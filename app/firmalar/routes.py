from app.firmalar import firmalar_bp
from app import db
# DÜZELTME: 'request' ve 'or_' eklendi
from flask import render_template, url_for, redirect, flash, request
from sqlalchemy import or_ # 'VEYA' sorgusu için eklendi
from sqlalchemy.exc import IntegrityError
import traceback

# --- GÜNCELLENEN IMPORTLAR ---
from app.models import Firma, Kiralama, Ekipman, Odeme, HizmetKaydi, KiralamaKalemi
from app.forms import FirmaForm
from sqlalchemy.orm import joinedload, subqueryload
# --- GÜNCELLENEN IMPORTLAR SONU ---

# -------------------------------------------------------------------------
# 1. Firma Listeleme Sayfası (ARAMA VE SAYFALAMA EKLENDİ)
# -------------------------------------------------------------------------
@firmalar_bp.route('/')
@firmalar_bp.route('/index')
def index():
    """
    Tüm firmaları (müşteriler VE tedarikçiler) listeler.
    GELİŞMİŞ ARAMA (Firma Adı VEYA Yetkili Adı) ve Sayfalama destekler.
    """
    try:
        # 1. URL'den 'page' (sayfa) ve 'q' (arama) parametrelerini al
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '', type=str) # Arama sorgusu
        
        # 2. Temel sorguyu başlat
        base_query = Firma.query
        
        # 3. Eğer bir arama sorgusu (q) varsa, sorguyu filtrele
        if q:
            # --- DÜZELTME: Arama artık iki alanda (Firma Adı VEYA Yetkili Adı) çalışır ---
            search_term = f'%{q}%'
            base_query = base_query.filter(
                or_(
                    Firma.firma_adi.ilike(search_term),
                    Firma.yetkili_adi.ilike(search_term)
                    # Buraya (ileride) Firma.vergi_no.ilike(search_term) de eklenebilir
                )
            )
            # --- DÜZELTME SONU ---
            
        # 4. Filtrelenmiş sorguyu, Sayfalama (paginate) yaparak çalıştır
        # (Her sayfada 25 firma göster)
        pagination = base_query.order_by(Firma.firma_adi).paginate(
            page=page, per_page=25, error_out=False
        )
        # O sayfaya ait firmaları al
        firmalar = pagination.items
        
        # 5. HTML'e 'firmalar' listesini, 'pagination' nesnesini ve 'q' (arama) sorgusunu gönder
        return render_template('firmalar/index.html', 
                               firmalar=firmalar, 
                               pagination=pagination,
                               q=q)
                               
    except Exception as e:
        flash(f"Firmalar yüklenirken bir hata oluştu: {str(e)}", "danger")
        traceback.print_exc()
        return render_template('firmalar/index.html', firmalar=[], pagination=None, q=q)

# -------------------------------------------------------------------------
# 2. Yeni Firma Ekleme Sayfası (Değişiklik yok)
# -------------------------------------------------------------------------
@firmalar_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    form = FirmaForm()
    if form.validate_on_submit():
        try:
            yeni_firma = Firma(
                firma_adi=form.firma_adi.data,
                yetkili_adi=form.yetkili_adi.data,
                iletisim_bilgileri=form.iletisim_bilgileri.data,
                vergi_dairesi=form.vergi_dairesi.data,
                vergi_no=form.vergi_no.data,
                is_musteri=form.is_musteri.data,
                is_tedarikci=form.is_tedarikci.data
            )
            db.session.add(yeni_firma)
            db.session.commit()
            flash('Yeni firma başarıyla eklendi!', 'success')
            return redirect(url_for('firmalar.index'))
        except IntegrityError as e:
            db.session.rollback() 
            if 'UNIQUE constraint failed: firma.vergi_no' in str(e):
                flash(f'HATA: Girdiğiniz vergi numarası ({form.vergi_no.data}) zaten sistemde kayıtlı.', 'danger')
            else:
                flash(f'Veritabanı bütünlük hatası: {str(e)}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f"Firma eklenirken beklenmedik bir hata oluştu: {str(e)}", "danger")
            traceback.print_exc()
    return render_template('firmalar/ekle.html', form=form)

# -------------------------------------------------------------------------
# 3. Firma Silme İşlemi (Değişiklik yok)
# -------------------------------------------------------------------------
@firmalar_bp.route('/sil/<int:id>', methods=['POST'])
def sil(id):
    firma = Firma.query.options(
        joinedload(Firma.kiralamalar),
        joinedload(Firma.odemeler),
        joinedload(Firma.hizmet_kayitlari),
        joinedload(Firma.tedarik_edilen_ekipmanlar),
        joinedload(Firma.saglanan_nakliye_hizmetleri)
    ).get_or_404(id)
    
    if (firma.kiralamalar or 
        firma.odemeler or 
        firma.hizmet_kayitlari or 
        firma.tedarik_edilen_ekipmanlar or 
        firma.saglanan_nakliye_hizmetleri):
        
        flash(f"HATA: '{firma.firma_adi}' SİLİNEMEZ!", 'danger')
        flash("Bu firmanın ilişkili kiralama, ödeme, hizmet veya ekipman kayıtları bulunmaktadır.", 'warning')
        return redirect(url_for('firmalar.index'))
    
    try:
        db.session.delete(firma)
        db.session.commit()
        flash(f"'{firma.firma_adi}' başarıyla silindi (hiçbir finansal hareketi yoktu).", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Firma silinirken bir hata oluştu: {str(e)}", 'danger')
        traceback.print_exc() 
    
    return redirect(url_for('firmalar.index')) 
    
# -------------------------------------------------------------------------
# 4. Firma Düzenleme Sayfası (Değişiklik yok)
# -------------------------------------------------------------------------
@firmalar_bp.route('/duzelt/<int:id>', methods=['GET', 'POST'])
def duzelt(id):
    firma = Firma.query.get_or_404(id)
    form = FirmaForm(obj=firma)
    if form.validate_on_submit():
        try:
            firma.firma_adi = form.firma_adi.data
            firma.yetkili_adi = form.yetkili_adi.data
            firma.iletisim_bilgileri = form.iletisim_bilgileri.data
            firma.vergi_dairesi = form.vergi_dairesi.data
            firma.vergi_no = form.vergi_no.data
            firma.is_musteri = form.is_musteri.data
            firma.is_tedarikci = form.is_tedarikci.data
            db.session.commit()
            flash('Firma bilgileri başarıyla güncellendi!', 'success')
            return redirect(url_for('firmalar.index'))
        except IntegrityError as e:
            db.session.rollback() 
            if 'UNIQUE constraint failed: firma.vergi_no' in str(e):
                flash(f'HATA: Girdiğiniz vergi numarası ({form.vergi_no.data}) zaten başka bir kayıtta mevcut.', 'danger')
            else:
                flash(f'Veritabanı bütünlük hatası: {str(e)}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f"Firma güncellenirken beklenmedik bir hata oluştu: {str(e)}", "danger")
            traceback.print_exc()
    return render_template('firmalar/duzelt.html', form=form, firma=firma) 

# -------------------------------------------------------------------------
# 5. Firma Bilgi Sayfası (Cari Bakiye için hazır)
# -------------------------------------------------------------------------
@firmalar_bp.route('/bilgi/<int:id>', methods=['GET'])
def bilgi(id):
    try:
        firma = Firma.query.options(
            subqueryload(Firma.kiralamalar).options(
                subqueryload(Kiralama.kalemler).options(
                    joinedload(KiralamaKalemi.ekipman)
                )
            ),
            subqueryload(Firma.odemeler),
            subqueryload(Firma.hizmet_kayitlari),
            subqueryload(Firma.tedarik_edilen_ekipmanlar),
            subqueryload(Firma.saglanan_nakliye_hizmetleri)
        ).get_or_404(id)
        
        # (İleride buraya Cari Bakiye hesaplama mantığı eklenecek)
        
        return render_template('firmalar/bilgi.html', firma=firma)
    except Exception as e:
        flash(f"Firma bilgileri yüklenirken bir hata oluştu: {str(e)}", "danger")
        traceback.print_exc()
        return redirect(url_for('firmalar.index'))