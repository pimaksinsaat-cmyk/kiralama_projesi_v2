# app/nakliyeler/forms.py
from flask_wtf import FlaskForm
from app.utils import validate_currency # Ortak doğrulayıcımız
from app.firmalar.models import Firma   # Firma listesini çekeceğiz

# Toplu import (Kopya kağıdımızdan)
from wtforms import (
    StringField, TextAreaField, IntegerField, DecimalField, DateField, 
    SelectField, SubmitField,FloatField,DecimalRangeField
)
from wtforms.validators import DataRequired, Optional

class NakliyeForm(FlaskForm):
    tarih = DateField('Tarih', format='%Y-%m-%d', validators=[DataRequired()])
    
    # Müşteri seçimi (Select box dinamik doldurulacak)
    firma_id = SelectField('Müşteri / Firma', coerce=int, validators=[DataRequired()])
    
    guzergah = StringField('Güzergah (Nereden - Nereye)', validators=[DataRequired()])
    plaka = StringField('Araç Plaka', validators=[Optional()])
    aciklama = TextAreaField('Yük Açıklaması / Notlar')
    
    tutar = FloatField('Navlun Tutarı (KDV Hariç)', validators=[DataRequired(), validate_currency])
    kdv_orani = IntegerField('KDV (%)', default=20)
    
    submit = SubmitField('Nakliye İşlemini Kaydet')

    def __init__(self, *args, **kwargs):
        super(NakliyeForm, self).__init__(*args, **kwargs)
        
        # SORGUYU DEĞİŞTİRİYORUZ:
        # Adının içinde "Kasa" veya "Dahili" geçmeyenleri getir.
        # notilike -> Büyük/küçük harf duyarsız "içermez" demektir.
        
        firmalar = Firma.query.filter(
            Firma.firma_adi.notilike('%Kasa%'),
            Firma.firma_adi.notilike('%Dahili%')
        ).order_by(Firma.firma_adi).all()
        
        self.firma_id.choices = [(f.id, f.firma_adi) for f in firmalar]