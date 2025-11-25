from app.firmalar import firmalar_bp
from app import db
from flask import render_template, url_for, redirect, flash, request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
import traceback
from decimal import Decimal

# Modeller
from app.models import Firma, Kiralama, Ekipman, Odeme, HizmetKaydi, KiralamaKalemi, StokKarti, StokHareket
from app.forms import FirmaForm
from sqlalchemy.orm import joinedload, subqueryload

# -------------------------------------------------------------------------
# 1. Firma Listeleme
# -------------------------------------------------------------------------
@firmalar_bp.route('/')
@firmalar_bp.route('/index')
def index():
    try:
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '', type=str)
        base_query = Firma.query.filter_by(is_active=True)
        
        if q:
            search_term = f'%{q}%'
            base_query = base_query.filter(or_(Firma.firma_adi.ilike(search_term), Firma.yetkili_adi.ilike(search_term), Firma.vergi_no.ilike(search_term)))
            
        pagination = base_query.order_by(Firma.firma_adi).paginate(page=page, per_page=25, error_out=False)
        firmalar = pagination.items
        return render_template('firmalar/index.html', firmalar=firmalar, pagination=pagination, q=q)
    except Exception as e:
        flash(f"Hata: {str(e)}", "danger"); return render_template('firmalar/index.html', firmalar=[], pagination=None, q=q)

# -------------------------------------------------------------------------
# 2. Yeni Firma Ekleme
# -------------------------------------------------------------------------
@firmalar_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    form = FirmaForm()
    if form.validate_on_submit():
        try:
            yeni_firma = Firma(
                firma_adi=form.firma_adi.data, yetkili_adi=form.yetkili_adi.data, iletisim_bilgileri=form.iletisim_bilgileri.data,
                vergi_dairesi=form.vergi_dairesi.data, vergi_no=form.vergi_no.data, is_musteri=form.is_musteri.data, is_tedarikci=form.is_tedarikci.data, is_active=True
            )
            db.session.add(yeni_firma)
            db.session.commit()
            flash('Firma eklendi!', 'success')
            return redirect(url_for('firmalar.index'))
        except Exception as e:
            db.session.rollback(); flash(f"Hata: {str(e)}", "danger")
    return render_template('firmalar/ekle.html', form=form)

# -------------------------------------------------------------------------
# 3. Firma Silme (Soft Delete)
# -------------------------------------------------------------------------
@firmalar_bp.route('/sil/<int:id>', methods=['POST'])
def sil(id):
    firma = Firma.query.get_or_404(id)
    try:
        firma.is_active = False
        db.session.commit()
        flash(f"'{firma.firma_adi}' arşive kaldırıldı.", 'success')
    except Exception as e:
        db.session.rollback(); flash(f"Hata: {str(e)}", 'danger')
    return redirect(url_for('firmalar.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))

# -------------------------------------------------------------------------
# 4. Firma Düzenleme
# -------------------------------------------------------------------------
@firmalar_bp.route('/duzelt/<int:id>', methods=['GET', 'POST'])
def duzelt(id):
    firma = Firma.query.filter_by(id=id, is_active=True).first_or_404()
    form = FirmaForm(obj=firma)
    if form.validate_on_submit():
        try:
            firma.firma_adi = form.firma_adi.data; firma.yetkili_adi = form.yetkili_adi.data; firma.iletisim_bilgileri = form.iletisim_bilgileri.data
            firma.vergi_dairesi = form.vergi_dairesi.data; firma.vergi_no = form.vergi_no.data; firma.is_musteri = form.is_musteri.data; firma.is_tedarikci = form.is_tedarikci.data
            db.session.commit()
            flash('Güncellendi!', 'success')
            return redirect(url_for('firmalar.index'))
        except Exception as e:
            db.session.rollback(); flash(f"Hata: {str(e)}", "danger")
    return render_template('firmalar/duzelt.html', form=form, firma=firma) 

# -------------------------------------------------------------------------
# 5. Firma Bilgi Sayfası (CARİ HESAPLAMA BURADA)
# -------------------------------------------------------------------------
@firmalar_bp.route('/bilgi/<int:id>', methods=['GET'])
def bilgi(id):
    try:
        firma = Firma.query.options(
            subqueryload(Firma.kiralamalar).options(subqueryload(Kiralama.kalemler).options(joinedload(KiralamaKalemi.ekipman))),
            subqueryload(Firma.odemeler),
            subqueryload(Firma.hizmet_kayitlari),
            subqueryload(Firma.tedarik_edilen_ekipmanlar),
            subqueryload(Firma.saglanan_nakliye_hizmetleri),
            subqueryload(Firma.tedarik_edilen_parcalar),
            subqueryload(Firma.stok_hareketleri)
        ).get_or_404(id)
        
        # --- CARİ HESAPLAMA BAŞLANGICI ---
        toplam_borc = 0.0   # Firmanın bize borcu (Bizim kestiğimiz faturalar)
        toplam_alacak = 0.0 # Firmanın bizden alacağı (Ödemeler + Onların kestiği faturalar)
        
        # 1. Hizmet/Fatura Kayıtlarını Hesapla
        # (Kiralama işlemlerini de HizmetKaydi'na işlediğimiz için onları ayrıca toplamıyoruz,
        # hepsi burada 'giden' veya 'gelen' olarak birikiyor.)
        for h in firma.hizmet_kayitlari:
            tutar = float(h.tutar or 0)
            if h.yon == 'giden':
                toplam_borc += tutar # Borçlandır (Satış/Kiralama Geliri)
            elif h.yon == 'gelen':
                toplam_alacak += tutar # Alacaklandır (Alış/Gider Faturası)
                
        # 2. Ödemeleri (Tahsilatları) Hesapla
        for o in firma.odemeler:
            toplam_alacak += float(o.tutar or 0) # Ödeme yaptı, borcu düştü (alacak hanesine yazılır)
            
        bakiye = toplam_borc - toplam_alacak
        # -----------------------------------
        
        return render_template('firmalar/bilgi.html', 
                               firma=firma,
                               toplam_borc=toplam_borc,
                               toplam_alacak=toplam_alacak,
                               bakiye=bakiye)
                               
    except Exception as e:
        flash(f"Hata: {str(e)}", "danger"); traceback.print_exc()
        return redirect(url_for('firmalar.index'))