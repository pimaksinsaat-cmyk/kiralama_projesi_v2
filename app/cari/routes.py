from flask import render_template, redirect, url_for, flash, request
from app import db
from app.cari import cari_bp
from app.cari.forms import OdemeForm, HizmetKaydiForm, KasaForm
from app.cari.models import Kasa, Odeme, HizmetKaydi
from app.firmalar.models import Firma
from sqlalchemy import func, case


from decimal import Decimal
from datetime import date, datetime
import traceback

# -------------------------------------------------------------------------
# 🛠️ YARDIMCI FONKSİYONLAR
# -------------------------------------------------------------------------
def clean_currency_input(value_str):
    if not value_str: return Decimal('0.0')
    # Noktayı silip virgülü noktaya çeviriyoruz
    val = str(value_str).strip().replace('.', '').replace(',', '.')
    try:
        return Decimal(val)
    except:
        return Decimal('0.0')

def bakiye_guncelle(kasa_id, tutar_decimal, yon='giris'):
    kasa = Kasa.query.get(kasa_id)
    if not kasa: return
    if yon == 'giris': kasa.bakiye += tutar_decimal
    else: kasa.bakiye -= tutar_decimal

def get_dahili_islem_firmasi():
    firma = Firma.query.filter_by(firma_adi='Dahili Kasa İşlemleri').first()
    if not firma:
        firma = Firma(
            firma_adi='Dahili Kasa İşlemleri',
            yetkili_adi='Sistem',              # ✅ ZORUNLU
            iletisim_bilgileri='-',             # opsiyonel ama temiz
            vergi_dairesi='-',
            vergi_no='-',
            is_musteri=True,
            is_tedarikci=False,
            is_active=True,
            bakiye=0
        )
        db.session.add(firma)
        db.session.commit()
    return firma


# -------------------------------------------------------------------------
# 1. ÖDEME VE TAHSİLAT
# -------------------------------------------------------------------------
@cari_bp.route('/odeme/ekle', methods=['GET', 'POST'])
def odeme_ekle():
    firma_id = request.args.get('firma_id', type=int)
    yon_param = request.args.get('yon', 'tahsilat')
    form = OdemeForm()
    
    form.firma_musteri_id.choices = [(f.id, f.firma_adi) for f in Firma.query.filter_by(is_active=True).all()]
    form.kasa_id.choices = [(k.id, f"{k.kasa_adi} ({k.bakiye} TL)") for k in Kasa.query.all()]
    
    if request.method == 'GET':
        if firma_id: form.firma_musteri_id.data = firma_id
        form.tarih.data = date.today()
        form.yon.data = yon_param

    if form.validate_on_submit():
        try:
            tutar = form.tutar.data
            yeni_odeme = Odeme(
                firma_musteri_id=form.firma_musteri_id.data,
                kasa_id=form.kasa_id.data,
                tarih=form.tarih.data,
                tutar=tutar,
                yon=form.yon.data,
                aciklama=form.aciklama.data,
                # EKSİK OLAN SATIRLAR BURADA:
                fatura_no=form.fatura_no.data,      # Formdan oku, modele yaz
                vade_tarihi=form.vade_tarihi.data   # Formdan oku, modele yaz
            )
            
            k_yon = 'giris' if form.yon.data == 'tahsilat' else 'cikis'
            bakiye_guncelle(form.kasa_id.data, tutar, k_yon)
            
            db.session.add(yeni_odeme)
            db.session.commit()
            
            flash('İşlem başarıyla kaydedildi.', 'success')
            return redirect(url_for('firmalar.bilgi', id=form.firma_musteri_id.data))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Hata: {str(e)}", "danger")
            
    return render_template('cari/odeme_ekle.html', form=form)

@cari_bp.route('/odeme/sil/<int:id>', methods=['POST'])
def odeme_sil(id):
    odeme = Odeme.query.get_or_404(id)
    f_id = odeme.firma_musteri_id
    try:
        # Kasa bakiyesini tersine çeviriyoruz (Ters işlemle geri al)
        # Eğer tahsilatsa (giriş yapılmıştı), şimdi çıkış yapıyoruz.
        g_yon = 'cikis' if odeme.yon == 'tahsilat' else 'giris'
        bakiye_guncelle(odeme.kasa_id, odeme.tutar, g_yon)
        
        db.session.delete(odeme)
        db.session.commit()
        flash('Ödeme/Tahsilat kaydı silindi ve kasa bakiyesi düzeltildi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {str(e)}', 'danger')
    return redirect(url_for('firmalar.bilgi', id=f_id))

# -------------------------------------------------------------------------
# 2. HİZMET / FATURA (NAKLİYE KORUMALI)
# -------------------------------------------------------------------------
@cari_bp.route('/hizmet/ekle', methods=['GET', 'POST'])
def hizmet_ekle():
    firma_id = request.args.get('firma_id', type=int)
    form = HizmetKaydiForm()
    form.firma_id.choices = [(f.id, f.firma_adi) for f in Firma.query.filter_by(is_active=True).all()]
    if request.method == 'GET':
        if firma_id: form.firma_id.data = firma_id
        form.tarih.data = date.today()

    if form.validate_on_submit():
        
        try:
            yeni_hizmet = HizmetKaydi(
                firma_id=form.firma_id.data,
                tarih=form.tarih.data,
                tutar=form.tutar.data,
                yon=form.yon.data,
                aciklama=form.aciklama.data,
                fatura_no=form.fatura_no.data
            )
            db.session.add(yeni_hizmet)
            db.session.commit()
            flash('Fatura kaydedildi.', 'success')
            return redirect(url_for('firmalar.bilgi', id=form.firma_id.data))
        except Exception as e:
            db.session.rollback()
            flash(f"Hata: {e}", "danger")
    return render_template('cari/hizmet_ekle.html', form=form)

@cari_bp.route('/hizmet/sil/<int:id>', methods=['POST'])
def hizmet_sil(id):
    hizmet = HizmetKaydi.query.get_or_404(id)
    f_id = hizmet.firma_id
    
    # Nakliye modülü ile bağlantısı varsa silinmesini engelliyoruz (Senin yapındaki koruma)
    if hasattr(hizmet, 'nakliye_id') and hizmet.nakliye_id:
        flash('Nakliye bağlantılı kayıtlar buradan silinemez!', 'warning')
        return redirect(url_for('firmalar.bilgi', id=f_id))
        
    try:
        db.session.delete(hizmet)
        db.session.commit()
        flash('Hizmet/Fatura kaydı silindi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {str(e)}', 'danger')
    return redirect(url_for('firmalar.bilgi', id=f_id))

@cari_bp.route('/hizmet/duzelt/<int:id>', methods=['GET', 'POST'])
def hizmet_duzelt(id):
    # 1. Kaydı bul veya 404 döndür
    hizmet = HizmetKaydi.query.get_or_404(id)
    
    # 2. Formu mevcut verilerle doldur (obj=hizmet)
    form = HizmetKaydiForm(obj=hizmet)
    
    # 3. Firma listesini dropdown için tekrar yükle
    form.firma_id.choices = [(f.id, f.firma_adi) for f in Firma.query.filter_by(is_active=True).all()]

    if form.validate_on_submit():
        try:
            # 4. Formdaki verileri modele aktar
            hizmet.firma_id = form.firma_id.data
            hizmet.tarih = form.tarih.data
            hizmet.tutar = form.tutar.data
            hizmet.yon = form.yon.data
            hizmet.aciklama = form.aciklama.data
            hizmet.fatura_no = form.fatura_no.data
            
            db.session.commit()
            flash(f'{hizmet.fatura_no or "Hizmet"} kaydı başarıyla güncellendi.', 'success')
            
            # 5. İşlem bittiğinde firmanın detay sayfasına geri dön
            return redirect(url_for('firmalar.bilgi', id=hizmet.firma_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Güncelleme sırasında bir hata oluştu: {str(e)}", "danger")
            
    return render_template('cari/hizmet_ekle.html', form=form, title="cari/hizmet_duzelt", hizmet=hizmet)
# -------------------------------------------------------------------------
# 3. KASA YÖNETİMİ VE TRANSFER
# -------------------------------------------------------------------------
@cari_bp.route('/kasa/listesi')
def kasa_listesi():
    kasalar = Kasa.query.filter_by(is_active=True).all()
    return render_template('cari/kasa_listesi.html', kasalar=kasalar)

@cari_bp.route('/kasa/transfer', methods=['POST'])
def kasa_transfer():
    try:
        k_id = request.form.get('kaynak_kasa_id', type=int)
        h_id = request.form.get('hedef_kasa_id', type=int)
        tutar = clean_currency_input(request.form.get('tutar'))
        kaynak = Kasa.query.get_or_404(k_id)
        hedef = Kasa.query.get_or_404(h_id)
        if kaynak.bakiye < tutar:
            flash('Yetersiz bakiye!', 'danger')
            return redirect(url_for('cari.kasa_listesi'))
        
        dahili = get_dahili_islem_firmasi()
        db.session.add(Odeme(firma_musteri_id=dahili.id, kasa_id=k_id, tarih=date.today(), tutar=tutar, yon='odeme', aciklama=f"Transfer -> {hedef.kasa_adi}"))
        bakiye_guncelle(k_id, tutar, 'cikis')
        db.session.add(Odeme(firma_musteri_id=dahili.id, kasa_id=h_id, tarih=date.today(), tutar=tutar, yon='tahsilat', aciklama=f"Transfer <- {kaynak.kasa_adi}"))
        bakiye_guncelle(h_id, tutar, 'giris')
        db.session.commit()
        flash('Transfer başarılı.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Hata: {e}", "danger")
    return redirect(url_for('cari.kasa_listesi'))

@cari_bp.route('/kasa/ekle', methods=['GET', 'POST'])
def kasa_ekle():
    form = KasaForm()
    if form.validate_on_submit():
        try:
            # Bakiyeyi bizim zırhlı clean_currency_input ile temizliyoruz
            yeni_kasa = Kasa(
                kasa_adi=form.kasa_adi.data,
                bakiye=form.bakiye.data or 0, # Başlangıç bakiyesi
                is_active=True
            )
            db.session.add(yeni_kasa)
            db.session.commit()
            flash(f'{yeni_kasa.kasa_adi} başarıyla oluşturuldu.', 'success')
            return redirect(url_for('cari.kasa_listesi'))
        except Exception as e:
            db.session.rollback()
            flash(f"Kasa eklenirken hata oluştu: {str(e)}", "danger")
            
    return render_template('cari/kasa_ekle.html', form=form, title="Yeni Kasa/Banka Ekle")

@cari_bp.route('/kasa/duzelt/<int:id>', methods=['GET', 'POST'])
def kasa_duzelt(id):
    kasa = Kasa.query.get_or_404(id)
    # obj=kasa diyerek mevcut verileri form kutularına otomatik dolduruyoruz
    form = KasaForm(obj=kasa) 

    diger_kasalar = Kasa.query.filter(
         Kasa.id != kasa.id,
         Kasa.para_birimi == kasa.para_birimi,
         Kasa.is_active == True
    ).all()

    if form.validate_on_submit():
        try:
            kasa.kasa_adi = form.kasa_adi.data
            # Not: Bakiyeyi buradan manuel değiştirmek muhasebe dengesini bozabilir, 
            # ama istersen bu satırı da aktif edebilirsin:
            # kasa.bakiye = form.bakiye.data
            kasa.tipi = form.tipi.data
            kasa.para_birimi = form.para_birimi.data



            db.session.commit()
            flash(f'{kasa.kasa_adi} bilgileri güncellendi.', 'success')
            return redirect(url_for('cari.kasa_listesi'))
        except Exception as e:
            db.session.rollback()
            flash(f"Güncelleme sırasında hata oluştu: {str(e)}", "danger")

        
            
    return render_template('cari/kasa_duzelt.html', form=form,kasa=kasa, diger_kasalar=diger_kasalar, title="Kasa/Banka Düzenle")
# -------------------------------------------------------------------------
# 4. RAPORLAR VE MENÜ (ANA SAYFA İÇİN KRİTİK)
# -------------------------------------------------------------------------
@cari_bp.route('/finans-menu')
def finans_menu():
    return render_template('cari/finans_menu.html')

@cari_bp.route('/cari-durum-raporu')
def cari_durum_raporu():
    """SQL Aggregation kullanarak tüm firma bakiyelerini tek sorguda ve hatasız hesaplar."""
    try:
        # 1. Hizmet Kayıtlarını Topla (Firma bazlı)
        h_ozet = db.session.query(
            HizmetKaydi.firma_id,
            func.sum(case((HizmetKaydi.yon == 'giden', HizmetKaydi.tutar), else_=0)).label('b'),
            func.sum(case((HizmetKaydi.yon == 'gelen', HizmetKaydi.tutar), else_=0)).label('a')
        ).group_by(HizmetKaydi.firma_id).subquery()

        # 2. Ödemeleri Topla (Firma bazlı)
        o_ozet = db.session.query(
            Odeme.firma_musteri_id,
            func.sum(case((Odeme.yon == 'odeme', Odeme.tutar), else_=0)).label('b'),
            func.sum(case((Odeme.yon == 'tahsilat', Odeme.tutar), else_=0)).label('a')
        ).group_by(Odeme.firma_musteri_id).subquery()

        # 3. Ana Sorgu (Coalesce ile SQL seviyesinde None kontrolü)
        sorgu = db.session.query(
            Firma.id, 
            Firma.firma_adi,
            (func.coalesce(h_ozet.c.b, 0) + func.coalesce(o_ozet.c.b, 0)).label('tb'),
            (func.coalesce(h_ozet.c.a, 0) + func.coalesce(o_ozet.c.a, 0)).label('ta')
        ).outerjoin(h_ozet, Firma.id == h_ozet.c.firma_id)\
         .outerjoin(o_ozet, Firma.id == o_ozet.c.firma_musteri_id)\
         .filter(Firma.is_active == True).all()

        rapor = []
        # Decimal başlangıç değerleri
        toplamlar = {'borc': Decimal('0.00'), 'alacak': Decimal('0.00'), 'bakiye': Decimal('0.00')}

        for r in sorgu:
            # Python seviyesinde ikinci bir koruma katmanı (Hata alınan yerin çözümü)
            # r.tb veya r.ta None gelirse 0.00 olarak kabul et
            val_borc = Decimal(str(r.tb)) if r.tb is not None else Decimal('0.00')
            val_alacak = Decimal(str(r.ta)) if r.ta is not None else Decimal('0.00')
            
            # Net Bakiye Hesabı: $Bakiye = Borç - Alacak$
            bakiye_hesap = val_borc - val_alacak

            # Genel Toplamları Güncelle
            toplamlar['borc'] += val_borc
            toplamlar['alacak'] += val_alacak
            toplamlar['bakiye'] += bakiye_hesap

            rapor.append({
                'id': r.id,
                'firma_adi': r.firma_adi,
                'borc': val_borc,
                'alacak': val_alacak,
                'bakiye': bakiye_hesap
            })

        return render_template('cari/cari_durum_raporu.html', rapor=rapor, genel_toplam=toplamlar)

    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        flash(f"Rapor hazırlanırken bir hata oluştu: {str(e)}", "danger")
        return redirect(url_for('cari.finans_menu'))

@cari_bp.route('/kasa/sil/<int:id>', methods=['POST'])
def kasa_sil(id):
    kasa = Kasa.query.get_or_404(id)

    try:
        mevcut_bakiye = kasa.bakiye or 0
        hedef_kasa_id = request.form.get('hedef_kasa_id', type=int)

        # Eğer bakiye varsa hedef kasa ZORUNLU
        if mevcut_bakiye != 0:
            if not hedef_kasa_id:
                flash('Bakiyesi olan kasa silinemez. Lütfen hedef kasa seçin.', 'danger')
                return redirect(url_for('cari.kasa_duzelt', id=id))

            hedef = Kasa.query.get_or_404(hedef_kasa_id)

            if hedef.para_birimi != kasa.para_birimi:
                flash('Hedef kasa para birimi uyumsuz!', 'danger')
                return redirect(url_for('cari.kasa_duzelt', id=id))

            dahili = get_dahili_islem_firmasi()

            # Çıkış (eski kasa)
            db.session.add(Odeme(
                firma_musteri_id=dahili.id,
                kasa_id=kasa.id,
                tarih=date.today(),
                tutar=mevcut_bakiye,
                yon='odeme',
                aciklama=f"Kasa kapatma → {hedef.kasa_adi}"
            ))

            # Giriş (hedef kasa)
            db.session.add(Odeme(
                firma_musteri_id=dahili.id,
                kasa_id=hedef.id,
                tarih=date.today(),
                tutar=mevcut_bakiye,
                yon='tahsilat',
                aciklama=f"Kasa devri ← {kasa.kasa_adi}"
            ))

            bakiye_guncelle(kasa.id, mevcut_bakiye, 'cikis')
            bakiye_guncelle(hedef.id, mevcut_bakiye, 'giris')

        # Soft delete (önerilen)
        kasa.is_active = False
        db.session.commit()

        flash(f'{kasa.kasa_adi} hesabı kapatıldı.', 'success')
        return redirect(url_for('cari.kasa_listesi'))

    except Exception as e:
        db.session.rollback()
        flash(f"Kasa silinirken hata oluştu: {str(e)}", 'danger')
        return redirect(url_for('cari.kasa_listesi'))

@cari_bp.route('/kasa/hizli_islem', methods=['POST'])
def kasa_hizli_islem():
    try:
        kasa_id = request.form.get('kasa_id', type=int)
        islem_yonu = request.form.get('islem_yonu')  # giris / cikis
        tutar = clean_currency_input(request.form.get('tutar'))
        aciklama = request.form.get('aciklama', '')

        if not kasa_id or tutar <= 0:
            flash("Geçersiz işlem bilgileri", "danger")
            return redirect(url_for('cari.kasa_listesi'))

        kasa = Kasa.query.filter_by(id=kasa_id, is_active=True).first_or_404()

        if islem_yonu not in ('giris', 'cikis'):
            flash("Geçersiz işlem yönü", "danger")
            return redirect(url_for('cari.kasa_listesi'))

        if islem_yonu == 'cikis' and kasa.bakiye < tutar:
            flash("Yetersiz kasa bakiyesi", "danger")
            return redirect(url_for('cari.kasa_listesi'))

        dahili = get_dahili_islem_firmasi()

        # Odeme yönü belirle
        yon = 'tahsilat' if islem_yonu == 'giris' else 'odeme'

        odeme = Odeme(
            firma_musteri_id=dahili.id,
            kasa_id=kasa.id,
            tarih=date.today(),
            tutar=tutar,
            yon=yon,
            aciklama=f"Hızlı Kasa İşlemi: {aciklama}"
        )

        # Bakiye güncelle
        bakiye_guncelle(kasa.id, tutar, islem_yonu)

        db.session.add(odeme)
        db.session.commit()

        flash("Kasa işlemi başarıyla kaydedildi", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Hızlı kasa işlem hatası: {str(e)}", "danger")

    return redirect(url_for('cari.kasa_listesi'))


@cari_bp.route('/kasa/hareketleri/<int:id>')
def kasa_hareketleri(id):
    # 1️⃣ Kasa var mı kontrol et
    kasa = Kasa.query.get_or_404(id)

    # 2️⃣ Bu kasaya ait tüm işlemleri çek
    hareketler = (
        Odeme.query
        .filter(Odeme.kasa_id == kasa.id)
        .order_by(Odeme.tarih.desc(), Odeme.id.desc())
        .all()
    )

    # 3️⃣ Template'e gönder
    return render_template('cari/kasa_hareketleri.html',kasa=kasa,hareketler=hareketler,now=datetime.now())

@cari_bp.route('/odeme/duzelt/<int:id>', methods=['GET', 'POST'])
def odeme_duzelt(id):
    odeme = Odeme.query.get_or_404(id)

    # ŞİMDİLİK sadece bilgi verip geri döndürüyoruz
    flash(
        f"{odeme.tarih} tarihli {odeme.tutar} tutarındaki ödeme için "
        f"düzeltme ekranı henüz aktif değil.",
        "info"
    )

    # Geldiği yere geri dön (referrer yoksa kasa listesi)
    return redirect(request.referrer or url_for('cari.kasa_listesi'))

