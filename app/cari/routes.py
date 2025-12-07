from app.cari import cari_bp
from app import db
from flask import render_template, redirect, url_for, flash, request
from datetime import datetime
from decimal import Decimal, InvalidOperation
import traceback

# Modeller ve Formlar
from app.models import Odeme, HizmetKaydi, Firma, Kasa ,Kiralama
from app.forms import OdemeForm, HizmetKaydiForm, KasaForm

# -------------------------------------------------------------------------
# YARDIMCI FONKSİYONLAR
# -------------------------------------------------------------------------
def clean_currency_input(value_str):
    """
    TR formatındaki (1.500,50) veriyi Decimal formatına (1500.50) çevirir.
    Hatalı veri gelirse 0.0 döner.
    """
    if not value_str:
        return Decimal('0.0')
    
    val = str(value_str).strip()
    # Önce binlik ayracını (.) kaldır, sonra kuruş ayracını (,) nokta yap
    if ',' in val:
        val = val.replace('.', '').replace(',', '.')
    
    try:
        return Decimal(val)
    except (ValueError, InvalidOperation):
        return Decimal('0.0')

def bakiye_guncelle(model_obj, tutar_decimal, islem_tipi='ekle'):
    """
    Firma veya Kasa bakiyesini güvenli şekilde günceller.
    tutar_decimal: İşlem tutarı (Artı veya Eksi olabilir)
    islem_tipi: 'ekle' (yeni kayıt) veya 'sil' (kayıt iptali)
    """
    if not model_obj: return

    # Veritabanında String tutuyoruz, işlem için Decimal'e çevir
    mevcut = Decimal(model_obj.bakiye or 0)
    
    if islem_tipi == 'ekle':
        # Yeni işlem ekleniyorsa, tutarı bakiyeye ekle
        model_obj.bakiye = str(mevcut + tutar_decimal)
    elif islem_tipi == 'sil':
        # İşlem siliniyorsa, etkinin tersini yap (Çıkar)
        model_obj.bakiye = str(mevcut - tutar_decimal)

def str_to_date(tarih_str):
    """String tarihleri (2025-10-25) datetime objesine çevirir."""
    if not tarih_str: return None
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(tarih_str, fmt)
        except ValueError:
            continue
    return None
# -------------------------------------------------------------------------
# 1. ÖDEME / TAHSİLAT İŞLEMLERİ
# -------------------------------------------------------------------------

@cari_bp.route('/odeme/ekle', methods=['GET', 'POST'])
def odeme_ekle():
    """TAHSİLAT (PARA GİRİŞİ): Kasa Artar (+), Firma Bakiyesi Düşer (-)"""
    form = OdemeForm()
    
    # --- FORM SEÇENEKLERİNİ DOLDURMA (GET/POST ayırmadan) ---
    form.firma_musteri_id.choices = [(0, '--- Müşteri Seçiniz ---')]
    try:
        musteriler = Firma.query.filter_by(is_musteri=True, is_active=True).order_by(Firma.firma_adi).all()
        form.firma_musteri_id.choices += [(f.id, f.firma_adi) for f in musteriler]
    except: pass

    form.kasa_id.choices = [(0, '--- Kasa Seçiniz ---')]
    try:
        kasalar = Kasa.query.order_by(Kasa.kasa_adi).all()
        form.kasa_id.choices += [(k.id, f"{k.kasa_adi} ({k.para_birimi})") for k in kasalar]
    except: pass
    # --------------------------------------------------------

    if request.method == 'GET':
        form.tarih.data = datetime.today().date()
        if request.args.get('musteri_id'):
            form.firma_musteri_id.data = request.args.get('musteri_id', type=int)

    if form.validate_on_submit():
        try:
            # Giriş işlemi: Pozitif Tutar
            tutar_net = abs(clean_currency_input(form.tutar.data))
            
            yeni_odeme = Odeme(
                firma_musteri_id=form.firma_musteri_id.data,
                kasa_id=form.kasa_id.data,
                tarih=form.tarih.data.strftime('%Y-%m-%d'),
                tutar=str(tutar_net), # DB'ye ARTI olarak kaydet
                fatura_no=form.fatura_no.data,
                vade_tarihi=form.vade_tarihi.data.strftime('%Y-%m-%d') if form.vade_tarihi.data else None,
                aciklama=form.aciklama.data
            )
            db.session.add(yeni_odeme)
            
            # 1. KASA GÜNCELLE (Para Girdiği için ARTAR)
            kasa = Kasa.query.get(form.kasa_id.data)
            bakiye_guncelle(kasa, tutar_net, 'ekle')

            # 2. FİRMA GÜNCELLE (Tahsilat yaptık, müşterinin borcu DÜŞER)
            firma = Firma.query.get(form.firma_musteri_id.data)
            bakiye_guncelle(firma, -tutar_net, 'ekle')

            db.session.commit()
            flash('Tahsilat alındı. Kasa arttı, cari bakiye düştü.', 'success')
            return redirect(url_for('firmalar.bilgi', id=form.firma_musteri_id.data))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Hata: {str(e)}', 'danger')
            traceback.print_exc()

    return render_template('cari/odeme_ekle.html', form=form)

@cari_bp.route('/odeme/yap', methods=['GET', 'POST'])
def odeme_yap():
    """ÖDEME YAPMA (PARA ÇIKIŞI): Kasa Azalır (-), Firma Alacağı Düşer (-)"""
    form = OdemeForm()
    
    # --- FORM SEÇENEKLERİNİ DOLDURMA ---
    form.firma_musteri_id.choices = [(0, '--- Firma Seçiniz ---')]
    try:
        firmalar = Firma.query.filter_by(is_active=True).order_by(Firma.firma_adi).all()
        form.firma_musteri_id.choices += [(f.id, f.firma_adi) for f in firmalar]
    except: pass

    form.kasa_id.choices = [(0, '--- Kasa Seçiniz ---')]
    try:
        kasalar = Kasa.query.order_by(Kasa.kasa_adi).all()
        form.kasa_id.choices += [(k.id, f"{k.kasa_adi} ({k.para_birimi})") for k in kasalar]
    except: pass
    # -----------------------------------

    if request.method == 'GET':
        form.tarih.data = datetime.today().date()
        if request.args.get('musteri_id'):
            form.firma_musteri_id.data = request.args.get('musteri_id', type=int)

    if form.validate_on_submit():
        try:
            # Çıkış işlemi: Negatif Tutar
            tutar_girilen = abs(clean_currency_input(form.tutar.data))
            tutar_net = -tutar_girilen # EKSİ YAPIYORUZ

            # Açıklamaya Kasa Adı Ekleme (Opsiyonel)
            aciklama_final = form.aciklama.data
            
            yeni_odeme = Odeme(
                firma_musteri_id=form.firma_musteri_id.data,
                kasa_id=form.kasa_id.data,
                tarih=form.tarih.data.strftime('%Y-%m-%d'),
                tutar=str(tutar_net), # DB'ye EKSİ olarak kaydet
                fatura_no=form.fatura_no.data,
                vade_tarihi=form.vade_tarihi.data.strftime('%Y-%m-%d') if form.vade_tarihi.data else None,
                aciklama=aciklama_final
            )
            db.session.add(yeni_odeme)
            
            # 1. KASA GÜNCELLE (Para Çıktığı için AZALIR - tutar_net zaten eksi)
            kasa = Kasa.query.get(form.kasa_id.data)
            bakiye_guncelle(kasa, tutar_net, 'ekle')
            
            # 2. FİRMA GÜNCELLE (Ödeme yaptık, borcumuz DÜŞER)
            firma = Firma.query.get(form.firma_musteri_id.data)
            bakiye_guncelle(firma, tutar_net, 'ekle')

            db.session.commit()
            flash('Ödeme yapıldı. Kasa ve cari bakiye güncellendi.', 'success')
            return redirect(url_for('firmalar.bilgi', id=form.firma_musteri_id.data))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Hata: {str(e)}', 'danger')
            traceback.print_exc()

    return render_template('cari/odeme_yap.html', form=form)

@cari_bp.route('/odeme/duzelt/<int:id>', methods=['GET', 'POST'])
def odeme_duzelt(id):
    odeme = Odeme.query.get_or_404(id)
    form = OdemeForm(obj=odeme)
    
    # --- SEÇENEKLERİ DOLDURMA ---
    form.firma_musteri_id.choices = [(0, '--- Seçiniz ---')]
    form.kasa_id.choices = [(0, '--- Seçiniz ---')]
    try:
        form.firma_musteri_id.choices += [(f.id, f.firma_adi) for f in Firma.query.all()]
        form.kasa_id.choices += [(k.id, k.kasa_adi) for k in Kasa.query.all()]
    except: pass
    
    if request.method == 'GET':
        # Ekrana basarken EKSİ işareti kafa karıştırmasın diye mutlak değer göster
        if odeme.tutar:
            val = str(abs(Decimal(odeme.tutar))).replace('.', ',')
            form.tutar.data = val
        if odeme.tarih:
             form.tarih.data = datetime.strptime(odeme.tarih, '%Y-%m-%d').date()

    if form.validate_on_submit():
        try:
            # 1. ESKİ İŞLEMİ GERİ AL (ROLLBACK)
            eski_tutar = Decimal(odeme.tutar or 0)
            eski_kasa = Kasa.query.get(odeme.kasa_id)
            eski_firma = Firma.query.get(odeme.firma_musteri_id)
            
            # Eski kasadan etkiyi sil
            bakiye_guncelle(eski_kasa, eski_tutar, 'sil')
            
            # Eski firmadan etkiyi sil
            if eski_firma:
                # Tahsilat (Pozitif) -> Firma bakiyesi düşmüştü. Geri almak için EKLEMEK lazım.
                if eski_tutar > 0:
                    eski_firma.bakiye = str(Decimal(eski_firma.bakiye or 0) + eski_tutar)
                # Ödeme (Negatif) -> Firma bakiyesi düşmüştü. Geri almak için EKLEMEK lazım (abs).
                else:
                    eski_firma.bakiye = str(Decimal(eski_firma.bakiye or 0) + abs(eski_tutar))

            # 2. YENİ VERİLERİ HAZIRLA
            girilen_tutar = abs(clean_currency_input(form.tutar.data))
            # Eski işlem negatifse (Ödeme Yap), yeni işlem de negatif olmalı
            yeni_tutar = girilen_tutar if eski_tutar >= 0 else -girilen_tutar
            
            odeme.firma_musteri_id = form.firma_musteri_id.data
            odeme.kasa_id = form.kasa_id.data
            odeme.tarih = form.tarih.data.strftime('%Y-%m-%d')
            odeme.tutar = str(yeni_tutar)
            odeme.aciklama = form.aciklama.data
            odeme.fatura_no = form.fatura_no.data
            
            # 3. YENİ İŞLEMİ UYGULA
            yeni_kasa = Kasa.query.get(odeme.kasa_id)
            yeni_firma = Firma.query.get(odeme.firma_musteri_id)
            
            # Kasa güncellenir
            bakiye_guncelle(yeni_kasa, yeni_tutar, 'ekle')
            
            # Firma güncellenir
            if yeni_firma:
                if yeni_tutar > 0: # Tahsilat -> Bakiye Düşer
                    yeni_firma.bakiye = str(Decimal(yeni_firma.bakiye or 0) - yeni_tutar)
                else: # Ödeme Yap -> Bakiye Düşer
                    yeni_firma.bakiye = str(Decimal(yeni_firma.bakiye or 0) + yeni_tutar) # tutar eksi

            db.session.commit()
            flash('İşlem güncellendi.', 'success')
            return redirect(url_for('firmalar.bilgi', id=odeme.firma_musteri_id))

        except Exception as e:
            db.session.rollback()
            flash(f'Hata: {str(e)}', 'danger')
            traceback.print_exc()

    return render_template('cari/odeme_duzelt.html', form=form, odeme=odeme)

@cari_bp.route('/odeme/sil/<int:id>', methods=['POST'])
def odeme_sil(id):
    odeme = Odeme.query.get_or_404(id)
    firma_id = odeme.firma_musteri_id
    try:
        tutar = Decimal(odeme.tutar or 0)
        
        # 1. KASADAN GERİ AL
        if odeme.kasa:
            bakiye_guncelle(odeme.kasa, tutar, 'sil')
            
        # 2. FİRMADAN GERİ AL (Her durumda borç geri gelir)
        firma = Firma.query.get(firma_id)
        if firma:
            mevcut = Decimal(firma.bakiye or 0)
            firma.bakiye = str(mevcut + abs(tutar))
        
        db.session.delete(odeme)
        db.session.commit()
        flash('İşlem silindi, bakiyeler eski haline döndü.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {str(e)}', 'danger')
        
    return redirect(url_for('firmalar.bilgi', id=firma_id))

# -------------------------------------------------------------------------
# 2. HİZMET / FATURA İŞLEMLERİ
# -------------------------------------------------------------------------

@cari_bp.route('/hizmet/ekle', methods=['GET', 'POST'])
def hizmet_ekle():
    form = HizmetKaydiForm()
    # Select doldurma...
    form.firma_id.choices = [(0, '--- Seçiniz ---')]
    try:
        form.firma_id.choices += [(f.id, f.firma_adi) for f in Firma.query.all()]
    except: pass

    if request.method == 'GET':
        form.tarih.data = datetime.today().date()
        if request.args.get('firma_id'): form.firma_id.data = int(request.args.get('firma_id'))

    if form.validate_on_submit():
        try:
            tutar = abs(clean_currency_input(form.tutar.data))
            
            yeni_hizmet = HizmetKaydi(
                firma_id=form.firma_id.data,
                tarih=form.tarih.data.strftime('%Y-%m-%d'),
                tutar=str(tutar),
                aciklama=form.aciklama.data,
                yon=form.yon.data,
                fatura_no=form.fatura_no.data,
                vade_tarihi=form.vade_tarihi.data
            )
            db.session.add(yeni_hizmet)
            
            # FİRMA BAKİYESİ GÜNCELLEME (Fatura bakiyeyi artırır)
            firma = Firma.query.get(form.firma_id.data)
            bakiye_guncelle(firma, tutar, 'ekle')

            db.session.commit()
            flash('Fatura/Hizmet kaydedildi.', 'success')
            return redirect(url_for('firmalar.bilgi', id=form.firma_id.data))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Hata: {str(e)}', 'danger')

    return render_template('cari/hizmet_ekle.html', form=form)

@cari_bp.route('/hizmet/duzelt/<int:id>', methods=['GET', 'POST'])
def hizmet_duzelt(id):
    hizmet = HizmetKaydi.query.get_or_404(id)
    form = HizmetKaydiForm(obj=hizmet)
    
    # Select doldurma...
    form.firma_id.choices = [(0, '--- Seçiniz ---')]
    try:
        form.firma_id.choices += [(f.id, f.firma_adi) for f in Firma.query.all()]
    except: pass

    if request.method == 'GET':
         if hizmet.tutar: form.tutar.data = str(hizmet.tutar).replace('.', ',')
         if hizmet.tarih: form.tarih.data = datetime.strptime(hizmet.tarih, '%Y-%m-%d').date()

    if form.validate_on_submit():
        try:
            eski_tutar = Decimal(hizmet.tutar or 0)
            eski_firma = Firma.query.get(hizmet.firma_id)
            
            # 1. Eski bakiyeyi geri al
            if eski_firma:
                bakiye_guncelle(eski_firma, eski_tutar, 'sil')
            
            # 2. Veriyi Güncelle
            yeni_tutar = abs(clean_currency_input(form.tutar.data))
            hizmet.tutar = str(yeni_tutar)
            hizmet.firma_id = form.firma_id.data
            hizmet.aciklama = form.aciklama.data
            hizmet.fatura_no = form.fatura_no.data
            hizmet.tarih = form.tarih.data.strftime('%Y-%m-%d')
            
            # 3. Yeni bakiyeyi ekle
            yeni_firma = Firma.query.get(hizmet.firma_id)
            bakiye_guncelle(yeni_firma, yeni_tutar, 'ekle')

            db.session.commit()
            flash('Fatura güncellendi.', 'success')
            return redirect(url_for('firmalar.bilgi', id=hizmet.firma_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Hata: {str(e)}', 'danger')

    return render_template('cari/hizmet_duzelt.html', form=form, hizmet=hizmet)

@cari_bp.route('/hizmet/sil/<int:id>', methods=['POST'])
def hizmet_sil(id):
    hizmet = HizmetKaydi.query.get_or_404(id)
    firma_id = hizmet.firma_id
    try:
        # Faturayı silersek, müşterinin borcu (bakiyesi) DÜŞMELİ
        tutar = Decimal(hizmet.tutar or 0)
        firma = Firma.query.get(firma_id)
        if firma:
            bakiye_guncelle(firma, tutar, 'sil')
            
        db.session.delete(hizmet)
        db.session.commit()
        flash('Fatura silindi, bakiye güncellendi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {str(e)}', 'danger')
        
    return redirect(url_for('firmalar.bilgi', id=firma_id))

# -------------------------------------------------------------------------
# 3. KASA / BANKA YÖNETİMİ
# -------------------------------------------------------------------------
@cari_bp.route('/kasa/listesi')
def kasa_listesi():
    kasalar = Kasa.query.order_by(Kasa.kasa_adi).all()
    return render_template('cari/kasa_listesi.html', kasalar=kasalar)

@cari_bp.route('/kasa/ekle', methods=['GET', 'POST'])
def kasa_ekle():
    form = KasaForm()
    if form.validate_on_submit():
        try:
            yeni_kasa = Kasa(
                kasa_adi=form.kasa_adi.data,
                tipi=form.tipi.data,
                para_birimi=form.para_birimi.data,
                bakiye=str(form.bakiye.data or 0.0)
            )
            db.session.add(yeni_kasa)
            db.session.commit()
            flash('Kasa açıldı.', 'success')
            return redirect(url_for('cari.kasa_listesi'))
        except Exception as e:
            flash(f'Hata: {e}', 'danger')
    return render_template('cari/kasa_ekle.html', form=form)

@cari_bp.route('/kasa/duzelt/<int:id>', methods=['GET', 'POST'])
def kasa_duzelt(id):
    kasa = Kasa.query.get_or_404(id)
    form = KasaForm(obj=kasa)
    diger_kasalar = Kasa.query.filter(Kasa.id != id, Kasa.para_birimi == kasa.para_birimi).all()
    
    if request.method == 'GET':
        form.bakiye.data = Decimal(kasa.bakiye or 0)

    if form.validate_on_submit():
        try:
            kasa.kasa_adi = form.kasa_adi.data
            kasa.tipi = form.tipi.data
            kasa.para_birimi = form.para_birimi.data
            kasa.bakiye = str(form.bakiye.data or 0.0)
            db.session.commit()
            flash('Hesap bilgileri güncellendi.', 'success')
            return redirect(url_for('cari.kasa_listesi'))
        except Exception as e:
            db.session.rollback()
            flash(f'Hata: {str(e)}', 'danger')

    return render_template('cari/kasa_duzelt.html', form=form, kasa=kasa, diger_kasalar=diger_kasalar)

@cari_bp.route('/kasa/sil/<int:id>', methods=['POST'])
def kasa_sil(id):
    kasa = Kasa.query.get_or_404(id)
    hedef_kasa_id = request.form.get('hedef_kasa_id')
    
    try:
        bakiye = float(kasa.bakiye or 0)
        
        if bakiye != 0:
            if hedef_kasa_id:
                hedef_kasa = Kasa.query.get(hedef_kasa_id)
                if hedef_kasa:
                    # Bakiyeyi devret
                    hedef_kasa.bakiye = str(float(hedef_kasa.bakiye or 0) + bakiye)
                    
                    # Kayıt at
                    dahili_firma = get_dahili_islem_firmasi()
                    devir_kaydi = Odeme(
                        firma_musteri_id=dahili_firma.id,
                        kasa_id=hedef_kasa.id,
                        tarih=datetime.now().strftime('%Y-%m-%d'),
                        tutar=str(bakiye),
                        aciklama=f"Kasa Kapanış Devri: {kasa.kasa_adi} hesabından."
                    )
                    db.session.add(devir_kaydi)
                    flash(f"Bakiye '{hedef_kasa.kasa_adi}' hesabına devredildi.", 'info')
                else:
                    flash('Hata: Hedef hesap bulunamadı.', 'danger')
                    return redirect(url_for('cari.kasa_listesi')) # Düzeltme: Liste'ye dön
            else:
                flash('Hata: Bakiye sıfır değil, lütfen devredilecek hesabı seçin!', 'danger')
                return redirect(url_for('cari.kasa_listesi'))
        
        db.session.delete(kasa)
        db.session.commit()
        flash('Hesap başarıyla silindi.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {str(e)}', 'danger')
        
    return redirect(url_for('cari.kasa_listesi'))

@cari_bp.route('/kasa/hareketler/<int:id>')
def kasa_hareketleri(id):
    kasa = Kasa.query.get_or_404(id)
    hareketler = Odeme.query.filter_by(kasa_id=id).order_by(Odeme.tarih.desc(), Odeme.id.desc()).all()
    return render_template('cari/kasa_hareketleri.html', kasa=kasa, hareketler=hareketler, now=datetime.now)

@cari_bp.route('/kasa/hizli_islem', methods=['POST'])
def kasa_hizli_islem():
    try:
        kasa_id = request.form.get('kasa_id', type=int)
        islem_yonu = request.form.get('islem_yonu') 
        tutar_str = request.form.get('tutar')
        aciklama = request.form.get('aciklama')
        
        tutar = float(clean_currency_input(tutar_str))
        if tutar <= 0:
            flash("Tutar sıfırdan büyük olmalıdır.", "warning")
            return redirect(url_for('cari.kasa_listesi'))

        kasa = Kasa.query.get_or_404(kasa_id)
        dahili_firma = get_dahili_islem_firmasi()
        
        # Giriş ise pozitif, Çıkış ise negatif
        islem_tutari = tutar if islem_yonu == 'giris' else -tutar
        
        yeni_hareket = Odeme(
            firma_musteri_id=dahili_firma.id,
            kasa_id=kasa.id,
            tarih=datetime.now().strftime('%Y-%m-%d'),
            tutar=str(islem_tutari),
            aciklama=f"Hızlı İşlem ({'Giriş' if islem_yonu=='giris' else 'Çıkış'}): {aciklama}"
        )
        db.session.add(yeni_hareket)

        # Kasa bakiyesini güncelle
        mevcut = Decimal(kasa.bakiye or 0)
        kasa.bakiye = str(mevcut + Decimal(islem_tutari))
        
        db.session.commit()
        flash(f"İşlem kaydedildi.", 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f"İşlem Hatası: {str(e)}", 'danger')
        traceback.print_exc()
        
    return redirect(url_for('cari.kasa_listesi'))

@cari_bp.route('/kasa/transfer', methods=['POST'])
def kasa_transfer():
    try:
        kaynak_id = request.form.get('kaynak_kasa_id', type=int)
        hedef_id = request.form.get('hedef_kasa_id', type=int)
        tutar_str = request.form.get('tutar')
        aciklama = request.form.get('aciklama')
        
        tutar = Decimal(clean_currency_input(tutar_str))
        if tutar <= 0:
            flash("Transfer tutarı sıfırdan büyük olmalıdır.", "warning")
            return redirect(url_for('cari.kasa_listesi'))

        kaynak = Kasa.query.get_or_404(kaynak_id)
        hedef = Kasa.query.get_or_404(hedef_id)
        dahili_firma = get_dahili_islem_firmasi()
        
        if kaynak.para_birimi != hedef.para_birimi:
            flash("Hata: Farklı para birimleri arasında transfer yapılamaz.", "danger")
            return redirect(url_for('cari.kasa_listesi'))

        # Kaynak -> Çıkış
        cikis_kaydi = Odeme(
            firma_musteri_id=dahili_firma.id,
            kasa_id=kaynak.id,
            tarih=datetime.now().strftime('%Y-%m-%d'),
            tutar=str(-tutar),
            aciklama=f"Transfer Çıkışı -> {hedef.kasa_adi} ({aciklama})"
        )
        db.session.add(cikis_kaydi)
        kaynak.bakiye = str(Decimal(kaynak.bakiye or 0) - tutar)

        # Hedef -> Giriş
        giris_kaydi = Odeme(
            firma_musteri_id=dahili_firma.id,
            kasa_id=hedef.id,
            tarih=datetime.now().strftime('%Y-%m-%d'),
            tutar=str(tutar),
            aciklama=f"Transfer Girişi <- {kaynak.kasa_adi} ({aciklama})"
        )
        db.session.add(giris_kaydi)
        hedef.bakiye = str(Decimal(hedef.bakiye or 0) + tutar)
        
        db.session.commit()
        flash(f"Transfer başarıyla tamamlandı.", 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f"Transfer Hatası: {str(e)}", 'danger')
        traceback.print_exc()
        
    return redirect(url_for('cari.kasa_listesi'))


@cari_bp.route('/finans-menu')
def finans_menu():
    return render_template('cari/finans_menu.html')
@cari_bp.route('/cari-durum-raporu')
def cari_durum_raporu():
    # Sadece aktif firmaları getir
    firmalar = Firma.query.filter_by(is_active=True).all()
    rapor_listesi = []

    # GENEL TOPLAM DEĞİŞKENLERİ
    genel_toplam = {
        'borc': Decimal('0.0'),   # Toplam Borç (Giden Para + Satışlar)
        'alacak': Decimal('0.0'), # Toplam Alacak (Gelen Para + Alışlar)
        'bakiye': Decimal('0.0')
    }

    for firma in firmalar:
        # Filtre (Dahili hesapları gizle)
        adi_kucuk = firma.firma_adi.lower()
        if 'dahili' in adi_kucuk or 'transfer' in adi_kucuk:
            continue

        toplam_borc = Decimal('0.0')   # Sol Sütun (Bizim Alacağımız / Onların Borcu)
        toplam_alacak = Decimal('0.0') # Sağ Sütun (Bizim Borcumuz / Onların Alacağı)

        # ---------------------------------------------------------
        # 1. HİZMET KAYITLARI (FATURALAR)
        # ---------------------------------------------------------
        if firma.hizmet_kayitlari:
            for h in firma.hizmet_kayitlari:
                tutar = clean_currency_input(h.tutar)
                
                if h.yon == 'giden':
                    # Biz Fatura Kestik (Satış/Gelir) -> BORÇ Sütununa
                    toplam_borc += tutar
                elif h.yon == 'gelen':
                    # Bize Fatura Geldi (Alış/Gider) -> ALACAK Sütununa
                    toplam_alacak += tutar

        # ---------------------------------------------------------
        # 2. ÖDEME HAREKETLERİ (NAKİT GİRİŞ/ÇIKIŞ)
        # ---------------------------------------------------------
        # KRİTİK DÜZELTME: Odeme modelinde 'yon' olmadığı için
        # tutarın Eksi (-) veya Artı (+) olmasına bakıyoruz.
        if firma.odemeler:
            for odeme in firma.odemeler:
                tutar = clean_currency_input(odeme.tutar)
                
                # SENARYO A: Tutar NEGATİF ise (-5.500) -> Bu bir ÖDEMEDİR (Para Çıkışı)
                # Para bizden çıkarsa, karşı tarafın borcunu düşürürüz ama muhasebe tekniği olarak
                # "Borç" sütununa eklenmez, "Borç Bakiyesini" düşürmek için işlem yapılır.
                # Ancak senin tablon "Borç / Alacak" mantığıyla çalıştığı için:
                # Ödeme (Bizden Giden Para) -> Tedarikçiye verdiysek -> BORÇ (Giden) hanesine yazarız.
                
                if tutar < 0:
                    # Negatif değer, bizden para çıktığını gösterir.
                    # Mutlak değerini alıp BORÇ (Giden) sütununa ekliyoruz.
                    toplam_borc += abs(tutar) 
                
                # SENARYO B: Tutar POZİTİF ise (2.500) -> Bu bir TAHSİLATTIR (Para Girişi)
                # Müşteriden para geldiyse -> ALACAK (Gelen) hanesine yazarız.
                else:
                    toplam_alacak += tutar

        # ---------------------------------------------------------
        # 3. SONUÇ HESAPLAMA
        # ---------------------------------------------------------
        bakiye = toplam_borc - toplam_alacak

        # Genel Toplamlara Ekle
        genel_toplam['borc'] += toplam_borc
        genel_toplam['alacak'] += toplam_alacak
        genel_toplam['bakiye'] += bakiye

        # Firma Tipi Gösterimi
        tip_str = "Tedarikçi"
        if firma.is_musteri and firma.is_tedarikci:
            tip_str = "Müşteri & Tedarikçi"
        elif firma.is_musteri:
            tip_str = "Müşteri"

        rapor_listesi.append({
            'id': firma.id,
            'firma_adi': firma.firma_adi,
            'yetkili': firma.yetkili_adi,
            'tipi': tip_str,
            'toplam_borc': toplam_borc,    # HTML'de bu değişkeni kullan
            'toplam_alacak': toplam_alacak, # HTML'de bu değişkeni kullan
            'bakiye': bakiye
        })

    return render_template('cari/cari_durum_raporu.html', rapor=rapor_listesi, genel_toplam=genel_toplam)