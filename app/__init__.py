from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

# 1. Eklentileri (Extensions) başlatıyoruz
# Henüz bir uygulamaya bağlı değiller.
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect() # CSRF koruması için (Flask-WTF)

def create_app(config_class=Config):
    """
    Application Factory (Uygulama Fabrikası) Fonksiyonu.
    """
    
    # 2. Ana Flask uygulamasını oluştur
    app = Flask(__name__)
    
    # 3. Yapılandırmayı (Config) yükle
    app.config.from_object(config_class)
    
    # 4. Eklentileri uygulamaya bağla
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app) # CSRF'yi uygulamaya bağla

    # --- Blueprint'leri Kaydetme ---
    # Bu blueprint'leri birazdan oluşturacağız ama yerleri hazır.
    
    # Ana Sayfa Blueprint'i
    from app.main import main_bp
    app.register_blueprint(main_bp)

    # Filo (Makine Parkı) Blueprint'i
    from app.filo import filo_bp
    # url_prefix='/filo' sayesinde bu blueprint'teki tüm URL'ler
    # /filo/.. ile başlayacak (örn: /filo/ekle)
    app.register_blueprint(filo_bp, url_prefix='/filo')

    # Kiralama Blueprint'i
    from app.kiralama import kiralama_bp    
    # url_prefix='/kiralama' sayesinde bu blueprint'teki tüm URL'ler
    # /kiralama/.. ile başlayacak (örn: /kiralama/index)    
    app.register_blueprint(kiralama_bp, url_prefix='/kiralama')

    
    # Firmalar Blueprint'i
    from app.firmalar import firmalar_bp    
    # url_prefix='/firmalar' sayesinde bu blueprint'teki tüm URL'ler
    # /firmalar/.. ile başlayacak (örn: /firmalar/index)    
    app.register_blueprint(firmalar_bp, url_prefix='/firmalar')


    # 5. Bitmiş uygulamayı fabrikadan döndür
    return app

# Modellerimizi de buraya import edelim ki migrate aracı bulabilsin.
from app import models