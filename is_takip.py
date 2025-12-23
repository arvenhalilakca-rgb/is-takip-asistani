import streamlit as st
import pandas as pd
import pdfplumber # PDF'den metin ayıklamak için en stabil kütüphane
from datetime import datetime
import io
import re

# --- 1. SAYFA AYARLARI ---
st.set_page_config(page_title="SMMM Halil Akça | AI KDV Denetim", page_icon="🤖", layout="wide")

# --- 2. TASARIM ---
st.markdown("""
    <style>
    .stApp { background-color: #F8FAFC; }
    .report-card { background-color: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #E2E8F0; margin-bottom: 15px; }
    .risk-high { border-left: 8px solid #EF4444; }
    .risk-low { border-left: 8px solid #10B981; }
    .main-title { color: #1E293B; font-size: 2.5rem; font-weight: 800; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. FONKSİYONLAR (BEYANNAME OKUMA MOTORU) ---
def beyanname_analiz_et(pdf_file):
    results = []
    with pdfplumber.open(pdf_file) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text: continue
            
            # --- VERİ AYIKLAMA MANTIĞI (REGEX) ---
            # Not: Bu desenler standart KDV1 beyannamesi formatına göre optimize edilmiştir.
            
            # 1. Mükellef Adı/Unvanı (Genelde üst kısımdadır)
            unvan_match = re.search(r"Soyadı \(Unvanı\)\s+(.*)", text)
            unvan = unvan_match.group(1).strip() if unvan_match else f"Bilinmeyen Mükellef (Sayfa {i+1})"
            
            # 2. Matrah Toplamı
            matrah_match = re.search(r"Matrah Toplamı\s+([\d\.,]+)", text)
            matrah = float(matrah_match.group(1).replace(".", "").replace(",", ".")) if matrah_match else 0.0
            
            # 3. Hesaplanan KDV
            kdv_match = re.search(r"Hesaplanan Katma Değer Vergisi\s+([\d\.,]+)", text)
            kdv = float(kdv_match.group(1).replace(".", "").replace(",", ".")) if kdv_match else 0.0
            
            # 4. Kredi Kartı ile Tahsil Edilen (POS) - Genelde en alt tablodadır
            pos_match = re.search(r"Kredi Kartı ile Tahsil Edilen Teslim ve Hizmetlerin Bedeli\s+([\d\.,]+)", text)
            pos = float(pos_match.group(1).replace(".", "").replace(",", ".")) if pos_match else 0.0
            
            # --- HESAPLAMA VE RİSK ANALİZİ ---
            toplam_gelir = matrah + kdv
            fark = toplam_gelir - pos
            risk_durumu = "🚨 RİSKLİ" if fark < 0 else "✅ UYGUN"
            
            results.append({
                "Mükellef": unvan,
                "Matrah": matrah,
                "KDV": kdv,
                "Toplam Beyan": toplam_gelir,
                "POS Tahsilat": pos,
                "Fark": fark,
                "Durum": risk_durumu
            })
    return pd.DataFrame(results)

# --- 4. ARAYÜZ ---
st.markdown("<div class='main-title'>SMMM HALİL AKÇA AI DENETİM</div>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#64748B;'>Toplu KDV Beyannamesi Analiz ve Risk Tespit Sistemi</p>", unsafe_allow_html=True)
st.divider()

# Yan Menü
with st.sidebar:
    st.header("⚙️ Ayarlar")
    st.info("Sistem, yüklediğiniz PDF'deki her sayfayı ayrı bir beyanname olarak kabul eder ve analiz eder.")
    if st.button("Verileri Sıfırla"):
        st.rerun()

# Ana Ekran
col1, col2 = st.columns([1, 3])

with col1:
    st.subheader("📥 Dosya Yükleme")
    uploaded_file = st.file_uploader("Beyannameleri içeren PDF dosyasını seçin", type="pdf")
    
    if uploaded_file is not None:
        if st.button("Analizi Başlat", type="primary", use_container_width=True):
            with st.spinner("Yapay zeka beyannameleri okuyor..."):
                try:
                    df_sonuc = beyanname_analiz_et(uploaded_file)
                    st.session_state['analiz_sonuc'] = df_sonuc
                    st.success(f"{len(df_sonuc)} Beyanname analiz edildi!")
                except Exception as e:
                    st.error(f"Hata oluştu: {e}")

with col2:
    if 'analiz_sonuc' in st.session_state:
        df = st.session_state['analiz_sonuc']
        
        # Özet Metrikler
        s1, s2, s3 = st.columns(3)
        s1.metric("Toplam Beyanname", len(df))
        s2.metric("Riskli Mükellef", len(df[df['Durum'] == "🚨 RİSKLİ"]), delta_color="inverse")
        s3.metric("Toplam POS Hacmi", f"{df['POS Tahsilat'].sum():,.2f} ₺")
        
        st.divider()
        
        # Detaylı Tablo
        st.subheader("📋 Analiz Sonuç Listesi")
        st.dataframe(df.style.apply(lambda x: ['background-color: #fee2e2' if v == "🚨 RİSKLİ" else '' for v in x], axis=1), use_container_width=True)
        
        # Riskli Mükellefler İçin Otomatik Mesajlar
        riskli_df = df[df['Durum'] == "🚨 RİSKLİ"]
        if not riskli_df.empty:
            st.divider()
            st.subheader("⚠️ Riskli Mükellefler İçin Uyarı Taslakları")
            for _, row in riskli_df.iterrows():
                with st.expander(f"📩 {row['Mükellef']} için mesaj hazırla"):
                    mesaj = f"Sayın {row['Mükellef']}, KDV beyannamenizde POS tahsilatınız ({row['POS Tahsilat']:,.2f} TL), beyan edilen matrahın ({row['Toplam Beyan']:,.2f} TL) üzerindedir. Lütfen kontrol ediniz."
                    st.text_area("Mesaj Metni:", mesaj, height=100)
                    st.button(f"WhatsApp'a Kopyala ({row['Mükellef']})")
    else:
        st.info("Analiz sonuçlarını görmek için sol taraftan PDF yükleyip 'Analizi Başlat' butonuna basın.")

# --- 5. GEREKLİ KÜTÜPHANE UYARISI ---
# requirements.txt dosyanıza 'pdfplumber' eklemeyi unutmayın!
