from app.extensions import db
# 1. FIRMA (Müşteri/Tedarikçi)
class Firma(db.Model):
    __tablename__ = 'firma'
    id = db.Column(db.Integer, primary_key=True)
    firma_adi = db.Column(db.String(150), nullable=False, index=True)
    yetkili_adi = db.Column(db.String(100), nullable=False)
    iletisim_bilgileri = db.Column(db.String(200), nullable=False)
    vergi_dairesi = db.Column(db.String(100), nullable=False)
    vergi_no = db.Column(db.String(50), unique=True, nullable=False, index=True)
    is_musteri = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_tedarikci = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    bakiye = db.Column(db.String(50), default='0.0') 
    kiralamalar = db.relationship('Kiralama', back_populates='firma_musteri', foreign_keys='Kiralama.firma_musteri_id', cascade="all, delete-orphan")
    tedarik_edilen_ekipmanlar = db.relationship('Ekipman', back_populates='firma_tedarikci', foreign_keys='Ekipman.firma_tedarikci_id')
    odemeler = db.relationship('Odeme', back_populates='firma_musteri', foreign_keys='Odeme.firma_musteri_id', cascade="all, delete-orphan")
    saglanan_nakliye_hizmetleri = db.relationship('KiralamaKalemi', back_populates='nakliye_tedarikci', foreign_keys='KiralamaKalemi.nakliye_tedarikci_id')
    hizmet_kayitlari = db.relationship('HizmetKaydi', back_populates='firma', foreign_keys='HizmetKaydi.firma_id')
    tedarik_edilen_parcalar = db.relationship('StokKarti', back_populates='varsayilan_tedarikci', foreign_keys='StokKarti.varsayilan_tedarikci_id')
    stok_hareketleri = db.relationship('StokHareket', back_populates='firma', cascade="all, delete-orphan")
    
    def __repr__(self): return f'<Firma {self.firma_adi}>'