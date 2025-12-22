import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import pandas as pd
import re

# --- GÜVENLİK VE AYARLAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]
    API_TOKEN = st.secrets["API_TOKEN"]
    GRUP_ID = st.secrets["GRUP_ID"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
except:
    st.error("Sistem Bulut modunda değil veya şifreler eksik!")
    st.stop()

# --- FONKSİYONLAR ---
def google_sheet_baglan(sayfa_adi="Sheet1"):
    client = gspread.authorize(creds)
    if sayfa_adi == "Sheet1":
        return client.open("Is_Takip_Sistemi").sheet1
    else:
        return client.open("Is_Takip_Sistemi").worksheet(sayfa_adi)

def numaralari_ayikla(tel_str):
    """
    Excel hücresindeki tüm numaraları bulur ve liste olarak döndürür.
    Örn: "(0532) 111 \n 0533 222" -> ['90532111...', '90533222...']
    """
    if not tel_str: return []
    
    tel_str = str(tel_str)
    # Hem virgül hem de yeni satır karakterine göre böl (alt alta veya yan yana yazılanlar için)
    ham_parcalar = re.split(r'[,\n]', tel_str)
    
    temiz_numaralar = []
    
    for parca in ham_parcalar:
        # Sadece rakamları bırak
        sadece_rakamlar = re.sub(r'\D', '', parca)
        
        # Format düzeltme
        son_hal = None
        if len(sadece_rakamlar) == 10: # 532... -> 90532...
            son_hal = "90" + sadece_rakamlar
        elif len(sadece_rakamlar) == 11 and sadece_rakamlar.startswith("0"): # 0532... -> 90532...
            son_hal = "9" + sadece_rakamlar
        elif len(sadece_rakamlar) == 12 and sadece_rakamlar.startswith("90"): # 90532... (Hazır)
            son_hal = sadece_rakamlar
            
        if son_hal:
            temiz_numaralar.append(son_hal)
            
    return temiz_numaralar

def whatsapp_gonder(chat_id, mesaj):
    # Kişiye atıyorsak ve numara formatındaysa sonuna @c.us ekle
    if "@" not in chat_id:
        chat_id = f"{chat_id}@c.us"
        
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    payload = {'chatId': chat_id, 'message': mesaj}
    try:
        requests.post(url, json=payload)
        return True
    except:
        return False

def musterileri_getir():
    try:
        sheet = google_sheet_baglan("Musteriler")
        veriler = sheet.get_all_records()
        return pd.DataFrame(veriler)
    except:
        return pd.DataFrame()

# --- SAYFA TASARIMI ---
st.set_page_config(page_title="İş Asistanı", page_icon="💼")
st.title("👨‍💼 Mobil İş Takip Asistanı")

tab1, tab2 = st.tabs(["➕ Yeni İş Ekle", "📋 Listeyi Gör"])

with tab1:
    with st.form("is_formu", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tarih = st.date_input("Tarih")
        with col2:
            saat = st.time_input("Saat")
        
        # Müşterileri Çek
        df_musteriler = musterileri_getir()
        bulunan_numaralar = []
        
        if not df_musteriler.empty:
            isim_listesi = df_musteriler["Ad Soyad"].tolist()
            secilen_musteri = st.selectbox("Mükellef Seç", isim_listesi)
            
            # Seçilen kişinin numaralarını bul
            if secilen_musteri:
                satir = df_musteriler[df_musteriler["Ad Soyad"] == secilen_musteri]
                if not satir.empty:
                    ham_veri = satir.iloc[0]["Telefon"]
                    bulunan_numaralar = numaralari_ayikla(ham_veri)
                    
                    # Ekrana bilgi ver
                    if bulunan_numaralar:
                        st.success(f"📞 Kayıtlı {len(bulunan_numaralar)} numara bulundu: {', '.join(bulunan_numaralar)}")
                    else:
                        st.warning("⚠️ Bu müşteride geçerli telefon numarası bulunamadı.")
        else:
            secilen_musteri = st.text_input("Müşteri Adı (Manuel)")
            st.warning("Müşteri listesi boş.")

        is_notu = st.text_input("Yapılacak İş / Not", placeholder="Örn: KDV Beyannamesi Onayı")
        
        # --- ONAY KUTUSU ---
        st.write("---")
        musteriye_gonderilsin_mi = st.checkbox("📨 Mükellefe (Tüm Numaralarına) Bildirim Gönder")
        
        submit_btn = st.form_submit_button("✅ Kaydet ve İşlemi Başlat")

        if submit_btn and is_notu:
            try:
                sheet = google_sheet_baglan()
                tarih_str = tarih.strftime("%d.%m.%Y")
                saat_str = saat.strftime("%H:%M")
                tam_is_tanimi = f"{secilen_musteri} - {is_notu}"
                
                # 1. Google Sheets'e Kaydet
                sheet.append_row([tarih_str, saat_str, tam_is_tanimi, "Gonderildi", "Bekliyor"])
                st.info("✅ İş listeye kaydedildi.")
                
                # 2. Ofis Grubuna Gönder
                grup_mesaji = f"📅 *YENİ İŞ*\n👤 *Mükellef:* {secilen_musteri}\n📌 *İş:* {is_notu}\n🗓 *Tarih:* {tarih_str} {saat_str}"
                whatsapp_gonder(GRUP_ID, grup_mesaji)
                
                # 3. Müşteriye (Tüm Numaralara) Gönder
                if musteriye_gonderilsin_mi and bulunan_numaralar:
                    musteri_mesaji = f"Sayın *{secilen_musteri}*,\n\nİşleminiz ({is_notu}) iş takvimimize alınmıştır.\n\nBilginize sunarız.\n*Mali Müşavirlik Ofisi*"
                    
                    for num in bulunan_numaralar:
                        whatsapp_gonder(num, musteri_mesaji)
                    
                    st.success(f"🚀 Mükellefin {len(bulunan_numaralar)} numarasına da mesaj gönderildi!")
                    
                elif musteriye_gonderilsin_mi and not bulunan_numaralar:
                    st.error("❌ Mükellefe gönderilemedi: Numara bulunamadı.")
                
                st.balloons()
                
            except Exception as e:
                st.error(f"Hata oluştu: {e}")

with tab2:
    st.subheader("Bekleyen İşler")
    if st.button("🔄 Listeyi Yenile"):
        st.rerun()
    try:
        df = verileri_getir()
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Kayıt yok.")
    except:
        st.error("Veri hatası.")
