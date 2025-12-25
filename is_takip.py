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
# 0) UYGULAMA AYARLARI VE GÜVENLİK
# =========================================================
st.set_page_config(
    page_title="Halil Akça Takip Sistemi",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

try:
    ID_INSTANCE = st.secrets.get("ID_INSTANCE", "YOUR_INSTANCE_ID")
    API_TOKEN   = st.secrets.get("API_TOKEN", "YOUR_API_TOKEN")
except FileNotFoundError:
    ID_INSTANCE = "YOUR_INSTANCE_ID"
    API_TOKEN = "YOUR_API_TOKEN"

SABIT_IHBAR_NO = "905351041616"

# Dosya Yolları
KALICI_EXCEL_YOLU     = "mukellef_db_kalici.xlsx"
PERSONEL_DOSYASI      = "personel_db.xlsx"
YAPILACAK_IS_DOSYASI  = "yapilacak_isler.xlsx"
YAPILACAK_IS_BACKUP   = "yapilacak_isler.xlsx.bak"
MUKELLEF_NOT_DOSYASI  = "mukellef_notlari.xlsx"

# Kolon Şemaları
YAPILACAK_IS_COLS = [
    "IsID","Tip","Durum","Öncelik","Dönem","Mükellef","VKN",
    "Konu","Açıklama","SonTarih","Sorumlu","SorumluTel","MükellefTelAll",
    "Not","OlusturmaZamani","GuncellemeZamani","KapanisZamani"
]

# =========================================================
# 1) CSS TEMA
# =========================================================
st.markdown("""
<style>
:root{ --bg:#f4f8ff; --card:#ffffff; --line:#e6eefc; --blue:#0b5ed7; --text:#0f172a; --muted:#64748b; 
--s-open-bg: rgba(11,94,215,0.07); --s-open-b: rgba(11,94,215,0.35); --s-open-strip: #0b5ed7;
--s-prog-bg: rgba(245,158,11,0.10); --s-prog-b: rgba(245,158,11,0.45); --s-prog-strip:#f59e0b;
--s-done-bg: rgba(22,163,74,0.10); --s-done-b: rgba(22,163,74,0.45); --s-done-strip:#16a34a;
--s-cancel-bg: rgba(148,163,184,0.12); --s-cancel-b: rgba(148,163,184,0.55); --s-cancel-strip:#94a3b8; }
.stApp{ background: var(--bg); font-family: "Segoe UI", system-ui, Arial; }
[data-testid="stSidebar"]{ background: linear-gradient(180deg,#ffffff 0%,#f7fbff 100%); border-right:1px solid var(--line); }
.ha-topbar{ background: linear-gradient(90deg, #0b5ed7 0%, #1d4ed8 55%, #38bdf8 120%); color:#fff; padding:18px 20px; border-radius:18px; margin-bottom: 12px; }
.ha-title{ font-size:22px; font-weight:900; margin:0; } .ha-sub{ margin:6px 0 0 0; font-size:12px; opacity:0.92; }
.card{ background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 14px; box-shadow: 0 10px 26px rgba(15,23,42,0.08); margin-bottom: 12px; }
.card h3{ margin:0 0 8px 0; font-size:15px; font-weight:900; color: var(--text); }
.badge{ display:inline-flex; align-items:center; gap:6px; padding: 4px 10px; font-size: 11px; border-radius: 999px; border: 1px solid var(--line); background:#f8fbff; color: var(--muted); }
.badge-blue{ border-color: rgba(11,94,215,0.25); background: rgba(11,94,215,0.06); color: var(--blue); }
.kpis{ display:flex; gap:10px; flex-wrap:wrap; } .kpi{ flex: 1 1 160px; background: rgba(11,94,215,0.06); border: 1px solid rgba(11,94,215,0.16); border-radius: 16px; padding: 12px; }
.kpi .v{ font-size:18px; font-weight:900; color: var(--blue); } .kpi .l{ font-size:12px; color: var(--muted); margin-top:2px; }
.task-row{ border-radius: 16px; border: 1px solid var(--line); box-shadow: 0 8px 18px rgba(15,23,42,0.06); margin-bottom: 10px; overflow:hidden; }
.task-row .wrap{ padding: 12px 12px; } .task-row .top{ display:flex; align-items:flex-start; justify-content:space-between; gap:10px; flex-wrap:wrap; }
.pill{ display:inline-flex; align-items:center; gap:6px; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--line); font-size:11px; color: var(--muted); background:#fff; }
.task-open { background: var(--s-open-bg); border-color: var(--s-open-b); } .task-open .strip{ background: var(--s-open-strip); height:6px; }
.task-prog { background: var(--s-prog-bg); border-color: var(--s-prog-b); } .task-prog .strip{ background: var(--s-prog-strip); height:6px; }
.task-done { background: var(--s-done-bg); border-color: var(--s-done-b); } .task-done .strip{ background: var(--s-done-strip); height:6px; }
.task-cancel { background: var(--s-cancel-bg); border-color: var(--s-cancel-b); } .task-cancel .strip{ background: var(--s-cancel-strip); height:6px; }
.stButton>button{ border-radius: 12px !important; } .stTextInput input, .stTextArea textarea{ border-radius: 12px !important; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# 2) YARDIMCI FONKSİYONLAR
# =========================================================
def now_str() -> str: return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def safe_html_text(x) -> str: return escape(str(x or "")).replace("\n", "<br>")

def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if len(p) == 10: p = "90" + p
    if len(p) == 11 and p.startswith("0"): p = "9" + p
    return p if len(p) >= 11 else ""

def parse_phones(cell_text: str) -> list:
    t = str(cell_text or "").strip()
    if not t: return []
    candidates = re.findall(r"(?:\+?90\s*)?(?:0\s*)?5\d{2}\s*\d{3}\s*\d{2}\s*\d{2}", t)
    out = []
    for c in candidates:
        n = normalize_phone(c)
        if n and n not in out: out.append(n)
    if not out:
        digits = re.findall(r"\d+", t)
        joined = "".join(digits)
        c2 = re.findall(r"(?:90)?5\d{9}", joined)
        for c in c2:
            n = normalize_phone(c)
            if n and n not in out: out.append(n)
    return out

def whatsapp_gonder(numara: str, mesaj: str) -> bool:
    if not numara or ID_INSTANCE == "YOUR_INSTANCE_ID": return False
    numara = normalize_phone(numara)
    if not numara: return False
    target = f"{SABIT_IHBAR_NO}@c.us" if numara == "SABIT" else f"{numara}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    try:
        requests.post(url, json={"chatId": target, "message": mesaj}, timeout=12)
        return True
    except: return False

def whatsapp_gonder_coklu(numaralar: list, mesaj: str) -> int:
    ok = 0
    for n in (numaralar or []):
        if whatsapp_gonder(n, mesaj): ok += 1
        time.sleep(0.25)
    return ok

def yeni_is_id() -> str:
    return "IS-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()

# VCF PARSER (Basit Rehber Okuyucu)
def parse_vcf_content(content: str) -> list:
    contacts = []
    # VCard'ları ayır
    cards = content.split("BEGIN:VCARD")
    for card in cards:
        if not card.strip(): continue
        # İsim bul (FN:...)
        name_match = re.search(r"FN:(.*)", card)
        # Tel bul (TEL...:...)
        tel_match = re.search(r"TEL.*:(.*)", card)
        
        if name_match and tel_match:
            name = name_match.group(1).strip()
            tel = normalize_phone(tel_match.group(1).strip())
            if name and tel:
                contacts.append({"Personel": name, "Telefon": tel, "Aktif": "Evet"})
    return contacts

# =========================================================
# 3) VERİTABANI YÖNETİMİ (KAYIP ÖNLEME SİSTEMİ)
# =========================================================
def safe_backup(src: str, dst: str):
    try:
        if os.path.exists(src): shutil.copy2(src, dst)
    except: pass

def load_excel_safe(path, cols=None) -> pd.DataFrame:
    if not os.path.exists(path): return pd.DataFrame(columns=cols or []).fillna("")
    try:
        df = pd.read_excel(path, dtype=str).fillna("")
        if cols:
            for c in cols:
                if c not in df.columns: df[c] = ""
            df = df[cols]
        return df.fillna("")
    except: return pd.DataFrame(columns=cols or []).fillna("")

def save_excel_safe(df: pd.DataFrame, path: str, backup_path: str = None):
    df = df.fillna("")
    if backup_path: safe_backup(path, backup_path)
    df.to_excel(path, index=False)

# --- GLOBAL OTOMATİK YÜKLEME (DATA PERSISTENCE) ---
if "mukellef_db" not in st.session_state:
    st.session_state["mukellef_db"] = load_excel_safe(KALICI_EXCEL_YOLU, ["A_UNVAN","B_TC","C_VKN","D_TEL","D_TEL_ALL"])

if "personel_db" not in st.session_state:
    st.session_state["personel_db"] = load_excel_safe(PERSONEL_DOSYASI, ["Personel","Telefon","Aktif"])

if "yapilacak_isler_db" not in st.session_state:
    st.session_state["yapilacak_isler_db"] = load_excel_safe(YAPILACAK_IS_DOSYASI, YAPILACAK_IS_COLS)

if "mukellef_not_db" not in st.session_state:
    st.session_state["mukellef_not_db"] = load_excel_safe(MUKELLEF_NOT_DOSYASI, ["VKN","Mükellef","Notlar","GuncellemeZamani"])

# --- VERİ GÜNCELLEME FONKSİYONLARI ---
def data_append_is(row: dict):
    df = st.session_state["yapilacak_isler_db"]
    if not df.empty and (df["IsID"].astype(str) == str(row.get("IsID",""))).any(): return
    df2 = pd.concat([df, pd.DataFrame([row], columns=YAPILACAK_IS_COLS)], ignore_index=True)
    st.session_state["yapilacak_isler_db"] = df2
    save_excel_safe(df2, YAPILACAK_IS_DOSYASI, YAPILACAK_IS_BACKUP)

def data_update_is(isid: str, updates: dict):
    df = st.session_state["yapilacak_isler_db"]
    if df.empty: return
    m = df["IsID"].astype(str) == str(isid)
    if not m.any(): return
    idx = df[m].index[0]
    for k, v in updates.items():
        if k in df.columns: df.loc[idx, k] = v
    st.session_state["yapilacak_isler_db"] = df
    save_excel_safe(df, YAPILACAK_IS_DOSYASI, YAPILACAK_IS_BACKUP)

def msg_personel(r: dict) -> str:
    return (f"✅ *İŞ ATAMASI*\n🆔 {r.get('IsID','')}\n📅 Son: {r.get('SonTarih','')}\n"
            f"🏢 {r.get('Mükellef','')}\n📝 {r.get('Konu','')}\n🧾 {r.get('Açıklama','')}")

def msg_mukellef(r: dict) -> str:
    return (f"Merhaba,\nİşlem/talep:\n📌 {r.get('Konu','')}\n📝 {r.get('Açıklama','')}\n📅 Son Tarih: {r.get('SonTarih','')}")

# =========================================================
# 4) MENÜ YAPISI
# =========================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=64)
    st.header("HALİL AKÇA")
    secim = st.radio(
        "MENÜ",
        ["1. Excel Listesi Yükle", "2. Yapılacak İşler", "3. KDV Analiz Modülü", "4. Profesyonel Mesaj", "5. Tasdik Robotu"],
        index=1
    )
    st.caption("Veri Korumalı Sistem v2.1")

# ------------------------------------------------------------------
# SAYFA 1: EXCEL YÜKLE
# ------------------------------------------------------------------
if secim == "1. Excel Listesi Yükle":
    st.markdown("""<div class="ha-topbar"><p class="ha-title">Veri Yükleme</p><p class="ha-sub">Mükellef veritabanı</p></div>""", unsafe_allow_html=True)
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
            st.success(f"✅ Kaydedildi. Toplam: {len(df)}")
            st.dataframe(df.head(40), use_container_width=True)
        except Exception as e: st.error(f"Hata: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------
# SAYFA 2: YAPILACAK İŞLER
# ------------------------------------------------------------------
elif secim == "2. Yapılacak İşler":
    st.markdown("""<div class="ha-topbar"><p class="ha-title">İş Takip Paneli</p><p class="ha-sub">Yönetim ve Atama Merkezi</p></div>""", unsafe_allow_html=True)
    
    dfm = st.session_state["mukellef_db"]
    dfp = st.session_state["personel_db"]
    dfy = st.session_state["yapilacak_isler_db"]

    if dfm.empty:
        st.warning("Mükellef listesi boş.")
        st.stop()

    # DASHBOARD
    st.markdown('<div class="card">', unsafe_allow_html=True)
    kp1, kp2, kp3, kp4 = st.columns(4)
    kp1.markdown(f'<div class="kpi"><div class="v">{len(dfy)}</div><div class="l">Toplam</div></div>', unsafe_allow_html=True)
    kp2.markdown(f'<div class="kpi"><div class="v">{(dfy["Durum"]=="AÇIK").sum()}</div><div class="l">Açık</div></div>', unsafe_allow_html=True)
    kp3.markdown(f'<div class="kpi"><div class="v">{(dfy["Durum"]=="İNCELEMEDE").sum()}</div><div class="l">İncelemede</div></div>', unsafe_allow_html=True)
    kp4.markdown(f'<div class="kpi"><div class="v">{(dfy["Durum"]=="KAPANDI").sum()}</div><div class="l">Kapandı</div></div>', unsafe_allow_html=True)
    
    st.markdown("<br><h5>📊 Analiz</h5>", unsafe_allow_html=True)
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        if not dfy.empty: st.bar_chart(dfy["Durum"].value_counts(), color="#0b5ed7")
    with col_g2:
        if not dfy.empty:
            aktif = dfy[dfy["Durum"].isin(["AÇIK","İNCELEMEDE"])]
            if not aktif.empty: st.dataframe(aktif["Sorumlu"].value_counts().reset_index(name="İş Sayısı"), use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # --- TOPLU İŞ OLUŞTURMA ---
    with st.expander("🔄 Toplu İş Oluşturucu (Çoklu Seçim)", expanded=False):
        t1, t2, t3 = st.columns(3)
        with t1: t_konu = st.text_input("Konu", value="2025/Ocak KDV", key="t_konu")
        with t2: t_donem = st.text_input("Dönem", value=datetime.now().strftime("%B %Y"), key="t_donem")
        with t3: t_son = st.date_input("Son Tarih", key="t_son")
        t_ack = st.text_area("Açıklama", "Dönemsel işlem.", height=68, key="t_ack")
        
        tum_liste = dfm["A_UNVAN"].astype(str).tolist()
        if st.checkbox("Tümünü Listele", key="chk_all"): def_sel = tum_liste
        else: def_sel = []
        
        sel_muk = st.multiselect("Mükellefler", options=tum_liste, default=def_sel, key="ms_muk")
        st.write(f"Seçili: {len(sel_muk)}")
        
        if st.button("🚀 Oluştur", type="primary", use_container_width=True):
            if not sel_muk or not t_konu: st.error("Eksik bilgi.")
            else:
                bar = st.progress(0)
                c = 0
                for i, m in enumerate(sel_muk):
                    rec = dfm[dfm["A_UNVAN"].astype(str)==str(m)].iloc[0]
                    row = {
                        "IsID": yeni_is_id(), "Tip": "OTOMATİK", "Durum": "AÇIK", "Öncelik": "Orta",
                        "Dönem": str(t_donem), "Mükellef": str(m),
                        "VKN": str(rec.get("C_VKN","") or rec.get("B_TC","")),
                        "Konu": str(t_konu), "Açıklama": str(t_ack), "SonTarih": str(t_son),
                        "Sorumlu": "", "SorumluTel": "", "MükellefTelAll": str(rec.get("D_TEL_ALL","")),
                        "Not": "", "OlusturmaZamani": now_str(), "GuncellemeZamani": now_str(), "KapanisZamani": ""
                    }
                    data_append_is(row)
                    c+=1
                    bar.progress((i+1)/len(sel_muk))
                st.success(f"{c} iş oluşturuldu.")
                time.sleep(1)
                st.rerun()

    # --- TOPLU KAPATMA ---
    with st.expander("⚡ Toplu İşlem (Kapatma/Devretme)", expanded=False):
        fc1, fc2 = st.columns(2)
        with fc1: f_dur = st.multiselect("Durum Filtre", ["AÇIK","İNCELEMEDE","KAPANDI"], default=["AÇIK","İNCELEMEDE"])
        with fc2: f_per = st.selectbox("Personel Filtre", ["(Hepsi)"] + dfp["Personel"].astype(str).tolist())
        
        sub_df = dfy.copy()
        if f_dur: sub_df = sub_df[sub_df["Durum"].isin(f_dur)]
        if f_per != "(Hepsi)": sub_df = sub_df[sub_df["Sorumlu"]==f_per]
        
        if not sub_df.empty:
            sub_df["Görünüm"] = sub_df["Mükellef"] + " | " + sub_df["Konu"]
            sel_ids = st.multiselect("İş Seçin", options=sub_df["IsID"].tolist(), format_func=lambda x: sub_df[sub_df["IsID"]==x]["Görünüm"].values[0])
            if sel_ids:
                ac1, ac2 = st.columns(2)
                with ac1: new_st = st.selectbox("Yeni Durum", ["(Değişme)","KAPANDI","İNCELEMEDE","AÇIK"])
                with ac2: new_res = st.selectbox("Yeni Sorumlu", ["(Değişme)"] + dfp["Personel"].astype(str).tolist())
                
                if st.button("⚡ Uygula", type="primary"):
                    bar = st.progress(0)
                    for i, sid in enumerate(sel_ids):
                        ups = {}
                        log = []
                        if new_st != "(Değişme)":
                            ups["Durum"] = new_st
                            if new_st=="KAPANDI": ups["KapanisZamani"] = now_str()
                            log.append(f"Durum->{new_st}")
                        if new_res != "(Değişme)":
                            ups["Sorumlu"] = new_res
                            pr = dfp[dfp["Personel"]==new_res]
                            ups["SorumluTel"] = normalize_phone(pr.iloc[0]["Telefon"]) if not pr.empty else ""
                            log.append(f"Sor->{new_res}")
                        
                        if ups:
                            ups["GuncellemeZamani"] = now_str()
                            old_n = dfy[dfy["IsID"]==sid].iloc[0]["Not"]
                            ups["Not"] = str(old_n) + f" | [Toplu: {', '.join(log)}]"
                            data_update_is(sid, ups)
                        bar.progress((i+1)/len(sel_ids))
                    st.success("Güncellendi.")
                    time.sleep(1)
                    st.rerun()

    # TEKİL İŞLEMLER
    col_l, col_r = st.columns([1.25, 1.0], gap="large")
    with col_l:
        st.markdown('<div class="card"><h3>➕ Tekil İş</h3>', unsafe_allow_html=True)
        s_muk = st.selectbox("Mükellef", dfm["A_UNVAN"].astype(str).tolist(), key="s_muk")
        s_rec = dfm[dfm["A_UNVAN"].astype(str)==str(s_muk)].iloc[0]
        s_vkn = str(s_rec.get("C_VKN","") or s_rec.get("B_TC",""))
        s_tel = str(s_rec.get("D_TEL_ALL",""))
        
        st.markdown(f'<span class="badge badge-blue">VKN: {s_vkn}</span>', unsafe_allow_html=True)
        s_konu = st.text_input("Konu", key="s_konu")
        s_ack = st.text_area("Açıklama", height=100, key="s_ack")
        c1, c2, c3 = st.columns(3)
        with c1: s_don = st.text_input("Dönem", key="s_don")
        with c2: s_onc = st.selectbox("Öncelik", ["Orta","Yüksek","Düşük"], key="s_onc")
        with c3: s_tar = st.date_input("Son Tarih", key="s_tar")
        
        s_per = st.selectbox("Sorumlu", ["(Yok)"] + dfp[dfp["Aktif"]=="Evet"]["Personel"].astype(str).tolist(), key="s_per")
        s_wa = st.checkbox("WhatsApp Gönder", value=True)
        
        if st.button("✅ Kaydet", type="primary", use_container_width=True):
            if not s_konu: st.error("Konu giriniz.")
            else:
                s_ptel = ""
                if s_per != "(Yok)":
                    pr = dfp[dfp["Personel"]==s_per]
                    if not pr.empty: s_ptel = normalize_phone(pr.iloc[0]["Telefon"])
                
                row = {
                    "IsID": yeni_is_id(), "Tip": "MANUEL", "Durum": "AÇIK", "Öncelik": s_onc,
                    "Dönem": str(s_don), "Mükellef": str(s_muk), "VKN": s_vkn,
                    "Konu": str(s_konu), "Açıklama": str(s_ack), "SonTarih": str(s_tar),
                    "Sorumlu": "" if s_per=="(Yok)" else s_per, "SorumluTel": s_ptel,
                    "MükellefTelAll": s_tel, "Not": "", 
                    "OlusturmaZamani": now_str(), "GuncellemeZamani": now_str(), "KapanisZamani": ""
                }
                data_append_is(row)
                if s_wa and s_ptel: whatsapp_gonder(s_ptel, msg_personel(row))
                st.success("Kaydedildi.")
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with col_r:
        st.markdown('<div class="card"><h3>🗒️ Notlar</h3>', unsafe_allow_html=True)
        dfn = st.session_state["mukellef_not_db"]
        old_n = ""
        hit = dfn[dfn["VKN"].astype(str)==str(s_vkn)]
        if not hit.empty: old_n = str(hit.iloc[0]["Notlar"])
        new_n = st.text_area("Özel Not", value=old_n, height=220, key="new_n")
        
        if st.button("💾 Notu Güncelle", use_container_width=True):
            dfn2 = dfn.copy()
            m = dfn2["VKN"].astype(str) == str(s_vkn)
            if m.any():
                idx = dfn2[m].index[0]
                dfn2.loc[idx, "Notlar"] = new_n.strip()
                dfn2.loc[idx, "GuncellemeZamani"] = now_str()
            else:
                dfn2 = pd.concat([dfn2, pd.DataFrame([{"VKN":s_vkn,"Mükellef":str(s_muk),"Notlar":new_n.strip(),"GuncellemeZamani":now_str()}])], ignore_index=True)
            st.session_state["mukellef_not_db"] = dfn2
            save_excel_safe(dfn2, MUKELLEF_NOT_DOSYASI)
            st.success("Not kaydedildi.")
        st.markdown("</div>", unsafe_allow_html=True)

    # LİSTELEME
    st.markdown('<div class="card"><h3>📌 Liste</h3>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns([1,1,1,2])
    with c1: lf_dur = st.selectbox("Durum", ["(Tümü)","AÇIK","İNCELEMEDE","KAPANDI"], key="lf_dur")
    with c2: lf_per = st.selectbox("Personel", ["(Tümü)"] + dfp["Personel"].tolist(), key="lf_per")
    with c3: lf_tar = st.selectbox("Tarih", ["(Tümü)","Gecikenler"], key="lf_tar")
    with c4: lf_ara = st.text_input("Ara", key="lf_ara")
    
    view = dfy.copy()
    if lf_dur != "(Tümü)": view = view[view["Durum"]==lf_dur]
    if lf_per != "(Tümü)": view = view[view["Sorumlu"]==lf_per]
    if lf_ara: 
        q = lf_ara.lower()
        view = view[view["Mükellef"].str.lower().str.contains(q, na=False) | view["Konu"].str.lower().str.contains(q, na=False)]
    
    today = pd.to_datetime(date.today())
    view["_dt"] = pd.to_datetime(view["SonTarih"], errors="coerce")
    view["_gc"] = (view["_dt"] < today) & (view["Durum"].isin(["AÇIK","İNCELEMEDE"]))
    if lf_tar == "Gecikenler": view = view[view["_gc"]==True]
    view = view.sort_values(by=["_gc","_dt"], ascending=[False, True])

    for _, r in view.drop(columns=["_dt","_gc"]).iterrows():
        st_cls = "task-open"
        if r["Durum"]=="KAPANDI": st_cls = "task-done"
        elif r["Durum"]=="İNCELEMEDE": st_cls = "task-prog"
        elif r["Durum"]=="İPTAL": st_cls = "task-cancel"
        
        pill_g = "<span class='pill'>⚠️ GECİKMİŞ</span>" if (pd.to_datetime(r["SonTarih"], errors="coerce") < today and r["Durum"] in ["AÇIK","İNCELEMEDE"]) else ""
        
        html = f"""<div class="task-row {st_cls}"><div class="strip"></div><div class="wrap"><div class="top">
        <div><div class="title">{safe_html_text(r["Mükellef"])} — {safe_html_text(r["Konu"])}</div>
        <div class="sub">VKN: {r["VKN"]} · Dönem: {r["Dönem"]} · ID: {r["IsID"]}</div></div>
        <div><span class="badge badge-blue">{r["Durum"]}</span></div></div>
        <div class="meta"><span class="pill">Sorumlu: {r["Sorumlu"]}</span><span class="pill">Son: {r["SonTarih"]}</span>{pill_g}</div>
        <div class="sub" style="margin-top:8px">Açıklama: {safe_html_text(r["Açıklama"])}</div></div></div>"""
        st.markdown(html, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if not dfy.empty:
        st.markdown('<div class="card"><h3>🛠️ Detay Düzenle</h3>', unsafe_allow_html=True)
        uid = st.selectbox("ID Seç", dfy["IsID"].tolist(), key="u_id")
        urow = dfy[dfy["IsID"]==uid].iloc[0]
        c1, c2 = st.columns(2)
        with c1: 
            u_dur = st.selectbox("Durum", ["AÇIK","İNCELEMEDE","KAPANDI","İPTAL"], index=["AÇIK","İNCELEMEDE","KAPANDI","İPTAL"].index(urow["Durum"]), key="u_dur")
            u_tar = st.text_input("Tarih", urow["SonTarih"], key="u_tar")
        with c2:
            u_not = st.text_area("Not Ekle", urow["Not"], height=100, key="u_not")
            if st.button("Kaydet ve Güncelle", key="u_btn"):
                ups = {"Durum":u_dur, "SonTarih":u_tar, "Not":u_not, "GuncellemeZamani":now_str()}
                if u_dur=="KAPANDI": ups["KapanisZamani"] = now_str()
                data_update_is(uid, ups)
                st.success("Güncellendi.")
                time.sleep(1)
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------
# SAYFA 3: KDV ANALİZ
# ------------------------------------------------------------------
elif secim == "3. KDV Analiz Modülü":
    st.markdown("""<div class="ha-topbar"><p class="ha-title">KDV Analiz</p><p class="ha-sub">Vergi Kontrol Modülü</p></div>""", unsafe_allow_html=True)
    st.info("KDV beyannamelerini analiz etmek için burası kullanılacak.")

# ------------------------------------------------------------------
# SAYFA 4: MESAJ
# ------------------------------------------------------------------
elif secim == "4. Profesyonel Mesaj":
    st.markdown("""<div class="ha-topbar"><p class="ha-title">WhatsApp Mesaj</p></div>""", unsafe_allow_html=True)
    dfm = st.session_state["mukellef_db"]
    if dfm.empty: st.warning("Liste boş."); st.stop()
    
    st.markdown('<div class="card"><h3>📤 Gönder</h3>', unsafe_allow_html=True)
    k = st.selectbox("Kişi", dfm["A_UNVAN"].tolist())
    r = dfm[dfm["A_UNVAN"]==k].iloc[0]
    ts = parse_phones(r["D_TEL_ALL"])
    st.write(f"Numaralar: {ts}")
    m = st.text_area("Mesaj")
    all_n = st.checkbox("Tüm numaralara", True)
    if st.button("Gönder", type="primary"):
        if all_n: c = whatsapp_gonder_coklu(ts, m)
        else: c = 1 if ts and whatsapp_gonder(ts[0], m) else 0
        st.success(f"{c} gönderildi.")
    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------
# SAYFA 5: TASDİK ROBOTU (Personel Yönetimi Dahil)
# ------------------------------------------------------------------
elif secim == "5. Tasdik Robotu":
    st.markdown("""<div class="ha-topbar"><p class="ha-title">Veri Kayıtları</p></div>""", unsafe_allow_html=True)
    t1,t2,t3 = st.tabs(["Mükellef","Personel","İşler"])
    with t1: st.dataframe(st.session_state["mukellef_db"], use_container_width=True)
    
    with t2:
        st.markdown("### 👥 Personel Yönetimi")
        
        # VCF YÜKLEME MODÜLÜ
        st.info("Telefondan Kişileri Almak İçin: Rehber > Ayarlar > Kişileri Dışa Aktar > VCF dosyasını buraya yükle.")
        vcf_up = st.file_uploader("Rehber Dosyası (VCF) Yükle", type=["vcf"])
        
        d = st.session_state["personel_db"]
        
        if vcf_up:
            try:
                content = vcf_up.read().decode("utf-8")
                new_contacts = parse_vcf_content(content)
                if new_contacts:
                    new_df = pd.DataFrame(new_contacts)
                    d = pd.concat([d, new_df], ignore_index=True).drop_duplicates(subset=["Telefon"])
                    st.session_state["personel_db"] = d
                    save_excel_safe(d, PERSONEL_DOSYASI)
                    st.success(f"✅ {len(new_contacts)} kişi rehberden eklendi!")
                    st.rerun()
            except Exception as e: st.error(f"Dosya okunamadı: {e}")

        # MANUEL EKLEME
        st.markdown("---")
        c1,c2,c3 = st.columns([2,2,1])
        with c1: pa = st.text_input("Ad")
        with c2: pt = st.text_input("Tel")
        with c3: pk = st.selectbox("Aktif",["Evet","Hayır"])
        if st.button("Manuel Ekle"):
            d = pd.concat([d, pd.DataFrame([{"Personel":pa,"Telefon":normalize_phone(pt),"Aktif":pk}])], ignore_index=True)
            st.session_state["personel_db"] = d
            save_excel_safe(d, PERSONEL_DOSYASI)
            st.rerun()
            
        st.dataframe(d, use_container_width=True)
        
    with t3: st.dataframe(st.session_state["yapilacak_isler_db"], use_container_width=True)
