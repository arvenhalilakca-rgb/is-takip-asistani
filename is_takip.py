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
import pdfplumber

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir Asistanı UX",
    page_icon="✨",
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
    
    /* Hızlı Not Alanı */
    .hizli-not {font-size: 12px; color: #bdc3c7;}
    
    /* Son İşlem Bilgisi */
    .son-islem {font-size: 11px; color: #7f8c8d; text-align: right; margin-top: 10px;}
    
    /* Mesaj Önizleme */
    .msg-preview {
        background-color: #e8f5e9; border-left: 5px solid #4caf50;
        padding: 10px; color: #2e7d32; font-style: italic; margin-top: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SESSION STATE (GEÇİCİ HAFIZA) ---
if 'hizli_not' not in st.session_state: st.session_state['hizli_not'] = ""
if 'son_islem' not in st.session_state: st.session_state['son_islem'] = "Henüz işlem yapılmadı."

# --- SABİT VERİLER ---
IS_SABLONLARI = [
    "KDV Beyannamesi", "Muhtasar Beyanname", "SGK İşe Giriş", "SGK İşten Çıkış", 
    "Geçici Vergi", "Yıllık Gelir Vergisi", "Kurumlar Vergisi", 
    "Ticaret Sicil İşlemleri", "Genel Danışmanlık", "Diğer (Elle Yaz)"
]

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
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try: requests.post(url, json={'chatId': chat_id, 'message': mesaj}); return True
    except: return False

def son_islem_guncelle(islem_adi):
    # Fikir 9: Son İşlem Bilgisi
    st.session_state['son_islem'] = f"{datetime.now().strftime('%H:%M')} - {islem_adi}"

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
    
    # Fikir 2: Hızlı Not Alanı
    st.markdown("### 📝 Hızlı Not")
    st.session_state['hizli_not'] = st.text_area("Unutmamak için not al:", value=st.session_state['hizli_not'], height=100, placeholder="Buraya yazılanlar silinmez...")
    
    st.markdown("---")
    
    # MENÜ
    menu = ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "💰 Finans & Kâr", "❓ Yardım / İpuçları"]
    secim = st.radio("MENÜ", menu)
    
    st.markdown("---")
    # Fikir 9: Son İşlem
    st.caption(f"⚡ Son İşlem:\n{st.session_state['son_islem']}")

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
            
            # Kâr
            df_c = verileri_getir("Cari")
            if not df_c.empty:
                df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
                net = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
                c4.metric("Net Kâr", f"{net:,.0f} TL")

        col1, col2 = st.columns(2)
        with col1: st.dataframe(df.tail(5), use_container_width=True, hide_index=True)
        with col2: st.bar_chart(df["Durum"].value_counts())

# --- 2. İŞ EKLE (ŞABLONLU) ---
elif secim == "➕ İş Ekle":
    st.title("📝 Hızlı İş Girişi")
    
    with st.container():
        with st.form("is_ekle"):
            c1, c2 = st.columns(2)
            tarih = c1.date_input("Tarih")
            saat = c2.time_input("Saat")
            
            df_m = verileri_getir("Musteriler")
            mus = st.selectbox("Mükellef", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
            
            # Fikir 5: Otomatik Şablonlar
            is_tipi = st.selectbox("İş Şablonu Seç:", IS_SABLONLARI)
            
            if is_tipi == "Diğer (Elle Yaz)":
                is_detay = st.text_input("Özel İş Tanımı Giriniz:")
                final_is_notu = is_detay
            else:
                final_is_notu = is_tipi
            
            # Fikir 7: Mesaj Önizleme
            sms_gonder = st.checkbox("Mükellefe WhatsApp Bilgisi Gönder")
            
            # Form içi buton
            submitted = st.form_submit_button("✅ Görevi Kaydet", type="primary")

        # Form dışı önizleme (Anlık tepki için form dışına koymak daha iyidir ama Streamlit'te form içi veri submit edilmeden dışarı çıkmaz.
        # En temiz yöntem: Kullanıcıya submit öncesi statik bir örnek göstermek)
        if sms_gonder:
            st.markdown(f"""
            <div class="msg-preview">
            📱 <b>WhatsApp Önizleme:</b><br>
            "Sayın {mus}, işleminiz ({final_is_notu if final_is_notu else '...'}) işleme alınmıştır."
            </div>
            """, unsafe_allow_html=True)

        if submitted:
            google_sheet_baglan("Sheet1").append_row([
                tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), 
                f"{mus} - {final_is_notu}", "Gonderildi", "Bekliyor", "-"
            ])
            onbellek_temizle()
            son_islem_guncelle(f"Yeni İş: {mus}")
            
            if sms_gonder and not df_m.empty:
                satir = df_m[df_m["Ad Soyad"] == mus]
                if not satir.empty:
                    nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                    msg = f"Sayın {mus}, işleminiz ({final_is_notu}) işleme alınmıştır."
                    for n in nums: whatsapp_gonder(n, msg)
            
            st.success("İş başarıyla kaydedildi!")

# --- 3. İŞ YÖNETİMİ (FİLTRELİ & ARAMALI) ---
elif secim == "✅ İş Yönetimi":
    st.title("📋 İş Takip Merkezi")
    
    if st.button("🔄 Yenile"): onbellek_temizle(); st.rerun()
    
    df = verileri_getir("Sheet1")
    if not df.empty:
        # Fikir 8: Basit Arama Çubuğu
        arama = st.text_input("🔍 İş veya Müşteri Ara:", placeholder="Örn: Ahmet, KDV...")
        
        # Fikir 6: Bugünün İşleri Filtresi
        bugun_filtre = st.checkbox("Sadece Bugünün İşlerini Göster")
        
        # Veriyi Filtrele
        df_goster = df.copy()
        
        if bugun_filtre:
            bugun_str = datetime.now().strftime("%d.%m.%Y")
            df_goster = df_goster[df_goster["Tarih"] == bugun_str]
        
        if arama:
            df_goster = df_goster[df_goster.astype(str).apply(lambda row: row.str.contains(arama, case=False).any(), axis=1)]
        
        # Fikir 3: Renk Kodlu Gösterim (Pandas Styler ile basit renklendirme)
        # Streamlit dataframe'i editlemeye izin verir, burada basitleştirilmiş gösterim yapıyoruz
        st.dataframe(
            df_goster[["Tarih", "Is Tanimi", "Durum"]], 
            use_container_width=True,
            column_config={
                "Durum": st.column_config.SelectboxColumn(
                    "Durum",
                    help="İşin durumu",
                    width="medium",
                    options=["Bekliyor", "Tamamlandi", "İptal", "İşlemde"],
                    required=True,
                )
            },
            hide_index=True
        )
        
        # İş Bitirme Alanı
        bekleyenler = df[df["Durum"] != "Tamamlandi"]["Is Tanimi"].tolist()
        if bekleyenler:
            st.markdown("---")
            with st.container():
                c1, c2 = st.columns([3,1])
                biten_is = c1.selectbox("Hızlı İş Bitir:", bekleyenler)
                if c2.button("Kapat 🏁"):
                    rows = google_sheet_baglan("Sheet1").get_all_values()
                    for i, r in enumerate(rows):
                        if len(r) > 2 and r[2] == biten_is:
                            google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Tamamlandi")
                            onbellek_temizle()
                            son_islem_guncelle(f"İş Bitti: {biten_is}")
                            st.success("İş kapatıldı!")
                            st.rerun()
                            break

# --- 4. ARŞİV (AKILLI KOPYALA) ---
elif secim == "📂 Müşteri Arşivi":
    st.title("📂 Müşteri Kartvizitleri")
    
    df_m = verileri_getir("Musteriler")
    if not df_m.empty:
        # Fikir 8: Arama burada da var
        arama_m = st.text_input("🔍 Müşteri Ara:", placeholder="Ad Soyad...")
        if arama_m:
            df_m = df_m[df_m["Ad Soyad"].str.contains(arama_m, case=False, na=False)]
            
        secilen_m = st.selectbox("Detay Görüntüle:", df_m["Ad Soyad"].tolist())
        
        if secilen_m:
            bilgi = df_m[df_m["Ad Soyad"] == secilen_m].iloc[0]
            
            st.markdown("### 📋 Müşteri Künyesi (Kopyalamak için sağ üstteki ikona bas)")
            
            # Fikir 1 & 4: Akıllı Kopyala Butonları (st.code kullanarak)
            # Telefon
            c1, c2, c3 = st.columns(3)
            with c1:
                st.caption("📞 Telefon")
                st.code(bilgi.get("Telefon", "-"), language="text")
            with c2:
                st.caption("🆔 TC / VKN")
                st.code(bilgi.get("TC", "-"), language="text")
            with c3:
                st.caption("💰 Aylık Ücret")
                st.code(f"{bilgi.get('Ucret', '-')} TL", language="text")
            
            # Fikir 4: Tek Blok Özet (Mail atmak veya bir yere yapıştırmak için)
            st.caption("📝 Tam Özet (Kopyala)")
            ozet_blok = f"""
            Müşteri: {bilgi.get('Ad Soyad')}
            Tel: {bilgi.get('Telefon')}
            TC/VKN: {bilgi.get('TC')}
            Sorumlu: {bilgi.get('Sorumlu')}
            """
            st.code(ozet_blok, language="text")

# --- 5. FİNANS (Kısa tutuldu) ---
elif secim == "💰 Finans & Kâr":
    st.title("💰 Finans")
    df_c = verileri_getir("Cari")
    if not df_c.empty:
        df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
        net = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
        st.metric("Net Kâr", f"{net:,.0f} TL")
        st.dataframe(df_c)

# --- 10. YARDIM / İPUÇLARI ---
elif secim == "❓ Yardım / İpuçları":
    st.title("❓ Ofis Asistanı Kullanım Rehberi")
    
    with st.expander("📌 Yeni Müşteri Nasıl Eklenir?"):
        st.write("Google Sheets > 'Musteriler' sayfasına gidip en alt satıra Ad, Tel, TC bilgilerini girin. Sayfayı yenileyince burada görünür.")
    
    with st.expander("📌 İş Nasıl Kapatılır?"):
        st.write("'İş Yönetimi' menüsüne gidin. Aşağıdaki açılır listeden işi seçip 'Kapat' butonuna basın. Durum 'Tamamlandi' olacaktır.")
    
    with st.expander("📌 Finansal Veri Girişi"):
        st.write("'Finans' menüsünden Tahsilat veya Gider girebilirsiniz. KDV Beyannamesini okutmak için PDF yükleyebilirsiniz.")
        
    st.info("💡 İpucu: Sol menüdeki 'Hızlı Not' alanı size özeldir. Oraya aldığınız notlar silinmez.")
