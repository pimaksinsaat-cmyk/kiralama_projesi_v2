from app.extensions import db
from datetime import datetime

# 2. KASA (Nakit/Banka Hesapları)
class Kasa(db.Model):
    __tablename__ = 'kasa'
    
    id = db.Column(db.Integer, primary_key=True)
    kasa_adi = db.Column(db.String(100), nullable=False)
    tipi = db.Column(db.String(20), nullable=False, default='nakit') # nakit, banka, pos
    para_birimi = db.Column(db.String(3), nullable=False, default='TRY')
    
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Bakiye Numeric (Doğru)
    bakiye = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    
    # İlişkiler
    odemeler = db.relationship('Odeme', back_populates='kasa')
    
    def __repr__(self):
        return f'<Kasa {self.kasa_adi}>'

# 6. ODEME (Tahsilat / Tedarikçi Ödemesi)
class Odeme(db.Model):
    __tablename__ = 'odeme'
    
    id = db.Column(db.Integer, primary_key=True)
    firma_musteri_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=False)
    kasa_id = db.Column(db.Integer, db.ForeignKey('kasa.id'), nullable=True)
    
    # Tarih Date formatında (Doğru)
    tarih = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    
    # Tutar Numeric formatında (Doğru)
    tutar = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    
    # --- EKLENEN KRİTİK ALAN: YÖN ---
    # 'tahsilat' = Kasaya Para Girişi (+)
    # 'odeme'    = Kasadan Para Çıkışı (-)
    yon = db.Column(db.String(20), default='tahsilat', nullable=False) 
    
    fatura_no = db.Column(db.String(50), nullable=True)
    vade_tarihi = db.Column(db.Date, nullable=True)
    aciklama = db.Column(db.String(250), nullable=True)

    # İlişkiler
    firma_musteri = db.relationship('Firma', back_populates='odemeler', foreign_keys=[firma_musteri_id])
    kasa = db.relationship('Kasa', back_populates='odemeler')
    
    def __repr__(self):
        return f'<Odeme {self.tutar} ({self.yon})>'

# 7. HIZMET KAYDI (Gelir/Gider Faturası)
class HizmetKaydi(db.Model):
    __tablename__ = 'hizmet_kaydi'
    
    id = db.Column(db.Integer, primary_key=True)
    firma_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=False)

    nakliye_id = db.Column(
        db.Integer, 
        db.ForeignKey('nakliye.id', ondelete='CASCADE'), 
        nullable=True
    )
    ozel_id = db.Column(db.Integer, nullable=True)
    # Tarih ve Tutar Numeric/Date (Doğru)
    tarih = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    tutar = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    
    aciklama = db.Column(db.String(250), nullable=True)
    
    # Yön: 'giden' (Gelir), 'gelen' (Gider)
    yon = db.Column(db.String(10), nullable=False, default='giden') 
    
    fatura_no = db.Column(db.String(50), nullable=True)
    vade_tarihi = db.Column(db.Date, nullable=True)

    # İlişkiler
    firma = db.relationship('Firma', back_populates='hizmet_kayitlari', foreign_keys=[firma_id])
    
    def __repr__(self):
        return f'<Hizmet {self.tutar}>'