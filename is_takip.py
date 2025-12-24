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
    
    /* Mesaj Hata Kutusu */
    .hata-kutusu {
        background-color: #ffebee; color: #c62828; padding: 10px; border-radius: 5px; font-size: 12px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
MESAJ_SABLONLARI = {
    "Tasdik Ödenmedi (RESMİ UYARI)": "Sayın Mükellefimiz {isim}, 2026 yılı Defter Tasdik ve Yazılım Giderleri ücretiniz ({tutar} TL) daha önce tarafınıza bildirildiği ancak ödenmediği için defterleriniz notere teslim EDİLMEMİŞTİR. Bugün SON GÜN. Cezalı duruma düşmemek için acilen ödeme yapmanızı rica ederiz.",
    "Kibar Hatırlatma": "Sayın Mükellefimiz {isim}, 2026 yılı Defter Tasdik ve Yazılım giderleri ödemenizi ({tutar} TL) hatırlatmak isteriz. Defterlerin zamanında tasdiklenmesi için ödemenizi bekliyoruz. İyi çalışmalar."
}

# --- SESSION ---
if 'sessiz_mod' not in st.session_state: st.session_state['sessiz_mod'] = False
if 'tasdik_data' not in st.session_state: st.session_state['tasdik_data'] = None

# --- BAĞLANTILAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]; API_TOKEN = st.secrets["API_TOKEN"]
    # Diğer servisler opsiyonel hata vermesin diye try içinde
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    except: creds = None
except: st.error("⚠️ Ayar Hatası: Secrets (Green API) eksik."); st.stop()

def google_sheet_baglan(sayfa_adi="Sheet1"):
    if not creds: return None
    client = gspread.authorize(creds)
    if sayfa_adi == "Sheet1": return client.open("Is_Takip_Sistemi").sheet1
    else: return client.open("Is_Takip_Sistemi").worksheet(sayfa_adi)

# --- WHATSAPP GÖNDERME (HATA GÖSTEREN VERSİYON) ---
def whatsapp_gonder(chat_id, mesaj):
    if st.session_state['sessiz_mod']: return False
    
    # Numara temizliği
    chat_id = str(chat_id).replace(" ", "").replace("+", "")
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    
    try:
        payload = {'chatId': chat_id, 'message': mesaj}
        response = requests.post(url, json=payload)
        
        # Eğer sunucu OK (200) döndüyse
        if response.status_code == 200:
            return True, "Başarılı"
        else:
            # Hata kodunu döndür
            return False, f"Hata Kodu: {response.status_code} - {response.text}"
            
    except Exception as e:
        return False, f"Bağlantı Hatası: {str(e)}"

def numaralari_ayikla(tel_str):
    if not tel_str: return []
    tel_str = str(tel_str)
    if tel_str == "nan" or tel_str == "None": return []
    ham_parcalar = re.split(r'[,\n/]', tel_str)
    temiz = []
    for parca in ham_parcalar:
        sadece_rakam = re.sub(r'\D', '', parca)
        # Türkiye formatı kontrolü
        if len(sadece_rakam) == 10: temiz.append("90" + sadece_rakam)
        elif len(sadece_rakam) == 11 and sadece_rakam.startswith("0"): temiz.append("9" + sadece_rakam)
        elif len(sadece_rakam) == 12 and sadece_rakam.startswith("90"): temiz.append(sadece_rakam)
    return temiz

# Para Formatı (9.000 TL)
def para_formatla(deger):
    try:
        val = float(str(deger).replace(",", "."))
        return "{:,.0f}".format(val).replace(",", ".")
    except:
        return str(deger)

def verileri_getir(sayfa="Ana"):
    if not creds: return pd.DataFrame()
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
    if creds:
        df = verileri_getir("Sheet1")
        if not df.empty and "Durum" in df.columns:
            c1, c2 = st.columns(2)
            c1.metric("Bekleyen İş", len(df[df["Durum"]!="Tamamlandi"]))
            c2.metric("Toplam İş", len(df))
    else:
        st.warning("Google Sheets bağlantısı yok, sadece Tasdik Robotu kullanılabilir.")

# --- 2. İŞ YÖNETİMİ ---
elif secim == "İş Yönetimi":
    st.title("📋 İş Takip")
    if creds:
        st.dataframe(verileri_getir("Sheet1"), use_container_width=True)
    else:
        st.error("Google Sheets bağlantısı gerekli.")

# --- 3. TASDİK ROBOTU (OPERASYON PANELİ) ---
elif secim == "Tasdik Robotu":
    st.title("🤖 Tasdik Operasyon Merkezi")
    st.info("💡 Excel/CSV dosyanızı yükleyin. Sütun isimleri: 'Ünvan / Ad Soyad', 'Para Alındı mı', '1.NUMARA', 'Defter Tasdik Ücreti'")

    # 1. DOSYA YÜKLEME
    if st.session_state['tasdik_data'] is None:
        up = st.file_uploader("PLANLAMA 2026 Dosyasını Yükle", type=["xlsx", "xls", "csv"])
        if up:
            try:
                if up.name.endswith('.csv'): df = pd.read_csv(up)
                else: df = pd.read_excel(up)
                
                # Tahsilat Durumu Sütunu Oluştur (Boşlar = False)
                if "Para Alındı mı" in df.columns:
                    df["Tahsil_Edildi"] = df["Para Alındı mı"].apply(lambda x: True if pd.notna(x) and str(x).strip() != "" else False)
                else:
                    df["Tahsil_Edildi"] = False
                
                # Tutar düzeltme
                if "Defter Tasdik Ücreti" not in df.columns: df["Defter Tasdik Ücreti"] = 0
                
                st.session_state['tasdik_data'] = df
                st.rerun()
            except Exception as e: st.error(f"Dosya okuma hatası: {e}")

    # 2. OPERASYON EKRANI
    if st.session_state['tasdik_data'] is not None:
        df = st.session_state['tasdik_data']
        
        # Üst Panel: Özet
        c1, c2, c3 = st.columns([2, 2, 1])
        odenmeyen = len(df[df["Tahsil_Edildi"]==False])
        c1.metric("🔴 Ödemeyen (Borçlu)", odenmeyen)
        c2.metric("🟢 Ödeyen (Tamam)", len(df) - odenmeyen)
        if c3.button("🔄 Listeyi Sıfırla"):
            st.session_state['tasdik_data'] = None; st.rerun()
        
        st.divider()
        
        # --- BÖLÜM A: TAHSİLAT GÜNCELLEME ---
        st.subheader("1. Tahsilat Listesi (Ödemeyi İşaretle)")
        
        edited_df = st.data_editor(
            df[["Ünvan / Ad Soyad", "Defter Tasdik Ücreti", "Tahsil_Edildi"]],
            column_config={
                "Tahsil_Edildi": st.column_config.CheckboxColumn("Tahsil Edildi mi?", default=False),
                "Defter Tasdik Ücreti": st.column_config.NumberColumn("Tutar", format="%.2f TL"),
                "Ünvan / Ad Soyad": st.column_config.TextColumn("Mükellef", disabled=True)
            },
            hide_index=True,
            use_container_width=True,
            height=300
        )
        
        if st.button("💾 Tahsilatları Kaydet", type="primary"):
            st.session_state['tasdik_data'].update(edited_df)
            st.success("Liste Güncellendi!")
            time.sleep(0.5)
            st.rerun()
            
        st.divider()
        
        # --- BÖLÜM B: MESAJ GÖNDERME ---
        st.subheader("2. Mesaj Gönderimi (Sadece Ödemeyenler)")
        
        borclular = st.session_state['tasdik_data'][st.session_state['tasdik_data']["Tahsil_Edildi"] == False]
        
        if borclular.empty:
            st.balloons()
            st.success("🎉 Tebrikler! Borçlu mükellef kalmadı.")
        else:
            mesaj_turu = st.selectbox("Mesaj Şablonu:", list(MESAJ_SABLONLARI.keys()))
            sablon = MESAJ_SABLONLARI[mesaj_turu]
            
            # Önizleme
            ornek_tutar = para_formatla(9000)
            st.info(f"**Önizleme:** {sablon.replace('{isim}', 'Ahmet Yılmaz').replace('{tutar}', ornek_tutar)}")
            
            st.markdown("---")
            
            # KARTLAR VE BUTONLAR
            for index, row in borclular.iterrows():
                isim = row["Ünvan / Ad Soyad"]
                tutar_raw = row.get("Defter Tasdik Ücreti", 0)
                tutar_guzel = para_formatla(tutar_raw)
                tel = row.get("1.NUMARA", "")
                
                col_info, col_btn = st.columns([3, 1])
                
                with col_info:
                    st.markdown(f"""
                    <div class='kisi-karti'>
                        <b>{isim}</b><br>
                        <span style='color:black; font-weight:bold'>Borç: {tutar_guzel} TL</span> <span style='color:grey'>| Tel: {tel}</span>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col_btn:
                    # Gönder Butonu
                    if st.button(f"📲 Gönder", key=f"btn_{index}"):
                        tels = numaralari_ayikla(str(tel))
                        if tels:
                            msg = sablon.replace("{isim}", str(isim)).replace("{tutar}", str(tutar_guzel))
                            basarili_mi = False
                            
                            for t in tels:
                                # Burada hata kontrolü yapan fonksiyonu çağırıyoruz
                                status, detay = whatsapp_gonder(t, msg)
                                if status:
                                    basarili_mi = True
                                else:
                                    # Hata varsa ekrana bas
                                    st.error(f"Gitmedi: {detay}")
                            
                            if basarili_mi:
                                st.toast(f"{isim}: Mesaj İletildi! ✅", icon="✅")
                            else:
                                st.toast(f"{isim}: HATA OLUŞTU! ❌", icon="❌")
                        else:
                            st.error(f"{isim} için geçerli numara yok.")

# --- 4. AYARLAR ---
elif secim == "Ayarlar":
    st.title("⚙️ Ayarlar")
    st.write("Veritabanı yedeği alabilirsiniz.")
