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
import io
from streamlit_option_menu import option_menu

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir Asistanı Ultimate",
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
    .etiket {background-color: #E3F2FD; color: #1565C0; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; margin: 2px;}
    .risk-yuksek {background-color: #ffebee; color: #c62828; padding: 10px; border-radius: 8px; border-left: 5px solid #c62828; margin-bottom: 10px;}
    .risk-orta {background-color: #fff3e0; color: #ef6c00; padding: 10px; border-radius: 8px; border-left: 5px solid #ef6c00; margin-bottom: 10px;}
    .sifre-kutu {background-color: #333; color: #0f0; font-family: monospace; padding: 10px; border-radius: 5px; letter-spacing: 1px;}
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
RESMI_TATILLER = ["01.01", "23.04", "01.05", "19.05", "15.07", "30.08", "29.10"]
MESAJ_SABLONLARI = {
    "Özel Mesaj Yaz": "",
    "KDV Ödeme Hatırlatma": "Sayın {isim}, {ay} dönemi KDV beyannameniz onaylanmıştır. Ödemenizi vadesinde yapmanızı rica ederiz.",
    "E-İmza Uyarısı": "Sayın {isim}, E-İmza süreniz {tarih} tarihinde dolmaktadır. Yenileme işlemlerini acilen başlatmanızı rica ederiz.",
    "Borç Hatırlatma": "Sayın {isim}, ofisimize ait cari bakiyeniz {borc} TL'dir.",
}

# --- SESSION ---
if 'hizli_not' not in st.session_state: st.session_state['hizli_not'] = ""
if 'son_islem_yedek' not in st.session_state: st.session_state['son_islem_yedek'] = None
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

# --- 19. LOG KAYDI FONKSİYONU ---
def log_kayit(kullanici, islem, detay):
    try:
        tarih_saat = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        google_sheet_baglan("Logs").append_row([tarih_saat, kullanici, islem, detay])
    except: pass

def whatsapp_gonder(chat_id, mesaj):
    if st.session_state['sessiz_mod']: return False
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
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.markdown("<h3 style='margin-top:0;'>MÜŞAVİR PRO</h3>", unsafe_allow_html=True)
    
    df_m = verileri_getir("Musteriler")
    p_list = ["Admin"]
    if not df_m.empty and "Sorumlu" in df_m.columns:
        p_list += [p for p in df_m["Sorumlu"].unique().tolist() if str(p) not in ["nan", ""]]
    aktif = st.selectbox("👤 Aktif Kullanıcı", list(set(p_list)))
    
    st.markdown("---")
    
    secim = option_menu(
        menu_title=None,
        options=["Genel Bakış", "Araçlar & Hesap", "İş Ekle", "İş Yönetimi", "Mesaj Merkezi", "Arşiv & Şifre", "Finans", "Ayarlar"],
        icons=["house", "calculator", "plus-circle", "kanban", "chat-dots", "folder2-open", "cash-coin", "gear"],
        menu_icon="cast", default_index=0,
        styles={"container": {"padding": "0!important", "background-color": "#ffffff"}, "nav-link": {"font-size": "14px"}}
    )
    
    st.session_state['sessiz_mod'] = st.toggle("🔕 Sessiz Mod", value=st.session_state['sessiz_mod'])
    st.session_state['hizli_not'] = st.text_area("", value=st.session_state['hizli_not'], height=80, placeholder="Hızlı Not...")

# --- 1. GENEL BAKIŞ (KÂRLILIK VE E-İMZA EKLENDİ) ---
if secim == "Genel Bakış":
    st.title("📊 Yönetim Kokpiti")
    df = verileri_getir("Sheet1")
    
    # 2. E-İMZA KONTROLÜ
    if not df_m.empty and "E_Imza_Bitis" in df_m.columns:
        bugun = datetime.now()
        riskli_imzalar = []
        for i, row in df_m.iterrows():
            try:
                bitis = pd.to_datetime(row["E_Imza_Bitis"], format="%d.%m.%Y")
                kalansure = (bitis - bugun).days
                if 0 < kalansure <= 15:
                    riskli_imzalar.append(f"⚠️ {row['Ad Soyad']} (Kalan: {kalansure} gün)")
            except: pass
        
        if riskli_imzalar:
            st.error(f"🚨 DİKKAT! E-İmza Süresi Biten {len(riskli_imzalar)} Müşteri Var!")
            st.markdown("\n".join([f"- {k}" for k in riskli_imzalar]))

    # 10. KÂRLILIK ANALİZİ
    with st.expander("📊 Müşteri Kârlılık Analizi (Gelir / İş Yükü)", expanded=True):
        if not df_m.empty and not df.empty:
            df_m["Ucret"] = pd.to_numeric(df_m["Ucret"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
            is_sayilari = df["Is Tanimi"].apply(lambda x: x.split(" - ")[0] if " - " in x else x).value_counts().reset_index()
            is_sayilari.columns = ["Ad Soyad", "Is_Yuku"]
            
            # Merge
            analiz = pd.merge(df_m, is_sayilari, on="Ad Soyad", how="left").fillna(0)
            analiz["Skor"] = analiz["Ucret"] / (analiz["Is_Yuku"] + 1) # Basit Skor
            analiz = analiz.sort_values("Skor", ascending=True).head(5) # En kötü 5
            
            st.write("📉 **En Düşük Kârlılık (Çok İş / Az Para)**")
            st.dataframe(analiz[["Ad Soyad", "Ucret", "Is_Yuku"]], use_container_width=True)

    if not df.empty and "Durum" in df.columns:
        c1, c2, c3 = st.columns(3)
        c1.metric("Bekleyen", len(df[df["Durum"]!="Tamamlandi"]))
        c2.metric("Tamamlanan", len(df[df["Durum"]=="Tamamlandi"]))
        c3.metric("Toplam İş", len(df))

# --- 5 & 6. ARAÇLAR (MAAŞ & KİRA) ---
elif secim == "Araçlar & Hesap":
    st.title("🧮 Hesaplama Araçları")
    t1, t2 = st.tabs(["💵 Maaş Hesaplama", "🏠 Kira Artışı"])
    
    with t1:
        st.subheader("Netten Brüte Basit Hesap")
        net_maas = st.number_input("Net Maaş (TL)", value=25000)
        if st.button("Hesapla"):
            # Örnek katsayılar (2025 tahmini ortalama yük)
            brut = net_maas * 1.45
            isveren_maliyeti = brut * 1.225
            st.success(f"Tahmini Brüt: {brut:,.2f} TL")
            st.info(f"İşverene Toplam Maliyet: {isveren_maliyeti:,.2f} TL")
            st.caption("*Not: Rakamlar ortalama vergi dilimine göre tahmindir.")
            
    with t2:
        st.subheader("🏠 Kira Artış Hesaplayıcı")
        mevcut_kira = st.number_input("Mevcut Kira Bedeli", value=10000)
        tufe_orani = st.number_input("TÜFE (Artış) Oranı %", value=65.0)
        if st.button("Kira Hesapla"):
            yeni_kira = mevcut_kira * (1 + tufe_orani/100)
            fark = yeni_kira - mevcut_kira
            st.success(f"Yeni Kira: {yeni_kira:,.2f} TL")
            st.warning(f"Artış Miktarı: {fark:,.2f} TL")
            
            yazi = f"Sayın Kiracı, kontrat gereği {tufe_orani}% oranında artışla yeni kiranız {yeni_kira:,.0f} TL olmuştur."
            st.text_area("Kopyalanabilir Mesaj:", value=yazi)

# --- İŞ EKLE ---
elif secim == "İş Ekle":
    st.title("📝 İş Girişi")
    with st.form("is_ekle"):
        c1, c2 = st.columns(2); t = c1.date_input("Tarih"); s = c2.time_input("Saat")
        mus = st.selectbox("Mükellef", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
        notu = st.text_input("Açıklama", "KDV Beyannamesi")
        p = st.selectbox("Sorumlu", p_list)
        if st.form_submit_button("Kaydet"):
            google_sheet_baglan("Sheet1").append_row([t.strftime("%d.%m.%Y"), s.strftime("%H:%M"), f"{mus} - {notu}", "Gonderildi", "Bekliyor", "-", p])
            log_kayit(aktif, "İş Eklendi", f"{mus} - {notu}") # 19. LOG
            st.success("Kaydedildi!")

# --- İŞ YÖNETİMİ ---
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
                    google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Tamamlandi")
                    log_kayit(aktif, "İş Bitirildi", secilen) # 19. LOG
                    st.success("Bitti!"); st.rerun()

# --- MESAJ MERKEZİ ---
elif secim == "Mesaj Merkezi":
    st.title("💬 Mesaj")
    secilen = st.selectbox("Müşteri", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
    sablon = st.selectbox("Şablon", list(MESAJ_SABLONLARI.keys()))
    msg = st.text_area("İçerik", value=MESAJ_SABLONLARI[sablon])
    if st.button("Gönder"):
        satir = df_m[df_m["Ad Soyad"] == secilen]
        if not satir.empty:
            tel = numaralari_ayikla(satir.iloc[0]["Telefon"])
            for t in tel: whatsapp_gonder(t, msg.replace("{isim}", secilen))
            log_kayit(aktif, "Mesaj Gönderildi", f"{secilen} - {sablon}") # 19. LOG
            st.success("Gönderildi!")

# --- 1. ŞİFRE KASASI & ARŞİV ---
elif secim == "Arşiv & Şifre":
    st.title("📂 Arşiv ve Şifreler")
    t1, t2 = st.tabs(["📂 Evraklar", "🔑 Şifre Kasası"])
    
    with t1:
        mus = st.selectbox("Müşteri:", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
        up = st.file_uploader("Dosya")
        if st.button("Yükle") and up:
            l = drive_yukle(up, mus, "Evrak")
            google_sheet_baglan("Sheet1").append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{mus} - [EVRAK]", "-", "Tamamlandi", l, aktif])
            st.success("Yüklendi")
            
    with t2:
        st.info("🔒 Müşteri şifrelerini güvenli not alın.")
        
        # Şifre Ekleme
        with st.form("sifre_ekle"):
            c1, c2 = st.columns(2)
            m_sec = c1.selectbox("Müşteri Seç", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
            platform = c2.selectbox("Platform", ["İnteraktif VD", "SGK", "E-Devlet", "E-Fatura", "Diğer"])
            k_adi = c1.text_input("Kullanıcı Adı / TC")
            sifre = c2.text_input("Şifre")
            
            if st.form_submit_button("💾 Kasaya Kaydet"):
                google_sheet_baglan("Sifreler").append_row([m_sec, platform, k_adi, sifre])
                log_kayit(aktif, "Şifre Eklendi", f"{m_sec} - {platform}")
                st.success("Şifre eklendi!")
        
        st.divider()
        
        # Şifre Görüntüleme
        sifre_ara = st.selectbox("Şifresini Gör:", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
        if sifre_ara:
            df_sifre = verileri_getir("Sifreler")
            if not df_sifre.empty:
                bulunanlar = df_sifre[df_sifre["Musteri"] == sifre_ara]
                if not bulunanlar.empty:
                    for i, row in bulunanlar.iterrows():
                        st.markdown(f"**{row['Platform']}**: `{row['Kullanici_Adi']}` / <span class='sifre-kutu'>{row['Sifre']}</span>", unsafe_allow_html=True)
                else: st.warning("Kayıtlı şifre yok.")

# --- FİNANS ---
elif secim == "Finans":
    st.title("💰 Finans")
    df_c = verileri_getir("Cari")
    if not df_c.empty: st.dataframe(df_c, use_container_width=True)

# --- AYARLAR ---
elif secim == "Ayarlar":
    st.title("⚙️ Ayarlar")
    
    # 19. LOG KAYITLARI GÖRÜNTÜLEME
    if st.checkbox("🕵️ Güvenlik Loglarını Göster"):
        df_log = verileri_getir("Logs")
        st.dataframe(df_log.tail(20), use_container_width=True)
        
    if st.button("📦 Yedek Al"):
        st.download_button("İndir", excel_yedek_olustur(verileri_getir("Sheet1"), df_m, verileri_getir("Cari")), "Yedek.xlsx")
