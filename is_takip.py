import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import requests
import pandas as pd
import re
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir Asistanı Pro",
    page_icon="⚖️",
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
    [data-testid="stForm"], div.stContainer {
        background-color: #FFFFFF; padding: 20px; border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #E0E0E0;
    }
    .stButton>button {width: 100%; border-radius: 8px; height: 3em; font-weight: 600; border: none;}
    button[kind="primary"] {background: linear-gradient(90deg, #1abc9c 0%, #16a085 100%); color: white;}
    thead tr th:first-child {display:none} tbody th {display:none}
    /* Gecikmiş İş Uyarısı İçin Stil */
    .gecikmis-kutu {
        padding: 15px; background-color: #ffcccc; color: #990000;
        border-radius: 10px; border-left: 5px solid #cc0000; margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- GÜVENLİK ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]
    API_TOKEN = st.secrets["API_TOKEN"]
    GRUP_ID = st.secrets["GRUP_ID"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    creds_dict = st.secrets["gcp_service_account"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
except:
    st.error("⚠️ Ayar Hatası: Secrets şifreleri eksik.")
    st.stop()

# --- FONKSİYONLAR ---
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
        elif len(sadece_rakamlar) == 12 and sadece_rakamlar.startswith("90"): temiz_numaralar.append(sadece_rakamlar)
    return temiz_numaralar

# --- YENİ: CACHE (ÖNBELLEK) SİSTEMİ ---
# Bu kod, veriyi çektikten sonra 60 saniye boyunca hafızada tutar.
# Sayfayı her yenilediğinde Google'a gitmez, hafızadan getirir. HIZ DEMEKTİR!
@st.cache_data(ttl=60)
def verileri_getir(sayfa="Ana"):
    try:
        sheet = google_sheet_baglan(sayfa)
        return pd.DataFrame(sheet.get_all_records())
    except:
        return pd.DataFrame()

# Önbelleği temizlemek için bir fonksiyon (Kayıt ekleyince çalışacak)
def onbellek_temizle():
    verileri_getir.clear()

# --- MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    st.markdown("### 🏛️ Müşavir Panel")
    st.markdown("---")
    secim = st.radio("MENÜ", ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "🏢 Kuruluş Sihirbazı", "💰 Finans Paneli"])
    st.markdown("---")
    st.caption("v.Turbo | Cache Aktif ⚡")

# --- 1. DASHBOARD ---
if secim == "📊 Genel Bakış":
    st.title("📊 Yönetim Paneli")
    df = verileri_getir("Sheet1")
    
    if not df.empty and "Durum" in df.columns:
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Toplam İş", len(df))
            c2.metric("✅ Tamamlanan", len(df[df["Durum"]=="Tamamlandi"]))
            c3.metric("⏳ Bekleyen", len(df[df["Durum"]!="Tamamlandi"]))
            
            bekleyen_tahsilat = 0
            if "Tahsilat" in df.columns:
                bekleyen_tahsilat = len(df[df["Tahsilat"]=="Bekliyor ❌"])
            c4.metric("💰 Açık Bakiye", f"{bekleyen_tahsilat} Adet", delta_color="inverse")

        # Grafik Ekleme (Manus'un 2. Tavsiyesi - Basit Versiyon)
        st.markdown("### 📈 İş Durum Analizi")
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.dataframe(df[["Tarih", "Is Tanimi", "Durum"]].tail(5), use_container_width=True, hide_index=True)
        with col_g2:
            st.bar_chart(df["Durum"].value_counts())

# --- 2. İŞ EKLE ---
elif secim == "➕ İş Ekle":
    st.title("📝 Yeni Görev Girişi")
    with st.form("is_formu", clear_on_submit=True):
        col1, col2 = st.columns(2)
        tarih = col1.date_input("Tarih")
        saat = col2.time_input("Saat")
        
        df_m = verileri_getir("Musteriler")
        isimler = df_m["Ad Soyad"].tolist() if not df_m.empty else []
        musteri = st.selectbox("Mükellef", isimler)
        is_notu = st.text_input("İş Tanımı", placeholder="Örn: KDV Beyannamesi")
        sms = st.checkbox("📨 Mükellefe bilgilendirme gitsin mi?")
        
        if st.form_submit_button("✅ Görevi Kaydet", type="primary"):
            sheet = google_sheet_baglan("Sheet1")
            tam_ad = f"{musteri} - {is_notu}"
            sheet.append_row([tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), tam_ad, "Gonderildi", "Bekliyor", "-"])
            
            # Kayıt ekleyince cache'i temizle ki yeni veri hemen görünsün
            onbellek_temizle()
            
            whatsapp_gonder(GRUP_ID, f"📅 *YENİ İŞ*\n👤 {musteri}\n📌 {is_notu}")
            if sms and not df_m.empty:
                satir = df_m[df_m["Ad Soyad"] == musteri]
                if not satir.empty:
                    nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                    for n in nums: whatsapp_gonder(n, f"Sayın {musteri}, işleminiz ({is_notu}) alınmıştır.")
            st.success("Kayıt Başarılı!")

# --- 3. İŞ YÖNETİMİ (GECİKMİŞ İŞ UYARISI EKLENDİ) ---
elif secim == "✅ İş Yönetimi":
    st.title("📋 Görev Kontrol Merkezi")
    
    if st.button("🔄 Yenile (Cache Temizle)"): 
        onbellek_temizle()
        st.rerun()
    
    df = verileri_getir("Sheet1")
    if not df.empty and "Durum" in df.columns:
        bekleyenler = df[df["Durum"] != "Tamamlandi"].copy()
        
        # --- MANUS'UN 3. TAVSİYESİ: GECİKMİŞ İŞLER ---
        # Tarih formatını datetime'a çevirip kontrol ediyoruz
        bugun = datetime.now()
        bekleyenler['Tarih_Format'] = pd.to_datetime(bekleyenler['Tarih'], format='%d.%m.%Y', errors='coerce')
        gecikmisler = bekleyenler[bekleyenler['Tarih_Format'] < bugun]
        
        if not gecikmisler.empty:
            st.markdown(f"""
            <div class="gecikmis-kutu">
                🚨 <b>DİKKAT!</b> Vadesi geçmiş <b>{len(gecikmisler)}</b> adet işiniz var! Lütfen bunları önceliklendirin.
            </div>
            """, unsafe_allow_html=True)
            st.dataframe(gecikmisler[["Tarih", "Is Tanimi", "Durum"]], use_container_width=True, hide_index=True)
            st.divider()

        if not bekleyenler.empty:
            st.markdown("### ⏳ Bekleyen Tüm İşler")
            st.dataframe(bekleyenler[["Tarih", "Is Tanimi", "Durum"]], use_container_width=True, hide_index=True)
            
            st.markdown("### 🏁 İş Bitirme")
            with st.container():
                c1, c2 = st.columns([3,1])
                secilen = c1.selectbox("Tamamlanan İşi Seç:", bekleyenler["Is Tanimi"].tolist())
                final_sms = c1.checkbox("Müşteriye 'Tamamlandı' mesajı at")
                
                if c2.button("İşi Kapat 🏁", type="primary"):
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
                            onbellek_temizle() # Veri değişti, hafızayı tazele
                            st.success("İşlem kapatıldı!")
                            st.rerun()
                            break
        else:
            st.info("Harika! Bekleyen hiç işiniz yok.")

# --- 4. MÜŞTERİ ARŞİVİ ---
elif secim == "📂 Müşteri Arşivi":
    st.title("📂 Dijital Müşteri Defteri")
    df_m = verileri_getir("Musteriler")
    if not df_m.empty:
        musteri = st.selectbox("Mükellef Seçiniz:", df_m["Ad Soyad"].tolist())
        df = verileri_getir("Sheet1")
        if not df.empty:
            ozel_veri = df[df["Is Tanimi"].str.contains(musteri, na=False)]
            cols = ["Tarih", "Is Tanimi", "Durum"]
            if "Dosya" in ozel_veri.columns: cols.append("Dosya")
            
            c1, c2 = st.columns([2, 1])
            with c1:
                st.dataframe(ozel_veri[cols], use_container_width=True, hide_index=True, column_config={"Dosya": st.column_config.LinkColumn("Evrak")})
            with c2:
                with st.form("dosya_up"):
                    not_txt = st.text_area("Açıklama")
                    yuklenen = st.file_uploader("Dosya")
                    if st.form_submit_button("Kaydet", type="primary"):
                        link = "-"
                        if yuklenen:
                            with st.spinner("Yükleniyor..."): link = drive_yukle(yuklenen)
                        sheet = google_sheet_baglan("Sheet1")
                        sheet.append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{musteri} - [NOT] {not_txt}", "-", "Tamamlandi", link])
                        onbellek_temizle()
                        st.success("Kaydedildi!")
                        st.rerun()

# --- 5. KURULUŞ SİHİRBAZI ---
elif secim == "🏢 Kuruluş Sihirbazı":
    st.title("🏢 Şirket Kuruluş Sihirbazı")
    with st.container():
        col_ad, col_tel = st.columns(2)
        aday_musteri = col_ad.text_input("Görüşülen Kişi")
        aday_tel = col_tel.text_input("Telefon")

    if aday_musteri:
        with st.form("kurulus_form"):
            with st.expander("1. Şirket Yapısı", expanded=True):
                c1, c2 = st.columns(2)
                sirket_turu = c1.radio("Tür", ["Şahıs", "Ltd", "A.Ş."])
                vergi_usulu = c2.radio("Usul", ["Gerçek", "Basit"])
            with st.expander("2. Finansal Detaylar", expanded=True):
                c3, c4 = st.columns(2)
                muhasebe_ucreti = c3.text_input("Aylık Ücret")
                acilis_bedeli = c4.text_input("Açılış Bedeli")
            
            if st.form_submit_button("Görüşmeyi Kaydet", type="primary"):
                rapor = f"GÖRÜŞME: {aday_musteri} ({sirket_turu})\nÜcret: {muhasebe_ucreti}"
                sheet = google_sheet_baglan("Sheet1")
                sheet.append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{aday_musteri} - [AÇILIŞ]", "-", "Tamamlandi", "-"])
                onbellek_temizle()
                whatsapp_gonder(GRUP_ID, f"🆕 *YENİ GÖRÜŞME*\n{rapor}")
                st.success("Kaydedildi.")

# --- 6. FİNANS PANELİ ---
elif secim == "💰 Finans Paneli":
    st.title("💰 Finansal Durum")
    df = verileri_getir("Cari")
    
    tab1, tab2 = st.tabs(["Özet", "İşlem Ekle"])
    
    with tab1:
        if not df.empty:
            df["Tutar"] = pd.to_numeric(df["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
            alacak = df[df["Islem_Turu"].str.contains("Borç", na=False)]["Tutar"].sum()
            tahsilat = df[df["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum()
            bakiye = alacak - tahsilat
            c1, c2, c3 = st.columns(3)
            c1.metric("Toplam Ciro", f"{alacak:,.0f} TL")
            c2.metric("Tahsilat", f"{tahsilat:,.0f} TL")
            c3.metric("Açık Hesap", f"{bakiye:,.0f} TL", delta_color="inverse")
    
    with tab2:
        with st.form("finans_ekle"):
            c1, c2 = st.columns(2)
            trh = c1.date_input("Tarih")
            
            df_m = verileri_getir("Musteriler")
            isimler = df_m["Ad Soyad"].tolist() if not df_m.empty else []
            mus = c2.selectbox("Müşteri", isimler)
            
            tur = st.radio("İşlem", ["Hizmet Bedeli (Borç)", "Tahsilat (Ödeme)"], horizontal=True)
            ttr = st.number_input("Tutar", step=100.0)
            ack = st.text_input("Açıklama")
            
            if st.form_submit_button("Kaydet", type="primary"):
                sheet = google_sheet_baglan("Cari")
                sheet.append_row([trh.strftime("%d.%m.%Y"), mus, tur, ttr, ack])
                onbellek_temizle()
                st.success("Finansal kayıt eklendi.")
