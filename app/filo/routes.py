from app.filo import filo_bp
from app import db 
from decimal import Decimal 
from flask import render_template, redirect, url_for, flash, request, jsonify
from datetime import datetime, date # 'date' eklendi
from sqlalchemy.orm import joinedload, subqueryload
from sqlalchemy.exc import IntegrityError 
import traceback 
# DÜZELTME: 'request' ve 'or_' eklendi
from flask import request
from sqlalchemy import or_

# Modellerin ve Formların tamamı
from app.models import Ekipman, Firma, Kiralama, KiralamaKalemi
from app.forms import EkipmanForm 

# -------------------------------------------------------------------------
# 1. Makine Parkı Listeleme Sayfası (NİHAİ GÜNCELLEME)
# (Arama + Sayfalama + Hızlı Durum Sorgulama)
# -------------------------------------------------------------------------
@filo_bp.route('/')
@filo_bp.route('/index')
def index():
    """
    SADECE BİZİM makinelerimizi ('firma_tedarikci_id' = None) listeler.
    Arama (Kod, Tipi, Seri No) ve Sayfalama destekler.
    HIZLI: 'N+1' sorgu sorunu çözüldü.
    """
    try:
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '', type=str)
        
        # 1. Temel sorgu: Sadece bizim makinelerimiz
        base_query = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.is_(None)
        ).options(
            # İlişkili kalemleri, kiralamaları ve müşterileri TEK SEFERDE YÜKLE
            subqueryload(Ekipman.kiralama_kalemleri).options(
                joinedload(KiralamaKalemi.kiralama).joinedload(Kiralama.firma_musteri)
            )
        )
        
        # 2. Arama sorgusu varsa filtrele
        if q:
            search_term = f'%{q}%'
            base_query = base_query.filter(
                or_(
                    Ekipman.kod.ilike(search_term),
                    Ekipman.tipi.ilike(search_term),
                    Ekipman.seri_no.ilike(search_term)
                )
            )
        
        # 3. Sayfalama yap
        pagination = base_query.order_by(Ekipman.kod).paginate(
            page=page, per_page=25, error_out=False
        )
        ekipmanlar = pagination.items
        
        # 4. (HIZLI) Aktif kiralama bilgisini N+1 sorgu OLMADAN bul
        for ekipman in ekipmanlar:
            ekipman.aktif_kiralama_bilgisi = None 
            if ekipman.calisma_durumu == 'kirada':
                # DB'ye sorma, zaten yüklenmiş olan 'kiralama_kalemleri' listesini kullan
                aktif_kalemler = [
                    k for k in ekipman.kiralama_kalemleri if not k.sonlandirildi
                ]
                if aktif_kalemler:
                    # En son (en yüksek ID'li) aktif kalemi bul
                    ekipman.aktif_kiralama_bilgisi = max(aktif_kalemler, key=lambda k: k.id)
    
    except Exception as e:
        flash(f"Ekipmanlar yüklenirken bir hata oluştu: {str(e)}", "danger")
        traceback.print_exc()
        ekipmanlar = []
        pagination = None
        q = q

    return render_template('filo/index.html', 
                           ekipmanlar=ekipmanlar, 
                           pagination=pagination, 
                           q=q)

# -------------------------------------------------------------------------
# 2. Yeni Makine Ekleme Sayfası (Düzeltilmiş)
# -------------------------------------------------------------------------
@filo_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    """
    Yeni Pimaks ekipmanı ekler. (Harici tedarikçi mantığı kaldırıldı).
    'giris_maliyeti' eklendi.
    """
    form = EkipmanForm()
    
    # Tedarikçi listesi mantığı kaldırıldı
    
    try:
        son_ekipman = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.is_(None)
        ).order_by(Ekipman.id.desc()).first()
        son_kod = son_ekipman.kod if son_ekipman else 'Henüz kayıt yok'
    except Exception:
        son_kod = 'Veritabanı hatası'

    if form.validate_on_submit():
        try:
            yeni_ekipman = Ekipman(
                kod=form.kod.data,
                yakit=form.yakit.data,
                tipi=form.tipi.data,
                marka=form.marka.data,
                seri_no=form.seri_no.data,
                calisma_yuksekligi=int(form.calisma_yuksekligi.data),
                kaldirma_kapasitesi=int(form.kaldirma_kapasitesi.data), 
                uretim_tarihi=form.uretim_tarihi.data,
                giris_maliyeti=str(form.giris_maliyeti.data or 0.0),
                firma_tedarikci_id=None, # Bu BİZİM makinemiz
                calisma_durumu='bosta'
            )
            
            db.session.add(yeni_ekipman)
            db.session.commit()
            flash('Yeni makine başarıyla filoya eklendi!', 'success')
            return redirect(url_for('filo.index'))
            
        except ValueError:
            flash("Hata: Yükseklik ve Kapasite alanları sayısal (tamsayı) olmalıdır.", "danger")
        except IntegrityError as e:
            db.session.rollback()
            if 'UNIQUE constraint failed: ekipman.kod' in str(e):
                flash(f"Hata: Bu makine kodu ({form.kod.data}) zaten kullanılıyor.", "danger")
            elif 'UNIQUE constraint failed: ekipman.seri_no' in str(e):
                 flash(f"Hata: Bu seri numarası ({form.seri_no.data}) zaten kullanılıyor.", "danger")
            else:
                flash(f"Veritabanı bütünlük hatası: {str(e)}", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Kaydederken beklenmedik bir hata oluştu: {str(e)}", "danger")
            traceback.print_exc()
    
    return render_template('filo/ekle.html', form=form, son_kod=son_kod)

# -------------------------------------------------------------------------
# 3. Makine Silme İşlemi
# -------------------------------------------------------------------------
@filo_bp.route('/sil/<int:id>', methods=['POST'])
def sil(id):
    ekipman = Ekipman.query.get_or_404(id)
    
    if ekipman.calisma_durumu == 'kirada':
        flash('Kirada olan bir ekipman silinemez! Önce kirayı sonlandırın.', 'danger')
        return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))
        
    try:
        db.session.delete(ekipman)
        db.session.commit()
        flash('Makine başarıyla silindi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ekipman silinirken bir hata oluştu: {str(e)}', 'danger')
        traceback.print_exc()
    
    return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))

# -------------------------------------------------------------------------
# 4. Makine Düzeltme Sayfası
# -------------------------------------------------------------------------
@filo_bp.route('/duzelt/<int:id>', methods=['GET', 'POST'])
def duzelt(id):
    ekipman = Ekipman.query.filter(
        Ekipman.id == id,
        Ekipman.firma_tedarikci_id.is_(None) 
    ).first_or_404()
    
    form = EkipmanForm(obj=ekipman)
    
    # Tedarikçi listesi mantığı kaldırıldı
    
    if form.validate_on_submit():
        try:
            ekipman.marka = form.marka.data
            ekipman.yakit = form.yakit.data
            ekipman.tipi = form.tipi.data
            ekipman.kod = form.kod.data
            ekipman.seri_no = form.seri_no.data
            ekipman.calisma_yuksekligi = int(form.calisma_yuksekligi.data)
            ekipman.kaldirma_kapasitesi = int(form.kaldirma_kapasitesi.data)
            ekipman.uretim_tarihi = form.uretim_tarihi.data
            ekipman.giris_maliyeti = str(form.giris_maliyeti.data or 0.0)
            
            if ekipman.calisma_durumu != 'kirada':
                ekipman.calisma_durumu = 'bosta'
            
            db.session.commit()
            flash('Makine bilgileri başarıyla güncellendi!', 'success')
            return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))
            
        except ValueError:
            flash("Hata: Yükseklik ve Kapasite alanları sayısal (tamsayı) olmalıdır.", "danger")
        except IntegrityError as e:
            # ... (IntegrityError kontrolleri) ...
            db.session.rollback()
            if 'UNIQUE constraint failed: ekipman.kod' in str(e):
                flash(f"Hata: Bu makine kodu ({form.kod.data}) zaten kullanılıyor.", "danger")
            elif 'UNIQUE constraint failed: ekipman.seri_no' in str(e):
                 flash(f"Hata: Bu seri numarası ({form.seri_no.data}) zaten kullanılıyor.", "danger")
            else:
                flash(f"Veritabanı bütünlük hatası: {str(e)}", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Güncellerken beklenmedik bir hata oluştu: {str(e)}", "danger")
            traceback.print_exc()
    
    elif request.method == 'GET':
        try:
            form.giris_maliyeti.data = Decimal(ekipman.giris_maliyeti or 0.0)
        except:
            form.giris_maliyeti.data = Decimal(0.0)

    return render_template('filo/duzelt.html', form=form, ekipman=ekipman)

# -------------------------------------------------------------------------
# 5. Makine Bilgi Sayfası (İleride Bakım Geçmişi burada olacak)
# -------------------------------------------------------------------------
@filo_bp.route('/bilgi/<int:id>', methods=['GET'])
def bilgi(id):
    ekipman = Ekipman.query.filter(
        Ekipman.id == id,
        Ekipman.firma_tedarikci_id.is_(None) 
    ).options(
        subqueryload(Ekipman.kiralama_kalemleri).options(
            joinedload(KiralamaKalemi.kiralama).joinedload(Kiralama.firma_musteri)
        )
    ).first_or_404()
    
    kalemler = sorted(ekipman.kiralama_kalemleri, key=lambda k: k.id, reverse=True)
    
    return render_template('filo/bilgi.html', ekipman=ekipman, kalemler=kalemler)

# -------------------------------------------------------------------------
# 6. KİRALAMA SONLANDIRMA (Modal için)
# -------------------------------------------------------------------------
@filo_bp.route('/sonlandir', methods=['POST'])
def sonlandir():
    """
    Formdan (Modal'dan) gelen 'ekipman_id' ve 'bitis_tarihi'ne göre
    o ekipmanın son aktif kalemini sonlandırır.
    """
    try:
        ekipman_id = request.form.get('ekipman_id', type=int)
        bitis_tarihi_str = request.form.get('bitis_tarihi') 

        if not (ekipman_id and bitis_tarihi_str):
            flash('Eksik bilgi! Ekipman ID veya Bitiş Tarihi gelmedi.', 'danger')
            return redirect(url_for('filo.index'))

        ekipman = Ekipman.query.get_or_404(ekipman_id)

        if ekipman.calisma_durumu == 'kirada':
            
            aktif_kalem = KiralamaKalemi.query.filter_by(
                ekipman_id=ekipman.id,
                sonlandirildi=False
            ).order_by(KiralamaKalemi.id.desc()).first()
            
            if aktif_kalem:
                # Sunucu Tarafı Tarih Kontrolü
                try:
                    baslangic_dt = datetime.strptime(aktif_kalem.kiralama_baslangıcı, "%Y-%m-%d").date()
                    bitis_dt = datetime.strptime(bitis_tarihi_str, "%Y-%m-%d").date()
                    
                    if bitis_dt < baslangic_dt:
                        flash(f"Hata: Bitiş tarihi ({bitis_tarihi_str}), başlangıç tarihinden ({aktif_kalem.kiralama_baslangıcı}) önce olamaz!", 'danger')
                        return redirect(url_for('filo.index'))
                except ValueError:
                    flash("Tarih formatı geçersiz.", 'danger')
                    return redirect(url_for('filo.index'))

                aktif_kalem.kiralama_bitis = bitis_tarihi_str
                ekipman.calisma_durumu = 'bosta' # Sadece bizim makineler
                aktif_kalem.sonlandirildi = True 
                
                db.session.commit()
                flash(f"{ekipman.kod} kodlu ekipman kiralaması başarıyla sonlandırıldı.", 'success')
            else:
                ekipman.calisma_durumu = 'bosta'
                db.session.commit()
                flash(f"{ekipman.kod} 'kirada' görünüyordu ama aktif kiralama kalemi bulunamadı! Ekipman 'boşa' alındı.", 'warning')
        else:
            flash(f"{ekipman.kod} kodlu ekipman zaten 'Boşta'.", 'info')
    
    except Exception as e:
        db.session.rollback()
        flash(f"Kiralama sonlandırılırken bir hata oluştu: {str(e)}", 'danger')
        traceback.print_exc()
        
    return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))

# -------------------------------------------------------------------------
# 7. YENİ ROTA: Harici Ekipman Listeleme
# -------------------------------------------------------------------------
@filo_bp.route('/harici')
def harici():
    """
    Sadece 'harici' (tedarikçilere ait) ekipmanları listeler.
    (Bu sayfa da 'Arama' ve 'Sayfalama'ya ihtiyaç duyar, ileride eklenebilir)
    """
    try:
        ekipmanlar = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.isnot(None) 
        ).options(
            joinedload(Ekipman.firma_tedarikci) 
        ).order_by(Ekipman.kod).all()
        
    except Exception as e:
        flash(f"Harici ekipmanlar yüklenirken bir hata oluştu: {str(e)}", "danger")
        traceback.print_exc()
        ekipmanlar = []

    return render_template('filo/harici.html', ekipmanlar=ekipmanlar)