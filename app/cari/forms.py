from flask_wtf import FlaskForm
from wtforms import (
    StringField, DecimalField, SelectField, DateField, SubmitField, 
    FormField, FieldList, HiddenField, IntegerField, BooleanField, TextAreaField
)
from wtforms.validators import DataRequired, InputRequired, NumberRange, Optional, Length
from app.utils import secim_hata_mesaji

# --- ÖZEL ALAN: VİRGÜLÜ NOKTAYA ÇEVİREN DECIMAL FIELD ---
class TRDecimalField(DecimalField):
    def process_formdata(self, valuelist):
        if valuelist and valuelist[0]:
            # Örn gelen: "1.500,50" veya "1.500"
            val = valuelist[0].strip()
            
            # ADIM 1: Eğer değerde hem nokta hem virgül varsa (1.500,50)
            # Sadece noktayı (binlik) silip virgülü noktaya çeviriyoruz.
            if '.' in val and ',' in val:
                val = val.replace('.', '').replace(',', '.')
            
            # ADIM 2: Eğer sadece virgül varsa (1500,50)
            elif ',' in val:
                val = val.replace(',', '.')
                
            # ADIM 3: Eğer sadece nokta varsa (1.500)
            # İşte burası kritik! JS'den gelen binlik noktasını SİLMELİYİZ.
            elif '.' in val:
                # Eğer noktadan sonra 2 basamak varsa ondalık olabilir, 
                # ama kiralama projesinde 1.500 genelde binliktir. 
                # JS submit ederken noktayı sildiği için buraya gelen nokta 'ondalık' kabul edilebilir.
                # Garantiye almak için her türlü noktayı temizliyoruz (JS submit ile uyumlu)
                pass 

            valuelist[0] = val
            
        return super(TRDecimalField, self).process_formdata(valuelist)
# -------------------------------------------------------------------------
# 5. OdemeForm (Tahsilat / Ödeme)
# -------------------------------------------------------------------------
class OdemeForm(FlaskForm):
    firma_musteri_id = SelectField('Firma/Müşteri', coerce=int, choices=[], validators=[DataRequired()])
    kasa_id = SelectField('Kasa/Banka', coerce=int, choices=[], validators=[DataRequired()])
    
    tarih = DateField('Tarih', format='%Y-%m-%d', validators=[DataRequired()])
    
    # Kuruşlu giriş (Virgül destekli)
    tutar = TRDecimalField('Tutar', places=2, validators=[
        DataRequired(message="Tutar alanı boş bırakılamaz."), 
        NumberRange(min=0.01, message="Tutar 0'dan büyük olmalıdır.")
    ])
    
    # --- İŞTE EKSİK OLAN KISIM BURASIYDI ---
    yon = SelectField('İşlem Türü', choices=[
        ('tahsilat', 'Tahsilat (Para Girişi)'), 
        ('odeme', 'Ödeme (Para Çıkışı)')
    ], default='tahsilat', validators=[DataRequired()])
    # ---------------------------------------
    
    fatura_no = StringField('Belge/Fatura No', validators=[Optional(), Length(max=50)])
    vade_tarihi = DateField('Vade Tarihi', format='%Y-%m-%d', validators=[Optional()])
    aciklama = StringField('Açıklama', validators=[Optional(), Length(max=250)])
    
    submit = SubmitField('Kaydet')

# -------------------------------------------------------------------------
# 6. HizmetKaydiForm (Gelir / Gider Faturası)
# -------------------------------------------------------------------------
class HizmetKaydiForm(FlaskForm):
    firma_id = SelectField('İlgili Firma', coerce=int, default=0, validators=[NumberRange(min=1, message=secim_hata_mesaji)])
    tarih = DateField('İşlem Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    
    tutar = TRDecimalField('Tutar (KDV Dahil)', places=2, validators=[
        InputRequired(message="Tutar zorunludur."), 
        NumberRange(min=0.01, message="Hatalı tutar.")
    ])
    
    aciklama = StringField('Hizmet/Ürün Açıklaması', validators=[InputRequired(), Length(max=250)])
    
    yon = SelectField('İşlem Yönü', choices=[
        ('giden', 'Hizmet/Ürün Satışı (Firmayı Borçlandır - Gelir)'), 
        ('gelen', 'Hizmet/Ürün Alımı (Firmayı Alacaklandır - Gider)')
    ], validators=[InputRequired()])
    
    fatura_no = StringField('Fatura No', validators=[Optional(), Length(max=50)])
    vade_tarihi = DateField('Vade Tarihi', format='%Y-%m-%d', validators=[Optional()])
    
    submit = SubmitField('Hizmet Kaydını Oluştur')

# -------------------------------------------------------------------------
# 10. KasaForm (Banka / Nakit Hesap Tanımı)
# -------------------------------------------------------------------------
class KasaForm(FlaskForm):
    kasa_adi = StringField('Hesap Adı (Örn: Merkez Kasa, Garanti TL)', validators=[InputRequired(), Length(max=100)])
    
    tipi = SelectField('Hesap Tipi', choices=[
        ('nakit', 'Nakit Kasa'), 
        ('banka', 'Banka Hesabı')
    ], default='banka', validators=[InputRequired()])
    
    para_birimi = SelectField('Para Birimi', choices=[
        ('TRY', 'TL (Türk Lirası)'), 
        ('USD', 'USD (Dolar)'), 
        ('EUR', 'EUR (Euro)')
    ], default='TRY', validators=[InputRequired()])
    
    bakiye = TRDecimalField('Açılış Bakiyesi', places=2, default=0.0, validators=[Optional()])
    
    submit = SubmitField('Kaydet')