import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import pandas as pd
import re
from datetime import datetime

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
        return pd.DataFrame()

def ana_verileri_getir():
    sheet = google_sheet_baglan()
    return sheet.get_all_records()

# --- SAYFA TASARIMI ---
st.set_page_config(page_title="İş Asistanı", page_icon="💼", layout="wide")
st.title("👨‍💼 Mobil İş Takip Asistanı")

# Sekmeler: İş Ekle | Yönet | Defter (Yeni) | Analiz
tab1, tab2, tab3, tab4 = st.tabs(["➕ Yeni İş Ekle", "✅ İşleri Yönet", "📒 Müşteri Defteri", "📊 Patron Paneli"])

# --- TAB 1: İŞ EKLEME ---
with tab1:
    with st.form("is_formu", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1: tarih = st.date_input("Tarih")
        with col2: saat = st.time_input("Saat")
        
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
                        st.caption(f"📞 Kayıtlı Numara Sayısı: {len(bulunan_numaralar)}")
        else:
            secilen_musteri = st.text_input("Müşteri Adı (Manuel)")
            st.warning("⚠️ Müşteri listesi boş.")

        is_notu = st.text_input("Yapılacak İş / Not", placeholder="Örn: KDV Beyannamesi")
        st.write("---")
        musteriye_gonderilsin_mi = st.checkbox("📨 Mükellefe Bildirim Gönder")
        
        submit_btn = st.form_submit_button("✅ Kaydet ve Başlat")

        if submit_btn and is_notu:
            try:
                sheet = google_sheet_baglan()
                tarih_str = tarih.strftime("%d.%m.%Y")
                saat_str = saat.strftime("%H:%M")
                tam_is_tanimi = f"{secilen_musteri} - {is_notu}"
                
                sheet.append_row([tarih_str, saat_str, tam_is_tanimi, "Gonderildi", "Bekliyor"])
                st.info("✅ İş sisteme girildi.")
                
                whatsapp_gonder(GRUP_ID, f"📅 *YENİ İŞ*\n👤 {secilen_musteri}\n📌 {is_notu}\n🗓 {tarih_str} {saat_str}")
                
                if musteriye_gonderilsin_mi and bulunan_numaralar:
                    msg = f"Sayın *{secilen_musteri}*,\n\nİşleminiz ({is_notu}) iş takvimimize alınmıştır.\n\nBilgilerinize.\n*Mali Müşavirlik Ofisi*"
                    for num in bulunan_numaralar: whatsapp_gonder(num, msg)
                    st.success("Mükellefe iletildi.")
                
                st.balloons()
            except Exception as e:
                st.error(f"Hata: {e}")

# --- TAB 2: İŞ YÖNETİMİ ---
with tab2:
    st.subheader("📋 İş Listesi ve Durum Yönetimi")
    if st.button("🔄 Yenile", key="yenile_btn"): st.rerun()

    try:
        raw_data = ana_verileri_getir()
        df = pd.DataFrame(raw_data)
        
        if df.empty or "Durum" not in df.columns:
            st.info("Henüz veri yok veya başlıklar eksik.")
        else:
            bekleyenler = df[df["Durum"] != "Tamamlandi"]
            if not bekleyenler.empty:
                st.dataframe(bekleyenler[["Tarih", "Is Tanimi", "Durum"]], use_container_width=True)
                
                st.divider()
                st.markdown("### 🏁 İş Bitirme Ekranı")
                
                secilen_is = st.selectbox("Tamamlanan İşi Seç:", bekleyenler["Is Tanimi"].tolist())
                final_mesaj = st.checkbox("🎉 Müşteriye 'Bitti' mesajı at")
                
                if st.button("İşi Bitir ve Arşivle"):
                    sheet = google_sheet_baglan()
                    tum_veriler = sheet.get_all_values()
                    satir_no = 0
                    for i, row in enumerate(tum_veriler):
                        if len(row) > 2 and row[2] == secilen_is:
                            satir_no = i + 1
                            break
                    
                    if satir_no > 0:
                        sheet.update_cell(satir_no, 5, "Tamamlandi")
                        st.success("İş tamamlandı!")
                        if final_mesaj:
                            musteri_adi = secilen_is.split(" - ")[0]
                            df_mus = musterileri_getir()
                            satir = df_mus[df_mus["Ad Soyad"] == musteri_adi]
                            if not satir.empty:
                                nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                                msg = f"Sayın *{musteri_adi}*,\n\nİşleminiz ({secilen_is.split(' - ')[1]}) tamamlanmıştır.\n\nTeşekkürler.\n*Mali Müşavirlik Ofisi*"
                                for n in nums: whatsapp_gonder(n, msg)
                        st.rerun()
            else:
                st.success("Bekleyen hiç işiniz kalmadı. ☕️")

    except Exception as e:
        st.error(f"Hata: {e}")

# --- TAB 3: MÜŞTERİ DEFTERİ (YENİ!) ---
with tab3:
    st.header("📒 Müşteri Özel Defteri")
    
    # 1. Müşteri Seçimi
    df_musteriler = musterileri_getir()
    if not df_musteriler.empty:
        isim_listesi = df_musteriler["Ad Soyad"].tolist()
        secilen_musteri_defter = st.selectbox("Dosyasını Açmak İstediğiniz Mükellef:", isim_listesi, key="defter_secim")
        
        st.divider()
        
        # 2. Geçmişi Getir
        try:
            raw_data = ana_verileri_getir()
            df = pd.DataFrame(raw_data)
            
            if not df.empty and "Is Tanimi" in df.columns:
                # Sadece seçilen müşteriye ait kayıtları filtrele
                musteri_gecmisi = df[df["Is Tanimi"].str.contains(secilen_musteri_defter, na=False)]
                
                col_a, col_b = st.columns([2, 1])
                
                with col_a:
                    st.subheader(f"📜 {secilen_musteri_defter} - Geçmiş Hareketler")
                    if not musteri_gecmisi.empty:
                        # Tabloyu göster
                        st.dataframe(musteri_gecmisi[["Tarih", "Is Tanimi", "Durum"]], use_container_width=True)
                    else:
                        st.info("Bu mükellef için henüz bir kayıt bulunmuyor.")
                
                # 3. Özel Not Ekleme Bölümü
                with col_b:
                    st.markdown("### 📝 Görüşme Notu Ekle")
                    with st.form("not_formu", clear_on_submit=True):
                        st.caption("Buraya eklenen notlar 'Tamamlandı' olarak kaydedilir ve müşteriye mesaj gitmez.")
                        not_icerik = st.text_area("Görüşme Detayı / Not", placeholder="Örn: Banka kredisi için bilanço istedi...")
                        not_tarih = st.date_input("Not Tarihi")
                        
                        not_kaydet = st.form_submit_button("💾 Notu Arşive Ekle")
                        
                        if not_kaydet and not_icerik:
                            sheet = google_sheet_baglan()
                            t_str = not_tarih.strftime("%d.%m.%Y")
                            s_str = datetime.now().strftime("%H:%M")
                            # Not olduğunu belli etmek için başına [NOT] ekliyoruz
                            tam_not = f"{secilen_musteri_defter} - [NOT] {not_icerik}"
                            
                            # Direkt 'Tamamlandi' olarak ekliyoruz ki iş listesini kirletmesin
                            sheet.append_row([t_str, s_str, tam_not, "Gonderilmedi", "Tamamlandi"])
                            st.success("Not deftere işlendi!")
                            st.rerun()

        except Exception as e:
            st.error(f"Defter okunurken hata: {e}")
    else:
        st.warning("Müşteri listesi boş.")

# --- TAB 4: PATRON PANELİ ---
with tab4:
    st.header("📊 Ofis Performans Raporu")
    
    try:
        raw_data = ana_verileri_getir()
        df = pd.DataFrame(raw_data)
        
        if not df.empty and "Durum" in df.columns:
            toplam_is = len(df)
            biten_is = len(df[df["Durum"] == "Tamamlandi"])
            bekleyen_is = len(df[df["Durum"] != "Tamamlandi"])
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Toplam Kayıt", toplam_is)
            c2.metric("✅ Tamamlanan/Notlar", biten_is)
            c3.metric("⏳ Bekleyen İşler", bekleyen_is, delta_color="inverse")
            
            st.divider()
            st.subheader("🏆 Müşteri Yoğunluk Analizi")
            df['Musteri_Adi'] = df['Is Tanimi'].apply(lambda x: x.split(" - ")[0] if " - " in str(x) else "Diğer")
            st.bar_chart(df['Musteri_Adi'].value_counts())
            
    except Exception as e:
        st.error(f"Analiz Hatası: {e}")
