import json
import traceback
import requests 
import xml.etree.ElementTree as ET 
from datetime import datetime, timezone, date
from decimal import Decimal
from flask import render_template, redirect, url_for, flash, jsonify, request
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, subqueryload
import urllib3
# SSL uyarılarını gizle
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)



from app.kiralama import kiralama_bp

# Firmalar (Kendi klasörü)
from app.firmalar.models import Firma

# Kiralama Klasöründen Gelenler
from app.kiralama.models import Kiralama, KiralamaKalemi

# Filo Klasöründen Gelenler
from app.filo.models import Ekipman, BakimKaydi, KullanilanParca, StokKarti, StokHareket

# Cari Klasöründen Gelenler
from app.cari.models import Kasa, Odeme, HizmetKaydi


from app.forms import KiralamaForm, KiralamaKalemiForm 

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYONLAR
# -------------------------------------------------------------------------
def clean_currency_input(value_str):
    """
    1.500,00 formatını 1500.00 float formatına çevirir.
    """
    if not value_str: return '0.0'
    val = str(value_str).strip()
    if ',' in val:
        val = val.replace('.', '') 
        val = val.replace(',', '.') 
    return val

def get_tcmb_kurlari():
    """
    TCMB'den günlük kurları çeker.
    """
    rates = {'USD': 0.0, 'EUR': 0.0}
    try:
        url = "https://www.tcmb.gov.tr/kurlar/today.xml"
        response = requests.get(url, verify=False, timeout=5)
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
    Kiralamanın toplam tutarını hesaplar ve müşteri carisine (HizmetKaydi - Gelir) işler.
    """
    try:
        kiralama = Kiralama.query.get(kiralama_id)
        if not kiralama: return

        toplam_gelir = Decimal(0.0)
        
        for kalem in kiralama.kalemler:
            # Tarihleri al
            if kalem.sonlandirildi and kalem.kiralama_bitis:
                bitis_dt = datetime.strptime(kalem.kiralama_bitis, "%Y-%m-%d").date()
            else:
                bitis_dt = datetime.strptime(kalem.kiralama_bitis, "%Y-%m-%d").date()
                
            baslangic_dt = datetime.strptime(kalem.kiralama_baslangıcı, "%Y-%m-%d").date()
            
            # Gün farkı
            gun_sayisi = (bitis_dt - baslangic_dt).days + 1
            if gun_sayisi < 1: gun_sayisi = 1
            
            # Tutar hesabı
            brm = Decimal(kalem.kiralama_brm_fiyat or 0)
            nakliye = Decimal(kalem.nakliye_satis_fiyat or 0)
            toplam_gelir += (brm * gun_sayisi) + nakliye

        # Müşteri Cari Kaydını Güncelle (Gelir)
        cari_kayit = HizmetKaydi.query.filter_by(
            firma_id=kiralama.firma_musteri_id,
            fatura_no=kiralama.kiralama_form_no,
            yon='giden' # Gelir faturası
        ).first()
        
        if cari_kayit:
            cari_kayit.tutar = str(toplam_gelir)
            cari_kayit.aciklama = f"Kiralama Geliri (Güncel): {kiralama.kiralama_form_no}"
        
        db.session.commit()
    except Exception as e:
        print(f"Cari güncelleme hatası: {e}")

# Form doldurma yardımcıları
def get_pimaks_ekipman_choices(kiralama_objesi=None, include_ids=None):
    if include_ids is None: include_ids = []
    try:
        query = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.is_(None), 
            or_(Ekipman.calisma_durumu == 'bosta', Ekipman.id.in_(include_ids))
        )
        gecerli_ekipmanlar = query.order_by(Ekipman.kod).all()
        gecerli_ids = {e.id for e in gecerli_ekipmanlar}
        choices = [(e.id, f"{e.kod} ({e.tipi})") for e in gecerli_ekipmanlar]
        
        if kiralama_objesi:
            for k in kiralama_objesi.kalemler:
                if k.ekipman_id and k.ekipman_id not in gecerli_ids and k.ekipman and k.ekipman.firma_tedarikci_id is None:
                    choices.append((k.ekipman_id, f"{k.ekipman.kod} (Şu an Kirada)"))
        
        choices.insert(0, ('0', '--- Pimaks Filosu ---'))
        return choices
    except: return [('0', 'Hata')]

def get_tedarikci_choices(include_pimaks=False):
    try:
        tedarikciler = Firma.query.filter_by(is_tedarikci=True).order_by(Firma.firma_adi).all()
        choices = [(f.id, f.firma_adi) for f in tedarikciler]
        choices.insert(0, ('0', '--- Tedarikçi Seçiniz ---'))
        return choices
    except: return [('0', 'Hata')]

def populate_kiralama_form_choices(form, kiralama_objesi=None, include_ids=None):
    try:
        musteriler = Firma.query.filter_by(is_musteri=True).order_by(Firma.firma_adi).all()
        form.firma_musteri_id.choices = [(f.id, f.firma_adi) for f in musteriler]
        form.firma_musteri_id.choices.insert(0, ('0', '--- Müşteri Seçiniz ---'))
    except: form.firma_musteri_id.choices = []

    pimaks_list = get_pimaks_ekipman_choices(kiralama_objesi, include_ids)
    ted_list = get_tedarikci_choices()
    
    for subform in form.kalemler:
        subform.form.ekipman_id.choices = pimaks_list
        subform.form.harici_ekipman_tedarikci_id.choices = ted_list
        subform.form.nakliye_tedarikci_id.choices = ted_list

@kiralama_bp.app_template_filter('tarihtr')
def tarihtr(value):
    if not value: return ""
    if isinstance(value, str):
        try: value = datetime.strptime(value, '%Y-%m-%d')
        except: return value
    return value.strftime("%d.%m.%Y")

# -------------------------------------------------------------------------
# 3. KİRALAMA LİSTELEME
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
        
        today = date.today()
        for k in kiralamalar:
            for kalem in k.kalemler:
                # --- DURUM HESAPLAMASI ---
                kalem.durum_mesaji = "Aktif"
                kalem.durum_sinifi = "success"
                kalem.sure_bilgisi = "" # Başlangıçta boş

                if kalem.sonlandirildi:
                    kalem.durum_mesaji = "Tamamlandı"
                    kalem.durum_sinifi = "secondary"
                
                # --- SÜRE HESAPLAMASI ---
                if kalem.kiralama_bitis and kalem.kiralama_baslangıcı:
                    try:
                        baslangic_dt = datetime.strptime(kalem.kiralama_baslangıcı, '%Y-%m-%d').date()
                        bitis_dt = datetime.strptime(kalem.kiralama_bitis, '%Y-%m-%d').date()
                        
                        toplam_gun = (bitis_dt - baslangic_dt).days + 1
                        gecen_gun = (today - baslangic_dt).days + 1
                        
                        if kalem.sonlandirildi:
                            kalem.sure_bilgisi = f"Toplam {toplam_gun} Gün Sürdü"
                        elif gecen_gun < 1:
                            kalem.sure_bilgisi = f"Henüz Başlamadı (Plan: {toplam_gun} Gün)"
                        else:
                            kalem.sure_bilgisi = f"{gecen_gun}. Gün / Toplam {toplam_gun} Gün"

                        # Kalan gün hesaplaması ve renk kodlaması
                        kalan_gun = (bitis_dt - today).days
                        if not kalem.sonlandirildi:
                            if kalan_gun < 0:
                                kalem.durum_mesaji = f"Gecikti ({abs(kalan_gun)} gün)"
                                kalem.durum_sinifi = "danger"
                            elif kalan_gun == 0:
                                kalem.durum_mesaji = "BUGÜN BİTİYOR"
                                kalem.durum_sinifi = "warning"
                            elif kalan_gun <= 7:
                                kalem.durum_mesaji = f"Bitiyor ({kalan_gun} gün)"
                                kalem.durum_sinifi = "warning"
                                
                    except Exception as e:
                        print(f"Hata sure/durum hesaplama: {e}")
                        kalem.durum_mesaji = "Tarih Hatası"
                        kalem.durum_sinifi = "dark"


        return render_template('kiralama/index.html', kiralamalar=kiralamalar, pagination=pagination, q=q, kurlar=kurlar)
    except Exception as e:
        flash(f"Hata: {e}", "danger")
        return render_template('kiralama/index.html', kiralamalar=[], kurlar={})

# -------------------------------------------------------------------------
# 4. YENİ KİRALAMA EKLEME
# -------------------------------------------------------------------------
@kiralama_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    ekipman_id = request.args.get('ekipman_id', type=int)
    next_url = request.args.get('next', 'kiralama.index')
    page = request.args.get('page')
    q = request.args.get('q')
    
    kurlar = get_tcmb_kurlari()
    
    if request.method == 'GET':
        form = KiralamaForm()
        if ekipman_id:
            form.kalemler.append_entry({'ekipman_id': ekipman_id})
        else:
            if not form.kalemler: form.kalemler.append_entry()
            
        form.doviz_kuru_usd.data = Decimal(kurlar.get('USD', 0))
        form.doviz_kuru_eur.data = Decimal(kurlar.get('EUR', 0))
        
        last = Kiralama.query.order_by(Kiralama.id.desc()).first()
        new_id = (last.id + 1) if last else 1
        form.kiralama_form_no.data = f"PF-{datetime.now().year}/{new_id:04d}"
        
    else:
        form = KiralamaForm()

    populate_kiralama_form_choices(form, include_ids=[ekipman_id] if ekipman_id else [])

    # Hata durumunda context_data'yı hızlı oluşturmak için fonksiyon
    def get_context_data():
        return {
            'ekipman_choices_json': json.dumps(get_pimaks_ekipman_choices(None, [ekipman_id] if ekipman_id else [])),
            'tedarikci_choices_json': json.dumps(get_tedarikci_choices()),
            'nakliye_tedarikci_choices_json': json.dumps(get_tedarikci_choices()),
            'next_url': next_url,
            'page': page,
            'q': q
        }

    if form.validate_on_submit():
        try:
            yeni_kiralama = Kiralama(
                kiralama_form_no=form.kiralama_form_no.data,
                firma_musteri_id=form.firma_musteri_id.data,
                kdv_orani=form.kdv_orani.data,
                doviz_kuru_usd=float(form.doviz_kuru_usd.data or 0),
                doviz_kuru_eur=float(form.doviz_kuru_eur.data or 0)
            )
            db.session.add(yeni_kiralama)
            db.session.flush()

            toplam_gelir = Decimal(0)
            
            for kalem_form in form.kalemler:
                baslangic = kalem_form.kiralama_baslangıcı.data
                bitis = kalem_form.kiralama_bitis.data
                gun_sayisi = (bitis - baslangic).days + 1
                if gun_sayisi < 1: gun_sayisi = 1
                
                satis_fiyati = Decimal(clean_currency_input(kalem_form.kiralama_brm_fiyat.data))
                alis_fiyati = Decimal(clean_currency_input(kalem_form.kiralama_alis_fiyat.data))
                nakliye_satis = Decimal(clean_currency_input(kalem_form.nakliye_satis_fiyat.data))
                nakliye_alis = Decimal(clean_currency_input(kalem_form.nakliye_alis_fiyat.data))
                
                ekipman_id_to_use = None
                
                # A. DIŞ TEDARİK
                if kalem_form.dis_tedarik_ekipman.data:
                    tedarikci_id = kalem_form.harici_ekipman_tedarikci_id.data
                    seri_no = kalem_form.harici_ekipman_seri_no.data.strip()
                    
                    if not (tedarikci_id and seri_no):
                        flash("Dış tedarik için Tedarikçi ve Seri No zorunludur!", "danger")
                        return render_template('kiralama/ekle.html', form=form, **get_context_data())

                    # --- SERİ NO MANTIĞI (TEKRAR KİRALAMA) ---
                    mevcut_makine = Ekipman.query.filter_by(seri_no=seri_no).first()
                    
                    harici = None
                    if mevcut_makine:
                        if mevcut_makine.firma_tedarikci_id != tedarikci_id:
                            owner_name = mevcut_makine.firma_tedarikci.firma_adi if mevcut_makine.firma_tedarikci else "Pimaks Stok"
                            flash(f"HATA: '{seri_no}' seri numaralı makine zaten '{owner_name}' firmasına kayıtlı! Farklı tedarikçiden aynı seri no girilemez.", "danger")
                            return render_template('kiralama/ekle.html', form=form, **get_context_data())
                        else:
                            harici = mevcut_makine
                            harici.marka = kalem_form.harici_ekipman_marka.data or harici.marka
                            harici.model = kalem_form.harici_ekipman_model.data or harici.model
                            harici.tipi = kalem_form.harici_ekipman_tipi.data or harici.tipi
                            harici.calisma_durumu = 'harici'
                            if not harici.is_active: harici.is_active = True
                    else:
                        harici = Ekipman(
                            kod=f"TED-{seri_no}", 
                            marka=kalem_form.harici_ekipman_marka.data or "Bilinmiyor",
                            model=kalem_form.harici_ekipman_model.data or "",
                            tipi=kalem_form.harici_ekipman_tipi.data or "Harici",
                            seri_no=seri_no,
                            firma_tedarikci_id=tedarikci_id,
                            calisma_durumu='harici',
                            calisma_yuksekligi=0, kaldirma_kapasitesi=0, uretim_tarihi="2000"
                        )
                        db.session.add(harici)
                        db.session.flush()
                    
                    ekipman_id_to_use = harici.id
                    
                    # TEDARİKÇİ GİDER KAYDI
                    if alis_fiyati > 0:
                        gider_tutar = alis_fiyati * gun_sayisi
                        hizmet_gider = HizmetKaydi(
                            firma_id=tedarikci_id,
                            tarih=datetime.now().strftime('%Y-%m-%d'),
                            tutar=str(gider_tutar),
                            yon='gelen',  # Gider
                            aciklama=f"Dış Kiralama Gideri: {harici.marka} ({harici.seri_no}) - Form: {yeni_kiralama.kiralama_form_no}",
                            fatura_no=yeni_kiralama.kiralama_form_no
                        )
                        db.session.add(hizmet_gider)

                # B. PİMAKS MAKİNESİ
                else:
                    ekipman_id_to_use = kalem_form.ekipman_id.data
                    if not ekipman_id_to_use: continue
                    ekip = Ekipman.query.get(ekipman_id_to_use)
                    ekip.calisma_durumu = 'kirada'
                
                # KALEM KAYDI
                yeni_kalem = KiralamaKalemi(
                    kiralama_id=yeni_kiralama.id,
                    ekipman_id=ekipman_id_to_use,
                    kiralama_baslangıcı=baslangic.strftime('%Y-%m-%d'),
                    kiralama_bitis=bitis.strftime('%Y-%m-%d'),
                    kiralama_brm_fiyat=str(satis_fiyati),
                    kiralama_alis_fiyat=str(alis_fiyati),
                    nakliye_satis_fiyat=str(nakliye_satis),
                    nakliye_alis_fiyat=str(nakliye_alis),
                    nakliye_tedarikci_id=kalem_form.nakliye_tedarikci_id.data if kalem_form.dis_tedarik_nakliye.data else None
                )
                db.session.add(yeni_kalem)
                
                toplam_gelir += (satis_fiyati * gun_sayisi) + nakliye_satis
                
                # NAKLİYE GİDER KAYDI
                if kalem_form.dis_tedarik_nakliye.data and nakliye_alis > 0:
                    nakliye_firma_id = kalem_form.nakliye_tedarikci_id.data
                    if nakliye_firma_id:
                        hizmet_nakliye = HizmetKaydi(
                            firma_id=nakliye_firma_id,
                            tarih=datetime.now().strftime('%Y-%m-%d'),
                            tutar=str(nakliye_alis),
                            yon='gelen', # Gider
                            aciklama=f"Dış Nakliye Gideri - Form: {yeni_kiralama.kiralama_form_no}",
                            fatura_no=yeni_kiralama.kiralama_form_no
                        )
                        db.session.add(hizmet_nakliye)

            # MÜŞTERİ GELİR KAYDI
            if toplam_gelir > 0:
                hizmet_gelir = HizmetKaydi(
                    firma_id=form.firma_musteri_id.data,
                    tarih=datetime.now().strftime('%Y-%m-%d'),
                    tutar=str(toplam_gelir),
                    yon='giden', # Gelir
                    aciklama=f"Kiralama Hizmet Bedeli - Form: {yeni_kiralama.kiralama_form_no}",
                    fatura_no=yeni_kiralama.kiralama_form_no
                )
                db.session.add(hizmet_gelir)

            db.session.commit()
            flash('Kiralama başarıyla oluşturuldu.', 'success')
            return redirect(url_for('kiralama.index'))

        except Exception as e:
            db.session.rollback()
            flash(f"Hata: {str(e)}", "danger")
            traceback.print_exc()
    
    return render_template('kiralama/ekle.html', form=form, **get_context_data())

# -------------------------------------------------------------------------
# 5. KİRALAMA DÜZENLEME (TAM VE DETAYLI VERSİYON)
# -------------------------------------------------------------------------
@kiralama_bp.route('/duzenle/<int:kiralama_id>', methods=['GET', 'POST'])
def duzenle(kiralama_id):
    kiralama = Kiralama.query.options(joinedload(Kiralama.firma_musteri), joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.ekipman)).get_or_404(kiralama_id)

    if request.method == 'POST':
        form = KiralamaForm()
    else:
        form = KiralamaForm(obj=kiralama)
    
    populate_kiralama_form_choices(form, kiralama_objesi=kiralama)
    
    if request.method == 'GET':
        form.firma_musteri_id.data = kiralama.firma_musteri_id
        form.kdv_orani.data = kiralama.kdv_orani
        form.doviz_kuru_usd.data = Decimal(kiralama.doviz_kuru_usd or 0)
        form.doviz_kuru_eur.data = Decimal(kiralama.doviz_kuru_eur or 0)
        
        while len(form.kalemler) > 0: form.kalemler.pop_entry()
        
        for kalem in kiralama.kalemler:
            kalem_data = {}
            kalem_data['id'] = kalem.id
            kalem_data['ekipman_id'] = kalem.ekipman_id
            kalem_data['kiralama_baslangıcı'] = datetime.strptime(kalem.kiralama_baslangıcı, '%Y-%m-%d').date()
            kalem_data['kiralama_bitis'] = datetime.strptime(kalem.kiralama_bitis, '%Y-%m-%d').date()
            kalem_data['kiralama_brm_fiyat'] = Decimal(kalem.kiralama_brm_fiyat or 0)
            kalem_data['kiralama_alis_fiyat'] = Decimal(kalem.kiralama_alis_fiyat or 0)
            kalem_data['nakliye_satis_fiyat'] = Decimal(kalem.nakliye_satis_fiyat or 0)
            kalem_data['nakliye_alis_fiyat'] = Decimal(kalem.nakliye_alis_fiyat or 0)
            
            if kalem.ekipman and kalem.ekipman.firma_tedarikci_id:
                kalem_data['dis_tedarik_ekipman'] = True
                kalem_data['harici_ekipman_tedarikci_id'] = kalem.ekipman.firma_tedarikci_id
                kalem_data['harici_ekipman_tipi'] = kalem.ekipman.tipi
                kalem_data['harici_ekipman_marka'] = kalem.ekipman.marka
                kalem_data['harici_ekipman_model'] = kalem.ekipman.model
                kalem_data['harici_ekipman_seri_no'] = kalem.ekipman.seri_no
                kalem_data['harici_ekipman_calisma_yuksekligi'] = kalem.ekipman.calisma_yuksekligi
                kalem_data['harici_ekipman_kaldirma_kapasitesi'] = kalem.ekipman.kaldirma_kapasitesi
            
            if kalem.nakliye_tedarikci_id:
                kalem_data['dis_tedarik_nakliye'] = True
                kalem_data['nakliye_tedarikci_id'] = kalem.nakliye_tedarikci_id
            
            form.kalemler.append_entry(kalem_data)

    # Context data helper
    def get_context_data():
        return {
            'ekipman_choices_json': json.dumps(get_pimaks_ekipman_choices(kiralama, [k.ekipman_id for k in kiralama.kalemler])),
            'tedarikci_choices_json': json.dumps(get_tedarikci_choices(include_pimaks=False)),
            'nakliye_tedarikci_choices_json': json.dumps(get_tedarikci_choices(include_pimaks=True))
        }

    if form.validate_on_submit():
        original_db_kalemler = {k.id: k for k in kiralama.kalemler if not k.sonlandirildi}
        original_pimaks_ekipman_ids = {k.ekipman_id for k in original_db_kalemler.values() if k.ekipman and k.ekipman.firma_tedarikci_id is None}
        
        try:
            # 1. Cari Kayıtları Temizle
            HizmetKaydi.query.filter_by(fatura_no=kiralama.kiralama_form_no).delete()
            
            kiralama.kiralama_form_no = form.kiralama_form_no.data
            kiralama.firma_musteri_id = form.firma_musteri_id.data
            kiralama.kdv_orani = form.kdv_orani.data
            
            form_kalemler_map = {} 
            yeni_pimaks_ekipman_idler = set()
            ekipmanlar_to_update_status = {} 
            
            toplam_gelir = Decimal(0)

            for kalem_data in form.kalemler.data:
                db_kalem = None
                kalem_id_str = str(kalem_data.get('id') or '')
                if kalem_id_str.isdigit() and int(kalem_id_str) > 0:
                    db_kalem = KiralamaKalemi.query.get(int(kalem_id_str))
                    if db_kalem and db_kalem.sonlandirildi:
                        if db_kalem.ekipman and db_kalem.ekipman.firma_tedarikci_id is None:
                            yeni_pimaks_ekipman_idler.add(db_kalem.ekipman_id)
                        continue 

                ekipman_id_to_use = None
                
                satis_fiyati = Decimal(clean_currency_input(str(kalem_data['kiralama_brm_fiyat'])))
                alis_fiyati = Decimal(clean_currency_input(str(kalem_data['kiralama_alis_fiyat'])))
                nakliye_satis = Decimal(clean_currency_input(str(kalem_data['nakliye_satis_fiyat'])))
                nakliye_alis = Decimal(clean_currency_input(str(kalem_data['nakliye_alis_fiyat'])))
                
                baslangic = kalem_data['kiralama_baslangıcı']
                bitis = kalem_data['kiralama_bitis']
                gun_sayisi = (bitis - baslangic).days + 1
                if gun_sayisi < 1: gun_sayisi = 1
                
                toplam_gelir += (satis_fiyati * gun_sayisi) + nakliye_satis

                # A. DIŞ TEDARİK (GÜNCELLEME)
                if kalem_data['dis_tedarik_ekipman']:
                    tedarikci_id = kalem_data['harici_ekipman_tedarikci_id']
                    seri_no = (kalem_data['harici_ekipman_seri_no'] or '').strip()
                    
                    if not (tedarikci_id and seri_no): raise ValueError("Dış tedarik bilgileri eksik.")
                    
                    # GLOBAL SERİ NO KONTROLÜ (RE-RENTAL)
                    mevcut_makine = Ekipman.query.filter_by(seri_no=seri_no).first()
                    
                    harici_ekipman = None
                    if mevcut_makine:
                        if mevcut_makine.firma_tedarikci_id != tedarikci_id:
                             owner_name = mevcut_makine.firma_tedarikci.firma_adi if mevcut_makine.firma_tedarikci else "Pimaks Stok"
                             flash(f"HATA: '{seri_no}' seri numaralı makine zaten '{owner_name}' üzerinde kayıtlı!", "danger")
                             return render_template('kiralama/duzelt.html', form=form, kiralama=kiralama, **get_context_data())
                        else:
                             # Mevcut kaydı kullan (Tekrar Kiralama)
                             harici_ekipman = mevcut_makine
                             harici_ekipman.marka = kalem_data['harici_ekipman_marka']
                             harici_ekipman.model = kalem_data['harici_ekipman_model']
                             if not harici_ekipman.is_active: harici_ekipman.is_active = True
                    else:
                        harici_ekipman = Ekipman(
                            kod=f"TED-{seri_no}", 
                            seri_no=seri_no, 
                            tipi=kalem_data['harici_ekipman_tipi'], 
                            marka=kalem_data['harici_ekipman_marka'], 
                            model=kalem_data['harici_ekipman_model'], 
                            yakit="Bilinmiyor", 
                            calisma_yuksekligi=int(kalem_data.get('harici_ekipman_calisma_yuksekligi') or 0), 
                            kaldirma_kapasitesi=int(kalem_data.get('harici_ekipman_kaldirma_kapasitesi') or 0), 
                            uretim_tarihi="2000", 
                            giris_maliyeti='0', 
                            firma_tedarikci_id=tedarikci_id, 
                            calisma_durumu='harici', is_active=True
                        )
                        db.session.add(harici_ekipman)
                        db.session.flush()
                    
                    ekipman_id_to_use = harici_ekipman.id
                    
                    # TEDARİKÇİ CARİ YENİDEN
                    if alis_fiyati > 0:
                        gider_tutar = alis_fiyati * gun_sayisi
                        hizmet_gider = HizmetKaydi(
                            firma_id=tedarikci_id,
                            tarih=datetime.now().strftime('%Y-%m-%d'),
                            tutar=str(gider_tutar),
                            yon='gelen',
                            aciklama=f"Dış Kiralama Gideri: {harici_ekipman.marka} ({harici_ekipman.seri_no}) - Form: {kiralama.kiralama_form_no}",
                            fatura_no=kiralama.kiralama_form_no
                        )
                        db.session.add(hizmet_gider)

                # B. PİMAKS EKİPMANI (GÜNCELLEME)
                else:
                    ekipman_id_to_use = kalem_data['ekipman_id']
                    if not (ekipman_id_to_use and ekipman_id_to_use > 0): continue 
                    if ekipman_id_to_use in yeni_pimaks_ekipman_idler: raise ValueError("Aynı ekipman iki kere seçilemez.")
                    
                    ekipman_to_update = Ekipman.query.get(ekipman_id_to_use)
                    if not ekipman_to_update: raise ValueError("Ekipman bulunamadı.")
                    
                    if (ekipman_to_update.calisma_durumu != 'bosta' and ekipman_id_to_use not in original_pimaks_ekipman_ids): 
                        raise ValueError(f"Ekipman {ekipman_to_update.kod} şu an müsait değil.")
                    
                    yeni_pimaks_ekipman_idler.add(ekipman_id_to_use)
                    ekipmanlar_to_update_status[ekipman_id_to_use] = 'kirada'
                
                nakliye_ted_id = kalem_data['nakliye_tedarikci_id'] if kalem_data['dis_tedarik_nakliye'] else None
                
                # NAKLİYE CARİ YENİDEN
                if kalem_data['dis_tedarik_nakliye'] and nakliye_alis > 0 and nakliye_ted_id:
                    hizmet_nakliye = HizmetKaydi(
                        firma_id=nakliye_ted_id,
                        tarih=datetime.now().strftime('%Y-%m-%d'),
                        tutar=str(nakliye_alis),
                        yon='gelen',
                        aciklama=f"Dış Nakliye Gideri - Form: {kiralama.kiralama_form_no}",
                        fatura_no=kiralama.kiralama_form_no
                    )
                    db.session.add(hizmet_nakliye)

                if db_kalem and db_kalem.id in original_db_kalemler:
                    db_kalem.ekipman_id = ekipman_id_to_use
                    db_kalem.kiralama_baslangıcı = baslangic.strftime("%Y-%m-%d")
                    db_kalem.kiralama_bitis = bitis.strftime("%Y-%m-%d")
                    db_kalem.kiralama_brm_fiyat = str(satis_fiyati)
                    db_kalem.kiralama_alis_fiyat = str(alis_fiyati)
                    db_kalem.nakliye_satis_fiyat = str(nakliye_satis)
                    db_kalem.nakliye_alis_fiyat = str(nakliye_alis)
                    db_kalem.nakliye_tedarikci_id = nakliye_ted_id
                    form_kalemler_map[db_kalem.id] = ekipman_id_to_use
                else:
                    yeni_kalem = KiralamaKalemi(
                        kiralama=kiralama, 
                        ekipman_id=ekipman_id_to_use,
                        kiralama_baslangıcı=baslangic.strftime("%Y-%m-%d"),
                        kiralama_bitis=bitis.strftime("%Y-%m-%d"),
                        kiralama_brm_fiyat=str(satis_fiyati),
                        kiralama_alis_fiyat=str(alis_fiyati),
                        nakliye_satis_fiyat=str(nakliye_satis),
                        nakliye_alis_fiyat=str(nakliye_alis),
                        nakliye_tedarikci_id=nakliye_ted_id,
                        sonlandirildi=False
                    )
                    db.session.add(yeni_kalem)

            # MÜŞTERİ CARİ YENİDEN
            if toplam_gelir > 0:
                hizmet_gelir = HizmetKaydi(
                    firma_id=form.firma_musteri_id.data,
                    tarih=datetime.now().strftime('%Y-%m-%d'),
                    tutar=str(toplam_gelir),
                    yon='giden',
                    aciklama=f"Kiralama Hizmet Bedeli - Form: {kiralama.kiralama_form_no}",
                    fatura_no=kiralama.kiralama_form_no
                )
                db.session.add(hizmet_gelir)

            ids_to_make_bosta = original_pimaks_ekipman_ids - yeni_pimaks_ekipman_idler
            for ekip_id in ids_to_make_bosta: 
                ekipmanlar_to_update_status[ekip_id] = 'bosta'
            
            for ekip_id, new_status in ekipmanlar_to_update_status.items():
                ekip = Ekipman.query.get(ekip_id)
                if ekip: ekip.calisma_durumu = new_status

            form_ids_set = {int(k.get('id')) for k in form.kalemler.data if k.get('id') and str(k.get('id')).isdigit()}
            ids_to_delete = set(original_db_kalemler.keys()) - form_ids_set
            
            if ids_to_delete: 
                KiralamaKalemi.query.filter(KiralamaKalemi.id.in_(ids_to_delete)).delete(synchronize_session=False)

            db.session.commit()
            flash('Kiralama güncellendi.', 'success')
            return redirect(url_for('kiralama.index'))

        except Exception as e:
            db.session.rollback()
            flash(f"Hata: {str(e)}", "danger")
            traceback.print_exc()

    elif request.method == 'POST' and form.errors:
        flash("Form hatası.", "danger")
    
    return render_template('kiralama/duzelt.html', form=form, kiralama=kiralama, **get_context_data())

@kiralama_bp.route('/sil/<int:kiralama_id>', methods=['POST'])
def sil(kiralama_id):
    kiralama = Kiralama.query.get_or_404(kiralama_id)
    try:
        HizmetKaydi.query.filter_by(fatura_no=kiralama.kiralama_form_no).delete()
        for kalem in kiralama.kalemler:
            if kalem.ekipman and kalem.ekipman.firma_tedarikci_id is None and not kalem.sonlandirildi:
                kalem.ekipman.calisma_durumu = 'bosta'
        
        db.session.delete(kiralama)
        db.session.commit()
        flash('Kiralama ve ilgili tüm cari kayıtlar silindi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {e}', 'danger')
    return redirect(url_for('kiralama.index'))

@kiralama_bp.route('/kalem/sonlandir', methods=['POST'])
def sonlandir_kalem():
    try:
        kalem_id = request.form.get('kalem_id', type=int)
        bitis_tarihi = request.form.get('bitis_tarihi')
        
        kalem = KiralamaKalemi.query.get_or_404(kalem_id)
        if kalem.sonlandirildi: return redirect(url_for('kiralama.index'))

        kalem.kiralama_bitis = bitis_tarihi
        kalem.sonlandirildi = True
        
        if kalem.ekipman and kalem.ekipman.firma_tedarikci_id is None:
            kalem.ekipman.calisma_durumu = 'bosta'
        
        db.session.commit()
        guncelle_cari_toplam(kalem.kiralama_id)
        
        flash("Kalem sonlandırıldı ve cari güncellendi.", "success")
    except Exception as e:
        db.session.rollback(); flash(f"Hata: {e}", "danger")
        
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