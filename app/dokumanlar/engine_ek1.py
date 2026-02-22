import os
import subprocess
import platform
import logging
import time
import re
from datetime import date
from flask import send_file, flash, redirect, url_for, current_app
from docxtpl import DocxTemplate

# Loglama yapılandırması
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Modellerin gerçek konumlarını içe aktarıyoruz
try:
    from app.kiralama.models import Kiralama, KiralamaKalemi
    from app.firmalar.models import Firma
except ImportError as e:
    logger.error(f"Modeller içe aktarılamadı: {e}")

# Blueprint'i aynı klasördeki __init__.py dosyasından alıyoruz
from . import dokumanlar_bp

# Windows ortamında PDF dönüşümü için gerekli
if platform.system() == "Windows":
    import pythoncom

def safe_filename(name):
    """
    Dosya ismindeki tüm riskli karakterleri temizler.
    Harf, rakam, tire (-) ve alt tire (_) DIŞINDAKİ her şeyi '_' yapar.
    Bu yöntem slaş (/) sorununu %100 çözer.
    """
    if not name:
        return "isimsiz_dosya"
    
    # İsmi stringe çevir
    name = str(name).strip()
    
    # Beyaz liste dışındaki her şeyi (boşluk, slaş, nokta vb.) alt tireye çevir
    # re.sub(r'[^a-zA-Z0-9\-_]', ...) -> Alfanumerik, tire ve alt tire haricindekileri eşleştir
    safe_name = re.sub(r'[^a-zA-Z0-9\-_]', '_', name)
    
    # Peş peşe gelen alt tireleri teke indir
    safe_name = re.sub(r'_+', '_', safe_name).strip('_')
    
    return safe_name

def pdf_donustur(docx_path, output_dir):
    """
    İşletim sistemine göre LibreOffice veya docx2pdf kullanarak PDF üretir.
    """
    current_os = platform.system()
    pdf_path = docx_path.replace(".docx", ".pdf")
    
    if current_os == "Windows":
        try:
            from docx2pdf import convert
            pythoncom.CoInitialize()
            
            if os.path.exists(pdf_path):
                try: os.remove(pdf_path)
                except: pass

            # Tam yolları normalize et ve mutlak yola çevir
            abs_docx = os.path.abspath(docx_path)
            abs_pdf = os.path.abspath(pdf_path)
            
            convert(abs_docx, abs_pdf)
            time.sleep(1.5) 
            return pdf_path if os.path.exists(pdf_path) else None
        except Exception as e:
            logger.error(f"Windows PDF Dönüşüm Hatası: {str(e)}")
            return None
        finally:
            try: pythoncom.CoUninitialize()
            except: pass
    else:
        # Linux / Render / Docker (LibreOffice)
        try:
            subprocess.run([
                'soffice', '--headless', '--convert-to', 'pdf',
                '--outdir', output_dir, docx_path
            ], check=True, capture_output=True, timeout=60)
            
            return pdf_path if os.path.exists(pdf_path) else None
        except Exception as e:
            logger.error(f"Linux PDF Dönüşüm Hatası: {str(e)}")
            return None

@dokumanlar_bp.route('/yazdir/form/<int:rental_id>')
def kiralama_formu_yazdir(rental_id):
    """
    Kiralama modellerine tam uyumlu döküman hazırlama rotası.
    """
    try:
        # 1. Veritabanından veriyi çekiyoruz
        kiralama = Kiralama.query.get_or_404(rental_id)
        musteri = kiralama.firma_musteri 
        
        if not musteri:
            flash("Kiralama kaydına bağlı müşteri bulunamadı.", "danger")
            return redirect(url_for('kiralama.index'))

        # --- GENEL SÖZLEŞME KONTROLÜ ---
        gs_no = getattr(musteri, 'sozlesme_no', None)
        
        if gs_no is None or str(gs_no).strip() == "":
            flash(f"Müşteri ({musteri.firma_adi}) için tanımlı bir Genel Sözleşme bulunamadı.", "danger")
            return redirect(url_for('kiralama.index'))

        # 2. Kalemler Hazırlığı (Döngü)
        kalemler_listesi = []
        genel_toplam = 0
        
        for kalem in kiralama.kalemler:
            gun = (kalem.kiralama_bitis - kalem.kiralama_baslangici).days + 1
            birim_fiyat = float(kalem.kiralama_brm_fiyat or 0)
            nakliye = float(kalem.nakliye_satis_fiyat or 0)
            satir_toplam = (gun * birim_fiyat) + nakliye
            genel_toplam += satir_toplam
            
            if kalem.is_dis_tedarik_ekipman:
                ekipman_adi = f"{kalem.harici_ekipman_marka} {kalem.harici_ekipman_model}"
                seri_no = kalem.harici_ekipman_seri_no or "-"
            else:
                if kalem.ekipman:
                    ekipman_adi = f"{kalem.ekipman.kod} ({kalem.ekipman.tipi})"
                    seri_no = kalem.ekipman.seri_no or "-"
                else:
                    ekipman_adi = "Tanımsız Makine"
                    seri_no = "-"

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
        
        # Ana çıktı klasörünü oluştur ve normalize et
        output_dir = os.path.abspath(os.path.join(base_dir, 'static', 'arsiv', bulut_adi, 'Formlar'))
        os.makedirs(output_dir, exist_ok=True)
        
        # 4. Dosya Adı Güvenliği (KESİN ÇÖZÜM)
        # PF-2026/0003 -> PF_2026_0003 olacak
        safe_form_no = safe_filename(kiralama.kiralama_form_no)
        docx_filename = f"{safe_form_no}_Form.docx"
        
        # Tam dosya yolunu oluştur ve işletim sistemi formatına zorla
        docx_path = os.path.join(output_dir, docx_filename)

        if not os.path.exists(template_path):
            logger.error(f"Şablon dosyası bulunamadı: {template_path}")
            return f"Taslak bulunamadı: {template_path}", 404

        # 5. Word Şablonunu Doldur
        doc = DocxTemplate(template_path)
        context = {
            'form_no': kiralama.kiralama_form_no, # Word belgesi içinde / görünebilir, sorun yok
            'gunun_tarihi': date.today().strftime('%d.%m.%Y'),
            'genel_sozlesme_no': gs_no,
            'musteri_unvan': musteri.firma_adi.upper(),
            'musteri_vergi': f"{musteri.vergi_dairesi or ''} / {musteri.vergi_no or ''}",
            'musteri_adres': musteri.iletisim_bilgileri or "",
            'musteri_tel': musteri.telefon or "",
            'kalemler': kalemler_listesi,
            'genel_toplam': f"{genel_toplam:,.2f} TL"
        }
        
        doc.render(context)
        
        # Kaydetme denemesi
        try:
            doc.save(docx_path)
            logger.info(f"Dosya başarıyla kaydedildi: {docx_path}")
        except Exception as e:
            logger.error(f"Kayıt Hatası: {docx_path} - {str(e)}")
            raise e

        # 6. PDF Dönüştürme
        pdf_file = pdf_donustur(docx_path, output_dir)
        
        if pdf_file and os.path.exists(pdf_file):
            try: os.remove(docx_path)
            except: pass
            return send_file(pdf_file, mimetype='application/pdf')
        
        return send_file(docx_path, as_attachment=False)

    except Exception as e:
        logger.error(f"Kiralama Yazdırma Hatası: {str(e)}")
        flash(f"Döküman hazırlanırken hata: {str(e)}", "warning")
        return redirect(url_for('kiralama.index'))