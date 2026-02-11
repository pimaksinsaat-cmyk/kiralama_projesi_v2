from app.filo import filo_bp
from app import db 
from decimal import Decimal, InvalidOperation 
from flask import render_template, redirect, url_for, flash, request, jsonify
from sqlalchemy.orm import joinedload, subqueryload
from sqlalchemy.exc import IntegrityError 
import traceback 
from sqlalchemy import or_, and_




# Firmalar (Kendi klasörü)
from app.firmalar.models import Firma

# Kiralama Klasöründen Gelenler
from app.kiralama.models import Kiralama, KiralamaKalemi

# Filo Klasöründen Gelenler
from app.filo.models import Ekipman, BakimKaydi, KullanilanParca, StokKarti, StokHareket

# Cari Klasöründen Gelenler
from app.cari.models import Kasa, Odeme, HizmetKaydi


from app.filo.forms import EkipmanForm 
import locale

# Türkçe yerel ayarlarını dene
try:
    locale.setlocale(locale.LC_ALL, 'tr_TR.UTF-8')
except:
    pass

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYON: Para Birimi Temizleme
# -------------------------------------------------------------------------
def clean_currency_input(value_str):
    if not value_str: return '0.0'
    val = str(value_str).strip()
    if ',' in val:
        val = val.replace('.', '').replace(',', '.')
    return val

# -------------------------------------------------------------------------
# 1. Makine Parkı Listeleme (Sadece Aktifler)
# -------------------------------------------------------------------------
@filo_bp.route('/')
@filo_bp.route('/index')
def index():
    try:
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '', type=str)
        
        # SADECE AKTİF VE BİZİM OLANLAR
        base_query = Ekipman.query.filter(
            and_(
                Ekipman.firma_tedarikci_id.is_(None),
                Ekipman.is_active == True 
            )
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
                aktif_kalemler = [k for k in ekipman.kiralama_kalemleri if not k.sonlandirildi]
                if aktif_kalemler:
                    ekipman.aktif_kiralama_bilgisi = max(aktif_kalemler, key=lambda k: k.id)
    
    except Exception as e:
        flash(f"Hata: {str(e)}", "danger")
        ekipmanlar = []
        pagination = None
        q = q

    return render_template('filo/index.html', ekipmanlar=ekipmanlar, pagination=pagination, q=q)


# -------------------------------------------------------------------------
# 2. Yeni Makine Ekleme (KOD VE SERİ NO KONTROLÜ)
# -------------------------------------------------------------------------
@filo_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    form = EkipmanForm()
    
    try:
        son_ekipman = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.is_(None)
        ).order_by(Ekipman.kod.desc()).first()
        son_kod = son_ekipman.kod if son_ekipman else 'Henüz kayıt yok'
    except:
        son_kod = '...'

    if form.validate_on_submit():
        try:
            # --- KONTROL 1: BU KOD DAHA ÖNCE VAR MI? ---
            mevcut_makine = Ekipman.query.filter_by(kod=form.kod.data).first()
            if mevcut_makine:
                if mevcut_makine.is_active:
                    flash(f"HATA: '{form.kod.data}' kodlu makine zaten listenizde mevcut.", "danger")
                    return render_template('filo/ekle.html', form=form, son_kod=son_kod)
                else:
                    flash(f"UYARI: '{form.kod.data}' kodlu bir makine ARŞİVDE (Pasif Durumda) mevcut!", "warning")
                    flash(f"Lütfen 'Pasif Makineler' sayfasına giderek bu makineyi geri yükleyiniz.", "info")
                    return render_template('filo/ekle.html', form=form, son_kod=son_kod)
            
            # --- KONTROL 2: BU SERİ NO DAHA ÖNCE VAR MI? (YENİ EKLENDİ) ---
            # Sadece Pimaks envanterindeki (tedarikçi=None) seri numaralarını kontrol etmeliyiz.
            mevcut_seri = Ekipman.query.filter_by(
                seri_no=form.seri_no.data, 
                firma_tedarikci_id=None 
            ).first()

            if mevcut_seri:
                if mevcut_seri.is_active:
                    flash(f"HATA: '{form.seri_no.data}' seri numaralı bir makine zaten mevcut (Kod: {mevcut_seri.kod}).", "danger")
                    return render_template('filo/ekle.html', form=form, son_kod=son_kod)
                else:
                    flash(f"UYARI: '{form.seri_no.data}' seri numaralı makine ARŞİVDE mevcut (Kod: {mevcut_seri.kod})!", "warning")
                    flash(f"Lütfen 'Pasif Makineler' sayfasına giderek bu makineyi geri yükleyiniz.", "info")
                    return render_template('filo/ekle.html', form=form, son_kod=son_kod)
            # --------------------------------------------------------------

            maliyet_raw = form.giris_maliyeti.data
            maliyet_db = clean_currency_input(maliyet_raw)

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
                giris_maliyeti=maliyet_db,
                para_birimi=form.para_birimi.data,
                firma_tedarikci_id=None,
                calisma_durumu='bosta',
                is_active=True
            )
            
            db.session.add(yeni_ekipman)
            db.session.commit()
            flash('Yeni makine eklendi!', 'success')
            return redirect(url_for('filo.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Kayıt hatası: {str(e)}", "danger")
            traceback.print_exc()
    
    return render_template('filo/ekle.html', form=form, son_kod=son_kod)

# ... (sil, duzelt, bilgi, sonlandir fonksiyonları AYNI KALIR) ...
# Lütfen dosyanızdaki diğer fonksiyonları koruyun, yer kaplamaması için buraya eklemedim.

@filo_bp.route('/sil/<int:id>', methods=['POST'])
def sil(id):
    ekipman = Ekipman.query.get_or_404(id)
    if ekipman.calisma_durumu == 'kirada':
        flash('Kirada olan makine silinemez!', 'danger')
        return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))
    try:
        ekipman.is_active = False
        db.session.commit()
        flash('Makine silindi (arşive kaldırıldı).', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {str(e)}', 'danger')
    return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))

@filo_bp.route('/duzelt/<int:id>', methods=['GET', 'POST'])
def duzelt(id):
    ekipman = Ekipman.query.filter(
        Ekipman.id == id,
        Ekipman.firma_tedarikci_id.is_(None),
        Ekipman.is_active == True
    ).first_or_404()
    
    form = EkipmanForm(obj=ekipman)
    
    if request.method == 'GET':
        try:
            maliyet_str = ekipman.giris_maliyeti
            if maliyet_str:
                if ',' in maliyet_str: maliyet_str = maliyet_str.replace('.', '').replace(',', '.')
                form.giris_maliyeti.data = Decimal(maliyet_str)
            else: form.giris_maliyeti.data = Decimal(0.0)
        except (ValueError, InvalidOperation):
            form.giris_maliyeti.data = Decimal(0.0)

    if form.validate_on_submit():
        try:
            # --- DÜZELTME: BURADA DA SERİ NO KONTROLÜ YAPILABİLİR (OPSİYONEL) ---
            # Eğer kullanıcı seri nosunu değiştirip başka bir makinenin seri nosunu yazarsa?
            # Bu kontrolü burada yapmak da iyidir ama 'ekle' kadar kritik değildir.
            # Şimdilik temel akışı bozmuyoruz.
            
            ekipman.marka = form.marka.data
            ekipman.model = form.model.data 
            ekipman.yakit = form.yakit.data
            ekipman.tipi = form.tipi.data
            ekipman.kod = form.kod.data
            ekipman.seri_no = form.seri_no.data
            ekipman.calisma_yuksekligi = int(form.calisma_yuksekligi.data)
            ekipman.kaldirma_kapasitesi = int(form.kaldirma_kapasitesi.data)
            ekipman.uretim_tarihi = form.uretim_tarihi.data
            ekipman.para_birimi = form.para_birimi.data
            
            maliyet_raw = form.giris_maliyeti.data
            ekipman.giris_maliyeti = clean_currency_input(maliyet_raw)
            
            if ekipman.calisma_durumu != 'kirada':
                ekipman.calisma_durumu = 'bosta'
            
            db.session.commit()
            flash('Güncellendi!', 'success')
            return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Hata: {str(e)}", "danger")

    return render_template('filo/duzelt.html', form=form, ekipman=ekipman)

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
             flash(f"Hata: Harici bir makine.", 'danger')
             return redirect(url_for('filo.index'))

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
                        flash(f"Hata: Bitiş tarihi başlangıçtan önce olamaz!", 'danger')
                        return redirect(url_for('filo.index'))
                except ValueError:
                    flash("Tarih formatı geçersiz.", 'danger')
                    return redirect(url_for('filo.index'))
                
                aktif_kalem.kiralama_bitis = bitis_tarihi_str
                ekipman.calisma_durumu = 'bosta'
                aktif_kalem.sonlandirildi = True 
                
                db.session.commit()
                flash(f"Sonlandırıldı.", 'success')
            else:
                ekipman.calisma_durumu = 'bosta'
                db.session.commit()
                flash(f"Kalem bulunamadı, boşa alındı.", 'warning')
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
        # Haricilerde de aktif olanları göster
        ekipmanlar = Ekipman.query.filter(
            and_(
                Ekipman.firma_tedarikci_id.isnot(None),
                Ekipman.is_active == True
            )
        ).options(
            joinedload(Ekipman.firma_tedarikci) 
        ).order_by(Ekipman.kod).all()
        
    except Exception as e:
        flash(f"Hata: {str(e)}", "danger")
        ekipmanlar = []

    return render_template('filo/harici.html', ekipmanlar=ekipmanlar)


# -------------------------------------------------------------------------
# 8. Pasif (Arşivlenmiş) Makineler Listesi
# -------------------------------------------------------------------------
@filo_bp.route('/arsiv')
def arsiv():
    try:
        ekipmanlar = Ekipman.query.filter(
            and_(
                Ekipman.firma_tedarikci_id.is_(None),
                Ekipman.is_active == False 
            )
        ).order_by(Ekipman.kod).all()
    except Exception as e:
        flash(f"Arşiv yüklenirken hata: {str(e)}", "danger")
        ekipmanlar = []

    return render_template('filo/arsiv.html', ekipmanlar=ekipmanlar)

# -------------------------------------------------------------------------
# 9. Makineyi Geri Yükle (Aktifleştir)
# -------------------------------------------------------------------------
@filo_bp.route('/geri_yukle/<int:id>', methods=['POST'])
def geri_yukle(id):
    ekipman = Ekipman.query.get_or_404(id)
    try:
        ekipman.is_active = True
        db.session.commit()
        flash(f"'{ekipman.kod}' başarıyla geri yüklendi.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Hata: {str(e)}", "danger")
    return redirect(url_for('filo.arsiv'))

# -------------------------------------------------------------------------
# 10. Bakımdaki (Serviste) Makineler
# -------------------------------------------------------------------------
@filo_bp.route('/bakimda')
def bakimda():
    try:
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '', type=str)
        
        base_query = Ekipman.query.filter(
            and_(
                Ekipman.firma_tedarikci_id.is_(None), # Sadece bizim makineler
                Ekipman.is_active == True,           # Sadece aktifler
                Ekipman.calisma_durumu == 'serviste' # Sadece BAKIMDAKİLER
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
        
    except Exception as e:
        flash(f"Hata: {str(e)}", "danger")
        ekipmanlar = []
        pagination = None
        q = q

    return render_template('filo/bakimda.html', ekipmanlar=ekipmanlar, pagination=pagination, q=q)

# -------------------------------------------------------------------------
# 11. YENİ ROTA: Makineyi Bakıma Al
# -------------------------------------------------------------------------
@filo_bp.route('/bakima_al', methods=['POST'])
def bakima_al():
    try:
        ekipman_id = request.form.get('ekipman_id', type=int)
        tarih = request.form.get('tarih')
        aciklama = request.form.get('aciklama')
        
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '')

        if not (ekipman_id and tarih):
            flash('Eksik bilgi! Lütfen tarih seçiniz.', 'danger')
            return redirect(url_for('filo.index', page=page, q=q))

        ekipman = Ekipman.query.get_or_404(ekipman_id)
        
        if ekipman.calisma_durumu == 'bosta':
            # 1. Durumu 'serviste' yap
            ekipman.calisma_durumu = 'serviste'
            
            # 2. Bakım Kaydı Oluştur
            yeni_bakim = BakimKaydi(
                ekipman_id=ekipman.id,
                tarih=tarih,
                aciklama=aciklama or "Hızlı Bakım Girişi (Listeden)",
                calisma_saati=0 # Bilinmiyor
            )
            db.session.add(yeni_bakim)
            db.session.commit()
            flash(f"'{ekipman.kod}' bakıma alındı.", 'success')
        else:
            flash(f"'{ekipman.kod}' zaten '{ekipman.calisma_durumu}' durumunda. Bakıma alınamaz.", 'warning')
            
    except Exception as e:
        db.session.rollback()
        flash(f"Hata oluştu: {str(e)}", 'danger')
        
    return redirect(url_for('filo.index', page=page, q=q))
# -------------------------------------------------------------------------
# 12. YENİ ROTA: Bakımı Bitir (Servisten Çıkar)
# -------------------------------------------------------------------------
@filo_bp.route('/bakim_bitir/<int:id>', methods=['POST'])
def bakim_bitir(id):
    ekipman = Ekipman.query.get_or_404(id)
    
    try:
        if ekipman.calisma_durumu == 'serviste':
            ekipman.calisma_durumu = 'bosta'
            db.session.commit()
            flash(f"'{ekipman.kod}' bakımdan çıktı ve 'Boşta' durumuna alındı.", "success")
        else:
            flash(f"'{ekipman.kod}' zaten serviste değil.", "warning")
            
    except Exception as e:
        db.session.rollback()
        flash(f"Hata oluştu: {str(e)}", "danger")
        
    # İşlemden sonra bakım listesine geri dön
    return redirect(url_for('filo.bakimda'))