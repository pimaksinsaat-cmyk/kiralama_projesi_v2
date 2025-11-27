from app.cari import cari_bp
from app import db
from flask import render_template, redirect, url_for, flash, request
from datetime import datetime
from decimal import Decimal
import traceback

# Modeller ve Formlar
from app.models import Odeme, HizmetKaydi, Firma, Kasa
from app.forms import OdemeForm, HizmetKaydiForm, KasaForm

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYON: Para Birimi Temizleme
# -------------------------------------------------------------------------
def clean_currency_input(value_str):
    """
    '2.500,50' -> '2500.50' yapar.
    """
    if not value_str:
        return '0.0'
    
    val = str(value_str).strip()
    
    # Virgül varsa, binlik ayracı olan noktaları sil, virgülü nokta yap
    if ',' in val:
        val = val.replace('.', '') # Binlikleri sil
        val = val.replace(',', '.') # Virgülü ondalık nokta yap
    
    return val

# -------------------------------------------------------------------------
# 1. YENİ ÖDEME/TAHSİLAT EKLEME
# -------------------------------------------------------------------------
@cari_bp.route('/odeme/ekle', methods=['GET', 'POST'])
def odeme_ekle():
    form = OdemeForm()
    
    try:
        musteriler = Firma.query.filter_by(is_musteri=True, is_active=True).order_by(Firma.firma_adi).all()
        form.firma_musteri_id.choices = [(f.id, f.firma_adi) for f in musteriler]
    except:
        form.firma_musteri_id.choices = []
    
    form.firma_musteri_id.choices.insert(0, (0, '--- Müşteri Seçiniz ---'))

    try:
        kasalar = Kasa.query.order_by(Kasa.kasa_adi).all()
        form.kasa_id.choices = [(k.id, f"{k.kasa_adi} ({k.para_birimi})") for k in kasalar]
    except:
        form.kasa_id.choices = []
        
    form.kasa_id.choices.insert(0, (0, '--- Kasa/Banka Seçiniz ---'))

    if request.method == 'GET':
        musteri_id = request.args.get('musteri_id', type=int)
        if musteri_id:
            form.firma_musteri_id.data = musteri_id
        
        form.tarih.data = datetime.today().date()

    if form.validate_on_submit():
        try:
            # --- DÜZELTME: Tutar Temizleme ---
            tutar_raw = form.tutar.data
            tutar_db = clean_currency_input(tutar_raw)
            # ---------------------------------
            
            yeni_odeme = Odeme(
                firma_musteri_id=form.firma_musteri_id.data,
                kasa_id=form.kasa_id.data,
                tarih=form.tarih.data.strftime('%Y-%m-%d'),
                tutar=tutar_db, # Temizlenmiş tutar
                fatura_no=form.fatura_no.data,
                vade_tarihi=form.vade_tarihi.data.strftime('%Y-%m-%d') if form.vade_tarihi.data else None,
                aciklama=form.aciklama.data
            )
            
            db.session.add(yeni_odeme)
            
            # Kasa bakiyesini güncelle
            kasa = Kasa.query.get(form.kasa_id.data)
            if kasa:
                try:
                    eski_bakiye = float(kasa.bakiye or 0)
                except ValueError:
                    eski_bakiye = 0.0
                
                # Yeni tutarı ekle
                yeni_bakiye = eski_bakiye + float(tutar_db)
                kasa.bakiye = str(yeni_bakiye)
            
            db.session.commit()
            
            firma = Firma.query.get(form.firma_musteri_id.data)
            flash(f'{firma.firma_adi} firmasından {tutar_db} tutarında ödeme alındı.', 'success')
            
            return redirect(url_for('firmalar.bilgi', id=form.firma_musteri_id.data))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Hata oluştu: {str(e)}', 'danger')
            traceback.print_exc()

    return render_template('cari/odeme_ekle.html', form=form)


# -------------------------------------------------------------------------
# 1.1. ÖDEME DÜZENLEME
# -------------------------------------------------------------------------
@cari_bp.route('/odeme/duzelt/<int:id>', methods=['GET', 'POST'])
def odeme_duzelt(id):
    odeme = Odeme.query.get_or_404(id)
    form = OdemeForm(obj=odeme)
    
    # Select listelerini doldur
    try:
        musteriler = Firma.query.filter_by(is_musteri=True, is_active=True).order_by(Firma.firma_adi).all()
        form.firma_musteri_id.choices = [(f.id, f.firma_adi) for f in musteriler]
    except: form.firma_musteri_id.choices = []
    form.firma_musteri_id.choices.insert(0, (0, '--- Müşteri Seçiniz ---'))

    try:
        kasalar = Kasa.query.order_by(Kasa.kasa_adi).all()
        form.kasa_id.choices = [(k.id, f"{k.kasa_adi} ({k.para_birimi})") for k in kasalar]
    except: form.kasa_id.choices = []
    form.kasa_id.choices.insert(0, (0, '--- Kasa/Banka Seçiniz ---'))

    if request.method == 'GET':
        if odeme.tarih: form.tarih.data = datetime.strptime(odeme.tarih, '%Y-%m-%d').date()
        if odeme.vade_tarihi: form.vade_tarihi.data = datetime.strptime(odeme.vade_tarihi, '%Y-%m-%d').date()
        # Tutarı noktalı formatta ver (15000.50)
        # Eğer virgüllü ise temizlemeden verelim ki JS formatlasın
        if odeme.tutar:
            form.tutar.data = odeme.tutar

    if form.validate_on_submit():
        try:
            # Eski değerleri sakla (Bakiye düzeltmesi için)
            eski_tutar = float(odeme.tutar or 0)
            eski_kasa_id = odeme.kasa_id
            
            # Yeni veriler
            tutar_raw = form.tutar.data
            yeni_tutar_db = clean_currency_input(tutar_raw)
            yeni_tutar_float = float(yeni_tutar_db)
            yeni_kasa_id = form.kasa_id.data
            
            # Ödemeyi güncelle
            odeme.firma_musteri_id = form.firma_musteri_id.data
            odeme.kasa_id = yeni_kasa_id
            odeme.tarih = form.tarih.data.strftime('%Y-%m-%d')
            odeme.tutar = yeni_tutar_db
            odeme.fatura_no = form.fatura_no.data
            odeme.vade_tarihi = form.vade_tarihi.data.strftime('%Y-%m-%d') if form.vade_tarihi.data else None
            odeme.aciklama = form.aciklama.data

            # --- KASA BAKİYESİ DÜZELTME ---
            # 1. Eski kasadan eski tutarı ÇIKAR (İptal et)
            if eski_kasa_id:
                eski_kasa = Kasa.query.get(eski_kasa_id)
                if eski_kasa:
                    mevcut = float(eski_kasa.bakiye or 0)
                    eski_kasa.bakiye = str(mevcut - eski_tutar)
            
            # 2. Yeni kasaya yeni tutarı EKLE
            if yeni_kasa_id:
                yeni_kasa = Kasa.query.get(yeni_kasa_id)
                if yeni_kasa:
                    mevcut = float(yeni_kasa.bakiye or 0)
                    yeni_kasa.bakiye = str(mevcut + yeni_tutar_float)
            # ------------------------------
            
            db.session.commit()
            flash('Ödeme güncellendi.', 'success')
            return redirect(url_for('firmalar.bilgi', id=form.firma_musteri_id.data))

        except Exception as e:
            db.session.rollback(); flash(f'Hata: {str(e)}', 'danger')
            traceback.print_exc()

    return render_template('cari/odeme_duzelt.html', form=form, odeme=odeme)


# -------------------------------------------------------------------------
# 1.2. ÖDEME SİLME
# -------------------------------------------------------------------------
@cari_bp.route('/odeme/sil/<int:id>', methods=['POST'])
def odeme_sil(id):
    odeme = Odeme.query.get_or_404(id)
    firma_id = odeme.firma_musteri_id
    try:
        # Kasadan düş (İşlemi geri al)
        if odeme.kasa:
            tutar = float(odeme.tutar or 0)
            mevcut_bakiye = float(odeme.kasa.bakiye or 0)
            odeme.kasa.bakiye = str(mevcut_bakiye - tutar)
        
        db.session.delete(odeme)
        db.session.commit()
        flash('Ödeme silindi ve kasadan düşüldü.', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'Hata: {str(e)}', 'danger')
        
    return redirect(url_for('firmalar.bilgi', id=firma_id))


# -------------------------------------------------------------------------
# 2. YENİ HİZMET/FATURA KAYDI EKLEME
# -------------------------------------------------------------------------
@cari_bp.route('/hizmet/ekle', methods=['GET', 'POST'])
def hizmet_ekle():
    form = HizmetKaydiForm()
    
    # Tüm Aktif Firmalar (Hem müşteri hem tedarikçi olabilir)
    try:
        firmalar = Firma.query.filter_by(is_active=True).order_by(Firma.firma_adi).all()
        form.firma_id.choices = [(f.id, f.firma_adi) for f in firmalar]
    except:
        form.firma_id.choices = []
    form.firma_id.choices.insert(0, (0, '--- Firma Seçiniz ---'))
    
    if request.method == 'GET':
        firma_id = request.args.get('firma_id', type=int)
        if firma_id:
            form.firma_id.data = firma_id
        form.tarih.data = datetime.today().date()

    if form.validate_on_submit():
        try:
            # --- DÜZELTME: Tutar Temizleme ---
            tutar_raw = form.tutar.data
            tutar_db = clean_currency_input(tutar_raw)
            # ---------------------------------

            yeni_hizmet = HizmetKaydi(
                firma_id=form.firma_id.data,
                tarih=form.tarih.data.strftime('%Y-%m-%d'),
                tutar=tutar_db, # Temizlenmiş tutar
                aciklama=form.aciklama.data,
                yon=form.yon.data, 
                fatura_no=form.fatura_no.data,
                vade_tarihi=form.vade_tarihi.data.strftime('%Y-%m-%d') if form.vade_tarihi.data else None
            )
            
            db.session.add(yeni_hizmet)
            db.session.commit()
            
            flash('Hizmet/Fatura kaydı başarıyla oluşturuldu.', 'success')
            return redirect(url_for('firmalar.bilgi', id=form.firma_id.data))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Hata oluştu: {str(e)}', 'danger')
            traceback.print_exc()

    return render_template('cari/hizmet_ekle.html', form=form)


# -------------------------------------------------------------------------
# 2.1. HİZMET DÜZENLEME
# -------------------------------------------------------------------------
@cari_bp.route('/hizmet/duzelt/<int:id>', methods=['GET', 'POST'])
def hizmet_duzelt(id):
    hizmet = HizmetKaydi.query.get_or_404(id)
    form = HizmetKaydiForm(obj=hizmet)
    
    try:
        firmalar = Firma.query.filter_by(is_active=True).order_by(Firma.firma_adi).all()
        form.firma_id.choices = [(f.id, f.firma_adi) for f in firmalar]
    except: form.firma_id.choices = []
    form.firma_id.choices.insert(0, (0, '--- Firma Seçiniz ---'))

    if request.method == 'GET':
        if hizmet.tarih: form.tarih.data = datetime.strptime(hizmet.tarih, '%Y-%m-%d').date()
        if hizmet.vade_tarihi: form.vade_tarihi.data = datetime.strptime(hizmet.vade_tarihi, '%Y-%m-%d').date()
        if hizmet.tutar: form.tutar.data = hizmet.tutar

    if form.validate_on_submit():
        try:
            hizmet.firma_id = form.firma_id.data
            hizmet.tarih = form.tarih.data.strftime('%Y-%m-%d')
            hizmet.tutar = clean_currency_input(form.tutar.data)
            hizmet.aciklama = form.aciklama.data
            hizmet.yon = form.yon.data
            hizmet.fatura_no = form.fatura_no.data
            hizmet.vade_tarihi = form.vade_tarihi.data.strftime('%Y-%m-%d') if form.vade_tarihi.data else None
            
            db.session.commit()
            flash('Kayıt güncellendi.', 'success')
            return redirect(url_for('firmalar.bilgi', id=hizmet.firma_id))
        except Exception as e:
            db.session.rollback(); flash(f'Hata: {str(e)}', 'danger')

    return render_template('cari/hizmet_duzelt.html', form=form, hizmet=hizmet)

# -------------------------------------------------------------------------
# 2.2. HİZMET SİLME
# -------------------------------------------------------------------------
@cari_bp.route('/hizmet/sil/<int:id>', methods=['POST'])
def hizmet_sil(id):
    hizmet = HizmetKaydi.query.get_or_404(id)
    firma_id = hizmet.firma_id
    try:
        db.session.delete(hizmet)
        db.session.commit()
        flash('Kayıt silindi.', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'Hata: {str(e)}', 'danger')
    return redirect(url_for('firmalar.bilgi', id=firma_id))


# -------------------------------------------------------------------------
# 3. KASA/BANKA TANIMLAMA VE LİSTELEME
# -------------------------------------------------------------------------
@cari_bp.route('/kasa/ekle', methods=['GET', 'POST'])
def kasa_ekle():
    form = KasaForm()
    if form.validate_on_submit():
        try:
            yeni_kasa = Kasa(
                kasa_adi=form.kasa_adi.data,
                tipi=form.tipi.data,
                para_birimi=form.para_birimi.data,
                bakiye=str(form.bakiye.data or 0.0)
            )
            db.session.add(yeni_kasa)
            db.session.commit()
            flash('Yeni kasa/banka hesabı tanımlandı.', 'success')
            return redirect(url_for('cari.kasa_listesi'))
        except Exception as e:
            db.session.rollback()
            flash(f'Hata: {str(e)}', 'danger')
            
    return render_template('cari/kasa_ekle.html', form=form)

@cari_bp.route('/kasa/listesi')
def kasa_listesi():
    kasalar = Kasa.query.order_by(Kasa.kasa_adi).all()
    return render_template('cari/kasa_listesi.html', kasalar=kasalar)