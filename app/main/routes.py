from app.main import main_bp
from flask import render_template, url_for

@main_bp.route('/')
@main_bp.route('/index')
def index():
    """
    Ana Sayfa (Dashboard).
    """
    # Birazdan oluşturacağımız 'main/index.html' şablonunu döndürür.
    return render_template('main/index.html')