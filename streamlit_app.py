"""
Systematic Review Bot — Streamlit Web App
==========================================
Deploy free on Streamlit Cloud (share.streamlit.io)
"""

import streamlit as st
import os, json, time, urllib.parse, io
from datetime import datetime

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Systematic Review Bot",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
h1, h2, h3 { font-family: 'IBM Plex Mono', monospace; }

.stApp { background: #0d1117; color: #e6edf3; }

.metric-card {
    background: #161b22; border: 1px solid #30363d;
    border-radius: 6px; padding: 16px; text-align: center;
}
.metric-card .num { font-family: 'IBM Plex Mono'; font-size: 2rem; color: #58a6ff; font-weight: 600; }
.metric-card .lbl { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }

.dim-badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 0.72rem; font-family: 'IBM Plex Mono'; font-weight: 600;
}
.dim-d1 { background: #1c2d4f; color: #79c0ff; border: 1px solid #2d5a9e; }
.dim-d2 { background: #1a2e1a; color: #7ee787; border: 1px solid #2d5e2d; }
.dim-d3 { background: #2e2a14; color: #e3b341; border: 1px solid #5e4e14; }

.log-line { font-family: 'IBM Plex Mono'; font-size: 0.8rem; color: #8b949e; padding: 2px 0; }
.log-ok   { color: #3fb950; }
.log-err  { color: #f85149; }
.log-info { color: #58a6ff; }

.section-header {
    border-left: 3px solid #58a6ff; padding-left: 12px;
    font-family: 'IBM Plex Mono'; color: #e6edf3;
}
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔬 Systematic Review Bot")
    st.markdown("---")
    st.markdown("### API Keys")

    springer_meta = st.text_input("Springer Meta API Key", type="password",
                                   value="37be5cdf1b66a6aa4b77de297dcc4ec8")
    springer_oa   = st.text_input("Springer Open Access Key", type="password",
                                   value="547069e6b9af47166cfa75f20d815009")
    elsevier_key  = st.text_input("Elsevier / Scopus API Key", type="password",
                                   value="76e7e8b25be92da632764cabd04e2a64")

    st.markdown("---")
    st.markdown("### Search Parameters")
    year_start = st.number_input("Year From", min_value=2000, max_value=2026, value=2015)
    year_end   = st.number_input("Year To",   min_value=2000, max_value=2026, value=2026)
    max_per_db = st.slider("Max results per DB per query", 10, 100, 50, 10)

    st.markdown("---")
    st.markdown("### Databases")
    use_springer = st.checkbox("Springer",       value=True)
    use_elsevier = st.checkbox("Elsevier/Scopus",value=True)
    use_acm      = st.checkbox("ACM Digital Library", value=True)
    use_scholar  = st.checkbox("Google Scholar", value=True)

    st.markdown("---")
    st.markdown("### Dimensions")
    use_d1 = st.checkbox("D1 — Standardization & AI", value=True)
    use_d2 = st.checkbox("D2 — Context Engineering",  value=True)
    use_d3 = st.checkbox("D3 — Token Efficiency",     value=True)

    st.markdown("---")
    st.caption("PRISMA 2020 | Webster & Watson")
    st.caption("Uni Koblenz — HiWi Project")

# ─── Search Strings ───────────────────────────────────────────────────────────
ALL_SEARCH_STRINGS = {
    "D1_Standardization_AI": [
        {"id":"D1Q1","label":"Standards + AI-readiness + LLM",
         "generic":'("data standards" OR "technical standards" OR "semantic standards" OR "standardization") AND ("machine-readable" OR "AI-ready" OR "AI-native" OR "digital-ready") AND ("large language models" OR "LLM" OR "generative AI")',
         "springer":'("data standards" OR "technical standards") AND ("machine-readable" OR "AI-ready") AND ("large language models" OR "generative AI")',
         "elsevier":'TITLE-ABS-KEY(("data standards" OR "technical standards") AND ("machine-readable" OR "AI-ready") AND ("large language models" OR "LLM"))',
         "acm":'"data standards" AND "machine-readable" AND ("large language models" OR "LLM")',},
        {"id":"D1Q2","label":"Digital standards + Ontology + Automation",
         "generic":'("machine-readable standards" OR "digital standards") AND ("semantic annotation" OR "metadata" OR "ontology") AND ("automation" OR "compliance" OR "validation")',
         "springer":'("machine-readable standards" OR "digital standards") AND ("ontology" OR "semantic annotation") AND ("automation" OR "compliance")',
         "elsevier":'TITLE-ABS-KEY(("machine-readable standards" OR "digital standards") AND ("semantic annotation" OR "ontology") AND ("automation" OR "compliance"))',
         "acm":'"machine-readable standards" AND (ontology OR "semantic annotation") AND (automation OR compliance)',},
    ],
    "D2_Context_Engineering": [
        {"id":"D2Q1","label":"LLM + Context Engineering + Structured Data",
         "generic":'("large language models" OR "LLM") AND ("context engineering" OR "context design" OR "context construction" OR "context provisioning") AND ("structured data" OR "knowledge representation")',
         "springer":'("large language models" OR LLM) AND ("context engineering" OR "context provisioning") AND ("structured data" OR "knowledge representation")',
         "elsevier":'TITLE-ABS-KEY(("large language models" OR "LLM") AND ("context engineering" OR "context design" OR "context provisioning") AND ("structured data" OR "knowledge representation"))',
         "acm":'("large language models" OR LLM) AND ("context engineering" OR "context provisioning")',},
        {"id":"D2Q2","label":"LLM + Context Window + Hallucination",
         "generic":'("large language models" OR "LLM") AND ("prompt context" OR "context window" OR "context selection") AND ("answer quality" OR "accuracy" OR "hallucination")',
         "springer":'("large language models" OR LLM) AND ("context window" OR "context selection") AND ("hallucination" OR "accuracy")',
         "elsevier":'TITLE-ABS-KEY(("large language models" OR "LLM") AND ("context window" OR "context selection") AND ("accuracy" OR "hallucination"))',
         "acm":'("large language models" OR LLM) AND ("context window" OR "context selection") AND (hallucination OR accuracy)',},
        {"id":"D2Q3","label":"Semantic Context + LLM + Efficiency",
         "generic":'("structured context" OR "semantic context" OR "context package") AND ("large language models" OR "LLM") AND ("efficiency" OR "token efficiency" OR "cost")',
         "springer":'("structured context" OR "semantic context") AND ("large language models" OR LLM) AND (efficiency OR cost)',
         "elsevier":'TITLE-ABS-KEY(("structured context" OR "semantic context") AND ("large language models" OR "LLM") AND ("token efficiency" OR "efficiency"))',
         "acm":'("structured context" OR "semantic context") AND ("large language models" OR LLM) AND (efficiency OR cost)',},
    ],
    "D3_Token_Efficiency": [
        {"id":"D3Q1","label":"LLM + Token/Context Compression + Performance",
         "generic":'("large language models" OR "LLM") AND ("token efficiency" OR "context compression" OR "prompt compression") AND ("answer quality" OR "accuracy" OR "performance")',
         "springer":'("large language models" OR LLM) AND ("token efficiency" OR "context compression" OR "prompt compression") AND (accuracy OR performance)',
         "elsevier":'TITLE-ABS-KEY(("large language models" OR "LLM") AND ("token efficiency" OR "context compression" OR "prompt compression") AND ("accuracy" OR "performance"))',
         "acm":'("large language models" OR LLM) AND ("token efficiency" OR "context compression" OR "prompt compression")',},
        {"id":"D3Q2","label":"LLM + Cost Efficiency + RAG",
         "generic":'("large language models" OR "LLM") AND ("cost efficiency" OR "inference cost" OR "token cost") AND ("retrieval augmented generation" OR "RAG" OR "context selection")',
         "springer":'("large language models" OR LLM) AND ("inference cost" OR "token cost") AND ("retrieval augmented generation" OR RAG)',
         "elsevier":'TITLE-ABS-KEY(("large language models" OR "LLM") AND ("inference cost" OR "cost efficiency") AND ("retrieval augmented generation" OR "RAG"))',
         "acm":'("large language models" OR LLM) AND ("inference cost" OR "token cost") AND (RAG OR "retrieval augmented generation")',},
        {"id":"D3Q3","label":"Context Pruning + LLM + QA",
         "generic":'("context compression" OR "prompt compression" OR "context pruning") AND ("large language models" OR "LLM") AND ("question answering" OR "document QA")',
         "springer":'("context compression" OR "prompt compression" OR "context pruning") AND ("large language models" OR LLM) AND ("question answering")',
         "elsevier":'TITLE-ABS-KEY(("context compression" OR "prompt compression" OR "context pruning") AND ("large language models" OR "LLM") AND ("question answering" OR "document QA"))',
         "acm":'("context compression" OR "prompt compression" OR "context pruning") AND ("large language models" OR LLM)',},
    ],
}

EXCLUSION_CRITERIA = [
    "E1: Outside year range", "E2: Not English",
    "E3: Not journal/conference paper", "E4: Not relevant to dimension",
    "E5: Duplicate", "E6: Full text not accessible",
    "E7: Abstract only / insufficient detail", "E8: Not peer-reviewed",
]

# ─── Searcher functions ───────────────────────────────────────────────────────

def search_springer(query, api_key, year_start, year_end, max_records):
    import requests
    results, start = [], 1
    while len(results) < max_records:
        params = {"api_key": api_key, "q": query, "s": start, "p": 25,
                  "dateFrom": f"{year_start}-01-01", "dateTo": f"{year_end}-12-31"}
        try:
            r = requests.get("https://api.springernature.com/meta/v2/json", params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            records = data.get("records", [])
            if not records: break
            for rec in records:
                ctype = rec.get("contentType","").lower()
                if not any(t in ctype for t in ["article","chapter","conference"]): continue
                results.append({
                    "title":    rec.get("title",""),
                    "authors":  "; ".join(a.get("creator","") for a in rec.get("creators",[])),
                    "year":     rec.get("publicationDate","")[:4],
                    "source":   rec.get("publicationName",""),
                    "doi":      rec.get("doi",""),
                    "abstract": rec.get("abstract",""),
                    "url":      (rec.get("url",[{}])[0].get("value","") if rec.get("url") else ""),
                    "type":     rec.get("contentType",""), "database": "Springer",
                })
            total = int(data.get("result",[{}])[0].get("total",0))
            if start + 25 > min(total, max_records): break
            start += 25; time.sleep(0.5)
        except Exception as e:
            return results, str(e)
    return results, None


def search_elsevier(query, api_key, year_start, year_end, max_records):
    import requests
    results, start = [], 0
    date_q = f"({query}) AND (PUBYEAR > {year_start-1} AND PUBYEAR < {year_end+1})"
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    while len(results) < max_records:
        params = {"query": date_q, "start": start, "count": 25, "sort": "relevancy",
                  "field": "dc:title,dc:creator,prism:coverDate,prism:publicationName,prism:doi,dc:description,prism:url,subtypeDescription"}
        try:
            r = requests.get("https://api.elsevier.com/content/search/scopus",
                             headers=headers, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            entries = data.get("search-results",{}).get("entry",[])
            if not entries or entries[0].get("error"): break
            for e in entries:
                stype = e.get("subtypeDescription","").lower()
                if stype not in ["article","conference paper","review","conference review"]: continue
                results.append({
                    "title":    e.get("dc:title",""), "authors": e.get("dc:creator",""),
                    "year":     e.get("prism:coverDate","")[:4],
                    "source":   e.get("prism:publicationName",""),
                    "doi":      e.get("prism:doi",""), "abstract": e.get("dc:description",""),
                    "url":      e.get("prism:url",""), "type": e.get("subtypeDescription",""),
                    "database": "Elsevier/Scopus",
                })
            total = int(data.get("search-results",{}).get("opensearch:totalResults",0))
            if start + 25 >= min(total, max_records): break
            start += 25; time.sleep(0.5)
        except Exception as e:
            return results, str(e)
    return results, None


def search_acm(query, year_start, year_end, max_records):
    import requests
    from bs4 import BeautifulSoup
    results, page = [], 0
    encoded = urllib.parse.quote(query)
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AcademicResearch/1.0)"}
    while len(results) < max_records:
        url = (f"https://dl.acm.org/action/doSearch?query={encoded}"
               f"&startPage={page}&pageSize=20"
               f"&AfterYear={year_start}&BeforeYear={year_end}"
               f"&ContentItemType=research-article&ContentItemType=proceeding")
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select("li.search__item")
            if not items: break
            for item in items:
                title_el = item.select_one("h5.issue-item__title a")
                if not title_el: continue
                href = title_el.get("href","")
                doi = href.split("/doi/")[-1] if "/doi/" in href else ""
                authors = "; ".join(a.get_text(strip=True) for a in item.select("ul.rlist--inline.loa li a span"))
                year = ""
                detail = item.select_one("div.issue-item__detail")
                if detail:
                    for txt in detail.stripped_strings:
                        if txt.strip().isdigit() and len(txt.strip())==4:
                            year = txt.strip(); break
                source_el  = item.select_one("span.epub-section__title")
                abstract_el= item.select_one("div.issue-item__abstract p")
                results.append({
                    "title":    title_el.get_text(strip=True), "authors": authors, "year": year,
                    "source":   source_el.get_text(strip=True) if source_el else "",
                    "doi": doi, "abstract": abstract_el.get_text(strip=True) if abstract_el else "",
                    "url": f"https://dl.acm.org{href}" if href else "",
                    "type": "Article/Conference", "database": "ACM",
                })
            page += 1
            if len(items) < 20: break
            time.sleep(2)
        except Exception as e:
            return results, str(e)
    return results, None


def search_scholar(query, year_start, year_end, max_records):
    from scholarly import scholarly
    results = []
    try:
        gen = scholarly.search_pubs(query)
        count = 0
        while count < min(max_records, 20):
            try:
                pub = next(gen)
                bib = pub.get("bib",{})
                year_str = str(bib.get("pub_year",""))
                if year_str.isdigit() and not (year_start <= int(year_str) <= year_end):
                    count += 1; continue
                results.append({
                    "title":    bib.get("title",""),
                    "authors":  "; ".join(bib.get("author",[])) if isinstance(bib.get("author"),list) else bib.get("author",""),
                    "year":     year_str,
                    "source":   bib.get("journal","") or bib.get("booktitle",""),
                    "doi":      pub.get("externalids",{}).get("DOI",""),
                    "abstract": bib.get("abstract",""),
                    "url":      pub.get("pub_url",""),
                    "type":     bib.get("ENTRYTYPE",""), "database": "Google Scholar",
                })
                count += 1; time.sleep(1.5)
            except StopIteration: break
            except: count += 1; time.sleep(3)
    except Exception as e:
        return results, str(e)
    return results, None


def deduplicate(papers):
    seen_doi, seen_title, unique, dupes = set(), set(), [], 0
    for p in papers:
        doi   = p.get("doi","").strip().lower()
        title = p.get("title","").strip().lower()[:80]
        key   = doi if doi else title
        if key and key in seen_doi:        dupes += 1; continue
        if key:                             seen_doi.add(key)
        if title and title in seen_title:   dupes += 1; continue
        if title:                           seen_title.add(title)
        unique.append(p)
    return unique, dupes


# ─── Excel Builder ────────────────────────────────────────────────────────────

def build_excel_bytes(papers, stats):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    H_FILL = PatternFill("solid", start_color="1F4E79")
    H_FONT = Font(bold=True, color="FFFFFF", name="Arial", size=10)
    THIN   = Side(style="thin", color="BFBFBF")
    BDR    = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    DIM_CLR= {"D1":"D6E4F0","D2":"D5E8D4","D3":"FFF2CC"}
    PH_CLR = {"Identification":"D6E4F0","Screening":"D5E8D4","Eligibility":"FFF2CC","Included":"FCE4D6"}

    wb = openpyxl.Workbook()

    # ── PRISMA Flow ────────────────────────────────────────────────────────────
    ws = wb.active; ws.title = "PRISMA_Flow"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 3
    ws["B2"].value = "PRISMA 2020 Flow Tracker"
    ws["B2"].font  = Font(bold=True, size=14, color="1F4E79", name="Arial")
    ws.merge_cells("B2:H2")
    hdrs = ["Phase","Step","Database","Query ID","n (raw)","n (filtered)","Notes"]
    wids = [18,40,18,12,12,14,45]
    for ci,(h,w) in enumerate(zip(hdrs,wids),2):
        c=ws.cell(row=4,column=ci,value=h)
        c.font=H_FONT;c.fill=H_FILL;c.border=BDR
        c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
        ws.column_dimensions[get_column_letter(ci)].width=w
    ws.row_dimensions[4].height=28
    rows=[]
    for db,qc in stats.get("identification",{}).items():
        for qid,n in qc.items():
            rows.append(["Identification",f"Records from {db}",db,qid,n,"",""])
    rows+=[
        ["Identification","Duplicate records removed","All","ALL",stats.get("duplicates",0),"","Deduped by DOI+Title"],
        ["Screening","Records screened (title/abstract)","All","ALL",stats.get("after_dedup",0),"","Manual screening"],
        ["Screening","Records excluded — title screen","All","ALL","","",""],
        ["Screening","Reports sought for retrieval","All","ALL","","",""],
        ["Screening","Reports not retrieved","All","ALL","","",""],
        ["Eligibility","Reports assessed for eligibility","All","ALL","","",""],
        ["Eligibility","Reports excluded with reasons","All","ALL","","","E1–E8"],
        ["Included","Studies included in review","All","ALL","","","Final count"],
    ]
    for ri,row in enumerate(rows,5):
        fill=PatternFill("solid",start_color=PH_CLR.get(row[0],"FFFFFF"))
        for ci,val in enumerate(row,2):
            c=ws.cell(row=ri,column=ci,value=val)
            c.fill=fill;c.border=BDR
            c.font=Font(name="Arial",size=9)
            c.alignment=Alignment(wrap_text=True,vertical="center")

    # ── Screening Sheet ────────────────────────────────────────────────────────
    ws2=wb.create_sheet("Screening_Sheet"); ws2.freeze_panes="A2"
    COLS=[
        ("ID",6),("Dimension",14),("Query ID",8),("Database",12),("Title",40),
        ("Authors",22),("Year",6),("Source / Journal",22),("DOI",25),("URL",25),
        ("Abstract (snippet)",45),("Title Screen\nY/N",10),("Title Screen\nReason",22),
        ("Abstract Screen\nY/N",10),("Abstract Screen\nReason",22),
        ("Full Text\nRetrieved?",10),("Eligible?\nY/N",10),
        ("Exclusion\nReason",20),("Included\nFinal Y/N",10),("Notes",28),
    ]
    for ci,(name,width) in enumerate(COLS,1):
        c=ws2.cell(row=1,column=ci,value=name)
        c.font=H_FONT;c.fill=H_FILL;c.border=BDR
        c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
        ws2.column_dimensions[get_column_letter(ci)].width=width
    ws2.row_dimensions[1].height=36
    for ri,p in enumerate(papers,2):
        dk=p.get("dimension","")[:2]
        fill=PatternFill("solid",start_color=DIM_CLR.get(dk,"FFFFFF"))
        vals=[f"{dk}_{ri-1:04d}",p.get("dimension",""),p.get("query_id",""),
              p.get("database",""),p.get("title",""),p.get("authors","")[:120],
              p.get("year",""),p.get("source","")[:60],p.get("doi",""),
              p.get("url","")[:100],p.get("abstract","")[:250],
              "","","","","","","","",""]
        for ci,val in enumerate(vals,1):
            c=ws2.cell(row=ri,column=ci,value=val)
            c.fill=fill;c.border=BDR
            c.font=Font(name="Arial",size=9)
            c.alignment=Alignment(wrap_text=True,vertical="top")
    ws2.auto_filter.ref=f"A1:{get_column_letter(len(COLS))}{len(papers)+1}"

    # ── Concept Matrix ────────────────────────────────────────────────────────
    ws3=wb.create_sheet("Concept_Matrix_W&W")
    ws3.column_dimensions["A"].width=3;ws3.column_dimensions["B"].width=4
    ws3["C2"].value="Webster & Watson (2002) Concept Matrix"
    ws3["C2"].font=Font(bold=True,size=14,color="1F4E79",name="Arial")
    ws3.merge_cells("C2:T2")
    ws3["C3"].value="✓ = concept addressed by paper. Add included papers as rows."
    ws3["C3"].font=Font(italic=True,size=9,color="595959")
    concepts=[
        "Data\nStandards","AI-\nReadiness","Machine-\nReadable","Semantic\nAnnotation",
        "Context\nEngineering","Context\nWindow","Prompt\nDesign","Structured\nContext","Knowledge\nRepresent.",
        "Token\nEfficiency","Context\nCompression","Prompt\nCompression","RAG","Inference\nCost","Answer\nQuality","Hallucin-\nation",
    ]
    cfills=(["D6E4F0"]*4)+["D5E8D4"]*5+["FFF2CC"]*7
    ws3.merge_cells("C5:F5");c=ws3["C5"]
    c.value="D1: Standardization & AI";c.fill=PatternFill("solid",start_color="1F4E79")
    c.font=Font(bold=True,color="FFFFFF",name="Arial",size=9);c.alignment=Alignment(horizontal="center")
    ws3.merge_cells("G5:K5");c=ws3["G5"]
    c.value="D2: Context Engineering";c.fill=PatternFill("solid",start_color="375623")
    c.font=Font(bold=True,color="FFFFFF",name="Arial",size=9);c.alignment=Alignment(horizontal="center")
    ws3.merge_cells("L5:R5");c=ws3["L5"]
    c.value="D3: Token Efficiency";c.fill=PatternFill("solid",start_color="7F6000")
    c.font=Font(bold=True,color="FFFFFF",name="Arial",size=9);c.alignment=Alignment(horizontal="center")
    for ci,(h,w) in enumerate([("Author(s) Year",28),("Title",40)],3):
        c=ws3.cell(row=6,column=ci,value=h)
        c.font=H_FONT;c.fill=H_FILL;c.border=BDR
        c.alignment=Alignment(horizontal="center",vertical="bottom")
        ws3.column_dimensions[get_column_letter(ci)].width=w
    for ci,(concept,cfill) in enumerate(zip(concepts,cfills),5):
        c=ws3.cell(row=6,column=ci,value=concept)
        c.fill=PatternFill("solid",start_color=cfill)
        c.font=Font(bold=True,name="Arial",size=8,color="1F4E79")
        c.alignment=Alignment(text_rotation=90,horizontal="center",vertical="bottom",wrap_text=True)
        c.border=BDR;ws3.column_dimensions[get_column_letter(ci)].width=5
    ws3.row_dimensions[6].height=80
    for ri in range(7,32):
        alt=PatternFill("solid",start_color="F8F8F8") if ri%2==0 else PatternFill()
        for ci in range(3,5+len(concepts)):
            c=ws3.cell(row=ri,column=ci,value="")
            c.border=BDR;c.fill=alt
            c.font=Font(name="Arial",size=10)
            c.alignment=Alignment(horizontal="center",vertical="center")
        ws3.row_dimensions[ri].height=18

    # ── Exclusion Criteria ────────────────────────────────────────────────────
    ws4=wb.create_sheet("Exclusion_Criteria")
    ws4["B2"].value="Exclusion Criteria Reference"
    ws4["B2"].font=Font(bold=True,size=13,color="1F4E79",name="Arial")
    ws4.column_dimensions["B"].width=65
    ecolors=["FFE0E0","FFE0E0","FFF2CC","FFF2CC","D5E8D4","D5E8D4","D6E4F0","D6E4F0"]
    for ri,crit in enumerate(EXCLUSION_CRITERIA,4):
        c=ws4.cell(row=ri,column=2,value=crit)
        c.font=Font(name="Arial",size=10)
        c.fill=PatternFill("solid",start_color=ecolors[ri-4])
        c.border=BDR;ws4.row_dimensions[ri].height=22

    # ── Search Log ────────────────────────────────────────────────────────────
    ws5=wb.create_sheet("Search_Log")
    ws5["B2"].value="Search Query Log — All Queries × All Databases"
    ws5["B2"].font=Font(bold=True,size=13,color="1F4E79",name="Arial")
    lhdrs=["Dimension","Query ID","Label","Database","Query String","n Retrieved"]
    lwids=[24,8,30,16,60,12]
    for ci,(h,w) in enumerate(zip(lhdrs,lwids),2):
        c=ws5.cell(row=4,column=ci,value=h)
        c.font=H_FONT;c.fill=H_FILL;c.border=BDR
        c.alignment=Alignment(horizontal="center")
        ws5.column_dimensions[get_column_letter(ci)].width=w
    lri=5
    for dim,queries in ALL_SEARCH_STRINGS.items():
        for q in queries:
            for db_name,db_key in [("Springer","springer"),("Elsevier","elsevier"),("ACM","acm"),("Google Scholar","generic")]:
                row=[dim,q["id"],q["label"],db_name,q[db_key],
                     stats.get("identification",{}).get(db_name,{}).get(q["id"],"")]
                fill=PatternFill("solid",start_color=DIM_CLR.get(dim[:2],"FFFFFF"))
                for ci,val in enumerate(row,2):
                    c=ws5.cell(row=lri,column=ci,value=val)
                    c.fill=fill;c.border=BDR
                    c.font=Font(name="Arial",size=9)
                    c.alignment=Alignment(wrap_text=True,vertical="top")
                ws5.row_dimensions[lri].height=28;lri+=1

    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf.read()


# ─── Main UI ──────────────────────────────────────────────────────────────────

st.markdown("# 🔬 Systematic Review Bot")
st.markdown("**PRISMA 2020** · **Webster & Watson** · 4 Databases · 9 Search Strings")
st.markdown("---")

# Build active search strings based on sidebar selections
active_strings = {}
dim_map = {"D1_Standardization_AI": use_d1, "D2_Context_Engineering": use_d2, "D3_Token_Efficiency": use_d3}
for dim, enabled in dim_map.items():
    if enabled:
        active_strings[dim] = ALL_SEARCH_STRINGS[dim]

# Preview panel
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown('<div class="metric-card"><div class="num">{}</div><div class="lbl">Dimensions</div></div>'.format(len(active_strings)), unsafe_allow_html=True)
with col2:
    total_queries = sum(len(v) for v in active_strings.values())
    st.markdown('<div class="metric-card"><div class="num">{}</div><div class="lbl">Search Queries</div></div>'.format(total_queries), unsafe_allow_html=True)
with col3:
    dbs = sum([use_springer, use_elsevier, use_acm, use_scholar])
    st.markdown('<div class="metric-card"><div class="num">{}</div><div class="lbl">Databases</div></div>'.format(dbs), unsafe_allow_html=True)

st.markdown("")

# Query preview
with st.expander("📋 Preview Search Queries", expanded=False):
    for dim, queries in active_strings.items():
        dk = dim[:2]
        badge_cls = f"dim-{dk.lower()}"
        st.markdown(f'<span class="dim-badge {badge_cls}">{dk}</span> **{dim}**', unsafe_allow_html=True)
        for q in queries:
            st.markdown(f"&nbsp;&nbsp;&nbsp;`{q['id']}` — {q['label']}")
        st.markdown("")

st.markdown("---")

# Run button
run_col, _ = st.columns([1, 3])
with run_col:
    run_clicked = st.button("🚀 Run Systematic Search", type="primary", use_container_width=True)

if run_clicked:
    if not active_strings:
        st.error("Select at least one dimension.")
        st.stop()

    all_papers = []
    stats = {"identification": {}, "total_raw": 0, "duplicates": 0, "after_dedup": 0}

    log_container = st.container()
    progress_bar  = st.progress(0)
    status_text   = st.empty()

    total_ops = sum(len(q) for q in active_strings.values()) * dbs
    op_done   = 0

    with log_container:
        st.markdown("### 📡 Search Log")
        log_area = st.empty()
        log_lines = []

        def log(msg, kind="info"):
            icon = {"ok":"✅","err":"❌","info":"→","warn":"⚠️"}.get(kind,"→")
            log_lines.append(f"`{datetime.now():%H:%M:%S}` {icon} {msg}")
            log_area.markdown("\n\n".join(log_lines[-30:]))

        for dimension, queries in active_strings.items():
            log(f"**Dimension: {dimension}**", "info")

            for q in queries:
                log(f"Query `{q['id']}` — {q['label']}", "info")

                if use_springer:
                    status_text.text(f"Springer → {q['id']}...")
                    results, err = search_springer(q["springer"], springer_meta, year_start, year_end, max_per_db)
                    if err: log(f"Springer `{q['id']}`: {err}", "err")
                    else:   log(f"Springer `{q['id']}` → {len(results)} results", "ok")
                    for p in results: p.update({"dimension": dimension, "query_id": q["id"]})
                    stats["identification"].setdefault("Springer",{}).setdefault(q["id"],0)
                    stats["identification"]["Springer"][q["id"]] += len(results)
                    all_papers.extend(results)
                    op_done += 1; progress_bar.progress(op_done / total_ops)

                if use_elsevier:
                    status_text.text(f"Elsevier → {q['id']}...")
                    results, err = search_elsevier(q["elsevier"], elsevier_key, year_start, year_end, max_per_db)
                    if err: log(f"Elsevier `{q['id']}`: {err}", "err")
                    else:   log(f"Elsevier `{q['id']}` → {len(results)} results", "ok")
                    for p in results: p.update({"dimension": dimension, "query_id": q["id"]})
                    stats["identification"].setdefault("Elsevier/Scopus",{}).setdefault(q["id"],0)
                    stats["identification"]["Elsevier/Scopus"][q["id"]] += len(results)
                    all_papers.extend(results)
                    op_done += 1; progress_bar.progress(op_done / total_ops)

                if use_acm:
                    status_text.text(f"ACM → {q['id']}...")
                    results, err = search_acm(q["acm"], year_start, year_end, max_per_db)
                    if err: log(f"ACM `{q['id']}`: {err}", "err")
                    else:   log(f"ACM `{q['id']}` → {len(results)} results", "ok")
                    for p in results: p.update({"dimension": dimension, "query_id": q["id"]})
                    stats["identification"].setdefault("ACM",{}).setdefault(q["id"],0)
                    stats["identification"]["ACM"][q["id"]] += len(results)
                    all_papers.extend(results)
                    op_done += 1; progress_bar.progress(op_done / total_ops)

                if use_scholar:
                    status_text.text(f"Google Scholar → {q['id']}...")
                    results, err = search_scholar(q["generic"], year_start, year_end, max_per_db)
                    if err: log(f"Scholar `{q['id']}`: {err}", "err")
                    else:   log(f"Scholar `{q['id']}` → {len(results)} results", "ok")
                    for p in results: p.update({"dimension": dimension, "query_id": q["id"]})
                    stats["identification"].setdefault("Google Scholar",{}).setdefault(q["id"],0)
                    stats["identification"]["Google Scholar"][q["id"]] += len(results)
                    all_papers.extend(results)
                    op_done += 1; progress_bar.progress(op_done / total_ops)

        # Dedup
        status_text.text("Deduplicating...")
        unique, dupes = deduplicate(all_papers)
        stats.update({"total_raw": len(all_papers), "duplicates": dupes, "after_dedup": len(unique)})
        log(f"Deduplication: {len(all_papers)} raw → {dupes} removed → **{len(unique)} unique**", "ok")

    progress_bar.progress(1.0)
    status_text.text("Done!")

    # Summary metrics
    st.markdown("---")
    st.markdown("### 📊 Results Summary")
    m1,m2,m3,m4 = st.columns(4)
    with m1: st.markdown(f'<div class="metric-card"><div class="num">{stats["total_raw"]}</div><div class="lbl">Total Raw</div></div>', unsafe_allow_html=True)
    with m2: st.markdown(f'<div class="metric-card"><div class="num">{stats["duplicates"]}</div><div class="lbl">Duplicates Removed</div></div>', unsafe_allow_html=True)
    with m3: st.markdown(f'<div class="metric-card"><div class="num">{stats["after_dedup"]}</div><div class="lbl">For Screening</div></div>', unsafe_allow_html=True)
    with m4:
        d_counts = {}
        for p in unique:
            d = p.get("dimension","")[:2]
            d_counts[d] = d_counts.get(d,0)+1
        summary = " / ".join(f"{k}:{v}" for k,v in sorted(d_counts.items()))
        st.markdown(f'<div class="metric-card"><div class="num" style="font-size:1.1rem">{summary}</div><div class="lbl">By Dimension</div></div>', unsafe_allow_html=True)

    # Papers preview table
    if unique:
        st.markdown("---")
        st.markdown("### 📄 Papers Preview (first 50)")
        import pandas as pd
        preview_data = [{
            "Dim": p.get("dimension","")[:2],
            "QID": p.get("query_id",""),
            "DB":  p.get("database",""),
            "Year":p.get("year",""),
            "Title":p.get("title","")[:80],
            "Authors":p.get("authors","")[:50],
            "Source":p.get("source","")[:40],
            "DOI":p.get("doi",""),
        } for p in unique[:50]]
        df = pd.DataFrame(preview_data)
        st.dataframe(df, use_container_width=True, height=350)

    # Downloads
    st.markdown("---")
    st.markdown("### 💾 Download Results")
    dl1, dl2 = st.columns(2)

    with dl1:
        excel_bytes = build_excel_bytes(unique, stats)
        fname = f"systematic_review_{datetime.now():%Y%m%d_%H%M}.xlsx"
        st.download_button(
            label="📥 Download PRISMA Excel",
            data=excel_bytes,
            file_name=fname,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with dl2:
        json_bytes = json.dumps({"stats": stats, "papers": unique}, indent=2, ensure_ascii=False).encode()
        st.download_button(
            label="📥 Download Raw JSON",
            data=json_bytes,
            file_name=f"raw_results_{datetime.now():%Y%m%d_%H%M}.json",
            mime="application/json",
            use_container_width=True,
        )

    st.success(f"✅ Search complete! {stats['after_dedup']} papers ready for PRISMA screening.")

else:
    # Instructions when not yet run
    st.markdown("### How to use")
    st.markdown("""
1. **Configure** API keys + parameters in the sidebar
2. **Select** databases and dimensions  
3. Click **Run Systematic Search**
4. **Download** the Excel file → screen papers in `Screening_Sheet` tab
5. Fill **`Concept_Matrix_W&W`** for included papers
6. Update **`PRISMA_Flow`** counts after each screening phase
    """)

    st.info("💡 **Tip:** Springer & Elsevier keys need your server's IP whitelisted. Go to [api.springernature.com](https://api.springernature.com) and [dev.elsevier.com](https://dev.elsevier.com) to add the Streamlit Cloud IP.")
