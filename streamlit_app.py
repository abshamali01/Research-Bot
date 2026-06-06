"""
Systematic Review — File Importer v2
Upload CSV (Springer/Scopus/Scholar) + BIB (ACM)
→ PRISMA Excel with separate sheets for missing year / missing DOI
"""

import streamlit as st
import pandas as pd
import io, re, csv
from datetime import datetime

st.set_page_config(page_title="SR Importer", page_icon="📥", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Fraunces:wght@300;600&display=swap');
*, html, body { box-sizing: border-box; }
[class*="css"], .stApp { font-family: 'Fraunces', serif; background: #f7f4ef; color: #1a1a2e; }
h1,h2,h3 { font-family: 'JetBrains Mono', monospace; }
.stApp { background: #f7f4ef; }
.tag { display: inline-block; padding: 3px 10px; border-radius: 4px; font-family: 'JetBrains Mono'; font-size: 0.72rem; font-weight: 700; margin: 2px; }
.tag-springer { background: #e8f4d4; color: #2d6a2d; border: 1px solid #2d6a2d; }
.tag-acm      { background: #fde8e8; color: #8b1a1a; border: 1px solid #8b1a1a; }
.tag-scopus   { background: #e8eef8; color: #1a3a8b; border: 1px solid #1a3a8b; }
.tag-scholar  { background: #fef8e8; color: #7a5a00; border: 1px solid #7a5a00; }
.stat-box { background: #fff; border: 1px solid #e0d8cc; border-radius: 6px; padding: 14px; text-align: center; }
.stat-num { font-family: 'JetBrains Mono'; font-size: 1.8rem; color: #1a1a2e; font-weight: 700; }
.stat-lbl { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 1px; }
.warn-box { background: #fff8e8; border: 1px solid #e0c050; border-radius: 6px; padding: 10px 14px; margin: 6px 0; font-size: 0.85rem; }
section[data-testid="stFileUploadDropzone"] { background: #fff !important; border: 2px dashed #c8b99a !important; }
</style>
""", unsafe_allow_html=True)

QUERY_MAP = {
    "D1Q1": "D1_Standardization_AI", "D1Q2": "D1_Standardization_AI",
    "D2Q1": "D2_Context_Engineering", "D2Q2": "D2_Context_Engineering", "D2Q3": "D2_Context_Engineering",
    "D3Q1": "D3_Token_Efficiency",   "D3Q2": "D3_Token_Efficiency",   "D3Q3": "D3_Token_Efficiency",
}

EXCLUSION_CRITERIA = [
    "E1: Outside year range (2015–2026)", "E2: Not English",
    "E3: Not journal/conference/review paper", "E4: Not relevant to dimension topic",
    "E5: Duplicate", "E6: Full text not accessible",
    "E7: Abstract only / insufficient detail", "E8: Not peer-reviewed",
]

# ─── Parsers ──────────────────────────────────────────────────────────────────

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
                "url":      row.get("URL","").strip(),
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
                "abstract": row.get("Abstract","").strip(),
                "url":      row.get("Link","").strip(),
                "type":     row.get("Document Type","").strip(),
                "database": "Elsevier/Scopus", "query_id": query_id,
                "dimension": QUERY_MAP.get(query_id,""),
            })
    except Exception as e:
        st.warning(f"Scopus parse error: {e}")
    return papers


def parse_scopus_pop_csv(content, query_id):
    """Parse Scopus CSV exported via Publish or Perish (different columns than direct Scopus export)"""
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
                "abstract": row.get("Abstract","").strip(),
                "url":      row.get("ArticleURL","").strip(),
                "type":     row.get("Type","Article").strip(),
                "database": "Elsevier/Scopus", "query_id": query_id,
                "dimension": QUERY_MAP.get(query_id,""),
            })
    except Exception as e:
        import streamlit as st
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
                "source":   row.get("Publication","").strip(),
                "doi":      row.get("DOI","").strip(),
                "abstract": row.get("Abstract","").strip(),
                "url":      row.get("URL","").strip(),
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
            "abstract": get_field("abstract", entry)[:300],
            "url":      get_field("url", entry),
            "type":     "Conference Paper" if "inproceedings" in entry[:30].lower() else "Article",
            "database": "ACM", "query_id": query_id,
            "dimension": QUERY_MAP.get(query_id,""),
        })
    return [p for p in papers if p["title"]]

def detect_csv_type(content, fname=""):
    first  = content.split('\n')[0].lower()
    second = content.split('\n')[1].lower() if len(content.split('\n')) > 1 else ""
    # Filename priority
    if "scopus"   in fname: return "scopus_pop"
    if "springer" in fname: return "springer"
    if "scholar"  in fname: return "scholar"
    # Header detection
    if "item title"   in first: return "springer"
    if "source title" in first: return "scopus"
    # Scopus via Publish or Perish — has scopus.com URLs in data rows
    if "scopus.com" in second:  return "scopus_pop"
    return "scholar"

def deduplicate(papers):
    seen_doi, seen_title, unique, dupes = set(), set(), [], 0
    for p in papers:
        doi   = p.get("doi","").strip().lower()
        title = p.get("title","").strip().lower()[:80]
        key   = doi if doi else title
        if key and key in seen_doi:       dupes += 1; continue
        if key:                            seen_doi.add(key)
        if title and title in seen_title:  dupes += 1; continue
        if title:                          seen_title.add(title)
        unique.append(p)
    return unique, dupes

def is_valid_year(y):
    return str(y).strip().isdigit() and 2015 <= int(str(y).strip()) <= 2026

# ─── Excel Builder ────────────────────────────────────────────────────────────

def build_excel(papers, stats):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    H_FILL  = PatternFill("solid", start_color="1F4E79")
    H_FONT  = Font(bold=True, color="FFFFFF", name="Arial", size=10)
    W_FILL  = PatternFill("solid", start_color="FFF2CC")  # warning yellow
    M_FILL  = PatternFill("solid", start_color="FFE0E0")  # missing red
    THIN    = Side(style="thin", color="BFBFBF")
    BDR     = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    DIM_CLR = {"D1":"D6E4F0","D2":"D5E8D4","D3":"FFF2CC"}
    PH_CLR  = {"Identification":"D6E4F0","Screening":"D5E8D4","Eligibility":"FFF2CC","Included":"FCE4D6"}

    # Categorize papers
    main_papers    = [p for p in papers if is_valid_year(p.get("year","")) and p.get("doi","").strip()]
    missing_year   = [p for p in papers if not str(p.get("year","")).strip().isdigit() or not is_valid_year(p.get("year",""))]
    missing_doi    = [p for p in papers if not p.get("doi","").strip() and is_valid_year(p.get("year",""))]

    wb = openpyxl.Workbook()

    # ─── Helper: write screening columns ──────────────────────────────────────
    SCREEN_COLS = [
        ("ID",6),("Dimension",18),("Query ID",8),("Database",14),("Title",42),
        ("Authors",22),("Year",6),("Source / Journal",24),("DOI",26),("URL",26),
        ("Abstract (snippet)",45),("Title Screen\nY/N",10),("Title Screen\nReason",22),
        ("Abstract Screen\nY/N",10),("Abstract Screen\nReason",22),
        ("Full Text\nRetrieved?",10),("Eligible?\nY/N",10),
        ("Exclusion\nReason",20),("Included\nFinal Y/N",10),("Notes",28),
    ]

    def write_screening_sheet(ws, paper_list, fill_override=None):
        ws.freeze_panes = "A2"
        for ci,(name,width) in enumerate(SCREEN_COLS,1):
            c = ws.cell(row=1, column=ci, value=name)
            c.font=H_FONT; c.fill=H_FILL; c.border=BDR
            c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
            ws.column_dimensions[get_column_letter(ci)].width=width
        ws.row_dimensions[1].height=36
        for ri,p in enumerate(paper_list,2):
            dk = p.get("dimension","")[:2]
            fill = fill_override or PatternFill("solid", start_color=DIM_CLR.get(dk,"FFFFFF"))
            vals = [f"{dk}_{ri-1:04d}",p.get("dimension",""),p.get("query_id",""),
                    p.get("database",""),p.get("title",""),p.get("authors","")[:120],
                    p.get("year",""),p.get("source","")[:60],p.get("doi",""),
                    p.get("url","")[:100],p.get("abstract","")[:250],
                    "","","","","","","","",""]
            for ci,val in enumerate(vals,1):
                c=ws.cell(row=ri,column=ci,value=val)
                c.fill=fill; c.border=BDR
                c.font=Font(name="Arial",size=9)
                c.alignment=Alignment(wrap_text=True,vertical="top")
        ws.auto_filter.ref=f"A1:{get_column_letter(len(SCREEN_COLS))}{len(paper_list)+1}"

    # ── Sheet 1: PRISMA Flow ──────────────────────────────────────────────────
    ws = wb.active; ws.title = "PRISMA_Flow"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 3
    ws["B2"].value = "PRISMA 2020 Flow Tracker"
    ws["B2"].font  = Font(bold=True, size=14, color="1F4E79", name="Arial")
    ws.merge_cells("B2:H2")

    # Summary stats for PRISMA
    total_raw      = stats.get("total_raw", 0)
    total_dupes    = stats.get("duplicates", 0)
    after_dedup    = stats.get("after_dedup", 0)
    n_missing_year = len(missing_year)
    n_missing_doi  = len(missing_doi)
    n_main         = len(main_papers)

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
        ["Identification", "Total records identified",          "All","ALL", total_raw,      "", "Sum of all DB results"],
        ["Identification", "Duplicate records removed",         "All","ALL", total_dupes,    "", "Deduped by DOI + Title"],
        ["Identification", "Records after deduplication",       "All","ALL", after_dedup,    "", ""],
        ["Screening",      "Records screened (title/abstract)", "All","ALL", after_dedup,    "", "Manual screening required"],
        ["Screening",      "⚠ Missing year — manual check",     "All","ALL", n_missing_year, "", "See 'Missing_Year' sheet"],
        ["Screening",      "⚠ Missing DOI — manual check",      "All","ALL", n_missing_doi,  "", "See 'Missing_DOI' sheet"],
        ["Screening",      "Records with year + DOI (main)",    "All","ALL", n_main,         "", "See 'Screening_Sheet'"],
        ["Screening",      "Records excluded — title screen",   "All","ALL", "",             "", "Fill after manual screening"],
        ["Screening",      "Records excluded — abstract screen","All","ALL", "",             "", "Fill after manual screening"],
        ["Screening",      "Reports sought for retrieval",      "All","ALL", "",             "", ""],
        ["Screening",      "Reports not retrieved",             "All","ALL", "",             "", ""],
        ["Eligibility",    "Reports assessed for eligibility",  "All","ALL", "",             "", ""],
        ["Eligibility",    "Reports excluded with reasons",     "All","ALL", "",             "", "E1–E8 (see Exclusion_Criteria)"],
        ["Included",       "Studies included in final review",  "All","ALL", "",             "", "Fill after full screening"],
    ]

    for ri,row in enumerate(rows,5):
        fill = PatternFill("solid", start_color=PH_CLR.get(row[0],"FFFFFF"))
        # Warning rows get yellow
        if "⚠" in str(row[1]):
            fill = W_FILL
        for ci,val in enumerate(row,2):
            c=ws.cell(row=ri,column=ci,value=val)
            c.fill=fill; c.border=BDR
            c.font=Font(name="Arial",size=9)
            c.alignment=Alignment(wrap_text=True,vertical="center")

    # ── Sheet 2: Main Screening Sheet (has year + DOI) ────────────────────────
    ws2 = wb.create_sheet("Screening_Sheet")
    write_screening_sheet(ws2, main_papers)

    # ── Sheet 3: Missing Year ─────────────────────────────────────────────────
    ws_my = wb.create_sheet("Missing_Year")
    ws_my["B1"].value = f"⚠ Papers with missing or invalid year ({len(missing_year)} papers) — verify manually"
    ws_my["B1"].font  = Font(bold=True, size=12, color="7F6000", name="Arial")
    ws_my.merge_cells("B1:T1")
    ws_my.row_dimensions[1].height = 22

    # Write header on row 2
    for ci,(name,width) in enumerate(SCREEN_COLS,1):
        c=ws_my.cell(row=2,column=ci,value=name)
        c.font=H_FONT; c.fill=PatternFill("solid",start_color="7F6000"); c.border=BDR
        c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
        ws_my.column_dimensions[get_column_letter(ci)].width=width
    ws_my.row_dimensions[2].height=36
    ws_my.freeze_panes="A3"

    for ri,p in enumerate(missing_year,3):
        dk = p.get("dimension","")[:2]
        vals=[f"MY_{ri-2:04d}",p.get("dimension",""),p.get("query_id",""),
              p.get("database",""),p.get("title",""),p.get("authors","")[:120],
              p.get("year","") or "MISSING",p.get("source","")[:60],p.get("doi",""),
              p.get("url","")[:100],p.get("abstract","")[:250],
              "","","","","","","","",""]
        for ci,val in enumerate(vals,1):
            c=ws_my.cell(row=ri,column=ci,value=val)
            c.fill=W_FILL; c.border=BDR
            c.font=Font(name="Arial",size=9)
            c.alignment=Alignment(wrap_text=True,vertical="top")
    ws_my.auto_filter.ref=f"A2:{get_column_letter(len(SCREEN_COLS))}{len(missing_year)+2}"

    # ── Sheet 4: Missing DOI ──────────────────────────────────────────────────
    ws_md = wb.create_sheet("Missing_DOI")
    ws_md["B1"].value = f"⚠ Papers with missing DOI ({len(missing_doi)} papers) — verify + add DOI manually"
    ws_md["B1"].font  = Font(bold=True, size=12, color="8B1A1A", name="Arial")
    ws_md.merge_cells("B1:T1")
    ws_md.row_dimensions[1].height = 22

    # Extra column: Manual DOI entry
    DOI_COLS = SCREEN_COLS + [("Manual DOI\n(fill here)", 30)]
    for ci,(name,width) in enumerate(DOI_COLS,1):
        c=ws_md.cell(row=2,column=ci,value=name)
        c.font=H_FONT; c.fill=PatternFill("solid",start_color="8B1A1A"); c.border=BDR
        c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
        ws_md.column_dimensions[get_column_letter(ci)].width=width
    ws_md.row_dimensions[2].height=36
    ws_md.freeze_panes="A3"

    for ri,p in enumerate(missing_doi,3):
        dk=p.get("dimension","")[:2]
        vals=[f"MD_{ri-2:04d}",p.get("dimension",""),p.get("query_id",""),
              p.get("database",""),p.get("title",""),p.get("authors","")[:120],
              p.get("year",""),p.get("source","")[:60],"DOI MISSING",
              p.get("url","")[:100],p.get("abstract","")[:250],
              "","","","","","","","","",""]
        for ci,val in enumerate(vals,1):
            c=ws_md.cell(row=ri,column=ci,value=val)
            c.fill=M_FILL; c.border=BDR
            c.font=Font(name="Arial",size=9)
            c.alignment=Alignment(wrap_text=True,vertical="top")
    ws_md.auto_filter.ref=f"A2:{get_column_letter(len(DOI_COLS))}{len(missing_doi)+2}"

    # ── Sheet 5: Concept Matrix ───────────────────────────────────────────────
    ws3=wb.create_sheet("Concept_Matrix_W&W")
    ws3.column_dimensions["A"].width=3; ws3.column_dimensions["B"].width=4
    ws3["C2"].value="Webster & Watson (2002) Concept Matrix"
    ws3["C2"].font=Font(bold=True,size=14,color="1F4E79",name="Arial")
    ws3.merge_cells("C2:T2")
    ws3["C3"].value="✓ = concept addressed. Add included papers as rows after full screening."
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

    # ── Sheet 6: Exclusion Criteria ───────────────────────────────────────────
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


# ─── UI ───────────────────────────────────────────────────────────────────────

st.markdown("# 📥 Systematic Review — File Importer")
st.markdown("Upload exported files → auto-parse → PRISMA Excel with quality checks")
st.markdown("---")

st.markdown("### Step 1 — Upload Files")
st.markdown("Name files like `springer_d1q1.csv`, `acm_d1q2.bib`, `scopus_d2q1.csv`, `scholar_d3q1.csv`")
st.caption("Supported: Springer CSV · Scopus CSV · Google Scholar CSV (Publish or Perish) · ACM BibTeX (.bib)")

uploaded = st.file_uploader("Drop all files here", type=["csv","bib"],
                              accept_multiple_files=True, label_visibility="collapsed")

if uploaded:
    all_papers = []
    stats = {"identification": {}, "total_raw": 0, "duplicates": 0, "after_dedup": 0}
    parse_log = []

    for f in uploaded:
        fname = f.name.lower()
        qid = "UNKNOWN"
        for q in ["d1q1","d1q2","d2q1","d2q2","d2q3","d3q1","d3q2","d3q3"]:
            if q in fname: qid = q.upper(); break

        content = f.read().decode("utf-8", errors="replace")

        if fname.endswith(".bib"):
            papers = parse_bib(content, qid); db = "ACM"
        else:
            ctype = detect_csv_type(content, fname)
            if ctype == "springer":
                papers = parse_springer_csv(content, qid); db = "Springer"
            elif ctype in ("scopus", "scopus_pop"):
                papers = parse_scopus_pop_csv(content, qid) if ctype == "scopus_pop" else parse_scopus_csv(content, qid)
                db = "Elsevier/Scopus"
            else:
                papers = parse_scholar_csv(content, qid); db = "Google Scholar"

        parse_log.append((f.name, db, qid, len(papers)))
        stats["identification"].setdefault(db,{}).setdefault(qid,0)
        stats["identification"][db][qid] += len(papers)
        all_papers.extend(papers)

    unique, dupes = deduplicate(all_papers)
    stats.update({"total_raw": len(all_papers), "duplicates": dupes, "after_dedup": len(unique)})

    # Categorize
    main_papers  = [p for p in unique if is_valid_year(p.get("year","")) and p.get("doi","").strip()]
    missing_year = [p for p in unique if not str(p.get("year","")).strip().isdigit() or not is_valid_year(p.get("year",""))]
    missing_doi  = [p for p in unique if not p.get("doi","").strip() and is_valid_year(p.get("year",""))]

    # ── Step 2: Parse log
    st.markdown("### Step 2 — Files Parsed")
    for fname, db, qid, n in parse_log:
        db_cls = {"Springer":"springer","ACM":"acm","Elsevier/Scopus":"scopus","Google Scholar":"scholar"}.get(db,"springer")
        st.markdown(
            f'`{fname}` → <span class="tag tag-{db_cls}">{db}</span> `{qid}` → **{n} papers**',
            unsafe_allow_html=True)

    # ── Step 3: Summary
    st.markdown("---")
    st.markdown("### Step 3 — Summary")
    c1,c2,c3,c4 = st.columns(4)
    with c1: st.markdown(f'<div class="stat-box"><div class="stat-num">{stats["total_raw"]}</div><div class="stat-lbl">Total Raw</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="stat-box"><div class="stat-num">{stats["duplicates"]}</div><div class="stat-lbl">Duplicates Removed</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="stat-box"><div class="stat-num">{stats["after_dedup"]}</div><div class="stat-lbl">Unique Papers</div></div>', unsafe_allow_html=True)
    with c4:
        d_counts = {}
        for p in unique:
            d = p.get("dimension","")[:2]
            d_counts[d] = d_counts.get(d,0)+1
        summary = " / ".join(f"{k}:{v}" for k,v in sorted(d_counts.items()))
        st.markdown(f'<div class="stat-box"><div class="stat-num" style="font-size:1.1rem">{summary}</div><div class="stat-lbl">By Dimension</div></div>', unsafe_allow_html=True)

    st.markdown("")
    c5,c6,c7 = st.columns(3)
    with c5: st.markdown(f'<div class="stat-box"><div class="stat-num" style="color:#2d6a2d">{len(main_papers)}</div><div class="stat-lbl">✅ Main (year + DOI)</div></div>', unsafe_allow_html=True)
    with c6: st.markdown(f'<div class="stat-box"><div class="stat-num" style="color:#7F6000">{len(missing_year)}</div><div class="stat-lbl">⚠ Missing Year</div></div>', unsafe_allow_html=True)
    with c7: st.markdown(f'<div class="stat-box"><div class="stat-num" style="color:#8B1A1A">{len(missing_doi)}</div><div class="stat-lbl">⚠ Missing DOI</div></div>', unsafe_allow_html=True)

    # Warnings
    if missing_year:
        st.markdown(f'<div class="warn-box">⚠️ <b>{len(missing_year)} papers</b> have missing/invalid year → exported to <b>Missing_Year</b> sheet for manual review</div>', unsafe_allow_html=True)
    if missing_doi:
        st.markdown(f'<div class="warn-box">⚠️ <b>{len(missing_doi)} papers</b> have no DOI → exported to <b>Missing_DOI</b> sheet — add DOIs manually then move to Screening_Sheet</div>', unsafe_allow_html=True)

    # ── Step 4: Preview
    st.markdown("---")
    st.markdown("### Step 4 — Preview (first 100 main papers)")
    df = pd.DataFrame([{
        "QID": p.get("query_id",""), "DB": p.get("database",""),
        "Year": p.get("year",""), "Type": p.get("type",""),
        "Title": p.get("title","")[:70], "Authors": p.get("authors","")[:40],
        "DOI": p.get("doi",""),
    } for p in main_papers[:100]])
    st.dataframe(df, use_container_width=True, height=300)

    # ── Step 5: Excel sheets breakdown
    st.markdown("---")
    st.markdown("### Step 5 — Excel Output (6 sheets)")
    sheets_info = {
        "PRISMA_Flow":        f"PRISMA 2020 tracker — all counts auto-filled",
        "Screening_Sheet":    f"{len(main_papers)} papers with valid year + DOI",
        "Missing_Year":       f"{len(missing_year)} papers — check year manually",
        "Missing_DOI":        f"{len(missing_doi)} papers — add DOI manually",
        "Concept_Matrix_W&W": "Webster & Watson matrix — fill after screening",
        "Exclusion_Criteria": "E1–E8 reference",
    }
    for sheet, desc in sheets_info.items():
        color = "#FFE0E0" if "Missing" in sheet else "#f0f7ff"
        st.markdown(f'<div style="background:{color};border-radius:4px;padding:6px 12px;margin:3px 0;font-family:JetBrains Mono,monospace;font-size:0.85rem"><b>{sheet}</b> — {desc}</div>', unsafe_allow_html=True)

    # ── Download
    st.markdown("---")
    excel_bytes = build_excel(unique, stats)
    fname_out = f"systematic_review_{datetime.now():%Y%m%d_%H%M}.xlsx"
    st.download_button(
        label="📥 Download PRISMA Excel",
        data=excel_bytes, file_name=fname_out,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True, type="primary",
    )
    st.success(f"✅ Done! {stats['after_dedup']} unique papers → {len(main_papers)} main + {len(missing_year)} missing year + {len(missing_doi)} missing DOI")

else:
    st.markdown("---")
    st.markdown("### File naming convention")
    st.dataframe(pd.DataFrame({
        "File":   ["springer_d1q1.csv","springer_d1q2.csv","acm_d1q1.bib","acm_d1q2.bib","scopus_d1q1.csv","scholar_d1q1.csv"],
        "DB":     ["Springer","Springer","ACM","ACM","Elsevier/Scopus","Google Scholar"],
        "Query":  ["D1Q1","D1Q2","D1Q1","D1Q2","D1Q1","D1Q1"],
        "Format": ["CSV","CSV","BibTeX","BibTeX","CSV","CSV"],
    }), use_container_width=True, hide_index=True)
    st.info("💡 Query ID (d1q1, d2q2 etc.) must be in filename — app uses it to assign papers to correct dimension.")
