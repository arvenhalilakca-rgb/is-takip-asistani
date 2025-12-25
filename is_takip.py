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
    page_title="Müşavir Kulesi (Canlı Akış & Akıllı Okuyucu)",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Ayarları
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

# Aranacak anahtar ifadeler
MATRAH_IFADESI = "Teslim ve Hizmetlerin Karşılığını Teşkil Eden Bedel"
HESAPLANAN_KDV_IFADESI = "Hesaplanan Katma Değer Vergisi"
POS_ANAHTAR_KELIMESI = "Kredi Kartı"

BEYANNAME_AYRACI = "KATMA DEĞER VERGİSİ BEYANNAMESİ"

# CSS Stilleri
st.markdown("""
    <style>
    .stApp {background-color: #f4f6f9; font-family: 'Segoe UI', sans-serif;}
    [data-testid="stSidebar"] {background-color: #fff; border-right: 1px solid #ddd;}
    .card { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 10px; border: 1px solid #eee; }
    .risk-card {border-left: 5px solid #d32f2f;}
    .stat-val {font-weight: bold; font-size: 15px; color: #333;}
    .stat-lbl {font-size: 11px; color: #777;}
    .card-title {font-size: 16px; font-weight: bold; margin-bottom: 5px;}
    .card-sub {font-size: 12px; color: #666; margin-bottom: 10px;}
    /* YENİ: Canlı Akış Terminali için stil */
    .terminal-window {
        background-color: #1e1e1e; color: #f0f0f0; font-family: monospace;
        padding: 15px; border-radius: 8px; height: 300px; overflow-y: auto;
        font-size: 13px; margin-bottom: 20px; border: 1px solid #333;
        line-height: 1.6;
    }
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
    if not numara or not ID_INSTANCE or not API_TOKEN:
        st.error("API bilgileri veya telefon numarası eksik!")
        return False
    target = f"{SABIT_IHBAR_NO}@c.us" if numara == "SABIT" else f"{numara}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        requests.post(url, json={'chatId': target, 'message': mesaj}, timeout=10).raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        st.error(f"WhatsApp gönderme hatası: {e}")
        return False

def vkn_bul(text):
    patterns = [r'"(\d{10,11})"', r'(?:Vergi Kimlik|TC Kimlik|Vergi No|VKN|TCKN)[\s:]*(\d{10,11})', r'\b(\d{10,11})\b']
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match: return match.group(1)
    return None

def isim_eslestir_excel(numara):
    if st.session_state.get('mukellef_db') is None: return f"Bilinmeyen ({numara or 'Bulunamadı'})"
    if not numara: return "VKN/TCKN PDF'te Bulunamadı"
    df = st.session_state['mukellef_db']
    numara_str = str(numara).strip()
    res_vkn = df[df['C_VKN'] == numara_str]
    if not res_vkn.empty: return res_vkn.iloc[0]['A_UNVAN']
    res_tc = df[df['B_TC'] == numara_str]
    if not res_tc.empty: return res_tc.iloc[0]['A_UNVAN']
    return f"Listede Yok ({numara_str})"

def veri_bul(text, anahtar_ifade):
    try:
        pattern = re.escape(anahtar_ifade) + r'[\s\S]*?([\d\.,]{3,})'
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match: return text_to_float(match.group(1))
    except Exception: return 0.0
    return 0.0

# ==========================================
# 3. ARAYÜZ & ANA UYGULAMA AKIŞI
# ==========================================

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.header("MÜŞAVİR PANELİ")
    # ORİJİNAL MENÜ YAPINIZ KORUNDU
    secim = st.radio("MENÜ", ["1. Excel Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"])

if secim == "1. Excel Listesi Yükle":
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

elif secim == "2. KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz Üssü (Canlı Akış & Akıllı Okuyucu)")
    
    if st.session_state.get('mukellef_db') is None:
        st.warning("⚠️ Lütfen önce '1. Excel Listesi Yükle' menüsünden listenizi yükleyin.")
        st.stop()
    
    pdf_files = st.file_uploader("İçinde bir veya yüzlerce beyanname olan PDF dosyasını yükleyin", type=["pdf"], accept_multiple_files=True)
    
    if pdf_files and st.button("🚀 TÜM BEYANNAMELERİ ANALİZ ET", type="primary", use_container_width=True):
        sonuclar = []
        toplam_bulunan_beyanname = 0
        
        # YENİ: Canlı Akış için Terminal Ekranı
        st.subheader("Canlı Analiz Akışı")
        terminal = st.empty()
        logs = []

        for pdf_idx, pdf_file in enumerate(pdf_files):
            try:
                full_text = ""
                with pdfplumber.open(pdf_file) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text(x_tolerance=1)
                        if page_text: full_text += page_text + "\n"
                
                beyanname_bloklari = re.split(f'({re.escape(BEYANNAME_AYRACI)})', full_text, flags=re.IGNORECASE)
                processed_blocks = [beyanname_bloklari[i] + beyanname_bloklari[i+1] for i in range(1, len(beyanname_bloklari)-1, 2)] if len(beyanname_bloklari) > 1 else beyanname_bloklari

                for beyanname_text in processed_blocks:
                    if not beyanname_text.strip() or len(beyanname_text) < 100: continue
                    toplam_bulunan_beyanname += 1
                    
                    # --- "BÖL VE FETHET" MANTIĞI ---
                    try:
                        # Metni "Kredi Kartı" ifadesinden ikiye böl
                        bolumler = re.split(f'({re.escape(POS_ANAHTAR_KELIMESI)})', beyanname_text, maxsplit=1, flags=re.IGNORECASE)
                        ust_kisim = bolumler[0]
                        alt_kisim = bolumler[1] + bolumler[2] if len(bolumler) > 2 else ""
                    except Exception:
                        # Eğer "Kredi Kartı" bulunamazsa, tüm metni üst kısım say
                        ust_kisim = beyanname_text
                        alt_kisim = ""

                    vkn = vkn_bul(ust_kisim) # VKN genellikle üstte olur
                    isim = isim_eslestir_excel(vkn)
                    
                    # Değerleri kendi bölgelerinde ara
                    matrah = veri_bul(ust_kisim, MATRAH_IFADESI)
                    hesaplanan_kdv = veri_bul(ust_kisim, HESAPLANAN_KDV_IFADESI)
                    pos_satis = veri_bul(alt_kisim, POS_ANAHTAR_KELIMESI) if alt_kisim else 0.0
                    
                    beyan_toplami = matrah + hesaplanan_kdv
                    fark = pos_satis - beyan_toplami
                    
                    if pos_satis > 0 and beyan_toplami == 0: durum = "OKUNAMADI"
                    elif fark > 50: durum = "RISKLI"
                    else: durum = "TEMIZ"
                    
                    # YENİ: Canlı Akış için log oluşturma
                    log_mesaji = f" > Mükellef: {isim[:20]:<20} | Matrah: {para_formatla(matrah):>15} | KDV: {para_formatla(hesaplanan_kdv):>15} | POS: {para_formatla(pos_satis):>15} | Durum: {durum}"
                    renk = "#d32f2f" if durum == "RISKLI" else "#ffc107" if durum == "OKUNAMADI" else "#28a745"
                    logs.append(f"<span style='color:{renk};'>{log_mesaji}</span>")
                    terminal.markdown(f"<div class='terminal-window'>{'<br>'.join(logs)}</div>", unsafe_allow_html=True)
                    time.sleep(0.1) # Akışın gözle takip edilebilmesi için küçük bir bekleme

                    sonuclar.append({"Mükellef": isim, "VKN": vkn or "Bulunamadı", "POS": pos_satis, "Beyan": beyan_toplami, "Fark": fark, "Durum": durum})

            except Exception as e: st.error(f"'{pdf_file.name}' işlenirken hata: {e}")

        st.success(f"Analiz tamamlandı! Toplam **{toplam_bulunan_beyanname}** beyanname incelendi.")
        if sonuclar: st.session_state['sonuclar'] = pd.DataFrame(sonuclar)

    if st.session_state.get('sonuclar') is not None:
        # ... Sonuç gösterme ve İhbar Et butonları önceki gibi çalışacak ...
        df_sonuc = st.session_state['sonuclar']
        if not df_sonuc.empty:
            riskliler = df_sonuc[df_sonuc['Durum'] == "RISKLI"]
            temizler = df_sonuc[df_sonuc['Durum'] == "TEMIZ"]
            okunamayanlar = df_sonuc[df_sonuc['Durum'] == "OKUNAMADI"]

            st.subheader("Analiz Sonuçları")
            tab1, tab2, tab3 = st.tabs([f"🚨 RİSKLİ ({len(riskliler)})", f"✅ UYUMLU ({len(temizler)})", f"❓ OKUNAMAYAN ({len(okunamayanlar)})"])
            
            with tab1:
                if not riskliler.empty:
                    st.error(f"Aşağıdaki {len(riskliler)} mükellefin POS satışı, KDV beyanından yüksek.")
                    for i, row in riskliler.iterrows():
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.markdown(f"""<div class='card risk-card'><div class='card-title'>{row['Mükellef']}</div><div class='card-sub'>VKN/TCKN: {row['VKN']}</div><div style='display:flex; gap:15px; margin-top:10px'><div><span class='stat-lbl'>POS SATIŞI</span><br><span class='stat-val'>{para_formatla(row['POS'])}</span></div><div><span class='stat-lbl'>KDV BEYANI</span><br><span class='stat-val'>{para_formatla(row['Beyan'])}</span></div></div><div style='color:#d32f2f; font-weight:bold; margin-top:10px; font-size:16px;'>FARK: {para_formatla(row['Fark'])}</div></div>""", unsafe_allow_html=True)
                        with col2:
                            st.write(""); st.write("")
                            if st.button("🚨 İHBAR ET", key=f"ihbar_{i}", type="primary", use_container_width=True):
                                mesaj = f"⚠️ *KDV RİSK UYARISI*\n\n*Firma:* {row['Mükellef']}\n*POS Satışları:* {para_formatla(row['POS'])}\n*KDV Beyanı Toplamı:* {para_formatla(row['Beyan'])}\n*Negatif Fark:* {para_formatla(row['Fark'])}"
                                if whatsapp_gonder("SABIT", mesaj): st.toast(f"✅ {row['Mükellef']} için ihbar gönderildi!")
                else: st.success("🎉 Riskli bulunan mükellef yok.")
            
            with tab2: st.dataframe(temizler)
            with tab3: st.dataframe(okunamayanlar)

# ORİJİNAL MENÜLERİNİZ OLDUĞU GİBİ ÇALIŞIYOR
elif secim == "3. Profesyonel Mesaj":
    st.title("📤 Profesyonel Mesaj Gönderimi")
    if st.session_state.get('mukellef_db') is not None:
        df = st.session_state['mukellef_db']
        kisi = st.selectbox("Kişi", df['A_UNVAN'])
        tel = df[df['A_UNVAN']==kisi].iloc[0].get('D_TEL', "")
        st.write(f"Telefon Numarası: {tel}")
        txt = st.text_area("Mesajınız:")
        if st.button("Gönder"):
            if whatsapp_gonder(tel, txt): st.success("Mesaj gönderildi!")
            else: st.error("Mesaj gönderilemedi.")
    else: st.warning("Lütfen önce '1. Excel Listesi Yükle' menüsünden mükellef listenizi yükleyin.")

elif secim == "4. Tasdik Robotu":
    st.title("🤖 Yüklenen Mükellef Listesi (Tasdik)")
    if st.session_state.get('mukellef_db') is not None:
        st.info(f"Sistemde kayıtlı {len(st.session_state['mukellef_db'])} mükellef bulunmaktadır.")
        st.dataframe(st.session_state['mukellef_db'])
    else:
        st.warning("Görüntülenecek bir liste yok. Lütfen önce '1. Excel Listesi Yükle' menüsünden listenizi yükleyin.")
