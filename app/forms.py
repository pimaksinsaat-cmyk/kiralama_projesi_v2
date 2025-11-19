from flask_wtf import FlaskForm
from wtforms import (
    StringField, DecimalField, SelectField, DateField, SubmitField, 
    FormField, FieldList, HiddenField, IntegerField, BooleanField, TextAreaField
)
from wtforms.validators import Optional, InputRequired, NumberRange

# -------------------------------------------------------------------------
# 1. FirmaForm
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
# 2. EkipmanForm (GÜNCELLENDİ: 'model' alanı eklendi)
# -------------------------------------------------------------------------
class EkipmanForm(FlaskForm):
    """
    Yeni Pimaks makinesi (ekipman) eklemek için kullanılacak form.
    """
    kod = StringField('Makine Kodu', validators=[InputRequired()])
    yakit = StringField('Yakıt Türü', validators=[InputRequired()])
    tipi = StringField('Makine Tipi', validators=[InputRequired()])
    marka = StringField('Makine Markası', validators=[InputRequired()])
    
    # --- YENİ EKLENEN ALAN ---
    model = StringField('Makine Modeli', validators=[InputRequired()])
    # -------------------------

    seri_no = StringField('Makine Seri No', validators=[InputRequired()])
    calisma_yuksekligi = StringField('Çalışma Yüksekliği (m)', validators=[InputRequired()]) 
    kaldirma_kapasitesi = StringField('Kaldırma Kapasitesi (kg)', validators=[InputRequired()])
    uretim_tarihi = StringField('Üretim Tarihi (Yıl)', validators=[InputRequired()])
    
    giris_maliyeti = DecimalField('Giriş Maliyeti (Satın Alma)', default=0.0, validators=[Optional()])
    
    submit = SubmitField('Kaydet')


# -------------------------------------------------------------------------
# 3. KiralamaKalemiForm (Dış Tedarik Alanları Zaten Vardı)
# -------------------------------------------------------------------------
class KiralamaKalemiForm(FlaskForm):
    class Meta:
        csrf = False 
    id = HiddenField('Kalem ID')

    dis_tedarik_ekipman = BooleanField("Dış Tedarik Ekipman?")

    # --- Bizim Filomuz ---
    ekipman_id = SelectField(
        'Pimaks Filosu', coerce=int, default='0', validators=[Optional()]
    )
    
    # --- Harici Ekipman Bilgileri ---
    harici_ekipman_tedarikci_id = SelectField('Ekipman Tedarikçisi', coerce=int, default='0', validators=[Optional()])
    harici_ekipman_tipi = StringField('Harici Ekipman Tipi', validators=[Optional()])
    harici_ekipman_marka = StringField('Harici Ekipman Markası', validators=[Optional()])
    harici_ekipman_model = StringField('Harici Ekipman Modeli', validators=[Optional()])
    harici_ekipman_seri_no = StringField('Harici Seri No', validators=[Optional()])

    kiralama_baslangıcı = DateField('Başlangıç Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    kiralama_bitis = DateField('Bitiş Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    kiralama_brm_fiyat = DecimalField('Ekipman Satış Fiyatı (Gelir)', validators=[InputRequired()], default=0.0)
    kiralama_alis_fiyat = DecimalField('Ekipman Alış Fiyatı (Maliyet)', validators=[Optional()], default=0.0)

    dis_tedarik_nakliye = BooleanField("Harici Nakliye?")
    nakliye_satis_fiyat = DecimalField('Nakliye Satış Fiyatı (Gelir)', validators=[Optional()], default=0.0)
    nakliye_alis_fiyat = DecimalField('Nakliye Alış Fiyatı (Maliyet)', validators=[Optional()], default=0.0)
    nakliye_tedarikci_id = SelectField('Nakliye Tedarikçisi', coerce=int, default='0', validators=[Optional()])


# -------------------------------------------------------------------------
# 4. KiralamaForm (Değişiklik yok)
# -------------------------------------------------------------------------
class KiralamaForm(FlaskForm):
    kiralama_form_no = StringField('Kiralama Form No', validators=[Optional()])
    firma_musteri_id = SelectField(
        'Müşteri (Firma) Seç', coerce=int, default='0', 
        validators=[NumberRange(min=1, message="Lütfen geçerli bir seçim yapınız.")]
    )
    kdv_orani = IntegerField('KDV Oranı (%)', default=20, validators=[InputRequired(), NumberRange(min=0, max=100)])
    kalemler = FieldList(FormField(KiralamaKalemiForm), min_entries=1)
    submit = SubmitField('Kaydet')

# -------------------------------------------------------------------------
# 5. OdemeForm (Değişiklik yok)
# -------------------------------------------------------------------------
class OdemeForm(FlaskForm):
    firma_musteri_id = SelectField('Ödeme Yapan Müşteri (Firma)', coerce=int, default='0', validators=[NumberRange(min=1)])
    tarih = DateField('Ödeme Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    tutar = DecimalField('Ödeme Tutarı', validators=[InputRequired()])
    aciklama = StringField('Açıklama (Örn: EFT, Fatura No)', validators=[Optional()])
    submit = SubmitField('Ödemeyi Kaydet')

# -------------------------------------------------------------------------
# 6. HizmetKaydiForm (Değişiklik yok)
# -------------------------------------------------------------------------
class HizmetKaydiForm(FlaskForm):
    firma_id = SelectField('İlgili Firma', coerce=int, default='0', validators=[NumberRange(min=1)])
    tarih = DateField('Hizmet Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    tutar = DecimalField('Hizmet Tutarı (KDV Hariç)', validators=[InputRequired()])
    aciklama = StringField('Hizmet Açıklaması', validators=[InputRequired()])
    yon = SelectField('İşlem Yönü', choices=[('giden', 'Hizmet/Ürün Satışı Yaptık'), ('gelen', 'Hizmet/Ürün Alımı Yaptık')], validators=[InputRequired()])
    submit = SubmitField('Hizmet Kaydını Oluştur')

# -------------------------------------------------------------------------
# 7. StokKartiForm (Değişiklik yok)
# -------------------------------------------------------------------------
class StokKartiForm(FlaskForm):
    parca_kodu = StringField('Parça Kodu', validators=[InputRequired()])
    parca_adi = StringField('Parça Adı', validators=[InputRequired()])
    mevcut_stok = IntegerField('Mevcut Stok Adedi', default=0, validators=[InputRequired()])
    varsayilan_tedarikci_id = SelectField('Varsayılan Tedarikçi', coerce=int, default='0', validators=[Optional()])
    submit = SubmitField('Stok Kartını Kaydet')

# -------------------------------------------------------------------------
# 8. KullanilanParcaForm (Değişiklik yok)
# -------------------------------------------------------------------------
class KullanilanParcaForm(FlaskForm):
    class Meta:
        csrf = False
    stok_karti_id = SelectField('Kullanılan Parça', coerce=int, default='0', validators=[NumberRange(min=1)])
    kullanilan_adet = IntegerField('Adet', default=1, validators=[InputRequired()])

# -------------------------------------------------------------------------
# 9. BakimKaydiForm (Değişiklik yok)
# -------------------------------------------------------------------------
class BakimKaydiForm(FlaskForm):
    ekipman_id = SelectField('Bakım Yapılan Ekipman', coerce=int, default='0', validators=[NumberRange(min=1)])
    tarih = DateField('Bakım Tarihi', format='%Y-%m-%d', validators=[InputRequired()])
    aciklama = TextAreaField('Yapılan İşlemlerin Açıklaması', validators=[InputRequired()])
    calisma_saati = IntegerField('Ekipman Çalışma Saati (Opsiyonel)', validators=[Optional()])
    kullanilan_parcalar = FieldList(FormField(KullanilanParcaForm), min_entries=0)
    submit = SubmitField('Bakım Kaydını Tamamla')