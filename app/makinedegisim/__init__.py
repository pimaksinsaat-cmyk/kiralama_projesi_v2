from flask import Blueprint

# 'makine degisim' adında bir blueprint (departman tabelası) oluştur
makinedegisim_bp = Blueprint('makinedegisim', __name__)

# Bu departmana ait rotaları (URL'leri) bağla
# (Circular import'u önlemek için import en sonda yapılır)
from app.makinedegisim import routes