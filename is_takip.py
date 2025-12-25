import os

KALICI_EXCEL_YOLU = "mukellef_db_kalici.xlsx"

def kalici_db_yukle():
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

# Uygulama açılışında otomatik yükle (bir kez)
if st.session_state.get("mukellef_db") is None:
    kalici_db_yukle()
