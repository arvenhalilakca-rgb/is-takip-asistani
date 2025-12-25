import os
import re
import time
import uuid
import shutil
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, date
from html import escape

# =========================================================
# 0) UYGULAMA AYARLARI
# =========================================================
st.set_page_config(
    page_title="Halil Akça Takip Sistemi",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Secrets hatası almamak için güvenli erişim
try:
    ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
    API_TOKEN   = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
except FileNotFoundError:
    ID_INSTANCE = "YOUR_INSTANCE_ID"
    API_TOKEN = "YOUR_API_TOKEN"

SABIT_IHBAR_NO = "905351041616"

# Kalıcı dosyalar
KALICI_EXCEL_YOLU     = "mukellef_db_kalici.xlsx"
PERSONEL_DOSYASI      = "personel_db.xlsx"
YAPILACAK_IS_DOSYASI  = "yapilacak_isler.xlsx"
YAPILACAK_IS_BACKUP   = "yapilacak_isler.xlsx.bak"
MUKELLEF_NOT_DOSYASI  = "mukellef_notlari.xlsx"

# Yapılacak iş kolonları (stabil şema)
YAPILACAK_IS_COLS = [
    "IsID","Tip","Durum","Öncelik","Dönem","Mükellef","VKN",
    "Konu","Açıklama","SonTarih","Sorumlu","SorumluTel","MükellefTelAll",
    "Not","OlusturmaZamani","GuncellemeZamani","KapanisZamani"
]

# =========================================================
# 1) TEMA / CSS (Sakin + Profesyonel, LIGHT THEME)
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

.task-row{ border-radius: 16px; border: 1px solid var(--line); box-shadow: 0 8px 18px rgba(15,23,42,0.06); margin-bottom: 10px; overflow:hidden; }
.task-row .wrap{ padding: 12px 12px; }
.task-row .top{ display:flex; align-items:flex-start; justify-content:space-between; gap:10px; flex-wrap:wrap; }
.task-row .title{ font-weight:900; color: var(--text); font-size:14px; }
.task-row .sub{ color: var(--muted); font-size:12px; margin-top:2px; }
.task-row .meta{ display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }
.pill{ display:inline-flex; align-items:center; gap:6px; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--line); font-size:11px; color: var(--muted); background:#fff; }
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
# 2) GENEL YARDIMCILAR
# =========================================================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def safe_html_text(x) -> str:
    s = escape(str(x or ""))
    return s.replace("\n", "<br>")

def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if len(p) == 10: p = "90" + p
    if len(p) == 11 and p.startswith("0"): p = "9" + p
    return p if len(p) >= 11 else ""

def parse_phones(cell_text: str) -> list:
    t = str(cell_text or "")
    if not t.strip(): return []
    candidates = re.findall(r"(?:\+?90\s*)?(?:0\s*)?5\d{2}\s*\d{3}\s*\d{2}\s*\d{2}", t)
    out = []
    for c in candidates:
        n = normalize_phone(c)
        if n and n not in out: out.append(n)
    if not out:
        digits = re.findall(r"\d+", t)
        joined = "".join(digits)
        candidates2 = re.findall(r"(?:90)?5\d{9}", joined)
        for c in candidates2:
            n = normalize_phone(c)
            if n and n not in out: out.append(n)
    return out

def whatsapp_gonder(numara: str, mesaj: str) -> bool:
    if not numara or ID_INSTANCE == "YOUR_INSTANCE_ID":
        # st.warning(f"WhatsApp API Ayarlı Değil. Mesaj (Simülasyon): {mesaj[:20]}...")
        return False
    numara = normalize_phone(numara)
    if not numara: return False
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
        if whatsapp_gonder(n, mesaj): ok += 1
        time.sleep(0.25)
    return ok

def yeni_is_id() -> str:
    return "IS-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()

# =========================================================
# 3) KALICI OKU/YAZ
# =========================================================
def safe_backup(src: str, dst: str):
    try:
        if os.path.exists(src): shutil.copy2(src, dst)
    except Exception: pass

def load_excel_safe(path, cols=None) -> pd.DataFrame:
    if not os.path.exists(path): return pd.DataFrame(columns=cols or []).fillna("")
    try:
        df = pd.read_excel(path, dtype=str).fillna("")
        if cols:
            for c in cols:
                if c not in df.columns: df[c] = ""
            df = df[cols]
        return df.fillna("")
    except Exception: return pd.DataFrame(columns=cols or []).fillna("")

def save_excel_safe(df: pd.DataFrame, path: str, backup_path: str = None):
    df = df.fillna("")
    if backup_path: safe_backup(path, backup_path)
    df.to_excel(path, index=False)

def load_mukellef() -> pd.DataFrame:
    cols = ["A_UNVAN","B_TC","C_VKN","D_TEL","D_TEL_ALL"]
    df = load_excel_safe(KALICI_EXCEL_YOLU, cols=cols)
    if not df.empty and (df["D_TEL_ALL"].astype(str).str.strip() == "").all():
        df["D_TEL_ALL"] = df["D_TEL"].apply(lambda x: " | ".join(parse_phones(x)))
    if not df.empty and (df["D_TEL"].astype(str).str.strip() == "").all():
        df["D_TEL"] = df["D_TEL_ALL"].apply(lambda x: (parse_phones(x)[0] if parse_phones(x) else ""))
    return df.fillna("")

def load_personel() -> pd.DataFrame:
    cols = ["Personel","Telefon","Aktif"]
    df = load_excel_safe(PERSONEL_DOSYASI, cols=cols)
    if not df.empty and (df["Aktif"].astype(str).str.strip() == "").all():
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
    if not df.empty and (df["IsID"].astype(str) == str(row.get("IsID",""))).any(): return
    df2 = pd.concat([df, pd.DataFrame([row], columns=YAPILACAK_IS_COLS)], ignore_index=True)
    save_excel_safe(df2, YAPILACAK_IS_DOSYASI, backup_path=YAPILACAK_IS_BACKUP)

def update_yapilacak_is(isid: str, updates: dict):
    df = load_yapilacak_isler()
    if df.empty: return
    m = df["IsID"].astype(str) == str(isid)
    if not m.any(): return
    idx = df[m].index[0]
    for k, v in (updates or {}).items():
        if k in df.columns: df.loc[idx, k] = v
    save_excel_safe(df, YAPILACAK_IS_DOSYASI, backup_path=YAPILACAK_IS_BACKUP)

# =========================================================
# 4) MESAJ ŞABLONLARI
# =========================================================
def msg_yapilacak_is_personel(r: dict) -> str:
    return (f"✅ *YAPILACAK İŞ ATAMASI*\n🆔 {r.get('IsID','')}\n📅 {r.get('SonTarih','')}\n"
            f"━━━━━━━━━━━━━━━━\n🏢 {r.get('Mükellef','')}\n📝 {r.get('Konu','')}\n🧾 {r.get('Açıklama','')}")

def msg_yapilacak_is_mukellef(r: dict) -> str:
    return (f"Merhaba,\nTarafınızla ilgili bir işlem/talep bulunmaktadır.\n📌 Konu: {r.get('Konu','')}\n"
            f"📝 Açıklama: {r.get('Açıklama','')}\n📅 Son Tarih: {r.get('SonTarih','')}")

# =========================================================
# 5) MENÜ VE SAYFA
# =========================================================
if "mukellef_db" not in st.session_state or st.session_state["mukellef_db"] is None:
    st.session_state["mukellef_db"] = load_mukellef()

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=64)
    st.header("HALİL AKÇA")
    secim = st.radio(
        "MENÜ",
        ["1. Excel Listesi Yükle", "2. Yapılacak İşler", "3. KDV Analiz Modülü", "4. Profesyonel Mesaj", "5. Tasdik Robotu"],
        index=1
    )
    st.caption("Takip ve Yönetim Paneli")

# =========================================================
# MODÜLLER
# =========================================================
if secim == "1. Excel Listesi Yükle":
    st.markdown("""<div class="ha-topbar"><p class="ha-title">Halil Akça Takip Sistemi</p>
    <p class="ha-sub">Mükellef veritabanı yükleme ve kalıcı kayıt</p></div>""", unsafe_allow_html=True)

    st.markdown('<div class="card"><h3>📂 Mükellef Veritabanı</h3>', unsafe_allow_html=True)
    up = st.file_uploader("Excel seçin", type=["xlsx", "xls"])
    if up:
        try:
            raw = pd.read_excel(up, dtype=str).fillna("")
            cols = {c.strip().lower(): c for c in raw.columns}
            unvan_col = cols.get("unvan", raw.columns[0])
            tckn_col  = cols.get("tckn",  raw.columns[1] if len(raw.columns)>1 else raw.columns[0])
            vkn_col   = cols.get("vkn",   raw.columns[2] if len(raw.columns)>2 else raw.columns[0])
            tel_col   = cols.get("telefon", raw.columns[3] if len(raw.columns)>3 else raw.columns[0])

            df = pd.DataFrame()
            df["A_UNVAN"] = raw[unvan_col].astype(str).str.strip()
            df["B_TC"]    = raw[tckn_col].astype(str).str.strip()
            df["C_VKN"]   = raw[vkn_col].astype(str).str.strip()
            df["D_TEL_ALL"] = raw[tel_col].apply(lambda x: " | ".join(parse_phones(x)))
            df["D_TEL"] = df["D_TEL_ALL"].apply(lambda x: (parse_phones(x)[0] if parse_phones(x) else ""))

            st.session_state["mukellef_db"] = df.fillna("")
            save_excel_safe(df, KALICI_EXCEL_YOLU)
            st.success(f"✅ Kaydedildi. Toplam kayıt: {len(df)}")
            st.dataframe(df.head(40), use_container_width=True)
        except Exception as e: st.error(f"Hata: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

# ----------------------------------------------
# 2. YAPILACAK İŞLER (AYRI SAYFA)
# ----------------------------------------------
elif secim == "2. Yapılacak İşler":
    st.markdown("""<div class="ha-topbar"><p class="ha-title">Yapılacak İş Takip Paneli</p>
    <p class="ha-sub">İş Atama · Takip · Yönetim Dashboard</p></div>""", unsafe_allow_html=True)

    dfm = st.session_state["mukellef_db"]
    if dfm is None or dfm.empty:
        st.warning("Önce '1. Excel Listesi Yükle' menüsünden mükellef listesini yükleyin.")
        st.stop()

    dfp = load_personel()
    dfy = load_yapilacak_isler()

    # KPI & DASHBOARD
    st.markdown('<div class="card">', unsafe_allow_html=True)
    kp1, kp2, kp3, kp4 = st.columns(4)
    kp1.markdown(f'<div class="kpi"><div class="v">{len(dfy)}</div><div class="l">Toplam İş</div></div>', unsafe_allow_html=True)
    kp2.markdown(f'<div class="kpi"><div class="v">{(dfy["Durum"]=="AÇIK").sum()}</div><div class="l">Açık</div></div>', unsafe_allow_html=True)
    kp3.markdown(f'<div class="kpi"><div class="v">{(dfy["Durum"]=="İNCELEMEDE").sum()}</div><div class="l">İncelemede</div></div>', unsafe_allow_html=True)
    kp4.markdown(f'<div class="kpi"><div class="v">{(dfy["Durum"]=="KAPANDI").sum()}</div><div class="l">Kapandı</div></div>', unsafe_allow_html=True)
    
    # GRAFİKSEL ANALİZ
    st.markdown("<br><h5>📊 Durum Analizi</h5>", unsafe_allow_html=True)
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        durum_counts = dfy["Durum"].value_counts().reset_index()
        durum_counts.columns = ["Durum", "Adet"]
        st.bar_chart(durum_counts, x="Durum", y="Adet", color="Durum") 
    with col_g2:
        if not dfy.empty:
            aktif_isler = dfy[dfy["Durum"].isin(["AÇIK", "İNCELEMEDE"])]
            if not aktif_isler.empty:
                yuk_counts = aktif_isler["Sorumlu"].value_counts().reset_index()
                yuk_counts.columns = ["Personel", "Aktif İş Sayısı"]
                st.dataframe(yuk_counts, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # --- MODÜL 1: TOPLU İŞ OLUŞTURUCU ---
    with st.expander("🔄 Toplu / Dönemsel İş Oluşturucu (Çoklu Seçim)", expanded=False):
        st.info("Buradan seçeceğiniz birden fazla mükellefe aynı anda iş atayabilirsiniz.")
        t_col1, t_col2, t_col3 = st.columns(3)
        with t_col1: toplu_konu = st.text_input("İş Konusu", value="2025/Ocak KDV Tahakkuku", key="t_konu")
        with t_col2: toplu_donem = st.text_input("Dönem", value=datetime.now().strftime("%B %Y"), key="t_donem")
        with t_col3: toplu_son = st.date_input("Son Tarih", key="t_son")
        toplu_aciklama = st.text_area("Açıklama", "Dönemsel beyanname ve tahakkuk işlemleri.", height=68, key="t_ack")
        
        tum_liste = dfm["A_UNVAN"].astype(str).tolist()
        tumunu_sec = st.checkbox("Tüm Listeyi Getir", key="chk_all")
        default_secim = tum_liste if tumunu_sec else []
        
        secilen_mukellefler = st.multiselect("Mükellefleri Seçiniz (İstediklerinizi ekleyip çıkarabilirsiniz)", options=tum_liste, default=default_secim, key="multi_select_muk")
        
        st.markdown(f"**Seçili Mükellef Sayısı:** {len(secilen_mukellefler)}")
        
        if st.button("🚀 Seçili Kişilere İşleri Oluştur", type="primary", use_container_width=True):
            if not secilen_mukellefler or not toplu_konu:
                st.error("Mükellef veya konu seçilmedi.")
            else:
                count = 0
                bar = st.progress(0)
                total = len(secilen_mukellefler)
                for i, m_isim in enumerate(secilen_mukellefler):
                    m_rec = dfm[dfm["A_UNVAN"].astype(str) == str(m_isim)].iloc[0]
                    row_new = {
                        "IsID": yeni_is_id(),
                        "Tip": "OTOMATİK", "Durum": "AÇIK", "Öncelik": "Orta",
                        "Dönem": str(toplu_donem), "Mükellef": str(m_isim),
                        "VKN": str(m_rec.get("C_VKN","") or m_rec.get("B_TC","")),
                        "Konu": str(toplu_konu), "Açıklama": str(toplu_aciklama),
                        "SonTarih": str(toplu_son), "Sorumlu": "", "SorumluTel": "",
                        "MükellefTelAll": str(m_rec.get("D_TEL_ALL","")), "Not": "",
                        "OlusturmaZamani": now_str(), "GuncellemeZamani": now_str(), "KapanisZamani": ""
                    }
                    append_yapilacak_is(row_new)
                    count += 1
                    bar.progress((i + 1) / total)
                    time.sleep(0.02)
                st.success(f"✅ {count} adet iş oluşturuldu.")
                time.sleep(1)
                st.rerun()

    # --- MODÜL 2: TOPLU İŞLEM ---
    with st.expander("⚡ Toplu İşlem Menüsü (Çoklu Kapatma / Devretme)", expanded=False):
        st.warning("Dikkat: Burada yapacağınız değişiklikler seçilen TÜM işlere uygulanır.")
        filtre_col1, filtre_col2 = st.columns(2)
        with filtre_col1:
            t_filter_durum = st.multiselect("Şu Durumdaki İşleri Listele:", ["AÇIK", "İNCELEMEDE", "KAPANDI"], default=["AÇIK", "İNCELEMEDE"])
        with filtre_col2:
            t_filter_personel = st.selectbox("Personel Filtresi", ["(Hepsi)"] + dfp["Personel"].astype(str).tolist())

        df_islem = dfy.copy()
        if t_filter_durum: df_islem = df_islem[df_islem["Durum"].isin(t_filter_durum)]
        if t_filter_personel != "(Hepsi)": df_islem = df_islem[df_islem["Sorumlu"] == t_filter_personel]

        if df_islem.empty: st.info("Kriterlere uygun iş bulunamadı.")
        else:
            df_islem["Görünüm"] = df_islem["Mükellef"] + " | " + df_islem["Konu"] + " (" + df_islem["SonTarih"] + ")"
            secilen_is_idleri = st.multiselect(
                f"İşlem Yapılacak Kayıtları Seçin (Toplam {len(df_islem)} kayıt listelendi)",
                options=df_islem["IsID"].tolist(),
                format_func=lambda x: df_islem[df_islem["IsID"]==x]["Görünüm"].values[0],
                key="batch_select_box"
            )
            st.markdown(f"**Seçili Kayıt Sayısı:** {len(secilen_is_idleri)}")

            if secilen_is_idleri:
                st.markdown("---")
                act_col1, act_col2 = st.columns(2)
                with act_col1: toplu_yeni_durum = st.selectbox("Yeni Durum Ne Olsun?", ["(Değiştirme)", "KAPANDI", "İNCELEMEDE", "İPTAL", "AÇIK"])
                with act_col2: 
                    personel_listesi = ["(Değiştirme)"] + dfp[dfp["Aktif"]=="Evet"]["Personel"].tolist()
                    toplu_yeni_sorumlu = st.selectbox("Yeni Sorumlu Kim Olsun?", personel_listesi)

                if st.button("⚡ SEÇİLENLERİ UYGULA", type="primary", use_container_width=True):
                    progress_text = "İşlemler uygulanıyor..."
                    my_bar = st.progress(0, text=progress_text)
                    for idx, target_id in enumerate(secilen_is_idleri):
                        updates = {}
                        update_log = []
                        if toplu_yeni_durum != "(Değiştirme)":
                            updates["Durum"] = toplu_yeni_durum
                            if toplu_yeni_durum == "KAPANDI": updates["KapanisZamani"] = now_str()
                            update_log.append(f"Durum -> {toplu_yeni_durum}")
                        if toplu_yeni_sorumlu != "(Değiştirme)":
                            updates["Sorumlu"] = toplu_yeni_sorumlu
                            yeni_tel = ""
                            p_row = dfp[dfp["Personel"] == toplu_yeni_sorumlu]
                            if not p_row.empty: yeni_tel = normalize_phone(p_row.iloc[0]["Telefon"])
                            updates["SorumluTel"] = yeni_tel
                            update_log.append(f"Sorumlu -> {toplu_yeni_sorumlu}")

                        if updates:
                            updates["GuncellemeZamani"] = now_str()
                            curr_note = dfy[dfy["IsID"] == target_id].iloc[0]["Not"]
                            log_msg = f" | [Toplu İşlem: {', '.join(update_log)} - {now_str()}]"
                            updates["Not"] = str(curr_note) + log_msg
                            update_yapilacak_is(target_id, updates)
                        my_bar.progress((idx + 1) / len(secilen_is_idleri))
                    st.success(f"✅ {len(secilen_is_idleri)} adet kayıt güncellendi!")
                    time.sleep(1)
                    st.rerun()

    # TEKİL İŞ & NOTLAR
    col_left, col_right = st.columns([1.25, 1.0], gap="large")
    with col_left:
        st.markdown('<div class="card"><h3>➕ Tekil İş Oluştur</h3>', unsafe_allow_html=True)
        mukellef_list = dfm["A_UNVAN"].astype(str).tolist()
        mukellef = st.selectbox("Mükellef", mukellef_list, key="is_mukellef")
        rec = dfm[dfm["A_UNVAN"].astype(str) == str(mukellef)].iloc[0].to_dict()
        vkn = str(rec.get("C_VKN","") or rec.get("B_TC","")).strip()
        tel_all = str(rec.get("D_TEL_ALL","")).strip()

        st.markdown(f'<span class="badge badge-blue">VKN: {safe_html_text(vkn)}</span> <span class="badge">Tel: {safe_html_text(tel_all)}</span>', unsafe_allow_html=True)
        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

        konu = st.text_input("Konu", key="is_konu")
        aciklama = st.text_area("Açıklama", height=105, key="is_aciklama")
        cA, cB, cC = st.columns([1.1, 1.0, 1.0])
        with cA: donem = st.text_input("Dönem", key="is_donem")
        with cB: oncelik = st.selectbox("Öncelik", ["Yüksek","Orta","Düşük"], index=1, key="is_onc")
        with cC: son_tarih = st.date_input("Son Tarih", value=date.today(), key="is_son")
        
        aktif = dfp[dfp["Aktif"].astype(str).str.lower().isin(["evet","yes","true","1"])].copy()
        sorumlu = st.selectbox("Sorumlu", ["(Atama Yok)"] + aktif["Personel"].astype(str).tolist(), key="is_sorumlu")

        wa_p = st.checkbox("Personeli bilgilendir", value=True, key="wa_p")

        if st.button("✅ KAYDET", type="primary", use_container_width=True, key="is_kaydet"):
            if not konu or not aciklama: st.error("Konu/Açıklama eksik.")
            else:
                sor_tel = ""
                if sorumlu != "(Atama Yok)":
                    rr = aktif[aktif["Personel"].astype(str) == str(sorumlu)]
                    if not rr.empty: sor_tel = normalize_phone(rr.iloc[0].get("Telefon",""))
                
                row = {
                    "IsID": yeni_is_id(), "Tip": "MANUEL", "Durum": "AÇIK", "Öncelik": oncelik,
                    "Dönem": str(donem), "Mükellef": str(mukellef), "VKN": vkn,
                    "Konu": str(konu), "Açıklama": str(aciklama), "SonTarih": str(son_tarih),
                    "Sorumlu": "" if sorumlu == "(Atama Yok)" else str(sorumlu),
                    "SorumluTel": sor_tel, "MükellefTelAll": tel_all, "Not": "",
                    "OlusturmaZamani": now_str(), "GuncellemeZamani": now_str(), "KapanisZamani": ""
                }
                append_yapilacak_is(row)
                if wa_p and sor_tel: whatsapp_gonder(sor_tel, msg_yapilacak_is_personel(row))
                st.success("Kaydedildi.")
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="card"><h3>🗒️ Mükellef Notları</h3>', unsafe_allow_html=True)
        dfn = load_mukellef_not()
        old_note = ""
        hit = dfn[dfn["VKN"].astype(str) == str(vkn)]
        if not hit.empty: old_note = str(hit.iloc[0].get("Notlar",""))
        muk_not = st.text_area("Genel Not", value=old_note, height=240, key="muk_not")

        if st.button("💾 NOTU KAYDET", use_container_width=True, key="not_kaydet"):
            dfn2 = dfn.copy()
            m = dfn2["VKN"].astype(str) == str(vkn)
            if m.any():
                idx = dfn2[m].index[0]
                dfn2.loc[idx, "Mükellef"] = str(mukellef)
                dfn2.loc[idx, "Notlar"] = str(muk_not).strip()
                dfn2.loc[idx, "GuncellemeZamani"] = now_str()
            else:
                dfn2 = pd.concat([dfn2, pd.DataFrame([{"VKN":str(vkn),"Mükellef":str(mukellef),"Notlar":str(muk_not).strip(),"GuncellemeZamani":now_str()}])], ignore_index=True)
            save_excel_safe(dfn2, MUKELLEF_NOT_DOSYASI)
            st.success("Not kaydedildi.")
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # LİSTELEME
    st.markdown('<div class="card"><h3>📌 Yapılacak İşler</h3>', unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.2, 2.4])
    with f1: fdurum = st.selectbox("Durum", ["(Tümü)", "AÇIK", "İNCELEMEDE", "KAPANDI", "İPTAL"], key="f_durum")
    with f2: fonc = st.selectbox("Öncelik", ["(Tümü)","Yüksek","Orta","Düşük"], key="f_onc")
    with f3: fson = st.selectbox("Tarih", ["(Hepsi)", "Gecikenler"], key="f_son")
    with f4: fara = st.text_input("Ara", placeholder="Mükellef / Konu", key="f_ara")

    view = dfy.copy()
    if fdurum != "(Tümü)": view = view[view["Durum"].astype(str) == fdurum]
    if fonc != "(Tümü)": view = view[view["Öncelik"].astype(str) == fonc]
    if str(fara).strip():
        q = str(fara).strip().lower()
        view = view[view["Mükellef"].astype(str).str.lower().str.contains(q, na=False) | view["Konu"].astype(str).str.lower().str.contains(q, na=False)]

    def to_dt(x):
        try: return pd.to_datetime(str(x), errors="coerce")
        except: return pd.NaT
    view["_son"] = view["SonTarih"].apply(to_dt)
    today_dt = pd.to_datetime(date.today())
    view["_gecik"] = (view["_son"].notna()) & (view["_son"] < today_dt) & (view["Durum"].astype(str).isin(["AÇIK","İNCELEMEDE"]))
    if fson == "Gecikenler": view = view[view["_gecik"] == True]
    view = view.sort_values(by=["_gecik","_son"], ascending=[False, True])

    def status_class(s: str) -> str:
        s = (s or "").strip().upper()
        if s == "KAPANDI": return "task-row task-done"
        if s == "İNCELEMEDE": return "task-row task-prog"
        if s == "İPTAL": return "task-row task-cancel"
        return "task-row task-open"

    if view.empty: st.info("Kayıt bulunamadı.")
    else:
        for _, r in view.drop(columns=["_son","_gecik"], errors="ignore").iterrows():
            durum, oncelik, son_t = str(r.get("Durum","")), str(r.get("Öncelik","")), str(r.get("SonTarih",""))
            gecik_pill = "<span class='pill'><strong>GECİKMİŞ</strong></span>" if (pd.to_datetime(son_t,errors='coerce') < today_dt and durum in ["AÇIK","İNCELEMEDE"]) else ""
            
            # HTML SOLA YASLI - DÜZELTİLMİŞ HAL
            html = f"""<div class="{status_class(durum)}"><div class="strip"></div><div class="wrap"><div class="top">
<div><div class="title">{safe_html_text(r.get("Mükellef",""))} — {safe_html_text(r.get("Konu",""))}</div>
<div class="sub">VKN: {safe_html_text(r.get("VKN",""))} · Dönem: {safe_html_text(r.get("Dönem",""))} · ID: {r.get("IsID","")}</div></div>
<div><span class="badge badge-blue">{safe_html_text(durum)}</span></div></div>
<div class="meta"><span class="pill"><strong>Öncelik:</strong> {safe_html_text(oncelik)}</span>
<span class="pill"><strong>Son Tarih:</strong> {safe_html_text(son_t)}</span>
<span class="pill"><strong>Sorumlu:</strong> {safe_html_text(r.get("Sorumlu",""))}</span>{gecik_pill}</div>
<div class="sub" style="margin-top:8px;"><strong>Açıklama:</strong> {safe_html_text(r.get("Açıklama",""))}</div>
<div class="sub"><strong>Not:</strong> {safe_html_text(r.get("Not",""))}</div></div></div>"""
            st.markdown(html, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # GÜNCELLEME
    st.markdown('<div class="card"><h3>🛠️ İş Güncelle</h3>', unsafe_allow_html=True)
    dfy_all = load_yapilacak_isler()
    if not dfy_all.empty:
        sec_id = st.selectbox("Kayıt Seç (IsID)", dfy_all["IsID"].astype(str).tolist(), key="sec_is")
        row = dfy_all[dfy_all["IsID"].astype(str) == str(sec_id)].iloc[0].to_dict()
        a, b = st.columns([1.2, 1.0], gap="large")
        with a:
            new_status = st.selectbox("Durum", ["AÇIK","İNCELEMEDE","KAPANDI","İPTAL"], index=0, key="upd_durum")
            new_due = st.text_input("Son Tarih", value=str(row.get("SonTarih","")), key="upd_son")
            new_note = st.text_area("Not", value=str(row.get("Not","")), height=110, key="upd_not")
        with b:
            target = st.selectbox("Mesaj Gönder", ["Gönderme", "Sorumlu Personele", "Mükellefe"], key="upd_target")
            all_m = st.checkbox("Mükellefe TÜM numara", value=True, key="upd_allm")

        if st.button("💾 GÜNCELLE", type="primary", use_container_width=True, key="upd_btn"):
            updates = {"Durum": new_status, "SonTarih": str(new_due).strip(), "Not": str(new_note).strip(), "GuncellemeZamani": now_str()}
            if new_status == "KAPANDI": updates["KapanisZamani"] = now_str()
            update_yapilacak_is(sec_id, updates)
            
            cur = load_yapilacak_isler()[load_yapilacak_isler()["IsID"]==str(sec_id)].iloc[0].to_dict()
            if target == "Sorumlu Personele":
                tel = normalize_phone(cur.get("SorumluTel",""))
                if tel: whatsapp_gonder(tel, msg_yapilacak_is_personel(cur))
            elif target == "Mükellefe":
                tels = parse_phones(cur.get("MükellefTelAll",""))
                if tels:
                    if all_m: whatsapp_gonder_coklu(tels, msg_yapilacak_is_mukellef(cur))
                    else: whatsapp_gonder(tels[0], msg_yapilacak_is_mukellef(cur))
            st.success("Güncellendi.")
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# ----------------------------------------------
# 3. KDV ANALİZ MODÜLÜ (AYRI SAYFA)
# ----------------------------------------------
elif secim == "3. KDV Analiz Modülü":
    st.markdown("""<div class="ha-topbar"><p class="ha-title">KDV Analiz Modülü</p>
    <p class="ha-sub">Vergi Analizi · Kontrol</p></div>""", unsafe_allow_html=True)
    
    dfm = st.session_state["mukellef_db"]
    if dfm is None or dfm.empty:
        st.warning("Önce '1. Excel Listesi Yükle' menüsünden mükellef listesini yükleyin.")
        st.stop()
        
    st.markdown('<div class="card"><h3>🧾 KDV Analiz</h3><div class="hint">Bu sayfa KDV analiz kodlarını bekliyor.</div>', unsafe_allow_html=True)
    st.info("KDV Analiz Modülü için gerekli kodları buraya entegre edebilirsiniz.")
    st.markdown("</div>", unsafe_allow_html=True)

elif secim == "4. Profesyonel Mesaj":
    st.markdown('<div class="ha-topbar"><p class="ha-title">Profesyonel Mesaj</p></div>', unsafe_allow_html=True)
    dfm = load_mukellef()
    st.markdown('<div class="card"><h3>📤 Mesaj Gönder</h3>', unsafe_allow_html=True)
    kisi = st.selectbox("Mükellef", dfm["A_UNVAN"].astype(str).tolist(), key="pm_kisi")
    if kisi:
        rec = dfm[dfm["A_UNVAN"].astype(str) == str(kisi)].iloc[0].to_dict()
        tels = parse_phones(rec.get("D_TEL_ALL",""))
        st.write(f"Telefonlar: {tels}")
        msg = st.text_area("Mesaj", key="pm_msg")
        to_all = st.checkbox("Tüm numaralara", value=True, key="pm_all")
        if st.button("Gönder", type="primary", key="pm_send"):
            if to_all: st.success(f"{whatsapp_gonder_coklu(tels, msg)} gönderildi.")
            else: st.success("Gönderildi." if whatsapp_gonder(tels[0], msg) else "Hata")
    st.markdown("</div>", unsafe_allow_html=True)

elif secim == "5. Tasdik Robotu":
    st.markdown('<div class="ha-topbar"><p class="ha-title">Kayıtlar</p></div>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["📋 Mükellefler", "👥 Personel", "🗂️ Yapılacak İşler"])
    with t1: st.dataframe(load_mukellef(), use_container_width=True)
    with t2:
        dfp = load_personel()
        c1, c2, c3 = st.columns([2,2,1])
        with c1: p_ad = st.text_input("Personel", key="p_ad")
        with c2: p_tel = st.text_input("Telefon", key="p_tel")
        with c3: p_aktif = st.selectbox("Aktif", ["Evet","Hayır"], key="p_aktif")
        if st.button("➕ Kaydet", key="p_kaydet"):
            if p_ad:
                dfp = pd.concat([dfp, pd.DataFrame([{"Personel":p_ad,"Telefon":normalize_phone(p_tel),"Aktif":p_aktif}])], ignore_index=True)
                save_excel_safe(dfp, PERSONEL_DOSYASI)
                st.rerun()
        st.dataframe(dfp, use_container_width=True)
    with t3: st.dataframe(load_yapilacak_isler(), use_container_width=True)
