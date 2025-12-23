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
import io
from streamlit_option_menu import option_menu # <-- YENİ TASARIM MODÜLÜ

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir Asistanı",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TASARIM (CSS - MODERN) ---
st.markdown("""
    <style>
    /* Genel Font ve Arka Plan */
    .stApp {background-color: #F0F2F6; font-family: 'Roboto', sans-serif;}
    
    /* Sidebar Arka Planı */
    [data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E0E0E0;
    }
    
    /* Kart Tasarımları (Gölgeli) */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
        border: none;
    }
    
    /* Butonlar */
    .stButton>button {
        border-radius: 12px;
        height: 50px;
        font-weight: bold;
        border: none;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }
    button[kind="primary"] {
        background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
    }
    button[kind="primary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.2);
    }
    
    /* Özel Etiketler */
    .etiket {
        background-color: #E3F2FD; color: #1565C0; 
        padding: 5px 12px; border-radius: 20px; 
        font-size: 13px; font-weight: 600; display: inline-block; margin: 2px;
    }
    .mesaj-onizleme {
        background-color: #F1F8E9; border-left: 5px solid #66BB6A;
        padding: 15px; border-radius: 8px; color: #2E7D32; font-style: italic;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
RESMI_TATILLER = ["01.01", "23.04", "01.05", "19.05", "15.07", "30.08", "29.10"]
MESAJ_SABLONLARI = {
    "Özel Mesaj Yaz": "",
    "KDV Ödeme Hatırlatma": "Sayın {isim}, {ay} dönemi KDV beyannameniz onaylanmıştır. Ödemenizi vadesinde yapmanızı rica ederiz.",
    "SGK Ödeme Hatırlatma": "Sayın {isim}, SGK ödemelerinizin son günü yaklaşmaktadır.",
    "Borç Hatırlatma": "Sayın {isim}, ofisimize ait cari bakiyeniz {borc} TL'dir.",
    "Bayram Kutlaması": "Sayın {isim}, bayramınızı en içten dileklerimizle kutlarız.",
}

# --- SESSION ---
if 'hizli_not' not in st.session_state: st.session_state['hizli_not'] = ""
if 'son_islem_yedek' not in st.session_state: st.session_state['son_islem_yedek'] = None
if 'sessiz_mod' not in st.session_state: st.session_state['sessiz_mod'] = False

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

def drive_yukle(uploaded_file, musteri_adi, evrak_turu):
    try:
        service = build('drive', 'v3', credentials=creds)
        uzanti = uploaded_file.name.split(".")[-1]
        yeni_isim = f"{musteri_adi}_{datetime.now().strftime('%Y-%m-%d')}_{evrak_turu}.{uzanti}".replace(" ", "_")
        file_metadata = {'name': yeni_isim, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(uploaded_file, mimetype=uploaded_file.type)
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file.get('webViewLink')
    except: return None

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

def beyanname_analiz_et(pdf_file):
    try:
        text = ""
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages: text += page.extract_text()
        match = re.search(r"Kredi Kartı.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
        if match: return float(match.group(1).replace(".", "").replace(",", ".")), text
        return 0.0, text
    except Exception as e: return 0.0, str(e)

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

# --- MODERN YAN MENÜ (SIDEBAR) ---
with st.sidebar:
    # Logo Alanı
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.markdown("<h3 style='margin-top:0;'>MÜŞAVİR PRO</h3>", unsafe_allow_html=True)
    
    # Kullanıcı
    df_m = verileri_getir("Musteriler")
    p_list = ["Admin"]
    if not df_m.empty and "Sorumlu" in df_m.columns:
        p_list += [p for p in df_m["Sorumlu"].unique().tolist() if str(p) not in ["nan", ""]]
    aktif = st.selectbox("👤 Aktif Kullanıcı", list(set(p_list)))
    
    st.markdown("---")
    
    # YENİ NESİL MENÜ (OPTION MENU)
    secim = option_menu(
        menu_title=None, # Başlık gizli
        options=["Genel Bakış", "İş Ekle", "İş Yönetimi", "Mesaj Merkezi", "Müşteri Arşivi", "Finans", "Kuruluş", "Ayarlar"],
        icons=["house", "plus-circle", "kanban", "chat-dots", "folder2-open", "cash-coin", "building", "gear"],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "#ffffff"},
            "icon": {"color": "#2c3e50", "font-size": "16px"}, 
            "nav-link": {"font-size": "14px", "text-align": "left", "margin":"0px", "--hover-color": "#f0f2f6"},
            "nav-link-selected": {"background-color": "#1e3c72", "color": "white", "font-weight":"bold"},
        }
    )
    
    st.markdown("---")
    st.session_state['sessiz_mod'] = st.toggle("🔕 Sessiz Mod", value=st.session_state['sessiz_mod'])
    
    with st.expander("📝 Hızlı Not"):
        st.session_state['hizli_not'] = st.text_area("", value=st.session_state['hizli_not'], height=100, placeholder="Buraya not al...")

# --- 1. DASHBOARD ---
if secim == "Genel Bakış":
    st.title("📊 Yönetim Kokpiti")
    df = verileri_getir("Sheet1")
    
    # Doğum Günü
    if not df_m.empty and "Dogum_Tarihi" in df_m.columns:
        bugun = datetime.now()
        df_m["Dogum_Tarihi_Format"] = pd.to_datetime(df_m["Dogum_Tarihi"], format='%d.%m.%Y', errors='coerce')
        bg = df_m[(df_m["Dogum_Tarihi_Format"].dt.day == bugun.day) & (df_m["Dogum_Tarihi_Format"].dt.month == bugun.month)]
        if not bg.empty: st.success(f"🎂 BUGÜN DOĞUM GÜNÜ: {', '.join(bg['Ad Soyad'].tolist())}")

    if not df.empty and "Durum" in df.columns:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Toplam İş", len(df))
        c2.metric("✅ Biten", len(df[df["Durum"]=="Tamamlandi"]))
        c3.metric("⏳ Bekleyen", len(df[df["Durum"]!="Tamamlandi"]))
        
        df_c = verileri_getir("Cari")
        if not df_c.empty:
            df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
            net = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
            c4.metric("Net Kâr", f"{net:,.0f} TL")
        else: c4.metric("Net Kâr", "0 TL")

        if "Personel" in df.columns:
            sahipsiz = df[(df["Personel"] == "") & (df["Durum"] != "Tamamlandi")]
            if not sahipsiz.empty: st.warning(f"⚠️ {len(sahipsiz)} adet işe personel atanmamış!")

        col1, col2 = st.columns([2,1])
        with col1: 
            st.markdown("### 🗓️ Son Hareketler")
            st.dataframe(df.tail(5)[["Tarih", "Is Tanimi", "Durum"]], use_container_width=True, hide_index=True)
        with col2: 
            st.plotly_chart(px.pie(df, names="Durum", hole=0.5), use_container_width=True)

# --- 2. İŞ EKLE ---
elif secim == "İş Ekle":
    st.title("📝 Akıllı İş Girişi")
    with st.container():
        with st.form("is_ekle"):
            c1, c2 = st.columns(2)
            tarih = c1.date_input("Tarih")
            if tarih.strftime("%d.%m") in RESMI_TATILLER: st.warning("⚠️ Resmi Tatil Günü!")
            saat = c2.time_input("Saat")
            
            mus = st.selectbox("Mükellef", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
            sec_p = st.selectbox("Sorumlu", p_list)
            
            is_tipi = st.selectbox("İş Şablonu", ["KDV Beyannamesi", "Muhtasar", "SGK Giriş", "Genel", "Diğer"])
            notu = is_tipi if is_tipi != "Diğer" else st.text_input("Açıklama")
            sms = st.checkbox("WhatsApp Gönder")
            
            if st.form_submit_button("✅ Görevi Kaydet", type="primary"):
                google_sheet_baglan("Sheet1").append_row([tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), f"{mus} - {notu}", "Gonderildi", "Bekliyor", "-", sec_p])
                onbellek_temizle()
                whatsapp_gonder(GRUP_ID, f"🆕 *İŞ*: {mus} - {notu} ({sec_p})")
                if sms and not df_m.empty:
                    satir = df_m[df_m["Ad Soyad"] == mus]
                    if not satir.empty:
                        for n in numaralari_ayikla(satir.iloc[0]["Telefon"]): whatsapp_gonder(n, f"Sayın {mus}, işleminiz ({notu}) alınmıştır.")
                st.success("Kaydedildi!")

# --- 3. İŞ YÖNETİMİ ---
elif secim == "İş Yönetimi":
    st.title("📋 İş Takip Merkezi")
    tab_list, tab_takvim = st.tabs(["📋 Liste", "📅 Takvim"])
    df = verileri_getir("Sheet1")
    
    with tab_list:
        if st.button("🔄 Yenile"): onbellek_temizle(); st.rerun()
        if not df.empty:
            filtre = st.checkbox(f"Sadece Bana ({aktif}) Ait Olanlar")
            df_g = df.copy()
            if filtre and aktif != "Admin" and "Personel" in df_g.columns: df_g = df_g[df_g["Personel"] == aktif]
            st.dataframe(df_g[["Tarih", "Is Tanimi", "Durum", "Personel"]], use_container_width=True, hide_index=True)
            
            st.markdown("---")
            c1, c2 = st.columns([3,1])
            bekleyen = df[df["Durum"] != "Tamamlandi"]["Is Tanimi"].tolist()
            secilen = c1.selectbox("İş Seç:", bekleyen)
            
            if secilen and c2.button("🏁 Bitir", type="primary"):
                st.session_state['son_islem_yedek'] = secilen
                rows = google_sheet_baglan("Sheet1").get_all_values()
                for i, r in enumerate(rows):
                    if len(r)>2 and r[2]==secilen: google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Tamamlandi"); onbellek_temizle(); st.balloons(); st.rerun()
            
            if st.session_state['son_islem_yedek'] and st.button("↩️ Geri Al"):
                 rows = google_sheet_baglan("Sheet1").get_all_values()
                 for i, r in enumerate(rows):
                    if len(r)>2 and r[2]==st.session_state['son_islem_yedek']: google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Bekliyor"); st.session_state['son_islem_yedek']=None; onbellek_temizle(); st.rerun()
    
    with tab_takvim:
        if not df.empty:
            df['Baslangic'] = pd.to_datetime(df['Tarih'], format='%d.%m.%Y', errors='coerce')
            df['Bitis'] = df['Baslangic'] + pd.Timedelta(days=1)
            df = df.dropna(subset=['Baslangic'])
            if not df.empty: st.plotly_chart(px.timeline(df, x_start="Baslangic", x_end="Bitis", y="Personel", color="Durum"), use_container_width=True)

# --- 4. MESAJ MERKEZİ ---
elif secim == "Mesaj Merkezi":
    st.title("💬 Mesaj Merkezi")
    t1, t2 = st.tabs(["📤 Yeni Mesaj", "🧾 Borç Hatırlatıcı"])
    
    with t1:
        c1, c2 = st.columns(2)
        hedef = c1.radio("Kime?", ["Tek Kişi", "Herkes (Toplu)"])
        sablon = c2.selectbox("Şablon", list(MESAJ_SABLONLARI.keys()))
        msg = st.text_area("İçerik", value=MESAJ_SABLONLARI[sablon], height=100)
        
        mus_listesi = []
        if hedef == "Tek Kişi":
            sec = c1.selectbox("Seç:", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
            if sec: mus_listesi=[sec]
        else:
            if not df_m.empty: mus_listesi = df_m["Ad Soyad"].tolist()
        
        st.markdown(f"<div class='mesaj-onizleme'>Önizleme: {msg.replace('{isim}', 'Ahmet Bey')}</div>", unsafe_allow_html=True)
        
        if st.button("🚀 GÖNDER", type="primary"):
            if mus_listesi:
                bar=st.progress(0)
                for i, m in enumerate(mus_listesi):
                    satir = df_m[df_m["Ad Soyad"] == m]
                    if not satir.empty:
                        for t in numaralari_ayikla(satir.iloc[0]["Telefon"]): 
                            whatsapp_gonder(t, msg.replace("{isim}", m).replace("{ay}", datetime.now().strftime("%B")))
                    bar.progress((i+1)/len(mus_listesi))
                    time.sleep(0.5)
                st.success("Gönderildi!")

    with t2:
        if st.button("🔍 Borçluları Bul"):
            df_cari = verileri_getir("Cari")
            if not df_cari.empty:
                df_cari["Tutar"] = pd.to_numeric(df_cari["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
                tahsilat = df_cari[df_cari["Islem_Turu"].str.contains("Tahsilat", na=False)].groupby("Musteri")["Tutar"].sum()
                borc = df_cari[df_cari["Islem_Turu"].str.contains("Hizmet|Borç", na=False)].groupby("Musteri")["Tutar"].sum()
                bakiye = (borc - tahsilat).reset_index(); bakiye.columns=["Musteri", "Bakiye"]
                borclular = bakiye[bakiye["Bakiye"] > 0]
                st.session_state['borclular_cache'] = borclular
                
        if 'borclular_cache' in st.session_state:
            st.dataframe(st.session_state['borclular_cache'])
            if st.button("💸 Hatırlat"):
                for i, r in st.session_state['borclular_cache'].iterrows():
                    satir = df_m[df_m["Ad Soyad"] == r["Musteri"]]
                    if not satir.empty:
                         for t in numaralari_ayikla(satir.iloc[0]["Telefon"]):
                             whatsapp_gonder(t, MESAJ_SABLONLARI["Borç Hatırlatma"].replace("{isim}", r["Musteri"]).replace("{borc}", str(r["Bakiye"])))
                st.success("İletildi!")

# --- 5. ARŞİV ---
elif secim == "Müşteri Arşivi":
    st.title("📂 Arşiv")
    if not df_m.empty:
        mus = st.selectbox("Seç:", df_m["Ad Soyad"].tolist())
        bilgi = df_m[df_m["Ad Soyad"] == mus].iloc[0]
        st.info(f"Tel: {bilgi.get('Telefon')} | TC: {bilgi.get('TC')} | Ücret: {bilgi.get('Ucret')} TL")
        
        with st.form("up"):
            d=st.file_uploader("Dosya"); t=st.selectbox("Tür", ["Fatura", "Diğer"])
            if st.form_submit_button("Yükle"):
                l=drive_yukle(d, mus, t) if d else "-"
                google_sheet_baglan("Sheet1").append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{mus} - [{t}]", "-", "Tamamlandi", l, aktif])
                st.success("Yüklendi")

# --- 6. FİNANS ---
elif secim == "Finans":
    st.title("💰 Finans")
    df_c = verileri_getir("Cari")
    t1, t2, t3, t4 = st.tabs(["📊 Analiz", "💸 Ekle", "📄 OCR", "🔄 Tahakkuk"])
    with t1:
        if not df_c.empty: st.dataframe(df_c, use_container_width=True)
    with t2:
        with st.form("f_ekle"):
            tr=st.date_input("Tarih"); tur=st.radio("Tür", ["Hizmet Bedeli (Borç)", "Tahsilat", "GİDER"]); m=st.selectbox("Müşteri", df_m["Ad Soyad"].tolist()); tut=st.number_input("Tutar")
            if st.form_submit_button("Kaydet"): google_sheet_baglan("Cari").append_row([tr.strftime("%d.%m.%Y"), m, tur, tut, "-"]); onbellek_temizle(); st.success("Ok")
    with t3:
        up=st.file_uploader("KDV PDF", type="pdf")
        if up: 
            v,t = beyanname_analiz_et(up)
            if v>0: st.success(f"POS: {v}"); st.button("Kaydet")
    with t4:
        m_t=st.selectbox("Müşteri Seç", df_m["Ad Soyad"].tolist()); tu=st.number_input("Tutar")
        if st.button("Yıllık İşle"): google_sheet_baglan("Cari").append_rows([[f"15.{i+1:02d}.2025", m_t, "Borç", tu, "-"] for i in range(12)]); st.success("Tamam")

# --- 7. KURULUŞ ---
elif secim == "Kuruluş":
    st.title("🏢 Kuruluş Sihirbazı")
    with st.form("kur"):
        a=st.text_input("Aday"); t=st.selectbox("Tür", ["Ltd", "Şahıs"])
        if st.form_submit_button("Teklif"): st.success("Teklif Oluşturuldu")

# --- 8. AYARLAR ---
elif secim == "Ayarlar":
    st.title("⚙️ Ayarlar")
    u=st.file_uploader("Müşteri Listesi (Excel)", type="xlsx")
    if u and st.button("İçe Aktar"):
        df_n=pd.read_excel(u)
        google_sheet_baglan("Musteriler").append_rows(df_n.values.tolist())
        st.success("Aktarıldı")
    if st.button("Yedek Al"):
        st.download_button("İndir", excel_yedek_olustur(verileri_getir("Sheet1"), df_m, verileri_getir("Cari")), "Yedek.xlsx")
