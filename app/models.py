from app import db
from datetime import datetime, date

# -------------------------------------------------------------------------
# 1. ANA MODEL: 'Firma'
# -------------------------------------------------------------------------
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

    # İlişkiler
    kiralamalar = db.relationship('Kiralama', back_populates='firma_musteri', foreign_keys='Kiralama.firma_musteri_id', cascade="all, delete-orphan")
    tedarik_edilen_ekipmanlar = db.relationship('Ekipman', back_populates='firma_tedarikci', foreign_keys='Ekipman.firma_tedarikci_id')
    odemeler = db.relationship('Odeme', back_populates='firma_musteri', foreign_keys='Odeme.firma_musteri_id', cascade="all, delete-orphan")
    saglanan_nakliye_hizmetleri = db.relationship('KiralamaKalemi', back_populates='nakliye_tedarikci', foreign_keys='KiralamaKalemi.nakliye_tedarikci_id')
    hizmet_kayitlari = db.relationship('HizmetKaydi', back_populates='firma', foreign_keys='HizmetKaydi.firma_id')
    
    tedarik_edilen_parcalar = db.relationship('StokKarti', back_populates='varsayilan_tedarikci', foreign_keys='StokKarti.varsayilan_tedarikci_id')
    stok_hareketleri = db.relationship('StokHareket', back_populates='firma', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Firma {self.firma_adi}>'

# -------------------------------------------------------------------------
# 2. YENİ MODEL: 'Kasa' (Banka/Nakit)
# -------------------------------------------------------------------------
class Kasa(db.Model):
    __tablename__ = 'kasa'
    id = db.Column(db.Integer, primary_key=True)
    kasa_adi = db.Column(db.String(100), nullable=False) # Örn: "Merkez Kasa", "Garanti Bankası"
    tipi = db.Column(db.String(20), nullable=False, default='nakit') # 'nakit' veya 'banka'
    para_birimi = db.Column(db.String(3), nullable=False, default='TRY')
    bakiye = db.Column(db.String(50), nullable=False, default='0')

    odemeler = db.relationship('Odeme', back_populates='kasa')

    def __repr__(self):
        return f'<Kasa {self.kasa_adi}>'

# -------------------------------------------------------------------------
# 3. GÜNCELLENEN MODEL: 'Ekipman'
# (Model, Marka, Maliyet, Para Birimi Alanları Tam)
# -------------------------------------------------------------------------
class Ekipman(db.Model):
    __tablename__ = 'ekipman'

    id = db.Column(db.Integer, primary_key=True)
    kod = db.Column(db.String(100), unique=True, nullable=False, index=True)
    
    # Özellikler
    yakit = db.Column(db.String(50), nullable=False, default='')
    tipi = db.Column(db.String(100), nullable=False, default='')
    marka = db.Column(db.String(100), nullable=False)
    model = db.Column(db.String(100), nullable=True, default='') 
    seri_no = db.Column(db.String(100), nullable=False, index=True) 
    calisma_yuksekligi = db.Column(db.Integer, nullable=False)
    kaldirma_kapasitesi = db.Column(db.Integer, nullable=False)
    uretim_tarihi = db.Column(db.String(100), nullable=False)
    calisma_durumu = db.Column(db.String(50), nullable=False, default='bosta') 
    
    # Finansal
    giris_maliyeti = db.Column(db.String(50), nullable=True, default='0')
    para_birimi = db.Column(db.String(3), nullable=False, default='TRY') 

    # İlişkiler
    firma_tedarikci_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=True)
    firma_tedarikci = db.relationship('Firma', back_populates='tedarik_edilen_ekipmanlar', foreign_keys=[firma_tedarikci_id])
    
    kiralama_kalemleri = db.relationship('KiralamaKalemi', back_populates='ekipman', cascade="all, delete-orphan")
    bakim_kayitlari = db.relationship('BakimKaydi', back_populates='ekipman', cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint('firma_tedarikci_id', 'seri_no', name='_tedarikci_seri_no_uc'),
    )

    def __repr__(self):
        return f'<Ekipman {self.kod}>'

# -------------------------------------------------------------------------
# 4. GÜNCELLENEN MODEL: 'Kiralama'
# (Döviz Kurları Tam)
# -------------------------------------------------------------------------
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

    def __repr__(self):
        if getattr(self, 'firma_musteri', None):
            return f'<Kiralama {self.kiralama_form_no or ""} - {self.firma_musteri.firma_adi}>'
        return f'<Kiralama {self.kiralama_form_no or ""}>'

# -------------------------------------------------------------------------
# 5. MODEL: 'KiralamaKalemi'
# -------------------------------------------------------------------------
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

    def __repr__(self):
        return f'<KiralamaKalemi K:{self.kiralama_id} E:{self.ekipman_id}>'

# -------------------------------------------------------------------------
# 6. GÜNCELLENEN MODEL: 'Odeme'
# (Kasa, Fatura Detayları Eklendi)
# -------------------------------------------------------------------------
class Odeme(db.Model):
    __tablename__ = 'odeme'
    id = db.Column(db.Integer, primary_key=True)
    
    firma_musteri_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=False)
    firma_musteri = db.relationship('Firma', back_populates='odemeler', foreign_keys=[firma_musteri_id])
    
    kasa_id = db.Column(db.Integer, db.ForeignKey('kasa.id'), nullable=True)
    kasa = db.relationship('Kasa', back_populates='odemeler')

    tarih = db.Column(db.String(50), nullable=False)
    tutar = db.Column(db.String(50), nullable=False)
    
    fatura_no = db.Column(db.String(50), nullable=True)
    vade_tarihi = db.Column(db.String(50), nullable=True)
    
    aciklama = db.Column(db.String(250), nullable=True)

    def __repr__(self):
        return f'<Odeme {self.tutar}>'

# -------------------------------------------------------------------------
# 7. GÜNCELLENEN MODEL: 'HizmetKaydi'
# (Fatura Detayları Eklendi)
# -------------------------------------------------------------------------
class HizmetKaydi(db.Model):
    __tablename__ = 'hizmet_kaydi'
    id = db.Column(db.Integer, primary_key=True)
    
    firma_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=False)
    firma = db.relationship('Firma', back_populates='hizmet_kayitlari', foreign_keys=[firma_id])
    
    tarih = db.Column(db.String(50), nullable=False)
    aciklama = db.Column(db.String(250), nullable=True)
    tutar = db.Column(db.String(50), nullable=False)
    yon = db.Column(db.String(10), nullable=False, default='giden') 
    
    fatura_no = db.Column(db.String(50), nullable=True)
    vade_tarihi = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f'<HizmetKaydi {self.tutar}>'

# -------------------------------------------------------------------------
# 8. MODEL: 'StokKarti'
# -------------------------------------------------------------------------
class StokKarti(db.Model):
    __tablename__ = 'stok_karti'
    id = db.Column(db.Integer, primary_key=True)
    parca_kodu = db.Column(db.String(100), unique=True, nullable=False, index=True)
    parca_adi = db.Column(db.String(250), nullable=False)
    mevcut_stok = db.Column(db.Integer, nullable=False, default=0)
    
    varsayilan_tedarikci_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=True)
    varsayilan_tedarikci = db.relationship('Firma', back_populates='tedarik_edilen_parcalar', foreign_keys=[varsayilan_tedarikci_id])
    
    hareketler = db.relationship('StokHareket', back_populates='stok_karti', cascade="all, delete-orphan")
    kullanim_kayitlari = db.relationship('KullanilanParca', back_populates='stok_karti')

    def __repr__(self):
        return f'<StokKarti {self.parca_kodu}>'

# -------------------------------------------------------------------------
# 9. YENİ MODEL: 'StokHareket' (Stok Giriş/Çıkış)
# -------------------------------------------------------------------------
class StokHareket(db.Model):
    __tablename__ = 'stok_hareket'
    id = db.Column(db.Integer, primary_key=True)
    
    stok_karti_id = db.Column(db.Integer, db.ForeignKey('stok_karti.id'), nullable=False)
    firma_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=True) 
    
    tarih = db.Column(db.String(50), nullable=False)
    adet = db.Column(db.Integer, nullable=False) 
    birim_fiyat = db.Column(db.String(50), nullable=True, default='0') 
    
    hareket_tipi = db.Column(db.String(20), nullable=False, default='giris')
    fatura_no = db.Column(db.String(50), nullable=True)
    aciklama = db.Column(db.String(250), nullable=True)

    stok_karti = db.relationship('StokKarti', back_populates='hareketler')
    firma = db.relationship('Firma', back_populates='stok_hareketleri')

    def __repr__(self):
        return f'<StokHareket {self.stok_karti.parca_kodu}>'

# -------------------------------------------------------------------------
# 10. MODEL: 'BakimKaydi'
# -------------------------------------------------------------------------
class BakimKaydi(db.Model):
    __tablename__ = 'bakim_kaydi'
    id = db.Column(db.Integer, primary_key=True)
    
    ekipman_id = db.Column(db.Integer, db.ForeignKey('ekipman.id'), nullable=False)
    ekipman = db.relationship('Ekipman', back_populates='bakim_kayitlari')

    tarih = db.Column(db.String(50), nullable=False)
    aciklama = db.Column(db.String(500), nullable=True) 
    calisma_saati = db.Column(db.Integer, nullable=True) 
    
    kullanilan_parcalar = db.relationship('KullanilanParca', back_populates='bakim_kaydi', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<BakimKaydi Ekipman:{self.ekipman_id}>'

# -------------------------------------------------------------------------
# 11. MODEL: 'KullanilanParca'
# -------------------------------------------------------------------------
class KullanilanParca(db.Model):
    __tablename__ = 'kullanilan_parca'
    id = db.Column(db.Integer, primary_key=True)
    
    bakim_kaydi_id = db.Column(db.Integer, db.ForeignKey('bakim_kaydi.id'), nullable=False)
    stok_karti_id = db.Column(db.Integer, db.ForeignKey('stok_karti.id'), nullable=False)
    
    kullanilan_adet = db.Column(db.Integer, nullable=False, default=1)
    
    bakim_kaydi = db.relationship('BakimKaydi', back_populates='kullanilan_parcalar')
    stok_karti = db.relationship('StokKarti', back_populates='kullanim_kayitlari')

    def __repr__(self):
        return f'<Kullanim B:{self.bakim_kaydi_id} S:{self.stok_karti_id}>'