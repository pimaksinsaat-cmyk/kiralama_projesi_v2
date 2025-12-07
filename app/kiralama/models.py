from app.extensions import db
# 4. KIRALAMA (Ana Form)
class Kiralama(db.Model):
    __tablename__ = 'kiralama'
    id = db.Column(db.Integer, primary_key=True)
    kiralama_form_no = db.Column(db.String(100), nullable=True)
    kdv_orani = db.Column(db.Integer, nullable=False, default=20)
    doviz_kuru_usd = db.Column(db.Float, nullable=True, default=0.0)
    doviz_kuru_eur = db.Column(db.Float, nullable=True, default=0.0)
    firma_musteri_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=False)
    
    firma_musteri = db.relationship('Firma', back_populates='kiralamalar', foreign_keys=[firma_musteri_id])
    kalemler = db.relationship('KiralamaKalemi', back_populates='kiralama', cascade="all, delete-orphan")
    def __repr__(self): return f'<Kiralama {self.kiralama_form_no}>'

# 5. KIRALAMA KALEMI (Satırlar)
class KiralamaKalemi(db.Model):
    __tablename__ = 'kiralama_kalemi'
    id = db.Column(db.Integer, primary_key=True)
    kiralama_id = db.Column(db.Integer, db.ForeignKey('kiralama.id'), nullable=False)
    ekipman_id = db.Column(db.Integer, db.ForeignKey('ekipman.id'), nullable=False)
    kiralama_baslangıcı = db.Column(db.String(50), nullable=False)
    kiralama_bitis = db.Column(db.String(50), nullable=False)
    kiralama_brm_fiyat = db.Column(db.String(50), nullable=False, default='0') 
    kiralama_alis_fiyat = db.Column(db.String(50), nullable=True, default='0') 
    nakliye_satis_fiyat = db.Column(db.String(50), nullable=True, default='0') 
    nakliye_alis_fiyat = db.Column(db.String(50), nullable=True, default='0') 
    nakliye_tedarikci_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=True)
    sonlandirildi = db.Column(db.Boolean, default=False, nullable=False)

    kiralama = db.relationship('Kiralama', back_populates='kalemler')
    ekipman = db.relationship('Ekipman', back_populates='kiralama_kalemleri')
    nakliye_tedarikci = db.relationship('Firma', back_populates='saglanan_nakliye_hizmetleri', foreign_keys=[nakliye_tedarikci_id])
    def __repr__(self): return f'<Kalem K:{self.kiralama_id} E:{self.ekipman_id}>'
