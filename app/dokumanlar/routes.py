import os
from flask import flash, redirect, url_for, send_file
from . import dokumanlar_bp
from app.firmalar.models import Firma

# word_engine modülünü güvenli bir şekilde içe aktaralım
try:
    from app.dokumanlar.word_engine import ps_word_olustur
except ImportError:
    from .word_engine import ps_word_olustur

@dokumanlar_bp.route('/ps-yazdir/<int:firma_id>')
def ps_yazdir(firma_id):
    """
    Sözleşmeyi oluşturur ve tarayıcıya gönderir.
    PDF ise ekranda açar, Word ise indirme işlemi başlatır.
    """
    try:
        # 1. Firmayı veritabanından bul
        firma = Firma.query.get_or_404(firma_id)
        
        # 2. PS Numarası atanıp atanmadığını kontrol et
        if not firma.sozlesme_no:
            flash(f"'{firma.firma_adi}' için önce PS numarası oluşturmalısınız (Sağ Tık -> Sözleşme Hazırla).", "warning")
            return redirect(url_for('firmalar.index'))

        # 3. Dosyayı OLUŞTUR (word_engine.py dosyasındaki seçili kodu çalıştırır)
        # Bu fonksiyon PDF oluşturursa .pdf yolunu, hata alırsa .docx yolunu döndürür.
        dosya_yolu = ps_word_olustur(firma)
        
        if not dosya_yolu or not os.path.exists(dosya_yolu):
            flash("Dosya oluşturulamadı veya sunucu diskinde bulunamadı.", "danger")
            return redirect(url_for('firmalar.index'))

        # 4. Uzantıyı ve MIME Tipini Dinamik Olarak Belirle
        uzanti = os.path.splitext(dosya_yolu)[1].lower()
        
        if uzanti == '.pdf':
            mimetype = 'application/pdf'
            # as_attachment=False: iPhone ve bilgisayarda dosyayı indirmeden tarayıcıda açar.
            as_attachment = False
        else:
            # Word dosyası için standart MIME tipi
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            # Word dosyaları tarayıcıda açılamayacağı için indirilmesini sağlarız.
            as_attachment = True

        # 5. Dosyayı Kullanıcıya Gönder
        return send_file(
            dosya_yolu,
            mimetype=mimetype,
            as_attachment=as_attachment,
            download_name=f"{firma.sozlesme_no}_{firma.firma_adi}{uzanti}"
        )
        
    except Exception as e:
        # Hata durumunda log bas ve kullanıcıyı ana sayfaya yönlendir
        flash(f"Döküman hazırlama sırasında bir hata oluştu: {str(e)}", "danger")
        return redirect(url_for('firmalar.index'))