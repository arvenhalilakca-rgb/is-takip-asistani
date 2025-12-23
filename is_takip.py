import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import requests
import pandas as pd
import re
from datetime import datetime

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

@st.cache_data(ttl=60)
def verileri_getir(sayfa="Ana"):
    try:
        sheet = google_sheet_baglan(sayfa)
        return pd.DataFrame(sheet.get_all_records())
    except:
        return pd.DataFrame()

def onbellek_temizle():
    verileri_getir.clear()

# --- MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    st.markdown("### 🏛️ Müşavir Panel")
    secim = st.radio("MENÜ", ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "🏢 Kuruluş Sihirbazı", "💰 Finans Paneli"])
    st.caption("v.Tahakkuk | Otomasyon 🤖")

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
            bekleyen_tahsilat = 0
            if "Tahsilat" in df.columns:
                bekleyen_tahsilat = len(df[df["Tahsilat"]=="Bekliyor ❌"])
            c4.metric("💰 Açık Bakiye", f"{bekleyen_tahsilat} Adet", delta_color="inverse")
        
        st.markdown("### 📈 İş Analizi")
        col_g1, col_g2 = st.columns(2)
        with col_g1: st.dataframe(df[["Tarih", "Is Tanimi", "Durum"]].tail(5), use_container_width=True, hide_index=True)
        with col_g2: st.bar_chart(df["Durum"].value_counts())

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
        is_notu = st.text_input("İş Tanımı")
        sms = st.checkbox("📨 Bilgilendirme Gönder")
        
        if st.form_submit_button("✅ Görevi Kaydet", type="primary"):
            sheet = google_sheet_baglan("Sheet1")
            tam_ad = f"{musteri} - {is_notu}"
            sheet.append_row([tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), tam_ad, "Gonderildi", "Bekliyor", "-"])
            onbellek_temizle()
            whatsapp_gonder(GRUP_ID, f"📅 *YENİ İŞ*\n👤 {musteri}\n📌 {is_notu}")
            if sms and not df_m.empty:
                satir = df_m[df_m["Ad Soyad"] == musteri]
                if not satir.empty:
                    nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                    for n in nums: whatsapp_gonder(n, f"Sayın {musteri}, işleminiz ({is_notu}) alınmıştır.")
            st.success("Kayıt Başarılı!")

# --- 3. İŞ YÖNETİMİ ---
elif secim == "✅ İş Yönetimi":
    st.title("📋 Görev Kontrol")
    if st.button("🔄 Yenile"): onbellek_temizle(); st.rerun()
    df = verileri_getir("Sheet1")
    if not df.empty and "Durum" in df.columns:
        bekleyenler = df[df["Durum"] != "Tamamlandi"].copy()
        bugun = datetime.now()
        bekleyenler['Tarih_Format'] = pd.to_datetime(bekleyenler['Tarih'], format='%d.%m.%Y', errors='coerce')
        gecikmisler = bekleyenler[bekleyenler['Tarih_Format'] < bugun]
        
        if not gecikmisler.empty:
            st.markdown(f"""<div class="gecikmis-kutu">🚨 <b>DİKKAT!</b> Vadesi geçmiş <b>{len(gecikmisler)}</b> adet işiniz var!</div>""", unsafe_allow_html=True)
        
        if not bekleyenler.empty:
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
                            onbellek_temizle()
                            st.success("Kapatıldı!"); st.rerun(); break
        else: st.info("Bekleyen iş yok.")

# --- 4. MÜŞTERİ ARŞİVİ ---
elif secim == "📂 Müşteri Arşivi":
    st.title("📂 Dijital Arşiv")
    df_m = verileri_getir("Musteriler")
    if not df_m.empty:
        musteri = st.selectbox("Mükellef Seç:", df_m["Ad Soyad"].tolist())
        df = verileri_getir("Sheet1")
        ozel_veri = df[df["Is Tanimi"].str.contains(musteri, na=False)] if not df.empty else pd.DataFrame()
        
        c1, c2 = st.columns([2, 1])
        with c1:
            if not ozel_veri.empty:
                cols = ["Tarih", "Is Tanimi", "Durum"]
                if "Dosya" in ozel_veri.columns: cols.append("Dosya")
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
                    onbellek_temizle(); st.success("Kaydedildi!"); st.rerun()

# --- 5. KURULUŞ SİHİRBAZI ---
elif secim == "🏢 Kuruluş Sihirbazı":
    st.title("🏢 Kuruluş Formu")
    with st.container():
        c_ad, c_tel = st.columns(2)
        aday = c_ad.text_input("Görüşülen Kişi")
        tel = c_tel.text_input("Telefon")
    if aday:
        with st.form("kurulus"):
            with st.expander("Detaylar", expanded=True):
                sirket = st.radio("Tür", ["Şahıs", "Ltd", "A.Ş."])
                ucret = st.text_input("Aylık Ücret")
            if st.form_submit_button("Kaydet", type="primary"):
                rapor = f"GÖRÜŞME: {aday}\nTür: {sirket}\nÜcret: {ucret}"
                sheet = google_sheet_baglan("Sheet1")
                sheet.append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{aday} - [AÇILIŞ]", "-", "Tamamlandi", "-"])
                onbellek_temizle()
                whatsapp_gonder(GRUP_ID, f"🆕 *GÖRÜŞME*\n{rapor}")
                st.success("Kaydedildi.")

# --- 6. FİNANS PANELİ (YENİLENMİŞ!) ---
elif secim == "💰 Finans Paneli":
    st.title("💰 Finansal Yönetim")
    df = verileri_getir("Cari")
    
    # SEKMELER (TABLAR)
    tab1, tab2, tab3 = st.tabs(["Özet & Ekstre", "Tekil İşlem", "🔄 Yıllık Toplu Tahakkuk"])
    
    # --- TAB 1: ÖZET ---
    with tab1:
        if not df.empty:
            df["Tutar"] = pd.to_numeric(df["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
            alacak = df[df["Islem_Turu"].str.contains("Borç", na=False)]["Tutar"].sum()
            tahsilat = df[df["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum()
            bakiye = alacak - tahsilat
            c1, c2, c3 = st.columns(3)
            c1.metric("Toplam Alacak", f"{alacak:,.0f} TL")
            c2.metric("Toplam Tahsilat", f"{tahsilat:,.0f} TL")
            c3.metric("Piyasa Bakiyesi", f"{bakiye:,.0f} TL", delta_color="inverse")
            
            st.markdown("---")
            st.subheader("Müşteri Ekstresi")
            mus_list = df["Musteri"].unique()
            secilen_m = st.selectbox("Ekstre İçin Müşteri Seç", mus_list)
            if secilen_m:
                m_df = df[df["Musteri"]==secilen_m]
                m_borc = m_df[m_df["Islem_Turu"].str.contains("Borç", na=False)]["Tutar"].sum()
                m_ode = m_df[m_df["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum()
                m_bak = m_borc - m_ode
                st.caption(f"Güncel Bakiye: {m_bak:,.2f} TL")
                st.dataframe(m_df[["Tarih", "Islem_Turu", "Aciklama", "Tutar"]], use_container_width=True)

    # --- TAB 2: TEKİL İŞLEM ---
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
                st.success("Kaydedildi.")

    # --- TAB 3: TOPLU TAHAKKUK (YENİ!) ---
    with tab3:
        st.subheader("🔄 Yıllık Muhasebe Ücreti Yansıtma")
        st.info("Seçilen müşteriye Ocak'tan Aralık ayına kadar 12 aylık borç kaydı girer.")
        
        with st.form("toplu_tahakkuk"):
            col_t1, col_t2 = st.columns(2)
            
            df_m = verileri_getir("Musteriler")
            isimler = df_m["Ad Soyad"].tolist() if not df_m.empty else []
            
            t_musteri = col_t1.selectbox("Hangi Mükellef?", isimler, key="toplu_mus")
            t_yil = col_t2.number_input("Hangi Yıl?", min_value=2024, max_value=2030, value=2025)
            
            t_tutar = st.number_input("Aylık Muhasebe Ücreti (TL)", min_value=0.0, step=100.0)
            
            t_sms = st.checkbox("Mükellefe 'Yıllık Plan Oluşturuldu' mesajı at")
            
            btn_tahakkuk = st.form_submit_button("🚀 12 Aylık Borcu İşle", type="primary")
            
            if btn_tahakkuk and t_musteri and t_tutar > 0:
                sheet = google_sheet_baglan("Cari")
                
                # Toplu Veri Hazırlığı
                veriler = []
                aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", 
                         "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
                
                for i, ay in enumerate(aylar):
                    # Her ayın 15'ine kayıt atalım (Örn: 15.01.2025)
                    tarih_str = f"15.{i+1:02d}.{t_yil}"
                    aciklama = f"{ay} {t_yil} - Muhasebe Hizmet Bedeli"
                    
                    # Satır: Tarih, Musteri, Islem_Turu, Tutar, Aciklama
                    satir = [tarih_str, t_musteri, "Hizmet Bedeli (Borç)", t_tutar, aciklama]
                    veriler.append(satir)
                
                # Google Sheet'e Toplu Yazma (Hız için append_rows kullanılır)
                try:
                    sheet.append_rows(veriler)
                    onbellek_temizle()
                    
                    st.success(f"{t_musteri} için {t_yil} yılına ait toplam {t_tutar*12:,.0f} TL borç kaydı oluşturuldu.")
                    
                    if t_sms:
                        satir_m = df_m[df_m["Ad Soyad"] == t_musteri]
                        if not satir_m.empty:
                            nums = numaralari_ayikla(satir_m.iloc[0]["Telefon"])
                            msg = f"Sayın *{t_musteri}*,\n\n{t_yil} yılına ait muhasebe hizmet bedeli tahakkuklarınız (Aylık {t_tutar} TL) cari hesabınıza işlenmiştir.\n\nİyi çalışmalar dileriz.\n*Mali Müşavirlik Ofisi*"
                            for n in nums: whatsapp_gonder(n, msg)
                            st.info("Bilgilendirme mesajı gönderildi.")
                            
                except Exception as e:
                    st.error(f"Hata oluştu: {e}")
