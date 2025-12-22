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
    st.error("⚠️ Sistem Bulut modunda değil veya şifreler eksik!")
    st.stop()

# --- FONKSİYONLAR ---
def google_sheet_baglan(sayfa_adi="Sheet1"):
    client = gspread.authorize(creds)
    # Varsayılan olarak ilk sayfayı açar, adı ne olursa olsun
    if sayfa_adi == "Sheet1":
        return client.open("Is_Takip_Sistemi").sheet1
    else:
        return client.open("Is_Takip_Sistemi").worksheet(sayfa_adi)

def numaralari_ayikla(tel_str):
    if not tel_str: return []
    tel_str = str(tel_str)
    ham_parcalar = re.split(r'[,\n]', tel_str)
    temiz_numaralar = []
    for parca in ham_parcalar:
        sadece_rakamlar = re.sub(r'\D', '', parca)
        son_hal = None
        if len(sadece_rakamlar) == 10: son_hal = "90" + sadece_rakamlar
        elif len(sadece_rakamlar) == 11 and sadece_rakamlar.startswith("0"): son_hal = "9" + sadece_rakamlar
        elif len(sadece_rakamlar) == 12 and sadece_rakamlar.startswith("90"): son_hal = sadece_rakamlar
        if son_hal: temiz_numaralar.append(son_hal)
    return temiz_numaralar

def whatsapp_gonder(chat_id, mesaj):
    if "@" not in chat_id: chat_id = f"{chat_id}@c.us"
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
        return pd.DataFrame() # Müşteri sayfası yoksa boş dön

def ana_verileri_getir():
    sheet = google_sheet_baglan()
    return sheet.get_all_records()

# --- SAYFA TASARIMI ---
st.set_page_config(page_title="İş Asistanı", page_icon="💼")
st.title("👨‍💼 Mobil İş Takip Asistanı")

tab1, tab2 = st.tabs(["➕ Yeni İş Ekle", "✅ İşleri Yönet"])

# --- TAB 1: İŞ EKLEME ---
with tab1:
    with st.form("is_formu", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1: tarih = st.date_input("Tarih")
        with col2: saat = st.time_input("Saat")
        
        # Müşteri Listesi
        df_musteriler = musterileri_getir()
        bulunan_numaralar = []
        
        if not df_musteriler.empty:
            isim_listesi = df_musteriler["Ad Soyad"].tolist()
            secilen_musteri = st.selectbox("Mükellef Seç", isim_listesi)
            
            if secilen_musteri:
                satir = df_musteriler[df_musteriler["Ad Soyad"] == secilen_musteri]
                if not satir.empty:
                    ham_veri = satir.iloc[0]["Telefon"]
                    bulunan_numaralar = numaralari_ayikla(ham_veri)
                    if bulunan_numaralar: 
                        st.caption(f"📞 Sistemde kayıtlı {len(bulunan_numaralar)} numara var.")
        else:
            secilen_musteri = st.text_input("Müşteri Adı (Manuel)")
            st.warning("⚠️ 'Musteriler' sayfası bulunamadı veya boş.")

        is_notu = st.text_input("Yapılacak İş / Not", placeholder="Örn: KDV Beyannamesi")
        st.write("---")
        musteriye_gonderilsin_mi = st.checkbox("📨 Mükellefe de 'İşleme Alındı' mesajı at")
        
        submit_btn = st.form_submit_button("✅ Kaydet ve Başlat")

        if submit_btn and is_notu:
            try:
                sheet = google_sheet_baglan()
                tarih_str = tarih.strftime("%d.%m.%Y")
                saat_str = saat.strftime("%H:%M")
                tam_is_tanimi = f"{secilen_musteri} - {is_notu}"
                
                # Sütun sırası: Tarih, Saat, Is Tanimi, Mesaj Durumu, Durum
                sheet.append_row([tarih_str, saat_str, tam_is_tanimi, "Gonderildi", "Bekliyor"])
                st.info("✅ İş sisteme kaydedildi.")
                
                # Gruba mesaj
                whatsapp_gonder(GRUP_ID, f"📅 *YENİ İŞ*\n👤 {secilen_musteri}\n📌 {is_notu}\n🗓 {tarih_str} {saat_str}")
                
                # Müşteriye mesaj
                if musteriye_gonderilsin_mi and bulunan_numaralar:
                    msg = f"Sayın *{secilen_musteri}*,\n\nİşleminiz ({is_notu}) iş takvimimize alınmıştır.\n\nBilgilerinize.\n*Mali Müşavirlik Ofisi*"
                    for num in bulunan_numaralar: whatsapp_gonder(num, msg)
                    st.success("Mükellefe bilgi verildi.")
                
                st.balloons()
            except Exception as e:
                st.error(f"Hata oluştu: {e}")

# --- TAB 2: İŞ YÖNETİMİ ---
with tab2:
    st.subheader("📋 Bekleyen İşler")
    
    if st.button("🔄 Listeyi Yenile"):
        st.rerun()

    try:
        raw_data = ana_verileri_getir()
        df = pd.DataFrame(raw_data)
        
        # Eğer tablo boşsa veya başlıklar yoksa uyar
        if df.empty:
            st.info("Henüz kayıtlı bir iş yok. (Veya 'Sayfa1' başlıkları eksik)")
        elif "Durum" not in df.columns:
            st.error("⚠️ HATA: Google Sheet 'Sayfa1' içinde 'Durum' sütunu bulunamadı! Lütfen başlıkları ekleyin.")
            st.write("Olması gereken başlıklar: Tarih | Saat | Is Tanimi | Mesaj Durumu | Durum")
        else:
            # Sadece Bekleyenleri Göster
            bekleyenler = df[df["Durum"] != "Tamamlandi"]
            
            if not bekleyenler.empty:
                st.dataframe(bekleyenler[["Tarih", "Saat", "Is Tanimi", "Durum"]], use_container_width=True)
                
                st.write("---")
                st.subheader("✅ İşi Tamamla")
                
                # İş Seçimi
                is_listesi = bekleyenler["Is Tanimi"].tolist()
                secilen_is = st.selectbox("Tamamlanan İşi Seç:", is_listesi)
                
                final_mesaj = st.checkbox("🎉 Mükellefe 'Tamamlandı' mesajı gönder")
                
                if st.button("🏁 İşi Bitir"):
                    sheet = google_sheet_baglan()
                    tum_veriler = sheet.get_all_values()
                    
                    # Satırı bul
                    satir_no = 0
                    for i, row in enumerate(tum_veriler):
                        # row[2] -> Is Tanimi sütunu
                        if len(row) > 2 and row[2] == secilen_is:
                            satir_no = i + 1
                            break
                    
                    if satir_no > 0:
                        # Durum sütununu (E sütunu -> 5. sütun) güncelle
                        sheet.update_cell(satir_no, 5, "Tamamlandi")
                        st.success(f"'{secilen_is}' tamamlandı olarak işaretlendi!")
                        
                        if final_mesaj:
                            # İsimden numarayı bul
                            musteri_adi = secilen_is.split(" - ")[0]
                            df_mus = musterileri_getir()
                            satir = df_mus[df_mus["Ad Soyad"] == musteri_adi]
                            if not satir.empty:
                                nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                                msg = f"Sayın *{musteri_adi}*,\n\nİşleminiz ({secilen_is.split(' - ')[1]}) tamamlanmıştır.\n\nİyi günler dileriz.\n*Mali Müşavirlik Ofisi*"
                                for n in nums: whatsapp_gonder(n, msg)
                                st.success("Mükellefe tamamlandı mesajı gönderildi.")
                        
                        st.rerun()
                    else:
                        st.error("İş satırı bulunamadı.")
            else:
                st.info("Harika! Bekleyen hiç işiniz yok. Hepsi tamamlanmış. ☕️")

    except Exception as e:
        st.error(f"Veri okuma hatası: {e}")
