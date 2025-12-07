from app.extensions import db
# 2. KASA (Yeni)
class Kasa(db.Model):
    __tablename__ = 'kasa'
    id = db.Column(db.Integer, primary_key=True)
    kasa_adi = db.Column(db.String(100), nullable=False)
    tipi = db.Column(db.String(20), nullable=False, default='nakit')
    para_birimi = db.Column(db.String(3), nullable=False, default='TRY')
    bakiye = db.Column(db.String(50), nullable=False, default='0')
    odemeler = db.relationship('Odeme', back_populates='kasa')
    def __repr__(self): return f'<Kasa {self.kasa_adi}>'

# 6. ODEME (Tahsilat)
class Odeme(db.Model):
    __tablename__ = 'odeme'
    id = db.Column(db.Integer, primary_key=True)
    firma_musteri_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=False)
    kasa_id = db.Column(db.Integer, db.ForeignKey('kasa.id'), nullable=True)
    tarih = db.Column(db.String(50), nullable=False)
    tutar = db.Column(db.String(50), nullable=False)
    fatura_no = db.Column(db.String(50), nullable=True)
    vade_tarihi = db.Column(db.String(50), nullable=True)
    aciklama = db.Column(db.String(250), nullable=True)

    firma_musteri = db.relationship('Firma', back_populates='odemeler', foreign_keys=[firma_musteri_id])
    kasa = db.relationship('Kasa', back_populates='odemeler')
    def __repr__(self): return f'<Odeme {self.tutar}>'

# 7. HIZMET KAYDI (Gelir/Gider Faturası)
class HizmetKaydi(db.Model):
    __tablename__ = 'hizmet_kaydi'
    id = db.Column(db.Integer, primary_key=True)
    firma_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=False)
    tarih = db.Column(db.String(50), nullable=False)
    aciklama = db.Column(db.String(250), nullable=True)
    tutar = db.Column(db.String(50), nullable=False)
    yon = db.Column(db.String(10), nullable=False, default='giden') 
    fatura_no = db.Column(db.String(50), nullable=True)
    vade_tarihi = db.Column(db.String(50), nullable=True)

    firma = db.relationship('Firma', back_populates='hizmet_kayitlari', foreign_keys=[firma_id])
    def __repr__(self): return f'<Hizmet {self.tutar}>'
