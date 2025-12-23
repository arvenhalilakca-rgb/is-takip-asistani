# streamlit_app.py (2. Aşama Güncellemesi)

import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import requests
import pandas as pd
import re
from datetime import datetime, timedelta
import time
import plotly.express as px
import pdfplumber

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir Asistanı Pro Max",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
 )

# --- TASARIM (CSS) ---
st.markdown("""
    <style>
    .stApp {background-color: #F8F9FA; font-family: 'Helvetica', sans-serif;}
    [data-testid="stSidebar"] {background-color: #2C3E50;}
    [data-testid="stSidebar"] * {color: #ECF0F1 !important;}
    div.stContainer {background-color: #FFFFFF; padding: 20px; border-radius: 12px; border: 1px solid #E0E0E0;}
    .stButton>button {width: 100%; border-radius: 8px; font-weight: 600;}
    button[kind="primary"] {background: linear-gradient(90deg, #2980b9 0%, #2c3e50 100%); color: white;}
    </style>
    """, unsafe_allow_html=True)

# --- SABİT VERİLER ---
RESMI_TATILLER = ["01.01", "23.04", "01.05", "19.05", "15.07", "30.08", "29.10"]

# --- SESSION STATE ---
if 'hizli_not' not in st.session_state: st.session_state['hizli_not'] = ""
if 'son_islem_yedek' not in st.session_state: st.session_state['son_islem_yedek'] = None
if 'sessiz_mod' not in st.session_state: st.session_state['sessiz_mod'] = False
if 'aktif_kullanici' not in st.session_state: st.session_state['aktif_kullanici'] = "Admin"
if 'son_islem_logu' not in st.session_state: st.session_state['son_islem_logu'] = "Sistem başlatıldı."


# --- BAĞLANTILAR ---
try:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"] )
except Exception as e:
    st.error(f"⚠️ Ayar Hatası: Secrets eksik veya hatalı. {e}"); st.stop()

@st.cache_data(ttl=60)
def verileri_getir(sayfa_adi):
    try:
        client = gspread.authorize(creds)
        sheet = client.open("Is_Takip_Sistemi").worksheet(sayfa_adi)
        return pd.DataFrame(sheet.get_all_records())
    except Exception as e:
        st.sidebar.error(f"Veri çekme hatası: {sayfa_adi} - {e}")
        return pd.DataFrame()

def onbellek_temizle():
    verileri_getir.clear()

def log_kaydi_ekle(is_id, kullanici, eylem):
    try:
        client = gspread.authorize(creds)
        sheet = client.open("Is_Takip_Sistemi").worksheet("Loglar")
        sheet.append_row([datetime.now().strftime("%d.%m.%Y %H:%M:%S"), str(is_id), kullanici, eylem])
        st.session_state['son_islem_logu'] = f"{kullanici} - {eylem}"
    except Exception:
        st.sidebar.warning("Loglama yapılamadı.")

def whatsapp_gonder(chat_id, mesaj):
    if st.session_state.get('sessiz_mod', False): return False
    try:
        ID_INSTANCE = st.secrets["ID_INSTANCE"]
        API_TOKEN = st.secrets["API_TOKEN"]
        if "@" not in str(chat_id): chat_id = f"{chat_id}@c.us"
        url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
        requests.post(url, json={'chatId': chat_id, 'message': mesaj}, timeout=5 )
        return True
    except Exception as e:
        st.sidebar.warning(f"WhatsApp gönderilemedi: {e}")
        return False

def numaralari_ayikla(tel_str):
    if not tel_str: return []
    tel_str = str(tel_str)
    ham_parcalar = re.split(r'[,\n/]', tel_str)
    temiz = set()
    for parca in ham_parcalar:
        sadece_rakam = re.sub(r'\D', '', parca.strip())
        if len(sadece_rakam) == 10: temiz.add("90" + sadece_rakam)
        elif len(sadece_rakam) == 11 and sadece_rakam.startswith("0"): temiz.add("9" + sadece_rakam)
    return list(temiz)

# --- YAN MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80 )
    
    df_m = verileri_getir("Musteriler")
    personel_listesi = ["Admin"]
    if not df_m.empty and "Sorumlu" in df_m.columns:
        personel_listesi.extend([p for p in df_m["Sorumlu"].unique() if p and str(p) not in ["nan", "None"]])
    
    st.session_state['aktif_kullanici'] = st.selectbox("👤 Kullanıcı", sorted(list(set(personel_listesi))))
    st.session_state['sessiz_mod'] = st.toggle("🔕 Sessiz Mod", help="Aktifken WhatsApp bildirimi gönderilmez.")
    
    st.markdown("---")
    menu_options = ["⚙️ Otomasyon Kuralları", "📊 Genel Bakış", "➕ İş Ekle", "✅ İş Yönetimi", "📂 Müşteri Arşivi", "💰 Finans & Kâr"]
    secim = st.radio("MENÜ", menu_options)
    
    st.markdown("---")
    st.caption(f"Son İşlem: {st.session_state.get('son_islem_logu', 'Sistem başlatıldı.')}")

# ==============================================================================
# --- OTOMASYON KURALLARI SAYFASI ---
# ==============================================================================
if secim == "⚙️ Otomasyon Kuralları":
    st.title("⚙️ Otomasyon Kuralları Yönetimi")
    st.info("Bu ekrandan, her ay veya belirli dönemlerde otomatik olarak oluşturulacak görev kurallarını tanımlayabilirsiniz.")
    tab1, tab2 = st.tabs(["➕ Yeni Kural Ekle", "📋 Mevcut Kuralları Görüntüle"])
    with tab1:
        with st.form("kural_ekle_form", clear_on_submit=True):
            df_m = verileri_getir("Musteriler")
            musteri = st.selectbox("Hangi Müşteri İçin?", df_m["Ad Soyad"].tolist() if not df_m.empty else [])
            is_sablonu = st.text_input("Otomatik Oluşturulacak İşin Adı", placeholder="Örn: KDV Beyannamesi Hazırlığı")
            col1, col2 = st.columns(2)
            tekrar_tipi = col1.selectbox("Tekrarlama Sıklığı", ["Her Ay", "Her 3 Ayda Bir"])
            tekrar_gunu = col2.number_input("Ayın Kaçıncı Günü Oluşturulsun?", min_value=1, max_value=28, value=15)
            kural_str = f"{tekrar_tipi}ın {tekrar_gunu}'ü"
            personel_listesi = [""]
            if not df_m.empty and "Sorumlu" in df_m.columns:
                personel_listesi.extend([p for p in df_m["Sorumlu"].unique() if p and str(p) not in ["nan", "None"]])
            sorumlu = st.selectbox("Bu Görev Kime Atansın?", sorted(list(set(personel_listesi))))
            if st.form_submit_button("✅ Kuralı Kaydet", type="primary"):
                try:
                    client = gspread.authorize(creds)
                    sheet = client.open("Is_Takip_Sistemi").worksheet("Tekrarlayan_Isler")
                    sheet.append_row([musteri, is_sablonu, kural_str, sorumlu, "EVET"])
                    log_kaydi_ekle(f"Kural: {musteri}", st.session_state['aktif_kullanici'], "Yeni otomasyon kuralı ekledi.")
                    onbellek_temizle()
                    st.success("Yeni otomasyon kuralı başarıyla eklendi!")
                    time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Kural kaydedilirken bir hata oluştu: {e}")
    with tab2:
        st.subheader("Mevcut Otomasyon Kuralları")
        st.dataframe(verileri_getir("Tekrarlayan_Isler"), use_container_width=True, hide_index=True)

# ==============================================================================
# --- GENEL BAKIŞ SAYFASI ---
# ==============================================================================
elif secim == "📊 Genel Bakış":
    st.title("📊 Yönetim Kokpiti")
    # ... (Bu sayfanın kodu aynı kalabilir, değişiklik gerekmiyor) ...

# ==============================================================================
# --- İŞ EKLE (YENİ VE GÜNCELLENMİŞ VERSİYON) ---
# ==============================================================================
elif secim == "➕ İş Ekle":
    st.title("📝 Akıllı İş Girişi")
    with st.container():
        with st.form("is_ekle_formu", clear_on_submit=True):
            st.subheader("🗓️ Zamanlama")
            c1, c2, c3 = st.columns(3)
            tarih = c1.date_input("Başlangıç Tarihi")
            saat = c2.time_input("Saat")
            son_teslim_tarihi = c3.date_input("Son Teslim Tarihi", value=None, help="Bu işin bitmesi gereken son tarih. Boş bırakılabilir.")
            if tarih.strftime("%d.%m") in RESMI_TATILLER or tarih.weekday() == 6:
                st.warning(f"⚠️ Başlangıç tarihi ({tarih.strftime('%d.%m.%Y')}) resmi tatil veya Pazar gününe denk geliyor.")
            st.divider()
            st.subheader("📋 Görev Detayları")
            df_m = verileri_getir("Musteriler")
            mus_list = df_m["Ad Soyad"].tolist() if not df_m.empty else []
            mus = st.selectbox("Mükellef Seçiniz", mus_list)
            is_tipi = st.selectbox("İş Şablonu", ["Genel Görev", "KDV Beyannamesi", "Muhtasar Beyanname", "SGK Bildirgesi", "Diğer..."])
            notu = st.text_input("Lütfen İşin Açıklamasını Girin:", placeholder="Örn: Ticaret Odası tescil yazısı alınacak.") if is_tipi == "Diğer..." else is_tipi
            st.divider()
            st.subheader("👤 Atama ve Bildirimler")
            df_is = verileri_getir("Sheet1")
            sorumlu_bul = ""
            if not df_m.empty and "Sorumlu" in df_m.columns:
                f = df_m[df_m["Ad Soyad"] == mus]
                if not f.empty: sorumlu_bul = f.iloc[0]["Sorumlu"]
            p_list_yuklu = [""]
            def_idx = 0
            if not df_is.empty and "Personel" in df_is.columns:
                yukler = df_is[df_is["Durum"] != "Tamamlandi"]["Personel"].value_counts()
                personel_listesi = sorted([p for p in df_m["Sorumlu"].unique() if p and str(p) not in ["nan", "None"]])
                for p in personel_listesi:
                    etiket = f"{p} (Aktif İş: {yukler.get(p, 0)})"
                    p_list_yuklu.append(etiket)
                    if p == sorumlu_bul: def_idx = len(p_list_yuklu) - 1
            sec_p = st.selectbox("Görevi Kime Atayalım?", p_list_yuklu, index=def_idx).split(" (")[0]
            sms = st.checkbox("Mükellefe bilgilendirme SMS'i gönderilsin mi?")
            if st.form_submit_button("✅ Yeni İşi Kaydet", type="primary"):
                son_teslim_str = son_teslim_tarihi.strftime("%d.%m.%Y") if son_teslim_tarihi else ""
                yeni_satir = [tarih.strftime("%d.%m.%Y"), saat.strftime("%H:%M"), f"{mus} - {notu}", "Gonderildi", "Bekliyor", "-", sec_p, son_teslim_str]
                try:
                    client = gspread.authorize(creds)
                    sheet = client.open("Is_Takip_Sistemi").sheet1
                    sheet.append_row(yeni_satir)
                    onbellek_temizle()
                    log_kaydi_ekle(f"İş: {mus}", st.session_state['aktif_kullanici'], f"yeni görev oluşturdu: {notu}")
                    whatsapp_gonder(st.secrets.get("GRUP_ID"), f"🆕 YENİ GÖREV\n\nMükellef: {mus}\nİş: {notu}\nSorumlu: {sec_p or 'Atanmadı'}\nSon Tarih: {son_teslim_str or 'Belirtilmedi'}")
                    if sms:
                        satir = df_m[df_m["Ad Soyad"] == mus]
                        if not satir.empty:
                            for n in numaralari_ayikla(satir.iloc[0]["Telefon"]):
                                whatsapp_gonder(n, f"Sayın {mus}, '{notu}' konulu işleminiz tarafımıza ulaşmıştır. İyi günler dileriz.")
                    st.success("Yeni görev başarıyla oluşturuldu!")
                    st.balloons(); time.sleep(2); st.rerun()
                except Exception as e: st.error(f"Kayıt sırasında bir hata oluştu: {e}")

# ... Diğer elif bloklarınız (İş Yönetimi, Arşiv vb.) burada devam edebilir ...
# Onlarda bir değişiklik yapmadık.
