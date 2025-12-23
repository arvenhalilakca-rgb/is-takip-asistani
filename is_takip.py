# streamlit_app.py (Nihai Versiyon - Marka Güncellemesi)

import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import pandas as pd
import re
from datetime import datetime
import time

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="SMMM Halil Akça - İş Takip",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TASARIM (CSS) ---
st.markdown("""
    <style>
    .stApp {background-color: #F8F9FA; font-family: 'Helvetica', sans-serif;}
    [data-testid="stSidebar"] {background-color: #2C3E50;}
    [data-testid="stSidebar"] * {color: #ECF0F1 !important;}
    div.stContainer {background-color: #FFFFFF; padding: 20px; border-radius: 12px; border: 1px solid #E0E0E0;}
    .stButton>button {width: 100%; border-radius: 8px; font-weight: 600;}
    button[kind="primary"] {background: linear-gradient(90deg, #2980b9 0%, #2c3e50 100%); color: white;}
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
RESMI_TATILLER = ["01.01", "23.04", "01.05", "19.05", "15.07", "30.08", "29.10"]

# --- SESSION STATE ---
if 'aktif_kullanici' not in st.session_state: st.session_state['aktif_kullanici'] = "Admin"
if 'son_islem_logu' not in st.session_state: st.session_state['son_islem_logu'] = "Sistem başlatıldı."

# --- BAĞLANTILAR VE FONKSİYONLAR ---
try:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"] )
except Exception as e:
    st.error(f"⚠️ Ayar Hatası: Google Secrets eksik veya hatalı. {e}"); st.stop()

@st.cache_data(ttl=60)
def verileri_getir(sayfa_adi):
    try:
        client = gspread.authorize(creds)
        sheet = client.open("Is_Takip_Sistemi").worksheet(sayfa_adi)
        return pd.DataFrame(sheet.get_all_records())
    except Exception as e:
        st.sidebar.error(f"Veri çekme hatası: {sayfa_adi} - {e}")
        return pd.DataFrame()

def onbellek_temizle():
    verileri_getir.clear()

def log_kaydi_ekle(is_id, kullanici, eylem):
    try:
        client = gspread.authorize(creds)
        sheet = client.open("Is_Takip_Sistemi").worksheet("Loglar")
        sheet.append_row([datetime.now().strftime("%d.%m.%Y %H:%M:%S"), str(is_id), kullanici, eylem])
        st.session_state['son_islem_logu'] = f"{kullanici} - {eylem}"
    except Exception:
        st.sidebar.warning("Loglama yapılamadı.")

# ... (Diğer fonksiyonlar buraya eklenebilir) ...

# --- YAN MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80 )
    df_m = verileri_getir("Musteriler")
    personel_listesi = ["Admin"]
    if not df_m.empty and "Sorumlu" in df_m.columns:
        personel_listesi.extend([p for p in df_m["Sorumlu"].unique() if p and str(p) not in ["nan", "None"]])
    st.session_state['aktif_kullanici'] = st.selectbox("👤 Kullanıcı", sorted(list(set(personel_listesi))))
    st.markdown("---")
    menu_options = ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "⚙️ Tekrarlayan Görevler"]
    secim = st.radio("MENÜ", menu_options)
    st.markdown("---")
    st.caption(f"Son İşlem: {st.session_state.get('son_islem_logu', 'Sistem başlatıldı.')}")

# ==============================================================================
# --- ANA BAŞLIK VE SAYFA İÇERİKLERİ ---
# ==============================================================================
st.title("SMMM HALİL AKÇA ANALİZ VE İŞ TAKİP")
st.divider()

if secim == "⚙️ Tekrarlayan Görevler":
    st.header("Tekrarlayan Görev Yönetimi")
    st.info(
        """
        Bu modül, ofisinizin tekrar eden iş yükünü otomatize etmek için tasarlanmıştır. 
        
        **Nasıl Çalışır?**
        1.  **Kural Tanımlayın:** "Her Ayın 15'i", "Her 3 Ayda Bir" gibi kurallar oluşturun.
        2.  **Görev Atayın:** Bu kurallara göre otomatik olarak hangi işin (örn: KDV Beyannamesi) ve hangi sorumluya atanacağını belirtin.
        3.  **Sistem Oluştursun:** Zamanı geldiğinde, sistem bu görevleri sizin yerinize otomatik olarak ana iş listesine ekler.
        """
    )
    
    tab1, tab2 = st.tabs(["➕ Yeni Tekrarlayan Görev Ekle", "📋 Mevcut Kuralları Görüntüle"])
    
    with tab1:
        with st.form("kural_ekle_form", clear_on_submit=True):
            df_m = verileri_getir("Musteriler")
            musteri = st.selectbox("Hangi Müşteri İçin?", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
            is_sablonu = st.text_input("Otomatik Oluşturulacak İşin Adı", placeholder="Örn: KDV Beyannamesi Hazırlığı")
            col1, col2 = st.columns(2)
            tekrar_tipi = col1.selectbox("Tekrarlama Sıklığı", ["Her Ay", "Her 3 Ayda Bir"])
            tekrar_gunu = col2.number_input("Ayın Kaçıncı Günü Oluşturulsun?", min_value=1, max_value=28, value=15)
            kural_str = f"{tekrar_tipi}ın {tekrar_gunu}'ü"
            personel_listesi_form = [""]
            if not df_m.empty and "Sorumlu" in df_m.columns:
                personel_listesi_form.extend([p for p in df_m["Sorumlu"].unique() if p and str(p) not in ["nan", "None"]])
            sorumlu = st.selectbox("Bu Görev Kime Atansın?", sorted(list(set(personel_listesi_form))))
            if st.form_submit_button("✅ Kuralı Kaydet", type="primary"):
                try:
                    client = gspread.authorize(creds)
                    sheet = client.open("Is_Takip_Sistemi").worksheet("Tekrarlayan_Isler")
                    sheet.append_row([musteri, is_sablonu, kural_str, sorumlu, "EVET"])
                    log_kaydi_ekle(f"Kural: {musteri}", st.session_state['aktif_kullanici'], "Yeni otomasyon kuralı ekledi.")
                    onbellek_temizle()
                    st.success("Yeni otomasyon kuralı başarıyla eklendi!")
                    time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Kural kaydedilirken bir hata oluştu: {e}")
    with tab2:
        st.subheader("Mevcut Otomasyon Kuralları")
        st.dataframe(verileri_getir("Tekrarlayan_Isler"), use_container_width=True, hide_index=True)

# ... (Diğer elif bloklarınız burada devam eder) ...
