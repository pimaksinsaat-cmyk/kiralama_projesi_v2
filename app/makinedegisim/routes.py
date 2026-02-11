from flask import render_template, redirect, url_for, flash, request
from app.makinedegisim import makinedegisim_bp
from app.makinedegisim.models import MakineDegisim # Modeli buradan import ediyoruz
from app.extensions import db

@makinedegisim_bp.route('/')
def liste():
    # Değişimleri listeleme sayfası
    degisimler = MakineDegisim.query.order_by(MakineDegisim.tarih.desc()).all()
    return render_template('makinedegisim/liste.html', degisimler=degisimler)

@makinedegisim_bp.route('/yeni', methods=['GET', 'POST'])
def yeni_degisim():
    # Yeni değişim formu ve mantığı buraya gelecek
    # Önemli: Burada 'class MakineDegisim' diye bir şey tanımlama!
    return render_template('makinedegisim/form.html')