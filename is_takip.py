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

# --- TASARIM ---
st.markdown("""
    <style>
    .stApp {background-color: #f0f2f6;}
    [data-testid="stSidebar"] {background-color: #1e293b;}
    [data-testid="stSidebar"] * {color: white !important;}
    div.block-container {padding-top: 1rem;}
    .stButton>button {width: 100%; border-radius: 6px; font-weight: bold;}
    .stRadio > div {flex-direction: row;} /* Radyo butonları yan yana */
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

def google_sheet_baglan(sayfa_adi="Sheet1"):
    client = gspread.authorize(creds)
    if sayfa_adi == "Sheet1":
        return client.open("Is_Takip_Sistemi").sheet1
    else:
        return client.open("Is_Takip_Sistemi").worksheet(sayfa_adi)

def drive_yukle(uploaded_file):
    try:
        service = build('drive', 'v3', credentials=creds)
        file_metadata = {'name': uploaded_file.name, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(uploaded_file, mimetype=uploaded_file.type)
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file.get('webViewLink')
    except Exception as e:
        return None

def whatsapp_gonder(chat_id, mesaj):
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    payload = {'chatId': chat_id, 'message': mesaj}
    try:
        requests.post(url, json=payload)
        return True
    except:
        return False

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

def verileri_getir(sayfa="Ana"):
    try:
        sheet = google_sheet_baglan(sayfa)
        return pd.DataFrame(sheet.get_all_records())
    except:
        return pd.DataFrame()

# --- MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=70)
    st.markdown("### 🏛️ Müşavir Panel")
    secim = st.radio("MENÜ", ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "🏢 Kuruluş Sihirbazı"])
    st.markdown("---")
    st.caption("v.4.0 | Kuruluş Modülü")

# --- 1. DASHBOARD ---
if secim == "📊 Genel Bakış":
    st.header("📊 Ofis Durumu")
    df = verileri_getir("Sheet1")
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
            sms = st.checkbox("📨 Mükellefe SMS gönder")
            
            if st.form_submit_button("✅ Kaydet"):
                sheet = google_sheet_baglan("Sheet1")
                tam_ad = f"{musteri} - {is_notu}"
                sheet.append_row([tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), tam_ad, "Gonderildi", "Bekliyor", "-"])
                whatsapp_gonder(GRUP_ID, f"📅 *YENİ İŞ*\n👤 {musteri}\n📌 {is_notu}")
                if sms and not df_m.empty:
                    satir = df_m[df_m["Ad Soyad"] == musteri]
                    if not satir.empty:
                        nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                        for n in nums: whatsapp_gonder(n, f"Sayın {musteri}, işleminiz ({is_notu}) alınmıştır.")
                st.success("Kaydedildi!")

# --- 3. İŞ YÖNETİMİ ---
elif secim == "✅ İş Yönetimi":
    st.header("📋 Görev Yönetimi")
    if st.button("🔄 Yenile"): st.rerun()
    df = verileri_getir("Sheet1")
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
                            st.success("İşlem tamamlandı!")
                            st.rerun()
                            break
        else:
            st.success("Bekleyen iş yok.")

# --- 4. MÜŞTERİ ARŞİVİ ---
elif secim == "📂 Müşteri Arşivi":
    st.header("📂 Müşteri Evrak Sistemi")
    df_m = verileri_getir("Musteriler")
    if not df_m.empty:
        musteri = st.selectbox("Mükellef Seç:", df_m["Ad Soyad"].tolist())
        st.divider()
        df = verileri_getir("Sheet1")
        if not df.empty:
            ozel_veri = df[df["Is Tanimi"].str.contains(musteri, na=False)]
            cols = ["Tarih", "Is Tanimi", "Durum"]
            if "Dosya" in ozel_veri.columns: cols.append("Dosya")
            
            c_sol, c_sag = st.columns([2, 1])
            with c_sol:
                st.subheader("📜 Geçmiş Kayıtlar")
                st.dataframe(ozel_veri[cols], use_container_width=True, hide_index=True, column_config={"Dosya": st.column_config.LinkColumn("Evrak")})
            
            with c_sag:
                with st.container(border=True):
                    st.subheader("📎 Evrak Yükle")
                    with st.form("dosya_upload"):
                        not_txt = st.text_area("Not/Açıklama")
                        yuklenen = st.file_uploader("Dosya Seç")
                        if st.form_submit_button("💾 Kaydet"):
                            link = "-"
                            if yuklenen:
                                with st.spinner("Yükleniyor..."):
                                    link = drive_yukle(yuklenen)
                            sheet = google_sheet_baglan("Sheet1")
                            sheet.append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{musteri} - [NOT] {not_txt}", "-", "Tamamlandi", link])
                            st.success("Kaydedildi!")
                            st.rerun()

# --- 5. KURULUŞ SİHİRBAZI (YENİ!) ---
elif secim == "🏢 Kuruluş Sihirbazı":
    st.header("🏗️ Yeni İşletme Kuruluş Formu")
    st.info("Müşteriyle görüşme esnasında bu formu doldurarak hiçbir detayı atlamazsın.")

    with st.container(border=True):
        # Müşteri Adı Girişi (Listede yoksa elle yazsın)
        col_ad, col_tel = st.columns(2)
        aday_musteri = col_ad.text_input("Görüşülen Kişi / Aday Müşteri Adı")
        aday_tel = col_tel.text_input("Telefon Numarası")

        st.markdown("---")
        
        # 1. TEMEL BİLGİLER
        c1, c2 = st.columns(2)
        sirket_turu = c1.radio("📌 Şirket Türü", ["Şahıs İşletmesi", "Limited Şirket", "Anonim Şirket"], horizontal=True)
        vergi_usulu = c2.radio("📊 Vergi Usulü", ["Gerçek Usul", "Basit Usul", "Kurumlar Vergisi"], horizontal=True)

        st.markdown("---")

        # 2. İŞYERİ VE FAALİYET
        c3, c4 = st.columns(2)
        isyeri_tipi = c3.selectbox("🏠 İşyeri Durumu (Stopaj İçin)", ["Kiralık (Stopajlı)", "Kendine Ait (Tapulu)", "Sanal Ofis", "Aile Bireyine Ait (Emsal Kira)"])
        faaliyet = c4.text_area("🛠️ Yapılacak İş (NACE için detaylı)", placeholder="Örn: E-ticaret üzerinden kıyafet satışı...")

        st.markdown("---")

        # 3. KRİTİK SORULAR
        st.subheader("⚠️ Kritik Kontroller")
        col_k1, col_k2, col_k3 = st.columns(3)
        sgk_durumu = col_k1.selectbox("SGK Durumu (Bağkur Planı)", ["Başka Yerde 4a'lı (Sigortalı)", "Emekli", "Hiçbiri (Bağkur Başlar)", "Genç Girişimci Adayı"])
        arac = col_k2.radio("🚗 İşletmeye Araç Kaydı?", ["Yok", "Binek Araç", "Ticari Araç"])
        yazar_kasa = col_k3.radio("📠 Yazar Kasa Gerekli mi?", ["Evet", "Hayır (E-Fatura)", "Belli Değil"])

        st.markdown("---")
        
        # SONUÇ VE KAYIT
        notlar = st.text_area("📝 Ekstra Notlar / Fiyat Teklifi", placeholder="Defter tasdik ücreti 5000 TL söylendi...")
        
        kaydet_btn = st.button("💾 Görüşmeyi Kaydet ve Dosya Oluştur", use_container_width=True, type="primary")

        if kaydet_btn and aday_musteri:
            # Rapor Metni Oluştur
            rapor = f"""
            GÖRÜŞME RAPORU ({datetime.now().strftime("%d.%m.%Y")})
            ------------------------------------------
            Müşteri: {aday_musteri} ({aday_tel})
            Tür: {sirket_turu} | Usul: {vergi_usulu}
            İşyeri: {isyeri_tipi}
            Faaliyet: {faaliyet}
            ------------------------------------------
            SGK: {sgk_durumu}
            Araç: {arac} | ÖKC: {yazar_kasa}
            ------------------------------------------
            ÖZEL NOTLAR: {notlar}
            """
            
            # Google Sheet'e Kaydet
            sheet = google_sheet_baglan("Sheet1")
            # Tarih, Saat, İş (Rapor), Mesaj, Durum, Dosya
            sheet.append_row([
                datetime.now().strftime("%d.%m.%Y"), 
                datetime.now().strftime("%H:%M"), 
                f"{aday_musteri} - [KURULUŞ GÖRÜŞMESİ] (Detaylar Kaydedildi)", 
                "-", 
                "Tamamlandi", 
                "-"
            ])
            
            # Ayrıca WhatsApp Grubuna Rapor At
            whatsapp_gonder(GRUP_ID, f"🆕 *YENİ KURULUŞ GÖRÜŞMESİ*\n{rapor}")
            
            st.success("Görüşme başarıyla kaydedildi! Gruba rapor gönderildi.")
            st.code(rapor, language="text") # Ekrana da raporu basar
