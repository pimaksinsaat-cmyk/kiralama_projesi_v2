
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField, DateField, SelectField, DecimalField,HiddenField,DecimalField,DateField,BooleanField,FieldList,FormField
from wtforms.validators import DataRequired,Optional,InputRequired,NumberRange
# Modelin yeni adresi:
from app.kiralama.models import Kiralama

from app.utils import validate_currency, secim_hata_mesaji

# 3. KiralamaKalemiForm
class KiralamaKalemiForm(FlaskForm):
    class Meta: csrf = False 
    id = HiddenField('Kalem ID')
    dis_tedarik_ekipman = IntegerField("Dış Tedarik Ekipman?", default=0)
    ekipman_id = SelectField('Pimaks Filosu', coerce=int, validators=[Optional()])
    harici_ekipman_tedarikci_id = SelectField('Ekipman Tedarikçisi', coerce=int, default='0', validators=[Optional()])
    harici_ekipman_tipi = StringField('Harici Ekipman Tipi', validators=[Optional()])
    harici_ekipman_marka = StringField('Harici Ekipman Markası', validators=[Optional()])
    harici_ekipman_model = StringField('Harici Ekipman Modeli', validators=[Optional()])
    harici_ekipman_seri_no = StringField('Harici Seri No', validators=[Optional()])
    harici_ekipman_calisma_yuksekligi = IntegerField('Çalışma Yüksekliği (m)', validators=[Optional()])
    harici_ekipman_kaldirma_kapasitesi = IntegerField('Kaldırma Kapasitesi (kg)', validators=[Optional()])
    harici_ekipman_uretim_tarihi = IntegerField('Üretim Yılı', validators=[Optional()])
    kiralama_baslangici = DateField('Başlangıç Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    kiralama_bitis = DateField('Bitiş Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    kiralama_brm_fiyat = DecimalField('Ekipman Satış Fiyatı (Gelir)', validators=[InputRequired()], default=0.0)
    kiralama_alis_fiyat = DecimalField('Ekipman Alış Fiyatı (Maliyet)', validators=[Optional()], default=0.0)
    dis_tedarik_nakliye = IntegerField("Harici Nakliye?", default=0)
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