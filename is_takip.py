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
    page_title="Müşavir Kulesi (Pro Veri Okuyucu)",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Ayarları (Streamlit Secrets'tan güvenli bir şekilde çekilir)
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616" # İhbarların gönderileceği sabit numara

# PDF'ten veri aramak için kullanılacak anahtar kelime listeleri
# Bu listeleri düzenleyerek arama yeteneğini geliştirebilirsiniz.
MATRAH_ANAHTAR_KELIMELER = [
    "Teslim ve Hizmetlerin Karşılığını Teşkil Eden Bedel",
    "TOPLAM MATRAH",
    "Matrah"
]
KDV_ANAHTAR_KELIMELER = [
    "TOPLAM HESAPLANAN KDV",
    "Hesaplanan KDV Toplamı",
    "Hesaplanan Katma Değer Vergisi",
    "Hesaplanan KDV"
]
POS_ANAHTAR_KELIMELER = [
    "Kredi Kartı ile Tahsil Edilen Teslim ve Hizmetlerin KDV Dahil Karşılığını Teşkil Eden Bedel",
    "Kredi Kartı ile Tahsil Edilen Teslim ve Hizmetler",
    "Kredi Kartı ile Tahsil",
    "Kredi Kartı"
]

# CSS Stilleri
st.markdown("""
    <style>
    .stApp {background-color: #f4f6f9; font-family: 'Segoe UI', sans-serif;}
    [data-testid="stSidebar"] {background-color: #fff; border-right: 1px solid #ddd;}
    .terminal-window {
        background-color: #1e1e1e; color: #00ff41; font-family: monospace;
        padding: 15px; border-radius: 8px; height: 200px; overflow-y: auto;
        font-size: 12px; margin-bottom: 20px; border: 1px solid #333;
    }
    .card {
        background: white; padding: 15px; border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 10px; border: 1px solid #eee;
    }
    .risk-card {border-left: 5px solid #d32f2f;}
    .clean-card {border-left: 5px solid #28a745;}
    .stat-val {font-weight: bold; font-size: 15px; color: #333;}
    .stat-lbl {font-size: 11px; color: #777;}
    .card-title {font-size: 16px; font-weight: bold; margin-bottom: 5px;}
    .card-sub {font-size: 12px; color: #666; margin-bottom: 10px;}
    </style>
    """, unsafe_allow_html=True)

# Session State (Oturum Yönetimi)
if 'sonuclar' not in st.session_state: st.session_state['sonuclar'] = None
if 'mukellef_db' not in st.session_state: st.session_state['mukellef_db'] = None

# ==========================================
# 2. MOTOR: YARDIMCI FONKSİYONLAR
# ==========================================

def text_to_float(text):
    """Metin içindeki sayısal ifadeyi float'a çevirir. Para formatlarını (.,) anlar."""
    try:
        text = str(text).replace('"', '').replace("'", "").strip()
        clean = re.sub(r'[^\d,\.]', '', text)
        if "," in clean and "." in clean:
            if clean.rfind(".") > clean.rfind(","): # 1.234.567,89 formatı
                clean = clean.replace(".", "").replace(",", ".")
            else: # 1,234,567.89 formatı
                clean = clean.replace(",", "")
        elif "," in clean:
            clean = clean.replace(",", ".")
        return float(clean)
    except (ValueError, TypeError):
        return 0.0

def para_formatla(deger):
    """Sayıyı para formatında (örn: 1.234,56 TL) string'e çevirir."""
    if not isinstance(deger, (int, float)): return "0,00 TL"
    return "{:,.2f} TL".format(deger).replace(",", "X").replace(".", ",").replace("X", ".")

def whatsapp_gonder(numara, mesaj):
    """Green-API kullanarak WhatsApp mesajı gönderir."""
    if not numara or not ID_INSTANCE or not API_TOKEN:
        st.error("API bilgileri veya telefon numarası eksik!")
        return False
    target = f"{SABIT_IHBAR_NO}@c.us" if numara == "SABIT" else f"{numara}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        response = requests.post(url, json={'chatId': target, 'message': mesaj}, timeout=10)
        response.raise_for_status() # HTTP hatalarını kontrol et
        return True
    except requests.exceptions.RequestException as e:
        st.error(f"WhatsApp gönderme hatası: {e}")
        return False

def vkn_bul(text):
    """PDF metninden VKN veya TCKN bulur. Farklı formatları dener."""
    # Desen 1: Tırnak içinde 10 veya 11 haneli sayı "1234567890"
    m1 = re.search(r'"(\d{10,11})"', text)
    if m1: return m1.group(1)
    
    # Desen 2: Anahtar kelimeden sonra gelen 10-11 haneli sayı (Vergi No: 1234567890)
    m2 = re.search(r'(?:Vergi Kimlik|TC Kimlik|Vergi No|VKN|TCKN)[\s:]*(\d{10,11})', text, re.IGNORECASE)
    if m2: return m2.group(1)

    # Desen 3: Sadece metin içinde geçen 10 veya 11 haneli bir sayı bloğu
    m3 = re.search(r'\b(\d{10,11})\b', text)
    if m3: return m3.group(1)
    
    return None

def isim_eslestir_excel(numara):
    """Bulunan VKN/TCKN'yi Excel listesindeki mükellef ismiyle eşleştirir."""
    if st.session_state['mukellef_db'] is None: return f"Bilinmeyen ({numara or 'Bulunamadı'})"
    if not numara: return "VKN/TCKN PDF'te Bulunamadı"
    
    df = st.session_state['mukellef_db']
    numara_str = str(numara).strip()
    
    # Önce VKN sütununda ara
    res_vkn = df[df['C_VKN'] == numara_str]
    if not res_vkn.empty: return res_vkn.iloc[0]['A_UNVAN']
    
    # Bulamazsa TC sütununda ara
    res_tc = df[df['B_TC'] == numara_str]
    if not res_tc.empty: return res_tc.iloc[0]['A_UNVAN']
    
    return f"Listede Yok ({numara_str})"

def veri_cozucu_pro(text, anahtar_kelimeler):
    """
    [GELİŞTİRİLMİŞ FONKSİYON]
    PDF metninden, anahtar kelimeleri takip eden sayısal değeri agresif bir şekilde bulur.
    Yeni satır, farklı boşluklar ve format farklılıklarına karşı dayanıklıdır.
    """
    for kelime in anahtar_kelimeler:
        try:
            # Desen: Anahtar kelime + herhangi bir karakter (boşluk, yeni satır vb.) + sayısal değer
            # re.DOTALL, '.' karakterinin yeni satırları da eşleştirmesini sağlar.
            # [\s\S]*? en esnek yapıdır: herhangi bir karakterin tembel eşleşmesi.
            # ([\d\.,]{3,}) en az 3 haneli bir sayı arayarak (örn: 1,00) ilgisiz rakamları eler.
            pattern = re.escape(kelime) + r'[\s\S]*?([\d\.,]{3,})'
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return text_to_float(match.group(1))
        except Exception:
            continue # Bir anahtar kelime hata verirse diğerleriyle devam et
    return 0.0

# ==========================================
# 3. ARAYÜZ & UYGULAMA AKIŞI
# ==========================================

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.header("MÜŞAVİR PANELİ")
    secim = st.radio("MENÜ", ["1. Excel Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"])

# --- 1. LİSTE YÜKLEME ---
if secim == "1. Excel Listesi Yükle":
    st.title("📂 Mükellef Veritabanı Yükle")
    st.info("Lütfen Excel dosyanızın ilk 4 sütununun şu sırada olduğundan emin olun: **A (Unvan), B (TCKN), C (VKN), D (Telefon)**. Telefon sütunu olmasa da çalışır.")
    
    uploaded_file = st.file_uploader("Excel Dosyasını Seçin", type=["xlsx", "xls"])
    if uploaded_file:
        try:
            raw_df = pd.read_excel(uploaded_file, dtype=str, header=None) # Başlıksız oku
            if raw_df.shape[1] >= 3:
                df = pd.DataFrame()
                df['A_UNVAN'] = raw_df.iloc[:, 0].astype(str).str.strip()
                df['B_TC']    = raw_df.iloc[:, 1].astype(str).str.strip()
                df['C_VKN']   = raw_df.iloc[:, 2].astype(str).str.strip()
                
                # Telefon numarası sütunu varsa (D sütunu)
                if raw_df.shape[1] >= 4:
                    df['D_TEL'] = raw_df.iloc[:, 3].astype(str).str.strip().str.replace(r'\D', '', regex=True)
                else:
                    df['D_TEL'] = ""
                
                st.session_state['mukellef_db'] = df.fillna("")
                st.success(f"✅ Başarılı! {len(df)} mükellef bilgisi sisteme yüklendi.")
                st.dataframe(df.head())
            else:
                st.error("❌ Hata: Excel dosyasında en az 3 sütun (Unvan, TC, VKN) bulunmalıdır.")
        except Exception as e:
            st.error(f"❌ Dosya okunurken bir hata oluştu: {e}")

# --- 2. KDV ANALİZ ROBOTU ---
elif secim == "2. KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz Üssü (Pro Okuyucu)")
    
    if st.session_state.get('mukellef_db') is None:
        st.warning("⚠️ Lütfen analizden önce '1. Excel Listesi Yükle' menüsünden mükellef listenizi yükleyin.")
        st.stop()
        
    pdf_files = st.file_uploader("Bir veya daha fazla KDV Beyannamesi PDF'i yükleyin", type=["pdf"], accept_multiple_files=True)
    
    if pdf_files and st.button("🚀 ANALİZİ BAŞLAT", type="primary", use_container_width=True):
        terminal = st.empty()
        logs = []
        def log_yaz(t, color="#00ff41"): # Yeşil renk varsayılan
            logs.append(f"<span style='color:{color};'> > {t}</span>")
            if len(logs) > 10: logs.pop(0)
            terminal.markdown(f"<div class='terminal-window'>{'<br>'.join(logs)}</div>", unsafe_allow_html=True)
            time.sleep(0.05)
        
        log_yaz("Sistem başlatıldı. PDF'ler okunuyor...", "white")
        
        sonuclar = []
        progress_bar = st.progress(0, text="Analiz ilerlemesi...")

        for idx, pdf_file in enumerate(pdf_files):
            try:
                with pdfplumber.open(pdf_file) as pdf:
                    full_text = ""
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            full_text += page_text + "\n"
                    
                    if "KATMA DEĞER VERGİSİ" in full_text or "MATRAH" in full_text:
                        vkn = vkn_bul(full_text)
                        isim = isim_eslestir_excel(vkn)
                        log_yaz(f"Okunuyor: {isim[:25]}...", "#00BFFF") # Mavi renk

                        matrah = veri_cozucu_pro(full_text, MATRAH_ANAHTAR_KELIMELER)
                        kdv = veri_cozucu_pro(full_text, KDV_ANAHTAR_KELIMELER)
                        pos = veri_cozucu_pro(full_text, POS_ANAHTAR_KELIMELER)
                        
                        beyan_toplami = matrah + kdv
                        fark = pos - beyan_toplami
                        durum = "RISKLI" if fark > 50 else "TEMIZ"
                        
                        if durum == "RISKLI":
                            log_yaz(f"UYARI: {isim[:15]}.. Fark: {para_formatla(fark)}", "#FF4500") # Kırmızı/Turuncu
                        
                        sonuclar.append({
                            "Mükellef": isim, "VKN": vkn or "Bulunamadı", "POS": pos,
                            "Beyan": beyan_toplami, "Fark": fark, "Durum": durum
                        })
            except Exception as e:
                log_yaz(f"HATA: {pdf_file.name} dosyası işlenemedi. Hata: {e}", "red")
            
            progress_bar.progress((idx + 1) / len(pdf_files), text=f"{pdf_file.name} analiz edildi.")

        st.session_state['sonuclar'] = pd.DataFrame(sonuclar) if sonuclar else pd.DataFrame()
        log_yaz("Analiz tamamlandı.", "white")
        time.sleep(1)
        terminal.empty()
        progress_bar.empty()

    # --- SONUÇLARI GÖSTERME ---
    if st.session_state.get('sonuclar') is not None:
        df_sonuc = st.session_state['sonuclar']
        if df_sonuc.empty:
            st.info("Yüklenen PDF'lerden analiz edilecek veri bulunamadı.")
        else:
            riskliler = df_sonuc[df_sonuc['Durum'] == "RISKLI"]
            temizler = df_sonuc[df_sonuc['Durum'] == "TEMIZ"]
            
            st.download_button(
                label="📊 Sonuçları Excel Olarak İndir",
                data=df_sonuc.to_csv(index=False).encode('utf-8-sig'),
                file_name='kdv_analiz_sonuclari.csv',
                mime='text/csv',
            )

            tab1, tab2 = st.tabs([f"🚨 RİSKLİ MÜKELLEFLER ({len(riskliler)})", f"✅ UYUMLU MÜKELLEFLER ({len(temizler)})"])
            
            with tab1:
                if riskliler.empty:
                    st.success("🎉 Harika! Riskli bulunan mükellef yok.")
                else:
                    for i, row in riskliler.iterrows():
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.markdown(f"""
                            <div class='card risk-card'>
                                <div class='card-title'>{row['Mükellef']}</div>
                                <div class='card-sub'>VKN/TCKN: {row['VKN']}</div>
                                <div style='display:flex; gap:15px; margin-top:10px'>
                                    <div><span class='stat-lbl'>POS SATIŞI</span><br><span class='stat-val'>{para_formatla(row['POS'])}</span></div>
                                    <div><span class='stat-lbl'>KDV BEYANI</span><br><span class='stat-val'>{para_formatla(row['Beyan'])}</span></div>
                                </div>
                                <div style='color:#d32f2f; font-weight:bold; margin-top:10px; font-size:16px;'>FARK: {para_formatla(row['Fark'])}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        with col2:
                            st.write("") # Boşluk
                            st.write("") # Boşluk
                            if st.button("🚨 İHBAR ET", key=f"risk_{i}", type="primary", use_container_width=True):
                                mesaj = f"⚠️ *KDV RİSK UYARISI*\n\n*Firma:* {row['Mükellef']}\n*POS Satışları:* {para_formatla(row['POS'])}\n*KDV Beyanı Toplamı:* {para_formatla(row['Beyan'])}\n*Negatif Fark:* {para_formatla(row['Fark'])}"
                                if whatsapp_gonder("SABIT", mesaj):
                                    st.toast(f"✅ {row['Mükellef']} için ihbar gönderildi!")
            
            with tab2:
                if temizler.empty:
                    st.info("Uyumlu mükellef bulunamadı.")
                else:
                    for i, row in temizler.iterrows():
                        st.markdown(f"""
                        <div class='card clean-card'>
                            <div style='display:flex; justify-content:space-between; align-items:center;'>
                                <div class='card-title' style='margin:0;'>{row['Mükellef']}</div>
                                <div style='display:flex; gap:20px; font-size:14px;'>
                                    <span>POS: <b>{para_formatla(row['POS'])}</b></span>
                                    <span>Beyan: <b>{para_formatla(row['Beyan'])}</b></span>
                                </div>
                                <div style='color:#28a745; font-weight:bold;'>✓ UYUMLU</div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

# --- 3. PROFESYONEL MESAJ ---
elif secim == "3. Profesyonel Mesaj":
    st.title("📤 Tekli Mesaj Gönderimi")
    if st.session_state.get('mukellef_db') is not None:
        df_mukellef = st.session_state['mukellef_db']
        secilen_kisi = st.selectbox("Mesaj gönderilecek mükellefi seçin:", df_mukellef['A_UNVAN'])
        
        if secilen_kisi:
            kisi_bilgileri = df_mukellef[df_mukellef['A_UNVAN'] == secilen_kisi].iloc[0]
            tel_no = kisi_bilgileri.get('D_TEL', "")
            
            st.text_input("Telefon Numarası:", value=tel_no, disabled=True)
            mesaj_sablonu = st.selectbox("Hazır Mesaj Şablonu Seç:", ["", "Vergi Ödemesi Hatırlatması", "Belge Talebi", "Genel Duyuru"])
            
            mesaj_metni = ""
            if mesaj_sablonu == "Vergi Ödemesi Hatırlatması":
                mesaj_metni = f"Sayın {secilen_kisi}, yaklaşan vergi ödemeniz hakkında hatırlatma yapmak istedik. Detaylı bilgi için ofisimizle iletişime geçebilirsiniz. İyi çalışmalar dileriz."
            elif mesaj_sablonu == "Belge Talebi":
                mesaj_metni = f"Sayın {secilen_kisi}, muhasebe kayıtları için gerekli olan bazı belgeleriniz eksiktir. Lütfen en kısa sürede ofisimize ulaştırınız. İyi çalışmalar dileriz."
            
            txt_area = st.text_area("Gönderilecek Mesaj:", value=mesaj_metni, height=150)
            
            if st.button("📲 WhatsApp ile Gönder", type="primary"):
                if tel_no and txt_area:
                    if whatsapp_gonder(tel_no, txt_area):
                        st.success("✅ Mesaj başarıyla gönderildi!")
                    # Hata mesajı whatsapp_gonder fonksiyonu içinde zaten gösteriliyor.
                else:
                    st.warning("⚠️ Telefon numarası veya mesaj metni boş olamaz.")
    else:
        st.warning("⚠️ Lütfen önce mükellef listenizi yükleyin.")

# --- 4. TASDİK ROBOTU ---
elif secim == "4. Tasdik Robotu":
    st.title("🤖 Yüklenen Mükellef Listesi")
    if st.session_state.get('mukellef_db') is not None:
        st.info(f"Sistemde kayıtlı {len(st.session_state['mukellef_db'])} mükellef bulunmaktadır.")
        st.dataframe(st.session_state['mukellef_db'])
    else:
        st.warning("⚠️ Görüntülenecek bir liste yok. Lütfen önce '1. Excel Listesi Yükle' menüsünden listenizi yükleyin.")
