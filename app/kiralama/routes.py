# --- 1. GEREKLİ TÜM IMPORTLAR ---
import json
import traceback
from datetime import datetime, timezone, date
from decimal import Decimal

# DÜZELTME: 'request' ve 'or_' import edildi
from flask import render_template, redirect, url_for, flash, jsonify, request
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, subqueryload

from app import db
from app.kiralama import kiralama_bp 

# --- GÜNCELLENEN MODELLER ---
from app.models import Kiralama, Ekipman, Firma, KiralamaKalemi
# --- GÜNCELLENEN MODELLER SONU ---

# --- GÜNCELLENEN FORMLAR ---
from app.forms import KiralamaForm, KiralamaKalemiForm 
# --- GÜNCELLENEN FORMLAR SONU ---

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYONLAR (DÜZELTİLDİ: Placeholder '0' oldu)
# -------------------------------------------------------------------------

def get_pimaks_ekipman_choices(kiralama_objesi=None):
    """
    SADECE BİZİM ('bosta' olan VEYA bu kiralamaya ait olan)
    makinelerimizin listesini döndürür.
    """
    try:
        # 1. Bizim ve 'bosta' olanlar
        query = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.is_(None), 
            Ekipman.calisma_durumu == 'bosta'
        )
        
        gecerli_ekipmanlar = query.order_by(Ekipman.kod).all()
        gecerli_ekipman_id_seti = {e.id for e in gecerli_ekipmanlar}
        choices = [(e.id, f"{e.kod} ({e.tipi} / {e.calisma_yuksekligi or 0}m)") for e in gecerli_ekipmanlar]

        # 2. 'duzenle' ekranı için, mevcut kiradaki makineleri ekle
        if kiralama_objesi:
            for kalem in kiralama_objesi.kalemler:
                if (kalem.ekipman_id not in gecerli_ekipman_id_seti and 
                    kalem.ekipman and 
                    kalem.ekipman.firma_tedarikci_id is None):
                    e = kalem.ekipman
                    label = f"{e.kod} ({e.tipi} / {e.calisma_yuksekligi or 0}m) (ŞU AN KİRADA)"
                    choices.append((e.id, label))
                    gecerli_ekipman_id_seti.add(e.id)

        # --- DÜZELTME: Placeholder '' -> '0' (ValueError düzeltmesi) ---
        choices.insert(0, ('0', '--- Pimaks Filosu Seçiniz ---'))
        return choices
        
    except Exception as e:
        print(f"Hata (get_pimaks_ekipman_choices): {e}")
        return [('0', '--- Hata: Ekipmanlar Yüklenemedi ---')]

def get_tedarikci_choices(include_pimaks=False):
    """ 
    Tüm 'Tedarikçi' firmaların listesini döndürür.
    """
    try:
        tedarikciler = Firma.query.filter_by(is_tedarikci=True).order_by(Firma.firma_adi).all()
        choices = [(f.id, f.firma_adi) for f in tedarikciler]
        
        if include_pimaks:
            # --- DÜZELTME: Placeholder '' -> '0' ---
            choices.insert(0, ('0', '--- Pimaks (Maliyet Yok) ---'))
        else:
            # --- DÜZELTME: Placeholder '' -> '0' ---
            choices.insert(0, ('0', '--- Tedarikçi Seçiniz ---'))
            
        return choices
    except Exception as e:
        print(f"Hata (get_tedarikci_choices): {e}")
        return [('0', '--- Hata: Tedarikçiler Yüklenemedi ---')]

def populate_kiralama_form_choices(form, kiralama_objesi=None):
    """
    KiralamaForm'undaki tüm dinamik SelectField'ları doldurur.
    """
    try:
        musteri_choices = [(f.id, f.firma_adi) for f in Firma.query.filter_by(is_musteri=True).order_by(Firma.firma_adi).all()]
        # --- DÜZELTME: Placeholder '' -> '0' ---
        musteri_choices.insert(0, ('0', '--- Müşteri Seçiniz ---'))
        form.firma_musteri_id.choices = musteri_choices
    except Exception as e:
        print(f"Hata (populate_kiralama_form_choices - Müşteriler): {e}")
        form.firma_musteri_id.choices = [('0', 'Hata: Müşteriler Yüklenemedi')]

    # (Bu listeler artık '0' placeholder'ını içeriyor)
    pimaks_ekipman_list = get_pimaks_ekipman_choices(kiralama_objesi)
    ekipman_tedarikci_list = get_tedarikci_choices(include_pimaks=False)
    nakliye_tedarikci_list = get_tedarikci_choices(include_pimaks=True)
    
    for kalem_form_field in form.kalemler:
        kalem_form_field.form.ekipman_id.choices = pimaks_ekipman_list
        kalem_form_field.form.harici_ekipman_tedarikci_id.choices = ekipman_tedarikci_list
        kalem_form_field.form.nakliye_tedarikci_id.choices = nakliye_tedarikci_list

# -------------------------------------------------------------------------
# 2. JINJA2 FİLTRESİ (Tarih Formatlama)
# -------------------------------------------------------------------------
@kiralama_bp.app_template_filter('tarihtr')
def tarihtr(value):
    if not value: return ""
    if isinstance(value, (datetime, date)): return value.strftime("%d.%m.%Y")
    if isinstance(value, str):
        try:
            value_dt = datetime.strptime(value, '%Y-%m-%d').date()
            return value_dt.strftime("%d.%m.%Y")
        except ValueError:
            return value 
    return value

# -------------------------------------------------------------------------
# 3. KİRALAMA LİSTELEME (NİHAİ - ARAMA, SAYFALAMA, KALEM BAZLI DURUM)
# -------------------------------------------------------------------------
@kiralama_bp.route('/index')
@kiralama_bp.route('/') 
def index():
    """ 
    Tüm kiralama kayıtlarını listeler.
    YENİ: Arama (Form No, Firma Adı, Yetkili Adı) ve Sayfalama destekler.
    YENİ: Her BİR KALEM için 'durum' hesaplar.
    """
    try:
        # 1. URL'den 'page' (sayfa) ve 'q' (arama) parametrelerini al
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '', type=str) # Arama sorgusu

        # 2. Temel sorguyu başlat (ve hızlı yükleme için ilişkileri hazırla)
        base_query = Kiralama.query.options(
            joinedload(Kiralama.firma_musteri), 
            joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.ekipman).joinedload(Ekipman.firma_tedarikci),
            joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.nakliye_tedarikci)
        )

        # 3. Eğer bir arama sorgusu (q) varsa, sorguyu filtrele
        if q:
            search_term = f'%{q}%'
            # --- YENİ: İlişkili 'Firma' tablosuna sorgu için katıl (JOIN) ---
            base_query = base_query.join(
                Firma, Kiralama.firma_musteri_id == Firma.id
            ).filter(
                or_(
                    Kiralama.kiralama_form_no.ilike(search_term), # Form No
                    Firma.firma_adi.ilike(search_term),          # Firma Adı
                    Firma.yetkili_adi.ilike(search_term)       # Yetkili Adı
                )
            )

        # 4. Filtrelenmiş sorguyu, Sayfalama (paginate) yaparak çalıştır
        pagination = base_query.order_by(Kiralama.id.desc()).paginate(
            page=page, per_page=25, error_out=False
        )
        kiralamalar = pagination.items
        
        # --- YENİ DÜZELTİLMİŞ DURUM HESAPLAMA (KALEM BAZLI) ---
        today = date.today()
        
        for kiralama in kiralamalar:
            # Artık kiralama.durum_mesaji YOK.
            # Döngüyü 'kalem' seviyesine indiriyoruz:
            for kalem in kiralama.kalemler:
                if kalem.sonlandirildi:
                    kalem.durum_mesaji = "Tamamlandı"
                    kalem.durum_sinifi = "secondary"
                elif not kalem.kiralama_bitis:
                    kalem.durum_mesaji = "Aktif (Bitiş Belirsiz)"
                    kalem.durum_sinifi = "primary"
                else:
                    try:
                        bitis_dt = datetime.strptime(kalem.kiralama_bitis, '%Y-%m-%d').date()
                        kalan_gun = (bitis_dt - today).days
                        
                        if kalan_gun < 0:
                            kalem.durum_mesaji = f"Gecikti ({abs(kalan_gun)} gün)"
                            kalem.durum_sinifi = "danger"
                        elif kalan_gun == 0:
                            kalem.durum_mesaji = "BUGÜN BİTİYOR"
                            kalem.durum_sinifi = "warning"
                        elif kalan_gun <= 7:
                            kalem.durum_mesaji = f"{kalan_gun} gün sonra bitecek"
                            kalem.durum_sinifi = "warning"
                        else:
                            kalem.durum_mesaji = "Aktif"
                            kalem.durum_sinifi = "success"
                    except Exception as e:
                        print(f"Tarih ayrıştırma hatası: {e}")
                        kalem.durum_mesaji = "Hatalı Tarih"
                        kalem.durum_sinifi = "dark" # Hatalı veriyi göster
        # --- DURUM HESAPLAMA SONU ---
            
        return render_template(
            'kiralama/index.html', 
            kiralamalar=kiralamalar,
            pagination=pagination,
            q=q
        )

    except Exception as e:
        flash(f"Kiralamalar yüklenirken bir hata oluştu: {str(e)}", "danger")
        traceback.print_exc()
        return render_template('kiralama/index.html', kiralamalar=[], pagination=None, q=q)

# -------------------------------------------------------------------------
# 4. YENİ KİRALAMA EKLEME (KISAYOL MANTIĞI DÜZELTİLDİ)
# -------------------------------------------------------------------------
@kiralama_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    """ 
    Yeni kiralama kaydı oluşturur.
    "Dış Tedarik" (Ekipman + Nakliye) mantığını tam olarak destekler.
    YENİ: URL'den 'ekipman_id' parametresini alarak formu önceden doldurur.
    """
    
    # --- DÜZELTME: Form başlatma mantığı 'GET' ve 'POST' için ayrıldı ---
    
    if request.method == 'GET':
        # --- YENİ EKLENEN KISAYOL MANTIĞI (DÜZELTİLDİ) ---
        ekipman_id_from_url = request.args.get('ekipman_id', type=int)
        pre_data = {} # Formu önceden doldurmak için veri
        
        if ekipman_id_from_url:
            # Formu, ilk kalemi bu ID ile dolu olarak başlat
            pre_data = {
                'kalemler': [{
                    'ekipman_id': ekipman_id_from_url
                }]
            }
        
        # Formu, bu 'pre_data' ile başlat
        form = KiralamaForm(data=pre_data) 
        # --- YENİ MANTIK SONU ---

        # Form Numarası Oluşturma (GET'e taşındı)
        try:
            simdiki_yil = datetime.now(timezone.utc).year
            form_prefix = f'PF-{simdiki_yil}/'
            son_kiralama = Kiralama.query.filter(Kiralama.kiralama_form_no.like(f"{form_prefix}%")).order_by(Kiralama.id.desc()).first()
            yeni_numara = 1
            if son_kiralama and son_kiralama.kiralama_form_no:
                try:
                    son_numara_str = son_kiralama.kiralama_form_no.split('/')[-1]
                    if son_numara_str.isdigit():
                        yeni_numara = int(son_numara_str) + 1
                except:
                    pass 
            form.kiralama_form_no.data = f'{form_prefix}{yeni_numara}'
        except Exception as e:
            flash(f"Form numarası oluşturulurken hata: {e}", "warning")
            
    else: # request.method == 'POST'
        # Formu POST verisiyle başlat (boş)
        form = KiralamaForm() 

    # Formdaki tüm 'Select' alanlarını doldur (GET'te ve POST'ta da gerekli)
    populate_kiralama_form_choices(form)
    
    # --- POST MANTIĞI (NİHAİ) ---
    if form.validate_on_submit():
        yeni_kiralama = Kiralama(
            kiralama_form_no=form.kiralama_form_no.data,
            firma_musteri_id=form.firma_musteri_id.data,
            kdv_orani=form.kdv_orani.data
        )
        db.session.add(yeni_kiralama) 
        
        try:
            secilen_pimaks_ekipman_idler = set()
            kalemler_to_add = [] # (Ekipman objesi, KiralamaKalemi objesi)
            
            for kalem_data in form.kalemler.data:
                
                ekipman_id_to_use = None
                ekipman_to_update_status = None # Sadece Pimaks makinesiyse

                # --- 1. EKİPMAN SEÇİMİ (DIŞ TEDARİK MANTIĞI) ---
                if kalem_data['dis_tedarik_ekipman']:
                    # --- DIŞ TEDARİK ---
                    tedarikci_id = kalem_data['harici_ekipman_tedarikci_id']
                    seri_no = (kalem_data['harici_ekipman_seri_no'] or '').strip()
                    tipi = (kalem_data['harici_ekipman_tipi'] or 'Bilinmiyor').strip()
                    
                    if not (tedarikci_id and tedarikci_id > 0 and seri_no):
                        raise ValueError(f"Dış Tedarik seçildi ancak Tedarikçi veya Seri No bilgisi eksik.")
                    
                    harici_ekipman = Ekipman.query.filter_by(
                        firma_tedarikci_id=tedarikci_id,
                        seri_no=seri_no
                    ).first()
                    
                    if not harici_ekipman:
                        harici_ekipman = Ekipman(
                            kod=f"HARICI-{seri_no}",
                            seri_no=seri_no,
                            tipi=tipi,
                            marka="Harici",
                            yakit="Bilinmiyor",
                            calisma_yuksekligi=0,
                            kaldirma_kapasitesi=0,
                            uretim_tarihi="Bilinmiyor",
                            giris_maliyeti='0',
                            firma_tedarikci_id=tedarikci_id,
                            calisma_durumu='harici'
                        )
                        db.session.add(harici_ekipman)
                        db.session.flush() # ID'sini almak için
                    
                    ekipman_id_to_use = harici_ekipman.id
                    
                else:
                    # --- PİMAKS FİLOSU ---
                    ekipman_id_to_use = kalem_data['ekipman_id']
                    if not (ekipman_id_to_use and ekipman_id_to_use > 0):
                        continue # Boş satırı ('0' seçili) atla
                    
                    if ekipman_id_to_use in secilen_pimaks_ekipman_idler:
                        raise ValueError(f"Ekipmanı (ID: {ekipman_id_to_use}) aynı formda birden fazla seçemezsiniz.")
                    
                    ekipman_to_update_status = Ekipman.query.get(ekipman_id_to_use)
                    if not ekipman_to_update_status or ekipman_to_update_status.firma_tedarikci_id is not None:
                        raise ValueError(f"Pimaks filosu ekipmanı (ID: {ekipman_id_to_use}) bulunamadı veya harici bir makine.")
                    
                    if ekipman_to_update_status.calisma_durumu != 'bosta':
                         raise ValueError(f"Ekipman ({ekipman_to_update_status.kod}) 'boşta' değil, kiralanamaz.")
                
                # --- 2. TARİH KONTROLÜ ---
                baslangic = kalem_data['kiralama_baslangıcı']
                bitis = kalem_data['kiralama_bitis']
                if not baslangic:
                    raise ValueError(f"Ekipman {ekipman_id_to_use} için Başlangıç Tarihi zorunludur.")
                if not bitis:
                    raise ValueError(f"Ekipman {ekipman_id_to_use} için Bitiş Tarihi zorunludur.")
                if bitis < baslangic:
                    raise ValueError(f"Hata: Bitiş Tarihi, Başlangıç Tarihinden önce olamaz.")
                
                baslangic_str = baslangic.strftime("%Y-%m-%d")
                bitis_str = bitis.strftime("%Y-%m-%d")
                
                # --- 3. NAKLİYE KONTROLÜ ---
                nakliye_ted_id_data = kalem_data['nakliye_tedarikci_id']
                nakliye_ted_id = nakliye_ted_id_data if nakliye_ted_id_data != 0 else None
                
                if kalem_data['dis_tedarik_nakliye'] and not nakliye_ted_id:
                     raise ValueError(f"Harici Nakliye seçildi ancak Nakliye Tedarikçisi seçilmedi.")
                
                # --- 4. KİRALAMA KALEMİNİ OLUŞTUR ---
                yeni_kalem = KiralamaKalemi(
                    ekipman_id=ekipman_id_to_use,
                    kiralama_baslangıcı=baslangic_str,
                    kiralama_bitis=bitis_str,
                    kiralama_brm_fiyat=str(kalem_data['kiralama_brm_fiyat'] or 0),
                    kiralama_alis_fiyat=str(kalem_data['kiralama_alis_fiyat'] or 0),
                    nakliye_satis_fiyat=str(kalem_data['nakliye_satis_fiyat'] or 0),
                    nakliye_alis_fiyat=str(kalem_data['nakliye_alis_fiyat'] or 0),
                    nakliye_tedarikci_id=nakliye_ted_id if kalem_data['dis_tedarik_nakliye'] else None,
                    sonlandirildi=False # Yeni kalem
                )
                
                kalemler_to_add.append((ekipman_to_update_status, yeni_kalem)) 
                if ekipman_to_update_status: # Sadece Pimaks ID'lerini takip et
                    secilen_pimaks_ekipman_idler.add(ekipman_id_to_use)

            # --- 5. KAYDET VE EKİPMAN DURUMLARINI GÜNCELLE ---
            if not kalemler_to_add:
                flash("En az bir geçerli kiralama kalemi eklemelisiniz.", "danger")
                db.session.rollback()
            else:
                for ekipman, kalem in kalemler_to_add:
                    kalem.kiralama = yeni_kiralama 
                    
                    if ekipman: # (Ekipman None ise harici makinedir)
                        ekipman.calisma_durumu = "kirada"
                        
                    db.session.add(kalem)
                    
                db.session.commit()
                flash(f"{len(kalemler_to_add)} kalem başarıyla kiralandı!", "success")
                return redirect(url_for('kiralama.index')) 

        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash(f"Veri doğrulama hatası: {str(e)}", "danger")
        except IntegrityError as e: # 'UniqueConstraint' hatasını yakala
            db.session.rollback()
            flash(f"Veritabanı benzersizlik hatası: {str(e)}", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Veritabanı hatası oluştu: {str(e)}", "danger")
            traceback.print_exc()

    else:
        if request.method == 'POST' and form.errors:
            flash("Formda hatalar var, lütfen kontrol edin.", "warning")
            print("FORM HATALARI:", form.errors)

    # --- JSON VERİLERİNİ TEMPLATE'E GÖNDER (HATAYI ÇÖZER) ---
    ekipman_choices_json = json.dumps(get_pimaks_ekipman_choices())
    tedarikci_choices_json = json.dumps(get_tedarikci_choices(include_pimaks=False))
    nakliye_tedarikci_choices_json = json.dumps(get_tedarikci_choices(include_pimaks=True))
    # --- JSON VERİLERİ SONU ---

    return render_template(
        'kiralama/ekle.html', 
        form=form, 
        ekipman_choices_json=ekipman_choices_json,
        tedarikci_choices_json=tedarikci_choices_json, # Harici Ekipman için
        nakliye_tedarikci_choices_json=nakliye_tedarikci_choices_json # Harici Nakliye için
    )

# -------------------------------------------------------------------------
# 5. KİRALAMA KAYDI DÜZENLEME (NİHAİ VE TAMAMLANMIŞ)
# -------------------------------------------------------------------------
@kiralama_bp.route('/duzenle/<int:kiralama_id>', methods=['GET', 'POST'])
def duzenle(kiralama_id):
    """ 
    Mevcut bir kiralama kaydını düzenler.
    'ekle' fonksiyonundaki tüm "Dış Tedarik" mantığını destekler.
    """
    
    kiralama = Kiralama.query.options(
        joinedload(Kiralama.firma_musteri),
        joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.ekipman),
        joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.nakliye_tedarikci)
    ).get_or_404(kiralama_id)

    # DÜZELTME: 'obj=kiralama'yı 'POST'ta kullanma
    if request.method == 'POST':
        form = KiralamaForm()
    else: # 'GET' isteği
        form = KiralamaForm(obj=kiralama)
    
    # Formdaki tüm 'Select' alanlarını doldur
    populate_kiralama_form_choices(form, kiralama_objesi=kiralama)
    
    # --- GET İsteği (Formu Doldurma) ---
    if request.method == 'GET':
        try:
            form.firma_musteri_id.data = kiralama.firma_musteri_id
            form.kdv_orani.data = kiralama.kdv_orani
            
            for i, kalem in enumerate(kiralama.kalemler):
                if i < len(form.kalemler):
                    kalem_form = form.kalemler[i]
                    
                    ekipman_obj = kalem.ekipman
                    if ekipman_obj and ekipman_obj.firma_tedarikci_id is not None:
                        # Bu HARİCİ bir ekipman
                        kalem_form.dis_tedarik_ekipman.data = True
                        kalem_form.harici_ekipman_tedarikci_id.data = ekipman_obj.firma_tedarikci_id
                        kalem_form.harici_ekipman_tipi.data = ekipman_obj.tipi
                        kalem_form.harici_ekipman_seri_no.data = ekipman_obj.seri_no
                    else:
                        # Bu PİMAKS ekipmanı
                        kalem_form.dis_tedarik_ekipman.data = False
                        kalem_form.ekipman_id.data = kalem.ekipman_id
                    
                    if kalem.nakliye_tedarikci_id is not None:
                        kalem_form.dis_tedarik_nakliye.data = True
                        kalem_form.nakliye_tedarikci_id.data = kalem.nakliye_tedarikci_id
                    else:
                        kalem_form.dis_tedarik_nakliye.data = False
                        kalem_form.nakliye_tedarikci_id.data = 0 # 0 = Pimaks
                    
                    if isinstance(kalem.kiralama_baslangıcı, str):
                        kalem_form.kiralama_baslangıcı.data = datetime.strptime(kalem.kiralama_baslangıcı, '%Y-%m-%d').date()
                    if isinstance(kalem.kiralama_bitis, str):
                        kalem_form.kiralama_bitis.data = datetime.strptime(kalem.kiralama_bitis, '%Y-%m-%d').date()
                    
                    kalem_form.kiralama_brm_fiyat.data = Decimal(kalem.kiralama_brm_fiyat or 0)
                    kalem_form.kiralama_alis_fiyat.data = Decimal(kalem.kiralama_alis_fiyat or 0)
                    kalem_form.nakliye_satis_fiyat.data = Decimal(kalem.nakliye_satis_fiyat or 0)
                    kalem_form.nakliye_alis_fiyat.data = Decimal(kalem.nakliye_alis_fiyat or 0)
                
        except Exception as e:
            flash(f"Form verileri yüklenirken bir hata oluştu: {e}", "danger")
            traceback.print_exc()
    # --- GET İsteği Sonu ---

    # --- POST ISTEGI (Formu Kaydetme) ---
    if form.validate_on_submit():
        
        original_db_kalemler = {k.id: k for k in kiralama.kalemler if not k.sonlandirildi}
        original_pimaks_ekipman_ids = {
            k.ekipman_id for k in original_db_kalemler.values() 
            if k.ekipman_id and k.ekipman and k.ekipman.firma_tedarikci_id is None
        }
        
        try:
            # 1. Ana Kiralama Formunu Güncelle
            kiralama.kiralama_form_no = form.kiralama_form_no.data
            kiralama.firma_musteri_id = form.firma_musteri_id.data
            kiralama.kdv_orani = form.kdv_orani.data
            
            form_kalemler_map = {} # Formdan gelen {kalem_id: ekipman_id}
            yeni_pimaks_ekipman_idler = set()
            ekipmanlar_to_update_status = {} # {ekipman_id: 'durum'}
            
            # Formdan gelen kalemleri işle
            for kalem_data in form.kalemler.data:
                
                db_kalem = None
                kalem_id_str = str(kalem_data.get('id') or '')
                
                # A. Kilitli (sonlandırılmış) bir kalem mi?
                if kalem_id_str.isdigit() and int(kalem_id_str) > 0:
                    db_kalem = KiralamaKalemi.query.get(int(kalem_id_str))
                    if db_kalem and db_kalem.sonlandirildi:
                        # Kilitli kalemi atla, durumunu koru
                        if db_kalem.ekipman and db_kalem.ekipman.firma_tedarikci_id is None:
                            yeni_pimaks_ekipman_idler.add(db_kalem.ekipman_id)
                        continue 

                # B. Ekipman Seçimini İşle ('ekle' fonksiyonundaki gibi)
                ekipman_id_to_use = None
                ekipman_to_update = None
                
                if kalem_data['dis_tedarik_ekipman']:
                    tedarikci_id = kalem_data['harici_ekipman_tedarikci_id']
                    seri_no = (kalem_data['harici_ekipman_seri_no'] or '').strip()
                    tipi = (kalem_data['harici_ekipman_tipi'] or 'Bilinmiyor').strip()
                    
                    if not (tedarikci_id and tedarikci_id > 0 and seri_no):
                        raise ValueError(f"Dış Tedarik seçildi ancak Tedarikçi veya Seri No bilgisi eksik.")
                    
                    harici_ekipman = Ekipman.query.filter_by(firma_tedarikci_id=tedarikci_id, seri_no=seri_no).first()
                    if not harici_ekipman:
                        harici_ekipman = Ekipman(
                            kod=f"HARICI-{seri_no}", seri_no=seri_no, tipi=tipi, marka="Harici",
                            yakit="Bilinmiyor", calisma_yuksekligi=0, kaldirma_kapasitesi=0,
                            uretim_tarihi="Bilinmiyor", giris_maliyeti='0',
                            firma_tedarikci_id=tedarikci_id, calisma_durumu='harici'
                        )
                        db.session.add(harici_ekipman)
                        db.session.flush()
                    ekipman_id_to_use = harici_ekipman.id
                
                else: # Pimaks Filosu
                    ekipman_id_to_use = kalem_data['ekipman_id']
                    if not (ekipman_id_to_use and ekipman_id_to_use > 0):
                        continue # Boş satırı atla
                    
                    if ekipman_id_to_use in yeni_pimaks_ekipman_idler: # Bu formda çift seçimi engelle
                        raise ValueError(f"Ekipmanı (ID: {ekipman_id_to_use}) aynı formda birden fazla seçemezsiniz.")
                    
                    ekipman_to_update = Ekipman.query.get(ekipman_id_to_use)
                    if not ekipman_to_update or ekipman_to_update.firma_tedarikci_id is not None:
                        raise ValueError(f"Pimaks filosu ekipmanı (ID: {ekipman_id_to_use}) bulunamadı.")
                    
                    if (ekipman_to_update.calisma_durumu != 'bosta' and 
                        ekipman_id_to_use not in original_pimaks_ekipman_ids):
                         raise ValueError(f"Ekipman ({ekipman_to_update.kod}) 'boşta' değil, kiralanamaz.")
                    
                    yeni_pimaks_ekipman_idler.add(ekipman_id_to_use)
                    ekipmanlar_to_update_status[ekipman_id_to_use] = 'kirada'
                
                # C. Tarih ve Finansal Verileri Hazırla
                baslangic = kalem_data['kiralama_baslangıcı']
                bitis = kalem_data['kiralama_bitis']
                if not baslangic or not bitis: raise ValueError("Tarih alanları zorunludur.")
                if bitis < baslangic: raise ValueError("Bitiş Tarihi, Başlangıç Tarihinden önce olamaz.")
                baslangic_str = baslangic.strftime("%Y-%m-%d")
                bitis_str = bitis.strftime("%Y-%m-%d")
                
                nakliye_ted_id_data = kalem_data['nakliye_tedarikci_id']
                nakliye_ted_id = nakliye_ted_id_data if nakliye_ted_id_data != 0 else None
                if kalem_data['dis_tedarik_nakliye'] and not nakliye_ted_id:
                     raise ValueError(f"Harici Nakliye seçildi ancak Nakliye Tedarikçisi seçilmedi.")

                # D. Yeni mi, Güncelleme mi?
                if db_kalem and db_kalem.id in original_db_kalemler:
                    # --- GÜNCELLEME ---
                    db_kalem.ekipman_id = ekipman_id_to_use
                    db_kalem.kiralama_baslangıcı = baslangic_str
                    db_kalem.kiralama_bitis = bitis_str
                    db_kalem.kiralama_brm_fiyat = str(kalem_data['kiralama_brm_fiyat'] or 0)
                    db_kalem.kiralama_alis_fiyat = str(kalem_data['kiralama_alis_fiyat'] or 0)
                    db_kalem.nakliye_satis_fiyat = str(kalem_data['nakliye_satis_fiyat'] or 0)
                    db_kalem.nakliye_alis_fiyat = str(kalem_data['nakliye_alis_fiyat'] or 0)
                    db_kalem.nakliye_tedarikci_id = nakliye_ted_id if kalem_data['dis_tedarik_nakliye'] else None
                    
                    form_kalemler_map[db_kalem.id] = ekipman_id_to_use
                else:
                    # --- YENİ KALEM ---
                    yeni_kalem = KiralamaKalemi(
                        kiralama=kiralama, # Doğrudan ana kiralamaya bağla
                        ekipman_id=ekipman_id_to_use,
                        kiralama_baslangıcı=baslangic_str,
                        kiralama_bitis=bitis_str,
                        kiralama_brm_fiyat=str(kalem_data['kiralama_brm_fiyat'] or 0),
                        kiralama_alis_fiyat=str(kalem_data['kiralama_alis_fiyat'] or 0),
                        nakliye_satis_fiyat=str(kalem_data['nakliye_satis_fiyat'] or 0),
                        nakliye_alis_fiyat=str(kalem_data['nakliye_alis_fiyat'] or 0),
                        nakliye_tedarikci_id=nakliye_ted_id if kalem_data['dis_tedarik_nakliye'] else None,
                        sonlandirildi=False
                    )
                    db.session.add(yeni_kalem)

            # 2. Ekipman Durumlarını Güncelle (Farkı Bularak)
            ids_to_make_bosta = original_pimaks_ekipman_ids - yeni_pimaks_ekipman_idler
            
            for ekip_id in ids_to_make_bosta:
                ekipmanlar_to_update_status[ekip_id] = 'bosta'
            
            for ekip_id, new_status in ekipmanlar_to_update_status.items():
                ekip = Ekipman.query.get(ekip_id)
                if ekip: ekip.calisma_durumu = new_status

            # 3. Formdan Silinen Kalemleri DB'den Sil
            form_ids_set = {int(kalem_data.get('id')) for kalem_data in form.kalemler.data if kalem_data.get('id') and str(kalem_data.get('id')).isdigit()}
            ids_to_delete = set(original_db_kalemler.keys()) - form_ids_set
            
            if ids_to_delete:
                KiralamaKalemi.query.filter(KiralamaKalemi.id.in_(ids_to_delete)).delete(synchronize_session=False)

            db.session.commit()
            flash('Kiralama kaydı başarıyla güncellendi.', 'success')
            return redirect(url_for('kiralama.index'))

        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash(f"Güncelleme sırasında veri hatası: {str(e)}", "danger")
        except IntegrityError as e: 
            db.session.rollback()
            flash(f"Veritabanı benzersizlik hatası: {str(e)}", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Güncelleme sırasında bir veritabanı hatası oluştu: {str(e)}", "danger")
            traceback.print_exc()

    elif request.method == 'POST' and form.errors:
        flash("Formda hatalar var. Lütfen kontrol ediniz.", "danger")
        print("FORM HATALARI:", form.errors)
        
    ekipman_choices_json = json.dumps(get_pimaks_ekipman_choices(kiralama))
    tedarikci_choices_json = json.dumps(get_tedarikci_choices(include_pimaks=False))
    nakliye_tedarikci_choices_json = json.dumps(get_tedarikci_choices(include_pimaks=True))
    
    return render_template(
        'kiralama/duzelt.html', 
        form=form, 
        kiralama=kiralama,
        ekipman_choices_json=ekipman_choices_json,
        tedarikci_choices_json=tedarikci_choices_json,
        nakliye_tedarikci_choices_json=nakliye_tedarikci_choices_json
    )

# -------------------------------------------------------------------------
# 6. KİRALAMA KAYDI SİLME
# -------------------------------------------------------------------------
@kiralama_bp.route('/sil/<int:kiralama_id>', methods=['POST'])
def sil(kiralama_id):
    kiralama = Kiralama.query.get_or_404(kiralama_id)
    try:
        for kalem in kiralama.kalemler:
            if kalem.ekipman and kalem.ekipman.firma_tedarikci_id is None and not kalem.sonlandirildi:
                kalem.ekipman.calisma_durumu = 'bosta'
        
        db.session.delete(kiralama)
        db.session.commit()
        flash('Kiralama kaydı ve bağlı kalemleri başarıyla silindi.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Kiralama silinirken bir hata oluştu: {str(e)}', 'danger')
        traceback.print_exc() 

    # Silme işleminden sonra arama/sayfalama bilgisi olmadan ana sayfaya dön
    return redirect(url_for('kiralama.index'))

# -------------------------------------------------------------------------
# 7. EKİPMAN FİLTRELEME API (NİHAİ GÜNCELLEME)
# -------------------------------------------------------------------------
@kiralama_bp.route('/api/get-ekipman')
def get_ekipman():
    """ 
    Kiralama formu için SADECE PİMAKS FİLOSU ekipmanlarını JSON olarak sağlar.
    """
    try:
        include_id = request.args.get('include_id', None, type=int)
        
        query = Ekipman.query.filter(
            Ekipman.firma_tedarikci_id.is_(None), 
            Ekipman.calisma_durumu == 'bosta'
        )
        ekipmanlar = query.order_by(Ekipman.kod).all()
        ekipman_id_seti = {e.id for e in ekipmanlar}
        
        if include_id and include_id not in ekipman_id_seti:
             mevcut_ekipman = Ekipman.query.filter_by(id=include_id, firma_tedarikci_id=None).first()
             if mevcut_ekipman:
                 ekipmanlar.insert(0, mevcut_ekipman)

        sonuc = [
            {
                "id": e.id, 
                "kod": (
                    f"{e.kod} ({e.tipi} / {e.calisma_yuksekligi or 0}m)" +
                    (" (MEVCUT SEÇİM)" if e.id == include_id and e.id not in ekipman_id_seti else "")
                )
            } 
            for e in ekipmanlar
        ]
        
        return jsonify(sonuc)
        
    except Exception as e:
        print(f"API Hatası (get_ekipman): {e}")
        traceback.print_exc()
        return jsonify({"error": str(e), "details": "Sunucu tarafında bir hata oluştu."}), 500

# -------------------------------------------------------------------------
# 8. YENİ ROTA: Tek Bir Kiralama Kalemini Sonlandırma
# -------------------------------------------------------------------------
@kiralama_bp.route('/kalem/sonlandir', methods=['POST'])
def sonlandir_kalem():
    """
    Formdan gelen 'kalem_id' ve 'bitis_tarihi' bilgilerine göre
    tek bir kiralama kalemini sonlandırır.
    """
    try:
        # Verileri formdan al
        kalem_id = request.form.get('kalem_id', type=int)
        bitis_tarihi_str = request.form.get('bitis_tarihi')
        
        # Arama ve sayfalama bilgilerini de al (geri dönmek için)
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '')

        if not (kalem_id and bitis_tarihi_str):
            flash('Eksik bilgi! Kalem ID veya Bitiş Tarihi gelmedi.', 'danger')
            return redirect(url_for('kiralama.index', page=page, q=q))
            
        kalem = KiralamaKalemi.query.get_or_404(kalem_id)
        
        if kalem.sonlandirildi:
            flash(f"Bu kalem zaten 'Tamamlandı' olarak işaretlenmiş.", 'info')
            return redirect(url_for('kiralama.index', page=page, q=q))

        ekipman = kalem.ekipman

        # --- Sunucu Tarafı Tarih Kontrolü ---
        try:
            baslangic_dt = datetime.strptime(kalem.kiralama_baslangıcı, "%Y-%m-%d").date()
            bitis_dt = datetime.strptime(bitis_tarihi_str, "%Y-%m-%d").date()
            
            if bitis_dt < baslangic_dt:
                flash(f"Hata: Bitiş tarihi ({bitis_tarihi_str}), başlangıç tarihinden ({kalem.kiralama_baslangıcı}) önce olamaz!", 'danger')
                return redirect(url_for('kiralama.index', page=page, q=q))
        except ValueError:
            flash("Tarih formatı geçersiz.", 'danger')
            return redirect(url_for('kiralama.index', page=page, q=q))
        # --- Tarih Kontrolü Sonu ---

        kalem.kiralama_bitis = bitis_tarihi_str
        kalem.sonlandirildi = True
        
        if ekipman and ekipman.firma_tedarikci_id is None:
            ekipman.calisma_durumu = 'bosta'
        
        db.session.commit()
        flash(f"'{ekipman.kod if ekipman else 'Ekipman'}' kodlu ekipmanın kiralaması {bitis_tarihi_str} tarihiyle başarıyla sonlandırıldı.", 'success')

    except Exception as e:
        db.session.rollback()
        flash(f"Kalem sonlandırılırken bir hata oluştu: {str(e)}", 'danger')
        traceback.print_exc()

    return redirect(url_for('kiralama.index', page=page, q=q))