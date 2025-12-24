import streamlit as st
import requests
import pandas as pd
import re
import time
import pdfplumber

# ==========================================
# 1. AYARLAR & GÖRSEL TASARIM (MATRIX MODU)
# ==========================================
st.set_page_config(
    page_title="Müşavir İletişim Kulesi",
    page_icon="🗼",
    layout="wide"
)

# API Bilgileri (Buraya kendi bilgilerinizi girin)
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

st.markdown("""
    <style>
    /* Ana Arka Plan */
    .stApp {background-color: #0e1117; color: #e0e0e0; font-family: 'Segoe UI', sans-serif;}
    
    /* HAVALI TERMİNAL EKRANI */
    .terminal-window {
        background-color: #000000;
        color: #00ff41; /* Hacker Yeşili */
        font-family: 'Courier New', Courier, monospace;
        padding: 15px;
        border: 1px solid #333;
        border-radius: 5px;
        height: 350px;
        overflow-y: auto;
        box-shadow: 0 0 20px rgba(0, 255, 65, 0.15);
        font-size: 13px;
        line-height: 1.5;
        margin-bottom: 20px;
    }
    
    /* SONUÇ KARTLARI */
    .risk-card {
        background-color: #1a1a1a;
        border-left: 5px solid #ff4b4b;
        padding: 20px;
        margin-bottom: 15px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.5);
    }
    .card-head {font-size: 18px; font-weight: bold; color: #fff;}
    .card-sub {font-size: 13px; color: #888; margin-top: 5px;}
    .card-val {font-size: 16px; font-weight: bold; color: #eee;}
    .card-alert {color: #ff4b4b; font-weight: bold; font-size: 16px; margin-top: 10px; border-top: 1px solid #333; padding-top: 10px;}
    
    /* BUTONLAR */
    .stButton>button {
        background-color: #262730; color: white; border: 1px solid #444; width: 100%;
    }
    .stButton>button:hover {border-color: #00ff41; color: #00ff41;}
    </style>
    """, unsafe_allow_html=True)

# Session State
if 'sonuclar' not in st.session_state: st.session_state['sonuclar'] = None

# ==========================================
# 2. MOTOR (İSİM VE VERİ AVCISI)
# ==========================================

def text_to_float(text):
    """Metni paraya çevirir."""
    try:
        clean = re.sub(r'[^\d,\.]', '', str(text)).strip()
        if "," in clean and "." in clean: clean = clean.replace(".", "").replace(",", ".")
        elif "," in clean: clean = clean.replace(",", ".")
        return float(clean)
    except: return 0.0

def para_formatla(deger):
    """TL formatı yapar."""
    return "{:,.2f} TL".format(deger).replace(",", "X").replace(".", ",").replace("X", ".")

def whatsapp_gonder(mesaj):
    chat_id = f"{SABIT_IHBAR_NO}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        requests.post(url, json={'chatId': chat_id, 'message': mesaj})
        return True
    except: return False

def mukellef_ismini_sok_al(text):
    """
    Bu fonksiyon PDF içindeki gizli formatı (CSV yapısını) söker alır.
    Örnek yapı: "Soyadı (Unvanı)","18 MART...",,
    """
    isim_tam = ""
    
    # ADIM 1: "Soyadı (Unvanı)" etiketinin yanındaki tırnaklı veriyi al
    # Regex Mantığı: "Soyadı (Unvanı)" bul -> virgülden sonraki "..." içini kap
    match_soyad = re.search(r'"Soyadı \(Unvanı\)"\s*,\s*"([^"]+)"', text)
    if match_soyad:
        isim_tam += match_soyad.group(1).strip()
    
    # ADIM 2: "Adı (Unvanın Devamı)" etiketinin yanındaki tırnaklı veriyi al
    match_ad = re.search(r'"Adı \(Unvanın Devamı\)"\s*,\s*"([^"]+)"', text)
    if match_ad:
        isim_tam += " " + match_ad.group(1).strip()
    
    # ADIM 3: Eğer yukarıdakiler çalışmazsa (Tırnaksız format), klasik yöntem
    if len(isim_tam) < 3:
        lines = text.split('\n')
        for i, line in enumerate(lines[:50]):
            clean_line = line.replace('"', '').replace(',', ' ').strip()
            if "Soyadı (Unvanı)" in clean_line and i+1 < len(lines):
                candidate = lines[i+1].replace('"', '').replace(',', ' ').strip()
                # Gereksiz kelimeleri ele
                if "SMMM" not in candidate and "VERGİ" not in candidate:
                    isim_tam = candidate
                    break
    
    return isim_tam if len(isim_tam) > 2 else "Bilinmeyen Mükellef"

# ==========================================
# 3. ANA UYGULAMA
# ==========================================

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/9203/9203764.png", width=80)
    st.header("KONTROL PANELİ")
    st.info("KDV Analiz Modülü v5.0\n(Quote/CSV Parser Aktif)")

st.title("🕵️‍♂️ KDV & POS Uyumsuzluk Dedektörü")
st.markdown("Yüklenen PDF'teki **'KATMA DEĞER VERGİSİ BEYANNAMESİ'** sayfalarını tespit eder, tırnak içine gizlenmiş isimleri okur ve analizi yapar.")

pdf_up = st.file_uploader("📂 Beyanname PDF Dosyasını Buraya Sürükleyin", type=["pdf"])

if pdf_up:
    if st.button("🚀 SİSTEMİ BAŞLAT", type="primary"):
        
        # --- TERMİNAL EKRANI HAZIRLIĞI ---
        terminal = st.empty()
        logs = []
        
        def log_bas(txt, renk="#00ff41"):
            t = time.strftime("%H:%M:%S")
            logs.append(f"<span style='color:#555'>[{t}]</span> <span style='color:{renk}'>{txt}</span>")
            # Son 15 satırı göster
            if len(logs) > 15: logs.pop(0)
            terminal.markdown(f"<div class='terminal-window'>{'<br>'.join(logs)}<br><span class='blink'>_</span></div>", unsafe_allow_html=True)
            time.sleep(0.02) # Efekt hızı

        sonuclar = []
        log_bas("Sistem başlatılıyor...", "white")
        log_bas("OCR motoru ve Regex kütüphanesi yüklendi...", "white")
        
        with pdfplumber.open(pdf_up) as pdf:
            total_pages = len(pdf.pages)
            log_bas(f"PDF Tarama Başladı: Toplam {total_pages} sayfa.", "cyan")
            
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text: continue
                
                # SADECE "KATMA DEĞER VERGİSİ BEYANNAMESİ" YAZAN SAYFALARI AL
                if "KATMA DEĞER VERGİSİ BEYANNAMESİ" in text:
                    
                    # 1. İSMİ BUL (Yeni Fonksiyon ile)
                    isim = mukellef_ismini_sok_al(text)
                    
                    # Terminalde ismi göster (Kullanıcı görsün diye)
                    if isim != "Bilinmeyen Mükellef":
                        log_bas(f"✓ MÜKELLEF BULUNDU: {isim}", "#ffff00")
                    else:
                        log_bas(f"! İsim okunamadı (Sayfa {i+1})", "red")

                    # 2. VERİLERİ ÇEK
                    # Matrah
                    m_match = re.search(r"(?:TOPLAM MATRAH|Teslim ve Hizmetlerin Karşılığını).*?([\d\.,]+)", text, re.IGNORECASE)
                    matrah = text_to_float(m_match.group(1)) if m_match else 0.0
                    
                    # KDV
                    k_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
                    kdv = text_to_float(k_match.group(1)) if k_match else 0.0
                    
                    # POS (Kredi Kartı)
                    pos_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
                    pos = text_to_float(pos_match.group(1)) if pos_match else 0.0
                    
                    # 3. HESAPLAMA (Senin İstediğin Mantık)
                    # (Matrah + KDV) vs POS
                    beyan_toplam = matrah + kdv
                    fark = pos - beyan_toplam
                    
                    # 50 TL üzeri fark varsa kaydet
                    if fark > 50:
                        log_bas(f"⚠️ RİSK TESPİTİ! Fark: {int(fark)} TL", "red")
                        sonuclar.append({
                            "Mükellef": isim,
                            "POS": pos,
                            "Beyan": beyan_toplam,
                            "Fark": fark
                        })
                    else:
                        # Temizse sadece bilgi geç
                        # log_bas(f"Durum Temiz.", "#555") 
                        pass
        
        log_bas("Analiz tamamlandı. Rapor hazırlanıyor...", "cyan")
        time.sleep(1)
        st.session_state['sonuclar'] = pd.DataFrame(sonuclar)
        terminal.empty() # Terminali temizle

# SONUÇLARI GÖSTER
if st.session_state['sonuclar'] is not None:
    df = st.session_state['sonuclar']
    
    if df.empty:
        st.success("✅ Mükemmel! Taranan beyannamelerde herhangi bir POS uyumsuzluğu bulunamadı.")
        st.balloons()
    else:
        st.error(f"🚨 Toplam {len(df)} Adet Riskli Beyanname Tespit Edildi")
        
        for i, row in df.iterrows():
            ad = row['Mükellef']
            pos_txt = para_formatla(row['POS'])
            beyan_txt = para_formatla(row['Beyan'])
            fark_txt = para_formatla(row['Fark'])
            
            with st.container():
                col1, col2 = st.columns([0.75, 0.25])
                
                with col1:
                    st.markdown(f"""
                    <div class='risk-card'>
                        <div class='card-head'>🚨 {ad}</div>
                        <div class='card-sub'>KDV Beyannamesi Analizi</div>
                        <div style='display:flex; justify-content:space-between; margin-top:15px; background:#222; padding:10px; border-radius:5px;'>
                            <div><span style='color:#aaa; font-size:12px'>KREDİ KARTI (POS)</span><br><span class='card-val'>{pos_txt}</span></div>
                            <div><span style='color:#aaa; font-size:12px'>BEYAN (KDV DAHİL)</span><br><span class='card-val'>{beyan_txt}</span></div>
                        </div>
                        <div class='card-alert'>⚠️ EKSİK BEYAN FARKI: {fark_txt}</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    st.write("")
                    st.write("")
                    st.write("")
                    if st.button(f"İHBAR ET 📲", key=f"btn_{i}", type="primary", use_container_width=True):
                        # MESAJ İÇERİĞİ
                        msg = (f"⚠️ *KDV RİSK RAPORU*\n\n"
                               f"📄 *Firma:* {ad}\n"
                               f"💳 *POS Tahsilat:* {pos_txt}\n"
                               f"📊 *Beyan (Matrah+KDV):* {beyan_txt}\n"
                               f"‼️ *TESPİT EDİLEN FARK:* {fark_txt}\n\n"
                               f"Lütfen muhasebe kayıtlarını kontrol ediniz.")
                        
                        if whatsapp_gonder(msg):
                            st.toast("✅ Başarıyla İletildi!", icon="📩")
                        else:
                            st.error("Gönderim Başarısız!")
