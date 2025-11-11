from app import db

#
# ÖNEMLİ NOT: 'kiralama_ekipman_association' adlı db.Table nesnesi
# bu yeni "Association Object" modelinde artık GEREKLİ DEĞİLDİR ve silinmiştir.
#

class Ekipman(db.Model):
    """
    Filodaki her bir makineyi temsil eder.
    """
    __tablename__ = 'ekipman'

    id = db.Column(db.Integer, primary_key=True)
    kod = db.Column(db.String(100), unique=True, nullable=False, index=True)
    yakit = db.Column(db.String(50), nullable=False, default='')
    tipi = db.Column(db.String(100), nullable=False, default='')
    marka = db.Column(db.String(100), nullable=False)
    seri_no = db.Column(db.String(100), unique=True, nullable=False, index=True)
    calisma_yuksekligi = db.Column(db.Integer, nullable=False)
    kaldirma_kapasitesi = db.Column(db.Integer, nullable=False)
    uretim_tarihi = db.Column(db.String(100), nullable=False)
    calisma_durumu = db.Column(db.String(50), nullable=False, default='bosta')

    # DEĞİŞEN İLİŞKİ:
    # Bir Ekipman, birden çok 'KiralamaKalemi' satırında yer alabilir.
    # 'Kiralama' ile doğrudan ilişkisi kalmadı.
    kiralama_kalemleri = db.relationship('KiralamaKalemi', 
                                         back_populates='ekipman', 
                                         cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Ekipman {self.kod}>'


class Musteri(db.Model):
    """
    Müşteri (Firma) bilgilerini tutar.
    Bu modelde bir değişiklik yapılmadı.
    """
    __tablename__ = 'musteri'

    id = db.Column(db.Integer, primary_key=True)
    firma_adi = db.Column(db.String(150), nullable=False)
    yetkili_adi = db.Column(db.String(100), nullable=False)
    iletisim_bilgileri = db.Column(db.String(200), nullable=False)
    vergi_dairesi = db.Column(db.String(100), nullable=False)
    vergi_no = db.Column(db.String(50), unique=True, nullable=False)

    # Kiralama (ana form) ile bire-çok ilişkisi devam ediyor.
    kiralamalar = db.relationship('Kiralama', 
                                  back_populates='musteri', 
                                  cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Musteri {self.firma_adi}>'


class KiralamaKalemi(db.Model):
    """
    YENİ MODEL (Association Object)
    ...
    """
    __tablename__ = 'kiralama_kalemi'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # --- Yabancı Anahtarlar (Foreign Keys) ---
    kiralama_id = db.Column(db.Integer, db.ForeignKey('kiralama.id'), nullable=False)
    ekipman_id = db.Column(db.Integer, db.ForeignKey('ekipman.id'), nullable=False)
    
    # --- Kaleme Özel Veriler ---
    kiralama_baslangıcı = db.Column(db.String(50), nullable=False)
    kiralama_bitis = db.Column(db.String(50), nullable=False)
    kiralama_brm_fiyat = db.Column(db.String(50), nullable=False)
    nakliye_fiyat = db.Column(db.String(50), nullable=False, default='0')

    # --- YENİ EKLENECEK SÜTUN ---
    # Bu, kiralama kaleminin 'filo' sayfasından kalıcı olarak 
    # sonlandırılıp sonlandırılmadığını belirler.
    sonlandirildi = db.Column(db.Boolean, default=False, nullable=False)
    # --- YENİ SÜTUN SONU ---

    # --- İlişki Tanımları (back_populates) ---
    kiralama = db.relationship('Kiralama', back_populates='kalemler')
    ekipman = db.relationship('Ekipman', back_populates='kiralama_kalemleri')

    def __repr__(self):
        return f'<KiralamaKalemi (K:{self.kiralama_id} E:{self.ekipman_id} Fiyat:{self.kiralama_brm_fiyat})>'


class Kiralama(db.Model):
    """
    Ana Kiralama Formu. Artık sadece Müşteri ve Form No gibi
    genel bilgileri ve 'KiralamaKalemi' listesini tutar.
    """
    __tablename__ = 'kiralama'

    id = db.Column(db.Integer, primary_key=True)
    kiralama_form_no = db.Column(db.String(100), nullable=True)

    # --- YENİ EKLENECEK ALAN ---
    # KDV Oranı. Varsayılan olarak %20.
    kdv_orani = db.Column(db.Integer, nullable=False, default=20)
    # --- YENİ ALAN SONU ---

    # Müşteri ilişkisi (Aynı kaldı)
    musteri_id = db.Column(db.Integer, db.ForeignKey('musteri.id'), nullable=False)
    musteri = db.relationship('Musteri', back_populates='kiralamalar')

    # DEĞİŞEN İLİŞKİ:
    # 'ekipmanlar' listesi yerine, 'KiralamaKalemi' nesnelerinin
    # listesini tutan 'kalemler' listesi geldi.
    kalemler = db.relationship('KiralamaKalemi', 
                               back_populates='kiralama', 
                               cascade="all, delete-orphan")

    # TAŞINAN ALANLAR:
    # Aşağıdaki 4 alan 'KiralamaKalemi' modeline taşındı:
    # - kiralama_baslangıcı
    # - kiralama_bitis
    # - kiralama_brm_fiyat
    # - nakliye_fiyat

    def __repr__(self):
        return f'<Kiralama {self.kiralama_form_no or ""} - {self.musteri.firma_adi}>'