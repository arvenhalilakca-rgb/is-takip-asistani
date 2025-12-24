import streamlit as st
import pandas as pd
import re
import pdfplumber
import requests

# ==========================================
# 1. AYARLAR
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi (e-Mükellef Uyumlu)",
    page_icon="🏢",
    layout="wide"
)

# WhatsApp API Ayarları (Burayı doldurun)
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

# Session State
if 'sonuclar' not in st.session_state: st.session_state['sonuclar'] = None
if 'mukellef_listesi' not in st.session_state: st.session_state['mukellef_listesi'] = None

# ==========================================
# 2. FONKSİYONLAR
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
    return "{:,.2f} TL".format(deger).replace(",", "X").replace(".", ",").replace("X", ".")

def whatsapp_gonder(mesaj):
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        requests.post(url, json={'chatId': f"{SABIT_IHBAR_NO}@c.us", 'message': mesaj})
        return True
    except: return False

def vkn_bul_pdf(text):
    """PDF Sayfasındaki Vergi Kimlik Numarasını Bulur."""
    # 1. YÖNTEM: Tırnaklı Format (CSV benzeri sayfa) -> "0010961739"
    m1 = re.search(r'"(\d{10,11})"', text)
    if m1: return m1.group(1)
    
    # 2. YÖNTEM: Standart Etiket -> Vergi Kimlik Numarası ... 1234567890
    m2 = re.search(r'(?:Vergi Kimlik Numarası|TC Kimlik No).*?(\d{10,11})', text, re.IGNORECASE | re.DOTALL)
    if m2: return m2.group(1)
    
    return None

def isim_getir_listeden(vkn):
    """Bulunan VKN'yi yüklenen Excel listesinde arar."""
    if st.session_state['mukellef_listesi'] is not None and vkn:
        df = st.session_state['mukellef_listesi']
        
        # Vergi Numaralarını temizle ve string yap
        vkn = str(vkn).strip()
        
        # Eşleşme ara (Vergi_No sütununda)
        sonuc = df[df['Vergi_No'] == vkn]
        
        if not sonuc.empty:
            return sonuc.iloc[0]['Unvan']
    
    return f"LİSTEDE YOK ({vkn})"

# ==========================================
# 3. ARAYÜZ VE UYGULAMA
# ==========================================

with st.sidebar:
    st.header("YÖNETİM PANELİ")
    mod = st.radio("Seçiniz:", ["1. Mükellef Listesi Yükle", "2. Analizi Başlat"])

# --- MODÜL 1: LİSTE YÜKLEME (DÜZELTİLDİ) ---
if mod == "1. Mükellef Listesi Yükle":
    st.title("📂 Mükellef Listesi Entegrasyonu")
    st.info("e-Mükellef formatındaki (TC/VN ve Ünvan / Ad Soyad sütunlu) dosyanızı yükleyin.")
    
    up_list = st.file_uploader("Mükellef Listesi (Excel/CSV)", type=["xlsx", "xls", "csv"])
    
    if up_list:
        try:
            # Dosyayı oku (String olarak, VKN başındaki 0'lar gitmesin)
            if up_list.name.endswith(".csv"):
                df = pd.read_csv(up_list, dtype=str)
            else:
                df = pd.read_excel(up_list, dtype=str)
            
            # --- KOLON EŞLEŞTİRME VE DÜZELTME ---
            # Sizin dosyanızdaki başlıklar: "TC/VN" ve "Ünvan / Ad Soyad"
            # Bunları kodun anlayacağı "Vergi_No" ve "Unvan" formatına çevirelim.
            
            rename_map = {}
            
            # Vergi No Kolonunu Bul
            if "TC/VN" in df.columns: rename_map["TC/VN"] = "Vergi_No"
            elif "Vergi No" in df.columns: rename_map["Vergi No"] = "Vergi_No"
            elif "VN" in df.columns: rename_map["VN"] = "Vergi_No"
            
            # Ünvan Kolonunu Bul
            if "Ünvan / Ad Soyad" in df.columns: rename_map["Ünvan / Ad Soyad"] = "Unvan"
            elif "Ünvan" in df.columns: rename_map["Ünvan"] = "Unvan"
            
            # İsimleri değiştir
            df = df.rename(columns=rename_map)
            
            # Kontrol et: Gerekli kolonlar oluştu mu?
            if "Vergi_No" in df.columns and "Unvan" in df.columns:
                # Boşlukları temizle
                df["Vergi_No"] = df["Vergi_No"].astype(str).str.strip()
                df["Unvan"] = df["Unvan"].astype(str).str.strip()
                
                st.session_state['mukellef_listesi'] = df
                st.success(f"✅ Liste Başarıyla Yüklendi! Toplam {len(df)} Mükellef.")
                st.dataframe(df[["Unvan", "Vergi_No"]].head())
            else:
                st.error("❌ HATA: Dosyada 'TC/VN' veya 'Ünvan / Ad Soyad' sütunları bulunamadı.")
                st.write("Dosyanızdaki Sütunlar:", df.columns.tolist())
                
        except Exception as e:
            st.error(f"Dosya okuma hatası: {e}")

# --- MODÜL 2: ANALİZ ---
elif mod == "2. Analizi Başlat":
    st.title("🕵️‍♂️ KDV Uyumsuzluk Analizi")
    
    # Liste kontrolü
    if st.session_state['mukellef_listesi'] is None:
        st.warning("⚠️ Lütfen önce yan menüden 'Mükellef Listesi' yükleyiniz.")
        st.stop()
        
    pdf_up = st.file_uploader("Beyanname PDF Dosyasını Yükle", type=["pdf"])
    
    if pdf_up:
        if st.button("🚀 ANALİZİ BAŞLAT", type="primary"):
            st.info("Beyannameler taranıyor ve listenizle eşleştiriliyor...")
            sonuclar = []
            
            with pdfplumber.open(pdf_up) as pdf:
                total_pages = len(pdf.pages)
                bar = st.progress(0)
                
                for i, page in enumerate(pdf.pages):
                    bar.progress((i+1)/total_pages)
                    text = page.extract_text()
                    if not text: continue
                    
                    # Sadece KDV Beyannameleri
                    if "KATMA DEĞER VERGİSİ" in text or "MATRAH" in text:
                        
                        # 1. Vergi Numarasını PDF'ten Bul
                        vkn = vkn_bul_pdf(text)
                        
                        # 2. İsmi Senin Listenden Çek (Eşleştirme)
                        isim = isim_getir_listeden(vkn)
                        
                        # 3. Rakamsal Verileri Çek
                        m_match = re.search(r"(?:TOPLAM MATRAH|Teslim ve Hizmetlerin Karşılığını).*?([\d\.,]+)", text, re.IGNORECASE)
                        matrah = text_to_float(m_match.group(1)) if m_match else 0.0
                        
                        k_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
                        kdv = text_to_float(k_match.group(1)) if k_match else 0.0
                        
                        pos_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
                        pos = text_to_float(pos_match.group(1)) if pos_match else 0.0
                        
                        # 4. Hesaplama (Matrah + KDV vs POS)
                        beyan_toplam = matrah + kdv
                        fark = pos - beyan_toplam
                        
                        # Fark varsa kaydet
                        if fark > 50:
                            sonuclar.append({
                                "Mükellef": isim,
                                "Vergi_No": vkn,
                                "POS": pos,
                                "Beyan": beyan_toplam,
                                "Fark": fark
                            })
            
            st.session_state['sonuclar'] = pd.DataFrame(sonuclar)
            st.rerun()

    # --- SONUÇ EKRANI ---
    if st.session_state['sonuclar'] is not None:
        df = st.session_state['sonuclar']
        
        if df.empty:
            st.success("✅ Harika! Hiçbir riskli mükellef bulunamadı.")
        else:
            st.error(f"🚨 Toplam {len(df)} Adet Riskli Durum Tespit Edildi")
            
            for i, row in df.iterrows():
                # Tasarım
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.markdown(f"""
                        <div style="background-color:white; padding:15px; border-radius:10px; border-left:6px solid #d32f2f; box-shadow:0 2px 5px rgba(0,0,0,0.1); margin-bottom:15px;">
                            <div style="font-size:18px; font-weight:bold; color:#d32f2f;">{row['Mükellef']}</div>
                            <div style="font-size:12px; color:#666;">Vergi No: {row['Vergi_No']}</div>
                            <hr style="margin:10px 0;">
                            <div style="display:flex; gap:20px;">
                                <div><b>POS Tahsilat:</b><br>{para_formatla(row['POS'])}</div>
                                <div><b>Beyan (Matrah+KDV):</b><br>{para_formatla(row['Beyan'])}</div>
                            </div>
                            <div style="margin-top:10px; font-weight:bold; color:#d32f2f;">⚠️ FARK: {para_formatla(row['Fark'])}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col2:
                        st.write("")
                        st.write("")
                        st.write("")
                        if st.button(f"İHBAR ET 📲", key=f"btn_{i}", type="secondary", use_container_width=True):
                            msg = (f"⚠️ *KDV UYUMSUZLUK RAPORU*\n\n"
                                   f"Firma: {row['Mükellef']}\n"
                                   f"Vergi No: {row['Vergi_No']}\n"
                                   f"POS Tahsilat: {para_formatla(row['POS'])}\n"
                                   f"Beyan (Dahil): {para_formatla(row['Beyan'])}\n"
                                   f"Fark: {para_formatla(row['Fark'])}\n\n"
                                   f"Lütfen kontrol ediniz.")
                            
                            if whatsapp_gonder(msg):
                                st.toast("✅ Mesaj Başarıyla İletildi!")
                            else:
                                st.error("Gönderim Hatası!")
