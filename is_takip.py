import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time

# --- 1. PREMIUM SAYFA AYARLARI ---
st.set_page_config(page_title="SMMM Halil Akça | Premium Panel", page_icon="🏛️", layout="wide")

# --- 2. GELİŞMİŞ CSS TASARIMI (UI/UX) ---
st.markdown("""
    <style>
    /* Ana Arka Plan */
    .stApp {
        background-color: #F1F5F9;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Sidebar Tasarımı */
    [data-testid="stSidebar"] {
        background-color: #0F172A;
        border-right: 1px solid #1E293B;
    }
    [data-testid="stSidebar"] .stMarkdown h1 {
        color: #F8FAFC !important;
        font-weight: 800;
        letter-spacing: -1px;
    }
    
    /* Kart Yapısı (Metric & Container) */
    div.stMetric {
        background-color: #FFFFFF;
        padding: 25px !important;
        border-radius: 20px !important;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05) !important;
        border: 1px solid #E2E8F0 !important;
    }
    
    /* Başlıklar */
    .main-title {
        background: linear-gradient(90deg, #1E293B 0%, #334155 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 3rem;
        font-weight: 800;
        text-align: center;
        margin-bottom: 5px;
    }
    .sub-title {
        color: #64748B;
        text-align: center;
        font-size: 1.2rem;
        margin-bottom: 40px;
    }
    
    /* Butonlar */
    .stButton>button {
        border-radius: 12px !important;
        padding: 10px 24px !important;
        font-weight: 600 !important;
        background-color: #2563EB !important;
        color: white !important;
        border: none !important;
        transition: all 0.2s ease !important;
    }
    .stButton>button:hover {
        background-color: #1D4ED8 !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
    }
    
    /* Tablo Güzelleştirme */
    .stDataFrame {
        background-color: white;
        padding: 10px;
        border-radius: 20px;
        border: 1px solid #E2E8F0;
    }
    
    /* Formlar */
    [data-testid="stForm"] {
        background-color: white !important;
        border-radius: 24px !important;
        padding: 40px !important;
        border: 1px solid #E2E8F0 !important;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.05) !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. VERİ BAĞLANTISI (GÜVENLİ) ---
@st.cache_resource
def google_baglan():
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            st.secrets["gcp_service_account"], 
            ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds).open("Is_Takip_Sistemi")
    except:
        return None

doc = google_baglan()

def verileri_getir(sayfa_adi):
    try:
        return pd.DataFrame(doc.worksheet(sayfa_adi).get_all_records())
    except:
        return pd.DataFrame()

# --- 4. SIDEBAR & NAVİGASYON ---
with st.sidebar:
    st.markdown("<h1 style='text-align: center;'>🏛️ HALİL AKÇA</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #94A3B8;'>Müşavir Yönetim Sistemi</p>", unsafe_allow_html=True)
    st.divider()
    
    menu = {
        "🏠 Dashboard": "📊 Genel Bakış",
        "➕ Yeni Kayıt": "➕ İş Ekle",
        "📋 İş Listesi": "✅ Yönetim",
        "👥 Mükellefler": "👥 Arşiv",
        "💰 Finans": "💰 Kasa"
    }
    secim = st.radio("Navigasyon", list(menu.keys()))
    
    st.divider()
    if st.button("🔄 Verileri Tazele", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 5. ANA İÇERİK ---
st.markdown(f"<div class='main-title'>SMMM HALİL AKÇA</div>", unsafe_allow_html=True)
st.markdown(f"<div class='sub-title'>Analiz, İş Takip ve Finansal Yönetim Kokpiti</div>", unsafe_allow_html=True)

if menu[secim] == "📊 Genel Bakış":
    df = verileri_getir("Sheet1")
    if not df.empty:
        # Üst Metrik Kartları
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Toplam İş", len(df))
        m2.metric("Bekleyen", len(df[df['Durum'] != 'Tamamlandi']), delta_color="inverse")
        m3.metric("Tamamlanan", len(df[df['Durum'] == 'Tamamlandi']))
        m4.metric("Verimlilik", f"%{int((len(df[df['Durum'] == 'Tamamlandi'])/len(df))*100)}")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Grafikler
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("### 📊 Personel Performansı")
            fig = px.bar(df[df['Durum'] != 'Tamamlandi']['Personel'].value_counts().reset_index(), 
                         x='index', y='Personel', color='index', 
                         template="plotly_white", color_discrete_sequence=px.colors.sequential.Blues_r)
            fig.update_layout(showlegend=False, bordercolor="#E2E8F0", plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
            
        with c2:
            st.markdown("### 🥧 İş Dağılımı")
            fig2 = px.pie(df, names='Durum', hole=0.6, color_discrete_sequence=px.colors.sequential.RdBu)
            fig2.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Henüz veri girişi yapılmamış.")

elif menu[secim] == "➕ İş Ekle":
    st.markdown("### 📝 Yeni Görev Oluştur")
    df_m = verileri_getir("Musteriler")
    df_p = verileri_getir("Personel")
    
    with st.form("premium_form"):
        col1, col2 = st.columns(2)
        tarih = col1.date_input("Başlangıç Tarihi")
        son_teslim = col2.date_input("Son Teslim Tarihi", value=None)
        
        m_list = df_m['Ad Soyad'].tolist() if not df_m.empty else ["Müşteri Listesi Boş"]
        musteri = st.selectbox("Mükellef Seçimi", m_list)
        
        is_tanimi = st.text_area("İş Açıklaması", placeholder="Yapılacak işlemi detaylandırın...")
        
        p_list = df_p['Personel_Adi'].tolist() if not df_p.empty else ["Halil", "Aslı", "Tuğçe", "Özlem"]
        personel = st.selectbox("Sorumlu Ataması", p_list)
        
        submitted = st.form_submit_button("🚀 Görevi Sisteme İşle")
        if submitted:
            if is_tanimi:
                doc.sheet1.append_row([
                    tarih.strftime("%d.%m.%Y"), "09:00", f"{musteri} - {is_tanimi}", 
                    "Bekliyor", personel, son_teslim.strftime("%d.%m.%Y") if son_teslim else ""
                ])
                st.success("İşlem Başarıyla Kaydedildi!")
                time.sleep(1)
                st.rerun()

elif menu[secim] == "✅ Yönetim":
    st.markdown("### 📋 İş Listesi Yönetimi")
    df = verileri_getir("Sheet1")
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        
        st.markdown("---")
        st.markdown("#### ⚡ Durum Güncelle")
        c1, c2 = st.columns([2, 1])
        is_idx = c1.selectbox("İş Seçin", df.index.tolist(), format_func=lambda x: f"{df.iloc[x]['Is Tanimi']}")
        yeni_durum = c2.selectbox("Yeni Durum", ["Bekliyor", "İşleme Alındı", "Tamamlandi", "İptal"])
        
        if st.button("Değişikliği Kaydet", use_container_width=True):
            doc.sheet1.update_cell(is_idx + 2, 4, yeni_durum)
            st.toast("Durum Güncellendi!", icon='✅')
            time.sleep(1)
            st.rerun()

elif menu[secim] == "👥 Arşiv":
    st.markdown("### 👥 Mükellef Veritabanı")
    df_m = verileri_getir("Musteriler")
    if not df_m.empty:
        st.dataframe(df_m, use_container_width=True)
    else:
        st.warning("Müşteri verisi bulunamadı.")

elif menu[secim] == "💰 Kasa":
    st.markdown("### 💰 Finansal Analiz")
    df_f = verileri_getir("Finans")
    if not df_f.empty:
        gelir = df_f[df_f['Tip'] == 'Gelir']['Tutar'].sum()
        gider = df_f[df_f['Tip'] == 'Gider']['Tutar'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam Tahsilat", f"{gelir:,.0f} ₺")
        c2.metric("Toplam Gider", f"{gider:,.0f} ₺", delta_color="inverse")
        c3.metric("Net Durum", f"{gelir-gider:,.0f} ₺")
        
        fig = go.Figure(go.Indicator(
            mode = "number+gauge+delta",
            value = gelir - gider,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Kâr Marjı", 'font': {'size': 24}},
            gauge = {'axis': {'range': [None, gelir]},
                     'bar': {'color': "#2563EB"},
                     'steps' : [
                         {'range': [0, gelir/2], 'color': "#F1F5F9"},
                         {'range': [gelir/2, gelir], 'color': "#E2E8F0"}]}))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Finansal kayıt bulunamadı.")
