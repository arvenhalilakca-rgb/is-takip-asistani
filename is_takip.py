import os, re, time, requests
import pandas as pd
import pdfplumber
import streamlit as st
from datetime import datetime

# -------------------- Ayarlar --------------------
st.set_page_config(page_title="Müşavir Kulesi", page_icon="🗼", layout="wide", initial_sidebar_state="expanded")

ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

KALICI_EXCEL_YOLU = "mukellef_db_kalici.xlsx"
PERSONEL_DOSYASI = "personel_db.xlsx"
IS_TAKIP_DOSYASI = "is_takip.xlsx"

BEYANNAME_AYRACI = "KATMA DEĞER VERGİSİ BEYANNAMESİ"
MATRAH_AYLIK_IFADESI = "Teslim ve Hizmetlerin Karşılığını Teşkil Eden Bedel (aylık)"
KDV_TOPLAM_IFADESI = "Toplam Katma Değer Vergisi"
KDV_HESAPLANAN_IFADESI = "Hesaplanan Katma Değer Vergisi"
AMOUNT_REGEX = r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"
POS_SATIRI_TAM = "Kredi Kartı İle Tahsil Edilen Teslim ve Hizmetlerin KDV Dahil Karşılığını Teşkil Eden Bedel"

RISK_ESIK = 50.0
MAX_TUTAR_SANITY = 200_000_000

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

# -------------------- Session --------------------
for k in ["sonuclar", "mukellef_db", "personel_db", "is_takip_db"]:
    if k not in st.session_state:
        st.session_state[k] = None

# -------------------- Yardımcılar --------------------
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if len(p) == 10:          # 5xxxxxxxxx
        p = "90" + p
    if len(p) == 11 and p.startswith("0"):  # 05xxxxxxxxx
        p = "9" + p
    return p

def parse_phones(cell_text: str):
    """
    Excel 'Telefon' hücresinde birden fazla numara var.
    Bu fonksiyon hücre içinden tüm GSM numaralarını yakalar, normalize eder, tekrarı atar.
    Kabul: 05xxxxxxxxx, 5xxxxxxxxx, 90xxxxxxxxxx gibi biçimler.
    """
    t = str(cell_text or "")
    if not t.strip():
        return []
    # önce olası GSM formatlarını yakala
    candidates = re.findall(r"(?:\+?90\s*)?(?:0\s*)?5\d{2}\s*\d{3}\s*\d{2}\s*\d{2}", t)
    out = []
    for c in candidates:
        n = normalize_phone(c)
        if n and n not in out:
            out.append(n)

    # bazı hücrelerde farklı boşluk/ayraç varsa: fallback (rakam dizileri)
    if not out:
        digits = re.findall(r"\d+", t)
        joined = " ".join(digits)
        candidates2 = re.findall(r"(?:90)?5\d{9}", joined.replace(" ", ""))
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

def whatsapp_gonder_coklu(numaralar, mesaj: str):
    ok = 0
    for n in (numaralar or []):
        if whatsapp_gonder(n, mesaj):
            ok += 1
        time.sleep(0.3)
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

def isim_eslestir_excel(numara):
    df = st.session_state.get("mukellef_db")
    if df is None or df.empty:
        return f"Bilinmeyen ({numara or 'Bulunamadı'})"
    if not numara:
        return "VKN/TCKN PDF'te Bulunamadı"
    num = str(numara).strip()

    hit = df[df["C_VKN"].astype(str) == num]
    if hit.empty:
        hit = df[df["B_TC"].astype(str) == num]
    if not hit.empty:
        return hit.iloc[0]["A_UNVAN"]
    return f"Listede Yok ({num})"

def mukellef_kayit_getir(vkn_or_tc: str):
    df = st.session_state.get("mukellef_db")
    if df is None or df.empty:
        return None
    key = str(vkn_or_tc or "").strip()
    if not key:
        return None
    hit = df[df["C_VKN"].astype(str) == key]
    if hit.empty:
        hit = df[df["B_TC"].astype(str) == key]
    if hit.empty:
        return None
    return hit.iloc[0].to_dict()

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

def risk_mesaji_olustur(row: dict) -> str:
    donem = row.get("Dönem") or "Bilinmiyor"
    return (
        "🚨🚨 *KDV RİSK ALARMI* 🚨🚨\n"
        f"📅 *Dönem:* {donem}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🏢 *Firma:* {row.get('Mükellef','')}\n"
        f"🆔 *VKN/TCKN:* {row.get('VKN','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"💳 *POS (KDV Dahil):* {para_formatla(row.get('POS',0))}\n"
        f"🧾 *Beyan (Matrah(Aylık)+KDV):* {para_formatla(row.get('Beyan',0))}\n"
        f"📌 *FARK:* {para_formatla(row.get('Fark',0))}\n"
        "━━━━━━━━━━━━━━━━\n"
        "⚠️ *İnceleme Önerisi:* POS tahsilatı beyan toplamını aşıyor."
    )

def log_yaz(logs, terminal, msg, color="#f0f0f0"):
    logs.append(f"<span style='color:{color};'>{msg}</span>")
    terminal.markdown(f"<div class='terminal-window'>{'<br>'.join(logs[-280:])}</div>", unsafe_allow_html=True)

# -------------------- Kalıcı yükle --------------------
def kalici_mukellef_yukle():
    if not os.path.exists(KALICI_EXCEL_YOLU):
        return False
    try:
        raw = pd.read_excel(KALICI_EXCEL_YOLU, dtype=str, header=None)
        df = pd.DataFrame()
        df["A_UNVAN"] = raw.iloc[:, 0].astype(str).str.strip()
        df["B_TC"]    = raw.iloc[:, 1].astype(str).str.strip() if raw.shape[1] > 1 else ""
        df["C_VKN"]   = raw.iloc[:, 2].astype(str).str.strip() if raw.shape[1] > 2 else ""
        # burada D sütununa "birincil" kaydediyoruz
        df["D_TEL"]   = raw.iloc[:, 3].astype(str).str.strip() if raw.shape[1] > 3 else ""
        # birincilin yanı sıra çoklu numarayı da tekrar üretelim (D_TEL_ALL yoksa tek numara gibi kalır)
        df["D_TELLER"] = df["D_TEL"].apply(lambda x: parse_phones(x))
        df["D_TEL_ALL"] = df["D_TELLER"].apply(lambda lst: " | ".join(lst))
        st.session_state["mukellef_db"] = df.fillna("")
        return True
    except Exception:
        return False

# Açılışta otomatik yükle
if st.session_state["mukellef_db"] is None:
    kalici_mukellef_yukle()

# -------------------- Menü --------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.header("MÜŞAVİR PANELİ")
    secim = st.radio("MENÜ", ["1. Excel Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"])

# ======================================================
# 1) Excel Yükle (ÇOKLU TELEFON OKUR)
# ======================================================
if secim == "1. Excel Listesi Yükle":
    st.title("📂 Mükellef Veritabanı Yükle")
    st.info("Excel’inizde Telefon hücresinde birden fazla numara varsa sistem hepsini ayıklar ve saklar.")

    uploaded_file = st.file_uploader("Excel Dosyasını Seçin", type=["xlsx", "xls"])
    if uploaded_file:
        try:
            # Sizin dosyanızda ilk satır başlık: Unvan, TCKN, VKN, Telefon
            raw = pd.read_excel(uploaded_file, dtype=str)
            raw = raw.fillna("")

            # Kolon isimleri farklı gelirse esnek eşleştir
            cols = {c.strip().lower(): c for c in raw.columns}
            unvan_col = cols.get("unvan", raw.columns[0])
            tckn_col  = cols.get("tckn",  raw.columns[1] if len(raw.columns) > 1 else raw.columns[0])
            vkn_col   = cols.get("vkn",   raw.columns[2] if len(raw.columns) > 2 else raw.columns[0])
            tel_col   = cols.get("telefon", raw.columns[3] if len(raw.columns) > 3 else raw.columns[0])

            df = pd.DataFrame()
            df["A_UNVAN"] = raw[unvan_col].astype(str).str.strip()
            df["B_TC"]    = raw[tckn_col].astype(str).str.strip().replace("-", "")
            df["C_VKN"]   = raw[vkn_col].astype(str).str.strip().replace("-", "")
            # Çoklu telefon: liste + birincil + tümü
            df["D_TELLER"] = raw[tel_col].apply(parse_phones)
            df["D_TEL"]    = df["D_TELLER"].apply(lambda lst: lst[0] if isinstance(lst, list) and len(lst) > 0 else "")
            df["D_TEL_ALL"] = df["D_TELLER"].apply(lambda lst: " | ".join(lst) if isinstance(lst, list) else "")

            df = df.fillna("")
            st.session_state["mukellef_db"] = df

            # Kalıcı dosyaya minimum (Unvan, TCKN, VKN, TelefonBirincil) kaydediyoruz
            out = df[["A_UNVAN", "B_TC", "C_VKN", "D_TEL"]].copy()
            out.to_excel(KALICI_EXCEL_YOLU, index=False, header=False)

            st.success(f"✅ Başarılı! {len(df)} mükellef yüklendi. Çoklu telefonlar da analiz edildi.")
            st.dataframe(df[["A_UNVAN","B_TC","C_VKN","D_TEL_ALL"]].head(30), use_container_width=True)
            st.caption("Not: D_TEL_ALL sütununda mükellefin tüm numaraları listelenir.")
        except Exception as e:
            st.error(f"❌ Okuma hatası: {e}")

    if st.session_state.get("mukellef_db") is not None:
        st.divider()
        st.subheader("Kayıtlı Liste Özeti")
        st.write(f"Toplam kayıt: {len(st.session_state['mukellef_db'])}")
        st.dataframe(st.session_state["mukellef_db"][["A_UNVAN","B_TC","C_VKN","D_TEL_ALL"]].head(20), use_container_width=True)

# ======================================================
# 2) KDV Analiz Robotu (Kısa) + İHBAR: TÜM NUMARALARA GÖNDER opsiyonu
# ======================================================
elif secim == "2. KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz Üssü (Canlı Akış)")

    if st.session_state.get("mukellef_db") is None:
        st.warning("⚠️ Önce '1. Excel Listesi Yükle' menüsünden listenizi yükleyin.")
        st.stop()

    pdf_files = st.file_uploader("PDF yükleyin", type=["pdf"], accept_multiple_files=True)

    if pdf_files and st.button("🚀 ANALİZ ET", type="primary", use_container_width=True):
        terminal = st.empty()
        logs = []
        progress = st.progress(0)

        all_blocks = []
        for pdf_file in pdf_files:
            full_text = pdf_to_full_text(pdf_file)
            blocks = split_beyannameler(full_text)
            all_blocks += blocks

        if not all_blocks:
            st.error("Beyanname bloğu bulunamadı.")
            st.stop()

        results = []
        total = len(all_blocks)

        for i, block in enumerate(all_blocks, start=1):
            progress.progress(int(i/total*100))
            ay, yil = donem_bul(block)
            donem = f"{ay} / {yil}" if ay and yil else (yil or ay or "Bilinmiyor")

            vkn = vkn_bul(block)
            isim = isim_eslestir_excel(vkn)

            matrah = first_amount_after_label(block, MATRAH_AYLIK_IFADESI, 620)
            kdv = first_amount_after_label(block, KDV_TOPLAM_IFADESI, 680) or first_amount_after_label(block, KDV_HESAPLANAN_IFADESI, 780)
            pos = pos_bul_istenen_satirdan(block)

            beyan = matrah + kdv
            fark = pos - beyan
            if pos > 0 and beyan == 0:
                durum = "OKUNAMADI"
                color = "#ffc107"
            elif fark > RISK_ESIK:
                durum = "RISKLI"
                color = "#ff6b6b"
            else:
                durum = "TEMIZ"
                color = "#28a745"

            log_yaz(logs, terminal, f"[{i}/{total}] {donem} | {isim[:30]} | POS={para_formatla(pos)} | BEYAN={para_formatla(beyan)} | FARK={para_formatla(fark)} | {durum}", color=color)

            results.append({
                "Dönem": donem, "Mükellef": isim, "VKN": vkn or "Bulunamadı",
                "POS": pos, "Beyan": beyan, "Fark": fark, "Durum": durum
            })

        st.session_state["sonuclar"] = pd.DataFrame(results)
        st.success("Analiz tamamlandı.")

    if st.session_state.get("sonuclar") is not None and not st.session_state["sonuclar"].empty:
        df = st.session_state["sonuclar"]
        risk = df[df["Durum"] == "RISKLI"]
        st.subheader(f"🚨 Riskli Kayıtlar ({len(risk)})")

        tum_numaralara = st.checkbox("İhbar/Mesaj gönderirken mükellefin TÜM numaralarına gönder", value=True)

        if risk.empty:
            st.success("Riskli kayıt yok.")
        else:
            for idx, row in risk.iterrows():
                col1, col2 = st.columns([4,1])
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

                        # Sabit ihbar numarasına zaten gidiyor:
                        if whatsapp_gonder("SABIT", msg):
                            st.toast("✅ Sabit ihbar numarasına gönderildi.")

                        # ayrıca mükellefin numaralarına da göndermek isterseniz:
                        kayit = mukellef_kayit_getir(row["VKN"])
                        if kayit:
                            nums = kayit.get("D_TELLER", [])
                            if not isinstance(nums, list):
                                nums = parse_phones(kayit.get("D_TEL_ALL", "") or kayit.get("D_TEL", ""))

                            if tum_numaralara:
                                sent = whatsapp_gonder_coklu(nums, msg)
                                st.toast(f"📨 Mükellefe {sent} numaraya gönderildi.")
                            else:
                                if nums:
                                    if whatsapp_gonder(nums[0], msg):
                                        st.toast("📨 Mükellefe birincil numaraya gönderildi.")
                        else:
                            st.warning("Mükellef kaydı/telefonu bulunamadı.")

# ======================================================
# 3) Profesyonel Mesaj (Mükellefin tüm numaralarına gönder)
# ======================================================
elif secim == "3. Profesyonel Mesaj":
    st.title("📤 Profesyonel Mesaj Gönderimi")

    df = st.session_state.get("mukellef_db")
    if df is None or df.empty:
        st.warning("Önce mükellef listesini yükleyin.")
        st.stop()

    kisi = st.selectbox("Mükellef", df["A_UNVAN"].astype(str).tolist())
    hit = df[df["A_UNVAN"].astype(str) == kisi]
    rec = hit.iloc[0].to_dict() if not hit.empty else {}
    all_nums = rec.get("D_TELLER", [])
    if not isinstance(all_nums, list):
        all_nums = parse_phones(rec.get("D_TEL_ALL","") or rec.get("D_TEL",""))

    st.write(f"Bulunan numaralar: {rec.get('D_TEL_ALL','') or 'Yok'}")
    txt = st.text_area("Mesajınız")
    to_all = st.checkbox("Tüm numaralara gönder", value=True)

    if st.button("Gönder", type="primary"):
        if to_all:
            sent = whatsapp_gonder_coklu(all_nums, txt)
            st.success(f"Mesaj {sent} numaraya gönderildi.")
        else:
            if all_nums:
                ok = whatsapp_gonder(all_nums[0], txt)
                st.success("Gönderildi." if ok else "Gönderilemedi.")
            else:
                st.error("Telefon bulunamadı.")

# ======================================================
# 4) Tasdik Robotu (liste kontrol)
# ======================================================
elif secim == "4. Tasdik Robotu":
    st.title("🤖 Kayıtlı Mükellefler")
    df = st.session_state.get("mukellef_db")
    if df is None or df.empty:
        st.warning("Liste yok.")
    else:
        st.info(f"Toplam {len(df)} kayıt")
        st.dataframe(df[["A_UNVAN","B_TC","C_VKN","D_TEL_ALL"]], use_container_width=True)
