from app.filo import filo_bp
from app import db 
from flask import render_template, redirect, url_for, flash, request, jsonify
from sqlalchemy.orm import joinedload, subqueryload
from sqlalchemy.exc import IntegrityError 
import traceback 
from sqlalchemy import or_
from decimal import Decimal, InvalidOperation
import locale

from app.models import Ekipman, Firma, Kiralama, KiralamaKalemi
from app.forms import EkipmanForm 

# Türkçe yerel ayarlarını dene (Linux/Windows uyumlu)
try:
    locale.setlocale(locale.LC_ALL, 'tr_TR.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'Turkish_Turkey.1254')
    except:
        pass

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYON: Para Birimi Temizleme
# -------------------------------------------------------------------------
def clean_currency_input(value_str):
    """
    Formdan gelen '15.000,50' veya '15000,50' formatındaki veriyi
    veritabanına uygun '15000.50' formatına çevirir.
    """
    if not value_str:
        return '0.0'
    
    val = str(value_str).strip()
    
    # Eğer virgül varsa, bu kesinlikle ondalık ayracıdır (Türkçe mantığı)
    if ',' in val:
        # Önce binlik ayracı olabilecek noktaları sil (15.000,50 -> 15000,50)
        val = val.replace('.', '')
        # Sonra virgülü noktaya çevir (15000,50 -> 15000.50)
        val = val.replace(',', '.')
    
    # Eğer virgül yoksa ve nokta varsa, Python bunu ondalık kabul eder.
    # (15000.50 -> 15000.50) - Değişiklik yapma.
    
    return val

# -------------------------------------------------------------------------
# 1. Makine Parkı Listeleme
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
        flash(f"Hata: {str(e)}", "danger")
        ekipmanlar = []
        pagination = None
        q = q

    return render_template('filo/index.html', ekipmanlar=ekipmanlar, pagination=pagination, q=q)


# -------------------------------------------------------------------------
# 2. Yeni Makine Ekleme
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
            # --- MALİYET TEMİZLEME ---
            maliyet_raw = form.giris_maliyeti.data
            maliyet_db = clean_currency_input(maliyet_raw)
            # -------------------------

            yeni_ekipman = Ekipman(
                kod=form.kod.data,
                yakit=form.yakit.data,
                tipi=form.tipi.data,
                marka=form.marka.data,
                
                # Model Kaydı
                model=form.model.data,
                
                seri_no=form.seri_no.data,
                calisma_yuksekligi=int(form.calisma_yuksekligi.data),
                kaldirma_kapasitesi=int(form.kaldirma_kapasitesi.data), 
                uretim_tarihi=form.uretim_tarihi.data,
                
                # Temizlenmiş Maliyet Kaydı
                giris_maliyeti=maliyet_db, 
                para_birimi=form.para_birimi.data,
                
                firma_tedarikci_id=None,
                calisma_durumu='bosta'
            )
            
            db.session.add(yeni_ekipman)
            db.session.commit()
            flash('Yeni makine başarıyla filoya eklendi!', 'success')
            return redirect(url_for('filo.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Kayıt hatası: {str(e)}", "danger")
            traceback.print_exc()
    
    return render_template('filo/ekle.html', form=form, son_kod=son_kod)

# -------------------------------------------------------------------------
# 3. Makine Silme
# -------------------------------------------------------------------------
@filo_bp.route('/sil/<int:id>', methods=['POST'])
def sil(id):
    ekipman = Ekipman.query.get_or_404(id)
    if ekipman.calisma_durumu == 'kirada':
        flash('Kirada olan makine silinemez!', 'danger')
        return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))
    try:
        db.session.delete(ekipman)
        db.session.commit()
        flash('Silindi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {str(e)}', 'danger')
    return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))

# -------------------------------------------------------------------------
# 4. Makine Düzeltme
# -------------------------------------------------------------------------
@filo_bp.route('/duzelt/<int:id>', methods=['GET', 'POST'])
def duzelt(id):
    ekipman = Ekipman.query.filter(
        Ekipman.id == id,
        Ekipman.firma_tedarikci_id.is_(None) 
    ).first_or_404()
    
    form = EkipmanForm(obj=ekipman)
    
    # --- GET İsteği: VERİ DÖNÜŞTÜRME ---
    # Veritabanından String ("15000.50") gelir.
    # Form (DecimalField olsaydı sorun olurdu, ama StringField yaptık).
    # Ancak 'duzelt.html'deki JavaScript için bunun temiz bir sayı olması iyidir.
    # Eğer StringField ise doğrudan atama yeterlidir, ancak Decimal dönüşümü
    # formda sayısal doğrulama yapıyorsa gerekebilir.
    if request.method == 'GET':
        # Eğer form.giris_maliyeti bir DecimalField ise bu blok zorunludur.
        # Eğer StringField ise de zararı olmaz, veriyi temizler.
        try:
            maliyet_str = ekipman.giris_maliyeti
            if maliyet_str:
                # Veritabanında "1.250,00" gibi bozuk format varsa temizle
                if ',' in maliyet_str:
                    maliyet_str = maliyet_str.replace('.', '').replace(',', '.')
                
                # Decimal'e çevirip forma ver (Form StringField olsa bile str() ile alır)
                form.giris_maliyeti.data = Decimal(maliyet_str)
            else:
                form.giris_maliyeti.data = Decimal(0.0)
        except (ValueError, InvalidOperation) as e:
            # Çevrilemezse 0.0 yap
            form.giris_maliyeti.data = Decimal(0.0)

    # --- POST İsteği: KAYDETME ---
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
            ekipman.para_birimi = form.para_birimi.data
            
            # --- MALİYET TEMİZLEME ---
            maliyet_raw = form.giris_maliyeti.data
            ekipman.giris_maliyeti = clean_currency_input(maliyet_raw)
            # -------------------------
            
            if ekipman.calisma_durumu != 'kirada':
                ekipman.calisma_durumu = 'bosta'
            
            db.session.commit()
            flash('Güncellendi!', 'success')
            return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Hata: {str(e)}", "danger")

    return render_template('filo/duzelt.html', form=form, ekipman=ekipman)

# ... (Diğer fonksiyonlar aynı kalır) ...
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
            flash('Eksik bilgi!', 'danger'); return redirect(url_for('filo.index'))
        ekipman = Ekipman.query.get_or_404(ekipman_id)
        if ekipman.firma_tedarikci_id is not None:
             flash(f"Hata: Harici makine.", 'danger'); return redirect(url_for('filo.index'))
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
                flash(f"Sonlandırıldı.", 'success')
            else:
                ekipman.calisma_durumu = 'bosta'; db.session.commit()
                flash(f"Kalem bulunamadı, boşa alındı.", 'warning')
        else: flash(f"Kirada değil.", 'info')
    except Exception as e:
        db.session.rollback(); flash(f"Hata: {str(e)}", 'danger')
    return redirect(url_for('filo.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))

@filo_bp.route('/harici')
def harici():
    try:
        ekipmanlar = Ekipman.query.filter(Ekipman.firma_tedarikci_id.isnot(None)).options(joinedload(Ekipman.firma_tedarikci)).order_by(Ekipman.kod).all()
    except: ekipmanlar = []
    return render_template('filo/harici.html', ekipmanlar=ekipmanlar)