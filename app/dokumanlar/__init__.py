from flask import Blueprint

# Dökümanlar modülü için Blueprint oluşturuluyor
# template_folder belirtiyoruz ki 'templates/dokumanlar' klasöründeki dosyaları bulabilsin
dokumanlar_bp = Blueprint('dokumanlar', __name__, template_folder='templates')

from app.dokumanlar import routes