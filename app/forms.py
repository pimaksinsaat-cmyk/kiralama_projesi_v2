from flask_wtf import FlaskForm
from wtforms import (
    StringField, 
    DecimalField, 
    SelectField, 
    DateField, 
    SubmitField, 
    FormField,   
    FieldList,   
    HiddenField,
    IntegerField,
    BooleanField,
    TextAreaField,
    SelectMultipleField # Yeni eklendi (belki lazım olur)
)
from wtforms.validators import Optional, InputRequired, NumberRange

# -------------------------------------------------------------------------
# 1. GÜNCELLENEN FORM: 'FirmaForm' (Eski 'MusteriForm')
# -------------------------------------------------------------------------
class FirmaForm(FlaskForm):
    """
    Yeni firma (müşteri ve/veya tedarikçi) eklemek için kullanılacak form.
    """
    firma_adi = StringField('Firma Adı', validators=[InputRequired()])
    yetkili_adi = StringField('Yetkili Kişi', validators=[InputRequired()])
    iletisim_bilgileri = TextAreaField('Adres / İletişim', validators=[InputRequired()])
    vergi_dairesi = StringField('Vergi Dairesi', validators=[InputRequired()])
    vergi_no = StringField('Vergi Numarası', validators=[InputRequired()])
    
    is_musteri = BooleanField('Bu bir Müşteri mi?', default=True)
    is_tedarikci = BooleanField('Bu bir Tedarikçi mi?', default=False)
    
    submit = SubmitField('Kaydet')


# -------------------------------------------------------------------------
# 2. GÜNCELLENEN FORM: 'EkipmanForm'
# -------------------------------------------------------------------------
class EkipmanForm(FlaskForm):
    """
    Yeni makine (ekipman) eklemek için kullanılacak form.
    """
    kod = StringField('Makine Kodu', validators=[InputRequired()])
    yakit = StringField('Yakıt Türü', validators=[InputRequired()])
    tipi = StringField('Makine Tipi', validators=[InputRequired()])
    marka = StringField('Makine Markası', validators=[InputRequired()])
    seri_no = StringField('Makine Seri No', validators=[InputRequired()])
    calisma_yuksekligi = StringField('Çalışma Yüksekliği (m)', validators=[InputRequired()]) 
    kaldirma_kapasitesi = StringField('Kaldırma Kapasitesi (kg)', validators=[InputRequired()])
    uretim_tarihi = StringField('Üretim Tarihi (Örn: 2023-10-31)', validators=[InputRequired()])
    
    giris_maliyeti = DecimalField('Giriş Maliyeti (Satın Alma)', default=0.0, validators=[Optional()])
    
    # 'choices' listesi 'routes.py' içinde doldurulacak.
    firma_tedarikci_id = SelectField('Tedarikçi Firma (Harici ise)', default=0, coerce=int, validators=[Optional()])

    submit = SubmitField('Kaydet')


# -------------------------------------------------------------------------
# 3. NİHAİ FORM: 'KiralamaKalemiForm' (Alt Form)
# -------------------------------------------------------------------------
class KiralamaKalemiForm(FlaskForm):
    """
    Ana Kiralama formundaki her bir ekipman satırını temsil eder.
    """
    class Meta:
        csrf = False 

    id = HiddenField('Kalem ID')

    ekipman_id = SelectField('Ekipman Seç', validators=[InputRequired()])
    
    kiralama_baslangıcı = DateField('Başlangıç Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    kiralama_bitis = DateField('Bitiş Tarihi', format='%Y-%m-%d', validators=[InputRequired()])

    # --- Ekipman Finansalları ---
    kiralama_brm_fiyat = DecimalField('Ekipman Satış Fiyatı (Gelir)', validators=[InputRequired()], default=0.0)
    kiralama_alis_fiyat = DecimalField('Ekipman Alış Fiyatı (Maliyet)', validators=[Optional()], default=0.0)

    # --- Nakliye Finansalları ---
    nakliye_satis_fiyat = DecimalField('Nakliye Satış Fiyatı (Gelir)', validators=[Optional()], default=0.0)
    nakliye_alis_fiyat = DecimalField('Nakliye Alış Fiyatı (Maliyet)', validators=[Optional()], default=0.0)
    
    # 'choices' listesi 'routes.py' içinde doldurulacak.
    nakliye_tedarikci_id = SelectField('Nakliye Tedarikçisi', coerce=int, validators=[Optional()])


# -------------------------------------------------------------------------
# 4. GÜNCELLENEN FORM: 'KiralamaForm' (Ana Form)
# -------------------------------------------------------------------------
class KiralamaForm(FlaskForm):
    """
    Ana Kiralama Formu.
    """
    kiralama_form_no = StringField('Kiralama Form No', validators=[Optional()])
    
    # ÖNEMLİ: 'musteri_id' idi, 'firma_musteri_id' oldu.
    # 'choices' listesi 'routes.py' içinde doldurulacak.
    firma_musteri_id = SelectField('Müşteri (Firma) Seç', coerce=int, validators=[InputRequired()])

    kdv_orani = IntegerField(
        'KDV Oranı (%)', 
        default=20, 
        validators=[InputRequired(), NumberRange(min=0, max=100)]
    )

    kalemler = FieldList(FormField(KiralamaKalemiForm), min_entries=1)
    
    submit = SubmitField('Kaydet')


# -------------------------------------------------------------------------
# 5. YENİ FORM: 'OdemeForm' (Cari Hesap - Alacak)
# -------------------------------------------------------------------------
class OdemeForm(FlaskForm):
    """
    Müşterilerden (Firmalardan) ödeme/tahsilat almak için form.
    """
    # 'choices' listesi 'routes.py' içinde doldurulacak.
    firma_musteri_id = SelectField('Ödeme Yapan Müşteri (Firma)', coerce=int, validators=[InputRequired()])
    tarih = DateField('Ödeme Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    tutar = DecimalField('Ödeme Tutarı', validators=[InputRequired()])
    aciklama = StringField('Açıklama (Örn: EFT, Fatura No)', validators=[Optional()])
    submit = SubmitField('Ödemeyi Kaydet')


# -------------------------------------------------------------------------
# 6. YENİ FORM: 'HizmetKaydiForm' (Cari Hesap - Borç/Alacak Jokeri)
# -------------------------------------------------------------------------
class HizmetKaydiForm(FlaskForm):
    """
    Kiralama dışı bağımsız hizmetleri (servis, parça alımı, harici nakliye)
    kaydetmek için çift yönlü form.
    """
    # 'choices' listesi 'routes.py' içinde doldurulacak.
    firma_id = SelectField('İlgili Firma', coerce=int, validators=[InputRequired()])
    tarih = DateField('Hizmet Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    tutar = DecimalField('Hizmet Tutarı (KDV Hariç)', validators=[InputRequired()])
    aciklama = StringField('Hizmet Açıklaması', validators=[InputRequired()])
    
    yon = SelectField(
        'İşlem Yönü', 
        choices=[
            ('giden', 'Hizmet/Ürün Satışı Yaptık (Firmayı Borçlandır)'),
            ('gelen', 'Hizmet/Ürün Alımı Yaptık (Firmayı Alacaklandır)')
        ],
        validators=[InputRequired()]
    )
    submit = SubmitField('Hizmet Kaydını Oluştur')

# -------------------------------------------------------------------------
# 7. YENİ FORM: 'StokKartiForm' (Stok Modülü)
# -------------------------------------------------------------------------
class StokKartiForm(FlaskForm):
    """
    Yeni bir yedek parça (stok kartı) tanımlamak için form.
    """
    parca_kodu = StringField('Parça Kodu', validators=[InputRequired()])
    parca_adi = StringField('Parça Adı', validators=[InputRequired()])
    mevcut_stok = IntegerField('Mevcut Stok Adedi', default=0, validators=[InputRequired()])
    
    # 'choices' listesi 'routes.py' içinde doldurulacak.
    varsayilan_tedarikci_id = SelectField('Varsayılan Tedarikçi', coerce=int, validators=[Optional()])
    
    submit = SubmitField('Stok Kartını Kaydet')

# -------------------------------------------------------------------------
# 8. YENİ FORM: 'KullanilanParcaForm' (Servis Alt Formu)
# -------------------------------------------------------------------------
class KullanilanParcaForm(FlaskForm):
    """
    'BakimKaydiForm' içinde kullanılacak alt form (FieldList).
    """
    class Meta:
        csrf = False

    # 'choices' listesi 'routes.py' içinde doldurulacak.
    stok_karti_id = SelectField('Kullanılan Parça', coerce=int, validators=[InputRequired()])
    kullanilan_adet = IntegerField('Adet', default=1, validators=[InputRequired()])

# -------------------------------------------------------------------------
# 9. YENİ FORM: 'BakimKaydiForm' (Servis Ana Formu)
# -------------------------------------------------------------------------
class BakimKaydiForm(FlaskForm):
    """
    Bir ekipmana bakım kaydı girmek için ana form.
    """
    # 'choices' listesi 'routes.py' içinde doldurulacak.
    ekipman_id = SelectField('Bakım Yapılan Ekipman', coerce=int, validators=[InputRequired()])
    tarih = DateField('Bakım Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    aciklama = TextAreaField('Yapılan İşlemlerin Açıklaması', validators=[InputRequired()])
    calisma_saati = IntegerField('Ekipman Çalışma Saati (Opsiyonel)', validators=[Optional()])

    # Stoktan kullanılan parçaları girmek için alt form listesi
    kullanilan_parcalar = FieldList(FormField(KullanilanParcaForm), min_entries=0)

    submit = SubmitField('Bakım Kaydını Tamamla')