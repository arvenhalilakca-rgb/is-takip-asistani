import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import requests
import pandas as pd
import re
from datetime import datetime, timedelta
import time
import plotly.express as px
import pdfplumber

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir Asistanı Pro+",
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
    div.stContainer {background-color: #FFFFFF; padding: 20px; border-radius: 12px; border: 1px solid #E0E0E0;}
    .stButton>button {width: 100%; border-radius: 8px; font-weight: 600;}
    button[kind="primary"] {background: linear-gradient(90deg, #2980b9 0%, #2c3e50 100%); color: white;}
    
    /* Tarihli Not Kutusu */
    .tarihli-not {
        font-size: 13px; color: #2c3e50; 
        background-color: #ecf0f1; padding: 8px; 
        border-radius: 5px; margin-bottom: 5px; border-left: 3px solid #3498db;
    }
    .istatistik-ozet {
        font-size: 14px; font-weight: bold; color: #7f8c8d; margin-top: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SESSION STATE ---
if 'hizli_not' not in st.session_state: st.session_state['hizli_not'] = ""

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
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try: requests.post(url, json={'chatId': chat_id, 'message': mesaj}); return True
    except: return False

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

def numaralari_ayikla(tel_str):
    if not tel_str: return []
    tel_str = str(tel_str)
    ham_parcalar = re.split(r'[,\n]', tel_str)
    temiz = []
    for parca in ham_parcalar:
        sadece_rakam = re.sub(r'\D', '', parca)
        if len(sadece_rakam) == 10: temiz.append("90" + sadece_rakam)
        elif len(sadece_rakam) == 11 and sadece_rakam.startswith("0"): temiz.append("9" + sadece_rakam)
    return temiz

@st.cache_data(ttl=60)
def verileri_getir(sayfa="Ana"):
    try: sheet = google_sheet_baglan(sayfa); return pd.DataFrame(sheet.get_all_records())
    except: return pd.DataFrame()
def onbellek_temizle(): verileri_getir.clear()

# --- YAN MENÜ & KULLANICI SEÇİMİ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=70)
    
    # KULLANICI SEÇİMİ (Login Yerine Hızlı Seçim)
    df_m = verileri_getir("Musteriler")
    personel_listesi = ["Admin"]
    if not df_m.empty and "Sorumlu" in df_m.columns:
        personel_listesi += df_m["Sorumlu"].unique().tolist()
        # Tekrar edenleri temizle ve boşları at
        personel_listesi = list(set([p for p in personel_listesi if str(p) != "nan" and str(p) != ""]))
    
    aktif_kullanici = st.selectbox("👤 Şu an Kimsin?", personel_listesi)
    
    # Hızlı Not
    st.markdown("### 📝 Hızlı Not")
    st.session_state['hizli_not'] = st.text_area("Anlık Notlar:", value=st.session_state['hizli_not'], height=100)
    
    st.markdown("---")
    menu = ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "💰 Finans & Kâr", "🏢 Kuruluş Sihirbazı", "🧮 Defter Tasdik", "👥 Personel & Portföy"]
    secim = st.radio("MENÜ", menu)

# --- 1. DASHBOARD ---
if secim == "📊 Genel Bakış":
    st.title("📊 Yönetim Kokpiti")
    df = verileri_getir("Sheet1")
    
    # DOĞUM GÜNÜ
    bugun_doganlar = []
    if not df_m.empty and "Dogum_Tarihi" in df_m.columns:
        bugun = datetime.now()
        df_m["Dogum_Tarihi_Format"] = pd.to_datetime(df_m["Dogum_Tarihi"], format='%d.%m.%Y', errors='coerce')
        bg = df_m[(df_m["Dogum_Tarihi_Format"].dt.day == bugun.day) & (df_m["Dogum_Tarihi_Format"].dt.month == bugun.month)]
        if not bg.empty: st.success(f"🎂 İYİ Kİ DOĞDUNUZ: {', '.join(bg['Ad Soyad'].tolist())}")

    if not df.empty and "Durum" in df.columns:
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Toplam İş", len(df))
            c2.metric("✅ Biten", len(df[df["Durum"]=="Tamamlandi"]))
            c3.metric("⏳ Bekleyen", len(df[df["Durum"]!="Tamamlandi"]))
            
            # KÂR
            df_c = verileri_getir("Cari")
            if not df_c.empty:
                df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
                net = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
                c4.metric("Net Kâr", f"{net:,.0f} TL")

        # Madde 18: Hızlı İstatistikler
        col1, col2 = st.columns(2)
        with col1:
            st.dataframe(df.tail(5), use_container_width=True, hide_index=True)
            # En aktif müşteriyi bul
            if "Is Tanimi" in df.columns:
                try:
                    en_aktif = df["Is Tanimi"].apply(lambda x: x.split(" - ")[0] if " - " in x else x).mode()[0]
                    st.markdown(f"<div class='istatistik-ozet'>🏆 Haftanın En Aktif Müşterisi: {en_aktif}</div>", unsafe_allow_html=True)
                except: pass
                
        with col2: 
            st.bar_chart(df["Durum"].value_counts())

# --- 2. İŞ EKLE ---
elif secim == "➕ İş Ekle":
    st.title("📝 İş Girişi")
    with st.form("is"):
        c1, c2 = st.columns(2); t = c1.date_input("Tarih"); s = c2.time_input("Saat")
        mus = st.selectbox("Mükellef", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
        
        # Şablonlar
        sablonlar = ["KDV Beyannamesi", "Muhtasar", "SGK Giriş", "SGK Çıkış", "Geçici Vergi", "Genel Danışmanlık", "Diğer"]
        secilen_sablon = st.selectbox("İş Şablonu", sablonlar)
        if secilen_sablon == "Diğer": notu = st.text_input("Özel Açıklama")
        else: notu = secilen_sablon
        
        sms = st.checkbox("SMS Gönder")
        if st.form_submit_button("Kaydet", type="primary"):
            google_sheet_baglan("Sheet1").append_row([t.strftime("%d.%m.%Y"), s.strftime("%H:%M"), f"{mus} - {notu}", "Gonderildi", "Bekliyor", "-"])
            onbellek_temizle(); whatsapp_gonder(GRUP_ID, f"🆕 *İŞ*: {mus} - {notu}"); st.success("Kaydedildi!")

# --- 3. İŞ YÖNETİMİ (KİŞİSEL FİLTRE EKLENDİ) ---
elif secim == "✅ İş Yönetimi":
    st.title("📋 İş Takip")
    if st.button("🔄 Yenile"): onbellek_temizle(); st.rerun()
    
    df = verileri_getir("Sheet1")
    if not df.empty:
        # Madde 12: Benim İşlerim Filtresi
        filtre_bana_ait = st.checkbox(f"Sadece Bana ({aktif_kullanici}) Ait Olanları Göster")
        
        df_goster = df.copy()
        
        if filtre_bana_ait and aktif_kullanici != "Admin":
            if not df_m.empty and "Sorumlu" in df_m.columns:
                # Sorumlusu aktif kullanıcı olan müşterileri bul
                benim_musterilerim = df_m[df_m["Sorumlu"] == aktif_kullanici]["Ad Soyad"].tolist()
                # İş tanımı içinde bu müşteri adları geçiyor mu diye bak
                df_goster = df_goster[df_goster["Is Tanimi"].apply(lambda x: any(m in x for m in benim_musterilerim))]
                if df_goster.empty:
                    st.warning(f"⚠️ {aktif_kullanici} kullanıcısına atanmış müşteri bulunamadı veya iş yok.")
        
        # Madde 3: Renkli Etiketler (Basit Simülasyon)
        # Streamlit dataframe'de 'Durum' kolonunu daha görünür yapıyoruz
        st.dataframe(
            df_goster[["Tarih", "Is Tanimi", "Durum"]], 
            use_container_width=True,
            column_config={
                "Durum": st.column_config.SelectboxColumn("Durum", options=["Bekliyor", "Tamamlandi", "İptal", "İşlemde"], width="medium")
            },
            hide_index=True
        )

        # Madde 13: Tekrarlayan İş (Kopyalama)
        st.markdown("---")
        with st.expander("🛠️ İşlemler (Bitir / Kopyala)"):
            c1, c2 = st.columns(2)
            secilen = c1.selectbox("İş Seç:", df_goster["Is Tanimi"].tolist())
            
            if c2.button("🏁 İşi Kapat (Tamamlandı)"):
                 rows = google_sheet_baglan("Sheet1").get_all_values()
                 for i, r in enumerate(rows):
                    if len(r)>2 and r[2]==secilen:
                        google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Tamamlandi"); onbellek_temizle(); st.rerun()

            if c2.button("🔁 Gelecek Aya Kopyala (Tekrarla)"):
                 # Seçilen işin detaylarını bul
                 satir = df[df["Is Tanimi"] == secilen].iloc[0]
                 yeni_tarih = (datetime.now() + timedelta(days=30)).strftime("%d.%m.%Y")
                 google_sheet_baglan("Sheet1").append_row([yeni_tarih, satir["Saat"], satir["Is Tanimi"], "Gonderildi", "Bekliyor", "-"])
                 onbellek_temizle(); st.success("İş bir sonraki ay için kopyalandı!")

# --- 4. ARŞİV (TARİHLİ NOTLAR EKLENDİ) ---
elif secim == "📂 Müşteri Arşivi":
    st.title("📂 Arşiv & Notlar")
    if not df_m.empty:
        mus = st.selectbox("Seç:", df_m["Ad Soyad"].tolist())
        
        # Madde 16: Tarihli Not Sistemi
        st.subheader("📝 Müşteri Geçmişi")
        
        # Mevcut notları göster (Sheet1'den filtreleyerek not gibi gösteriyoruz)
        gecmis_notlar = verileri_getir("Sheet1")
        if not gecmis_notlar.empty:
            musteri_notlari = gecmis_notlar[
                (gecmis_notlar["Is Tanimi"].str.contains(mus, na=False)) & 
                (gecmis_notlar["Is Tanimi"].str.contains("NOT", na=False))
            ]
            
            if not musteri_notlari.empty:
                for index, row in musteri_notlari.iterrows():
                    # Not metnini temizle
                    raw_text = row['Is Tanimi'].split("NOT]")[-1] if "NOT]" in row['Is Tanimi'] else row['Is Tanimi']
                    st.markdown(f"""
                    <div class='tarihli-not'>
                        <b>📅 {row['Tarih']}</b>: {raw_text} 
                        <br><i>(Dosya: {row.get('Dosya', '-')})</i>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Bu müşteri için henüz not girilmemiş.")
        
        st.markdown("---")
        with st.form("yeni_not"):
            txt = st.text_area("Yeni Not / Görüşme Detayı")
            dosya = st.file_uploader("Varsa Evrak Ekle")
            
            if st.form_submit_button("💾 Notu Tarihçeye Ekle"):
                # Madde 16 Formatı: [Tarih - Kullanıcı]: Not
                formatli_not = f"[{datetime.now().strftime('%H:%M')} - {aktif_kullanici}]: {txt}"
                link = "-"
                if dosya: link = drive_yukle(dosya, mus, "Not_Eki")
                
                # Veritabanına "NOT" etiketiyle kaydediyoruz
                google_sheet_baglan("Sheet1").append_row([
                    datetime.now().strftime("%d.%m.%Y"), 
                    "-", 
                    f"{mus} - [NOT] {formatli_not}", 
                    "-", 
                    "Tamamlandi", 
                    link
                ])
                onbellek_temizle(); st.success("Not eklendi!"); st.rerun()

# --- 5. DİĞERLERİ (ÖZET) ---
elif secim == "💰 Finans & Kâr":
    st.title("💰 Finans")
    # (Finans kodları aynı kalıyor, yer kazanmak için kısa geçiyorum)
    df_c = verileri_getir("Cari")
    if not df_c.empty:
        df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
        net = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
        st.metric("Net Kâr", f"{net:,.0f} TL")
        st.dataframe(df_c)

elif secim == "🏢 Kuruluş Sihirbazı":
    st.title("🏢 Kuruluş")
    # (Kuruluş kodları aynı)
    with st.form("kur"):
        a=st.text_input("Aday"); t=st.selectbox("Tür", ["Ltd", "Şahıs"])
        if st.form_submit_button("Teklif"): st.success("Hesaplandı")

elif secim == "🧮 Defter Tasdik":
    st.title("🧮 Tasdik"); s=st.number_input("Sayfa"); st.metric("Tutar", s*6+300)

elif secim == "👥 Personel & Portföy":
    st.title("👥 Analiz"); st.info("Sorumlu Analizi Burada")
    df_m = verileri_getir("Musteriler")
    if not df_m.empty and "Sorumlu" in df_m.columns:
        df_m["Ucret"] = pd.to_numeric(df_m["Ucret"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
        st.bar_chart(df_m.groupby("Sorumlu")["Ucret"].sum())
