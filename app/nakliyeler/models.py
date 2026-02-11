from app.extensions import db
from datetime import date
from decimal import Decimal

class Nakliye(db.Model):
    __tablename__ = 'nakliye'

    # --- Temel Kimlik Bilgileri ---
    id = db.Column(db.Integer, primary_key=True)
    # Operasyon tarihi (Saat karmaşası olmaması için Date kullanıldı)
    tarih = db.Column(db.Date, default=date.today, nullable=False)
    
    # --- İlişkiler ---
    # Firma tablosundaki ID'yi referans alır.
    firma_id = db.Column(db.Integer, db.ForeignKey('firma.id'), nullable=False)
    
    # Firma modeliyle senkronizasyon (Firma.nakliyeler ile konuşur)
    firma = db.relationship('Firma', back_populates='nakliyeler')

    # --- Operasyonel Bilgiler ---
    guzergah = db.Column(db.String(200), nullable=False)  # Örn: "Depo - Şantiye A"
    plaka = db.Column(db.String(20), nullable=True)       # Örn: "34 ABC 123"
    aciklama = db.Column(db.Text, nullable=True)          # Detaylı yük notları
    
    # --- Parasal Veriler (Yüksek Hassasiyetli Numeric Yapı) ---
    # Numeric(15, 2) -> 9.9 Trilyon TL'ye kadar kuruşu kuruşuna doğru hesaplama sağlar.
    tutar = db.Column(db.Numeric(15, 2), nullable=False, default=Decimal('0.00')) 
    kdv_orani = db.Column(db.Integer, default=20) # Varsayılan KDV %20
    toplam_tutar = db.Column(db.Numeric(15, 2), nullable=False, default=Decimal('0.00')) 
    
    # --- Durum ve Arşiv Kontrolleri ---
    cari_islendi_mi = db.Column(db.Boolean, default=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    cari_hareket = db.relationship(
        'HizmetKaydi', 
        backref='ilgili_nakliye', 
        cascade='all, delete-orphan', 
        uselist=False
    )

    def hesapla_ve_guncelle(self):
        """
        Matrah (tutar) ve KDV üzerinden toplam tutarı hesaplar.
        Decimal kullanarak float yuvarlama hatalarını önler.
        """
        if self.tutar:
            kdv_carpani = Decimal(self.kdv_orani) / Decimal(100)
            kdv_miktari = self.tutar * kdv_carpani
            self.toplam_tutar = self.tutar + kdv_miktari
        return self.toplam_tutar

    def __repr__(self):
        return f'<Nakliye #{self.id} | {self.guzergah} | {self.toplam_tutar} TL>'