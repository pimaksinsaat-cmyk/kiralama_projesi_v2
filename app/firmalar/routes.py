import os
from flask import render_template, url_for, redirect, flash, request
from sqlalchemy import or_, and_
import traceback
from decimal import Decimal
from datetime import date

from app import db
from app.firmalar import firmalar_bp
from app.firmalar.models import Firma
from app.kiralama.models import Kiralama, KiralamaKalemi
from app.filo.models import Ekipman
from app.cari.models import Kasa, Odeme, HizmetKaydi
from app.firmalar.forms import FirmaForm
from sqlalchemy.orm import joinedload, subqueryload

# YARDIMCI FONKSİYONLAR
from app.utils import klasor_adi_temizle

# -------------------------------------------------------------------------
# 1. Firma Listeleme (Görünürlük Sorunu Giderildi)
# -------------------------------------------------------------------------
@firmalar_bp.route('/')
@firmalar_bp.route('/index')
def index():
    try:
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '', type=str)
        
        # Filtre: is_active alanı True olanlar VEYA NULL (boş) kalanlar görünür
        # Veritabanı taşımalarında is_active alanı dolmamış firmalar bu sayede kaybolmaz.
        base_query = Firma.query.filter(
            and_(
                Firma.firma_adi != 'Dahili Kasa İşlemleri',
                or_(Firma.is_active == True, Firma.is_active == None)
            )
        )
        
        if q:
            search_term = f'%{q}%'
            base_query = base_query.filter(
                or_(
                    Firma.firma_adi.ilike(search_term),
                    Firma.yetkili_adi.ilike(search_term),
                    Firma.vergi_no.ilike(search_term),
                    Firma.telefon.ilike(search_term),
                    Firma.eposta.ilike(search_term)
                )
            )

        # Sayfa başına 50 kayıt göstererek listeyi daha kapsayıcı hale getirdik
        pagination = base_query.order_by(Firma.id.desc()).paginate(page=page, per_page=50, error_out=False)
        firmalar = pagination.items
        
        # Debug: Konsola listelenen miktar bilgisini basar
        print(f"Sistem Bilgisi: {len(firmalar)} firma listeleniyor.")
        
        return render_template('firmalar/index.html', firmalar=firmalar, pagination=pagination, q=q)
    except Exception as e:
        traceback.print_exc()
        flash(f"Liste yüklenirken hata oluştu: {str(e)}", "danger")
        return render_template('firmalar/index.html', firmalar=[], pagination=None, q=q)

# -------------------------------------------------------------------------
# 2. Yeni Firma Ekleme
# -------------------------------------------------------------------------
@firmalar_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    form = FirmaForm()
    if form.validate_on_submit():
        try:
            # Mükerrer vergi no kontrolü
            if form.vergi_no.data:
                mevcut = Firma.query.filter_by(vergi_no=form.vergi_no.data).first()
                if mevcut:
                    status = "arşivde" if not mevcut.is_active else "aktif"
                    flash(f"'{form.vergi_no.data}' vergi numarası zaten {status} bir kayıtta mevcut!", "warning")
                    return render_template('firmalar/ekle.html', form=form)

            yeni_firma = Firma(
                firma_adi=form.firma_adi.data,
                yetkili_adi=form.yetkili_adi.data,
                telefon=form.telefon.data,
                eposta=form.eposta.data,
                iletisim_bilgileri=form.iletisim_bilgileri.data,
                vergi_dairesi=form.vergi_dairesi.data,
                vergi_no=form.vergi_no.data,
                is_musteri=form.is_musteri.data,
                is_tedarikci=form.is_tedarikci.data,
                sozlesme_no=None, # Başlangıçta numara atanmaz
                sozlesme_rev_no=0,
                is_active=True,
                bakiye=Decimal('0')
            )
            db.session.add(yeni_firma)
            db.session.commit()
            flash(f"'{yeni_firma.firma_adi}' başarıyla kaydedildi. Sözleşme hazırlamak için listeden sağ tıklayın.", "success")
            return redirect(url_for('firmalar.index'))
        except Exception as e:
            db.session.rollback()
            flash(f"Kayıt hatası: {str(e)}", "danger")
    return render_template('firmalar/ekle.html', form=form, today_date=date.today().strftime('%d.%m.%Y'))

# -------------------------------------------------------------------------
# 3. Sözleşme Hazırla (PS Numarası Atama ve Klasörleme)
# -------------------------------------------------------------------------
@firmalar_bp.route('/sozlesme-hazirla/<int:id>', methods=['POST'])
def sozlesme_hazirla(id):
    firma = Firma.query.get_or_404(id)
    if firma.sozlesme_no:
        flash(f"'{firma.firma_adi}' için zaten bir sözleşme ({firma.sozlesme_no}) mevcut.", "info")
        return redirect(url_for('firmalar.index'))
    try:
        # PS Numarası Hesaplama (Yıl Bazlı)
        current_year = date.today().year
        last_firma = Firma.query.filter(Firma.sozlesme_no.like(f"PS-{current_year}-%"))\
                                .order_by(Firma.sozlesme_no.desc()).first()
        
        next_nr = 1
        if last_firma and last_firma.sozlesme_no:
            try:
                # Son numarayı alıp 1 artırıyoruz
                next_nr = int(last_firma.sozlesme_no.split('-')[-1]) + 1
            except: pass
        
        next_ps_no = f"PS-{current_year}-{next_nr:03d}"

        # Klasör İsimlendirme (FirmaAdı_VergiNo)
        ikinci_parametre = firma.vergi_no if firma.vergi_no else str(firma.id)
        klasor_adi = klasor_adi_temizle(firma.firma_adi, ikinci_parametre)
        
        firma.sozlesme_no = next_ps_no
        firma.sozlesme_tarihi = date.today()
        firma.bulut_klasor_adi = klasor_adi
        
        # Arşiv Klasörlerini Fiziksel Olarak Oluştur
        base_path = os.path.join(os.getcwd(), 'app', 'static', 'arsiv', klasor_adi)
        os.makedirs(os.path.join(base_path, 'PS'), exist_ok=True)
        os.makedirs(os.path.join(base_path, 'Kiralama_Formlari'), exist_ok=True)
        
        db.session.commit()
        flash(f"'{firma.firma_adi}' için {next_ps_no} nolu sözleşme ve arşiv klasörü hazırlandı.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"İşlem hatası: {str(e)}", "danger")
    return redirect(url_for('firmalar.index'))

# -------------------------------------------------------------------------
# 4. Firma Düzenleme
# -------------------------------------------------------------------------
@firmalar_bp.route('/duzelt/<int:id>', methods=['GET', 'POST'])
def duzelt(id):
    firma = Firma.query.get_or_404(id)
    form = FirmaForm(obj=firma)
    if request.method == 'GET':
        form.genel_sozlesme_no.data = firma.sozlesme_no
        form.sozlesme_rev_no.data = firma.sozlesme_rev_no
        form.sozlesme_tarihi.data = firma.sozlesme_tarihi

    if form.validate_on_submit():
        try:
            form.populate_obj(firma)
            firma.sozlesme_no = form.genel_sozlesme_no.data
            firma.sozlesme_rev_no = form.sozlesme_rev_no.data
            firma.sozlesme_tarihi = form.sozlesme_tarihi.data
            db.session.commit()
            flash('Firma bilgileri güncellendi!', 'success')
            return redirect(url_for('firmalar.index'))
        except Exception as e:
            db.session.rollback()
            flash(f"Hata: {str(e)}", "danger")
    return render_template('firmalar/duzelt.html', form=form, firma=firma)

# -------------------------------------------------------------------------
# 5. Firma Bilgi (Detaylı Cari Hesaplamalar)
# -------------------------------------------------------------------------
@firmalar_bp.route('/bilgi/<int:id>', methods=['GET'])
def bilgi(id):
    try:
        # Firmayı tüm finansal ilişkileriyle tek seferde çekiyoruz (Eager Loading)
        firma = Firma.query.options(
            subqueryload(Firma.kiralamalar).options(subqueryload(Kiralama.kalemler).options(joinedload(KiralamaKalemi.ekipman))),
            subqueryload(Firma.odemeler).joinedload(Odeme.kasa),
            subqueryload(Firma.hizmet_kayitlari),
        ).get_or_404(id)
        
        hareketler = []
        
        # 1. Hizmet ve Fatura Kayıtlarını İşle (Borç/Alacak Ayrımı)
        for h in firma.hizmet_kayitlari:
            tutar = h.tutar or Decimal('0')
            if hasattr(h, 'kiralama_id') and h.kiralama_id:
                tur_adi, tur_tipi, ozel_id = 'Kiralama', 'kiralama', h.kiralama_id
            elif hasattr(h, 'nakliye_id') and h.nakliye_id:
                tur_adi, tur_tipi, ozel_id = 'Nakliye', 'nakliye', h.nakliye_id
            else:
                tur_tipi, ozel_id = 'fatura', h.id
                tur_adi = 'Fatura (Satış)' if h.yon == 'giden' else 'Fatura (Alış)'

            hareketler.append({
                'id': h.id, 
                'ozel_id': ozel_id, 
                'tarih': h.tarih, 
                'tur': tur_adi,
                'tur_tipi': tur_tipi, 
                'aciklama': h.aciklama, 
                'belge_no': h.fatura_no,
                'borc': tutar if h.yon == 'giden' else Decimal('0'),
                'alacak': tutar if h.yon == 'gelen' else Decimal('0'),
                'nesne': h
            })

        # 2. Ödemeleri ve Tahsilatları İşle
        for o in firma.odemeler:
            tutar = o.tutar or Decimal('0')
            yon = getattr(o, 'yon', 'tahsilat')
            hareketler.append({
                'id': o.id, 
                'ozel_id': o.id, 
                'tarih': o.tarih,
                'tur': 'Tahsilat (Giriş)' if yon == 'tahsilat' else 'Ödeme (Çıkış)',
                'tur_tipi': 'odeme', 
                'aciklama': o.aciklama or 'Finansal İşlem',
                'belge_no': f"{o.kasa.kasa_adi if o.kasa else 'Kasa Tanımsız'}",
                'borc': tutar if yon == 'odeme' else Decimal('0'),
                'alacak': tutar if yon == 'tahsilat' else Decimal('0'),
                'nesne': o
            })

        # 3. Tüm Hareketleri Kronolojik Olarak Sırala
        hareketler.sort(key=lambda x: x['tarih'] if x['tarih'] else date.min)
        
        # 4. Yürüyen Bakiye Hesaplama
        yuruyen_bakiye, toplam_borc, toplam_alacak = Decimal('0'), Decimal('0'), Decimal('0')
        for islem in hareketler:
            toplam_borc += islem['borc']
            toplam_alacak += islem['alacak']
            # Borç toplama eklenir, alacak toplamdan çıkarılır
            yuruyen_bakiye = (yuruyen_bakiye + islem['borc']) - islem['alacak']
            islem['kumulatif_bakiye'] = yuruyen_bakiye

        # Bakiye Durumunu Belirle
        if yuruyen_bakiye > 0: 
            durum_metni, durum_rengi = "Borçlu", "text-danger"
        elif yuruyen_bakiye < 0: 
            durum_metni, durum_rengi = "Alacaklı", "text-success"
        else: 
            durum_metni, durum_rengi = "Hesap Kapalı", "text-muted"

        return render_template('firmalar/bilgi.html', 
                               firma=firma, 
                               hareketler=hareketler,
                               toplam_borc=toplam_borc, 
                               toplam_alacak=toplam_alacak,
                               bakiye=abs(yuruyen_bakiye), 
                               durum_metni=durum_metni, 
                               durum_rengi=durum_rengi)
    except Exception as e:
        traceback.print_exc()
        flash(f"Cari bilgiler yüklenirken hata oluştu: {str(e)}", "danger")
        return redirect(url_for('firmalar.index'))

# -------------------------------------------------------------------------
# 6. İmza Yetkisi Kontrolü
# -------------------------------------------------------------------------
@firmalar_bp.route('/imza-kontrol/<int:id>', methods=['POST'])
def imza_kontrol(id):
    firma = Firma.query.get_or_404(id)
    try:
        firma.imza_yetkisi_kontrol_edildi = True
        firma.imza_yetkisi_kontrol_tarihi = date.today()
        db.session.commit()
        flash("İmza yetkisi kontrolü başarıyla onaylandı.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Onay hatası: {str(e)}", "danger")
    return redirect(url_for('firmalar.bilgi', id=id))

# -------------------------------------------------------------------------
# 7. Firma Silme (Soft Delete / Arşivleme)
# -------------------------------------------------------------------------
@firmalar_bp.route('/sil/<int:id>', methods=['POST'])
def sil(id):
    firma = Firma.query.get_or_404(id)
    try:
        # Fiziksel silme yerine pasife çekme işlemi yapıyoruz
        firma.is_active = False
        db.session.commit()
        flash(f"'{firma.firma_adi}' başarıyla arşive kaldırıldı.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Silme hatası: {str(e)}", 'danger')
    return redirect(url_for('firmalar.index'))