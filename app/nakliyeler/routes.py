from flask import render_template, redirect, url_for, flash, request
from app import db
from . import nakliye_bp
from decimal import Decimal, InvalidOperation
import traceback

# Modeller ve Formlar
from .models import Nakliye
from app.firmalar.models import Firma
from app.cari.models import HizmetKaydi
from .forms import NakliyeForm

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYON: Decimal Hata Çözücü
# -------------------------------------------------------------------------
def to_decimal(value):
    if value is None or value == '':
        return Decimal('0.00')
    if isinstance(value, Decimal):
        return value
    try:
        clean_val = str(value).replace('.', '').replace(',', '.')
        return Decimal(clean_val)
    except (InvalidOperation, ValueError):
        return Decimal('0.00')

# ---------------------------------------------------
# 1. LİSTELEME
# ---------------------------------------------------
@nakliye_bp.route('/')
@nakliye_bp.route('/index')
def index():
    nakliyeler = Nakliye.query.order_by(Nakliye.tarih.desc()).all()
    return render_template('nakliyeler/index.html', nakliyeler=nakliyeler)

# ---------------------------------------------------
# 2. YENİ NAKLİYE EKLEME
# ---------------------------------------------------
@nakliye_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    form = NakliyeForm()
    firmalar = Firma.query.filter_by(is_active=True).order_by(Firma.firma_adi).all()
    form.firma_id.choices = [(f.id, f.firma_adi) for f in firmalar]

    if form.validate_on_submit():
        try:
            nakliye = Nakliye()
            form.populate_obj(nakliye)
            nakliye.tutar = to_decimal(request.form.get('tutar'))
            nakliye.hesapla_ve_guncelle()

            # --- CARİ ENTEGRASYONU (Yeni İlişki Yapısıyla) ---
            yeni_hareket = HizmetKaydi(
                firma_id=nakliye.firma_id,
                tarih=nakliye.tarih,
                tutar=nakliye.toplam_tutar,
                yon='giden', # ÖNEMLİ: Gider olduğu için 'gelen' yaptık
                aciklama=f"Nakliye: {nakliye.plaka} | {nakliye.guzergah}",
                fatura_no=f"NK-{nakliye.tarih.strftime('%y%m%d')}",
                # İlişkiyi bağlıyoruz:
                ilgili_nakliye=nakliye 
            )
            
            nakliye.cari_islendi_mi = True
            db.session.add(nakliye)
            db.session.add(yeni_hareket)
            db.session.commit()
            
            flash('Nakliye eklendi ve cariye işlendi.', 'success')
            return redirect(url_for('nakliyeler.index'))
            
        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f'Kayıt sırasında bir hata oluştu: {str(e)}', 'danger')

    return render_template('nakliyeler/ekle.html', form=form)

# ---------------------------------------------------
# 3. DÜZENLEME
# ---------------------------------------------------
@nakliye_bp.route('/duzenle/<int:id>', methods=['GET', 'POST'])
def duzenle(id):
    nakliye = Nakliye.query.get_or_404(id)
    form = NakliyeForm(obj=nakliye)
    
    firmalar = Firma.query.filter_by(is_active=True).order_by(Firma.firma_adi).all()
    form.firma_id.choices = [(f.id, f.firma_adi) for f in firmalar]

    if form.validate_on_submit():
        try: # Eksik olan try eklendi
            form.populate_obj(nakliye)
            nakliye.tutar = to_decimal(request.form.get('tutar'))
            nakliye.hesapla_ve_guncelle()
            
            # İlişki üzerinden cari kaydı otomatik bul ve güncelle
            if nakliye.cari_hareket:
                nakliye.cari_hareket.tarih = nakliye.tarih
                nakliye.cari_hareket.tutar = nakliye.toplam_tutar
                nakliye.cari_hareket.firma_id = nakliye.firma_id
                nakliye.cari_hareket.aciklama = f"Nakliye: {nakliye.plaka} | {nakliye.guzergah}"
    
            db.session.commit()
            flash('Kayıt ve cari hareket başarıyla güncellendi.', 'success')
            return redirect(url_for('nakliyeler.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Güncelleme Hatası: {e}', 'danger')

    return render_template('nakliyeler/duzenle.html', form=form)

# ---------------------------------------------------
# 4. SİLME
# ---------------------------------------------------
@nakliye_bp.route('/sil/<int:id>', methods=['POST'])
def sil(id):
    nakliye = Nakliye.query.get_or_404(id)
    try:
        # Cascade sayesinde HizmetKaydi otomatik silinecek
        db.session.delete(nakliye)
        db.session.commit()
        flash('Kayıt ve bağlı cari hareket silindi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Silme Hatası: {e}', 'danger')
        
    return redirect(url_for('nakliyeler.index'))

# ---------------------------------------------------
# 5. DETAY
# ---------------------------------------------------
@nakliye_bp.route('/detay/<int:id>')
def detay(id):
    nakliye = Nakliye.query.get_or_404(id)
    return render_template('nakliyeler/detay.html', nakliye=nakliye)