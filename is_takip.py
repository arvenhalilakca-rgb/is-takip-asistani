import streamlit as st
import requests
import pandas as pd
import re
from datetime import datetime
import time
import pdfplumber
import io

# ==========================================
# 1. AYARLAR VE YAPILANDIRMA
# ==========================================
st.set_page_config(
    page_title="Müşavir İletişim Kulesi",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API ve Sabit Ayarlar
# Buraya kendi Instance ve Token bilgilerinizi girin veya st.secrets kullanın
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"  # İhbarların gideceği sabit numara

# Görsel Tasarım (CSS)
st.markdown("""
    <style>
    .stApp {background-color: #F2F6FC; font-family: 'Segoe UI', sans-serif;}
    [data-testid="stSidebar"] {background-color: #FFFFFF; border-right: 1px solid #E0E0E0;}
    
    /* Risk Kartı Tasarımı */
    .risk-karti {
        background-color: #ffffff; padding: 20px; border-radius: 12px; 
        border-left: 8px solid #d32f2f; margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .risk-baslik {font-size: 18px; font-weight: bold; color: #b71c1c; margin-bottom: 10px;}
    .risk-detay {font-size: 15px; color: #333; margin-bottom: 5px;}
    .risk-fark {font-size: 16px; font-weight: bold; color: #d32f2f; margin-top: 10px; border-top: 1px solid #eee; padding-top:10px;}
    
    /* Mesaj Balonu */
    .chat-container {background-color: #e5ddd5; padding: 20px; border-radius: 10px; border: 1px solid #ddd;}
    .message-bubble {background-color: #dcf8c6; padding: 10px; border-radius: 8px; color: #303030; display: inline-block;}
    </style>
    """, unsafe_allow_html=True)

# Session State (Veri Saklama)
if 'analiz_sonuclari' not in st.session_state: st.session_state['analiz_sonuclari'] = None
if 'tasdik_data' not in st.session_state: st.session_state['tasdik_data'] = None

# Mesaj Şablonları
MESAJ_SABLONLARI = {
    "Serbest Metin": "",
    "KDV Tahakkuk Bilgisi": "Sayın {isim}, {ay} dönemi KDV beyannameniz onaylanmıştır. Ödemenizi vadesinde yapmanızı rica ederiz.",
    "Tasdik Borcu Uyarısı": "Sayın Mükellefimiz {isim}, Defter Tasdik borcunuz ({tutar} TL) bulunmaktadır. Ödeme yapılmadığı takdirde defter teslimi yapılamayacaktır.",
}

# ==========================================
# 2. FONKSİYONLAR
# ==========================================

def clean_text(text):
    """Metni tırnak, virgül vb. karakterlerden temizler."""
    if not text: return ""
    return text.replace('"', '').replace(',', ' ').strip()

def text_to_float(text):
    """Metni sayıya çevirir (1.000,00 formatı)."""
    try:
        clean = re.sub(r'[^\d,\.]', '', str(text)).strip()
        if "," in clean and "." in clean: clean = clean.replace(".", "").replace(",", ".")
        elif "," in clean: clean = clean.replace(",", ".")
        return float(clean)
    except: return 0.0

def para_formatla(deger):
    """Parayı TL formatına çevirir."""
    return "{:,.2f} TL".format(deger).replace(",", "X").replace(".", ",").replace("X", ".")

def whatsapp_gonder(numara, mesaj):
    """WhatsApp mesajı gönderir."""
    if numara == "905351041616": # Sabit numara formatı zaten doğru
        chat_id = f"{numara}@c.us"
    else:
        # Diğer numaralar için temizlik
        numara = re.sub(r'\D', '', str(numara))
        if len(numara) == 10: numara = "90" + numara
        elif len(numara) == 11 and numara.startswith("0"): numara = "9" + numara
        chat_id = f"{numara}@c.us"

    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        payload = {'chatId': chat_id, 'message': mesaj}
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except: return False

def mukellef_ismi_bul(text):
    """Karmaşık PDF yapısından Mükellef ismini (Soyadı + Adı/Unvan Devamı) çeker."""
    lines = text.split('\n')
    part1 = ""
    part2 = ""
    
    # İlk 60 satırı tara
    limit = min(len(lines), 60)
    
    for i in range(limit):
        clean_line = clean_text(lines[i])
        
        # 1. Parça: Soyadı (Unvanı)
        if "Soyadı (Unvanı)" in clean_line:
            # Genellikle değer bir alt satırdadır
            if i + 1 < limit:
                val = clean_text(lines[i+1])
                # Müşavir veya Vergi dairesi bilgisi değilse al
                if "SMMM" not in val and "VERGİ" not in val and "MÜDÜR" not in val:
                    part1 = val
        
        # 2. Parça: Adı (Unvanın Devamı)
        if "Adı (Unvanın Devamı)" in clean_line:
            if i + 1 < limit:
                val = clean_text(lines[i+1])
                part2 = val
                
    full_name = f"{part1} {part2}".strip()
    
    # Eğer boşsa veya yanlışlıkla müşavir ismi geldiyse regex dene
    if not full_name or "SMMM" in full_name:
        try:
            # Yedek Yöntem: Regex ile tırnak içindeki veriyi al
            m = re.search(r'"Soyadı \(Unvanı\)"\s*,\s*"([^"]+)"', text)
            if m: full_name = m.group(1)
        except: pass
        
    return full_name if full_name else "İsim Okunamadı"

# ==========================================
# 3. ANA UYGULAMA VE MENÜLER
# ==========================================

# Yan Menü
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    st.title("Müşavir Kulesi")
    secim = st.radio("İŞLEM SEÇİNİZ", ["KDV Analiz Robotu", "Veri Yükle", "Profesyonel Mesaj", "Tasdik Robotu"])
    st.markdown("---")
    st.info("v3.0 - Tek Parça Sürüm")

# --- 1. KDV ANALİZ ROBOTU ---
if secim == "KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz & İhbar Sistemi")
    st.markdown("""
    **Analiz Mantığı:** 1. `(Matrah + Hesaplanan KDV)` toplanır.
    2. `Kredi Kartı (POS)` tutarı ile karşılaştırılır.
    3. Eğer **POS > (Matrah + KDV)** ise risk uyarısı verir.
    """)
    
    pdf_up = st.file_uploader("KDV Beyannamesi Yükle (PDF)", type=["pdf"])
    
    if pdf_up:
        if st.button("🚀 ANALİZİ BAŞLAT", type="primary"):
            progress = st.progress(0)
            sonuclar = []
            
            with pdfplumber.open(pdf_up) as pdf:
                total_pages = len(pdf.pages)
                for i, page in enumerate(pdf.pages):
                    progress.progress((i+1)/total_pages)
                    text = page.extract_text()
                    if not text: continue
                    
                    # A) İsim Bul
                    isim = mukellef_ismi_bul(text)
                    
                    # B) Verileri Çek (Regex)
                    # Matrah
                    m_match = re.search(r"(?:TOPLAM MATRAH|Teslim ve Hizmetlerin Karşılığını).*?([\d\.,]+)", text, re.IGNORECASE)
                    matrah = text_to_float(m_match.group(1)) if m_match else 0.0
                    
                    # KDV (Toplam Hesaplanan)
                    k_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
                    kdv = text_to_float(k_match.group(1)) if k_match else 0.0
                    
                    # Kredi Kartı (POS)
                    kk_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
                    pos = text_to_float(kk_match.group(1)) if kk_match else 0.0
                    
                    # C) Hesaplama
                    # İstediğin Mantık: Matrah + KDV vs POS
                    beyan_toplam = matrah + kdv
                    fark = pos - beyan_toplam
                    
                    # 50 TL Tolerans
                    if fark > 50:
                        sonuclar.append({
                            "Mükellef": isim,
                            "Matrah": matrah,
                            "KDV": kdv,
                            "Beyan_Toplam": beyan_toplam,
                            "POS": pos,
                            "Fark": fark
                        })
            
            st.session_state['analiz_sonuclari'] = pd.DataFrame(sonuclar)
            st.rerun()

    # Sonuç Ekranı
    if st.session_state['analiz_sonuclari'] is not None:
        df = st.session_state['analiz_sonuclari']
        
        if df.empty:
            st.success("✅ Taranan dosyalarda herhangi bir KDV/POS uyumsuzluğu bulunamadı.")
        else:
            st.error(f"🚨 {len(df)} Adet Riskli Beyanname Tespit Edildi!")
            
            for i, row in df.iterrows():
                # Değişkenler
                ad = row['Mükellef']
                pos_str = para_formatla(row['POS'])
                beyan_str = para_formatla(row['Beyan_Toplam'])
                fark_str = para_formatla(row['Fark'])
                
                # Kart Yapısı
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.markdown(f"""
                        <div class='risk-karti'>
                            <div class='risk-baslik'>🚨 {ad}</div>
                            <div class='risk-detay'>
                                <b>💳 POS Tahsilat:</b> {pos_str}<br>
                                <b>📄 Beyan (Matrah+KDV):</b> {beyan_str}
                            </div>
                            <div class='risk-fark'>⚠️ EKSİK BEYAN FARKI: {fark_str}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col2:
                        st.write("") # Hizalama boşluğu
                        st.info("📞 İhbar Hattı:\n**0535 104 16 16**")
                        
                        if st.button("🚨 İHBAR ET", key=f"btn_{i}", type="primary", use_container_width=True):
                            # Mesaj Hazırla
                            msg = (f"⚠️ *KDV UYUMSUZLUK RAPORU*\n\n"
                                   f"Firma: {ad}\n"
                                   f"POS Tahsilat: {pos_str}\n"
                                   f"Beyan (Dahil): {beyan_str}\n"
                                   f"Fark: {fark_str}\n\n"
                                   f"Lütfen kontrol ediniz.")
                            
                            # Gönder
                            if whatsapp_gonder(SABIT_IHBAR_NO, msg):
                                st.toast(f"İhbar İletildi: {ad} ✅")
                            else:
                                st.error("Gönderim Başarısız (API Hatası)")

# --- 2. VERİ YÜKLEME ---
elif secim == "Veri Yükle":
    st.title("📂 Müşteri Veritabanı")
    st.info("Müşteri listesini (Excel) buradan yükleyerek diğer modülleri aktif edebilirsiniz.")
    
    up = st.file_uploader("Excel Dosyası Yükle", type=["xlsx", "xls"])
    if up:
        try:
            df = pd.read_excel(up)
            # Kolon kontrolü ve temizliği
            if "Para Alındı mı" in df.columns:
                df["Tahsil_Edildi"] = df["Para Alındı mı"].apply(lambda x: True if pd.notna(x) and str(x).strip() != "" else False)
            else:
                df["Tahsil_Edildi"] = False
            
            st.session_state['tasdik_data'] = df
            st.success(f"✅ {len(df)} Müşteri Kaydı Başarıyla Yüklendi.")
            st.dataframe(df.head())
        except Exception as e:
            st.error(f"Dosya okuma hatası: {e}")

# --- 3. PROFESYONEL MESAJ ---
elif secim == "Profesyonel Mesaj":
    st.title("📤 Toplu Mesaj Merkezi")
    
    if st.session_state['tasdik_data'] is None:
        st.warning("⚠️ Lütfen önce 'Veri Yükle' menüsünden müşteri listenizi yükleyin.")
    else:
        df_m = st.session_state['tasdik_data']
        
        c1, c2 = st.columns(2)
        with c1:
            hedef = st.selectbox("Kime Gönderilecek?", ["Seçiniz..."] + df_m["Ünvan / Ad Soyad"].tolist())
            sablon = st.selectbox("Şablon Seç", list(MESAJ_SABLONLARI.keys()))
            txt = st.text_area("Mesaj İçeriği", value=MESAJ_SABLONLARI[sablon], height=150)
            
        with c2:
            st.subheader("Önizleme")
            preview_text = txt.replace("{isim}", hedef if hedef != "Seçiniz..." else "Müşteri Adı").replace("{ay}", "Cari Ay")
            st.markdown(f"<div class='chat-container'><div class='message-bubble'>{preview_text}</div></div>", unsafe_allow_html=True)
            
            if st.button("GÖNDER", type="primary"):
                if hedef == "Seçiniz...":
                    st.error("Müşteri seçmediniz.")
                else:
                    # Gerçek gönderim simülasyonu (Numara excelden çekilir)
                    row = df_m[df_m["Ünvan / Ad Soyad"] == hedef].iloc[0]
                    tel = row.get("1.NUMARA", "") # Excel kolon adı
                    if whatsapp_gonder(tel, preview_text):
                        st.success("Mesaj Gönderildi! ✅")
                    else:
                        st.error("Gönderilemedi (API veya Numara Hatası)")

# --- 4. TASDİK ROBOTU ---
elif secim == "Tasdik Robotu":
    st.title("🤖 Tasdik Takip Sistemi")
    
    if st.session_state['tasdik_data'] is None:
        st.warning("⚠️ Lütfen önce 'Veri Yükle' menüsünden müşteri listenizi yükleyin.")
    else:
        df_t = st.session_state['tasdik_data']
        borclular = df_t[df_t["Tahsil_Edildi"] == False]
        
        col1, col2 = st.columns(2)
        col1.metric("🔴 Ödemeyen Mükellef", len(borclular))
        col2.metric("🟢 Tahsil Edilen", len(df_t) - len(borclular))
        
        st.divider()
        st.subheader("Borçlu Listesi & Aksiyon")
        
        for i, row in borclular.iterrows():
            with st.expander(f"{row['Ünvan / Ad Soyad']} - {row.get('Defter Tasdik Ücreti', 0)} TL"):
                c_btn1, c_btn2 = st.columns(2)
                
                if c_btn1.button("✅ ÖDENDİ İŞARETLE", key=f"pay_{i}"):
                    st.session_state['tasdik_data'].at[i, "Tahsil_Edildi"] = True
                    st.rerun()
                    
                if c_btn2.button("📩 BORÇ UYARISI AT", key=f"msg_{i}"):
                    msg = MESAJ_SABLONLARI["Tasdik Borcu Uyarısı"].format(
                        isim=row['Ünvan / Ad Soyad'], 
                        tutar=row.get('Defter Tasdik Ücreti', 0)
                    )
                    tel = row.get("1.NUMARA", "")
                    whatsapp_gonder(tel, msg)
                    st.toast("Uyarı Gönderildi")
