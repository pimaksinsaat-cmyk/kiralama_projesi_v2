from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, InputRequired

# İsteğiniz üzerine utils kütüphanesi korundu
from app.utils import validate_currency, secim_hata_mesaji
# Modelin yeni adresi:
from app.firmalar.models import Firma

class FirmaForm(FlaskForm):
    # Veritabanında max 150 karakter
    firma_adi = StringField('Firma Ünvanı', validators=[
        DataRequired(message="Firma adı boş bırakılamaz."),
        Length(max=150, message="Firma adı en fazla 150 karakter olabilir.")
    ])

    # Veritabanında max 100 karakter
    yetkili_adi = StringField('Yetkili Kişi', validators=[
        DataRequired(message="Yetkili adı boş bırakılamaz."),
        Length(max=100, message="Yetkili adı en fazla 100 karakter olabilir.")
    ])
    # Telefon ve eposta alanları için yeni validasyonlar eklenebilir
    telefon = StringField('Telefon', validators=[
        Length(max=20, message="Telefon numarası en fazla 20 karakter olabilir.")
    ])
    eposta = StringField('E-posta', validators=[
        Length(max=120, message="E-posta en fazla 120 karakter olabilir.")
    ])
    
    # TextAreaField adres için daha uygundur
    iletisim_bilgileri = TextAreaField('Adres / İletişim Bilgileri', validators=[
        DataRequired(message="İletişim bilgisi zorunludur.")
    ])

    # Veritabanında max 100 karakter
    vergi_dairesi = StringField('Vergi Dairesi', validators=[
        DataRequired(message="Vergi dairesi zorunludur."),
        Length(max=100)
    ])

    # Veritabanında max 50 karakter
    vergi_no = StringField('Vergi Numarası', validators=[
        DataRequired(message="Vergi numarası zorunludur."),
        Length(max=50, message="Vergi numarası çok uzun.")
    ])

    # Rol Seçimleri
    is_musteri = BooleanField('Bu bir Müşteri mi?', default=True)
    is_tedarikci = BooleanField('Bu bir Tedarikçi mi?', default=False)

    submit = SubmitField('Kaydet')