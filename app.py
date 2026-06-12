import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="UniMatch Online",
    page_icon="🎓",
    layout="wide"
)

DB_TRIENNALI = "Database (3).xlsx"
DB_MAGISTRALI = "db giugno26.xlsx"
FOGLIO_MAGISTRALI = "requirements Online"


@st.cache_data
def carica_dati():
    triennali = pd.read_excel(DB_TRIENNALI)
    magistrali = pd.read_excel(DB_MAGISTRALI, sheet_name=FOGLIO_MAGISTRALI)
    return triennali, magistrali


def estrai_requisiti(row):
    requisiti = []

    for col in row.index:
        if str(col).startswith("Requisito SSD"):
            suffisso = str(col).replace("Requisito SSD", "")
            col_cfu = "Requisito CFU" + suffisso

            ssd = row.get(col)
            cfu = row.get(col_cfu)

            if pd.notna(ssd) and pd.notna(cfu):
                try:
                    requisiti.append((str(ssd).strip(), float(cfu)))
                except:
                    pass

    return requisiti


def calcola_match(profilo, requisiti):
    richiesti = sum(cfu for _, cfu in requisiti)
    coperti = 0
    mancanti = []

    for ssd, cfu_richiesti in requisiti:
        cfu_posseduti = profilo.get(ssd, 0)

        if cfu_posseduti >= cfu_richiesti:
            coperti += cfu_richiesti
        else:
            coperti += cfu_posseduti
            mancanti.append(f"{ssd}: {cfu_richiesti - cfu_posseduti:g} CFU")

    match = round((coperti / richiesti) * 100) if richiesti > 0 else 0

    return match, coperti, richiesti, mancanti


def crea_profilo_manual():
    st.subheader("Inserisci i tuoi CFU")

    profilo = {}

    testo = st.text_area(
        "Scrivi un SSD per riga nel formato SSD: CFU",
        placeholder="Esempio:\nM-PSI/01: 9\nM-PSI/05: 6\nSPS/07: 12"
    )

    for riga in testo.splitlines():
        if ":" in riga:
            ssd, cfu = riga.split(":", 1)
            try:
                profilo[ssd.strip()] = float(cfu.strip())
            except:
                pass

    return profilo


st.title("🎓 UniMatch Online")
st.write("Scopri quali magistrali online sono più compatibili con il tuo percorso.")

try:
    triennali, magistrali = carica_dati()
except Exception as e:
    st.error("Errore nel caricamento dei file Excel.")
    st.exception(e)
    st.stop()


modalita = st.radio(
    "Come vuoi inserire il tuo percorso?",
    ["Scelgo una laurea dal database", "Inserisco manualmente i miei CFU"]
)

profilo = {}

if modalita == "Scelgo una laurea dal database":
    corso_col = "Corso"

    if corso_col not in triennali.columns:
        st.error(f"Nel file triennali manca la colonna '{corso_col}'.")
        st.write("Colonne trovate:", list(triennali.columns))
        st.stop()

    corso_scelto = st.selectbox(
        "Da quale triennale parti?",
        sorted(triennali[corso_col].dropna().unique())
    )

    riga = triennali[triennali[corso_col] == corso_scelto].iloc[0]

    for col in triennali.columns:
        valore = riga[col]
        if pd.notna(valore):
            try:
                cfu = float(valore)
                if cfu > 0 and col != corso_col:
                    profilo[str(col).strip()] = cfu
            except:
                pass

else:
    profilo = crea_profilo_manual()


st.divider()

if not profilo:
    st.warning("Inserisci o seleziona un profilo CFU per vedere i risultati.")
    st.stop()


risultati = []

for _, row in magistrali.iterrows():
    requisiti = estrai_requisiti(row)
    match, coperti, richiesti, mancanti = calcola_match(profilo, requisiti)

    risultati.append({
        "Corso": row.get("Corso", row.get("Magistrale", "Corso senza nome")),
        "Università": row.get("Università", row.get("Ateneo", "")),
        "Link": row.get("Link requisiti di accesso", ""),
        "Compatibilità": match,
        "CFU coperti": coperti,
        "CFU richiesti": richiesti,
        "CFU mancanti": mancanti
    })


df = pd.DataFrame(risultati)
df = df.sort_values("Compatibilità", ascending=False)

st.subheader("Risultati UniMatch Online")

for index, row in df.iterrows():
    match = row["Compatibilità"]

    if match >= 80:
        badge = "🟢 Ottima compatibilità"
    elif match >= 50:
        badge = "🟡 Compatibilità media"
    elif match >= 30:
        badge = "🟠 Compatibilità parziale"
    else:
        badge = "🔴 Compatibilità bassa"

    with st.container(border=True):
        col1, col2 = st.columns([4, 1])

        with col1:
            st.markdown(f"### {row['Corso']}")
            st.write(row["Università"])
            st.caption(badge)

        with col2:
            st.metric("Match", f"{match}%")

        c1, c2, c3 = st.columns(3)
        c1.metric("CFU coperti", f"{row['CFU coperti']:g}")
        c2.metric("CFU richiesti", f"{row['CFU richiesti']:g}")
        c3.metric("CFU mancanti", f"{max(row['CFU richiesti'] - row['CFU coperti'], 0):g}")

        if row["CFU mancanti"]:
            with st.expander("Vedi CFU mancanti"):
                for mancante in row["CFU mancanti"]:
                    st.write("-", mancante)

        if pd.notna(row["Link"]) and str(row["Link"]).startswith("http"):
            st.link_button("Vai al sito ufficiale", row["Link"])
