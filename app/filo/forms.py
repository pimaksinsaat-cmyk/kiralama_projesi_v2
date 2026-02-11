from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField, SelectField, TextAreaField, DateField, FieldList, FormField
from wtforms.validators import DataRequired, InputRequired, Length, Email, Optional, ValidationError
from wtforms.validators import  NumberRange

# Modellerin yeni adresleri:
from app.filo.models import Ekipman, BakimKaydi, StokKarti

from app.utils import validate_currency, secim_hata_mesaji

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