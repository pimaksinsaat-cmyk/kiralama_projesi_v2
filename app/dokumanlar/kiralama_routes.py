import os
import subprocess
import platform
import logging
import re
from datetime import date
from flask import send_file, flash, redirect, url_for, current_app
from docxtpl import DocxTemplate

# Modellerin gerçek konumlarını içe aktarıyoruz
try:
    from app.kiralama.models import Kiralama, KiralamaKalemi
    from app.firmalar.models import Firma
except ImportError as e:
    logging.error(f"Modeller içe aktarılamadı: {e}")

# Blueprint nesnesini paket düzeyinden alıyoruz
from . import dokumanlar_bp

# Windows ortamında Word/PDF işlemleri için gerekli
if platform.system() == "Windows":
    import pythoncom

# Log yapılandırması - Canlıda sadece kritik hataları loglamak performansı artırır
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

def safe_filename(name):
    """
    Dosya ismindeki geçersiz karakterleri temizler.
    Windows ve Bulut sürücülerindeki ayraç sorunlarını önler.
    """
    if not name:
        return "isimsiz_dosya"
    name = str(name).strip()
    # Slaş ve diğer riskli karakterleri alt tireye çeviriyoruz
    return re.sub(r'[\\/*?:"<>|]', '_', name)

def pdf_donustur(docx_path, output_dir):
    """
    İşletim sistemine göre en hızlı şekilde PDF üretir.
    Canlı (Linux) ortamında 'soffice' kullanarak çok hızlı sonuç verir.
    """
    current_os = platform.system()
    pdf_path = docx_path.replace(".docx", ".pdf")
    
    abs_docx = os.path.abspath(docx_path)
    abs_pdf = os.path.abspath(pdf_path)

    if current_os == "Windows":
        try:
            from docx2pdf import convert
            pythoncom.CoInitialize()
            
            if os.path.exists(abs_pdf):
                try: os.remove(abs_pdf)
                except: pass
            
            convert(abs_docx, abs_pdf)
            return pdf_path if os.path.exists(abs_pdf) else None
        except Exception as e:
            logger.error(f"Windows PDF Dönüşüm Hatası: {str(e)}")
            return None
        finally:
            try: pythoncom.CoUninitialize()
            except: pass
    else:
        # CANLI ORTAM (Linux / Docker / Render)
        # LibreOffice 'soffice' komutu çok hızlıdır ve Word açmaz.
        try:
            subprocess.run([
                'soffice', '--headless', '--convert-to', 'pdf',
                '--outdir', output_dir, abs_docx
            ], check=True, capture_output=True, timeout=30)
            
            return pdf_path if os.path.exists(abs_pdf) else None
        except Exception as e:
            logger.error(f"Linux PDF Dönüşüm Hatası: {str(e)}")
            return None

@dokumanlar_bp.route('/yazdir/form/<int:rental_id>')
def kiralama_formu_yazdir(rental_id):
    """
    Kiralama Formu üretme rotası.
    """
    try:
        # 1. Veriyi Veritabanından Çek
        kiralama = Kiralama.query.get_or_404(rental_id)
        musteri = kiralama.firma_musteri 
        
        if not musteri:
            flash("Müşteri bulunamadı.", "danger")
            return redirect(url_for('kiralama.index'))

        # Müşterinin sözleşme numarasını al (Firma modelindeki alan)
        gs_no = getattr(musteri, 'sozlesme_no', None) or "BELİRTİLMEDİ"

        # 2. Kalemler Listesini Hazırla
        kalemler_listesi = []
        genel_toplam = 0
        
        for kalem in kiralama.kalemler:
            # Süre ve tutar hesaplama
            gun = (kalem.kiralama_bitis - kalem.kiralama_baslangici).days + 1
            birim_fiyat = float(kalem.kiralama_brm_fiyat or 0)
            nakliye = float(kalem.nakliye_satis_fiyat or 0)
            satir_toplam = (gun * birim_fiyat) + nakliye
            genel_toplam += satir_toplam
            
            if kalem.is_dis_tedarik_ekipman:
                ekipman_adi = f"{kalem.harici_ekipman_marka} {kalem.harici_ekipman_model}"
                seri_no = kalem.harici_ekipman_seri_no or "-"
            else:
                ekipman_adi = f"{kalem.ekipman.kod} ({kalem.ekipman.tipi})" if kalem.ekipman else "Tanımsız"
                seri_no = kalem.ekipman.seri_no if kalem.ekipman else "-"

            kalemler_listesi.append({
                'ekipman': ekipman_adi,
                'seri_no': seri_no,
                'bas_tarih': kalem.kiralama_baslangici.strftime('%d.%m.%Y'),
                'bit_tarih': kalem.kiralama_bitis.strftime('%d.%m.%Y'),
                'gun_sayisi': gun,
                'birim_fiyat': f"{birim_fiyat:,.2f} TL",
                'nakliye': f"{nakliye:,.2f} TL",
                'satir_toplam': f"{satir_toplam:,.2f} TL"
            })

        # 3. Dosya Yolları
        base_dir = current_app.root_path 
        template_path = os.path.join(base_dir, 'static', 'templates', 'Kiralama_Formu_TASLAK.docx')
        
        bulut_adi = musteri.bulut_klasor_adi or "Genel_Arsiv"
        output_dir = os.path.join(base_dir, 'static', 'arsiv', bulut_adi, 'Formlar')
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # Dosya adındaki / ve \ işaretlerini temizliyoruz
        safe_f_no = safe_filename(kiralama.kiralama_form_no)
        docx_path = os.path.join(output_dir, f"{safe_f_no}_Form.docx")

        if not os.path.exists(template_path):
            return "Şablon dosyası bulunamadı.", 404

        # 4. WORD ŞABLONUNU DOLDURMA (Oldukça hızlıdır)
        doc = DocxTemplate(template_path)
        context = {
            'form_no': kiralama.kiralama_form_no,
            'gunun_tarihi': date.today().strftime('%d.%m.%Y'),
            'genel_sozlesme_no': gs_no,
            'musteri_unvan': musteri.firma_adi.upper(),
            'musteri_vergi': f"{musteri.vergi_dairesi or ''} / {musteri.vergi_no or ''}",
            'musteri_adres': musteri.iletisim_bilgileri or "",
            'musteri_tel': musteri.telefon or "",
            'kalemler': kalemler_listesi,
            'genel_toplam': f"{genel_toplam:,.2f} TL"
        }
        
        # Word doldurma işlemi
        doc.render(context)
        doc.save(docx_path)

        # 5. PDF DÖNÜŞTÜRME
        pdf_file = pdf_donustur(docx_path, output_dir)
        
        if pdf_file and os.path.exists(pdf_file):
            try: os.remove(docx_path) # PDF başarılıysa Word'ü temizle
            except: pass
            return send_file(pdf_file, mimetype='application/pdf')
        
        # PDF dönüşümü başarısız olursa beklemeden Word'ü gönder
        return send_file(docx_path, as_attachment=False)

    except Exception as e:
        logger.error(f"Döküman Üretim Hatası: {str(e)}")
        flash(f"Hata: {str(e)}", "warning")
        return redirect(url_for('kiralama.index'))