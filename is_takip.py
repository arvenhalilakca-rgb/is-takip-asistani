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
    
    .kisi-karti {
        background-color: white; padding: 10px; border-radius: 8px; 
        border-left: 5px solid #128C7E; margin-bottom: 5px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .risk-karti {
        background-color: #ffebee; padding: 10px; border-radius: 8px; 
        border-left: 5px solid #c62828; margin-bottom: 5px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1); color: #c62828;
    }
    
    .stButton>button {
        border-radius: 8px; font-weight: bold; border: none; 
        transition: all 0.2s ease; width: 100%; height: 45px;
    }
    button[kind="primary"] {background-color: #128C7E; color: white;}
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
MESAJ_SABLONLARI = {
    "KDV Hata Uyarısı (Personele)": "Sayın {personel}, {musteri} firmasının KDV beyannamesinde Kredi Kartı Satışları ile Beyan Edilen Matrah arasında uyumsuzluk tespit edilmiştir.\n\nKredi Kartı: {kk_tutar} TL\nBeyan Edilen (KDV Dahil): {beyan_tutar} TL\nFark: {fark} TL\n\nOfis olarak yaptığımız KDV incelemelerinde hata yapıldığını düşünüyoruz. Müşterideki veya kayıtlardaki hatanın incelenip tarafımıza raporlanmasını rica ederim.",
    "Genel Duyuru": "Sayın {isim}, ..."
}

# --- SESSION ---
if 'analiz_sonuclari' not in st.session_state: st.session_state['analiz_sonuclari'] = None
if 'tasdik_data' not in st.session_state: st.session_state['tasdik_data'] = None

# --- BAĞLANTILAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]; API_TOKEN = st.secrets["API_TOKEN"]
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
        return "{:,.2f}".format(val).replace(",", ".") # Kuruşlu format
    except: return str(deger)

def text_to_float(text):
    try:
        # 1.250,50 formatını 1250.50 float formatına çevir
        clean = text.replace(".", "").replace(",", ".")
        return float(clean)
    except: return 0.0

# --- KDV ANALİZ MOTORU ---
def beyanname_analiz_et(pdf_file):
    sonuclar = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            
            # 1. Mükellef Adını Bul (Beyannamelerde genelde SOYADI (UNVANI) satırında olur)
            # Bu regex beyanname formatına göre değişebilir, genel bir yakalama yapıyoruz.
            isim_match = re.search(r"SOYADI \(UNVANI\)\s*[:\n]\s*(.*)", text)
            if not isim_match:
                # Alternatif: Ticaret Unvanı satırı
                isim_match = re.search(r"TİCARET UNVANI\s*[:\n]\s*(.*)", text)
            
            musteri_adi = isim_match.group(1).strip() if isim_match else "Bilinmeyen Mükellef"
            # Gereksiz alt satırları temizle
            musteri_adi = musteri_adi.split("\n")[0]

            # 2. Kredi Kartı Tutarını Bul (45. Satır)
            # "Kredi Kartı ile Tahsil Edilen..." satırını arar
            kk_match = re.search(r"Kredi Kartı ile Tahsil.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
            kk_tutar = text_to_float(kk_match.group(1)) if kk_match else 0.0

            # 3. Matrah Toplamını Bul
            # "TOPLAM MATRAH" veya "Matrah Toplamı"
            matrah_match = re.search(r"TOPLAM MATRAH.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
            # Eğer toplam matrah yoksa (bazen sadece matrah yazar), satır 40-44 arası tarama yapılabilir.
            # Basit yöntem:
            matrah_tutar = text_to_float(matrah_match.group(1)) if matrah_match else 0.0

            # 4. Hesaplanan KDV Toplamını Bul
            # "TOPLAM HESAPLANAN KDV"
            kdv_match = re.search(r"TOPLAM HESAPLANAN KDV.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
            kdv_tutar = text_to_float(kdv_match.group(1)) if kdv_match else 0.0

            # 5. Özel Matrah (Varsa)
            ozel_matrah_match = re.search(r"Özel Matrah.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
            ozel_matrah = text_to_float(ozel_matrah_match.group(1)) if ozel_matrah_match else 0.0

            # 6. Analiz
            # Beyan Edilen Satış (KDV Dahil) = Matrah + KDV + Özel Matrah
            beyan_edilen = matrah_tutar + kdv_tutar + ozel_matrah
            fark = kk_tutar - beyan_edilen
            
            # Tolerans (Örn: 50 TL yuvarlama farkı olabilir)
            durum = "RİSKLİ" if fark > 50 else "TEMİZ"
            
            if musteri_adi != "Bilinmeyen Mükellef":
                sonuclar.append({
                    "Mükellef": musteri_adi,
                    "Kredi_Karti": kk_tutar,
                    "Matrah": matrah_tutar,
                    "KDV": kdv_tutar,
                    "Ozel_Matrah": ozel_matrah,
                    "Beyan_Edilen_Toplam": beyan_edilen,
                    "Fark": fark,
                    "Durum": durum
                })
                
    return pd.DataFrame(sonuclar)

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
    
# --- VERİ YÜKLEME ---
if secim == "Veri Yükle":
    st.title("📂 Veritabanı")
    st.info("Sistem, personel bilgisini ve müşteri telefonunu bu listeden alır.")
    
    up = st.file_uploader("PLANLAMA 2026 Dosyasını Yükle", type=["xlsx", "xls", "csv"])
    if up:
        try:
            if up.name.endswith('.csv'): df = pd.read_csv(up)
            else: df = pd.read_excel(up)
            
            # Gerekli sütunlar: Ünvan / Ad Soyad, 1.NUMARA, Sorumlu (veya personel sütunu yoksa eklenmeli)
            st.session_state['tasdik_data'] = df
            st.success(f"✅ {len(df)} Müşteri Yüklendi.")
            st.dataframe(df.head())
        except Exception as e: st.error(str(e))

# --- KDV ANALİZ ROBOTU ---
elif secim == "KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz & İhbar Robotu")
    st.info("Toplu KDV beyannamesi PDF'ini yükleyin. Sistem Kredi Kartı vs. Matrah kontrolü yapar.")
    
    if st.session_state['tasdik_data'] is None:
        st.error("Lütfen önce 'Veri Yükle' menüsünden müşteri listesini yükleyin (Personel eşleşmesi için).")
    
    # PDF YÜKLEME
    pdf_up = st.file_uploader("Beyanname PDF'ini Yükle", type=["pdf"])
    
    if pdf_up:
        if st.button("🔍 Analizi Başlat"):
            with st.spinner("Beyannameler taranıyor..."):
                df_sonuc = beyanname_analiz_et(pdf_up)
                st.session_state['analiz_sonuclari'] = df_sonuc
    
    # SONUÇLARI GÖSTER
    if st.session_state['analiz_sonuclari'] is not None:
        df_res = st.session_state['analiz_sonuclari']
        
        # Sadece Risklileri Filtrele Butonu
        sadece_risk = st.checkbox("Sadece Hatalı (Riskli) Olanları Göster", value=True)
        
        if sadece_risk:
            df_goster = df_res[df_res["Durum"] == "RİSKLİ"]
        else:
            df_goster = df_res
            
        c1, c2 = st.columns(2)
        c1.metric("Taranan Beyanname", len(df_res))
        c2.metric("🚨 Tespit Edilen Risk", len(df_res[df_res["Durum"]=="RİSKLİ"]))
        
        st.divider()
        
        # LİSTE VE AKSİYON
        if not df_goster.empty:
            for i, row in df_goster.iterrows():
                musteri = row["Mükellef"]
                fark = para_formatla(row["Fark"])
                kk = para_formatla(row["Kredi_Karti"])
                beyan = para_formatla(row["Beyan_Edilen_Toplam"])
                
                # Personeli Bul (Excel'den)
                personel_adi = "Personel"
                personel_tel = ""
                
                if st.session_state['tasdik_data'] is not None:
                    # Basit bir fuzzy match veya exact match denemesi
                    df_data = st.session_state['tasdik_data']
                    # Mükellef adının bir kısmı geçiyorsa bulmaya çalış
                    eslesme = df_data[df_data["Ünvan / Ad Soyad"].str.contains(musteri[:10], case=False, na=False)]
                    
                    if not eslesme.empty:
                        # Eğer excelde "Sorumlu" veya "Personel" sütunu varsa onu al
                        # Yoksa admin numarasını kullanabiliriz. Şimdilik "1.NUMARA"yı müşteri sanıyoruz ama personel lazım.
                        # Varsayalım ki 'Sorumlu' sütunu var. Yoksa manuel girilecek.
                        if "Sorumlu" in df_data.columns:
                            personel_adi = eslesme.iloc[0]["Sorumlu"]
                        # Personel numarasını nereden alacağız? 
                        # Eğer excelde yoksa, buraya sabit bir input koyalım veya admin'e atsın.
                
                # KART GÖRÜNÜMÜ
                with st.container():
                    col_detay, col_btn = st.columns([3, 1])
                    with col_detay:
                        st.markdown(f"""
                        <div class='risk-karti'>
                            <b>{musteri}</b><br>
                            Kredi Kartı: {kk} TL | Beyan (Dahil): {beyan} TL<br>
                            <b>FARK: {fark} TL (Eksik Beyan)</b>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col_btn:
                        # Personel Seçimi (Eğer otomatik bulunamadıysa)
                        # Burada basitlik olsun diye manuel numara girişi veya listeden seçim yapılabilir
                        # Biz şimdilik manuel numara girişi koyalım, daha güvenli.
                        
                        target_tel = st.text_input(f"Personel Tel ({i})", placeholder="53X...", key=f"tel_{i}")
                        
                        if st.button("🚨 İhbar Et", key=f"btn_{i}"):
                            if target_tel:
                                msg = MESAJ_SABLONLARI["KDV Hata Uyarısı (Personele)"].format(
                                    personel=personel_adi,
                                    musteri=musteri,
                                    kk_tutar=kk,
                                    beyan_tutar=beyan,
                                    fark=fark
                                )
                                tels = numaralari_ayikla(target_tel)
                                for t in tels:
                                    whatsapp_text_gonder(t, msg)
                                st.toast("Personel Uyarıldı! 👮‍♂️", icon="✅")
                            else:
                                st.error("Numara giriniz.")
        else:
            st.success("Tebrikler! Yüklenen beyannamelerde kredi kartı uyumsuzluğu bulunamadı. 🧿")

# --- PROFESYONEL MESAJ (MEVCUT) ---
elif secim == "Profesyonel Mesaj":
    # (Burada önceki kodun 'Profesyonel Mesaj' bloğu aynen kalacak)
    st.title("📤 Profesyonel Mesaj")
    if st.session_state['tasdik_data'] is not None:
        # ... (Önceki kodun aynısı)
        pass # Yer kaplamasın diye kısalttım, siz önceki kodu buraya yapıştırın

# --- TASDİK ROBOTU (MEVCUT) ---
elif secim == "Tasdik Robotu":
    # (Burada önceki kodun 'Tasdik Robotu' bloğu aynen kalacak)
    pass
