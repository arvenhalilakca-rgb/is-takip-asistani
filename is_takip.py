import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import requests
import pandas as pd
import re
from datetime import datetime

# --- SAYFA AYARLARI (BROWSER TAB'I) ---
st.set_page_config(
    page_title="Müşavir Asistanı Pro",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- PREMIUM TASARIM (CSS ENJEKSİYONU) ---
st.markdown("""
    <style>
    /* Ana Arka Plan */
    .stApp {
        background-color: #F8F9FA;
        font-family: 'Helvetica', sans-serif;
    }
    
    /* Sidebar (Yan Menü) Tasarımı */
    [data-testid="stSidebar"] {
        background-color: #2C3E50; /* Koyu Lacivert */
    }
    [data-testid="stSidebar"] * {
        color: #ECF0F1 !important; /* Açık Gri Yazı */
    }
    
    /* Metrik Kartları (Sayıların olduğu kutular) */
    div[data-testid="stMetricValue"] {
        font-size: 28px;
        color: #2C3E50;
        font-weight: bold;
    }
    
    /* Form ve Konteyner Kutuları (Kart Görünümü) */
    [data-testid="stForm"], div.stContainer {
        background-color: #FFFFFF;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); /* Hafif Gölge */
        border: 1px solid #E0E0E0;
    }
    
    /* Buton Tasarımı */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        font-weight: 600;
        border: none;
        transition: all 0.3s ease;
    }
    
    /* Birincil Buton (Kaydet vb.) */
    button[kind="primary"] {
        background: linear-gradient(90deg, #1abc9c 0%, #16a085 100%);
        color: white;
    }
    
    /* Tablo Başlıkları */
    thead tr th:first-child {display:none}
    tbody th {display:none}
    
    /* Başlıkların Altındaki Çizgiler */
    h1, h2, h3 {
        color: #34495e;
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

# --- SOL MENÜ (SIDEBAR) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    st.markdown("### 🏛️ Müşavir Panel")
    st.markdown("---")
    
    # Menüyü Radyo Yerine Daha Şık Bir Selectbox ile Yapabiliriz veya Radyo Kalabilir
    secim = st.radio(
        "MENÜ", 
        ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "🏢 Kuruluş Sihirbazı"]
    )
    
    st.markdown("---")
    st.info(f"📅 {datetime.now().strftime('%d.%m.%Y')}")
    st.caption("v.Executive | Pro Design")

# --- 1. DASHBOARD ---
if secim == "📊 Genel Bakış":
    st.title("📊 Yönetim Paneli")
    st.markdown("Ofisinizin güncel performans özeti aşağıdadır.")
    
    df = verileri_getir("Sheet1")
    if not df.empty and "Durum" in df.columns:
        # Metrikleri Kart İçinde Göster
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Toplam İş", len(df))
            c2.metric("✅ Tamamlanan", len(df[df["Durum"]=="Tamamlandi"]))
            c3.metric("⏳ Bekleyen", len(df[df["Durum"]!="Tamamlandi"]))
            
            # Tahsilat eklendiyse onu da gösteririz, yoksa boş geçer
            bekleyen_tahsilat = 0
            if "Tahsilat" in df.columns:
                bekleyen_tahsilat = len(df[df["Tahsilat"]=="Bekliyor ❌"])
            c4.metric("💰 Açık Bakiye", f"{bekleyen_tahsilat} Adet", delta_color="inverse")

        st.markdown("### 🗓 Son Hareketler")
        with st.container():
            cols = ["Tarih", "Is Tanimi", "Durum"]
            if "Dosya" in df.columns: cols.append("Dosya")
            st.dataframe(
                df[cols].tail(8), 
                use_container_width=True, 
                hide_index=True, 
                column_config={"Dosya": st.column_config.LinkColumn("Evrak")}
            )

# --- 2. İŞ EKLE ---
elif secim == "➕ İş Ekle":
    st.title("📝 Yeni Görev Girişi")
    
    with st.form("is_formu", clear_on_submit=True):
        st.subheader("İş Detayları")
        col1, col2 = st.columns(2)
        tarih = col1.date_input("Tarih")
        saat = col2.time_input("Saat")
        
        df_m = verileri_getir("Musteriler")
        isimler = df_m["Ad Soyad"].tolist() if not df_m.empty else []
        musteri = st.selectbox("Mükellef Seçiniz", isimler)
        is_notu = st.text_input("Yapılacak İş Tanımı", placeholder="Örn: SGK İşe Giriş Bildirgesi")
        
        st.markdown("---")
        sms = st.checkbox("📨 Mükellefe bilgilendirme mesajı gönderilsin mi?")
        
        # Primary Buton Rengi CSS ile değiştirildi
        if st.form_submit_button("✅ Görevi Kaydet", type="primary"):
            sheet = google_sheet_baglan("Sheet1")
            tam_ad = f"{musteri} - {is_notu}"
            sheet.append_row([tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), tam_ad, "Gonderildi", "Bekliyor", "-"])
            whatsapp_gonder(GRUP_ID, f"📅 *YENİ İŞ*\n👤 {musteri}\n📌 {is_notu}")
            if sms and not df_m.empty:
                satir = df_m[df_m["Ad Soyad"] == musteri]
                if not satir.empty:
                    nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                    for n in nums: whatsapp_gonder(n, f"Sayın {musteri}, işleminiz ({is_notu}) işleme alınmıştır.")
            st.success("Kayıt Başarılı!")

# --- 3. İŞ YÖNETİMİ ---
elif secim == "✅ İş Yönetimi":
    st.title("📋 Görev Kontrol Merkezi")
    
    col_btn, col_bos = st.columns([1,4])
    if col_btn.button("🔄 Listeyi Yenile"): st.rerun()
    
    df = verileri_getir("Sheet1")
    if not df.empty and "Durum" in df.columns:
        bekleyenler = df[df["Durum"] != "Tamamlandi"]
        
        if not bekleyenler.empty:
            with st.container():
                st.dataframe(bekleyenler[["Tarih", "Is Tanimi", "Durum"]], use_container_width=True, hide_index=True)
            
            st.markdown("### 🏁 İş Bitirme")
            with st.container():
                c1, c2 = st.columns([3,1])
                secilen = c1.selectbox("Tamamlanan İşi Seç:", bekleyenler["Is Tanimi"].tolist())
                final_sms = c1.checkbox("Müşteriye 'Tamamlandı' mesajı gönder")
                
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
                            st.success("İşlem başarıyla kapatıldı!")
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
            
            c_sol, c_sag = st.columns([2, 1])
            with c_sol:
                st.subheader("Geçmiş Hareketler")
                with st.container():
                    st.dataframe(
                        ozel_veri[cols], 
                        use_container_width=True, 
                        hide_index=True, 
                        column_config={"Dosya": st.column_config.LinkColumn("Evrak Linki")}
                    )
            
            with c_sag:
                st.subheader("Yeni Kayıt / Evrak")
                with st.form("dosya_upload"):
                    not_txt = st.text_area("Açıklama / Not")
                    yuklenen = st.file_uploader("Dosya (PDF/Resim)")
                    if st.form_submit_button("Arşive Kaydet 💾", type="primary"):
                        link = "-"
                        if yuklenen:
                            with st.spinner("Drive'a Yükleniyor..."):
                                link = drive_yukle(yuklenen)
                        sheet = google_sheet_baglan("Sheet1")
                        sheet.append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{musteri} - [NOT] {not_txt}", "-", "Tamamlandi", link])
                        st.success("Kaydedildi!")
                        st.rerun()

# --- 5. KURULUŞ SİHİRBAZI (PRO TASARIM) ---
elif secim == "🏢 Kuruluş Sihirbazı":
    st.title("🏢 Şirket Kuruluş Sihirbazı")
    st.markdown("Aşağıdaki adımları takip ederek eksiksiz bir kuruluş planı oluşturun.")

    with st.container():
        # Aday Girişi
        col_ad, col_tel = st.columns(2)
        aday_musteri = col_ad.text_input("Görüşülen Kişi / Firma Adı")
        aday_tel = col_tel.text_input("İletişim Numarası")

    if aday_musteri:
        with st.form("kurulus_form"):
            # Bölüm 1: Şirket Yapısı (Expander ile gizle/göster)
            with st.expander("1. Şirket Yapısı ve Vergi", expanded=True):
                c1, c2 = st.columns(2)
                sirket_turu = c1.radio("Şirket Türü", ["Şahıs İşletmesi", "Limited Şirket", "Anonim Şirket"])
                vergi_usulu = c2.radio("Vergi Usulü", ["Gerçek Usul", "Basit Usul", "Kurumlar Vergisi"])

            # Bölüm 2: Operasyonel Detaylar
            with st.expander("2. İşyeri ve Faaliyet Bilgileri"):
                c3, c4 = st.columns(2)
                isyeri_tipi = c3.selectbox("İşyeri Durumu", ["Kiralık (Stopajlı)", "Kendine Ait (Tapulu)", "Sanal Ofis", "Aile Bireyine Ait"])
                faaliyet = c4.text_area("Faaliyet Konusu (NACE)", placeholder="Örn: İnşaat malzemeleri toptan satışı")

            # Bölüm 3: Teknik Kontroller
            with st.expander("3. SGK, Araç ve ÖKC"):
                col_k1, col_k2, col_k3 = st.columns(3)
                sgk_durumu = col_k1.selectbox("SGK Durumu", ["Başka Yerde Sigortalı", "Emekli", "Hiçbiri (Bağkur)", "Genç Girişimci"])
                arac = col_k2.radio("Araç Kaydı?", ["Yok", "Binek", "Ticari"])
                yazar_kasa = col_k3.radio("Yazar Kasa?", ["Evet", "Hayır", "Belli Değil"])

            # Bölüm 4: Finansal (En Önemlisi)
            with st.expander("4. Ücret ve Yasal Bildirimler", expanded=True):
                st.info("Lütfen anlaşılan net tutarları giriniz.")
                c_fin1, c_fin2, c_fin3 = st.columns(3)
                muhasebe_ucreti = c_fin1.text_input("Aylık Muhasebe Ücreti", placeholder="3.000 TL")
                acilis_bedeli = c_fin2.text_input("Kuruluş Hizmet Bedeli", placeholder="5.000 TL")
                faydalanici = c_fin3.radio("Gerçek Faydalanıcı Bildirimi?", ["Evet, Yapılacak", "Hayır / Gerek Yok"])
                
                notlar = st.text_area("Ekstra Notlar")

            # Kaydet Butonu
            submitted = st.form_submit_button("💾 Görüşmeyi ve Sözleşmeyi Kaydet", type="primary")

            if submitted:
                # Rapor Oluşturma ve Kayıt Kodları (Değişmedi, sadece tasarım iyileşti)
                rapor = f"""
                GÖRÜŞME RAPORU ({datetime.now().strftime("%d.%m.%Y")})
                ------------------------------------------
                Müşteri: {aday_musteri} ({aday_tel})
                Tür: {sirket_turu} | Usul: {vergi_usulu}
                ------------------------------------------
                💰 FİNANSAL
                Aylık: {muhasebe_ucreti} | Açılış: {acilis_bedeli}
                ------------------------------------------
                TEKNİK DETAY
                SGK: {sgk_durumu} | İşyeri: {isyeri_tipi}
                Not: {notlar}
                """
                sheet = google_sheet_baglan("Sheet1")
                sheet.append_row([
                    datetime.now().strftime("%d.%m.%Y"), 
                    datetime.now().strftime("%H:%M"), 
                    f"{aday_musteri} - [AÇILIŞ] (Detaylar Kaydedildi)", "-", "Tamamlandi", "-"
                ])
                whatsapp_gonder(GRUP_ID, f"🆕 *YENİ MÜŞTERİ GÖRÜŞMESİ*\n{rapor}")
                st.success("Tebrikler! Görüşme başarıyla kaydedildi.")
                st.code(rapor)
