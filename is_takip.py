import streamlit as st
import pandas as pd
import re
import pdfplumber
import requests

# ==========================================
# 1. AYARLAR & GÖRÜNÜM
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi (Otomatik Eşleşme)",
    page_icon="🏢",
    layout="wide"
)

# API Ayarları
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

st.markdown("""
    <style>
    .stApp {background-color: #f7f9fc; font-family: 'Segoe UI', sans-serif;}
    .success-box {background-color: #d4edda; color: #155724; padding: 15px; border-radius: 8px; border: 1px solid #c3e6cb;}
    .error-box {background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; border: 1px solid #f5c6cb;}
    .info-card {background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 10px;}
    .risk-card {border-left: 6px solid #dc3545;}
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

def vkn_bul_pdf(text):
    """PDF Sayfasındaki Vergi Kimlik Numarasını (10 veya 11 hane) bulur."""
    # 1. Öncelik: Tırnak içindeki net veri "1234567890" (Sizin PDF yapınız)
    m1 = re.search(r'"(\d{10,11})"', text)
    if m1: return m1.group(1)
    
    # 2. Öncelik: Etiketli veri
    m2 = re.search(r'(?:Vergi Kimlik|TC Kimlik).*?(\d{10,11})', text, re.IGNORECASE | re.DOTALL)
    if m2: return m2.group(1)
    
    return None

def isim_getir(vkn):
    """Excel veritabanından VKN'ye karşılık gelen ismi bulur."""
    if st.session_state['mukellef_db'] is not None and vkn:
        df = st.session_state['mukellef_db']
        vkn = str(vkn).strip()
        
        # DataFrame içinde ara
        sonuc = df[df['VKN'] == vkn]
        if not sonuc.empty:
            return sonuc.iloc[0]['ISIM']
            
    return f"LİSTEDE YOK ({vkn})"

# ==========================================
# 3. YÖNETİM PANELİ
# ==========================================

with st.sidebar:
    st.header("MÜŞAVİR KULESİ")
    mod = st.radio("Seçenekler:", ["1. Mükellef Listesi (Excel)", "2. KDV Analizi"])

# --- MODÜL 1: EXCEL YÜKLEME ---
if mod == "1. Mükellef Listesi (Excel)":
    st.title("📂 Mükellef Listesi Yükle")
    st.info("e-Mükellef sisteminden aldığınız Excel dosyasını yükleyin. Sütun isimleri otomatik algılanacaktır.")
    
    up_file = st.file_uploader("Excel Dosyası (.xlsx / .xls)", type=["xlsx", "xls", "csv"])
    
    if up_file:
        try:
            # Dosya Okuma
            if up_file.name.endswith(".csv"):
                df = pd.read_csv(up_file, dtype=str)
            else:
                df = pd.read_excel(up_file, dtype=str)
            
            # --- AKILLI KOLON EŞLEŞTİRME ---
            # Dosyanızdaki olası kolon isimlerini standart hale getiriyoruz
            yeni_kolonlar = {}
            for col in df.columns:
                col_clean = col.strip()
                # VKN Kolonunu Bul
                if col_clean in ["TC/VN", "Vergi No", "VN", "TC", "VKN"]:
                    yeni_kolonlar[col] = "VKN"
                # İsim Kolonunu Bul
                elif col_clean in ["Ünvan / Ad Soyad", "Ünvan", "Ad Soyad", "Firma Adı", "Mükellef"]:
                    yeni_kolonlar[col] = "ISIM"
            
            df.rename(columns=yeni_kolonlar, inplace=True)
            
            # Kontrol
            if "VKN" in df.columns and "ISIM" in df.columns:
                # Veri Temizliği (Boşlukları sil)
                df["VKN"] = df["VKN"].astype(str).str.strip()
                df["ISIM"] = df["ISIM"].astype(str).str.strip()
                
                st.session_state['mukellef_db'] = df
                st.markdown(f"<div class='success-box'>✅ Başarılı! <b>{len(df)}</b> mükellef sisteme yüklendi.</div>", unsafe_allow_html=True)
                st.dataframe(df[["ISIM", "VKN"]].head())
            else:
                st.markdown(f"<div class='error-box'>❌ HATA: Gerekli sütunlar bulunamadı.<br>Dosyanızdaki sütunlar: {list(df.columns)}<br>Beklenen: 'TC/VN' ve 'Ünvan / Ad Soyad'</div>", unsafe_allow_html=True)
                
        except Exception as e:
            st.error(f"Dosya okuma hatası: {e}")

# --- MODÜL 2: ANALİZ ---
elif mod == "2. KDV Analizi":
    st.title("🕵️‍♂️ KDV & POS Uyumsuzluk Analizi")
    
    if st.session_state['mukellef_db'] is None:
        st.warning("⚠️ Lütfen önce '1. Mükellef Listesi' menüsünden Excel dosyasını yükleyin.")
        st.stop()
        
    pdf_up = st.file_uploader("KDV Beyannamesi (PDF)", type=["pdf"])
    
    if pdf_up:
        if st.button("ANALİZİ BAŞLAT", type="primary"):
            st.info("Beyannameler taranıyor, Vergi No üzerinden isimler eşleştiriliyor...")
            sonuclar = []
            
            with pdfplumber.open(pdf_up) as pdf:
                total = len(pdf.pages)
                bar = st.progress(0)
                
                for i, page in enumerate(pdf.pages):
                    bar.progress((i+1)/total)
                    text = page.extract_text()
                    if not text: continue
                    
                    # Sadece ilgili sayfaları işle
                    if "KATMA DEĞER VERGİSİ" in text or "MATRAH" in text:
                        
                        # 1. PDF'ten Vergi No (VKN) Bul
                        vkn = vkn_bul_pdf(text)
                        
                        # 2. Excel Listesinden İsmi Bul
                        isim = isim_getir(vkn)
                        
                        # 3. Verileri Çek
                        m_match = re.search(r"(?:TOPLAM MATRAH|Teslim ve Hizmetlerin Karşılığını).*?([\d\.,]+)", text, re.IGNORECASE)
                        matrah = text_to_float(m_match.group(1)) if m_match else 0.0
                        
                        k_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
                        kdv = text_to_float(k_match.group(1)) if k_match else 0.0
                        
                        pos_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
                        pos = text_to_float(pos_match.group(1)) if pos_match else 0.0
                        
                        # 4. Hesaplama: (Matrah + KDV) vs POS
                        beyan = matrah + kdv
                        fark = pos - beyan
                        
                        # Fark varsa listeye ekle
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

    # SONUÇ LİSTESİ
    if st.session_state['sonuclar'] is not None:
        df = st.session_state['sonuclar']
        
        if df.empty:
            st.success("✅ Tebrikler! Hiçbir riskli mükellef bulunamadı.")
        else:
            st.error(f"🚨 Toplam {len(df)} Adet Riskli Durum Tespit Edildi")
            
            for i, row in df.iterrows():
                m_ad = row['Mükellef']
                m_vkn = row['VKN']
                
                # Kart Tasarımı
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"""
                        <div class='info-card risk-card'>
                            <div style='font-size:18px; font-weight:bold; color:#d9534f'>{m_ad}</div>
                            <div style='font-size:12px; color:#777'>Vergi No: {m_vkn}</div>
                            <hr style='margin:10px 0; border-top:1px solid #eee;'>
                            <div style='display:flex; justify-content:space-between; width:80%'>
                                <div><b>POS Tahsilat:</b><br>{para_formatla(row['POS'])}</div>
                                <div><b>Beyan (Dahil):</b><br>{para_formatla(row['Beyan'])}</div>
                            </div>
                            <div style='margin-top:10px; color:#d9534f; font-weight:bold'>⚠️ EKSİK BEYAN: {para_formatla(row['Fark'])}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col2:
                        st.write("") 
                        st.write("")
                        if st.button(f"İHBAR ET 📲", key=f"btn_{i}", type="secondary", use_container_width=True):
                            msg = (f"⚠️ *KDV RİSK RAPORU*\n\n"
                                   f"Firma: {m_ad}\nVKN: {m_vkn}\n"
                                   f"POS: {para_formatla(row['POS'])}\n"
                                   f"Beyan: {para_formatla(row['Beyan'])}\n"
                                   f"Fark: {para_formatla(row['Fark'])}\n\n"
                                   f"Lütfen kontrol ediniz.")
                            
                            if whatsapp_gonder(msg): st.toast("✅ Mesaj İletildi!")
                            else: st.error("Gönderim Hatası!")
