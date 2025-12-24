import streamlit as st
import pandas as pd
import re
import pdfplumber
import requests
import time

# ==========================================
# 1. AYARLAR & SABİT DEĞİŞKENLER
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi (Çoklu Beyanname Okuyucu)",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Ayarları
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

# Aranacak anahtar kelimeler
MATRAH_ANAHTAR_KELIMELER = ["Teslim ve Hizmetlerin Karşılığını Teşkil Eden Bedel", "TOPLAM MATRAH", "Matrah"]
KDV_ANAHTAR_KELIMELER = ["TOPLAM HESAPLANAN KDV", "Hesaplanan KDV Toplamı", "Hesaplanan Katma Değer Vergisi", "Hesaplanan KDV"]
POS_ANAHTAR_KELIMELER = ["Kredi Kartı ile Tahsil Edilen Teslim ve Hizmetlerin KDV Dahil Karşılığını Teşkil Eden Bedel", "Kredi Kartı ile Tahsil", "Kredi Kartı"]

# YENİ: Beyannameleri ayırmak için kullanılacak başlık. Bu, bir beyannamenin başlangıcını işaret eder.
BEYANNAME_AYRACI = "KATMA DEĞER VERGİSİ BEYANNAMESİ"

# CSS Stilleri
st.markdown("""
    <style>
    /* ... CSS kodları öncekiyle aynı, buraya eklemeye gerek yok ... */
    .stApp {background-color: #f4f6f9; font-family: 'Segoe UI', sans-serif;}
    [data-testid="stSidebar"] {background-color: #fff; border-right: 1px solid #ddd;}
    .card { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 10px; border: 1px solid #eee; }
    .risk-card {border-left: 5px solid #d32f2f;}
    .clean-card {border-left: 5px solid #28a745;}
    .stat-val {font-weight: bold; font-size: 15px; color: #333;}
    .stat-lbl {font-size: 11px; color: #777;}
    .card-title {font-size: 16px; font-weight: bold; margin-bottom: 5px;}
    .card-sub {font-size: 12px; color: #666; margin-bottom: 10px;}
    </style>
    """, unsafe_allow_html=True)

# Session State
if 'sonuclar' not in st.session_state: st.session_state['sonuclar'] = None
if 'mukellef_db' not in st.session_state: st.session_state['mukellef_db'] = None

# ==========================================
# 2. MOTOR: YARDIMCI FONKSİYONLAR (Değişiklik yok)
# ==========================================
def text_to_float(text):
    try:
        text = str(text).replace('"', '').replace("'", "").strip()
        clean = re.sub(r'[^\d,\.]', '', text)
        if "," in clean and "." in clean:
            if clean.rfind(".") > clean.rfind(","): clean = clean.replace(".", "").replace(",", ".")
            else: clean = clean.replace(",", "")
        elif "," in clean: clean = clean.replace(",", ".")
        return float(clean)
    except (ValueError, TypeError): return 0.0

def para_formatla(deger):
    if not isinstance(deger, (int, float)): return "0,00 TL"
    return "{:,.2f} TL".format(deger).replace(",", "X").replace(".", ",").replace("X", ".")

def whatsapp_gonder(numara, mesaj):
    # ... (Bu fonksiyon aynı kalabilir)
    pass

def vkn_bul(text):
    # ... (Bu fonksiyon aynı kalabilir)
    m1 = re.search(r'"(\d{10,11})"', text)
    if m1: return m1.group(1)
    m2 = re.search(r'(?:Vergi Kimlik|TC Kimlik|Vergi No|VKN|TCKN)[\s:]*(\d{10,11})', text, re.IGNORECASE)
    if m2: return m2.group(1)
    m3 = re.search(r'\b(\d{10,11})\b', text)
    if m3: return m3.group(1)
    return None

def isim_eslestir_excel(numara):
    # ... (Bu fonksiyon aynı kalabilir)
    if st.session_state['mukellef_db'] is None: return f"Bilinmeyen ({numara or 'Bulunamadı'})"
    if not numara: return "VKN/TCKN PDF'te Bulunamadı"
    df = st.session_state['mukellef_db']
    numara_str = str(numara).strip()
    res_vkn = df[df['C_VKN'] == numara_str]
    if not res_vkn.empty: return res_vkn.iloc[0]['A_UNVAN']
    res_tc = df[df['B_TC'] == numara_str]
    if not res_tc.empty: return res_tc.iloc[0]['A_UNVAN']
    return f"Listede Yok ({numara_str})"

def veri_cozucu_pro(text, anahtar_kelimeler):
    # ... (Bu fonksiyon aynı kalabilir)
    for kelime in anahtar_kelimeler:
        try:
            pattern = re.escape(kelime) + r'[\s\S]*?([\d\.,]{3,})'
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match: return text_to_float(match.group(1))
        except Exception: continue
    return 0.0

# ==========================================
# 3. ARAYÜZ & ANA UYGULAMA AKIŞI
# ==========================================

# Sidebar (Yan Menü)
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.header("MÜŞAVİR PANELİ")
    secim = st.radio("MENÜ", ["1. Excel Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"])

# Sayfa 1: Excel Yükleme
if secim == "1. Excel Listesi Yükle":
    # ... (Bu bölüm aynı kalabilir)
    st.title("📂 Mükellef Veritabanı Yükle")
    st.info("Sütunlar: **A (Unvan), B (TCKN), C (VKN), D (Telefon)**.")
    uploaded_file = st.file_uploader("Excel Dosyasını Seçin", type=["xlsx", "xls"])
    if uploaded_file:
        try:
            raw_df = pd.read_excel(uploaded_file, dtype=str, header=None)
            df = pd.DataFrame()
            df['A_UNVAN'] = raw_df.iloc[:, 0].astype(str).str.strip()
            df['B_TC']    = raw_df.iloc[:, 1].astype(str).str.strip()
            df['C_VKN']   = raw_df.iloc[:, 2].astype(str).str.strip()
            df['D_TEL'] = raw_df.iloc[:, 3].astype(str).str.strip().str.replace(r'\D', '', regex=True) if raw_df.shape[1] >= 4 else ""
            st.session_state['mukellef_db'] = df.fillna("")
            st.success(f"✅ Başarılı! {len(df)} mükellef bilgisi yüklendi.")
        except Exception as e: st.error(f"❌ Dosya okunurken hata: {e}")

# Sayfa 2: KDV Analiz Robotu
elif secim == "2. KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz Üssü (Çoklu Beyanname Okuyucu)")
    
    if st.session_state.get('mukellef_db') is None:
        st.warning("⚠️ Lütfen önce '1. Excel Listesi Yükle' menüsünden listenizi yükleyin.")
        st.stop()
    
    pdf_files = st.file_uploader("İçinde bir veya yüzlerce beyanname olan PDF dosyasını yükleyin", type=["pdf"], accept_multiple_files=True)
    
    if pdf_files and st.button("🚀 TÜM BEYANNAMELERİ ANALİZ ET", type="primary", use_container_width=True):
        sonuclar = []
        toplam_bulunan_beyanname = 0
        
        progress_bar = st.progress(0, text="PDF'ler okunuyor...")

        for pdf_idx, pdf_file in enumerate(pdf_files):
            try:
                # 1. ADIM: PDF'in tüm metnini tek bir string olarak oku
                full_text = ""
                with pdfplumber.open(pdf_file) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text(x_tolerance=1)
                        if page_text:
                            full_text += page_text + "\n"
                
                # 2. ADIM: Okunan tüm metni, beyanname başlığına göre böl
                # re.split, ayraç metnini de korumak için parantez içine alınır.
                beyanname_bloklari = re.split(f'({re.escape(BEYANNAME_AYRACI)})', full_text)
                
                # re.split'in çıktısını birleştirerek anlamlı bloklar oluştur
                # Çıktı: ['', 'AYRAÇ', 'beyanname 1 metni', 'AYRAÇ', 'beyanname 2 metni', ...]
                if len(beyanname_bloklari) > 1:
                    # İlk eleman genellikle boştur, atla. Sonra her ayraçla metnini birleştir.
                    processed_blocks = [beyanname_bloklari[i] + beyanname_bloklari[i+1] for i in range(1, len(beyanname_bloklari)-1, 2)]
                else:
                    processed_blocks = beyanname_bloklari # Eğer hiç ayraç bulunamazsa, tüm metni tek blok say

                st.info(f"'{pdf_file.name}' dosyasında yaklaşık **{len(processed_blocks)}** adet beyanname bloğu tespit edildi. İşleniyor...")
                time.sleep(2)

                # 3. ADIM: Her bir beyanname bloğu için analiz döngüsü başlat
                for beyanname_text in processed_blocks:
                    if not beyanname_text.strip(): continue # Boş blokları atla

                    toplam_bulunan_beyanname += 1
                    
                    vkn = vkn_bul(beyanname_text)
                    isim = isim_eslestir_excel(vkn)
                    matrah = veri_cozucu_pro(beyanname_text, MATRAH_ANAHTAR_KELIMELER)
                    kdv = veri_cozucu_pro(beyanname_text, KDV_ANAHTAR_KELIMELER)
                    pos = veri_cozucu_pro(beyanname_text, POS_ANAHTAR_KELIMELER)
                    
                    beyan_toplami = matrah + kdv
                    fark = pos - beyan_toplami
                    
                    if pos > 0 and beyan_toplami == 0:
                        durum = "OKUNAMADI"
                    elif fark > 50:
                        durum = "RISKLI"
                    else:
                        durum = "TEMIZ"
                    
                    sonuclar.append({
                        "Mükellef": isim, "VKN": vkn or "Bulunamadı", "POS": pos,
                        "Beyan": beyan_toplami, "Fark": fark, "Durum": durum
                    })

            except Exception as e:
                st.error(f"'{pdf_file.name}' dosyasını işlerken kritik bir hata oluştu: {e}")
            
            progress_bar.progress((pdf_idx + 1) / len(pdf_files), text=f"'{pdf_file.name}' dosyası tamamlandı.")

        st.session_state['sonuclar'] = pd.DataFrame(sonuclar) if sonuclar else pd.DataFrame()
        st.success(f"Analiz tamamlandı! Toplam **{toplam_bulunan_beyanname}** beyanname incelendi.")
        progress_bar.empty()

    # --- SONUÇLARI GÖSTERME ---
    if st.session_state.get('sonuclar') is not None:
        df_sonuc = st.session_state['sonuclar']
        if not df_sonuc.empty:
            riskliler = df_sonuc[df_sonuc['Durum'] == "RISKLI"]
            temizler = df_sonuc[df_sonuc['Durum'] == "TEMIZ"]
            okunamayanlar = df_sonuc[df_sonuc['Durum'] == "OKUNAMADI"]

            tab1, tab2, tab3 = st.tabs([f"🚨 RİSKLİ ({len(riskliler)})", f"✅ UYUMLU ({len(temizler)})", f"❓ OKUNAMAYAN ({len(okunamayanlar)})"])
            
            with tab1:
                # ... (Riskli sekmesi için olan kod aynı kalabilir)
                st.dataframe(riskliler)
            with tab2:
                # ... (Temiz sekmesi için olan kod aynı kalabilir)
                st.dataframe(temizler)
            with tab3:
                # ... (Okunamayan sekmesi için olan kod aynı kalabilir)
                st.dataframe(okunamayanlar)

# Diğer sayfalar (Mesaj, Tasdik) aynı kalabilir...
elif secim == "3. Profesyonel Mesaj":
    # ...
    pass
elif secim == "4. Tasdik Robotu":
    # ...
    pass
