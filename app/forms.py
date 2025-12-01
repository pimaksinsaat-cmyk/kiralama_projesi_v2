from flask_wtf import FlaskForm
from wtforms import (
    StringField, DecimalField, SelectField, DateField, SubmitField, 
    FormField, FieldList, HiddenField, IntegerField, BooleanField, TextAreaField
)
from wtforms.validators import Optional, InputRequired, NumberRange, ValidationError

secim_hata_mesaji = "Lütfen geçerli bir seçim yapınız."

# Para Birimi Doğrulayıcı
def validate_currency(form, field):
    if field.data:
        clean_value = field.data.replace('.', '').replace(',', '.')
        try:
            float(clean_value)
        except ValueError:
            raise ValidationError("Lütfen geçerli bir sayısal değer giriniz (Örn: 150.000,00).")

# 1. FirmaForm
class FirmaForm(FlaskForm):
    firma_adi = StringField('Firma Adı', validators=[InputRequired()])
    yetkili_adi = StringField('Yetkili Kişi', validators=[InputRequired()])
    iletisim_bilgileri = TextAreaField('Adres / İletişim', validators=[InputRequired()])
    vergi_dairesi = StringField('Vergi Dairesi', validators=[InputRequired()])
    vergi_no = StringField('Vergi Numarası', validators=[InputRequired()])
    is_musteri = BooleanField('Bu bir Müşteri mi?', default=True)
    is_tedarikci = BooleanField('Bu bir Tedarikçi mi?', default=False)
    submit = SubmitField('Kaydet')

# 2. EkipmanForm
class EkipmanForm(FlaskForm):
    kod = StringField('Makine Kodu', validators=[InputRequired()])
    yakit = StringField('Yakıt Türü', validators=[InputRequired()])
    tipi = StringField('Makine Tipi', validators=[InputRequired()])
    marka = StringField('Makine Markası', validators=[InputRequired()])
    model = StringField('Makine Modeli', validators=[InputRequired()])
    seri_no = StringField('Makine Seri No', validators=[InputRequired()])
    calisma_yuksekligi = StringField('Çalışma Yüksekliği (m)', validators=[InputRequired()]) 
    kaldirma_kapasitesi = StringField('Kaldırma Kapasitesi (kg)', validators=[InputRequired()])
    uretim_tarihi = StringField('Üretim Tarihi (Yıl)', validators=[InputRequired()])
    giris_maliyeti = StringField('Giriş Maliyeti (Satın Alma)', validators=[Optional(), validate_currency])
    para_birimi = SelectField(
        'Para Birimi', 
        choices=[('TRY', 'TL (Türk Lirası)'), ('USD', 'USD (Amerikan Doları)'), ('EUR', 'EUR (Euro)')],
        default='TRY',
        validators=[InputRequired()]
    )
    submit = SubmitField('Kaydet')

# 3. KiralamaKalemiForm
class KiralamaKalemiForm(FlaskForm):
    class Meta: csrf = False 
    id = HiddenField('Kalem ID')
    dis_tedarik_ekipman = BooleanField("Dış Tedarik Ekipman?")
    ekipman_id = SelectField('Pimaks Filosu', coerce=int, default='0', validators=[Optional()])
    harici_ekipman_tedarikci_id = SelectField('Ekipman Tedarikçisi', coerce=int, default='0', validators=[Optional()])
    harici_ekipman_tipi = StringField('Harici Ekipman Tipi', validators=[Optional()])
    harici_ekipman_marka = StringField('Harici Ekipman Markası', validators=[Optional()])
    harici_ekipman_model = StringField('Harici Ekipman Modeli', validators=[Optional()])
    harici_ekipman_seri_no = StringField('Harici Seri No', validators=[Optional()])
    harici_ekipman_calisma_yuksekligi = IntegerField('Çalışma Yüksekliği (m)', validators=[Optional()])
    harici_ekipman_kaldirma_kapasitesi = IntegerField('Kaldırma Kapasitesi (kg)', validators=[Optional()])
    kiralama_baslangıcı = DateField('Başlangıç Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    kiralama_bitis = DateField('Bitiş Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    kiralama_brm_fiyat = DecimalField('Ekipman Satış Fiyatı (Gelir)', validators=[InputRequired()], default=0.0)
    kiralama_alis_fiyat = DecimalField('Ekipman Alış Fiyatı (Maliyet)', validators=[Optional()], default=0.0)
    dis_tedarik_nakliye = BooleanField("Harici Nakliye?")
    nakliye_satis_fiyat = DecimalField('Nakliye Satış Fiyatı (Gelir)', validators=[Optional()], default=0.0)
    nakliye_alis_fiyat = DecimalField('Nakliye Alış Fiyatı (Maliyet)', validators=[Optional()], default=0.0)
    nakliye_tedarikci_id = SelectField('Nakliye Tedarikçisi', coerce=int, default='0', validators=[Optional()])

# 4. KiralamaForm
class KiralamaForm(FlaskForm):
    kiralama_form_no = StringField('Kiralama Form No', validators=[Optional()])
    firma_musteri_id = SelectField('Müşteri (Firma) Seç', coerce=int, default='0', validators=[NumberRange(min=1, message=secim_hata_mesaji)])
    kdv_orani = IntegerField('KDV Oranı (%)', default=20, validators=[InputRequired(), NumberRange(min=0, max=100)])
    doviz_kuru_usd = DecimalField('USD Kuru (TCMB)', places=4, default=0.0, validators=[Optional()])
    doviz_kuru_eur = DecimalField('EUR Kuru (TCMB)', places=4, default=0.0, validators=[Optional()])
    kalemler = FieldList(FormField(KiralamaKalemiForm), min_entries=1)
    submit = SubmitField('Kaydet')

# 5. OdemeForm (DÜZELTİLDİ: Tutar StringField oldu)
class OdemeForm(FlaskForm):
    firma_musteri_id = SelectField('Ödeme Yapan Müşteri (Firma)', coerce=int, default='0', validators=[NumberRange(min=1, message=secim_hata_mesaji)])
    kasa_id = SelectField('Giriş Yapılacak Kasa/Banka', coerce=int, default='0', validators=[NumberRange(min=1, message="Lütfen bir kasa/banka seçiniz.")])
    tarih = DateField('Ödeme Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    alacakli_musteri_id = SelectField('Ödeme Yapılan (Firma)', coerce=int, default='0', validators=[NumberRange(min=1, message=secim_hata_mesaji)])



    # DÜZELTME: StringField ve validate_currency
    tutar = StringField('Ödeme Tutarı', validators=[InputRequired(), validate_currency])
    
    fatura_no = StringField('Makbuz/Dekont No', validators=[Optional()])
    vade_tarihi = DateField('Vade Tarihi (Opsiyonel)', format='%Y-%m-%d', validators=[Optional()])
    aciklama = StringField('Açıklama (Örn: EFT, Nakit Tahsilat)', validators=[Optional()])
    submit = SubmitField('Ödemeyi Kaydet')

# 6. HizmetKaydiForm (DÜZELTİLDİ: Tutar StringField oldu)
class HizmetKaydiForm(FlaskForm):
    firma_id = SelectField('İlgili Firma', coerce=int, default='0', validators=[NumberRange(min=1, message=secim_hata_mesaji)])
    tarih = DateField('İşlem Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    
    # DÜZELTME: StringField ve validate_currency
    tutar = StringField('Tutar (KDV Dahil)', validators=[InputRequired(), validate_currency])
    
    aciklama = StringField('Hizmet/Ürün Açıklaması', validators=[InputRequired()])
    yon = SelectField('İşlem Yönü', choices=[('giden', 'Hizmet/Ürün Satışı (Firmayı Borçlandır - Gelir)'), ('gelen', 'Hizmet/Ürün Alımı (Firmayı Alacaklandır - Gider)')], validators=[InputRequired()])
    fatura_no = StringField('Fatura No', validators=[Optional()])
    vade_tarihi = DateField('Vade Tarihi', format='%Y-%m-%d', validators=[Optional()])
    submit = SubmitField('Hizmet Kaydını Oluştur')

# 7. StokKartiForm
class StokKartiForm(FlaskForm):
    parca_kodu = StringField('Parça Kodu', validators=[InputRequired()])
    parca_adi = StringField('Parça Adı', validators=[InputRequired()])
    mevcut_stok = IntegerField('Mevcut Stok Adedi', default=0, validators=[InputRequired()])
    varsayilan_tedarikci_id = SelectField('Varsayılan Tedarikçi', coerce=int, default='0', validators=[Optional()])
    submit = SubmitField('Stok Kartını Kaydet')

# 8. KullanilanParcaForm
class KullanilanParcaForm(FlaskForm):
    class Meta: csrf = False
    stok_karti_id = SelectField('Kullanılan Parça', coerce=int, default='0', validators=[NumberRange(min=1, message=secim_hata_mesaji)])
    kullanilan_adet = IntegerField('Adet', default=1, validators=[InputRequired()])

# 9. BakimKaydiForm
class BakimKaydiForm(FlaskForm):
    ekipman_id = SelectField('Bakım Yapılan Ekipman', coerce=int, default='0', validators=[NumberRange(min=1, message=secim_hata_mesaji)])
    tarih = DateField('Bakım Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    aciklama = TextAreaField('Yapılan İşlemlerin Açıklaması', validators=[InputRequired()])
    calisma_saati = IntegerField('Ekipman Çalışma Saati (Opsiyonel)', validators=[Optional()])
    kullanilan_parcalar = FieldList(FormField(KullanilanParcaForm), min_entries=0)
    submit = SubmitField('Bakım Kaydını Tamamla')

# 10. KasaForm
class KasaForm(FlaskForm):
    kasa_adi = StringField('Hesap Adı (Örn: Merkez Kasa, Garanti TL)', validators=[InputRequired()])
    tipi = SelectField('Hesap Tipi', choices=[('nakit', 'Nakit Kasa'), ('banka', 'Banka Hesabı')], default='banka', validators=[InputRequired()])
    para_birimi = SelectField('Para Birimi', choices=[('TRY', 'TL (Türk Lirası)'), ('USD', 'USD (Dolar)'), ('EUR', 'EUR (Euro)')], default='TRY', validators=[InputRequired()])
    bakiye = DecimalField('Açılış Bakiyesi', default=0.0, validators=[Optional()])
    submit = SubmitField('Kaydet')