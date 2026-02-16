#!/usr/bin/env bash

# 1. Python kütüphanelerini yükle
pip install -r requirements.txt

# 2. Sunucu paket listesini güncelle ve LibreOffice'i kur
# Bu komut Render'ın Linux sunucusuna PDF dönüştürücü motoru yükler
apt-get update && apt-get install -y libreoffice