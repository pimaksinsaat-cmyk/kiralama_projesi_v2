from wtforms.validators import ValidationError

# Ortak hata mesajı değişkeni
secim_hata_mesaji = "Lütfen geçerli bir seçim yapınız."

# Para Birimi Doğrulayıcı Fonksiyonu
def validate_currency(form, field):
    if field.data:
        # Noktaları sil, virgülü noktaya çevir (1.500,00 -> 1500.00)
        clean_value = str(field.data).replace('.', '').replace(',', '.')
        try:
            float(clean_value)
        except ValueError:
            raise ValidationError("Lütfen geçerli bir sayısal değer giriniz (Örn: 150.000,00).")