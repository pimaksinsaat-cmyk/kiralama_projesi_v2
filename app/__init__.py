# app/__init__.py
from flask import Flask
from config import Config
from flask_wtf.csrf import CSRFProtect 
from app.extensions import db, migrate


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

    # 6. Nakliyeler
    from app.nakliyeler import nakliye_bp
    app.register_blueprint(nakliye_bp, url_prefix='/nakliyeler')

    # 7. makine degişim
    from app.makinedegisim import makinedegisim_bp
    app.register_blueprint(makinedegisim_bp,url_prefix='/makinedegisim')

    return app