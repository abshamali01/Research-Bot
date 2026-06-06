"""
Systematic Review — File Importer v4 (Fixed & Enhanced)
"""

import streamlit as st
import pandas as pd
import io, re, csv, time, concurrent.futures, threading
from datetime import datetime
from urllib.parse import urlparse

st.set_page_config(page_title="SR Importer", page_icon="📥", layout="wide")

# ── Query Mapping ─────────────────────────────────────────────────────────────
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
        if not entry.strip(): 
            continue
        if not entry.startswith('@'): 
            entry = '@' + entry
        def get_field(field, text):
            # Fixed regex with proper escaping
            pattern = rf'{re.escape(field)}\s*=\s*\{{(.+?)\}}\s*[,\}}]|{re.escape(field)}\s*=\s*"(.+?)"\s*[,\}}]'
            m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if m:
                result = m.group(1) if m.group(1) else m.group(2)
                return result.strip().replace('\n', ' ')
            return ""
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
    score = 0
    if p.get("abstract","").strip(): score += 3
    if p.get("doi","").strip():      score += 2
    if p.get("url","").strip():      score += 1
    if p.get("authors","").strip():  score += 1
    return score

def deduplicate(papers):
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

# ── Enhanced Abstract Fetching ──────────────────────────────────────────────

import requests as _req
from bs4 import BeautifulSoup

_lock = threading.Lock()
_request_times = []
MAX_RPS = 5  # Max requests per second

def rate_limit():
    """Simple rate limiter to avoid being blocked"""
    with _lock:
        now = time.time()
        # Remove requests older than 1 second
        _request_times[:] = [t for t in _request_times if now - t < 1.0]
        if len(_request_times) >= MAX_RPS:
            sleep_time = 1.0 - (now - _request_times[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
        _request_times.append(time.time())

def is_english(text):
    if not text or len(text) < 10: 
        return True
    non_ascii = sum(1 for c in text if ord(c) > 127)
    return (non_ascii / len(text)) < 0.3

def clean_abstract(text):
    if not text: 
        return ""
    # Remove XML/HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove common prefixes
    text = re.sub(r'^(Abstract|ABSTRACT|Summary|SUMMARY)\s*[:\-]?\s*', '', text, flags=re.I)
    return text

def fetch_crossref(doi):
    """Fetch abstract from CrossRef API"""
    if not doi: 
        return ""
    try:
        rate_limit()
        r = _req.get(
            f"https://api.crossref.org/works/{doi}",
            headers={"User-Agent": "SystematicReview/1.0 (mailto:research@example.com)"}, 
            timeout=8
        )
        if r.ok:
            data = r.json().get("message", {})
            abstract = data.get("abstract", "")
            if abstract:
                abstract = clean_abstract(abstract)
                if len(abstract) > 50 and is_english(abstract):
                    return abstract
    except Exception:
        pass
    return ""

def fetch_semantic_scholar(doi):
    """Fetch abstract from Semantic Scholar API (supports DOI lookup)"""
    if not doi: 
        return ""
    try:
        rate_limit()
        # Semantic Scholar supports DOI: prefix
        r = _req.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
            params={"fields": "title,abstract,authors,year"}, 
            timeout=8
        )
        if r.ok:
            data = r.json()
            abstract = data.get("abstract", "")
            if abstract and len(abstract) > 50 and is_english(abstract):
                return abstract
    except Exception:
        pass
    # Try without DOI: prefix as fallback
    try:
        rate_limit()
        r = _req.get(
            f"https://api.semanticscholar.org/graph/v1/paper/{doi}",
            params={"fields": "title,abstract,authors,year"}, 
            timeout=8
        )
        if r.ok:
            data = r.json()
            abstract = data.get("abstract", "")
            if abstract and len(abstract) > 50 and is_english(abstract):
                return abstract
    except Exception:
        pass
    return ""

def fetch_openalex(doi):
    """Fetch abstract from OpenAlex API"""
    if not doi: 
        return ""
    try:
        rate_limit()
        r = _req.get(
            f"https://api.openalex.org/works/doi:{doi}",
            timeout=8
        )
        if r.ok:
            data = r.json()
            abstract = data.get("abstract", "")
            if abstract and len(abstract) > 50 and is_english(abstract):
                return abstract
            # OpenAlex has inverted index abstracts
            abstract_inv = data.get("abstract_inverted_index")
            if abstract_inv:
                # Reconstruct abstract from inverted index
                words = []
                for word, positions in abstract_inv.items():
                    for pos in positions:
                        while len(words) <= pos:
                            words.append("")
                        words[pos] = word
                abstract = " ".join(words)
                if len(abstract) > 50 and is_english(abstract):
                    return abstract
    except Exception:
        pass
    return ""

def fetch_by_doi(doi):
    """Try multiple APIs in order: CrossRef -> Semantic Scholar -> OpenAlex"""
    if not doi: 
        return ""

    # Try CrossRef first
    abstract = fetch_crossref(doi)
    if abstract: 
        return abstract

    # Try Semantic Scholar
    abstract = fetch_semantic_scholar(doi)
    if abstract: 
        return abstract

    # Try OpenAlex
    abstract = fetch_openalex(doi)
    if abstract: 
        return abstract

    return ""

def is_pdf_url(url):
    """Check if URL is a PDF"""
    if not url:
        return False
    url_lower = url.lower()
    return url_lower.endswith('.pdf') or '/pdf/' in url_lower or url_lower.endswith('.pdf?download=1')

def fetch_by_url(url):
    """Enhanced URL scraping with publisher-specific selectors and better handling"""
    if not url: 
        return ""

    # Skip PDFs - can't scrape HTML
    if is_pdf_url(url):
        return "[PDF - cannot scrape abstract from PDF]"

    # Skip SSRN - requires special handling (often blocked or JS-rendered)
    if "ssrn.com" in url.lower() or "papers.ssrn" in url.lower():
        return "[SSRN - abstract not available via scraping]"

    try:
        rate_limit()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        r = _req.get(url, headers=headers, timeout=12, allow_redirects=True)
        if not r.ok: 
            return ""

        content_type = r.headers.get('Content-Type', '')
        if 'pdf' in content_type.lower():
            return "[PDF - cannot scrape abstract from PDF]"

        soup = BeautifulSoup(r.text, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()

        # Publisher-specific selectors (ordered by priority)
        selectors = [
            # ACM Digital Library
            "div.abstract",
            "section.abstract",
            "div#abstract",
            "div.abstractSection",
            "p.abstract",
            "#Abs1-content",
            "div[class*='abstract']",
            "section[class*='abstract']",

            # Springer
            "section[data-title='Abstract']",
            "div.c-article-section__content",
            "div.Abstract",

            # IEEE
            "div.abstract-text",
            "div.u-mb-1",

            # ScienceDirect / Elsevier
            "div.Abstracts",
            "div#abstracts",

            # SSRN
            "div.abstract-text",
            "div#abstract",

            # General meta tags
            "meta[name='description']",
            "meta[property='og:description']",
            "meta[name='citation_abstract']",

            # arXiv
            "blockquote.abstract",
            "div.abstract",

            # Generic
            "article div.abstract",
            "#abstract",
            ".abstract",
        ]

        for sel in selectors:
            try:
                el = soup.select_one(sel)
                if el:
                    if el.name == "meta":
                        text = el.get("content", "")
                    else:
                        text = el.get_text(" ", strip=True)

                    text = clean_abstract(text)
                    if len(text) > 80 and is_english(text) and len(text) < 5000:
                        return text
            except Exception:
                continue

        # Fallback: try to find any paragraph containing "abstract" in nearby text
        for p in soup.find_all(['p', 'div']):
            try:
                text = p.get_text(" ", strip=True)
                if len(text) > 100 and len(text) < 3000:
                    parent_text = ""
                    if p.parent:
                        parent_text = p.parent.get_text(" ", strip=True)[:200].lower()
                    class_text = ""
                    if p.get('class'):
                        class_text = ' '.join(p.get('class', [])).lower()

                    if 'abstract' in parent_text or 'abstract' in class_text:
                        text = clean_abstract(text)
                        if len(text) > 80 and is_english(text):
                            return text
            except Exception:
                continue

    except Exception:
        pass

    return ""

def build_doi_url(doi):
    if not doi: 
        return ""
    doi = doi.strip()
    if doi.startswith("http"): 
        return doi
    return f"https://doi.org/{doi}"

def fetch_abstract_for_paper(paper):
    """Fetch abstract for a single paper using all available methods"""
    doi = paper.get("doi", "").strip()
    url = paper.get("url", "").strip()

    # Try DOI-based APIs first
    if doi:
        abstract = fetch_by_doi(doi)
        if abstract: 
            return abstract

        # Try doi.org URL as fallback
        doi_url = build_doi_url(doi)
        abstract = fetch_by_url(doi_url)
        if abstract: 
            return abstract

    # Try original URL if different from doi.org and not a PDF
    if url and url != build_doi_url(doi):
        if not is_pdf_url(url):
            abstract = fetch_by_url(url)
            if abstract: 
                return abstract

    return ""

def fetch_abstracts_concurrent(papers, max_workers=5):
    """Fetch abstracts concurrently with rate limiting"""
    results = {}
    found = 0

    def fetch_one(idx_paper):
        idx, paper = idx_paper
        abstract = fetch_abstract_for_paper(paper)
        return idx, abstract

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_one, (i, p)): i for i, p in enumerate(papers)}
        for future in concurrent.futures.as_completed(futures):
            idx, abstract = future.result()
            results[idx] = abstract
            if abstract:
                found += 1

    return results, found

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
    DIM_CLR = {"D1": "D6E4F0", "D2": "D5E8D4", "D3": "FFF2CC"}
    PH_CLR  = {"Identification": "D6E4F0", "Screening": "D5E8D4", "Eligibility": "FFF2CC", "Included": "FCE4D6"}

    # Compute subsets from papers (which is unique with abstracts)
    main_papers  = papers
    missing_year = [p for p in papers if not str(p.get("year", "")).strip().isdigit() or not is_valid_year(p.get("year", ""))]
    missing_doi  = [p for p in papers if not p.get("doi", "").strip()]

    wb = openpyxl.Workbook()

    SCREEN_COLS = [
        ("Database",       14),
        ("Title",          50),
        ("Authors",        25),
        ("Year",            6),
        ("Source / Journal", 26),
        ("DOI",            28),
        ("URL",            28),
        ("Abstract (snippet)", 50),
    ]

    def write_screen(ws, paper_list, row_fill_fn=None, start_row=1):
        ws.freeze_panes = f"A{start_row+1}"
        for ci, (name, width) in enumerate(SCREEN_COLS, 1):
            c = ws.cell(row=start_row, column=ci, value=name)
            c.font = H_FONT
            c.fill = H_FILL
            c.border = BDR
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.column_dimensions[get_column_letter(ci)].width = width
        ws.row_dimensions[start_row].height = 32

        for ri, p in enumerate(paper_list, start_row+1):
            if row_fill_fn:
                fill = row_fill_fn(p)
            else:
                fill = PatternFill("solid", start_color=DIM_CLR.get(p.get("dimension", "")[:2], "FFFFFF"))

            vals = [
                p.get("database", ""),
                p.get("title", ""),
                p.get("authors", "")[:120],
                p.get("year", ""),
                p.get("source", "")[:60],
                p.get("doi", ""),
                p.get("url", "")[:100],
                p.get("abstract", ""),  # Abstract from paper dict - this is the key fix!
            ]
            for ci, val in enumerate(vals, 1):
                c = ws.cell(row=ri, column=ci, value=val)
                c.fill = fill
                c.border = BDR
                c.font = Font(name="Arial", size=9)
                c.alignment = Alignment(wrap_text=True, vertical="top")

        ws.auto_filter.ref = f"A{start_row}:{get_column_letter(len(SCREEN_COLS))}{start_row+len(paper_list)}"

    # ── Sheet 1: PRISMA Flow ──────────────────────────────────────────────────
    ws = wb.active
    ws.title = "PRISMA_Flow"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 3
    ws["B2"].value = "PRISMA 2020 Flow Tracker"
    ws["B2"].font = Font(bold=True, size=14, color="1F4E79", name="Arial")
    ws.merge_cells("B2:H2")

    total_raw   = stats.get("total_raw", 0)
    total_dupes = len(dupe_list)
    after_dedup = stats.get("after_dedup", 0)

    hdrs = ["Phase", "Step", "Database", "Query ID", "n (raw)", "n (after filter)", "Notes"]
    wids = [18, 42, 18, 12, 12, 16, 50]
    for ci, (h, w) in enumerate(zip(hdrs, wids), 2):
        c = ws.cell(row=4, column=ci, value=h)
        c.font = H_FONT
        c.fill = H_FILL
        c.border = BDR
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.row_dimensions[4].height = 28

    rows = []
    for db, qc in stats.get("identification", {}).items():
        for qid, n in qc.items():
            rows.append(["Identification", f"Records identified: {db}", db, qid, n, "", ""])
    rows += [
        ["Identification", "Total records identified",         "All", "ALL", total_raw,   "", "Sum of all DB results"],
        ["Identification", "Duplicate records removed",        "All", "ALL", total_dupes, "", "See Duplicates_Removed sheet"],
        ["Identification", "Records after deduplication",      "All", "ALL", after_dedup, "", ""],
        ["Screening",     "Records screened (title/abstract)", "All", "ALL", after_dedup, "", "Manual screening required"],
        ["Screening",     "Missing year - manual check",      "All", "ALL", len(missing_year), "", "See Missing_Year sheet"],
        ["Screening",     "Missing DOI - manual check",       "All", "ALL", len(missing_doi), "", "See Missing_DOI sheet"],
        ["Screening",     "Records with year + DOI (main)",   "All", "ALL", len(main_papers), "", "See Screening_Sheet"],
        ["Screening",     "Records excluded - title screen",  "All", "ALL", "", "", "Fill after manual screening"],
        ["Screening",     "Records excluded - abstract",      "All", "ALL", "", "", "Fill after manual screening"],
        ["Screening",     "Reports sought for retrieval",     "All", "ALL", "", "", ""],
        ["Screening",     "Reports not retrieved",            "All", "ALL", "", "", ""],
        ["Eligibility",   "Reports assessed for eligibility", "All", "ALL", "", "", ""],
        ["Eligibility",   "Reports excluded with reasons",    "All", "ALL", "", "", "E1-E8 see Exclusion_Criteria"],
        ["Included",      "Studies included in final review", "All", "ALL", "", "", "Fill after full screening"],
    ]
    for ri, row in enumerate(rows, 5):
        fill = PatternFill("solid", start_color=PH_CLR.get(row[0], "FFFFFF"))
        if "missing" in str(row[1]).lower() or "duplicate" in str(row[1]).lower():
            fill = W_FILL
        for ci, val in enumerate(row, 2):
            c = ws.cell(row=ri, column=ci, value=val)
            c.fill = fill
            c.border = BDR
            c.font = Font(name="Arial", size=9)
            c.alignment = Alignment(wrap_text=True, vertical="center")

    # ── Sheet 2: Screening Sheet ────────────────────────────────────────────────
    ws2 = wb.create_sheet("Screening_Sheet")
    write_screen(ws2, main_papers)

    # ── Sheet 3: Duplicates Removed ───────────────────────────────────────────
    ws_dup = wb.create_sheet("Duplicates_Removed")
    ws_dup["A1"].value = f"Duplicates removed ({len(dupe_list)}) — verify deduplication is correct"
    ws_dup["A1"].font = Font(bold=True, size=12, color="2E4057", name="Arial")
    ws_dup.merge_cells(f"A1:{get_column_letter(len(SCREEN_COLS))}1")
    ws_dup.row_dimensions[1].height = 20
    write_screen(ws_dup, dupe_list, row_fill_fn=lambda p: D_FILL, start_row=2)

    # ── Sheet 4: Missing Year ─────────────────────────────────────────────────
    ws_my = wb.create_sheet("Missing_Year")
    ws_my["A1"].value = f"Missing/invalid year ({len(missing_year)}) — verify manually"
    ws_my["A1"].font = Font(bold=True, size=12, color="7F6000", name="Arial")
    ws_my.merge_cells(f"A1:{get_column_letter(len(SCREEN_COLS))}1")
    ws_my.row_dimensions[1].height = 20
    write_screen(ws_my, missing_year, row_fill_fn=lambda p: W_FILL, start_row=2)

    # ── Sheet 5: Missing DOI ──────────────────────────────────────────────────
    ws_md = wb.create_sheet("Missing_DOI")
    ws_md["A1"].value = f"Missing DOI ({len(missing_doi)}) — add DOI manually then move to Screening_Sheet"
    ws_md["A1"].font = Font(bold=True, size=12, color="8B1A1A", name="Arial")
    ws_md.merge_cells(f"A1:{get_column_letter(len(SCREEN_COLS))}1")
    ws_md.row_dimensions[1].height = 20
    write_screen(ws_md, missing_doi, row_fill_fn=lambda p: M_FILL, start_row=2)

    # ── Sheet 6: Concept Matrix ───────────────────────────────────────────────
    ws3 = wb.create_sheet("Concept_Matrix_W&W")
    ws3.column_dimensions["A"].width = 3
    ws3.column_dimensions["B"].width = 4
    ws3["C2"].value = "Webster & Watson (2002) Concept Matrix"
    ws3["C2"].font = Font(bold=True, size=14, color="1F4E79", name="Arial")
    ws3.merge_cells("C2:T2")
    ws3["C3"].value = "Add included papers as rows after screening. Mark with check where concept is addressed."
    ws3["C3"].font = Font(italic=True, size=9, color="595959")

    concepts = [
        "Data\nStandards", "AI-\nReadiness", "Machine-\nReadable", "Semantic\nAnnotation",
        "Context\nEngineering", "Context\nWindow", "Prompt\nDesign", "Structured\nContext", "Knowledge\nRepresent.",
        "Token\nEfficiency", "Context\nCompression", "Prompt\nCompression", "RAG", "Inference\nCost", "Answer\nQuality", "Hallucin-\nation"
    ]
    cfills = (["D6E4F0"] * 4) + ["D5E8D4"] * 5 + ["FFF2CC"] * 7

    ws3.merge_cells("C5:F5")
    c = ws3["C5"]
    c.value = "D1: Standardization & AI"
    c.fill = PatternFill("solid", start_color="1F4E79")
    c.font = Font(bold=True, color="FFFFFF", name="Arial", size=9)
    c.alignment = Alignment(horizontal="center")

    ws3.merge_cells("G5:K5")
    c = ws3["G5"]
    c.value = "D2: Context Engineering"
    c.fill = PatternFill("solid", start_color="375623")
    c.font = Font(bold=True, color="FFFFFF", name="Arial", size=9)
    c.alignment = Alignment(horizontal="center")

    ws3.merge_cells("L5:R5")
    c = ws3["L5"]
    c.value = "D3: Token Efficiency"
    c.fill = PatternFill("solid", start_color="7F6000")
    c.font = Font(bold=True, color="FFFFFF", name="Arial", size=9)
    c.alignment = Alignment(horizontal="center")

    for ci, (h, w) in enumerate([("Author(s) Year", 28), ("Title", 40)], 3):
        c = ws3.cell(row=6, column=ci, value=h)
        c.font = H_FONT
        c.fill = H_FILL
        c.border = BDR
        c.alignment = Alignment(horizontal="center", vertical="bottom")
        ws3.column_dimensions[get_column_letter(ci)].width = w

    for ci, (concept, cfill) in enumerate(zip(concepts, cfills), 5):
        c = ws3.cell(row=6, column=ci, value=concept)
        c.fill = PatternFill("solid", start_color=cfill)
        c.font = Font(bold=True, name="Arial", size=8, color="1F4E79")
        c.alignment = Alignment(text_rotation=90, horizontal="center", vertical="bottom", wrap_text=True)
        c.border = BDR
        ws3.column_dimensions[get_column_letter(ci)].width = 5

    ws3.row_dimensions[6].height = 80
    for ri in range(7, 57):
        alt = PatternFill("solid", start_color="F8F8F8") if ri % 2 == 0 else PatternFill()
        for ci in range(3, 5 + len(concepts)):
            c = ws3.cell(row=ri, column=ci, value="")
            c.border = BDR
            c.fill = alt
            c.font = Font(name="Arial", size=10)
            c.alignment = Alignment(horizontal="center", vertical="center")
        ws3.row_dimensions[ri].height = 18

    # ── Sheet 7: Exclusion Criteria ───────────────────────────────────────────
    ws4 = wb.create_sheet("Exclusion_Criteria")
    ws4["B2"].value = "Exclusion Criteria Reference (PRISMA)"
    ws4["B2"].font = Font(bold=True, size=13, color="1F4E79", name="Arial")
    ws4.column_dimensions["B"].width = 65
    ecolors = ["FFE0E0", "FFE0E0", "FFF2CC", "FFF2CC", "D5E8D4", "D5E8D4", "D6E4F0", "D6E4F0"]
    for ri, crit in enumerate(EXCLUSION_CRITERIA, 4):
        c = ws4.cell(row=ri, column=2, value=crit)
        c.font = Font(name="Arial", size=10)
        c.fill = PatternFill("solid", start_color=ecolors[ri-4])
        c.border = BDR
        ws4.row_dimensions[ri].height = 22

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ── Professional UI Styling ───────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap');

/* Base theme overrides for dark professional look */
html, body, [class*="css"] { 
    font-family: 'Inter', sans-serif; 
}

.stApp { 
    background: linear-gradient(135deg, #0d1117 0%, #161b22 100%); 
}

/* Main title styling */
h1 {
    font-family: 'Inter', sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
}

h2, h3 {
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
}

/* Custom card components */
.sr-card {
    background: rgba(22, 27, 34, 0.8);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(88, 166, 255, 0.15);
    border-radius: 12px;
    padding: 20px;
    margin: 12px 0;
    transition: all 0.3s ease;
}
.sr-card:hover {
    border-color: rgba(88, 166, 255, 0.3);
    box-shadow: 0 4px 20px rgba(88, 166, 255, 0.1);
}

/* Stat boxes */
.stat-box {
    background: linear-gradient(135deg, rgba(88, 166, 255, 0.1) 0%, rgba(88, 166, 255, 0.05) 100%);
    border: 1px solid rgba(88, 166, 255, 0.2);
    border-radius: 10px;
    padding: 20px;
    text-align: center;
    transition: transform 0.2s ease;
}
.stat-box:hover {
    transform: translateY(-2px);
    border-color: rgba(88, 166, 255, 0.4);
}
.stat-num {
    font-family: 'JetBrains Mono', monospace;
    font-size: 2.2rem;
    color: #58a6ff;
    font-weight: 700;
    line-height: 1;
    margin-bottom: 8px;
}
.stat-lbl {
    font-size: 0.75rem;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    font-weight: 500;
}

/* Tags */
.tag {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    font-weight: 600;
    margin: 3px;
    letter-spacing: 0.02em;
}
.tag-springer { background: rgba(46, 160, 67, 0.15); color: #3fb950; border: 1px solid rgba(46, 160, 67, 0.3); }
.tag-acm { background: rgba(248, 81, 73, 0.15); color: #f85149; border: 1px solid rgba(248, 81, 73, 0.3); }
.tag-scopus { background: rgba(88, 166, 255, 0.15); color: #58a6ff; border: 1px solid rgba(88, 166, 255, 0.3); }
.tag-scholar { background: rgba(210, 153, 34, 0.15); color: #e3b341; border: 1px solid rgba(210, 153, 34, 0.3); }

/* Warning boxes */
.warn-box {
    background: rgba(210, 153, 34, 0.1);
    border: 1px solid rgba(210, 153, 34, 0.25);
    border-radius: 8px;
    padding: 12px 16px;
    margin: 8px 0;
    font-size: 0.9rem;
    color: #e3b341;
}

/* Success boxes */
.success-box {
    background: rgba(46, 160, 67, 0.1);
    border: 1px solid rgba(46, 160, 67, 0.25);
    border-radius: 8px;
    padding: 12px 16px;
    margin: 8px 0;
    font-size: 0.9rem;
    color: #3fb950;
}

/* Info boxes */
.info-box {
    background: rgba(88, 166, 255, 0.08);
    border: 1px solid rgba(88, 166, 255, 0.2);
    border-radius: 8px;
    padding: 12px 16px;
    margin: 8px 0;
    font-size: 0.9rem;
    color: #58a6ff;
}

/* Progress bar styling */
.stProgress > div > div {
    background: linear-gradient(90deg, #58a6ff 0%, #3fb950 100%) !important;
    border-radius: 4px !important;
}

/* Button enhancements */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(88, 166, 255, 0.3) !important;
}

/* File uploader */
[data-testid="stFileUploader"] {
    border: 2px dashed rgba(88, 166, 255, 0.3) !important;
    border-radius: 12px !important;
    background: rgba(22, 27, 34, 0.5) !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: rgba(88, 166, 255, 0.6) !important;
    background: rgba(22, 27, 34, 0.8) !important;
}

/* Dataframe styling */
[data-testid="stDataFrame"] {
    border-radius: 8px !important;
    border: 1px solid rgba(88, 166, 255, 0.15) !important;
}

/* Divider styling */
hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent 0%, rgba(88, 166, 255, 0.3) 50%, transparent 100%) !important;
    margin: 24px 0 !important;
}

/* Sheet preview cards */
.sheet-card {
    background: rgba(22, 27, 34, 0.6);
    border: 1px solid rgba(88, 166, 255, 0.15);
    border-radius: 8px;
    padding: 10px 14px;
    margin: 4px 0;
    font-size: 0.85rem;
    transition: all 0.2s ease;
}
.sheet-card:hover {
    border-color: rgba(88, 166, 255, 0.3);
    background: rgba(22, 27, 34, 0.8);
}
.sheet-card b {
    color: #58a6ff;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
}

/* Custom scrollbar */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}
::-webkit-scrollbar-track {
    background: #0d1117;
}
::-webkit-scrollbar-thumb {
    background: #30363d;
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
    background: #58a6ff;
}
</style>
""", unsafe_allow_html=True)

# ── Main UI ───────────────────────────────────────────────────────────────────

st.markdown("""
<div style="text-align: center; padding: 20px 0 30px 0;">
    <h1 style="font-size: 2.5rem; margin-bottom: 8px;">🔬 Systematic Review Bot</h1>
    <p style="color: #8b949e; font-size: 1.1rem; margin: 0;">
        Upload CSV/BIB files → Parse → Fetch Abstracts → Download PRISMA Excel
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ── File upload ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="sr-card">
    <h3 style="margin-top: 0;">📁 Step 1 — Upload Files</h3>
    <p style="color: #8b949e; margin-bottom: 12px;">
        Name files like <code>springer_d1q1.csv</code>, <code>acm_d1q2.bib</code>, 
        <code>scopus_d2q1.csv</code>, <code>scholar_d3q1.csv</code>
    </p>
</div>
""", unsafe_allow_html=True)

st.caption("Supports: Springer CSV · Scopus CSV · Google Scholar CSV (Publish or Perish) · ACM BibTeX")

uploaded = st.file_uploader("Drop all files here", type=["csv", "bib"],
                              accept_multiple_files=True, label_visibility="collapsed")

if uploaded:
    st.markdown("---")

    # ── Parse ─────────────────────────────────────────────────────────────────
    all_papers, stats, parse_log = [], {"identification": {}, "total_raw": 0, "duplicates": 0, "after_dedup": 0}, []

    for f in uploaded:
        fname = f.name.lower()
        qid = "UNKNOWN"
        for q in ["d1q1", "d1q2", "d2q1", "d2q2", "d2q3", "d3q1", "d3q2", "d3q3"]:
            if q in fname: 
                qid = q.upper()
                break
        cf = f.read().decode("utf-8", errors="replace")
        if fname.endswith(".bib"):
            papers = parse_bib(cf, qid)
            db = "ACM"
        else:
            ctype = detect_csv_type(cf, fname)
            if ctype == "springer":
                papers = parse_springer_csv(cf, qid)
                db = "Springer"
            elif ctype in ("scopus", "scopus_pop"):
                papers = parse_scopus_pop_csv(cf, qid) if ctype == "scopus_pop" else parse_scopus_csv(cf, qid)
                db = "Elsevier/Scopus"
            else:
                papers = parse_scholar_csv(cf, qid)
                db = "Google Scholar"
        parse_log.append((f.name, db, qid, len(papers)))
        stats["identification"].setdefault(db, {}).setdefault(qid, 0)
        stats["identification"][db][qid] += len(papers)
        all_papers.extend(papers)

    unique, dupe_list = deduplicate(all_papers)

    # Filter non-English papers
    def likely_english(p):
        text = (p.get("title", "") + " " + p.get("source", ""))
        if not text.strip(): 
            return True
        non_ascii = sum(1 for c in text if ord(c) > 127)
        return (non_ascii / max(len(text), 1)) < 0.25

    non_english = [p for p in unique if not likely_english(p)]
    unique = [p for p in unique if likely_english(p)]

    stats.update({
        "total_raw": len(all_papers),
        "duplicates": len(dupe_list),
        "after_dedup": len(unique),
        "non_english": len(non_english)
    })

    # ── Show parse log ────────────────────────────────────────────────────────
    st.markdown("""
    <div class="sr-card">
        <h3 style="margin-top: 0;">📊 Step 2 — Files Parsed</h3>
    </div>
    """, unsafe_allow_html=True)

    for fname, db, qid, n in parse_log:
        db_cls = {"Springer": "springer", "ACM": "acm", "Elsevier/Scopus": "scopus", "Google Scholar": "scholar"}.get(db, "springer")
        st.markdown(f"<div style='margin: 4px 0;'><code>{fname}</code> → <span class='tag tag-{db_cls}'>{db}</span> <code>{qid}</code> → <b>{n} papers</b></div>", unsafe_allow_html=True)

    # ── Summary ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("""
    <div class="sr-card">
        <h3 style="margin-top: 0;">📈 Step 3 — Summary</h3>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1: 
        st.markdown(f'<div class="stat-box"><div class="stat-num">{stats["total_raw"]}</div><div class="stat-lbl">Total Raw</div></div>', unsafe_allow_html=True)
    with c2: 
        st.markdown(f'<div class="stat-box"><div class="stat-num">{len(dupe_list)}</div><div class="stat-lbl">Duplicates Removed</div></div>', unsafe_allow_html=True)
    with c3: 
        st.markdown(f'<div class="stat-box"><div class="stat-num">{stats["after_dedup"]}</div><div class="stat-lbl">Unique Papers</div></div>', unsafe_allow_html=True)
    with c4:
        d_counts = {}
        for p in unique:
            d = p.get("dimension", "")[:2]
            d_counts[d] = d_counts.get(d, 0) + 1
        summary = " / ".join(f"{k}:{v}" for k, v in sorted(d_counts.items()))
        st.markdown(f'<div class="stat-box"><div class="stat-num" style="font-size:1.1rem">{summary}</div><div class="stat-lbl">By Dimension</div></div>', unsafe_allow_html=True)

    # Pre-compute missing lists for display
    missing_year_pre = [p for p in unique if not str(p.get("year", "")).strip().isdigit() or not is_valid_year(p.get("year", ""))]
    missing_doi_pre = [p for p in unique if not p.get("doi", "").strip()]

    if missing_year_pre:
        st.markdown(f'<div class="warn-box">⚠️ <b>{len(missing_year_pre)} papers</b> missing year → flagged in Missing_Year sheet</div>', unsafe_allow_html=True)
    if missing_doi_pre:
        st.markdown(f'<div class="warn-box">⚠️ <b>{len(missing_doi_pre)} papers</b> missing DOI → flagged in Missing_DOI sheet</div>', unsafe_allow_html=True)

    # ── GENERATE BUTTON ───────────────────────────────────────────────────────
    st.markdown("---")

    need_abstract = [p for p in unique if p.get("doi", "").strip() or p.get("url", "").strip()]
    est_mins = max(1, len(need_abstract) // 20)  # Faster with concurrent fetching

    st.markdown(f"""
    <div class="sr-card">
        <h3 style="margin-top: 0;">🚀 Step 4 — Generate Excel</h3>
        <p style="color: #8b949e; margin-bottom: 0;">
            Will fetch abstracts for <b>{len(need_abstract)} papers</b> via DOI/URL (~{est_mins} min with concurrent fetching)
        </p>
    </div>
    """, unsafe_allow_html=True)

    fetch_toggle = st.checkbox("Fetch abstracts automatically", value=True)

    # Advanced options
    with st.expander("⚙️ Advanced Options"):
        max_workers = st.slider("Concurrent fetch workers", 1, 10, 5, 
                                help="Higher = faster but may hit rate limits")
        skip_pdf = st.checkbox("Skip PDF URLs (faster)", value=True,
                              help="Skip URLs ending in .pdf - cannot scrape abstracts from PDFs")

    generate_clicked = st.button("🚀 Generate Excel", type="primary", use_container_width=True)

    if generate_clicked:
        progress_container = st.container()

        with progress_container:
            prog_bar = st.progress(0)
            status_text = st.empty()
            detail_text = st.empty()

            if fetch_toggle and need_abstract:
                t0 = time.time()
                total = len(need_abstract)

                status_text.markdown("🔄 **Fetching abstracts...**")

                # Fetch abstracts concurrently with progress updates
                results = {}
                found = 0
                completed = 0

                def fetch_one(idx_paper):
                    idx, paper = idx_paper
                    abstract = fetch_abstract_for_paper(paper)
                    return idx, abstract

                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(fetch_one, (i, p)): i for i, p in enumerate(need_abstract)}
                    for future in concurrent.futures.as_completed(futures):
                        idx, abstract = future.result()
                        results[idx] = abstract
                        if abstract:
                            found += 1
                        completed += 1

                        # Update progress
                        pct = int((completed / total) * 100)
                        prog_bar.progress(pct / 100)
                        elapsed = time.time() - t0
                        if completed > 0:
                            rate = completed / elapsed
                            remaining = (total - completed) / rate if rate > 0 else 0
                            m, s = divmod(int(remaining), 60)
                            t_str = f"{m}m {s}s remaining"
                        else:
                            t_str = "estimating..."

                        detail_text.markdown(
                            f"**{pct}%** · ⏱ {t_str} · ✅ {found} fetched · 📄 {completed}/{total}"
                        )

                # Apply results to papers
                for idx, abstract in results.items():
                    need_abstract[idx]["abstract"] = abstract

                prog_bar.progress(1.0)
                total_sec = int(time.time() - t0)
                status_text.markdown(f"✅ **Done!** Fetched {found}/{total} abstracts in {total_sec}s")
                detail_text.empty()

            # Build Excel
            status_text.markdown("📊 **Building Excel workbook...**")
            excel_bytes = build_excel(unique, stats, dupe_list)

            # Store in session state
            st.session_state["excel_bytes"] = excel_bytes
            st.session_state["excel_fname"] = f"systematic_review_{datetime.now():%Y%m%d_%H%M}.xlsx"
            st.session_state["excel_ready"] = True
            st.session_state["abstracts_filled"] = sum(1 for p in unique if p.get("abstract", "").strip())
            st.session_state["total_papers"] = stats["after_dedup"]
            st.session_state["dupe_count"] = len(dupe_list)

            status_text.empty()
            prog_bar.empty()

    # ── Download (only shown after Generate) ─────────────────────────────────
    if st.session_state.get("excel_ready"):
        st.markdown("---")
        st.markdown("""
        <div class="sr-card">
            <h3 style="margin-top: 0;">📥 Step 5 — Download</h3>
        </div>
        """, unsafe_allow_html=True)

        sheets = {
            "PRISMA_Flow": "PRISMA 2020 tracker",
            "Screening_Sheet": f"{st.session_state.get('total_papers', 0)} papers",
            "Duplicates_Removed": f"{st.session_state.get('dupe_count', 0)} duplicates",
            "Missing_Year": f"{len(missing_year_pre)} — check year",
            "Missing_DOI": f"{len(missing_doi_pre)} — add DOI",
            "Concept_Matrix_W&W": "Webster & Watson matrix",
            "Exclusion_Criteria": "E1-E8 reference",
        }
        colors = {"Duplicates_Removed": "#E8EAF6", "Missing_Year": "#FFF8E8", "Missing_DOI": "#FFE8E8"}

        for sheet, desc in sheets.items():
            color = colors.get(sheet, "#f0f7ff")
            st.markdown(f'<div class="sheet-card" style="background: {color}10; border-color: {color}40;"><b>{sheet}</b> — {desc}</div>', unsafe_allow_html=True)

        st.markdown("")
        st.download_button("📥 Download PRISMA Excel",
            data=st.session_state["excel_bytes"],
            file_name=st.session_state["excel_fname"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True, type="primary")

        n = st.session_state.get("total_papers", 0)
        a = st.session_state.get("abstracts_filled", 0)
        d = st.session_state.get("dupe_count", 0)
        st.success(f"✅ {n} papers · {a} with abstract · {d} dupes removed")

else:
    st.markdown("---")
    st.markdown("""
    <div class="sr-card">
        <h3 style="margin-top: 0;">📋 File Naming Convention</h3>
    </div>
    """, unsafe_allow_html=True)

    st.dataframe(pd.DataFrame({
        "File":   ["springer_d1q1.csv", "springer_d1q2.csv", "acm_d1q1.bib", "acm_d1q2.bib", "scopus_d1q1.csv", "scholar_d1q1.csv"],
        "DB":     ["Springer", "Springer", "ACM", "ACM", "Elsevier/Scopus", "Google Scholar"],
        "Query":  ["D1Q1", "D1Q2", "D1Q1", "D1Q2", "D1Q1", "D1Q1"],
        "Format": ["CSV", "CSV", "BibTeX", "BibTeX", "CSV", "CSV"],
    }), use_container_width=True, hide_index=True)

    st.info("💡 Query ID (d1q1, d2q2 etc.) must be in filename.")
