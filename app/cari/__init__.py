from flask import Blueprint

# Blueprint'i oluştur
cari_bp = Blueprint('cari', __name__, template_folder='templates')

# Rotaları içe aktar (Dairesel importu önlemek için en sonda)
from . import routes