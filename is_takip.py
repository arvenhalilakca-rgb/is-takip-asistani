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
    page_title="Müşavir Asistanı Pro",
    page_icon="🏢",
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
    .gecikmis-kutu {padding: 15px; background-color: #ffebee; color: #c0392b; border-radius: 8px; border-left: 5px solid #c0392b; margin-bottom: 20px;}
    </style>
    """, unsafe_allow_html=True)

# --- FİYAT & NACE VERİTABANI ---
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

# --- OTURUM YÖNETİMİ ---
if 'giris_yapildi' not in st.session_state: st.session_state['giris_yapildi'] = False
if 'kullanici_rolu' not in st.session_state: st.session_state['kullanici_rolu'] = None

def giris_ekrani():
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=100)
        st.title("Giriş Paneli")
        k = st.text_input("Kullanıcı Adı"); s = st.text_input("Şifre", type="password")
        if st.button("Giriş", type="primary"):
            if k == "admin" and s == "1234":
                st.session_state['giris_yapildi'] = True; st.session_state['kullanici_rolu'] = "admin"; st.rerun()
            elif k == "personel" and s == "1111":
                st.session_state['giris_yapildi'] = True; st.session_state['kullanici_rolu'] = "personel"; st.rerun()
            else: st.error("Hatalı!")

if not st.session_state['giris_yapildi']: giris_ekrani(); st.stop()

# --- BAĞLANTILAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]; API_TOKEN = st.secrets["API_TOKEN"]
    GRUP_ID = st.secrets["GRUP_ID"]; DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
except: st.error("⚠️ Secrets Eksik!"); st.stop()

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

# --- MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    rol = st.session_state['kullanici_rolu']
    # MENÜ SEÇENEKLERİ
    menu = ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi"]
    
    if rol == "admin": 
        # Patron Modunda Ekstra Menüler
        menu += ["🧮 Defter Tasdik", "👥 Personel & Portföy", "🏢 Kuruluş Sihirbazı", "💰 Finans & Kâr", "📂 Müşteri Arşivi"]
    else:
        menu += ["📂 Müşteri Arşivi"]
        
    secim = st.radio("MENÜ", menu)
    st.markdown("---")
    if st.button("Çıkış"): st.session_state['giris_yapildi'] = False; st.rerun()

# --- 1. DASHBOARD ---
if secim == "📊 Genel Bakış":
    st.title("📊 Yönetim Kokpiti")
    df = verileri_getir("Sheet1")
    if not df.empty and "Durum" in df.columns:
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Toplam İş", len(df))
            c2.metric("✅ Biten", len(df[df["Durum"]=="Tamamlandi"]))
            c3.metric("⏳ Bekleyen", len(df[df["Durum"]!="Tamamlandi"]))
            if rol == "admin":
                df_c = verileri_getir("Cari")
                if not df_c.empty:
                    df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
                    kar = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
                    c4.metric("Net Kâr", f"{kar:,.0f} TL", delta_color="normal" if kar>0 else "inverse")
            else: c4.metric("Rol", "Personel")
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
        bekleyen = df[df["Durum"]!="Tamamlandi"]
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

# --- YENİ: DEFTER TASDİK HESAPLAYICI (MADDE 3) ---
elif secim == "🧮 Defter Tasdik":
    st.title("🧮 Defter Tasdik & Kırtasiye Hesaplayıcı")
    st.info("Sayfa sayılarına göre tahmini noter masrafı ve hizmet bedelini hesaplar.")
    
    with st.container():
        c1, c2 = st.columns(2)
        defter_turu = c1.selectbox("Defter Türü", ["Yevmiye/Kebir/Envanter (Bilanço)", "İşletme Defteri", "Serbest Meslek", "A.Ş. Karar/Pay"])
        sayfa_sayisi = c2.number_input("Toplam Sayfa Sayısı", min_value=0, value=100, step=50)
        
        st.markdown("### ⚙️ Maliyet Parametreleri (Değiştirilebilir)")
        c3, c4, c5 = st.columns(3)
        noter_sayfa_ucreti = c3.number_input("Noter Sayfa Başı (TL)", value=6.00)
        noter_kapak_ucreti = c4.number_input("Noter Kapak/Cilt (TL)", value=300.00)
        hizmet_bedeli = c5.number_input("Bizim Hizmet Bedelimiz (TL)", value=3500.0)
        
        # HESAPLAMA
        noter_toplam = (sayfa_sayisi * noter_sayfa_ucreti) + noter_kapak_ucreti
        genel_toplam = noter_toplam + hizmet_bedeli
        
        st.divider()
        
        if st.button("🧮 Hesapla ve Teklif Oluştur", type="primary"):
            c_res1, c_res2 = st.columns(2)
            c_res1.metric("Noter Masrafı (Tahmini)", f"{noter_toplam:,.2f} TL")
            c_res2.metric("Müşteriden İstenecek Toplam", f"{genel_toplam:,.2f} TL", delta="Tahsil Edilecek")
            
            st.success("Hesaplama tamamlandı. Bu tutarı müşteriye 'Aralık Ayı Defter Tasdik Avansı' olarak iletebilirsiniz.")

# --- YENİ: PERSONEL & PORTFÖY ANALİZİ (MADDE 4) ---
elif secim == "👥 Personel & Portföy":
    st.title("👥 Personel Performans & Portföy Analizi")
    st.markdown("Hangi personel hangi müşterilere bakıyor ve ne kadar ciro yönetiyor?")
    
    df_m = verileri_getir("Musteriler")
    
    if not df_m.empty and "Sorumlu" in df_m.columns and "Ucret" in df_m.columns:
        # Sayısal veriyi temizle (Ucret sütunu)
        df_m["Ucret"] = pd.to_numeric(df_m["Ucret"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
        
        # 1. ÖZET TABLO (Personel Bazlı)
        ozet = df_m.groupby("Sorumlu").agg(
            Musteri_Sayisi=("Ad Soyad", "count"),
            Yonetilen_Ciro=("Ucret", "sum")
        ).reset_index().sort_values(by="Yonetilen_Ciro", ascending=False)
        
        c1, c2 = st.columns([2,1])
        with c1:
            st.subheader("🏆 Performans Ligi (Ciro Bazlı)")
            st.dataframe(ozet, use_container_width=True)
            
            # Seçilen Personelin Detayı
            personeller = df_m["Sorumlu"].unique()
            secilen_p = st.selectbox("Personel Seç ve Detay Gör:", personeller)
            
            if secilen_p:
                p_df = df_m[df_m["Sorumlu"] == secilen_p]
                st.write(f"**{secilen_p}** sorumluluğundaki müşteriler:")
                st.dataframe(p_df[["Ad Soyad", "Telefon", "Ucret"]], use_container_width=True)
                
        with c2:
            st.subheader("📊 Ciro Dağılımı")
            fig = px.pie(ozet, values='Yonetilen_Ciro', names='Sorumlu', title='Portföy Büyüklüğü', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            
    else:
        st.error("⚠️ Veri Hatası: 'Musteriler' sayfasında 'Sorumlu' ve 'Ucret' sütunları olduğundan emin olun.")
        st.info("Lütfen Google Sheet'e gidip 'Musteriler' sayfasına 'Sorumlu' ve 'Ucret' sütunlarını ekleyin ve doldurun.")

# --- 5. KURULUŞ SİHİRBAZI ---
elif secim == "🏢 Kuruluş Sihirbazı":
    st.title("🏢 Kuruluş & Teklif")
    with st.form("kur"):
        aday = st.text_input("Aday"); tur = st.selectbox("Tür", list(FIYAT_TARIFESI.keys()))
        if st.form_submit_button("Hesapla"):
            fiyat = FIYAT_TARIFESI[tur]["Hizmet"]
            st.success(f"Tarife: {fiyat['Kurulus']} TL Kuruluş | {fiyat['Defter']} TL Aylık")
            google_sheet_baglan("Sheet1").append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{aday} - [AÇILIŞ]", "-", "Tamamlandi", "-"])
            st.success("Kaydedildi.")

# --- 6. FİNANS ---
elif secim == "💰 Finans & Kâr":
    st.title("💰 Finans")
    df = verileri_getir("Cari")
    tab1, tab2 = st.tabs(["Analiz", "İşlem Ekle"])
    with tab1:
        if not df.empty:
            df["Tutar"] = pd.to_numeric(df["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
            net = df[df["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df[df["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
            st.metric("Net Kâr", f"{net:,.0f} TL")
            st.bar_chart(df[df["Islem_Turu"].str.contains("Gider", na=False)].set_index("Aciklama")["Tutar"])
    with tab2:
        with st.form("fin"):
            t = st.date_input("Tarih"); tur = st.radio("Tür", ["Tahsilat", "Borç", "Gider"])
            mus = st.text_input("Müşteri/Açıklama"); tut = st.number_input("Tutar")
            if st.form_submit_button("Kaydet"):
                google_sheet_baglan("Cari").append_row([t.strftime("%d.%m.%Y"), mus, tur, tut, "-"]); st.success("Ok")

# --- 7. ARŞİV ---
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
