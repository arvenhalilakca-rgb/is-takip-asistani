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
def google_sheet_baglan(sayfa_adi="Sheet1"):
    client = gspread.authorize(creds)
    # Eğer sayfa adı verilmezse varsayılanı (Ana tabloyu) aç
    if sayfa_adi == "Sheet1":
        return client.open("Is_Takip_Sistemi").sheet1
    else:
        # Müşteriler sayfasını aç
        return client.open("Is_Takip_Sistemi").worksheet(sayfa_adi)

def whatsapp_gonder(mesaj):
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    payload = {'chatId': GRUP_ID, 'message': mesaj}
    try:
        requests.post(url, json=payload)
        return True
    except:
        return False

def verileri_getir():
    sheet = google_sheet_baglan() # Ana sayfayı getir
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def musterileri_getir():
    try:
        sheet = google_sheet_baglan("Musteriler") # Senin yeni açtığın sayfa
        veriler = sheet.get_all_records()
        df = pd.DataFrame(veriler)
        # Sadece Ad Soyad sütununu liste yap
        return df["Ad Soyad"].tolist()
    except Exception as e:
        return []

# --- SAYFA TASARIMI ---
st.set_page_config(page_title="İş Asistanı", page_icon="💼")

st.title("👨‍💼 Mobil İş Takip Asistanı")

# --- SEKME YAPISI ---
tab1, tab2 = st.tabs(["➕ Yeni İş Ekle", "📋 Listeyi Gör"])

with tab1:
    with st.form("is_formu", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tarih = st.date_input("Tarih")
        with col2:
            saat = st.time_input("Saat")
        
        # --- YENİ EKLENEN KISIM: AÇILIR LİSTE ---
        musteri_listesi = musterileri_getir()
        
        if musteri_listesi:
            # Excel'den gelen isimleri kutuya koyuyoruz
            secilen_musteri = st.selectbox("Mükellef Seç", musteri_listesi)
        else:
            st.warning("Müşteri listesi okunamadı! Sayfa adının 'Musteriler' olduğundan emin ol.")
            secilen_musteri = st.text_input("Müşteri Adı (Manuel)")

        is_notu = st.text_input("Yapılacak İş / Not", placeholder="Örn: KDV Beyannamesi Onayı")
        
        submit_btn = st.form_submit_button("✅ Kaydet ve Gönder")

        if submit_btn and is_notu:
            try:
                sheet = google_sheet_baglan() # Kayıt ana sayfaya yapılacak
                tarih_str = tarih.strftime("%d.%m.%Y")
                saat_str = saat.strftime("%H:%M")
                
                # İsim ve Notu birleştiriyoruz
                tam_is_tanimi = f"{secilen_musteri} - {is_notu}"
                
                # Google Sheets'e Ekle
                sheet.append_row([tarih_str, saat_str, tam_is_tanimi, "Gonderildi", "Bekliyor"])
                
                # WhatsApp'a Gönder
                mesaj = f"📅 *YENİ PLANLAMA*\n\n👤 *Mükellef:* {secilen_musteri}\n📌 *İş:* {is_notu}\n🗓 *Tarih:* {tarih_str} {saat_str}"
                whatsapp_gonder(mesaj)
                
                st.balloons()
                st.success(f"'{secilen_musteri}' için iş başarıyla oluşturuldu!")
                
            except Exception as e:
                st.error(f"Hata oluştu: {e}")

with tab2:
    st.subheader("📅 Bekleyen Planlamalar")
    if st.button("🔄 Listeyi Yenile"):
        st.rerun()
        
    try:
        df = verileri_getir()
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Henüz kayıtlı bir iş yok.")
    except Exception as e:
        st.error("Veriler çekilemedi.")
