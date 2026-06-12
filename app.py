import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="UniMatch", page_icon="🎓", layout="centered")

st.markdown("# 🎓 UniMatch")
st.markdown("### Trova le magistrali online compatibili con il tuo percorso")
st.caption("Matching basato su classe di laurea, SSD e CFU dichiarati nei requisiti di accesso.")
st.markdown("---")

excel_file = "Database (3).xlsx"
online_file = "db giugno26.xlsx"

programs = pd.read_excel(excel_file, sheet_name="program_course")
requirements = pd.read_excel(excel_file, sheet_name="master_requirements")
online_requirements = pd.read_excel(online_file, sheet_name="requirements Online")

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
    ["Magistrali Online", "Magistrali Trieste"]
)

if catalog_mode == "Magistrali Online":
    trieste_requirements = online_requirements.copy()

metadata_cols = [
    "Università", "Anno", "Tipo", "Codice CDL", "Nome CDL",
    "Crediti variabili", "Totale CFU"
]

ssd_cols = [col for col in trieste_programs.columns if col not in metadata_cols]


def course_label(row):
    return f"{str(row['Codice CDL']).upper().strip()} · {row['Nome CDL']}"


def build_profile_from_course(course_name):
    labels = trieste_programs.apply(course_label, axis=1)

    selected = trieste_programs[labels == course_name]

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
        "code": str(row["Codice CDL"]).upper().strip(),
        "total_cfu": row["Totale CFU"],
        "cfu": cfu
    }


def extract_credit_requirements(row):
    credit_requirements = []

    for i in range(1, 13):
        req_col = f"Requisito{i}"
        val_col = f"Valore{i}"

        if req_col in row and val_col in row:
            if str(row[req_col]).strip().lower() == "crediti" and pd.notna(row[val_col]):
                credit_requirements.append(row[val_col])

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


def parse_degree_classes(value):
    if pd.isna(value):
        return []

    text = str(value).upper()
    text = text.replace(";", ",")
    text = text.replace("/", ",")
    text = text.replace("\n", ",")

    return [
        item.strip()
        for item in text.split(",")
        if item.strip().startswith("L-")
    ]


def extract_direct_degree_classes(row):
    direct_classes = []

    for i in range(1, 13):
        req_col = f"Requisito{i}"
        val_col = f"Valore{i}"

        if req_col in row and val_col in row:
            if str(row[req_col]).strip().lower() == "laurea":
                direct_classes.extend(parse_degree_classes(row[val_col]))

    return sorted(set(direct_classes))


def evaluate_course(student, row):
    direct_classes = extract_direct_degree_classes(row)
    direct_class_match = str(student["code"]).upper().strip() in direct_classes

    results = match_group_requirements(student, row["parsed_requirements"])

    if len(results) == 0 and not direct_class_match:
        return None

    total_required_cfu = sum(r["required"] for r in results)
    total_covered_cfu = sum(min(r["available"], r["required"]) for r in results)

    if direct_class_match:
        compatibility = 100
    elif total_required_cfu > 0:
        compatibility = round(total_covered_cfu / total_required_cfu * 100)
    else:
        compatibility = 0

    missing = []

    for r in results:
        if not r["ok"]:
            missing.append({
                "SSD": ", ".join(r["ssds"]),
                "Mancano CFU": r["missing"]
            })

    course_name = row["Nome CDL"] if "Nome CDL" in row else "Corso senza nome"
    course_code = str(row["Codice CDL"]).upper().strip() if "Codice CDL" in row else ""

    return {
        "Università": row["Università"] if "Università" in row else "",
        "Codice": course_code,
        "Corso": course_name,
        "URL": row["Link requisiti di accesso"] if "Link requisiti di accesso" in row else "",
        "Compatibilità": compatibility,
        "CFU coperti": total_covered_cfu,
        "CFU richiesti": total_required_cfu,
        "Requisiti soddisfatti": sum(r["ok"] for r in results),
        "Requisiti totali": len(results),
        "Mancanze": missing,
        "Accesso diretto per classe": direct_class_match,
        "Classi ammesse": ", ".join(direct_classes)
    }


def status_label(row):
    if row.get("Accesso diretto per classe", False):
        return "✅ Accesso diretto per classe"

    if row["Requisiti soddisfatti"] == row["Requisiti totali"]:
        return "✅ Compatibile per CFU"
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

    if ranking.empty:
        return ranking

    ranking = ranking.sort_values(
        by=["Compatibilità", "CFU coperti"],
        ascending=[False, False]
    )

    ranking["Stato"] = ranking.apply(status_label, axis=1)
    ranking = ranking.drop_duplicates(subset=["Corso"], keep="first")

    return ranking


course_options = sorted(
    trieste_programs.apply(course_label, axis=1).dropna().unique()
)

st.subheader("1. Scegli il tuo percorso di partenza")

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

if ranking.empty:
    st.warning("Nessuna magistrale valutabile con i dati disponibili.")
    st.stop()

st.subheader("2. Il tuo profilo CFU")

st.markdown(
    f"""
    <div style="
        border:1px solid #e5e7eb;
        border-radius:14px;
        padding:16px 18px;
        margin:16px 0 22px 0;
        background-color:#f9fafb;
    ">
        <div style="font-size:14px; color:#6b7280; margin-bottom:4px;">
            Profilo analizzato
        </div>
        <div style="font-size:23px; font-weight:750; line-height:1.25;">
            🎓 {profile['code']} · {profile['course']}
        </div>
        <div style="font-size:14px; color:#6b7280; margin-top:6px;">
            CFU rilevati: <strong>{profile['total_cfu']:.0f}</strong>
        </div>
        <div style="font-size:13px; color:#6b7280; margin-top:6px;">
            Attendibilità stimata: 85% · Per precisione massima inserisci i tuoi CFU manualmente
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

st.subheader("3. Le migliori opportunità per te")
st.caption("Ordinate automaticamente in base al tuo profilo CFU")

medals = [
    "🥇 Miglior opportunità",
    "🥈 Ottima compatibilità",
    "🥉 Da valutare"
]

for index, (_, row) in enumerate(ranking.head(10).iterrows()):

    cfu_mancanti = max(row["CFU richiesti"] - row["CFU coperti"], 0)

    if row["Compatibilità"] >= 80:
        colore = "#16a34a"
    elif row["Compatibilità"] >= 50:
        colore = "#ca8a04"
    elif row["Compatibilità"] >= 30:
        colore = "#ea580c"
    else:
        colore = "#dc2626"

    badge = medals[index] if index < 3 else "🎓 Opportunità formativa"

    with st.container(border=True):
        st.caption(badge)

        left, right = st.columns([4, 1])

        with left:
            st.markdown(f"### 🎓 {row['Codice']} · {row['Corso']}")
            st.caption(f"🏛️ {row['Università']}")

        with right:
            if row.get("Accesso diretto per classe", False):
                badge_text = "ACCESSO DIRETTO"
            else:
                badge_text = f"MATCH {row['Compatibilità']}%"

            st.markdown(
                f"""
                <div style="text-align:right;">
                    <span style="
                        display:inline-block;
                        background:{colore};
                        color:white;
                        padding:6px 12px;
                        border-radius:999px;
                        font-size:14px;
                        font-weight:700;
                    ">
                        {badge_text}
                    </span>
                </div>
                """,
                unsafe_allow_html=True
            )

        if row.get("Accesso diretto per classe", False):
    st.markdown(
        f"""
        <div style="
            font-size:15px;
            margin-top:8px;
            margin-bottom:8px;
            color:#374151;
        ">
            Requisito principale soddisfatto:
            <strong>{profile['code']}</strong> è tra le classi ammesse.
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    st.markdown(
        f"""
        <div style="
            font-size:15px;
            margin-top:8px;
            margin-bottom:8px;
            color:#374151;
        ">
            Coperti: <strong>{row['CFU coperti']:.0f}</strong>
            · Richiesti: <strong>{row['CFU richiesti']:.0f}</strong>
            · Mancano: <strong>{cfu_mancanti:.0f}</strong>
        </div>
        """,
        unsafe_allow_html=True
    )

        if row.get("Accesso diretto per classe", False):
            st.success(
                f"✅ Accesso diretto: la tua classe di laurea è ammessa. "
                f"Classi ammesse: {row['Classi ammesse']}."
            )
        elif cfu_mancanti == 0:
            st.success("✅ Compatibile: i CFU richiesti risultano coperti.")
        else:
            st.warning(f"⚠️ Mancano {cfu_mancanti:.0f} CFU per coprire tutti i requisiti.")

        if pd.notna(row["URL"]) and str(row["URL"]).strip() != "":
            st.link_button(
                "Vai al sito ufficiale →",
                row["URL"],
                use_container_width=True
            )

st.info(
    "La compatibilità indica quanta parte dei CFU richiesti risulta già coperta dal tuo percorso. "
    "Se la tua classe di laurea è ammessa direttamente, UniMatch segnala accesso diretto. "
    "Controlla sempre il bando ufficiale del corso prima di iscriverti."
)

st.subheader("4. Dettaglio requisiti mancanti")
st.caption("Seleziona una magistrale per vedere quali CFU mancano")

selected_master = st.selectbox(
    "Seleziona magistrale",
    [f"{row['Codice']} · {row['Corso']}" for _, row in ranking.iterrows()]
)

course_name_selected = selected_master.split(" · ", 1)[1]
course = ranking[ranking["Corso"] == course_name_selected].iloc[0]

st.markdown(f"### {course['Codice']} · {course['Corso']}")

col1, col2, col3 = st.columns(3)

col1.metric("Stato", course["Stato"])
col2.metric("Compatibilità", str(course["Compatibilità"]) + "%")
col3.metric(
    "CFU coperti",
    str(int(course["CFU coperti"])) + " / " + str(int(course["CFU richiesti"]))
)

if course.get("Accesso diretto per classe", False):
    st.success(
        f"Accesso diretto per classe di laurea. Classi ammesse: {course['Classi ammesse']}"
    )

if len(course["Mancanze"]) == 0:
    st.success("Nessuna mancanza rilevata.")
else:
    for item in course["Mancanze"]:
        st.warning(
            f"Mancano {item['Mancano CFU']:.0f} CFU complessivi in uno o più dei seguenti SSD: {item['SSD']}"
        )
