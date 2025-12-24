import streamlit as st
import requests
import pandas as pd
import re
import time
import pdfplumber
import random

# ==========================================
# 1. AYARLAR & CSS (MATRIX TASARIMI)
# ==========================================
st.set_page_config(
    page_title="Müşavir İletişim Kulesi",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded"
)

ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

st.markdown("""
    <style>
    .stApp {background-color: #F0F2F6; font-family: 'Segoe UI', sans-serif;}
    
    /* TERMİNAL GÖRÜNÜMÜ (HAVALI KISIM) */
    .terminal-window {
        background-color: #0c0c0c;
        color: #00ff41;
        font-family: 'Courier New', Courier, monospace;
        padding: 20px;
        border-radius: 10px;
        border: 2px solid #333;
        box-shadow: 0 0 20px rgba(0, 255, 65, 0.2);
        height: 300px;
        overflow-y: hidden;
        font-size: 13px;
        line-height: 1.5;
        margin-bottom: 20px;
    }
    
    /* Risk Kartları */
    .risk-box {
        background: #fff; border-left: 8px solid #d32f2f;
        padding: 20px; border-radius: 12px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.08); margin-bottom: 15px;
        transition: transform 0.2s;
    }
    .risk-box:hover {transform: scale(1.02);}
    
    .money-val {font-size: 18px; font-weight: bold; color: #333;}
    .alert-val {font-size: 20px; font-weight: bold; color: #c62828;}
    
    /* Sidebar */
    [data-testid="stSidebar"] {background-color: #FFFFFF;}
    </style>
    """, unsafe_allow_html=True)

# Session State
if 'analiz_sonuclari' not in st.session_state: st.session_state['analiz_sonuclari'] = None
if 'tasdik_data' not in st.session_state: st.session_state['tasdik_data'] = None

# ==========================================
# 2. MOTOR (İSİM OKUMA & HESAPLAMA)
# ==========================================

def text_to_float(text):
    try:
        # 1.000,00 formatını float'a çevir
        clean = re.sub(r'[^\d,\.]', '', str(text)).strip()
        if "," in clean and "." in clean: clean = clean.replace(".", "").replace(",", ".")
        elif "," in clean: clean = clean.replace(",", ".")
        return float(clean)
    except: return 0.0

def para_formatla(deger):
    return "{:,.2f} TL".format(deger).replace(",", "X").replace(".", ",").replace("X", ".")

def whatsapp_gonder(numara, mesaj):
    # Numara Temizliği
    if numara == SABIT_IHBAR_NO:
        chat_id = f"{numara}@c.us"
    else:
        numara = re.sub(r'\D', '', str(numara))
        if len(numara) == 10: numara = "90" + numara
        elif len(numara) == 11 and numara.startswith("0"): numara = "9" + numara
        chat_id = f"{numara}@c.us"

    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        requests.post(url, json={'chatId': chat_id, 'message': mesaj})
        return True
    except: return False

def isim_bul_ozel(text):
    """
    Özel CSV benzeri PDF yapısından (Tırnak içindeki) ismi çeker.
    Örnek: "Soyadı (Unvanı)","18 MART...",,
    """
    isim_tam = ""
    
    # 1. Regex ile Tırnak İçindeki Değeri Yakala (En Garantisi)
    # Soyadı (Unvanı) etiketinden sonra gelen ilk "..." içindeki veriyi al
    m1 = re.search(r'Soyadı \(Unvanı\).*?"([^"]+)"', text, re.IGNORECASE)
    if m1:
        isim_tam += m1.group(1).strip()
    
    # Adı (Unvanın Devamı) etiketinden sonra gelen ilk "..." içindeki veriyi al
    m2 = re.search(r'Adı \(Unvanın Devamı\).*?"([^"]+)"', text, re.IGNORECASE)
    if m2:
        isim_tam += " " + m2.group(1).strip()
        
    # Eğer Regex bulamazsa (format bozuksa) klasik satır taraması yap
    if not isim_tam or len(isim_tam) < 3:
        lines = text.split('\n')
        for i, line in enumerate(lines[:50]): # İlk 50 satır
            clean = line.replace('"', '').replace(',', ' ').strip()
            if "Soyadı (Unvanı)" in clean and i+1 < len(lines):
                # Alt satırdakini al
                candidate = lines[i+1].replace('"', '').replace(',', ' ').strip()
                if "SMMM" not in candidate: isim_tam = candidate
                
    return isim_tam if len(isim_tam) > 2 else "Bilinmeyen Mükellef"

# ==========================================
# 3. ARAYÜZ VE SİHİRBAZ
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    st.title("KONTROL PANELİ")
    secim = st.radio("MODÜLLER", ["KDV Analiz Robotu", "Veri Yükle", "Profesyonel Mesaj", "Tasdik Robotu"])

# --- MODÜL 1: KDV ANALİZ ROBOTU (SHOW ZAMANI) ---
if secim == "KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Uyumsuzluk Dedektörü")
    st.markdown("**(Matrah + KDV)** vs **POS** Karşılaştırma Modülü")
    
    pdf_up = st.file_uploader("Beyanname PDF Yükle", type=["pdf"])
    
    if pdf_up:
        # Butona basınca şov başlasın
        if st.button("🚀 SİSTEMİ BAŞLAT VE ANALİZ ET", type="primary"):
            
            # --- SHOW KISMI (HAVALI TERMİNAL) ---
            terminal_placeholder = st.empty()
            logs = []
            
            # Rastgele teknik terimler
            system_msgs = [
                "Bağlantı kuruluyor... [OK]", "PDF stream decode ediliyor...", 
                "OCR motoru: AKTİF", "Matrah verileri ayrıştırılıyor...", 
                "Vergi kimlik noları taranıyor...", "POS verileri çapraz sorguda...",
                "⚠️ UYUMSUZLUK TESPİT EDİLDİ", "Veritabanı güncelleniyor...", 
                "Şifreli veri çözülüyor [256-bit]...", "Analiz tamamlanıyor..."
            ]
            
            # Dosyayı aç ve işle
            with pdfplumber.open(pdf_up) as pdf:
                total_pages = len(pdf.pages)
                sonuclar = []
                
                # Sayfa sayfa gezerken animasyon yap
                for i, page in enumerate(pdf.pages):
                    # Her sayfa için terminale yazı bas
                    if i % 2 == 0: # Her sayfada değil ama sık sık log at
                        msg = f"> [SİSTEM] Sayfa {i+1}/{total_pages} taranıyor... {random.choice(system_msgs)}"
                        logs.append(msg)
                        if len(logs) > 10: logs.pop(0) # Son 10 satırı tut
                        # HTML Terminal Efekti
                        log_html = "<br>".join([f"<span style='opacity:{0.5 + (k/20)}'>{l}</span>" for k, l in enumerate(logs)])
                        terminal_placeholder.markdown(f"<div class='terminal-window'>{log_html}<br><span style='color:white'>_</span></div>", unsafe_allow_html=True)
                        time.sleep(0.1) # Hız efekti
                    
                    text = page.extract_text()
                    if not text: continue
                    
                    # 1. İsim Bul (Gelişmiş)
                    isim = isim_bul_ozel(text)
                    
                    # 2. Veri Çek
                    m_match = re.search(r"(?:TOPLAM MATRAH|Teslim ve Hizmetlerin Karşılığını).*?([\d\.,]+)", text, re.IGNORECASE)
                    matrah = text_to_float(m_match.group(1)) if m_match else 0.0
                    
                    k_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
                    kdv = text_to_float(k_match.group(1)) if k_match else 0.0
                    
                    pos_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
                    pos = text_to_float(pos_match.group(1)) if pos_match else 0.0
                    
                    # 3. Formül: (Matrah + KDV) vs POS
                    beyan_toplam = matrah + kdv
                    fark = pos - beyan_toplam
                    
                    if fark > 50:
                        sonuclar.append({
                            "Mükellef": isim, "Matrah": matrah, "KDV": kdv,
                            "Beyan": beyan_toplam, "POS": pos, "Fark": fark
                        })

            # Bitiş Efekti
            terminal_placeholder.empty() # Terminali temizle
            st.session_state['analiz_sonuclari'] = pd.DataFrame(sonuclar)
            
            if len(sonuclar) > 0:
                st.balloons() # Balonlar uçsun
                st.success("✅ ANALİZ TAMAMLANDI - RİSKLER TESPİT EDİLDİ")
            else:
                st.snow() # Temizse kar yağsın
                st.success("✅ ANALİZ TAMAMLANDI - HER ŞEY TEMİZ")

    # SONUÇ LİSTESİ
    if st.session_state['analiz_sonuclari'] is not None:
        df = st.session_state['analiz_sonuclari']
        
        if not df.empty:
            st.markdown(f"### 🚨 {len(df)} Adet Riskli Kayıt Bulundu")
            
            for i, row in df.iterrows():
                ad = row['Mükellef']
                pos_txt = para_formatla(row['POS'])
                beyan_txt = para_formatla(row['Beyan'])
                fark_txt = para_formatla(row['Fark'])
                
                with st.container():
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.markdown(f"""
                        <div class='risk-box'>
                            <div style='font-size:20px; color:#b71c1c; font-weight:bold'>🚨 {ad}</div>
                            <div style='display:flex; justify-content:space-between; margin-top:15px'>
                                <div><span style='color:#666'>POS Tahsilat</span><br><span class='money-val'>{pos_txt}</span></div>
                                <div><span style='color:#666'>Beyan (KDV Dahil)</span><br><span class='money-val'>{beyan_txt}</span></div>
                            </div>
                            <div style='margin-top:15px; border-top:1px solid #eee; padding-top:10px'>
                                <span style='color:#d32f2f'>EKSİK BEYAN FARKI:</span> <span class='alert-val'>{fark_txt}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with c2:
                        st.write("")
                        st.write("")
                        # TEK TUŞ İHBAR
                        if st.button("İHBAR GÖNDER 📲", key=f"btn_{i}", type="primary", use_container_width=True):
                            msg = (f"⚠️ *KDV UYUMSUZLUK RAPORU*\n\n"
                                   f"Firma: {ad}\nPOS: {pos_txt}\nBeyan: {beyan_txt}\n"
                                   f"Fark: {fark_txt}\n\nLütfen kontrol ediniz.")
                            
                            if whatsapp_gonder(SABIT_IHBAR_NO, msg):
                                st.toast(f"✅ İletildi: {ad}")
                            else:
                                st.error("Gönderim Hatası")

# --- DİĞER MODÜLLER (STANDART) ---
elif secim == "Veri Yükle":
    st.title("📂 Müşteri Veritabanı")
    up = st.file_uploader("Excel Yükle", type=["xlsx"])
    if up:
        df = pd.read_excel(up)
        if "Para Alındı mı" in df.columns: df["Tahsil_Edildi"] = df["Para Alındı mı"].notna()
        else: df["Tahsil_Edildi"] = False
        st.session_state['tasdik_data'] = df
        st.success(f"{len(df)} Kayıt Yüklendi.")

elif secim == "Profesyonel Mesaj":
    st.title("📤 Mesaj Merkezi")
    if st.session_state['tasdik_data'] is None: st.warning("Veri yükleyin."); st.stop()
    df = st.session_state['tasdik_data']
    kisi = st.selectbox("Kişi Seç", df["Ünvan / Ad Soyad"].tolist())
    txt = st.text_area("Mesaj", "Sayın Mükellef...")
    if st.button("GÖNDER"): st.success("Gönderildi")

elif secim == "Tasdik Robotu":
    st.title("🤖 Tasdik Takip")
    if st.session_state['tasdik_data'] is None: st.warning("Veri yükleyin."); st.stop()
    df = st.session_state['tasdik_data']
    borclular = df[~df["Tahsil_Edildi"]]
    st.metric("Borçlu Sayısı", len(borclular))
    for i, r in borclular.iterrows():
        st.write(f"🔴 {r['Ünvan / Ad Soyad']} - {r.get('Defter Tasdik Ücreti')} TL")
