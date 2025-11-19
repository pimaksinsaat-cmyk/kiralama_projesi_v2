import os

# Projemizin temel dizinini bul
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """
    Tüm yapılandırmalar için temel sınıf.
    """
    
    # --- Güvenlik Ayarları ---
    
    # Flask ve Flask-WTF'nin CSRF koruması için gizli anahtar
    # BU ÇOK ÖNEMLİ! Güvenlik için bunu karmaşık bir şey yapmalıyız.
    # Terminalde "python -c 'import secrets; print(secrets.token_hex(16))'" 
    # komutuyla rastgele bir anahtar üretebilirsiniz.
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'buraya-tahmin-edilmesi-zor-bir-sifre-yazin'
    
    
    # --- Veritabanı Ayarları ---
    
    # Veritabanımızın konumu (SQLite için)
    # 'app.db' adında bir dosya oluşturacak (ana dizinde)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')
        
    # Veritabanında değişiklik olduğunda sinyal göndermeyi kapat (performans)
    SQLALCHEMY_TRACK_MODIFICATIONS = False