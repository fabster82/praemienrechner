import io
from typing import List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Prämien-Rechner Fußball", page_icon="⚽", layout="wide")

# ---------- Helpers ----------
def normalize_tiers(df_tiers: pd.DataFrame) -> pd.DataFrame:
    df = df_tiers.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    rename_map = {
        "von": "von_platz",
        "bis": "bis_platz",
        "€/punkt": "eur_pro_punkt",
        "euro pro punkt": "eur_pro_punkt",
        "eur_pro_punkt": "eur_pro_punkt",
        "von_platz": "von_platz",
        "bis_platz": "bis_platz",
    }
    df.rename(columns=rename_map, inplace=True)
    for col in ["von_platz", "bis_platz"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    df["eur_pro_punkt"] = pd.to_numeric(df.get("eur_pro_punkt", np.nan), errors="coerce")
    df = df.dropna(subset=["von_platz", "bis_platz", "eur_pro_punkt"]).reset_index(drop=True)
    df = df[df["von_platz"] <= df["bis_platz"]]
    return df.sort_values(["von_platz", "bis_platz"]).reset_index(drop=True)

def normalize_promos(df_promos: pd.DataFrame) -> pd.DataFrame:
    df = df_promos.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    rename_map = {
        "von": "von_platz",
        "bis": "bis_platz",
        "bonus": "bonus_eur",
        "aufstiegsbonus": "bonus_eur",
        "bonus_eur": "bonus_eur",
    }
    df.rename(columns=rename_map, inplace=True)
    for col in ["von_platz", "bis_platz"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    df["bonus_eur"] = pd.to_numeric(df.get("bonus_eur", np.nan), errors="coerce")
    df = df.dropna(subset=["von_platz", "bis_platz", "bonus_eur"]).reset_index(drop=True)
    df = df[df["von_platz"] <= df["bis_platz"]]
    return df.sort_values(["von_platz", "bis_platz"]).reset_index(drop=True)

def find_rate_for_place(place: int, tiers: pd.DataFrame, base_rate: float, match_mode: str = "first") -> float:
    """€/Punkt für Platz aus Stufen. Fallback: base_rate.
    match_mode:
      - 'first': erste passende Zeile (Top-Down)
      - 'max_range': bei Überschneidungen die engste Spanne (bis-von minimal)
    """
    matches = tiers[(tiers["von_platz"] <= place) & (tiers["bis_platz"] >= place)]
    if matches.empty:
        return base_rate
    if match_mode == "max_range":
        matches = matches.assign(width=matches["bis_platz"] - matches["von_platz"])
        return float(matches.sort_values(["width", "von_platz"]).iloc[0]["eur_pro_punkt"])
    return float(matches.iloc[0]["eur_pro_punkt"])

def find_bonus_for_place(place: int, promos: pd.DataFrame, mode: str = "first") -> float:
    """Bonus für Platz aus Bonus-Bereichen.
    mode:
      - 'first': nur erster Treffer
      - 'max':   größter Bonus über alle Treffer
      - 'sum':   Summe aller Treffer
    """
    matches = promos[(promos["von_platz"] <= place) & (promos["bis_platz"] >= place)]
    if matches.empty:
        return 0.0
    vals = matches["bonus_eur"].astype(float).tolist()
    if mode == "first":
        return float(vals[0])
    if mode == "max":
        return float(max(vals))
    return float(sum(vals))

def compute_scenarios(df_scen: pd.DataFrame, tiers: pd.DataFrame, base_rate: float,
                      promos: pd.DataFrame, promo_mode: str, tier_mode: str) -> pd.DataFrame:
    df = df_scen.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    rename_map = {"platz": "platz", "punkte": "punkte"}
    df.rename(columns=rename_map, inplace=True)
    df["platz"] = pd.to_numeric(df.get("platz", np.nan), errors="coerce").astype("Int64")
    df["punkte"] = pd.to_numeric(df.get("punkte", np.nan), errors="coerce")
    df = df.dropna(subset=["platz", "punkte"]).reset_index(drop=True)

    rates, bonuses, totals = [], [], []
    for _, row in df.iterrows():
        place = int(row["platz"])
        pts = float(row["punkte"])
        rate = find_rate_for_place(place, tiers, base_rate, match_mode=tier_mode)
        bonus = find_bonus_for_place(place, promos, mode=promo_mode)
        total = pts * rate + bonus
        rates.append(rate); bonuses.append(bonus); totals.append(total)

    df_out = df.copy()
    df_out["€/Punkt"] = rates
    df_out["Aufstiegsbonus (€)"] = bonuses
    df_out["Gesamt-Prämie (€)"] = totals
    return df_out

def df_to_csv_download(df: pd.DataFrame, filename: str) -> bytes:
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")

# ---------- Deine Standardwerte ----------
DEFAULT_BASE_RATE = 50.0
DEFAULT_TIERS = pd.DataFrame({
    # ab Platz 3 -> 100 €/Punkt (3–6), ab Platz 7 -> 75 €/Punkt (7–999)
    "von_platz": [3, 7],
    "bis_platz": [6, 999],
    "eur_pro_punkt": [100, 75],
})
DEFAULT_PROMOS = pd.DataFrame({
    # Aufstiegsprämie 500 € für Platz 1–2
    "von_platz": [1],
    "bis_platz": [2],
    "bonus_eur": [500],
})
DEFAULT_SCENARIOS = pd.DataFrame({
    "Platz":  [1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14, 15, 16],
    "Punkte": [73, 69, 67, 59, 51, 46, 35, 35, 32, 32, 31, 26, 23, 19, 11, 11],
})

# ---------- Defaults in Session ----------
if "tiers" not in st.session_state:
    st.session_state.tiers = DEFAULT_TIERS.copy()
if "promos" not in st.session_state:
    st.session_state.promos = DEFAULT_PROMOS.copy()
if "base_rate" not in st.session_state:
    st.session_state.base_rate = DEFAULT_BASE_RATE
if "scenarios" not in st.session_state:
    st.session_state.scenarios = DEFAULT_SCENARIOS.copy()

# ---------- UI ----------
st.title("⚽ Prämien-Rechner Fußball")
st.caption("Platz-basierte €/Punkt-Stufen + Aufstiegsbonus. Ergebnisse je Szenario (Platz, Punkte).")

with st.sidebar:
    st.header("⚙️ Variablen")
    if st.button("🔄 Standardwerte laden"):
        st.session_state.tiers = DEFAULT_TIERS.copy()
        st.session_state.promos = DEFAULT_PROMOS.copy()
        st.session_state.base_rate = DEFAULT_BASE_RATE
        st.session_state.scenarios = DEFAULT_SCENARIOS.copy()
        st.success("Standardwerte gesetzt.")

    st.session_state.base_rate = st.number_input(
        "Basis-€ pro Punkt (Rest)", min_value=0.0, step=5.0, value=float(st.session_state.base_rate)
    )
    tier_mode = st.selectbox(
        "Tier-Match bei Überlappungen",
        ["first", "max_range"],
        help="Wie bei überlappenden Platz-Bereichen entschieden wird."
    )
    promo_mode = st.selectbox(
        "Bonus-Modus",
        ["first", "max", "sum"],
        index=0,
        help="Wenn mehrere Bonus-Bereiche greifen."
    )
    st.markdown("---")
    st.write("📥 **Szenarien per CSV (optional)** – Spalten: `Platz;Punkte`")
    up = st.file_uploader("CSV hochladen", type=["csv"])
    if up:
        try:
            df_up = pd.read_csv(up, sep=None, engine="python")
            st.session_state.scenarios = df_up
            st.success("CSV geladen.")
        except Exception as e:
            st.error(f"CSV konnte nicht gelesen werden: {e}")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Stufen (Von/Bis → €/Punkt)")
    st.info("Nicht abgedeckte Plätze nutzen den Basis-Wert.")
    tiers_edit = st.data_editor(
        st.session_state.tiers,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "von_platz": st.column_config.NumberColumn("Von Platz", min_value=1, step=1),
            "bis_platz": st.column_config.NumberColumn("Bis Platz", min_value=1, step=1),
            "eur_pro_punkt": st.column_config.NumberColumn("€ pro Punkt", min_value=0.0, step=5.0, format="%.2f"),
        }
    )
with col2:
    st.subheader("🏆 Aufstiegsbonus (Von/Bis → Bonus €)")
    st.info("Du kannst auch mehrere Bereiche definieren (z. B. 1–2 und 1–3).")
    promos_edit = st.data_editor(
        st.session_state.promos,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "von_platz": st.column_config.NumberColumn("Von Platz", min_value=1, step=1),
            "bis_platz": st.column_config.NumberColumn("Bis Platz", min_value=1, step=1),
            "bonus_eur": st.column_config.NumberColumn("Bonus (€)", min_value=0.0, step=50.0, format="%.2f"),
        }
    )

st.session_state.tiers = normalize_tiers(tiers_edit)
st.session_state.promos = normalize_promos(promos_edit)

st.subheader("📝 Szenarien (Platz + Punkte)")
st.caption("Trage beliebige Kombinationen ein. Ergebnis wird unten berechnet.")
scen_edit = st.data_editor(
    st.session_state.scenarios,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Platz": st.column_config.NumberColumn("Platz", min_value=1, step=1),
        "Punkte": st.column_config.NumberColumn("Punkte", min_value=0.0, step=1.0, format="%.0f"),
    }
)
st.session_state.scenarios = scen_edit

# Validation warnings
warns = []
if not st.session_state.tiers.empty and (st.session_state.tiers["von_platz"] > st.session_state.tiers["bis_platz"]).any():
    warns.append("In **Stufen** ist mindestens eine Zeile mit `Von > Bis`.")
if not st.session_state.promos.empty and (st.session_state.promos["von_platz"] > st.session_state.promos["bis_platz"]).any():
    warns.append("In **Aufstiegsbonus** ist mindestens eine Zeile mit `Von > Bis`.")

for w in warns:
    st.warning(w)

st.markdown("---")
st.subheader("✅ Ergebnis")
result_df = compute_scenarios(
    st.session_state.scenarios,
    st.session_state.tiers,
    st.session_state.base_rate,
    st.session_state.promos,
    promo_mode=promo_mode,
    tier_mode=tier_mode,
)
st.dataframe(result_df, use_container_width=True)

# ---- Nur Ø €/Punkt als kleines KPI-Signal (die anderen beiden wurden entfernt) ----
if not result_df.empty:
    avg_rate = float(result_df["€/Punkt"].mean())
    st.metric("Ø €/Punkt", f"{avg_rate:,.2f}".replace(",", " ").replace(".", ","))
