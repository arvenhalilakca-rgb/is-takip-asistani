import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time

# --- 1. SAYFA AYARLARI VE TASARIM ---
st.set_page_config(page_title="SMMM Halil Akça | İşletim Sistemi", page_icon="💼", layout="wide")

st.markdown("""
    <style>
    .stApp {background-color: #F8FAFC;}
    [data-testid="stSidebar"] {background-color: #0F172A; border-right: 1px solid #1E293B;}
    .main-header {color: #1E293B; font-size: 2.2rem; font-weight: 800; text-align: center; margin-bottom: 10px; letter-spacing: -1px;}
    .sub-header {color: #64748B; text-align: center; margin-bottom: 30px; font-size: 1.1rem;}
    div.stMetric {background-color: #FFFFFF; padding: 20px; border-radius: 15px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); border: 1px solid #F1F5F9;}
    .stDataFrame {border-radius: 15px; overflow: hidden; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);}
    .stButton>button {border-radius: 10px; font-weight: 600; transition: all 0.3s;}
    .stButton>button:hover {transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1);}
    </style>
    """, unsafe_allow_html=True)

# --- 2. VERİ BAĞLANTISI ---
@st.cache_resource
def google_baglan():
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            st.secrets["gcp_service_account"], 
            ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        return client.open("Is_Takip_Sistemi")
    except Exception as e:
        st.error(f"Bağlantı Hatası: {e}")
        return None

doc = google_baglan()

def verileri_getir(sayfa_adi):
    try:
        sheet = doc.worksheet(sayfa_adi)
        return pd.DataFrame(sheet.get_all_records())
    except:
        return pd.DataFrame()

def onbellek_temizle():
    st.cache_data.clear()

# --- 3. YAN MENÜ ---
with st.sidebar:
    st.markdown("<h1 style='color:white; text-align:center; font-size: 1.5rem;'>SMMM HALİL AKÇA</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#94A3B8; text-align:center;'>Dijital Ofis Yönetimi</p>", unsafe_allow_html=True)
    st.divider()
    menu = ["📊 Yönetim Kokpiti", "➕ Yeni İş Girişi", "✅ İşleri Yönet", "👥 Mükellef Listesi", "💰 Finansal Durum"]
    secim = st.sidebar.selectbox("Gidilecek Sayfa", menu)
    st.divider()
    if st.button("🔄 Verileri Güncelle", use_container_width=True):
        onbellek_temizle()
        st.rerun()
    st.info("Sistem Durumu: Güvenli & Kapalı Devre")

st.markdown("<div class='main-header'>SMMM HALİL AKÇA ANALİZ VE İŞ TAKİP</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>Ofis Verimlilik ve Takip Platformu</div>", unsafe_allow_html=True)

# --- 4. SAYFA İÇERİKLERİ ---

if secim == "📊 Yönetim Kokpiti":
    df = verileri_getir("Sheet1")
    if not df.empty:
        # Metrikler
        toplam = len(df)
        bekleyen = len(df[df['Durum'] != 'Tamamlandi'])
        geciken = 0 # Basit mantık: Bugünün tarihi geçmişse (opsiyonel geliştirilebilir)
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Toplam Görev", toplam)
        m2.metric("Bekleyen İşler", bekleyen, delta=f"{int(bekleyen/toplam*100)}%", delta_color="inverse")
        m3.metric("Tamamlanan", toplam - bekleyen)
        
        st.divider()
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("👨‍💼 Personel İş Yükü")
            fig_p = px.bar(df[df['Durum'] != 'Tamamlandi']['Personel'].value_counts().reset_index(), 
                           x='index', y='Personel', color='index', text_auto=True,
                           labels={'index':'Personel', 'Personel':'İş Sayısı'},
                           color_discrete_sequence=px.colors.qualitative.Set3)
            fig_p.update_layout(showlegend=False, plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_p, use_container_width=True)
            
        with c2:
            st.subheader("📈 İş Durum Dağılımı")
            fig_d = px.pie(df, names='Durum', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_d, use_container_width=True)
    else:
        st.warning("Analiz için veri bulunamadı. Lütfen iş ekleyin.")

elif secim == "➕ Yeni İş Girişi":
    st.subheader("📝 Yeni Görev Tanımla")
    df_m = verileri_getir("Musteriler")
    df_p = verileri_getir("Personel")
    
    with st.container():
        with st.form("is_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            tarih = col1.date_input("Başlangıç Tarihi")
            saat = col2.time_input("Saat")
            son_teslim = col3.date_input("Son Teslim Tarihi", value=None)
            
            m_list = df_m['Ad Soyad'].tolist() if not df_m.empty else ["Müşteri Bulunamadı"]
            musteri = st.selectbox("Mükellef Seçimi", m_list)
            
            is_tanimi = st.text_area("İşin Detayı", placeholder="Yapılacak işlemi buraya yazın...")
            
            p_list = df_p['Personel_Adi'].tolist() if not df_p.empty else ["Halil", "Aslı", "Tuğçe", "Özlem"]
            personel = st.selectbox("Sorumlu Personel", p_list)
            
            if st.form_submit_button("✅ Görevi Kaydet", type="primary"):
                if is_tanimi:
                    doc.sheet1.append_row([
                        tarih.strftime("%d.%m.%Y"), 
                        saat.strftime("%H:%M"), 
                        f"{musteri} - {is_tanimi}", 
                        "Bekliyor", 
                        personel, 
                        son_teslim.strftime("%d.%m.%Y") if son_teslim else ""
                    ])
                    st.success("İş başarıyla kaydedildi!")
                    onbellek_temizle()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Lütfen iş tanımını doldurun.")

elif secim == "✅ İşleri Yönet":
    st.subheader("🛠️ İş Listesi ve Durum Güncelleme")
    df = verileri_getir("Sheet1")
    if not df.empty:
        # Filtreleme
        filtre = st.multiselect("Duruma Göre Filtrele", df['Durum'].unique(), default=df['Durum'].unique())
        df_filtered = df[df['Durum'].isin(filtre)]
        
        st.dataframe(df_filtered, use_container_width=True)
        
        st.divider()
        st.subheader("⚡ Hızlı İşlem")
        col1, col2 = st.columns(2)
        with col1:
            is_idx = st.selectbox("İş Seçin", df.index.tolist(), format_func=lambda x: f"{df.iloc[x]['Is Tanimi']}")
        with col2:
            yeni_durum = st.selectbox("Yeni Durum", ["Bekliyor", "İşleme Alındı", "Tamamlandi", "İptal"])
            
        if st.button("Durumu Güncelle", use_container_width=True):
            doc.sheet1.update_cell(is_idx + 2, 4, yeni_durum)
            st.success(f"'{df.iloc[is_idx]['Is Tanimi']}' durumu '{yeni_durum}' olarak güncellendi.")
            onbellek_temizle()
            time.sleep(1)
            st.rerun()
    else:
        st.info("Yönetilecek iş bulunamadı.")

elif secim == "👥 Mükellef Listesi":
    st.subheader("👥 Kayıtlı Mükellefler")
    df_m = verileri_getir("Musteriler")
    if not df_m.empty:
        st.dataframe(df_m, use_container_width=True)
        st.download_button("Excel Olarak İndir", df_m.to_csv(index=False), "musteri_listesi.csv", "text/csv")
    else:
        st.warning("Müşteri listesi boş.")

elif secim == "💰 Finansal Durum":
    st.subheader("💰 Gelir & Gider Analizi")
    df_f = verileri_getir("Finans") # Google Sheets'te 'Finans' sayfası olduğunu varsayıyoruz
    if not df_f.empty:
        gelir = df_f[df_f['Tip'] == 'Gelir']['Tutar'].sum()
        gider = df_f[df_f['Tip'] == 'Gider']['Tutar'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam Gelir", f"{gelir:,.2f} TL")
        c2.metric("Toplam Gider", f"{gider:,.2f} TL", delta_color="inverse")
        c3.metric("Net Kâr", f"{gelir-gider:,.2f} TL")
        
        fig_f = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = gelir - gider,
            title = {'text': "Kârlılık Durumu"},
            gauge = {'axis': {'range': [None, gelir]},
                     'bar': {'color': "#10B981"}}
        ))
        st.plotly_chart(fig_f, use_container_width=True)
    else:
        st.info("Finansal veri bulunamadı. 'Finans' sayfasını Google Sheets'e ekleyerek başlayabilirsiniz.")
