import streamlit as st
import pandas as pd
import re
import pdfplumber
import requests
import time

# ==========================================
# 1) AYARLAR & SABİTLER (MENÜ YAPISI BOZULMAZ)
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi (Canlı Akış & Akıllı Okuyucu)",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# WhatsApp (Green-API)
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

# Tek PDF içinde çoklu beyanname ayıracı
BEYANNAME_AYRACI = "KATMA DEĞER VERGİSİ BEYANNAMESİ"

# PDF şablonuna göre hedef ifadeler
MATRAH_AYLIK_IFADESI = "Teslim ve Hizmetlerin Karşılığını Teşkil Eden Bedel (aylık)"
KDV_TOPLAM_IFADESI = "Toplam Katma Değer Vergisi"
KDV_HESAPLANAN_IFADESI = "Hesaplanan Katma Değer Vergisi"
POS_SATIRI_IFADESI = "Kredi Kartı İle Tahsil Edilen"

# Risk eşiği (TL)
RISK_ESIK = 50.0

# ==========================================
# 2) CSS
# ==========================================
st.markdown("""
<style>
.stApp {background-color: #f4f6f9; font-family: 'Segoe UI', sans-serif;}
[data-testid="stSidebar"] {background-color: #fff; border-right: 1px solid #ddd;}
.card { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 10px; border: 1px solid #eee; }
.risk-card {border-left: 5px solid #d32f2f;}
.stat-val {font-weight: bold; font-size: 15px; color: #333;}
.stat-lbl {font-size: 11px; color: #777;}
.card-title {font-size: 16px; font-weight: bold; margin-bottom: 5px;}
.card-sub {font-size: 12px; color: #666; margin-bottom: 10px;}
.terminal-window {
    background-color: #1e1e1e; color: #f0f0f0; font-family: monospace;
    padding: 15px; border-radius: 8px; height: 320px; overflow-y: auto;
    font-size: 13px; margin-bottom: 20px; border: 1px solid #333; line-height: 1.6;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3) SESSION STATE
# ==========================================
if "sonuclar" not in st.session_state:
    st.session_state["sonuclar"] = None
if "mukellef_db" not in st.session_state:
    st.session_state["mukellef_db"] = None

# ==========================================
# 4) YARDIMCI FONKSİYONLAR
# ==========================================
def text_to_float(text) -> float:
    """
    TR format sayıları güvenle çevirir:
    203.922,89 / 1.211.645,59 / 206183,59 / 810,00 / 123456
    """
    try:
        if text is None:
            return 0.0
        t = str(text).strip().replace("\u00a0", " ")
        t = re.sub(r"[^0-9\.,]", "", t)
        if not t:
            return 0.0

        # Hem nokta hem virgül varsa: en sağdaki ayıracı ondalık kabul et
        if "," in t and "." in t:
            if t.rfind(",") > t.rfind("."):
                t = t.replace(".", "").replace(",", ".")
            else:
                t = t.replace(",", "")
        elif "," in t:
            t = t.replace(".", "").replace(",", ".")
        else:
            # sadece nokta varsa: 1.234.567 -> 1234567 (binlik)
            parts = t.split(".")
            if len(parts) > 2:
                t = t.replace(".", "")
        return float(t)
    except Exception:
        return 0.0

def para_formatla(deger: float) -> str:
    try:
        return "{:,.2f} TL".format(float(deger)).replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00 TL"

def whatsapp_gonder(numara: str, mesaj: str) -> bool:
    if not numara or not ID_INSTANCE or not API_TOKEN:
        st.error("WhatsApp API bilgileri veya telefon numarası eksik.")
        return False

    target = f"{SABIT_IHBAR_NO}@c.us" if numara == "SABIT" else f"{numara}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        requests.post(url, json={"chatId": target, "message": mesaj}, timeout=12).raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        st.error(f"WhatsApp gönderim hatası: {e}")
        return False

def vkn_bul(text: str):
    if not text:
        return None
    patterns = [
        r"(?:Vergi\s*Kimlik\s*Numarası\s*(?:\(|:)?[^\d]{0,30})(\d{10,11})",
        r"(?:Vergi\s*Kimlik|Vergi\s*No|VKN)[\s:]*([0-9]{10,11})",
        r"(?:TC\s*Kimlik|TCKN)[\s:]*([0-9]{10,11})",
        r"\b(\d{10,11})\b",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def isim_eslestir_excel(numara):
    if st.session_state.get("mukellef_db") is None:
        return f"Bilinmeyen ({numara or 'Bulunamadı'})"
    if not numara:
        return "VKN/TCKN PDF'te Bulunamadı"

    df = st.session_state["mukellef_db"]
    num = str(numara).strip()

    res_vkn = df[df["C_VKN"] == num]
    if not res_vkn.empty:
        return res_vkn.iloc[0]["A_UNVAN"]

    res_tc = df[df["B_TC"] == num]
    if not res_tc.empty:
        return res_tc.iloc[0]["A_UNVAN"]

    return f"Listede Yok ({num})"

def pdf_to_full_text(pdf_file) -> str:
    full = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=1, y_tolerance=2)
            if t:
                full.append(t)
    return "\n".join(full)

def split_beyannameler(full_text: str):
    """
    'KATMA DEĞER VERGİSİ BEYANNAMESİ' başlığı ile bloklara ayırır.
    """
    if not full_text:
        return []
    parts = re.split(rf"(?i)({re.escape(BEYANNAME_AYRACI)})", full_text)
    if len(parts) <= 1:
        return [full_text]

    blocks = []
    # parts: [önmetin, AYRAC, blok1, AYRAC, blok2, ...]
    for i in range(1, len(parts), 2):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        block = (header + "\n" + body).strip()
        if len(block) >= 300:
            blocks.append(block)
    return blocks

def first_amount_after_label(text: str, label: str, lookahead_chars: int = 220) -> float:
    """
    label sonrası küçük bir pencerede ilk parasal değeri bulur.
    """
    if not text:
        return 0.0
    try:
        m = re.search(re.escape(label), text, flags=re.IGNORECASE)
        if not m:
            return 0.0
        start = m.end()
        window = text[start:start + lookahead_chars]

        # Tutar yakalama: 1.234.567,89 / 123.456 / 123456 / 810,00 vb.
        amt = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d{1,3}(?:\.\d{3})+|\d+)", window)
        return text_to_float(amt.group(1)) if amt else 0.0
    except Exception:
        return 0.0

def pos_bul_satir_bazli(text: str) -> float:
    """
    'Kredi Kartı İle Tahsil Edilen ...' satırını bulur.
    Bu satırdan SONRA gelen ilk tutarı POS kabul eder.
    Böylece kümülatif/aylık toplamın POS diye alınması engellenir.
    """
    if not text:
        return 0.0
    try:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            if re.search(POS_SATIRI_IFADESI, ln, flags=re.IGNORECASE):
                for j in range(i + 1, min(i + 15, len(lines))):
                    amt = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d{1,3}(?:\.\d{3})+|\d+)", lines[j])
                    if amt:
                        return text_to_float(amt.group(1))
        return 0.0
    except Exception:
        return 0.0

# ==========================================
# 5) ANA MENÜ (KORUNDU)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.header("MÜŞAVİR PANELİ")
    secim = st.radio("MENÜ", ["1. Excel Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"])

# ==========================================
# 6) 1. MENÜ: EXCEL YÜKLE
# ==========================================
if secim == "1. Excel Listesi Yükle":
    st.title("📂 Mükellef Veritabanı Yükle")
    st.info("Sütunlar: **A (Unvan), B (TCKN), C (VKN), D (Telefon)**.")

    uploaded_file = st.file_uploader("Excel Dosyasını Seçin", type=["xlsx", "xls"])
    if uploaded_file:
        try:
            raw_df = pd.read_excel(uploaded_file, dtype=str, header=None)

            df = pd.DataFrame()
            df["A_UNVAN"] = raw_df.iloc[:, 0].astype(str).str.strip()
            df["B_TC"] = raw_df.iloc[:, 1].astype(str).str.strip() if raw_df.shape[1] > 1 else ""
            df["C_VKN"] = raw_df.iloc[:, 2].astype(str).str.strip() if raw_df.shape[1] > 2 else ""
            df["D_TEL"] = (
                raw_df.iloc[:, 3].astype(str).str.strip().str.replace(r"\D", "", regex=True)
                if raw_df.shape[1] > 3 else ""
            )

            st.session_state["mukellef_db"] = df.fillna("")
            st.success(f"✅ Başarılı! {len(df)} mükellef bilgisi yüklendi.")
        except Exception as e:
            st.error(f"❌ Dosya okunurken hata: {e}")

# ==========================================
# 7) 2. MENÜ: KDV ANALİZ ROBOTU
# ==========================================
elif secim == "2. KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz Üssü (Canlı Akış & Akıllı Okuyucu)")

    if st.session_state.get("mukellef_db") is None:
        st.warning("⚠️ Lütfen önce '1. Excel Listesi Yükle' menüsünden listenizi yükleyin.")
        st.stop()

    pdf_files = st.file_uploader(
        "İçinde bir veya yüzlerce beyanname olan PDF dosyasını yükleyin",
        type=["pdf"],
        accept_multiple_files=True
    )

    if pdf_files and st.button("🚀 TÜM BEYANNAMELERİ ANALİZ ET", type="primary", use_container_width=True):
        sonuclar = []
        toplam_beyan = 0

        st.subheader("Canlı Analiz Akışı")
        terminal = st.empty()
        logs = []

        for pdf_file in pdf_files:
            try:
                full_text = pdf_to_full_text(pdf_file)
                blocks = split_beyannameler(full_text)

                for block in blocks:
                    if not block.strip():
                        continue

                    toplam_beyan += 1

                    vkn = vkn_bul(block)
                    isim = isim_eslestir_excel(vkn)

                    # Matrah: (aylık) bedel
                    matrah = first_amount_after_label(
                        block,
                        MATRAH_AYLIK_IFADESI,
                        lookahead_chars=200
                    )

                    # KDV: önce "Toplam KDV", yoksa "Hesaplanan KDV"
                    kdv = first_amount_after_label(
                        block,
                        KDV_TOPLAM_IFADESI,
                        lookahead_chars=220
                    )
                    if kdv == 0.0:
                        kdv = first_amount_after_label(
                            block,
                            KDV_HESAPLANAN_IFADESI,
                            lookahead_chars=260
                        )

                    # POS: satır bazlı, ilk tutar
                    pos = pos_bul_satir_bazli(block)

                    beyan_toplami = matrah + kdv
                    fark = pos - beyan_toplami

                    if pos > 0 and beyan_toplami == 0:
                        durum = "OKUNAMADI"
                    elif fark > RISK_ESIK:
                        durum = "RISKLI"
                    else:
                        durum = "TEMIZ"

                    log = (
                        f" > Mükellef: {isim[:24]:<24} | "
                        f"Matrah(Aylık): {para_formatla(matrah):>15} | "
                        f"KDV: {para_formatla(kdv):>15} | "
                        f"POS: {para_formatla(pos):>15} | Durum: {durum}"
                    )
                    renk = "#d32f2f" if durum == "RISKLI" else "#ffc107" if durum == "OKUNAMADI" else "#28a745"
                    logs.append(f"<span style='color:{renk};'>{log}</span>")
                    terminal.markdown(f"<div class='terminal-window'>{'<br>'.join(logs[-200:])}</div>", unsafe_allow_html=True)
                    time.sleep(0.02)

                    sonuclar.append({
                        "Mükellef": isim,
                        "VKN": vkn or "Bulunamadı",
                        "Matrah(Aylık)": matrah,
                        "KDV": kdv,
                        "POS": pos,
                        "Beyan": beyan_toplami,
                        "Fark": fark,
                        "Durum": durum
                    })

            except Exception as e:
                st.error(f"'{getattr(pdf_file, 'name', 'PDF')}' işlenirken hata: {e}")

        st.success(f"Analiz tamamlandı! Toplam **{toplam_beyan}** beyanname incelendi.")
        st.session_state["sonuclar"] = pd.DataFrame(sonuclar) if sonuclar else pd.DataFrame()

    # Sonuçlar
    if st.session_state.get("sonuclar") is not None:
        df_sonuc = st.session_state["sonuclar"]
        if not df_sonuc.empty:
            riskliler = df_sonuc[df_sonuc["Durum"] == "RISKLI"]
            temizler = df_sonuc[df_sonuc["Durum"] == "TEMIZ"]
            okunamayanlar = df_sonuc[df_sonuc["Durum"] == "OKUNAMADI"]

            st.subheader("Analiz Sonuçları")
            tab1, tab2, tab3 = st.tabs([
                f"🚨 RİSKLİ ({len(riskliler)})",
                f"✅ UYUMLU ({len(temizler)})",
                f"❓ OKUNAMAYAN ({len(okunamayanlar)})"
            ])

            with tab1:
                if not riskliler.empty:
                    st.error(f"Aşağıdaki {len(riskliler)} mükellefin POS satışı, (Matrah(Aylık)+KDV) toplamından yüksektir.")
                    for i, row in riskliler.iterrows():
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.markdown(f"""
                            <div class='card risk-card'>
                                <div class='card-title'>{row['Mükellef']}</div>
                                <div class='card-sub'>VKN/TCKN: {row['VKN']}</div>
                                <div style='display:flex; gap:15px; margin-top:10px'>
                                    <div>
                                        <span class='stat-lbl'>POS</span><br>
                                        <span class='stat-val'>{para_formatla(row['POS'])}</span>
                                    </div>
                                    <div>
                                        <span class='stat-lbl'>BEYAN (Matrah(Aylık)+KDV)</span><br>
                                        <span class='stat-val'>{para_formatla(row['Beyan'])}</span>
                                    </div>
                                </div>
                                <div style='color:#d32f2f; font-weight:bold; margin-top:10px; font-size:16px;'>
                                    FARK: {para_formatla(row['Fark'])}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                        with col2:
                            st.write("")
                            if st.button("🚨 İHBAR ET", key=f"ihbar_{i}", type="primary", use_container_width=True):
                                mesaj = (
                                    "⚠️ *KDV RİSK UYARISI*\n\n"
                                    f"*Firma:* {row['Mükellef']}\n"
                                    f"*VKN/TCKN:* {row['VKN']}\n"
                                    f"*POS:* {para_formatla(row['POS'])}\n"
                                    f"*Beyan (Matrah(Aylık)+KDV):* {para_formatla(row['Beyan'])}\n"
                                    f"*Fark:* {para_formatla(row['Fark'])}"
                                )
                                if whatsapp_gonder("SABIT", mesaj):
                                    st.toast(f"✅ {row['Mükellef']} için ihbar gönderildi.")
                else:
                    st.success("Riskli bulunan mükellef yok.")

            with tab2:
                st.dataframe(temizler, use_container_width=True)

            with tab3:
                st.dataframe(okunamayanlar, use_container_width=True)

# ==========================================
# 8) 3. MENÜ: PROFESYONEL MESAJ
# ==========================================
elif secim == "3. Profesyonel Mesaj":
    st.title("📤 Profesyonel Mesaj Gönderimi")

    if st.session_state.get("mukellef_db") is not None:
        df = st.session_state["mukellef_db"]
        kisi = st.selectbox("Kişi", df["A_UNVAN"])
        tel = df[df["A_UNVAN"] == kisi].iloc[0].get("D_TEL", "")
        st.write(f"Telefon Numarası: {tel}")
        txt = st.text_area("Mesajınız:")

        if st.button("Gönder"):
            if whatsapp_gonder(tel, txt):
                st.success("Mesaj gönderildi.")
            else:
                st.error("Mesaj gönderilemedi.")
    else:
        st.warning("Lütfen önce '1. Excel Listesi Yükle' menüsünden mükellef listenizi yükleyin.")

# ==========================================
# 9) 4. MENÜ: TASDİK ROBOTU
# ==========================================
elif secim == "4. Tasdik Robotu":
    st.title("🤖 Yüklenen Mükellef Listesi (Tasdik)")

    if st.session_state.get("mukellef_db") is not None:
        st.info(f"Sistemde kayıtlı {len(st.session_state['mukellef_db'])} mükellef bulunmaktadır.")
        st.dataframe(st.session_state["mukellef_db"], use_container_width=True)
    else:
        st.warning("Görüntülenecek bir liste yok. Lütfen önce '1. Excel Listesi Yükle' menüsünden listenizi yükleyin.")
