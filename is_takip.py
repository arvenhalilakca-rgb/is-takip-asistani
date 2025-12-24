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

# --- TASARIM (CSS) ---
st.markdown("""
    <style>
    .stApp {background-color: #e5ddd5; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;}
    [data-testid="stSidebar"] {background-color: #FFFFFF; border-right: 1px solid #E0E0E0;}
    .chat-container {background-image: url('https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png'); background-repeat: repeat; padding: 20px; border-radius: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); min-height: 300px;}
    .message-bubble {background-color: #dcf8c6; padding: 10px 15px; border-radius: 8px; box-shadow: 0 1px 1px rgba(0,0,0,0.1); max-width: 80%; margin-bottom: 10px; position: relative; float: right; clear: both;}
    .kisi-karti {background-color: white; padding: 10px; border-radius: 8px; border-left: 5px solid #128C7E; margin-bottom: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);}
    .risk-karti {background-color: #ffebee; padding: 10px; border-radius: 8px; border-left: 5px solid #c62828; margin-bottom: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); color: #c62828;}
    .stButton>button {border-radius: 8px; font-weight: bold; border: none; transition: all 0.2s ease; width: 100%; height: 45px;}
    button[kind="primary"] {background-color: #128C7E; color: white;}
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
MESAJ_SABLONLARI = {
    "Serbest Metin": "",
    "KDV Hata Uyarısı (Personele)": "Sayın {personel}, {musteri} firmasının KDV beyannamesinde Kredi Kartı Satışları ile Beyan Edilen Matrah arasında uyumsuzluk tespit edilmiştir.\n\nKredi Kartı: {kk_tutar} TL\nBeyan Edilen (KDV Dahil): {beyan_tutar} TL\nFark: {fark} TL\n\nOfis olarak incelemede hata olduğunu düşünüyoruz. Kontrol edilip raporlanmasını rica ederim.",
    "KDV Tahakkuk": "Sayın {isim}, {ay} dönemi KDV beyannameniz onaylanmıştır. Tahakkuk fişiniz ektedir. Ödemenizi vadesinde yapmanızı rica ederiz.",
    "Tasdik Ödenmedi (RESMİ UYARI)": "Sayın Mükellefimiz {isim}, 2026 yılı Defter Tasdik ve Yazılım Giderleri ücretiniz ({tutar} TL) ödenmediği için defterleriniz notere teslim EDİLMEMİŞTİR. Bugün SON GÜN.",
}

# --- SESSION ---
if 'analiz_sonuclari' not in st.session_state: st.session_state['analiz_sonuclari'] = None
if 'tasdik_data' not in st.session_state: st.session_state['tasdik_data'] = None

# --- BAĞLANTILAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]; API_TOKEN = st.secrets["API_TOKEN"]
    try: creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    except: creds = None
except: st.error("⚠️ Ayar Hatası: Secrets eksik."); st.stop()

# --- YARDIMCI FONKSİYONLAR ---
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
    return temiz

def para_formatla(deger):
    try:
        val = float(str(deger).replace(",", "."))
        return "{:,.2f}".format(val).replace(",", ".")
    except: return str(deger)

def text_to_float(text):
    try:
        clean = text.replace(".", "").replace(",", ".")
        return float(clean)
    except: return 0.0

# --- KDV ANALİZ MOTORU (HASSAS MOD) ---
def beyanname_analiz_et(pdf_file):
    sonuclar = []
    bos_df = pd.DataFrame(columns=["Mükellef", "Kredi_Karti", "Matrah", "KDV", "Ozel_Matrah", "Beyan_Edilen_Toplam", "Fark", "Durum"])
    
    ham_text_log = "" # Debug için log tutacağız

    try:
        with pdfplumber.open(pdf_file) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text: 
                    ham_text_log += f"\n--- SAYFA {i+1}: BOŞ (Metin okunamadı) ---\n"
                    continue
                
                # Debug için ilk 300 karakteri kaydet
                ham_text_log += f"\n--- SAYFA {i+1} ---\n{text[:300]}...\n----------------\n"

                # 1. Mükellef Bul (Daha Esnek Regex)
                # Hem "SOYADI" hem "UNVANI" kelimelerine bakar, büyük/küçük harf duyarsız
                isim_match = re.search(r"(SOYADI|UNVANI|ÜNVANI).*?[:\n](.*)", text, re.IGNORECASE)
                
                if not isim_match:
                    continue # İsim yoksa beyanname değildir

                # Bulunan satırı temizle (Gereksiz boşlukları at)
                musteri_adi = isim_match.group(2).strip()
                # Eğer isim çok kısaysa alt satıra kaymış olabilir, orayı al
                if len(musteri_adi) < 3: 
                    lines = text.split('\n')
                    for j, line in enumerate(lines):
                        if "SOYADI" in line or "UNVANI" in line:
                            if j+1 < len(lines): musteri_adi = lines[j+1].strip()
                            break

                # 2. Veri Çek (Kredi Kartı - Satır 45)
                kk_match = re.search(r"Kredi Kartı ile Tahsil.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
                kk_tutar = text_to_float(kk_match.group(1)) if kk_match else 0.0

                # 3. Matrah (Toplam Matrah veya Matrah Toplamı)
                matrah_match = re.search(r"(TOPLAM MATRAH|Matrah Toplamı).*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
                matrah_tutar = text_to_float(matrah_match.group(2)) if matrah_match else 0.0

                # 4. KDV (Toplam Hesaplanan)
                kdv_match = re.search(r"TOPLAM HESAPLANAN KDV.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
                kdv_tutar = text_to_float(kdv_match.group(1)) if kdv_match else 0.0

                # 5. Özel Matrah
                ozel_matrah_match = re.search(r"Özel Matrah.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
                ozel_matrah = text_to_float(ozel_matrah_match.group(1)) if ozel_matrah_match else 0.0

                # Hesapla
                beyan_edilen = matrah_tutar + kdv_tutar + ozel_matrah
                fark = kk_tutar - beyan_edilen
                durum = "RİSKLİ" if fark > 50 else "TEMİZ"
                
                sonuclar.append({
                    "Mükellef": musteri_adi, "Kredi_Karti": kk_tutar, "Matrah": matrah_tutar,
                    "KDV": kdv_tutar, "Ozel_Matrah": ozel_matrah, "Beyan_Edilen_Toplam": beyan_edilen,
                    "Fark": fark, "Durum": durum
                })
    except Exception as e:
        st.error(f"PDF Analiz Hatası: {e}"); return bos_df, ham_text_log

    return (pd.DataFrame(sonuclar) if sonuclar else bos_df), ham_text_log

# --- YAN MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.markdown("### İLETİŞİM KULESİ")
    secim = option_menu(
        menu_title=None,
        options=["KDV Analiz Robotu", "Profesyonel Mesaj", "Tasdik Robotu", "Veri Yükle"],
        icons=["search", "whatsapp", "robot", "cloud-upload"],
        menu_icon="cast", default_index=0,
        styles={"container": {"padding": "0!important"}}
    )
    
# --- 1. VERİ YÜKLEME ---
if secim == "Veri Yükle":
    st.title("📂 Veritabanı")
    st.info("PLANLAMA 2026.xlsx dosyasını buraya yükleyin.")
    up = st.file_uploader("Dosyayı Sürükle Bırak", type=["xlsx", "xls", "csv"])
    if up:
        try:
            if up.name.endswith('.csv'): df = pd.read_csv(up)
            else: df = pd.read_excel(up)
            if "Para Alındı mı" in df.columns: df["Tahsil_Edildi"] = df["Para Alındı mı"].apply(lambda x: True if pd.notna(x) and str(x).strip() != "" else False)
            else: df["Tahsil_Edildi"] = False
            if "Defter Tasdik Ücreti" not in df.columns: df["Defter Tasdik Ücreti"] = 0
            st.session_state['tasdik_data'] = df
            st.success(f"✅ {len(df)} Kişi Yüklendi!"); st.dataframe(df.head())
        except Exception as e: st.error(str(e))

# --- 2. KDV ANALİZ ROBOTU (DEBUG MODLU) ---
elif secim == "KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz & İhbar Robotu")
    if st.session_state['tasdik_data'] is None: st.warning("⚠️ Önce 'Veri Yükle' kısmından müşteri listesini yükleyin.")
    
    pdf_up = st.file_uploader("Beyanname PDF'ini Yükle", type=["pdf"])
    
    if pdf_up:
        if st.button("🔍 Analizi Başlat"):
            with st.spinner("Beyannameler taranıyor..."):
                df_sonuc, ham_log = beyanname_analiz_et(pdf_up)
                st.session_state['analiz_sonuclari'] = df_sonuc
                st.session_state['analiz_log'] = ham_log
    
    # SONUÇ GÖSTERİMİ
    if st.session_state['analiz_sonuclari'] is not None:
        df_res = st.session_state['analiz_sonuclari']
        
        # --- DEBUG PENCERESİ ---
        with st.expander("🛠️ Robotun Gördüğü Ham Veri (Hata Varsa Buraya Bak)"):
            if 'analiz_log' in st.session_state:
                st.text(st.session_state['analiz_log'])
            else:
                st.write("Henüz veri yok.")

        if df_res.empty:
            st.error("❌ Veri okunamadı! Yukarıdaki 'Robotun Gördüğü Ham Veri' kutusunu açın.")
            st.info("Eğer kutu boşsa: PDF resim formatındadır (Taranmış belge).")
            st.info("Eğer kutuda yazılar varsa: Mükellef adı formatı farklı olabilir.")
        else:
            sadece_risk = st.checkbox("Sadece Riskli Olanlar", value=True)
            df_goster = df_res[df_res["Durum"] == "RİSKLİ"] if sadece_risk else df_res
            
            c1, c2 = st.columns(2)
            c1.metric("Taranan", len(df_res))
            c2.metric("🚨 Riskli", len(df_res[df_res["Durum"]=="RİSKLİ"]))
            st.divider()
            
            if not df_goster.empty:
                for i, row in df_goster.iterrows():
                    musteri = row["Mükellef"]; fark = para_formatla(row["Fark"])
                    kk = para_formatla(row["Kredi_Karti"]); beyan = para_formatla(row["Beyan_Edilen_Toplam"])
                    
                    personel_adi = "Yetkili"
                    if st.session_state['tasdik_data'] is not None:
                        d = st.session_state['tasdik_data']
                        match = d[d["Ünvan / Ad Soyad"].str.contains(str(musteri)[:10], case=False, na=False)]
                        if not match.empty and "Sorumlu" in d.columns: personel_adi = match.iloc[0]["Sorumlu"]
                    
                    with st.container():
                        c_d, c_b = st.columns([3, 1])
                        with c_d: st.markdown(f"<div class='risk-karti'><b>{musteri}</b><br>KK: {kk} | Beyan: {beyan}<br><b>FARK: {fark} TL</b></div>", unsafe_allow_html=True)
                        with c_b:
                            tel = st.text_input(f"Tel", key=f"t_{i}", placeholder="53X...")
                            if st.button("🚨 İhbar Et", key=f"b_{i}"):
                                msg = MESAJ_SABLONLARI["KDV Hata Uyarısı (Personele)"].format(personel=personel_adi, musteri=musteri, kk_tutar=kk, beyan_tutar=beyan, fark=fark)
                                for t in numaralari_ayikla(tel): whatsapp_text_gonder(t, msg)
                                st.toast("Uyarıldı! ✅")
            else: st.success("Riskli durum yok.")

# --- 3. PROFESYONEL MESAJ ---
elif secim == "Profesyonel Mesaj":
    st.title("📤 Profesyonel Mesaj")
    if st.session_state['tasdik_data'] is not None:
        df_m = st.session_state['tasdik_data']
        c_form, c_view = st.columns([1.2, 1])
        with c_form:
            tur = st.radio("Kime?", ["Tek Müşteri", "Toplu"], horizontal=True)
            if tur == "Tek Müşteri": secilen = [st.selectbox("Müşteri", df_m["Ünvan / Ad Soyad"].tolist())]
            else: secilen = df_m["Ünvan / Ad Soyad"].tolist(); st.warning(f"{len(secilen)} kişi!")
            sablon = st.selectbox("Şablon", list(MESAJ_SABLONLARI.keys()))
            icerik = st.text_area("İçerik", value=MESAJ_SABLONLARI[sablon], height=150)
            dosya_ekle = st.toggle("📎 Dosya Ekle")
            up_file = st.file_uploader("Dosya", type=["pdf","jpg","xlsx"]) if dosya_ekle else None

        with c_view:
            st.markdown("### Önizleme")
            orn = secilen[0] if secilen else "İsim"
            final = icerik.replace("{isim}", str(orn)).replace("{ay}", datetime.now().strftime("%B"))
            st.markdown(f"<div class='chat-container'><div class='message-bubble'><div class='message-text'>{final}</div></div></div>", unsafe_allow_html=True)
            if st.button("🚀 GÖNDER", type="primary"):
                bar = st.progress(0); basarili = 0
                for i, m in enumerate(secilen):
                    row = df_m[df_m["Ünvan / Ad Soyad"]==m]
                    if not row.empty:
                        tel = row.iloc[0].get("1.NUMARA", ""); tels = numaralari_ayikla(tel)
                        msg = icerik.replace("{isim}", str(m)).replace("{ay}", datetime.now().strftime("%B"))
                        for t in tels:
                            if up_file: up_file.seek(0); whatsapp_dosya_gonder(t, up_file, up_file.name, msg)
                            else: whatsapp_text_gonder(t, msg)
                        if tels: basarili += 1
                    bar.progress((i+1)/len(secilen))
                st.success(f"{basarili} gönderim tamam.")

# --- 4. TASDİK ROBOTU ---
elif secim == "Tasdik Robotu":
    st.title("🤖 Tasdik Operasyon")
    if st.session_state['tasdik_data'] is not None:
        df = st.session_state['tasdik_data']
        c1, c2 = st.columns(2)
        borc = len(df[df["Tahsil_Edildi"]==False])
        c1.metric("🔴 Borçlu", borc); c2.metric("🟢 Ödeyen", len(df)-borc)
        edited = st.data_editor(df[["Ünvan / Ad Soyad", "Defter Tasdik Ücreti", "Tahsil_Edildi"]], column_config={"Tahsil_Edildi": st.column_config.CheckboxColumn("Ödendi?", default=False)}, hide_index=True, use_container_width=True)
        if st.button("💾 Kaydet", type="primary"): st.session_state['tasdik_data'].update(edited); st.rerun()
