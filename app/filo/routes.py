from app.filo import filo_bp
from app import db 
from decimal import Decimal, InvalidOperation 
from flask import render_template, redirect, url_for, flash, request, jsonify
from datetime import datetime, date 
from sqlalchemy.orm import joinedload, subqueryload
from sqlalchemy.exc import IntegrityError 
import traceback 
from sqlalchemy import or_

from app.models import Ekipman, Firma, Kiralama, KiralamaKalemi
from app.forms import EkipmanForm 
import locale
locale.setlocale(locale.LC_ALL, 'tr_TR.UTF-8')  # Türk Lirası formatı

# -------------------------------------------------------------------------
# 1. Makine Parkı Listeleme Sayfası
# -------------------------------------------------------------------------
@filo_bp.route('/')
@filo_bp.route('/index')
def index():
    try:
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '', type=str)
        
        base_query = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.is_(None)
        ).options(
            subqueryload(Ekipman.kiralama_kalemleri).options(
                joinedload(KiralamaKalemi.kiralama).joinedload(Kiralama.firma_musteri)
            )
        )
        
        if q:
            search_term = f'%{q}%'
            base_query = base_query.filter(
                or_(
                    Ekipman.kod.ilike(search_term),
                    Ekipman.tipi.ilike(search_term),
                    Ekipman.seri_no.ilike(search_term)
                )
            )
        
        pagination = base_query.order_by(Ekipman.kod).paginate(
            page=page, per_page=25, error_out=False
        )
        ekipmanlar = pagination.items
        
        for ekipman in ekipmanlar:
            ekipman.aktif_kiralama_bilgisi = None 
            if ekipman.calisma_durumu == 'kirada':
                aktif_kalemler = [
                    k for k in ekipman.kiralama_kalemleri if not k.sonlandirildi
                ]
                if aktif_kalemler:
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
# 2. Yeni Makine Ekleme Sayfası
# -------------------------------------------------------------------------
@filo_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    form = EkipmanForm()
    
    try:
        son_ekipman = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.is_(None)
        ).order_by(Ekipman.kod.desc()).first()
        son_kod = son_ekipman.kod if son_ekipman else 'Henüz kayıt yok'
    except Exception as e:
        print(f"Son kod hatası: {e}")
        son_kod = 'Veritabanı hatası'

    if form.validate_on_submit():
        try:
            yeni_ekipman = Ekipman(
                kod=form.kod.data,
                yakit=form.yakit.data,
                tipi=form.tipi.data,
                marka=form.marka.data,
                model=form.model.data,
                seri_no=form.seri_no.data,
                calisma_yuksekligi=int(form.calisma_yuksekligi.data),
                kaldirma_kapasitesi=int(form.kaldirma_kapasitesi.data), 
                uretim_tarihi=form.uretim_tarihi.data,
                giris_maliyeti=str(form.giris_maliyeti.data or 0.0),
                firma_tedarikci_id=None,
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
# 4. Makine Düzeltme Sayfası (MALİYET DÖNÜŞTÜRME DÜZELTİLDİ)
# -------------------------------------------------------------------------
@filo_bp.route('/duzelt/<int:id>', methods=['GET', 'POST'])
def duzelt(id):
    ekipman = Ekipman.query.filter(
        Ekipman.id == id,
        Ekipman.firma_tedarikci_id.is_(None) 
    ).first_or_404()
    
    form = EkipmanForm(obj=ekipman)
    
    # --- GET İsteği (Sayfa Yükleme) ---
    if request.method == 'GET':
        # Maliyet verisini String'den Decimal'e güvenli şekilde çevir
        if request.method == 'GET':
            try:
                maliyet_str = ekipman.giris_maliyeti or "0.0"
                maliyet_clean = maliyet_str.replace('.', '').replace(',', '.')
                maliyet_decimal = Decimal(maliyet_clean)
                form.giris_maliyeti.data = maliyet_decimal
                # Kullanıcıya gösterilecek format
                form.giris_maliyeti.data = float(maliyet_decimal)
            except (ValueError, InvalidOperation) as e:
                form.giris_maliyeti.data = Decimal(0.0)
    # --- POST İsteği (Kaydetme) ---
    if form.validate_on_submit():
        try:
            ekipman.marka = form.marka.data
            ekipman.model = form.model.data 
            ekipman.yakit = form.yakit.data
            ekipman.tipi = form.tipi.data
            ekipman.kod = form.kod.data
            ekipman.seri_no = form.seri_no.data
            ekipman.calisma_yuksekligi = int(form.calisma_yuksekligi.data)
            ekipman.kaldirma_kapasitesi = int(form.kaldirma_kapasitesi.data)
            ekipman.uretim_tarihi = form.uretim_tarihi.data
            
            # Maliyet Güncelleme
            ekipman.giris_maliyeti = str(form.giris_maliyeti.data or 0.0)
            
            if ekipman.calisma_durumu != 'kirada':
                ekipman.calisma_durumu = 'bosta'
            
            db.session.commit()
            flash('Makine bilgileri başarıyla güncellendi!', 'success')
            return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))
            
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
            flash(f"Güncellerken beklenmedik bir hata oluştu: {str(e)}", "danger")
            traceback.print_exc()

    return render_template('filo/duzelt.html', form=form, ekipman=ekipman)

# ... (bilgi, sonlandir, harici fonksiyonları aynı kalır) ...
@filo_bp.route('/bilgi/<int:id>', methods=['GET'])
def bilgi(id):
    ekipman = Ekipman.query.filter(Ekipman.id == id, Ekipman.firma_tedarikci_id.is_(None)).options(subqueryload(Ekipman.kiralama_kalemleri).options(joinedload(KiralamaKalemi.kiralama).joinedload(Kiralama.firma_musteri))).first_or_404()
    kalemler = sorted(ekipman.kiralama_kalemleri, key=lambda k: k.id, reverse=True)
    return render_template('filo/bilgi.html', ekipman=ekipman, kalemler=kalemler)

@filo_bp.route('/sonlandir', methods=['POST'])
def sonlandir():
    try:
        ekipman_id = request.form.get('ekipman_id', type=int)
        bitis_tarihi_str = request.form.get('bitis_tarihi') 
        if not (ekipman_id and bitis_tarihi_str):
            flash('Eksik bilgi!', 'danger')
            return redirect(url_for('filo.index'))
        ekipman = Ekipman.query.get_or_404(ekipman_id)
        if ekipman.firma_tedarikci_id is not None:
             flash(f"Hata: Harici bir makinedir.", 'danger')
             return redirect(url_for('filo.index'))
        if ekipman.calisma_durumu == 'kirada':
            aktif_kalem = KiralamaKalemi.query.filter_by(ekipman_id=ekipman.id, sonlandirildi=False).order_by(KiralamaKalemi.id.desc()).first()
            if aktif_kalem:
                try:
                    baslangic_dt = datetime.strptime(aktif_kalem.kiralama_baslangıcı, "%Y-%m-%d").date()
                    bitis_dt = datetime.strptime(bitis_tarihi_str, "%Y-%m-%d").date()
                    if bitis_dt < baslangic_dt:
                        flash(f"Hata: Bitiş tarihi başlangıçtan önce olamaz!", 'danger')
                        return redirect(url_for('filo.index'))
                except ValueError:
                    flash("Tarih formatı geçersiz.", 'danger')
                    return redirect(url_for('filo.index'))
                aktif_kalem.kiralama_bitis = bitis_tarihi_str
                ekipman.calisma_durumu = 'bosta'
                aktif_kalem.sonlandirildi = True 
                db.session.commit()
                flash(f"Kiralama sonlandırıldı.", 'success')
            else:
                ekipman.calisma_durumu = 'bosta'
                db.session.commit()
                flash(f"Kiralama kalemi bulunamadı, durum 'boşta' yapıldı.", 'warning')
        else:
            flash(f"Makine zaten kirada değil.", 'info')
    except Exception as e:
        db.session.rollback()
        flash(f"Hata: {str(e)}", 'danger')
        traceback.print_exc()
    return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))

@filo_bp.route('/harici')
def harici():
    try:
        ekipmanlar = Ekipman.query.filter(Ekipman.firma_tedarikci_id.isnot(None)).options(joinedload(Ekipman.firma_tedarikci)).order_by(Ekipman.kod).all()
    except Exception as e:
        flash(f"Hata: {str(e)}", "danger")
        ekipmanlar = []
    return render_template('filo/harici.html', ekipmanlar=ekipmanlar)
