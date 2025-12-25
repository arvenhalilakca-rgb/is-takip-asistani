import os
import re
import time
import uuid
import requests
import pandas as pd
import pdfplumber
import streamlit as st
from datetime import datetime, date

# ==========================================
# 1) AYARLAR & SABİTLER (MENÜ YAPISI KORUNUR)
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi (Ana Sayfa: İş Emri + Analiz + Takip)",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# WhatsApp (Green-API)
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

# Kalıcı dosyalar
KALICI_EXCEL_YOLU = "mukellef_db_kalici.xlsx"     # mükellef veritabanı (kalıcı)
PERSONEL_DOSYASI = "personel_db.xlsx"            # personel/numara (kalıcı)
IS_TAKIP_DOSYASI = "is_takip.xlsx"               # işler (kalıcı)
MUKELLEF_NOT_DOSYASI = "mukellef_notlari.xlsx"    # mükellef notları (kalıcı)

# Beyanname ayraç ve alanlar
BEYANNAME_AYRACI = "KATMA DEĞER VERGİSİ BEYANNAMESİ"
MATRAH_AYLIK_IFADESI = "Teslim ve Hizmetlerin Karşılığını Teşkil Eden Bedel (aylık)"
KDV_TOPLAM_IFADESI = "Toplam Katma Değer Vergisi"
KDV_HESAPLANAN_IFADESI = "Hesaplanan Katma Değer Vergisi"
POS_SATIRI_TAM = "Kredi Kartı İle Tahsil Edilen Teslim ve Hizmetlerin KDV Dahil Karşılığını Teşkil Eden Bedel"

AMOUNT_REGEX = r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"
RISK_ESIK = 50.0
MAX_TUTAR_SANITY = 200_000_000

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
    padding: 15px; border-radius: 8px; height: 360px; overflow-y: auto;
    font-size: 13px; margin-bottom: 20px; border: 1px solid #333; line-height: 1.6;
}
.small-note {font-size: 12px; color:#666;}
.kpi {background:white; border:1px solid #eee; border-radius:10px; padding:12px; box-shadow: 0 2px 5px rgba(0,0,0,0.04);}
.kpi .v {font-weight:700; font-size:18px;}
.kpi .l {font-size:12px; color:#666;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3) SESSION STATE
# ==========================================
for k in ["sonuclar", "mukellef_db", "personel_db", "is_takip_db", "mukellef_not_db"]:
    if k not in st.session_state:
        st.session_state[k] = None

# ==========================================
# 4) YARDIMCI FONKSİYONLAR
# ==========================================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if len(p) == 10:
        p = "90" + p
    if len(p) == 11 and p.startswith("0"):
        p = "9" + p
    if len(p) < 11:
        return ""
    return p

def parse_phones(cell_text: str) -> list:
    t = str(cell_text or "")
    if not t.strip():
        return []
    candidates = re.findall(r"(?:\+?90\s*)?(?:0\s*)?5\d{2}\s*\d{3}\s*\d{2}\s*\d{2}", t)
    out = []
    for c in candidates:
        n = normalize_phone(c)
        if n and n not in out:
            out.append(n)
    if not out:
        digits = re.findall(r"\d+", t)
        joined = "".join(digits)
        candidates2 = re.findall(r"(?:90)?5\d{9}", joined)
        for c in candidates2:
            n = normalize_phone(c)
            if n and n not in out:
                out.append(n)
    return out

def text_to_float(text) -> float:
    try:
        t = str(text).strip().replace("\u00a0", " ")
        t = re.sub(r"[^0-9\.,]", "", t)
        if not t:
            return 0.0
        if "," in t and "." in t:
            if t.rfind(",") > t.rfind("."):
                t = t.replace(".", "").replace(",", ".")
            else:
                t = t.replace(",", "")
        elif "," in t:
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(".", "")
        return float(t)
    except Exception:
        return 0.0

def para_formatla(x: float) -> str:
    try:
        return "{:,.2f} TL".format(float(x)).replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00 TL"

def yuzde_formatla(deger: float) -> str:
    try:
        return "%{:,.2f}".format(float(deger)).replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "%0,00"

def whatsapp_gonder(numara: str, mesaj: str) -> bool:
    if not numara or not ID_INSTANCE or not API_TOKEN:
        st.error("WhatsApp API bilgileri veya telefon numarası eksik.")
        return False
    numara = normalize_phone(numara)
    if not numara:
        return False
    target = f"{SABIT_IHBAR_NO}@c.us" if numara == "SABIT" else f"{numara}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        requests.post(url, json={"chatId": target, "message": mesaj}, timeout=12).raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        st.error(f"WhatsApp gönderim hatası: {e}")
        return False

def whatsapp_gonder_coklu(numaralar: list, mesaj: str) -> int:
    ok = 0
    for n in (numaralar or []):
        if whatsapp_gonder(n, mesaj):
            ok += 1
        time.sleep(0.25)
    return ok

def vkn_bul(text: str):
    if not text:
        return None
    patterns = [
        r"(?:Vergi\s*Kimlik|Vergi\s*No|VKN)[\s:]*([0-9]{10,11})",
        r"(?:TC\s*Kimlik|TCKN)[\s:]*([0-9]{10,11})",
        r"\b(\d{10,11})\b",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def donem_bul(block_text: str):
    t = re.sub(r"\s+", " ", str(block_text or "")).strip()
    if not t:
        return (None, None)
    ay_map = {
        "ocak":"Ocak","şubat":"Şubat","subat":"Şubat","mart":"Mart","nisan":"Nisan","mayıs":"Mayıs","mayis":"Mayıs",
        "haziran":"Haziran","temmuz":"Temmuz","ağustos":"Ağustos","agustos":"Ağustos","eylül":"Eylül","eylul":"Eylül",
        "ekim":"Ekim","kasım":"Kasım","kasim":"Kasım","aralık":"Aralık","aralik":"Aralık"
    }
    ay_regex = r"(ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik)"
    m = re.search(rf"Yıl\s*Ay\s*(20\d{{2}}).{{0,200}}?\b{ay_regex}\b", t, flags=re.IGNORECASE)
    if m:
        return (ay_map.get(m.group(2).lower()), m.group(1))
    m2 = re.search(rf"Yıl\s*(20\d{{2}}).{{0,240}}?Ay.{{0,240}}?\b{ay_regex}\b", t, flags=re.IGNORECASE)
    if m2:
        return (ay_map.get(m2.group(2).lower()), m2.group(1))
    yil = re.search(r"\b(20\d{2})\b", t)
    ay = re.search(rf"\b{ay_regex}\b", t, flags=re.IGNORECASE)
    return (ay_map.get(ay.group(1).lower()) if ay else None, yil.group(1) if yil else None)

def first_amount_after_label(text: str, label: str, lookahead_chars: int = 520) -> float:
    if not text:
        return 0.0
    try:
        m = re.search(re.escape(label), text, flags=re.IGNORECASE)
        if not m:
            return 0.0
        window = text[m.end(): m.end() + lookahead_chars]
        amt = re.search(AMOUNT_REGEX, window)
        if not amt:
            return 0.0
        val = text_to_float(amt.group(1))
        if val <= 0 or val > MAX_TUTAR_SANITY:
            return 0.0
        return val
    except Exception:
        return 0.0

def pos_bul_istenen_satirdan(text: str) -> float:
    if not text:
        return 0.0
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    if not lines:
        return 0.0
    k1, k2, k3, k4 = "Kredi Kartı İle Tahsil Edilen", "KDV Dahil", "Teşkil Eden", "Bedel"
    for i, ln in enumerate(lines):
        if re.search(re.escape(k1), ln, flags=re.IGNORECASE):
            joined = " ".join(lines[i:i+10])
            if re.search(k2, joined, flags=re.IGNORECASE) and re.search(k3, joined, flags=re.IGNORECASE) and re.search(k4, joined, flags=re.IGNORECASE):
                amt = re.search(AMOUNT_REGEX, joined)
                if amt:
                    val = text_to_float(amt.group(1))
                    if 0 < val <= MAX_TUTAR_SANITY:
                        return val
            for j in range(i, min(i+20, len(lines))):
                amt2 = re.search(AMOUNT_REGEX, lines[j])
                if amt2:
                    val2 = text_to_float(amt2.group(1))
                    if 0 < val2 <= MAX_TUTAR_SANITY:
                        return val2
    return 0.0

def pdf_to_full_text(pdf_file) -> str:
    full = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=1, y_tolerance=2)
            if t:
                full.append(t)
    return "\n".join(full)

def split_beyannameler(full_text: str):
    if not full_text:
        return []
    matches = list(re.finditer(re.escape(BEYANNAME_AYRACI), full_text, flags=re.IGNORECASE))
    if not matches:
        return [full_text]
    starts = [m.start() for m in matches]
    blocks = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(full_text)
        block = full_text[s:e].strip()
        if len(block) >= 300:
            blocks.append(block)
    return blocks

def log_yaz(logs, terminal, msg, color="#f0f0f0"):
    logs.append(f"<span style='color:{color};'>{msg}</span>")
    terminal.markdown(
        f"<div class='terminal-window'>{'<br>'.join(logs[-320:])}</div>",
        unsafe_allow_html=True
    )

# ==========================================
# 5) KALICI VERİ: YÜKLE / KAYDET
# ==========================================
def yukle_mukellef_kalici() -> bool:
    if not os.path.exists(KALICI_EXCEL_YOLU):
        return False
    try:
        raw = pd.read_excel(KALICI_EXCEL_YOLU, dtype=str).fillna("")
        # başlık yoksa header=None fallback
        if not {"A_UNVAN", "B_TC", "C_VKN"}.issubset(set(raw.columns)):
            raw2 = pd.read_excel(KALICI_EXCEL_YOLU, dtype=str, header=None).fillna("")
            df = pd.DataFrame()
            df["A_UNVAN"] = raw2.iloc[:, 0].astype(str).str.strip() if raw2.shape[1] > 0 else ""
            df["B_TC"]    = raw2.iloc[:, 1].astype(str).str.strip() if raw2.shape[1] > 1 else ""
            df["C_VKN"]   = raw2.iloc[:, 2].astype(str).str.strip() if raw2.shape[1] > 2 else ""
            df["D_TEL"]   = raw2.iloc[:, 3].astype(str).str.strip() if raw2.shape[1] > 3 else ""
            df["D_TEL_ALL"] = df["D_TEL"].apply(lambda x: " | ".join(parse_phones(x)))
        else:
            df = raw.copy()
            if "D_TEL_ALL" not in df.columns:
                df["D_TEL_ALL"] = df.get("D_TEL", "").apply(lambda x: " | ".join(parse_phones(x)))
            if "D_TEL" not in df.columns:
                df["D_TEL"] = df["D_TEL_ALL"].apply(lambda x: (parse_phones(x)[0] if parse_phones(x) else ""))
        st.session_state["mukellef_db"] = df.fillna("")
        return True
    except Exception:
        return False

def kaydet_mukellef_kalici(df: pd.DataFrame):
    df = df.fillna("")
    out_cols = ["A_UNVAN", "B_TC", "C_VKN", "D_TEL", "D_TEL_ALL"]
    for c in out_cols:
        if c not in df.columns:
            df[c] = ""
    df[out_cols].to_excel(KALICI_EXCEL_YOLU, index=False)

def yukle_personel() -> pd.DataFrame:
    if os.path.exists(PERSONEL_DOSYASI):
        try:
            df = pd.read_excel(PERSONEL_DOSYASI, dtype=str).fillna("")
        except Exception:
            df = pd.DataFrame(columns=["Personel", "Telefon", "Aktif"]).fillna("")
    else:
        df = pd.DataFrame(columns=["Personel", "Telefon", "Aktif"]).fillna("")
    if "Aktif" not in df.columns:
        df["Aktif"] = "Evet"
    st.session_state["personel_db"] = df
    return df

def kaydet_personel(df: pd.DataFrame):
    df = df.fillna("")
    df.to_excel(PERSONEL_DOSYASI, index=False)
    st.session_state["personel_db"] = df

def yukle_is_takip() -> pd.DataFrame:
    if os.path.exists(IS_TAKIP_DOSYASI):
        try:
            df = pd.read_excel(IS_TAKIP_DOSYASI, dtype=str).fillna("")
        except Exception:
            df = pd.DataFrame()
    else:
        df = pd.DataFrame()

    if df.empty:
        df = pd.DataFrame(columns=[
            "IsID", "Tip", "Durum", "Öncelik",
            "Dönem", "Mükellef", "VKN",
            "Konu", "Açıklama",
            "SonTarih",
            "Sorumlu", "SorumluTel",
            "MükellefTelAll",
            "POS", "Beyan", "Fark",
            "Not",
            "OlusturmaZamani", "GuncellemeZamani", "KapanisZamani"
        ]).fillna("")

    must_cols = [
        "IsID","Tip","Durum","Öncelik","Dönem","Mükellef","VKN","Konu","Açıklama","SonTarih",
        "Sorumlu","SorumluTel","MükellefTelAll","POS","Beyan","Fark","Not","OlusturmaZamani","GuncellemeZamani","KapanisZamani"
    ]
    for c in must_cols:
        if c not in df.columns:
            df[c] = ""
    df = df[must_cols].fillna("")
    st.session_state["is_takip_db"] = df
    return df

def kaydet_is_takip(df: pd.DataFrame):
    df = df.fillna("")
    df.to_excel(IS_TAKIP_DOSYASI, index=False)
    st.session_state["is_takip_db"] = df

def yukle_mukellef_notlari() -> pd.DataFrame:
    if os.path.exists(MUKELLEF_NOT_DOSYASI):
        try:
            df = pd.read_excel(MUKELLEF_NOT_DOSYASI, dtype=str).fillna("")
        except Exception:
            df = pd.DataFrame()
    else:
        df = pd.DataFrame()
    if df.empty:
        df = pd.DataFrame(columns=["VKN", "Mükellef", "Notlar", "GuncellemeZamani"]).fillna("")
    for c in ["VKN", "Mükellef", "Notlar", "GuncellemeZamani"]:
        if c not in df.columns:
            df[c] = ""
    df = df[["VKN", "Mükellef", "Notlar", "GuncellemeZamani"]].fillna("")
    st.session_state["mukellef_not_db"] = df
    return df

def kaydet_mukellef_notlari(df: pd.DataFrame):
    df = df.fillna("")
    df.to_excel(MUKELLEF_NOT_DOSYASI, index=False)
    st.session_state["mukellef_not_db"] = df

# Açılış yüklemeleri
if st.session_state["mukellef_db"] is None:
    yukle_mukellef_kalici()
if st.session_state["personel_db"] is None:
    yukle_personel()
if st.session_state["is_takip_db"] is None:
    yukle_is_takip()
if st.session_state["mukellef_not_db"] is None:
    yukle_mukellef_notlari()

# ==========================================
# 6) MESAJ ŞABLONLARI
# ==========================================
def mesaj_is_emri_personel(is_row: dict) -> str:
    return (
        "📌 *YENİ İŞ EMRİ*\n"
        f"🆔 *İş No:* {is_row.get('IsID','')}\n"
        f"📅 *Son Tarih:* {is_row.get('SonTarih','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🏢 *Mükellef:* {is_row.get('Mükellef','')}\n"
        f"🆔 *VKN/TCKN:* {is_row.get('VKN','')}\n"
        f"⭐ *Öncelik:* {is_row.get('Öncelik','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📝 *Konu:* {is_row.get('Konu','')}\n"
        f"🧾 *Açıklama:* {is_row.get('Açıklama','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        "Lütfen işlemi tamamlayınca not ekleyiniz."
    )

def mesaj_is_emri_mukellef(is_row: dict) -> str:
    return (
        "Merhaba,\n"
        "Tarafınızla ilgili bir işlem/evrak talebi bulunmaktadır.\n"
        f"📌 Konu: {is_row.get('Konu','')}\n"
        f"📝 Açıklama: {is_row.get('Açıklama','')}\n"
        f"📅 Son Tarih: {is_row.get('SonTarih','')}\n"
        "Geri dönüşünüz rica olunur."
    )

# ==========================================
# 7) İŞ TAKİP: OLUŞTUR / GÜNCELLE
# ==========================================
def yeni_is_id() -> str:
    return "IS-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()

# ==========================================
# 8) ANA MENÜ (AYNEN) - SADECE "DEFAULT" EKRAN: 2. MENÜ
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.header("MÜŞAVİR PANELİ")
    secim = st.radio("MENÜ", ["1. Excel Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"], index=1)

# ======================================================
# 1) Excel Yükle
# ======================================================
if secim == "1. Excel Listesi Yükle":
    st.title("📂 Mükellef Veritabanı Yükle")
    st.info("Telefon hücresinde birden fazla numara varsa sistem hepsini ayıklar ve saklar (D_TEL_ALL).")

    uploaded_file = st.file_uploader("Excel Dosyasını Seçin", type=["xlsx", "xls"])
    if uploaded_file:
        try:
            raw = pd.read_excel(uploaded_file, dtype=str).fillna("")
            cols = {c.strip().lower(): c for c in raw.columns}
            unvan_col = cols.get("unvan", raw.columns[0])
            tckn_col  = cols.get("tckn",  raw.columns[1] if len(raw.columns) > 1 else raw.columns[0])
            vkn_col   = cols.get("vkn",   raw.columns[2] if len(raw.columns) > 2 else raw.columns[0])
            tel_col   = cols.get("telefon", raw.columns[3] if len(raw.columns) > 3 else raw.columns[0])

            df = pd.DataFrame()
            df["A_UNVAN"] = raw[unvan_col].astype(str).str.strip()
            df["B_TC"]    = raw[tckn_col].astype(str).str.strip()
            df["C_VKN"]   = raw[vkn_col].astype(str).str.strip()

            df["D_TEL_ALL"] = raw[tel_col].apply(lambda x: " | ".join(parse_phones(x)))
            df["D_TEL"] = df["D_TEL_ALL"].apply(lambda x: (parse_phones(x)[0] if parse_phones(x) else ""))

            df = df.fillna("")
            st.session_state["mukellef_db"] = df
            kaydet_mukellef_kalici(df)

            st.success(f"✅ Yüklendi ve kalıcı kaydedildi. Toplam kayıt: {len(df)}")
            st.dataframe(df[["A_UNVAN","B_TC","C_VKN","D_TEL_ALL"]].head(40), use_container_width=True)
        except Exception as e:
            st.error(f"❌ Okuma hatası: {e}")

    dfm = st.session_state.get("mukellef_db")
    if dfm is not None and not dfm.empty:
        st.divider()
        st.subheader("Kayıtlı Liste (Özet)")
        st.write(f"Toplam: {len(dfm)}")
        st.dataframe(dfm[["A_UNVAN","B_TC","C_VKN","D_TEL_ALL"]].head(20), use_container_width=True)

# ======================================================
# 2) KDV Analiz Robotu (ANA SAYFA: İŞ EMRİ ÖNCE)
# ======================================================
elif secim == "2. KDV Analiz Robotu":
    st.title("🧾 İş Emri Merkezi (Önce) + 📄 Beyanname Analizi + 📌 Takip")

    dfm = st.session_state.get("mukellef_db")
    if dfm is None or dfm.empty:
        st.warning("⚠️ Önce '1. Excel Listesi Yükle' menüsünden mükellef veritabanını yükleyin.")
        st.stop()

    dfp = yukle_personel()
    dfi = yukle_is_takip()
    dfn = yukle_mukellef_notlari()

    # -------------------- ÜST KPI --------------------
    colk1, colk2, colk3, colk4 = st.columns(4)
    with colk1:
        st.markdown(f"<div class='kpi'><div class='v'>{len(dfi)}</div><div class='l'>Toplam İş</div></div>", unsafe_allow_html=True)
    with colk2:
        acik = (dfi["Durum"].astype(str) == "AÇIK").sum()
        st.markdown(f"<div class='kpi'><div class='v'>{acik}</div><div class='l'>Açık İş</div></div>", unsafe_allow_html=True)
    with colk3:
        ince = (dfi["Durum"].astype(str) == "İNCELEMEDE").sum()
        st.markdown(f"<div class='kpi'><div class='v'>{ince}</div><div class='l'>İncelemede</div></div>", unsafe_allow_html=True)
    with colk4:
        kap = (dfi["Durum"].astype(str) == "KAPANDI").sum()
        st.markdown(f"<div class='kpi'><div class='v'>{kap}</div><div class='l'>Kapandı</div></div>", unsafe_allow_html=True)

    st.divider()

    # ======================================================
    # A) İŞ EMRİ AÇ (EN ÜSTTE)
    # ======================================================
    st.subheader("➕ İş Emri Aç")

    left, right = st.columns([2, 2])

    with left:
        mukellef_sec = st.selectbox("Mükellef Seç", dfm["A_UNVAN"].astype(str).tolist(), key="is_mukellef_sec")
        hit = dfm[dfm["A_UNVAN"].astype(str) == str(mukellef_sec)]
        muk = hit.iloc[0].to_dict() if not hit.empty else {}
        vkn_val = str(muk.get("C_VKN", "")).strip() or str(muk.get("B_TC", "")).strip()
        tel_all = str(muk.get("D_TEL_ALL", "")).strip()
        tel_list = parse_phones(tel_all)

        st.caption(f"VKN/TCKN: {vkn_val or '-'}")
        st.caption(f"Mükellef Telefon(lar): {tel_all or '-'}")

        konu = st.text_input("İş Konusu", placeholder="Örn: Ocak 2024 KDV evrak tamamlama", key="is_konu")
        aciklama = st.text_area("İş Açıklaması / Talimat", height=110, key="is_aciklama")

        # İşle ilgili notlar (işe özel)
        is_notu = st.text_area("İş ile İlgili Notlar (İşe özel)", height=90, key="is_notu")
        oncelik = st.selectbox("Öncelik", ["Yüksek", "Orta", "Düşük"], index=1, key="is_oncelik")

    with right:
        son_tarih = st.date_input("Son Tarih", value=date.today(), key="is_sontarih")
        donem = st.text_input("Dönem (opsiyonel)", placeholder="Örn: Ocak / 2024", key="is_donem")

        # Mükellef notları (kalıcı, mükellef kartı gibi)
        st.markdown("**🗒️ Mükellef Notları (Kalıcı)**")
        mevcut_not = ""
        not_hit = dfn[dfn["VKN"].astype(str) == str(vkn_val)]
        if not not_hit.empty:
            mevcut_not = str(not_hit.iloc[0].get("Notlar", ""))

        muk_not = st.text_area("Mükellef ile ilgili genel notlar", value=mevcut_not, height=110, key="muk_genel_not")

        # Personel atama
        aktif_personel = dfp[dfp["Aktif"].astype(str).str.lower().isin(["evet", "yes", "true", "1"])].copy()
        personel_ops = ["(Atama Yok)"] + aktif_personel["Personel"].astype(str).tolist()
        sorumlu = st.selectbox("Sorumlu Personel", personel_ops, key="is_sorumlu")

        st.markdown("**WhatsApp Bildirimi**")
        bildir_personel = st.checkbox("Personeli WhatsApp ile bilgilendir", value=True, key="is_bildir_personel")
        bildir_mukellef = st.checkbox("Mükellefi WhatsApp ile bilgilendir", value=False, key="is_bildir_mukellef")
        muk_tum_num = st.checkbox("Mükellefe gönderimde TÜM numaralara gönder", value=True, key="is_muk_tum")

    colbtn1, colbtn2 = st.columns([2, 1])
    with colbtn1:
        if st.button("✅ İŞ EMRİNİ OLUŞTUR", type="primary", use_container_width=True):
            if not str(konu).strip():
                st.error("İş konusu boş olamaz.")
            elif not str(aciklama).strip():
                st.error("İş açıklaması boş olamaz.")
            else:
                # 1) Mükellef genel notunu kaydet
                dfn2 = dfn.copy()
                mask = dfn2["VKN"].astype(str) == str(vkn_val)
                if mask.any():
                    idxn = dfn2[mask].index[0]
                    dfn2.loc[idxn, "Mükellef"] = str(mukellef_sec).strip()
                    dfn2.loc[idxn, "Notlar"] = str(muk_not).strip()
                    dfn2.loc[idxn, "GuncellemeZamani"] = now_str()
                else:
                    dfn2 = pd.concat([dfn2, pd.DataFrame([{
                        "VKN": str(vkn_val),
                        "Mükellef": str(mukellef_sec).strip(),
                        "Notlar": str(muk_not).strip(),
                        "GuncellemeZamani": now_str()
                    }])], ignore_index=True)
                kaydet_mukellef_notlari(dfn2)

                # 2) İş kaydını oluştur
                isid = yeni_is_id()
                sorumlu_tel = ""
                if sorumlu != "(Atama Yok)":
                    rr = aktif_personel[aktif_personel["Personel"].astype(str) == str(sorumlu)]
                    if not rr.empty:
                        sorumlu_tel = normalize_phone(rr.iloc[0].get("Telefon", ""))

                yeni = {
                    "IsID": isid,
                    "Tip": "MANUEL",
                    "Durum": "AÇIK",
                    "Öncelik": oncelik,
                    "Dönem": str(donem).strip(),
                    "Mükellef": str(mukellef_sec).strip(),
                    "VKN": str(vkn_val).strip(),
                    "Konu": str(konu).strip(),
                    "Açıklama": str(aciklama).strip(),
                    "SonTarih": str(son_tarih),
                    "Sorumlu": "" if sorumlu == "(Atama Yok)" else str(sorumlu),
                    "SorumluTel": sorumlu_tel,
                    "MükellefTelAll": tel_all,
                    "POS": "",
                    "Beyan": "",
                    "Fark": "",
                    "Not": str(is_notu).strip(),  # işe özel not
                    "OlusturmaZamani": now_str(),
                    "GuncellemeZamani": now_str(),
                    "KapanisZamani": ""
                }

                dfi2 = yukle_is_takip()
                dfi2 = pd.concat([dfi2, pd.DataFrame([yeni])], ignore_index=True)
                kaydet_is_takip(dfi2)

                st.success(f"İş emri oluşturuldu: {isid}")
                st.toast("🗂️ Yapılacak işler listesine eklendi.")

                # 3) WhatsApp bildirimleri
                if bildir_personel and sorumlu_tel:
                    msg_p = mesaj_is_emri_personel(yeni)
                    if whatsapp_gonder(sorumlu_tel, msg_p):
                        st.toast("📨 Personel bilgilendirildi.")
                    else:
                        st.warning("Personel bilgilendirilemedi (telefon/API kontrol ediniz).")

                if bildir_mukellef and tel_list:
                    msg_m = mesaj_is_emri_mukellef(yeni)
                    if muk_tum_num:
                        sent = whatsapp_gonder_coklu(tel_list, msg_m)
                        st.toast(f"📨 Mükellefe {sent} numaraya gönderildi.")
                    else:
                        if whatsapp_gonder(tel_list[0], msg_m):
                            st.toast("📨 Mükellefe birincil numaraya gönderildi.")
                        else:
                            st.warning("Mükellefe gönderilemedi.")

    with colbtn2:
        st.caption("İpucu: Mükellef notları kalıcıdır; iş notu sadece o işe kaydolur.")

    st.divider()

    # ======================================================
    # B) YAPILACAK İŞLER LİSTESİ (İŞ EMRİNDEN SONRA)
    # ======================================================
    st.subheader("📌 Yapılacak İşler Listesi (Takip)")

    dfi = yukle_is_takip()

    f1, f2, f3, f4, f5 = st.columns([1.4, 1.2, 1.2, 1.2, 1.6])
    with f1:
        filt_durum = st.selectbox("Durum", ["(Tümü)", "AÇIK", "İNCELEMEDE", "KAPANDI", "İPTAL"], key="f_durum")
    with f2:
        filt_tip = st.selectbox("Tip", ["(Tümü)", "MANUEL", "RISKLI", "OKUNAMADI"], key="f_tip")
    with f3:
        filt_oncelik = st.selectbox("Öncelik", ["(Tümü)", "Yüksek", "Orta", "Düşük"], key="f_onc")
    with f4:
        filt_geciken = st.selectbox("Geciken", ["(Hepsi)", "Sadece Geciken"], key="f_geciken")
    with f5:
        filt_muk = st.text_input("Mükellef Ara", placeholder="örn: tekstil", key="f_muk")

    view = dfi.copy()
    if filt_durum != "(Tümü)":
        view = view[view["Durum"].astype(str) == filt_durum]
    if filt_tip != "(Tümü)":
        view = view[view["Tip"].astype(str) == filt_tip]
    if filt_oncelik != "(Tümü)":
        view = view[view["Öncelik"].astype(str) == filt_oncelik]
    if str(filt_muk).strip():
        view = view[view["Mükellef"].astype(str).str.lower().str.contains(str(filt_muk).strip().lower(), na=False)]

    # geciken hesapla
    def to_dt(x):
        try:
            return pd.to_datetime(str(x), errors="coerce")
        except Exception:
            return pd.NaT

    view["_son"] = view["SonTarih"].apply(to_dt)
    today_dt = pd.to_datetime(date.today())
    view["_geciken"] = (view["_son"].notna()) & (view["_son"] < today_dt) & (view["Durum"].astype(str).isin(["AÇIK", "İNCELEMEDE"]))

    if filt_geciken == "Sadece Geciken":
        view = view[view["_geciken"] == True]

    view = view.sort_values(by=["_geciken", "_son"], ascending=[False, True])
    st.dataframe(view.drop(columns=["_son","_geciken"], errors="ignore"), use_container_width=True)

    st.divider()
    st.subheader("🛠️ Seçili İş Üzerinde İşlem / Not Alma")

    if view.empty:
        st.info("Filtreye uygun iş bulunamadı.")
    else:
        is_list = view["IsID"].astype(str).tolist()
        sec_isid = st.selectbox("İş Seç (IsID)", is_list, key="sec_isid")
        row = dfi[dfi["IsID"].astype(str) == str(sec_isid)]
        if row.empty:
            st.error("İş bulunamadı.")
        else:
            r = row.iloc[0].to_dict()

            c1, c2 = st.columns([2, 2])
            with c1:
                yeni_durum = st.selectbox("Yeni Durum", ["AÇIK", "İNCELEMEDE", "KAPANDI", "İPTAL"], index=0, key="upd_durum")
                yeni_son = st.text_input("Son Tarih (YYYY-MM-DD)", value=str(r.get("SonTarih","")), key="upd_son")
                yeni_not = st.text_area("İş Notu / Yapılan İşlem", value=str(r.get("Not","")), height=130, key="upd_not")

            with c2:
                st.markdown("**İş Özeti**")
                st.write(f"**İş No:** {r.get('IsID','')}")
                st.write(f"**Tip:** {r.get('Tip','')} | **Öncelik:** {r.get('Öncelik','')}")
                st.write(f"**Mükellef:** {r.get('Mükellef','')}")
                st.write(f"**VKN:** {r.get('VKN','')}")
                st.write(f"**Konu:** {r.get('Konu','')}")
                st.write(f"**Sorumlu:** {r.get('Sorumlu','') or '-'}")

                st.markdown("**Hatırlatma / Mesaj**")
                hedef = st.selectbox("Mesaj Gönder (opsiyonel)", ["Gönderme", "Sorumlu Personele", "Mükellefe", "Serbest Numara"], key="upd_hedef")
                serbest = ""
                tum_muk = False
                if hedef == "Serbest Numara":
                    serbest = st.text_input("Serbest Numara", placeholder="905xxxxxxxxx", key="upd_serbest")
                if hedef == "Mükellefe":
                    tum_muk = st.checkbox("Mükellefe TÜM numaralara gönder", value=True, key="upd_tummuk")

            if st.button("💾 GÜNCELLE", type="primary", use_container_width=True, key="upd_kaydet"):
                idx = dfi[dfi["IsID"].astype(str) == str(sec_isid)].index[0]
                dfi.loc[idx, "Durum"] = yeni_durum
                dfi.loc[idx, "SonTarih"] = str(yeni_son).strip()
                dfi.loc[idx, "Not"] = str(yeni_not).strip()
                dfi.loc[idx, "GuncellemeZamani"] = now_str()
                if yeni_durum == "KAPANDI" and not str(dfi.loc[idx, "KapanisZamani"]).strip():
                    dfi.loc[idx, "KapanisZamani"] = now_str()
                kaydet_is_takip(dfi)
                st.success("Güncellendi.")

                # mesaj
                if hedef != "Gönderme":
                    guncel = dfi.loc[idx].to_dict()
                    if hedef == "Sorumlu Personele":
                        tel = normalize_phone(guncel.get("SorumluTel",""))
                        if tel:
                            msg = mesaj_is_emri_personel(guncel)
                            if whatsapp_gonder(tel, msg):
                                st.toast("📨 Sorumlu personele gönderildi.")
                        else:
                            st.warning("Sorumlu personel telefonu yok.")
                    elif hedef == "Mükellefe":
                        tels = parse_phones(guncel.get("MükellefTelAll",""))
                        if tels:
                            msg = mesaj_is_emri_mukellef(guncel)
                            if tum_muk:
                                sent = whatsapp_gonder_coklu(tels, msg)
                                st.toast(f"📨 Mükellefe {sent} numaraya gönderildi.")
                            else:
                                if whatsapp_gonder(tels[0], msg):
                                    st.toast("📨 Mükellefe birincil numaraya gönderildi.")
                        else:
                            st.warning("Mükellef telefonu yok (D_TEL_ALL boş).")
                    else:
                        tel = normalize_phone(serbest)
                        if tel:
                            msg = mesaj_is_emri_personel(guncel)
                            if whatsapp_gonder(tel, msg):
                                st.toast("📨 Serbest numaraya gönderildi.")
                        else:
                            st.warning("Serbest numara geçersiz.")

    st.divider()

    # ======================================================
    # C) BEYANNAME ANALİZİ (ALTTA)
    # ======================================================
    st.subheader("📄 Beyanname Analizi (İsteğe Bağlı)")
    st.caption("Bu bölüm en altta; ana ekran önce iş emri açma ve iş takibi gösterir.")

    pdf_files = st.file_uploader("PDF yükleyin (tek dosyada çok beyanname olabilir)", type=["pdf"], accept_multiple_files=True)

    if pdf_files and st.button("🚀 ANALİZİ BAŞLAT", type="primary", use_container_width=True, key="analiz_baslat"):
        terminal = st.empty()
        logs = []
        progress = st.progress(0)
        info = st.empty()

        log_yaz(logs, terminal, "Analiz başlatıldı. PDF metinleri hazırlanıyor...", color="#ffc107")

        all_blocks = []
        for pf in pdf_files:
            try:
                log_yaz(logs, terminal, f"[{pf.name}] Metin çıkarılıyor...", color="#8ab4f8")
                full_text = pdf_to_full_text(pf)
                blocks = split_beyannameler(full_text)
                all_blocks.extend(blocks)
                log_yaz(logs, terminal, f"[{pf.name}] Bulunan blok: {len(blocks)}", color="#8ab4f8")
            except Exception as e:
                log_yaz(logs, terminal, f"[{pf.name}] HATA: {e}", color="#ff6b6b")

        if not all_blocks:
            st.error("Beyanname bloğu bulunamadı.")
            st.stop()

        results = []
        total = len(all_blocks)

        for i, block in enumerate(all_blocks, start=1):
            progress.progress(int(i / total * 100))
            info.info(f"İşleniyor: {i}/{total}")

            ay, yil = donem_bul(block)
            donem = f"{ay} / {yil}" if ay and yil else (yil or ay or "Bilinmiyor")
            vkn = vkn_bul(block) or ""

            # mükellef eşleştirme
            isim = "Bilinmeyen"
            tel_all = ""
            hit = dfm[dfm["C_VKN"].astype(str) == str(vkn)]
            if hit.empty:
                hit = dfm[dfm["B_TC"].astype(str) == str(vkn)]
            if not hit.empty:
                isim = str(hit.iloc[0].get("A_UNVAN", "Bilinmeyen"))
                tel_all = str(hit.iloc[0].get("D_TEL_ALL", ""))
            else:
                isim = f"Listede Yok ({vkn})" if vkn else "VKN/TCKN Bulunamadı"

            matrah = first_amount_after_label(block, MATRAH_AYLIK_IFADESI, 620)
            kdv = first_amount_after_label(block, KDV_TOPLAM_IFADESI, 680)
            if kdv == 0.0:
                kdv = first_amount_after_label(block, KDV_HESAPLANAN_IFADESI, 780)
            pos = pos_bul_istenen_satirdan(block)

            beyan = matrah + kdv
            fark = pos - beyan

            if pos > 0 and beyan == 0:
                durum = "OKUNAMADI"
                renk = "#ffc107"
            elif fark > RISK_ESIK:
                durum = "RISKLI"
                renk = "#ff6b6b"
            else:
                durum = "TEMIZ"
                renk = "#28a745"

            log_yaz(
                logs, terminal,
                f"[{i}/{total}] {donem} | {isim[:35]:<35} | POS={para_formatla(pos)} | BEYAN={para_formatla(beyan)} | FARK={para_formatla(fark)} | {durum}",
                color=renk
            )

            results.append({
                "Dönem": donem,
                "Mükellef": isim,
                "VKN": vkn or "Bulunamadı",
                "MükellefTelAll": tel_all,
                "POS": pos,
                "Beyan": beyan,
                "Fark": fark,
                "Durum": durum
            })

            time.sleep(0.01)

        df_res = pd.DataFrame(results)
        st.session_state["sonuclar"] = df_res
        st.success("Analiz tamamlandı.")

# ======================================================
# 3) PROFESYONEL MESAJ
# ======================================================
elif secim == "3. Profesyonel Mesaj":
    st.title("📤 Profesyonel Mesaj Gönderimi")
    dfm = st.session_state.get("mukellef_db")
    if dfm is None or dfm.empty:
        st.warning("Önce mükellef listesini yükleyin.")
        st.stop()

    kisi = st.selectbox("Mükellef", dfm["A_UNVAN"].astype(str).tolist())
    hit = dfm[dfm["A_UNVAN"].astype(str) == str(kisi)]
    rec = hit.iloc[0].to_dict() if not hit.empty else {}
    tels = parse_phones(rec.get("D_TEL_ALL",""))

    st.write(f"Bulunan numaralar: {rec.get('D_TEL_ALL','') or '-'}")
    txt = st.text_area("Mesajınız")
    to_all = st.checkbox("Tüm numaralara gönder", value=True)

    if st.button("Gönder", type="primary"):
        if to_all:
            sent = whatsapp_gonder_coklu(tels, txt)
            st.success(f"Mesaj {sent} numaraya gönderildi.")
        else:
            if tels:
                ok = whatsapp_gonder(tels[0], txt)
                st.success("Gönderildi." if ok else "Gönderilemedi.")
            else:
                st.error("Telefon bulunamadı.")

# ======================================================
# 4) TASDİK ROBOTU (MÜKELLEF + PERSONEL + İŞ HAM KAYIT)
# ======================================================
elif secim == "4. Tasdik Robotu":
    st.title("🤖 Tasdik Robotu / Kayıtlar")

    tA, tB, tC, tD = st.tabs(["📋 Mükellef Listesi", "🗒️ Mükellef Notları", "👥 Personel Yönetimi", "🗂️ İş Takip (Ham)"])

    with tA:
        dfm = st.session_state.get("mukellef_db")
        if dfm is None or dfm.empty:
            st.warning("Mükellef listesi yok.")
        else:
            st.info(f"Toplam {len(dfm)} kayıt")
            st.dataframe(dfm[["A_UNVAN","B_TC","C_VKN","D_TEL_ALL"]], use_container_width=True)

    with tB:
        dfn = yukle_mukellef_notlari()
        st.info(f"Toplam not kaydı: {len(dfn)}")
        st.dataframe(dfn, use_container_width=True)

    with tC:
        st.subheader("Personel Ekle / Güncelle")
        dfp = yukle_personel()

        c1, c2, c3 = st.columns([2,2,1])
        with c1:
            p_ad = st.text_input("Personel Adı Soyadı")
        with c2:
            p_tel = st.text_input("Telefon (örn 905xxxxxxxxx veya 05xxxxxxxxx)")
        with c3:
            p_aktif = st.selectbox("Aktif", ["Evet","Hayır"], index=0)

        if st.button("➕ Personel Kaydet", type="primary", use_container_width=True):
            if not str(p_ad).strip():
                st.error("Personel adı boş olamaz.")
            else:
                tel_norm = normalize_phone(p_tel)
                if not tel_norm:
                    st.error("Telefon numarası geçersiz.")
                else:
                    mask = dfp["Personel"].astype(str).str.strip().str.lower() == str(p_ad).strip().lower()
                    if mask.any():
                        idx = dfp[mask].index[0]
                        dfp.loc[idx, "Telefon"] = tel_norm
                        dfp.loc[idx, "Aktif"] = p_aktif
                    else:
                        dfp = pd.concat([dfp, pd.DataFrame([{
                            "Personel": str(p_ad).strip(),
                            "Telefon": tel_norm,
                            "Aktif": p_aktif
                        }])], ignore_index=True)
                    kaydet_personel(dfp)
                    st.success("Kaydedildi.")

        st.divider()
        st.subheader("Personel Listesi")
        st.dataframe(dfp, use_container_width=True)

    with tD:
        dfi = yukle_is_takip()
        st.info(f"Toplam iş kaydı: {len(dfi)}")
        st.dataframe(dfi, use_container_width=True)
