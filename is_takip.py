import os
import re
import time
import requests
import pandas as pd
import pdfplumber
import streamlit as st
from datetime import datetime

# ==========================================
# 1) AYARLAR & SABİTLER (GENEL YAPI KORUNUR)
# ==========================================
st.set_page_config(
    page_title="Müşavir Kulesi (Canlı Akış + İş Takip)",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# WhatsApp (Green-API)
ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

# Kalıcı dosyalar
KALICI_EXCEL_YOLU = "mukellef_db_kalici.xlsx"
ARSIV_DOSYASI = "arsiv_risk_kayitlari.xlsx"
PERSONEL_DOSYASI = "personel_db.xlsx"
IS_TAKIP_DOSYASI = "is_takip.xlsx"

# Tek PDF içinde çoklu beyanname ayıracı
BEYANNAME_AYRACI = "KATMA DEĞER VERGİSİ BEYANNAMESİ"

# Aranacak ifadeler (beyan)
MATRAH_AYLIK_IFADESI = "Teslim ve Hizmetlerin Karşılığını Teşkil Eden Bedel (aylık)"
KDV_TOPLAM_IFADESI = "Toplam Katma Değer Vergisi"
KDV_HESAPLANAN_IFADESI = "Hesaplanan Katma Değer Vergisi"

# POS satırı (SİZİN İSTEDİĞİNİZ)
POS_SATIRI_TAM = "Kredi Kartı İle Tahsil Edilen Teslim ve Hizmetlerin KDV Dahil Karşılığını Teşkil Eden Bedel"

# SADECE PARA FORMATINI yakala
AMOUNT_REGEX = r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"

# Risk eşiği
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
if "sonuclar" not in st.session_state:
    st.session_state["sonuclar"] = None
if "mukellef_db" not in st.session_state:
    st.session_state["mukellef_db"] = None
if "personel_db" not in st.session_state:
    st.session_state["personel_db"] = None
if "is_takip_db" not in st.session_state:
    st.session_state["is_takip_db"] = None

# ==========================================
# 4) YARDIMCI FONKSİYONLAR
# ==========================================
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if len(p) == 10:
        p = "90" + p
    if len(p) == 11 and p.startswith("0"):
        p = "9" + p
    return p

def text_to_float(text) -> float:
    try:
        if text is None:
            return 0.0
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

def para_formatla(deger: float) -> str:
    try:
        return "{:,.2f} TL".format(float(deger)).replace(",", "X").replace(".", ",").replace("X", ".")
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

def mukellef_tel_bul(vkn: str = "", unvan: str = "") -> str:
    """Mükellef excelinden telefon getirir (D_TEL)."""
    df = st.session_state.get("mukellef_db")
    if df is None or df.empty:
        return ""
    vkn = str(vkn or "").strip()
    unvan = str(unvan or "").strip()

    if vkn:
        hit = df[df["C_VKN"].astype(str) == vkn]
        if hit.empty:
            hit = df[df["B_TC"].astype(str) == vkn]
        if not hit.empty:
            return normalize_phone(hit.iloc[0].get("D_TEL", ""))

    if unvan:
        hit2 = df[df["A_UNVAN"].astype(str).str.lower() == unvan.lower()]
        if not hit2.empty:
            return normalize_phone(hit2.iloc[0].get("D_TEL", ""))

    return ""

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
    try:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return 0.0

        k1 = "Kredi Kartı İle Tahsil Edilen"
        k2 = "KDV Dahil"
        k3 = "Teşkil Eden"
        k4 = "Bedel"

        for i, ln in enumerate(lines):
            if re.search(re.escape(k1), ln, flags=re.IGNORECASE):
                window_lines = lines[i:i + 10]
                joined = " ".join(window_lines)

                has_all = (
                    re.search(k1, joined, flags=re.IGNORECASE)
                    and re.search(k2, joined, flags=re.IGNORECASE)
                    and re.search(k3, joined, flags=re.IGNORECASE)
                    and re.search(k4, joined, flags=re.IGNORECASE)
                )

                if has_all:
                    amt = re.search(AMOUNT_REGEX, joined)
                    if amt:
                        val = text_to_float(amt.group(1))
                        if 0 < val <= MAX_TUTAR_SANITY:
                            return val

                for j in range(i, min(i + 20, len(lines))):
                    amt2 = re.search(AMOUNT_REGEX, lines[j])
                    if amt2:
                        val2 = text_to_float(amt2.group(1))
                        if 0 < val2 <= MAX_TUTAR_SANITY:
                            return val2
        return 0.0
    except Exception:
        return 0.0

def donem_bul(block_text: str):
    t = str(block_text or "")
    if not t.strip():
        return (None, None)

    t1 = re.sub(r"\s+", " ", t).strip()
    ay_map = {
        "ocak": "Ocak",
        "şubat": "Şubat", "subat": "Şubat",
        "mart": "Mart",
        "nisan": "Nisan",
        "mayıs": "Mayıs", "mayis": "Mayıs",
        "haziran": "Haziran",
        "temmuz": "Temmuz",
        "ağustos": "Ağustos", "agustos": "Ağustos",
        "eylül": "Eylül", "eylul": "Eylül",
        "ekim": "Ekim",
        "kasım": "Kasım", "kasim": "Kasım",
        "aralık": "Aralık", "aralik": "Aralık",
    }
    ay_regex = r"(ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik)"

    m = re.search(rf"Yıl\s*Ay\s*(20\d{{2}}).{{0,200}}?\b{ay_regex}\b", t1, flags=re.IGNORECASE)
    if m:
        yil = m.group(1)
        ay = ay_map.get((m.group(2) or "").lower())
        return (ay, yil)

    m2 = re.search(rf"Yıl\s*(20\d{{2}}).{{0,240}}?Ay.{{0,240}}?\b{ay_regex}\b", t1, flags=re.IGNORECASE)
    if m2:
        yil = m2.group(1)
        ay = ay_map.get((m2.group(2) or "").lower())
        return (ay, yil)

    yil = None
    ay = None
    m_yil = re.search(r"\b(20\d{2})\b", t1)
    if m_yil:
        yil = m_yil.group(1)
    m_ay = re.search(rf"\b{ay_regex}\b", t1, flags=re.IGNORECASE)
    if m_ay:
        ay = ay_map.get(m_ay.group(1).lower())
    return (ay, yil)

def risk_mesaji_olustur(row: dict) -> str:
    donem_str = row.get("Dönem", "") or "Bilinmiyor"
    pos = float(row.get("POS", 0.0) or 0.0)
    beyan = float(row.get("Beyan", 0.0) or 0.0)
    fark = float(row.get("Fark", 0.0) or 0.0)
    oran = (fark / beyan * 100.0) if beyan > 0 else 0.0

    mesaj = (
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
    return mesaj

def log_yaz(logs, terminal, msg, color="#f0f0f0"):
    logs.append(f"<span style='color:{color};'>{msg}</span>")
    terminal.markdown(
        f"<div class='terminal-window'>{'<br>'.join(logs[-280:])}</div>",
        unsafe_allow_html=True
    )

# ---------- Kalıcı DB yükle/kaydet ----------
def kalici_mukellef_yukle():
    if os.path.exists(KALICI_EXCEL_YOLU):
        try:
            raw_df = pd.read_excel(KALICI_EXCEL_YOLU, dtype=str, header=None)
            df = pd.DataFrame()
            df["A_UNVAN"] = raw_df.iloc[:, 0].astype(str).str.strip()
            df["B_TC"] = raw_df.iloc[:, 1].astype(str).str.strip() if raw_df.shape[1] > 1 else ""
            df["C_VKN"] = raw_df.iloc[:, 2].astype(str).str.strip() if raw_df.shape[1] > 2 else ""
            df["D_TEL"] = (
                raw_df.iloc[:, 3].astype(str).str.strip().str.replace(r"\D", "", regex=True)
                if raw_df.shape[1] > 3 else ""
            )
            st.session_state["mukellef_db"] = df.fillna("")
            return True
        except Exception:
            return False
    return False

def personel_yukle():
    if os.path.exists(PERSONEL_DOSYASI):
        try:
            df = pd.read_excel(PERSONEL_DOSYASI, dtype=str)
            if df.empty:
                df = pd.DataFrame(columns=["Personel", "Telefon", "Aktif"])
        except Exception:
            df = pd.DataFrame(columns=["Personel", "Telefon", "Aktif"])
    else:
        df = pd.DataFrame(columns=["Personel", "Telefon", "Aktif"])
    if "Aktif" not in df.columns:
        df["Aktif"] = "Evet"
    df = df.fillna("")
    st.session_state["personel_db"] = df
    return df

def personel_kaydet(df: pd.DataFrame):
    df = df.fillna("")
    df.to_excel(PERSONEL_DOSYASI, index=False)
    st.session_state["personel_db"] = df

def is_takip_yukle():
    if os.path.exists(IS_TAKIP_DOSYASI):
        try:
            df = pd.read_excel(IS_TAKIP_DOSYASI, dtype=str)
        except Exception:
            df = pd.DataFrame()
    else:
        df = pd.DataFrame()

    if df.empty:
        df = pd.DataFrame(columns=[
            "IsID", "Dönem", "Mükellef", "VKN", "Tip", "Durum", "Öncelik",
            "POS", "Beyan", "Fark", "Sorumlu", "SorumluTel",
            "Not", "OlusturmaZamani", "GuncellemeZamani", "KapanisZamani"
        ])
    df = df.fillna("")
    st.session_state["is_takip_db"] = df
    return df

def is_takip_kaydet(df: pd.DataFrame):
    df = df.fillna("")
    df.to_excel(IS_TAKIP_DOSYASI, index=False)
    st.session_state["is_takip_db"] = df

# ---------- Arşiv ----------
def arsiv_oku() -> pd.DataFrame:
    if os.path.exists(ARSIV_DOSYASI):
        try:
            return pd.read_excel(ARSIV_DOSYASI, dtype=str)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def arsive_ekle(df_kayit: pd.DataFrame):
    if df_kayit is None or df_kayit.empty:
        return
    keep_cols = ["Dönem", "Mükellef", "VKN", "POS", "Beyan", "Fark", "Durum", "KayitZamani"]
    for c in keep_cols:
        if c not in df_kayit.columns:
            df_kayit[c] = ""
    df_kayit = df_kayit[keep_cols].copy()

    if os.path.exists(ARSIV_DOSYASI):
        try:
            old = pd.read_excel(ARSIV_DOSYASI, dtype=str)
        except Exception:
            old = pd.DataFrame(columns=keep_cols)
    else:
        old = pd.DataFrame(columns=keep_cols)

    def norm(x): return str(x).strip()
    for col in ["POS", "Beyan", "Fark"]:
        old[col] = old[col].apply(norm) if col in old.columns else ""
        df_kayit[col] = df_kayit[col].apply(norm)

    old["__key"] = old["Dönem"].astype(str) + "|" + old["VKN"].astype(str) + "|" + old["POS"] + "|" + old["Beyan"] + "|" + old["Fark"] + "|" + old["Durum"].astype(str)
    df_kayit["__key"] = df_kayit["Dönem"].astype(str) + "|" + df_kayit["VKN"].astype(str) + "|" + df_kayit["POS"] + "|" + df_kayit["Beyan"] + "|" + df_kayit["Fark"] + "|" + df_kayit["Durum"].astype(str)

    combined = pd.concat([old, df_kayit], ignore_index=True)
    combined = combined.drop_duplicates(subset="__key", keep="first")
    combined = combined.drop(columns="__key", errors="ignore")
    combined.to_excel(ARSIV_DOSYASI, index=False)

# ---------- İş Takip ----------
def oncelik_hesapla(fark: float, tip: str) -> str:
    if tip == "OKUNAMADI":
        return "Orta"
    if fark >= 50000:
        return "Yüksek"
    if fark >= 10000:
        return "Orta"
    return "Düşük"

def is_id_uret(donem: str, vkn: str, tip: str) -> str:
    return f"{donem}|{vkn}|{tip}"

def is_olustur_veya_guncelle(df_is: pd.DataFrame, row: dict) -> pd.DataFrame:
    donem = row.get("Dönem", "Bilinmiyor")
    vkn = row.get("VKN", "Bulunamadı")
    tip = row.get("Durum", "")
    isid = is_id_uret(donem, vkn, tip)

    pos = row.get("POS", 0.0)
    beyan = row.get("Beyan", 0.0)
    fark = row.get("Fark", 0.0)

    try:
        fark_num = float(fark)
    except Exception:
        fark_num = 0.0

    oncelik = oncelik_hesapla(fark_num, tip)

    mask = (df_is["IsID"].astype(str) == str(isid))
    if mask.any():
        idx = df_is[mask].index[0]
        df_is.loc[idx, "POS"] = str(pos)
        df_is.loc[idx, "Beyan"] = str(beyan)
        df_is.loc[idx, "Fark"] = str(fark)
        df_is.loc[idx, "Öncelik"] = oncelik
        df_is.loc[idx, "GuncellemeZamani"] = now_str()
    else:
        yeni = {
            "IsID": isid,
            "Dönem": donem,
            "Mükellef": row.get("Mükellef", ""),
            "VKN": vkn,
            "Tip": tip,                 # RISKLI / OKUNAMADI
            "Durum": "AÇIK",
            "Öncelik": oncelik,
            "POS": str(pos),
            "Beyan": str(beyan),
            "Fark": str(fark),
            "Sorumlu": "",
            "SorumluTel": "",
            "Not": "",
            "OlusturmaZamani": now_str(),
            "GuncellemeZamani": now_str(),
            "KapanisZamani": ""
        }
        df_is = pd.concat([df_is, pd.DataFrame([yeni])], ignore_index=True)

    return df_is

def manuel_is_id_uret() -> str:
    return "MANUEL-" + datetime.now().strftime("%Y%m%d%H%M%S")

def manuel_is_ekle(df_is: pd.DataFrame, donem: str, mukellef: str, vkn: str, konu: str, aciklama: str,
                   oncelik: str, sorumlu: str, sorumlu_tel: str) -> pd.DataFrame:
    isid = manuel_is_id_uret()
    not_text = f"Konu: {konu}\nAçıklama: {aciklama}".strip()

    yeni = {
        "IsID": isid,
        "Dönem": donem or "",
        "Mükellef": mukellef or "",
        "VKN": vkn or "",
        "Tip": "MANUEL",
        "Durum": "AÇIK",
        "Öncelik": oncelik or "Orta",
        "POS": "",
        "Beyan": "",
        "Fark": "",
        "Sorumlu": sorumlu or "",
        "SorumluTel": sorumlu_tel or "",
        "Not": not_text,
        "OlusturmaZamani": now_str(),
        "GuncellemeZamani": now_str(),
        "KapanisZamani": ""
    }
    df_is = pd.concat([df_is, pd.DataFrame([yeni])], ignore_index=True)
    return df_is

def atama_mesaji_olustur(is_row: dict) -> str:
    return (
        "📌 *YENİ İŞ ATAMASI*\n"
        f"🆔 *İş:* {is_row.get('IsID','')}\n"
        f"📅 *Dönem:* {is_row.get('Dönem','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🏢 *Firma:* {is_row.get('Mükellef','')}\n"
        f"🆔 *VKN:* {is_row.get('VKN','')}\n"
        f"⚠️ *Tip:* {is_row.get('Tip','')}\n"
        f"⭐ *Öncelik:* {is_row.get('Öncelik','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📝 *Not:* {is_row.get('Not','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        "Lütfen inceleyip sonuç/not giriniz."
    )

def mukellef_bilgi_mesaji_olustur(is_row: dict) -> str:
    # Mükellefe gidecek daha sade mesaj
    return (
        "Merhaba,\n"
        "Tarafınızla ilgili bir kontrol/işlem kaydı oluşturulmuştur.\n"
        f"📌 Konu/Not: {is_row.get('Not','')}\n"
        f"📅 Dönem: {is_row.get('Dönem','')}\n"
        "Geri dönüşünüz rica olunur."
    )

# ---------- Açılış yüklemeleri ----------
if st.session_state.get("mukellef_db") is None:
    kalici_mukellef_yukle()
if st.session_state.get("personel_db") is None:
    personel_yukle()
if st.session_state.get("is_takip_db") is None:
    is_takip_yukle()

# ==========================================
# 5) ANA MENÜ (AYNEN KORUNUR)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.header("MÜŞAVİR PANELİ")
    secim = st.radio("MENÜ", ["1. Excel Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"])

# ==========================================
# 6) 1. MENÜ: EXCEL YÜKLE (KALICI)
# ==========================================
if secim == "1. Excel Listesi Yükle":
    st.title("📂 Mükellef Veritabanı Yükle")
    st.info("Sütunlar: **A (Unvan), B (TCKN), C (VKN), D (Telefon)**. Bir kez yükleyince sistemde kalır.")

    colA, colB = st.columns([3, 2])
    with colA:
        uploaded_file = st.file_uploader("Excel Dosyasını Seçin", type=["xlsx", "xls"])
    with colB:
        st.write("")
        st.write("")
        if st.button("🗑️ Kayıtlı Listeyi Sil (Sıfırla)", use_container_width=True):
            try:
                if os.path.exists(KALICI_EXCEL_YOLU):
                    os.remove(KALICI_EXCEL_YOLU)
                st.session_state["mukellef_db"] = None
                st.success("Kayıtlı mükellef listesi silindi.")
            except Exception as e:
                st.error(f"Silme hatası: {e}")

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
            df = df.fillna("")
            st.session_state["mukellef_db"] = df
            df_out = df[["A_UNVAN", "B_TC", "C_VKN", "D_TEL"]]
            df_out.to_excel(KALICI_EXCEL_YOLU, index=False, header=False)
            st.success(f"✅ Başarılı! {len(df)} mükellef bilgisi yüklendi ve kalıcı kaydedildi.")
            st.dataframe(df.head(20), use_container_width=True)
        except Exception as e:
            st.error(f"❌ Dosya okunurken hata: {e}")

    if uploaded_file is None and st.session_state.get("mukellef_db") is not None:
        st.success(f"✅ Kayıtlı liste hazır. Toplam {len(st.session_state['mukellef_db'])} mükellef.")
        st.dataframe(st.session_state["mukellef_db"].head(20), use_container_width=True)

# ==========================================
# 7) 2. MENÜ: KDV ANALİZ ROBOTU + İŞ TAKİP (MANUEL İŞ DAHİL)
# ==========================================
elif secim == "2. KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz Üssü (Canlı Akış + İş Takip)")

    if st.session_state.get("mukellef_db") is None:
        st.warning("⚠️ Mükellef listesi bulunamadı. '1. Excel Listesi Yükle' menüsünden bir kez yükleyin.")
        st.stop()

    tabA, tabB = st.tabs(["📄 Beyanname Analizi", "🗂️ İş Takip (Manuel İş Emri + Atama)"])

    # ------------------ TAB A: ANALİZ ------------------
    with tabA:
        pdf_files = st.file_uploader(
            "İçinde bir veya yüzlerce beyanname olan PDF dosyasını yükleyin",
            type=["pdf"],
            accept_multiple_files=True
        )

        if pdf_files and st.button("🚀 TÜM BEYANNAMELERİ ANALİZ ET", type="primary", use_container_width=True):
            st.session_state["sonuclar"] = None
            sonuclar = []

            st.subheader("Canlı Analiz Akışı")
            terminal = st.empty()
            logs = []
            progress = st.progress(0)
            pro_text = st.empty()

            all_blocks = []
            log_yaz(logs, terminal, "Analiz başlatıldı. PDF metinleri okunuyor...", color="#ffc107")

            for pdf_file in pdf_files:
                pdf_name = getattr(pdf_file, "name", "PDF")
                try:
                    log_yaz(logs, terminal, f"[{pdf_name}] Metin çıkarılıyor...", color="#8ab4f8")
                    full_text = pdf_to_full_text(pdf_file)
                    blocks = split_beyannameler(full_text)
                    all_blocks.append((pdf_name, blocks))
                    log_yaz(logs, terminal, f"[{pdf_name}] Bulunan beyanname bloğu: {len(blocks)}", color="#8ab4f8")
                except Exception as e:
                    all_blocks.append((pdf_name, []))
                    log_yaz(logs, terminal, f"[{pdf_name}] HATA: {e}", color="#ff6b6b")

            total_blocks = sum(len(b) for _, b in all_blocks)
            done = 0

            if total_blocks == 0:
                st.error("Beyanname bloğu bulunamadı. PDF metni okunamıyor veya ayraç farklı olabilir.")
                st.stop()

            log_yaz(logs, terminal, f"Toplam işlenecek blok: {total_blocks}", color="#ffc107")

            for pdf_name, blocks in all_blocks:
                for idx, block in enumerate(blocks, start=1):
                    done += 1
                    pct = int((done / max(total_blocks, 1)) * 100)
                    progress.progress(min(pct, 100))
                    pro_text.info(f"İlerleme: {done}/{total_blocks} (%{pct}) | {pdf_name} - Blok {idx}/{len(blocks)}")

                    ay, yil = donem_bul(block)
                    donem_str = "Bilinmiyor"
                    if ay and yil:
                        donem_str = f"{ay} / {yil}"
                    elif yil and not ay:
                        donem_str = f"{yil}"
                    elif ay and not yil:
                        donem_str = f"{ay}"

                    vkn = vkn_bul(block)
                    isim = isim_eslestir_excel(vkn)

                    matrah = first_amount_after_label(block, MATRAH_AYLIK_IFADESI, lookahead_chars=620)
                    kdv = first_amount_after_label(block, KDV_TOPLAM_IFADESI, lookahead_chars=680)
                    if kdv == 0.0:
                        kdv = first_amount_after_label(block, KDV_HESAPLANAN_IFADESI, lookahead_chars=780)
                    pos = pos_bul_istenen_satirdan(block)

                    beyan_toplami = matrah + kdv
                    fark = pos - beyan_toplami

                    if pos > 0 and beyan_toplami == 0:
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
                        f"[{pdf_name} | {idx}] Dönem={donem_str} | {isim[:28]} | POS={para_formatla(pos)} | BEYAN={para_formatla(beyan_toplami)} | FARK={para_formatla(fark)} | {durum}",
                        color=renk
                    )

                    sonuclar.append({
                        "Dönem": donem_str,
                        "Mükellef": isim,
                        "VKN": vkn or "Bulunamadı",
                        "Matrah(Aylık)": matrah,
                        "KDV": kdv,
                        "POS": pos,
                        "Beyan": beyan_toplami,
                        "Fark": fark,
                        "Durum": durum
                    })

                    time.sleep(0.01)

            progress.progress(100)
            pro_text.success(f"Analiz tamamlandı. Toplam {total_blocks} beyanname bloğu işlendi.")
            log_yaz(logs, terminal, "Analiz tamamlandı.", color="#28a745")

            df_sonuc = pd.DataFrame(sonuclar) if sonuclar else pd.DataFrame()
            st.session_state["sonuclar"] = df_sonuc

            # Arşive ekle
            if not df_sonuc.empty:
                df_arsivlik = df_sonuc[df_sonuc["Durum"].isin(["RISKLI", "OKUNAMADI"])].copy()
                if not df_arsivlik.empty:
                    df_arsivlik["KayitZamani"] = now_str()
                    arsive_ekle(df_arsivlik)
                    st.toast("📌 Riskli/Okunamayan kayıtlar arşive işlendi.")

            # İş aç/güncelle
            df_is = is_takip_yukle()
            if not df_sonuc.empty:
                df_problem = df_sonuc[df_sonuc["Durum"].isin(["RISKLI", "OKUNAMADI"])].copy()
                if not df_problem.empty:
                    for _, rr in df_problem.iterrows():
                        df_is = is_olustur_veya_guncelle(df_is, rr.to_dict())
                    is_takip_kaydet(df_is)
                    st.toast("🗂️ İş Takip: Problemli kayıtlar için işler oluşturuldu/güncellendi.")

        # Analiz sonucu göster
        if st.session_state.get("sonuclar") is not None:
            df_sonuc = st.session_state["sonuclar"]
            if df_sonuc is not None and not df_sonuc.empty:
                riskliler = df_sonuc[df_sonuc["Durum"] == "RISKLI"]
                temizler = df_sonuc[df_sonuc["Durum"] == "TEMIZ"]
                okunamayanlar = df_sonuc[df_sonuc["Durum"] == "OKUNAMADI"]

                st.subheader("Analiz Sonuçları")
                t1, t2, t3 = st.tabs([
                    f"🚨 RİSKLİ ({len(riskliler)})",
                    f"✅ UYUMLU ({len(temizler)})",
                    f"❓ OKUNAMAYAN ({len(okunamayanlar)})",
                ])

                with t1:
                    if not riskliler.empty:
                        for i, row in riskliler.iterrows():
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
                                if st.button("🚨 İHBAR ET", key=f"ihbar_{i}", type="primary", use_container_width=True):
                                    mesaj = risk_mesaji_olustur(row.to_dict())
                                    if whatsapp_gonder("SABIT", mesaj):
                                        st.toast("✅ İhbar gönderildi.")
                    else:
                        st.success("Riskli kayıt yok.")
                with t2:
                    st.dataframe(temizler, use_container_width=True)
                with t3:
                    st.dataframe(okunamayanlar, use_container_width=True)

    # ------------------ TAB B: İŞ TAKİP + MANUEL İŞ ------------------
    with tabB:
        st.info("Bu bölümde hem otomatik (analizden gelen) hem de manuel iş emirlerini yönetebilir, personele/mükellefe/serbest numaraya mesaj gönderebilirsiniz.")
        df_is = is_takip_yukle()
        df_personel = personel_yukle()

        sub1, sub2 = st.tabs(["➕ Manuel İş Emri Oluştur", "📌 İş Listesi / Atama / Mesaj"])

        # ---- Manuel İş Emri ----
        with sub1:
            col1, col2 = st.columns([2, 2])
            with col1:
                manuel_donem = st.text_input("Dönem (opsiyonel) - örn: Ocak / 2024", value="")
                manuel_konu = st.text_input("İş Konusu", value="")
                manuel_oncelik = st.selectbox("Öncelik", ["Yüksek", "Orta", "Düşük"], index=1)
            with col2:
                # Mükellef seçimi opsiyonel
                muk_df = st.session_state.get("mukellef_db")
                muk_options = ["(Seçmeyeceğim)"]
                if muk_df is not None and not muk_df.empty:
                    muk_options += muk_df["A_UNVAN"].astype(str).tolist()

                manuel_muk = st.selectbox("Mükellef (opsiyonel)", muk_options)
                manuel_vkn = st.text_input("VKN/TCKN (opsiyonel) - mükellef seçtiyseniz boş bırakabilirsiniz", value="")
                manuel_aciklama = st.text_area("Açıklama / Talimat", height=110)

            st.markdown("---")
            st.subheader("Mesaj / Alıcı Seçimi")
            alici_tipi = st.radio("Mesaj Kime Gidecek?", ["Personel", "Mükellef", "Serbest Numara"], horizontal=True)

            sorumlu_ad = ""
            sorumlu_tel = ""
            hedef_tel = ""

            if alici_tipi == "Personel":
                aktif_personel = df_personel[df_personel["Aktif"].astype(str).str.lower().isin(["evet", "yes", "true", "1"])]
                personel_options = ["(Seçiniz)"] + aktif_personel["Personel"].astype(str).tolist()
                sorumlu_ad = st.selectbox("Sorumlu Personel", personel_options)
                if sorumlu_ad != "(Seçiniz)":
                    hit = aktif_personel[aktif_personel["Personel"].astype(str) == sorumlu_ad]
                    if not hit.empty:
                        sorumlu_tel = normalize_phone(hit.iloc[0].get("Telefon", ""))
                hedef_tel = sorumlu_tel

            elif alici_tipi == "Mükellef":
                # mükellef seçildiyse tel otomatik
                sec_unvan = "" if manuel_muk == "(Seçmeyeceğim)" else manuel_muk
                sec_vkn = manuel_vkn.strip()
                tel = mukellef_tel_bul(vkn=sec_vkn, unvan=sec_unvan)
                hedef_tel = tel
                st.caption(f"Mükellef telefonu (bulunan): {hedef_tel or 'Bulunamadı (Excel D sütunu)'}")

            else:
                hedef_tel = st.text_input("Serbest Numara (örn 905xxxxxxxxx)", value="")

            gonder = st.checkbox("WhatsApp ile bilgilendirme gönder", value=True)

            if st.button("✅ Manuel İş Emrini Kaydet", type="primary", use_container_width=True):
                # mükellef bilgisi normalize
                mukellef_unvan = "" if manuel_muk == "(Seçmeyeceğim)" else manuel_muk
                vkn_final = manuel_vkn.strip()
                if not vkn_final and mukellef_unvan:
                    # unvandan VKN çekebilirsek çekelim
                    dfm = st.session_state.get("mukellef_db")
                    if dfm is not None and not dfm.empty:
                        hit = dfm[dfm["A_UNVAN"].astype(str).str.lower() == mukellef_unvan.lower()]
                        if not hit.empty:
                            vkn_final = str(hit.iloc[0].get("C_VKN", "")).strip() or str(hit.iloc[0].get("B_TC", "")).strip()

                # Personelse sorumlu alanına yazalım
                sorumlu_save = sorumlu_ad if alici_tipi == "Personel" and sorumlu_ad != "(Seçiniz)" else ""
                sorumlu_tel_save = hedef_tel if alici_tipi == "Personel" else ""

                if not manuel_konu.strip():
                    st.error("İş konusu boş olamaz.")
                else:
                    df_is2 = manuel_is_ekle(
                        df_is=df_is,
                        donem=manuel_donem.strip(),
                        mukellef=mukellef_unvan.strip(),
                        vkn=vkn_final,
                        konu=manuel_konu.strip(),
                        aciklama=manuel_aciklama.strip(),
                        oncelik=manuel_oncelik,
                        sorumlu=sorumlu_save,
                        sorumlu_tel=sorumlu_tel_save
                    )
                    is_takip_kaydet(df_is2)
                    st.success("Manuel iş emri kaydedildi.")
                    st.toast("🗂️ İş Takip güncellendi.")

                    # Mesaj gönder
                    if gonder:
                        # En son eklenen iş
                        yeni_is = df_is2.iloc[-1].to_dict()
                        if alici_tipi == "Personel":
                            if hedef_tel:
                                msg = atama_mesaji_olustur(yeni_is)
                                if whatsapp_gonder(hedef_tel, msg):
                                    st.toast("📨 Personel bilgilendirildi.")
                            else:
                                st.warning("Personel telefonu bulunamadı. (Personel listesi kontrol ediniz)")
                        elif alici_tipi == "Mükellef":
                            if hedef_tel:
                                msg = mukellef_bilgi_mesaji_olustur(yeni_is)
                                if whatsapp_gonder(hedef_tel, msg):
                                    st.toast("📨 Mükellefe mesaj gönderildi.")
                            else:
                                st.warning("Mükellef telefonu bulunamadı (Excel D sütunu).")
                        else:
                            if normalize_phone(hedef_tel):
                                msg = mukellef_bilgi_mesaji_olustur(yeni_is)
                                if whatsapp_gonder(hedef_tel, msg):
                                    st.toast("📨 Mesaj gönderildi.")
                            else:
                                st.warning("Serbest numara geçersiz.")

        # ---- İş listesi / atama / mesaj ----
        with sub2:
            # filtreler
            c1, c2, c3 = st.columns([2, 2, 2])
            with c1:
                donem_list = ["(Tümü)"] + sorted([d for d in df_is["Dönem"].astype(str).unique() if d.strip()])
                f_donem = st.selectbox("Dönem Filtresi", donem_list)
            with c2:
                durum_list = ["(Tümü)", "AÇIK", "İNCELEMEDE", "KAPANDI", "İPTAL"]
                f_durum = st.selectbox("Durum Filtresi", durum_list)
            with c3:
                tip_list = ["(Tümü)", "RISKLI", "OKUNAMADI", "MANUEL"]
                f_tip = st.selectbox("Tip Filtresi", tip_list)

            view = df_is.copy()
            if f_donem != "(Tümü)":
                view = view[view["Dönem"].astype(str) == f_donem]
            if f_durum != "(Tümü)":
                view = view[view["Durum"].astype(str) == f_durum]
            if f_tip != "(Tümü)":
                view = view[view["Tip"].astype(str) == f_tip]

            st.subheader("İş Listesi")
            st.dataframe(view, use_container_width=True)

            st.divider()
            st.subheader("Seçili İş Üzerinde İşlem")
            is_ids = view["IsID"].astype(str).tolist()
            if not is_ids:
                st.warning("Seçilebilecek iş yok.")
            else:
                sec_isid = st.selectbox("İş Seçin (IsID)", is_ids)
                sec_is = df_is[df_is["IsID"].astype(str) == str(sec_isid)]
                if sec_is.empty:
                    st.error("İş bulunamadı.")
                else:
                    sec_is_row = sec_is.iloc[0].to_dict()

                    aktif_personel = df_personel[df_personel["Aktif"].astype(str).str.lower().isin(["evet", "yes", "true", "1"])]
                    personel_options = ["(Atama Yok)"] + aktif_personel["Personel"].astype(str).tolist()

                    colA, colB = st.columns([2, 2])
                    with colA:
                        sec_personel = st.selectbox("Sorumlu Personel", personel_options, index=0)
                        yeni_durum = st.selectbox("Durum", ["AÇIK", "İNCELEMEDE", "KAPANDI", "İPTAL"])
                        yeni_not = st.text_area("Not / Yapılan İşlem", value=str(sec_is_row.get("Not", "")), height=110)

                    with colB:
                        st.markdown("**İş Özeti**")
                        st.write(f"**İş:** {sec_is_row.get('IsID','')}")
                        st.write(f"**Tip:** {sec_is_row.get('Tip','')} | **Öncelik:** {sec_is_row.get('Öncelik','')}")
                        st.write(f"**Dönem:** {sec_is_row.get('Dönem','')}")
                        st.write(f"**Firma:** {sec_is_row.get('Mükellef','')}")
                        st.write(f"**VKN:** {sec_is_row.get('VKN','')}")
                        st.caption("Kaydedince isterseniz personele veya mükellefe mesaj gönderebilirsiniz.")

                        gonder_kime = st.selectbox("Mesaj Gönder (opsiyonel)", ["Gönderme", "Personele", "Mükellefe", "Serbest Numara"])
                        serbest_tel = ""
                        if gonder_kime == "Serbest Numara":
                            serbest_tel = st.text_input("Serbest Numara", value="")

                    if st.button("💾 Güncelle (Atama/Durum/Not)", type="primary", use_container_width=True):
                        # personel tel
                        sorumlu_tel = ""
                        sorumlu_ad = ""
                        if sec_personel != "(Atama Yok)":
                            res = aktif_personel[aktif_personel["Personel"].astype(str) == sec_personel]
                            if not res.empty:
                                sorumlu_ad = sec_personel
                                sorumlu_tel = normalize_phone(res.iloc[0].get("Telefon", ""))

                        idx = df_is[df_is["IsID"].astype(str) == str(sec_isid)].index[0]
                        df_is.loc[idx, "Sorumlu"] = sorumlu_ad
                        df_is.loc[idx, "SorumluTel"] = sorumlu_tel
                        df_is.loc[idx, "Durum"] = yeni_durum
                        df_is.loc[idx, "Not"] = yeni_not
                        df_is.loc[idx, "GuncellemeZamani"] = now_str()
                        if yeni_durum == "KAPANDI" and not str(df_is.loc[idx, "KapanisZamani"]).strip():
                            df_is.loc[idx, "KapanisZamani"] = now_str()

                        is_takip_kaydet(df_is)
                        st.success("Güncellendi.")

                        # mesaj
                        if gonder_kime != "Gönderme":
                            guncel_is = df_is.loc[idx].to_dict()

                            if gonder_kime == "Personele":
                                if sorumlu_tel:
                                    msg = atama_mesaji_olustur(guncel_is)
                                    if whatsapp_gonder(sorumlu_tel, msg):
                                        st.toast("📨 Personel bilgilendirildi.")
                                else:
                                    st.warning("Personel seçilmedi veya telefon bulunamadı.")

                            elif gonder_kime == "Mükellefe":
                                tel = mukellef_tel_bul(vkn=guncel_is.get("VKN",""), unvan=guncel_is.get("Mükellef",""))
                                if tel:
                                    msg = mukellef_bilgi_mesaji_olustur(guncel_is)
                                    if whatsapp_gonder(tel, msg):
                                        st.toast("📨 Mükellefe mesaj gönderildi.")
                                else:
                                    st.warning("Mükellef telefonu bulunamadı (Excel D sütunu).")

                            else:
                                tel = normalize_phone(serbest_tel)
                                if tel:
                                    msg = mukellef_bilgi_mesaji_olustur(guncel_is)
                                    if whatsapp_gonder(tel, msg):
                                        st.toast("📨 Mesaj gönderildi.")
                                else:
                                    st.warning("Serbest numara geçersiz.")

# ==========================================
# 8) 3. MENÜ: PROFESYONEL MESAJ
# ==========================================
elif secim == "3. Profesyonel Mesaj":
    st.title("📤 Profesyonel Mesaj Gönderimi")
    if st.session_state.get("mukellef_db") is not None:
        df = st.session_state.get("mukellef_db")
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
# 9) 4. MENÜ: TASDİK ROBOTU (MÜKELLEF + PERSONEL)
# ==========================================
elif secim == "4. Tasdik Robotu":
    st.title("🤖 Kayıtlar (Tasdik)")

    tab1, tab2, tab3 = st.tabs(["📋 Mükellef Listesi", "👥 Personel / Numara Yönetimi", "📊 Arşiv & İş Takip Durumu"])

    with tab1:
        if st.session_state.get("mukellef_db") is not None:
            st.info(f"Sistemde kayıtlı {len(st.session_state['mukellef_db'])} mükellef bulunmaktadır.")
            st.dataframe(st.session_state["mukellef_db"], use_container_width=True)
        else:
            st.warning("Mükellef listesi yok. '1. Excel Listesi Yükle' menüsünden yükleyin.")

    with tab2:
        st.subheader("Personel Ekle (Numara Ekleme)")
        df_personel = personel_yukle()

        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            p_ad = st.text_input("Personel Adı Soyadı")
        with col2:
            p_tel = st.text_input("Telefon (örn 905xxxxxxxxx veya 05xxxxxxxxx)")
        with col3:
            p_aktif = st.selectbox("Aktif", ["Evet", "Hayır"])

        if st.button("➕ Personel / Numara Ekle", type="primary", use_container_width=True):
            if not str(p_ad).strip():
                st.error("Personel adı boş olamaz.")
            elif not normalize_phone(p_tel):
                st.error("Telefon numarası geçersiz.")
            else:
                tel_norm = normalize_phone(p_tel)
                mask = df_personel["Personel"].astype(str).str.strip().str.lower() == str(p_ad).strip().lower()
                if mask.any():
                    idx = df_personel[mask].index[0]
                    df_personel.loc[idx, "Telefon"] = tel_norm
                    df_personel.loc[idx, "Aktif"] = p_aktif
                else:
                    df_personel = pd.concat([df_personel, pd.DataFrame([{
                        "Personel": str(p_ad).strip(),
                        "Telefon": tel_norm,
                        "Aktif": p_aktif
                    }])], ignore_index=True)

                personel_kaydet(df_personel)
                st.success("Personel kaydedildi.")

        st.divider()
        st.subheader("Personel Listesi")
        st.dataframe(df_personel, use_container_width=True)

        st.subheader("Personel Sil / Pasifleştir")
        if not df_personel.empty:
            sec = st.selectbox("Personel Seç", df_personel["Personel"].astype(str).tolist())
            colx, coly = st.columns([1, 1])
            with colx:
                if st.button("🚫 Pasifleştir", use_container_width=True):
                    idx = df_personel[df_personel["Personel"].astype(str) == sec].index[0]
                    df_personel.loc[idx, "Aktif"] = "Hayır"
                    personel_kaydet(df_personel)
                    st.success("Pasifleştirildi.")
            with coly:
                if st.button("🗑️ Sil", use_container_width=True):
                    df_personel = df_personel[df_personel["Personel"].astype(str) != sec].copy()
                    personel_kaydet(df_personel)
                    st.success("Silindi.")
        else:
            st.warning("Henüz personel yok.")

    with tab3:
        st.subheader("Dosya Durumları")
        st.write(f"📁 Arşiv: **{ARSIV_DOSYASI}** {'✅' if os.path.exists(ARSIV_DOSYASI) else '❌'}")
        st.write(f"📁 İş Takip: **{IS_TAKIP_DOSYASI}** {'✅' if os.path.exists(IS_TAKIP_DOSYASI) else '❌'}")
        st.write(f"📁 Personel: **{PERSONEL_DOSYASI}** {'✅' if os.path.exists(PERSONEL_DOSYASI) else '❌'}")

        ars = arsiv_oku()
        if not ars.empty:
            st.caption("Arşivden son 20 kayıt")
            st.dataframe(ars.tail(20), use_container_width=True)
        else:
            st.info("Arşivde kayıt yok veya okunamadı.")

        df_is = is_takip_yukle()
        if not df_is.empty:
            st.caption("İş takipten son 20 kayıt")
            st.dataframe(df_is.tail(20), use_container_width=True)
        else:
            st.info("İş takipte kayıt yok veya okunamadı.")
