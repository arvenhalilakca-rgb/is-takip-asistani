import streamlit as st
import requests
import pandas as pd
import re
import time
import pdfplumber

# ==========================================
# 1. AYARLAR VE TASARIM
# ==========================================
st.set_page_config(
    page_title="KDV Analiz & İhbar Sistemi",
    page_icon="⚖️",
    layout="wide"
)

# API Bilgileri (Burayı kendi sisteminize göre doldurmalısınız veya st.secrets kullanmalısınız)
# Eğer secrets yoksa kod hata vermesin diye varsayılan boş değerler atıyoruz.
ID_INSTANCE = st.secrets["ID_INSTANCE"] if "ID_INSTANCE" in st.secrets else "YOUR_INSTANCE_ID"
API_TOKEN = st.secrets["API_TOKEN"] if "API_TOKEN" in st.secrets else "YOUR_API_TOKEN"
SABIT_IHBAR_NO = "905351041616"  # Hedef Numara: 0535 104 16 16

# Özel CSS Tasarımı
st.markdown("""
    <style>
    .stApp {background-color: #f8f9fa;}
    .risk-box {
        background-color: #ffffff;
        border-left: 8px solid #dc3545;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .safe-box {
        background-color: #d4edda;
        border-left: 8px solid #28a745;
        padding: 15px;
        border-radius: 10px;
        color: #155724;
        margin-bottom: 10px;
    }
    .stat-text {font-size: 14px; color: #6c757d;}
    .big-money {font-size: 18px; font-weight: bold; color: #343a40;}
    .alert-money {font-size: 20px; font-weight: bold; color: #dc3545;}
    </style>
    """, unsafe_allow_html=True)

# Session State Tanımları
if 'sonuclar' not in st.session_state: st.session_state['sonuclar'] = None

# ==========================================
# 2. YARDIMCI FONKSİYONLAR
# ==========================================

def text_to_float(text):
    """
    Metin içindeki 1.234,56 formatındaki sayıları float'a çevirir.
    """
    if not text: return 0.0
    try:
        clean = re.sub(r'[^\d,\.]', '', str(text)).strip()
        # Türkçe format: Binlik ayracı nokta, ondalık virgül (1.000,50)
        if "," in clean and "." in clean:
            clean = clean.replace(".", "").replace(",", ".")
        elif "," in clean:
            clean = clean.replace(",", ".")
        return float(clean)
    except:
        return 0.0

def para_formatla(deger):
    """Sayıyı Türkçe para formatına çevirir."""
    return "{:,.2f} TL".format(deger).replace(",", "X").replace(".", ",").replace("X", ".")

def whatsapp_gonder(numara, mesaj):
    """Green-API üzerinden mesaj gönderir."""
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    payload = {'chatId': f"{numara}@c.us", 'message': mesaj}
    try:
        r = requests.post(url, json=payload)
        return r.status_code == 200
    except:
        return False

# ==========================================
# 3. ANALİZ MOTORU
# ==========================================
def beyanname_analiz_et(pdf_file):
    bulunanlar = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for sayfa_no, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text: continue
            
            # --- A) Mükellef İsmi Bulma ---
            # Strateji: "Soyadı (Unvanı)" kelimesini bulup altındaki satırı alacağız.
            # Ancak "BEYANNAMEYİ DÜZENLEYEN" kısmına (Müşavir) karışmamalı.
            lines = text.split('\n')
            mukellef_adi = "Bilinmeyen Mükellef"
            
            # Sayfanın sadece üst yarısına bakalım (Mükellef genelde üsttedir)
            limit_index = len(lines)
            for idx, line in enumerate(lines):
                if "BEYANNAMEYİ DÜZENLEYEN" in line:
                    limit_index = idx
                    break
            
            for idx, line in enumerate(lines[:limit_index]):
                if "Soyadı (Unvanı)" in line or "Unvanı" in line:
                    if idx + 1 < limit_index:
                        aday_isim = lines[idx+1].strip()
                        # Eğer isim çok kısaysa veya gereksiz karakterse bir alt satıra daha bak
                        if len(aday_isim) < 3 and idx + 2 < limit_index:
                            aday_isim = lines[idx+2].strip()
                        
                        # Mali müşavir kelimeleri geçmiyorsa bu mükelleftir
                        if "SMMM" not in aday_isim and "MÜŞAVİR" not in aday_isim:
                            mukellef_adi = aday_isim
                            break

            # --- B) Finansal Verileri Çekme ---
            
            # 1. Matrah (Teslim ve Hizmet Bedeli)
            # Genellikle "TOPLAM MATRAH" veya "Teslim ve Hizmetlerin..." satırındadır.
            matrah_match = re.search(r"(?:TOPLAM MATRAH|Teslim ve Hizmetlerin Karşılığını).*?([\d\.,]+)", text, re.IGNORECASE)
            matrah = text_to_float(matrah_match.group(1)) if matrah_match else 0.0
            
            # 2. Hesaplanan KDV (Tevkifatlı + Tevkifatsız Toplamı)
            kdv_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
            hesaplanan_kdv = text_to_float(kdv_match.group(1)) if kdv_match else 0.0
            
            # 3. Kredi Kartı (POS) Tahsilatı
            kk_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
            kk_tutar = text_to_float(kk_match.group(1)) if kk_match else 0.0
            
            # --- C) Yeni Formül ---
            # (Matrah + Hesaplanan KDV) vs Kredi Kartı
            # Özel Matrah dahil EDİLMİYOR.
            
            beyan_kdv_dahil = matrah + hesaplanan_kdv
            fark = kk_tutar - beyan_kdv_dahil
            
            # Tolerans (Örn: 50 TL altı farkları yoksay)
            durum = "RISKLI" if fark > 50 else "TEMIZ"
            
            if durum == "RISKLI":
                bulunanlar.append({
                    "Sayfa": sayfa_no + 1,
                    "Mükellef": mukellef_adi,
                    "Matrah": matrah,
                    "KDV": hesaplanan_kdv,
                    "Beyan_Toplam": beyan_kdv_dahil,
                    "KK_Tutar": kk_tutar,
                    "Fark": fark
                })
                
    return pd.DataFrame(bulunanlar)

# ==========================================
# 4. ARAYÜZ (FRONTEND)
# ==========================================

st.title("🕵️‍♂️ KDV Uyumsuzluk Dedektörü")
st.markdown("""
Bu sistem yüklenen KDV beyannamesindeki **(Matrah + KDV)** toplamını, **Kredi Kartı (POS)** tahsilatları ile karşılaştırır.
Eğer POS tahsilatı, beyan edilen tutardan fazlaysa uyarı verir.
""")

uploaded_file = st.file_uploader("KDV Beyannamesi (PDF) Yükle", type=["pdf"])

if uploaded_file:
    if st.button("🚀 ANALİZİ BAŞLAT", type="primary"):
        with st.spinner("Beyannameler taranıyor..."):
            df_sonuc = beyanname_analiz_et(uploaded_file)
            st.session_state['sonuclar'] = df_sonuc
            
        if df_sonuc.empty:
            st.success("✅ Taranan dosyalarda herhangi bir riskli durum (POS Farkı) tespit edilmedi.")
        else:
            st.warning(f"⚠️ Toplam {len(df_sonuc)} adet riskli mükellef tespit edildi!")

# Sonuçları Göster
if st.session_state['sonuclar'] is not None and not st.session_state['sonuclar'].empty:
    df = st.session_state['sonuclar']
    
    for i, row in df.iterrows():
        # Verileri Hazırla
        ad = row['Mükellef']
        kk_str = para_formatla(row['KK_Tutar'])
        beyan_str = para_formatla(row['Beyan_Toplam'])
        fark_str = para_formatla(row['Fark'])
        matrah_str = para_formatla(row['Matrah'])
        kdv_str = para_formatla(row['KDV'])
        
        # Kart Yapısı
        with st.container():
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f"""
                <div class='risk-box'>
                    <h3 style='margin-top:0; color:#c82333;'>🚨 {ad}</h3>
                    <div style='display:flex; flex-wrap:wrap; gap:20px; margin-top:15px;'>
                        <div>
                            <span class='stat-text'>Kredi Kartı (POS)</span><br>
                            <span class='big-money'>{kk_str}</span>
                        </div>
                        <div>
                            <span class='stat-text'>Beyan Edilen (KDV Dahil)</span><br>
                            <span class='big-money'>{beyan_str}</span>
                            <br><span style='font-size:11px; color:#888'>(Matrah: {matrah_str} + KDV: {kdv_str})</span>
                        </div>
                    </div>
                    <hr>
                    <div style='text-align:right'>
                        <span class='stat-text'>EKSİK BEYAN FARKI:</span>
                        <span class='alert-money'>{fark_str}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.write("")
                st.write("")
                st.info(f"📞 Hedef No:\n**0535 104 16 16**")
                
                # İhbar Butonu
                if st.button(f"SİNYAL GÖNDER 📲", key=f"btn_{i}", type="primary", use_container_width=True):
                    # Mesaj İçeriği
                    mesaj = (
                        f"⚠️ *KDV RİSK ANALİZ RAPORU*\n\n"
                        f"📄 *Mükellef:* {ad}\n"
                        f"💳 *POS Tahsilatı:* {kk_str}\n"
                        f"📊 *Beyan (Matrah+KDV):* {beyan_str}\n"
                        f"‼️ *TESPİT EDİLEN FARK:* {fark_str}\n\n"
                        f"Lütfen kayıtlara bakınız."
                    )
                    
                    # Gönderim İşlemi
                    # Not: API ayarları yapılmadıysa ekranda sadece uyarı gösteririz.
                    if ID_INSTANCE == "YOUR_INSTANCE_ID":
                        st.error("API Ayarları Eksik! Kod içerisine ID_INSTANCE ve API_TOKEN giriniz.")
                    else:
                        sonuc = whatsapp_gonder(SABIT_IHBAR_NO, mesaj)
                        if sonuc:
                            st.toast(f"✅ Mesaj İletildi: {ad}")
                        else:
                            st.error("Mesaj gönderilemedi. API hatası.")

    # İstersen toplu tabloyu da göster
    with st.expander("📂 Detaylı Excel Görünümü"):
        st.dataframe(df)
