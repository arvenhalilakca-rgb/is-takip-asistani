import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import pandas as pd
from datetime import datetime

# --- GÜVENLİK VE AYARLAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]
    API_TOKEN = st.secrets["API_TOKEN"]
    GRUP_ID = st.secrets["GRUP_ID"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
except:
    st.error("Sistem Bulut modunda değil veya şifreler eksik!")
    st.stop()

# --- FONKSİYONLAR ---
def google_sheet_baglan():
    client = gspread.authorize(creds)
    return client.open("Is_Takip_Sistemi").sheet1

def whatsapp_gonder(mesaj):
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    payload = {'chatId': GRUP_ID, 'message': mesaj}
    try:
        requests.post(url, json=payload)
        return True
    except:
        return False

def verileri_getir():
    sheet = google_sheet_baglan()
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# --- SAYFA TASARIMI ---
st.set_page_config(page_title="İş Asistanı", page_icon="💼")

st.title("👨‍💼 Mobil İş Takip Asistanı")
st.success("Bulut Sistemi Aktif ☁️")

# --- SEKME YAPISI (Giriş ve Liste) ---
tab1, tab2 = st.tabs(["➕ Yeni İş Ekle", "📋 Listeyi Gör"])

with tab1:
    with st.form("is_formu", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tarih = st.date_input("Tarih")
        with col2:
            saat = st.time_input("Saat")
        
        is_tanimi = st.text_input("İş Tanımı", placeholder="Örn: Ahmet Bey ile BİGFOTT KAFE toplantısı")
        
        submit_btn = st.form_submit_button("✅ Kaydet ve Gönder")

        if submit_btn and is_tanimi:
            try:
                sheet = google_sheet_baglan()
                tarih_str = tarih.strftime("%d.%m.%Y")
                saat_str = saat.strftime("%H:%M")
                
                # Google Sheets'e Ekle
                sheet.append_row([tarih_str, saat_str, is_tanimi, "Gonderildi", "Bekliyor"])
                
                # WhatsApp'a Gönder
                mesaj = f"📅 *YENİ PLANLAMA*\n\n📌 *İş:* {is_tanimi}\n🗓 *Tarih:* {tarih_str}\n🕐 *Saat:* {saat_str}"
                whatsapp_gonder(mesaj)
                
                st.balloons()
                st.success(f"'{is_tanimi}' başarıyla kaydedildi!")
                
            except Exception as e:
                st.error(f"Hata oluştu: {e}")

with tab2:
    st.subheader("📅 Bekleyen Planlamalar")
    if st.button("🔄 Listeyi Yenile"):
        st.rerun()
        
    try:
        df = verileri_getir()
        if not df.empty:
            # Tabloyu daha şık gösterelim
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Henüz kayıtlı bir iş yok.")
    except Exception as e:
        st.error("Veriler çekilemedi.")
