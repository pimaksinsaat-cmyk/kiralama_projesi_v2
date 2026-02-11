from app.extensions import db
from datetime import datetime

class MakineDegisim(db.Model):
    """
    Makine değişim (Swap) kayıtlarını tutan tablo.
    """
    __tablename__ = 'makine_degisimleri'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    tarih = db.Column(db.DateTime, default=datetime.utcnow)
    
    # ForeignKey tanımları - Mutlaka 'ekipman' (tablo adı) kullanılmalı
    eski_ekipman_id = db.Column(db.Integer, db.ForeignKey('ekipman.id'), nullable=False)
    yeni_ekipman_id = db.Column(db.Integer, db.ForeignKey('ekipman.id'), nullable=False)
    kiralama_kalemi_id = db.Column(db.Integer, db.ForeignKey('kiralama_kalemi.id'), nullable=False)
    
    # Bilgi alanları
    degisim_nedeni = db.Column(db.String(100), nullable=False)
    eski_ekipman_saati = db.Column(db.Integer)
    yeni_ekipman_saati = db.Column(db.Integer)
    nakliye_ucreti = db.Column(db.Numeric(15, 2), default=0.0)
    aciklama = db.Column(db.Text)

    # İlişki tanımları (String referans kullanarak döngüsel importu engelliyoruz)
    kiralama_kalemi = db.relationship('KiralamaKalemi', backref='degisimler')

    def __repr__(self):
        return f'<MakineDegisim {self.id} | {self.degisim_nedeni}>'