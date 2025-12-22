import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import pandas as pd
import re
from datetime import datetime

# --- SAYFA AYARLARI (İLK SATIR OLMALI) ---
st.set_page_config(
    page_title="Müşavir Asistanı",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TASARIM İÇİN CSS (SİHİRLİ DOKUNUŞ) ---
st.markdown("""
    <style>
    /* Ana arka planı hafif gri yapalım ki kartlar öne çıksın */
    .stApp {background-color: #f8f9fa;}
    
    /* Yan menü (Sidebar) rengi */
    [data-testid="stSidebar"] {
        background-color: #2c3e50;
    }
    [data-testid="stSidebar"] * {
        color: white !important;
    }
    
    /* Kart Görünümü (Beyaz kutular) */
    div.block-container {padding-top: 2rem;}
    div[data-testid="stMetricValue"] {font-size: 28px;}
    
    /* Tablo başlıkları */
    thead tr th:first-child {display:none}
    tbody th {display:none}
    
    /* Butonları Güzelleştir */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- GÜVENLİK VE BAĞLANTILAR ---
try:
    ID_INSTANCE = st.secrets["ID_INSTANCE"]
    API_TOKEN = st.secrets["API_TOKEN"]
    GRUP_ID = st.secrets["GRUP_ID"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
except:
    st.error("⚠️ Bağlantı hatası: Şifreler eksik.")
    st.stop()

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

def verileri_getir(sayfa="Ana"):
    try:
        if sayfa == "Musteriler":
            sheet = google_sheet_baglan("Musteriler")
            return pd.DataFrame(sheet.get_all_records())
        else:
            sheet = google_sheet_baglan()
            return pd.DataFrame(sheet.get_all_records())
    except:
        return pd.DataFrame()

# --- SOL MENÜ TASARIMI ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    st.title("Müşavir Panel")
    st.markdown("---")
    secim = st.radio("MENÜ", ["📊 Genel Durum", "➕ Yeni İş Ekle", "✅ İş Yönetimi", "📒 Müşteri Defteri"])
    st.markdown("---")
    st.info("Sistem Aktif 🟢")

# --- 1. SAYFA: GENEL DURUM (DASHBOARD) ---
if secim == "📊 Genel Durum":
    st.markdown("## 📊 Ofis Performans Raporu")
    st.markdown("Bugünkü durum özeti aşağıdadır.")
    
    df = verileri_getir()
    if not df.empty and "Durum" in df.columns:
        col1, col2, col3, col4 = st.columns(4)
        
        toplam = len(df)
        biten = len(df[df["Durum"] == "Tamamlandi"])
        bekleyen = len(df[df["Durum"] != "Tamamlandi"])
        basari_orani = int((biten / toplam) * 100) if toplam > 0 else 0
        
        col1.metric("Toplam İş", f"{toplam} Adet", border=True)
        col2.metric("Tamamlanan", f"{biten} Adet", "✅", border=True)
        col3.metric("Bekleyen", f"{bekleyen} Adet", "⏳", delta_color="inverse", border=True)
        col4.metric("Başarı Oranı", f"%{basari_orani}", border=True)
        
        st.write("")
        col_g1, col_g2 = st.columns([2,1])
        
        with col_g1:
            st.subheader("🗓 Son Eklenen İşler")
            # Tabloyu renklendir
            st.dataframe(
                df[["Tarih", "Is Tanimi", "Durum"]].tail(5),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Durum": st.column_config.TextColumn(
                        "Durum",
                        help="İş Durumu",
                        validate="^(Tamamlandi|Bekliyor)$"
                    )
                }
            )
            
        with col_g2:
            st.subheader("🏆 Müşteri Yoğunluğu")
            df['Musteri'] = df['Is Tanimi'].apply(lambda x: x.split(" - ")[0] if " - " in str(x) else "Diğer")
            st.bar_chart(df['Musteri'].value_counts())

# --- 2. SAYFA: YENİ İŞ EKLE ---
elif secim == "➕ Yeni İş Ekle":
    st.markdown("## 📝 Yeni Görev Oluştur")
    
    with st.container(border=True):
        with st.form("is_formu", clear_on_submit=True):
            col1, col2 = st.columns(2)
            tarih = col1.date_input("Tarih")
            saat = col2.time_input("Saat")
            
            df_m = verileri_getir("Musteriler")
            isimler = df_m["Ad Soyad"].tolist() if not df_m.empty else []
            
            secilen_musteri = st.selectbox("Mükellef Seçiniz", isimler)
            
            # Telefon kontrolü
            bulunan_numaralar = []
            if secilen_musteri and not df_m.empty:
                satir = df_m[df_m["Ad Soyad"] == secilen_musteri]
                if not satir.empty:
                    bulunan_numaralar = numaralari_ayikla(satir.iloc[0]["Telefon"])
            
            is_notu = st.text_input("İş / Görev Tanımı", placeholder="Örn: KDV Beyannamesi hazırlanacak")
            
            st.markdown("---")
            col_b1, col_b2 = st.columns([3,1])
            sms_atilsin_mi = col_b1.checkbox("📨 Mükellefe bilgilendirme mesajı gönder")
            kaydet = st.form_submit_button("✅ Kaydet ve Sisteme İşle")
            
            if kaydet and is_notu:
                try:
                    sheet = google_sheet_baglan()
                    t_str = tarih.strftime("%d.%m.%Y")
                    s_str = saat.strftime("%H:%M")
                    tam_ad = f"{secilen_musteri} - {is_notu}"
                    
                    sheet.append_row([t_str, s_str, tam_ad, "Gonderildi", "Bekliyor"])
                    
                    whatsapp_gonder(GRUP_ID, f"📅 *YENİ İŞ*\n👤 {secilen_musteri}\n📌 {is_notu}\n🗓 {t_str} {s_str}")
                    
                    if sms_atilsin_mi and bulunan_numaralar:
                        msg = f"Sayın *{secilen_musteri}*,\n\nİşleminiz ({is_notu}) işleme alınmıştır.\n\n*Mali Müşavirlik Ofisi*"
                        for num in bulunan_numaralar: whatsapp_gonder(num, msg)
                        st.success("Mükellefe mesaj iletildi.")
                        
                    st.success("İşlem Başarılı! Kayıt oluşturuldu.")
                except Exception as e:
                    st.error(f"Hata: {e}")

# --- 3. SAYFA: İŞ YÖNETİMİ ---
elif secim == "✅ İş Yönetimi":
    st.markdown("## 📋 Görev Yönetim Merkezi")
    
    col_r1, col_r2 = st.columns([4,1])
    if col_r2.button("🔄 Listeyi Yenile"): st.rerun()
    
    df = verileri_getir()
    if not df.empty and "Durum" in df.columns:
        bekleyenler = df[df["Durum"] != "Tamamlandi"]
        
        if not bekleyenler.empty:
            # Şık Tablo Gösterimi
            st.dataframe(
                bekleyenler[["Tarih", "Saat", "Is Tanimi", "Durum"]],
                use_container_width=True,
                hide_index=True
            )
            
            st.write("")
            with st.container(border=True):
                st.subheader("🏁 İş Bitirme")
                c1, c2 = st.columns([3,1])
                
                secilen_is = c1.selectbox("Tamamlanan İşi Seçiniz:", bekleyenler["Is Tanimi"].tolist())
                final_msg = c1.checkbox("🎉 Mükellefe 'Tamamlandı' mesajı gönder")
                
                if c2.button("Tamamla 🏁"):
                    sheet = google_sheet_baglan()
                    rows = sheet.get_all_values()
                    for i, row in enumerate(rows):
                        if len(row) > 2 and row[2] == secilen_is:
                            sheet.update_cell(i+1, 5, "Tamamlandi")
                            
                            if final_msg:
                                # Mesaj atma kodu (basitleştirildi)
                                ad = secilen_is.split(" - ")[0]
                                df_m = verileri_getir("Musteriler")
                                satir = df_m[df_m["Ad Soyad"] == ad]
                                if not satir.empty:
                                    nums = numaralari_ayikla(satir.iloc[0]["Telefon"])
                                    for n in nums: whatsapp_gonder(n, f"Sayın {ad}, işleminiz tamamlanmıştır.")
                            
                            st.success("İşlem tamamlandı!")
                            st.rerun()
                            break
        else:
            st.success("Tebrikler! Bekleyen hiç işiniz yok.")

# --- 4. SAYFA: MÜŞTERİ DEFTERİ ---
elif secim == "📒 Müşteri Defteri":
    st.markdown("## 📂 Müşteri Arşivi")
    
    df_m = verileri_getir("Musteriler")
    if not df_m.empty:
        musteri = st.selectbox("Mükellef Seçiniz:", df_m["Ad Soyad"].tolist())
        
        st.markdown("---")
        
        df = verileri_getir()
        if not df.empty:
            ozel_veri = df[df["Is Tanimi"].str.contains(musteri, na=False)]
            
            c1, c2 = st.columns([2,1])
            with c1:
                st.subheader("📜 Geçmiş Hareketler")
                st.dataframe(ozel_veri[["Tarih", "Is Tanimi", "Durum"]], use_container_width=True, hide_index=True)
            
            with c2:
                with st.container(border=True):
                    st.subheader("📝 Özel Not Ekle")
                    with st.form("not_ekle"):
                        not_txt = st.text_area("Notunuz")
                        tarih_not = st.date_input("Tarih")
                        if st.form_submit_button("Notu Kaydet"):
                            sheet = google_sheet_baglan()
                            full_not = f"{musteri} - [NOT] {not_txt}"
                            sheet.append_row([tarih_not.strftime("%d.%m.%Y"), "-", full_not, "-", "Tamamlandi"])
                            st.success("Not eklendi.")
                            st.rerun()
