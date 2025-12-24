import streamlit as st
import pandas as pd
import re
import pdfplumber
import requests
import time

# ==========================================
# 1. AYARLAR & CSS
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi (Pro Veri Okuyucu)",
    page_icon="🗼",
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
    [data-testid="stSidebar"] {background-color: #fff; border-right: 1px solid #ddd;}
    
    .terminal-window {
        background-color: #1e1e1e; color: #00ff41; font-family: monospace;
        padding: 15px; border-radius: 8px; height: 200px; overflow-y: auto;
        font-size: 12px; margin-bottom: 20px;
    }
    
    .card {
        background: white; padding: 15px; border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 10px; border: 1px solid #eee;
    }
    .risk-card {border-left: 5px solid #d32f2f;}
    .clean-card {border-left: 5px solid #28a745;}
    
    .stat-val {font-weight: bold; font-size: 15px; color: #333;}
    .stat-lbl {font-size: 11px; color: #777;}
    </style>
    """, unsafe_allow_html=True)

# Session
if 'sonuclar' not in st.session_state: st.session_state['sonuclar'] = None
if 'mukellef_db' not in st.session_state: st.session_state['mukellef_db'] = None

# ==========================================
# 2. MOTOR: GELİŞMİŞ VERİ AVCISI
# ==========================================

def text_to_float(text):
    try:
        # Tırnakları ve boşlukları temizle
        text = str(text).replace('"', '').replace("'", "").strip()
        # Sadece rakam, nokta ve virgül kalsın
        clean = re.sub(r'[^\d,\.]', '', text)
        if "," in clean and "." in clean: clean = clean.replace(".", "").replace(",", ".")
        elif "," in clean: clean = clean.replace(",", ".")
        return float(clean)
    except: return 0.0

def para_formatla(deger):
    return "{:,.2f} TL".format(deger).replace(",", "X").replace(".", ",").replace("X", ".")

def whatsapp_gonder(numara, mesaj):
    target = f"{SABIT_IHBAR_NO}@c.us" if numara == "SABIT" else f"{numara}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        requests.post(url, json={'chatId': target, 'message': mesaj})
        return True
    except: return False

def vkn_bul(text):
    """PDF'ten ID bulur."""
    m1 = re.search(r'"(\d{10,11})"', text) 
    if m1: return m1.group(1)
    m2 = re.search(r'(?:Vergi Kimlik|TC Kimlik|Vergi No).*?(\d{10,11})', text, re.IGNORECASE | re.DOTALL)
    if m2: return m2.group(1)
    return None

def isim_eslestir_excel(numara):
    if st.session_state['mukellef_db'] is None: return f"Bilinmeyen ({numara})"
    df = st.session_state['mukellef_db']
    numara = str(numara).strip()
    
    res_c = df[df['C_VKN'] == numara]
    if not res_c.empty: return res_c.iloc[0]['A_UNVAN']
    
    res_b = df[df['B_TC'] == numara]
    if not res_b.empty: return res_b.iloc[0]['A_UNVAN']
    
    return f"Listede Yok ({numara})"

def veri_cozucu_pro(text, anahtar_kelimeler):
    """
    Bu fonksiyon, PDF içindeki veriyi bulmak için hem CSV (tırnaklı) hem standart formatı dener.
    En agresif okuma yöntemidir.
    """
    for kelime in anahtar_kelimeler:
        # YÖNTEM 1: CSV Formatı -> "Matrah","100.000,00"
        # Kelime, tırnak, virgül, tırnak, SAYI
        pattern_csv = r'"' + re.escape(kelime) + r'".*?,\s*"([\d\.,]+)"'
        m1 = re.search(pattern_csv, text, re.IGNORECASE | re.DOTALL)
        if m1: return text_to_float(m1.group(1))
        
        # YÖNTEM 2: Standart Format -> Matrah ... 100.000,00
        pattern_std = re.escape(kelime) + r'.*?([\d\.,]+)'
        m2 = re.search(pattern_std, text, re.IGNORECASE | re.DOTALL)
        if m2: return text_to_float(m2.group(1))

        # YÖNTEM 3: Kelime ... sayı (daha esnek)
        pattern_loose = re.escape(kelime) + r'\s+([\d\.,]+)'
        m3 = re.search(pattern_loose, text, re.IGNORECASE)
        if m3: return text_to_float(m3.group(1))

    return 0.0

# ==========================================
# 3. ARAYÜZ
# ==========================================

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.header("MÜŞAVİR PANELİ")
    secim = st.radio("MENÜ", ["1. Excel Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"])

# --- 1. LİSTE YÜKLEME ---
if secim == "1. Excel Listesi Yükle":
    st.title("📂 Excel Veritabanı")
    st.info("Sütunlar: A (Unvan), B (TC), C (Vergi No)")
    
    up = st.file_uploader("Dosya Seç", type=["xlsx", "xls"])
    if up:
        try:
            raw_df = pd.read_excel(up, dtype=str)
            if len(raw_df.columns) >= 3:
                df = pd.DataFrame()
                df['A_UNVAN'] = raw_df.iloc[:, 0].astype(str).str.strip()
                df['B_TC']    = raw_df.iloc[:, 1].astype(str).str.strip()
                df['C_VKN']   = raw_df.iloc[:, 2].astype(str).str.strip()
                
                # Varsa Tel
                if len(raw_df.columns) >= 4: df['D_TEL'] = raw_df.iloc[:, 3].astype(str).str.strip()
                else: df['D_TEL'] = ""
                
                st.session_state['mukellef_db'] = df.fillna("")
                st.success(f"✅ {len(df)} Mükellef Yüklendi.")
            else: st.error("Eksik sütun.")
        except Exception as e: st.error(str(e))

# --- 2. KDV ANALİZ ROBOTU ---
elif secim == "2. KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz Üssü (Pro Okuyucu)")
    
    if st.session_state['mukellef_db'] is None:
        st.warning("Önce listeyi yükleyin.")
        st.stop()
        
    pdf_up = st.file_uploader("KDV PDF", type=["pdf"])
    
    if pdf_up:
        if st.button("🚀 ANALİZİ BAŞLAT", type="primary"):
            
            # Terminal
            terminal = st.empty()
            logs = []
            def log_yaz(t, color="#0f0"):
                logs.append(f"<span style='color:{color}'> > {t}</span>")
                if len(logs)>10: logs.pop(0)
                terminal.markdown(f"<div class='terminal-window'>{'<br>'.join(logs)}</div>", unsafe_allow_html=True)
                time.sleep(0.01)
            
            log_yaz("Motor başlatıldı...", "white")
            
            sonuclar = []
            
            with pdfplumber.open(pdf_up) as pdf:
                total = len(pdf.pages)
                bar = st.progress(0)
                
                for i, page in enumerate(pdf.pages):
                    bar.progress((i+1)/total)
                    text = page.extract_text()
                    if not text: continue
                    
                    if "KATMA DEĞER VERGİSİ" in text or "MATRAH" in text:
                        vkn = vkn_bul(text)
                        isim = isim_eslestir_excel(vkn)
                        
                        # --- GELİŞMİŞ VERİ ÇEKME (BURASI DEĞİŞTİ) ---
                        
                        # 1. MATRAH: Hem "Toplam Matrah" hem "Matrah" hem de uzun cümleyi arar
                        matrah = veri_cozucu_pro(text, [
                            "TOPLAM MATRAH", 
                            "Matrah", 
                            "Teslim ve Hizmetlerin Karşılığını Teşkil Eden Bedel"
                        ])
                        
                        # 2. KDV: Hem "Toplam Hesaplanan" hem "Hesaplanan KDV" arar
                        kdv = veri_cozucu_pro(text, [
                            "TOPLAM HESAPLANAN KDV", 
                            "Hesaplanan KDV Toplamı", 
                            "Hesaplanan KDV"
                        ])
                        
                        # 3. POS: Hem "Kredi Kartı ile Tahsil" hem "Kredi Kartı" arar
                        pos = veri_cozucu_pro(text, [
                            "Kredi Kartı ile Tahsil Edilen Teslim ve Hizmetlerin KDV Dahil Karşılığını Teşkil Eden Bedel",
                            "Kredi Kartı ile Tahsil", 
                            "Kredi Kartı"
                        ])
                        
                        beyan = matrah + kdv
                        fark = pos - beyan
                        durum = "RISKLI" if fark > 50 else "TEMIZ"
                        
                        if durum == "RISKLI":
                            log_yaz(f"UYARI: {isim[:15]}.. Fark: {int(fark)}", "red")
                        
                        sonuclar.append({
                            "Mükellef": isim, "VKN": vkn, "POS": pos,
                            "Beyan": beyan, "Fark": fark, "Durum": durum
                        })
            
            st.session_state['sonuclar'] = pd.DataFrame(sonuclar)
            log_yaz("Bitti.", "white")
            terminal.empty()

    # --- SONUÇLAR ---
    if st.session_state['sonuclar'] is not None:
        df = st.session_state['sonuclar']
        riskliler = df[df['Durum']=="RISKLI"]
        temizler = df[df['Durum']=="TEMIZ"]
        
        tab1, tab2 = st.tabs([f"🚨 RİSKLİLER ({len(riskliler)})", f"✅ SORUNSUZLAR ({len(temizler)})"])
        
        with tab1:
            if riskliler.empty: st.success("Temiz.")
            else:
                for i, row in riskliler.iterrows():
                    with st.container():
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.markdown(f"""
                            <div class='card risk-card'>
                                <div class='card-title'>{row['Mükellef']}</div>
                                <div class='card-sub'>VKN: {row['VKN']}</div>
                                <div style='display:flex; gap:15px; margin-top:10px'>
                                    <div><span class='stat-lbl'>POS</span><br><span class='stat-val'>{para_formatla(row['POS'])}</span></div>
                                    <div><span class='stat-lbl'>BEYAN</span><br><span class='stat-val'>{para_formatla(row['Beyan'])}</span></div>
                                </div>
                                <div style='color:#d32f2f; font-weight:bold; margin-top:5px'>FARK: {para_formatla(row['Fark'])}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        with c2:
                            st.write("")
                            if st.button("🚨 İHBAR ET", key=f"r_{i}", type="primary"):
                                msg = f"⚠️ *KDV RİSKİ*\nFirma: {row['Mükellef']}\nPOS: {para_formatla(row['POS'])}\nBeyan: {para_formatla(row['Beyan'])}\nFark: {para_formatla(row['Fark'])}"
                                if whatsapp_gonder("SABIT", msg): st.toast("Gitti!")

        with tab2:
            if temizler.empty: st.info("Yok.")
            else:
                for i, row in temizler.iterrows():
                    st.markdown(f"""
                    <div class='card clean-card'>
                        <div class='card-title' style='font-size:16px'>{row['Mükellef']}</div>
                        <div style='display:flex; gap:15px; font-size:14px;'>
                            <div>POS: <b>{para_formatla(row['POS'])}</b></div>
                            <div>Beyan: <b>{para_formatla(row['Beyan'])}</b></div>
                            <div style='color:#28a745'>✓ UYUMLU</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# --- 3. MESAJ ---
elif secim == "3. Profesyonel Mesaj":
    st.title("📤 Mesaj")
    if st.session_state['mukellef_db'] is not None:
        df = st.session_state['mukellef_db']
        kisi = st.selectbox("Kişi", df['A_UNVAN'])
        tel = df[df['A_UNVAN']==kisi].iloc[0].get('D_TEL', "")
        st.write(f"Tel: {tel}")
        txt = st.text_area("Mesaj")
        if st.button("Gönder"):
            if whatsapp_gonder(tel, txt): st.success("OK")
            else: st.error("Hata")
    else: st.warning("Liste yükle.")

# --- 4. TASDİK ---
elif secim == "4. Tasdik Robotu":
    st.title("🤖 Tasdik")
    if st.session_state['mukellef_db'] is not None:
        st.dataframe(st.session_state['mukellef_db'])
    else: st.warning("Liste yükle.")
