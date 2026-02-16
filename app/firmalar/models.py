from app.extensions import db
from datetime import date

# 1. FIRMA (Müşteri/Tedarikçi)
class Firma(db.Model):
    __tablename__ = 'firma'
    
    id = db.Column(db.Integer, primary_key=True)
    firma_adi = db.Column(db.String(150), nullable=False, index=True)
    yetkili_adi = db.Column(db.String(100), nullable=False)
    
    telefon = db.Column(db.String(20), nullable=True)
    eposta = db.Column(db.String(120), nullable=True, index=True)


    # GÜNCELLEME: Adresler uzun olabilir, Text daha güvenlidir.
    iletisim_bilgileri = db.Column(db.Text, nullable=False)
    
    vergi_dairesi = db.Column(db.String(100), nullable=False)
    vergi_no = db.Column(db.String(50), unique=True, nullable=False, index=True)
    
    # Rol Tanımları
    is_musteri = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_tedarikci = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # KRİTİK GÜNCELLEME: Float -> Numeric(15, 2)
    bakiye = db.Column(db.Numeric(15, 2), default=0, nullable=False)

    # --- YENİ: SÖZLEŞME VE BULUT YÖNETİM ALANLARI ---
    # Sözleşme Takibi
    sozlesme_no = db.Column(db.String(50), unique=False, nullable=True) # Örn: PS-2026-001
    sozlesme_rev_no = db.Column(db.Integer, default=0, nullable=True) # Yenilendikçe artacak
    sozlesme_tarihi = db.Column(db.Date, nullable=True, default=date.today)
    
    # Bulut Klasör Yönetimi
    # Örn: "145_pimaks_i" şeklinde slugified klasör adı
    bulut_klasor_adi = db.Column(db.String(100), unique=True, nullable=True)



    # -------------------------------------------------
    # İMZA YETKİSİ / SÖZLEŞME KONTROL DURUMU (HAFİF)
    # -------------------------------------------------
    
    # Firma imza yetkisi kontrol edildi mi?
    imza_yetkisi_kontrol_edildi = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    # Kontrol tarihi (manuel veya sistemsel)
    imza_yetkisi_kontrol_tarihi = db.Column(
        db.DateTime,
        nullable=True
    )

    # Kim kontrol etti (User id, FK yok -> giriftlik yok)
    imza_yetkisi_kontrol_eden_id = db.Column(
        db.Integer,
        nullable=True
    )

    # Opsiyonel: Fiziksel arşiv / klasör notu
    imza_arsiv_notu = db.Column(
        db.String(255),
        nullable=True
    )

    # --- İLİŞKİLER (RELATIONSHIPS) ---
    # Not: foreign_keys parametreleri string referans olarak bırakıldı,
    # böylece circular import hatası almazsınız.
    
    # Kiralama Modülü
    kiralamalar = db.relationship(
        'Kiralama',
        back_populates='firma_musteri',
        foreign_keys='Kiralama.firma_musteri_id',
        cascade="all, delete-orphan",
        order_by="desc(Kiralama.id)"
    )
    
    # Filo Modülü (Tedarikçi ise)
    tedarik_edilen_ekipmanlar = db.relationship(
        'Ekipman',
        back_populates='firma_tedarikci',
        foreign_keys='Ekipman.firma_tedarikci_id'
    )
    
    # Cari / Ödeme Modülü
    odemeler = db.relationship(
        'Odeme',
        back_populates='firma_musteri',
        foreign_keys='Odeme.firma_musteri_id',
        cascade="all, delete-orphan"
    )
    
    # Nakliye Hizmetleri
    saglanan_nakliye_hizmetleri = db.relationship(
        'KiralamaKalemi',
        back_populates='nakliye_tedarikci',
        foreign_keys='KiralamaKalemi.nakliye_tedarikci_id'
    )
    
    # Muhasebe Kayıtları (Hizmet/Fatura)
    hizmet_kayitlari = db.relationship(
        'HizmetKaydi',
        back_populates='firma',
        foreign_keys='HizmetKaydi.firma_id'
    )
    
    # Stok Modülü
    tedarik_edilen_parcalar = db.relationship(
        'StokKarti',
        back_populates='varsayilan_tedarikci',
        foreign_keys='StokKarti.varsayilan_tedarikci_id'
    )

    stok_hareketleri = db.relationship(
        'StokHareket',
        back_populates='firma',
        cascade="all, delete-orphan"
    )

    # Nakliye Modülü
    nakliyeler = db.relationship(
        'Nakliye',
        back_populates='firma',
        cascade="all, delete-orphan"
    )
    
    def __repr__(self):
        return f'<Firma {self.firma_adi}>'
