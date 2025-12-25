import os
import re
import time
import uuid
import shutil
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, date

# =========================================================
# 0) UYGULAMA KİMLİĞİ
# =========================================================
st.set_page_config(
    page_title="Halil Akça Takip Sistemi",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
API_TOKEN   = st.secrets.get("API_TOKEN", "YOUR_INSTANCE_ID")
SABIT_IHBAR_NO = "905351041616"

KALICI_EXCEL_YOLU     = "mukellef_db_kalici.xlsx"
PERSONEL_DOSYASI      = "personel_db.xlsx"
YAPILACAK_IS_DOSYASI  = "yapilacak_isler.xlsx"
YAPILACAK_IS_BACKUP   = "yapilacak_isler.xlsx.bak"
MUKELLEF_NOT_DOSYASI  = "mukellef_notlari.xlsx"

YAPILACAK_IS_COLS = [
    "IsID","Tip","Durum","Öncelik","Dönem","Mükellef","VKN",
    "Konu","Açıklama","SonTarih","Sorumlu","SorumluTel","MükellefTelAll",
    "Not","OlusturmaZamani","GuncellemeZamani","KapanisZamani"
]

# =========================================================
# 1) PROFESYONEL TEMA + DURUMA GÖRE RENKLER
# =========================================================
st.markdown("""
<style>
:root{
  --bg:#f4f8ff;
  --card:#ffffff;
  --line:#e6eefc;
  --blue:#0b5ed7;
  --text:#0f172a;
  --muted:#64748b;

  --s-open-bg: rgba(11,94,215,0.07);
  --s-open-b:  rgba(11,94,215,0.35);
  --s-open-strip: #0b5ed7;

  --s-prog-bg: rgba(245,158,11,0.10);
  --s-prog-b:  rgba(245,158,11,0.45);
  --s-prog-strip:#f59e0b;

  --s-done-bg: rgba(22,163,74,0.10);
  --s-done-b:  rgba(22,163,74,0.45);
  --s-done-strip:#16a34a;

  --s-cancel-bg: rgba(148,163,184,0.12);
  --s-cancel-b:  rgba(148,163,184,0.55);
  --s-cancel-strip:#94a3b8;

  --shadow: 0 10px 26px rgba(15,23,42,0.08);
}

.stApp{ background: var(--bg); font-family: "Segoe UI", system-ui, -apple-system, Arial; }
[data-testid="stSidebar"]{ background: linear-gradient(180deg,#ffffff 0%,#f7fbff 100%); border-right:1px solid var(--line); }

.ha-topbar{
  background: linear-gradient(90deg, rgba(11,94,215,1) 0%, rgba(29,78,216,1) 55%, rgba(56,189,248,1) 120%);
  color:#fff; padding:18px 20px; border-radius:18px;
  box-shadow: 0 14px 28px rgba(11,94,215,0.18);
  border: 1px solid rgba(255,255,255,0.18);
  margin-bottom: 12px;
}
.ha-title{ font-size:22px; font-weight:900; margin:0; }
.ha-sub{ margin:6px 0 0 0; font-size:12px; opacity:0.92; }

.card{
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 14px;
  box-shadow: var(--shadow);
  margin-bottom: 12px;
}
.card h3{ margin:0 0 8px 0; font-size:15px; font-weight:900; color: var(--text); }
.card .hint{ margin-top:-2px; margin-bottom:10px; font-size:12px; color: var(--muted); }

.hr{ height:1px; background: var(--line); margin:10px 0 12px 0; }

.badge{
  display:inline-flex; align-items:center; gap:6px;
  padding: 4px 10px; font-size: 11px;
  border-radius: 999px; border: 1px solid var(--line);
  background:#f8fbff; color: var(--muted);
}
.badge-blue{ border-color: rgba(11,94,215,0.25); background: rgba(11,94,215,0.06); color: var(--blue); }

.kpis{ display:flex; gap:10px; flex-wrap:wrap; }
.kpi{ flex: 1 1 160px; background: rgba(11,94,215,0.06); border: 1px solid rgba(11,94,215,0.16); border-radius: 16px; padding: 12px; }
.kpi .v{ font-size:18px; font-weight:900; color: var(--blue); }
.kpi .l{ font-size:12px; color: var(--muted); margin-top:2px; }

.small{ font-size:12px; color: var(--muted); }

.task-row{
  border-radius: 16px;
  border: 1px solid var(--line);
  box-shadow: 0 8px 18px rgba(15,23,42,0.06);
  margin-bottom: 10px;
  overflow:hidden;
}
.task-row .wrap{ padding: 12px 12px; }
.task-row .top{
  display:flex; align-items:flex-start; justify-content:space-between; gap:10px; flex-wrap:wrap;
}
.task-row .title{ font-weight:900; color: var(--text); font-size:14px; }
.task-row .sub{ color: var(--muted); font-size:12px; margin-top:2px; }
.task-row .meta{ display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }
.pill{
  display:inline-flex; align-items:center; gap:6px;
  padding: 4px 10px; border-radius: 999px;
  border: 1px solid var(--line); font-size:11px; color: var(--muted); background:#fff;
}
.pill strong{ color: var(--text); font-weight:800; }
.strip{ height:6px; }

.task-open { background: var(--s-open-bg); border-color: var(--s-open-b); }
.task-open .strip{ background: var(--s-open-strip); }
.task-prog { background: var(--s-prog-bg); border-color: var(--s-prog-b); }
.task-prog .strip{ background: var(--s-prog-strip); }
.task-done { background: var(--s-done-bg); border-color: var(--s-done-b); }
.task-done .strip{ background: var(--s-done-strip); }
.task-cancel { background: var(--s-cancel-bg); border-color: var(--s-cancel-b); }
.task-cancel .strip{ background: var(--s-cancel-strip); }

.stButton>button{ border-radius: 12px !important; border: 1px solid rgba(11,94,215,0.28) !important; }
.stButton>button[kind="primary"]{ background: var(--blue) !important; border: 1px solid rgba(11,94,215,0.35) !important; }
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"]{ border-radius: 12px !important; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# 2) YARDIMCILAR
# =========================================================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if len(p) == 10:
        p = "90" + p
    if len(p) == 11 and p.startswith("0"):
        p = "9" + p
    return p if len(p) >= 11 else ""

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

def whatsapp_gonder(numara: str, mesaj: str) -> bool:
    if not numara or not ID_INSTANCE or not API_TOKEN:
        st.error("WhatsApp API bilgileri veya numara eksik.")
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

def yeni_is_id() -> str:
    return "IS-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()

# =========================================================
# 3) KALICI OKU/YAZ (SİLİNMEZLİK + YEDEK)
# =========================================================
def safe_backup(src: str, dst: str):
    try:
        if os.path.exists(src):
            shutil.copy2(src, dst)
    except Exception:
        pass

def load_excel_safe(path, cols=None) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=cols or []).fillna("")
    try:
        df = pd.read_excel(path, dtype=str).fillna("")
        if cols:
            for c in cols:
                if c not in df.columns:
                    df[c] = ""
            df = df[cols]
        return df.fillna("")
    except Exception:
        return pd.DataFrame(columns=cols or []).fillna("")

def save_excel_safe(df: pd.DataFrame, path: str, backup_path: str = None):
    df = df.fillna("")
    if backup_path:
        safe_backup(path, backup_path)
    df.to_excel(path, index=False)

def load_mukellef() -> pd.DataFrame:
    cols = ["A_UNVAN","B_TC","C_VKN","D_TEL","D_TEL_ALL"]
    df = load_excel_safe(KALICI_EXCEL_YOLU, cols=cols)
    if (df["D_TEL_ALL"].astype(str).str.strip() == "").all():
        df["D_TEL_ALL"] = df["D_TEL"].apply(lambda x: " | ".join(parse_phones(x)))
    if (df["D_TEL"].astype(str).str.strip() == "").all():
        df["D_TEL"] = df["D_TEL_ALL"].apply(lambda x: (parse_phones(x)[0] if parse_phones(x) else ""))
    return df.fillna("")

def load_personel() -> pd.DataFrame:
    cols = ["Personel","Telefon","Aktif"]
    df = load_excel_safe(PERSONEL_DOSYASI, cols=cols)
    if (df["Aktif"].astype(str).str.strip() == "").all():
        df["Aktif"] = "Evet"
    return df.fillna("")

def load_mukellef_not() -> pd.DataFrame:
    cols = ["VKN","Mükellef","Notlar","GuncellemeZamani"]
    return load_excel_safe(MUKELLEF_NOT_DOSYASI, cols=cols).fillna("")

def load_yapilacak_isler() -> pd.DataFrame:
    df = load_excel_safe(YAPILACAK_IS_DOSYASI, cols=YAPILACAK_IS_COLS)
    if df.empty and os.path.exists(YAPILACAK_IS_BACKUP):
        df_bak = load_excel_safe(YAPILACAK_IS_BACKUP, cols=YAPILACAK_IS_COLS)
        if not df_bak.empty:
            save_excel_safe(df_bak, YAPILACAK_IS_DOSYASI, backup_path=None)
            df = df_bak.copy()
    if df is None or df.empty:
        df = pd.DataFrame(columns=YAPILACAK_IS_COLS)
    return df.fillna("")

def append_yapilacak_is(row: dict):
    df = load_yapilacak_isler()
    if not df.empty and (df["IsID"].astype(str) == str(row.get("IsID",""))).any():
        return
    df2 = pd.concat([df, pd.DataFrame([row], columns=YAPILACAK_IS_COLS)], ignore_index=True)
    save_excel_safe(df2, YAPILACAK_IS_DOSYASI, backup_path=YAPILACAK_IS_BACKUP)

def update_yapilacak_is(isid: str, updates: dict):
    df = load_yapilacak_isler()
    if df.empty:
        return
    m = df["IsID"].astype(str) == str(isid)
    if not m.any():
        return
    idx = df[m].index[0]
    for k, v in (updates or {}).items():
        if k in df.columns:
            df.loc[idx, k] = v
    save_excel_safe(df, YAPILACAK_IS_DOSYASI, backup_path=YAPILACAK_IS_BACKUP)

# =========================================================
# 4) MESAJ ŞABLONLARI
# =========================================================
def msg_yapilacak_is_personel(r: dict) -> str:
    return (
        "✅ *YAPILACAK İŞ ATAMASI*\n"
        f"🆔 *Kayıt No:* {r.get('IsID','')}\n"
        f"📅 *Son Tarih:* {r.get('SonTarih','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🏢 *Mükellef:* {r.get('Mükellef','')}\n"
        f"🆔 *VKN/TCKN:* {r.get('VKN','')}\n"
        f"⭐ *Öncelik:* {r.get('Öncelik','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📝 *Konu:* {r.get('Konu','')}\n"
        f"🧾 *Açıklama:* {r.get('Açıklama','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        "Tamamlanınca not ekleyiniz."
    )

def msg_yapilacak_is_mukellef(r: dict) -> str:
    return (
        "Merhaba,\n"
        "Tarafınızla ilgili bir işlem/talep bulunmaktadır.\n"
        f"📌 Konu: {r.get('Konu','')}\n"
        f"📝 Açıklama: {r.get('Açıklama','')}\n"
        f"📅 Son Tarih: {r.get('SonTarih','')}\n"
        "Geri dönüşünüz rica olunur."
    )

# =========================================================
# 5) SOL MENÜ (AYNEN)
# =========================================================
if "mukellef_db" not in st.session_state or st.session_state["mukellef_db"] is None:
    st.session_state["mukellef_db"] = load_mukellef()

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=64)
    st.header("HALİL AKÇA")
    secim = st.radio(
        "MENÜ",
        ["1. Excel Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"],
        index=1
    )
    st.caption("Takip ve Yönetim Paneli")

# =========================================================
# 6) 1. EXCEL YÜKLE
# =========================================================
if secim == "1. Excel Listesi Yükle":
    st.markdown("""
    <div class="ha-topbar">
      <p class="ha-title">Halil Akça Takip Sistemi</p>
      <p class="ha-sub">Mükellef veritabanı yükleme ve kalıcı kayıt</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="card"><h3>📂 Mükellef Veritabanı</h3><div class="hint">Telefon hücresinde birden fazla numara varsa sistem hepsini D_TEL_ALL alanında saklar.</div>', unsafe_allow_html=True)

    up = st.file_uploader("Excel seçin", type=["xlsx", "xls"])
    if up:
        try:
            raw = pd.read_excel(up, dtype=str).fillna("")
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
            save_excel_safe(df, KALICI_EXCEL_YOLU)

            st.success(f"✅ Kaydedildi. Toplam kayıt: {len(df)}")
            st.dataframe(df[["A_UNVAN","B_TC","C_VKN","D_TEL_ALL"]].head(40), use_container_width=True)
        except Exception as e:
            st.error(f"Okuma hatası: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# 7) 2. PANEL: DURUMA GÖRE RENKLİ GÖSTERİM
# =========================================================
elif secim == "2. KDV Analiz Robotu":
    st.markdown("""
    <div class="ha-topbar">
      <p class="ha-title">Halil Akça Takip Sistemi</p>
      <p class="ha-sub">Yapılacak İş oluşturma · Renkli durum görünümü · Kayıtlar silinmez</p>
    </div>
    """, unsafe_allow_html=True)

    dfm = st.session_state["mukellef_db"]
    if dfm is None or dfm.empty:
        st.warning("Önce '1. Excel Listesi Yükle' menüsünden mükellef listesini yükleyin.")
        st.stop()

    dfp = load_personel()
    dfy = load_yapilacak_isler()
    dfn = load_mukellef_not()

    open_count = (dfy["Durum"].astype(str) == "AÇIK").sum()
    inq_count  = (dfy["Durum"].astype(str) == "İNCELEMEDE").sum()
    clo_count  = (dfy["Durum"].astype(str) == "KAPANDI").sum()

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="kpis">', unsafe_allow_html=True)
    st.markdown(f'<div class="kpi"><div class="v">{len(dfy)}</div><div class="l">Toplam</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="kpi"><div class="v">{open_count}</div><div class="l">Açık</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="kpi"><div class="v">{inq_count}</div><div class="l">İncelemede</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="kpi"><div class="v">{clo_count}</div><div class="l">Kapandı</div></div>', unsafe_allow_html=True)
    st.markdown('</div><div class="small">🔒 Silme yok. Tüm kayıtlar kalıcıdır.</div></div>', unsafe_allow_html=True)

    # ---- ÜST: Oluştur + Notlar ----
    col_left, col_right = st.columns([1.25, 1.0], gap="large")

    with col_left:
        st.markdown('<div class="card"><h3>➕ Yapılacak İş Oluştur</h3><div class="hint">Kayıt kalıcıdır, silinmez. Durum ve not güncellenebilir.</div>', unsafe_allow_html=True)

        mukellef = st.selectbox("Mükellef", dfm["A_UNVAN"].astype(str).tolist())
        rec = dfm[dfm["A_UNVAN"].astype(str) == str(mukellef)].iloc[0].to_dict()
        vkn = str(rec.get("C_VKN","")).strip() or str(rec.get("B_TC","")).strip()
        tel_all = str(rec.get("D_TEL_ALL","")).strip()
        tel_list = parse_phones(tel_all)

        st.markdown(
            f'<span class="badge badge-blue">VKN/TCKN: {vkn or "-"}</span> '
            f'<span class="badge">Tel: {tel_all or "-"}</span>',
            unsafe_allow_html=True
        )

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

        konu = st.text_input("Konu", placeholder="Örn: KDV evrak tamamlama")
        aciklama = st.text_area("Açıklama / Talimat", height=105)
        is_notu = st.text_area("Not (Bu kayıt)", height=80)

        cA, cB, cC = st.columns([1.1, 1.0, 1.0])
        with cA:
            donem = st.text_input("Dönem", placeholder="Örn: Ocak / 2024")
        with cB:
            oncelik = st.selectbox("Öncelik", ["Yüksek","Orta","Düşük"], index=1)
        with cC:
            son_tarih = st.date_input("Son Tarih", value=date.today())

        aktif = dfp[dfp["Aktif"].astype(str).str.lower().isin(["evet","yes","true","1"])].copy()
        sorumlu = st.selectbox("Sorumlu Personel", ["(Atama Yok)"] + aktif["Personel"].astype(str).tolist())

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
        st.markdown("**WhatsApp Bildirimi**")
        wa_p = st.checkbox("Personeli bilgilendir", value=True)
        wa_m = st.checkbox("Mükellefi bilgilendir", value=False)
        wa_m_all = st.checkbox("Mükellefe TÜM numara", value=True)

        if st.button("✅ KAYDET", type="primary", use_container_width=True):
            if not str(konu).strip():
                st.error("Konu boş olamaz.")
            elif not str(aciklama).strip():
                st.error("Açıklama boş olamaz.")
            else:
                sor_tel = ""
                if sorumlu != "(Atama Yok)":
                    rr = aktif[aktif["Personel"].astype(str) == str(sorumlu)]
                    if not rr.empty:
                        sor_tel = normalize_phone(rr.iloc[0].get("Telefon",""))

                row = {
                    "IsID": yeni_is_id(),
                    "Tip": "MANUEL",
                    "Durum": "AÇIK",
                    "Öncelik": oncelik,
                    "Dönem": str(donem).strip(),
                    "Mükellef": str(mukellef).strip(),
                    "VKN": str(vkn).strip(),
                    "Konu": str(konu).strip(),
                    "Açıklama": str(aciklama).strip(),
                    "SonTarih": str(son_tarih),
                    "Sorumlu": "" if sorumlu == "(Atama Yok)" else str(sorumlu),
                    "SorumluTel": sor_tel,
                    "MükellefTelAll": tel_all,
                    "Not": str(is_notu).strip(),
                    "OlusturmaZamani": now_str(),
                    "GuncellemeZamani": now_str(),
                    "KapanisZamani": ""
                }

                append_yapilacak_is(row)

                if wa_p and sor_tel:
                    whatsapp_gonder(sor_tel, msg_yapilacak_is_personel(row))
                if wa_m and tel_list:
                    if wa_m_all:
                        whatsapp_gonder_coklu(tel_list, msg_yapilacak_is_mukellef(row))
                    else:
                        whatsapp_gonder(tel_list[0], msg_yapilacak_is_mukellef(row))

                st.success(f"Kaydedildi: {row['IsID']}")
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="card"><h3>🗒️ Mükellef Notları</h3><div class="hint">Mükellef bazında kalıcıdır.</div>', unsafe_allow_html=True)

        dfn = load_mukellef_not()
        old_note = ""
        hit = dfn[dfn["VKN"].astype(str) == str(vkn)]
        if not hit.empty:
            old_note = str(hit.iloc[0].get("Notlar",""))

        muk_not = st.text_area("Genel Not", value=old_note, height=240)

        if st.button("💾 NOTU KAYDET", use_container_width=True):
            dfn2 = dfn.copy()
            m = dfn2["VKN"].astype(str) == str(vkn)
            if m.any():
                idx = dfn2[m].index[0]
                dfn2.loc[idx, "Mükellef"] = str(mukellef)
                dfn2.loc[idx, "Notlar"] = str(muk_not).strip()
                dfn2.loc[idx, "GuncellemeZamani"] = now_str()
            else:
                dfn2 = pd.concat([dfn2, pd.DataFrame([{
                    "VKN": str(vkn),
                    "Mükellef": str(mukellef),
                    "Notlar": str(muk_not).strip(),
                    "GuncellemeZamani": now_str()
                }])], ignore_index=True)

            save_excel_safe(dfn2, MUKELLEF_NOT_DOSYASI)
            st.success("Not kaydedildi.")
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # ---- LİSTE: RENKLİ KARTLAR ----
    st.markdown('<div class="card"><h3>📌 Yapılacak İşler (Renkli)</h3><div class="hint">Kapandı/Devam ediyor/İncelemede renkleri farklıdır.</div>', unsafe_allow_html=True)

    dfy = load_yapilacak_isler()

    f1, f2, f3, f4, f5 = st.columns([1.15, 1.15, 1.15, 1.15, 2.4])
    with f1:
        fdurum = st.selectbox("Durum", ["(Tümü)", "AÇIK", "İNCELEMEDE", "KAPANDI", "İPTAL"])
    with f2:
        fonc = st.selectbox("Öncelik", ["(Tümü)","Yüksek","Orta","Düşük"])
    with f3:
        fson = st.selectbox("Tarih", ["(Hepsi)", "Gecikenler"])
    with f4:
        fsirala = st.selectbox("Sırala", ["Önce Geciken", "Son Tarih Yakın", "Yeni → Eski", "Eski → Yeni"])
    with f5:
        fara = st.text_input("Ara (Mükellef / Konu)", placeholder="örn: tekstil / kdv / evrak")

    view = dfy.copy()
    if fdurum != "(Tümü)":
        view = view[view["Durum"].astype(str) == fdurum]
    if fonc != "(Tümü)":
        view = view[view["Öncelik"].astype(str) == fonc]
    if str(fara).strip():
        q = str(fara).strip().lower()
        view = view[
            view["Mükellef"].astype(str).str.lower().str.contains(q, na=False) |
            view["Konu"].astype(str).str.lower().str.contains(q, na=False) |
            view["Açıklama"].astype(str).str.lower().str.contains(q, na=False)
        ]

    def to_dt(x):
        try:
            return pd.to_datetime(str(x), errors="coerce")
        except Exception:
            return pd.NaT

    view["_son"] = view["SonTarih"].apply(to_dt)
    today_dt = pd.to_datetime(date.today())
    view["_gecik"] = (view["_son"].notna()) & (view["_son"] < today_dt) & (view["Durum"].astype(str).isin(["AÇIK","İNCELEMEDE"]))

    if fson == "Gecikenler":
        view = view[view["_gecik"] == True]

    # Sıralama
    if fsirala == "Önce Geciken":
        view = view.sort_values(by=["_gecik","_son"], ascending=[False, True])
    elif fsirala == "Son Tarih Yakın":
        view = view.sort_values(by=["_son"], ascending=[True])
    elif fsirala == "Yeni → Eski":
        view = view.sort_values(by=["OlusturmaZamani"], ascending=[False])
    else:
        view = view.sort_values(by=["OlusturmaZamani"], ascending=[True])

    # Kart render
    def status_class(s: str) -> str:
        s = (s or "").strip().upper()
        if s == "KAPANDI":
            return "task-row task-done"
        if s == "İNCELEMEDE":
            return "task-row task-prog"
        if s == "İPTAL":
            return "task-row task-cancel"
        return "task-row task-open"  # AÇIK

    def pill(text: str) -> str:
        return f"<span class='pill'>{text}</span>"

    if view.empty:
        st.info("Kayıt bulunamadı.")
    else:
        for _, r in view.drop(columns=["_son","_gecik"], errors="ignore").iterrows():
            durum = str(r.get("Durum","")).strip()
            oncelik = str(r.get("Öncelik","")).strip()
            son_t = str(r.get("SonTarih","")).strip()
            gecik = False
            try:
                dt = pd.to_datetime(son_t, errors="coerce")
                if pd.notna(dt):
                    gecik = (dt.date() < date.today()) and (durum in ["AÇIK","İNCELEMEDE"])
            except Exception:
                pass

            gecik_pill = "<span class='pill'><strong>GECİKMİŞ</strong></span>" if gecik else ""

            html = f"""
            <div class="{status_class(durum)}">
              <div class="strip"></div>
              <div class="wrap">
                <div class="top">
                  <div>
                    <div class="title">{r.get("Mükellef","")} — {r.get("Konu","")}</div>
                    <div class="sub">VKN: {r.get("VKN","")} · Dönem: {r.get("Dönem","") or "-"} · Kayıt No: {r.get("IsID","")}</div>
                  </div>
                  <div>
                    <span class="badge badge-blue">{durum or "-"}</span>
                  </div>
                </div>
                <div class="meta">
                  {pill(f"<strong>Öncelik:</strong> {oncelik or '-'}")}
                  {pill(f"<strong>Son Tarih:</strong> {son_t or '-'}")}
                  {pill(f"<strong>Sorumlu:</strong> {r.get('Sorumlu','') or '-'}")}
                  {gecik_pill}
                </div>
                <div class="sub" style="margin-top:8px;"><strong>Açıklama:</strong> {r.get("Açıklama","")}</div>
                <div class="sub"><strong>Not:</strong> {r.get("Not","") or "-"}</div>
              </div>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # ---- SEÇİLİ KAYIT GÜNCELLE (aynı)
    st.markdown('<div class="card"><h3>🛠️ Seçili Yapılacak İş</h3><div class="hint">Silme yoktur. Sadece güncelleme yapılır.</div>', unsafe_allow_html=True)

    dfy_all = load_yapilacak_isler()
    if dfy_all.empty:
        st.info("Kayıt yok.")
    else:
        sec_id = st.selectbox("Kayıt Seç (IsID)", dfy_all["IsID"].astype(str).tolist())
        row = dfy_all[dfy_all["IsID"].astype(str) == str(sec_id)].iloc[0].to_dict()

        a, b = st.columns([1.2, 1.0], gap="large")
        with a:
            new_status = st.selectbox("Durum", ["AÇIK","İNCELEMEDE","KAPANDI","İPTAL"], index=0)
            new_due = st.text_input("Son Tarih (YYYY-MM-DD)", value=str(row.get("SonTarih","")))
            new_note = st.text_area("Not (Bu kayıt)", value=str(row.get("Not","")), height=110)

        with b:
            st.markdown("**Hatırlatma / Mesaj**")
            target = st.selectbox("Gönder", ["Gönderme", "Sorumlu Personele", "Mükellefe", "Serbest Numara"])
            free = ""
            all_m = False
            if target == "Serbest Numara":
                free = st.text_input("Numara", placeholder="905xxxxxxxxx")
            if target == "Mükellefe":
                all_m = st.checkbox("Mükellefe TÜM numara", value=True)

        if st.button("💾 GÜNCELLE", type="primary", use_container_width=True):
            updates = {
                "Durum": new_status,
                "SonTarih": str(new_due).strip(),
                "Not": str(new_note).strip(),
                "GuncellemeZamani": now_str()
            }
            if new_status == "KAPANDI":
                updates["KapanisZamani"] = now_str()

            update_yapilacak_is(sec_id, updates)

            # WhatsApp (opsiyonel)
            cur_df = load_yapilacak_isler()
            cur = cur_df[cur_df["IsID"].astype(str) == str(sec_id)].iloc[0].to_dict()

            if target != "Gönderme":
                if target == "Sorumlu Personele":
                    tel = normalize_phone(cur.get("SorumluTel",""))
                    if tel:
                        whatsapp_gonder(tel, msg_yapilacak_is_personel(cur))
                elif target == "Mükellefe":
                    tels = parse_phones(cur.get("MükellefTelAll",""))
                    if tels:
                        if all_m:
                            whatsapp_gonder_coklu(tels, msg_yapilacak_is_mukellef(cur))
                        else:
                            whatsapp_gonder(tels[0], msg_yapilacak_is_mukellef(cur))
                else:
                    tel = normalize_phone(free)
                    if tel:
                        whatsapp_gonder(tel, msg_yapilacak_is_personel(cur))

            st.success("Güncellendi.")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# 8) 3. PROFESYONEL MESAJ
# =========================================================
elif secim == "3. Profesyonel Mesaj":
    st.markdown("""
    <div class="ha-topbar">
      <p class="ha-title">Profesyonel Mesaj</p>
      <p class="ha-sub">Mükellef seçip WhatsApp üzerinden mesaj gönderimi</p>
    </div>
    """, unsafe_allow_html=True)

    dfm = load_mukellef()
    if dfm.empty:
        st.warning("Önce mükellef listesini yükleyin.")
        st.stop()

    st.markdown('<div class="card"><h3>📤 Mesaj Gönder</h3><div class="hint">Tüm numaralara veya ilk numaraya gönderim yapabilirsiniz.</div>', unsafe_allow_html=True)

    kisi = st.selectbox("Mükellef", dfm["A_UNVAN"].astype(str).tolist())
    rec = dfm[dfm["A_UNVAN"].astype(str) == str(kisi)].iloc[0].to_dict()
    tels = parse_phones(rec.get("D_TEL_ALL",""))

    st.markdown(f'<span class="badge badge-blue">Telefonlar: {rec.get("D_TEL_ALL","") or "-"}</span>', unsafe_allow_html=True)
    msg = st.text_area("Mesaj")
    to_all = st.checkbox("Tüm numaralara gönder", value=True)

    if st.button("Gönder", type="primary"):
        if to_all:
            sent = whatsapp_gonder_coklu(tels, msg)
            st.success(f"Gönderildi: {sent} numara")
        else:
            if tels:
                ok = whatsapp_gonder(tels[0], msg)
                st.success("Gönderildi." if ok else "Gönderilemedi.")
            else:
                st.error("Telefon bulunamadı.")

    st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# 9) 4. TASDİK ROBOTU
# =========================================================
elif secim == "4. Tasdik Robotu":
    st.markdown("""
    <div class="ha-topbar">
      <p class="ha-title">Kayıtlar</p>
      <p class="ha-sub">Mükellef / Personel / Yapılacak İşler</p>
    </div>
    """, unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["📋 Mükellefler", "👥 Personel", "🗂️ Yapılacak İşler (Ham)"])
    with t1:
        st.markdown('<div class="card"><h3>📋 Mükellef Listesi</h3></div>', unsafe_allow_html=True)
        st.dataframe(load_mukellef(), use_container_width=True)

    with t2:
        st.markdown('<div class="card"><h3>👥 Personel</h3><div class="hint">Personel yönetimi burada tutulur.</div>', unsafe_allow_html=True)
        st.dataframe(load_personel(), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with t3:
        st.markdown('<div class="card"><h3>🗂️ Yapılacak İşler (Ham)</h3><div class="hint">Silme yoktur. Kayıtlar kalıcıdır.</div>', unsafe_allow_html=True)
        st.dataframe(load_yapilacak_isler(), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
