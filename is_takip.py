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
import io
from streamlit_option_menu import option_menu

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir Asistanı Pro",
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
    .borclu-uyari {background-color: #ffebee; color: #c0392b; padding: 15px; border-radius: 10px; border-left: 5px solid #e74c3c; font-weight: bold;}
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
RESMI_TATILLER = ["01.01", "23.04", "01.05", "19.05", "15.07", "30.08", "29.10"]
MESAJ_SABLONLARI = {
    "Tasdik Ödenmedi (SERT)": "Sayın {isim}, 2026 yılı defter tasdik ücretinizi ödemediğiniz için defterleriniz notere teslim EDİLMEMİŞTİR. Cezalı duruma düşmemek ve mağduriyet yaşamamak için ödemenizi acilen yapmanızı önemle rica ederiz.",
    "Genel Bilgilendirme": "Sayın {isim}, ofisimizle ilgili bilgilendirme..."
}

# --- SESSION ---
if 'hizli_not' not in st.session_state: st.session_state['hizli_not'] = ""
if 'sessiz_mod' not in st.session_state: st.session_state['sessiz_mod'] = False
# Excel verilerini hafızada tutmak için
if 'tasdik_data' not in st.session_state: st.session_state['tasdik_data'] = None

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
    if st.session_state['sessiz_mod']: return False
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try: requests.post(url, json={'chatId': chat_id, 'message': mesaj}); return True
    except: return False

def numaralari_ayikla(tel_str):
    if not tel_str: return []
    tel_str = str(tel_str)
    if tel_str == "nan" or tel_str == "None": return []
    ham_parcalar = re.split(r'[,\n/]', tel_str)
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
    st.markdown("<h3 style='text-align:center'>MÜŞAVİR PRO 💎</h3>", unsafe_allow_html=True)
    df_m = verileri_getir("Musteriler")
    p_list = ["Admin"]
    if not df_m.empty and "Sorumlu" in df_m.columns:
        p_list += [p for p in df_m["Sorumlu"].unique().tolist() if str(p) not in ["nan", ""]]
    aktif = st.selectbox("👤 Kullanıcı", list(set(p_list)))
    
    st.markdown("---")
    secim = option_menu(
        menu_title=None,
        options=["Genel Bakış", "İş Ekle", "İş Yönetimi", "Mesaj Merkezi", "Tasdik Robotu", "Ayarlar"],
        icons=["house", "plus-circle", "kanban", "chat-dots", "robot", "gear"],
        menu_icon="cast", default_index=0,
        styles={"container": {"padding": "0!important", "background-color": "#ffffff"}, "nav-link": {"font-size": "14px"}}
    )
    
    st.session_state['sessiz_mod'] = st.toggle("🔕 Sessiz Mod", value=st.session_state['sessiz_mod'])

# --- 1. GENEL BAKIŞ ---
if secim == "Genel Bakış":
    st.title("📊 Yönetim Kokpiti")
    df = verileri_getir("Sheet1")
    if not df.empty and "Durum" in df.columns:
        c1, c2, c3 = st.columns(3)
        c1.metric("Bekleyen", len(df[df["Durum"]!="Tamamlandi"]))
        c2.metric("Tamamlanan", len(df[df["Durum"]=="Tamamlandi"]))
        c3.metric("Toplam İş", len(df))
    else: st.info("Sistemde kayıtlı iş yok.")

# --- 2. İŞ EKLE ---
elif secim == "İş Ekle":
    st.title("📝 İş Girişi")
    with st.form("is_ekle"):
        c1, c2 = st.columns(2); t = c1.date_input("Tarih"); s = c2.time_input("Saat")
        mus = st.selectbox("Mükellef", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
        notu = st.text_input("Açıklama", "KDV Beyannamesi")
        p = st.selectbox("Sorumlu", p_list)
        if st.form_submit_button("Kaydet"):
            google_sheet_baglan("Sheet1").append_row([t.strftime("%d.%m.%Y"), s.strftime("%H:%M"), f"{mus} - {notu}", "Gonderildi", "Bekliyor", "-", p])
            st.success("Kaydedildi!")

# --- 3. İŞ YÖNETİMİ ---
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
                    google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Tamamlandi"); st.success("Bitti!"); st.rerun()

# --- 4. MESAJ MERKEZİ ---
elif secim == "Mesaj Merkezi":
    st.title("💬 Mesaj")
    secilen = st.selectbox("Müşteri", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
    msg = st.text_area("İçerik", "Mesajınızı buraya yazın...")
    if st.button("Gönder"):
        satir = df_m[df_m["Ad Soyad"] == secilen]
        if not satir.empty:
            for t in numaralari_ayikla(satir.iloc[0]["Telefon"]): whatsapp_gonder(t, msg)
            st.success("Gönderildi!")

# --- 5. TASDİK ROBOTU (YENİ SİSTEM) ---
elif secim == "Tasdik Robotu":
    st.title("🤖 Tasdik Tahsilat Robotu")
    
    # 1. DOSYA YÜKLEME KISMI
    col_up, col_info = st.columns([1, 2])
    with col_up:
        uploaded_file = st.file_uploader("Listeyi Yükle (Excel/CSV)", type=["xlsx", "xls", "csv"])
    
    # Dosya yüklendiğinde ve henüz hafızaya alınmadıysa
    if uploaded_file:
        if st.session_state['tasdik_data'] is None:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_raw = pd.read_csv(uploaded_file)
                else:
                    df_raw = pd.read_excel(uploaded_file)
                
                # Gerekli Sütun Kontrolü
                if "Ünvan / Ad Soyad" in df_raw.columns:
                    # Yeni bir sütun ekle: "Tahsil_Edildi_Mi"
                    # Eğer "Para Alındı mı" doluysa True, boşsa False yap
                    if "Para Alındı mı" in df_raw.columns:
                        df_raw["Sistem_Tahsilat"] = df_raw["Para Alındı mı"].apply(lambda x: True if pd.notna(x) and str(x).strip() != "" else False)
                    else:
                        df_raw["Sistem_Tahsilat"] = False # Sütun yoksa herkes borçlu
                    
                    st.session_state['tasdik_data'] = df_raw
                    st.success("Liste Yüklendi! Şimdi aşağıdan yönetebilirsin.")
                    st.rerun()
                else:
                    st.error("Dosyada 'Ünvan / Ad Soyad' sütunu bulunamadı.")
            except Exception as e:
                st.error(f"Hata: {e}")

    # 2. LİSTE YÖNETİMİ
    if st.session_state['tasdik_data'] is not None:
        df_islem = st.session_state['tasdik_data']
        
        # Filtreleme (Sadece Borçluları Göster veya Tümü)
        gosterim_modu = st.radio("Görünüm:", ["Sadece Ödemeyenleri Göster (İşlem Yapılacaklar)", "Tüm Listeyi Göster"], horizontal=True)
        
        if "Sadece" in gosterim_modu:
            # Sadece ödememiş olanları (False) filtrele
            df_goster = df_islem[df_islem["Sistem_Tahsilat"] == False]
        else:
            df_goster = df_islem

        st.markdown("##### 👇 Ödemesini aldığınız kişilerin yanındaki kutucuğu işaretleyin:")
        
        # EDİTÖR: KULLANICININ TİK ATABİLECEĞİ ALAN
        # num_rows="dynamic" kapalı, sadece var olanları düzenle
        edited_df = st.data_editor(
            df_goster,
            column_config={
                "Sistem_Tahsilat": st.column_config.CheckboxColumn(
                    "Tahsil Edildi mi?",
                    help="Ödeme alındıysa işaretleyin, listeden düşsün.",
                    default=False,
                ),
                "Ünvan / Ad Soyad": st.column_config.TextColumn("Mükellef", disabled=True),
                "1.NUMARA": st.column_config.TextColumn("Telefon", disabled=True),
                "Defter Tasdik Ücreti": st.column_config.NumberColumn("Tutar", disabled=True)
            },
            disabled=["Ünvan / Ad Soyad", "1.NUMARA", "Para Alındı mı", "Vergi Dairesi"], # Sadece checkbox değişsin
            hide_index=True,
            use_container_width=True
        )

        # DEĞİŞİKLİKLERİ KAYDETME MANTIĞI
        # Streamlit data_editor, edited_df içinde değişiklikleri tutar.
        # Bunu ana session_state'e geri yazmamız lazım.
        
        if st.button("💾 Değişiklikleri Kaydet & Listeyi Güncelle"):
            # Güncellenmiş satırları ana veriye işle
            # Index üzerinden eşleştirme yapıyoruz
            st.session_state['tasdik_data'].update(edited_df)
            st.success("Liste Güncellendi! Ödeyenler mesaj listesinden çıkarıldı.")
            st.rerun()

        st.divider()

        # 3. MESAJ GÖNDERME ALANI
        # Mesaj sadece "Sistem_Tahsilat" == False olanlara gidecek
        kalan_borclular = st.session_state['tasdik_data'][st.session_state['tasdik_data']["Sistem_Tahsilat"] == False]
        
        st.markdown(f"<div class='borclu-uyari'>🚨 Mesaj Gönderilecek Kişi Sayısı: {len(kalan_borclular)}</div>", unsafe_allow_html=True)
        
        mesaj_taslagi = st.text_area("Gidecek Mesaj Şablonu:", value=MESAJ_SABLONLARI["Tasdik Ödenmedi (SERT)"], height=100)
        
        if st.button("🚀 KALAN BORÇLULARA MESAJI GÖNDER", type="primary"):
            if len(kalan_borclular) > 0:
                bar = st.progress(0)
                basarili = 0
                hatali = 0
                
                for i, row in kalan_borclular.iterrows():
                    isim = row["Ünvan / Ad Soyad"]
                    tel_ham = str(row.get("1.NUMARA", ""))
                    
                    tels = numaralari_ayikla(tel_ham)
                    
                    if tels:
                        kisiye_ozel_mesaj = mesaj_taslagi.replace("{isim}", str(isim))
                        for t in tels:
                            whatsapp_gonder(t, kisiye_ozel_mesaj)
                        basarili += 1
                    else:
                        hatali += 1
                    
                    bar.progress((i + 1) / len(kalan_borclular))
                    time.sleep(0.5)
                
                st.success(f"Tamamlandı! {basarili} kişiye mesaj gönderildi.")
            else:
                st.success("Gönderilecek kimse kalmadı, herkes ödemiş! 🎉")

    # Temizle Butonu
    if st.button("🔄 Yeni Liste Yüklemek İçin Sıfırla"):
        st.session_state['tasdik_data'] = None
        st.rerun()

# --- 6. AYARLAR ---
elif secim == "Ayarlar":
    st.title("⚙️ Ayarlar")
    if st.button("Yedek Al"): st.download_button("İndir", excel_yedek_olustur(verileri_getir("Sheet1"), df_m, verileri_getir("Cari")), "Yedek.xlsx")
