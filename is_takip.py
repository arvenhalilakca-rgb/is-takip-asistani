import streamlit as st
import pandas as pd
import re
import pdfplumber
import requests
import time

# ==========================================
# 1. AYARLAR & AYDINLIK OFİS TEMASI (CSS)
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi PRO",
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
    /* GENEL SAYFA (AYDINLIK) */
    .stApp {background-color: #f8f9fa; font-family: 'Segoe UI', sans-serif; color: #333;}
    
    /* YAN MENÜ */
    [data-testid="stSidebar"] {background-color: #ffffff; border-right: 1px solid #e0e0e0;}
    
    /* LOG PENCERESİ (TERMİNAL) */
    .terminal-window {
        background-color: #ffffff;
        color: #333;
        font-family: 'Courier New', monospace;
        padding: 15px;
        border: 1px solid #ddd;
        border-radius: 8px;
        height: 250px;
        overflow-y: auto;
        box-shadow: inset 0 0 10px rgba(0,0,0,0.05);
        font-size: 13px;
        margin-bottom: 20px;
    }
    
    /* KART TASARIMLARI (BEYAZ KARTLAR) */
    .card {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 15px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        border: 1px solid #eee;
    }
    .risk-card {border-left: 6px solid #dc3545;} /* Kırmızı Çizgi */
    .clean-card {border-left: 6px solid #28a745;} /* Yeşil Çizgi */
    
    .card-title {font-size: 18px; font-weight: bold; color: #212529;}
    .card-sub {font-size: 13px; color: #6c757d;}
    
    /* İSTATİSTİK KUTUCUKLARI */
    .stat-box {
        background-color: #f8f9fa;
        padding: 10px;
        border-radius: 6px;
        text-align: center;
        border: 1px solid #eee;
    }
    .stat-val {font-size: 16px; font-weight: bold; color: #333;}
    .stat-lbl {font-size: 11px; color: #666; text-transform: uppercase;}
    
    .danger-text {color: #dc3545; font-weight: bold;}
    .success-text {color: #28a745; font-weight: bold;}

    /* BUTONLAR */
    .stButton>button {
        border-radius: 6px; font-weight: 500;
    }
    </style>
    """, unsafe_allow_html=True)

# Session State (Hafıza)
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

def whatsapp_gonder(numara, mesaj):
    if numara == "SABIT":
        target = f"{SABIT_IHBAR_NO}@c.us"
    else:
        n = re.sub(r'\D', '', str(numara))
        if len(n) == 10: n = "90" + n
        elif len(n) == 11 and n.startswith("0"): n = "9" + n
        target = f"{n}@c.us"

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
    """Excel (A=Unvan, B=TC, C=Vergi) mantığına göre arar."""
    if st.session_state['mukellef_db'] is None: return f"Bilinmeyen ({numara})"
    
    df = st.session_state['mukellef_db']
    numara = str(numara).strip()
    
    # C Sütunu (Vergi No) Ara
    res_c = df[df['C_VKN'] == numara]
    if not res_c.empty: return res_c.iloc[0]['A_UNVAN']
    
    # B Sütunu (TC) Ara
    res_b = df[df['B_TC'] == numara]
    if not res_b.empty: return res_b.iloc[0]['A_UNVAN']
    
    return f"Listede Yok ({numara})"

# ==========================================
# 3. YAN MENÜ VE SAYFALAR
# ==========================================

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.title("MÜŞAVİR KULESİ")
    st.caption("Profesyonel Sürüm")
    
    secim = st.radio("MODÜLLER", [
        "1. Mükellef Listesi (Excel)",
        "2. KDV Analiz Robotu",
        "3. Profesyonel Mesaj",
        "4. Tasdik Robotu"
    ])

# --- 1. LİSTE YÜKLEME ---
if secim == "1. Mükellef Listesi (Excel)":
    st.header("📂 Mükellef Veritabanı")
    st.info("Excel dosyanızda sütun sırası şöyle olmalıdır: **A=Unvan, B=TC, C=Vergi No**")
    
    if st.session_state['mukellef_db'] is not None:
        st.success(f"✅ Şu an hafızada {len(st.session_state['mukellef_db'])} mükellef kayıtlı.")
        if st.button("Listeyi Temizle / Yeni Yükle"):
            st.session_state['mukellef_db'] = None
            st.rerun()
    else:
        up = st.file_uploader("Excel Dosyası Seç", type=["xlsx", "xls"])
        if up:
            try:
                raw_df = pd.read_excel(up, dtype=str)
                if len(raw_df.columns) >= 3:
                    df_clean = pd.DataFrame()
                    df_clean['A_UNVAN'] = raw_df.iloc[:, 0].astype(str).str.strip()
                    df_clean['B_TC']    = raw_df.iloc[:, 1].astype(str).str.strip()
                    df_clean['C_VKN']   = raw_df.iloc[:, 2].astype(str).str.strip()
                    
                    if len(raw_df.columns) >= 4:
                        df_clean['D_TEL'] = raw_df.iloc[:, 3].astype(str).str.strip()
                    else:
                        df_clean['D_TEL'] = ""

                    st.session_state['mukellef_db'] = df_clean.fillna("")
                    st.success(f"✅ {len(df_clean)} Kayıt Başarıyla Yüklendi.")
                    st.dataframe(df_clean.head())
                else:
                    st.error("Hata: Dosyada en az 3 sütun olmalı.")
            except Exception as e:
                st.error(f"Dosya okunamadı: {e}")

# --- 2. KDV ANALİZ ROBOTU ---
elif secim == "2. KDV Analiz Robotu":
    st.header("🕵️‍♂️ KDV & POS Analiz Merkezi")
    
    if st.session_state['mukellef_db'] is None:
        st.warning("⚠️ Lütfen önce 1. menüden Excel listesini yükleyin.")
        st.stop()
        
    pdf_up = st.file_uploader("Beyanname PDF", type=["pdf"])
    
    if pdf_up:
        if st.button("🚀 ANALİZİ BAŞLAT", type="primary"):
            
            # --- LOG EKRANI ---
            terminal = st.empty()
            logs = []
            def log_yaz(txt, renk="#333"):
                logs.append(f"<span style='color:{renk}'>» {txt}</span>")
                if len(logs) > 15: logs.pop(0)
                terminal.markdown(f"<div class='terminal-window'>{'<br>'.join(logs)}</div>", unsafe_allow_html=True)
                time.sleep(0.02)
            
            log_yaz("Sistem başlatılıyor...", "#007bff")
            
            sonuclar = []
            
            with pdfplumber.open(pdf_up) as pdf:
                total = len(pdf.pages)
                log_yaz(f"PDF Tarama Başlatıldı. Toplam: {total} Sayfa", "#333")
                
                bar = st.progress(0)
                
                for i, page in enumerate(pdf.pages):
                    bar.progress((i+1)/total)
                    text = page.extract_text()
                    if not text: continue
                    
                    if "KATMA DEĞER VERGİSİ" in text or "MATRAH" in text:
                        # Veri Çekme
                        vkn = vkn_bul(text)
                        isim = isim_eslestir_excel(vkn)
                        
                        m_match = re.search(r"(?:TOPLAM MATRAH|Teslim ve Hizmetlerin Karşılığını).*?([\d\.,]+)", text, re.IGNORECASE)
                        matrah = text_to_float(m_match.group(1)) if m_match else 0.0
                        
                        k_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
                        kdv = text_to_float(k_match.group(1)) if k_match else 0.0
                        
                        pos_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
                        pos = text_to_float(pos_match.group(1)) if pos_match else 0.0
                        
                        beyan = matrah + kdv
                        fark = pos - beyan
                        
                        durum = "RISKLI" if fark > 50 else "TEMIZ"
                        
                        if durum == "RISKLI":
                            log_yaz(f"RİSK: {isim[:20]}.. (Fark: {int(fark)})", "#dc3545")
                        elif i % 10 == 0:
                            log_yaz(f"Taranıyor... {isim[:15]} [OK]", "#28a745")
                        
                        sonuclar.append({
                            "Mükellef": isim, "VKN": vkn, "POS": pos,
                            "Beyan": beyan, "Fark": fark, "Durum": durum
                        })
            
            log_yaz("Analiz Tamamlandı. Sonuçlar listeleniyor...", "#007bff")
            time.sleep(0.5)
            st.session_state['sonuclar'] = pd.DataFrame(sonuclar)
            terminal.empty() # Logu temizle

    # --- SONUÇLAR ---
    if st.session_state['sonuclar'] is not None:
        df = st.session_state['sonuclar']
        riskliler = df[df['Durum'] == "RISKLI"]
        temizler = df[df['Durum'] == "TEMIZ"]
        
        # Sekmeler
        tab1, tab2 = st.tabs([f"🚨 RİSKLİLER ({len(riskliler)})", f"✅ SORUNSUZLAR ({len(temizler)})"])
        
        # TAB 1: RİSKLİLER
        with tab1:
            if riskliler.empty:
                st.success("Harika! Riskli kayıt bulunamadı.")
            else:
                for i, row in riskliler.iterrows():
                    with st.container():
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.markdown(f"""
                            <div class='card risk-card'>
                                <div class='card-title'>{row['Mükellef']}</div>
                                <div class='card-sub'>VKN: {row['VKN']}</div>
                                <div style='display:flex; gap:15px; margin-top:15px;'>
                                    <div class='stat-box'>
                                        <div class='stat-lbl'>POS TAHSİLAT</div>
                                        <div class='stat-val'>{para_formatla(row['POS'])}</div>
                                    </div>
                                    <div class='stat-box'>
                                        <div class='stat-lbl'>BEYAN (KDV DAHİL)</div>
                                        <div class='stat-val'>{para_formatla(row['Beyan'])}</div>
                                    </div>
                                </div>
                                <div class='danger-text' style='margin-top:10px'>EKSİK BEYAN: {para_formatla(row['Fark'])}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        with c2:
                            st.write("")
                            st.write("")
                            if st.button(f"🚨 İHBAR ET", key=f"r_{i}", type="secondary", use_container_width=True):
                                msg = (f"⚠️ *KDV RİSK RAPORU*\n\n"
                                       f"Firma: {row['Mükellef']}\n"
                                       f"POS: {para_formatla(row['POS'])}\n"
                                       f"Beyan: {para_formatla(row['Beyan'])}\n"
                                       f"Fark: {para_formatla(row['Fark'])}\n\n"
                                       f"Kontrol ediniz.")
                                if whatsapp_gonder("SABIT", msg): st.toast("Mesaj İletildi!")
                                else: st.error("Hata")
        
        # TAB 2: TEMİZLER
        with tab2:
            if temizler.empty:
                st.info("Kayıt yok.")
            else:
                st.markdown("Uyumluluk sorunu olmayan mükellefler:")
                for i, row in temizler.iterrows():
                    st.markdown(f"""
                    <div class='card clean-card'>
                        <div class='card-title' style='font-size:16px;'>{row['Mükellef']}</div>
                        <div style='display:flex; gap:20px; font-size:14px; margin-top:5px;'>
                            <div>POS: <b>{para_formatla(row['POS'])}</b></div>
                            <div>Beyan: <b>{para_formatla(row['Beyan'])}</b></div>
                            <div class='success-text'>✓ UYUMLU</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# --- 3. PROFESYONEL MESAJ ---
elif secim == "3. Profesyonel Mesaj":
    st.header("📤 Mesaj Merkezi")
    
    if st.session_state['mukellef_db'] is None:
        st.warning("Liste yüklenmedi.")
    else:
        df = st.session_state['mukellef_db']
        col1, col2 = st.columns(2)
        
        with col1:
            alici = st.selectbox("Müşteri Seç", df['A_UNVAN'].tolist())
            
            # Telefon bilgisi kontrolü
            secilen_row = df[df['A_UNVAN'] == alici].iloc[0]
            tel_no = secilen_row.get('D_TEL', "")
            if len(str(tel_no)) > 5:
                st.success(f"Kayıtlı Numara: {tel_no}")
            else:
                st.warning("Bu kişinin numarası Excel'de (D Sütunu) yok.")
            
            mesaj = st.text_area("Mesaj İçeriği", height=120)
            
        with col2:
            st.subheader("Gönderim")
            if st.button("Seçili Kişiye Gönder", type="primary"):
                if len(str(tel_no)) < 5:
                    st.error("Numara kayıtlı değil.")
                else:
                    if whatsapp_gonder(tel_no, mesaj): st.success("Gönderildi")
                    else: st.error("API Hatası")
            
            st.divider()
            if st.button("Sabit İhbar Hattına Test At"):
                whatsapp_gonder("SABIT", mesaj)
                st.toast("Sabit hatta gönderildi")

# --- 4. TASDİK ROBOTU ---
elif secim == "4. Tasdik Robotu":
    st.header("🤖 Tasdik Takip")
    if st.session_state['mukellef_db'] is None:
        st.warning("Veri yok.")
    else:
        df = st.session_state['mukellef_db']
        st.info("Yüklü Mükellef Listesi:")
        st.dataframe(df)
