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
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TASARIM ---
st.markdown("""
    <style>
    .stApp {background-color: #f0f2f6;}
    [data-testid="stSidebar"] {background-color: #1e293b;}
    [data-testid="stSidebar"] * {color: white !important;}
    div.block-container {padding-top: 2rem;}
    .stButton>button {width: 100%; border-radius: 8px; font-weight: bold;}
    div[data-testid="stMetricValue"] {font-size: 24px;}
    </style>
    """, unsafe_allow_html=True)

# --- GÜVENLİK VE BAĞLANTILAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]
    API_TOKEN = st.secrets["API_TOKEN"]
    GRUP_ID = st.secrets["GRUP_ID"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"] # Yeni eklediğimiz secret
    
    creds_dict = st.secrets["gcp_service_account"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
except:
    st.error("⚠️ Ayar Hatası: Secrets kısmında DRIVE_FOLDER_ID veya diğer şifreler eksik!")
    st.stop()

def google_sheet_baglan(sayfa_adi="Sheet1"):
    client = gspread.authorize(creds)
    if sayfa_adi == "Sheet1":
        return client.open("Is_Takip_Sistemi").sheet1
    else:
        return client.open("Is_Takip_Sistemi").worksheet(sayfa_adi)

# --- YENİ: GOOGLE DRIVE YÜKLEME FONKSİYONU ---
def drive_yukle(uploaded_file):
    """Dosyayı Google Drive'a yükler ve linkini döndürür."""
    try:
        service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {
            'name': uploaded_file.name,
            'parents': [DRIVE_FOLDER_ID]
        }
        
        media = MediaIoBaseUpload(uploaded_file, mimetype=uploaded_file.type)
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        return file.get('webViewLink')
    except Exception as e:
        st.error(f"Drive Yükleme Hatası: {e}")
        return None

def numaralari_ayikla(tel_str):
    if not tel_str: return []
    tel_str = str(tel_str)
    ham_parcalar = re.split(r'[,\n]', tel_str)
    temiz_numaralar = []
    for parca in ham_parcalar:
        sadece_rakamlar = re.sub(r'\D', '', parca)
        son_hal = None
        if len(sadece_rakamlar) == 10: son_hal = "90" + sadece_rakamlar
        elif len(sadece_rakamlar) == 11 and sadece_rakamlar.startswith("0"): son_hal = "9" + sadece_rakamlar
        elif len(sadece_rakamlar) == 12 and sadece_rakamlar.startswith("90"): son_hal = sadece_rakamlar
        if son_hal: temiz_numaralar.append(son_hal)
    return temiz_numaralar

def whatsapp_gonder(chat_id, mesaj):
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    payload = {'chatId': chat_id, 'message': mesaj}
    try:
        requests.post(url, json=payload)
        return True
    except:
        return False

def verileri_getir(sayfa="Ana"):
    try:
        if sayfa == "Musteriler":
            sheet = google_sheet_baglan("Musteriler")
            return pd.DataFrame(sheet.get_all_records())
        else:
            sheet = google_sheet_baglan()
            return pd.DataFrame(sheet.get_all_records())
    except:
        return pd.DataFrame()

# --- SOL MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=70)
    st.markdown("### 🏛️ Müşavir Panel")
    secim = st.radio("MENÜ", ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi"])
    st.markdown("---")
    st.caption("v.3.0 | Drive Entegrasyonu")

# --- 1. DASHBOARD ---
if secim == "📊 Genel Bakış":
    st.header("📊 Ofis Durumu")
    df = verileri_getir()
    if not df.empty and "Durum" in df.columns:
        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam", len(df), border=True)
        c2.metric("✅ Biten", len(df[df["Durum"]=="Tamamlandi"]), border=True)
        c3.metric("⏳ Bekleyen", len(df[df["Durum"]!="Tamamlandi"]), border=True, delta_color="inverse")
        
        st.subheader("🗓 Son Hareketler")
        cols = ["Tarih", "Is Tanimi", "Durum"]
        if "Dosya" in df.columns: cols.append("Dosya")
        st.dataframe(df[cols].tail(5), use_container_width=True, hide_index=True, column_config={"Dosya": st.column_config.LinkColumn("Evrak")})

# --- 2. İŞ EKLE ---
elif secim == "➕ İş Ekle":
    st.header("📝 Yeni Görev")
    with st.container(border=True):
        with st.form("is_formu", clear_on_submit=True):
            col1, col2 = st.columns(2)
            tarih = col1.date_input("Tarih")
            saat = col2.time_input("Saat")
            
            df_m = verileri_getir("Musteriler")
            isimler = df_m["Ad Soyad"].tolist() if not df_m.empty else []
            musteri = st.selectbox("Mükellef", isimler)
            is_notu = st.text_input("Yapılacak İş", placeholder="Örn: SGK Girişi")
            
            st.markdown("---")
            sms = st.checkbox("📨 Mükellefe SMS gönder")
            kaydet = st.form_submit_button("✅ Kaydet")
            
            if kaydet and is_notu:
                sheet = google_sheet_baglan()
                tam_ad = f"{musteri} - {is_notu}"
                sheet.append_row([tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), tam_ad, "Gonderildi", "Bekliyor", "-"])
                whatsapp_gonder(GRUP_ID, f"📅 *YENİ İŞ*\n👤 {musteri}\n📌 {is_notu}")
                if sms and not df_m.empty:
                    satir = df_m[df_m["Ad Soyad"] == musteri]
                    if not satir.empty:
                        nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                        for n in nums: whatsapp_gonder(n, f"Sayın {musteri}, işleminiz ({is_notu}) alınmıştır.")
                st.success("Kayıt Başarılı!")

# --- 3. İŞ YÖNETİMİ ---
elif secim == "✅ İş Yönetimi":
    st.header("📋 Görev Yönetimi")
    if st.button("🔄 Yenile"): st.rerun()
    df = verileri_getir()
    if not df.empty and "Durum" in df.columns:
        bekleyenler = df[df["Durum"] != "Tamamlandi"]
        if not bekleyenler.empty:
            st.dataframe(bekleyenler[["Tarih", "Is Tanimi", "Durum"]], use_container_width=True, hide_index=True)
            st.divider()
            with st.container(border=True):
                st.subheader("🏁 İşi Tamamla")
                c1, c2 = st.columns([3,1])
                secilen = c1.selectbox("Hangi iş bitti?", bekleyenler["Is Tanimi"].tolist())
                final_sms = c1.checkbox("Müşteriye 'Bitti' mesajı gönder")
                if c2.button("Tamamla 🏁", use_container_width=True):
                    sheet = google_sheet_baglan()
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
                            st.success("İşlem tamamlandı!")
                            st.rerun()
                            break
        else:
            st.success("Bekleyen iş yok.")

# --- 4. MÜŞTERİ DOSYASI (DRIVE UPLOAD) ---
elif secim == "📂 Müşteri Arşivi":
    st.header("📂 Müşteri Evrak Sistemi")
    
    df_m = verileri_getir("Musteriler")
    if not df_m.empty:
        musteri = st.selectbox("Mükellef Seç:", df_m["Ad Soyad"].tolist())
        st.divider()
        
        df = verileri_getir()
        if not df.empty:
            ozel_veri = df[df["Is Tanimi"].str.contains(musteri, na=False)]
            cols_to_show = ["Tarih", "Is Tanimi", "Durum"]
            if "Dosya" in ozel_veri.columns: cols_to_show.append("Dosya")
            
            c_sol, c_sag = st.columns([2, 1])
            with c_sol:
                st.subheader("📜 Geçmiş Kayıtlar")
                st.dataframe(ozel_veri[cols_to_show], use_container_width=True, hide_index=True, column_config={"Dosya": st.column_config.LinkColumn("Evrak")})
            
            with c_sag:
                with st.container(border=True):
                    st.subheader("📎 Evrak Yükle")
                    # DOSYA YÜKLEME FORMU
                    with st.form("dosya_upload", clear_on_submit=True):
                        not_txt = st.text_area("Evrak/Görüşme Notu", placeholder="Örn: Vergi levhası yüklendi.")
                        
                        # BURASI YENİ: DOSYA YÜKLEME BUTONU
                        yuklenen_dosya = st.file_uploader("Dosya Seç (PDF, Resim vb.)", type=["pdf", "png", "jpg", "jpeg", "xlsx", "docx"])
                        
                        kaydet_btn = st.form_submit_button("💾 Drive'a Yükle ve Kaydet")
                        
                        if kaydet_btn:
                            if not_txt:
                                link = "-"
                                if yuklenen_dosya:
                                    with st.spinner("Dosya Drive'a yükleniyor..."):
                                        link = drive_yukle(yuklenen_dosya)
                                    
                                    if link:
                                        st.success("Dosya başarıyla yüklendi!")
                                    else:
                                        st.error("Dosya yüklenemedi!")
                                
                                sheet = google_sheet_baglan()
                                full_not = f"{musteri} - [NOT] {not_txt}"
                                tarih = datetime.now().strftime("%d.%m.%Y")
                                sheet.append_row([tarih, "-", full_not, "-", "Tamamlandi", link])
                                st.success("Kayıt deftere işlendi!")
                                st.rerun()
                            else:
                                st.warning("Lütfen bir not yazın.")
