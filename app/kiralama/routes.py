import json
import traceback
import requests 
import xml.etree.ElementTree as ET 
from datetime import datetime, date
from decimal import Decimal
from flask import render_template, redirect, url_for, flash, request
from sqlalchemy import or_, and_
from sqlalchemy.orm import joinedload

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app import db
from app.kiralama import kiralama_bp

# Modeller
from app.firmalar.models import Firma
from app.kiralama.models import Kiralama, KiralamaKalemi
from app.filo.models import Ekipman
from app.cari.models import HizmetKaydi 

from app.kiralama.forms import KiralamaForm

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYONLAR
# -------------------------------------------------------------------------

def get_tcmb_kurlari():
    """TCMB'den günlük USD ve EUR kurlarını çeker."""
    rates = {'USD': Decimal('0.00'), 'EUR': Decimal('0.00')}
    try:
        url = "https://www.tcmb.gov.tr/kurlar/today.xml"
        response = requests.get(url, verify=False, timeout=2)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            usd = root.find("./Currency[@CurrencyCode='USD']/ForexSelling")
            eur = root.find("./Currency[@CurrencyCode='EUR']/ForexSelling")
            if usd is not None: rates['USD'] = Decimal(usd.text)
            if eur is not None: rates['EUR'] = Decimal(eur.text)
    except: pass
    return rates

def guncelle_cari_toplam(kiralama_id):
    """Kiralama güncellendiğinde veya sonlandırıldığında cariyi senkronize eder."""
    try:
        kiralama = Kiralama.query.get(kiralama_id)
        if not kiralama: return
        
        cari_kayit = HizmetKaydi.query.filter_by(fatura_no=kiralama.kiralama_form_no, yon='giden').first()
        
        toplam_gelir = Decimal('0.00')
        for kalem in kiralama.kalemler:
            if not (kalem.kiralama_baslangici and kalem.kiralama_bitis): continue
            gun = max((kalem.kiralama_bitis - kalem.kiralama_baslangici).days + 1, 1)
            toplam_gelir += (kalem.kiralama_brm_fiyat * gun) + (kalem.nakliye_satis_fiyat or 0)

        if cari_kayit:
            cari_kayit.tutar = toplam_gelir
            db.session.commit()
    except Exception as e:
        print(f"Cari hatası: {e}")

def populate_kiralama_form_choices(form, kiralama_objesi=None, include_ids=None):
    """Tüm SelectField seçeneklerini form nesnesine enjekte eder."""
    if include_ids is None: include_ids = []
    
    musteriler = Firma.query.filter_by(is_musteri=True, is_active=True).order_by(Firma.firma_adi).all()
    form.firma_musteri_id.choices = [(0, '--- Müşteri Seçiniz ---')] + [(f.id, f.firma_adi) for f in musteriler]
    
    tedarikciler = Firma.query.filter_by(is_tedarikci=True, is_active=True).order_by(Firma.firma_adi).all()
    ted_choices = [(0, '--- Tedarikçi Seçiniz ---')] + [(f.id, f.firma_adi) for f in tedarikciler]
    
    filo_query = Ekipman.query.filter(
        Ekipman.firma_tedarikci_id.is_(None),
        or_(Ekipman.calisma_durumu == 'bosta', Ekipman.id.in_(include_ids))
    ).order_by(Ekipman.kod).all()
    
    pimaks_choices = [(0, '--- Seçiniz ---')] + [(e.id, f"{e.kod} ({e.tipi})") for e in filo_query]

    for subform in form.kalemler:
        f = subform.form
        f.ekipman_id.choices = pimaks_choices
        f.harici_ekipman_tedarikci_id.choices = ted_choices
        f.nakliye_tedarikci_id.choices = ted_choices
        f.nakliye_araci_id.choices = pimaks_choices

# -------------------------------------------------------------------------
# ROUTES
# -------------------------------------------------------------------------

@kiralama_bp.route('/')
@kiralama_bp.route('/index')
def index():
    try:
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '', type=str)
        today = date.today() 
        
        query = Kiralama.query.options(
            joinedload(Kiralama.firma_musteri), 
            joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.ekipman),
            joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.harici_tedarikci)
        )
        
        if q:
            search = f"%{q}%"
            query = query.join(Firma, Kiralama.firma_musteri_id == Firma.id)\
                         .outerjoin(KiralamaKalemi, Kiralama.id == KiralamaKalemi.kiralama_id)\
                         .outerjoin(Ekipman, KiralamaKalemi.ekipman_id == Ekipman.id)\
                         .filter(
                or_(
                    Kiralama.kiralama_form_no.ilike(search),
                    Firma.firma_adi.ilike(search),
                    Ekipman.kod.ilike(search),
                    Ekipman.seri_no.ilike(search),
                    KiralamaKalemi.harici_ekipman_marka.ilike(search),
                    KiralamaKalemi.harici_ekipman_model.ilike(search),
                    KiralamaKalemi.harici_ekipman_seri_no.ilike(search)
                )
            ).distinct()
            
        pagination = query.order_by(Kiralama.id.desc()).paginate(page=page, per_page=20)
        
        return render_template(
            'kiralama/index.html', 
            kiralamalar=pagination.items, 
            pagination=pagination, 
            q=q, 
            kurlar=get_tcmb_kurlari(),
            today=today
        )
    except Exception as e:
        flash(f"Liste Hatası: {e}", "danger")
        traceback.print_exc()
        return render_template('kiralama/index.html', kiralamalar=[], kurlar={}, today=date.today())

@kiralama_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    ekipman_id = request.args.get('ekipman_id', type=int)
    form = KiralamaForm()
    
    ids_in_form = [int(k.ekipman_id.data) for k in form.kalemler if k.ekipman_id.data and int(k.ekipman_id.data) > 0]
    if ekipman_id: ids_in_form.append(ekipman_id)
    populate_kiralama_form_choices(form, include_ids=ids_in_form)

    if request.method == 'GET':
        kurlar = get_tcmb_kurlari()
        form.doviz_kuru_usd.data, form.doviz_kuru_eur.data = kurlar['USD'], kurlar['EUR']
        last = Kiralama.query.order_by(Kiralama.id.desc()).first()
        form.kiralama_form_no.data = f"PF-{datetime.now().year}/{(last.id + 1 if last else 1):04d}"
        if ekipman_id: form.kalemler.append_entry({'ekipman_id': ekipman_id})

    if form.validate_on_submit():
        try:
            yeni_kiralama = Kiralama(
                kiralama_form_no=form.kiralama_form_no.data,
                firma_musteri_id=form.firma_musteri_id.data,
                kdv_orani=form.kdv_orani.data,
                doviz_kuru_usd=form.doviz_kuru_usd.data,
                doviz_kuru_eur=form.doviz_kuru_eur.data
            )
            db.session.add(yeni_kiralama); db.session.flush()

            toplam_gelir = Decimal('0.00')

            for k_form in form.kalemler:
                bas, bit = k_form.kiralama_baslangici.data, k_form.kiralama_bitis.data
                if not (bas and bit): continue

                kalem = KiralamaKalemi(
                    kiralama_id=yeni_kiralama.id,
                    kiralama_baslangici=bas,
                    kiralama_bitis=bit,
                    kiralama_brm_fiyat=k_form.kiralama_brm_fiyat.data or 0,
                    kiralama_alis_fiyat=k_form.kiralama_alis_fiyat.data or 0,
                    nakliye_satis_fiyat=k_form.nakliye_satis_fiyat.data or 0,
                    nakliye_alis_fiyat=k_form.nakliye_alis_fiyat.data or 0,
                    sonlandirildi=0
                )

                if int(k_form.dis_tedarik_ekipman.data or 0) == 1:
                    kalem.is_dis_tedarik_ekipman = True
                    kalem.harici_ekipman_marka = k_form.harici_ekipman_marka.data
                    kalem.harici_ekipman_model = k_form.harici_ekipman_model.data
                    kalem.harici_ekipman_seri_no = k_form.harici_ekipman_seri_no.data
                    kalem.harici_ekipman_tedarikci_id = k_form.harici_ekipman_tedarikci_id.data
                    if kalem.kiralama_alis_fiyat > 0:
                        gun = max((bit - bas).days + 1, 1)
                        db.session.add(HizmetKaydi(
                            firma_id=kalem.harici_ekipman_tedarikci_id, tarih=date.today(),
                            tutar=(kalem.kiralama_alis_fiyat * gun), yon='gelen',
                            fatura_no=yeni_kiralama.kiralama_form_no, aciklama=f"Dış Kiralama: {kalem.harici_ekipman_marka}"
                        ))
                else:
                    eid = int(k_form.ekipman_id.data or 0)
                    if eid > 0:
                        kalem.ekipman_id = eid
                        ekip = Ekipman.query.get(eid)
                        if ekip: ekip.calisma_durumu = 'kirada'

                if int(k_form.dis_tedarik_nakliye.data or 0) == 1:
                    kalem.is_harici_nakliye, kalem.is_oz_mal_nakliye = True, False
                    kalem.nakliye_tedarikci_id = k_form.nakliye_tedarikci_id.data
                else:
                    kalem.is_oz_mal_nakliye = True
                    arac_id = int(k_form.nakliye_araci_id.data or 0)
                    kalem.nakliye_araci_id = arac_id if arac_id > 0 else None

                db.session.add(kalem)
                toplam_gelir += (kalem.kiralama_brm_fiyat * max((bit - bas).days + 1, 1)) + (kalem.nakliye_satis_fiyat or 0)

            if toplam_gelir > 0:
                db.session.add(HizmetKaydi(
                    firma_id=yeni_kiralama.firma_musteri_id, tarih=date.today(), tutar=toplam_gelir,
                    yon='giden', fatura_no=yeni_kiralama.kiralama_form_no, ozel_id=yeni_kiralama.id,
                    aciklama=f"Kiralama Bedeli - {yeni_kiralama.kiralama_form_no}"
                ))

            db.session.commit(); flash('Kiralama başarıyla kaydedildi.', 'success'); return redirect(url_for('kiralama.index'))
        except Exception as e:
            db.session.rollback(); traceback.print_exc(); flash(f"Kayıt Hatası: {e}", "danger")

    return render_template('kiralama/ekle.html', form=form)

@kiralama_bp.route('/duzenle/<int:kiralama_id>', methods=['GET', 'POST'])
def duzenle(kiralama_id):
    kiralama = Kiralama.query.get_or_404(kiralama_id)
    form = KiralamaForm()

    if request.method == 'GET':
        form.firma_musteri_id.data = kiralama.firma_musteri_id
        form.kdv_orani.data = kiralama.kdv_orani
        form.doviz_kuru_usd.data = kiralama.doviz_kuru_usd
        form.doviz_kuru_eur.data = kiralama.doviz_kuru_eur
        form.kiralama_form_no.data = kiralama.kiralama_form_no
        
        while len(form.kalemler) > 0: 
            form.kalemler.pop_entry()
            
        for k in kiralama.kalemler:
            entry = form.kalemler.append_entry({
                'ekipman_id': k.ekipman_id,
                'kiralama_baslangici': k.kiralama_baslangici,
                'kiralama_bitis': k.kiralama_bitis,
                'kiralama_brm_fiyat': k.kiralama_brm_fiyat,
                'kiralama_alis_fiyat': k.kiralama_alis_fiyat,
                'nakliye_satis_fiyat': k.nakliye_satis_fiyat,
                'nakliye_alis_fiyat': k.nakliye_alis_fiyat,
                'dis_tedarik_ekipman': 1 if k.is_dis_tedarik_ekipman else 0,
                'harici_ekipman_marka': k.harici_ekipman_marka,
                'harici_ekipman_model': k.harici_ekipman_model,
                'harici_ekipman_seri_no': k.harici_ekipman_seri_no,
                'harici_ekipman_tipi': k.harici_ekipman_tipi,
                'harici_ekipman_kaldirma_kapasitesi': k.harici_ekipman_kapasite,
                'harici_ekipman_calisma_yuksekligi': k.harici_ekipman_yukseklik,
                'harici_ekipman_uretim_tarihi': k.harici_ekipman_uretim_yili,
                'harici_ekipman_tedarikci_id': k.harici_ekipman_tedarikci_id,
                'dis_tedarik_nakliye': 1 if k.is_harici_nakliye else 0, 
                'nakliye_tedarikci_id': k.nakliye_tedarikci_id,
                'nakliye_araci_id': k.nakliye_araci_id or 0
            })
            entry.form.id.data = k.id
            
        if len(form.kalemler) == 0:
            form.kalemler.append_entry()

    populate_kiralama_form_choices(form, kiralama_objesi=kiralama, include_ids=[k.ekipman_id for k in kiralama.kalemler if k.ekipman_id])

    if form.validate_on_submit():
        try:
            HizmetKaydi.query.filter_by(fatura_no=kiralama.kiralama_form_no).delete(synchronize_session=False)
            
            kiralama.firma_musteri_id = form.firma_musteri_id.data
            kiralama.kdv_orani = form.kdv_orani.data
            kiralama.doviz_kuru_usd = form.doviz_kuru_usd.data
            kiralama.doviz_kuru_eur = form.doviz_kuru_eur.data
            
            toplam_gelir = Decimal('0.00')
            formdan_gelen_idler = []

            for k_form in form.kalemler:
                f = k_form.form 
                bas, bit = f.kiralama_baslangici.data, f.kiralama_bitis.data
                if not (bas and bit): continue

                kalem_id = f.id.data
                aktif = KiralamaKalemi.query.get(int(kalem_id)) if (kalem_id and str(kalem_id).isdigit()) else KiralamaKalemi(kiralama_id=kiralama.id)
                
                # Önce NOT NULL alanlarını doldurarak IntegrityError'u engelle
                aktif.kiralama_baslangici, aktif.kiralama_bitis = bas, bit
                aktif.kiralama_brm_fiyat = Decimal(str(f.kiralama_brm_fiyat.data or 0))
                aktif.kiralama_alis_fiyat = Decimal(str(f.kiralama_alis_fiyat.data or 0))
                aktif.nakliye_satis_fiyat = Decimal(str(f.nakliye_satis_fiyat.data or 0))
                aktif.nakliye_alis_fiyat = Decimal(str(f.nakliye_alis_fiyat.data or 0))
                aktif.sonlandirildi = 0

                is_dis = int(f.dis_tedarik_ekipman.data or 0) == 1
                if not is_dis:
                    y_eid = int(f.ekipman_id.data or 0)
                    if y_eid > 0:
                        if aktif.ekipman_id and aktif.ekipman_id != y_eid:
                            eski = Ekipman.query.get(aktif.ekipman_id)
                            if eski: eski.calisma_durumu = 'bosta'
                        
                        aktif.ekipman_id, aktif.is_dis_tedarik_ekipman = y_eid, False
                        ekip = Ekipman.query.get(y_eid)
                        if ekip: ekip.calisma_durumu = 'kirada'
                else:
                    if aktif.ekipman_id:
                        eski = Ekipman.query.get(aktif.ekipman_id)
                        if eski: eski.calisma_durumu = 'bosta'
                    aktif.ekipman_id, aktif.is_dis_tedarik_ekipman = None, True
                    aktif.harici_ekipman_marka = f.harici_ekipman_marka.data
                    aktif.harici_ekipman_model = f.harici_ekipman_model.data
                    aktif.harici_ekipman_tedarikci_id = f.harici_ekipman_tedarikci_id.data if int(f.harici_ekipman_tedarikci_id.data or 0) > 0 else None

                aktif.is_harici_nakliye = int(f.dis_tedarik_nakliye.data or 0) == 1
                aktif.is_oz_mal_nakliye = not aktif.is_harici_nakliye
                aktif.nakliye_tedarikci_id = f.nakliye_tedarikci_id.data if aktif.is_harici_nakliye else None
                aktif.nakliye_araci_id = f.nakliye_araci_id.data if (aktif.is_oz_mal_nakliye and int(f.nakliye_araci_id.data or 0) > 0) else None
                
                gun = max((bit - bas).days + 1, 1)
                toplam_gelir += (aktif.kiralama_brm_fiyat * gun) + aktif.nakliye_satis_fiyat
                
                if not aktif.id: db.session.add(aktif)
                db.session.flush()
                formdan_gelen_idler.append(aktif.id)
            
            for k in list(kiralama.kalemler):
                if k.id not in formdan_gelen_idler:
                    if k.ekipman: k.ekipman.calisma_durumu = 'bosta'
                    db.session.delete(k)

            if toplam_gelir > 0:
                db.session.add(HizmetKaydi(
                    firma_id=kiralama.firma_musteri_id, tarih=date.today(), tutar=toplam_gelir,
                    yon='giden', fatura_no=kiralama.kiralama_form_no, ozel_id=kiralama.id,
                    aciklama=f"Kiralama Güncelleme - {kiralama.kiralama_form_no}"
                ))
            
            db.session.commit()
            flash('Kiralama güncellendi.', 'success')
            return redirect(url_for('kiralama.index'))
        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Hata: {e}", "danger")

    return render_template('kiralama/duzelt.html', form=form, kiralama=kiralama)

@kiralama_bp.route('/sil/<int:kiralama_id>', methods=['POST'])
def sil(kiralama_id):
    kiralama = Kiralama.query.get_or_404(kiralama_id)
    try:
        HizmetKaydi.query.filter_by(fatura_no=kiralama.kiralama_form_no).delete()
        for k in kiralama.kalemler:
            if k.ekipman: k.ekipman.calisma_durumu = 'bosta'
        db.session.delete(kiralama); db.session.commit(); flash('Kiralama silindi.', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'Hata: {e}', 'danger')
    return redirect(url_for('kiralama.index'))

@kiralama_bp.route('/kalem/sonlandir', methods=['POST'])
def sonlandir_kalem():
    try:
        kalem = KiralamaKalemi.query.get_or_404(request.form.get('kalem_id', type=int))
        bitis = request.form.get('bitis_tarihi')
        if bitis: kalem.kiralama_bitis = datetime.strptime(bitis, '%Y-%m-%d').date()
        kalem.sonlandirildi = True
        if kalem.ekipman: kalem.ekipman.calisma_durumu = 'bosta'
        db.session.commit(); guncelle_cari_toplam(kalem.kiralama_id); flash("Kalem sonlandırıldı.", "success")
    except Exception as e:
        db.session.rollback(); flash(f"Hata: {e}", "danger")
    return redirect(url_for('kiralama.index'))

@kiralama_bp.route('/kalem/iptal_et', methods=['POST'])
def iptal_et_kalem():
    try:
        kalem = KiralamaKalemi.query.get_or_404(request.form.get('kalem_id', type=int))
        kalem.sonlandirildi = False
        if kalem.ekipman: kalem.ekipman.calisma_durumu = 'kirada'
        db.session.commit(); guncelle_cari_toplam(kalem.kiralama_id); flash("Sonlandırma geri alındı.", "success")
    except Exception as e:
        db.session.rollback(); flash(f"Hata: {e}", "danger")
    return redirect(url_for('kiralama.index'))