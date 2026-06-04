import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="UniMatch Trieste MVP", layout="wide")
st.title("🎓 UniMatch")
st.caption("Scopri le lauree magistrali compatibili con il tuo percorso")
st.markdown("---")

excel_file = "Database (3).xlsx"

programs = pd.read_excel(excel_file, sheet_name="program_course")
requirements = pd.read_excel(excel_file, sheet_name="master_requirements")

trieste_programs = programs[
    (programs["Università"] == "Università degli studi di Trieste") &
    (programs["Tipo"] == "Triennale") &
    (programs["Anno"] == "2024/2025")
].copy()

trieste_requirements = requirements[
    requirements["Università"] == "Università degli studi di Trieste"
].copy()

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

    for i in range(1, 13):
        req_col = f"Requisito{i}"
        val_col = f"Valore{i}"

        if req_col in row and val_col in row:
            if row[req_col] == "Crediti" and pd.notna(row[val_col]):
                credit_requirements.append(row[val_col])

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
        "Corso": row["Nome CDL"],
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

selected_degree = st.selectbox(
    "Da quale triennale parti?",
    course_options,
    placeholder="Cerca o seleziona il tuo corso..."
)

profile = build_profile_from_course(selected_degree)
ranking = rank_masters_for_profile(profile)

st.subheader("Profilo selezionato")
st.write("Corso:", profile["course"])
st.write("Codice:", profile["code"])
st.write("CFU totali:", profile["total_cfu"])

st.subheader("Ranking magistrali")

ranking_view = ranking[[
    "Corso",
    "Stato",
    "Compatibilità",
    "CFU coperti",
    "CFU richiesti",
    "Requisiti soddisfatti",
    "Requisiti totali"
]].head(20)

st.write(ranking_view.to_html(index=False), unsafe_allow_html=True)

st.subheader("Dettaglio mancanze")

selected_master = st.selectbox(
    "Seleziona magistrale",
    ranking["Corso"].tolist()
)

course = ranking[ranking["Corso"] == selected_master].iloc[0]

st.write("Magistrale:", course["Corso"])
st.write("Stato:", course["Stato"])
st.write("Compatibilità:", str(course["Compatibilità"]) + "%")
st.write("CFU:", str(course["CFU coperti"]) + " / " + str(course["CFU richiesti"]))

if len(course["Mancanze"]) == 0:
    st.success("Nessuna mancanza rilevata")
else:
    for item in course["Mancanze"]:
        st.warning(
            f"Mancano {item['Mancano CFU']} CFU complessivi in uno o più dei seguenti SSD: {item['SSD']}"
        )
