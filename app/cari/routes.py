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
# 2. YENİ HİZMET/FATURA KAYDI EKLEME
# -------------------------------------------------------------------------
@cari_bp.route('/hizmet/ekle', methods=['GET', 'POST'])
def hizmet_ekle():
    form = HizmetKaydiForm()
    
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