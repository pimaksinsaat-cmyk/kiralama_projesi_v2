from app.firmalar import firmalar_bp
from app import db
from flask import render_template, url_for, redirect, flash, request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
import traceback

# Tüm modelleri import ediyoruz (ilişkiler için gerekli olabilir)
from app.models import Firma, Kiralama, Ekipman, Odeme, HizmetKaydi, KiralamaKalemi, StokKarti, StokHareket
from app.forms import FirmaForm
from sqlalchemy.orm import joinedload, subqueryload

# -------------------------------------------------------------------------
# 1. Firma Listeleme Sayfası (Arama + Sayfalama + Soft Delete)
# -------------------------------------------------------------------------
@firmalar_bp.route('/')
@firmalar_bp.route('/index')
def index():
    """
    Tüm aktif firmaları (müşteriler VE tedarikçiler) listeler.
    GELİŞMİŞ ARAMA (Firma Adı VEYA Yetkili Adı) ve Sayfalama destekler.
    """
    try:
        # 1. URL'den parametreleri al
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '', type=str) # Arama sorgusu
        
        # 2. Temel sorgu: SADECE AKTİF olanlar (Silinmemişler)
        base_query = Firma.query.filter_by(is_active=True)
        
        # 3. Arama filtresi
        if q:
            search_term = f'%{q}%'
            base_query = base_query.filter(
                or_(
                    Firma.firma_adi.ilike(search_term),
                    Firma.yetkili_adi.ilike(search_term),
                    Firma.vergi_no.ilike(search_term) # Vergi no ile de arama eklendi
                )
            )
            
        # 4. Sayfalama
        pagination = base_query.order_by(Firma.firma_adi).paginate(
            page=page, per_page=25, error_out=False
        )
        firmalar = pagination.items
        
        return render_template('firmalar/index.html', 
                               firmalar=firmalar, 
                               pagination=pagination,
                               q=q)
                               
    except Exception as e:
        flash(f"Firmalar yüklenirken bir hata oluştu: {str(e)}", "danger")
        traceback.print_exc()
        return render_template('firmalar/index.html', firmalar=[], pagination=None, q=q)

# -------------------------------------------------------------------------
# 2. Yeni Firma Ekleme Sayfası
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
                is_tedarikci=form.is_tedarikci.data,
                is_active=True # Yeni firma varsayılan olarak aktiftir
            )
            
            db.session.add(yeni_firma)
            db.session.commit()
            
            flash('Yeni firma başarıyla eklendi!', 'success')
            return redirect(url_for('firmalar.index'))
            
        except IntegrityError as e:
            db.session.rollback() 
            if 'UNIQUE constraint failed' in str(e) or 'firma.vergi_no' in str(e):
                flash(f'HATA: Girdiğiniz vergi numarası ({form.vergi_no.data}) zaten sistemde kayıtlı.', 'danger')
            else:
                flash(f'Veritabanı bütünlük hatası: {str(e)}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f"Firma eklenirken beklenmedik bir hata oluştu: {str(e)}", "danger")
            traceback.print_exc()

    return render_template('firmalar/ekle.html', form=form)

# -------------------------------------------------------------------------
# 3. Firma Silme İşlemi (SOFT DELETE - PASİFE ALMA)
# -------------------------------------------------------------------------
@firmalar_bp.route('/sil/<int:id>', methods=['POST'])
def sil(id):
    # Silinen bir firmayı tekrar silmeye çalışırsa 404 vermemesi için normal get
    firma = Firma.query.get_or_404(id)
    
    # FİZİKSEL SİLME YAPMIYORUZ. Sadece 'is_active' alanını False yapıyoruz.
    # Böylece geçmiş kiralama/cari kayıtları bozulmuyor.
    try:
        firma.is_active = False
        db.session.commit()
        flash(f"'{firma.firma_adi}' başarıyla silindi (arşive kaldırıldı).", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Firma silinirken bir hata oluştu: {str(e)}", 'danger')
        traceback.print_exc() 
    
    # Arama/Sayfalama parametrelerini koruyarak listeye dön
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '')
    return redirect(url_for('firmalar.index', page=page, q=q))
    
# -------------------------------------------------------------------------
# 4. Firma Düzenleme Sayfası
# -------------------------------------------------------------------------
@firmalar_bp.route('/duzelt/<int:id>', methods=['GET', 'POST'])
def duzelt(id):
    # Sadece aktif firmalar düzenlenebilir (Pasifleri düzenlemek için önce aktifleştirmek gerekir - İleride eklenebilir)
    firma = Firma.query.filter_by(id=id, is_active=True).first_or_404()
    
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
            
            # Listeye geri dön
            page = request.args.get('page', 1, type=int)
            q = request.args.get('q', '')
            return redirect(url_for('firmalar.index', page=page, q=q))
            
        except IntegrityError as e:
            db.session.rollback() 
            if 'UNIQUE constraint failed' in str(e) or 'firma.vergi_no' in str(e):
                flash(f'HATA: Bu vergi numarası ({form.vergi_no.data}) başka bir firmada kullanılıyor.', 'danger')
            else:
                flash(f'Veritabanı hatası: {str(e)}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f"Firma güncellenirken hata oluştu: {str(e)}", "danger")
            traceback.print_exc()
    
    return render_template('firmalar/duzelt.html', form=form, firma=firma) 

# -------------------------------------------------------------------------
# 5. Firma Bilgi Sayfası (Cari ve Geçmiş Hareketler)
# -------------------------------------------------------------------------
@firmalar_bp.route('/bilgi/<int:id>', methods=['GET'])
def bilgi(id):
    """
    ID'si verilen firmanın detaylı bilgilerini gösterir.
    (Cari Hesap Ekstresi ve tüm ilişkili verileri yükler)
    """
    try:
        # --- EAGER LOADING (HIZLI YÜKLEME) ---
        # Tek bir sorguda firmanın tüm ilişkilerini çekiyoruz.
        # Pasif firmalar da detay sayfasında görüntülenebilir (Link varsa).
        firma = Firma.query.options(
            # Müşteri olduğu kiralamalar
            subqueryload(Firma.kiralamalar).options(
                subqueryload(Kiralama.kalemler).options(
                    joinedload(KiralamaKalemi.ekipman)
                )
            ),
            # Yaptığı ödemeler
            subqueryload(Firma.odemeler),
            # Bağımsız hizmet hareketleri
            subqueryload(Firma.hizmet_kayitlari),
            # Tedarikçi olduğu ekipmanlar
            subqueryload(Firma.tedarik_edilen_ekipmanlar),
            # Nakliye tedarikçisi olduğu kalemler
            subqueryload(Firma.saglanan_nakliye_hizmetleri),
            # Tedarik ettiği yedek parçalar (Stok Kartları)
            subqueryload(Firma.tedarik_edilen_parcalar),
            # Stok Hareketleri (Satın almalar)
            subqueryload(Firma.stok_hareketleri)
        ).get_or_404(id)
        
        return render_template('firmalar/bilgi.html', firma=firma)
        
    except Exception as e:
        flash(f"Firma bilgileri yüklenirken bir hata oluştu: {str(e)}", "danger")
        traceback.print_exc()
        return redirect(url_for('firmalar.index'))