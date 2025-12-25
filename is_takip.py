import os
import re
import time
import uuid
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
API_TOKEN   = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
SABIT_IHBAR_NO = "905351041616"

# Kalıcı dosyalar
KALICI_EXCEL_YOLU     = "mukellef_db_kalici.xlsx"
PERSONEL_DOSYASI      = "personel_db.xlsx"
IS_TAKIP_DOSYASI      = "is_takip.xlsx"
MUKELLEF_NOT_DOSYASI  = "mukellef_notlari.xlsx"

# =========================================================
# 1) TEMA / CSS (Mavi-Beyaz - Mali Müşavir Paneli)
# =========================================================
st.markdown("""
<style>
:root{
  --bg:#f6f9ff;
  --card:#ffffff;
  --line:#e6eefc;
  --blue:#0b5ed7;
  --blue2:#1d4ed8;
  --text:#0f172a;
  --muted:#64748b;
  --danger:#dc2626;
  --warn:#f59e0b;
  --ok:#16a34a;
}

.stApp{ background: var(--bg); color: var(--text); font-family: "Segoe UI", system-ui, -apple-system, Arial; }
[data-testid="stSidebar"]{
  background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
  border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h3 { color: var(--text); }

.ha-header{
  background: linear-gradient(90deg, rgba(11,94,215,1) 0%, rgba(29,78,216,1) 60%, rgba(56,189,248,1) 120%);
  color:#fff; padding:18px 20px; border-radius:16px;
  box-shadow: 0 10px 22px rgba(11,94,215,0.18);
  border: 1px solid rgba(255,255,255,0.18);
}
.ha-title{ font-size:22px; font-weight:800; margin:0; letter-spacing:0.2px; }
.ha-sub{ margin:4px 0 0 0; font-size:12px; opacity:0.9; }

.card{
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 14px 14px;
  box-shadow: 0 8px 18px rgba(15,23,42,0.06);
  margin-bottom: 12px;
}
.card h3{
  margin: 0 0 8px 0;
  font-size: 15px;
  font-weight: 800;
  color: var(--text);
}
.card .hint{
  margin-top: -2px;
  margin-bottom: 10px;
  font-size: 12px;
  color: var(--muted);
}

.kpis{
  display:flex; gap:10px; flex-wrap:wrap;
}
.kpi{
  flex: 1 1 160px;
  background: rgba(11,94,215,0.06);
  border: 1px solid rgba(11,94,215,0.14);
  border-radius: 14px;
  padding: 10px 12px;
}
.kpi .v{ font-size:18px; font-weight:900; color: var(--blue); }
.kpi .l{ font-size:12px; color: var(--muted); margin-top:2px; }

.badge{
  display:inline-block;
  padding: 3px 10px;
  font-size: 11px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background:#f8fbff;
  color: var(--muted);
}
.badge-blue{ border-color: rgba(11,94,215,0.25); background: rgba(11,94,215,0.06); color: var(--blue); }
.badge-ok{ border-color: rgba(22,163,74,0.25); background: rgba(22,163,74,0.08); color: var(--ok); }
.badge-warn{ border-color: rgba(245,158,11,0.30); background: rgba(245,158,11,0.10); color: #b45309; }
.badge-danger{ border-color: rgba(220,38,38,0.28); background: rgba(220,38,38,0.10); color: var(--danger); }

.hr{ height:1px; background: var(--line); margin:10px 0 12px 0; }

.small{ font-size:12px; color: var(--muted); }

.stButton>button{
  border-radius: 12px !important;
  border: 1px solid rgba(11,94,215,0.35) !important;
}
.stButton>button[kind="primary"]{
  background: var(--blue) !important;
  border: 1px solid rgba(11,94,215,0.35) !important;
}
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"]{
  border-radius: 12px !important;
}

</style>
""", unsafe_allow_html=True)

# =========================================================
# 2) YARDIMCI FONKSİYONLAR
# =========================================================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if len(p) == 10:           # 5xxxxxxxxx
        p = "90" + p
    if len(p) == 11 and p.startswith("0"):  # 05xxxxxxxxx
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

def save_excel_safe(df: pd.DataFrame, path: str):
    df = df.fillna("")
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

def load_isler() -> pd.DataFrame:
    cols = [
        "IsID","Tip","Durum","Öncelik","Dönem","Mükellef","VKN",
        "Konu","Açıklama","SonTarih","Sorumlu","SorumluTel","MükellefTelAll",
        "Not","OlusturmaZamani","GuncellemeZamani","KapanisZamani"
    ]
    return load_excel_safe(IS_TAKIP_DOSYASI, cols=cols).fillna("")

def load_mukellef_not() -> pd.DataFrame:
    cols = ["VKN","Mükellef","Notlar","GuncellemeZamani"]
    return load_excel_safe(MUKELLEF_NOT_DOSYASI, cols=cols).fillna("")

def msg_is_personel(r: dict) -> str:
    return (
        "📌 *YENİ İŞ EMRİ*\n"
        f"🆔 *İş No:* {r.get('IsID','')}\n"
        f"📅 *Son Tarih:* {r.get('SonTarih','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🏢 *Mükellef:* {r.get('Mükellef','')}\n"
        f"🆔 *VKN/TCKN:* {r.get('VKN','')}\n"
        f"⭐ *Öncelik:* {r.get('Öncelik','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📝 *Konu:* {r.get('Konu','')}\n"
        f"🧾 *Açıklama:* {r.get('Açıklama','')}\n"
        "━━━━━━━━━━━━━━━━\n"
        "Lütfen işlem sonrası not giriniz."
    )

def msg_is_mukellef(r: dict) -> str:
    return (
        "Merhaba,\n"
        "Tarafınızla ilgili bir talep bulunmaktadır.\n"
        f"📌 Konu: {r.get('Konu','')}\n"
        f"📝 Açıklama: {r.get('Açıklama','')}\n"
        f"📅 Son Tarih: {r.get('SonTarih','')}\n"
        "Geri dönüşünüz rica olunur."
    )

# Session ön yükleme
if "mukellef_db" not in st.session_state or st.session_state["mukellef_db"] is None:
    st.session_state["mukellef_db"] = load_mukellef()

# =========================================================
# 3) SOL MENÜ (AYNEN) - DEFAULT: 2
# =========================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=64)
    st.header("HALİL AKÇA")
    secim = st.radio(
        "MENÜ",
        ["1. Excel Listesi Yükle", "2. KDV Analiz Robotu", "3. Profesyonel Mesaj", "4. Tasdik Robotu"],
        index=1
    )
    st.caption("Takip ve İş Emri Paneli")

# =========================================================
# 4) 1. EXCEL YÜKLE
# =========================================================
if secim == "1. Excel Listesi Yükle":
    st.markdown("""
    <div class="ha-header">
      <p class="ha-title">Halil Akça Takip Sistemi</p>
      <p class="ha-sub">Mükellef veritabanı yükleme ve kalıcı kayıt</p>
    </div>
    """, unsafe_allow_html=True)
    st.write("")

    st.markdown('<div class="card"><h3>📂 Mükellef Veritabanı Yükle</h3><div class="hint">Telefon hücresinde birden fazla numara olabilir; sistem hepsini D_TEL_ALL alanında saklar.</div>', unsafe_allow_html=True)

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
            save_excel_safe(df[["A_UNVAN","B_TC","C_VKN","D_TEL","D_TEL_ALL"]], KALICI_EXCEL_YOLU)

            st.success(f"✅ Kaydedildi. Toplam kayıt: {len(df)}")
            st.dataframe(df[["A_UNVAN","B_TC","C_VKN","D_TEL_ALL"]].head(40), use_container_width=True)
        except Exception as e:
            st.error(f"Okuma hatası: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# 5) 2. ANA SAYFA: DERLİ TOPLU PANEL
# =========================================================
elif secim == "2. KDV Analiz Robotu":
    st.markdown("""
    <div class="ha-header">
      <p class="ha-title">Halil Akça Takip Sistemi</p>
      <p class="ha-sub">İş emri oluşturma · Personel atama · WhatsApp bildirim · İş takibi</p>
    </div>
    """, unsafe_allow_html=True)
    st.write("")

    dfm = st.session_state["mukellef_db"]
    if dfm is None or dfm.empty:
        st.warning("Önce '1. Excel Listesi Yükle' menüsünden mükellef listesini yükleyin.")
        st.stop()

    dfp = load_personel()
    dfi = load_isler()
    dfn = load_mukellef_not()

    # KPI Şeridi
    open_count = (dfi["Durum"].astype(str) == "AÇIK").sum()
    inq_count  = (dfi["Durum"].astype(str) == "İNCELEMEDE").sum()
    clo_count  = (dfi["Durum"].astype(str) == "KAPANDI").sum()

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="kpis">', unsafe_allow_html=True)
    st.markdown(f'<div class="kpi"><div class="v">{len(dfi)}</div><div class="l">Toplam İş</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="kpi"><div class="v">{open_count}</div><div class="l">Açık</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="kpi"><div class="v">{inq_count}</div><div class="l">İncelemede</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="kpi"><div class="v">{clo_count}</div><div class="l">Kapandı</div></div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

    # 2 sütun grid (sol: iş emri aç, sağ: mükellef notu)
    col_left, col_right = st.columns([1.25, 1.0], gap="large")

    with col_left:
        st.markdown('<div class="card"><h3>➕ İş Emri Aç</h3><div class="hint">Mükellef seçin, işi tanımlayın, personel atayın ve isterseniz WhatsApp bildirim gönderin.</div>', unsafe_allow_html=True)

        mukellef = st.selectbox("Mükellef", dfm["A_UNVAN"].astype(str).tolist())
        rec = dfm[dfm["A_UNVAN"].astype(str) == str(mukellef)].iloc[0].to_dict()
        vkn = str(rec.get("C_VKN","")).strip() or str(rec.get("B_TC","")).strip()
        tel_all = str(rec.get("D_TEL_ALL","")).strip()
        tel_list = parse_phones(tel_all)

        st.markdown(f'<span class="badge badge-blue">VKN/TCKN: {vkn or "-"}</span> &nbsp; <span class="badge">Tel: {tel_all or "-"}</span>', unsafe_allow_html=True)
        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

        konu = st.text_input("Konu", placeholder="Örn: Ocak KDV evrak tamamlama")
        aciklama = st.text_area("Açıklama / Talimat", height=100)
        is_notu = st.text_area("İş Notu (Bu işe özel)", height=80)

        cA, cB = st.columns([1, 1])
        with cA:
            donem = st.text_input("Dönem (opsiyonel)", placeholder="Örn: Ocak / 2024")
            oncelik = st.selectbox("Öncelik", ["Yüksek","Orta","Düşük"], index=1)
        with cB:
            son_tarih = st.date_input("Son Tarih", value=date.today())

        aktif = dfp[dfp["Aktif"].astype(str).str.lower().isin(["evet","yes","true","1"])].copy()
        sorumlu = st.selectbox("Sorumlu Personel", ["(Atama Yok)"] + aktif["Personel"].astype(str).tolist())

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
        st.markdown("**WhatsApp Bildirimi**")
        wa_p = st.checkbox("Personeli bilgilendir", value=True)
        wa_m = st.checkbox("Mükellefi bilgilendir", value=False)
        wa_m_all = st.checkbox("Mükellefe TÜM numaralara gönder", value=True)

        if st.button("✅ İŞ EMRİNİ OLUŞTUR", type="primary", use_container_width=True):
            if not str(konu).strip():
                st.error("Konu boş olamaz.")
            elif not str(aciklama).strip():
                st.error("Açıklama boş olamaz.")
            else:
                # sorumlu tel
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

                # kaydet iş
                dfi2 = pd.concat([dfi, pd.DataFrame([row])], ignore_index=True)
                save_excel_safe(dfi2, IS_TAKIP_DOSYASI)

                # WhatsApp
                if wa_p and sor_tel:
                    whatsapp_gonder(sor_tel, msg_is_personel(row))
                if wa_m and tel_list:
                    if wa_m_all:
                        whatsapp_gonder_coklu(tel_list, msg_is_mukellef(row))
                    else:
                        whatsapp_gonder(tel_list[0], msg_is_mukellef(row))

                st.success(f"İş emri oluşturuldu: {row['IsID']}")
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="card"><h3>🗒️ Mükellef Notları (Kalıcı)</h3><div class="hint">Bu notlar mükellef bazında saklanır ve her girişte görünür.</div>', unsafe_allow_html=True)

        # not getir
        old_note = ""
        hitn = dfn[dfn["VKN"].astype(str) == str(vkn)]
        if not hitn.empty:
            old_note = str(hitn.iloc[0].get("Notlar",""))

        muk_not = st.text_area("Genel Not", value=old_note, height=220)

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
            st.success("Mükellef notu kaydedildi.")
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # -------------------- İş Listesi --------------------
    st.markdown('<div class="card"><h3>📌 Yapılacak İşler</h3><div class="hint">Filtrele, seç ve tek ekrandan güncelle / hatırlatma gönder.</div>', unsafe_allow_html=True)

    dfi = load_isler()

    f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.2, 2.0])
    with f1:
        fdurum = st.selectbox("Durum", ["(Tümü)", "AÇIK", "İNCELEMEDE", "KAPANDI", "İPTAL"])
    with f2:
        fonc = st.selectbox("Öncelik", ["(Tümü)","Yüksek","Orta","Düşük"])
    with f3:
        fson = st.selectbox("Son Tarih", ["(Hepsi)", "Gecikenler"])
    with f4:
        fara = st.text_input("Ara (Mükellef/Konu)", placeholder="örn: tekstil / kdv")

    view = dfi.copy()
    if fdurum != "(Tümü)":
        view = view[view["Durum"].astype(str) == fdurum]
    if fonc != "(Tümü)":
        view = view[view["Öncelik"].astype(str) == fonc]
    if str(fara).strip():
        q = str(fara).strip().lower()
        view = view[
            view["Mükellef"].astype(str).str.lower().str.contains(q, na=False) |
            view["Konu"].astype(str).str.lower().str.contains(q, na=False)
        ]

    # geciken
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

    view = view.sort_values(by=["_gecik","_son"], ascending=[False, True])

    st.dataframe(view.drop(columns=["_son","_gecik"], errors="ignore"), use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # -------------------- Seçili iş güncelle --------------------
    st.markdown('<div class="card"><h3>🛠️ Seçili İş İşlemleri</h3><div class="hint">Durum/son tarih/not güncelleyin. İsterseniz WhatsApp hatırlatma gönderin.</div>', unsafe_allow_html=True)

    if view.empty:
        st.info("Liste boş.")
    else:
        sec_id = st.selectbox("İş Seç (IsID)", view["IsID"].astype(str).tolist())
        row = dfi[dfi["IsID"].astype(str) == str(sec_id)].iloc[0].to_dict()

        a, b = st.columns([1.2, 1.0], gap="large")
        with a:
            new_status = st.selectbox("Durum", ["AÇIK","İNCELEMEDE","KAPANDI","İPTAL"], index=0)
            new_due = st.text_input("Son Tarih (YYYY-MM-DD)", value=str(row.get("SonTarih","")))
            new_note = st.text_area("İş Notu", value=str(row.get("Not","")), height=110)
        with b:
            st.markdown("**Hatırlatma Mesajı**")
            target = st.selectbox("Gönder", ["Gönderme", "Sorumlu Personele", "Mükellefe", "Serbest Numara"])
            free = ""
            all_m = False
            if target == "Serbest Numara":
                free = st.text_input("Numara", placeholder="905xxxxxxxxx")
            if target == "Mükellefe":
                all_m = st.checkbox("Mükellefe TÜM numara", value=True)

        if st.button("💾 KAYDET", type="primary", use_container_width=True):
            idx = dfi[dfi["IsID"].astype(str) == str(sec_id)].index[0]
            dfi.loc[idx, "Durum"] = new_status
            dfi.loc[idx, "SonTarih"] = str(new_due).strip()
            dfi.loc[idx, "Not"] = str(new_note).strip()
            dfi.loc[idx, "GuncellemeZamani"] = now_str()
            if new_status == "KAPANDI" and not str(dfi.loc[idx, "KapanisZamani"]).strip():
                dfi.loc[idx, "KapanisZamani"] = now_str()

            save_excel_safe(dfi, IS_TAKIP_DOSYASI)

            cur = dfi.loc[idx].to_dict()

            if target != "Gönderme":
                if target == "Sorumlu Personele":
                    tel = normalize_phone(cur.get("SorumluTel",""))
                    if tel:
                        whatsapp_gonder(tel, msg_is_personel(cur))
                elif target == "Mükellefe":
                    tels = parse_phones(cur.get("MükellefTelAll",""))
                    if tels:
                        if all_m:
                            whatsapp_gonder_coklu(tels, msg_is_mukellef(cur))
                        else:
                            whatsapp_gonder(tels[0], msg_is_mukellef(cur))
                else:
                    tel = normalize_phone(free)
                    if tel:
                        whatsapp_gonder(tel, msg_is_personel(cur))

            st.success("Güncellendi.")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # Analiz kısmı (ekranı bozmasın diye kapalı)
    with st.expander("📄 Beyanname Analizi (Opsiyonel)"):
        st.info("Analiz ekranını da aynı mavi-beyaz stile göre entegre edebilirim. Mevcut analiz modülünüzü buraya taşıyabiliriz.")

# =========================================================
# 6) 3. PROFESYONEL MESAJ
# =========================================================
elif secim == "3. Profesyonel Mesaj":
    st.markdown("""
    <div class="ha-header">
      <p class="ha-title">Profesyonel Mesaj</p>
      <p class="ha-sub">Mükellef seçip WhatsApp üzerinden mesaj gönderimi</p>
    </div>
    """, unsafe_allow_html=True)
    st.write("")

    dfm = load_mukellef()
    if dfm.empty:
        st.warning("Önce mükellef listesini yükleyin.")
        st.stop()

    st.markdown('<div class="card"><h3>📤 Mesaj Gönder</h3><div class="hint">Mükellefin tüm numaralarına veya sadece ilk numaraya gönderim yapabilirsiniz.</div>', unsafe_allow_html=True)

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
# 7) 4. TASDİK ROBOTU
# =========================================================
elif secim == "4. Tasdik Robotu":
    st.markdown("""
    <div class="ha-header">
      <p class="ha-title">Kayıtlar</p>
      <p class="ha-sub">Mükellef / Personel / İş listeleri</p>
    </div>
    """, unsafe_allow_html=True)
    st.write("")

    t1, t2, t3 = st.tabs(["📋 Mükellefler", "👥 Personel", "🗂️ İşler (Ham)"])

    with t1:
        st.markdown('<div class="card"><h3>📋 Mükellef Listesi</h3></div>', unsafe_allow_html=True)
        st.dataframe(load_mukellef(), use_container_width=True)

    with t2:
        st.markdown('<div class="card"><h3>👥 Personel Yönetimi</h3><div class="hint">Yeni personel ekleyin veya numarasını güncelleyin.</div>', unsafe_allow_html=True)

        dfp = load_personel()

        a, b, c = st.columns([2, 2, 1])
        with a:
            p_ad = st.text_input("Personel")
        with b:
            p_tel = st.text_input("Telefon")
        with c:
            p_aktif = st.selectbox("Aktif", ["Evet","Hayır"], index=0)

        if st.button("➕ Kaydet", type="primary", use_container_width=True):
            tel = normalize_phone(p_tel)
            if not str(p_ad).strip():
                st.error("Personel adı boş olamaz.")
            elif not tel:
                st.error("Telefon geçersiz.")
            else:
                m = dfp["Personel"].astype(str).str.strip().str.lower() == str(p_ad).strip().lower()
                if m.any():
                    idx = dfp[m].index[0]
                    dfp.loc[idx, "Telefon"] = tel
                    dfp.loc[idx, "Aktif"] = p_aktif
                else:
                    dfp = pd.concat([dfp, pd.DataFrame([{"Personel":p_ad.strip(), "Telefon":tel, "Aktif":p_aktif}])], ignore_index=True)
                save_excel_safe(dfp, PERSONEL_DOSYASI)
                st.success("Kaydedildi.")
                st.rerun()

        st.dataframe(dfp, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with t3:
        st.markdown('<div class="card"><h3>🗂️ İşler (Ham)</h3></div>', unsafe_allow_html=True)
        st.dataframe(load_isler(), use_container_width=True)
