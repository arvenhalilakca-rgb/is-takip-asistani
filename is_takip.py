import streamlit as st
import pandas as pd
import re
import pdfplumber
import requests
import time

# ==========================================
# 1. AYARLAR & MATRIX TASARIMI (CSS)
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi PRO",
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
    /* GENEL */
    .stApp {background-color: #0e1117; color: #c9d1d9; font-family: 'Segoe UI', monospace;}
    
    /* YAN MENÜ */
    [data-testid="stSidebar"] {background-color: #161b22; border-right: 1px solid #30363d;}
    
    /* TERMINAL EFEKTİ */
    .terminal-window {
        background-color: #0d1117;
        color: #00ff41;
        font-family: 'Courier New', monospace;
        padding: 15px;
        border: 1px solid #30363d;
        border-radius: 6px;
        height: 250px;
        overflow-y: auto;
        box-shadow: 0 0 15px rgba(0, 255, 65, 0.1);
        font-size: 13px;
        margin-bottom: 20px;
    }
    
    /* KART TASARIMLARI */
    .card {
        background-color: #161b22;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 15px;
        border: 1px solid #30363d;
    }
    .risk-card {border-left: 5px solid #ff4b4b;}
    .clean-card {border-left: 5px solid #238636;}
    
    .card-title {font-size: 16px; font-weight: bold; color: #e6edf3;}
    .card-sub {font-size: 12px; color: #8b949e;}
    .stat-val {font-size: 15px; font-weight: bold; color: #e6edf3;}
    .stat-lbl {font-size: 11px; color: #8b949e; text-transform: uppercase;}
    
    .danger-text {color: #ff4b4b; font-weight: bold;}
    .success-text {color: #238636; font-weight: bold;}

    /* BUTONLAR */
    .stButton>button {
        background-color: #21262d; color: #c9d1d9; 
        border: 1px solid #30363d; width: 100%; transition: 0.2s;
    }
    .stButton>button:hover {
        border-color: #8b949e; background-color: #30363d;
    }
    </style>
    """, unsafe_allow_html=True)

# Session State
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
    # Eğer numara "SABIT" ise sabit hatta, değilse kişiye
    if numara == "SABIT":
        target = f"{SABIT_IHBAR_NO}@c.us"
    else:
        # Numara temizliği
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
    m1 = re.search(r'"(\d{10,11})"', text) # CSV formatı
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
    st.image("https://cdn-icons-png.flaticon.com/512/2920/2920349.png", width=60)
    st.markdown("### MÜŞAVİR KULESİ")
    st.info("v6.0 - Matrix Edition")
    
    secim = st.radio("MODÜLLER", [
        "1. Mükellef Listesi (Excel)",
        "2. KDV Analiz Robotu",
        "3. Profesyonel Mesaj",
        "4. Tasdik Robotu"
    ])

# --- 1. LİSTE YÜKLEME ---
if secim == "1. Mükellef Listesi (Excel)":
    st.title("📂 Mükellef Veritabanı")
    st.markdown("Excel dosyasını yükleyin. **Sütun A: Unvan, B: TC, C: Vergi No** olmalıdır.")
    
    up = st.file_uploader("Excel Dosyası", type=["xlsx", "xls"])
    if up:
        try:
            raw_df = pd.read_excel(up, dtype=str)
            if len(raw_df.columns) >= 3:
                # Sütunları indeksle alıp standartlaştırıyoruz
                df_clean = pd.DataFrame()
                df_clean['A_UNVAN'] = raw_df.iloc[:, 0].astype(str).str.strip()
                df_clean['B_TC']    = raw_df.iloc[:, 1].astype(str).str.strip()
                df_clean['C_VKN']   = raw_df.iloc[:, 2].astype(str).str.strip()
                
                # İsteğe bağlı: Telefon varsa D sütunu olarak alabiliriz
                if len(raw_df.columns) >= 4:
                    df_clean['D_TEL'] = raw_df.iloc[:, 3].astype(str).str.strip()
                else:
                    df_clean['D_TEL'] = ""

                st.session_state['mukellef_db'] = df_clean.fillna("")
                st.success(f"✅ {len(df_clean)} Kayıt Yüklendi.")
                st.dataframe(df_clean.head())
            else:
                st.error("Hata: Dosyada en az 3 sütun olmalı.")
        except Exception as e:
            st.error(f"Dosya okunamadı: {e}")

# --- 2. KDV ANALİZ ROBOTU (HAVALI MOD) ---
elif secim == "2. KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV & POS Analiz Üssü")
    
    if st.session_state['mukellef_db'] is None:
        st.warning("⚠️ Lütfen önce Excel listesini yükleyin.")
        st.stop()
        
    pdf_up = st.file_uploader("Beyanname PDF", type=["pdf"])
    
    if pdf_up:
        if st.button("🚀 ANALİZİ BAŞLAT", type="primary"):
            
            # --- TERMİNAL EKRANI ---
            terminal = st.empty()
            logs = []
            def log_yaz(txt, renk="#00ff41"):
                logs.append(f"<span style='color:{renk}'>root@analiz:~$ {txt}</span>")
                if len(logs) > 12: logs.pop(0)
                terminal.markdown(f"<div class='terminal-window'>{'<br>'.join(logs)}<br><span class='blink'>_</span></div>", unsafe_allow_html=True)
                time.sleep(0.02) # Efekt
            
            log_yaz("Sistem başlatılıyor...", "white")
            log_yaz("Excel veritabanı bağlantısı: OK", "cyan")
            
            sonuclar = []
            
            with pdfplumber.open(pdf_up) as pdf:
                total = len(pdf.pages)
                log_yaz(f"PDF Tarama Başlatıldı. Toplam Sayfa: {total}", "white")
                
                for i, page in enumerate(pdf.pages):
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
                        renk = "#ff4b4b" if durum == "RISKLI" else "#238636"
                        
                        # Terminale yaz (Her 5 sayfada bir veya riskliyse)
                        if durum == "RISKLI":
                            log_yaz(f"UYARI: {isim[:15]}.. Fark: {int(fark)}", "red")
                        elif i % 5 == 0:
                            log_yaz(f"Taraniyor... Sayfa {i+1} - {isim[:10]} [OK]", "#555")
                        
                        sonuclar.append({
                            "Mükellef": isim, "VKN": vkn, "POS": pos,
                            "Beyan": beyan, "Fark": fark, "Durum": durum
                        })
            
            log_yaz("Analiz Tamamlandı. Raporlar oluşturuluyor...", "cyan")
            time.sleep(0.5)
            st.session_state['sonuclar'] = pd.DataFrame(sonuclar)
            terminal.empty() # Terminali kapat

    # --- SONUÇ GÖSTERİMİ (TABS) ---
    if st.session_state['sonuclar'] is not None:
        df = st.session_state['sonuclar']
        riskliler = df[df['Durum'] == "RISKLI"]
        temizler = df[df['Durum'] == "TEMIZ"]
        
        # Sekmeler
        tab1, tab2 = st.tabs([f"🚨 RİSKLİLER ({len(riskliler)})", f"✅ SORUNSUZLAR ({len(temizler)})"])
        
        # TAB 1: RİSKLİLER
        with tab1:
            if riskliler.empty:
                st.success("Riskli kayıt bulunamadı.")
            else:
                for i, row in riskliler.iterrows():
                    with st.container():
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.markdown(f"""
                            <div class='card risk-card'>
                                <div class='card-title'>{row['Mükellef']}</div>
                                <div class='card-sub'>VKN: {row['VKN']}</div>
                                <div style='display:flex; gap:20px; margin-top:10px;'>
                                    <div><span class='stat-lbl'>POS</span><br><span class='stat-val'>{para_formatla(row['POS'])}</span></div>
                                    <div><span class='stat-lbl'>BEYAN</span><br><span class='stat-val'>{para_formatla(row['Beyan'])}</span></div>
                                </div>
                                <div class='danger-text' style='margin-top:10px'>EKSİK: {para_formatla(row['Fark'])}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        with c2:
                            st.write("")
                            if st.button(f"🚨 İHBAR ET", key=f"r_{i}", type="primary", use_container_width=True):
                                msg = (f"⚠️ *KDV RİSK RAPORU*\n\n"
                                       f"Firma: {row['Mükellef']}\n"
                                       f"POS: {para_formatla(row['POS'])}\n"
                                       f"Beyan: {para_formatla(row['Beyan'])}\n"
                                       f"Fark: {para_formatla(row['Fark'])}\n\n"
                                       f"Kontrol ediniz.")
                                if whatsapp_gonder("SABIT", msg): st.toast("İletildi!")
                                else: st.error("Hata")
        
        # TAB 2: SORUNSUZLAR (TEMİZLER)
        with tab2:
            if temizler.empty:
                st.info("Temiz kayıt yok.")
            else:
                st.markdown("Aşağıdaki mükelleflerin POS tutarları beyan edilen tutarın altındadır.")
                for i, row in temizler.iterrows():
                    st.markdown(f"""
                    <div class='card clean-card'>
                        <div class='card-title'>{row['Mükellef']}</div>
                        <div style='display:flex; gap:20px; margin-top:5px;'>
                            <div><span class='stat-lbl'>POS</span>: <span class='stat-val'>{para_formatla(row['POS'])}</span></div>
                            <div><span class='stat-lbl'>BEYAN</span>: <span class='stat-val'>{para_formatla(row['Beyan'])}</span></div>
                            <div class='success-text'>✓ UYUMLU</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# --- 3. PROFESYONEL MESAJ ---
elif secim == "3. Profesyonel Mesaj":
    st.title("📤 Mesaj Merkezi")
    
    if st.session_state['mukellef_db'] is None:
        st.warning("Liste yüklenmedi.")
    else:
        df = st.session_state['mukellef_db']
        col1, col2 = st.columns(2)
        
        with col1:
            alici = st.selectbox("Müşteri Seç", df['A_UNVAN'].tolist())
            tel_durum = "Kayıtlı Tel: Yok" 
            # Eğer D sütunu varsa ve doluysa
            secilen_row = df[df['A_UNVAN'] == alici].iloc[0]
            if 'D_TEL' in df.columns and len(str(secilen_row['D_TEL'])) > 5:
                tel_durum = f"Kayıtlı Tel: {secilen_row['D_TEL']}"
            
            st.caption(tel_durum)
            
            mesaj = st.text_area("Mesaj", height=150)
            
        with col2:
            st.subheader("İşlem")
            if st.button("Seçili Kişiye Gönder", type="primary"):
                # Burada D sütunundaki numarayı kullanırız
                numara = secilen_row.get('D_TEL', "")
                if len(str(numara)) < 5:
                    st.error("Bu kişinin telefon numarası listede yok.")
                else:
                    if whatsapp_gonder(numara, mesaj): st.success("Gönderildi")
                    else: st.error("Hata")
            
            st.divider()
            if st.button("Sabit Hatta Test Mesajı At"):
                whatsapp_gonder("SABIT", mesaj)
                st.toast("Sabit hatta gönderildi")

# --- 4. TASDİK ROBOTU ---
elif secim == "4. Tasdik Robotu":
    st.title("🤖 Tasdik Takip")
    if st.session_state['mukellef_db'] is None:
        st.warning("Veri yok.")
    else:
        df = st.session_state['mukellef_db']
        st.write("Veritabanı Önizleme:")
        st.dataframe(df)
        st.info("Bu modül, Excel dosyasındaki borç sütununa göre otomatik hatırlatma yapar. (Şu an sadece liste görüntüleniyor).")
