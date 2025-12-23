import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time

# --- 1. PREMIUM SAYFA AYARLARI ---
st.set_page_config(page_title="SMMM Halil Akça | KDV Analiz & İş Takip", page_icon="🏛️", layout="wide")

# --- 2. GELİŞMİŞ CSS TASARIMI (UI/UX) ---
st.markdown("""
    <style>
    .stApp { background-color: #F1F5F9; font-family: 'Inter', sans-serif; }
    [data-testid="stSidebar"] { background-color: #0F172A; border-right: 1px solid #1E293B; }
    div.stMetric { background-color: #FFFFFF; padding: 25px !important; border-radius: 20px !important; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05) !important; border: 1px solid #E2E8F0 !important; }
    .main-title { background: linear-gradient(90deg, #1E293B 0%, #334155 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.5rem; font-weight: 800; text-align: center; margin-bottom: 5px; }
    .sub-title { color: #64748B; text-align: center; font-size: 1.1rem; margin-bottom: 30px; }
    .stButton>button { border-radius: 12px !important; font-weight: 600 !important; background-color: #2563EB !important; color: white !important; transition: all 0.2s ease !important; }
    .risk-card { background-color: #FEE2E2; border-left: 5px solid #EF4444; padding: 15px; border-radius: 10px; margin-bottom: 10px; }
    .safe-card { background-color: #DCFCE7; border-left: 5px solid #22C55E; padding: 15px; border-radius: 10px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. VERİ BAĞLANTISI ---
@st.cache_resource
def google_baglan():
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("Is_Takip_Sistemi")
    except: return None

doc = google_baglan()

def verileri_getir(sayfa_adi):
    try: return pd.DataFrame(doc.worksheet(sayfa_adi).get_all_records())
    except: return pd.DataFrame()

# --- 4. SIDEBAR ---
with st.sidebar:
    st.markdown("<h1 style='text-align: center;'>🏛️ HALİL AKÇA</h1>", unsafe_allow_html=True)
    st.divider()
    menu = {
        "🏠 Dashboard": "📊 Genel Bakış",
        "🔍 KDV Analiz": "🔍 KDV Denetim",
        "➕ Yeni Kayıt": "➕ İş Ekle",
        "📋 İş Listesi": "✅ Yönetim",
        "👥 Mükellefler": "👥 Arşiv"
    }
    secim = st.radio("Navigasyon", list(menu.keys()))
    if st.button("🔄 Verileri Tazele", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown(f"<div class='main-title'>SMMM HALİL AKÇA</div>", unsafe_allow_html=True)
st.markdown(f"<div class='sub-title'>Analiz, KDV Denetim ve İş Takip Sistemi</div>", unsafe_allow_html=True)

# --- 5. SAYFA İÇERİKLERİ ---

if menu[secim] == "🔍 KDV Denetim":
    st.markdown("### 🔍 KDV Beyannamesi & POS Tutarlılık Analizi")
    st.info("Bu modül, beyan edilen KDV matrahı ile banka POS verilerini karşılaştırarak risk analizi yapar.")
    
    # Veri Giriş Alanı (Simüle edilmiş veya Google Sheets'ten çekilen)
    with st.expander("📥 Analiz İçin Veri Girişi", expanded=True):
        with st.form("kdv_analiz_form"):
            c1, c2, c3 = st.columns(3)
            df_m = verileri_getir("Musteriler")
            m_list = df_m['Ad Soyad'].tolist() if not df_m.empty else ["Müşteri Seçin"]
            secilen_m = c1.selectbox("Mükellef", m_list)
            matrah = c2.number_input("Toplam KDV Matrahı (KDV Hariç)", min_value=0.0, step=1000.0)
            pos_tahsilat = c3.number_input("Kredi Kartı (POS) Tahsilatı (KDV Dahil)", min_value=0.0, step=1000.0)
            
            kdv_orani = st.selectbox("Genel KDV Oranı", [20, 10, 1, 0], index=0)
            
            if st.form_submit_button("Analiz Et ve Kaydet"):
                kdv_tutari = matrah * (kdv_orani / 100)
                toplam_beyan = matrah + kdv_tutari
                fark = toplam_beyan - pos_tahsilat
                durum = "RİSKLİ" if fark < 0 else "UYGUN"
                
                # Google Sheets'e kaydet (KDV_Analiz adında bir sayfa olduğunu varsayıyoruz)
                try:
                    analiz_sheet = doc.worksheet("KDV_Analiz")
                    analiz_sheet.append_row([datetime.now().strftime("%d.%m.%Y"), secilen_m, matrah, pos_tahsilat, fark, durum])
                    st.success("Analiz tamamlandı ve kaydedildi!")
                except:
                    st.warning("KDV_Analiz sayfası bulunamadı, sadece ekranda gösteriliyor.")
                
                st.session_state['son_analiz'] = {"m": secilen_m, "matrah": matrah, "pos": pos_tahsilat, "fark": fark, "durum": durum, "beyan": toplam_beyan}

    # Analiz Sonuç Ekranı
    if 'son_analiz' in st.session_state:
        res = st.session_state['son_analiz']
        st.divider()
        col1, col2 = st.columns([2, 1])
        
        with col1:
            if res['durum'] == "RİSKLİ":
                st.markdown(f"""<div class='risk-card'>
                    <h4>🚨 DİKKAT: POS Tutarsızlığı Tespit Edildi!</h4>
                    <p><b>Mükellef:</b> {res['m']}<br>
                    <b>Beyan Edilen Toplam (KDV Dahil):</b> {res['beyan']:,.2f} ₺<br>
                    <b>POS Tahsilatı:</b> {res['pos']:,.2f} ₺<br>
                    <b>Fark:</b> <span style='color:red'>{res['fark']:,.2f} ₺</span></p>
                    <p><i>POS tahsilatı, beyan edilen KDV dahil matrahtan fazladır. İnceleme riski mevcuttur!</i></p>
                </div>""", unsafe_allow_html=True)
                
                # Otomatik Mesaj Hazırlama
                mesaj = f"Sayın {res['m']}, {datetime.now().strftime('%m/%Y')} dönemi KDV beyannamenizde kredi kartı (POS) tahsilatınız ({res['pos']:,.2f} TL), beyan edilen matrahın üzerindedir. Lütfen kontrol ediniz."
                st.text_area("Tuğçe Hanım'a Gönderilecek Mesaj Taslağı:", mesaj)
            else:
                st.markdown(f"""<div class='safe-card'>
                    <h4>✅ Veriler Tutarlı</h4>
                    <p><b>Mükellef:</b> {res['m']}<br>
                    <b>Durum:</b> POS tahsilatı beyan sınırları içerisindedir.</p>
                </div>""", unsafe_allow_html=True)

        with col2:
            fig = go.Figure(go.Bar(
                x=['Beyan (KDV Dahil)', 'POS Tahsilat'],
                y=[res['beyan'], res['pos']],
                marker_color=['#2563EB', '#EF4444' if res['durum'] == "RİSKLİ" else '#22C55E']
            ))
            fig.update_layout(title="Karşılaştırma Grafiği", height=300)
            st.plotly_chart(fig, use_container_width=True)

elif menu[secim] == "📊 Genel Bakış":
    df = verileri_getir("Sheet1")
    if not df.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Toplam İş", len(df))
        m2.metric("Bekleyen", len(df[df['Durum'] != 'Tamamlandi']), delta_color="inverse")
        m3.metric("Tamamlanan", len(df[df['Durum'] == 'Tamamlandi']))
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 📊 Personel Yükü")
            fig = px.bar(df[df['Durum'] != 'Tamamlandi']['Personel'].value_counts().reset_index(), x='index', y='Personel', template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.markdown("### 🥧 İş Durumu")
            fig2 = px.pie(df, names='Durum', hole=0.5)
            st.plotly_chart(fig2, use_container_width=True)

elif menu[secim] == "➕ İş Ekle":
    st.markdown("### 📝 Yeni Görev")
    df_m = verileri_getir("Musteriler")
    with st.form("is_form"):
        tarih = st.date_input("Tarih")
        m_list = df_m['Ad Soyad'].tolist() if not df_m.empty else ["Boş"]
        musteri = st.selectbox("Mükellef", m_list)
        is_tanimi = st.text_area("İş Detayı")
        personel = st.selectbox("Sorumlu", ["Halil", "Aslı", "Tuğçe", "Özlem"])
        if st.form_submit_button("Kaydet"):
            doc.sheet1.append_row([tarih.strftime("%d.%m.%Y"), "09:00", f"{musteri} - {is_tanimi}", "Bekliyor", personel, ""])
            st.success("Kaydedildi!")

elif menu[secim] == "✅ Yönetim":
    st.markdown("### 📋 İş Listesi")
    df = verileri_getir("Sheet1")
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        is_idx = st.selectbox("İş Seç", df.index.tolist(), format_func=lambda x: f"{df.iloc[x]['Is Tanimi']}")
        yeni_durum = st.selectbox("Durum", ["Bekliyor", "Tamamlandi"])
        if st.button("Güncelle"):
            doc.sheet1.update_cell(is_idx + 2, 4, yeni_durum)
            st.rerun()

elif menu[secim] == "👥 Arşiv":
    st.markdown("### 👥 Mükellefler")
    df_m = verileri_getir("Musteriler")
    if not df_m.empty: st.dataframe(df_m, use_container_width=True)
