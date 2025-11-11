from app.filo import filo_bp
from app import db 
from decimal import Decimal # Decimal dönüşümleri için eklendi

# --- GÜNCELLENEN IMPORTLAR ---
# 'Musteri' silindi, yerine 'Firma' geldi.
from app.models import Ekipman, Firma, Kiralama, KiralamaKalemi
# --- GÜNCELLENEN IMPORTLAR SONU ---

from app.forms import EkipmanForm 
from flask import render_template, redirect, url_for, flash, request, jsonify
from datetime import datetime
from sqlalchemy.orm import joinedload, subqueryload
from sqlalchemy.exc import IntegrityError # Hata yakalama için eklendi
import traceback # Hata ayıklama için

# -------------------------------------------------------------------------
# 1. Makine Parkı Listeleme Sayfası (NİHAİ GÜNCELLEME)
# -------------------------------------------------------------------------
@filo_bp.route('/')
@filo_bp.route('/index')
def index():
    """
    Tüm makine parkını listeler.
    YENİ: Artık SADECE BİZİM makinelerimizi ('firma_tedarikci_id' = None) listeler.
    """
    try:
        # --- GÜNCELLENEN SORGU ---
        # Sadece Pimaks'a ait ekipmanları (tedarikçisi olmayan) listele
        ekipmanlar = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.is_(None)
        ).options(
            subqueryload(Ekipman.kiralama_kalemleri).options(
                # 'Kiralama.musteri' -> 'Kiralama.firma_musteri' olarak GÜNCELLENDİ
                joinedload(KiralamaKalemi.kiralama).joinedload(Kiralama.firma_musteri)
            )
        ).order_by(Ekipman.kod).all()
        # --- GÜNCELLENEN SORGU SONU ---
        
        # Kirada olan ekipmanların bilgilerini bul (Bu mantık aynı kaldı)
        for ekipman in ekipmanlar:
            ekipman.aktif_kiralama_bilgisi = None 
            if ekipman.calisma_durumu == 'kirada':
                # Ekipmana ait 'sonlandırılmamış' aktif kalemi bul
                aktif_kalem = KiralamaKalemi.query.filter(
                    KiralamaKalemi.ekipman_id == ekipman.id,
                    KiralamaKalemi.sonlandirildi == False
                ).order_by(KiralamaKalemi.id.desc()).first()
                
                if aktif_kalem:
                    ekipman.aktif_kiralama_bilgisi = aktif_kalem
    
    except Exception as e:
        flash(f"Ekipmanlar yüklenirken bir hata oluştu: {str(e)}", "danger")
        traceback.print_exc()
        ekipmanlar = []

    return render_template('filo/index.html', ekipmanlar=ekipmanlar)

# -------------------------------------------------------------------------
# 2. Yeni Makine Ekleme Sayfası (NİHAİ GÜNCELLEME)
# -------------------------------------------------------------------------
@filo_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    """
    Yeni ekipman (bizim VEYA harici) ekler.
    'forms.py' dosyasındaki yeni alanları (maliyet, tedarikçi) destekler.
    """
    form = EkipmanForm()
    
    # --- YENİ EKLENDİ (Tedarikçi Listesi) ---
    # Tedarikçi seçme alanını (SelectField) doldur
    try:
        tedarikciler = Firma.query.filter_by(is_tedarikci=True).order_by(Firma.firma_adi).all()
        # 'coerce=int' kullandığımız için ID'ler sayı olmalı. '0' "Bizim Makinemiz" demektir.
        tedarikci_choices = [(f.id, f.firma_adi) for f in tedarikciler]
        tedarikci_choices.insert(0, (0, '--- Bu Bizim Makinemiz (Tedarikçi Yok) ---'))
        form.firma_tedarikci_id.choices = tedarikci_choices
    except Exception as e:
        flash(f"Tedarikçi listesi yüklenemedi: {e}", "danger")
        form.firma_tedarikci_id.choices = [(0, 'Hata: Tedarikçiler yüklenemedi')]
    # --- YENİ EKLENDİ SONU ---

    try:
        # Not: Bu sorgu artık harici makineleri de getirebilir.
        # Belki 'firma_tedarikci_id.is_(None)' filtresi eklemek iyi olabilir.
        son_ekipman = Ekipman.query.order_by(Ekipman.id.desc()).first()
        son_kod = son_ekipman.kod if son_ekipman else 'Henüz kayıt yok'
    except Exception:
        son_kod = 'Veritabanı hatası'

    if form.validate_on_submit():
        try:
            # --- YENİ EKLENDİ (Tedarikçi ID ve Durum Kontrolü) ---
            tedarikci_id_data = form.firma_tedarikci_id.data
            tedarikci_id = tedarikci_id_data if tedarikci_id_data != 0 else None

            # Eğer tedarikçi seçilmişse, bu 'harici' bir makinedir.
            # Eğer seçilmemişse (None), bu 'bosta' (bizim) makinemizdir.
            yeni_durum = 'harici' if tedarikci_id else 'bosta'
            # --- YENİ KONTROL SONU ---

            yeni_ekipman = Ekipman(
                kod=form.kod.data,
                yakit=form.yakit.data,
                tipi=form.tipi.data,
                marka=form.marka.data,
                seri_no=form.seri_no.data,
                calisma_yuksekligi=int(form.calisma_yuksekligi.data),
                kaldirma_kapasitesi=int(form.kaldirma_kapasitesi.data), 
                uretim_tarihi=form.uretim_tarihi.data,
                
                # --- YENİ EKLENEN ALANLAR (DB'YE KAYIT) ---
                giris_maliyeti=str(form.giris_maliyeti.data or 0.0),
                firma_tedarikci_id=tedarikci_id,
                calisma_durumu=yeni_durum
                # --- YENİ ALANLAR SONU ---
            )
            
            db.session.add(yeni_ekipman)
            db.session.commit()
            flash('Yeni makine başarıyla eklendi!', 'success')
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
# 3. Makine Silme İşlemi (GÜNCELLEME)
# -------------------------------------------------------------------------
@filo_bp.route('/sil/<int:id>', methods=['POST'])
def sil(id):
    ekipman = Ekipman.query.get_or_404(id)
    
    if ekipman.calisma_durumu == 'kirada':
        flash('Kirada olan bir ekipman silinemez! Önce kirayı sonlandırın.', 'danger')
        return redirect(url_for('filo.index'))
        
    # YENİ KONTROL: Harici bir makine silinirse, kiralama kalemlerini kontrol et?
    # Şimdilik, 'kirada' olmadığı sürece silinmesine izin veriyoruz.
    # 'harici' makineler de silinebilir.

    try:
        db.session.delete(ekipman)
        db.session.commit()
        flash('Makine başarıyla silindi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ekipman silinirken bir hata oluştu: {str(e)}', 'danger')
        traceback.print_exc()
    
    return redirect(url_for('filo.index'))

# -------------------------------------------------------------------------
# 4. Makine Düzeltme Sayfası (NİHAİ GÜNCELLEME)
# -------------------------------------------------------------------------
@filo_bp.route('/duzelt/<int:id>', methods=['GET', 'POST'])
def duzelt(id):
    ekipman = Ekipman.query.get_or_404(id)
    form = EkipmanForm(obj=ekipman)
    
    # --- YENİ EKLENDİ (Tedarikçi Listesi) ---
    # Tedarikçi seçme alanını (SelectField) doldur (ekle() fonksiyonundaki gibi)
    try:
        tedarikciler = Firma.query.filter_by(is_tedarikci=True).order_by(Firma.firma_adi).all()
        tedarikci_choices = [(f.id, f.firma_adi) for f in tedarikciler]
        tedarikci_choices.insert(0, (0, '--- Bu Bizim Makinemiz (Tedarikçi Yok) ---'))
        form.firma_tedarikci_id.choices = tedarikci_choices
    except Exception as e:
        flash(f"Tedarikçi listesi yüklenemedi: {e}", "danger")
        form.firma_tedarikci_id.choices = [(0, 'Hata: Tedarikçiler yüklenemedi')]
    # --- YENİ EKLENDİ SONU ---

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
            
            # --- YENİ EKLENEN ALANLAR (DB'YE KAYIT) ---
            tedarikci_id_data = form.firma_tedarikci_id.data
            tedarikci_id = tedarikci_id_data if tedarikci_id_data != 0 else None
            
            ekipman.giris_maliyeti = str(form.giris_maliyeti.data or 0.0)
            ekipman.firma_tedarikci_id = tedarikci_id
            
            # 'kirada' olan bir makinenin durumunu 'bosta' veya 'harici' yapmamalıyız.
            if ekipman.calisma_durumu != 'kirada':
                ekipman.calisma_durumu = 'harici' if tedarikci_id else 'bosta'
            # --- YENİ ALANLAR SONU ---
            
            db.session.commit()
            flash('Makine bilgileri başarıyla güncellendi!', 'success')
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
            flash(f"Güncellerken beklenmedik bir hata oluştu: {str(e)}", "danger")
            traceback.print_exc()
    
    elif request.method == 'GET':
        # --- YENİ EKLENDİ (GET İsteği Düzeltmesi) ---
        # Formu 'obj=ekipman' ile doldurduktan sonra,
        # DB'deki 'None' olan tedarikçi ID'sini, formdaki '0' default değeriyle eşle.
        form.firma_tedarikci_id.data = ekipman.firma_tedarikci_id or 0
        # DB'deki 'String' maliyeti, formdaki 'Decimal' alana çevir.
        try:
            form.giris_maliyeti.data = Decimal(ekipman.giris_maliyeti or 0.0)
        except:
            form.giris_maliyeti.data = Decimal(0.0)
        # --- YENİ EKLENDİ SONU ---

    return render_template('filo/duzelt.html', form=form, ekipman=ekipman)

# -------------------------------------------------------------------------
# 5. Makine Bilgi Sayfası (GÜNCELLEME)
# -------------------------------------------------------------------------
@filo_bp.route('/bilgi/<int:id>', methods=['GET'])
def bilgi(id):
    ekipman = Ekipman.query.options(
        subqueryload(Ekipman.kiralama_kalemleri).options(
            # 'Kiralama.musteri' -> 'Kiralama.firma_musteri' olarak GÜNCELLENDİ
            joinedload(KiralamaKalemi.kiralama).joinedload(Kiralama.firma_musteri)
        )
    ).get_or_404(id)
    
    # Kalemleri tarihe göre sıralayalım (en yeni en üstte)
    kalemler = sorted(ekipman.kiralama_kalemleri, key=lambda k: k.id, reverse=True)
    
    return render_template('filo/bilgi.html', ekipman=ekipman, kalemler=kalemler)

# -------------------------------------------------------------------------
# 6. KİRALAMA SONLANDIRMA (NİHAİ GÜNCELLEME)
# -------------------------------------------------------------------------
@filo_bp.route('/sonlandir', methods=['POST'])
def sonlandir():
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
                try:
                    baslangic_dt = datetime.strptime(aktif_kalem.kiralama_baslangıcı, "%Y-%m-%d").date()
                    bitis_dt = datetime.strptime(bitis_tarihi_str, "%Y-%m-%d").date()
                    
                    if bitis_dt < baslangic_dt:
                        flash(f"Hata: Bitiş tarihi ({bitis_tarihi_str}), başlangıç tarihinden ({aktif_kalem.kiralama_baslangıcı}) önce olamaz!", 'danger')
                        return redirect(url_for('filo.index'))
                except ValueError:
                    flash("Tarih formatı geçersiz.", 'danger')
                    return redirect(url_for('filo.index'))

                # --- ASIL İŞLEM BURADA (NİHAİ GÜNCELLEME) ---
                
                # 1. Bitiş tarihini ayarla
                aktif_kalem.kiralama_bitis = bitis_tarihi_str
                
                # 2. YENİ DURUM KONTROLÜ
                # 'harici' bir makine (tedarikçisi olan) asla 'bosta' olamaz.
                # 'kirada' değilse 'harici' durumuna geri döner.
                yeni_durum = 'harici' if ekipman.firma_tedarikci_id else 'bosta'
                ekipman.calisma_durumu = yeni_durum
                
                # 3. Kalemi kilitle
                aktif_kalem.sonlandirildi = True 
                
                db.session.commit()
                flash(f"{ekipman.kod} kodlu ekipman kiralaması başarıyla sonlandırıldı. Durumu: '{yeni_durum}'", 'success')
            else:
                # Veri tutarsızlığı: 'kirada' ama 'sonlandırılmamış' kalem yok.
                yeni_durum = 'harici' if ekipman.firma_tedarikci_id else 'bosta'
                ekipman.calisma_durumu = yeni_durum
                db.session.commit()
                flash(f"{ekipman.kod} 'kirada' görünüyordu ama aktif kiralama kalemi bulunamadı! Ekipman '{yeni_durum}' durumuna alındı.", 'warning')
        else:
            flash(f"{ekipman.kod} kodlu ekipman zaten 'kirada' değil (Durumu: {ekipman.calisma_durumu}).", 'info')
    
    except Exception as e:
        db.session.rollback()
        flash(f"Kiralama sonlandırılırken bir hata oluştu: {str(e)}", 'danger')
        traceback.print_exc()
        
    return redirect(url_for('filo.index'))

# -------------------------------------------------------------------------
# 7. YENİ ROTA: Harici Ekipman Listeleme
# -------------------------------------------------------------------------
@filo_bp.route('/harici')
def harici():
    """
    Sadece 'harici' (tedarikçilere ait) ekipmanları listeler.
    Bu, 'index' rotasının tam tersidir.
    """
    try:
        ekipmanlar = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.isnot(None) # Sadece tedarikçisi olanlar
        ).options(
            joinedload(Ekipman.firma_tedarikci) # Tedarikçi bilgisini yükle
        ).order_by(Ekipman.kod).all()
        
    except Exception as e:
        flash(f"Harici ekipmanlar yüklenirken bir hata oluştu: {str(e)}", "danger")
        traceback.print_exc()
        ekipmanlar = []

    # Bu rota için yeni bir HTML şablonu oluşturmanız gerekecek:
    return render_template('filo/harici.html', ekipmanlar=ekipmanlar)