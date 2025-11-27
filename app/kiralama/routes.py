# --- 1. GEREKLİ TÜM IMPORTLAR ---
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
# Geliştirme ortamında SSL uyarısını gizle
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app import db
from app.kiralama import kiralama_bp 
from app.models import Kiralama, Ekipman, Firma, KiralamaKalemi, HizmetKaydi
from app.forms import KiralamaForm, KiralamaKalemiForm 

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYON: Para Birimi Temizleme
# -------------------------------------------------------------------------
def clean_currency_input(value_str):
    if not value_str: return '0.0'
    val = str(value_str).strip()
    if ',' in val:
        val = val.replace('.', '') 
        val = val.replace(',', '.') 
    return val

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYON: CARİ HESABI GÜNCELLE
# -------------------------------------------------------------------------
def guncelle_cari_toplam(kiralama_id):
    try:
        kiralama = Kiralama.query.get(kiralama_id)
        if not kiralama: return

        toplam_tutar = Decimal(0.0)
        
        for kalem in kiralama.kalemler:
            baslangic = datetime.strptime(kalem.kiralama_baslangıcı, "%Y-%m-%d").date()
            bitis = datetime.strptime(kalem.kiralama_bitis, "%Y-%m-%d").date()
            gun_sayisi = (bitis - baslangic).days + 1
            if gun_sayisi < 1: gun_sayisi = 1
            
            brm_fiyat = Decimal(kalem.kiralama_brm_fiyat or 0)
            nakliye = Decimal(kalem.nakliye_satis_fiyat or 0)
            
            kalem_toplam = (brm_fiyat * gun_sayisi) + nakliye
            toplam_tutar += kalem_toplam
            
        cari_kayit = HizmetKaydi.query.filter_by(
            firma_id=kiralama.firma_musteri_id,
            fatura_no=kiralama.kiralama_form_no,
            yon='giden'
        ).first()
        
        if cari_kayit:
            cari_kayit.tutar = str(toplam_tutar)
            cari_kayit.aciklama = f"Kiralama Bedeli (Güncel): Form {kiralama.kiralama_form_no}"
            db.session.commit()
        
    except Exception as e:
        print(f"Cari güncelleme hatası: {e}")
        pass

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYON: TCMB Kur Çekme
# -------------------------------------------------------------------------
def get_tcmb_kurlari():
    rates = {'USD': 0.0, 'EUR': 0.0}
    try:
        url = "https://www.tcmb.gov.tr/kurlar/today.xml"
        response = requests.get(url, verify=False, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            usd_node = root.find("./Currency[@CurrencyCode='USD']/ForexSelling")
            if usd_node is not None and usd_node.text: rates['USD'] = float(usd_node.text)
            eur_node = root.find("./Currency[@CurrencyCode='EUR']/ForexSelling")
            if eur_node is not None and eur_node.text: rates['EUR'] = float(eur_node.text)
    except: pass
    return rates

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYONLAR (Form Doldurma)
# -------------------------------------------------------------------------
def get_pimaks_ekipman_choices(kiralama_objesi=None, include_ids=None):
    if include_ids is None: include_ids = []
    try:
        query = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.is_(None), 
            or_(Ekipman.calisma_durumu == 'bosta', Ekipman.id.in_(include_ids))
        )
        gecerli_ekipmanlar = query.order_by(Ekipman.kod).all()
        gecerli_ekipman_id_seti = {e.id for e in gecerli_ekipmanlar}
        choices = [(e.id, f"{e.kod} ({e.tipi} / {e.calisma_yuksekligi or 0}m)") for e in gecerli_ekipmanlar]
        
        if kiralama_objesi:
            for kalem in kiralama_objesi.kalemler:
                if (kalem.ekipman_id not in gecerli_ekipman_id_seti and 
                    kalem.ekipman and 
                    kalem.ekipman.firma_tedarikci_id is None):
                    e = kalem.ekipman
                    label = f"{e.kod} ({e.tipi} / {e.calisma_yuksekligi or 0}m) (ŞU AN KİRADA)"
                    choices.append((e.id, label))
                    gecerli_ekipman_id_seti.add(e.id)
        
        choices.insert(0, ('0', '--- Pimaks Filosu Seçiniz ---'))
        return choices
    except: return [('0', '--- Hata ---')]

def get_tedarikci_choices(include_pimaks=False):
    try:
        tedarikciler = Firma.query.filter_by(is_tedarikci=True).order_by(Firma.firma_adi).all()
        choices = [(f.id, f.firma_adi) for f in tedarikciler]
        if include_pimaks: choices.insert(0, ('0', '--- Pimaks (Maliyet Yok) ---'))
        else: choices.insert(0, ('0', '--- Tedarikçi Seçiniz ---'))
        return choices
    except: return [('0', '--- Hata ---')]

def populate_kiralama_form_choices(form, kiralama_objesi=None, include_ekipman_ids=None):
    try:
        musteri_choices = [(f.id, f.firma_adi) for f in Firma.query.filter_by(is_musteri=True).order_by(Firma.firma_adi).all()]
        musteri_choices.insert(0, ('0', '--- Müşteri Seçiniz ---'))
        form.firma_musteri_id.choices = musteri_choices
    except: form.firma_musteri_id.choices = [('0', 'Hata')]

    pimaks_ekipman_list = get_pimaks_ekipman_choices(kiralama_objesi, include_ids=include_ekipman_ids)
    ekipman_tedarikci_list = get_tedarikci_choices(include_pimaks=False)
    nakliye_tedarikci_list = get_tedarikci_choices(include_pimaks=True)
    
    for kalem_form_field in form.kalemler:
        kalem_form_field.form.ekipman_id.choices = pimaks_ekipman_list
        kalem_form_field.form.harici_ekipman_tedarikci_id.choices = ekipman_tedarikci_list
        kalem_form_field.form.nakliye_tedarikci_id.choices = nakliye_tedarikci_list

@kiralama_bp.app_template_filter('tarihtr')
def tarihtr(value):
    if not value: return ""
    if isinstance(value, (datetime, date)): return value.strftime("%d.%m.%Y")
    if isinstance(value, str):
        try: return datetime.strptime(value, '%Y-%m-%d').date().strftime("%d.%m.%Y")
        except ValueError: return value 
    return value

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
        
        base_query = Kiralama.query.options(
            joinedload(Kiralama.firma_musteri), 
            joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.ekipman).joinedload(Ekipman.firma_tedarikci),
            joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.nakliye_tedarikci)
        )

        if q:
            search_term = f'%{q}%'
            base_query = base_query.join(Firma, Kiralama.firma_musteri_id == Firma.id).filter(
                or_(
                    Kiralama.kiralama_form_no.ilike(search_term), 
                    Firma.firma_adi.ilike(search_term), 
                    Firma.yetkili_adi.ilike(search_term)
                )
            )

        pagination = base_query.order_by(Kiralama.id.desc()).paginate(page=page, per_page=25, error_out=False)
        kiralamalar = pagination.items
        
        today = date.today()
        for kiralama in kiralamalar:
            for kalem in kiralama.kalemler:
                # Varsayılan değerler
                kalem.sure_bilgisi = ""

                # 1. Durum Mesajı Hesaplama
                if kalem.sonlandirildi:
                    kalem.durum_mesaji = "Tamamlandı"
                    kalem.durum_sinifi = "secondary"
                elif not kalem.kiralama_bitis:
                    kalem.durum_mesaji = "Aktif (Bitiş Belirsiz)"
                    kalem.durum_sinifi = "primary"
                else:
                    try:
                        bitis_dt = datetime.strptime(kalem.kiralama_bitis, '%Y-%m-%d').date()
                        kalan_gun = (bitis_dt - today).days
                        
                        if kalan_gun < 0: 
                            kalem.durum_mesaji = f"Gecikti ({abs(kalan_gun)} gün)"
                            kalem.durum_sinifi = "danger"
                        elif kalan_gun == 0: 
                            kalem.durum_mesaji = "BUGÜN BİTİYOR"
                            kalem.durum_sinifi = "warning"
                        elif kalan_gun <= 7: 
                            kalem.durum_mesaji = f"{kalan_gun} gün kaldı"
                            kalem.durum_sinifi = "warning"
                        else: 
                            kalem.durum_mesaji = "Aktif"
                            kalem.durum_sinifi = "success"
                    except: 
                        kalem.durum_mesaji = "Hatalı Tarih"
                        kalem.durum_sinifi = "dark" 

                # 2. YENİ: Süre Bilgisi Hesaplama (Kaçıncı Gün / Toplam)
                try:
                    baslangic_dt = datetime.strptime(kalem.kiralama_baslangıcı, '%Y-%m-%d').date()
                    bitis_dt = datetime.strptime(kalem.kiralama_bitis, '%Y-%m-%d').date()
                    
                    # Toplam planlanan gün (Giriş günü dahil +1)
                    toplam_gun = (bitis_dt - baslangic_dt).days + 1
                    
                    if kalem.sonlandirildi:
                         # Bitti ise sadece toplam süreyi göster
                         kalem.sure_bilgisi = f"Toplam {toplam_gun} Gün Sürdü"
                    else:
                         # Devam ediyorsa kaçıncı günde olduğunu göster
                         gecen_gun = (today - baslangic_dt).days + 1
                         
                         if gecen_gun < 1:
                             kalem.sure_bilgisi = f"Henüz Başlamadı (Plan: {toplam_gun} Gün)"
                         elif gecen_gun > toplam_gun:
                             # Gecikmede ise
                             kalem.sure_bilgisi = f"{gecen_gun}. Gün (Plan: {toplam_gun} Gün)"
                         else:
                             # Normal süreçte ise
                             kalem.sure_bilgisi = f"{gecen_gun}. Gün / Toplam {toplam_gun} Gün"
                except Exception as e:
                    print(f"Süre hesaplama hatası: {e}")
                    kalem.sure_bilgisi = ""
        
        return render_template('kiralama/index.html', kiralamalar=kiralamalar, pagination=pagination, q=q, kurlar=kurlar)
    except Exception as e:
        flash(f"Hata: {str(e)}", "danger"); traceback.print_exc()
        return render_template('kiralama/index.html', kiralamalar=[], pagination=None, q=q, kurlar={'USD': 0.0, 'EUR': 0.0})

# -------------------------------------------------------------------------
# 4. YENİ KİRALAMA EKLEME
# -------------------------------------------------------------------------
@kiralama_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    ekipman_id_from_url = None
    kurlar = get_tcmb_kurlari()

    if request.method == 'GET':
        ekipman_id_from_url = request.args.get('ekipman_id', type=int)
        pre_data = {}
        if ekipman_id_from_url:
            pre_data['kalemler'] = [{'ekipman_id': ekipman_id_from_url}]
        
        form = KiralamaForm(data=pre_data) 
        form.doviz_kuru_usd.data = Decimal(kurlar['USD'])
        form.doviz_kuru_eur.data = Decimal(kurlar['EUR'])

        try:
            simdiki_yil = datetime.now(timezone.utc).year
            form_prefix = f'PF-{simdiki_yil}/'
            son_kiralama = Kiralama.query.filter(Kiralama.kiralama_form_no.like(f"{form_prefix}%")).order_by(Kiralama.id.desc()).first()
            yeni_numara = 1
            if son_kiralama and son_kiralama.kiralama_form_no:
                try: son_numara_str = son_kiralama.kiralama_form_no.split('/')[-1]; yeni_numara = int(son_numara_str) + 1 if son_numara_str.isdigit() else 1
                except: pass 
            form.kiralama_form_no.data = f'{form_prefix}{yeni_numara}'
        except: pass
    else:
        form = KiralamaForm() 

    include_ids = [ekipman_id_from_url] if ekipman_id_from_url else []
    populate_kiralama_form_choices(form, include_ekipman_ids=include_ids)
    
    if form.validate_on_submit():
        yeni_kiralama = Kiralama(
            kiralama_form_no=form.kiralama_form_no.data,
            firma_musteri_id=form.firma_musteri_id.data,
            kdv_orani=form.kdv_orani.data,
            doviz_kuru_usd=float(form.doviz_kuru_usd.data or kurlar['USD']),
            doviz_kuru_eur=float(form.doviz_kuru_eur.data or kurlar['EUR'])
        )
        db.session.add(yeni_kiralama) 
        
        try:
            secilen_pimaks_ekipman_idler = set()
            kalemler_to_add = [] 
            toplam_musteri_alacagi = Decimal(0.0)
            
            for kalem_data in form.kalemler.data:
                ekipman_id_to_use = None
                ekipman_to_update_status = None 
                
                kiralama_brm_fiyat = Decimal(clean_currency_input(str(kalem_data['kiralama_brm_fiyat'])))
                nakliye_satis_fiyat = Decimal(clean_currency_input(str(kalem_data['nakliye_satis_fiyat'])))
                
                baslangic = kalem_data['kiralama_baslangıcı']
                bitis = kalem_data['kiralama_bitis']
                gun_sayisi = (bitis - baslangic).days + 1
                if gun_sayisi < 1: gun_sayisi = 1
                
                kalem_toplam_tutar = (kiralama_brm_fiyat * gun_sayisi) + nakliye_satis_fiyat
                toplam_musteri_alacagi += kalem_toplam_tutar

                if kalem_data['dis_tedarik_ekipman']:
                    tedarikci_id = kalem_data['harici_ekipman_tedarikci_id']
                    seri_no = (kalem_data['harici_ekipman_seri_no'] or '').strip()
                    tipi = (kalem_data['harici_ekipman_tipi'] or 'Bilinmiyor').strip()
                    marka = (kalem_data['harici_ekipman_marka'] or 'Bilinmiyor').strip()
                    model = (kalem_data['harici_ekipman_model'] or '').strip()
                    yukseklik = int(kalem_data.get('harici_ekipman_calisma_yuksekligi') or 0)
                    kapasite = int(kalem_data.get('harici_ekipman_kaldirma_kapasitesi') or 0)
                    
                    kiralama_alis_fiyat = Decimal(clean_currency_input(str(kalem_data['kiralama_alis_fiyat'])))
                    if kiralama_alis_fiyat > 0:
                         gider_tutar = kiralama_alis_fiyat * gun_sayisi
                         hizmet_gider = HizmetKaydi(
                             firma_id=tedarikci_id,
                             tarih=datetime.now().strftime('%Y-%m-%d'),
                             tutar=str(gider_tutar),
                             yon='gelen', 
                             aciklama=f"Dış Kiralama Gideri: {marka} {model} ({seri_no})",
                             fatura_no=yeni_kiralama.kiralama_form_no 
                         )
                         db.session.add(hizmet_gider)
                    
                    if not (tedarikci_id and tedarikci_id > 0 and seri_no):
                        raise ValueError(f"Dış Tedarik seçildi ancak Tedarikçi veya Seri No bilgisi eksik.")
                    
                    harici_ekipman = Ekipman.query.filter_by(firma_tedarikci_id=tedarikci_id, seri_no=seri_no).first()
                    if not harici_ekipman:
                        harici_ekipman = Ekipman(
                            kod=f"HARICI-{seri_no}", seri_no=seri_no, tipi=tipi, marka=marka, model=model,
                            yakit="Bilinmiyor", calisma_yuksekligi=yukseklik, kaldirma_kapasitesi=kapasite,
                            uretim_tarihi="Bilinmiyor", giris_maliyeti='0', 
                            firma_tedarikci_id=tedarikci_id, calisma_durumu='harici', is_active=True
                        )
                        db.session.add(harici_ekipman)
                        db.session.flush()
                    else:
                        if not harici_ekipman.is_active: harici_ekipman.is_active = True
                        harici_ekipman.marka = marka; harici_ekipman.model = model; harici_ekipman.tipi = tipi
                        harici_ekipman.calisma_yuksekligi = yukseklik; harici_ekipman.kaldirma_kapasitesi = kapasite
                    ekipman_id_to_use = harici_ekipman.id
                else:
                    ekipman_id_to_use = kalem_data['ekipman_id']
                    if not (ekipman_id_to_use and ekipman_id_to_use > 0): continue
                    if ekipman_id_to_use in secilen_pimaks_ekipman_idler: raise ValueError(f"Ekipman çakışması.")
                    ekipman_to_update_status = Ekipman.query.get(ekipman_id_to_use)
                    if not ekipman_to_update_status or ekipman_to_update_status.firma_tedarikci_id is not None: raise ValueError("Pimaks ekipmanı bulunamadı.")
                    if ekipman_to_update_status.calisma_durumu != 'bosta' and ekipman_id_to_use != request.args.get('ekipman_id', type=int): raise ValueError("Ekipman boşta değil.")
                
                if bitis < baslangic: raise ValueError("Tarih hatası.")
                
                nakliye_ted_id = kalem_data['nakliye_tedarikci_id'] if kalem_data['dis_tedarik_nakliye'] else None
                if nakliye_ted_id and kalem_data['dis_tedarik_nakliye']:
                    nakliye_alis_fiyat = Decimal(clean_currency_input(str(kalem_data['nakliye_alis_fiyat'])))
                    if nakliye_alis_fiyat > 0:
                         hizmet_nakliye = HizmetKaydi(
                             firma_id=nakliye_ted_id,
                             tarih=datetime.now().strftime('%Y-%m-%d'),
                             tutar=str(nakliye_alis_fiyat),
                             yon='gelen', 
                             aciklama=f"Dış Nakliye Gideri",
                             fatura_no=yeni_kiralama.kiralama_form_no 
                         )
                         db.session.add(hizmet_nakliye)

                yeni_kalem = KiralamaKalemi(
                    ekipman_id=ekipman_id_to_use,
                    kiralama_baslangıcı=baslangic.strftime("%Y-%m-%d"),
                    kiralama_bitis=bitis.strftime("%Y-%m-%d"),
                    kiralama_brm_fiyat=str(clean_currency_input(str(kalem_data['kiralama_brm_fiyat']))),
                    kiralama_alis_fiyat=str(clean_currency_input(str(kalem_data['kiralama_alis_fiyat']))),
                    nakliye_satis_fiyat=str(clean_currency_input(str(kalem_data['nakliye_satis_fiyat']))),
                    nakliye_alis_fiyat=str(clean_currency_input(str(kalem_data['nakliye_alis_fiyat']))),
                    nakliye_tedarikci_id=nakliye_ted_id,
                    sonlandirildi=False 
                )
                kalemler_to_add.append((ekipman_to_update_status, yeni_kalem)) 
                if ekipman_to_update_status: secilen_pimaks_ekipman_idler.add(ekipman_id_to_use)

            if not kalemler_to_add:
                flash("Geçerli kalem yok.", "danger"); db.session.rollback()
            else:
                for ekipman, kalem in kalemler_to_add:
                    kalem.kiralama = yeni_kiralama 
                    if ekipman: ekipman.calisma_durumu = "kirada"
                    db.session.add(kalem)
                
                if toplam_musteri_alacagi > 0:
                    hizmet_musteri = HizmetKaydi(
                        firma_id=form.firma_musteri_id.data,
                        tarih=datetime.now().strftime('%Y-%m-%d'),
                        tutar=str(toplam_musteri_alacagi),
                        yon='giden', 
                        aciklama=f"Kiralama Bedeli (Toplam)",
                        fatura_no=yeni_kiralama.kiralama_form_no
                    )
                    db.session.add(hizmet_musteri)

                db.session.commit()
                flash(f"{len(kalemler_to_add)} kalem kiralandı!", "success")
                return redirect(url_for('kiralama.index')) 

        except Exception as e:
            db.session.rollback()
            flash(f"Hata: {str(e)}", "danger")
            traceback.print_exc()
    else:
        if request.method == 'POST' and form.errors: flash("Form hatası.", "warning")

    ekipman_choices_json = json.dumps(get_pimaks_ekipman_choices(include_ids=([ekipman_id_from_url] if ekipman_id_from_url else [])))
    tedarikci_choices_json = json.dumps(get_tedarikci_choices(include_pimaks=False))
    nakliye_tedarikci_choices_json = json.dumps(get_tedarikci_choices(include_pimaks=True))

    next_url = request.args.get('next', 'kiralama.index')
    page = request.args.get('page')
    q = request.args.get('q')

    return render_template(
        'kiralama/ekle.html', 
        form=form, 
        ekipman_choices_json=ekipman_choices_json,
        tedarikci_choices_json=tedarikci_choices_json, 
        nakliye_tedarikci_choices_json=nakliye_tedarikci_choices_json,
        next_url=next_url, page=page, q=q
    )

# -------------------------------------------------------------------------
# 5. KİRALAMA KAYDI DÜZENLEME
# -------------------------------------------------------------------------
@kiralama_bp.route('/duzenle/<int:kiralama_id>', methods=['GET', 'POST'])
def duzenle(kiralama_id):
    kiralama = Kiralama.query.options(joinedload(Kiralama.firma_musteri), joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.ekipman), joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.nakliye_tedarikci)).get_or_404(kiralama_id)

    if request.method == 'POST': form = KiralamaForm()
    else: form = KiralamaForm(obj=kiralama)
    populate_kiralama_form_choices(form, kiralama_objesi=kiralama)
    
    if request.method == 'GET':
        try:
            form.firma_musteri_id.data = kiralama.firma_musteri_id
            form.kdv_orani.data = kiralama.kdv_orani
            form.doviz_kuru_usd.data = Decimal(kiralama.doviz_kuru_usd or 0.0)
            form.doviz_kuru_eur.data = Decimal(kiralama.doviz_kuru_eur or 0.0)
            
            for i, kalem in enumerate(kiralama.kalemler):
                if i < len(form.kalemler):
                    kalem_form = form.kalemler[i]
                    ekipman_obj = kalem.ekipman
                    if ekipman_obj and ekipman_obj.firma_tedarikci_id is not None:
                        kalem_form.dis_tedarik_ekipman.data = True
                        kalem_form.harici_ekipman_tedarikci_id.data = ekipman_obj.firma_tedarikci_id
                        kalem_form.harici_ekipman_tipi.data = ekipman_obj.tipi
                        kalem_form.harici_ekipman_marka.data = ekipman_obj.marka
                        kalem_form.harici_ekipman_model.data = ekipman_obj.model
                        kalem_form.harici_ekipman_seri_no.data = ekipman_obj.seri_no
                        kalem_form.harici_ekipman_calisma_yuksekligi.data = ekipman_obj.calisma_yuksekligi
                        kalem_form.harici_ekipman_kaldirma_kapasitesi.data = ekipman_obj.kaldirma_kapasitesi
                    else:
                        kalem_form.dis_tedarik_ekipman.data = False
                        kalem_form.ekipman_id.data = kalem.ekipman_id
                    
                    if kalem.nakliye_tedarikci_id is not None:
                        kalem_form.dis_tedarik_nakliye.data = True
                        kalem_form.nakliye_tedarikci_id.data = kalem.nakliye_tedarikci_id
                    else:
                        kalem_form.dis_tedarik_nakliye.data = False
                        kalem_form.nakliye_tedarikci_id.data = 0 
                    
                    if isinstance(kalem.kiralama_baslangıcı, str): kalem_form.kiralama_baslangıcı.data = datetime.strptime(kalem.kiralama_baslangıcı, '%Y-%m-%d').date()
                    if isinstance(kalem.kiralama_bitis, str): kalem_form.kiralama_bitis.data = datetime.strptime(kalem.kiralama_bitis, '%Y-%m-%d').date()
                    kalem_form.kiralama_brm_fiyat.data = Decimal(kalem.kiralama_brm_fiyat or 0)
                    kalem_form.kiralama_alis_fiyat.data = Decimal(kalem.kiralama_alis_fiyat or 0)
                    kalem_form.nakliye_satis_fiyat.data = Decimal(kalem.nakliye_satis_fiyat or 0)
                    kalem_form.nakliye_alis_fiyat.data = Decimal(kalem.nakliye_alis_fiyat or 0)
        except Exception as e:
            flash(f"Form hatası: {e}", "danger"); traceback.print_exc()

    if form.validate_on_submit():
        original_db_kalemler = {k.id: k for k in kiralama.kalemler if not k.sonlandirildi}
        original_pimaks_ekipman_ids = {k.ekipman_id for k in original_db_kalemler.values() if k.ekipman_id and k.ekipman and k.ekipman.firma_tedarikci_id is None}
        try:
            kiralama.kiralama_form_no = form.kiralama_form_no.data
            kiralama.firma_musteri_id = form.firma_musteri_id.data
            kiralama.kdv_orani = form.kdv_orani.data
            
            form_kalemler_map = {} 
            yeni_pimaks_ekipman_idler = set()
            ekipmanlar_to_update_status = {} 
            
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
                if kalem_data['dis_tedarik_ekipman']:
                    tedarikci_id = kalem_data['harici_ekipman_tedarikci_id']; seri_no = (kalem_data['harici_ekipman_seri_no'] or '').strip()
                    tipi = (kalem_data['harici_ekipman_tipi'] or 'Bilinmiyor').strip(); marka = (kalem_data['harici_ekipman_marka'] or 'Bilinmiyor').strip(); model = (kalem_data['harici_ekipman_model'] or '').strip()
                    yukseklik = int(kalem_data.get('harici_ekipman_calisma_yuksekligi') or 0); kapasite = int(kalem_data.get('harici_ekipman_kaldirma_kapasitesi') or 0)
                    if not (tedarikci_id and tedarikci_id > 0 and seri_no): raise ValueError(f"Dış Tedarik eksik.")
                    harici_ekipman = Ekipman.query.filter_by(firma_tedarikci_id=tedarikci_id, seri_no=seri_no).first()
                    if not harici_ekipman:
                        harici_ekipman = Ekipman(kod=f"HARICI-{seri_no}", seri_no=seri_no, tipi=tipi, marka=marka, model=model, yakit="Bilinmiyor", calisma_yuksekligi=yukseklik, kaldirma_kapasitesi=kapasite, uretim_tarihi="Bilinmiyor", giris_maliyeti='0', firma_tedarikci_id=tedarikci_id, calisma_durumu='harici', is_active=True)
                        db.session.add(harici_ekipman); db.session.flush()
                    else:
                        if not harici_ekipman.is_active: harici_ekipman.is_active = True
                        harici_ekipman.marka = marka; harici_ekipman.model = model; harici_ekipman.tipi = tipi; harici_ekipman.calisma_yuksekligi = yukseklik; harici_ekipman.kaldirma_kapasitesi = kapasite
                    ekipman_id_to_use = harici_ekipman.id
                else:
                    ekipman_id_to_use = kalem_data['ekipman_id']
                    if not (ekipman_id_to_use and ekipman_id_to_use > 0): continue 
                    if ekipman_id_to_use in yeni_pimaks_ekipman_idler: raise ValueError(f"Ekipman çakışması.")
                    ekipman_to_update = Ekipman.query.get(ekipman_id_to_use)
                    if not ekipman_to_update or ekipman_to_update.firma_tedarikci_id is not None: raise ValueError("Hata")
                    if (ekipman_to_update.calisma_durumu != 'bosta' and ekipman_id_to_use not in original_pimaks_ekipman_ids): raise ValueError("Hata")
                    yeni_pimaks_ekipman_idler.add(ekipman_id_to_use)
                    ekipmanlar_to_update_status[ekipman_id_to_use] = 'kirada'
                
                baslangic = kalem_data['kiralama_baslangıcı']; bitis = kalem_data['kiralama_bitis']
                baslangic_str = baslangic.strftime("%Y-%m-%d"); bitis_str = bitis.strftime("%Y-%m-%d")
                nakliye_ted_id = kalem_data['nakliye_tedarikci_id'] if kalem_data['dis_tedarik_nakliye'] else None
                
                if db_kalem and db_kalem.id in original_db_kalemler:
                    db_kalem.ekipman_id = ekipman_id_to_use
                    db_kalem.kiralama_baslangıcı = baslangic_str
                    db_kalem.kiralama_bitis = bitis_str
                    db_kalem.kiralama_brm_fiyat = str(clean_currency_input(str(kalem_data['kiralama_brm_fiyat'])))
                    db_kalem.kiralama_alis_fiyat = str(clean_currency_input(str(kalem_data['kiralama_alis_fiyat'])))
                    db_kalem.nakliye_satis_fiyat = str(clean_currency_input(str(kalem_data['nakliye_satis_fiyat'])))
                    db_kalem.nakliye_alis_fiyat = str(clean_currency_input(str(kalem_data['nakliye_alis_fiyat'])))
                    db_kalem.nakliye_tedarikci_id = nakliye_ted_id
                    form_kalemler_map[db_kalem.id] = ekipman_id_to_use
                else:
                    yeni_kalem = KiralamaKalemi(
                        kiralama=kiralama, 
                        ekipman_id=ekipman_id_to_use,
                        kiralama_baslangıcı=baslangic_str,
                        kiralama_bitis=bitis_str,
                        kiralama_brm_fiyat=str(clean_currency_input(str(kalem_data['kiralama_brm_fiyat']))),
                        kiralama_alis_fiyat=str(clean_currency_input(str(kalem_data['kiralama_alis_fiyat']))),
                        nakliye_satis_fiyat=str(clean_currency_input(str(kalem_data['nakliye_satis_fiyat']))),
                        nakliye_alis_fiyat=str(clean_currency_input(str(kalem_data['nakliye_alis_fiyat']))),
                        nakliye_tedarikci_id=nakliye_ted_id,
                        sonlandirildi=False
                    )
                    db.session.add(yeni_kalem)

            ids_to_make_bosta = original_pimaks_ekipman_ids - yeni_pimaks_ekipman_idler
            for ekip_id in ids_to_make_bosta: ekipmanlar_to_update_status[ekip_id] = 'bosta'
            for ekip_id, new_status in ekipmanlar_to_update_status.items():
                ekip = Ekipman.query.get(ekip_id)
                if ekip: ekip.calisma_durumu = new_status

            form_ids_set = {int(kalem_data.get('id')) for kalem_data in form.kalemler.data if kalem_data.get('id') and str(kalem_data.get('id')).isdigit()}
            ids_to_delete = set(original_db_kalemler.keys()) - form_ids_set
            if ids_to_delete: KiralamaKalemi.query.filter(KiralamaKalemi.id.in_(ids_to_delete)).delete(synchronize_session=False)

            db.session.commit()
            
            # Cari Hesabı Otomatik Güncelle
            guncelle_cari_toplam(kiralama.id)
            
            flash('Güncellendi.', 'success')
            return redirect(url_for('kiralama.index'))

        except Exception as e:
            db.session.rollback()
            flash(f"Hata: {str(e)}", "danger")
            traceback.print_exc()

    elif request.method == 'POST' and form.errors:
        flash("Form hatası.", "danger")
        
    ekipman_choices_json = json.dumps(get_pimaks_ekipman_choices(kiralama, include_ids=[k.ekipman_id for k in kiralama.kalemler]))
    tedarikci_choices_json = json.dumps(get_tedarikci_choices(include_pimaks=False))
    nakliye_tedarikci_choices_json = json.dumps(get_tedarikci_choices(include_pimaks=True))
    
    return render_template(
        'kiralama/duzelt.html', 
        form=form, 
        kiralama=kiralama,
        ekipman_choices_json=ekipman_choices_json,
        tedarikci_choices_json=tedarikci_choices_json,
        nakliye_tedarikci_choices_json=nakliye_tedarikci_choices_json
    )

@kiralama_bp.route('/sil/<int:kiralama_id>', methods=['POST'])
def sil(kiralama_id):
    kiralama = Kiralama.query.get_or_404(kiralama_id)
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '')
    try:
        for kalem in kiralama.kalemler:
            if kalem.ekipman and kalem.ekipman.firma_tedarikci_id is None and not kalem.sonlandirildi:
                kalem.ekipman.calisma_durumu = 'bosta'
        db.session.delete(kiralama)
        db.session.commit()
        flash('Kiralama silindi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {str(e)}', 'danger')
    return redirect(url_for('kiralama.index', page=page, q=q))

@kiralama_bp.route('/api/get-ekipman')
def get_ekipman():
    return jsonify([])

@kiralama_bp.route('/kalem/sonlandir', methods=['POST'])
def sonlandir_kalem():
    try:
        kalem_id = request.form.get('kalem_id', type=int)
        bitis_tarihi_str = request.form.get('bitis_tarihi')
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '')

        if not (kalem_id and bitis_tarihi_str): return redirect(url_for('kiralama.index'))
        kalem = KiralamaKalemi.query.get_or_404(kalem_id)
        if kalem.sonlandirildi: return redirect(url_for('kiralama.index'))

        ekipman = kalem.ekipman
        kalem.kiralama_bitis = bitis_tarihi_str
        kalem.sonlandirildi = True
        if ekipman and ekipman.firma_tedarikci_id is None:
            ekipman.calisma_durumu = 'bosta'
        
        db.session.commit()
        
        # Sonlandırmada da Cariyi Güncelle
        guncelle_cari_toplam(kalem.kiralama_id)
        
        flash(f"Sonlandırıldı.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Hata: {str(e)}", 'danger')

    return redirect(url_for('kiralama.index', page=page, q=q))

@kiralama_bp.route('/kalem/iptal_et', methods=['POST'])
def iptal_et_kalem():
    """
    Yanlışlıkla sonlandırılan bir kiralama kalemini tekrar 'Aktif' hale getirir.
    """
    try:
        kalem_id = request.form.get('kalem_id', type=int)
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '')

        if not kalem_id: return redirect(url_for('kiralama.index'))
        
        kalem = KiralamaKalemi.query.get_or_404(kalem_id)
        if not kalem.sonlandirildi:
            flash("Bu kalem zaten aktif durumda.", "warning")
            return redirect(url_for('kiralama.index', page=page, q=q))

        ekipman = kalem.ekipman
        kalem.sonlandirildi = False
        
        if ekipman and ekipman.firma_tedarikci_id is None:
            ekipman.calisma_durumu = 'kirada'
        
        db.session.commit()
        
        guncelle_cari_toplam(kalem.kiralama_id)
        
        flash(f"Sonlandırma işlemi geri alındı. Makine tekrar kirada.", 'success')

    except Exception as e:
        db.session.rollback()
        flash(f"Hata oluştu: {str(e)}", 'danger')

    return redirect(url_for('kiralama.index', page=page, q=q))