import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import pandas as pd
import re
from datetime import datetime
import time
import pdfplumber
import io

# ==========================================
# 1. AYARLAR VE CSS (GÖRSEL TASARIM)
# ==========================================
st.set_page_config(
    page_title="Müşavir İletişim Kulesi",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Bilgileri
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"  # İhbarların gideceği sabit numara

# CSS
st.markdown("""
    <style>
    .stApp {background-color: #F2F6FC; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;}
    [data-testid="stSidebar"] {background-color: #FFFFFF; border-right: 1px solid #E0E0E0;}
    
    /* Risk Kartları (KDV) */
    .risk-karti {
        background-color: #ffffff; padding: 15px; border-radius: 12px; 
        border-left: 6px solid #d32f2f; margin-bottom: 15px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    .temiz-karti {
        background-color: #e8f5e9; padding: 10px; border-radius: 12px; 
        border-left: 6px solid #2ecc71; margin-bottom: 5px; opacity: 0.8;
    }
    
    /* WhatsApp Balonu */
    .chat-container {background-color: #e5ddd5; padding: 20px; border-radius: 15px; border: 1px solid #d1d7db; min-height: 250px;}
    .message-bubble {background-color: #dcf8c6; padding: 10px 15px; border-radius: 8px; box-shadow: 0 1px 1px rgba(0,0,0,0.1); max-width: 80%; margin-bottom: 10px; position: relative; float: right; clear: both; color: #303030;}
    
    /* Terminal */
    .terminal-window {
        background-color: #1e1e1e; color: #00ff00; font-family: 'Courier New', Courier, monospace;
        padding: 15px; border-radius: 10px; font-size: 14px; height: 200px; overflow-y: auto;
        border: 2px solid #333;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SESSION STATE ---
if 'analiz_sonuclari' not in st.session_state: st.session_state['analiz_sonuclari'] = None
if 'analiz_log' not in st.session_state: st.session_state['analiz_log'] = ""
if 'tasdik_data' not in st.session_state: st.session_state['tasdik_data'] = None

# --- MESAJ ŞABLONLARI ---
MESAJ_SABLONLARI = {
    "Serbest Metin": "",
    "KDV Tahakkuk": "Sayın {isim}, {ay} dönemi KDV beyannameniz onaylanmıştır. Tahakkuk fişiniz ektedir. Ödemenizi vadesinde yapmanızı rica ederiz.",
    "Tasdik Ödenmedi (RESMİ UYARI)": "Sayın Mükellefimiz {isim}, Defter Tasdik ve Yazılım Giderleri ücretiniz ({tutar} TL) ödenmediği için defterleriniz notere teslim EDİLMEMİŞTİR. Mağduriyet yaşamamanız için ödemenizi bekliyoruz.",
}

# ==========================================
# 2. YARDIMCI FONKSİYONLAR
# ==========================================
def whatsapp_text_gonder(chat_id, mesaj):
    chat_id = str(chat_id).replace(" ", "").replace("+", "")
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        response = requests.post(url, json={'chatId': chat_id, 'message': mesaj})
        return response.status_code == 200
    except: return False

def whatsapp_dosya_gonder(chat_id, dosya, dosya_adi, mesaj=""):
    chat_id = str(chat_id).replace(" ", "").replace("+", "")
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendFileByUpload/{API_TOKEN}"
    try:
        files = {'file': (dosya_adi, dosya.getvalue())}
        data = {'chatId': chat_id, 'fileName': dosya_adi, 'caption': mesaj}
        response = requests.post(url, files=files, data=data)
        return response.status_code == 200
    except: return False

def text_to_float(text):
    try:
        clean = re.sub(r'[^\d,\.]', '', str(text)).strip()
        if "," in clean and "." in clean: clean = clean.replace(".", "").replace(",", ".")
        elif "," in clean: clean = clean.replace(",", ".")
        return float(clean)
    except: return 0.0

def para_formatla(deger):
    return "{:,.2f} TL".format(deger).replace(",", "X").replace(".", ",").replace("X", ".")

def numaralari_ayikla(tel_str):
    if not tel_str: return []
    tel_str = str(tel_str)
    if tel_str == "nan": return []
    ham = re.split(r'[,\n/]', tel_str)
    temiz = []
    for p in ham:
        sadece_rakam = re.sub(r'\D', '', p)
        if len(sadece_rakam) == 10: temiz.append("90" + sadece_rakam)
        elif len(sadece_rakam) == 11 and sadece_rakam.startswith("0"): temiz.append("9" + sadece_rakam)
    return temiz

# ==========================================
# 3. MENÜ VE SAYFALAR
# ==========================================

# Yan Menü (Sidebar)
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=70)
    st.title("Müşavir Kulesi")
    secim = st.radio("MENÜ", ["KDV Analiz Robotu", "Profesyonel Mesaj", "Tasdik Robotu", "Veri Yükle"])

# --- SAYFA 1: VERİ YÜKLEME ---
if secim == "Veri Yükle":
    st.title("📂 Müşteri Veritabanı")
    st.info("Müşteri listesini (Excel) buradan yükleyiniz.")
    
    up = st.file_uploader("Müşteri Listesi (Excel)", type=["xlsx", "xls"])
    if up:
        try:
            df = pd.read_excel(up)
            # Veri temizliği
            if "Para Alındı mı" in df.columns: 
                df["Tahsil_Edildi"] = df["Para Alındı mı"].apply(lambda x: True if pd.notna(x) and str(x).strip() != "" else False)
            else: df["Tahsil_Edildi"] = False
            
            st.session_state['tasdik_data'] = df
            st.success(f"✅ {len(df)} Müşteri Kaydı Yüklendi.")
            st.dataframe(df.head())
        except Exception as e: st.error(f"Hata: {e}")

# --- SAYFA 2: KDV ANALİZ ROBOTU (GÜNCELLENMİŞ MANTIK) ---
elif secim == "KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz & İhbar Robotu")
    st.markdown("**Formül:** (Matrah + Hesaplanan KDV) ile (Kredi Kartı Tahsilatı) karşılaştırılır.")
    
    pdf_up = st.file_uploader("KDV Beyannamesi (PDF)", type=["pdf"])
    
    if pdf_up:
        if st.button("🚀 ANALİZİ BAŞLAT", type="primary"):
            progress_bar = st.progress(0)
            status = st.empty()
            terminal_logs = []
            sonuclar = []
            
            with pdfplumber.open(pdf_up) as pdf:
                total = len(pdf.pages)
                for i, page in enumerate(pdf.pages):
                    progress_bar.progress((i+1)/total)
                    text = page.extract_text()
                    if not text: continue
                    
                    # 1. İsim Bulma (Müşavir Hariç)
                    lines = text.split('\n')
                    musteri_adi = "Bilinmeyen"
                    # Sayfanın üst kısmında ara
                    limit = len(lines)
                    for idx, line in enumerate(lines):
                        if "BEYANNAMEYİ DÜZENLEYEN" in line: limit = idx; break
                    
                    for idx, line in enumerate(lines[:limit]):
                        if "Soyadı (Unvanı)" in line or "Unvanı" in line:
                            if idx + 1 < limit:
                                candidate = lines[idx+1].strip()
                                if "SMMM" not in candidate and "MÜŞAVİR" not in candidate:
                                    musteri_adi = candidate
                                    break
                    
                    # 2. Veriler
                    matrah_match = re.search(r"(?:TOPLAM MATRAH|Teslim ve Hizmetlerin Karşılığını).*?([\d\.,]+)", text, re.IGNORECASE)
                    matrah = text_to_float(matrah_match.group(1)) if matrah_match else 0.0
                    
                    kdv_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
                    hesaplanan_kdv = text_to_float(kdv_match.group(1)) if kdv_match else 0.0
                    
                    kk_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
                    kk_tutar = text_to_float(kk_match.group(1)) if kk_match else 0.0
                    
                    # 3. YENİ FORMÜL (Özel Matrah Yok)
                    beyan_toplam = matrah + hesaplanan_kdv
                    fark = kk_tutar - beyan_toplam
                    
                    durum = "RİSKLİ" if fark > 50 else "TEMİZ"
                    
                    if durum == "RİSKLİ":
                        sonuclar.append({
                            "Mükellef": musteri_adi, "Matrah": matrah, "KDV": hesaplanan_kdv,
                            "Beyan_Toplam": beyan_toplam, "KK_Tutar": kk_tutar, "Fark": fark
                        })
            
            st.session_state['analiz_sonuclari'] = pd.DataFrame(sonuclar)
            status.success("✅ Analiz Bitti!")
            time.sleep(0.5)
            st.rerun()

    # SONUÇ EKRANI
    if st.session_state['analiz_sonuclari'] is not None:
        df_res = st.session_state['analiz_sonuclari']
        
        if df_res.empty:
            st.success("Taranan dosyalarda riskli durum yok.")
        else:
            st.error(f"🚨 {len(df_res)} Riskli Beyanname Tespit Edildi")
            
            for i, row in df_res.iterrows():
                ad = row['Mükellef']
                kk = para_formatla(row['KK_Tutar'])
                beyan = para_formatla(row['Beyan_Toplam'])
                fark = para_formatla(row['Fark'])
                
                with st.container():
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.markdown(f"""
                        <div class='risk-karti'>
                            <h4 style='margin:0; color:#c62828'>🚨 {ad}</h4>
                            <p style='margin:5px 0 0 0; color:#555'>
                                <b>POS:</b> {kk} | <b>Beyan (KDV Dahil):</b> {beyan}
                            </p>
                            <p style='margin-top:5px; font-weight:bold; color:#d32f2f'>EKSİK BEYAN FARKI: {fark}</p>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with c2:
                        st.write("")
                        st.write("")
                        # Sadece SABİT NUMARA İHBAR
                        if st.button(f"🚨 İHBAR ET", key=f"btn_{i}", type="primary", use_container_width=True):
                            msg = (f"⚠️ *KDV UYUMSUZLUK RAPORU*\n\n"
                                   f"Firma: {ad}\nPOS: {kk}\nBeyan: {beyan}\n"
                                   f"Fark: {fark}\n\nKontrol ediniz.")
                            
                            ok = whatsapp_text_gonder(SABIT_IHBAR_NO, msg)
                            if ok: st.toast("İhbar İletildi! ✅")
                            else: st.error("API Hatası!")

# --- SAYFA 3: PROFESYONEL MESAJ ---
elif secim == "Profesyonel Mesaj":
    st.title("📤 Mesaj Merkezi")
    
    if st.session_state['tasdik_data'] is None:
        st.warning("Lütfen önce veri yükleyiniz.")
    else:
        df_m = st.session_state['tasdik_data']
        col1, col2 = st.columns([1,1])
        
        with col1:
            tur = st.radio("Gönderim Türü", ["Tek Kişi", "Toplu Gönderim"], horizontal=True)
            if tur == "Tek Kişi":
                secilen = [st.selectbox("Müşteri Seç", df_m["Ünvan / Ad Soyad"].unique())]
            else:
                secilen = df_m["Ünvan / Ad Soyad"].tolist()
            
            sablon = st.selectbox("Şablon", list(MESAJ_SABLONLARI.keys()))
            icerik = st.text_area("Mesaj", value=MESAJ_SABLONLARI[sablon], height=150)
            
            dosya_ekle = st.toggle("Dosya Ekle")
            up_f = st.file_uploader("Dosya", type=["pdf","jpg","png"]) if dosya_ekle else None

        with col2:
            st.subheader("Önizleme")
            orn_isim = secilen[0] if secilen else "İsim"
            final_msg = icerik.replace("{isim}", str(orn_isim)).replace("{ay}", "Cari Ay")
            
            st.markdown(f"""<div class='chat-container'><div class='message-bubble'>{final_msg}</div></div>""", unsafe_allow_html=True)
            
            if st.button("GÖNDER", type="primary"):
                bar = st.progress(0)
                for idx, m in enumerate(secilen):
                    row = df_m[df_m["Ünvan / Ad Soyad"]==m].iloc[0]
                    tel = row.get("1.NUMARA", "")
                    msg_real = icerik.replace("{isim}", str(m)).replace("{ay}", datetime.now().strftime("%B"))
                    
                    for t in numaralari_ayikla(tel):
                        if up_f: 
                            up_f.seek(0)
                            whatsapp_dosya_gonder(t, up_f, up_f.name, msg_real)
                        else: 
                            whatsapp_text_gonder(t, msg_real)
                    bar.progress((idx+1)/len(secilen))
                st.success("Gönderim Tamamlandı.")

# --- SAYFA 4: TASDİK ROBOTU ---
elif secim == "Tasdik Robotu":
    st.title("🤖 Tasdik Takip")
    
    if st.session_state['tasdik_data'] is None:
        st.warning("Veri yükleyiniz.")
    else:
        df = st.session_state['tasdik_data']
        borclular = df[df["Tahsil_Edildi"]==False]
        
        c1, c2 = st.columns(2)
        c1.metric("Ödemeyen", len(borclular))
        c2.metric("Tahsil Edilen", len(df)-len(borclular))
        
        st.subheader("Ödeme İşle / Uyarı Gönder")
        
        for i, row in borclular.iterrows():
            with st.expander(f"🔴 {row['Ünvan / Ad Soyad']} - {row.get('Defter Tasdik Ücreti', 0)} TL"):
                c_a, c_b = st.columns(2)
                if c_a.button("ÖDENDİ İŞARETLE", key=f"ode_{i}"):
                    st.session_state['tasdik_data'].at[i, "Tahsil_Edildi"] = True
                    st.rerun()
                
                if c_b.button("UYARI AT", key=f"uyr_{i}"):
                    msg = MESAJ_SABLONLARI["Tasdik Ödenmedi (RESMİ UYARI)"].format(
                        isim=row['Ünvan / Ad Soyad'], tutar=row.get('Defter Tasdik Ücreti',0)
                    )
                    tel = row.get("1.NUMARA", "")
                    for t in numaralari_ayikla(tel): whatsapp_text_gonder(t, msg)
                    st.toast("Uyarı Gitti")

