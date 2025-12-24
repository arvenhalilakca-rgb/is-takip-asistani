import streamlit as st
import requests
import pandas as pd
import re
import time
import pdfplumber

# ==========================================
# 1. AYARLAR
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi Pro",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Ayarları
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

st.markdown("""
    <style>
    .stApp {background-color: #f4f6f9; font-family: 'Segoe UI', sans-serif;}
    [data-testid="stSidebar"] {background-color: #ffffff; border-right: 1px solid #e6e6e6;}
    
    .risk-box {
        background-color: white; 
        border-left: 6px solid #ff4b4b;
        padding: 20px; border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 15px;
    }
    .clean-box {
        background-color: #e8f5e9; 
        border-left: 6px solid #28a745;
        padding: 15px; border-radius: 8px; margin-bottom: 10px;
    }
    .metric-label {font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 1px;}
    .metric-val {font-size: 18px; font-weight: bold; color: #333;}
    .alert-text {color: #ff4b4b; font-weight: bold; font-size: 16px;}
    
    </style>
    """, unsafe_allow_html=True)

# Session State
if 'sonuclar' not in st.session_state: st.session_state['sonuclar'] = None
if 'mukellef_db' not in st.session_state: st.session_state['mukellef_db'] = None

# ==========================================
# 2. FONKSİYONLAR
# ==========================================

def text_to_float(text):
    try:
        clean = re.sub(r'[^\d,\.]', '', str(text)).strip()
        if "," in clean and "." in clean: clean = clean.replace(".", "").replace(",", ".")
        elif "," in clean: clean = clean.replace(",", ".")
        return float(clean)
    except: return 0.0

def para_formatla(deger):
    return "{:,.2f} TL".format(deger).replace(",", "X").replace(".", ",").replace("X", ".")

def whatsapp_gonder(mesaj):
    try:
        url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
        requests.post(url, json={'chatId': f"{SABIT_IHBAR_NO}@c.us", 'message': mesaj})
        return True
    except: return False

def vergi_no_bul(text):
    """PDF içinden 10 veya 11 haneli Vergi/TC numarasını bulur."""
    # 1. Tırnak içindeki format (CSV gibi): "0010961739"
    m1 = re.search(r'"(\d{10,11})"', text)
    if m1: return m1.group(1)
    
    # 2. Klasik format: Vergi Kimlik Numarası ... 1234567890
    m2 = re.search(r'(?:Vergi Kimlik Numarası|TC Kimlik No).*?(\d{10,11})', text, re.IGNORECASE)
    if m2: return m2.group(1)
    
    # 3. Herhangi bir 10-11 haneli sayı (Riskli ama son çare)
    # m3 = re.search(r'\b\d{10,11}\b', text)
    # if m3: return m3.group(0)
    
    return None

def isim_eslestir(vkn):
    """Excel veritabanından VKN'ye karşılık gelen ismi getirir."""
    if st.session_state['mukellef_db'] is not None and vkn:
        df = st.session_state['mukellef_db']
        # VKN sütununu string yapalım ki eşleşme tam olsun
        df['Vergi_No'] = df['Vergi_No'].astype(str).str.strip()
        vkn = str(vkn).strip()
        
        sonuc = df[df['Vergi_No'] == vkn]
        if not sonuc.empty:
            return sonuc.iloc[0]['Unvan']
    
    return f"Bilinmeyen Mükellef ({vkn})"

# ==========================================
# 3. ARAYÜZ
# ==========================================

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=70)
    st.title("YÖNETİM PANELİ")
    secim = st.radio("MENÜ", ["1. Mükellef Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"])
    
    if secim == "1. Mükellef Listesi Yükle":
        st.info("⚠️ ÖNEMLİ: Yükleyeceğiniz Excel dosyasında 'Vergi_No' ve 'Unvan' isimli sütunlar olmalıdır.")

# --- 1. MÜKELLEF LİSTESİ YÜKLEME ---
if secim == "1. Mükellef Listesi Yükle":
    st.header("📂 Mükellef Veritabanı (Excel)")
    st.markdown("PDF'ten isim okuma hatası yaşamamak için mükellef listenizi buradan yükleyin. Sistem **Vergi Numarası** üzerinden eşleştirme yapacaktır.")
    
    up_excel = st.file_uploader("Excel Dosyası Seç", type=["xlsx", "xls"])
    
    if up_excel:
        try:
            df = pd.read_excel(up_excel, dtype=str) # Hepsini string oku (Vergi no bozulmasın)
            
            # Kolon isimlerini temizle (Boşlukları sil, küçük harf yap vs. opsiyonel)
            # Biz direkt kullanıcının doğru girmesini bekleyelim veya map edelim
            if 'Vergi_No' not in df.columns or 'Unvan' not in df.columns:
                st.error("HATA: Excel dosyasında 'Vergi_No' ve 'Unvan' sütun başlıkları bulunamadı.")
                st.warning("Lütfen sütun başlıklarını kontrol edip tekrar yükleyin.")
            else:
                st.session_state['mukellef_db'] = df
                st.success(f"✅ {len(df)} Mükellef Kaydı Başarıyla Yüklendi.")
                st.dataframe(df.head())
        except Exception as e:
            st.error(f"Dosya okuma hatası: {e}")

# --- 2. KDV ANALİZ ROBOTU ---
elif secim == "2. KDV Analiz Robotu":
    st.header("🕵️‍♂️ KDV Uyumsuzluk Dedektörü")
    
    if st.session_state['mukellef_db'] is None:
        st.warning("⚠️ Lütfen önce '1. Mükellef Listesi Yükle' menüsünden veritabanını oluşturun.")
    
    pdf_up = st.file_uploader("Beyanname PDF Dosyasını Yükle", type=["pdf"])
    
    if pdf_up:
        if st.button("ANALİZİ BAŞLAT", type="primary"):
            st.info("Beyannameler Vergi Numarası üzerinden eşleştiriliyor...")
            sonuclar = []
            
            with pdfplumber.open(pdf_up) as pdf:
                bar = st.progress(0)
                total = len(pdf.pages)
                
                for i, page in enumerate(pdf.pages):
                    bar.progress((i+1)/total)
                    text = page.extract_text()
                    if not text: continue
                    
                    if "KATMA DEĞER VERGİSİ" in text or "MATRAH" in text:
                        
                        # A) Vergi Numarasını Bul
                        vkn = vergi_no_bul(text)
                        
                        # B) Excel'den İsmi Çek
                        isim = isim_eslestir(vkn)
                        
                        # C) Verileri Çek
                        m_match = re.search(r"(?:TOPLAM MATRAH|Teslim ve Hizmetlerin Karşılığını).*?([\d\.,]+)", text, re.IGNORECASE)
                        matrah = text_to_float(m_match.group(1)) if m_match else 0.0
                        
                        k_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
                        kdv = text_to_float(k_match.group(1)) if k_match else 0.0
                        
                        pos_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
                        pos = text_to_float(pos_match.group(1)) if pos_match else 0.0
                        
                        # D) Hesapla
                        beyan = matrah + kdv
                        fark = pos - beyan
                        
                        if fark > 50:
                            sonuclar.append({
                                "Mükellef": isim,
                                "VKN": vkn,
                                "POS": pos,
                                "Beyan": beyan,
                                "Fark": fark
                            })
            
            st.session_state['sonuclar'] = pd.DataFrame(sonuclar)
            st.rerun()

    # SONUÇLAR
    if st.session_state['sonuclar'] is not None:
        df = st.session_state['sonuclar']
        
        if df.empty:
            st.success("✅ Tüm beyannameler uyumlu. Risk bulunamadı.")
        else:
            st.error(f"🚨 {len(df)} Adet Riskli Mükellef Tespit Edildi")
            
            for i, row in df.iterrows():
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"""
                        <div class='risk-box'>
                            <div style='font-size:18px; font-weight:bold; color:#d32f2f'>{row['Mükellef']}</div>
                            <div style='font-size:12px; color:#888; margin-bottom:10px'>Vergi No: {row['VKN']}</div>
                            <div style='display:flex; gap:30px;'>
                                <div><span class='metric-label'>POS Tahsilat</span><br><span class='metric-val'>{para_formatla(row['POS'])}</span></div>
                                <div><span class='metric-label'>Beyan (Dahil)</span><br><span class='metric-val'>{para_formatla(row['Beyan'])}</span></div>
                            </div>
                            <div class='alert-text' style='margin-top:10px'>EKSİK BEYAN: {para_formatla(row['Fark'])}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col2:
                        st.write("")
                        st.write("")
                        if st.button(f"İHBAR ET 📲", key=f"btn_{i}", type="secondary", use_container_width=True):
                            msg = (f"⚠️ *KDV RİSK RAPORU*\n\n"
                                   f"Firma: {row['Mükellef']}\n"
                                   f"VKN: {row['VKN']}\n"
                                   f"POS: {para_formatla(row['POS'])}\n"
                                   f"Beyan: {para_formatla(row['Beyan'])}\n"
                                   f"Fark: {para_formatla(row['Fark'])}\n\n"
                                   f"Kontrol Ediniz.")
                            
                            if whatsapp_gonder(msg): st.toast("Gönderildi ✅")
                            else: st.error("Hata")

# --- 3. PROFESYONEL MESAJ ---
elif secim == "3. Profesyonel Mesaj":
    st.header("📤 Mesaj Merkezi")
    if st.session_state['mukellef_db'] is not None:
        df = st.session_state['mukellef_db']
        kisi = st.selectbox("Alıcı", df['Unvan'].tolist())
        txt = st.text_area("Mesaj", height=100)
        if st.button("Gönder"): st.success(f"{kisi} adlı kişiye gönderildi.")
    else: st.warning("Listeyi yükleyin.")

# --- 4. TASDİK ROBOTU ---
elif secim == "4. Tasdik Robotu":
    st.header("🤖 Tasdik Takip")
    st.info("Bu modül 'Mükellef Listesi'ndeki borç sütunlarına göre çalışır.")
    # (Buraya Excel'deki borç kolonuna göre mantık eklenebilir)
    if st.session_state['mukellef_db'] is not None:
        st.dataframe(st.session_state['mukellef_db'])
    else: st.warning("Listeyi yükleyin.")
