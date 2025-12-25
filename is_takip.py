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
    page_title="Müşavir Kulesi (Analiz + İş Takip)",
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
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3) SESSION STATE
# ==========================================
for k in ["sonuclar", "mukellef_db", "personel_db", "is_takip_db"]:
    if k not in st.session_state:
        st.session_state[k] = None

# ==========================================
# 4) YARDIMCI FONKSİYONLAR
# ==========================================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if len(p) == 10:          # 5xxxxxxxxx
        p = "90" + p
    if len(p) == 11 and p.startswith("0"):  # 05xxxxxxxxx
        p = "9" + p
    # 90 ile başlamıyorsa ama 12 hane gibi hatalıysa olduğu gibi bırakmayalım
    if len(p) < 11:
        return ""
    return p

def parse_phones(cell_text: str) -> list:
    """
    Telefon hücresinde birden fazla numarayı yakalar.
    Destek: +90 5xx xxx xx xx, 05xx xxx xx xx, 5xxxxxxxxx vb.
    """
    t = str(cell_text or "")
    if not t.strip():
        return []
    # genel gsm yakalama
    candidates = re.findall(r"(?:\+?90\s*)?(?:0\s*)?5\d{2}\s*\d{3}\s*\d{2}\s*\d{2}", t)
    out = []
    for c in candidates:
        n = normalize_phone(c)
        if n and n not in out:
            out.append(n)

    # fallback: tüm rakamları birleştirip 5xxxxxxxxx desenini ara
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
        raw = pd.read_excel(KALICI_EXCEL_YOLU, dtype=str)
        raw = raw.fillna("")
        # Kalıcı dosyada başlık olmayabilir; her iki durumu da destekleyelim
        if set([c.lower() for c in raw.columns]) >= {"a_unvan", "b_tc", "c_vkn", "d_tel", "d_tel_all"}:
            df = raw.copy()
        else:
            # header yok varsayımı
            raw2 = pd.read_excel(KALICI_EXCEL_YOLU, dtype=str, header=None).fillna("")
            df = pd.DataFrame()
            df["A_UNVAN"] = raw2.iloc[:, 0].astype(str).str.strip() if raw2.shape[1] > 0 else ""
            df["B_TC"]    = raw2.iloc[:, 1].astype(str).str.strip() if raw2.shape[1] > 1 else ""
            df["C_VKN"]   = raw2.iloc[:, 2].astype(str).str.strip() if raw2.shape[1] > 2 else ""
            df["D_TEL"]   = raw2.iloc[:, 3].astype(str).str.strip() if raw2.shape[1] > 3 else ""
            # D_TEL_ALL yoksa D_TEL üzerinden üret
            df["D_TEL_ALL"] = df["D_TEL"].apply(lambda x: " | ".join(parse_phones(x)))
        # her yüklemede garanti edelim
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
    # kalıcıda başlıkla kaydedelim (daha güvenli)
    out = df[["A_UNVAN", "B_TC", "C_VKN", "D_TEL", "D_TEL_ALL"]].copy()
    out.to_excel(KALICI_EXCEL_YOLU, index=False)

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

    # kolon güvence
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

# Açılış yüklemeleri
if st.session_state["mukellef_db"] is None:
    yukle_mukellef_kalici()
if st.session_state["personel_db"] is None:
    yukle_personel()
if st.session_state["is_takip_db"] is None:
    yukle_is_takip()

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

def risk_mesaji_olustur(row: dict) -> str:
    donem_str = row.get("Dönem", "") or "Bilinmiyor"
    pos = float(row.get("POS", 0.0) or 0.0)
    beyan = float(row.get("Beyan", 0.0) or 0.0)
    fark = float(row.get("Fark", 0.0) or 0.0)
    oran = (fark / beyan * 100.0) if beyan > 0 else 0.0
    return (
        "🚨🚨 *KDV RİSK ALARMI* 🚨🚨\n"
        f"📅 *Dönem:* {donem_str}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🏢 *Firma:* {row.get('Mükellef','')}\n"
        f"🆔 *VKN/TCKN:* {row.get('VKN','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"💳 *POS (KDV Dahil):* {para_formatla(pos)}\n"
        f"🧾 *Beyan (Matrah(Aylık)+KDV):* {para_formatla(beyan)}\n"
        f"📌 *FARK:* {para_formatla(fark)}\n"
        f"📈 *Sapma Oranı:* {yuzde_formatla(oran)}\n"
        "━━━━━━━━━━━━━━━━\n"
        "⚠️ *İnceleme Önerisi:* POS tahsilatı beyan toplamını aşıyor."
    )

# ==========================================
# 7) İŞ TAKİP: OLUŞTUR / GÜNCELLE
# ==========================================
def yeni_is_id() -> str:
    # kısa ve benzersiz
    return "IS-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()

def oncelik_hesapla(fark: float, tip: str) -> str:
    if tip == "OKUNAMADI":
        return "Orta"
    if fark >= 50000:
        return "Yüksek"
    if fark >= 10000:
        return "Orta"
    return "Düşük"

def otomatik_is_olustur_guncelle(df_is: pd.DataFrame, analiz_row: dict) -> pd.DataFrame:
    """
    Analizden gelen RISKLI/OKUNAMADI kayıtları için iş açar (varsa günceller).
    Anahtar: Tip + Dönem + VKN
    """
    tip = analiz_row.get("Durum", "")
    if tip not in ["RISKLI", "OKUNAMADI"]:
        return df_is

    donem = analiz_row.get("Dönem", "Bilinmiyor")
    vkn = analiz_row.get("VKN", "Bulunamadı")
    mukellef = analiz_row.get("Mükellef", "")
    pos = analiz_row.get("POS", 0.0)
    beyan = analiz_row.get("Beyan", 0.0)
    fark = analiz_row.get("Fark", 0.0)

    try:
        fark_num = float(fark)
    except Exception:
        fark_num = 0.0

    oncelik = oncelik_hesapla(fark_num, tip)

    key_mask = (
        (df_is["Tip"].astype(str) == tip) &
        (df_is["Dönem"].astype(str) == str(donem)) &
        (df_is["VKN"].astype(str) == str(vkn))
    )
    if key_mask.any():
        idx = df_is[key_mask].index[0]
        df_is.loc[idx, "Öncelik"] = oncelik
        df_is.loc[idx, "POS"] = str(pos)
        df_is.loc[idx, "Beyan"] = str(beyan)
        df_is.loc[idx, "Fark"] = str(fark)
        df_is.loc[idx, "GuncellemeZamani"] = now_str()
    else:
        # mükellef telefonları
        tel_all = ""
        dfm = st.session_state.get("mukellef_db")
        if dfm is not None and not dfm.empty and vkn:
            hit = dfm[dfm["C_VKN"].astype(str) == str(vkn)]
            if hit.empty:
                hit = dfm[dfm["B_TC"].astype(str) == str(vkn)]
            if not hit.empty:
                tel_all = str(hit.iloc[0].get("D_TEL_ALL", ""))

        yeni = {
            "IsID": yeni_is_id(),
            "Tip": tip,
            "Durum": "AÇIK",
            "Öncelik": oncelik,
            "Dönem": donem,
            "Mükellef": mukellef,
            "VKN": vkn,
            "Konu": "KDV Risk İncelemesi" if tip == "RISKLI" else "Beyanname Okunamadı",
            "Açıklama": "Analiz sisteminden otomatik oluştu.",
            "SonTarih": "",
            "Sorumlu": "",
            "SorumluTel": "",
            "MükellefTelAll": tel_all,
            "POS": str(pos),
            "Beyan": str(beyan),
            "Fark": str(fark),
            "Not": "",
            "OlusturmaZamani": now_str(),
            "GuncellemeZamani": now_str(),
            "KapanisZamani": ""
        }
        df_is = pd.concat([df_is, pd.DataFrame([yeni])], ignore_index=True)

    return df_is

# ==========================================
# 8) ANA MENÜ (AYNEN)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.header("MÜŞAVİR PANELİ")
    secim = st.radio("MENÜ", ["1. Excel Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"])

# ==========================================
# 9) 1. MENÜ: MÜKELLEF VERİTABANI YÜKLE (ÇOKLU NUMARA DESTEK)
# ==========================================
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

    if st.session_state.get("mukellef_db") is not None and not st.session_state["mukellef_db"].empty:
        st.divider()
        st.subheader("Kayıtlı Liste (Özet)")
        st.write(f"Toplam: {len(st.session_state['mukellef_db'])}")
        st.dataframe(st.session_state["mukellef_db"][["A_UNVAN","B_TC","C_VKN","D_TEL_ALL"]].head(20), use_container_width=True)

# ==========================================
# 10) 2. MENÜ: KDV ANALİZ + İŞ EMRİ (SİZİN İSTEDİĞİNİZ)
# ==========================================
elif secim == "2. KDV Analiz Robotu":
    st.title("🧠 KDV Analiz Robotu + 🗂️ İş Takip / İş Emri")

    if st.session_state.get("mukellef_db") is None or st.session_state["mukellef_db"].empty:
        st.warning("⚠️ Önce '1. Excel Listesi Yükle' menüsünden mükellef veritabanını yükleyin.")
        st.stop()

    tabA, tabB = st.tabs(["📄 Beyanname Analizi", "🧾 İş Emri Aç & Takip Et"])

    # ---------------------- TAB A: ANALİZ ----------------------
    with tabA:
        pdf_files = st.file_uploader("PDF yükleyin (tek dosyada çok beyanname olabilir)", type=["pdf"], accept_multiple_files=True)

        if pdf_files and st.button("🚀 ANALİZİ BAŞLAT", type="primary", use_container_width=True):
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

            # mukellef DB hızlı erişim map
            dfm = st.session_state["mukellef_db"].copy()
            vkn_map = {str(v): i for i, v in enumerate(dfm["C_VKN"].astype(str).tolist()) if str(v).strip()}
            tc_map  = {str(v): i for i, v in enumerate(dfm["B_TC"].astype(str).tolist()) if str(v).strip()}

            for i, block in enumerate(all_blocks, start=1):
                progress.progress(int(i / total * 100))
                info.info(f"İşleniyor: {i}/{total}")

                ay, yil = donem_bul(block)
                donem = f"{ay} / {yil}" if ay and yil else (yil or ay or "Bilinmiyor")

                vkn = vkn_bul(block) or ""
                isim = "Bilinmeyen"
                tel_all = ""

                idx_m = None
                if vkn and vkn in vkn_map:
                    idx_m = vkn_map[vkn]
                elif vkn and vkn in tc_map:
                    idx_m = tc_map[vkn]

                if idx_m is not None:
                    isim = str(dfm.iloc[idx_m].get("A_UNVAN", "Bilinmeyen"))
                    tel_all = str(dfm.iloc[idx_m].get("D_TEL_ALL", ""))
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

            # Otomatik işler oluştur/güncelle
            df_is = yukle_is_takip()
            for _, r in df_res.iterrows():
                if r["Durum"] in ["RISKLI", "OKUNAMADI"]:
                    df_is = otomatik_is_olustur_guncelle(df_is, r.to_dict())
            kaydet_is_takip(df_is)
            st.toast("🗂️ İş Takip güncellendi (otomatik işler).")

        # Sonuçlar
        if st.session_state.get("sonuclar") is not None and not st.session_state["sonuclar"].empty:
            df = st.session_state["sonuclar"]
            risk = df[df["Durum"] == "RISKLI"]
            temiz = df[df["Durum"] == "TEMIZ"]
            okunamadi = df[df["Durum"] == "OKUNAMADI"]

            t1, t2, t3 = st.tabs([f"🚨 Riskli ({len(risk)})", f"✅ Temiz ({len(temiz)})", f"❓ Okunamadı ({len(okunamadi)})"])

            with t1:
                tum_num = st.checkbox("Mükellef mesajında TÜM numaralara gönder", value=True)
                for idx, row in risk.iterrows():
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown(f"""
                        <div class='card risk-card'>
                            <div class='card-title'>{row['Mükellef']}</div>
                            <div class='card-sub'>Dönem: {row['Dönem']} | VKN/TCKN: {row['VKN']}</div>
                            <div style='display:flex; gap:15px; margin-top:10px'>
                                <div><span class='stat-lbl'>POS</span><br><span class='stat-val'>{para_formatla(row['POS'])}</span></div>
                                <div><span class='stat-lbl'>BEYAN</span><br><span class='stat-val'>{para_formatla(row['Beyan'])}</span></div>
                            </div>
                            <div style='color:#d32f2f; font-weight:bold; margin-top:10px; font-size:16px;'>
                                FARK: {para_formatla(row['Fark'])}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    with col2:
                        if st.button("🚨 İHBAR ET", key=f"ih_{idx}", type="primary", use_container_width=True):
                            msg = risk_mesaji_olustur(row.to_dict())
                            if whatsapp_gonder("SABIT", msg):
                                st.toast("✅ Sabit ihbar numarasına gönderildi.")

                            # İsterseniz mükellefe de
                            tels = parse_phones(row.get("MükellefTelAll", ""))
                            if tels:
                                if tum_num:
                                    sent = whatsapp_gonder_coklu(tels, msg)
                                    st.toast(f"📨 Mükellefe {sent} numaraya gönderildi.")
                                else:
                                    if whatsapp_gonder(tels[0], msg):
                                        st.toast("📨 Mükellefe birincil numaraya gönderildi.")

            with t2:
                st.dataframe(temiz, use_container_width=True)
            with t3:
                st.dataframe(okunamadi, use_container_width=True)

    # ---------------------- TAB B: İŞ EMRİ AÇ + LİSTE + TAKİP ----------------------
    with tabB:
        st.subheader("🧾 İş Emri Aç (Manuel)")
        dfm = st.session_state["mukellef_db"].copy()
        dfp = yukle_personel()
        dfi = yukle_is_takip()

        colA, colB = st.columns([2, 2])
        with colA:
            mukellef_sec = st.selectbox("Mükellef Seç", dfm["A_UNVAN"].astype(str).tolist())
            hit = dfm[dfm["A_UNVAN"].astype(str) == str(mukellef_sec)]
            muk = hit.iloc[0].to_dict() if not hit.empty else {}
            vkn_val = str(muk.get("C_VKN", "")).strip() or str(muk.get("B_TC", "")).strip()
            tel_all = str(muk.get("D_TEL_ALL", "")).strip()
            tel_list = parse_phones(tel_all)
            st.caption(f"VKN/TCKN: {vkn_val or '-'}")
            st.caption(f"Mükellef Telefon(lar): {tel_all or '-'}")

            konu = st.text_input("İş Konusu", placeholder="Örn: Ocak 2024 KDV evrak tamamlama")
            aciklama = st.text_area("İş Açıklaması / Talimat", height=110, placeholder="İstediğiniz veriyi/evrakı burada belirtin.")
            oncelik = st.selectbox("Öncelik", ["Yüksek", "Orta", "Düşük"], index=1)
        with colB:
            son_tarih = st.date_input("Son Tarih", value=date.today())
            donem = st.text_input("Dönem (opsiyonel)", placeholder="Örn: Ocak / 2024")

            aktif_personel = dfp[dfp["Aktif"].astype(str).str.lower().isin(["evet", "yes", "true", "1"])].copy()
            personel_ops = ["(Atama Yok)"] + aktif_personel["Personel"].astype(str).tolist()
            sorumlu = st.selectbox("Sorumlu Personel", personel_ops)

            # WhatsApp gönderim seçenekleri
            st.markdown("**WhatsApp Bildirimi**")
            bildir_personel = st.checkbox("Personeli WhatsApp ile bilgilendir", value=True)
            bildir_mukellef = st.checkbox("Mükellefi WhatsApp ile bilgilendir", value=False)
            muk_tum_num = st.checkbox("Mükellefe gönderimde TÜM numaralara gönder", value=True)

        if st.button("✅ İŞ EMRİNİ OLUŞTUR", type="primary", use_container_width=True):
            if not str(konu).strip():
                st.error("İş konusu boş olamaz.")
            elif not str(aciklama).strip():
                st.error("İş açıklaması boş olamaz.")
            else:
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
                    "VKN": vkn_val,
                    "Konu": str(konu).strip(),
                    "Açıklama": str(aciklama).strip(),
                    "SonTarih": str(son_tarih),
                    "Sorumlu": "" if sorumlu == "(Atama Yok)" else str(sorumlu),
                    "SorumluTel": sorumlu_tel,
                    "MükellefTelAll": tel_all,
                    "POS": "",
                    "Beyan": "",
                    "Fark": "",
                    "Not": "",
                    "OlusturmaZamani": now_str(),
                    "GuncellemeZamani": now_str(),
                    "KapanisZamani": ""
                }

                dfi = pd.concat([dfi, pd.DataFrame([yeni])], ignore_index=True)
                kaydet_is_takip(dfi)
                st.success(f"İş emri oluşturuldu: {isid}")
                st.toast("🗂️ Yapılacak işler listesine eklendi.")

                # WhatsApp bildirimleri
                if bildir_personel and sorumlu_tel:
                    msg_p = mesaj_is_emri_personel(yeni)
                    ok = whatsapp_gonder(sorumlu_tel, msg_p)
                    if ok:
                        st.toast("📨 Personel bilgilendirildi.")
                    else:
                        st.warning("Personel bilgilendirilemedi (telefon/API kontrol ediniz).")

                if bildir_mukellef and tel_list:
                    msg_m = mesaj_is_emri_mukellef(yeni)
                    if muk_tum_num:
                        sent = whatsapp_gonder_coklu(tel_list, msg_m)
                        st.toast(f"📨 Mükellefe {sent} numaraya gönderildi.")
                    else:
                        ok = whatsapp_gonder(tel_list[0], msg_m)
                        if ok:
                            st.toast("📨 Mükellefe birincil numaraya gönderildi.")
                        else:
                            st.warning("Mükellefe gönderilemedi.")

        st.divider()
        st.subheader("📌 Yapılacak İşler Listesi (Takip)")

        dfi = yukle_is_takip()  # güncel çek
        # filtreler
        f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
        with f1:
            filt_durum = st.selectbox("Durum", ["(Tümü)", "AÇIK", "İNCELEMEDE", "KAPANDI", "İPTAL"])
        with f2:
            filt_tip = st.selectbox("Tip", ["(Tümü)", "MANUEL", "RISKLI", "OKUNAMADI"])
        with f3:
            filt_oncelik = st.selectbox("Öncelik", ["(Tümü)", "Yüksek", "Orta", "Düşük"])
        with f4:
            filt_muk = st.text_input("Mükellef Ara (parça)", placeholder="örn: tekstil")

        view = dfi.copy()
        if filt_durum != "(Tümü)":
            view = view[view["Durum"].astype(str) == filt_durum]
        if filt_tip != "(Tümü)":
            view = view[view["Tip"].astype(str) == filt_tip]
        if filt_oncelik != "(Tümü)":
            view = view[view["Öncelik"].astype(str) == filt_oncelik]
        if str(filt_muk).strip():
            view = view[view["Mükellef"].astype(str).str.lower().str.contains(str(filt_muk).strip().lower(), na=False)]

        # Son tarih yaklaşıyor uyarısı için sıralama
        def safe_date(s):
            try:
                return pd.to_datetime(str(s), errors="coerce")
            except Exception:
                return pd.NaT

        view["_son"] = view["SonTarih"].apply(safe_date)
        view = view.sort_values(by=["Durum", "_son"], ascending=[True, True]).drop(columns=["_son"], errors="ignore")

        st.dataframe(view, use_container_width=True)

        st.divider()
        st.subheader("🛠️ Seçili İş Üzerinde İşlem")

        if view.empty:
            st.info("Filtreye uygun iş bulunamadı.")
        else:
            is_list = view["IsID"].astype(str).tolist()
            sec_isid = st.selectbox("İş Seç (IsID)", is_list)

            row = dfi[dfi["IsID"].astype(str) == str(sec_isid)]
            if row.empty:
                st.error("İş bulunamadı.")
            else:
                r = row.iloc[0].to_dict()

                c1, c2 = st.columns([2, 2])
                with c1:
                    yeni_durum = st.selectbox("Yeni Durum", ["AÇIK", "İNCELEMEDE", "KAPANDI", "İPTAL"], index=0)
                    yeni_son = st.text_input("Son Tarih (YYYY-MM-DD)", value=str(r.get("SonTarih","")))
                    yeni_not = st.text_area("Not / Yapılan İşlem", value=str(r.get("Not","")), height=110)

                with c2:
                    st.markdown("**İş Özeti**")
                    st.write(f"**İş No:** {r.get('IsID','')}")
                    st.write(f"**Tip:** {r.get('Tip','')} | **Öncelik:** {r.get('Öncelik','')}")
                    st.write(f"**Mükellef:** {r.get('Mükellef','')}")
                    st.write(f"**VKN:** {r.get('VKN','')}")
                    st.write(f"**Konu:** {r.get('Konu','')}")
                    st.write(f"**Sorumlu:** {r.get('Sorumlu','') or '-'}")

                    st.markdown("**Hatırlatma / Mesaj**")
                    hedef = st.selectbox("Mesaj Gönder (opsiyonel)", ["Gönderme", "Sorumlu Personele", "Mükellefe", "Serbest Numara"])
                    serbest = ""
                    tum_muk = False
                    if hedef == "Serbest Numara":
                        serbest = st.text_input("Serbest Numara", placeholder="905xxxxxxxxx")
                    if hedef == "Mükellefe":
                        tum_muk = st.checkbox("Mükellefe TÜM numaralara gönder", value=True)

                if st.button("💾 GÜNCELLE", type="primary", use_container_width=True):
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

# ==========================================
# 11) 3. MENÜ: PROFESYONEL MESAJ
# ==========================================
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

# ==========================================
# 12) 4. MENÜ: TASDİK ROBOTU (MÜKELLEF + PERSONEL)
# ==========================================
elif secim == "4. Tasdik Robotu":
    st.title("🤖 Tasdik Robotu / Kayıtlar")

    tA, tB, tC = st.tabs(["📋 Mükellef Listesi", "👥 Personel / Numara Yönetimi", "🗂️ İş Takip (Ham Kayıt)"])

    with tA:
        dfm = st.session_state.get("mukellef_db")
        if dfm is None or dfm.empty:
            st.warning("Mükellef listesi yok.")
        else:
            st.info(f"Toplam {len(dfm)} kayıt")
            st.dataframe(dfm[["A_UNVAN","B_TC","C_VKN","D_TEL_ALL"]], use_container_width=True)

    with tB:
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

    with tC:
        dfi = yukle_is_takip()
        st.info(f"Toplam iş kaydı: {len(dfi)}")
        st.dataframe(dfi, use_container_width=True)
