from app.firmalar import firmalar_bp
from app import db
from flask import render_template, url_for, redirect, flash, request
from sqlalchemy import or_, and_
import traceback

# FİNANSAL HESAPLAMA İÇİN GEREKLİ
from decimal import Decimal
from datetime import date

# Modeller
from app.firmalar.models import Firma
from app.kiralama.models import Kiralama, KiralamaKalemi
from app.filo.models import Ekipman
from app.cari.models import Kasa, Odeme, HizmetKaydi 

from app.firmalar.forms import FirmaForm
from sqlalchemy.orm import joinedload, subqueryload

# -------------------------------------------------------------------------
# 1. Firma Listeleme
# -------------------------------------------------------------------------
@firmalar_bp.route('/')
@firmalar_bp.route('/index')
def index():
    try:
        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '', type=str)
        
        base_query = Firma.query.filter(
            and_(
                Firma.is_active == True,
                Firma.firma_adi != 'Dahili Kasa İşlemleri'
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
            
        pagination = base_query.order_by(Firma.firma_adi).paginate(page=page, per_page=25, error_out=False)
        firmalar = pagination.items
        return render_template('firmalar/index.html', firmalar=firmalar, pagination=pagination, q=q)
    except Exception as e:
        flash(f"Hata: {str(e)}", "danger")
        return render_template('firmalar/index.html', firmalar=[], pagination=None, q=q)

# -------------------------------------------------------------------------
# 2. Yeni Firma Ekleme
# -------------------------------------------------------------------------
@firmalar_bp.route('/ekle', methods=['GET', 'POST'])
def ekle():
    form = FirmaForm()
    if form.validate_on_submit():
        try:
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
                is_active=True,
                bakiye=Decimal('0')
            )
            db.session.add(yeni_firma)
            db.session.commit()
            flash('Firma başarıyla eklendi!', 'success')
            return redirect(url_for('firmalar.index'))
        except Exception as e:
            db.session.rollback()
            flash(f"Hata: {str(e)}", "danger")
    return render_template('firmalar/ekle.html', form=form)

# -------------------------------------------------------------------------
# 3. Firma Silme (Soft Delete)
# -------------------------------------------------------------------------
@firmalar_bp.route('/sil/<int:id>', methods=['POST'])
def sil(id):
    firma = Firma.query.get_or_404(id)
    try:
        firma.is_active = False
        db.session.commit()
        flash(f"'{firma.firma_adi}' arşive kaldırıldı.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Hata: {str(e)}", 'danger')
    return redirect(url_for('firmalar.index', page=request.args.get('page', 1, type=int), q=request.args.get('q', '')))

# -------------------------------------------------------------------------
# 4. Firma Düzenleme
# -------------------------------------------------------------------------
@firmalar_bp.route('/duzelt/<int:id>', methods=['GET', 'POST'])
def duzelt(id):
    firma = Firma.query.filter_by(id=id, is_active=True).first_or_404()
    form = FirmaForm(obj=firma)
    if form.validate_on_submit():
        try:
            form.populate_obj(firma)
            db.session.commit()
            flash('Firma bilgileri güncellendi!', 'success')
            return redirect(url_for('firmalar.index'))
        except Exception as e:
            db.session.rollback()
            flash(f"Hata: {str(e)}", "danger")
    return render_template('firmalar/duzelt.html', form=form, firma=firma) 

# -------------------------------------------------------------------------
# 5. Firma Bilgi Sayfası (DÜZELTİLDİ: ID BİLGİLERİ EKLENDİ)
# -------------------------------------------------------------------------
@firmalar_bp.route('/bilgi/<int:id>', methods=['GET'])
def bilgi(id):
    try:
        firma = Firma.query.options(
            subqueryload(Firma.kiralamalar).options(subqueryload(Kiralama.kalemler).options(joinedload(KiralamaKalemi.ekipman))),
            subqueryload(Firma.odemeler).joinedload(Odeme.kasa),
            subqueryload(Firma.hizmet_kayitlari),
        ).get_or_404(id)
        
        hareketler = []

        # 1. Hizmet/Fatura Kayıtları (Nakliye ve Kiralama Ayrımı Eklendi)
        for h in firma.hizmet_kayitlari:

            print(f"İşlem ID: {h.id} | Kiralama ID: {getattr(h, 'ozel_id', 'YOK')} | Nakliye ID: {getattr(h, 'nakliye_id', 'YOK')}")
            tutar = h.tutar or Decimal('0')
            borc = Decimal('0')
            alacak = Decimal('0')
            # --- GARANTİYE ALINMIŞ TÜR BELİRLEME ---
            # 'kiralama_id' isminden emin değilsen modelindeki tam adı yazmalısın
            k_id = getattr(h, 'kiralama_id', None)
            n_id = getattr(h, 'nakliye_id', None)
            # --- TÜR VE ÖZEL ID BELİRLEME (HİÇBİR ŞEY SİLİNMEDİ) ---
            if hasattr(h, 'kiralama_id') and h.kiralama_id:
                tur_adi = 'Kiralama'
                tur_tipi = 'kiralama'
                ozel_id = h.kiralama_id # JS'nin kiralama düzenlemeye gitmesi için
            elif hasattr(h, 'nakliye_id') and h.nakliye_id:
                tur_adi = 'Nakliye'
                tur_tipi = 'nakliye'
                ozel_id = h.nakliye_id # JS'nin nakliye düzenlemeye gitmesi için
            else:
                # Standart Fatura
                tur_tipi = 'fatura'
                ozel_id = h.id
                if h.yon == 'giden':
                    tur_adi = 'Fatura (Satış)'
                else:
                    tur_adi = 'Fatura (Alış)'

            if h.yon == 'giden':
                borc = tutar
            else:
                alacak = tutar

            hareketler.append({
                'id': h.id,          # Cari tablo ID'si (Silme işlemi için şart)
                'ozel_id': ozel_id,  # Kiralama veya Nakliye ID'si (Düzenleme için şart)
                'tarih': h.tarih,
                'tur': tur_adi,
                'tur_tipi': tur_tipi,
                'aciklama': h.aciklama,
                'belge_no': h.fatura_no,
                'borc': borc,
                'alacak': alacak,
                'nesne': h,
                'nakliye_id': h.nakliye_id if hasattr(h, 'nakliye_id') else None,
                'kiralama_id': h.kiralama_id if hasattr(h, 'kiralama_id') else None 
            })

        # 2. Ödemeler / Tahsilatlar (KODUN OLDUĞU GİBİ KORUNDU)
        for o in firma.odemeler:
            tutar = o.tutar or Decimal('0')
            borc = Decimal('0')
            alacak = Decimal('0')
            yon = getattr(o, 'yon', 'tahsilat')
            
            if yon == 'tahsilat':
                alacak = tutar
                tur_adi = 'Tahsilat (Giriş)'
            elif yon == 'odeme':
                borc = tutar
                tur_adi = 'Ödeme (Çıkış)'

            hareketler.append({
                'id': o.id,
                'ozel_id': o.id, # Ödemelerde özel ID kendisidir
                'tarih': o.tarih,
                'tur': tur_adi,
                'tur_tipi': 'odeme',
                'aciklama': o.aciklama or 'Finansal İşlem',
                'belge_no': f"{o.kasa.kasa_adi if o.kasa else ''}",
                'borc': borc,
                'alacak': alacak,
                'nesne': o
            })

        # 3. Sırala (KORUNDU)
        hareketler.sort(key=lambda x: x['tarih'] if x['tarih'] else date.min)

        # 4. Kümülatif Hesaplama (KORUNDU)
        yuruyen_bakiye = Decimal('0')
        toplam_borc = Decimal('0')
        toplam_alacak = Decimal('0')

        for islem in hareketler:
            toplam_borc += islem['borc']
            toplam_alacak += islem['alacak']
            yuruyen_bakiye = (yuruyen_bakiye + islem['borc']) - islem['alacak']
            islem['kumulatif_bakiye'] = yuruyen_bakiye

        genel_bakiye = yuruyen_bakiye
        
        # Durum belirleme (KORUNDU)
        if genel_bakiye > 0:
            durum_metni = "Borçlu (Bize Ödemeli)"
            durum_rengi = "text-danger"
        elif genel_bakiye < 0:
            durum_metni = "Alacaklı (Biz Ödeyeceğiz)"
            durum_rengi = "text-success"
        else:
            durum_metni = "Hesap Kapalı"
            durum_rengi = "text-muted"

        return render_template('firmalar/bilgi.html', 
                               firma=firma,
                               hareketler=hareketler,
                               toplam_borc=toplam_borc,
                               toplam_alacak=toplam_alacak,
                               bakiye=genel_bakiye,
                               durum_metni=durum_metni,
                               durum_rengi=durum_rengi)
                               
    except Exception as e:
        traceback.print_exc()
        flash(f"Hata: {str(e)}", "danger")
        return redirect(url_for('firmalar.index'))
# -------------------------------------------------------------------------
# 6. Firma İmza Yetkisi Kontrol Onayı
# -------------------------------------------------------------------------
@firmalar_bp.route('/imza-kontrol/<int:id>', methods=['POST'])
def imza_kontrol(id):
    firma = Firma.query.get_or_404(id)

    try:
        if not firma.imza_yetkisi_kontrol_edildi:
            firma.imza_yetkisi_kontrol_edildi = True
            firma.imza_yetkisi_kontrol_tarihi = date.today()
            # İleride user sistemi bağlarsan:
            # firma.imza_yetkisi_kontrol_eden_id = current_user.id

            db.session.commit()
            flash("İmza yetkisi kontrol edildi olarak işaretlendi.", "success")
        else:
            flash("Bu firma için imza yetkisi zaten kontrol edilmiş.", "info")

    except Exception as e:
        db.session.rollback()
        flash(f"Hata: {str(e)}", "danger")

    return redirect(url_for('firmalar.bilgi', id=id))
