import os
from flask import flash, redirect, url_for, send_file
from . import dokumanlar_bp
from app.firmalar.models import Firma

# word_engine modülünü çağırıyoruz
try:
    from app.dokumanlar.word_engine import ps_word_olustur
except ImportError:
    from .word_engine import ps_word_olustur

@dokumanlar_bp.route('/ps-yazdir/<int:firma_id>')
def ps_yazdir(firma_id):
    """
    HTML tarafındaki butona tıklandığında çalışan fonksiyondur.
    word_engine.py dosyasındaki 'ps_word_olustur' fonksiyonunu tetikler.
    """
    try:
        # 1. Firmayı bul
        firma = Firma.query.get_or_404(firma_id)
        
        # 2. PS Numarası var mı kontrol et
        if not firma.sozlesme_no:
            flash(f"'{firma.firma_adi}' için önce PS numarası oluşturmalısınız.", "warning")
            return redirect(url_for('firmalar.index'))

        # 3. Word dosyasını OLUŞTUR (word_engine.py tetikleniyor)
        dosya_yolu = ps_word_olustur(firma)
        
        # 4. Oluşturulan dosyayı İNDİRT
        return send_file(
            dosya_yolu,
            as_attachment=True,
            download_name=f"{firma.sozlesme_no}_{firma.firma_adi}_Sozlesme.docx"
        )
        
    except Exception as e:
        flash(f"İşlem sırasında hata oluştu: {str(e)}", "danger")
        return redirect(url_for('firmalar.index'))