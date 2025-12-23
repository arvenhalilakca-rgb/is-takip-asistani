# ==============================================================================
# MÜŞAVİR ASİSTANI PRO MAX - v2.0
# Geliştiren: Manus AI & Kullanıcı İşbirliği
# Son Güncelleme: 23.12.2025
# ==============================================================================

# --- 1. GEREKLİ KÜTÜPHANELER ---
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

# --- 2. SAYFA AYARLARI VE TASARIM ---
st.set_page_config(
    page_title="Müşavir Asistanı Pro Max",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .stApp {background-color: #F8F9FA; font-family: 'Helvetica', sans-serif;}
    [data-testid="stSidebar"] {background-color: #2C3E50;}
    [data-testid="stSidebar"] * {color: #ECF0F1 !important;}
    div.stContainer {background-color: #FFFFFF; padding: 20px; border-radius: 12px; border: 1px solid #E0E0E0;}
    .stButton>button {width: 100%; border-radius: 8px; font-weight: 600;}
    button[kind="primary"] {background: linear-gradient(90deg, #2980b9 0%, #2c3e50 100%); color: white;}
    .etiket {background-color: #e0f7fa; color: #006064; padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-right: 5px; border: 1px solid #b2ebf2;}
    .tatil-uyari {background-color: #ffebee; color: #c62828; padding: 10px; border-radius: 8px; border-left: 5px solid #c62828;}
    .sahipsiz {border-left: 5px solid #ff9800; background-color: #fff3e0; padding: 10px;}
    .tarihli-not {font-size: 13px; color: #2c3e50; background-color: #ecf0f1; padding: 8px; border-radius: 5px; margin-bottom: 5px; border-left: 3px solid #3498db;}
    div[data-testid="stMetricValue"] {font-size: 24px; color: #2C3E50;}
    </style>
    """, unsafe_allow_html=True)

# --- 3. SABİT VERİLER VE OTURUM YÖNETİMİ ---
RESMI_TATILLER = ["01.01", "23.04", "01.05", "19.05", "15.07", "30.08", "29.10"]
FIYAT_TARIFESI = {
    "Şahıs İşletmesi": {"Hizmet": {"Kurulus": 10000, "Defter": 5000}, "Alım-Satım": {"Kurulus": 10000, "Defter": 5000}, "İmalat - İnşaat": {"Kurulus": 10000, "Defter": 5000}, "Serbest Meslek": {"Kurulus": 10000, "Defter": 6000}, "Bilanço Esasına Tabii": {"Kurulus": 11250, "Defter": 10000}},
    "Limited Şirket": {"Hizmet": {"Kurulus": 25000, "Defter": 12500}, "Alım-Satım": {"Kurulus": 25000, "Defter": 12500}, "İmalat - İnşaat": {"Kurulus": 25000, "Defter": 15000}},
    "Anonim Şirket": {"Hizmet": {"Kurulus": 25000, "Defter": 12500}, "İmalat - İnşaat": {"Kurulus": 25000, "Defter": 17500}}
}

# Oturum Değişkenleri
if 'hizli_not' not in st.session_state: st.session_state['hizli_not'] = ""
if 'son_islem_yedek' not in st.session_state: st.session_state['son_islem_yedek'] = None
if 'sessiz_mod' not in st.session_state: st.session_state['sessiz_mod'] = False
if 'aktif_kullanici' not in st.session_state: st.session_state['aktif_kullanici'] = "Admin"
if 'son_islem_logu' not in st.session_state: st.session_state['son_islem_logu'] = "Sistem başlatıldı."

# --- 4. BAĞLANTILAR VE TEMEL FONKSİYONLAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]; API_TOKEN = st.secrets["API_TOKEN"]
    GRUP_ID = st.secrets["GRUP_ID"]; DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
except Exception as e:
    st.error(f"⚠️ Ayar Hatası: Secrets dosyası okunamadı. Lütfen yapılandırmayı kontrol edin. Hata: {e}"); st.stop()

@st.cache_data(ttl=60)
def verileri_getir(sayfa="Ana"):
    try:
        client = gspread.authorize(creds)
        if sayfa == "Sheet1": sheet = client.open("Is_Takip_Sistemi").sheet1
        else: sheet = client.open("Is_Takip_Sistemi").worksheet(sayfa)
        return pd.DataFrame(sheet.get_all_records())
    except Exception as e:
        st.sidebar.error(f"Veri çekme hatası: '{sayfa}' sayfası bulunamadı veya yetki sorunu.")
        return pd.DataFrame()

def onbellek_temizle():
    verileri_getir.clear()

def log_kaydi_ekle(is_id, kullanici, eylem):
    try:
        client = gspread.authorize(creds)
        sheet = client.open("Is_Takip_Sistemi").worksheet("Loglar")
        sheet.append_row([datetime.now().strftime("%d.%m.%Y %H:%M:%S"), str(is_id), kullanici, eylem])
        st.session_state['son_islem_logu'] = f"{kullanici} - {eylem}"
    except Exception as e:
        st.sidebar.warning(f"Loglama Hatası: 'Loglar' sayfası bulunamadı.")

def whatsapp_gonder(chat_id, mesaj):
    if st.session_state.get('sessiz_mod', False): return False
    if not chat_id or not isinstance(chat_id, str): return False
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        requests.post(url, json={'chatId': chat_id, 'message': mesaj}, timeout=5).raise_for_status()
        return True
    except requests.exceptions.RequestException:
        return False

def numaralari_ayikla(tel_str):
    if not tel_str: return []
    tel_str = str(tel_str)
    ham_parcalar = re.split(r'[,\n/]', tel_str)
    temiz = {re.sub(r'\D', '', parca.strip()) for parca in ham_parcalar}
    sonuc = set()
    for num in temiz:
        if len(num) == 10: sonuc.add("90" + num)
        elif len(num) == 11 and num.startswith("0"): sonuc.add("9" + num)
        elif len(num) == 12 and num.startswith("90"): sonuc.add(num)
    return list(sonuc)

# --- 5. YAN MENÜ (SIDEBAR) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    
    df_m = verileri_getir("Musteriler")
    personel_listesi = ["Admin"]
    if not df_m.empty and "Sorumlu" in df_m.columns:
        personel_listesi.extend([p for p in df_m["Sorumlu"].unique() if p and str(p) not in ["nan", "None"]])
    
    unique_personel = sorted(list(set(personel_listesi)))
    try:
        default_index = unique_personel.index(st.session_state['aktif_kullanici'])
    except ValueError:
        default_index = 0
    
    st.session_state['aktif_kullanici'] = st.selectbox("👤 Kullanıcı", unique_personel, index=default_index)
    st.session_state['sessiz_mod'] = st.toggle("🔕 Sessiz Mod", value=st.session_state.get('sessiz_mod', False), help="Aktifken WhatsApp bildirimi gönderilmez.")
    arama_nav = st.text_input("🔍 Hızlı Git (Ctrl+K)", placeholder="Müşteri, İş Ekle...")
    
    st.markdown("---")
    menu_options = ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "💰 Finans & Kâr", "🏢 Kuruluş Sihirbazı", "🧮 Defter Tasdik", "👥 Personel & Portföy"]
    secim = st.radio("MENÜ", menu_options)
    
    st.markdown("---")
    st.session_state['hizli_not'] = st.text_area("📝 Hızlı Notlar:", value=st.session_state.get('hizli_not', ""), height=100)
    st.caption(f"Son İşlem: {st.session_state.get('son_islem_logu', 'Sistem başlatıldı.')}")

# Hızlı Git (Sihirli Arama) Mantığı
if arama_nav:
    nav_lower = arama_nav.lower()
    if any(keyword in nav_lower for keyword in ["ekle", "yeni"]): secim = "➕ İş Ekle"
    elif "finans" in nav_lower: secim = "💰 Finans & Kâr"
    elif "arşiv" in nav_lower: secim = "📂 Müşteri Arşivi"
    elif "yönetim" in nav_lower: secim = "✅ İş Yönetimi"

# --- 6. SAYFA İÇERİKLERİ ---

if secim == "📊 Genel Bakış":
    st.title("📊 Yönetim Kokpiti")
    df_is = verileri_getir("Sheet1")
    
    if not df_is.empty and "Durum" in df_is.columns:
        if not df_m.empty and "Dogum_Tarihi" in df_m.columns:
            bugun = datetime.now()
            df_m["Dogum_Tarihi_Format"] = pd.to_datetime(df_m["Dogum_Tarihi"], format='%d.%m.%Y', errors='coerce')
            dogum_gunleri = df_m[df_m["Dogum_Tarihi_Format"].dt.month == bugun.month]
            if not dogum_gunleri.empty:
                st.success(f"🎂 Bu Ay Doğanlar: {', '.join(dogum_gunleri['Ad Soyad'].tolist())}")

        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Toplam İş", len(df_is))
            c2.metric("✅ Biten", len(df_is[df_is["Durum"]=="Tamamlandi"]))
            c3.metric("⏳ Bekleyen", len(df_is[df_is["Durum"]!="Tamamlandi"]))
            
            df_c = verileri_getir("Cari")
            if not df_c.empty and "Tutar" in df_c.columns:
                df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", "", regex=False), errors='coerce').fillna(0)
                net_kar = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
                c4.metric("Net Kâr", f"{net_kar:,.0f} TL")
            else:
                c4.metric("Net Kâr", "0 TL")

        if "Personel" in df_is.columns:
            sahipsiz_isler = df_is[(df_is["Personel"].isnull() | (df_is["Personel"] == "")) & (df_is["Durum"] != "Tamamlandi")]
            if not sahipsiz_isler.empty:
                st.markdown(f"<div class='sahipsiz'>⚠️ {len(sahipsiz_isler)} işe personel atanmamış! Lütfen kontrol ediniz.</div>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Son Hareketler")
            st.dataframe(df_is.tail(5), use_container_width=True, hide_index=True)
        with col2:
            st.subheader("İş Durum Dağılımı")
            st.bar_chart(df_is["Durum"].value_counts())

elif secim == "➕ İş Ekle":
    st.title("📝 Akıllı İş Girişi")
    with st.container():
        with st.form("is_ekle_form"):
            c1, c2 = st.columns(2)
            tarih = c1.date_input("İşlem Tarihi")
            if tarih.strftime("%d.%m") in RESMI_TATILLER or tarih.weekday() >= 5:
                st.markdown(f"<div class='tatil-uyari'>⚠️ {tarih.strftime('%d.%m.%Y')} resmi tatil veya hafta sonu.</div>", unsafe_allow_html=True)
            saat = c2.time_input("Saat")
            
            musteri_listesi = [""]
            if not df_m.empty:
                df_m["Ucret"] = pd.to_numeric(df_m["Ucret"].astype(str).str.replace(",", "", regex=False), errors='coerce').fillna(0)
                vip_limit = df_m["Ucret"].quantile(0.8)
                for _, row in df_m.iterrows():
                    musteri_adi = row["Ad Soyad"]
                    if row["Ucret"] >= vip_limit and vip_limit > 0:
                        musteri_adi = f"⭐ {musteri_adi} (VIP)"
                    musteri_listesi.append(musteri_adi)
            
            secilen_musteri_raw = st.selectbox("Mükellef Seçiniz", musteri_listesi)
            secilen_musteri = secilen_musteri_raw.replace("⭐ ", "").replace(" (VIP)", "")
            
            personel_yuk_listesi = [""]
            varsayilan_personel_index = 0
            df_is = verileri_getir("Sheet1")
            
            musteri_sorumlusu = ""
            if not df_m.empty and "Sorumlu" in df_m.columns:
                sorumlu_satir = df_m[df_m["Ad Soyad"] == secilen_musteri]
                if not sorumlu_satir.empty:
                    musteri_sorumlusu = sorumlu_satir.iloc[0]["Sorumlu"]

            if not df_is.empty and "Personel" in df_is.columns:
                aktif_is_yukleri = df_is[df_is["Durum"] != "Tamamlandi"]["Personel"].value_counts()
                for p in unique_personel:
                    if p != "Admin":
                        etiket = f"{p} (Aktif: {aktif_is_yukleri.get(p, 0)})"
                        personel_yuk_listesi.append(etiket)
                        if p == musteri_sorumlusu:
                            varsayilan_personel_index = len(personel_yuk_listesi) - 1
            
            secilen_personel_raw = st.selectbox("Sorumlu Personel", personel_yuk_listesi, index=varsayilan_personel_index)
            secilen_personel = secilen_personel_raw.split(" (")[0] if "(" in secilen_personel_raw else secilen_personel_raw
            
            is_sablonu = st.selectbox("İş Şablonu", ["", "KDV Beyannamesi", "Muhtasar Beyanname", "SGK İşe Giriş", "Genel Kurul Hazırlığı", "Diğer"])
            is_notu = is_sablonu if is_sablonu != "Diğer" else st.text_input("İşin Açıklaması")
            
            sms_gonder = st.checkbox("Mükellefe SMS Gönder")
            
            if st.form_submit_button("✅ Görevi Kaydet", type="primary"):
                if not secilen_musteri or not is_notu:
                    st.warning("Lütfen bir mükellef seçin ve iş tanımı girin.")
                else:
                    is_tanimi = f"{secilen_musteri} - {is_notu}"
                    yeni_satir = [tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), is_tanimi, "Gonderildi", "Bekliyor", "-", secilen_personel]
                    
                    client = gspread.authorize(creds)
                    sheet = client.open("Is_Takip_Sistemi").sheet1
                    sheet.append_row(yeni_satir)
                    
                    log_kaydi_ekle(is_tanimi, st.session_state['aktif_kullanici'], "Yeni görev oluşturdu.")
                    onbellek_temizle()
                    whatsapp_gonder(GRUP_ID, f"🆕 *YENİ İŞ*: {is_tanimi} ({secilen_personel})")
                    
                    if sms_gonder:
                        musteri_satiri = df_m[df_m["Ad Soyad"] == secilen_musteri]
                        if not musteri_satiri.empty:
                            for numara in numaralari_ayikla(musteri_satiri.iloc[0].get("Telefon")):
                                whatsapp_gonder(numara, f"Sayın {secilen_musteri}, '{is_notu}' konulu işleminiz alınmıştır.")
                    st.success("Görev başarıyla kaydedildi!"); time.sleep(1); st.rerun()

elif secim == "✅ İş Yönetimi":
    st.title("📋 İş Takip ve Yönetim Merkezi")
    if st.button("🔄 Listeyi Yenile"): onbellek_temizle(); st.rerun()
    
    df_is = verileri_getir("Sheet1")
    if not df_is.empty:
        filtre_aktif = st.checkbox(f"Sadece Bana ({st.session_state['aktif_kullanici']}) Atananları Göster")
        gosterilecek_df = df_is.copy()
        if filtre_aktif and st.session_state['aktif_kullanici'] != "Admin" and "Personel" in gosterilecek_df.columns:
            gosterilecek_df = gosterilecek_df[gosterilecek_df["Personel"] == st.session_state['aktif_kullanici']]
        
        st.dataframe(gosterilecek_df[["Tarih", "Is Tanimi", "Durum", "Personel"]], use_container_width=True, hide_index=True)
        
        st.markdown("---")
        with st.container():
            c1, c2 = st.columns([3, 1])
            bekleyen_isler = df_is[df_is["Durum"] != "Tamamlandi"]["Is Tanimi"].tolist()
            if not bekleyen_isler:
                st.info("Harika! Bekleyen hiç işiniz yok.")
            else:
                secilen_is = c1.selectbox("Tamamlanacak İşi Seç:", bekleyen_isler)
                
                if any(keyword in secilen_is.upper() for keyword in ["AÇILIŞ", "KURULUŞ"]):
                    st.info("Kuruluş Kontrol Listesi")
                    adımlar = {"Sicil Gazetesi Alındı": st.checkbox("1. Sicil Gazetesi"), "İmza Sirküleri Çıkarıldı": st.checkbox("2. İmza Sirküleri"), "E-Tebligat Başvurusu Yapıldı": st.checkbox("3. E-Tebligat")}
                    if st.button("Durumu Güncelle"):
                        yeni_durum = f"İlerleme: {sum(adımlar.values())}/{len(adımlar)}"
                        if sum(adımlar.values()) == len(adımlar): yeni_durum = "Tamamlandi"
                        
                        client = gspread.authorize(creds)
                        sheet = client.open("Is_Takip_Sistemi").sheet1
                        if cell := sheet.find(secilen_is):
                            sheet.update_cell(cell.row, 5, yeni_durum)
                            log_kaydi_ekle(secilen_is, st.session_state['aktif_kullanici'], f"Kuruluş adımlarını güncelledi: {yeni_durum}")
                            onbellek_temizle(); st.success("Durum güncellendi!"); st.rerun()
                else:
                    if c2.button("🏁 İşi Bitir", type="primary"):
                        st.session_state['son_islem_yedek'] = {"is_tanimi": secilen_is, "onceki_durum": "Bekliyor"}
                        client = gspread.authorize(creds)
                        sheet = client.open("Is_Takip_Sistemi").sheet1
                        if cell := sheet.find(secilen_is):
                            sheet.update_cell(cell.row, 5, "Tamamlandi")
                            log_kaydi_ekle(secilen_is, st.session_state['aktif_kullanici'], "Görevi 'Tamamlandı' olarak işaretledi.")
                            onbellek_temizle(); st.balloons(); st.success(f"'{secilen_is}' başarıyla tamamlandı!"); time.sleep(2); st.rerun()
                
                if st.session_state.get('son_islem_yedek'):
                    if st.button("↩️ Son İşlemi Geri Al"):
                        is_bilgisi = st.session_state['son_islem_yedek']
                        client = gspread.authorize(creds)
                        sheet = client.open("Is_Takip_Sistemi").sheet1
                        if cell := sheet.find(is_bilgisi["is_tanimi"]):
                            sheet.update_cell(cell.row, 5, is_bilgisi["onceki_durum"])
                            log_kaydi_ekle(is_bilgisi["is_tanimi"], st.session_state['aktif_kullanici'], "Son 'tamamlandı' işlemini geri aldı.")
                            st.session_state['son_islem_yedek'] = None
                            onbellek_temizle(); st.info("İşlem geri alındı."); st.rerun()

elif secim == "💰 Finans & Kâr":
    st.title("💰 Finans Yönetimi")
    df_c = verileri_getir("Cari")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Analiz", "💸 Gelir/Gider Ekle", "📄 KDV'den Oku (OCR)", "🔄 Yıllık Tahakkuk"])
    
    with tab1:
        if not df_c.empty:
            df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", "", regex=False), errors='coerce').fillna(0)
            toplam_tahsilat = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum()
            toplam_gider = df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
            net_kar = toplam_tahsilat - toplam_gider
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Toplam Tahsilat", f"{toplam_tahsilat:,.0f} TL")
            c2.metric("Toplam Gider", f"{toplam_gider:,.0f} TL", delta_color="inverse")
            c3.metric("NET KÂR", f"{net_kar:,.0f} TL", delta_color="normal" if net_kar > 0 else "inverse")
            
            st.divider()
            st.subheader("Son Finansal Hareketler")
            st.dataframe(df_c.tail(10), use_container_width=True, hide_index=True)
        else:
            st.info("📭 Henüz finansal veri girişi yapılmamış. Yan sekmeden ekleyebilirsiniz.")

    with tab2:
        st.subheader("💸 Yeni Finansal İşlem Ekle")
        with st.form("finans_ekle_form"):
            c1, c2 = st.columns(2)
            tarih = c1.date_input("İşlem Tarihi")
            tur = c2.radio("İşlem Türü", ["Hizmet Bedeli (Borç)", "Tahsilat (Ödeme)", "🔴 OFİS GİDERİ"])
            
            muhatap = "OFİS GİDERİ" if tur == "🔴 OFİS GİDERİ" else st.selectbox("Müşteri Seçiniz", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
            tutar = st.number_input("Tutar (TL)", min_value=0.0, step=100.0, format="%.2f")
            aciklama = st.text_input("Açıklama", placeholder="Örn: Kira, Kırtasiye, Ocak Ayı Muhasebe...")
            
            if st.form_submit_button("✅ Kaydet", type="primary"):
                if not muhatap or tutar <= 0:
                    st.error("Lütfen geçerli bir muhatap seçin ve tutar girin.")
                else:
                    client = gspread.authorize(creds)
                    sheet = client.open("Is_Takip_Sistemi").worksheet("Cari")
                    sheet.append_row([tarih.strftime("%d.%m.%Y"), muhatap, tur, tutar, aciklama])
                    log_kaydi_ekle(f"{muhatap}-{tur}", st.session_state['aktif_kullanici'], f"Finansal işlem ekledi: {tutar} TL")
                    onbellek_temizle(); st.success("İşlem başarıyla kaydedildi!"); time.sleep(1); st.rerun()

    with tab3:
        st.subheader("📄 KDV Beyannamesinden POS Tutarı Oku")
        st.info("Bu araç, PDF içindeki 'Kredi Kartı ile Tahsil Edilen...' alanını okumaya çalışır.")
        
        if uploaded_pdf := st.file_uploader("Beyanname PDF'ini Buraya Yükleyin", type="pdf", key="ocr_uploader"):
            with st.spinner("PDF analiz ediliyor..."):
                text = "".join(page.extract_text() or "" for page in pdfplumber.open(uploaded_pdf).pages)
                if match := re.search(r"Kredi Kartı.*?(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})", text, re.IGNORECASE | re.DOTALL):
                    pos_tutari = float(match.group(1).replace(".", "").replace(",", "."))
                    st.success(f"Okunan Kredi Kartı Tahsilat Tutarı: **{pos_tutari:,.2f} TL**")
                else:
                    st.error("PDF içinde kredi kartı tahsilat tutarı otomatik olarak bulunamadı.")

    with tab4:
        st.subheader("🔄 Yıllık Muhasebe Ücreti Tahakkuku")
        with st.form("tahakkuk_form"):
            secilen_m = st.selectbox("Müşteri", df_m["Ad Soyad"].tolist() if not df_m.empty else [], key="tahakkuk_musteri")
            aylik_tutar = st.number_input("Aylık Muhasebe Ücreti", min_value=0.0, format="%.2f")
            
            if st.form_submit_button("12 Aylık Borç İşle", type="primary"):
                if not secilen_m or aylik_tutar <= 0:
                    st.error("Lütfen bir müşteri seçin ve geçerli bir aylık tutar girin.")
                else:
                    rows_to_append = [[f"15.{i+1:02d}.{datetime.now().year}", secilen_m, "Hizmet Bedeli (Borç)", aylik_tutar, f"{datetime.now().year} Yılı Muhasebe Ücreti"] for i in range(12)]
                    client = gspread.authorize(creds)
                    sheet = client.open("Is_Takip_Sistemi").worksheet("Cari")
                    sheet.append_rows(rows_to_append)
                    log_kaydi_ekle(secilen_m, st.session_state['aktif_kullanici'], f"12 aylık tahakkuk oluşturdu ({aylik_tutar} TL/ay)")
                    onbellek_temizle(); st.success(f"'{secilen_m}' için 12 aylık borç kaydı oluşturuldu!"); time.sleep(1); st.rerun()

else:
    st.info(f"'{secim}' sayfası yapım aşamasındadır.")
