import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import requests
import pandas as pd
import re
from datetime import datetime
import time
import plotly.express as px
import pdfplumber
import io
from streamlit_option_menu import option_menu

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir Asistanı Pro",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TASARIM (CSS) ---
st.markdown("""
    <style>
    .stApp {background-color: #F0F2F6; font-family: 'Roboto', sans-serif;}
    [data-testid="stSidebar"] {background-color: #FFFFFF; border-right: 1px solid #E0E0E0;}
    div[data-testid="stMetric"] {background-color: #FFFFFF; border-radius: 15px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);}
    .stButton>button {border-radius: 12px; height: 50px; font-weight: bold; border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: all 0.3s ease;}
    button[kind="primary"] {background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%); color: white;}
    button[kind="primary"]:hover {transform: translateY(-2px); box-shadow: 0 6px 12px rgba(0,0,0,0.2);}
    .borclu-uyari {background-color: #ffebee; color: #c0392b; padding: 15px; border-radius: 10px; border-left: 5px solid #e74c3c; font-weight: bold;}
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
RESMI_TATILLER = ["01.01", "23.04", "01.05", "19.05", "15.07", "30.08", "29.10"]
MESAJ_SABLONLARI = {
    "Tasdik Ödenmedi (SERT)": "Sayın {isim}, 2026 yılı defter tasdik ücretinizi ödemediğiniz için defterleriniz notere teslim EDİLMEMİŞTİR. Cezalı duruma düşmemek ve mağduriyet yaşamamak için ödemenizi acilen yapmanızı önemle rica ederiz.",
    "Genel Bilgilendirme": "Sayın {isim}, ofisimizle ilgili bilgilendirme..."
}

# --- SESSION ---
if 'hizli_not' not in st.session_state: st.session_state['hizli_not'] = ""
if 'sessiz_mod' not in st.session_state: st.session_state['sessiz_mod'] = False

# --- BAĞLANTILAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]; API_TOKEN = st.secrets["API_TOKEN"]
    GRUP_ID = st.secrets["GRUP_ID"]; DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
except: st.error("⚠️ Ayar Hatası: Secrets eksik."); st.stop()

def google_sheet_baglan(sayfa_adi="Sheet1"):
    client = gspread.authorize(creds)
    if sayfa_adi == "Sheet1": return client.open("Is_Takip_Sistemi").sheet1
    else: return client.open("Is_Takip_Sistemi").worksheet(sayfa_adi)

def whatsapp_gonder(chat_id, mesaj):
    if st.session_state['sessiz_mod']: return False
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try: requests.post(url, json={'chatId': chat_id, 'message': mesaj}); return True
    except: return False

def numaralari_ayikla(tel_str):
    if not tel_str: return []
    tel_str = str(tel_str)
    # Excel'den gelen nan/float değerleri temizle
    if tel_str == "nan" or tel_str == "None": return []
    
    ham_parcalar = re.split(r'[,\n/]', tel_str)
    temiz = []
    for parca in ham_parcalar:
        sadece_rakam = re.sub(r'\D', '', parca)
        if len(sadece_rakam) == 10: temiz.append("90" + sadece_rakam)
        elif len(sadece_rakam) == 11 and sadece_rakam.startswith("0"): temiz.append("9" + sadece_rakam)
    return temiz

def excel_yedek_olustur(df_is, df_mus, df_cari):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_is.to_excel(writer, sheet_name='Is_Listesi', index=False)
        df_mus.to_excel(writer, sheet_name='Musteriler', index=False)
        df_cari.to_excel(writer, sheet_name='Finans_Cari', index=False)
    return output.getvalue()

@st.cache_data(ttl=60)
def verileri_getir(sayfa="Ana"):
    try: sheet = google_sheet_baglan(sayfa); return pd.DataFrame(sheet.get_all_records())
    except: return pd.DataFrame()
def onbellek_temizle(): verileri_getir.clear()

# --- YAN MENÜ ---
with st.sidebar:
    st.markdown("<h3 style='text-align:center'>MÜŞAVİR PRO 💎</h3>", unsafe_allow_html=True)
    df_m = verileri_getir("Musteriler")
    p_list = ["Admin"]
    if not df_m.empty and "Sorumlu" in df_m.columns:
        p_list += [p for p in df_m["Sorumlu"].unique().tolist() if str(p) not in ["nan", ""]]
    aktif = st.selectbox("👤 Kullanıcı", list(set(p_list)))
    
    st.markdown("---")
    secim = option_menu(
        menu_title=None,
        options=["Genel Bakış", "İş Ekle", "İş Yönetimi", "Mesaj Merkezi", "Tasdik & Finans", "Ayarlar"],
        icons=["house", "plus-circle", "kanban", "chat-dots", "cash-coin", "gear"],
        menu_icon="cast", default_index=0,
        styles={"container": {"padding": "0!important", "background-color": "#ffffff"}, "nav-link": {"font-size": "14px"}}
    )
    
    st.session_state['sessiz_mod'] = st.toggle("🔕 Sessiz Mod", value=st.session_state['sessiz_mod'])

# --- 1. GENEL BAKIŞ ---
if secim == "Genel Bakış":
    st.title("📊 Yönetim Kokpiti")
    df = verileri_getir("Sheet1")
    if not df.empty and "Durum" in df.columns:
        c1, c2, c3 = st.columns(3)
        c1.metric("Bekleyen", len(df[df["Durum"]!="Tamamlandi"]))
        c2.metric("Tamamlanan", len(df[df["Durum"]=="Tamamlandi"]))
        c3.metric("Toplam İş", len(df))
    else: st.info("Sistemde kayıtlı iş yok.")

# --- 2. İŞ EKLE ---
elif secim == "İş Ekle":
    st.title("📝 İş Girişi")
    with st.form("is_ekle"):
        c1, c2 = st.columns(2); t = c1.date_input("Tarih"); s = c2.time_input("Saat")
        mus = st.selectbox("Mükellef", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
        notu = st.text_input("Açıklama", "KDV Beyannamesi")
        p = st.selectbox("Sorumlu", p_list)
        if st.form_submit_button("Kaydet"):
            google_sheet_baglan("Sheet1").append_row([t.strftime("%d.%m.%Y"), s.strftime("%H:%M"), f"{mus} - {notu}", "Gonderildi", "Bekliyor", "-", p])
            st.success("Kaydedildi!")

# --- 3. İŞ YÖNETİMİ ---
elif secim == "İş Yönetimi":
    st.title("📋 İş Takip")
    df = verileri_getir("Sheet1")
    if not df.empty:
        filtre = st.checkbox("Sadece Benim İşlerim")
        df_g = df[df["Personel"]==aktif] if filtre and aktif!="Admin" and "Personel" in df.columns else df
        st.dataframe(df_g[["Tarih", "Is Tanimi", "Durum", "Personel"]], use_container_width=True)
        secilen = st.selectbox("İş Seç:", df[df["Durum"]!="Tamamlandi"]["Is Tanimi"].tolist())
        if st.button("Bitir"):
            rows = google_sheet_baglan("Sheet1").get_all_values()
            for i, r in enumerate(rows):
                if len(r)>2 and r[2]==secilen:
                    google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Tamamlandi"); st.success("Bitti!"); st.rerun()

# --- 4. MESAJ MERKEZİ ---
elif secim == "Mesaj Merkezi":
    st.title("💬 Mesaj")
    secilen = st.selectbox("Müşteri", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
    msg = st.text_area("İçerik", "Mesajınızı buraya yazın...")
    if st.button("Gönder"):
        satir = df_m[df_m["Ad Soyad"] == secilen]
        if not satir.empty:
            for t in numaralari_ayikla(satir.iloc[0]["Telefon"]): whatsapp_gonder(t, msg)
            st.success("Gönderildi!")

# --- 5. TASDİK & FİNANS (CSV ENTEGRASYONLU) ---
elif secim == "Tasdik & Finans":
    st.title("🧮 Defter Tasdik 2026")
    
    st.info("💡 'PLANLAMA 2026' CSV dosyanızı yükleyin. Sistem 'Para Alındı mı' sütunu boş olanları borçlu sayar.")
    
    # CSV YÜKLEME ALANI
    uploaded_file = st.file_uploader("PLANLAMA 2026 Dosyasını Yükle (CSV)", type="csv")
    
    if uploaded_file:
        try:
            # CSV OKUMA
            df_tasdik = pd.read_csv(uploaded_file)
            
            # Gerekli sütunları kontrol et
            if "Ünvan / Ad Soyad" in df_tasdik.columns and "Para Alındı mı" in df_tasdik.columns:
                
                # Ödeme durumuna göre ayır (Boş olanlar = Ödemedi)
                odenmeyenler = df_tasdik[df_tasdik["Para Alındı mı"].isna() | (df_tasdik["Para Alındı mı"] == "")]
                odeyenler = df_tasdik[df_tasdik["Para Alındı mı"].notna() & (df_tasdik["Para Alındı mı"] != "")]
                
                # İstatistikler
                k1, k2, k3 = st.columns(3)
                k1.metric("Toplam Mükellef", len(df_tasdik))
                k2.metric("✅ İşlem Yapılan", len(odeyenler))
                k3.metric("❌ Ödemeyen (Riskli)", len(odenmeyenler), delta_color="inverse")
                
                st.divider()
                
                if not odenmeyenler.empty:
                    st.markdown(f"<div class='borclu-uyari'>🚨 DİKKAT: {len(odenmeyenler)} Mükellef Henüz Ödeme Yapmamış!</div>", unsafe_allow_html=True)
                    
                    # Tabloyu Göster
                    gosterilecek_sutunlar = ["Ünvan / Ad Soyad", "1.NUMARA", "Defter Tasdik Ücreti"]
                    st.dataframe(odenmeyenler[gosterilecek_sutunlar], use_container_width=True)
                    
                    st.subheader("📲 Borçlulara Toplu WhatsApp Gönder")
                    mesaj_taslagi = MESAJ_SABLONLARI["Tasdik Ödenmedi (SERT)"]
                    st.text_area("Gidecek Mesaj:", value=mesaj_taslagi, height=100, disabled=True)
                    
                    if st.button("🚀 LİSTEDEKİ HERKESE GÖNDER", type="primary"):
                        bar = st.progress(0)
                        basarili = 0
                        hatali = 0
                        
                        for i, row in odenmeyenler.iterrows():
                            isim = row["Ünvan / Ad Soyad"]
                            tel_ham = str(row.get("1.NUMARA", ""))
                            
                            tels = numaralari_ayikla(tel_ham)
                            
                            if tels:
                                kisiye_ozel_mesaj = mesaj_taslagi.replace("{isim}", str(isim))
                                for t in tels:
                                    whatsapp_gonder(t, kisiye_ozel_mesaj)
                                basarili += 1
                            else:
                                hatali += 1
                            
                            bar.progress((i + 1) / len(odenmeyenler))
                            time.sleep(0.5) # Spam olmaması için bekleme
                        
                        st.success(f"İşlem Tamamlandı! {basarili} kişiye mesaj atıldı. ({hatali} kişinin numarası yoktu)")
                else:
                    st.balloons()
                    st.success("Harika! Listede ödeme yapmayan kimse yok.")
            else:
                st.error("CSV dosyasında 'Ünvan / Ad Soyad' veya 'Para Alındı mı' sütunları bulunamadı.")
                st.write("Bulunan Sütunlar:", df_tasdik.columns.tolist())
                
        except Exception as e:
            st.error(f"Dosya okunurken hata oluştu: {e}")

# --- 6. AYARLAR ---
elif secim == "Ayarlar":
    st.title("⚙️ Ayarlar")
    if st.button("Yedek Al"): st.download_button("İndir", excel_yedek_olustur(verileri_getir("Sheet1"), df_m, verileri_getir("Cari")), "Yedek.xlsx")
