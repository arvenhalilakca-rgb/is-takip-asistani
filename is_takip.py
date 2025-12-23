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

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir Asistanı Dev",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TASARIM (CSS) ---
st.markdown("""
    <style>
    .stApp {background-color: #F8F9FA; font-family: 'Helvetica', sans-serif;}
    [data-testid="stSidebar"] {background-color: #2C3E50;}
    [data-testid="stSidebar"] * {color: #ECF0F1 !important;}
    div[data-testid="stMetricValue"] {font-size: 26px; color: #2C3E50; font-weight: bold;}
    div.stContainer {background-color: #FFFFFF; padding: 20px; border-radius: 12px; border: 1px solid #E0E0E0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);}
    .stButton>button {width: 100%; border-radius: 8px; font-weight: 600;}
    button[kind="primary"] {background: linear-gradient(90deg, #2980b9 0%, #2c3e50 100%); color: white;}
    .dogum-gunu-kutu {
        padding: 15px; background-color: #d4edda; color: #155724; 
        border-radius: 10px; border-left: 5px solid #28a745; margin-bottom: 20px;
        font-size: 16px; font-weight: bold;
    }
    .gecikmis-kutu {
        padding: 15px; background-color: #ffebee; color: #c0392b; 
        border-radius: 8px; border-left: 5px solid #c0392b; margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FİYAT & NACE VERİTABANI (Çanakkale 2026) ---
FIYAT_TARIFESI = {
    "Şahıs İşletmesi": {
        "Hizmet": {"Kurulus": 10000, "Defter": 5000},
        "Alım-Satım": {"Kurulus": 10000, "Defter": 5000},
        "İmalat - İnşaat": {"Kurulus": 10000, "Defter": 5000},
        "Serbest Meslek": {"Kurulus": 10000, "Defter": 6000},
        "Bilanço Esasına Tabii": {"Kurulus": 11250, "Defter": 10000}
    },
    "Limited Şirket": {
        "Hizmet": {"Kurulus": 25000, "Defter": 12500},
        "Alım-Satım": {"Kurulus": 25000, "Defter": 12500},
        "İmalat - İnşaat": {"Kurulus": 25000, "Defter": 15000}
    },
    "Anonim Şirket": {
        "Hizmet": {"Kurulus": 25000, "Defter": 12500},
        "İmalat - İnşaat": {"Kurulus": 25000, "Defter": 17500}
    }
}
NACE_DB = {"Muhasebe": "69.20", "İnşaat": "41.20", "Emlak": "68.31", "Restoran": "56.10", "Nakliye": "49.41", "Kuaför": "96.02", "Yazılım": "62.01"}

# --- BAĞLANTILAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]; API_TOKEN = st.secrets["API_TOKEN"]
    GRUP_ID = st.secrets["GRUP_ID"]; DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
except: st.error("⚠️ Ayar Hatası: Secrets eksik veya hatalı."); st.stop()

def google_sheet_baglan(sayfa_adi="Sheet1"):
    client = gspread.authorize(creds)
    if sayfa_adi == "Sheet1": return client.open("Is_Takip_Sistemi").sheet1
    else: return client.open("Is_Takip_Sistemi").worksheet(sayfa_adi)

def drive_yukle(uploaded_file, musteri_adi, evrak_turu):
    try:
        service = build('drive', 'v3', credentials=creds)
        uzanti = uploaded_file.name.split(".")[-1]
        yeni_isim = f"{musteri_adi}_{datetime.now().strftime('%Y-%m-%d')}_{evrak_turu}.{uzanti}".replace(" ", "_")
        file_metadata = {'name': yeni_isim, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(uploaded_file, mimetype=uploaded_file.type)
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file.get('webViewLink')
    except: return None

def whatsapp_gonder(chat_id, mesaj):
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    payload = {'chatId': chat_id, 'message': mesaj}
    try: requests.post(url, json=payload); return True
    except: return False

def numaralari_ayikla(tel_str):
    if not tel_str: return []
    tel_str = str(tel_str)
    ham_parcalar = re.split(r'[,\n]', tel_str)
    temiz_numaralar = []
    for parca in ham_parcalar:
        sadece_rakamlar = re.sub(r'\D', '', parca)
        if len(sadece_rakamlar) == 10: temiz_numaralar.append("90" + sadece_rakamlar)
        elif len(sadece_rakamlar) == 11 and sadece_rakamlar.startswith("0"): temiz_numaralar.append("9" + sadece_rakamlar)
    return temiz_numaralar

@st.cache_data(ttl=60)
def verileri_getir(sayfa="Ana"):
    try: sheet = google_sheet_baglan(sayfa); return pd.DataFrame(sheet.get_all_records())
    except: return pd.DataFrame()
def onbellek_temizle(): verileri_getir.clear()

# --- YAN MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    
    # DOĞUM GÜNÜ KONTROLÜ
    df_m = verileri_getir("Musteriler")
    bugun_doganlar = []
    if not df_m.empty and "Dogum_Tarihi" in df_m.columns:
        bugun = datetime.now()
        df_m["Dogum_Tarihi_Format"] = pd.to_datetime(df_m["Dogum_Tarihi"], format='%d.%m.%Y', errors='coerce')
        bugun_doganlar_df = df_m[
            (df_m["Dogum_Tarihi_Format"].dt.day == bugun.day) & 
            (df_m["Dogum_Tarihi_Format"].dt.month == bugun.month)
        ]
        if not bugun_doganlar_df.empty:
            bugun_doganlar = bugun_doganlar_df["Ad Soyad"].tolist()
            st.warning(f"🎂 BUGÜN {len(bugun_doganlar)} DOĞUM GÜNÜ VAR!")
            for k in bugun_doganlar: st.caption(f"🎉 {k}")

    # TAM MENÜ (Girişsiz, Herkes Her Şeyi Görür)
    menu = [
        "📊 Genel Bakış", 
        "➕ İş Ekle", 
        "✅ İş Yönetimi", 
        "📂 Müşteri Arşivi",
        "💰 Finans & Kâr",
        "🏢 Kuruluş Sihirbazı",
        "🧮 Defter Tasdik",
        "👥 Personel & Portföy"
    ]
    secim = st.radio("MENÜ", menu)
    st.markdown("---")
    st.caption("Geliştirici Modu (Açık Erişim)")

# --- 1. DASHBOARD ---
if secim == "📊 Genel Bakış":
    st.title("📊 Ofis Kokpiti")
    
    # Doğum Günü Kutusu
    if bugun_doganlar:
        st.markdown(f"""<div class="dogum-gunu-kutu">🎉 İYİ Kİ DOĞDUNUZ! Bugün <b>{', '.join(bugun_doganlar)}</b> doğum günü.</div>""", unsafe_allow_html=True)
        st.balloons()
        c_dg1, c_dg2 = st.columns([3,1])
        kisi = c_dg1.selectbox("Kutla:", bugun_doganlar)
        if c_dg2.button("🎁 Mesaj At", type="primary"):
            satir = df_m[df_m["Ad Soyad"] == kisi]
            if not satir.empty:
                nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                msg = f"Sayın *{kisi}*,\n\nDoğum gününüzü kutlar, sağlıklı ve başarılı bir yaş dileriz. 🎂\n\n*Mali Müşavirlik Ofisiniz*"
                for n in nums: whatsapp_gonder(n, msg)
                st.success("Kutlandı!")

    df = verileri_getir("Sheet1")
    if not df.empty and "Durum" in df.columns:
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Toplam İş", len(df))
            c2.metric("✅ Biten", len(df[df["Durum"]=="Tamamlandi"]))
            c3.metric("⏳ Bekleyen", len(df[df["Durum"]!="Tamamlandi"]))
            
            # KÂR METRİĞİ (Artık herkese açık)
            df_c = verileri_getir("Cari")
            if not df_c.empty:
                df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
                net = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
                c4.metric("Net Kâr", f"{net:,.0f} TL", delta_color="normal" if net>0 else "inverse")
            else:
                c4.metric("Net Kâr", "0 TL")

        col1, col2 = st.columns(2)
        with col1: st.dataframe(df.tail(5), use_container_width=True, hide_index=True)
        with col2: st.bar_chart(df["Durum"].value_counts())

# --- 2. İŞ EKLE ---
elif secim == "➕ İş Ekle":
    st.title("📝 İş Girişi")
    with st.form("is"):
        c1, c2 = st.columns(2); t = c1.date_input("Tarih"); s = c2.time_input("Saat")
        df_m = verileri_getir("Musteriler")
        mus = st.selectbox("Mükellef", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
        notu = st.text_input("İş Tanımı"); sms = st.checkbox("SMS Gönder")
        if st.form_submit_button("Kaydet", type="primary"):
            google_sheet_baglan("Sheet1").append_row([t.strftime("%d.%m.%Y"), s.strftime("%H:%M"), f"{mus} - {notu}", "Gonderildi", "Bekliyor", "-"])
            onbellek_temizle(); whatsapp_gonder(GRUP_ID, f"🆕 *İŞ*: {mus} - {notu}"); st.success("Kaydedildi!")

# --- 3. İŞ YÖNETİMİ ---
elif secim == "✅ İş Yönetimi":
    st.title("📋 Görev Takip")
    if st.button("🔄 Yenile"): onbellek_temizle(); st.rerun()
    df = verileri_getir("Sheet1")
    if not df.empty:
        bekleyen = df[df["Durum"]!="Tamamlandi"].copy()
        bugun = datetime.now()
        bekleyen['Tarih_Format'] = pd.to_datetime(bekleyen['Tarih'], format='%d.%m.%Y', errors='coerce')
        gec = bekleyen[bekleyen['Tarih_Format'] < bugun]
        if not gec.empty: st.markdown(f"""<div class="gecikmis-kutu">🚨 <b>{len(gec)}</b> gecikmiş iş var!</div>""", unsafe_allow_html=True)
        if not bekleyen.empty:
            st.dataframe(bekleyen[["Tarih", "Is Tanimi", "Durum"]], use_container_width=True)
            with st.form("bitir"):
                sec = st.selectbox("Biten:", bekleyen["Is Tanimi"].tolist())
                if st.form_submit_button("Kapat"):
                    rows = google_sheet_baglan("Sheet1").get_all_values()
                    for i, r in enumerate(rows):
                        if len(r)>2 and r[2]==sec:
                            google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Tamamlandi"); onbellek_temizle(); st.rerun()
        else: st.info("Bekleyen iş yok.")

# --- 4. ARŞİV ---
elif secim == "📂 Müşteri Arşivi":
    st.title("📂 Arşiv")
    df_m = verileri_getir("Musteriler")
    if not df_m.empty:
        m = st.selectbox("Seç:", df_m["Ad Soyad"].tolist())
        with st.form("up"):
            d = st.file_uploader("Dosya"); tur = st.selectbox("Tür", ["Fatura", "Diğer"])
            if st.form_submit_button("Yükle"):
                l = drive_yukle(d, m, tur) if d else "-"
                google_sheet_baglan("Sheet1").append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{m} - [{tur}]", "-", "Tamamlandi", l]); st.success("Ok")

# --- 5. FİNANS ---
elif secim == "💰 Finans & Kâr":
    st.title("💰 Finans")
    df = verileri_getir("Cari")
    tab1, tab2, tab3 = st.tabs(["Analiz", "İşlem Ekle", "Yıllık Tahakkuk"])
    with tab1:
        if not df.empty:
            df["Tutar"] = pd.to_numeric(df["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
            net = df[df["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df[df["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
            st.metric("Net Kâr", f"{net:,.0f} TL")
            st.bar_chart(df[df["Islem_Turu"].str.contains("Gider", na=False)].set_index("Aciklama")["Tutar"])
    with tab2:
        with st.form("fin"):
            t=st.date_input("Tarih"); tur=st.radio("Tür", ["Tahsilat", "Borç", "Gider"]); m=st.text_input("Açıklama"); tut=st.number_input("Tutar")
            if st.form_submit_button("Kaydet"): google_sheet_baglan("Cari").append_row([t.strftime("%d.%m.%Y"), m, tur, tut, "-"]); onbellek_temizle(); st.success("Ok")
    with tab3:
        with st.form("yillik"):
             df_m = verileri_getir("Musteriler")
             ymus = st.selectbox("Müşteri", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
             ytut = st.number_input("Aylık Tutar")
             if st.form_submit_button("12 Aylık İşle"):
                 rows=[[f"15.{i+1:02d}.2025", ymus, "Hizmet Bedeli (Borç)", ytut, "Yıllık"] for i in range(12)]
                 google_sheet_baglan("Cari").append_rows(rows); onbellek_temizle(); st.success("İşlendi!")

# --- 6. KURULUŞ ---
elif secim == "🏢 Kuruluş Sihirbazı":
    st.title("🏢 Kuruluş & Teklif (2026 Tarife)")
    with st.form("kur"):
        aday=st.text_input("Aday"); tur=st.selectbox("Tür", list(FIYAT_TARIFESI.keys()))
        if st.form_submit_button("Teklif Ver"):
            f=FIYAT_TARIFESI[tur]["Hizmet"]; st.success(f"Öneri: {f['Kurulus']} TL Kuruluş | {f['Defter']} TL Aylık")
            google_sheet_baglan("Sheet1").append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{aday} - [AÇILIŞ]", "-", "Tamamlandi", "-"])

# --- 7. TASDİK ---
elif secim == "🧮 Defter Tasdik":
    st.title("🧮 Tasdik Hesapla")
    with st.container():
        c1,c2=st.columns(2); tur=c1.selectbox("Tür", ["Bilanço", "İşletme"]); s=c2.number_input("Sayfa", 100)
        toplam = (s*6.0)+300.0+3500.0
        if st.button("Hesapla"): st.metric("Toplam Maliyet", f"{toplam:,.2f} TL")

# --- 8. PERSONEL ---
elif secim == "👥 Personel & Portföy":
    st.title("👥 Personel & Portföy Analizi")
    df_m = verileri_getir("Musteriler")
    if not df_m.empty and "Sorumlu" in df_m.columns and "Ucret" in df_m.columns:
        df_m["Ucret"] = pd.to_numeric(df_m["Ucret"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
        ozet = df_m.groupby("Sorumlu").agg(Musteri=("Ad Soyad", "count"), Ciro=("Ucret", "sum")).reset_index().sort_values(by="Ciro", ascending=False)
        c1, c2 = st.columns([2,1])
        with c1: st.dataframe(ozet, use_container_width=True)
        with c2: fig=px.pie(ozet, values='Ciro', names='Sorumlu', hole=0.4); st.plotly_chart(fig, use_container_width=True)
    else: st.error("Musteriler sayfasına 'Sorumlu' ve 'Ucret' sütunlarını ekleyiniz.")
