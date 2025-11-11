from app.firmalar import firmalar_bp
from app import db
from flask import render_template, url_for, redirect, flash
from sqlalchemy.exc import IntegrityError
import traceback

# --- GÜNCELLENEN IMPORTLAR ---
# 'Musteri' silindi, 'Firma' geldi. 'Ekipman' bu dosyada kullanılmıyor.
# Gelecekteki Cari Hesap sayfası için diğer modelleri de ekliyoruz.
from app.models import Firma, Kiralama, Ekipman, Odeme, HizmetKaydi, KiralamaKalemi
# 'EkipmanForm' bu dosyada kullanılmıyor.
from app.forms import FirmaForm
# Gelecekteki 'bilgi' sayfası için 'eager loading' importları
from sqlalchemy.orm import joinedload, subqueryload
# --- GÜNCELLENEN IMPORTLAR SONU ---

# -------------------------------------------------------------------------
# 1. Firma Listeleme Sayfası (GÜNCELLENDİ)
# -------------------------------------------------------------------------
@firmalar_bp.route('/')
@firmalar_bp.route('/index')
def index():
    """
    Tüm firmaları (müşteriler VE tedarikçiler) listeler.
    """
    try:
        # 'Musteri.query.all()' -> 'Firma.query.all()'
        firmalar = Firma.query.order_by(Firma.firma_adi).all()
        return render_template('firmalar/index.html', firmalar=firmalar)
    except Exception as e:
        flash(f"Firmalar yüklenirken bir hata oluştu: {str(e)}", "danger")
        traceback.print_exc()
        return render_template('firmalar/index.html', firmalar=[])

# -------------------------------------------------------------------------
# 2. Yeni Firma Ekleme Sayfası (GÜNCELLENDİ)
# -------------------------------------------------------------------------
@firmalar_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    """
    Yeni firma ekler (Roller dahil: Müşteri ve/veya Tedarikçi).
    """
    form = FirmaForm()
    
    if form.validate_on_submit():
        try:
            # 'Musteri(...)' -> 'Firma(...)'
            yeni_firma = Firma(
                firma_adi=form.firma_adi.data,
                yetkili_adi=form.yetkili_adi.data,
                iletisim_bilgileri=form.iletisim_bilgileri.data,
                vergi_dairesi=form.vergi_dairesi.data,
                vergi_no=form.vergi_no.data,
                
                # --- YENİ ROL ALANLARI EKLENDİ ---
                is_musteri=form.is_musteri.data,
                is_tedarikci=form.is_tedarikci.data
                # --- YENİ ROL ALANLARI SONU ---
            )
        
            db.session.add(yeni_firma)
            db.session.commit()
        
            flash('Yeni firma başarıyla eklendi!', 'success')
            return redirect(url_for('firmalar.index'))
            
        except IntegrityError as e:
            db.session.rollback() 
            # Tablo adını 'firma' olarak güncelledik
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
# 3. Firma Silme İşlemi (GÜVENLİK KONTROLLÜ EKLENDİ)
# -------------------------------------------------------------------------
@firmalar_bp.route('/sil/<int:id>', methods=['POST'])
def sil(id):
    """
    ID'si verilen firmayı siler.
    YENİ: Sadece hiçbir finansal kaydı yoksa siler.
    """
    firma = Firma.query.options(
        joinedload(Firma.kiralamalar),
        joinedload(Firma.odemeler),
        joinedload(Firma.hizmet_kayitlari),
        joinedload(Firma.tedarik_edilen_ekipmanlar),
        joinedload(Firma.saglanan_nakliye_hizmetleri)
    ).get_or_404(id)
    
    # --- YENİ GÜVENLİK KONTROLÜ ---
    # Bu firmanın ilişkili kayıtları varsa silmeyi engelle.
    if (firma.kiralamalar or 
        firma.odemeler or 
        firma.hizmet_kayitlari or 
        firma.tedarik_edilen_ekipmanlar or 
        firma.saglanan_nakliye_hizmetleri):
        
        flash(f"HATA: '{firma.firma_adi}' SİLİNEMEZ!", 'danger')
        flash("Bu firmanın ilişkili kiralama, ödeme, hizmet veya ekipman kayıtları bulunmaktadır.", 'warning')
        return redirect(url_for('firmalar.index'))
    # --- GÜVENLİK KONTROLÜ SONU ---
    
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
# 4. Firma Düzenleme Sayfası (GÜNCELLENDİ)
# -------------------------------------------------------------------------
@firmalar_bp.route('/duzelt/<int:id>', methods=['GET', 'POST'])
def duzelt(id):
    """
    Mevcut firmayı (roller dahil) düzenler.
    """
    # 'Musteri' -> 'Firma'
    firma = Firma.query.get_or_404(id)
    form = FirmaForm(obj=firma)
    
    if form.validate_on_submit():
        try:
            firma.firma_adi = form.firma_adi.data
            firma.yetkili_adi = form.yetkili_adi.data
            firma.iletisim_bilgileri = form.iletisim_bilgileri.data
            firma.vergi_dairesi = form.vergi_dairesi.data
            firma.vergi_no = form.vergi_no.data
            
            # --- YENİ ROL ALANLARI EKLENDİ ---
            firma.is_musteri = form.is_musteri.data
            firma.is_tedarikci = form.is_tedarikci.data
            # --- YENİ ROL ALANLARI SONU ---
            
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
    
    # 'musteri=musteri' -> 'firma=firma'
    return render_template('firmalar/duzelt.html', form=form, firma=firma) 

# -------------------------------------------------------------------------
# 5. Firma Bilgi Sayfası (CARİ HESAP İÇİN GÜNCELLENDİ)
# -------------------------------------------------------------------------
@firmalar_bp.route('/bilgi/<int:id>', methods=['GET'])
def bilgi(id):
    """
    ID'si verilen firmanın detaylı bilgilerini gösterir.
    (Gelecekteki 'Cari Hesap Ekstresi' için tüm verileri yükler)
    """
    try:
        # --- YENİ, GÜÇLÜ SORGU ---
        # Cari Hesap Ekstresi için GEREKLİ TÜM verileri tek seferde yükle
        firma = Firma.query.options(
            # Müşteri olduğu kiralamalar
            subqueryload(Firma.kiralamalar).options(
                subqueryload(Kiralama.kalemler).options(
                    joinedload(KiralamaKalemi.ekipman)
                )
            ),
            # Yaptığı ödemeler
            subqueryload(Firma.odemeler),
            # Bağımsız hizmet hareketleri (borç/alacak)
            subqueryload(Firma.hizmet_kayitlari),
            # Tedarikçi olduğu ekipmanlar
            subqueryload(Firma.tedarik_edilen_ekipmanlar),
            # Nakliye tedarikçisi olduğu kalemler
            subqueryload(Firma.saglanan_nakliye_hizmetleri)
        ).get_or_404(id)
        # --- SORGU SONU ---
        
        # (İleride buraya Cari Bakiye hesaplama mantığı eklenecek)
        
        return render_template('firmalar/bilgi.html', firma=firma)
        
    except Exception as e:
        flash(f"Firma bilgileri yüklenirken bir hata oluştu: {str(e)}", "danger")
        traceback.print_exc()
        return redirect(url_for('firmalar.index'))