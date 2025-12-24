import streamlit as st
import requests
import pandas as pd
import re
import time
import pdfplumber

# ==========================================
# 1. AYARLAR & MATRIX TASARIM
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi - Master Sürüm",
    page_icon="🗼",
    layout="wide"
)

# API Ayarları
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

st.markdown("""
    <style>
    .stApp {background-color: #000000; color: #0f0; font-family: 'Courier New', sans-serif;}
    
    /* Terminal Görünümü */
    .terminal-box {
        background-color: #111; border: 1px solid #333; color: #00ff00;
        padding: 15px; height: 300px; overflow-y: auto; font-family: monospace;
        box-shadow: 0 0 10px rgba(0,255,0,0.2); margin-bottom: 20px;
    }
    
    /* Kartlar */
    .risk-card {
        background-color: #1a1a1a; border-left: 5px solid #ff0000;
        padding: 15px; margin-bottom: 10px; border-radius: 5px;
    }
    .white-text {color: #ffffff;}
    .gray-text {color: #aaaaaa; font-size: 12px;}
    .big-num {font-size: 18px; font-weight: bold; color: #fff;}
    
    .stButton>button {
        background-color: #333; color: #0f0; border: 1px solid #0f0;
        transition: 0.3s;
    }
    .stButton>button:hover {background-color: #0f0; color: #000;}
    </style>
    """, unsafe_allow_html=True)

# Session
if 'sonuclar' not in st.session_state: st.session_state['sonuclar'] = None

# ==========================================
# 2. MOTOR: ÇOKLU KİLİT AÇMA SİSTEMİ
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

def isim_avcisi(text):
    """
    Bu fonksiyon ismi bulmak için 3 farklı strateji dener.
    """
    isim = ""
    lines = text.split('\n')
    
    # --- STRATEJİ 1: CSV FORMATI (Tırnaklar) ---
    # Örnek: "Soyadı (Unvanı)","18 MART..."
    m1 = re.search(r'"Soyadı \(Unvanı\)"\s*,\s*"([^"]+)"', text)
    if m1:
        isim = m1.group(1).strip()
        # Devamı var mı?
        m2 = re.search(r'"Adı \(Unvanın Devamı\)"\s*,\s*"([^"]+)"', text)
        if m2: isim += " " + m2.group(1).strip()
        return isim

    # --- STRATEJİ 2: ALT SATIR OKUMA (Klasik PDF) ---
    # Örnek: Soyadı, Adı (Unvanı) [Enter] ZARİF BİÇER
    for i, line in enumerate(lines[:50]): # İlk 50 satıra bak
        clean_line = line.strip()
        if "Soyadı, Adı (Unvanı)" in clean_line or "Soyadı (Unvanı)" in clean_line:
            if i + 1 < len(lines):
                aday = lines[i+1].strip()
                # Adayın geçerliliğini kontrol et (SMMM veya boş değilse)
                if aday and "SMMM" not in aday and "VERGİ" not in aday:
                    isim = aday
                    # Bir alt satırda devamı olabilir mi? (LTD. ŞTİ. gibi)
                    if i + 2 < len(lines):
                        aday2 = lines[i+2].strip()
                        if "ŞTİ" in aday2 or "LTD" in aday2 or "A.Ş" in aday2:
                            isim += " " + aday2
                    return isim

    # --- STRATEJİ 3: ANAHTAR KELİME SONRASI ---
    # Bazen aynı satırdadır: Soyadı (Unvanı): AHMET YILMAZ
    m3 = re.search(r'Soyadı.*?Unvanı.*?[,:]\s*(.*)', text, re.IGNORECASE)
    if m3:
        aday = m3.group(1).strip()
        if len(aday) > 3: return aday

    return "İsim Okunamadı"

# ==========================================
# 3. ARAYÜZ
# ==========================================

st.title("👁️ MÜŞAVİR KULESİ: MATRIX MODU")
st.markdown("Gelişmiş OCR Motoru: **Aktif** | Regex Motoru: **Agresif**")

pdf_up = st.file_uploader("📂 PDF DOSYASINI YÜKLE", type=["pdf"])

if pdf_up:
    if st.button("SİSTEMİ BAŞLAT", type="primary", use_container_width=True):
        
        # Terminal Setup
        terminal = st.empty()
        logs = []
        def log(msg, color="#0f0"):
            logs.append(f"<span style='color:{color}'> > {msg}</span>")
            if len(logs)>14: logs.pop(0)
            terminal.markdown(f"<div class='terminal-box'>{'<br>'.join(logs)}</div>", unsafe_allow_html=True)
            time.sleep(0.01)

        sonuclar = []
        log("Sistem başlatılıyor...", "white")
        
        with pdfplumber.open(pdf_up) as pdf:
            total = len(pdf.pages)
            log(f"Toplam {total} sayfa tespit edildi.", "cyan")
            
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text: continue
                
                # Sadece Beyanname Sayfalarını Al (Gereksiz sayfaları atla)
                if "KATMA DEĞER VERGİSİ" in text or "MATRAH" in text:
                    
                    # 1. İSMİ AVLA
                    bulunan_isim = isim_avcisi(text)
                    
                    if bulunan_isim != "İsim Okunamadı":
                        # İsim çok uzunsa kısalt (Log için)
                        kisa_isim = (bulunan_isim[:25] + '..') if len(bulunan_isim) > 25 else bulunan_isim
                        log(f"[{i+1}] İsim Çözüldü: {kisa_isim}", "#ffff00")
                    else:
                        # İsim bulunamazsa bile devam et, belki veri vardır
                        pass

                    # 2. VERİLERİ ÇEK
                    m_match = re.search(r"(?:TOPLAM MATRAH|Teslim ve Hizmetlerin Karşılığını).*?([\d\.,]+)", text, re.IGNORECASE)
                    matrah = text_to_float(m_match.group(1)) if m_match else 0.0
                    
                    k_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
                    kdv = text_to_float(k_match.group(1)) if k_match else 0.0
                    
                    pos_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
                    pos = text_to_float(pos_match.group(1)) if pos_match else 0.0
                    
                    # 3. ANALİZ
                    beyan = matrah + kdv
                    fark = pos - beyan
                    
                    if fark > 50:
                        log(f"⚠️ RİSK: {bulunan_isim} (Fark: {int(fark)})", "red")
                        sonuclar.append({
                            "Mükellef": bulunan_isim,
                            "POS": pos,
                            "Beyan": beyan,
                            "Fark": fark
                        })
        
        log("Analiz bitti. Sonuçlar listeleniyor...", "white")
        time.sleep(1)
        st.session_state['sonuclar'] = pd.DataFrame(sonuclar)
        terminal.empty()

# SONUÇLAR
if st.session_state['sonuclar'] is not None:
    df = st.session_state['sonuclar']
    
    if df.empty:
        st.success("✅ TEMİZ. Hiçbir riskli mükellef bulunamadı.")
    else:
        st.markdown(f"### 🚨 {len(df)} RİSKLİ MÜKELLEF TESPİT EDİLDİ")
        
        for i, row in df.iterrows():
            ad = row['Mükellef']
            # İsim okunamadıysa "Bilinmeyen (Sayfa X)" yazsın diye kontrol eklenebilir ama şu an ham veri
            if ad == "İsim Okunamadı": ad = "BİLİNMEYEN MÜKELLEF (İsim Okunamadı)"
            
            with st.container():
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"""
                    <div class='risk-card'>
                        <div class='white-text' style='font-size:20px; font-weight:bold'>{ad}</div>
                        <div style='display:flex; justify-content:space-between; margin-top:10px;'>
                            <div><span class='gray-text'>POS CİRO</span><br><span class='big-num'>{para_formatla(row['POS'])}</span></div>
                            <div><span class='gray-text'>BEYAN (KDV DAHİL)</span><br><span class='big-num'>{para_formatla(row['Beyan'])}</span></div>
                        </div>
                        <div style='margin-top:10px; color:#ff4444; font-weight:bold; border-top:1px solid #333; padding-top:5px'>
                            EKSİK BEYAN FARKI: {para_formatla(row['Fark'])}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with c2:
                    st.write("")
                    st.write("")
                    if st.button("İHBAR ET 📲", key=f"btn_{i}", use_container_width=True):
                        msg = (f"⚠️ *KDV RİSK RAPORU*\n\n"
                               f"Firma: {ad}\nPOS: {para_formatla(row['POS'])}\n"
                               f"Beyan: {para_formatla(row['Beyan'])}\n"
                               f"Fark: {para_formatla(row['Fark'])}\n\nKontrol Ediniz.")
                        if whatsapp_gonder(msg): st.toast("Gönderildi")
                        else: st.error("Hata")
