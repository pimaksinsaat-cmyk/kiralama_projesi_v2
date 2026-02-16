from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField, DateField, SelectField, DecimalField, HiddenField, BooleanField, FieldList, FormField
from wtforms.validators import DataRequired, Optional, InputRequired, NumberRange, ValidationError
from app.utils import validate_currency, secim_hata_mesaji

# 1. KALEM FORMU (Satır Bazlı Detaylar)
class KiralamaKalemiForm(FlaskForm):
    class Meta: 
        csrf = False # FieldList içinde performans ve hata yönetimi için kapalı
    
    id = HiddenField('Kalem ID')
    
    # --- MAKİNE SEÇİM VE DIŞ TEDARİK ---
    # JS tarafı 0/1 gönderdiği için IntegerField kullanımı senin orijinal yapınla daha uyumlu
    dis_tedarik_ekipman = IntegerField("Dış Tedarik?", default=0)
    ekipman_id = SelectField('Pimaks Filosu', coerce=int, validators=[Optional()])
    
    # Harici Ekipman Detayları (Yeni İskeletimiz İçin Şart)
    harici_ekipman_tedarikci_id = SelectField('Ekipman Tedarikçisi', coerce=int, default=0, validators=[Optional()])
    harici_ekipman_tipi = StringField('Harici Ekipman Tipi', validators=[Optional()])
    harici_ekipman_marka = StringField('Harici Ekipman Markası', validators=[Optional()])
    harici_ekipman_model = StringField('Harici Ekipman Modeli', validators=[Optional()])
    harici_ekipman_seri_no = StringField('Harici Seri No', validators=[Optional()])
    harici_ekipman_calisma_yuksekligi = IntegerField('Çalışma Yüksekliği (m)', validators=[Optional()])
    harici_ekipman_kaldirma_kapasitesi = IntegerField('Kaldırma Kapasitesi (kg)', validators=[Optional()])
    harici_ekipman_uretim_tarihi = IntegerField('Üretim Yılı', validators=[Optional()])
    
    # --- TARİHLER ---
    kiralama_baslangici = DateField('Başlangıç Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    kiralama_bitis = DateField('Bitiş Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    
    # --- FİYATLAR (Orijinal Hassasiyet Korundu) ---
    kiralama_brm_fiyat = DecimalField('Günlük Satış Fiyatı', places=2, validators=[InputRequired()], default=0.0)
    kiralama_alis_fiyat = DecimalField('Alış Fiyatı (Maliyet)', places=2, validators=[Optional()], default=0.0)
    
    # --- NAKLİYE ---
    dis_tedarik_nakliye = IntegerField("Harici Nakliye?", default=0)
    nakliye_satis_fiyat = DecimalField('Nakliye Satış Fiyatı', places=2, validators=[Optional()], default=0.0)
    nakliye_alis_fiyat = DecimalField('Nakliye Alış Fiyatı', places=2, validators=[Optional()], default=0.0)
    nakliye_tedarikci_id = SelectField('Nakliye Tedarikçisi', coerce=int, default=0, validators=[Optional()])
    
    # ÖZ MAL NAKLİYE ARACI (Yeni Gereksinimimiz)
    nakliye_araci_id = SelectField('Nakliye Aracı (Öz Mal)', coerce=int, default=0, validators=[Optional()])

    # --- ÖZEL DOĞRULAYICI: Tarih Kontrolü (Orijinal Mantık) ---
    def validate_kiralama_bitis(self, field):
        if self.kiralama_baslangici.data and field.data:
            if field.data < self.kiralama_baslangici.data:
                raise ValidationError("Bitiş tarihi başlangıç tarihinden önce olamaz!")

# 2. ANA KİRALAMA FORMU
class KiralamaForm(FlaskForm):
    kiralama_form_no = StringField('Kiralama Form No', validators=[Optional()])
    
    # Müşteri Seçimi (Özel hata mesajı korundu)
    firma_musteri_id = SelectField('Müşteri (Firma) Seç', coerce=int, default=0, 
                                 validators=[NumberRange(min=1, message=secim_hata_mesaji)])
    
    kdv_orani = IntegerField('KDV Oranı (%)', default=20, 
                            validators=[InputRequired(), NumberRange(min=0, max=100)])
    
    # Kur Hassasiyeti (4 basamak korundu)
    doviz_kuru_usd = DecimalField('USD Kuru (TCMB)', places=4, default=0.0, validators=[Optional()])
    doviz_kuru_eur = DecimalField('EUR Kuru (TCMB)', places=4, default=0.0, validators=[Optional()])
    
    # HATA DÜZELTME: min_entries=1 yapıldı. 
    # ekle.html içinde form.kalemler[0] öğesine erişildiği için bu listenin boş olmaması gerekir.
    kalemler = FieldList(FormField(KiralamaKalemiForm), min_entries=1)
    submit = SubmitField('Kiralama Formunu Kaydet')