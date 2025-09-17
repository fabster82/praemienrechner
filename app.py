import io
from typing import List, Tuple
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

# PDF (reines Python – läuft auf Streamlit Cloud)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

st.set_page_config(page_title="Prämien-Rechner Fußball", page_icon="⚽", layout="wide")

# ---------- Helpers ----------
def normalize_tiers(df_tiers: pd.DataFrame) -> pd.DataFrame:
    df = df_tiers.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    rename_map = {"von": "von_platz", "bis": "bis_platz", "€/punkt": "eur_pro_punkt",
                  "euro pro punkt": "eur_pro_punkt", "eur_pro_punkt": "eur_pro_punkt",
                  "von_platz": "von_platz", "bis_platz": "bis_platz"}
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
    rename_map = {"von": "von_platz", "bis": "bis_platz", "bonus": "bonus_eur",
                  "aufstiegsbonus": "bonus_eur", "bonus_eur": "bonus_eur"}
    df.rename(columns=rename_map, inplace=True)
    for col in ["von_platz", "bis_platz"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    df["bonus_eur"] = pd.to_numeric(df.get("bonus_eur", np.nan), errors="coerce")
    df = df.dropna(subset=["von_platz", "bis_platz", "bonus_eur"]).reset_index(drop=True)
    df = df[df["von_platz"] <= df["bis_platz"]]
    return df.sort_values(["von_platz", "bis_platz"]).reset_index(drop=True)

def find_rate_for_place(place: int, tiers: pd.DataFrame, base_rate: float, match_mode: str = "first") -> float:
    matches = tiers[(tiers["von_platz"] <= place) & (tiers["bis_platz"] >= place)]
    if matches.empty:
        return base_rate
    if match_mode == "max_range":
        matches = matches.assign(width=matches["bis_platz"] - matches["von_platz"])
        return float(matches.sort_values(["width", "von_platz"]).iloc[0]["eur_pro_punkt"])
    return float(matches.iloc[0]["eur_pro_punkt"])

def find_bonus_for_place(place: int, promos: pd.DataFrame, mode: str = "first") -> float:
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
    df.rename(columns={"platz": "platz", "punkte": "punkte"}, inplace=True)
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

    out = df.copy()
    out["€/Punkt"] = rates
    out["Aufstiegsbonus (€)"] = bonuses
    out["Gesamt-Prämie (€)"] = totals
    return out

def df_to_csv_download(df: pd.DataFrame, filename: str) -> bytes:
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")

# ---------- PDF ----------
def build_pdf_bytes(result_df: pd.DataFrame, tiers: pd.DataFrame, promos: pd.DataFrame, base_rate: float) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=24, leftMargin=24, topMargin=28, bottomMargin=28
    )
    styles = getSampleStyleSheet()
    story = []

    # Titel
    title = Paragraph("⚽ Prämien-Rechner – Auswertung", styles["Title"])
    ts = datetime.now().strftime("%d.%m.%Y %H:%M")
    subtitle = Paragraph(f"Stand: {ts}", styles["Normal"])
    story.extend([title, subtitle, Spacer(1, 10)])

    # Variablen
    story.append(Paragraph("<b>Variablen</b>", styles["Heading3"]))
    var_tbl = Table([
        ["Basis-€ pro Punkt (Rest)", f"{base_rate:,.2f}".replace(",", " ").replace(".", ",")],
    ], colWidths=[220, 140])
    var_tbl.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("BACKGROUND", (0,0), (0,0), colors.whitesmoke),
    ]))
    story.extend([var_tbl, Spacer(1, 8)])

    # Stufen
    story.append(Paragraph("<b>Stufen (€/Punkt)</b>", styles["Heading3"]))
    tiers_display = tiers.copy()
    tiers_display = tiers_display.rename(columns={"von_platz":"Von Platz","bis_platz":"Bis Platz","eur_pro_punkt":"€ pro Punkt"})
    tiers_data = [list(tiers_display.columns)] + [[int(r["Von Platz"]), int(r["Bis Platz"]), f'{float(r["€ pro Punkt"]):,.2f}'.replace(",", " ").replace(".", ",")] for _, r in tiers_display.iterrows()]
    if tiers_data:
        t_tbl = Table(tiers_data, colWidths=[80, 80, 120])
        t_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#F0F0F0")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.black),
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ]))
        story.append(t_tbl)
    story.append(Paragraph(f"Nicht abgedeckte Plätze: Basis {base_rate:,.2f} € / Punkt".replace(",", " ").replace(".", ","), styles["Italic"]))
    story.append(Spacer(1, 8))

    # Bonus
    story.append(Paragraph("<b>Aufstiegsbonus</b>", styles["Heading3"]))
    promos_display = promos.copy().rename(columns={"von_platz":"Von Platz","bis_platz":"Bis Platz","bonus_eur":"Bonus (€)"})
    promo_data = [list(promos_display.columns)] + [[int(r["Von Platz"]), int(r["Bis Platz"]), f'{float(r["Bonus (€)"]):,.2f}'.replace(",", " ").replace(".", ",")] for _, r in promos_display.iterrows()]
    if promo_data:
        p_tbl = Table(promo_data, colWidths=[80, 80, 120])
        p_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#F0F0F0")),
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ]))
        story.append(p_tbl)
    story.append(Spacer(1, 10))

    # Ergebnisse
    story.append(Paragraph("<b>Ergebnisse (Szenarien)</b>", styles["Heading3"]))
    if result_df is None or result_df.empty:
        story.append(Paragraph("Keine Szenarien vorhanden.", styles["Normal"]))
    else:
        df_disp = result_df.copy()
        # Formatierung
        for col in ["€/Punkt", "Aufstiegsbonus (€)", "Gesamt-Prämie (€)"]:
            df_disp[col] = df_disp[col].map(lambda x: f"{float(x):,.2f}".replace(",", " ").replace(".", ","))

        data = [list(["Platz","Punkte","€/Punkt","Aufstiegsbonus (€)","Gesamt-Prämie (€)"])]
        data += df_disp[["platz","punkte","€/Punkt","Aufstiegsbonus (€)","Gesamt-Prämie (€)"]].values.tolist()

        widths = [60, 60, 90, 120, 120]
        r_tbl = Table(data, colWidths=widths, repeatRows=1)
        r_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#DDEBF7")),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        story.append(r_tbl)

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes

# ---------- Standardwerte (deine aktuellen Defaults) ----------
# €/Punkt: 1–2 -> 75, 3–5 -> 50, 6–10 -> 35, Rest -> 25
# Bonus: Platz 1 -> 2500, Platz 2 -> 2000
DEFAULT_BASE_RATE = 25.0
DEFAULT_TIERS = pd.DataFrame({
    "von_platz":   [1, 3, 6],
    "bis_platz":   [2, 5, 10],
    "eur_pro_punkt":[75, 50, 35],
})
DEFAULT_PROMOS = pd.DataFrame({
    "von_platz": [1, 2],
    "bis_platz": [1, 2],
    "bonus_eur": [2500, 2000],
})
DEFAULT_SCENARIOS = pd.DataFrame({
    "Platz":  [1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14, 15, 16],
    "Punkte": [73, 69, 67, 59, 51, 46, 35, 35, 32, 32, 31, 26, 23, 19, 11, 11],
})

# ---------- Session-State ----------
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
    if st.button("🔄 Standardwerte laden", key="btn_defaults"):
        st.session_state.tiers = DEFAULT_TIERS.copy()
        st.session_state.promos = DEFAULT_PROMOS.copy()
        st.session_state.base_rate = DEFAULT_BASE_RATE
        st.session_state.scenarios = DEFAULT_SCENARIOS.copy()
        st.success("Standardwerte gesetzt.")

    st.session_state.base_rate = st.number_input(
        "Basis-€ pro Punkt (Rest)",
        min_value=0.0, step=1.0,
        value=float(st.session_state.base_rate),
        key="base_rate_input",
        help="Gilt für alle Plätze, die in den Stufen nicht abgedeckt sind (hier: >10)."
    )
    tier_mode = st.selectbox("Tier-Match bei Überlappungen", ["first", "max_range"], index=0, key="tier_mode")
    promo_mode = st.selectbox("Bonus-Modus", ["first", "max", "sum"], index=0, key="promo_mode")
    st.markdown("---")
    st.write("📥 **Szenarien per CSV (optional)** – Spalten: `Platz;Punkte`")
    up = st.file_uploader("CSV hochladen", type=["csv"], key="csv_upload")
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
    st.info("Nicht abgedeckte Plätze nutzen den Basis-Wert (Sidebar).")
    tiers_edit = st.data_editor(
        st.session_state.tiers,
        key="tiers_editor", num_rows="dynamic", use_container_width=True,
        column_config={
            "von_platz": st.column_config.NumberColumn("Von Platz", min_value=1, step=1),
            "bis_platz": st.column_config.NumberColumn("Bis Platz", min_value=1, step=1),
            "eur_pro_punkt": st.column_config.NumberColumn("€ pro Punkt", min_value=0.0, step=1.0, format="%.2f"),
        }
    )
with col2:
    st.subheader("🏆 Aufstiegsbonus (Von/Bis → Bonus €)")
    st.info("Für Platz-genau: Von = Bis (z. B. 1–1).")
    promos_edit = st.data_editor(
        st.session_state.promos,
        key="promos_editor", num_rows="dynamic", use_container_width=True,
        column_config={
            "von_platz": st.column_config.NumberColumn("Von Platz", min_value=1, step=1),
            "bis_platz": st.column_config.NumberColumn("Bis Platz", min_value=1, step=1),
            "bonus_eur": st.column_config.NumberColumn("Bonus (€)", min_value=0.0, step=50.0, format="%.2f"),
        }
    )

# Übernehmen & normalisieren
st.session_state.tiers = normalize_tiers(tiers_edit)
st.session_state.promos = normalize_promos(promos_edit)

st.subheader("📝 Szenarien (Platz + Punkte)")
st.caption("Trage beliebige Kombinationen ein. Ergebnis wird unten berechnet.")
scen_edit = st.data_editor(
    st.session_state.scenarios,
    key="scenarios_editor", num_rows="dynamic", use_container_width=True,
    column_config={
        "Platz": st.column_config.NumberColumn("Platz", min_value=1, step=1),
        "Punkte": st.column_config.NumberColumn("Punkte", min_value=0.0, step=1.0, format="%.0f"),
    }
)
st.session_state.scenarios = scen_edit

# Optionaler Aktualisieren-Button (erzwingt Re-Run)
force_update = st.button("🔁 Aktualisieren", type="primary", key="btn_update")
if force_update:
    st.rerun()

# Warnings
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
    promo_mode=st.session_state.get("promo_mode", "first"),
    tier_mode=st.session_state.get("tier_mode", "first"),
)
st.dataframe(result_df, use_container_width=True)

# Ø €/Punkt (leichtes KPI)
if not result_df.empty:
    avg_rate = float(result_df["€/Punkt"].mean())
    st.metric("Ø €/Punkt", f"{avg_rate:,.2f}".replace(",", " ").replace(".", ","))

# ---- PDF-Download ----
st.markdown("### 📄 Export")
pdf_bytes = build_pdf_bytes(
    result_df=result_df,
    tiers=st.session_state.tiers,
    promos=st.session_state.promos,
    base_rate=float(st.session_state.base_rate),
)
st.download_button(
    "PDF herunterladen",
    data=pdf_bytes,
    file_name="praemien_ergebnis.pdf",
    mime="application/pdf",
    use_container_width=False,
)
