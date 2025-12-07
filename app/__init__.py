# app/__init__.py
from flask import Flask
from config import Config
# DİKKAT: Aşağıdaki 2 satırı siliyoruz, artık extensions'dan alacağız
# from flask_sqlalchemy import SQLAlchemy 
# from flask_migrate import Migrate

from flask_wtf.csrf import CSRFProtect 

# DÜZELTME: db ve migrate nesnelerini extensions.py'dan çağırıyoruz
from app.extensions import db, migrate

# CSRF şimdilik burada kalabilir (istersen onu da extensions'a taşıyabilirsin ama şart değil)
csrf = CSRFProtect()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # extensions'dan gelen nesneleri başlatıyoruz
    db.init_app(app)
    migrate.init_app(app, db)
    
    # CSRF uygulamasını başlat
    csrf.init_app(app)

    # --- BLUEPRINT (MODÜL) KAYITLARI ---

    # 1. Ana Sayfa
    from app.main import main_bp
    app.register_blueprint(main_bp)

    # 2. Firmalar (Müşteri/Tedarikçi)
    from app.firmalar import firmalar_bp
    app.register_blueprint(firmalar_bp, url_prefix='/firmalar')

    # 3. Filo (Makine Parkı)
    from app.filo import filo_bp
    app.register_blueprint(filo_bp, url_prefix='/filo')

    # 4. Kiralama (Sözleşmeler)
    from app.kiralama import kiralama_bp
    app.register_blueprint(kiralama_bp, url_prefix='/kiralama')

    # 5. Cari (Finansal İşlemler)
    from app.cari import cari_bp
    app.register_blueprint(cari_bp, url_prefix='/cari')

    return app