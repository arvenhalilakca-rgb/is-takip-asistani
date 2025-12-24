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
    
    /* Özel Buton Tasarımı */
    .stButton>button {
        border-radius: 8px; font-weight: bold; border: none; 
        transition: all 0.2s ease; width: 100%;
    }
    
    /* Satır Kartı Tasarımı */
    .kisi-karti {
        background-color: white; padding: 10px; border-radius: 8px; 
        border-left: 5px solid #e74c3c; margin-bottom: 5px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    .odendi-karti {
        background-color: #e8f5e9; padding: 10px; border-radius: 8px;
        border-left: 5px solid #2ecc71; margin-bottom: 5px; opacity: 0.6;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
MESAJ_SABLONLARI = {
    "Tasdik Ödenmedi (SERT)": "Sayın {isim}, 2026 yılı defter tasdik ücretiniz ({tutar} TL) ödenmediği için defterleriniz notere teslim EDİLMEMİŞTİR. Cezalı duruma düşmemek için acilen ödeme yapmanızı rica ederiz.",
    "Kibar Hatırlatma": "Sayın {isim}, 2026 defter tasdik ödemenizi ({tutar} TL) hatırlatmak isteriz. İyi çalışmalar."
}

# --- SESSION ---
if 'sessiz_mod' not in st.session_state: st.session_state['sessiz_mod'] = False
if 'tasdik_data' not in st.session_state: st.session_state['tasdik_data'] = None

# --- BAĞLANTILAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]; API_TOKEN = st.secrets["API_TOKEN"]
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

def verileri_getir(sayfa="Ana"):
    try: sheet = google_sheet_baglan(sayfa); return pd.DataFrame(sheet.get_all_records())
    except: return pd.DataFrame()

# --- YAN MENÜ ---
with st.sidebar:
    st.markdown("<h3 style='text-align:center'>MÜŞAVİR PRO 💎</h3>", unsafe_allow_html=True)
    secim = option_menu(
        menu_title=None,
        options=["Genel Bakış", "Tasdik Robotu", "İş Yönetimi", "Ayarlar"],
        icons=["house", "robot", "kanban", "gear"],
        menu_icon="cast", default_index=1,
        styles={"container": {"padding": "0!important", "background-color": "#ffffff"}}
    )
    st.session_state['sessiz_mod'] = st.toggle("🔕 Sessiz Mod", value=st.session_state['sessiz_mod'])

# --- 1. GENEL BAKIŞ ---
if secim == "Genel Bakış":
    st.title("📊 Genel Bakış")
    df = verileri_getir("Sheet1")
    if not df.empty and "Durum" in df.columns:
        c1, c2 = st.columns(2)
        c1.metric("Bekleyen İş", len(df[df["Durum"]!="Tamamlandi"]))
        c2.metric("Toplam İş", len(df))

# --- 2. İŞ YÖNETİMİ ---
elif secim == "İş Yönetimi":
    st.title("📋 İş Takip")
    st.dataframe(verileri_getir("Sheet1"), use_container_width=True)

# --- 3. TASDİK ROBOTU (OPERASYON PANELİ) ---
elif secim == "Tasdik Robotu":
    st.title("🤖 Tasdik Operasyon Merkezi")

    # 1. DOSYA YÜKLEME (Sadece veri yoksa görünür)
    if st.session_state['tasdik_data'] is None:
        st.info("Lütfen Excel Listesini Yükleyin (Ad Soyad, Para Alındı mı, Defter Tasdik Ücreti, 1.NUMARA)")
        up = st.file_uploader("Dosyayı Yükle", type=["xlsx", "xls", "csv"])
        if up:
            try:
                if up.name.endswith('.csv'): df = pd.read_csv(up)
                else: df = pd.read_excel(up)
                
                # Tahsilat Durumu Sütunu Oluştur
                if "Para Alındı mı" in df.columns:
                    df["Tahsil_Edildi"] = df["Para Alındı mı"].apply(lambda x: True if pd.notna(x) and str(x).strip() != "" else False)
                else:
                    df["Tahsil_Edildi"] = False
                
                # Tutar düzeltme
                if "Defter Tasdik Ücreti" not in df.columns: df["Defter Tasdik Ücreti"] = 0
                
                st.session_state['tasdik_data'] = df
                st.rerun()
            except Exception as e: st.error(f"Hata: {e}")

    # 2. OPERASYON EKRANI
    if st.session_state['tasdik_data'] is not None:
        df = st.session_state['tasdik_data']
        
        # Üst Panel: Özet ve Sıfırlama
        c1, c2, c3 = st.columns([2, 2, 1])
        odenmeyen = len(df[df["Tahsil_Edildi"]==False])
        c1.metric("🔴 Ödemeyen", odenmeyen)
        c2.metric("🟢 Ödeyen", len(df) - odenmeyen)
        if c3.button("🔄 Listeyi Sil"):
            st.session_state['tasdik_data'] = None; st.rerun()
        
        st.divider()
        
        # --- BÖLÜM A: TAHSİLAT GÜNCELLEME (BASİT LİSTE) ---
        st.subheader("1. Tahsilat Durumunu Güncelle")
        st.write("Parasını aldığınız kişileri buradan işaretleyip kaydedin.")
        
        edited_df = st.data_editor(
            df[["Ünvan / Ad Soyad", "Defter Tasdik Ücreti", "Tahsil_Edildi"]],
            column_config={
                "Tahsil_Edildi": st.column_config.CheckboxColumn("Ödendi mi?", default=False),
                "Defter Tasdik Ücreti": st.column_config.NumberColumn("Tutar (TL)", format="%.2f TL"),
                "Ünvan / Ad Soyad": st.column_config.TextColumn("Mükellef", disabled=True)
            },
            hide_index=True,
            use_container_width=True,
            height=300
        )
        
        if st.button("💾 Değişiklikleri Kaydet", type="primary"):
            # Güncellemeleri ana veriye işle
            st.session_state['tasdik_data'].update(edited_df)
            st.success("Liste Güncellendi!")
            time.sleep(0.5)
            st.rerun()
            
        st.divider()
        
        # --- BÖLÜM B: TEK TEK MESAJ GÖNDERME (BORÇLULAR) ---
        st.subheader("2. Mükellef Bazında Mesaj Gönder")
        
        # Sadece ödemeyenleri filtrele
        borclular = st.session_state['tasdik_data'][st.session_state['tasdik_data']["Tahsil_Edildi"] == False]
        
        if borclular.empty:
            st.success("🎉 Tebrikler! Borçlu mükellef kalmadı.")
        else:
            mesaj_turu = st.selectbox("Mesaj Şablonu Seç:", list(MESAJ_SABLONLARI.keys()))
            sablon = MESAJ_SABLONLARI[mesaj_turu]
            
            st.markdown(f"**Gidecek Mesaj:** _{sablon.replace('{isim}', 'Mükellef Adı').replace('{tutar}', '000')}_")
            
            st.markdown("---")
            
            # HER SATIR İÇİN BİR KART VE BUTON
            for index, row in borclular.iterrows():
                isim = row["Ünvan / Ad Soyad"]
                tutar = row.get("Defter Tasdik Ücreti", 0)
                tel = row.get("1.NUMARA", "")
                
                # Kart Görünümü (Columns kullanarak)
                col_info, col_btn = st.columns([3, 1])
                
                with col_info:
                    st.markdown(f"""
                    <div class='kisi-karti'>
                        <b>{isim}</b><br>
                        <span style='color:grey'>Borç: {tutar} TL | Tel: {tel}</span>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col_btn:
                    # Benzersiz anahtar (key) kullanarak buton çakışmasını önle
                    if st.button(f"📲 Gönder", key=f"btn_{index}"):
                        tels = numaralari_ayikla(str(tel))
                        if tels:
                            msg = sablon.replace("{isim}", str(isim)).replace("{tutar}", str(tutar))
                            for t in tels:
                                whatsapp_gonder(t, msg)
                            st.toast(f"{isim} kişisine mesaj gönderildi!", icon="✅")
                        else:
                            st.toast(f"{isim} için telefon numarası yok!", icon="❌")

# --- 4. AYARLAR ---
elif secim == "Ayarlar":
    st.title("⚙️ Ayarlar")
    st.write("Veritabanı yedeği alabilirsiniz.")
