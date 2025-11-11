from app import db
from datetime import datetime, date

# -------------------------------------------------------------------------
# 1. ANA MODEL: 'Firma'
# 'Musteri' ve 'Tedarikci' tablolarının yerini alan ana varlık.
# -------------------------------------------------------------------------
class Firma(db.Model):
    """
    Sisteme kayıtlı tüm şirketleri (firmaları) tutar.
    Bu firma hem müşteri (is_musteri) hem de tedarikçi (is_tedarikci)
    ya da her ikisi birden olabilir.
    """
    __tablename__ = 'firma' # ÖNEMLİ: Tablo adı 'musteri' idi, 'firma' oldu.

    id = db.Column(db.Integer, primary_key=True)
    firma_adi = db.Column(db.String(150), nullable=False, index=True)
    yetkili_adi = db.Column(db.String(100), nullable=False)
    iletisim_bilgileri = db.Column(db.String(200), nullable=False)
    vergi_dairesi = db.Column(db.String(100), nullable=False)
    vergi_no = db.Column(db.String(50), unique=True, nullable=False, index=True)

    # --- ROL SÜTUNLARI (Çift Yönlü Çalışma İçin) ---
    is_musteri = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_tedarikci = db.Column(db.Boolean, default=False, nullable=False, index=True)

    # --- İLİŞKİLER (Tüm Modüllere Bağlantı) ---
    
    # 1. Bu firmanın 'MÜŞTERİ' olarak yaptığı kiralamalar
    kiralamalar = db.relationship('Kiralama', 
                                  back_populates='firma_musteri', 
                                  foreign_keys='Kiralama.firma_musteri_id',
                                  cascade="all, delete-orphan")

    # 2. Bu firmanın 'TEDARİKÇİ' olarak sağladığı ekipman kayıtları
    tedarik_edilen_ekipmanlar = db.relationship('Ekipman', 
                                                back_populates='firma_tedarikci', 
                                                foreign_keys='Ekipman.firma_tedarikci_id')
    
    # 3. Bu firmanın 'MÜŞTERİ' olarak yaptığı ödemeler (Cari Modülü Alacak)
    odemeler = db.relationship('Odeme', 
                               back_populates='firma_musteri',
                               foreign_keys='Odeme.firma_musteri_id',
                               cascade="all, delete-orphan")

    # 4. Bu firmanın 'NAKLİYE TEDARİKÇİSİ' olduğu kalemler
    saglanan_nakliye_hizmetleri = db.relationship(
        'KiralamaKalemi', 
        back_populates='nakliye_tedarikci', 
        foreign_keys='KiralamaKalemi.nakliye_tedarikci_id'
    )
    
    # 5. Bu firmanın dahil olduğu 'Bağımsız Hizmet' kayıtları
    hizmet_kayitlari = db.relationship('HizmetKaydi', 
                                       back_populates='firma', 
                                       foreign_keys='HizmetKaydi.firma_id')
                                       
    # 6. (YENİ) Bu firmanın 'TEDARİKÇİ' olduğu stok kartları
    tedarik_edilen_parcalar = db.relationship('StokKarti', 
                                              back_populates='varsayilan_tedarikci', 
                                              foreign_keys='StokKarti.varsayilan_tedarikci_id')

    def __repr__(self):
        return f'<Firma {self.firma_adi}>'


# -------------------------------------------------------------------------
# 2. GÜNCELLENEN MODEL: 'Ekipman'
# (Bakım kayıtları için yeni ilişki eklendi)
# -------------------------------------------------------------------------
class Ekipman(db.Model):
    """
    Filodaki her bir makineyi temsil eder.
    'firma_tedarikci_id' alanı sayesinde harici makineleri de tutabilir.
    """
    __tablename__ = 'ekipman'

    id = db.Column(db.Integer, primary_key=True)
    kod = db.Column(db.String(100), unique=True, nullable=False, index=True)
    # ... (yakit, tipi, marka, seri_no, yukseklik, kapasite, uretim_tarihi...)
    yakit = db.Column(db.String(50), nullable=False, default='')
    tipi = db.Column(db.String(100), nullable=False, default='')
    marka = db.Column(db.String(100), nullable=False)
    seri_no = db.Column(db.String(100), unique=True, nullable=False, index=True)
    calisma_yuksekligi = db.Column(db.Integer, nullable=False)
    kaldirma_kapasitesi = db.Column(db.Integer, nullable=False)
    uretim_tarihi = db.Column(db.String(100), nullable=False)
    
    # Durumlar: 'bosta', 'kirada', 'serviste', 'harici'
    calisma_durumu = db.Column(db.String(50), nullable=False, default='bosta') 

    giris_maliyeti = db.Column(db.String(50), nullable=True, default='0')
    firma_tedarikci_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=True)
    
    # --- İlişkiler ---
    firma_tedarikci = db.relationship('Firma', back_populates='tedarik_edilen_ekipmanlar', foreign_keys=[firma_tedarikci_id])
    kiralama_kalemleri = db.relationship('KiralamaKalemi', 
                                         back_populates='ekipman', 
                                         cascade="all, delete-orphan")
                                         
    # --- YENİ (STOK/SERVİS MODÜLÜ İÇİN) ---
    # Bu ekipmana yapılan tüm bakım/servis işlemleri
    bakim_kayitlari = db.relationship('BakimKaydi', 
                                      back_populates='ekipman', 
                                      cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Ekipman {self.kod}>'


# -------------------------------------------------------------------------
# 3. GÜNCELLENEN MODEL: 'Kiralama' (Ana Form)
# (Değişiklik yok, 'Firma'ya bağlı)
# -------------------------------------------------------------------------
class Kiralama(db.Model):
    __tablename__ = 'kiralama'
    id = db.Column(db.Integer, primary_key=True)
    kiralama_form_no = db.Column(db.String(100), nullable=True)
    kdv_orani = db.Column(db.Integer, nullable=False, default=20)
    firma_musteri_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=False)
    
    firma_musteri = db.relationship('Firma', back_populates='kiralamalar', foreign_keys=[firma_musteri_id])
    kalemler = db.relationship('KiralamaKalemi', 
                               back_populates='kiralama', 
                               cascade="all, delete-orphan")

    def __repr__(self):
        if self.firma_musteri:
            return f'<Kiralama {self.kiralama_form_no or ""} - {self.firma_musteri.firma_adi}>'
        return f'<Kiralama {self.kiralama_form_no or ""}>'


# -------------------------------------------------------------------------
# 4. NİHAİ MODEL: 'KiralamaKalemi' (En Kritik Tablo)
# (Değişiklik yok, tüm finansalları içeriyor)
# -------------------------------------------------------------------------
class KiralamaKalemi(db.Model):
    __tablename__ = 'kiralama_kalemi'
    id = db.Column(db.Integer, primary_key=True)
    kiralama_id = db.Column(db.Integer, db.ForeignKey('kiralama.id'), nullable=False)
    ekipman_id = db.Column(db.Integer, db.ForeignKey('ekipman.id'), nullable=False)
    
    kiralama_baslangıcı = db.Column(db.String(50), nullable=False)
    kiralama_bitis = db.Column(db.String(50), nullable=False)

    kiralama_brm_fiyat = db.Column(db.String(50), nullable=False, default='0') # SATIŞ (Müşteriye)
    kiralama_alis_fiyat = db.Column(db.String(50), nullable=True, default='0') # ALIŞ (Ekipman tedarikçisine)

    nakliye_satis_fiyat = db.Column(db.String(50), nullable=True, default='0') # SATIŞ (Müşteriye)
    nakliye_alis_fiyat = db.Column(db.String(50), nullable=True, default='0') # ALIŞ (Nakliye tedarikçisine)
    nakliye_tedarikci_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=True)

    sonlandirildi = db.Column(db.Boolean, default=False, nullable=False)

    kiralama = db.relationship('Kiralama', back_populates='kalemler')
    ekipman = db.relationship('Ekipman', back_populates='kiralama_kalemleri')
    nakliye_tedarikci = db.relationship('Firma', back_populates='saglanan_nakliye_hizmetleri', foreign_keys=[nakliye_tedarikci_id])

    def __repr__(self):
        return f'<KiralamaKalemi K:{self.kiralama_id} E:{self.ekipman_id}>'


# -------------------------------------------------------------------------
# 5. YENİ MODEL: 'Odeme' (Cari Hesap - Alacak)
# (Değişiklik yok, 'Firma'ya bağlı)
# -------------------------------------------------------------------------
class Odeme(db.Model):
    __tablename__ = 'odeme'
    id = db.Column(db.Integer, primary_key=True)
    firma_musteri_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=False)
    firma_musteri = db.relationship('Firma', back_populates='odemeler', foreign_keys=[firma_musteri_id])
    tarih = db.Column(db.String(50), nullable=False)
    tutar = db.Column(db.String(50), nullable=False)
    aciklama = db.Column(db.String(250), nullable=True)

    def __repr__(self):
        if self.firma_musteri:
            return f'<Odeme {self.firma_musteri.firma_adi} - {self.tutar}>'
        return f'<Odeme {self.tutar}>'


# -------------------------------------------------------------------------
# 6. YENİ MODEL: 'HizmetKaydi' (Cari Hesap - Borç/Alacak Jokeri)
# (Değişiklik yok, 'Firma'ya bağlı)
# -------------------------------------------------------------------------
class HizmetKaydi(db.Model):
    __tablename__ = 'hizmet_kaydi'
    id = db.Column(db.Integer, primary_key=True)
    firma_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=False)
    firma = db.relationship('Firma', back_populates='hizmet_kayitlari', foreign_keys=[firma_id])
    tarih = db.Column(db.String(50), nullable=False)
    aciklama = db.Column(db.String(250), nullable=True)
    tutar = db.Column(db.String(50), nullable=False)
    yon = db.Column(db.String(10), nullable=False, default='giden') # 'giden' veya 'gelen'

    def __repr__(self):
        if self.firma:
            return f'<HizmetKaydi {self.firma.firma_adi} - {self.yon} - {self.tutar}>'
        return f'<HizmetKaydi {self.yon} - {self.tutar}>'

# -------------------------------------------------------------------------
# 7. YENİ MODEL: 'StokKarti' (Stok Modülü - Ana Tablo)
# -------------------------------------------------------------------------
class StokKarti(db.Model):
    """
    Stoktaki yedek parçaları (filtre, yağ vb.) tanımlar.
    """
    __tablename__ = 'stok_karti'
    id = db.Column(db.Integer, primary_key=True)
    parca_kodu = db.Column(db.String(100), unique=True, nullable=False, index=True)
    parca_adi = db.Column(db.String(250), nullable=False)
    mevcut_stok = db.Column(db.Integer, nullable=False, default=0)
    
    # Bu parçayı genellikle kimden aldığımızı bilmek için
    varsayilan_tedarikci_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=True)
    varsayilan_tedarikci = db.relationship('Firma', back_populates='tedarik_edilen_parcalar', foreign_keys=[varsayilan_tedarikci_id])
    
    # Bu parçanın kullanıldığı tüm bakım kayıtları
    kullanim_kayitlari = db.relationship('KullanilanParca', back_populates='stok_karti')

    def __repr__(self):
        return f'<StokKarti {self.parca_kodu} (Adet: {self.mevcut_stok})>'

# -------------------------------------------------------------------------
# 8. YENİ MODEL: 'BakimKaydi' (Servis Modülü - Ana Tablo)
# -------------------------------------------------------------------------
class BakimKaydi(db.Model):
    """
    Bir ekipmana yapılan her bir servis/bakım işlemini temsil eder.
    'HizmetKaydi'ndan farklıdır; bu, iç operasyonel bir kayıttır.
    """
    __tablename__ = 'bakim_kaydi'
    id = db.Column(db.Integer, primary_key=True)
    
    # Hangi ekipmana bakım yapıldı?
    ekipman_id = db.Column(db.Integer, db.ForeignKey('ekipman.id'), nullable=False)
    ekipman = db.relationship('Ekipman', back_populates='bakim_kayitlari')

    tarih = db.Column(db.String(50), nullable=False)
    aciklama = db.Column(db.String(500), nullable=True) # "Periyodik Bakım Yapıldı"
    calisma_saati = db.Column(db.Integer, nullable=True) # Bakım yapıldığındaki saat
    
    # Bu bakımda hangi parçalar kullanıldı?
    kullanilan_parcalar = db.relationship('KullanilanParca', 
                                          back_populates='bakim_kaydi', 
                                          cascade="all, delete-orphan")

    def __repr__(self):
        return f'<BakimKaydi Ekipman:{self.ekipman_id} - {self.tarih}>'

# -------------------------------------------------------------------------
# 9. YENİ MODEL: 'KullanilanParca' (İlişki Nesnesi)
# Stok ve Servis modüllerini birbirine bağlar.
# --------------------------------