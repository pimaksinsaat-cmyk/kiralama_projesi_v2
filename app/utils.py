from wtforms.validators import ValidationError
import re
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
        
# klasör adı düzeltme fonksiyonu       
def klasor_adi_temizle(firma_adi, firma_id):
    """
    Firma adını klasör dostu hale getirir: 'Pimaks İnşaat' -> '145_pimaks_i'
    """
    # 1. Türkçe karakter dönüşümü
    mapping = str.maketrans("çğıöşüÇĞİÖŞÜ ", "cgiosuCGIOSU_")
    temiz = str(firma_adi).translate(mapping)
    
    # 2. Sadece harf, rakam ve alt tire kalsın (boşluklar alt tire oldu)
    temiz = re.sub(r'[^a-zA-Z0-9_]', '', temiz)
    
    # 3. Küçük harfe çevir ve ilk 8 karakteri al
    kisa_ad = temiz[:8].lower()
    
    # 4. ID ile birleştirerek benzersiz yap
    return f"{firma_id}_{kisa_ad}"