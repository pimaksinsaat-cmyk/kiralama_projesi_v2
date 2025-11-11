# --- 1. GEREKLİ TÜM IMPORTLAR ---
import json
import traceback
from datetime import datetime, timezone, date
from decimal import Decimal

from flask import render_template, redirect, url_for, flash, jsonify, request
# 'and_' ve 'or_' sqlalchemy sorguları için eklendi
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, subqueryload

from app import db
# 'kiralama_bp' __init__.py dosyasından içe aktarıldı
from app.kiralama import kiralama_bp 

# --- GÜNCELLENEN MODELLER ---
# 'Musteri' silindi, yerine 'Firma' geldi.
from app.models import Kiralama, Ekipman, Firma, KiralamaKalemi
# --- GÜNCELLENEN MODELLER SONU ---

# --- GÜNCELLENEN FORMLAR ---
from app.forms import KiralamaForm, KiralamaKalemiForm 
# --- GÜNCELLENEN FORMLAR SONU ---

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYONLAR (Form Seçeneklerini Doldurmak İçin)
# -------------------------------------------------------------------------

def get_ekipman_choices(kiralama_objesi=None):
    """
    Kiralama formlarındaki 'Ekipman Seç' alanı için seçenek listesi oluşturur.
    1. Bizim 'bosta' olan makinelerimizi
    2. Tüm 'harici' (tedarikçi) makinelerini
    3. (Düzenleme ise) Şu an kirada olan ve bu forma ait makineleri
    listeye ekler.
    """
    try:
        # 1. ve 2. Adım: Bizim boştaki makinelerimiz + tüm harici makineler
        gecerli_ekipmanlar = Ekipman.query.filter(
            or_(
                # Bizim ve 'bosta' olanlar
                and_(Ekipman.firma_tedarikci_id.is_(None), Ekipman.calisma_durumu == 'bosta'),
                # Tedarikçiye ait olanlar (durumu ne olursa olsun)
                Ekipman.firma_tedarikci_id.isnot(None)
            )
        ).order_by(Ekipman.kod).all()
        
        gecerli_ekipman_id_seti = {e.id for e in gecerli_ekipmanlar}
        choices = [
            (e.id, f"{e.kod} ({e.tipi} / {e.calisma_yuksekligi or 0}m)") 
            for e in gecerli_ekipmanlar
        ]

        # 3. Adım: 'duzenle' ekranı için, mevcut kiradaki makineleri ekle
        if kiralama_objesi:
            for kalem in kiralama_objesi.kalemler:
                if kalem.ekipman_id not in gecerli_ekipman_id_seti and kalem.ekipman:
                    e = kalem.ekipman
                    label = f"{e.kod} ({e.tipi} / {e.calisma_yuksekligi or 0}m) (ŞU AN KİRADA)"
                    choices.append((e.id, label))
                    gecerli_ekipman_id_seti.add(e.id) # Listeye tekrar eklenmesin

        choices.insert(0, ('', '--- Ekipman Seçiniz ---'))
        return choices
        
    except Exception as e:
        print(f"Hata (get_ekipman_choices): {e}")
        return [('', '--- Hata: Ekipmanlar Yüklenemedi ---')]

def get_tedarikci_choices():
    """ 'Nakliye Tedarikçisi' seçme alanı için seçenek listesi oluşturur. """
    try:
        tedarikciler = Firma.query.filter_by(is_tedarikci=True).order_by(Firma.firma_adi).all()
        choices = [(f.id, f.firma_adi) for f in tedarikciler]
        # '0' ID'si 'Pimaks' (yani biz) anlamına gelecek
        choices.insert(0, (0, '--- Pimaks (Maliyet Yok) ---'))
        return choices
    except Exception as e:
        print(f"Hata (get_tedarikci_choices): {e}")
        return [('', '--- Hata: Tedarikçiler Yüklenemedi ---')]

def populate_kiralama_form_choices(form, kiralama_objesi=None):
    """
    KiralamaForm'undaki tüm dinamik SelectField'ları doldurur.
    """
    # 1. Müşteri (Firma) Listesi
    try:
        form.firma_musteri_id.choices = [
            (f.id, f.firma_adi) for f in Firma.query.filter_by(is_musteri=True).order_by(Firma.firma_adi).all()
        ]
    except Exception as e:
        print(f"Hata (populate_kiralama_form_choices - Müşteriler): {e}")
        form.firma_musteri_id.choices = [('', 'Hata: Müşteriler Yüklenemedi')]

    # 2. Alt Formlar için Ekipman ve Tedarikçi Listeleri
    ekipman_choices_list = get_ekipman_choices(kiralama_objesi)
    tedarikci_choices_list = get_tedarikci_choices()
    
    for kalem_form_field in form.kalemler:
        kalem_form_field.form.ekipman_id.choices = ekipman_choices_list
        kalem_form_field.form.nakliye_tedarikci_id.choices = tedarikci_choices_list

# -------------------------------------------------------------------------
# 2. JINJA2 FİLTRESİ (Tarih Formatlama) - Değişiklik Yok
# -------------------------------------------------------------------------
@kiralama_bp.app_template_filter('tarihtr')
def tarihtr(value):
    # ... (Bu fonksiyonun içeriği sizde doğruydu, aynı kalabilir) ...
    if not value:
        return ""
    if isinstance(value, (datetime, date)):
         return value.strftime("%d.%m.%Y")
    if isinstance(value, str):
        try:
            value_dt = datetime.strptime(value, '%Y-%m-%d').date()
            return value_dt.strftime("%d.%m.%Y")
        except ValueError:
            return value 
    return value

# -------------------------------------------------------------------------
# 3. KİRALAMA LİSTELEME (NİHAİ GÜNCELLEME)
# -------------------------------------------------------------------------
@kiralama_bp.route('/index')
@kiralama_bp.route('/') 
def index():
    """ Tüm kiralama kayıtlarını listeler. """
    try:
        # --- GÜNCELLENEN SORGU ('Musteri' -> 'Firma') ---
        kiralamalar = Kiralama.query.options(
            # 'Kiralama.musteri' -> 'Kiralama.firma_musteri'
            joinedload(Kiralama.firma_musteri), 
            joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.ekipman),
            # (Yeni) Nakliye tedarikçisini de yükle
            joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.nakliye_tedarikci)
        ).order_by(Kiralama.id.desc()).all()
        # --- GÜNCELLENEN SORGU SONU ---
        
        return render_template('kiralama/index.html', kiralamalar=kiralamalar)

    except Exception as e:
        flash(f"Kiralamalar yüklenirken bir hata oluştu: {str(e)}", "danger")
        traceback.print_exc()
        return render_template('kiralama/index.html', kiralamalar=[])

# -------------------------------------------------------------------------
# 4. YENİ KİRALAMA EKLEME (NİHAİ GÜNCELLEME)
# -------------------------------------------------------------------------
@kiralama_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    """ Yeni kiralama kaydı oluşturur. (Tüm yeni finansal alanlar dahil) """
    form = KiralamaForm()
    
    # Formdaki tüm 'Select' alanlarını doldur
    populate_kiralama_form_choices(form)
    
    # --- Form Numarası Oluşturma (Bu mantık aynı kalabilir) ---
    if request.method == 'GET':
        try:
            simdiki_yil = datetime.now(timezone.utc).year
            form_prefix = f'PF-{simdiki_yil}/'
            
            son_kiralama = Kiralama.query.filter(
                Kiralama.kiralama_form_no.like(f"{form_prefix}%")
            ).order_by(Kiralama.id.desc()).first()
            
            yeni_numara = 1
            if son_kiralama and son_kiralama.kiralama_form_no:
                son_numara_parcalari = son_kiralama.kiralama_form_no.split('/')
                if len(son_numara_parcalari) > 1 and son_numara_parcalari[-1].isdigit():
                    son_numara_str = son_numara_parcalari[-1]
                    if son_numara_str: 
                        yeni_numara = int(son_numara_str) + 1
                        
            form.kiralama_form_no.data = f'{form_prefix}{yeni_numara}'
        except Exception as e:
            flash(f"Form numarası oluşturulurken hata: {e}", "warning")
            simdiki_yil = datetime.now(timezone.utc).year
            form.kiralama_form_no.data = f'PF-{simdiki_yil}/1'
    # --- Form Numarası Sonu ---

    if form.validate_on_submit():
        # --- ANA KİRALAMA KAYDI (GÜNCELLENDİ) ---
        yeni_kiralama = Kiralama(
            kiralama_form_no=form.kiralama_form_no.data,
            # 'musteri_id' -> 'firma_musteri_id'
            firma_musteri_id=form.firma_musteri_id.data,
            kdv_orani=form.kdv_orani.data
        )
        db.session.add(yeni_kiralama) 
        # --- ANA KİRALAMA KAYDI SONU ---

        try:
            secilen_ekipman_idler = set()
            kalemler_to_add = [] # Kaydetmeden önce kalemleri burada biriktir
            
            # Formdan gelen her bir kalem satırı için
            for kalem_data in form.kalemler.data:
                try:
                    ekipman_id = int(kalem_data['ekipman_id'])
                except (ValueError, TypeError):
                    continue 
                
                if not ekipman_id:
                    continue 
                    
                if ekipman_id in secilen_ekipman_idler:
                    raise ValueError(f"Ekipmanı (ID: {ekipman_id}) aynı formda birden fazla seçemezsiniz.")
                
                # --- YENİ EKİPMAN KONTROLÜ ---
                secilen_ekipman = Ekipman.query.get(ekipman_id)
                if not secilen_ekipman:
                     raise ValueError(f"Ekipman (ID: {ekipman_id}) bulunamadı.")
                
                # Eğer bizim makinemizse VE 'bosta' değilse hata ver
                if secilen_ekipman.firma_tedarikci_id is None and secilen_ekipman.calisma_durumu != 'bosta':
                    raise ValueError(f"Ekipman ({secilen_ekipman.kod}) 'boşta' değil, kiralanamaz.")
                # --- YENİ KONTROL SONU ---
                
                baslangic = kalem_data['kiralama_baslangıcı']
                bitis = kalem_data['kiralama_bitis']

                if baslangic and bitis and bitis < baslangic:
                    raise ValueError(f"Hata: Ekipman {secilen_ekipman.kod} için Bitiş Tarihi ({bitis.strftime('%d.%m.%Y')}), Başlangıç Tarihinden ({baslangic.strftime('%d.%m.%Y')}) önce olamaz.")
                
                baslangic_str = baslangic.strftime("%Y-%m-%d") if baslangic else None
                bitis_str = bitis.strftime("%Y-%m-%d") if bitis else None
                
                # Nakliye tedarikçisini '0' (Pimaks) ise None (NULL) yap
                nakliye_ted_id_data = kalem_data['nakliye_tedarikci_id']
                nakliye_ted_id = nakliye_ted_id_data if nakliye_ted_id_data != 0 else None

                # --- YENİ KİRALAMA KALEMİ (TÜM FİNANSALLAR) ---
                yeni_kalem = KiralamaKalemi(
                    ekipman_id=ekipman_id,
                    kiralama_baslangıcı=baslangic_str,
                    kiralama_bitis=bitis_str,
                    # Ekipman Finansalları
                    kiralama_brm_fiyat=str(kalem_data['kiralama_brm_fiyat'] or 0),
                    kiralama_alis_fiyat=str(kalem_data['kiralama_alis_fiyat'] or 0),
                    # Nakliye Finansalları
                    nakliye_satis_fiyat=str(kalem_data['nakliye_satis_fiyat'] or 0),
                    nakliye_alis_fiyat=str(kalem_data['nakliye_alis_fiyat'] or 0),
                    nakliye_tedarikci_id=nakliye_ted_id
                )
                # --- YENİ KİRALAMA KALEMİ SONU ---
                
                kalemler_to_add.append((yeni_kalem, secilen_ekipman)) 
                secilen_ekipman_idler.add(ekipman_id)

            if not secilen_ekipman_idler:
                flash("En az bir geçerli kiralama kalemi eklemelisiniz.", "danger")
                db.session.rollback()
            else:
                for kalem, ekipman in kalemler_to_add:
                    kalem.kiralama = yeni_kiralama 
                    
                    # SADECE BİZİM makinelerimizin durumunu 'kirada' yap
                    if ekipman.firma_tedarikci_id is None:
                        ekipman.calisma_durumu = "kirada"
                        
                    db.session.add(kalem)
                    
                db.session.commit()
                flash(f"{len(secilen_ekipman_idler)} kalem başarıyla kiralandı!", "success")
                return redirect(url_for('kiralama.index')) 

        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash(f"Veri doğrulama hatası: {str(e)}", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Veritabanı hatası oluştu: {str(e)}", "danger")
            traceback.print_exc()

    else:
        if request.method == 'POST' and form.errors:
            flash("Formda hatalar var, lütfen kontrol edin.", "warning")
            print("FORM HATALARI:", form.errors)
            # Hata durumunda SelectField'ları yeniden doldur
            populate_kiralama_form_choices(form)

    # API'ye göndermek için JSON listeleri
    ekipman_choices_json = json.dumps(get_ekipman_choices())
    tedarikci_choices_json = json.dumps(get_tedarikci_choices())

    return render_template(
        'kiralama/ekle.html', 
        form=form, 
        ekipman_choices_json=ekipman_choices_json,
        tedarikci_choices_json=tedarikci_choices_json
    )

# -------------------------------------------------------------------------
# 5. KİRALAMA KAYDI DÜZENLEME (NİHAİ GÜNCELLEME)
# -------------------------------------------------------------------------
@kiralama_bp.route('/duzenle/<int:kiralama_id>', methods=['GET', 'POST'])
def duzenle(kiralama_id):
    """ Mevcut bir kiralama kaydını (ana form ve kalemleri) düzenler. """
    
    # Kiralama ve ilişkili tüm verileri tek sorguda çek
    kiralama = Kiralama.query.options(
        joinedload(Kiralama.firma_musteri),
        joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.ekipman),
        joinedload(Kiralama.kalemler).joinedload(KiralamaKalemi.nakliye_tedarikci)
    ).get_or_404(kiralama_id)

    form = KiralamaForm(obj=kiralama)
    
    # Formdaki tüm 'Select' alanlarını doldur (mevcut kiralamayı da hesaba kat)
    populate_kiralama_form_choices(form, kiralama_objesi=kiralama)
    
    # --- GET İsteği (Formu Doldurma) ---
    if request.method == 'GET':
        try:
            # Ana form alanlarını doldur
            form.firma_musteri_id.data = kiralama.firma_musteri_id
            form.kdv_orani.data = kiralama.kdv_orani
            
            # Alt form (kalemler) alanlarını DB'den gelen verilerle DÖNÜŞTÜREREK doldur
            for i, kalem in enumerate(kiralama.kalemler):
                kalem_form = form.kalemler[i]
                
                # 1. Tarih Alanları (String -> Date objesi)
                if isinstance(kalem.kiralama_baslangıcı, str):
                    kalem_form.kiralama_baslangıcı.data = datetime.strptime(kalem.kiralama_baslangıcı, '%Y-%m-%d').date()
                if isinstance(kalem.kiralama_bitis, str):
                    kalem_form.kiralama_bitis.data = datetime.strptime(kalem.kiralama_bitis, '%Y-%m-%d').date()
                
                # 2. Finansal Alanlar (String -> Decimal objesi)
                kalem_form.kiralama_brm_fiyat.data = Decimal(kalem.kiralama_brm_fiyat or 0)
                kalem_form.kiralama_alis_fiyat.data = Decimal(kalem.kiralama_alis_fiyat or 0)
                kalem_form.nakliye_satis_fiyat.data = Decimal(kalem.nakliye_satis_fiyat or 0)
                kalem_form.nakliye_alis_fiyat.data = Decimal(kalem.nakliye_alis_fiyat or 0)
                
                # 3. Select Alanları (None -> 0)
                kalem_form.nakliye_tedarikci_id.data = kalem.nakliye_tedarikci_id or 0
                
        except Exception as e:
            flash(f"Form verileri yüklenirken bir hata oluştu: {e}", "danger")
            traceback.print_exc()
    # --- GET İsteği Sonu ---

    # --- POST ISTEGI (Formu Kaydetme) ---
    if form.validate_on_submit():
        
        # Orijinal kalemleri ve ekipmanları takip et (Durum güncellemesi için)
        original_db_kalemler = {k.id: k for k in kiralama.kalemler if not k.sonlandirildi}
        original_ekipman_ids = {
            k.ekipman_id for k in original_db_kalemler.values() 
            if k.ekipman_id and k.ekipman and k.ekipman.firma_tedarikci_id is None # Sadece BİZİM makineler
        }
        
        try:
            # 1. Ana Kiralama Formunu Güncelle
            kiralama.kiralama_form_no = form.kiralama_form_no.data
            kiralama.firma_musteri_id = form.firma_musteri_id.data
            kiralama.kdv_orani = form.kdv_orani.data
            
            form_kalem_idler_map = {} # Formdan gelen kalem ID'lerini ve ekipman ID'lerini tut
            kalemler_to_add = [] # Yeni eklenecek kalemler
            kalemler_to_update = [] # Güncellenecek kalemler
            sonlandirilmis_kalemler = [] # Dokunulmayacak kilitli kalemler
            
            # Formdan gelen kalemleri işle
            for kalem_data in form.kalemler.data:
                
                db_kalem = None
                kalem_id_str = str(kalem_data.get('id') or '')
                
                # A. Kilitli (sonlandırılmış) bir kalem mi?
                if kalem_id_str.isdigit():
                    db_kalem = KiralamaKalemi.query.get(int(kalem_id_str))
                    if db_kalem and db_kalem.sonlandirildi:
                        sonlandirilmis_kalemler.append(db_kalem)
                        form_kalem_idler_map[db_kalem.id] = db_kalem.ekipman_id
                        continue # Bu kalemi atla, işlem yapma

                # B. Geçerli bir ekipman ID'si var mı?
                try:
                    ekipman_id = int(kalem_data['ekipman_id'])
                except (ValueError, TypeError):
                    continue # Boş satır, atla
                
                if not ekipman_id:
                    continue # Boş satır, atla
                
                # C. Tarih ve Finansal Verileri Hazırla
                baslangic = kalem_data['kiralama_baslangıcı']
                bitis = kalem_data['kiralama_bitis']
                if baslangic and bitis and bitis < baslangic:
                    raise ValueError(f"Hata: Bitiş Tarihi ({bitis.strftime('%d.%m.%Y')}), Başlangıç Tarihinden ({baslangic.strftime('%d.%m.%Y')}) önce olamaz.")

                baslangic_str = baslangic.strftime("%Y-%m-%d") if baslangic else None
                bitis_str = bitis.strftime("%Y-%m-%d") if bitis else None
                nakliye_ted_id_data = kalem_data['nakliye_tedarikci_id']
                nakliye_ted_id = nakliye_ted_id_data if nakliye_ted_id_data != 0 else None
                
                # D. Yeni mi, Güncelleme mi?
                if db_kalem and db_kalem.id in original_db_kalemler:
                    # --- GÜNCELLEME ---
                    db_kalem.ekipman_id = ekipman_id
                    db_kalem.kiralama_baslangıcı = baslangic_str
                    db_kalem.kiralama_bitis = bitis_str
                    db_kalem.kiralama_brm_fiyat = str(kalem_data['kiralama_brm_fiyat'] or 0)
                    db_kalem.kiralama_alis_fiyat = str(kalem_data['kiralama_alis_fiyat'] or 0)
                    db_kalem.nakliye_satis_fiyat = str(kalem_data['nakliye_satis_fiyat'] or 0)
                    db_kalem.nakliye_alis_fiyat = str(kalem_data['nakliye_alis_fiyat'] or 0)
                    db_kalem.nakliye_tedarikci_id = nakliye_ted_id
                    
                    form_kalem_idler_map[db_kalem.id] = ekipman_id
                else:
                    # --- YENİ KALEM ---
                    yeni_kalem = KiralamaKalemi(
                        ekipman_id=ekipman_id,
                        kiralama_baslangıcı=baslangic_str,
                        kiralama_bitis=bitis_str,
                        kiralama_brm_fiyat=str(kalem_data['kiralama_brm_fiyat'] or 0),
                        kiralama_alis_fiyat=str(kalem_data['kiralama_alis_fiyat'] or 0),
                        nakliye_satis_fiyat=str(kalem_data['nakliye_satis_fiyat'] or 0),
                        nakliye_alis_fiyat=str(kalem_data['nakliye_alis_fiyat'] or 0),
                        nakliye_tedarikci_id=nakliye_ted_id,
                        sonlandirildi=False
                    )
                    kalemler_to_add.append(yeni_kalem)

            # 2. Ekipman Durumlarını Güncelle (En Zor Kısım)
            
            # Formdan gelen (ve bizim olan) ekipmanların ID'leri
            new_ekipman_ids = set()
            ekipman_listesi = Ekipman.query.filter(
                Ekipman.id.in_([eid for eid in form_kalem_idler_map.values()] + list(original_ekipman_ids))
            ).all()
            ekipman_map = {e.id: e for e in ekipman_listesi}
            
            for ekip_id in form_kalem_idler_map.values():
                ekip = ekipman_map.get(ekip_id)
                if ekip and ekip.firma_tedarikci_id is None: # Bizim makinemizse
                    new_ekipman_ids.add(ekip_id)
            
            # Formdan çıkarılanlar (eski listede var, yeni listede yok)
            ids_to_make_bosta = original_ekipman_ids - new_ekipman_ids
            # Forma yeni eklenenler (yeni listede var, eski listede yok)
            ids_to_make_kirada = new_ekipman_ids - original_ekipman_ids
            
            for ekip_id in ids_to_make_bosta:
                ekip = ekipman_map.get(ekip_id)
                if ekip: ekip.calisma_durumu = 'bosta'
            
            for ekip_id in ids_to_make_kirada:
                ekip = ekipman_map.get(ekip_id)
                if ekip and ekip.calisma_durumu == 'bosta':
                    ekip.calisma_durumu = 'kirada'
                elif ekip and ekip.calisma_durumu != 'bosta':
                    # Harici veya serviste olan bir makine 'bosta' değilse
                    raise ValueError(f"Ekipman ({ekip.kod}) 'boşta' değil, kiralanamaz.")

            # 3. Kiralama Kalemlerini DB'de Güncelle
            
            # Formdan silinen kalemleri DB'den sil
            ids_to_delete = set(original_db_kalemler.keys()) - set(form_kalem_idler_map.keys())
            if ids_to_delete:
                KiralamaKalemi.query.filter(KiralamaKalemi.id.in_(ids_to_delete)).delete(synchronize_session=False)

            # Yeni kalemleri ana kiralamaya ekle
            for kalem in kalemler_to_add:
                kalem.kiralama = kiralama
                db.session.add(kalem)

            db.session.commit()
            flash('Kiralama kaydı başarıyla güncellendi.', 'success')
            return redirect(url_for('kiralama.index'))

        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash(f"Güncelleme sırasında veri hatası: {str(e)}", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Güncelleme sırasında bir veritabanı hatası oluştu: {str(e)}", "danger")
            traceback.print_exc()

    elif request.method == 'POST' and form.errors:
        flash("Formda hatalar var. Lütfen kontrol ediniz.", "danger")
        print("FORM HATALARI:", form.errors)
        # Hata durumunda SelectField'ları yeniden doldur
        populate_kiralama_form_choices(form, kiralama_objesi=kiralama)
        
    # API'ye göndermek için JSON listeleri
    ekipman_choices_json = json.dumps(get_ekipman_choices(kiralama))
    tedarikci_choices_json = json.dumps(get_tedarikci_choices())
    
    return render_template(
        'kiralama/duzelt.html', 
        form=form, 
        kiralama=kiralama,
        ekipman_choices_json=ekipman_choices_json,
        tedarikci_choices_json=tedarikci_choices_json
    )

# -------------------------------------------------------------------------
# 6. KİRALAMA KAYDI SİLME (NİHAİ GÜNCELLEME)
# -------------------------------------------------------------------------
@kiralama_bp.route('/sil/<int:kiralama_id>', methods=['POST'])
def sil(kiralama_id):
    """
    Ana kiralama kaydını ve ona bağlı tüm kalemleri siler.
    İlişkili 'bizim' ekipmanlarımızın durumunu günceller.
    """
    kiralama = Kiralama.query.get_or_404(kiralama_id)
    
    try:
        for kalem in kiralama.kalemler:
            # Sadece 'bizim' olan ve 'kilitli olmayan' ekipmanların durumunu güncelle
            if kalem.ekipman and kalem.ekipman.firma_tedarikci_id is None and not kalem.sonlandirildi:
                kalem.ekipman.calisma_durumu = 'bosta'
        
        # 'cascade="all, delete-orphan"' ayarı sayesinde
        # ana kiralama silindiğinde tüm 'kalemler' otomatik silinir.
        db.session.delete(kiralama)
        db.session.commit()
        
        flash('Kiralama kaydı ve bağlı kalemleri başarıyla silindi.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Kiralama silinirken bir hata oluştu: {str(e)}', 'danger')
        traceback.print_exc() 

    return redirect(url_for('kiralama.index'))

# -------------------------------------------------------------------------
# 7. EKİPMAN FİLTRELEME API (JS için - GÜNCELLENDİ)
# -------------------------------------------------------------------------
@kiralama_bp.route('/api/get-ekipman')
def get_ekipman():
    """ 
    Ekipmanları filtrelemek için JSON verisi sağlar.
    'get_ekipman_choices' fonksiyonunun API versiyonudur.
    """
    try:
        # 'include_id' parametresi, 'duzenle' formunda o an seçili olan
        # (ve belki de 'kirada' olan) ekipmanı listeye dahil etmek için kullanılır.
        include_id = request.args.get('include_id', None, type=int)
        
        # 1. Bizim 'bosta' olanlar + tüm 'harici' olanlar
        query = Ekipman.query.filter(
            or_(
                and_(Ekipman.firma_tedarikci_id.is_(None), Ekipman.calisma_durumu == 'bosta'),
                Ekipman.firma_tedarikci_id.isnot(None)
            )
        )
        
        # --- (Opsiyonel) Sunucu tarafı filtreleme (JS'de de yapılabilir) ---
        tipi = request.args.get('tipi', '', type=str)
        min_yukseklik = request.args.get('min_yukseklik', 0, type=int) 
        if tipi:
             query = query.filter(Ekipman.tipi.ilike(f"%{tipi}%"))
        if min_yukseklik > 0:
             query = query.filter(Ekipman.calisma_yuksekligi >= min_yukseklik)
        # --- Filtreleme sonu ---

        ekipmanlar = query.order_by(Ekipman.kod).all()
        ekipman_id_seti = {e.id for e in ekipmanlar}
        
        # 2. 'include_id' listede yoksa (yani 'kirada' ise) manuel ekle
        if include_id and include_id not in ekipman_id_seti:
             mevcut_ekipman = Ekipman.query.get(include_id)
             if mevcut_ekipman:
                 ekipmanlar.insert(0, mevcut_ekipman) # Listenin başına ekle

        # 3. JSON sonucunu oluştur
        sonuc = [
            {
                "id": e.id, 
                "kod": (
                    f"{e.kod} ({e.tipi} / {e.calisma_yuksekligi or 0}m)" + 
                    (" (HARİCİ)" if e.firma_tedarikci_id else "") +
                    (" (MEVCUT SEÇİM)" if e.id == include_id and e.id not in ekipman_id_seti else "")
                ),
                "is_harici": e.firma_tedarikci_id is not None
            } 
            for e in ekipmanlar
        ]
        
        return jsonify(sonuc)
        
    except Exception as e:
        print(f"API Hatası (get_ekipman): {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e), "details": "Sunucu tarafında bir hata oluştu."}), 500