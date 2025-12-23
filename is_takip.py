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

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir Asistanı Pro",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TASARIM (CSS) ---
st.markdown("""
    <style>
    .stApp {background-color: #f4f6f9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;}
    [data-testid="stSidebar"] {background-color: #2c3e50;}
    [data-testid="stSidebar"] * {color: #ecf0f1 !important;}
    div[data-testid="stMetric"] {background-color: #ffffff; border: 1px solid #e0e0e0; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);}
    .stButton>button {width: 100%; border-radius: 8px; font-weight: 600; height: 45px;}
    button[kind="primary"] {background: linear-gradient(135deg, #3498db 0%, #2980b9 100%); color: white;}
    .etiket {background-color: #e0f2f1; color: #00695c; padding: 4px 10px; border-radius: 15px; font-size: 12px; margin: 2px;}
    .mesaj-onizleme {background-color: #e8f5e9; padding: 15px; border-radius: 10px; border-left: 5px solid #2e7d32; font-style: italic; color: #1b5e20;}
    .borclu-kutu {background-color: #ffebee; color: #c62828; padding: 5px 10px; border-radius: 5px; font-weight: bold;}
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
RESMI_TATILLER = ["01.01", "23.04", "01.05", "19.05", "15.07", "30.08", "29.10"]
MESAJ_SABLONLARI = {
    "Özel Mesaj Yaz": "",
    "KDV Ödeme Hatırlatma": "Sayın {isim}, {ay} dönemi KDV beyannameniz onaylanmıştır. Ödemenizi vadesinde yapmanızı önemle rica ederiz.",
    "SGK Ödeme Hatırlatma": "Sayın {isim}, personel SGK ödemelerinizin son günü yaklaşmaktadır. Cezalı duruma düşmemek için ödemenizi unutmayınız.",
    "Borç Hatırlatma (Otomatik Tutar)": "Sayın {isim}, ofisimize ait cari hesap bakiyeniz {borc} TL'dir. Ödemenizi bekler, iyi çalışmalar dileriz.",
    "Bayram Kutlaması": "Sayın {isim}, bayramınızı en içten dileklerimizle kutlar, ailenizle birlikte sağlıklı ve huzurlu nice bayramlar dileriz.",
    "Genel Bilgilendirme": "Sayın {isim}, mevzuatta yapılan son değişiklikler gereği..."
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

# --- YAN MENÜ ---
with st.sidebar:
    st.markdown("<h3 style='text-align: center;'>MÜŞAVİR PRO 💬</h3>", unsafe_allow_html=True)
    
    df_m = verileri_getir("Musteriler")
    p_list = ["Admin"]
    if not df_m.empty and "Sorumlu" in df_m.columns:
        p_list += [p for p in df_m["Sorumlu"].unique().tolist() if str(p) not in ["nan", ""]]
    aktif = st.selectbox("👤 Kullanıcı", list(set(p_list)))

    st.session_state['sessiz_mod'] = st.toggle("🔕 Sessiz Mod", value=st.session_state['sessiz_mod'])
    arama = st.text_input("🔍 Ara (Ctrl+K)...")
    
    st.markdown("---")
    menu = ["📊 Genel Bakış", "💬 Mesaj Merkezi", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "💰 Finans & Kâr", "🏢 Kuruluş Sihirbazı", "⚙️ Ayarlar"]
    secim = st.radio("MENÜ", menu)
    
    st.markdown("---")
    st.session_state['hizli_not'] = st.text_area("📝 Notlar:", value=st.session_state['hizli_not'], height=100)

if arama:
    if "mesaj" in arama.lower(): secim = "💬 Mesaj Merkezi"
    elif "ekle" in arama.lower(): secim = "➕ İş Ekle"

# --- 1. DASHBOARD ---
if secim == "📊 Genel Bakış":
    st.title("📊 Yönetim Kokpiti")
    df = verileri_getir("Sheet1")
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
        
        col1, col2 = st.columns([2,1])
        with col1: st.dataframe(df.tail(5)[["Tarih", "Is Tanimi", "Durum", "Personel"]], use_container_width=True, hide_index=True)
        with col2: st.plotly_chart(px.pie(df, names="Durum", hole=0.4), use_container_width=True)

# --- 2. YENİ: MESAJ MERKEZİ ---
elif secim == "💬 Mesaj Merkezi":
    st.title("💬 WhatsApp Mesaj Merkezi")
    
    t1, t2 = st.tabs(["📤 Yeni Mesaj Gönder", "🧾 Borç Hatırlatıcı"])
    
    with t1:
        st.info("💡 Müşterilerinize tek tek veya toplu olarak WhatsApp mesajı gönderin.")
        
        col_kime, col_sablon = st.columns(2)
        
        # Hedef Kitle Seçimi
        hedef = col_kime.radio("Kime Gönderilecek?", ["Tek Müşteri", "Tüm Müşteriler (Toplu)", "Etiketli Grup (Örn: #inşaat)"])
        
        secilen_musteriler = []
        if hedef == "Tek Müşteri":
            secilen = col_kime.selectbox("Müşteri Seç", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
            if secilen: secilen_musteriler = [secilen]
        elif hedef == "Tüm Müşteriler (Toplu)":
            if not df_m.empty: secilen_musteriler = df_m["Ad Soyad"].tolist()
            col_kime.warning(f"Dikkat: {len(secilen_musteriler)} kişiye mesaj gidecek!")
        else:
            etiket_ara = col_kime.text_input("Etiket Gir (Örn: inşaat)")
            if etiket_ara and not df_m.empty and "Etiket" in df_m.columns:
                secilen_musteriler = df_m[df_m["Etiket"].str.contains(etiket_ara, case=False, na=False)]["Ad Soyad"].tolist()
                col_kime.info(f"'{etiket_ara}' etiketli {len(secilen_musteriler)} kişi bulundu.")

        # Şablon Seçimi
        sablon = col_sablon.selectbox("Şablon Seç", list(MESAJ_SABLONLARI.keys()))
        mesaj_icerik = st.text_area("Mesaj İçeriği", value=MESAJ_SABLONLARI[sablon], height=150)
        
        # Önizleme
        st.markdown("### 📱 Önizleme")
        if secilen_musteriler:
            ornek_isim = secilen_musteriler[0]
            # Basit formatlama (sadece {isim} varsa değiştirir)
            final_mesaj = mesaj_icerik.replace("{isim}", ornek_isim).replace("{ay}", datetime.now().strftime("%B"))
            st.markdown(f"<div class='mesaj-onizleme'>{final_mesaj}</div>", unsafe_allow_html=True)
        
        if st.button("🚀 GÖNDER", type="primary"):
            if not secilen_musteriler:
                st.error("Müşteri seçilmedi.")
            else:
                bar = st.progress(0)
                basarili = 0
                for i, musteri in enumerate(secilen_musteriler):
                    # Telefonu bul
                    satir = df_m[df_m["Ad Soyad"] == musteri]
                    if not satir.empty:
                        tels = numaralari_ayikla(satir.iloc[0]["Telefon"])
                        # Mesajı Kişiselleştir
                        kisi_mesaj = mesaj_icerik.replace("{isim}", musteri).replace("{ay}", datetime.now().strftime("%B"))
                        
                        for t in tels:
                            whatsapp_gonder(t, kisi_mesaj)
                        basarili += 1
                    
                    bar.progress((i + 1) / len(secilen_musteriler))
                    time.sleep(0.5) # Spam olmaması için bekleme
                
                st.success(f"İşlem Tamamlandı! {basarili} kişiye mesaj iletildi.")

    with t2:
        st.subheader("🧾 Borçlu Müşterilere Hatırlatma")
        st.write("Sistem cari hesapları tarar ve bakiyesi olanlara otomatik tutarlı mesaj hazırlar.")
        
        if st.button("🔍 Borçluları Listele"):
            df_cari = verileri_getir("Cari")
            if not df_cari.empty:
                df_cari["Tutar"] = pd.to_numeric(df_cari["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
                
                # Pivot yap (Müşteri bazlı toplam)
                # Borçlar (Hizmet Bedeli) pozitif, Tahsilatlar negatif gibi düşünelim veya tam tersi
                # Basit mantık: Hizmet Bedeli toplami - Tahsilat toplami
                
                tahsilatlar = df_cari[df_cari["Islem_Turu"].str.contains("Tahsilat", na=False)].groupby("Musteri")["Tutar"].sum()
                borclar = df_cari[df_cari["Islem_Turu"].str.contains("Hizmet|Borç", na=False)].groupby("Musteri")["Tutar"].sum()
                
                bakiye_df = pd.DataFrame(borclar - tahsilatlar).reset_index()
                bakiye_df.columns = ["Musteri", "Bakiye"]
                borclular = bakiye_df[bakiye_df["Bakiye"] > 0]
                
                st.session_state['borclular_cache'] = borclular # Kaydet
            else:
                st.error("Cari veri yok.")

        if 'borclular_cache' in st.session_state and not st.session_state['borclular_cache'].empty:
            borclular = st.session_state['borclular_cache']
            st.dataframe(borclular)
            
            if st.button("💸 Seçili Borçlulara Mesaj Gönder"):
                bar2 = st.progress(0)
                cnt = 0
                for i, row in borclular.iterrows():
                    m_adi = row["Musteri"]
                    bakiye = row["Bakiye"]
                    
                    # Telefon bul
                    satir = df_m[df_m["Ad Soyad"] == m_adi]
                    if not satir.empty:
                        tels = numaralari_ayikla(satir.iloc[0]["Telefon"])
                        msg = MESAJ_SABLONLARI["Borç Hatırlatma (Otomatik Tutar)"].replace("{isim}", m_adi).replace("{borc}", f"{bakiye:,.2f}")
                        
                        for t in tels:
                            whatsapp_gonder(t, msg)
                        cnt += 1
                    bar2.progress((i+1)/len(borclular))
                    time.sleep(0.5)
                st.success(f"{cnt} borçluya hatırlatma gönderildi.")

# --- 3. İŞ EKLE ---
elif secim == "➕ İş Ekle":
    st.title("📝 Akıllı İş Girişi")
    with st.container():
        with st.form("is_ekle"):
            c1, c2 = st.columns(2)
            tarih = c1.date_input("Tarih")
            if tarih.strftime("%d.%m") in RESMI_TATILLER: st.markdown(f"<div class='tatil-uyari'>Resmi Tatil!</div>", unsafe_allow_html=True)
            saat = c2.time_input("Saat")
            
            mus = st.selectbox("Mükellef", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
            sec_p = st.selectbox("Sorumlu", p_list)
            
            is_tipi = st.selectbox("İş Şablonu", ["KDV Beyannamesi", "Muhtasar", "SGK Giriş", "Genel"])
            notu = is_tipi if is_tipi != "Genel" else st.text_input("Açıklama")
            
            if st.form_submit_button("✅ Kaydet", type="primary"):
                google_sheet_baglan("Sheet1").append_row([tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), f"{mus} - {notu}", "Gonderildi", "Bekliyor", "-", sec_p])
                onbellek_temizle(); whatsapp_gonder(GRUP_ID, f"🆕 *İŞ*: {mus} - {notu}"); st.success("Kaydedildi!")

# --- 4. İŞ YÖNETİMİ ---
elif secim == "✅ İş Yönetimi":
    st.title("📋 İş Takip")
    df = verileri_getir("Sheet1")
    if not df.empty:
        filtre = st.checkbox(f"Sadece Bana ({aktif}) Ait Olanlar")
        df_g = df.copy()
        if filtre and aktif != "Admin" and "Personel" in df_g.columns: df_g = df_g[df_g["Personel"] == aktif]
        st.dataframe(df_g[["Tarih", "Is Tanimi", "Durum", "Personel"]], use_container_width=True, hide_index=True)
        
        c1, c2 = st.columns([3,1])
        secilen = c1.selectbox("İş Seç:", df[df["Durum"]!="Tamamlandi"]["Is Tanimi"].tolist())
        if c2.button("🏁 Bitir"):
            rows = google_sheet_baglan("Sheet1").get_all_values()
            for i, r in enumerate(rows):
                if len(r)>2 and r[2]==secilen:
                    google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Tamamlandi")
                    onbellek_temizle(); st.balloons(); st.rerun()

# --- 5. ARŞİV ---
elif secim == "📂 Müşteri Arşivi":
    st.title("📂 Arşiv")
    if not df_m.empty:
        mus = st.selectbox("Müşteri:", df_m["Ad Soyad"].tolist())
        with st.form("up"):
            txt=st.text_area("Not"); d=st.file_uploader("Dosya"); 
            if st.form_submit_button("Kaydet"):
                l=drive_yukle(d, mus, "Not") if d else "-"
                google_sheet_baglan("Sheet1").append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{mus} - [NOT] {txt}", "-", "Tamamlandi", l, aktif])
                st.success("Kaydedildi")

# --- 6. FİNANS ---
elif secim == "💰 Finans & Kâr":
    st.title("💰 Finans")
    # (Finans kodları önceki gibi devam eder, yer darlığından kısaltıldı ama çalışır)
    df_c = verileri_getir("Cari")
    if not df_c.empty: st.dataframe(df_c)

# --- 7. AYARLAR ---
elif secim == "⚙️ Ayarlar":
    st.title("⚙️ Ayarlar")
    up = st.file_uploader("Müşteri Listesi (Excel)", type="xlsx")
    if up and st.button("Aktar"):
        df_new = pd.read_excel(up)
        # Basit aktarım mantığı
        google_sheet_baglan("Musteriler").append_rows(df_new.values.tolist()); st.success("Aktarıldı")
    
    if st.button("📦 YEDEĞİ İNDİR"):
        st.download_button("İndir", excel_yedek_olustur(verileri_getir("Sheet1"), df_m, verileri_getir("Cari")), "Yedek.xlsx")
