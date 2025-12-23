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
    div[data-testid="stMetricValue"] {font-size: 26px; color: #2C3E50; font-weight: bold;}
    div.stContainer {background-color: #FFFFFF; padding: 20px; border-radius: 12px; border: 1px solid #E0E0E0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);}
    .stButton>button {width: 100%; border-radius: 8px; font-weight: 600;}
    button[kind="primary"] {background: linear-gradient(90deg, #2980b9 0%, #2c3e50 100%); color: white;}
    .gecikmis-kutu {padding: 15px; background-color: #ffebee; color: #c0392b; border-radius: 8px; border-left: 5px solid #c0392b; margin-bottom: 20px;}
    </style>
    """, unsafe_allow_html=True)

# --- ÇANAKKALE 2026 FİYAT TARİFESİ VERİTABANI ---
# Kaynak: 125343.jpg görseli
FIYAT_TARIFESI = {
    "Şahıs İşletmesi": {
        "Hizmet": {"Kurulus": 10000, "Defter": 5000},
        "Alım-Satım": {"Kurulus": 10000, "Defter": 5000},
        "İmalat - İnşaat": {"Kurulus": 10000, "Defter": 5000},
        "Serbest Meslek": {"Kurulus": 10000, "Defter": 6000},
        "Bilanço Esasına Tabii": {"Kurulus": 11250, "Defter": 10000},
        "Eczane": {"Kurulus": 11250, "Defter": 12500}
    },
    "Limited Şirket": {
        "Hizmet": {"Kurulus": 25000, "Defter": 12500},
        "Alım-Satım": {"Kurulus": 25000, "Defter": 12500},
        "İmalat - İnşaat": {"Kurulus": 25000, "Defter": 15000},
        "Yabancı Ortaklı": {"Kurulus": 40000, "Defter": 20000}
    },
    "Anonim Şirket": {
        "Hizmet": {"Kurulus": 25000, "Defter": 12500},
        "Alım-Satım": {"Kurulus": 25000, "Defter": 12500},
        "İmalat - İnşaat": {"Kurulus": 25000, "Defter": 17500}, # A.Ş İnşaat tarifede 17.500
        "Yabancı Ortaklı": {"Kurulus": 40000, "Defter": 20000}
    }
}

# --- NACE KODLARI DB ---
NACE_DB = {
    "Muhasebe": "69.20 - Muhasebe, defter tutma ve denetim faaliyetleri",
    "Danışmanlık": "70.22 - İşletme ve diğer idari danışmanlık faaliyetleri",
    "Yazılım": "62.01 - Bilgisayar programlama faaliyetleri",
    "İnşaat": "41.20 - İkamet amaçlı binaların inşaatı",
    "Emlak": "68.31 - Gayrimenkul acentelerinin faaliyetleri",
    "Restoran": "56.10 - Lokantalar ve seyyar yemek hizmeti faaliyetleri",
    "Nakliye": "49.41 - Karayolu ile yük taşımacılığı",
    "Kuaför": "96.02 - Kuaförlük ve güzellik salonlarının faaliyetleri",
    "Kırtasiye": "47.62 - Belirli bir mala tahsis edilmiş mağazalarda kırtasiye ürünleri",
    "Otomotiv": "45.11 - Otomobillerin ve hafif motorlu kara taşıtlarının ticareti"
}

# --- OTURUM YÖNETİMİ ---
if 'giris_yapildi' not in st.session_state: st.session_state['giris_yapildi'] = False
if 'kullanici_rolu' not in st.session_state: st.session_state['kullanici_rolu'] = None

# --- GİRİŞ EKRANI ---
def giris_ekrani():
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=100)
        st.title("Giriş Paneli")
        kullanici = st.text_input("Kullanıcı Adı")
        sifre = st.text_input("Şifre", type="password")
        if st.button("Giriş Yap", type="primary"):
            if kullanici == "admin" and sifre == "1234":
                st.session_state['giris_yapildi'] = True; st.session_state['kullanici_rolu'] = "admin"
                st.rerun()
            elif kullanici == "personel" and sifre == "1111":
                st.session_state['giris_yapildi'] = True; st.session_state['kullanici_rolu'] = "personel"
                st.rerun()
            else: st.error("Hatalı bilgiler!")

if not st.session_state['giris_yapildi']: giris_ekrani(); st.stop()

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
        tarih_str = datetime.now().strftime("%Y-%m-%d")
        yeni_isim = f"{musteri_adi}_{tarih_str}_{evrak_turu}.{uzanti}".replace(" ", "_")
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
    menu = ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi"]
    if rol == "admin": menu += ["🏢 Kuruluş Sihirbazı", "💰 Finans & Kâr"]
    secim = st.radio("MENÜ", menu)
    st.markdown("---")
    if st.button("Çıkış Yap"): st.session_state['giris_yapildi'] = False; st.rerun()

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
                    net = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
                    renk = "normal" if net > 0 else "inverse"
                    c4.metric("💵 NET KÂR", f"{net:,.0f} TL", delta_color=renk)
            else: c4.metric("Rol", "Personel")
        col1, col2 = st.columns(2)
        with col1: st.markdown("### 🗓 Son Hareketler"); st.dataframe(df[["Tarih", "Is Tanimi", "Durum"]].tail(5), use_container_width=True, hide_index=True)
        with col2: st.markdown("### 📊 İş Durumu"); st.bar_chart(df["Durum"].value_counts())

# --- 2. İŞ EKLE ---
elif secim == "➕ İş Ekle":
    st.title("📝 Görev Girişi")
    with st.form("is"):
        c1, c2 = st.columns(2); t = c1.date_input("Tarih"); s = c2.time_input("Saat")
        df_m = verileri_getir("Musteriler")
        mus = st.selectbox("Mükellef", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
        notu = st.text_input("İş Tanımı")
        sms = st.checkbox("Bildirim Gönder")
        if st.form_submit_button("Kaydet", type="primary"):
            sheet = google_sheet_baglan("Sheet1")
            sheet.append_row([t.strftime("%d.%m.%Y"), s.strftime("%H:%M"), f"{mus} - {notu}", "Gonderildi", "Bekliyor", "-"])
            onbellek_temizle(); whatsapp_gonder(GRUP_ID, f"🆕 *İŞ*\n👤 {mus}\n📌 {notu}"); st.success("Kaydedildi!")

# --- 3. İŞ YÖNETİMİ ---
elif secim == "✅ İş Yönetimi":
    st.title("📋 Görev Kontrol")
    if st.button("🔄 Yenile"): onbellek_temizle(); st.rerun()
    df = verileri_getir("Sheet1")
    if not df.empty and "Durum" in df.columns:
        bekleyen = df[df["Durum"] != "Tamamlandi"].copy()
        bugun = datetime.now()
        bekleyen['Tarih_Format'] = pd.to_datetime(bekleyen['Tarih'], format='%d.%m.%Y', errors='coerce')
        gec = bekleyen[bekleyen['Tarih_Format'] < bugun]
        if not gec.empty: st.markdown(f"""<div class="gecikmis-kutu">🚨 <b>{len(gec)}</b> gecikmiş iş var!</div>""", unsafe_allow_html=True)
        if not bekleyen.empty:
            st.dataframe(bekleyen[["Tarih", "Is Tanimi", "Durum"]], use_container_width=True, hide_index=True)
            with st.container():
                c1, c2 = st.columns([3,1])
                sec = c1.selectbox("Biten İş:", bekleyen["Is Tanimi"].tolist())
                if c2.button("Kapat 🏁", type="primary"):
                    sheet = google_sheet_baglan("Sheet1")
                    rows = sheet.get_all_values()
                    for i, row in enumerate(rows):
                        if len(row) > 2 and row[2] == sec:
                            sheet.update_cell(i+1, 5, "Tamamlandi"); onbellek_temizle(); st.success("Kapatıldı!"); st.rerun(); break
        else: st.info("İş yok.")

# --- 4. ARŞİV ---
elif secim == "📂 Müşteri Arşivi":
    st.title("📂 Dijital Arşiv")
    df_m = verileri_getir("Musteriler")
    if not df_m.empty:
        mus = st.selectbox("Mükellef:", df_m["Ad Soyad"].tolist())
        df = verileri_getir("Sheet1")
        ozel = df[df["Is Tanimi"].str.contains(mus, na=False)] if not df.empty else pd.DataFrame()
        c1, c2 = st.columns([2, 1])
        with c1:
            if not ozel.empty:
                cols = ["Tarih", "Is Tanimi", "Durum"]
                if "Dosya" in ozel.columns: cols.append("Dosya")
                st.dataframe(ozel[cols], use_container_width=True, hide_index=True, column_config={"Dosya": st.column_config.LinkColumn("Evrak")})
        with c2:
            with st.form("up"):
                evrak_turu = st.selectbox("Evrak Türü", ["Fatura", "Dekont", "Vergi Levhası", "İmza Sirküsü", "Diğer"])
                txt = st.text_area("Açıklama")
                dosya = st.file_uploader("Dosya Seç")
                if st.form_submit_button("Kaydet", type="primary"):
                    link = "-"
                    if dosya:
                        with st.spinner("İsimlendiriliyor..."): link = drive_yukle(dosya, mus, evrak_turu)
                    sheet = google_sheet_baglan("Sheet1")
                    sheet.append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{mus} - [{evrak_turu}] {txt}", "-", "Tamamlandi", link])
                    onbellek_temizle(); st.success("Kaydedildi!"); st.rerun()

# --- 5. KURULUŞ SİHİRBAZI (OTOMATİK FİYATLI) ---
elif secim == "🏢 Kuruluş Sihirbazı":
    st.title("🏢 Kuruluş & Teklif Motoru")
    st.info("ℹ️ Fiyatlar Çanakkale 2026 Tarifesinden otomatik çekilir.")

    with st.container():
        c1, c2 = st.columns(2); aday = c1.text_input("Görüşülen Kişi"); tel = c2.text_input("Telefon")
    
    if aday:
        with st.form("kurulus"):
            # 1. BÖLÜM: TÜR VE SEKTÖR (TARİFE BELİRLEYİCİ)
            with st.expander("1. Şirket Yapısı (Otomatik Fiyat)", expanded=True):
                col_tur, col_sektor = st.columns(2)
                
                # Resimdeki kategorilere göre seçimler
                sirket_turu = col_tur.radio("Şirket Türü", ["Şahıs İşletmesi", "Limited Şirket", "Anonim Şirket"])
                
                # Sektör Seçimi (Fiyatı değiştirir)
                sektorler = ["Hizmet", "Alım-Satım", "İmalat - İnşaat", "Yabancı Ortaklı", "Serbest Meslek", "Eczane", "Bilanço Esasına Tabii"]
                secilen_sektor = col_sektor.selectbox("Faaliyet Alanı", sektorler)
                
                # --- OTOMATİK FİYAT HESAPLAMA MOTORU ---
                # Varsayılan değerler
                onerilen_kurulus = 0
                onerilen_defter = 0
                
                # Dictionary'den fiyat çekme
                if sirket_turu in FIYAT_TARIFESI:
                    if secilen_sektor in FIYAT_TARIFESI[sirket_turu]:
                        fiyatlar = FIYAT_TARIFESI[sirket_turu][secilen_sektor]
                        onerilen_kurulus = fiyatlar["Kurulus"]
                        onerilen_defter = fiyatlar["Defter"]
                    else:
                        # Eğer o sektör o şirkette yoksa (Örn: Şahısta Yabancı Ortak olmaz), Hizmet baz al
                        onerilen_kurulus = FIYAT_TARIFESI[sirket_turu]["Hizmet"]["Kurulus"]
                        onerilen_defter = FIYAT_TARIFESI[sirket_turu]["Hizmet"]["Defter"]
                
                # Fiyatı Ekrana Bas
                st.success(f"🏷️ TARİFE ÖNERİSİ: Kuruluş {onerilen_kurulus:,.0f} TL | Aylık {onerilen_defter:,.0f} TL")
                # ----------------------------------------

            # 2. BÖLÜM: NACE
            with st.expander("2. Faaliyet Kodu (NACE)"):
                anahtar = st.text_input("İş Tanımı Ara (Örn: İnşaat)")
                liste = [k for k in NACE_DB.keys() if anahtar.lower() in k.lower()] if anahtar else list(NACE_DB.keys())
                kod = st.selectbox("NACE Seç:", liste)
                tam_nace = NACE_DB.get(kod, "Diğer")
                st.caption(f"Kod: {tam_nace}")

            # 3. BÖLÜM: TEKLİF OLUŞTURMA
            with st.expander("3. Teklif Oluştur"):
                # Inputlara otomatik önerilen fiyatı yazıyoruz (value=...)
                c_f1, c_f2 = st.columns(2)
                
                # number_input ile varsayılan değer atama
                ucret_aylik = c_f1.number_input("Aylık Muhasebe Ücreti (TL)", value=float(onerilen_defter), step=500.0)
                ucret_kurulus = c_f2.number_input("Kuruluş Hizmet Bedeli (TL)", value=float(onerilen_kurulus), step=500.0)
                
                st.warning("Not: Tarifede 5+ işçi varsa ek ücret (+100 TL/Kişi) manuel eklenmelidir.")

            if st.form_submit_button("Teklifi Kaydet ve Bildir", type="primary"):
                rapor = f"GÖRÜŞME: {aday}\nTür: {sirket_turu} ({secilen_sektor})\nFaaliyet: {tam_nace}\n\n💰 TEKLİF:\nAylık: {ucret_aylik:,.0f} TL\nKuruluş: {ucret_kurulus:,.0f} TL"
                sheet = google_sheet_baglan("Sheet1")
                sheet.append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{aday} - [AÇILIŞ]", "-", "Tamamlandi", "-"])
                onbellek_temizle(); whatsapp_gonder(GRUP_ID, f"🆕 *YENİ TEKLİF*\n{rapor}"); st.success("Teklif kaydedildi!")

# --- 6. FİNANS (ADMIN) ---
elif secim == "💰 Finans & Kâr":
    st.title("💰 Finans Yönetimi")
    df = verileri_getir("Cari")
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Analiz", "💸 Ekle", "📜 Ekstre", "🔄 Tahakkuk"])
    # (Finans kodları aynı)
    with tab1:
        if not df.empty:
            df["Tutar"] = pd.to_numeric(df["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
            net = df[df["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df[df["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
            st.metric("NET KÂR", f"{net:,.0f} TL")
            st.bar_chart(df[df["Islem_Turu"].str.contains("Gider", na=False)].set_index("Aciklama")["Tutar"])
    with tab2:
        with st.form("fin"):
            trh = st.date_input("Tarih"); tur = st.radio("Tür", ["Hizmet Bedeli (Borç)", "Tahsilat (Ödeme)", "🔴 OFİS GİDERİ"])
            if tur == "🔴 OFİS GİDERİ": mus="GİDER"
            else: mus = st.selectbox("Müşteri", verileri_getir("Musteriler")["Ad Soyad"].tolist())
            tut = st.number_input("Tutar"); ack = st.text_input("Açıklama")
            if st.form_submit_button("Kaydet"):
                google_sheet_baglan("Cari").append_row([trh.strftime("%d.%m.%Y"), mus, tur, tut, ack]); onbellek_temizle(); st.success("Ok")
    with tab3:
        m = st.selectbox("Müşteri", verileri_getir("Musteriler")["Ad Soyad"].tolist())
        if m: st.dataframe(df[df["Musteri"]==m])
    with tab4:
        with st.form("tah"):
            mm = st.selectbox("Müşteri", verileri_getir("Musteriler")["Ad Soyad"].tolist(), key="tah")
            tt = st.number_input("Tutar"); 
            if st.form_submit_button("Yıllık İşle"):
                rows=[[f"15.{i+1:02d}.2025", mm, "Hizmet Bedeli (Borç)", tt, "Yıllık"] for i in range(12)]
                google_sheet_baglan("Cari").append_rows(rows); onbellek_temizle(); st.success("Tamam")
