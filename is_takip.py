import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import plotly.express as px

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="SMMM Halil Akça - Analiz & İş Takip", page_icon="📊", layout="wide")

# --- TASARIM ---
st.markdown("""
    <style>
    .stApp {background-color: #F4F7F6;}
    [data-testid="stSidebar"] {background-color: #1E293B;}
    .main-header {color: #1E293B; font-size: 2.5rem; font-weight: bold; text-align: center; margin-bottom: 20px;}
    div.stMetric {background-color: #FFFFFF; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    </style>
    """, unsafe_allow_html=True)

# --- BAĞLANTILAR ---
try:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], 
        ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open("Is_Takip_Sistemi")
except Exception as e:
    st.error(f"⚠️ Bağlantı Hatası: {e}"); st.stop()

# --- VERİ FONKSİYONLARI ---
@st.cache_data(ttl=30)
def verileri_getir(sayfa_adi):
    try:
        sheet = spreadsheet.worksheet(sayfa_adi)
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

def onbellek_temizle():
    verileri_getir.clear()

# --- YAN MENÜ ---
with st.sidebar:
    st.markdown("<h2 style='color:white; text-align:center;'>SMMM HALİL AKÇA</h2>", unsafe_allow_html=True)
    st.divider()
    menu = ["📊 Genel Bakış & Analiz", "➕ Yeni İş Girişi", "✅ İş Yönetimi & Düzenleme", "👥 Müşteri Portföyü"]
    secim = st.radio("Menü Seçimi:", menu)
    st.divider()
    if st.button("🔄 Verileri Yenile"):
        onbellek_temizle()
        st.rerun()

st.markdown(f"<div class='main-header'>SMMM HALİL AKÇA ANALİZ VE İŞ TAKİP</div>", unsafe_allow_html=True)

# --- SAYFALAR ---

if secim == "📊 Genel Bakış & Analiz":
    df = verileri_getir("Sheet1")
    if not df.empty:
        # Metrikler
        bekleyen = len(df[df['Durum'] != 'Tamamlandi'])
        tamamlanan = len(df[df['Durum'] == 'Tamamlandi'])
        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam Görev", len(df))
        c2.metric("Bekleyen İşler", bekleyen, delta_color="inverse")
        c3.metric("Tamamlananlar", tamamlanan)
        
        st.divider()
        
        # Grafikler
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Personel İş Yükü")
            fig_p = px.pie(df[df['Durum'] != 'Tamamlandi'], names='Personel', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_p, use_container_width=True)
        
        with col2:
            st.subheader("İş Durum Dağılımı")
            fig_d = px.bar(df['Durum'].value_counts().reset_index(), x='index', y='Durum', color='index', labels={'index':'Durum', 'Durum':'Sayı'})
            st.plotly_chart(fig_d, use_container_width=True)
    else:
        st.info("Henüz analiz edilecek veri bulunmuyor.")

elif secim == "➕ Yeni İş Girişi":
    st.subheader("📝 Yeni Görev Tanımla")
    df_m = verileri_getir("Musteriler")
    df_p = verileri_getir("Personel")
    
    with st.form("yeni_is_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        tarih = c1.date_input("Başlangıç")
        saat = c2.time_input("Saat")
        son_teslim = c3.date_input("Son Teslim", value=None)
        
        musteri_listesi = df_m['Ad Soyad'].tolist() if not df_m.empty else ["Müşteri Listesi Boş"]
        musteri = st.selectbox("Mükellef", musteri_listesi)
        
        is_tanimi = st.text_area("İşin Detayı", placeholder="Yapılacak işlemi buraya yazın...")
        
        personel_listesi = df_p['Personel_Adi'].tolist() if not df_p.empty else ["Halil", "Aslı", "Tuğçe", "Özlem"]
        personel = st.selectbox("Sorumlu Personel", personel_listesi)
        
        if st.form_submit_button("Sisteme Kaydet", type="primary"):
            if is_tanimi:
                try:
                    sheet = spreadsheet.sheet1
                    sheet.append_row([
                        tarih.strftime("%d.%m.%Y"), 
                        saat.strftime("%H:%M"), 
                        f"{musteri} - {is_tanimi}", 
                        "Bekliyor", 
                        personel, 
                        son_teslim.strftime("%d.%m.%Y") if son_teslim else ""
                    ])
                    st.success("Kayıt Başarılı!")
                    onbellek_temizle()
                except Exception as e:
                    st.error(f"Hata: {e}")
            else:
                st.warning("Lütfen iş tanımını boş bırakmayın.")

elif secim == "✅ İş Yönetimi & Düzenleme":
    st.subheader("🛠️ İş Listesi ve Durum Güncelleme")
    df = verileri_getir("Sheet1")
    if not df.empty:
        # Veri Düzenleme Ekranı
        st.write("Aşağıdaki tablodan işlerin durumunu takip edebilirsiniz:")
        st.dataframe(df, use_container_width=True)
        
        st.divider()
        st.subheader("Durum Güncelle")
        is_sec = st.selectbox("Güncellenecek İşi Seçin", df.index.tolist(), format_func=lambda x: f"{df.iloc[x]['Tarih']} - {df.iloc[x]['Is Tanimi']}")
        yeni_durum = st.selectbox("Yeni Durum", ["Bekliyor", "İşleme Alındı", "Tamamlandi", "İptal"])
        
        if st.button("Durumu Güncelle"):
            sheet = spreadsheet.sheet1
            # Google Sheets'te satır numarası index+2'dir (başlık satırı ve 0-index farkı)
            sheet.update_cell(is_sec + 2, 4, yeni_durum)
            st.success("Durum güncellendi!")
            onbellek_temizle()
            st.rerun()
    else:
        st.info("Yönetilecek iş bulunamadı.")

elif secim == "👥 Müşteri Portföyü":
    st.subheader("Mükellef Listesi")
    df_m = verileri_getir("Musteriler")
    if not df_m.empty:
        st.dataframe(df_m, use_container_width=True)
    else:
        st.warning("Müşteri listesi yüklenemedi.")
