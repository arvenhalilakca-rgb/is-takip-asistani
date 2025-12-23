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
    page_title="Müşavir Asistanı Pro X",
    page_icon="🛡️",
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
    .tatil-uyari {background-color: #ffebee; color: #c62828; padding: 12px; border-radius: 8px; border-left: 5px solid #ef5350;}
    .basari-kutu {background-color: #e8f5e9; color: #2e7d32; padding: 15px; border-radius: 8px; border-left: 5px solid #43a047;}
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
RESMI_TATILLER = ["01.01", "23.04", "01.05", "19.05", "15.07", "30.08", "29.10"]
FIYAT_TARIFESI = {
    "Şahıs İşletmesi": {"Hizmet": {"Kurulus": 10000, "Defter": 5000}, "Alım-Satım": {"Kurulus": 10000, "Defter": 5000}, "İmalat - İnşaat": {"Kurulus": 10000, "Defter": 5000}},
    "Limited Şirket": {"Hizmet": {"Kurulus": 25000, "Defter": 12500}, "Alım-Satım": {"Kurulus": 25000, "Defter": 12500}, "İmalat - İnşaat": {"Kurulus": 25000, "Defter": 15000}},
    "Anonim Şirket": {"Hizmet": {"Kurulus": 25000, "Defter": 12500}, "İmalat - İnşaat": {"Kurulus": 25000, "Defter": 17500}}
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

# --- YENİ: EXCEL EXPORT (YEDEKLEME) ---
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
    st.markdown("<h3 style='text-align: center;'>MÜŞAVİR PRO X 🛡️</h3>", unsafe_allow_html=True)
    
    df_m = verileri_getir("Musteriler")
    p_list = ["Admin"]
    if not df_m.empty and "Sorumlu" in df_m.columns:
        p_list += [p for p in df_m["Sorumlu"].unique().tolist() if str(p) not in ["nan", ""]]
    aktif = st.selectbox("👤 Kullanıcı", list(set(p_list)))

    st.session_state['sessiz_mod'] = st.toggle("🔕 Sessiz Mod", value=st.session_state['sessiz_mod'])
    arama = st.text_input("🔍 Hızlı Git (Ctrl+K)", placeholder="Ara...")
    
    st.markdown("---")
    menu = ["📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "💰 Finans & Kâr", "🏢 Kuruluş Sihirbazı", "⚙️ Ayarlar & Yedek"]
    secim = st.radio("MENÜ", menu)
    
    st.markdown("---")
    st.session_state['hizli_not'] = st.text_area("📝 Hızlı Notlar:", value=st.session_state['hizli_not'], height=100)

if arama:
    if "ekle" in arama.lower(): secim = "➕ İş Ekle"
    elif "finans" in arama.lower(): secim = "💰 Finans & Kâr"
    elif "ayar" in arama.lower(): secim = "⚙️ Ayarlar & Yedek"

# --- 1. DASHBOARD ---
if secim == "📊 Genel Bakış":
    st.title("📊 Yönetim Kokpiti")
    df = verileri_getir("Sheet1")
    
    if not df.empty and "Durum" in df.columns:
        # Metrikler
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Toplam İş", len(df))
        c2.metric("✅ Biten", len(df[df["Durum"]=="Tamamlandi"]))
        c3.metric("⏳ Bekleyen", len(df[df["Durum"]!="Tamamlandi"]))
        
        df_c = verileri_getir("Cari")
        if not df_c.empty:
            df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
            net = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum() - df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
            c4.metric("Net Kâr", f"{net:,.0f} TL", delta_color="normal" if net>0 else "inverse")
        else: c4.metric("Net Kâr", "0 TL")

        # Son Hareketler & Pasta Grafik
        col1, col2 = st.columns([2,1])
        with col1: 
            st.markdown("### 🗓️ Son Hareketler")
            st.dataframe(df.tail(5)[["Tarih", "Is Tanimi", "Durum", "Personel"]], use_container_width=True, hide_index=True)
        with col2: 
            st.markdown("### 📈 İş Durumu")
            st.plotly_chart(px.pie(df, names="Durum", hole=0.4), use_container_width=True)

# --- 2. İŞ EKLE ---
elif secim == "➕ İş Ekle":
    st.title("📝 Akıllı İş Girişi")
    with st.container():
        with st.form("is_ekle"):
            c1, c2 = st.columns(2)
            tarih = c1.date_input("Tarih")
            if tarih.strftime("%d.%m") in RESMI_TATILLER or tarih.weekday() == 6:
                st.markdown(f"<div class='tatil-uyari'>⚠️ {tarih.strftime('%d.%m.%Y')} resmi tatil veya Pazar.</div>", unsafe_allow_html=True)
            saat = c2.time_input("Saat")
            
            mus_list = []
            if not df_m.empty:
                df_m["Ucret"] = pd.to_numeric(df_m["Ucret"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
                lim = df_m["Ucret"].quantile(0.8)
                for i, r in df_m.iterrows():
                    ad = r["Ad Soyad"]
                    if r["Ucret"] >= lim and lim > 0: ad = f"⭐ {ad} (VIP)"
                    mus_list.append(ad)
            
            mus = st.selectbox("Mükellef", mus_list).replace("⭐ ", "").replace(" (VIP)", "")
            
            # Personel Otomatik Seç
            df_is = verileri_getir("Sheet1")
            p_list_yuk = [""]
            def_i = 0
            
            s_bul = ""
            if not df_m.empty and "Sorumlu" in df_m.columns:
                f = df_m[df_m["Ad Soyad"] == mus]
                if not f.empty: s_bul = f.iloc[0]["Sorumlu"]

            if not df_is.empty and "Personel" in df_is.columns:
                yuk = df_is[df_is["Durum"] != "Tamamlandi"]["Personel"].value_counts()
                for p in p_list:
                    if p != "Admin":
                        etiket = f"{p} (Aktif: {yuk.get(p, 0)})"
                        p_list_yuk.append(etiket)
                        if p == s_bul: def_i = len(p_list_yuk) - 1
            
            sec_p = st.selectbox("Sorumlu", p_list_yuk, index=def_i).split(" (")[0]
            
            is_tipi = st.selectbox("İş Şablonu", ["KDV Beyannamesi", "Muhtasar", "SGK Giriş", "Genel", "Diğer"])
            notu = is_tipi if is_tipi != "Diğer" else st.text_input("Açıklama")
            sms = st.checkbox("SMS Gönder")
            
            if st.form_submit_button("✅ Kaydet", type="primary"):
                google_sheet_baglan("Sheet1").append_row([tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), f"{mus} - {notu}", "Gonderildi", "Bekliyor", "-", sec_p])
                onbellek_temizle()
                whatsapp_gonder(GRUP_ID, f"🆕 *İŞ*: {mus} - {notu} ({sec_p})")
                if sms and not df_m.empty:
                    satir = df_m[df_m["Ad Soyad"] == mus]
                    if not satir.empty:
                        for n in numaralari_ayikla(satir.iloc[0]["Telefon"]): whatsapp_gonder(n, f"Sayın {mus}, işleminiz ({notu}) alınmıştır.")
                st.success("Kaydedildi!")

# --- 3. İŞ YÖNETİMİ ---
elif secim == "✅ İş Yönetimi":
    st.title("📋 İş Takip Merkezi")
    tab_list, tab_takvim = st.tabs(["📋 Liste", "📅 Takvim"])
    df = verileri_getir("Sheet1")
    
    with tab_list:
        if st.button("🔄 Yenile"): onbellek_temizle(); st.rerun()
        if not df.empty:
            filtre = st.checkbox(f"Sadece Bana ({aktif}) Ait Olanlar")
            df_g = df.copy()
            if filtre and aktif != "Admin" and "Personel" in df_g.columns:
                df_g = df_g[df_g["Personel"] == aktif]
            
            st.dataframe(df_g[["Tarih", "Is Tanimi", "Durum", "Personel"]], use_container_width=True, hide_index=True)
            
            st.markdown("---")
            c1, c2 = st.columns([3,1])
            bekleyen = df[df["Durum"] != "Tamamlandi"]["Is Tanimi"].tolist()
            secilen = c1.selectbox("İş Seç:", bekleyen)
            
            if secilen and ("AÇILIŞ" in secilen or "KURULUŞ" in secilen):
                st.info("Kuruluş Checklist")
                s1=st.checkbox("1. Sicil Gazetesi"); s2=st.checkbox("2. İmza Sirküleri"); s3=st.checkbox("3. E-Tebligat")
                if st.button("Güncelle"):
                    d = "Sicil/İmza Bekleniyor"
                    if s1 and s2 and s3: d = "Tamamlandi"
                    rows = google_sheet_baglan("Sheet1").get_all_values()
                    for i, r in enumerate(rows):
                        if len(r)>2 and r[2]==secilen: google_sheet_baglan("Sheet1").update_cell(i+1, 5, d); onbellek_temizle(); st.rerun()
            elif secilen:
                if c2.button("🏁 Bitir"):
                    st.session_state['son_islem_yedek'] = secilen
                    rows = google_sheet_baglan("Sheet1").get_all_values()
                    for i, r in enumerate(rows):
                        if len(r)>2 and r[2]==secilen: google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Tamamlandi"); onbellek_temizle(); st.balloons(); st.rerun()

            if st.session_state['son_islem_yedek'] and st.button("↩️ Geri Al"):
                rows = google_sheet_baglan("Sheet1").get_all_values()
                for i, r in enumerate(rows):
                    if len(r)>2 and r[2]==st.session_state['son_islem_yedek']: google_sheet_baglan("Sheet1").update_cell(i+1, 5, "Bekliyor"); st.session_state['son_islem_yedek']=None; onbellek_temizle(); st.rerun()

            if secilen and c2.button("🔁 Kopyala"):
                satir = df[df["Is Tanimi"] == secilen].iloc[0]
                t_yeni = (datetime.now()+timedelta(days=30)).strftime("%d.%m.%Y")
                google_sheet_baglan("Sheet1").append_row([t_yeni, satir["Saat"], satir["Is Tanimi"], "Gonderildi", "Bekliyor", "-", satir.get("Personel", "")]); onbellek_temizle(); st.success("Kopyalandı")

    with tab_takvim:
        if not df.empty:
            df['Baslangic'] = pd.to_datetime(df['Tarih'], format='%d.%m.%Y', errors='coerce')
            df['Bitis'] = df['Baslangic'] + pd.Timedelta(days=1)
            df = df.dropna(subset=['Baslangic'])
            if not df.empty:
                st.plotly_chart(px.timeline(df, x_start="Baslangic", x_end="Bitis", y="Personel", color="Durum", hover_name="Is Tanimi"), use_container_width=True)

# --- 4. ARŞİV ---
elif secim == "📂 Müşteri Arşivi":
    st.title("📂 Arşiv")
    if not df_m.empty:
        mus = st.selectbox("Müşteri:", df_m["Ad Soyad"].tolist())
        bilgi = df_m[df_m["Ad Soyad"] == mus].iloc[0]
        
        if "Etiket" in df_m.columns and str(bilgi["Etiket"]) != "nan":
            etiketler = str(bilgi["Etiket"]).split(",")
            st.markdown("".join([f"<span class='etiket'>#{e.strip()}</span>" for e in etiketler]), unsafe_allow_html=True)
            
        c1, c2, c3 = st.columns(3)
        c1.info(f"📞 {bilgi.get('Telefon', '-')}")
        c2.info(f"🆔 {bilgi.get('TC', '-')}")
        c3.success(f"💰 {bilgi.get('Ucret', '-')} TL")
        
        st.subheader("📝 Tarihçe")
        df_not = verileri_getir("Sheet1")
        if not df_not.empty:
            m_not = df_not[(df_not["Is Tanimi"].str.contains(mus, na=False)) & (df_not["Is Tanimi"].str.contains("NOT", na=False))]
            for i, r in m_not.iterrows():
                raw = r['Is Tanimi'].split("NOT]")[-1] if "NOT]" in r['Is Tanimi'] else r['Is Tanimi']
                st.markdown(f"<div class='tarihli-not'><b>📅 {r['Tarih']}</b>: {raw} <br><i>Dosya: {r.get('Dosya', '-')}</i></div>", unsafe_allow_html=True)
        
        with st.form("up"):
            txt = st.text_area("Not / Açıklama")
            d = st.file_uploader("Dosya"); tur = st.selectbox("Tür", ["Fatura", "Diğer"])
            if st.form_submit_button("Kaydet"):
                l = drive_yukle(d, mus, tur) if d else "-"
                msg = f"[{datetime.now().strftime('%H:%M')} - {aktif}]: {txt}"
                google_sheet_baglan("Sheet1").append_row([datetime.now().strftime("%d.%m.%Y"), "-", f"{mus} - [NOT] {msg} - [{tur}]", "-", "Tamamlandi", l, aktif])
                st.success("Kaydedildi"); st.rerun()

# --- 5. FİNANS ---
elif secim == "💰 Finans & Kâr":
    st.title("💰 Finans")
    df_c = verileri_getir("Cari")
    t1, t2, t3, t4 = st.tabs(["📊 Analiz", "💸 Ekle", "📄 OCR (KDV)", "🔄 Tahakkuk"])
    
    with t1:
        if not df_c.empty:
            df_c["Tutar"] = pd.to_numeric(df_c["Tutar"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
            t_t = df_c[df_c["Islem_Turu"].str.contains("Tahsilat", na=False)]["Tutar"].sum()
            t_g = df_c[df_c["Islem_Turu"].str.contains("Gider", na=False)]["Tutar"].sum()
            net = t_t - t_g
            c1, c2, c3 = st.columns(3)
            c1.metric("Tahsilat", f"{t_t:,.0f} TL"); c2.metric("Gider", f"{t_g:,.0f} TL"); c3.metric("Kâr", f"{net:,.0f} TL")
            st.dataframe(df_c, use_container_width=True)
        else: st.info("Veri yok.")
        
    with t2:
        with st.form("fin_ekle"):
            trh = st.date_input("Tarih"); tur = st.radio("Tür", ["Hizmet Bedeli (Borç)", "Tahsilat", "🔴 OFİS GİDERİ"])
            muh = "OFİS GİDERİ" if "GİDER" in tur else st.selectbox("Müşteri", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
            tut = st.number_input("Tutar"); ack = st.text_input("Açıklama")
            if st.form_submit_button("Kaydet"):
                google_sheet_baglan("Cari").append_row([trh.strftime("%d.%m.%Y"), muh, tur, tut, ack])
                onbellek_temizle(); st.success("Kaydedildi"); st.rerun()

    with t3:
        st.info("KDV PDF yükleyin, POS tutarını okuyalım.")
        up = st.file_uploader("KDV PDF", type="pdf")
        if up:
            val, txt = beyanname_analiz_et(up)
            if val > 0:
                st.success(f"✅ Okunan: {val:,.2f} TL")
                if st.button("Kaydet"):
                    google_sheet_baglan("Cari").append_row([datetime.now().strftime("%d.%m.%Y"), "OCR", "POS Bilgi", val, "KDV Okuma"])
                    st.success("Eklendi")
            else: st.error("Okunamadı")

    with t4:
        mus_t = st.selectbox("Müşteri Seç", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
        tutar_t = st.number_input("Aylık Tutar")
        if st.button("12 Aylık İşle"):
             rows=[[f"15.{i+1:02d}.2025", mus_t, "Hizmet Bedeli (Borç)", tutar_t, "Yıllık"] for i in range(12)]
             google_sheet_baglan("Cari").append_rows(rows); onbellek_temizle(); st.success("İşlendi")

# --- 6. KURULUŞ ---
elif secim == "🏢 Kuruluş Sihirbazı":
    st.title("🏢 Kuruluş (2026 Tarife)")
    with st.form("kur"):
        aday = st.text_input("Aday")
        sturu = st.radio("Tür", ["Şahıs İşletmesi", "Limited Şirket", "Anonim Şirket"], horizontal=True)
        sektor = st.selectbox("Sektör", ["Hizmet", "Alım-Satım", "İmalat - İnşaat", "Yabancı Ortaklı"])
        
        fiyat = {"Kurulus": 0, "Defter": 0}
        if sturu in FIYAT_TARIFESI:
            fiyat = FIYAT_TARIFESI[sturu].get(sektor, FIYAT_TARIFESI[sturu].get("Hizmet", {"Kurulus":0, "Defter":0}))
        
        st.info(f"Tarife: {fiyat['Kurulus']:,.0f} TL Kuruluş | {fiyat['Defter']:,.0f} TL Defter")
        
        c1, c2 = st.columns(2)
        son_kur = c1.number_input("Kuruluş (Teklif)", value=float(fiyat["Kurulus"]))
        son_def = c2.number_input("Aylık (Teklif)", value=float(fiyat["Defter"]))
        
        if st.form_submit_button("Teklif Kaydet"):
            baslik = f"{aday} - [AÇILIŞ] Şirket Kuruluşu"
            google_sheet_baglan("Sheet1").append_row([datetime.now().strftime("%d.%m.%Y"), "-", baslik, "-", "Bekliyor", "-", aktif])
            st.success("İşlem Başlatıldı")

# --- 7. AYARLAR & YEDEK (YENİ) ---
elif secim == "⚙️ Ayarlar & Yedek":
    st.title("⚙️ Ayarlar ve Güvenlik")
    
    st.subheader("📥 Toplu Müşteri Yükle (Excel)")
    uploaded_excel = st.file_uploader("Müşteri Listesi (Excel)", type="xlsx")
    if uploaded_excel:
        try:
            df_new = pd.read_excel(uploaded_excel)
            st.dataframe(df_new.head())
            if st.button("Bu Listeyi İçeri Aktar"):
                # Sütunları kontrol et ve aktar
                gerekli = ["Ad Soyad", "Telefon", "TC"]
                if all(col in df_new.columns for col in gerekli):
                    data = df_new[gerekli].values.tolist()
                    # Diğer sütunları boş geçerek ekle
                    final_data = [[row[0], row[1], row[2], "", "", "", ""] for row in data]
                    google_sheet_baglan("Musteriler").append_rows(final_data)
                    onbellek_temizle(); st.success(f"{len(data)} Müşteri Aktarıldı!")
                else:
                    st.error("Excel'de 'Ad Soyad', 'Telefon', 'TC' sütunları olmalı.")
        except Exception as e: st.error(f"Hata: {e}")

    st.divider()
    
    st.subheader("🛡️ Veri Yedekleme")
    st.write("Tüm sistem verilerini (Müşteriler, İşler, Cari) tek bir Excel dosyası olarak indir.")
    
    df_is = verileri_getir("Sheet1")
    df_mus = verileri_getir("Musteriler")
    df_cari = verileri_getir("Cari")
    
    if st.button("📦 YEDEĞİ HAZIRLA"):
        excel_data = excel_yedek_olustur(df_is, df_mus, df_cari)
        st.download_button(
            label="⬇️ Excel Olarak İndir (Backup.xlsx)",
            data=excel_data,
            file_name=f"Ofis_Yedek_{datetime.now().strftime('%d_%m_%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
