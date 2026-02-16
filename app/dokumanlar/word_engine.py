import os
import platform
import subprocess
from docxtpl import DocxTemplate
from datetime import date
import traceback

def ps_word_olustur(firma):
    """
    Hem Windows hem de Linux (Render/Cloud) uyumlu Word ve PDF motoru.
    """
    # 1. Klasör ve Şablon Yollarını Ayarla
    template_path = os.path.join(os.getcwd(), 'app', 'static', 'templates', 'Sozlesme_TASLAK.docx')
    
    if not os.path.exists(template_path):
        os.makedirs(os.path.dirname(template_path), exist_ok=True)
        raise FileNotFoundError(f"Şablon dosyası bulunamadı: {template_path}")

    # 2. Şablonu Doldur (docxtpl)
    doc = DocxTemplate(template_path)
    context = {
        'sozlesme_no': firma.sozlesme_no or "BELİRSİZ",
        'tarih': firma.sozlesme_tarihi.strftime('%d.%m.%Y') if firma.sozlesme_tarihi else date.today().strftime('%d.%m.%Y'),
        'firma_adi': firma.firma_adi.upper(),
        'adres': firma.iletisim_bilgileri or "",
        'vergi_dairesi': firma.vergi_dairesi or "",
        'vergi_no': firma.vergi_no or "",
        'yetkili': firma.yetkili_adi or "",
        'telefon': firma.telefon or "",
        'eposta': firma.eposta or ""
    }
    doc.render(context)

    # 3. Çıktı Klasörlerini Ayarla
    output_dir = os.path.join(os.getcwd(), 'app', 'static', 'arsiv', firma.bulut_klasor_adi, 'PS')
    os.makedirs(output_dir, exist_ok=True)
    
    docx_path = os.path.join(output_dir, f"{firma.sozlesme_no}_Sozlesme.docx")
    pdf_path = os.path.join(output_dir, f"{firma.sozlesme_no}_Sozlesme.pdf")
    
    # Önce Word olarak kaydet
    doc.save(docx_path)

    # 4. PDF Dönüşüm (İşletim Sistemine Göre)
    current_os = platform.system() # Windows veya Linux döner
    
    try:
        if current_os == "Windows":
            # Windows'ta docx2pdf kullan (MS Word yüklü olmalı)
            from docx2pdf import convert
            convert(docx_path, pdf_path)
        else:
            # Linux'ta (Render) LibreOffice kullan
            # Render ortamında 'libreoffice' komutu yüklü olmalıdır.
            # Komut: libreoffice --headless --convert-to pdf --outdir [hedef_klasor] [kaynak_dosya]
            subprocess.run([
                'libreoffice', '--headless', '--convert-to', 'pdf',
                '--outdir', output_dir, docx_path
            ], check=True, capture_output=True)
            
        return pdf_path

    except Exception as e:
        print(f"PDF Dönüşüm Hatası ({current_os}): {str(e)}")
        # PDF başarısız olursa güvenli tarafta kalıp Word'ü döndür
        return docx_path