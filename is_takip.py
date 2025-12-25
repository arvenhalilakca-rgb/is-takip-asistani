import streamlit as st
import pandas as pd
import re
import pdfplumber
import requests
import time

# ==========================================
# 1) AYARLAR & SABİTLER
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi (Canlı Akış & Akıllı Okuyucu)",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# WhatsApp API Ayarları (Green-API)
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")

# Sabit ihbar numarası
SABIT_IHBAR_NO = "905351041616"

# Beyanname ayıracı (tek PDF içinde yüzlercesi var)
BEYANNAME_AYRACI = "KATMA DEĞER VERGİSİ BEYANNAMESİ"

# Aranacak ifadeler (PDF örneğine göre güvenli seçim)
MATRAH_AYLIK_IFADESI = "Teslim ve Hizmetlerin Karşılığını Teşkil Eden Bedel (aylık)"
KDV_TOPLAM_IFADESI = "Toplam Katma Değer Vergisi"
KDV_HESAPLANAN_IFADESI = "Hesaplanan Katma Değer Vergisi"
POS_SATIRI_IFADESI = "Kredi Kartı İle Tahsil Edilen"

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
    203.922,89 / 206183,59 / 1.211.645,59 / 810,00 gibi TR formatlarını sayıya çevirir.
    """
    try:
        if text is None:
            return 0.0
        t = str(text).strip().replace("\u00a0", " ")
        # sadece rakam, nokta, virgül
        t = re.sub(r"[^0-9\.,]", "", t)

        if not t:
            return 0.0

        # Hem . hem , varsa binlik/ondalık çözümü
        if "," in t and "." in t:
            # TR genelde 1.234.567,89
            # en sağdaki ayıracı ondalık varsay
            if t.rfind(",") > t.rfind("."):
                t = t.replace(".", "").replace(",", ".")
            else:
                # 1,234,567.89 gibi bir şey gelirse
                t = t.replace(",", "")
        elif "," in t:
            t = t.replace(".", "").replace(",", ".")  # 123.456,78 -> 123456.78 (önce binlik . zaten temizlenir)
        else:
            # sadece nokta varsa: 123456.78 ya da 123.456 (binlik) olabilir
            # 3 haneli gruplama varsa binlik kabul et
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

def vkn_bul(text: str) -> str | None:
    """
    PDF’lerde VKN/TCKN birden fazla yerde geçebilir.
    En güvenlisi: 'Vergi Kimlik Numarası' yakınındaki 10-11 haneli değer.
    """
    if not text:
        return None

    patterns = [
        r"(?:Vergi\s*Kimlik\s*Numarası\s*(?:|:)?[^\d]{0,20})(\d{10,11})",
        r"(?:TC\s*Kimlik\s*No\s*?\s*:?[\s]*)(\d{10,11})",
        r"\b(\d{10,11})\b",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def isim_eslestir_excel(numara: str | None) -> str:
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

def first_amount_after_label(text: str, label: str, lookahead_chars: int = 250) -> float:
    """
    label sonrası belirli mesafe içinde ilk parasal değeri yakalar.
    """
    if not text:
        return 0.0
    try:
        idx = re.search(re.escape(label), text, flags=re.IGNORECASE)
        if not idx:
            return 0.0
        start = idx.end()
        window = text[start : start + lookahead_chars]
        m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d{1,3}(?:\.\d{3})+|\d+)", window)
        return text_to_float(m.group(1)) if m else 0.0
    except Exception:
        return 0.0

def pos_bul_satir_bazli(text: str) -> float:
    """
    Örnek PDF'te 'Kredi Kartı İle Tahsil Edilen ...' satırından sonra iki tutar geliyor:
    - 1. tutar POS (kredi kartı tahsilatı)
    - 2. tutar genellikle aylık/kümülatif bedel (karışmaması gerekir)

    Bu fonksiyon satırları gezer, ilgili satırı bulur ve SONRAKİ birkaç satırda
    gördüğü ilk tutarı POS kabul eder.
    """
    if not text:
        return 0.0
    try:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            if re.search(POS_SATIRI_IFADESI, ln, flags=re.IGNORECASE):
                # Sonraki 10 satırda ilk tutarı ara
                for j in range(i + 1, min(i + 12, len(lines))):
                    m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d{1,3}(?:\.\d{3})+|\d+)", lines[j])
                    if m:
                        return text_to_float(m.group(1))
        return 0.0
    except Exception:
        return 0.0

def pdf_to_full_text(pdf_file) -> str:
    """
    pdfplumber ile sayfaları birleştirir.
    """
    full = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=1, y_tolerance=2)
            if t:
                full.append(t)
    return "\n".join(full)

def split_beyannameler(full_text: str) -> list[str]:
    """
    Tek PDF içinde yüzlerce beyanname var: 'KATMA DEĞER VERGİSİ BEYANNAMESİ' başlığı ayraç.
    Split sonrası küçük gürültü bloklarını eler.
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
        block = f"{header}\n{body}".strip()
        if len(block) >= 300:  # çok küçük parçaları ele
            blocks.append(block)
    return blocks

# ==========================================
# 5) SİDEBAR / ANA MENÜ (BOZULMADI)
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

        for pdf_idx, pdf_file in enumerate(pdf_files):
            try:
                full_text = pdf_to_full_text(pdf_file)
                blocks = split_beyannameler(full_text)

                for b_idx, block in enumerate(blocks, start=1):
                    toplam_beyan += 1

                    # VKN + isim
                    vkn = vkn_bul(block)
                    isim = isim_eslestir_excel(vkn)

                    # Matrah (aylık bedel) - örnek PDF’te bu satır değerle geliyor
                    matrah = first_amount_after_label(block, MATRAH_AYLIK_IFADESI, lookahead_chars=
