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

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir Asistanı Güvenli",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TASARIM (CSS) ---
st.markdown("""
    <style>
    .stApp {background-color: #F8F9FA; font-family: 'Helvetica', sans-serif;}
    [data-testid="stSidebar"] {background-color: #2C3E50;}
    [data-testid="stSidebar"] * {color: #ECF0F1 !important;}
    div[data-testid="stMetricValue"] {font-size: 28px; color: #2C3E50; font-weight: bold;}
    div.stContainer {background-color: #FFFFFF; padding: 20px; border-radius: 12px; border: 1px solid #E0E0E0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);}
    .stButton>button {width: 100%; border-radius: 8px; font-weight: 600;}
    button[kind="primary"] {background: linear-gradient(90deg, #2980b9 0%, #2c3e50 100%); color: white;}
    .gecikmis-kutu {padding: 15px; background-color: #ffebee; color: #c0392b; border-radius: 8px; border-left: 5px solid #c0392b; margin-bottom: 20px;}
    </style>
    """, unsafe_allow_html=True)

# --- OTURUM YÖNETİMİ (SESSION STATE) ---
if 'giris_yapildi' not in st.session_state:
    st.session_state['giris_yapildi'] = False
if 'kullanici_rolu' not in st.session_state:
    st.session_state['kullanici_rolu'] = None

# --- GİRİŞ EKRANI FONKSİYONU ---
def giris_ekrani():
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=100)
        st.title("Ofis Giriş Paneli")
        st.info("Lütfen yetkili hesap bilgilerinizle giriş yapın.")
        
        kullanici = st.text_input("Kullanıcı Adı")
        sifre = st.text_input("Şifre", type="password")
        
        if st.button("Giriş Yap", type="primary"):
            # --- ŞİFRELER BURADA ---
            if kullanici == "admin" and sifre == "1234":
                st.session_state['giris_yapildi'] = True
                st.session_state['kullanici_rolu'] = "admin"
                st.success("Yönetici girişi başarılı! Yönlendiriliyorsunuz...")
                time.sleep(1)
                st.rerun()
            elif kullanici == "personel" and sifre == "1111":
                st.session_state['giris_yapildi'] = True
                st.session_state['kullanici_rolu'] = "personel"
                st.success("Personel girişi başarılı! Yönlendiriliyorsunuz...")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Hatalı kullanıcı adı veya şifre!")

# --- EĞER GİRİŞ YAPILMADIYSA DURDUR ---
if not st.session_state['giris_yapildi']:
    giris_ekrani()
    st.stop() # Kodun geri kalanını okuma

# =========================================================
# BURADAN AŞAĞISI SADECE GİRİŞ YAPILINCA ÇALIŞIR
# =========================================================

# --- GÜVENLİK VE BAĞLANTILAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]
    API_TOKEN = st.secrets["API_TOKEN"]
    GRUP_ID = st.secrets["GRUP_ID"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    creds_dict = st.secrets["gcp_service_account"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
except:
    st.error("⚠️ Ayar Hatası: Secrets eksik.")
    st.stop()

def google_sheet_baglan(sayfa_adi="Sheet1"):
    client = gspread.authorize(creds)
    if sayfa_adi == "Sheet1": return client.open("Is_Takip_Sistemi").sheet1
    else: return client.open("Is_Takip_Sistemi").worksheet(sayfa_adi)

def drive_yukle(uploaded_file):
    try:
        service = build('drive', 'v3', credentials=creds)
        file_metadata = {'name': uploaded_file.name, 'parents': [DRIVE_FOLDER_ID]}
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
    try:
        sheet = google_sheet_baglan(sayfa)
        return pd.DataFrame(sheet.get_all_records())
    except: return pd.DataFrame()

def onbellek_temizle(): verileri_getir.clear()

# --- DİNAMİK MENÜ (ROLE GÖRE DEĞİŞİR) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    
    # KİM GİRDİ?
    rol = st.session_state['kullanici_rolu']
    if rol == "admin":
        st.success(f"Yönetici Modu 🟢")
        menu_secenekleri = ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "🏢 Kuruluş Sihirbazı", "💰 Finans Paneli"]
    else:
        st.info(f"Personel Modu 🔵")
        # Personel FİNANS ve KURULUŞ SİHİRBAZI'nı görmez
        menu_secenekleri = ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi"]
        
    secim = st.radio("MENÜ", menu_secenekleri)
    st.markdown("---")
    if st.button("Çıkış Yap 🔒"):
        st.session_state['giris_yapildi'] = False
        st.rerun()

# --- 1. DASHBOARD ---
if secim == "📊 Genel Bakış":
    st.title("📊 Yönetim Paneli")
    df = verileri_getir("Sheet1")
    if not df.empty and "Durum" in df.columns:
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Toplam İş", len(df))
            c2.metric("✅ Biten", len(df[df["Durum"]=="Tamamlandi"]))
            c3.metric("⏳ Bekleyen", len(df[df["Durum"]!="Tamamlandi"]))
            
            # FİNANSAL VERİYİ SADECE ADMİN GÖRÜR
            if rol == "admin" and "Tahsilat" in df.columns:
                bekleyen_tahsilat = len(df[df["Tahsilat"]=="Bekliyor ❌"])
                c4.metric("💰 Açık Bakiye", f"{bekleyen_tahsilat} Adet", delta_color="inverse")
            elif rol != "admin":
                 c4.metric("Yetki", "Personel")

        st.markdown("### 📈 İş Analizi")
        col_g1, col_g2 = st.columns(2)
        with col_g1: st.dataframe(df[["Tarih", "Is Tanimi", "Durum"]].tail(5), use_container_width=True, hide_index=True)
        with col_g2: st.bar_chart(df["Durum"].value_counts())

# --- 2. İŞ EKLE ---
elif secim == "➕ İş Ekle":
    st.title("📝 Yeni Görev Girişi")
    with st.form("is_formu", clear_on_submit=True):
        c1, c2 = st.columns(2)
        tarih = c1.date_input("Tarih")
        saat = c2.time_input("Saat")
        df_m = verileri_getir("Musteriler")
        isimler = df_m["Ad Soyad"].tolist() if not df_m.empty else []
        musteri = st.selectbox("Mükellef", isimler)
        is_notu = st.text_input("İş Tanımı")
        sms = st.checkbox("Bildirim Gönder")
        
        if st.form_submit_button("✅ Kaydet", type="primary"):
            sheet = google_sheet_baglan("Sheet1")
            tam = f"{musteri} - {is_notu}"
            sheet.append_row([tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), tam, "Gonderildi", "Bekliyor", "-"])
            onbellek_temizle()
            whatsapp_gonder(GRUP_ID, f"📅 *YENİ İŞ*\n👤 {musteri}\n📌 {is_notu}")
            if sms and not df_m.empty:
                satir = df_m[df_m["Ad Soyad"] == musteri]
                if not satir.empty:
                    nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                    for n in nums: whatsapp_gonder(n, f"Sayın {musteri}, işleminiz ({is_notu}) alınmıştır.")
            st.success("Kaydedildi!")

# --- 3. İŞ YÖNETİMİ ---
elif secim == "✅ İş Yönetimi":
    st.title("📋 Görev Kontrol")
    if st.button("🔄 Yenile"): onbellek_temizle(); st.rerun()
    df = verileri_getir("Sheet1")
    if not df.empty and "Durum" in df.columns:
        bekleyenler = df[df["Durum"] != "Tamamlandi"].copy()
        
        # Gecikmiş İş Kontrolü
        bugun = datetime.now()
        bekleyenler['Tarih_Format'] = pd.to_datetime(bekleyenler['Tarih'], format='%d.%m.%Y', errors='coerce')
        gecikmisler = bekleyenler[bekleyenler['Tarih_Format'] < bugun]
        
        if not gecikmisler.empty:
            st.markdown(f"""<div class="gecikmis-kutu">🚨 <b>DİKKAT!</b> Vadesi geçmiş <b>{len(gecikmisler)}</b> iş var!</div>""", unsafe_allow_html=True)

        if not bekleyenler.empty:
            st.dataframe(bekleyenler[["Tarih", "Is Tanimi", "Durum"]], use_container_width=True, hide_index=True)
            with st.container():
                c1, c2 = st.columns([3,1])
                secilen = c1.selectbox("Biten İş:", bekleyenler["Is Tanimi"].tolist())
                final_sms = c1.checkbox("Tamamlandı mesajı at")
                if c2.button("Kapat 🏁", type="primary"):
                    sheet = google_sheet_baglan("Sheet1")
                    rows = sheet.get_all_values()
                    for i, row in enumerate(rows):
                        if len(row) > 2 and row[2] == secilen:
                            sheet.update_cell(i+1, 5, "Tamamlandi")
                            if final_sms:
                                ad = secilen.split(" - ")[0]
                                df_m = verileri_getir("Musteriler")
                                satir = df_m[df_m["Ad Soyad"] == ad]
                                if not satir.empty:
                                    nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                                    for n in nums: whatsapp_gonder(n, f"Sayın {ad}, işleminiz tamamlanmıştır.")
                            onbellek_temizle(); st.success("Kapatıldı!"); st.rerun(); break
        else: st.info("Bekleyen iş yok.")

# --- 4. MÜŞTERİ ARŞİVİ ---
elif secim == "📂 Müşteri Arşivi":
    st.title("📂 Dijital Arşiv")
    df_m = verileri_getir("Musteriler")
    if not df_m.empty:
        musteri = st.selectbox("Mükellef:", df_m["Ad Soyad"].tolist())
        df = verileri_getir("Sheet1")
        ozel = df[df["Is Tanimi"].str.contains(musteri, na=False)] if not df.empty else pd.DataFrame()
        
        c1, c2 = st.columns([2, 1])
        with c1:
            if not ozel.empty:
                cols = ["Tarih", "Is Tanimi", "Durum"]
                if "Dosya" in ozel.columns: cols.append("Dosya")
                st.dataframe(ozel[cols], use_container_width=True, hide_index=True, column_config={"Dosya": st.column_config.LinkColumn("Evrak")})
        with c2:
            with st.form("up"):
                txt = st.text_area("Açıklama")
                dosya = st.file_uploader("Dosya")
                if st.form_submit_button("Kaydet", type="primary"):
                    link = "-"
                    if dosya:
                        with st.spinner("Yükleniyor..."): link = drive_yukle(dosya)
                    sheet = google_sheet_baglan("Sheet1")
                    sheet.append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{musteri} - [NOT] {txt}", "-", "Tamamlandi", link])
                    onbellek_temizle(); st.success("Kaydedildi!"); st.rerun()

# --- 5. KURULUŞ SİHİRBAZI (SADECE ADMIN) ---
elif secim == "🏢 Kuruluş Sihirbazı":
    st.title("🏢 Kuruluş Formu (Admin)")
    with st.container():
        c1, c2 = st.columns(2)
        aday = c1.text_input("Görüşülen Kişi")
        tel = c2.text_input("Telefon")
    if aday:
        with st.form("kurulus"):
            with st.expander("Detaylar", expanded=True):
                tur = st.radio("Tür", ["Şahıs", "Ltd", "A.Ş."])
                # Ücret bilgisi personel için gizli, admin için açık
                ucret = st.text_input("Aylık Ücret (Gizli Bilgi)")
            if st.form_submit_button("Kaydet", type="primary"):
                sheet = google_sheet_baglan("Sheet1")
                sheet.append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{aday} - [AÇILIŞ]", "-", "Tamamlandi", "-"])
                onbellek_temizle()
                whatsapp_gonder(GRUP_ID, f"🆕 *YÖNETİCİ GÖRÜŞMESİ*\nKişi: {aday}\nÜcret: {ucret}")
                st.success("Kaydedildi.")

# --- 6. FİNANS PANELİ (SADECE ADMIN) ---
elif secim == "💰 Finans Paneli":
    st.title("💰 Finansal Yönetim (Admin)")
    df = verileri_getir("Cari")
    
    tab1, tab2, tab3 = st.tabs(["Özet", "İşlem", "Yıllık Tahakkuk"])
    with tab1:
        if not df.empty:
            df["Tutar"] = pd.to_numeric(df["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
            alacak = df[df["Islem_Turu"].str.contains("Borç", na=False)]["Tutar"].sum()
            tahsilat = df[df["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum()
            bakiye = alacak - tahsilat
            c1, c2, c3 = st.columns(3)
            c1.metric("Ciro", f"{alacak:,.0f} TL")
            c2.metric("Kasa", f"{tahsilat:,.0f} TL")
            c3.metric("Alacak", f"{bakiye:,.0f} TL", delta_color="inverse")
    with tab2:
        with st.form("finans"):
            c1, c2 = st.columns(2)
            trh = c1.date_input("Tarih")
            df_m = verileri_getir("Musteriler")
            mus = c2.selectbox("Müşteri", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
            tur = st.radio("İşlem", ["Borç", "Tahsilat"], horizontal=True)
            ttr = st.number_input("Tutar")
            if st.form_submit_button("Kaydet", type="primary"):
                sheet = google_sheet_baglan("Cari")
                sheet.append_row([trh.strftime("%d.%m.%Y"), mus, tur, ttr, "-"])
                onbellek_temizle(); st.success("Kaydedildi.")
    with tab3:
        st.info("Yıllık Toplu Tahakkuk")
        with st.form("tahakkuk"):
            mus_t = st.selectbox("Müşteri", df_m["Ad Soyad"].tolist() if not df_m.empty else [], key="tah_mus")
            tut_t = st.number_input("Aylık Tutar")
            if st.form_submit_button("İşle", type="primary"):
                veriler = []
                for i in range(12):
                    veriler.append([f"15.{i+1:02d}.2025", mus_t, "Borç", tut_t, "Yıllık Tahakkuk"])
                sheet = google_sheet_baglan("Cari")
                sheet.append_rows(veriler)
                onbellek_temizle(); st.success("İşlendi!")
