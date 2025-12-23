import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import time

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="SMMM Halil Akça - İş Takip", page_icon="📊", layout="wide")

# --- TASARIM ---
st.markdown("""
    <style>
    .stApp {background-color: #F8F9FA;}
    [data-testid="stSidebar"] {background-color: #2C3E50;}
    div.stContainer {background-color: #FFFFFF; padding: 20px; border-radius: 12px; border: 1px solid #E0E0E0;}
    </style>
    """, unsafe_allow_html=True)

# --- BAĞLANTILAR ---
try:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], 
        ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open("Is_Takip_Sistemi")
except Exception as e:
    st.error(f"⚠️ Bağlantı Hatası: {e}"); st.stop()

# --- VERİ FONKSİYONLARI ---
@st.cache_data(ttl=60)
def verileri_getir(sayfa_adi):
    try:
        sheet = spreadsheet.worksheet(sayfa_adi)
        return pd.DataFrame(sheet.get_all_records())
    except:
        return pd.DataFrame()

def onbellek_temizle():
    verileri_getir.clear()

# --- ANA BAŞLIK ---
st.title("SMMM HALİL AKÇA ANALİZ VE İŞ TAKİP")
st.divider()

# --- YAN MENÜ ---
with st.sidebar:
    st.header("Menü")
    menu = ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "⚙️ Tekrarlayan Görevler"]
    secim = st.radio("Gitmek istediğiniz sayfa:", menu)

# --- SAYFALAR ---

if secim == "📊 Genel Bakış":
    st.subheader("Ofis Genel Durumu")
    df = verileri_getir("Sheet1")
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam İş", len(df))
        c2.metric("Bekleyen", len(df[df['Durum'] != 'Tamamlandi']))
        c3.metric("Tamamlanan", len(df[df['Durum'] == 'Tamamlandi']))
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Henüz veri bulunmuyor.")

elif secim == "➕ İş Ekle":
    st.subheader("Yeni İş Girişi")
    with st.form("is_ekle"):
        c1, c2, c3 = st.columns(3)
        tarih = c1.date_input("Başlangıç Tarihi")
        saat = c2.time_input("Saat")
        son_teslim = c3.date_input("Son Teslim Tarihi", value=None)
        
        musteri = st.selectbox("Mükellef", ["Müşteri 1", "Müşteri 2"]) # Burayı dinamik yapabiliriz
        is_tanimi = st.text_input("İş Tanımı")
        personel = st.selectbox("Sorumlu", ["Halil", "Aslı", "Tuğçe", "Özlem"])
        
        if st.form_submit_button("Kaydet"):
            try:
                sheet = spreadsheet.sheet1
                sheet.append_row([
                    tarih.strftime("%d.%m.%Y"), 
                    saat.strftime("%H:%M"), 
                    is_tanimi, 
                    "Bekliyor", 
                    personel, 
                    son_teslim.strftime("%d.%m.%Y") if son_teslim else ""
                ])
                st.success("İş başarıyla kaydedildi.")
                onbellek_temizle()
            except Exception as e:
                st.error(f"Hata: {e}")

elif secim == "✅ İş Yönetimi":
    st.subheader("İşleri Yönet")
    df = verileri_getir("Sheet1")
    if not df.empty:
        # Burada işleri filtreleyip güncelleme mantığı kurulabilir
        st.write("Mevcut İş Listesi:")
        st.dataframe(df)
    else:
        st.info("Liste boş.")

elif secim == "⚙️ Tekrarlayan Görevler":
    st.subheader("Tekrarlayan Görev Tanımları")
    st.info("Bu bölümdeki kurallar sadece kayıt amaçlıdır, dış bağlantı kapalı olduğu için otomatik işlem yapmaz.")
    # Kural ekleme formu buraya gelebilir
