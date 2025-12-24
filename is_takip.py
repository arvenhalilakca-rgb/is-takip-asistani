import streamlit as st
import requests
import pandas as pd
import re
import time
import pdfplumber

# ==========================================
# 1. AYARLAR VE SADE TASARIM
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Ayarları (Lütfen kendi bilgilerinizi girin)
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

# CSS: Sade ve Profesyonel Görünüm
st.markdown("""
    <style>
    .stApp {background-color: #f5f7f9; font-family: 'Segoe UI', sans-serif;}
    
    /* Yan Menü */
    [data-testid="stSidebar"] {background-color: #ffffff; border-right: 1px solid #ddd;}
    
    /* Kartlar */
    .info-box {
        background-color: white; padding: 20px; border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 15px;
        border-left: 5px solid #007bff;
    }
    .risk-box {
        background-color: #fff5f5; padding: 20px; border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 15px;
        border-left: 5px solid #dc3545;
    }
    
    /* Metinler */
    .big-font {font-size: 18px; font-weight: bold; color: #333;}
    .risk-text {color: #dc3545; font-weight: bold;}
    .success-text {color: #28a745; font-weight: bold;}
    
    </style>
    """, unsafe_allow_html=True)

# Session State (Verileri hafızada tutmak için)
if 'sonuclar' not in st.session_state: st.session_state['sonuclar'] = None
if 'musteri_data' not in st.session_state: st.session_state['musteri_data'] = None

# ==========================================
# 2. FONKSİYONLAR (OKUMA VE HESAPLAMA)
# ==========================================

def text_to_float(text):
    """Metni sayıya çevirir."""
    try:
        clean = re.sub(r'[^\d,\.]', '', str(text)).strip()
        if "," in clean and "." in clean: clean = clean.replace(".", "").replace(",", ".")
        elif "," in clean: clean = clean.replace(",", ".")
        return float(clean)
    except: return 0.0

def para_formatla(deger):
    """TL formatı."""
    return "{:,.2f} TL".format(deger).replace(",", "X").replace(".", ",").replace("X", ".")

def whatsapp_gonder(mesaj):
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        payload = {'chatId': f"{SABIT_IHBAR_NO}@c.us", 'message': mesaj}
        requests.post(url, json=payload)
        return True
    except: return False

def mukellef_bul_hibrit(text):
    """
    Hem tırnaklı (CSV) hem de düz (Alt alta) formatı okuyan AKILLI FONKSİYON.
    """
    isim = ""
    lines = text.split('\n')
    
    # YÖNTEM 1: Tırnaklı Format (Örn: "Soyadı (Unvanı)","ABC LTD")
    # Sayfa 1'deki gibi karışık kodlu sayfalar için
    if '"Soyadı (Unvanı)"' in text:
        m1 = re.search(r'"Soyadı \(Unvanı\)"\s*,\s*"([^"]+)"', text)
        if m1:
            isim = m1.group(1).strip()
            # Devamı var mı?
            m2 = re.search(r'"Adı \(Unvanın Devamı\)"\s*,\s*"([^"]+)"', text)
            if m2: isim += " " + m2.group(1).strip()
            return isim

    # YÖNTEM 2: Düz Format (Örn: Soyadı (Unvanı) [Alt Satır] ZARİF BİÇER)
    # Sayfa 532'deki gibi düzgün sayfalar için
    for i, line in enumerate(lines[:60]): # İlk 60 satıra bak
        clean = line.strip()
        # Anahtar kelimeyi bul
        if "Soyadı, Adı (Unvanı)" in clean or "Soyadı (Unvanı)" in clean:
            # Hemen altındaki satırı al
            if i + 1 < len(lines):
                aday = lines[i+1].strip()
                # Eğer alt satır boşsa veya gereksiz bilgi içeriyorsa atla
                if aday and "Vergi Kimlik" not in aday and "SMMM" not in aday:
                    isim = aday
                    # Bir alt satırda devamı var mı? (ŞTİ. vb)
                    if i + 2 < len(lines):
                        aday2 = lines[i+2].strip()
                        if any(x in aday2 for x in ["LTD", "A.Ş", "ŞTİ", "TİC"]):
                            isim += " " + aday2
                    return isim

    return "Bilinmeyen Mükellef"

# ==========================================
# 3. YAN MENÜ VE SAYFALAR
# ==========================================

with st.sidebar:
    st.title("Müşavir Paneli")
    secim = st.radio("MENÜ", ["KDV Analiz Robotu", "Veri Yükle", "Profesyonel Mesaj", "Tasdik Robotu"])
    st.markdown("---")
    st.info("Sistem Durumu: Aktif ✅")

# --- SAYFA 1: KDV ANALİZ ROBOTU ---
if secim == "KDV Analiz Robotu":
    st.header("🕵️‍♂️ KDV Uyumsuzluk Analizi")
    st.write("Beyannamelerdeki (Matrah + KDV) toplamını, POS cihazı tahsilatlarıyla karşılaştırır.")
    
    pdf_up = st.file_uploader("Beyanname PDF Dosyasını Yükle", type=["pdf"])
    
    if pdf_up:
        if st.button("Analizi Başlat", type="primary"):
            st.info("Dosya taranıyor, lütfen bekleyiniz...")
            
            sonuclar = []
            with pdfplumber.open(pdf_up) as pdf:
                # İlerleme Çubuğu
                bar = st.progress(0)
                total = len(pdf.pages)
                
                for i, page in enumerate(pdf.pages):
                    bar.progress((i+1)/total)
                    text = page.extract_text()
                    if not text: continue
                    
                    # Sadece Beyanname Sayfalarını İşle
                    if "KATMA DEĞER VERGİSİ" in text or "MATRAH" in text:
                        
                        # 1. İsmi Bul (Hibrit)
                        isim = mukellef_bul_hibrit(text)
                        
                        # 2. Verileri Çek
                        # Matrah
                        m_match = re.search(r"(?:TOPLAM MATRAH|Teslim ve Hizmetlerin Karşılığını).*?([\d\.,]+)", text, re.IGNORECASE)
                        matrah = text_to_float(m_match.group(1)) if m_match else 0.0
                        
                        # KDV
                        k_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
                        kdv = text_to_float(k_match.group(1)) if k_match else 0.0
                        
                        # POS
                        pos_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
                        pos = text_to_float(pos_match.group(1)) if pos_match else 0.0
                        
                        # 3. Hesapla
                        beyan = matrah + kdv
                        fark = pos - beyan
                        
                        # Fark varsa listeye ekle
                        if fark > 50:
                            sonuclar.append({
                                "Mükellef": isim,
                                "POS": pos,
                                "Beyan": beyan,
                                "Fark": fark
                            })
            
            st.session_state['sonuclar'] = pd.DataFrame(sonuclar)
            st.rerun() # Sayfayı yenile

    # SONUÇ TABLOSU
    if st.session_state['sonuclar'] is not None:
        df = st.session_state['sonuclar']
        
        if df.empty:
            st.success("✅ Harika! Taranan dosyalarda herhangi bir risk bulunamadı.")
        else:
            st.error(f"🚨 {len(df)} Adet Riskli Beyanname Tespit Edildi")
            
            # Tablo Görünümü
            st.dataframe(df.style.format({"POS": "{:,.2f}", "Beyan": "{:,.2f}", "Fark": "{:,.2f}"}), use_container_width=True)
            
            st.markdown("### 📋 Detaylı Risk Listesi")
            for i, row in df.iterrows():
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"""
                        <div class='risk-box'>
                            <div class='big-font'>{row['Mükellef']}</div>
                            <div style='display:flex; gap:20px; margin-top:10px; color:#555;'>
                                <div>POS Tahsilat: <b>{para_formatla(row['POS'])}</b></div>
                                <div>Beyan (KDV Dahil): <b>{para_formatla(row['Beyan'])}</b></div>
                            </div>
                            <div class='risk-text' style='margin-top:10px;'>⚠️ EKSİK BEYAN FARKI: {para_formatla(row['Fark'])}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col2:
                        st.write("")
                        st.write("")
                        if st.button(f"📲 İHBAR ET", key=f"btn_{i}", type="secondary", use_container_width=True):
                            msg = (f"⚠️ *KDV RİSK RAPORU*\n\n"
                                   f"Firma: {row['Mükellef']}\n"
                                   f"POS: {para_formatla(row['POS'])}\n"
                                   f"Beyan: {para_formatla(row['Beyan'])}\n"
                                   f"Fark: {para_formatla(row['Fark'])}\n\n"
                                   f"Lütfen kontrol ediniz.")
                            
                            if whatsapp_gonder(msg):
                                st.toast("Mesaj İletildi ✅")
                            else:
                                st.error("Gönderim Hatası")

# --- SAYFA 2: VERİ YÜKLEME ---
elif secim == "Veri Yükle":
    st.header("📂 Müşteri Veritabanı")
    st.info("Müşteri listesini Excel olarak buradan yükleyiniz. (Diğer modüller için gereklidir)")
    
    up = st.file_uploader("Excel Dosyası", type=["xlsx", "xls"])
    if up:
        try:
            df = pd.read_excel(up)
            # Veri Temizliği: Tahsilat kolonunu True/False yap
            if "Para Alındı mı" in df.columns:
                df["Tahsil_Edildi"] = df["Para Alındı mı"].apply(lambda x: True if pd.notna(x) and str(x).strip() != "" else False)
            else:
                df["Tahsil_Edildi"] = False
                
            st.session_state['musteri_data'] = df
            st.success(f"✅ {len(df)} Müşteri kaydı başarıyla yüklendi.")
            st.dataframe(df.head())
        except Exception as e:
            st.error(f"Hata: {e}")

# --- SAYFA 3: PROFESYONEL MESAJ ---
elif secim == "Profesyonel Mesaj":
    st.header("📤 Toplu Mesaj Gönderimi")
    
    if st.session_state['musteri_data'] is None:
        st.warning("⚠️ Lütfen önce 'Veri Yükle' menüsünden müşteri listenizi yükleyin.")
    else:
        df = st.session_state['musteri_data']
        alici = st.selectbox("Alıcı Seçiniz", ["-- Seçiniz --"] + df["Ünvan / Ad Soyad"].tolist())
        mesaj = st.text_area("Mesaj İçeriği", height=150, placeholder="Mesajınızı buraya yazın...")
        
        if st.button("Gönder", type="primary"):
            if alici == "-- Seçiniz --":
                st.error("Lütfen bir alıcı seçin.")
            else:
                # Gerçek senaryoda Excel'den telefon numarasını çekeriz
                # Şimdilik simülasyon:
                st.success(f"Mesaj gönderildi: {alici}")
                st.toast("İşlem Başarılı")

# --- SAYFA 4: TASDİK ROBOTU ---
elif secim == "Tasdik Robotu":
    st.header("🤖 Tasdik Takip Sistemi")
    
    if st.session_state['musteri_data'] is None:
        st.warning("⚠️ Veri yüklenmedi.")
    else:
        df = st.session_state['musteri_data']
        borclular = df[df["Tahsil_Edildi"] == False]
        
        c1, c2 = st.columns(2)
        c1.metric("🔴 Ödemeyen Mükellef", len(borclular))
        c2.metric("🟢 Tahsil Edilen", len(df) - len(borclular))
        
        st.subheader("Borçlu Listesi")
        for i, row in borclular.iterrows():
            with st.expander(f"{row['Ünvan / Ad Soyad']} - {row.get('Defter Tasdik Ücreti', 0)} TL"):
                if st.button("Tahsilat Yapıldı Olarak İşaretle", key=f"tahsil_{i}"):
                    st.session_state['musteri_data'].at[i, "Tahsil_Edildi"] = True
                    st.rerun()
