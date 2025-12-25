import os
import re
import time
import requests
import pandas as pd
import pdfplumber
import streamlit as st

# ==========================================
# 1) AYARLAR & SABİTLER (GENEL YAPI KORUNUR)
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

# Kalıcı mükellef dosyası (1 kez yükle, hep kalsın)
KALICI_EXCEL_YOLU = "mukellef_db_kalici.xlsx"

# Tek PDF içinde çoklu beyanname ayıracı
BEYANNAME_AYRACI = "KATMA DEĞER VERGİSİ BEYANNAMESİ"

# Aranacak ifadeler (beyan)
MATRAH_AYLIK_IFADESI = "Teslim ve Hizmetlerin Karşılığını Teşkil Eden Bedel (aylık)"
KDV_TOPLAM_IFADESI = "Toplam Katma Değer Vergisi"
KDV_HESAPLANAN_IFADESI = "Hesaplanan Katma Değer Vergisi"

# POS satırı (SİZİN İSTEDİĞİNİZ)
POS_SATIRI_TAM = "Kredi Kartı İle Tahsil Edilen Teslim ve Hizmetlerin KDV Dahil Karşılığını Teşkil Eden Bedel"

# SADECE PARA FORMATINI yakala (VKN/TCKN gibi düz rakamları yakalama)
AMOUNT_REGEX = r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"

# Risk eşiği (TL)
RISK_ESIK = 50.0

# Uçuk değerleri elemek için üst limit
MAX_TUTAR_SANITY = 200_000_000  # 200 milyon TL

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
    """TR format sayıları güvenle çevirir: 1.234.567,89 / 123456,78"""
    try:
        if text is None:
            return 0.0
        t = str(text).strip().replace("\u00a0", " ")
        t = re.sub(r"[^0-9\.,]", "", t)
        if not t:
            return 0.0

        # TR: 1.234.567,89
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
    """Delimiter pozisyonlarına göre keserek bloklar üretir (deterministik)."""
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
    """label sonrası pencerede SADECE para formatlı ilk tutarı yakalar."""
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
    """
    POS geliri: 'Kredi Kartı İle Tahsil Edilen ... KDV Dahil ... Bedel' satırından okunur.
    Satır bölünmelerine dayanıklı.
    """
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

                # yedek: bu bölgedeki satırlarda ilk para tutarı
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
    """
    PDF'teki gerçek yapıya göre dönem yakalama:
    Genelde şu akış var:
      DÖNEM TİPİ  Aylık  Yıl  Ay  2024  ... (VERGİ DAİRESİ/MALMÜDÜRLÜĞÜ)  Ocak
    Bu yüzden 'Yıl Ay 2024 .... Ocak' desenini tek satıra indirip yakalıyoruz.
    """
    t = str(block_text or "")
    if not t.strip():
        return (None, None)

    # whitespace normalize
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

    # 1) En güçlü desen: "Yıl Ay 2024 ... Ocak"
    m = re.search(rf"Yıl\s*Ay\s*(20\d{{2}}).{{0,120}}?\b{ay_regex}\b", t1, flags=re.IGNORECASE)
    if m:
        yil = m.group(1)
        ay_raw = (m.group(2) or "").lower()
        ay = ay_map.get(ay_raw)
        return (ay, yil)

    # 2) Alternatif desen: "Yıl 2024 ... Ay ... Ocak"
    m2 = re.search(rf"Yıl\s*(20\d{{2}}).{{0,120}}?Ay.{{0,120}}?\b{ay_regex}\b", t1, flags=re.IGNORECASE)
    if m2:
        yil = m2.group(1)
        ay_raw = (m2.group(2) or "").lower()
        ay = ay_map.get(ay_raw)
        return (ay, yil)

    # 3) Yedek: Yıl ayrı, ay adı ayrı
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
    """WhatsApp için göze çarpan risk mesajı üretir (Ay/Yıl dahil)."""
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


def kalici_db_yukle():
    """Uygulama açılışında kalıcı excel varsa otomatik yükler."""
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


# Açılışta otomatik yükle (varsa)
if st.session_state.get("mukellef_db") is None:
    kalici_db_yukle()

# ==========================================
# 5) ANA MENÜ (AYNEN KORUNUR)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.header("MÜŞAVİR PANELİ")
    secim = st.radio("MENÜ", ["1. Excel Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"])

# ==========================================
# 6) 1. MENÜ: EXCEL YÜKLE (KALICI KAYIT DAHİL)
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
# 7) 2. MENÜ: KDV ANALİZ ROBOTU (DETAYLI PROAKTİF AKIŞ)
# ==========================================
elif secim == "2. KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz Üssü (Canlı Akış & Proaktif Detay)")

    if st.session_state.get("mukellef_db") is None:
        st.warning("⚠️ Mükellef listesi bulunamadı. '1. Excel Listesi Yükle' menüsünden bir kez yükleyin.")
        st.stop()

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

                # Dönem
                ay, yil = donem_bul(block)
                donem_str = "Bilinmiyor"
                if ay and yil:
                    donem_str = f"{ay} / {yil}"
                elif yil and not ay:
                    donem_str = f"{yil}"
                elif ay and not yil:
                    donem_str = f"{ay}"

                log_yaz(logs, terminal, f"[{pdf_name} | {idx}] Dönem: {donem_str}", color="#8ab4f8")

                # VKN
                log_yaz(logs, terminal, f"[{pdf_name} | {idx}] VKN/TCKN aranıyor...", color="#d7d7d7")
                vkn = vkn_bul(block)
                log_yaz(logs, terminal, f"[{pdf_name} | {idx}] VKN/TCKN: {vkn or 'Bulunamadı'}", color="#d7d7d7")

                # Mükellef
                isim = isim_eslestir_excel(vkn)
                log_yaz(logs, terminal, f"[{pdf_name} | {idx}] Mükellef: {isim}", color="#d7d7d7")

                # Matrah(Aylık)
                log_yaz(logs, terminal, f"[{pdf_name} | {idx}] Matrah(Aylık) aranıyor...", color="#d7d7d7")
                matrah = first_amount_after_label(block, MATRAH_AYLIK_IFADESI, lookahead_chars=620)
                log_yaz(logs, terminal, f"[{pdf_name} | {idx}] Matrah(Aylık): {para_formatla(matrah)}", color="#d7d7d7")

                # KDV
                log_yaz(logs, terminal, f"[{pdf_name} | {idx}] KDV aranıyor (Toplam KDV)...", color="#d7d7d7")
                kdv = first_amount_after_label(block, KDV_TOPLAM_IFADESI, lookahead_chars=680)
                if kdv == 0.0:
                    log_yaz(logs, terminal, f"[{pdf_name} | {idx}] Toplam KDV yok. Hesaplanan KDV deneniyor...", color="#ffc107")
                    kdv = first_amount_after_label(block, KDV_HESAPLANAN_IFADESI, lookahead_chars=780)
                log_yaz(logs, terminal, f"[{pdf_name} | {idx}] KDV: {para_formatla(kdv)}", color="#d7d7d7")

                # POS
                log_yaz(logs, terminal, f"[{pdf_name} | {idx}] POS aranıyor (Kredi Kartı...KDV Dahil...Bedel)...", color="#d7d7d7")
                pos = pos_bul_istenen_satirdan(block)
                log_yaz(logs, terminal, f"[{pdf_name} | {idx}] POS: {para_formatla(pos)}", color="#d7d7d7")

                # Hesap
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
                    f"[{pdf_name} | {idx}] BEYAN={para_formatla(beyan_toplami)} | FARK={para_formatla(fark)} | DURUM={durum}",
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

        st.session_state["sonuclar"] = pd.DataFrame(sonuclar) if sonuclar else pd.DataFrame()

    # Sonuç ekranı
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
                                <div class='card-sub'>Dönem: {row['Dönem']} | VKN/TCKN: {row['VKN']}</div>
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
                                mesaj = risk_mesaji_olustur(row.to_dict())
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
# 9) 4. MENÜ: TASDİK ROBOTU
# ==========================================
elif secim == "4. Tasdik Robotu":
    st.title("🤖 Yüklenen Mükellef Listesi (Tasdik)")

    if st.session_state.get("mukellef_db") is not None:
        st.info(f"Sistemde kayıtlı {len(st.session_state['mukellef_db'])} mükellef bulunmaktadır.")
        st.dataframe(st.session_state["mukellef_db"], use_container_width=True)
        if os.path.exists(KALICI_EXCEL_YOLU):
            st.caption("Not: Liste kalıcı kayıt dosyasından otomatik yüklenmektedir.")
    else:
        st.warning("Görüntülenecek bir liste yok. '1. Excel Listesi Yükle' menüsünden bir kez yükleyin.")
