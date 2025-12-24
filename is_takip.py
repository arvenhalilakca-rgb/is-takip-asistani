import streamlit as st
import pandas as pd
import re
import pdfplumber
import requests

# ==========================================
# 1. AYARLAR & TASARIM
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi (Sütun Ayarlı)",
    page_icon="🏢",
    layout="wide"
)

# API Ayarları
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

st.markdown("""
    <style>
    .stApp {background-color: #f0f2f6; font-family: 'Segoe UI', sans-serif;}
    .risk-box {
        background: #fff; border-left: 6px solid #d32f2f;
        padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 15px;
    }
    .metric-box {
        background: #f8f9fa; padding: 10px; border-radius: 5px; text-align: center; border: 1px solid #eee;
    }
    .metric-title {font-size: 11px; color: #666; font-weight: bold; text-transform: uppercase;}
    .metric-value {font-size: 16px; color: #333; font-weight: bold;}
    </style>
""", unsafe_allow_html=True)

# Session
if 'sonuclar' not in st.session_state: st.session_state['sonuclar'] = None
if 'mukellef_db' not in st.session_state: st.session_state['mukellef_db'] = None

# ==========================================
# 2. MOTOR FONKSİYONLARI
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
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        requests.post(url, json={'chatId': f"{SABIT_IHBAR_NO}@c.us", 'message': mesaj})
        return True
    except: return False

def id_bul_pdf(text):
    """PDF'ten 10 (VKN) veya 11 (TC) haneli numarayı çeker."""
    # 1. Öncelik: Tırnak içindeki net veri "1234567890"
    m1 = re.search(r'"(\d{10,11})"', text)
    if m1: return m1.group(1)
    
    # 2. Öncelik: Etiketli veri (Vergi Kimlik... TC Kimlik...)
    m2 = re.search(r'(?:Vergi Kimlik|TC Kimlik|Vergi No).*?(\d{10,11})', text, re.IGNORECASE | re.DOTALL)
    if m2: return m2.group(1)
    
    return None

def isim_eslestir(numara):
    """Numarayı Excel'in B (TC) ve C (VKN) sütunlarında arar, A (Unvan) sütununu döner."""
    if st.session_state['mukellef_db'] is None or not numara:
        return f"Tanımsız ({numara})"
        
    df = st.session_state['mukellef_db']
    numara = str(numara).strip()
    
    # Önce C Sütununda (Vergi No) Ara
    vkn_match = df[df['VKN'] == numara]
    if not vkn_match.empty:
        return vkn_match.iloc[0]['UNVAN']
        
    # Yoksa B Sütununda (TC) Ara
    tc_match = df[df['TC'] == numara]
    if not tc_match.empty:
        return tc_match.iloc[0]['UNVAN']
        
    return f"Listede Yok ({numara})"

# ==========================================
# 3. UYGULAMA
# ==========================================

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=70)
    st.header("MÜŞAVİR PANELİ")
    mod = st.radio("Seçenekler:", ["1. Excel Listesi Yükle", "2. KDV Analizi"])
    
    if mod == "1. Excel Listesi Yükle":
        st.warning("Excel Formatı:\nSütun A: Ünvan\nSütun B: TC No\nSütun C: Vergi No")

# --- MODÜL 1: EXCEL YÜKLEME ---
if mod == "1. Excel Listesi Yükle":
    st.title("📂 Mükellef Listesi (Sütun Eşleştirme)")
    st.info("Lütfen A, B ve C sütunlarının doğru olduğu Excel dosyasını yükleyin.")
    
    up_excel = st.file_uploader("Excel Dosyası", type=["xlsx", "xls"])
    
    if up_excel:
        try:
            # Excel'i oku (Header yok varsayabiliriz veya var varsayabiliriz, iloc ile sütun sırasına göre alacağız)
            df = pd.read_excel(up_excel, dtype=str)
            
            # SÜTUNLARI İNDEKSE GÖRE AL (A=0, B=1, C=2)
            # Kullanıcı talimatı: A=Unvan, B=TC, C=VergiNo
            # Veri güvenliği için yeni bir dataframe oluşturuyoruz
            clean_df = pd.DataFrame()
            
            if len(df.columns) >= 3:
                clean_df['UNVAN'] = df.iloc[:, 0].astype(str).str.strip()  # Sütun A
                clean_df['TC']    = df.iloc[:, 1].astype(str).str.strip()  # Sütun B
                clean_df['VKN']   = df.iloc[:, 2].astype(str).str.strip()  # Sütun C
                
                # NaN değerleri temizle
                clean_df = clean_df.fillna("")
                
                st.session_state['mukellef_db'] = clean_df
                st.success(f"✅ {len(clean_df)} Mükellef Yüklendi.")
                st.write("Veri Önizleme (İlk 5 Satır):")
                st.dataframe(clean_df.head())
            else:
                st.error("HATA: Excel dosyasında en az 3 sütun olmalı (A, B, C).")
                
        except Exception as e:
            st.error(f"Dosya hatası: {e}")

# --- MODÜL 2: ANALİZ ---
elif mod == "2. KDV Analizi":
    st.title("🕵️‍♂️ KDV Uyumsuzluk Analizi")
    
    if st.session_state['mukellef_db'] is None:
        st.error("⚠️ Önce '1. Excel Listesi Yükle' menüsünden listeyi yükleyiniz.")
        st.stop()
        
    pdf_up = st.file_uploader("KDV Beyannamesi (PDF)", type=["pdf"])
    
    if pdf_up:
        if st.button("ANALİZİ BAŞLAT", type="primary"):
            st.info("PDF taranıyor, A-B-C sütunlarına göre eşleştirme yapılıyor...")
            sonuclar = []
            
            with pdfplumber.open(pdf_up) as pdf:
                total = len(pdf.pages)
                bar = st.progress(0)
                
                for i, page in enumerate(pdf.pages):
                    bar.progress((i+1)/total)
                    text = page.extract_text()
                    if not text: continue
                    
                    if "KATMA DEĞER VERGİSİ" in text or "MATRAH" in text:
                        
                        # 1. PDF'ten Numarayı Bul
                        bulunan_id = id_bul_pdf(text)
                        
                        # 2. Listeden İsmi Çek
                        isim = isim_eslestir(bulunan_id)
                        
                        # 3. Verileri Çek
                        m_match = re.search(r"(?:TOPLAM MATRAH|Teslim ve Hizmetlerin Karşılığını).*?([\d\.,]+)", text, re.IGNORECASE)
                        matrah = text_to_float(m_match.group(1)) if m_match else 0.0
                        
                        k_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
                        kdv = text_to_float(k_match.group(1)) if k_match else 0.0
                        
                        pos_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
                        pos = text_to_float(pos_match.group(1)) if pos_match else 0.0
                        
                        # 4. Hesaplama
                        beyan = matrah + kdv
                        fark = pos - beyan
                        
                        # 50 TL Tolerans
                        if fark > 50:
                            sonuclar.append({
                                "Mükellef": isim,
                                "ID": bulunan_id,
                                "POS": pos,
                                "Beyan": beyan,
                                "Fark": fark
                            })
            
            st.session_state['sonuclar'] = pd.DataFrame(sonuclar)
            st.rerun()

    # SONUÇ EKRANI
    if st.session_state['sonuclar'] is not None:
        df = st.session_state['sonuclar']
        
        if df.empty:
            st.success("✅ Riskli kayıt bulunamadı.")
        else:
            st.error(f"🚨 {len(df)} Riskli Mükellef Tespit Edildi")
            
            for i, row in df.iterrows():
                ad = row['Mükellef']
                id_no = row['ID']
                
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"""
                        <div class='risk-box'>
                            <div style='font-size:18px; font-weight:bold; color:#d32f2f'>{ad}</div>
                            <div style='font-size:12px; color:#999; margin-bottom:10px'>Vergi/TC No: {id_no}</div>
                            <div style='display:flex; gap:15px;'>
                                <div class='metric-box'>
                                    <div class='metric-title'>POS TAHSİLAT</div>
                                    <div class='metric-value'>{para_formatla(row['POS'])}</div>
                                </div>
                                <div class='metric-box'>
                                    <div class='metric-title'>BEYAN (KDV DAHİL)</div>
                                    <div class='metric-value'>{para_formatla(row['Beyan'])}</div>
                                </div>
                                <div class='metric-box' style='border-color:#d32f2f; background:#fff5f5'>
                                    <div class='metric-title' style='color:#d32f2f'>EKSİK BEYAN</div>
                                    <div class='metric-value' style='color:#d32f2f'>{para_formatla(row['Fark'])}</div>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col2:
                        st.write("")
                        st.write("")
                        if st.button(f"İHBAR ET 📲", key=f"btn_{i}", type="secondary", use_container_width=True):
                            msg = (f"⚠️ *KDV RİSK RAPORU*\n\n"
                                   f"Firma: {ad}\nNo: {id_no}\n"
                                   f"POS: {para_formatla(row['POS'])}\n"
                                   f"Beyan: {para_formatla(row['Beyan'])}\n"
                                   f"Fark: {para_formatla(row['Fark'])}\n\n"
                                   f"Kontrol ediniz.")
                            
                            if whatsapp_gonder(msg): st.toast("Gönderildi ✅")
                            else: st.error("Hata!")
