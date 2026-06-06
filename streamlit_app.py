"""
Systematic Review — File Importer v3
"""

import streamlit as st
import pandas as pd
import io, re, csv
from datetime import datetime

st.set_page_config(page_title="SR Importer", page_icon="📥", layout="wide")


QUERY_MAP = {
    "D1Q1": "D1_Standardization_AI", "D1Q2": "D1_Standardization_AI",
    "D2Q1": "D2_Context_Engineering", "D2Q2": "D2_Context_Engineering", "D2Q3": "D2_Context_Engineering",
    "D3Q1": "D3_Token_Efficiency",   "D3Q2": "D3_Token_Efficiency",   "D3Q3": "D3_Token_Efficiency",
}

EXCLUSION_CRITERIA = [
    "E1: Outside year range (2015-2026)", "E2: Not English",
    "E3: Not journal/conference/review paper", "E4: Not relevant to dimension topic",
    "E5: Duplicate", "E6: Full text not accessible",
    "E7: Abstract only / insufficient detail", "E8: Not peer-reviewed",
]

# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_springer_csv(content, query_id):
    papers = []
    try:
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            papers.append({
                "title":    row.get("Item Title","").strip(),
                "authors":  row.get("Authors","").strip(),
                "year":     str(row.get("Publication Year","")).strip(),
                "source":   (row.get("Publication Title","") or row.get("Book Series Title","")).strip(),
                "doi":      row.get("Item DOI","").strip(),
                "abstract": "",
                "url":      row.get("ArticleURL","").strip() or row.get("URL","").strip(),
                "type":     row.get("Content Type","").strip(),
                "database": "Springer", "query_id": query_id,
                "dimension": QUERY_MAP.get(query_id,""),
            })
    except Exception as e:
        st.warning(f"Springer parse error: {e}")
    return papers

def parse_scopus_csv(content, query_id):
    papers = []
    try:
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            papers.append({
                "title":    row.get("Title","").strip(),
                "authors":  row.get("Authors","").strip(),
                "year":     str(row.get("Year","")).strip(),
                "source":   row.get("Source title","").strip(),
                "doi":      row.get("DOI","").strip(),
                "abstract": "",
                "url":      row.get("Link","").strip(),
                "type":     row.get("Document Type","").strip(),
                "database": "Elsevier/Scopus", "query_id": query_id,
                "dimension": QUERY_MAP.get(query_id,""),
            })
    except Exception as e:
        st.warning(f"Scopus parse error: {e}")
    return papers

def parse_scopus_pop_csv(content, query_id):
    papers = []
    try:
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            papers.append({
                "title":    row.get("Title","").strip(),
                "authors":  row.get("Authors","").strip(),
                "year":     str(row.get("Year","")).strip(),
                "source":   row.get("Source","").strip(),
                "doi":      row.get("DOI","").strip(),
                "abstract": "",
                "url":      row.get("ArticleURL","").strip(),
                "type":     row.get("Type","Article").strip(),
                "database": "Elsevier/Scopus", "query_id": query_id,
                "dimension": QUERY_MAP.get(query_id,""),
            })
    except Exception as e:
        st.warning(f"Scopus PoP parse error: {e}")
    return papers

def parse_scholar_csv(content, query_id):
    papers = []
    try:
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            papers.append({
                "title":    row.get("Title","").strip(),
                "authors":  row.get("Authors","").strip(),
                "year":     str(row.get("Year","")).strip(),
                "source":   row.get("Source","").strip(),
                "doi":      row.get("DOI","").strip(),
                "abstract": "",
                "url":      row.get("ArticleURL","").strip() or row.get("URL","").strip(),
                "type":     row.get("Type","article").strip(),
                "database": "Google Scholar", "query_id": query_id,
                "dimension": QUERY_MAP.get(query_id,""),
            })
    except Exception as e:
        st.warning(f"Scholar parse error: {e}")
    return papers

def parse_bib(content, query_id):
    papers = []
    entries = re.split(r'\n@', content)
    for entry in entries:
        if not entry.strip(): continue
        if not entry.startswith('@'): entry = '@' + entry
        def get_field(field, text):
            m = re.search(rf'{field}\s*=\s*[{{"](.+?)[}}"]\s*[,}}]', text, re.IGNORECASE|re.DOTALL)
            return m.group(1).strip().replace('\n',' ') if m else ""
        papers.append({
            "title":    get_field("title", entry),
            "authors":  get_field("author", entry),
            "year":     get_field("year", entry),
            "source":   get_field("booktitle", entry) or get_field("journal", entry),
            "doi":      get_field("doi", entry),
            "abstract": "",
            "url":      get_field("url", entry),
            "type":     "Conference Paper" if "inproceedings" in entry[:30].lower() else "Article",
            "database": "ACM", "query_id": query_id,
            "dimension": QUERY_MAP.get(query_id,""),
        })
    return [p for p in papers if p["title"]]

def detect_csv_type(content, fname=""):
    first  = content.split('\n')[0].lower()
    second = content.split('\n')[1].lower() if len(content.split('\n')) > 1 else ""
    if "scopus"   in fname: return "scopus_pop"
    if "springer" in fname: return "springer"
    if "scholar"  in fname: return "scholar"
    if "item title"   in first: return "springer"
    if "source title" in first: return "scopus"
    if "scopus.com"   in second: return "scopus_pop"
    return "scholar"

def paper_score(p):
    """Score paper by data completeness — higher = keep this one"""
    score = 0
    if p.get("abstract","").strip(): score += 3
    if p.get("doi","").strip():      score += 2
    if p.get("url","").strip():      score += 1
    if p.get("authors","").strip():  score += 1
    return score

def deduplicate(papers):
    # Sort by score descending so best version comes first
    sorted_papers = sorted(papers, key=paper_score, reverse=True)
    seen_doi, seen_title, unique, dupe_list = set(), set(), [], []
    for p in sorted_papers:
        doi   = p.get("doi","").strip().lower()
        title = p.get("title","").strip().lower()[:120]
        if doi:
            if doi in seen_doi:
                dupe_list.append(p); continue
            seen_doi.add(doi)
        else:
            if title and title in seen_title:
                dupe_list.append(p); continue
        if title:
            seen_title.add(title)
        unique.append(p)
    return unique, dupe_list

def is_valid_year(y):
    return str(y).strip().isdigit() and 2015 <= int(str(y).strip()) <= 2026

# ── Excel Builder ─────────────────────────────────────────────────────────────

def build_excel(papers, stats, dupe_list):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    H_FILL  = PatternFill("solid", start_color="1F4E79")
    H_FONT  = Font(bold=True, color="FFFFFF", name="Arial", size=10)
    W_FILL  = PatternFill("solid", start_color="FFF2CC")
    M_FILL  = PatternFill("solid", start_color="FFE0E0")
    D_FILL  = PatternFill("solid", start_color="E8EAF6")
    THIN    = Side(style="thin", color="BFBFBF")
    BDR     = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    DIM_CLR = {"D1":"D6E4F0","D2":"D5E8D4","D3":"FFF2CC"}
    PH_CLR  = {"Identification":"D6E4F0","Screening":"D5E8D4","Eligibility":"FFF2CC","Included":"FCE4D6"}

    # ALL papers go to screening — flag issues but don't exclude
    main_papers  = papers  # everyone screened
    missing_year = [p for p in papers if not str(p.get("year","")).strip().isdigit() or not is_valid_year(p.get("year",""))]
    missing_doi  = [p for p in papers if not p.get("doi","").strip()]

    wb = openpyxl.Workbook()

    # ── SCREEN_COLS: simplified — only 8 columns as requested ─────────────────
    SCREEN_COLS = [
        ("Database",       14),
        ("Title",          50),
        ("Authors",        25),
        ("Year",            6),
        ("Source / Journal",26),
        ("DOI",            28),
        ("URL",            28),
        ("Abstract (snippet)", 50),
    ]

    def write_screen(ws, paper_list, row_fill_fn=None, start_row=1):
        ws.freeze_panes = f"A{start_row+1}"
        for ci,(name,width) in enumerate(SCREEN_COLS,1):
            c = ws.cell(row=start_row, column=ci, value=name)
            c.font=H_FONT; c.fill=H_FILL; c.border=BDR
            c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
            ws.column_dimensions[get_column_letter(ci)].width=width
        ws.row_dimensions[start_row].height=32
        for ri,p in enumerate(paper_list, start_row+1):
            fill = row_fill_fn(p) if row_fill_fn else PatternFill("solid", start_color=DIM_CLR.get(p.get("dimension","")[:2],"FFFFFF"))
            vals = [
                p.get("database",""),
                p.get("title",""),
                p.get("authors","")[:120],
                p.get("year",""),
                p.get("source","")[:60],
                p.get("doi",""),
                p.get("url","")[:100],
                p.get("abstract",""),
            ]
            for ci,val in enumerate(vals,1):
                c=ws.cell(row=ri,column=ci,value=val)
                c.fill=fill; c.border=BDR
                c.font=Font(name="Arial",size=9)
                c.alignment=Alignment(wrap_text=True,vertical="top")
        ws.auto_filter.ref=f"A{start_row}:{get_column_letter(len(SCREEN_COLS))}{start_row+len(paper_list)}"

    # ── Sheet 1: PRISMA Flow ──────────────────────────────────────────────────
    ws = wb.active; ws.title = "PRISMA_Flow"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 3
    ws["B2"].value = "PRISMA 2020 Flow Tracker"
    ws["B2"].font  = Font(bold=True, size=14, color="1F4E79", name="Arial")
    ws.merge_cells("B2:H2")

    total_raw   = stats.get("total_raw", 0)
    total_dupes = len(dupe_list)
    after_dedup = stats.get("after_dedup", 0)

    hdrs = ["Phase","Step","Database","Query ID","n (raw)","n (after filter)","Notes"]
    wids = [18,42,18,12,12,16,50]
    for ci,(h,w) in enumerate(zip(hdrs,wids),2):
        c=ws.cell(row=4,column=ci,value=h)
        c.font=H_FONT; c.fill=H_FILL; c.border=BDR
        c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
        ws.column_dimensions[get_column_letter(ci)].width=w
    ws.row_dimensions[4].height=28

    rows=[]
    for db,qc in stats.get("identification",{}).items():
        for qid,n in qc.items():
            rows.append(["Identification",f"Records identified: {db}",db,qid,n,"",""])
    rows += [
        ["Identification","Total records identified",         "All","ALL",total_raw,   "","Sum of all DB results"],
        ["Identification","Duplicate records removed",        "All","ALL",total_dupes, "","See Duplicates_Removed sheet"],
        ["Identification","Records after deduplication",      "All","ALL",after_dedup, "",""],
        ["Screening",     "Records screened (title/abstract)","All","ALL",after_dedup, "","Manual screening required"],
        ["Screening",     "Missing year - manual check",      "All","ALL",len(missing_year),"","See Missing_Year sheet"],
        ["Screening",     "Missing DOI - manual check",       "All","ALL",len(missing_doi), "","See Missing_DOI sheet"],
        ["Screening",     "Records with year + DOI (main)",   "All","ALL",len(main_papers), "","See Screening_Sheet"],
        ["Screening",     "Records excluded - title screen",  "All","ALL","","","Fill after manual screening"],
        ["Screening",     "Records excluded - abstract",      "All","ALL","","","Fill after manual screening"],
        ["Screening",     "Reports sought for retrieval",     "All","ALL","","",""],
        ["Screening",     "Reports not retrieved",            "All","ALL","","",""],
        ["Eligibility",   "Reports assessed for eligibility", "All","ALL","","",""],
        ["Eligibility",   "Reports excluded with reasons",    "All","ALL","","","E1-E8 see Exclusion_Criteria"],
        ["Included",      "Studies included in final review", "All","ALL","","","Fill after full screening"],
    ]
    for ri,row in enumerate(rows,5):
        fill = PatternFill("solid", start_color=PH_CLR.get(row[0],"FFFFFF"))
        if "missing" in str(row[1]).lower() or "duplicate" in str(row[1]).lower():
            fill = W_FILL
        for ci,val in enumerate(row,2):
            c=ws.cell(row=ri,column=ci,value=val)
            c.fill=fill; c.border=BDR
            c.font=Font(name="Arial",size=9)
            c.alignment=Alignment(wrap_text=True,vertical="center")

    # ── Sheet 2: Screening Sheet (8 cols only) ────────────────────────────────
    ws2 = wb.create_sheet("Screening_Sheet")
    write_screen(ws2, main_papers)

    # ── Sheet 3: Duplicates Removed ───────────────────────────────────────────
    ws_dup = wb.create_sheet("Duplicates_Removed")
    ws_dup["A1"].value = f"Duplicates removed ({len(dupe_list)}) — verify deduplication is correct"
    ws_dup["A1"].font  = Font(bold=True, size=12, color="2E4057", name="Arial")
    ws_dup.merge_cells(f"A1:{get_column_letter(len(SCREEN_COLS))}1")
    ws_dup.row_dimensions[1].height = 20
    write_screen(ws_dup, dupe_list, row_fill_fn=lambda p: D_FILL, start_row=2)

    # ── Sheet 4: Missing Year ─────────────────────────────────────────────────
    ws_my = wb.create_sheet("Missing_Year")
    ws_my["A1"].value = f"Missing/invalid year ({len(missing_year)}) — verify manually"
    ws_my["A1"].font  = Font(bold=True, size=12, color="7F6000", name="Arial")
    ws_my.merge_cells(f"A1:{get_column_letter(len(SCREEN_COLS))}1")
    ws_my.row_dimensions[1].height = 20
    write_screen(ws_my, missing_year, row_fill_fn=lambda p: W_FILL, start_row=2)

    # ── Sheet 5: Missing DOI ──────────────────────────────────────────────────
    ws_md = wb.create_sheet("Missing_DOI")
    ws_md["A1"].value = f"Missing DOI ({len(missing_doi)}) — add DOI manually then move to Screening_Sheet"
    ws_md["A1"].font  = Font(bold=True, size=12, color="8B1A1A", name="Arial")
    ws_md.merge_cells(f"A1:{get_column_letter(len(SCREEN_COLS))}1")
    ws_md.row_dimensions[1].height = 20
    write_screen(ws_md, missing_doi, row_fill_fn=lambda p: M_FILL, start_row=2)

    # ── Sheet 6: Concept Matrix ───────────────────────────────────────────────
    ws3=wb.create_sheet("Concept_Matrix_W&W")
    ws3.column_dimensions["A"].width=3; ws3.column_dimensions["B"].width=4
    ws3["C2"].value="Webster & Watson (2002) Concept Matrix"
    ws3["C2"].font=Font(bold=True,size=14,color="1F4E79",name="Arial")
    ws3.merge_cells("C2:T2")
    ws3["C3"].value="Add included papers as rows after screening. Mark with check where concept is addressed."
    ws3["C3"].font=Font(italic=True,size=9,color="595959")
    concepts=["Data\nStandards","AI-\nReadiness","Machine-\nReadable","Semantic\nAnnotation",
              "Context\nEngineering","Context\nWindow","Prompt\nDesign","Structured\nContext","Knowledge\nRepresent.",
              "Token\nEfficiency","Context\nCompression","Prompt\nCompression","RAG","Inference\nCost","Answer\nQuality","Hallucin-\nation"]
    cfills=(["D6E4F0"]*4)+["D5E8D4"]*5+["FFF2CC"]*7
    ws3.merge_cells("C5:F5"); c=ws3["C5"]
    c.value="D1: Standardization & AI"; c.fill=PatternFill("solid",start_color="1F4E79")
    c.font=Font(bold=True,color="FFFFFF",name="Arial",size=9); c.alignment=Alignment(horizontal="center")
    ws3.merge_cells("G5:K5"); c=ws3["G5"]
    c.value="D2: Context Engineering"; c.fill=PatternFill("solid",start_color="375623")
    c.font=Font(bold=True,color="FFFFFF",name="Arial",size=9); c.alignment=Alignment(horizontal="center")
    ws3.merge_cells("L5:R5"); c=ws3["L5"]
    c.value="D3: Token Efficiency"; c.fill=PatternFill("solid",start_color="7F6000")
    c.font=Font(bold=True,color="FFFFFF",name="Arial",size=9); c.alignment=Alignment(horizontal="center")
    for ci,(h,w) in enumerate([("Author(s) Year",28),("Title",40)],3):
        c=ws3.cell(row=6,column=ci,value=h)
        c.font=H_FONT; c.fill=H_FILL; c.border=BDR
        c.alignment=Alignment(horizontal="center",vertical="bottom")
        ws3.column_dimensions[get_column_letter(ci)].width=w
    for ci,(concept,cfill) in enumerate(zip(concepts,cfills),5):
        c=ws3.cell(row=6,column=ci,value=concept)
        c.fill=PatternFill("solid",start_color=cfill)
        c.font=Font(bold=True,name="Arial",size=8,color="1F4E79")
        c.alignment=Alignment(text_rotation=90,horizontal="center",vertical="bottom",wrap_text=True)
        c.border=BDR; ws3.column_dimensions[get_column_letter(ci)].width=5
    ws3.row_dimensions[6].height=80
    for ri in range(7,57):
        alt=PatternFill("solid",start_color="F8F8F8") if ri%2==0 else PatternFill()
        for ci in range(3,5+len(concepts)):
            c=ws3.cell(row=ri,column=ci,value="")
            c.border=BDR; c.fill=alt
            c.font=Font(name="Arial",size=10)
            c.alignment=Alignment(horizontal="center",vertical="center")
        ws3.row_dimensions[ri].height=18

    # ── Sheet 7: Exclusion Criteria ───────────────────────────────────────────
    ws4=wb.create_sheet("Exclusion_Criteria")
    ws4["B2"].value="Exclusion Criteria Reference (PRISMA)"
    ws4["B2"].font=Font(bold=True,size=13,color="1F4E79",name="Arial")
    ws4.column_dimensions["B"].width=65
    ecolors=["FFE0E0","FFE0E0","FFF2CC","FFF2CC","D5E8D4","D5E8D4","D6E4F0","D6E4F0"]
    for ri,crit in enumerate(EXCLUSION_CRITERIA,4):
        c=ws4.cell(row=ri,column=2,value=crit)
        c.font=Font(name="Arial",size=10)
        c.fill=PatternFill("solid",start_color=ecolors[ri-4])
        c.border=BDR; ws4.row_dimensions[ri].height=22

    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf.read()





# ── UI ────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Fraunces:wght@300;600&display=swap');
*, html, body { box-sizing: border-box; }
[class*="css"], .stApp { font-family: 'Fraunces', serif; background: #f7f4ef; color: #1a1a2e; }
h1,h2,h3 { font-family: 'JetBrains Mono', monospace; }
.stApp { background: #f7f4ef; }
.tag{display:inline-block;padding:3px 10px;border-radius:4px;font-family:'JetBrains Mono';font-size:0.72rem;font-weight:700;margin:2px;}
.tag-springer{background:#e8f4d4;color:#2d6a2d;border:1px solid #2d6a2d;}
.tag-acm{background:#fde8e8;color:#8b1a1a;border:1px solid #8b1a1a;}
.tag-scopus{background:#e8eef8;color:#1a3a8b;border:1px solid #1a3a8b;}
.tag-scholar{background:#fef8e8;color:#7a5a00;border:1px solid #7a5a00;}
.stat-box{background:#fff;border:1px solid #e0d8cc;border-radius:6px;padding:14px;text-align:center;}
.stat-num{font-family:'JetBrains Mono';font-size:1.8rem;color:#1a1a2e;font-weight:700;}
.stat-lbl{font-size:0.75rem;color:#888;text-transform:uppercase;letter-spacing:1px;}
.warn-box{background:#fff8e8;border:1px solid #e0c050;border-radius:6px;padding:10px 14px;margin:6px 0;font-size:0.85rem;}
</style>
""", unsafe_allow_html=True)

import requests as _req, time as _time, re as _re

st.markdown("# 🔬 Systematic Review Bot")
st.markdown("Upload CSV/BIB files → parse → fetch abstracts → download PRISMA Excel")
st.markdown("---")

# ── File upload ───────────────────────────────────────────────────────────────
st.markdown("### Step 1 — Upload Files")
st.markdown("Name files like `springer_d1q1.csv`, `acm_d1q2.bib`, `scopus_d2q1.csv`, `scholar_d3q1.csv`")
st.caption("Supports: Springer CSV · Scopus CSV · Google Scholar CSV (Publish or Perish) · ACM BibTeX")

uploaded = st.file_uploader("Drop all files here", type=["csv","bib"],
                              accept_multiple_files=True, label_visibility="collapsed")

if uploaded:
    st.markdown("---")

    # ── Parse ─────────────────────────────────────────────────────────────────
    all_papers, stats, parse_log = [], {"identification":{}, "total_raw":0, "duplicates":0, "after_dedup":0}, []

    for f in uploaded:
        fname = f.name.lower()
        qid = "UNKNOWN"
        for q in ["d1q1","d1q2","d2q1","d2q2","d2q3","d3q1","d3q2","d3q3"]:
            if q in fname: qid = q.upper(); break
        cf = f.read().decode("utf-8", errors="replace")
        if fname.endswith(".bib"):
            papers = parse_bib(cf, qid); db = "ACM"
        else:
            ctype = detect_csv_type(cf, fname)
            if ctype == "springer":   papers = parse_springer_csv(cf, qid);   db = "Springer"
            elif ctype in ("scopus","scopus_pop"):
                papers = parse_scopus_pop_csv(cf, qid) if ctype=="scopus_pop" else parse_scopus_csv(cf, qid)
                db = "Elsevier/Scopus"
            else:                     papers = parse_scholar_csv(cf, qid);    db = "Google Scholar"
        parse_log.append((f.name, db, qid, len(papers)))
        stats["identification"].setdefault(db,{}).setdefault(qid,0)
        stats["identification"][db][qid] += len(papers)
        all_papers.extend(papers)

    unique, dupe_list = deduplicate(all_papers)

    # Filter non-English papers (title has >30% non-ASCII = likely not English)
    def likely_english(p):
        text = (p.get("title","") + " " + p.get("source",""))
        if not text.strip(): return True
        non_ascii = sum(1 for c in text if ord(c) > 127)
        return (non_ascii / max(len(text),1)) < 0.25

    non_english = [p for p in unique if not likely_english(p)]
    unique = [p for p in unique if likely_english(p)]

    stats.update({"total_raw":len(all_papers),"duplicates":len(dupe_list),
                  "after_dedup":len(unique),"non_english":len(non_english)})
    missing_year = [p for p in unique if not str(p.get("year","")).strip().isdigit() or not is_valid_year(p.get("year",""))]
    missing_doi  = [p for p in unique if not p.get("doi","").strip()]

    # ── Show parse log ────────────────────────────────────────────────────────
    st.markdown("### Step 2 — Files Parsed")
    for fname, db, qid, n in parse_log:
        db_cls = {"Springer":"springer","ACM":"acm","Elsevier/Scopus":"scopus","Google Scholar":"scholar"}.get(db,"springer")
        st.markdown(f"`{fname}` → <span class='tag tag-{db_cls}'>{db}</span> `{qid}` → **{n} papers**", unsafe_allow_html=True)

    # ── Summary ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Step 3 — Summary")
    c1,c2,c3,c4 = st.columns(4)
    with c1: st.markdown(f'<div class="stat-box"><div class="stat-num">{stats["total_raw"]}</div><div class="stat-lbl">Total Raw</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="stat-box"><div class="stat-num">{len(dupe_list)}</div><div class="stat-lbl">Duplicates Removed</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="stat-box"><div class="stat-num">{stats["after_dedup"]}</div><div class="stat-lbl">Unique Papers</div></div>', unsafe_allow_html=True)
    with c4:
        d_counts = {}
        for p in unique:
            d = p.get("dimension","")[:2]; d_counts[d] = d_counts.get(d,0)+1
        summary = " / ".join(f"{k}:{v}" for k,v in sorted(d_counts.items()))
        st.markdown(f'<div class="stat-box"><div class="stat-num" style="font-size:1.1rem">{summary}</div><div class="stat-lbl">By Dimension</div></div>', unsafe_allow_html=True)

    if missing_year:
        st.markdown(f'<div class="warn-box">⚠️ <b>{len(missing_year)} papers</b> missing year → flagged in Missing_Year sheet</div>', unsafe_allow_html=True)
    if missing_doi:
        st.markdown(f'<div class="warn-box">⚠️ <b>{len(missing_doi)} papers</b> missing DOI → flagged in Missing_DOI sheet</div>', unsafe_allow_html=True)

    # ── GENERATE BUTTON ───────────────────────────────────────────────────────
    st.markdown("---")
    need_abstract = [p for p in unique if p.get("doi","").strip() or p.get("url","").strip()]
    est_mins = max(1, len(need_abstract) // 10)
    st.markdown(f"### Step 4 — Generate Excel")
    st.markdown(f"Will fetch abstracts for **{len(need_abstract)} papers** via DOI/URL (~{est_mins} min)")

    fetch_toggle = st.checkbox("Fetch abstracts automatically", value=True)

    generate_clicked = st.button("🚀 Generate Excel", type="primary", use_container_width=True)

    if generate_clicked:
        # Store result in session state so download doesn't re-trigger
        def is_english(text):
            """Quick check — if >30% non-ASCII chars, likely not English"""
            if not text: return True
            non_ascii = sum(1 for c in text if ord(c) > 127)
            return (non_ascii / len(text)) < 0.3

        def fetch_by_doi(doi):
            """Try CrossRef then Semantic Scholar. One attempt each, no retry."""
            if not doi: return ""
            try:
                r = _req.get(f"https://api.crossref.org/works/{doi}",
                    headers={"User-Agent":"SystematicReview/1.0"}, timeout=6)
                if r.ok:
                    abstract = r.json().get("message",{}).get("abstract","")
                    if abstract:
                        abstract = _re.sub(r"<[^>]+>","",abstract).strip()
                        if is_english(abstract): return abstract
            except: pass
            try:
                r2 = _req.get(f"https://api.semanticscholar.org/graph/v1/paper/{doi}",
                    params={"fields":"abstract"}, timeout=6)
                if r2.ok:
                    abstract = r2.json().get("abstract","")
                    if abstract and is_english(abstract): return abstract
            except: pass
            return ""

        def fetch_by_url(url):
            """Scrape abstract from URL page. One attempt, no retry."""
            from bs4 import BeautifulSoup
            if not url: return ""
            # Build doi.org URL if it looks like a DOI
            try:
                r = _req.get(url, headers={"User-Agent":"Mozilla/5.0 (compatible; AcademicResearch/1.0)"},
                    timeout=8, allow_redirects=True)
                if not r.ok: return ""
                soup = BeautifulSoup(r.text,"html.parser")
                for sel in ["div.abstract","section.Abstract","div#abstract",
                            "div.abstractSection","p.abstract","#Abs1-content",
                            "div[class*=abstract]","section[class*=abstract]",
                            "meta[name=description]","meta[property='og:description']"]:
                    el = soup.select_one(sel)
                    if el:
                        text = el.get("content","") if el.name=="meta" else el.get_text(" ",strip=True)
                        if len(text) > 80 and is_english(text): return text
            except: pass
            return ""

        def build_doi_url(doi):
            """Convert DOI to doi.org URL"""
            if not doi: return ""
            doi = doi.strip()
            if doi.startswith("http"): return doi
            return f"https://doi.org/{doi}"

        if fetch_toggle and need_abstract:
            prog  = st.progress(0)
            s_txt = st.empty()
            p_txt = st.empty()
            found = 0
            t0    = _time.time()

            for i, p in enumerate(need_abstract):
                doi = p.get("doi","").strip()
                url = p.get("url","").strip()
                title = p.get("title","")[:40]
                elapsed = _time.time() - t0
                if i > 0:
                    rem = (elapsed/i) * (len(need_abstract)-i)
                    m,s = divmod(int(rem),60)
                    t_str = f"{m}m {s}s remaining"
                else:
                    t_str = "estimating..."
                pct = int((i+1)/len(need_abstract)*100)
                s_txt.markdown(f"**({i+1}/{len(need_abstract)})** `{title}...`")
                p_txt.markdown(f"**{pct}%** · ⏱ {t_str} · ✅ {found} fetched")
                prog.progress(pct/100)

                abstract = ""
                if doi:
                    # Try DOI-based APIs first
                    abstract = fetch_by_doi(doi)
                    _time.sleep(0.25)
                    if not abstract:
                        # Try doi.org URL as fallback
                        doi_url = build_doi_url(doi)
                        abstract = fetch_by_url(doi_url)
                        _time.sleep(0.25)
                if not abstract and url and url != build_doi_url(doi):
                    # Try original URL only if different from doi.org
                    abstract = fetch_by_url(url)
                    _time.sleep(0.25)
                if abstract:
                    p["abstract"] = abstract; found += 1

            prog.progress(1.0)
            total_sec = int(_time.time()-t0)
            s_txt.markdown(f"✅ **Done!** Fetched {found}/{len(need_abstract)} abstracts in {total_sec}s")
            p_txt.empty()

        # Build Excel once, store in session state
        excel_bytes = build_excel(unique, stats, dupe_list)
        st.session_state["excel_bytes"] = excel_bytes
        st.session_state["excel_fname"] = f"systematic_review_{datetime.now():%Y%m%d_%H%M}.xlsx"
        st.session_state["excel_ready"] = True
        abstracts_filled = sum(1 for p in unique if p.get("abstract","").strip())
        st.session_state["abstracts_filled"] = abstracts_filled
        st.session_state["total_papers"] = stats["after_dedup"]
        st.session_state["dupe_count"] = len(dupe_list)

    # ── Download (only shown after Generate) ─────────────────────────────────
    if st.session_state.get("excel_ready"):
        st.markdown("---")
        st.markdown("### Step 5 — Download")
        sheets = {
            "PRISMA_Flow":"PRISMA 2020 tracker",
            "Screening_Sheet":f"{st.session_state.get('total_papers',0)} papers",
            "Duplicates_Removed":f"{st.session_state.get('dupe_count',0)} duplicates",
            "Missing_Year":f"{len(missing_year)} — check year",
            "Missing_DOI":f"{len(missing_doi)} — add DOI",
            "Concept_Matrix_W&W":"Webster & Watson matrix",
            "Exclusion_Criteria":"E1-E8 reference",
        }
        colors = {"Duplicates_Removed":"#E8EAF6","Missing_Year":"#FFF8E8","Missing_DOI":"#FFE8E8"}
        for sheet,desc in sheets.items():
            color = colors.get(sheet,"#f0f7ff")
            st.markdown(f'<div style="background:{color};border-radius:4px;padding:6px 12px;margin:3px 0;font-size:0.85rem"><b>{sheet}</b> — {desc}</div>', unsafe_allow_html=True)
        st.markdown("")
        st.download_button("📥 Download PRISMA Excel",
            data=st.session_state["excel_bytes"],
            file_name=st.session_state["excel_fname"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True, type="primary")
        n = st.session_state.get("total_papers",0)
        a = st.session_state.get("abstracts_filled",0)
        d = st.session_state.get("dupe_count",0)
        st.success(f"✅ {n} papers · {a} with abstract · {d} dupes removed")

else:
    st.markdown("---")
    st.markdown("### File naming convention")
    st.dataframe(pd.DataFrame({
        "File":   ["springer_d1q1.csv","springer_d1q2.csv","acm_d1q1.bib","acm_d1q2.bib","scopus_d1q1.csv","scholar_d1q1.csv"],
        "DB":     ["Springer","Springer","ACM","ACM","Elsevier/Scopus","Google Scholar"],
        "Query":  ["D1Q1","D1Q2","D1Q1","D1Q2","D1Q1","D1Q1"],
        "Format": ["CSV","CSV","BibTeX","BibTeX","CSV","CSV"],
    }), use_container_width=True, hide_index=True)
    st.info("💡 Query ID (d1q1, d2q2 etc.) must be in filename.")
