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
    page_title="Müşavir Asistanı Smart",
    page_icon="🧠",
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
    
    /* Etiketler */
    .etiket {
        background-color: #e0f7fa; color: #006064; padding: 2px 8px; 
        border-radius: 12px; font-size: 12px; margin-right: 5px; border: 1px solid #b2ebf2;
    }
    /* VIP İkonu */
    .vip-badge {color: #f1c40f; font-weight: bold;}
    
    /* Tatil Uyarısı */
    .tatil-uyari {
        background-color: #ffebee; color: #c62828; padding: 10px; 
        border-radius: 8px; margin-bottom: 10px; border-left: 5px solid #c62828;
    }
    
    /* Sahipsiz İş */
    .sahipsiz {border-left: 5px solid #ff9800; background-color: #fff3e0; padding: 10px; margin-bottom: 5px;}
    </style>
    """, unsafe_allow_html=True)

# --- RESMİ TATİLLER (Örnek Liste) ---
RESMI_TATILLER = ["01.01", "23.04", "01.05", "19.05", "15.07", "30.08", "29.10"]

# --- SESSION STATE ---
if 'hizli_not' not in st.session_state: st.session_state['hizli_not'] = ""
if 'son_islem_yedek' not in st.session_state: st.session_state['son_islem_yedek'] = None # Undo için
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
    # Madde 23: Sessiz Mod Kontrolü
    if st.session_state['sessiz_mod']:
        return False # Gönderme
    
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

# --- YAN MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=70)
    
    # Kullanıcı Seçimi
    df_m = verileri_getir("Musteriler")
    personel_listesi = ["Admin"]
    if not df_m.empty and "Sorumlu" in df_m.columns:
        personel_listesi += [p for p in df_m["Sorumlu"].unique().tolist() if str(p) not in ["nan", ""]]
    aktif_kullanici = st.selectbox("👤 Kullanıcı:", list(set(personel_listesi)))

    # Madde 23: Sessiz Mod Toggle
    st.session_state['sessiz_mod'] = st.toggle("🔕 Sessiz Mod (Bildirim Yok)", value=st.session_state['sessiz_mod'])
    if st.session_state['sessiz_mod']:
        st.caption("⚠️ WhatsApp mesajları gönderilmeyecek.")

    # Madde 21: Sihirli Arama (Basit Versiyon)
    arama_nav = st.text_input("🔍 Hızlı Git (Ctrl+K)", placeholder="Müşteri veya İş Ara...")
    
    st.markdown("---")
    menu = ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "💰 Finans & Kâr", "🏢 Kuruluş Sihirbazı", "🧮 Defter Tasdik", "👥 Personel & Portföy"]
    secim = st.radio("MENÜ", menu)
    st.markdown("---")
    
    # Hızlı Not
    st.session_state['hizli_not'] = st.text_area("📝 Notlar:", value=st.session_state['hizli_not'], height=100)

# --- NAVİGASYON MANTIĞI ---
# Eğer aramaya bir şey yazıldıysa ilgili sayfayı bulmaya çalışırız (Basit Simülasyon)
if arama_nav:
    if "ekle" in arama_nav.lower(): secim = "➕ İş Ekle"
    elif "finans" in arama_nav.lower(): secim = "💰 Finans & Kâr"
    elif "arşiv" in arama_nav.lower(): secim = "📂 Müşteri Arşivi"

# --- 1. DASHBOARD ---
if secim == "📊 Genel Bakış":
    st.title("📊 Yönetim Kokpiti")
    df = verileri_getir("Sheet1")
    
    # Madde 18: Hızlı İstatistikler (Badge Style)
    if not df.empty and "Durum" in df.columns:
        bugun_biten = len(df[(df["Durum"]=="Tamamlandi") & (df["Tarih"] == datetime.now().strftime("%d.%m.%Y"))])
        st.markdown(f"**Günlük Skor:** 🎯 {bugun_biten} İş Tamamlandı")

    if not df.empty:
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

        # Madde 29: Boşta Kalan İşler (Sahipsiz)
        if "Personel" in df.columns:
            sahipsiz = df[(df["Personel"] == "") & (df["Durum"] != "Tamamlandi")]
            if not sahipsiz.empty:
                st.markdown(f"<div class='sahipsiz'>⚠️ <b>Dikkat:</b> {len(sahipsiz)} adet işe personel atanmamış!</div>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1: st.dataframe(df.tail(5), use_container_width=True, hide_index=True)
        with col2: st.bar_chart(df["Durum"].value_counts())

# --- 2. İŞ EKLE (AKILLI ÖZELLİKLER) ---
elif secim == "➕ İş Ekle":
    st.title("📝 Akıllı İş Girişi")
    
    with st.container():
        with st.form("is_ekle"):
            c1, c2 = st.columns(2)
            tarih = c1.date_input("Tarih")
            
            # Madde 27: Tatil Uyarısı
            tarih_str_kisa = tarih.strftime("%d.%m")
            if tarih_str_kisa in RESMI_TATILLER or tarih.weekday() == 6: # 6 = Pazar
                st.markdown(f"<div class='tatil-uyari'>⚠️ <b>Uyarı:</b> Seçtiğiniz tarih ({tarih.strftime('%d.%m.%Y')}) resmi tatil veya Pazar günüdür.</div>", unsafe_allow_html=True)
            
            saat = c2.time_input("Saat")
            
            # Müşteri Listesi (Madde 28: VIP Gösterimi)
            musteri_options = []
            if not df_m.empty:
                # VIP Hesapla (En yüksek %20)
                df_m["Ucret"] = pd.to_numeric(df_m["Ucret"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
                limit = df_m["Ucret"].quantile(0.8)
                
                for i, row in df_m.iterrows():
                    ad = row["Ad Soyad"]
                    if row["Ucret"] >= limit and limit > 0: ad = f"⭐ {ad} (VIP)"
                    musteri_options.append(ad)
            
            mus_raw = st.selectbox("Mükellef", musteri_options)
            mus = mus_raw.replace("⭐ ", "").replace(" (VIP)", "") # Temiz isim
            
            # Madde 22 & 26: Akıllı Personel Önerisi & İş Yükü
            # Personel listesini hazırla ve yanına iş yükünü yaz
            personel_options_yuklu = [""]
            varsayilan_index = 0
            
            df_isler = verileri_getir("Sheet1")
            
            # Seçilen müşterinin varsayılan sorumlusunu bul
            varsayilan_sorumlu = ""
            if not df_m.empty and "Sorumlu" in df_m.columns:
                bul = df_m[df_m["Ad Soyad"] == mus]
                if not bul.empty: varsayilan_sorumlu = bul.iloc[0]["Sorumlu"]

            if not df_isler.empty and "Personel" in df_isler.columns and "Durum" in df_isler.columns:
                is_yuku = df_isler[df_isler["Durum"] != "Tamamlandi"]["Personel"].value_counts()
                
                for p in personel_listesi:
                    yuk = is_yuku.get(p, 0)
                    etiket = f"{p} (Aktif: {yuk})"
                    personel_options_yuklu.append(etiket)
                    if p == varsayilan_sorumlu: varsayilan_index = len(personel_options_yuklu) - 1
            else:
                 personel_options_yuklu += personel_listesi

            secilen_personel_raw = st.selectbox("Sorumlu Personel", personel_options_yuklu, index=varsayilan_index, help="Otomatik olarak müşterinin sorumlusu seçilir.")
            secilen_personel = secilen_personel_raw.split(" (")[0] if "(" in secilen_personel_raw else secilen_personel_raw
            
            # İş Tanımı
            is_tipi = st.selectbox("İş Şablonu", ["KDV Beyannamesi", "Muhtasar", "SGK Giriş", "Genel", "Diğer"])
            notu = is_tipi if is_tipi != "Diğer" else st.text_input("Açıklama")
            
            sms = st.checkbox("SMS Gönder")
            
            if st.form_submit_button("✅ Kaydet", type="primary"):
                # Personel sütununu da ekliyoruz (Sheet1 G Sütunu)
                google_sheet_baglan("Sheet1").append_row([
                    tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), 
                    f"{mus} - {notu}", "Gonderildi", "Bekliyor", "-", secilen_personel
                ])
                onbellek_temizle()
                whatsapp_gonder(GRUP_ID, f"🆕 *İŞ*: {mus} - {notu} ({secilen_personel})")
                
                if sms and not df_m.empty:
                    satir = df_m[df_m["Ad Soyad"] == mus]
                    if not satir.empty:
                        nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                        for n in nums: whatsapp_gonder(n, f"Sayın {mus}, işleminiz ({notu}) alınmıştır.")
                
                st.success("Kaydedildi!")

# --- 3. İŞ YÖNETİMİ (GERİ AL & ETİKETLER) ---
elif secim == "✅ İş Yönetimi":
    st.title("📋 İş Takip")
    if st.button("🔄 Yenile"): onbellek_temizle(); st.rerun()
    
    df = verileri_getir("Sheet1")
    if not df.empty:
        # Madde 24: Etiket Filtresi
        filtre_bana_ait = st.checkbox(f"Sadece Bana ({aktif_kullanici}) Ait Olanlar")
        
        df_goster = df.copy()
        if filtre_bana_ait and aktif_kullanici != "Admin" and "Personel" in df_goster.columns:
            df_goster = df_goster[df_goster["Personel"] == aktif_kullanici]
        
        # Tabloyu Göster
        st.dataframe(df_goster[["Tarih", "Is Tanimi", "Durum", "Personel"]], use_container_width=True, hide_index=True)
        
        # Madde 25 & 30: İş Bitirme, Kutlama ve Geri Al
        st.markdown("---")
        with st.container():
            col_b1, col_b2 = st.columns([3,1])
            
            bekleyenler = df[df["Durum"] != "Tamamlandi"]["Is Tanimi"].tolist()
            secilen = col_b1.selectbox("İş Bitir:", bekleyenler)
            
            if col_b2.button("🏁 Bitir"):
                # Yedek Al (Undo için)
                st.session_state['son_islem_yedek'] = secilen
                
                rows = google_sheet_baglan("Sheet1").get_all_values()
                for i, r in enumerate(rows):
                    if len(r) > 2 and r[2] == secilen:
                        google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Tamamlandi")
                        onbellek_temizle()
                        st.balloons() # Madde 30: Kutlama
                        st.success("İş Tamamlandı!")
                        time.sleep(1)
                        st.rerun()
                        break
            
            # Madde 25: Geri Al Butonu (Eğer yedek varsa göster)
            if st.session_state['son_islem_yedek']:
                st.warning(f"Son İşlem: {st.session_state['son_islem_yedek']} tamamlandı.")
                if st.button("↩️ İşlemi Geri Al (Yanlışlıkla Oldu)"):
                    rows = google_sheet_baglan("Sheet1").get_all_values()
                    for i, r in enumerate(rows):
                        if len(r) > 2 and r[2] == st.session_state['son_islem_yedek']:
                            google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Bekliyor") # Eski haline çevir
                            st.session_state['son_islem_yedek'] = None
                            onbellek_temizle()
                            st.info("İşlem geri alındı.")
                            time.sleep(1)
                            st.rerun()
                            break

# --- 4. ARŞİV (ETİKET GÖSTERİMİ) ---
elif secim == "📂 Müşteri Arşivi":
    st.title("📂 Arşiv")
    if not df_m.empty:
        mus = st.selectbox("Müşteri:", df_m["Ad Soyad"].tolist())
        bilgi = df_m[df_m["Ad Soyad"] == mus].iloc[0]
        
        # Madde 24: Etiketleri Göster
        if "Etiket" in df_m.columns and str(bilgi["Etiket"]) != "nan":
            etiketler = str(bilgi["Etiket"]).split(",")
            html_etiket = "".join([f"<span class='etiket'>#{e.strip()}</span>" for e in etiketler])
            st.markdown(html_etiket, unsafe_allow_html=True)
            
        with st.form("up"):
            d = st.file_uploader("Dosya"); tur = st.selectbox("Tür", ["Fatura", "Diğer"])
            if st.form_submit_button("Yükle"):
                l = drive_yukle(d, mus, tur) if d else "-"
                google_sheet_baglan("Sheet1").append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{mus} - [{tur}]", "-", "Tamamlandi", l, aktif_kullanici])
                st.success("Yüklendi")

# --- DİĞERLERİ ---
elif secim == "💰 Finans & Kâr":
    st.title("💰 Finans")
    df_c = verileri_getir("Cari")
    if not df_c.empty:
        df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
        net = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
        st.metric("Net Kâr", f"{net:,.0f} TL")
        st.dataframe(df_c)

elif secim == "🏢 Kuruluş Sihirbazı":
    st.title("🏢 Kuruluş"); a=st.text_input("Aday"); t=st.selectbox("Tür", ["Ltd", "Şahıs"])
    if st.button("Teklif"): st.success("Hesaplandı")

elif secim == "🧮 Defter Tasdik":
    st.title("🧮 Tasdik"); s=st.number_input("Sayfa"); st.metric("Tutar", s*6+300)

elif secim == "👥 Personel & Portföy":
    st.title("👥 Analiz"); st.info("Sorumlu Analizi Burada")
    if not df_m.empty and "Sorumlu" in df_m.columns:
        df_m["Ucret"] = pd.to_numeric(df_m["Ucret"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
        st.bar_chart(df_m.groupby("Sorumlu")["Ucret"].sum())
