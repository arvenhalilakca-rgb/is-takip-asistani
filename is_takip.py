import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import pandas as pd
import re
from datetime import datetime
import time
from streamlit_option_menu import option_menu
import pdfplumber
import io

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir İletişim Kulesi",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TASARIM (CSS - MODERN & GÖRSEL) ---
st.markdown("""
    <style>
    .stApp {background-color: #F2F6FC; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;}
    [data-testid="stSidebar"] {background-color: #FFFFFF; border-right: 1px solid #E0E0E0;}
    
    /* WhatsApp Balonu */
    .chat-container {background-color: #e5ddd5; padding: 20px; border-radius: 15px; border: 1px solid #d1d7db; min-height: 250px;}
    .message-bubble {background-color: #dcf8c6; padding: 10px 15px; border-radius: 8px; box-shadow: 0 1px 1px rgba(0,0,0,0.1); max-width: 80%; margin-bottom: 10px; position: relative; float: right; clear: both; color: #303030;}
    
    /* Terminal Görünümü (Canlı Tarama İçin) */
    .terminal-window {
        background-color: #1e1e1e; color: #00ff00; font-family: 'Courier New', Courier, monospace;
        padding: 15px; border-radius: 10px; font-size: 14px; height: 200px; overflow-y: auto;
        border: 2px solid #333; box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    
    /* Risk Kartları */
    .risk-karti {
        background-color: #ffffff; padding: 15px; border-radius: 12px; 
        border-left: 6px solid #ff4d4d; margin-bottom: 15px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05); transition: transform 0.2s;
    }
    .risk-karti:hover {transform: translateY(-2px); box-shadow: 0 6px 15px rgba(0,0,0,0.1);}
    
    .temiz-karti {
        background-color: #ffffff; padding: 15px; border-radius: 12px; 
        border-left: 6px solid #2ecc71; margin-bottom: 10px; opacity: 0.7;
    }
    
    /* Butonlar */
    .stButton>button {border-radius: 10px; font-weight: bold; border: none; height: 45px; width: 100%; transition: 0.3s;}
    button[kind="primary"] {background: linear-gradient(45deg, #128C7E, #075E54); color: white;}
    button[kind="secondary"] {background: white; border: 1px solid #ddd; color: #333;}
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
MESAJ_SABLONLARI = {
    "Serbest Metin": "",
    "KDV Hata Uyarısı (Personele)": "Sayın {personel}, {musteri} firmasının KDV beyannamesinde Kredi Kartı Satışları ile Beyan Edilen Matrah arasında uyumsuzluk tespit edilmiştir.\n\nKredi Kartı: {kk_tutar} TL\nBeyan Edilen (KDV Dahil): {beyan_tutar} TL\nFark: {fark} TL\n\nOfis olarak yaptığımız incelemede hata olduğunu düşünüyoruz. Konunun ivedilikle incelenip tarafımıza raporlanmasını rica ederim.",
    "KDV Tahakkuk": "Sayın {isim}, {ay} dönemi KDV beyannameniz onaylanmıştır. Tahakkuk fişiniz ektedir. Ödemenizi vadesinde yapmanızı rica ederiz.",
    "Tasdik Ödenmedi (RESMİ UYARI)": "Sayın Mükellefimiz {isim}, 2026 yılı Defter Tasdik ve Yazılım Giderleri ücretiniz ({tutar} TL) ödenmediği için defterleriniz notere teslim EDİLMEMİŞTİR. Bugün SON GÜN. Mağduriyet yaşamamanız için ödemenizi bekliyoruz.",
}

# --- SESSION ---
if 'analiz_sonuclari' not in st.session_state: st.session_state['analiz_sonuclari'] = None
if 'analiz_log' not in st.session_state: st.session_state['analiz_log'] = ""
if 'tasdik_data' not in st.session_state: st.session_state['tasdik_data'] = None

# --- BAĞLANTILAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]; API_TOKEN = st.secrets["API_TOKEN"]
    try: creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    except: creds = None
except: st.error("⚠️ Ayar Hatası: Secrets eksik."); st.stop()

# --- FONKSİYONLAR ---
def whatsapp_text_gonder(chat_id, mesaj):
    chat_id = str(chat_id).replace(" ", "").replace("+", "")
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        response = requests.post(url, json={'chatId': chat_id, 'message': mesaj})
        return response.status_code == 200, response.text
    except Exception as e: return False, str(e)

def whatsapp_dosya_gonder(chat_id, dosya, dosya_adi, mesaj=""):
    chat_id = str(chat_id).replace(" ", "").replace("+", "")
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendFileByUpload/{API_TOKEN}"
    try:
        files = {'file': (dosya_adi, dosya.getvalue())}
        data = {'chatId': chat_id, 'fileName': dosya_adi, 'caption': mesaj}
        response = requests.post(url, files=files, data=data)
        return response.status_code == 200, response.text
    except Exception as e: return False, str(e)

def numaralari_ayikla(tel_str):
    if not tel_str: return []
    tel_str = str(tel_str)
    if tel_str == "nan" or tel_str == "None": return []
    ham_parcalar = re.split(r'[,\n/]', tel_str)
    temiz = []
    for parca in ham_parcalar:
        sadece_rakam = re.sub(r'\D', '', parca)
        if len(sadece_rakam) == 10: temiz.append("90" + sadece_rakam)
        elif len(sadece_rakam) == 11 and sadece_rakam.startswith("0"): temiz.append("9" + sadece_rakam)
        elif len(sadece_rakam) == 12 and sadece_rakam.startswith("90"): temiz.append(sadece_rakam)
    return temiz

def para_formatla(deger):
    try:
        val = float(str(deger).replace(",", "."))
        return "{:,.2f}".format(val).replace(",", ".")
    except: return str(deger)

def text_to_float(text):
    try:
        clean = re.sub(r'[^\d,\.]', '', text).strip(".,")
        clean = clean.replace(".", "").replace(",", ".")
        return float(clean)
    except: return 0.0

# --- YAN MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=70)
    st.markdown("### İLETİŞİM KULESİ")
    secim = option_menu(
        menu_title=None,
        options=["KDV Analiz Robotu", "Profesyonel Mesaj", "Tasdik Robotu", "Veri Yükle"],
        icons=["search", "whatsapp", "robot", "cloud-upload"],
        menu_icon="cast", default_index=0,
        styles={"container": {"padding": "0!important"}, "nav-link": {"font-size": "14px"}}
    )
    
# --- 1. VERİ YÜKLEME ---
if secim == "Veri Yükle":
    st.title("📂 Müşteri Veritabanı")
    st.info("Sistem, personel ve müşteri iletişim bilgilerini buradan alır.")
    
    col1, col2 = st.columns([2,1])
    with col1:
        up = st.file_uploader("PLANLAMA 2026.xlsx Dosyasını Yükle", type=["xlsx", "xls", "csv"])
    
    if up:
        try:
            if up.name.endswith('.csv'): df = pd.read_csv(up)
            else: df = pd.read_excel(up)
            
            # Veri Temizliği
            if "Para Alındı mı" in df.columns: df["Tahsil_Edildi"] = df["Para Alındı mı"].apply(lambda x: True if pd.notna(x) and str(x).strip() != "" else False)
            else: df["Tahsil_Edildi"] = False
            
            if "Defter Tasdik Ücreti" not in df.columns: df["Defter Tasdik Ücreti"] = 0
            
            st.session_state['tasdik_data'] = df
            st.success(f"✅ Başarılı! {len(df)} Müşteri Kaydı Yüklendi.")
            st.dataframe(df.head(), use_container_width=True)
        except Exception as e: st.error(f"Dosya Hatası: {str(e)}")

# --- 2. KDV ANALİZ ROBOTU (CANLI MATRIX MODU) ---
elif secim == "KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz Robotu")
    st.markdown("Kredi Kartı vs. Matrah uyumsuzluklarını saniyeler içinde tespit eder.")
    
    if st.session_state['tasdik_data'] is None: st.warning("⚠️ Lütfen önce 'Veri Yükle' sekmesinden müşteri listesini yükleyin."); st.stop()
    
    pdf_up = st.file_uploader("Beyanname PDF Dosyasını Sürükle Bırak", type=["pdf"])
    
    if pdf_up:
        if st.button("🚀 ANALİZİ BAŞLAT", type="primary"):
            
            # --- CANLI TARAMA EKRANI ---
            progress_bar = st.progress(0)
            status_text = st.empty()
            terminal = st.empty()
            
            terminal_logs = []
            sonuclar = []
            ham_text_full = ""
            
            with pdfplumber.open(pdf_up) as pdf:
                total_pages = len(pdf.pages)
                
                for i, page in enumerate(pdf.pages):
                    # Görsel Efekt
                    status_text.markdown(f"**Taranıyor:** Sayfa {i+1} / {total_pages}")
                    progress_bar.progress((i + 1) / total_pages)
                    
                    text = page.extract_text()
                    if not text:
                        terminal_logs.append(f"[UYARI] Sayfa {i+1}: Metin okunamadı (Resim olabilir)")
                        terminal.code("\n".join(terminal_logs[-5:])) # Son 5 satırı göster
                        continue
                    
                    ham_text_full += f"\n--- Sayfa {i+1} ---\n{text[:500]}...\n"
                    
                    # --- PARSING MOTORU ---
                    # 1. Mükellef
                    isim_match = re.search(r"(SOYADI|UNVANI|ÜNVANI).*?[:\n](.*)", text, re.IGNORECASE)
                    if not isim_match: continue
                    musteri_adi = isim_match.group(2).strip()
                    if len(musteri_adi) < 3: # Alt satıra taşma kontrolü
                         lines = text.split('\n')
                         for j, line in enumerate(lines):
                             if "SOYADI" in line or "UNVANI" in line:
                                 if j+1 < len(lines): musteri_adi = lines[j+1].strip()
                                 break
                    
                    # 2. Veriler
                    kk_match = re.search(r"(?:Kredi Kartı ile Tahsil|Kredi Kartı).*?([\d\.,]+)", text, re.IGNORECASE)
                    kk_tutar = text_to_float(kk_match.group(1)) if kk_match else 0.0

                    # Matrah (Çoklu Pattern)
                    matrah_patterns = [r"TOPLAM MATRAH.*?([\d\.,]+)", r"Matrah Toplamı.*?([\d\.,]+)", r"Matrah.*?Toplamı.*?([\d\.,]+)"]
                    matrah_tutar = 0.0
                    for pat in matrah_patterns:
                        m = re.search(pat, text, re.IGNORECASE)
                        if m: 
                            val = text_to_float(m.group(1))
                            if val > 0: matrah_tutar = val; break
                    
                    kdv_match = re.search(r"(?:TOPLAM HESAPLANAN KDV|Hesaplanan KDV Toplamı).*?([\d\.,]+)", text, re.IGNORECASE)
                    kdv_tutar = text_to_float(kdv_match.group(1)) if kdv_match else 0.0
                    
                    ozel_match = re.search(r"Özel Matrah.*?([\d\.,]+)", text, re.IGNORECASE)
                    ozel_matrah = text_to_float(ozel_match.group(1)) if ozel_match else 0.0
                    
                    # Hesaplama
                    beyan_edilen = matrah_tutar + kdv_tutar + ozel_matrah
                    fark = kk_tutar - beyan_edilen
                    durum = "RİSKLİ" if fark > 50 else "TEMİZ"
                    
                    # Terminale Yaz
                    log_msg = f"> {musteri_adi[:20]}... | KK: {kk_tutar:.0f} | Fark: {fark:.0f} | {durum}"
                    terminal_logs.append(log_msg)
                    terminal.code("\n".join(terminal_logs[-7:])) # Terminal efekti
                    
                    sonuclar.append({
                        "Mükellef": musteri_adi, "Kredi_Karti": kk_tutar, "Matrah": matrah_tutar,
                        "KDV": kdv_tutar, "Ozel_Matrah": ozel_matrah, "Beyan_Edilen_Toplam": beyan_edilen,
                        "Fark": fark, "Durum": durum
                    })
                    # time.sleep(0.05) # Çok hızlıysa görsel için azıcık bekle (Opsiyonel)

            st.session_state['analiz_sonuclari'] = pd.DataFrame(sonuclar)
            st.session_state['analiz_log'] = ham_text_full
            status_text.success("✅ Tarama Tamamlandı!")
            time.sleep(1)
            st.rerun()

    # --- SONUÇ EKRANI ---
    if st.session_state['analiz_sonuclari'] is not None:
        df_res = st.session_state['analiz_sonuclari']
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Taranan Dosya", f"{len(df_res)} Adet")
        c2.metric("🚨 Riskli Mükellef", f"{len(df_res[df_res['Durum']=='RİSKLİ'])} Adet")
        c3.metric("✅ Temiz", f"{len(df_res[df_res['Durum']=='TEMİZ'])} Adet")
        
        st.divider()
        
        # Filtreler
        mod = st.radio("Görünüm:", ["🚨 Sadece Riskli Olanlar", "📋 Tüm Liste"], horizontal=True)
        df_goster = df_res[df_res["Durum"] == "RİSKLİ"] if "Sadece" in mod else df_res
        
        if df_goster.empty:
            st.info("Listelenecek kayıt bulunamadı.")
        else:
            for i, row in df_goster.iterrows():
                musteri = row["Mükellef"]
                fark = para_formatla(row["Fark"])
                kk = para_formatla(row["Kredi_Karti"])
                beyan = para_formatla(row["Beyan_Edilen_Toplam"])
                
                # Personel Eşleştirme
                personel_adi = "Yetkili"
                personel_tel = ""
                if st.session_state['tasdik_data'] is not None:
                    d = st.session_state['tasdik_data']
                    # İsim benzerliği arama
                    match = d[d["Ünvan / Ad Soyad"].str.contains(str(musteri)[:15], case=False, na=False)]
                    if not match.empty:
                        if "Sorumlu" in d.columns: personel_adi = match.iloc[0]["Sorumlu"]
                        # Personel telefonu Excel'de yoksa admin manuel girer, varsa buradan çekilebilir
                
                # KART TASARIMI
                with st.container():
                    col_info, col_action = st.columns([3, 1])
                    
                    with col_info:
                        if row["Durum"] == "RİSKLİ":
                            html = f"""
                            <div class='risk-karti'>
                                <h4 style='margin:0; color:#c62828'>🚨 {musteri}</h4>
                                <p style='margin:5px 0 0 0; font-size:14px; color:#555'>
                                    <b>Kredi Kartı:</b> {kk} TL &nbsp;|&nbsp; 
                                    <b>Beyan (KDV Dahil):</b> {beyan} TL
                                </p>
                                <p style='margin:5px 0 0 0; font-weight:bold; color:#d32f2f'>EKSİK BEYAN FARKI: {fark} TL</p>
                            </div>
                            """
                        else:
                            html = f"<div class='temiz-karti'><b>✅ {musteri}</b><br><small>Sorunsuz</small></div>"
                        
                        st.markdown(html, unsafe_allow_html=True)
                    
                    with col_action:
                        if row["Durum"] == "RİSKLİ":
                            st.write("") # Boşluk
                            tel = st.text_input("Personel Tel", key=f"t_{i}", placeholder="53X...")
                            if st.button("🚨 İHBAR ET", key=f"b_{i}", type="primary"):
                                if tel:
                                    msg = MESAJ_SABLONLARI["KDV Hata Uyarısı (Personele)"].format(
                                        personel=personel_adi, musteri=musteri, kk_tutar=kk, beyan_tutar=beyan, fark=fark
                                    )
                                    for t in numaralari_ayikla(tel): whatsapp_text_gonder(t, msg)
                                    st.toast("Mesaj Gönderildi! ✅")
                                else: st.error("Numara giriniz.")
        
        with st.expander("🛠️ Teknik Detaylar (Raw Log)"):
            st.text(st.session_state['analiz_log'])

# --- 3. PROFESYONEL MESAJ ---
elif secim == "Profesyonel Mesaj":
    st.title("📤 Profesyonel Mesaj Merkezi")
    if st.session_state['tasdik_data'] is not None:
        df_m = st.session_state['tasdik_data']
        
        c_form, c_view = st.columns([1.2, 1])
        with c_form:
            st.subheader("Mesaj Ayarları")
            tur = st.radio("Hedef Kitle:", ["Tek Müşteri", "Toplu Gönderim"], horizontal=True)
            if tur == "Tek Müşteri":
                secilen = [st.selectbox("Müşteri Seçiniz", df_m["Ünvan / Ad Soyad"].tolist())]
            else:
                secilen = df_m["Ünvan / Ad Soyad"].tolist()
                st.warning(f"Dikkat: {len(secilen)} müşteriye mesaj gönderilecek.")
            
            sablon = st.selectbox("Şablon Seçiniz", list(MESAJ_SABLONLARI.keys()))
            icerik = st.text_area("Mesaj İçeriği", value=MESAJ_SABLONLARI[sablon], height=150)
            
            dosya_ekle = st.toggle("📎 Dosya / Resim Ekle")
            up_file = st.file_uploader("Dosya Seç", type=["pdf","jpg","png","xlsx"]) if dosya_ekle else None

        with c_view:
            st.subheader("Önizleme")
            orn = secilen[0] if secilen else "Müşteri Adı"
            final = icerik.replace("{isim}", str(orn)).replace("{ay}", datetime.now().strftime("%B"))
            
            st.markdown(f"""
            <div class='chat-container'>
                <div class='message-bubble'>
                    {'<div style="background:white; padding:5px; border-radius:5px; margin-bottom:5px;">📎 <b>' + up_file.name + '</b><br><small>Ekli Dosya</small></div>' if up_file else ''}
                    {final}
                    <div style="text-align:right; font-size:10px; color:#999; margin-top:5px">{datetime.now().strftime("%H:%M")} ✓✓</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("🚀 GÖNDERİMİ BAŞLAT", type="primary"):
                if not secilen: st.error("Kimse seçilmedi."); st.stop()
                
                bar = st.progress(0)
                basarili = 0
                for i, m in enumerate(secilen):
                    row = df_m[df_m["Ünvan / Ad Soyad"]==m]
                    if not row.empty:
                        tel = row.iloc[0].get("1.NUMARA", "")
                        msg = icerik.replace("{isim}", str(m)).replace("{ay}", datetime.now().strftime("%B"))
                        tels = numaralari_ayikla(tel)
                        
                        for t in tels:
                            if up_file: 
                                up_file.seek(0)
                                whatsapp_dosya_gonder(t, up_file, up_file.name, msg)
                            else: 
                                whatsapp_text_gonder(t, msg)
                        if tels: basarili += 1
                    bar.progress((i+1)/len(secilen))
                st.success(f"İşlem Tamamlandı! {basarili} müşteriye gönderim yapıldı.")

# --- 4. TASDİK ROBOTU ---
elif secim == "Tasdik Robotu":
    st.title("🤖 Tasdik Takip Sistemi")
    if st.session_state['tasdik_data'] is not None:
        df = st.session_state['tasdik_data']
        
        col1, col2 = st.columns(2)
        borc_sayisi = len(df[df["Tahsil_Edildi"]==False])
        col1.metric("🔴 Ödenmeyen", borc_sayisi)
        col2.metric("🟢 Tahsil Edilen", len(df)-borc_sayisi)
        
        st.divider()
        st.subheader("1. Tahsilat İşle")
        edited = st.data_editor(df[["Ünvan / Ad Soyad", "Defter Tasdik Ücreti", "Tahsil_Edildi"]], 
                                column_config={"Tahsil_Edildi": st.column_config.CheckboxColumn("Ödendi?", default=False)},
                                use_container_width=True, hide_index=True, height=300)
        
        if st.button("💾 Değişiklikleri Kaydet", type="primary"):
            st.session_state['tasdik_data'].update(edited)
            st.rerun()
            
        st.divider()
        st.subheader("2. Hızlı Mesaj")
        borclular = st.session_state['tasdik_data'][st.session_state['tasdik_data']["Tahsil_Edildi"]==False]
        if borclular.empty: st.success("Herkes ödemiş! 🎉")
        else:
            sablon = MESAJ_SABLONLARI["Tasdik Ödenmedi (RESMİ UYARI)"]
            for i, row in borclular.iterrows():
                isim = row["Ünvan / Ad Soyad"]; tutar = para_formatla(row.get("Defter Tasdik Ücreti", 0))
                tel = row.get("1.NUMARA", "")
                
                c_text, c_btn = st.columns([4,1])
                with c_text: st.info(f"**{isim}** | Borç: {tutar} TL")
                with c_btn:
                    if st.button("📩 Uyar", key=f"u_{i}"):
                        msg = sablon.replace("{isim}", str(isim)).replace("{tutar}", str(tutar))
                        for t in numaralari_ayikla(tel): whatsapp_text_gonder(t, msg)
                        st.toast("Uyarı Gitti! 🚀")
