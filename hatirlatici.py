import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import pandas as pd
from datetime import datetime, timedelta

# --- AYARLAR ---
# GitHub Actions bu bilgileri "Environment Variables" (Ortam Değişkenleri) olarak alacak
ID_INSTANCE = os.environ["ID_INSTANCE"]
API_TOKEN = os.environ["API_TOKEN"]
GRUP_ID = os.environ["GRUP_ID"]

# Google Credentials (JSON formatında string olarak gelecek)
creds_json_str = os.environ["GCP_CREDENTIALS"]
creds_dict = json.loads(creds_json_str)

# --- BAĞLANTILAR ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("Is_Takip_Sistemi").sheet1

def whatsapp_gonder(mesaj):
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    payload = {'chatId': GRUP_ID, 'message': mesaj}
    requests.post(url, json=payload)

# --- ANA KONTROL MEKANİZMASI ---
print("Robot kontrol için uyandı... 🤖")

# Tüm verileri çek
data = sheet.get_all_values()
# Başlıkları atla (ilk satır)
rows = data[1:] 

simdi = datetime.now()
print(f"Şu anki saat: {simdi.strftime('%H:%M')}")

for i, row in enumerate(rows):
    # Satır numarası (Google Sheet'te 1'den başlar, başlık olduğu için +2 ekliyoruz)
    satir_no = i + 2
    
    # Verileri al (Boş satır varsa atla)
    if len(row) < 5: continue
    
    tarih_str = row[0]  # 23.12.2025
    saat_str = row[1]   # 14:00
    is_tanimi = row[2]
    hatirlatma_durumu = row[4] # "Bekliyor" veya "Hatirlatildi"

    # Sadece "Bekliyor" olanlara bak
    if hatirlatma_durumu == "Bekliyor":
        try:
            # İşin zamanını hesapla
            is_zamani_str = f"{tarih_str} {saat_str}"
            is_zamani = datetime.strptime(is_zamani_str, "%d.%m.%Y %H:%M")
            
            # Ne kadar zaman kaldı?
            fark = is_zamani - simdi
            dakika_kaldi = fark.total_seconds() / 60
            
            # Eğer 0 ile 60 dakika arası kaldıysa MESAJ AT
            if 0 < dakika_kaldi <= 60:
                print(f"🔔 YAKALANDI: {is_tanimi} ({int(dakika_kaldi)} dk kaldı)")
                
                mesaj = f"⏰ *HATIRLATMA! (Son 1 Saat)*\n\n📌 *İş:* {is_tanimi}\n⏳ *Kalan Süre:* {int(dakika_kaldi)} dakika\n\n_Lütfen hazırlıklara başlayın._"
                whatsapp_gonder(mesaj)
                
                # Durumu güncelle ki tekrar mesaj atmasın
                sheet.update_cell(satir_no, 5, "Hatirlatildi")
                print("✅ Mesaj atıldı ve durum güncellendi.")
                
        except ValueError:
            pass # Tarih formatı hatalıysa geç

print("Kontrol bitti. Robot uyuyor. 💤")
