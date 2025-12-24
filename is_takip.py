import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import pandas as pd
import re
from datetime import datetime
import time
from streamlit_option_menu import option_menu

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Müşavir İletişim Kulesi",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TASARIM (CSS - MODERN & WHATSAPP STİLİ) ---
st.markdown("""
    <style>
    .stApp {background-color: #e5ddd5; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;}
    [data-testid="stSidebar"] {background-color: #FFFFFF; border-right: 1px solid #E0E0E0;}
    
    /* WhatsApp Mesaj Balonu Stili */
    .chat-container {
        background-image: url('https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png');
        background-repeat: repeat;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        min-height: 300px;
    }
    .message-bubble {
        background-color: #dcf8c6;
        padding: 10px 15px;
        border-radius: 8px;
        box-shadow: 0 1px 1px rgba(0,0,0,0.1);
        max-width: 80%;
        margin-bottom: 10px;
        position: relative;
        float: right;
        clear: both;
    }
    .message-text {
        color: #303030;
        font-size: 14px;
        line-height: 1.4;
    }
    .message-time {
        font-size: 11px;
        color: #999;
        text-align: right;
        margin-top: 5px;
    }
    
    /* Kart Tasarımları */
    .kisi-karti {
        background-color: white; padding: 10px; border-radius: 8px; 
        border-left: 5px solid #128C7E; margin-bottom: 5px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
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
    "Serbest Metin": "",
    "KDV Tahakkuk": "Sayın {isim}, {ay} dönemi KDV beyannameniz onaylanmıştır. Tahakkuk fişiniz ektedir. Ödemenizi vadesinde yapmanızı rica ederiz.",
    "SGK Bildirge": "Sayın {isim}, {ay} dönemi SGK hizmet listeniz ve tahakkuk fişiniz ektedir.",
    "Bayram Kutlaması": "Sayın {isim}, aileniz ve sevdiklerinizle birlikte sağlıklı, huzurlu ve mutlu bir bayram geçirmenizi dileriz.",
    "Genel Duyuru": "Sayın Mükellefimiz {isim}, mevzuatta yapılan son değişiklikler hakkında bilgilendirme...",
    "Tasdik Ödenmedi (RESMİ UYARI)": "Sayın Mükellefimiz {isim}, 2026 yılı Defter Tasdik ve Yazılım Giderleri ücretiniz ({tutar} TL) daha önce tarafınıza bildirildiği ancak ödenmediği için defterleriniz notere teslim EDİLMEMİŞTİR. Bugün SON GÜN. Cezalı duruma düşmemek için acilen ödeme yapmanızı rica ederiz.",
}

# --- SESSION YÖNETİMİ ---
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
    except Exception as e:
        return False, str(e)

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
        return "{:,.0f}".format(val).replace(",", ".")
    except: return str(deger)

# --- YAN MENÜ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.markdown("### İLETİŞİM KULESİ")
    secim = option_menu(
        menu_title=None,
        options=["Profesyonel Mesaj", "Tasdik Robotu", "Veri Yükle"],
        icons=["whatsapp", "robot", "cloud-upload"],
        menu_icon="cast", default_index=0,
        styles={"container": {"padding": "0!important"}}
    )
    st.info("💡 Tüm sistem 'PLANLAMA 2026.xlsx' dosyasındaki Ünvan ve 1.NUMARA sütunlarını kullanır.")

# --- VERİ KONTROLÜ VE YÜKLEME ---
# Eğer veri yoksa ve kullanıcı Veri Yükle sekmesinde değilse, uyar.
if st.session_state['tasdik_data'] is None and secim != "Veri Yükle":
    st.warning("⚠️ Lütfen önce 'Veri Yükle' menüsünden Excel listenizi yükleyin.")
    secim = "Veri Yükle" # Zorla oraya gönder

# --- 1. VERİ YÜKLEME (MERKEZİ) ---
if secim == "Veri Yükle":
    st.title("📂 Müşteri Veritabanı")
    st.info("İşlem yapmak için Excel dosyanızı (PLANLAMA 2026) buraya yükleyin. Sistem hem Tasdik Robotu hem de Mesajlaşma için bu listeyi kullanacak.")
    
    up = st.file_uploader("Dosyayı Sürükle Bırak (XLSX / CSV)", type=["xlsx", "xls", "csv"])
    if up:
        try:
            if up.name.endswith('.csv'): df = pd.read_csv(up)
            else: df = pd.read_excel(up)
            
            # Tahsilat Sütunu Kontrolü
            if "Para Alındı mı" in df.columns:
                df["Tahsil_Edildi"] = df["Para Alındı mı"].apply(lambda x: True if pd.notna(x) and str(x).strip() != "" else False)
            else:
                df["Tahsil_Edildi"] = False
            
            # Tutar düzeltme
            if "Defter Tasdik Ücreti" not in df.columns: df["Defter Tasdik Ücreti"] = 0
            
            # İsim ve Numara Kontrolü
            if "Ünvan / Ad Soyad" in df.columns and "1.NUMARA" in df.columns:
                st.session_state['tasdik_data'] = df
                st.success(f"✅ Liste Yüklendi! {len(df)} kişi hafızaya alındı.")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Excel dosyasında 'Ünvan / Ad Soyad' veya '1.NUMARA' sütunları bulunamadı.")
                st.write("Bulunan Sütunlar:", df.columns.tolist())
                
        except Exception as e: st.error(f"Hata: {e}")
    
    if st.session_state['tasdik_data'] is not None:
        st.write("📋 Şu an yüklü liste önizlemesi:")
        st.dataframe(st.session_state['tasdik_data'].head())
        if st.button("Listeyi Sıfırla"):
            st.session_state['tasdik_data'] = None
            st.rerun()

# --- 2. PROFESYONEL MESAJ (DOSYA & RESİM) ---
elif secim == "Profesyonel Mesaj":
    st.title("📤 Profesyonel Mesaj Merkezi")
    
    if st.session_state['tasdik_data'] is not None:
        df_m = st.session_state['tasdik_data']
        
        col_form, col_preview = st.columns([1.2, 1])
        
        with col_form:
            st.subheader("1. Gönderim Ayarları")
            gonderim_turu = st.radio("Kime Gönderilecek?", ["Tek Müşteri", "Toplu Gönderim (Tüm Liste)"], horizontal=True)
            
            secilen_musteriler = []
            if gonderim_turu == "Tek Müşteri":
                # Burası artık Excel'den gelen isimleri kullanıyor
                secilen_kisi = st.selectbox("Müşteri Seç:", df_m["Ünvan / Ad Soyad"].tolist())
                secilen_musteriler = [secilen_kisi]
            else:
                secilen_musteriler = df_m["Ünvan / Ad Soyad"].tolist()
                st.warning(f"Dikkat: Listede bulunan {len(secilen_musteriler)} kişiye mesaj gidecek!")
            
            st.markdown("---")
            
            st.subheader("2. İçerik Hazırla")
            sablon = st.selectbox("Hazır Şablon:", list(MESAJ_SABLONLARI.keys()))
            mesaj_icerik = st.text_area("Mesaj Metni:", value=MESAJ_SABLONLARI[sablon], height=150)
            
            dosya_ekle = st.toggle("📎 Dosya / Resim Ekle")
            uploaded_file = None
            if dosya_ekle:
                uploaded_file = st.file_uploader("Dosya Seç (PDF, JPG, PNG, XLSX)", type=["pdf", "jpg", "png", "jpeg", "xlsx"])
        
        with col_preview:
            st.subheader("📱 WhatsApp Önizleme")
            ornek_isim = secilen_musteriler[0] if secilen_musteriler else "Mükellef Adı"
            
            # Defter Tasdik Tutarı varsa onu bulalım (Önizleme için)
            ornek_tutar = "0"
            if not df_m.empty:
                satir = df_m[df_m["Ünvan / Ad Soyad"] == ornek_isim]
                if not satir.empty:
                    ornek_tutar = para_formatla(satir.iloc[0].get("Defter Tasdik Ücreti", 0))

            final_mesaj = mesaj_icerik.replace("{isim}", str(ornek_isim))\
                                      .replace("{ay}", datetime.now().strftime("%B"))\
                                      .replace("{tutar}", str(ornek_tutar))
            
            st.markdown(f"""
            <div class="chat-container">
                <div class="message-bubble">
                    {'<div style="background:white; padding:5px; border-radius:5px; margin-bottom:5px;">📎 <b>' + uploaded_file.name + '</b><br><small>Dosya Eklendi</small></div>' if uploaded_file else ''}
                    <div class="message-text">{final_mesaj}</div>
                    <div class="message-time">{datetime.now().strftime("%H:%M")} ✓✓</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            if st.button("🚀 GÖNDERİMİ BAŞLAT", type="primary"):
                bar = st.progress(0)
                basarili = 0
                
                for i, musteri in enumerate(secilen_musteriler):
                    # Excel'den Numarayı Bul
                    satir = df_m[df_m["Ünvan / Ad Soyad"] == musteri]
                    if not satir.empty:
                        # 1.NUMARA sütununu kullanıyoruz
                        tel_raw = satir.iloc[0].get("1.NUMARA", "")
                        tutar_raw = para_formatla(satir.iloc[0].get("Defter Tasdik Ücreti", 0))
                        
                        tels = numaralari_ayikla(tel_raw)
                        
                        # Mesajı kişiye özel hale getir
                        kisi_mesaj = mesaj_icerik.replace("{isim}", str(musteri))\
                                                 .replace("{ay}", datetime.now().strftime("%B"))\
                                                 .replace("{tutar}", str(tutar_raw))
                        
                        for t in tels:
                            if uploaded_file:
                                uploaded_file.seek(0)
                                s, m = whatsapp_dosya_gonder(t, uploaded_file, uploaded_file.name, kisi_mesaj)
                            else:
                                s, m = whatsapp_text_gonder(t, kisi_mesaj)
                            
                            if not s: print(f"Hata ({musteri}): {m}") # Konsola log
                        
                        if tels: basarili += 1
                    
                    bar.progress((i+1)/len(secilen_musteriler))
                    time.sleep(0.5) 
                
                st.success(f"İşlem Tamam! {basarili} kişiye gönderim yapıldı.")

# --- 3. TASDİK ROBOTU (OPERASYONEL) ---
elif secim == "Tasdik Robotu":
    st.title("🤖 Tasdik Operasyon Merkezi")
    
    if st.session_state['tasdik_data'] is not None:
        df = st.session_state['tasdik_data']
        
        # Üst Panel
        c1, c2 = st.columns(2)
        odenmeyen = len(df[df["Tahsil_Edildi"]==False])
        c1.metric("🔴 Ödemeyen (Borçlu)", odenmeyen)
        c2.metric("🟢 Ödeyen (Tamam)", len(df) - odenmeyen)
        st.divider()

        st.subheader("1. Tahsilat Listesi (Ödemeyi İşaretle)")
        edited_df = st.data_editor(
            df[["Ünvan / Ad Soyad", "Defter Tasdik Ücreti", "Tahsil_Edildi"]],
            column_config={
                "Tahsil_Edildi": st.column_config.CheckboxColumn("Tahsil Edildi mi?", default=False),
                "Defter Tasdik Ücreti": st.column_config.NumberColumn("Tutar", format="%.2f TL"),
                "Ünvan / Ad Soyad": st.column_config.TextColumn("Mükellef", disabled=True)
            },
            hide_index=True, use_container_width=True, height=300
        )
        
        if st.button("💾 Tahsilatları Kaydet", type="primary"):
            st.session_state['tasdik_data'].update(edited_df)
            st.success("Liste Güncellendi!"); time.sleep(0.5); st.rerun()
            
        st.divider()
        st.subheader("2. Mesaj Gönderimi (Sadece Ödemeyenler)")
        
        borclular = st.session_state['tasdik_data'][st.session_state['tasdik_data']["Tahsil_Edildi"] == False]
        
        if borclular.empty: st.success("🎉 Borçlu kalmadı.")
        else:
            mesaj_turu = st.selectbox("Uyarı Şablonu:", ["Tasdik Ödenmedi (RESMİ UYARI)", "Kibar Hatırlatma"])
            sablon = MESAJ_SABLONLARI[mesaj_turu]
            
            for index, row in borclular.iterrows():
                isim = row["Ünvan / Ad Soyad"]
                tutar = para_formatla(row.get("Defter Tasdik Ücreti", 0))
                tel = row.get("1.NUMARA", "")
                
                col_info, col_btn = st.columns([3, 1])
                with col_info:
                    st.markdown(f"<div class='kisi-karti'><b>{isim}</b><br>Borç: {tutar} TL | {tel}</div>", unsafe_allow_html=True)
                with col_btn:
                    if st.button(f"📲 Gönder", key=f"btn_{index}"):
                        tels = numaralari_ayikla(str(tel))
                        if tels:
                            msg = sablon.replace("{isim}", str(isim)).replace("{tutar}", str(tutar))
                            for t in tels: whatsapp_text_gonder(t, msg)
                            st.toast(f"{isim}: İletildi ✅", icon="✅")
                        else: st.toast("Numara Yok ❌", icon="❌")
