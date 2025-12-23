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
import pdfplumber  # <--- YENİ KÜTÜPHANE (PDF OKUMAK İÇİN)

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir Asistanı AI",
    page_icon="🤖",
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
    .ocr-sonuc {
        padding: 15px; background-color: #e3f2fd; color: #0d47a1; 
        border-radius: 10px; border-left: 5px solid #0d47a1; margin-bottom: 20px;
        font-size: 18px; font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- VERİTABANLARI ---
FIYAT_TARIFESI = {
    "Şahıs": {"Hizmet": {"Kurulus": 10000, "Defter": 5000}},
    "Ltd": {"Hizmet": {"Kurulus": 25000, "Defter": 12500}},
    "A.Ş.": {"Hizmet": {"Kurulus": 25000, "Defter": 12500}}
}

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

# --- YENİ: PDF'TEN VERİ ÇEKME MOTORU ---
def beyanname_analiz_et(pdf_file):
    try:
        text = ""
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text += page.extract_text()
        
        # 1. KREDİ KARTI (POS) TUTARINI BUL (Genelde 45. Satır civarı)
        # Metin içinde "Kredi Kartı" kelimesini arar ve yanındaki rakamı çeker.
        pos_tutari = 0.0
        
        # Basit bir Regex: "Kredi Kartı" kelimesinden sonra gelen ilk parasal değeri bul
        # Örnek metin: "Kredi Kartı ile Tahsil Edilen Teslim ve Hizmetlerin KDV Dahil Karşılığı 45 12.500,50"
        match = re.search(r"Kredi Kartı.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
        
        if match:
            bulunan_sayi = match.group(1) # Örn: 12.500,50
            # Sayıyı Python formatına çevir (Noktayı sil, virgülü nokta yap)
            temiz_sayi = float(bulunan_sayi.replace(".", "").replace(",", "."))
            pos_tutari = temiz_sayi
            
        return pos_tutari, text # Tutarı ve tüm metni döndür
    except Exception as e:
        return 0.0, str(e)

def onbellek_temizle(): verileri_getir.clear()

@st.cache_data(ttl=60)
def verileri_getir(sayfa="Ana"):
    try: sheet = google_sheet_baglan(sayfa); return pd.DataFrame(sheet.get_all_records())
    except: return pd.DataFrame()

# --- YAN MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    
    # DOĞUM GÜNÜ
    df_m = verileri_getir("Musteriler")
    if not df_m.empty and "Dogum_Tarihi" in df_m.columns:
        bugun = datetime.now()
        df_m["Dogum_Tarihi_Format"] = pd.to_datetime(df_m["Dogum_Tarihi"], format='%d.%m.%Y', errors='coerce')
        dg = df_m[(df_m["Dogum_Tarihi_Format"].dt.day == bugun.day) & (df_m["Dogum_Tarihi_Format"].dt.month == bugun.month)]
        if not dg.empty: st.warning(f"🎂 BUGÜN {len(dg)} DOĞUM GÜNÜ!")

    secim = st.radio("MENÜ", ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "🏢 Kuruluş Sihirbazı", "💰 Finans & Kâr", "🧮 Defter Tasdik", "👥 Personel & Portföy"])
    st.markdown("---")
    st.caption("AI Destekli Versiyon 🤖")

# --- 1. DASHBOARD ---
if secim == "📊 Genel Bakış":
    st.title("📊 Ofis Kokpiti")
    df = verileri_getir("Sheet1")
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Toplam İş", len(df))
        c2.metric("✅ Biten", len(df[df["Durum"]=="Tamamlandi"]))
        c3.metric("⏳ Bekleyen", len(df[df["Durum"]!="Tamamlandi"]))
        
        df_c = verileri_getir("Cari")
        if not df_c.empty:
            df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
            net = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
            c4.metric("Net Kâr", f"{net:,.0f} TL")
            
        c_g1, c_g2 = st.columns(2)
        c_g1.dataframe(df.tail(5), use_container_width=True)
        if "Durum" in df.columns: c_g2.bar_chart(df["Durum"].value_counts())

# --- 2. İŞ EKLE ---
elif secim == "➕ İş Ekle":
    st.title("📝 İş Girişi")
    with st.form("is"):
        t=st.date_input("Tarih"); s=st.time_input("Saat")
        m=st.selectbox("Mükellef", verileri_getir("Musteriler")["Ad Soyad"].tolist())
        n=st.text_input("Not"); 
        if st.form_submit_button("Kaydet"):
            google_sheet_baglan("Sheet1").append_row([t.strftime("%d.%m.%Y"), s.strftime("%H:%M"), f"{m} - {n}", "Gonderildi", "Bekliyor", "-"])
            onbellek_temizle(); st.success("Ok")

# --- 3. İŞ YÖNETİMİ (CHECKLIST DEVAM) ---
elif secim == "✅ İş Yönetimi":
    st.title("📋 İş Takibi")
    if st.button("Yenile"): onbellek_temizle(); st.rerun()
    df=verileri_getir("Sheet1")
    bekleyen=df[df["Durum"]!="Tamamlandi"]
    sec=st.selectbox("İş Seç:", bekleyen["Is Tanimi"].tolist() if not bekleyen.empty else [])
    
    if sec and ("AÇILIŞ" in sec or "KURULUŞ" in sec):
        st.info("Kuruluş Adımları")
        c1,c2=st.columns(2)
        s1=c1.checkbox("1. Sicil Gazetesi"); s2=c1.checkbox("2. İmza Sirküsü"); s3=c1.checkbox("3. Faydalanıcı Formu")
        s4=c2.checkbox("4. E-Tebligat"); s5=c2.checkbox("5. Banka"); s6=c2.checkbox("6. Yoklama/ÖKC")
        if st.button("Güncelle"): 
            durum="İşlemde"
            if s1 and s2 and s3 and s4 and s5 and s6: durum="Tamamlandi"
            rows=google_sheet_baglan("Sheet1").get_all_values()
            for i,r in enumerate(rows):
                if len(r)>2 and r[2]==sec:
                    google_sheet_baglan("Sheet1").update_cell(i+1,5,durum); onbellek_temizle(); st.success(f"Durum: {durum}"); st.rerun(); break
    elif sec:
        if st.button("Kapat"): 
            rows=google_sheet_baglan("Sheet1").get_all_values()
            for i,r in enumerate(rows):
                if len(r)>2 and r[2]==sec: google_sheet_baglan("Sheet1").update_cell(i+1,5,"Tamamlandi"); onbellek_temizle(); st.rerun()

# --- 4. FİNANS (KDV OKUYUCU EKLENDİ!) ---
elif secim == "💰 Finans & Kâr":
    st.title("💰 Finans")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Analiz", "📄 Beyanname Oku (OCR)", "💸 Manuel Ekle", "📜 Ekstre"])
    
    # TAB 1: Analiz (Aynı)
    with tab1:
        df_c = verileri_getir("Cari")
        if not df_c.empty:
            df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
            st.bar_chart(df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)].set_index("Aciklama")["Tutar"])

    # --- TAB 2: YENİ BEYANNAME OKUYUCU ---
    with tab2:
        st.subheader("📄 KDV Beyannamesinden Veri Çek")
        st.info("KDV Beyannamesi PDF dosyasını yükleyin, sistem 'Kredi Kartı (POS)' tutarını otomatik okusun.")
        
        uploaded_pdf = st.file_uploader("KDV Beyannamesi (PDF)", type="pdf")
        m_sec = st.selectbox("Hangi Mükellefin Beyannamesi?", verileri_getir("Musteriler")["Ad Soyad"].tolist())
        
        if uploaded_pdf:
            with st.spinner("Beyanname taranıyor..."):
                pos_tutar, raw_text = beyanname_analiz_et(uploaded_pdf)
            
            if pos_tutar > 0:
                st.markdown(f"""
                <div class="ocr-sonuc">
                    ✅ BULUNAN POS TUTARI: {pos_tutar:,.2f} TL
                </div>
                """, unsafe_allow_html=True)
                
                st.caption("Veri 45. Satır (Kredi Kartı ile Tahsil Edilen) kısmından çekildi.")
                
                if st.button("💾 Bu Tutarı Cariye Kaydet", type="primary"):
                    aciklama = f"KDV Beyannamesi POS Satışı - {datetime.now().strftime('%B %Y')}"
                    google_sheet_baglan("Cari").append_row([datetime.now().strftime("%d.%m.%Y"), m_sec, "POS Satışı (Bilgi)", pos_tutar, aciklama])
                    onbellek_temizle()
                    st.success("Tutar sisteme kaydedildi!")
            else:
                st.error("⚠️ PDF içinde 'Kredi Kartı' satırı veya tutarı okunamadı. Lütfen dosyanın KDV Beyannamesi olduğundan emin olun.")
                with st.expander("Okunan Ham Metni Gör"):
                    st.text(raw_text)

    # TAB 3: Manuel (Eski)
    with tab3:
        with st.form("manuel"):
            t=st.date_input("Tarih"); tr=st.radio("Tür", ["Tahsilat", "Borç", "Gider"])
            mu=st.text_input("Müşteri/Açıklama"); tu=st.number_input("Tutar")
            if st.form_submit_button("Kaydet"): google_sheet_baglan("Cari").append_row([t.strftime("%d.%m.%Y"), mu, tr, tu, "-"]); st.success("Ok")

# --- 5. DİĞERLERİ (Özet) ---
elif secim == "📂 Müşteri Arşivi":
    st.title("📂 Arşiv"); m=st.selectbox("Seç:", verileri_getir("Musteriler")["Ad Soyad"].tolist())
    d=st.file_uploader("Dosya")
    if st.button("Yükle") and d: drive_yukle(d, m, "Evrak"); st.success("Yüklendi")

elif secim == "🏢 Kuruluş Sihirbazı":
    st.title("🏢 Kuruluş"); a=st.text_input("Aday"); t=st.selectbox("Tür", ["Ltd", "Şahıs"])
    if st.button("Teklif"): st.success("Hesaplandı")

elif secim == "🧮 Defter Tasdik":
    st.title("🧮 Tasdik"); s=st.number_input("Sayfa"); st.metric("Tutar", s*6+300)

elif secim == "👥 Personel & Portföy":
    st.title("👥 Analiz"); st.info("Müşteri Listesi Sorumlu/Ücret Analizi Burada")
