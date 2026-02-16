from app.extensions import db
from datetime import datetime

class Kiralama(db.Model):
    __tablename__ = 'kiralama'
    
    id = db.Column(db.Integer, primary_key=True)
    kiralama_form_no = db.Column(db.String(100), nullable=True)
    kdv_orani = db.Column(db.Integer, nullable=False, default=20)
    
    # Döviz kurları için yüksek hassasiyet (Numeric)
    doviz_kuru_usd = db.Column(db.Numeric(10, 4), nullable=True, default=0.0)
    doviz_kuru_eur = db.Column(db.Numeric(10, 4), nullable=True, default=0.0)
    
    firma_musteri_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=False)
    
    # İlişkiler
    firma_musteri = db.relationship('Firma', back_populates='kiralamalar', foreign_keys=[firma_musteri_id])
    kalemler = db.relationship('KiralamaKalemi', back_populates='kiralama', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Kiralama {self.kiralama_form_no}>'

class KiralamaKalemi(db.Model):
    __tablename__ = 'kiralama_kalemi'
    
    id = db.Column(db.Integer, primary_key=True)
    kiralama_id = db.Column(db.Integer, db.ForeignKey('kiralama.id'), nullable=False)
    
    # PİMAKS FİLOSU (Kendi makinemiz ise burası dolu olur)
    ekipman_id = db.Column(db.Integer, db.ForeignKey('ekipman.id'), nullable=True)
    
    # --- DIŞ TEDARİK (HARİCİ) EKİPMAN BİLGİLERİ ---
    is_dis_tedarik_ekipman = db.Column(db.Boolean, default=False)
    harici_ekipman_tipi = db.Column(db.String(100))
    harici_ekipman_marka = db.Column(db.String(100))
    harici_ekipman_model = db.Column(db.String(100))
    harici_ekipman_seri_no = db.Column(db.String(100))
    harici_ekipman_kapasite = db.Column(db.Integer) 
    harici_ekipman_yukseklik = db.Column(db.Integer)
    harici_ekipman_uretim_yili = db.Column(db.Integer)
    harici_ekipman_tedarikci_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=True)
    
    # --- TARİHLER ---
    kiralama_baslangici = db.Column(db.Date, nullable=False)
    kiralama_bitis = db.Column(db.Date, nullable=False)
    
    # --- FİNANSAL VERİLER ---
    kiralama_brm_fiyat = db.Column(db.Numeric(15, 2), nullable=False, default=0.0) 
    kiralama_alis_fiyat = db.Column(db.Numeric(15, 2), nullable=True, default=0.0) 
    
    # --- NAKLİYE ---
    is_oz_mal_nakliye = db.Column(db.Boolean, default=True)
    is_harici_nakliye = db.Column(db.Boolean, default=False)
    nakliye_satis_fiyat = db.Column(db.Numeric(15, 2), nullable=True, default=0.0) 
    nakliye_alis_fiyat = db.Column(db.Numeric(15, 2), nullable=True, default=0.0) 
    nakliye_tedarikci_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=True)
    nakliye_araci_id = db.Column(db.Integer, db.ForeignKey('ekipman.id'), nullable=True)
    
    sonlandirildi = db.Column(db.Boolean, default=False, nullable=False)

    # --- İLİŞKİLER (Ambiguity/Belirsizlik Giderildi) ---
    kiralama = db.relationship('Kiralama', back_populates='kalemler')
    
    # Kiralanan asıl makine ilişkisi
    ekipman = db.relationship('Ekipman', back_populates='kiralama_kalemleri', foreign_keys=[ekipman_id])
    
    # Nakliye aracı ilişkisi (Backref ekleyerek karışıklığı önledik)
    nakliye_araci = db.relationship('Ekipman', foreign_keys=[nakliye_araci_id], backref='yapilan_nakliyeler')
    
    harici_tedarikci = db.relationship('Firma', foreign_keys=[harici_ekipman_tedarikci_id])
    nakliye_tedarikci = db.relationship('Firma', foreign_keys=[nakliye_tedarikci_id])

    def __repr__(self):
        return f'<KiralamaKalemi {self.id}>'