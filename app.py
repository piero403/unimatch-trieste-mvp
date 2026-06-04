import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="UniMatch Trieste MVP", layout="wide")
st.title("🎓 UniMatch")
st.caption("Scopri le lauree magistrali compatibili con il tuo percorso")
st.markdown("---")

excel_file = "Database (3).xlsx"
online_file = "gruppo multiversity.xlsx"

programs = pd.read_excel(excel_file, sheet_name="program_course")
requirements = pd.read_excel(excel_file, sheet_name="master_requirements")
online_requirements = pd.read_excel(
    online_file,
    sheet_name="Online_Requisiti Magistrali"
)

trieste_programs = programs[
    (programs["Università"] == "Università degli studi di Trieste") &
    (programs["Tipo"] == "Triennale") &
    (programs["Anno"] == "2024/2025")
].copy()

trieste_requirements = requirements[
    requirements["Università"] == "Università degli studi di Trieste"
].copy()
catalog_mode = st.radio(
    "Quali percorsi vuoi esplorare?",
    ["Magistrali Trieste", "Magistrali Online"]
)

if catalog_mode == "Magistrali Online":
    trieste_requirements = online_requirements.copy()

metadata_cols = [
    "Università", "Anno", "Tipo", "Codice CDL", "Nome CDL",
    "Crediti variabili", "Totale CFU"
]

ssd_cols = [col for col in trieste_programs.columns if col not in metadata_cols]

def build_profile_from_course(course_name):
    selected = trieste_programs[
        trieste_programs["Nome CDL"].str.contains(course_name, case=False, na=False)
    ]

    if selected.empty:
        return None

    row = selected.iloc[0]
    cfu = {}

    for ssd in ssd_cols:
        value = row[ssd]
        if pd.notna(value) and value > 0:
            cfu[ssd] = float(value)

    return {
        "course": row["Nome CDL"],
        "code": row["Codice CDL"],
        "total_cfu": row["Totale CFU"],
        "cfu": cfu
    }

def extract_credit_requirements(row):
    credit_requirements = []

    # Formato vecchio: Requisito1 / Valore1
    for i in range(1, 13):
        req_col = f"Requisito{i}"
        val_col = f"Valore{i}"

        if req_col in row and val_col in row:
            if row[req_col] == "Crediti" and pd.notna(row[val_col]):
                credit_requirements.append(row[val_col])

    # Formato nuovo: Requisito SSD / Requisito CFU
    for i in range(0, 12):
        if i == 0:
            ssd_col = "Requisito SSD"
            cfu_col = "Requisito CFU"
        else:
            ssd_col = f"Requisito SSD.{i}"
            cfu_col = f"Requisito CFU.{i}"

        if ssd_col in row and cfu_col in row:
            if pd.notna(row[ssd_col]) and pd.notna(row[cfu_col]):
                ssd_text = str(row[ssd_col]).replace("DI CUI ALMENO -->", "").strip()
                cfu_value = int(float(row[cfu_col]))

                credit_requirements.append(f"[{ssd_text}] {cfu_value}")

    return credit_requirements

def parse_credit_block(text):
    text = str(text)
    pattern = r"\[([^\]]+)\]\s*(\d+)"
    matches = re.findall(pattern, text)

    blocks = []

    for ssd_list, cfu in matches:
        ssds = [ssd.strip() for ssd in ssd_list.split(",")]
        blocks.append({
            "ssds": ssds,
            "cfu_required": int(cfu)
        })

    return blocks

trieste_requirements["credit_requirements"] = trieste_requirements.apply(
    extract_credit_requirements,
    axis=1
)

trieste_requirements["parsed_requirements"] = trieste_requirements["credit_requirements"].apply(
    lambda items: [parse_credit_block(item) for item in items]
)

def match_group_requirements(student, parsed_requirements):
    results = []

    for group in parsed_requirements:
        for block in group:
            ssds = block["ssds"]
            required = block["cfu_required"]
            available = sum(student["cfu"].get(ssd, 0) for ssd in ssds)
            missing = max(required - available, 0)

            results.append({
                "ssds": ssds,
                "required": required,
                "available": available,
                "missing": missing,
                "ok": missing == 0
            })

    return results

def evaluate_course(student, row):
    results = match_group_requirements(student, row["parsed_requirements"])

    if len(results) == 0:
        return None

    total_required_cfu = sum(r["required"] for r in results)
    total_covered_cfu = sum(min(r["available"], r["required"]) for r in results)

    compatibility = round(total_covered_cfu / total_required_cfu * 100)

    missing = []

    for r in results:
        if not r["ok"]:
            missing.append({
                "SSD": ", ".join(r["ssds"]),
                "Mancano CFU": r["missing"]
            })

    return {
    "Università": row["Università"] if "Università" in row else "",
    "Codice": row["Laurea Magistrale"] if "Laurea Magistrale" in row else "",
    "Corso": row["Nome CDL"] if "Nome CDL" in row else row["Nome magistrale"],
    "Compatibilità": compatibility,
    "CFU coperti": total_covered_cfu,
    "CFU richiesti": total_required_cfu,
    "Requisiti soddisfatti": sum(r["ok"] for r in results),
    "Requisiti totali": len(results),
    "Mancanze": missing
}

def status_label(row):
    if row["Requisiti soddisfatti"] == row["Requisiti totali"]:
        return "✅ Compatibile"
    elif row["Compatibilità"] >= 80:
        return "🟡 Quasi compatibile"
    elif row["Compatibilità"] >= 40:
        return "🟠 Parzialmente compatibile"
    else:
        return "🔴 Poco compatibile"

def rank_masters_for_profile(profile):
    all_results = []

    for _, row in trieste_requirements.iterrows():
        result = evaluate_course(profile, row)
        if result is not None:
            all_results.append(result)

    ranking = pd.DataFrame(all_results)
    ranking = ranking.sort_values(by="Compatibilità", ascending=False)
    ranking["Stato"] = ranking.apply(status_label, axis=1)
    ranking = ranking.drop_duplicates(subset=["Corso"], keep="first")

    return ranking

course_options = sorted(trieste_programs["Nome CDL"].dropna().unique())

st.subheader("1. Scegli il tuo corso di laurea triennale")

input_mode = st.radio(
    "Come vuoi inserire il tuo percorso?",
    ["Scelgo una laurea dal database", "Inserisco manualmente i miei CFU"]
)
if input_mode == "Scelgo una laurea dal database":
    selected_degree = st.selectbox(
        "Da quale triennale parti?",
        course_options,
        placeholder="Cerca o seleziona il tuo corso..."
    )

    profile = build_profile_from_course(selected_degree)

else:
    st.subheader("Inserisci manualmente i tuoi CFU")
    st.caption("Aggiungi solo gli SSD che hai nel tuo piano di studi.")

    available_ssds = sorted(ssd_cols)

    manual_rows = st.data_editor(
        pd.DataFrame([
            {"SSD": None, "CFU": 0.0},
            {"SSD": None, "CFU": 0.0},
            {"SSD": None, "CFU": 0.0}
        ]),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "SSD": st.column_config.SelectboxColumn(
                "SSD",
                options=available_ssds,
                required=False
            ),
            "CFU": st.column_config.NumberColumn(
                "CFU",
                min_value=0,
                max_value=60,
                step=1
            )
        }
    )

    manual_cfu = {}

    for _, row in manual_rows.iterrows():
        ssd = row["SSD"]
        cfu = row["CFU"]

        if pd.notna(ssd) and pd.notna(cfu) and cfu > 0:
            manual_cfu[ssd] = float(cfu)

    profile = {
        "course": "Percorso inserito manualmente",
        "code": "MANUALE",
        "total_cfu": sum(manual_cfu.values()),
        "cfu": manual_cfu
    }

if profile is None:
    st.stop()

ranking = rank_masters_for_profile(profile)

st.subheader("2. Il tuo profilo CFU")

st.markdown(
    f"""
    <div style="
        border:1px solid #e5e7eb;
        border-radius:12px;
        padding:14px 18px;
        margin:20px 0;
        background-color:#f9fafb;
    ">
        <div style="font-size:15px; color:#6b7280;">Profilo analizzato</div>
        <div style="font-size:24px; font-weight:700;">
            🎓 {profile['course']} <span style="color:#6b7280;">({profile['code']})</span>
        </div>
        <div style="font-size:14px; color:#6b7280;">
            Attendibilità stimata: 85% · Per precisione massima inserisci i tuoi CFU
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

st.subheader("3. Le migliori opportunità per te")
st.caption("Ordinate automaticamente in base al tuo profilo CFU")

medals = ["🥇 Miglior opportunità", "🥈 Ottima compatibilità", "🥉 Da valutare"]

top_results = ranking.head(9).reset_index(drop=True)

for start in range(0, len(top_results), 3):
    cols = st.columns(3)

    for col_index, col in enumerate(cols):
        result_index = start + col_index

        if result_index >= len(top_results):
            continue

        row = top_results.iloc[result_index]

        cfu_mancanti = row["CFU richiesti"] - row["CFU coperti"]

        if row["Compatibilità"] >= 80:
            match_badge = f"🟢 MATCH {row['Compatibilità']}%"
        elif row["Compatibilità"] >= 50:
            match_badge = f"🟡 MATCH {row['Compatibilità']}%"
        elif row["Compatibilità"] >= 30:
            match_badge = f"🟠 MATCH {row['Compatibilità']}%"
        else:
            match_badge = f"🔴 MATCH {row['Compatibilità']}%"

        badge = medals[result_index] if result_index < 3 else "🎓 Opportunità formativa"

        with col:
            with st.container(border=True):
                st.caption(badge)
                st.markdown(f"#### {row['Corso']}")
                st.caption(row["Università"])

                st.markdown(f"**{match_badge}**")

                if cfu_mancanti == 0:
                    st.success("✅ Nessun CFU mancante")
                else:
                    st.warning(f"⚠️ Mancano {cfu_mancanti:.0f} CFU")

                st.link_button(
                    "Scopri il corso",
                    "https://www.google.com"
                )

st.info(
    "La compatibilità indica quanta parte dei CFU richiesti risulta già coperta dal tuo percorso. "
    "Controlla sempre il bando ufficiale del corso prima di iscriverti."
)

st.subheader("4. Dettaglio requisiti mancanti")
st.caption("Seleziona una magistrale per vedere quali CFU mancano")

selected_master = st.selectbox(
    "Seleziona magistrale",
    ranking["Corso"].tolist()
)

course = ranking[ranking["Corso"] == selected_master].iloc[0]

st.markdown(f"### {course['Corso']}")

col1, col2, col3 = st.columns(3)

col1.metric("Stato", course["Stato"])
col2.metric("Compatibilità", str(course["Compatibilità"]) + "%")
col3.metric("CFU coperti", str(course["CFU coperti"]) + " / " + str(course["CFU richiesti"]))

if len(course["Mancanze"]) == 0:
    st.success("Nessuna mancanza rilevata")
else:
    for item in course["Mancanze"]:
        st.warning(
            f"Mancano {item['Mancano CFU']} CFU complessivi in uno o più dei seguenti SSD: {item['SSD']}"
        )
