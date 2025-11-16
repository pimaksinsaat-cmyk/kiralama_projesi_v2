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
    TextAreaField
)
from wtforms.validators import Optional, InputRequired, NumberRange

# -------------------------------------------------------------------------
# 1. FirmaForm (Bu doğru, değişiklik yok)
# -------------------------------------------------------------------------
class FirmaForm(FlaskForm):
    firma_adi = StringField('Firma Adı', validators=[InputRequired()])
    yetkili_adi = StringField('Yetkili Kişi', validators=[InputRequired()])
    iletisim_bilgileri = TextAreaField('Adres / İletişim', validators=[InputRequired()])
    vergi_dairesi = StringField('Vergi Dairesi', validators=[InputRequired()])
    vergi_no = StringField('Vergi Numarası', validators=[InputRequired()])
    is_musteri = BooleanField('Bu bir Müşteri mi?', default=True)
    is_tedarikci = BooleanField('Bu bir Tedarikçi mi?', default=False)
    submit = SubmitField('Kaydet')


# -------------------------------------------------------------------------
# 2. EkipmanForm (DÜZELTİLDİ - Sadece Pimaks Makineleri için)
# -------------------------------------------------------------------------
class EkipmanForm(FlaskForm):
    """
    Yeni Pimaks makinesi (ekipman) eklemek için kullanılacak form.
    Tedarikçi alanı kaldırıldı.
    """
    kod = StringField('Makine Kodu', validators=[InputRequired()])
    yakit = StringField('Yakıt Türü', validators=[InputRequired()])
    tipi = StringField('Makine Tipi', validators=[InputRequired()])
    marka = StringField('Makine Markası', validators=[InputRequired()])
    seri_no = StringField('Makine Seri No', validators=[InputRequired()])
    calisma_yuksekligi = StringField('Çalışma Yüksekliği (m)', validators=[InputRequired()]) 
    kaldirma_kapasitesi = StringField('Kaldırma Kapasitesi (kg)', validators=[InputRequired()])
    uretim_tarihi = StringField('Üretim Tarihi (Yıl)', validators=[InputRequired()])
    
    # SADECE Giriş Maliyeti kaldı (Bu bizim makinemizin maliyeti)
    giris_maliyeti = DecimalField('Giriş Maliyeti (Satın Alma)', default=0.0, validators=[Optional()])
    
    # Tedarikçi alanı (firma_tedarikci_id) buradan KALDIRILDI.
    
    submit = SubmitField('Kaydet')


# -------------------------------------------------------------------------
# 3. KiralamaKalemiForm (NİHAİ VE EN ÖNEMLİ DÜZELTME)
# Sizin "Dış Tedarik" vizyonunuzu destekler
# -------------------------------------------------------------------------
class KiralamaKalemiForm(FlaskForm):
    """
    Ana Kiralama formundaki her bir ekipman satırını temsil eder.
    "Dış Tedarik" (Ekipman ve Nakliye) mantığını içerir.
    """
    class Meta:
        csrf = False 

    id = HiddenField('Kalem ID') # 'duzenle' formu için

    # --- ANAHTAR 1: Dış Tedarik Ekipman? ---
    dis_tedarik_ekipman = BooleanField("Dış Tedarik Ekipman?")

    # Alan 1a: Bizim Filomuz (dis_tedarik_ekipman = False ise görünür)
    # 'routes.py'da doldurulacak (SADECE BİZİM BOŞTA OLANLAR)
    ekipman_id = SelectField('Pimaks Filosu', coerce=int, validators=[Optional()])
    
    # Alan 1b: Harici Ekipman Bilgileri (dis_tedarik_ekipman = True ise görünür)
    # 'routes.py'da doldurulacak (TÜM TEDARİKÇİLER)
    harici_ekipman_tedarikci_id = SelectField('Ekipman Tedarikçisi', coerce=int, validators=[Optional()])
    harici_ekipman_tipi = StringField('Harici Ekipman Tipi', validators=[Optional()])
    harici_ekipman_seri_no = StringField('Harici Seri No', validators=[Optional()])

    # --- Ortak Alanlar (Her iki durumda da görünür) ---
    kiralama_baslangıcı = DateField('Başlangıç Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    kiralama_bitis = DateField('Bitiş Tarihi', format='%Y-%m-%d', validators=[InputRequired()])

    # --- Ekipman Finansalları ---
    kiralama_brm_fiyat = DecimalField('Ekipman Satış Fiyatı (Gelir)', validators=[InputRequired()], default=0.0)
    # (dis_tedarik_ekipman = True ise görünür)
    kiralama_alis_fiyat = DecimalField('Ekipman Alış Fiyatı (Maliyet)', validators=[Optional()], default=0.0)

    # --- ANAHTAR 2: Dış Tedarik Nakliye? ---
    dis_tedarik_nakliye = BooleanField("Harici Nakliye?")

    # --- Nakliye Finansalları ---
    # (Her zaman görünür)
    nakliye_satis_fiyat = DecimalField('Nakliye Satış Fiyatı (Gelir)', validators=[Optional()], default=0.0)
    # (dis_tedarik_nakliye = True ise görünür)
    nakliye_alis_fiyat = DecimalField('Nakliye Alış Fiyatı (Maliyet)', validators=[Optional()], default=0.0)
    # (dis_tedarik_nakliye = True ise görünür)
    # 'routes.py'da doldurulacak (TÜM TEDARİKÇİLER)
    nakliye_tedarikci_id = SelectField('Nakliye Tedarikçisi', coerce=int, validators=[Optional()])


# -------------------------------------------------------------------------
# 4. KiralamaForm (Ana Form) (Bu doğru, değişiklik yok)
# -------------------------------------------------------------------------
class KiralamaForm(FlaskForm):
    kiralama_form_no = StringField('Kiralama Form No', validators=[Optional()])
    firma_musteri_id = SelectField('Müşteri (Firma) Seç', coerce=int, validators=[InputRequired()])
    kdv_orani = IntegerField(
        'KDV Oranı (%)', 
        default=20, 
        validators=[InputRequired(), NumberRange(min=0, max=100)]
    )
    kalemler = FieldList(FormField(KiralamaKalemiForm), min_entries=1)
    submit = SubmitField('Kaydet')

# -------------------------------------------------------------------------
# 5. OdemeForm (Bu doğru, değişiklik yok)
# -------------------------------------------------------------------------
class OdemeForm(FlaskForm):
    firma_musteri_id = SelectField('Ödeme Yapan Müşteri (Firma)', coerce=int, validators=[InputRequired()])
    tarih = DateField('Ödeme Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    tutar = DecimalField('Ödeme Tutarı', validators=[InputRequired()])
    aciklama = StringField('Açıklama (Örn: EFT, Fatura No)', validators=[Optional()])
    submit = SubmitField('Ödemeyi Kaydet')

# -------------------------------------------------------------------------
# 6. HizmetKaydiForm (Bu doğru, değişiklik yok)
# -------------------------------------------------------------------------
class HizmetKaydiForm(FlaskForm):
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
# 7. StokKartiForm (Bu doğru, değişiklik yok)
# -------------------------------------------------------------------------
class StokKartiForm(FlaskForm):
    parca_kodu = StringField('Parça Kodu', validators=[InputRequired()])
    parca_adi = StringField('Parça Adı', validators=[InputRequired()])
    mevcut_stok = IntegerField('Mevcut Stok Adedi', default=0, validators=[InputRequired()])
    varsayilan_tedarikci_id = SelectField('Varsayılan Tedarikçi', coerce=int, validators=[Optional()])
    submit = SubmitField('Stok Kartını Kaydet')

# -------------------------------------------------------------------------
# 8. KullanilanParcaForm (Bu doğru, değişiklik yok)
# -------------------------------------------------------------------------
class KullanilanParcaForm(FlaskForm):
    class Meta:
        csrf = False
    stok_karti_id = SelectField('Kullanılan Parça', coerce=int, validators=[InputRequired()])
    kullanilan_adet = IntegerField('Adet', default=1, validators=[InputRequired()])

# -------------------------------------------------------------------------
# 9. BakimKaydiForm (Bu doğru, değişiklik yok)
# -------------------------------------------------------------------------
class BakimKaydiForm(FlaskForm):
    ekipman_id = SelectField('Bakım Yapılan Ekipman', coerce=int, validators=[InputRequired()])
    tarih = DateField('Bakım Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    aciklama = TextAreaField('Yapılan İşlemlerin Açıklaması', validators=[InputRequired()])
    calisma_saati = IntegerField('Ekipman Çalışma Saati (Opsiyonel)', validators=[Optional()])
    kullanilan_parcalar = FieldList(FormField(KullanilanParcaForm), min_entries=0)
    submit = SubmitField('Bakım Kaydını Tamamla')