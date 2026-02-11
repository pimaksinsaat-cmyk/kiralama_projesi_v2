import json
import traceback
import requests 
import xml.etree.ElementTree as ET 
from datetime import datetime, date
from decimal import Decimal
from flask import render_template, redirect, url_for, flash, request
from sqlalchemy import or_, and_
from sqlalchemy.orm import joinedload, subqueryload

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app import db
from app.kiralama import kiralama_bp

# Modeller
from app.firmalar.models import Firma
from app.kiralama.models import Kiralama, KiralamaKalemi
from app.filo.models import Ekipman
from app.cari.models import HizmetKaydi # Cari entegrasyonu için şart

from app.kiralama.forms import KiralamaForm

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYONLAR
# -------------------------------------------------------------------------

def get_tcmb_kurlari():
    """TCMB'den günlük kurları çeker."""
    rates = {'USD': 0.0, 'EUR': 0.0}
    try:
        url = "https://www.tcmb.gov.tr/kurlar/today.xml"
        response = requests.get(url, verify=False, timeout=2)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            usd = root.find("./Currency[@CurrencyCode='USD']/ForexSelling")
            eur = root.find("./Currency[@CurrencyCode='EUR']/ForexSelling")
            if usd is not None: rates['USD'] = float(usd.text)
            if eur is not None: rates['EUR'] = float(eur.text)
    except: pass
    return rates

def guncelle_cari_toplam(kiralama_id):
    """
    Kiralama sonlandırma/iptal durumlarında cariyi günceller.
    """
    try:
        kiralama = Kiralama.query.get(kiralama_id)
        if not kiralama: return

        # 1. Mevcut Gelir Kaydını Bul
        cari_kayit = HizmetKaydi.query.filter_by(
            fatura_no=kiralama.kiralama_form_no,
            yon='giden' # Gelir
        ).first()

        # 2. Toplamı Yeniden Hesapla
        toplam_gelir = Decimal('0.00')
        for kalem in kiralama.kalemler:
            if not (kalem.kiralama_baslangici and kalem.kiralama_bitis): continue
            
            # Gün farkı
            gun = (kalem.kiralama_bitis - kalem.kiralama_baslangici).days + 1
            if gun < 1: gun = 1
            
            # Fiyatlar (Decimal)
            brm = kalem.kiralama_brm_fiyat or Decimal('0')
            nakliye = kalem.nakliye_satis_fiyat or Decimal('0')
            
            toplam_gelir += (brm * gun) + nakliye

        # 3. Kaydı Güncelle
        if cari_kayit:
            cari_kayit.tutar = toplam_gelir
            cari_kayit.aciklama = f"Kiralama Geliri (Güncel): {kiralama.kiralama_form_no}"
            db.session.commit()
            
    except Exception as e:
        print(f"Cari güncelleme hatası: {e}")

# Form Select Seçeneklerini Doldurma
def get_pimaks_ekipman_choices(kiralama_objesi=None, include_ids=None):
    if include_ids is None: include_ids = []
    try:
        # Sadece boşta olanlar veya şu an bu kiralamada olanlar
        query = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.is_(None), 
            or_(Ekipman.calisma_durumu == 'bosta', Ekipman.id.in_(include_ids))
        )
        gecerli_ekipmanlar = query.order_by(Ekipman.kod).all()
        
        choices = [(e.id, f"{e.kod} ({e.tipi})") for e in gecerli_ekipmanlar]
        
        # Düzenleme modunda mevcut seçili olanları listeye ekle
        gecerli_ids = {e.id for e in gecerli_ekipmanlar}
        if kiralama_objesi:
            for k in kiralama_objesi.kalemler:
                if k.ekipman_id and k.ekipman_id not in gecerli_ids and k.ekipman:
                    if k.ekipman.firma_tedarikci_id is None: 
                        choices.append((k.ekipman_id, f"{k.ekipman.kod} (Seçili)"))
        
        choices.insert(0, (0, '--- Pimaks Filosu ---'))
        return choices
    except: return [(0, 'Hata')]

def get_tedarikci_choices():
    try:
        tedarikciler = Firma.query.filter_by(is_tedarikci=True, is_active=True).order_by(Firma.firma_adi).all()
        choices = [(f.id, f.firma_adi) for f in tedarikciler]
        choices.insert(0, (0, '--- Tedarikçi Seçiniz ---'))
        return choices
    except: return [(0, 'Hata')]

def populate_kiralama_form_choices(form, kiralama_objesi=None, include_ids=None):
    # Müşteri Listesi
    musteriler = Firma.query.filter_by(is_musteri=True, is_active=True).filter(Firma.firma_adi != 'Dahili Kasa İşlemleri').order_by(Firma.firma_adi).all()
    form.firma_musteri_id.choices = [(f.id, f.firma_adi) for f in musteriler]
    form.firma_musteri_id.choices.insert(0, (0, '--- Müşteri Seçiniz ---'))

    # Kalem İçi Seçenekler
    pimaks_list = get_pimaks_ekipman_choices(kiralama_objesi, include_ids)
    ted_list = get_tedarikci_choices()
    
    for subform in form.kalemler:
        subform.ekipman_id.choices = pimaks_list
        subform.harici_ekipman_tedarikci_id.choices = ted_list
        subform.nakliye_tedarikci_id.choices = ted_list

# -------------------------------------------------------------------------
# 1. KİRALAMA LİSTELEME
# -------------------------------------------------------------------------
@kiralama_bp.route('/index')
@kiralama_bp.route('/') 
def index():
    try:
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '', type=str)
        kurlar = get_tcmb_kurlari()
        
        query = Kiralama.query.options(joinedload(Kiralama.firma_musteri), joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.ekipman))
        
        if q:
            search = f"%{q}%"
            query = query.join(Firma).filter(or_(Kiralama.kiralama_form_no.ilike(search), Firma.firma_adi.ilike(search)))
            
        pagination = query.order_by(Kiralama.id.desc()).paginate(page=page, per_page=20)
        kiralamalar = pagination.items
        
        # Durum Hesaplamaları
        today = date.today()
        for k in kiralamalar:
            for kalem in k.kalemler:
                kalem.durum_mesaji = "Aktif"
                kalem.durum_sinifi = "success"
                
                if kalem.sonlandirildi:
                    kalem.durum_mesaji = "Tamamlandı"
                    kalem.durum_sinifi = "secondary"
                elif kalem.kiralama_bitis:
                    kalan = (kalem.kiralama_bitis - today).days
                    if kalan < 0:
                        kalem.durum_mesaji = f"Gecikti ({abs(kalan)} gün)"
                        kalem.durum_sinifi = "danger"
                    elif kalan == 0:
                        kalem.durum_mesaji = "Bugün Bitiyor"
                        kalem.durum_sinifi = "warning"

        return render_template('kiralama/index.html', kiralamalar=kiralamalar, pagination=pagination, q=q, kurlar=kurlar)
    except Exception as e:
        flash(f"Liste Hatası: {e}", "danger")
        return render_template('kiralama/index.html', kiralamalar=[], kurlar={})

# -------------------------------------------------------------------------
# -------------------------------------------------------------------------
# 2. YENİ KİRALAMA EKLEME (TAM VE GÜNCEL VERSİYON)
# -------------------------------------------------------------------------
@kiralama_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    # 1. URL Parametrelerini ve Ön Hazırlığı Al
    ekipman_id = request.args.get('ekipman_id', type=int)
    next_url = request.args.get('next', 'kiralama.index')
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str)

    # 2. Formu Başlat
    # POST isteğinde choices'ların (seçeneklerin) doğrulanması için form verisini çekiyoruz
    form = KiralamaForm()

    # 3. Akıllı Seçenek Doldurma (Choices)
    # Form validate olmadan önce bu seçeneklerin yüklenmesi ŞARTTIR.
    ids_in_form = []
    if request.method == 'POST':
        # Formdan gelen tüm ekipman ID'lerini listeye ekle (Validation hatası almamak için)
        ids_in_form = [int(k.ekipman_id.data) for k in form.kalemler if k.ekipman_id.data and int(k.ekipman_id.data) > 0]
    
    if ekipman_id: ids_in_form.append(ekipman_id)
    populate_kiralama_form_choices(form, include_ids=ids_in_form)

    # 4. GET İstekleri İçin Varsayılan Verileri Doldur
    if request.method == 'GET':
        # Kurlar
        kurlar = get_tcmb_kurlari()
        form.doviz_kuru_usd.data = Decimal(str(kurlar.get('USD', 0)))
        form.doviz_kuru_eur.data = Decimal(str(kurlar.get('EUR', 0)))
        
        # Form No
        last = Kiralama.query.order_by(Kiralama.id.desc()).first()
        new_id = (last.id + 1) if last else 1
        form.kiralama_form_no.data = f"PF-{datetime.now().year}/{new_id:04d}"

        # URL'den bir makine gelmişse onu listeye ekle
        if ekipman_id: 
            form.kalemler.append_entry({'ekipman_id': ekipman_id})

    # Context Yardımcı Fonksiyonu
    def get_context_data():
        return {
            'ekipman_choices_json': json.dumps(get_pimaks_ekipman_choices(None, ids_in_form)),
            'tedarikci_choices_json': json.dumps(get_tedarikci_choices()),
            'nakliye_tedarikci_choices_json': json.dumps(get_tedarikci_choices()),
            'next_url': next_url, 'page': page, 'q': q
        }

    # 5. FORM KAYIT SÜRECİ (POST)
    if form.validate_on_submit():
        dolu_satir_var = False
        
        # A. Boş Form Kontrolü
        for k in form.kalemler:
            e_id = int(k.ekipman_id.data or 0)
            is_dis = int(k.dis_tedarik_ekipman.data or 0)
            if e_id > 0 or is_dis == 1:
                dolu_satir_var = True
                break
        
        if not dolu_satir_var:
            flash("En az bir makine eklemelisiniz!", "warning")
            return render_template('kiralama/ekle.html', form=form, **get_context_data())

        try:
            # B. Kiralama Ana Başlığını Oluştur
            yeni_kiralama = Kiralama(
                kiralama_form_no=form.kiralama_form_no.data,
                firma_musteri_id=form.firma_musteri_id.data,
                kdv_orani=form.kdv_orani.data,
                doviz_kuru_usd=float(form.doviz_kuru_usd.data or 0),
                doviz_kuru_eur=float(form.doviz_kuru_eur.data or 0)
            )
            db.session.add(yeni_kiralama)
            db.session.flush() # ID'yi almak için flush yapıyoruz

            toplam_gelir = Decimal('0.00')

            # C. Kalemleri (Satırları) İşle
            for kalem_form in form.kalemler:
                # Veri hazırlama
                s_fiyat = kalem_form.kiralama_brm_fiyat.data or Decimal('0')
                a_fiyat = kalem_form.kiralama_alis_fiyat.data or Decimal('0')
                n_satis = kalem_form.nakliye_satis_fiyat.data or Decimal('0')
                n_alis = kalem_form.nakliye_alis_fiyat.data or Decimal('0')
                bas = kalem_form.kiralama_baslangici.data
                bit = kalem_form.kiralama_bitis.data
                
                if not (bas and bit): continue

                gun = (bit - bas).days + 1
                if gun < 1: gun = 1
                
                target_ekipman_id = None

                # I. DIŞ TEDARİK (SUB-RENT) MANTIĞI
                if int(kalem_form.dis_tedarik_ekipman.data or 0) == 1:
                    ted_id = kalem_form.harici_ekipman_tedarikci_id.data
                    seri = (kalem_form.harici_ekipman_seri_no.data or '').strip()

                    if not (ted_id and seri):
                        flash("Dış tedarik için Seri No ve Tedarikçi zorunlu!", "danger")
                        db.session.rollback()
                        return render_template('kiralama/ekle.html', form=form, **get_context_data())

                    # Seri no kontrolü/kaydı
                    harici = Ekipman.query.filter_by(seri_no=seri).first()
                    if not harici:
                        harici = Ekipman(
                            kod=f"TED-{seri}", seri_no=seri, firma_tedarikci_id=ted_id,
                            marka=kalem_form.harici_ekipman_marka.data,
                            model=kalem_form.harici_ekipman_model.data,
                            tipi=kalem_form.harici_ekipman_tipi.data,
                            calisma_yuksekligi=kalem_form.harici_ekipman_calisma_yuksekligi.data,
                            kaldirma_kapasitesi=kalem_form.harici_ekipman_kaldirma_kapasitesi.data,
                            uretim_tarihi=kalem_form.harici_ekipman_uretim_tarihi.data,
                            calisma_durumu='harici', is_active=True
                        )
                        db.session.add(harici)
                        db.session.flush()
                    
                    target_ekipman_id = harici.id
                    
                    # Tedarikçiye BORÇ (Gider Kaydı)
                    if a_fiyat > 0:
                        db.session.add(HizmetKaydi(
                            firma_id=ted_id, tarih=date.today(), tutar=(a_fiyat * gun),
                            yon='gelen', fatura_no=yeni_kiralama.kiralama_form_no,
                            aciklama=f"Dış Kiralama: {harici.marka} - {yeni_kiralama.kiralama_form_no}"
                        ))

                # II. PİMAKS MAKİNESİ MANTIĞI
                else:
                    target_ekipman_id = int(kalem_form.ekipman_id.data or 0)
                    if target_ekipman_id <= 0: continue
                    
                    ekip = Ekipman.query.get(target_ekipman_id)
                    if ekip: ekip.calisma_durumu = 'kirada'

                # III. KİRALAMA KALEMİNİ VERİTABANINA EKLE
                yeni_kalem = KiralamaKalemi(
                    kiralama_id=yeni_kiralama.id,
                    ekipman_id=target_ekipman_id,
                    kiralama_baslangici=bas, kiralama_bitis=bit,
                    kiralama_brm_fiyat=s_fiyat, kiralama_alis_fiyat=a_fiyat,
                    nakliye_satis_fiyat=n_satis, nakliye_alis_fiyat=n_alis,
                    nakliye_tedarikci_id=kalem_form.nakliye_tedarikci_id.data if int(kalem_form.dis_tedarik_nakliye.data or 0) == 1 else None
                )
                db.session.add(yeni_kalem)
                
                toplam_gelir += (s_fiyat * gun) + n_satis

                # IV. HARİCİ NAKLİYE GİDERİ
                if int(kalem_form.dis_tedarik_nakliye.data or 0) == 1 and n_alis > 0:
                    nak_id = kalem_form.nakliye_tedarikci_id.data
                    if nak_id:
                        db.session.add(HizmetKaydi(
                            firma_id=nak_id, tarih=date.today(), tutar=n_alis,
                            yon='gelen', fatura_no=yeni_kiralama.kiralama_form_no,
                            aciklama=f"Nakliye Hizmet Alımı: {yeni_kiralama.kiralama_form_no}"
                        ))

            # D. Müşteriye ALACAK (Gelir Kaydı)
            if toplam_gelir > 0:
                db.session.add(HizmetKaydi(
                    firma_id=form.firma_musteri_id.data, tarih=date.today(), tutar=toplam_gelir,
                    yon='giden', fatura_no=yeni_kiralama.kiralama_form_no, ozel_id=yeni_kiralama.id,
                    aciklama=f"Kiralama Hizmet Bedeli - {yeni_kiralama.kiralama_form_no}"
                ))

            db.session.commit()
            flash('Kiralama başarıyla kaydedildi.', 'success')
            return redirect(url_for('kiralama.index'))

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Kayıt Hatası: {str(e)}", "danger")

    return render_template('kiralama/ekle.html', form=form, **get_context_data())
# -------------------------------------------------------------------------
# 3. KİRALAMA DÜZENLEME
# -------------------------------------------------------------------------
@kiralama_bp.route('/duzenle/<int:kiralama_id>', methods=['GET', 'POST'])
def duzenle(kiralama_id):
    """
    Kiralama kaydını ve bağlı kalemlerini güncelleyen ana fonksiyon.
    Hata Düzeltmeleri:
    - IntegrityError (NOT NULL ekipman.uretim_tarihi) typo hatası düzeltildi.
    - 'str' object has no attribute 'data' hatası (Field erişim yöntemi) çözüldü.
    - IntegrityError (Dış tedarik flush hatası) çözümü korundu.
    - Pimaks eklemelerindeki veri eksikliği giderildi.
    - Boş liste ve choices NoneType hataları engellendi.
    """
    next_url = request.args.get('next', 'kiralama.index')
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str)

    # 1. Mevcut kaydı çek
    kiralama = Kiralama.query.options(
        joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.ekipman)
    ).get_or_404(kiralama_id)

    form = KiralamaForm()

    # --- 2. DİNAMİK CHOICES YÖNETİMİ ---
    ids_in_form = []
    if request.method == 'POST':
        for key, value in request.form.items():
            if '-ekipman_id' in key and value and str(value).isdigit() and int(value) > 0:
                ids_in_form.append(int(value))
    else:
        ids_in_form = [k.ekipman_id for k in kiralama.kalemler if k.ekipman_id]

    # --- 3. GET İSTEĞİ: FORMU DOLDUR ---
    if request.method == 'GET':
        form.firma_musteri_id.data = kiralama.firma_musteri_id
        form.kdv_orani.data = kiralama.kdv_orani
        form.doviz_kuru_usd.data = Decimal(str(kiralama.doviz_kuru_usd or 0))
        form.doviz_kuru_eur.data = Decimal(str(kiralama.doviz_kuru_eur or 0))
        form.kiralama_form_no.data = kiralama.kiralama_form_no

        while len(form.kalemler) > 0:
            form.kalemler.pop_entry()

        for kalem in kiralama.kalemler:
            k_data = {
                'id': kalem.id, 'ekipman_id': kalem.ekipman_id,
                'kiralama_baslangici': kalem.kiralama_baslangici,
                'kiralama_bitis': kalem.kiralama_bitis,
                'kiralama_brm_fiyat': kalem.kiralama_brm_fiyat,
                'kiralama_alis_fiyat': kalem.kiralama_alis_fiyat,
                'nakliye_satis_fiyat': kalem.nakliye_satis_fiyat,
                'nakliye_alis_fiyat': kalem.nakliye_alis_fiyat,
            }
            if kalem.ekipman and kalem.ekipman.firma_tedarikci_id:
                k_data.update({
                    'dis_tedarik_ekipman': True,
                    'harici_ekipman_tedarikci_id': kalem.ekipman.firma_tedarikci_id,
                    'harici_ekipman_seri_no': kalem.ekipman.seri_no,
                    'harici_ekipman_marka': kalem.ekipman.marka,
                    'harici_ekipman_model': kalem.ekipman.model,
                    'harici_ekipman_tipi': kalem.ekipman.tipi,
                    'harici_ekipman_calisma_yuksekligi': kalem.ekipman.calisma_yuksekligi,
                    'harici_ekipman_kaldirma_kapasitesi': kalem.ekipman.kaldirma_kapasitesi,
                    'harici_ekipman_uretim_tarihi': kalem.ekipman.uretim_tarihi
                })
            if kalem.nakliye_tedarikci_id:
                k_data.update({'dis_tedarik_nakliye': True, 'nakliye_tedarikci_id': kalem.nakliye_tedarikci_id})
            
            form.kalemler.append_entry(k_data)

    # --- 4. EMNİYET VE SON CHOICES ---
    if len(form.kalemler) == 0:
        form.kalemler.append_entry()
    
    populate_kiralama_form_choices(form, kiralama_objesi=kiralama, include_ids=ids_in_form)

    def get_context_data():
        return {
            'ekipman_choices_json': json.dumps(get_pimaks_ekipman_choices(kiralama, ids_in_form)),
            'tedarikci_choices_json': json.dumps(get_tedarikci_choices()),
            'nakliye_tedarikci_choices_json': json.dumps(get_tedarikci_choices()),
            'next_url': next_url, 'page': page, 'q': q, 'kiralama': kiralama
        }

    # --- 5. POST İSTEĞİ ---
    if form.validate_on_submit():
        try:
            # Cariyi sıfırla
            HizmetKaydi.query.filter_by(fatura_no=kiralama.kiralama_form_no).delete()
            
            kiralama.firma_musteri_id = form.firma_musteri_id.data
            kiralama.kdv_orani = form.kdv_orani.data
            
            toplam_gelir = Decimal('0.00')
            mevcut_kalem_idler = [k.id for k in kiralama.kalemler]
            formdan_gelen_idler = []

            for kalem_form in form.kalemler:
                # Alanlara ['isim'] şeklinde erişmek nesne çakışmalarını önler
                raw_eid = kalem_form['ekipman_id'].data
                is_dis = kalem_form['dis_tedarik_ekipman'].data
                
                if (not raw_eid or int(raw_eid) == 0) and not is_dis:
                    continue

                bas = kalem_form['kiralama_baslangici'].data
                bit = kalem_form['kiralama_bitis'].data
                if not (bas and bit): continue 

                # ID'yi sözlük anahtarı gibi çekiyoruz
                val_id_raw = kalem_form['id'].data
                aktif_kalem = None
                if val_id_raw and str(val_id_raw).isdigit():
                    aktif_kalem = KiralamaKalemi.query.get(int(val_id_raw))

                if aktif_kalem and aktif_kalem.sonlandirildi:
                    bas, bit = aktif_kalem.kiralama_baslangici, aktif_kalem.kiralama_bitis
                
                gun = max((bit - bas).days + 1, 1)
                s_brm = kalem_form['kiralama_brm_fiyat'].data or Decimal('0')
                n_satis = kalem_form['nakliye_satis_fiyat'].data or Decimal('0')
                toplam_gelir += (s_brm * gun) + n_satis

                target_ekipman_id = int(raw_eid or 0)
                
                if is_dis:
                    seri = (kalem_form['harici_ekipman_seri_no'].data or '').strip()
                    harici = Ekipman.query.filter_by(seri_no=seri).first()
                    if not harici:
                        harici = Ekipman(
                            kod=f"TED-{seri}", seri_no=seri, 
                            firma_tedarikci_id=kalem_form['harici_ekipman_tedarikci_id'].data, 
                            calisma_durumu='harici', is_active=True,
                            uretim_tarihi=int(kalem_form['harici_ekipman_uretim_tarihi'].data or datetime.now().year)
                        )
                        db.session.add(harici)
                        db.session.flush()
                    
                    harici.marka = kalem_form['harici_ekipman_marka'].data
                    harici.model = kalem_form['harici_ekipman_model'].data
                    # DÜZELTME: Typo hatası giderildi (tırnak içinden .data çıkarıldı)
                    harici.uretim_tarihi = int(kalem_form['harici_ekipman_uretim_tarihi'].data or harici.uretim_tarihi or datetime.now().year)
                    target_ekipman_id = harici.id
                    
                    a_brm = kalem_form['kiralama_alis_fiyat'].data or Decimal('0')
                    if a_brm > 0:
                        db.session.add(HizmetKaydi(
                            firma_id=kalem_form['harici_ekipman_tedarikci_id'].data, tarih=date.today(), 
                            tutar=(a_brm * gun), yon='gelen', fatura_no=kiralama.kiralama_form_no, 
                            aciklama=f"Dış Kiralama (Düzeltme): {harici.marka}"
                        ))
                else:
                    if aktif_kalem and aktif_kalem.ekipman_id and aktif_kalem.ekipman_id != target_ekipman_id and not aktif_kalem.sonlandirildi:
                        eski = Ekipman.query.get(aktif_kalem.ekipman_id)
                        if eski and eski.firma_tedarikci_id is None: eski.calisma_durumu = 'bosta'
                    
                    if target_ekipman_id and (not aktif_kalem or not aktif_kalem.sonlandirildi):
                        yeni = Ekipman.query.get(target_ekipman_id)
                        if yeni: yeni.calisma_durumu = 'kirada'

                if not aktif_kalem:
                    aktif_kalem = KiralamaKalemi(
                        kiralama_id=kiralama.id,
                        ekipman_id=target_ekipman_id,
                        kiralama_baslangici=bas,
                        kiralama_bitis=bit,
                        kiralama_brm_fiyat=s_brm,
                        nakliye_satis_fiyat=n_satis,
                        kiralama_alis_fiyat=kalem_form['kiralama_alis_fiyat'].data or Decimal('0'),
                        nakliye_alis_fiyat=kalem_form['nakliye_alis_fiyat'].data or Decimal('0'),
                        nakliye_tedarikci_id=kalem_form['nakliye_tedarikci_id'].data if kalem_form['dis_tedarik_nakliye'].data else None
                    )
                    db.session.add(aktif_kalem)
                    db.session.flush()
                    formdan_gelen_idler.append(aktif_kalem.id)
                else:
                    aktif_kalem.ekipman_id = target_ekipman_id
                    aktif_kalem.kiralama_baslangici = bas
                    aktif_kalem.kiralama_bitis = bit
                    aktif_kalem.kiralama_brm_fiyat = s_brm
                    aktif_kalem.nakliye_satis_fiyat = n_satis
                    aktif_kalem.kiralama_alis_fiyat = kalem_form['kiralama_alis_fiyat'].data or Decimal('0')
                    aktif_kalem.nakliye_alis_fiyat = kalem_form['nakliye_alis_fiyat'].data or Decimal('0')
                    aktif_kalem.nakliye_tedarikci_id = kalem_form['nakliye_tedarikci_id'].data if kalem_form['dis_tedarik_nakliye'].data else None
                    formdan_gelen_idler.append(aktif_kalem.id)

            for eski_id in mevcut_kalem_idler:
                if eski_id not in formdan_gelen_idler:
                    sil = KiralamaKalemi.query.get(eski_id)
                    if sil:
                        if sil.ekipman and sil.ekipman.firma_tedarikci_id is None: sil.ekipman.calisma_durumu = 'bosta'
                        db.session.delete(sil)

            if toplam_gelir > 0:
                db.session.add(HizmetKaydi(
                    firma_id=kiralama.firma_musteri_id, tarih=date.today(), tutar=toplam_gelir, 
                    yon='giden', fatura_no=kiralama.kiralama_form_no, ozel_id=kiralama.id, 
                    aciklama=f"Kiralama Bedeli (Düzeltme) - {kiralama.kiralama_form_no}"
                ))

            db.session.commit()
            flash('Kiralama başarıyla güncellendi.', 'success')
            return redirect(url_for('kiralama.index'))

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Güncelleme Hatası: {str(e)}", "danger")

    if form.errors:
        for field, errors in form.errors.items():
            for error in errors: flash(f"Hata ({field}): {error}", "warning")

    return render_template('kiralama/duzelt.html', form=form, **get_context_data())
# -------------------------------------------------------------------------
# 4. SİLME VE SONLANDIRMA
# -------------------------------------------------------------------------
@kiralama_bp.route('/sil/<int:kiralama_id>', methods=['POST'])
def sil(kiralama_id):
    kiralama = Kiralama.query.get_or_404(kiralama_id)
    try:
        HizmetKaydi.query.filter_by(fatura_no=kiralama.kiralama_form_no).delete()
        for kalem in kiralama.kalemler:
            if kalem.ekipman and kalem.ekipman.firma_tedarikci_id is None:
                kalem.ekipman.calisma_durumu = 'bosta'
        db.session.delete(kiralama)
        db.session.commit()
        flash('Kiralama silindi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {e}', 'danger')
    return redirect(url_for('kiralama.index'))

@kiralama_bp.route('/kalem/sonlandir', methods=['POST'])
def sonlandir_kalem():
    try:
        kalem_id = request.form.get('kalem_id', type=int)
        bitis_str = request.form.get('bitis_tarihi')
        kalem = KiralamaKalemi.query.get_or_404(kalem_id)
        
        if bitis_str:
            kalem.kiralama_bitis = datetime.strptime(bitis_str, '%Y-%m-%d').date()
        
        kalem.sonlandirildi = True
        if kalem.ekipman and kalem.ekipman.firma_tedarikci_id is None:
            kalem.ekipman.calisma_durumu = 'bosta'
        
        db.session.commit()
        guncelle_cari_toplam(kalem.kiralama_id)
        flash("Kalem sonlandırıldı.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Hata: {e}", "danger")
    return redirect(url_for('kiralama.index'))

@kiralama_bp.route('/kalem/iptal_et', methods=['POST'])
def iptal_et_kalem():
    try:
        kalem_id = request.form.get('kalem_id', type=int)
        kalem = KiralamaKalemi.query.get_or_404(kalem_id)
        if not kalem.sonlandirildi: return redirect(url_for('kiralama.index'))

        kalem.sonlandirildi = False
        if kalem.ekipman and kalem.ekipman.firma_tedarikci_id is None:
            kalem.ekipman.calisma_durumu = 'kirada'
            
        db.session.commit()
        guncelle_cari_toplam(kalem.kiralama_id)
        flash("Sonlandırma geri alındı.", "success")
    except Exception as e:
        db.session.rollback(); flash(f"Hata: {e}", "danger")
    return redirect(url_for('kiralama.index'))