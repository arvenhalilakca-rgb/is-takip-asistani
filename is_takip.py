import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
from datetime import datetime

# --- GÜVENLİK AYARLARI (SECRETS) ---
# Bulutta çalışırken şifreleri 'st.secrets' içinden alır.
# Bilgisayarında çalışırken hata verirse 'credentials.json' yoluna döner.

try:
    # Streamlit Cloud üzerindeki gizli kasadan bilgileri çek
    ID_INSTANCE = st.secrets["ID_INSTANCE"]
    API_TOKEN = st.secrets["API_TOKEN"]
    GRUP_ID = st.secrets["GRUP_ID"]
    # Google Anahtarı (JSON içeriği olarak gelecek)
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
except:
    # Eğer bilgisayarındaysan ve secrets ayarlı değilse manuel mod (Test için)
    # Buraya kendi bilgilerini tekrar yazman gerekebilir veya yerel test için eski yöntemi kullanabilirsin.
    # Ancak buluta yükleyince üstteki kısım çalışacak.
    st.error("Bu uygulama şu an Bulut Modunda çalışmak için ayarlandı. Lütfen Streamlit Secrets ayarlarını yapınız.")
    st.stop()

# --- FONKSİYONLAR ---
def whatsapp_gonder(mesaj):
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    payload = {'chatId': GRUP_ID, 'message': mesaj}
    try:
        requests.post(url, json=payload)
        return True
    except:
        return False

def google_sheet_baglan():
    client = gspread.authorize(creds)
    return client.open("Is_Takip_Sistemi").sheet1

# --- ARAYÜZ ---
st.title("👨‍💼 Mobil İş Takip Asistanı")
st.info("Sistem Bulut Sunucusunda Aktif ☁️")

with st.form("is_formu", clear_on_submit=True): # clear_on_submit formu temizler, çift gönderimi engeller
    tarih = st.date_input("Tarih")
    saat = st.time_input("Saat")
    is_tanimi = st.text_input("İş Tanımı", placeholder="Örn: Ahmet Bey Toplantı")
    
    submit_btn = st.form_submit_button("✅ Kaydet ve Gönder")

    if submit_btn and is_tanimi:
        try:
            # 1. Google Sheets
            sheet = google_sheet_baglan()
            tarih_str = tarih.strftime("%d.%m.%Y")
            saat_str = saat.strftime("%H:%M")
            sheet.append_row([tarih_str, saat_str, is_tanimi, "Gonderildi", "Bekliyor"])
            
            # 2. WhatsApp
            mesaj = f"📅 *YENİ PLANLAMA*\n\n📌 *İş:* {is_tanimi}\n🗓 *Tarih:* {tarih_str}\n🕐 *Saat:* {saat_str}"
            whatsapp_gonder(mesaj)
            
            st.success("İşlem Başarılı! Mesaj gönderildi.")
            st.balloons()
        except Exception as e:
            st.error(f"Hata: {e}")
