"""
Systematic Review — File Importer v7 (Auto-Screening)
3 Dimensions: D1 Standardization & AI, D2 Context Engineering, D3 Token Efficiency
PRISMA 2020 + Auto E1/E2/E7 Screening + Webster & Watson Concept Matrix + Word Template
"""

import streamlit as st
import pandas as pd
import io, re, csv, time, concurrent.futures, threading, json, os, hashlib
from datetime import datetime
from urllib.parse import urlparse, unquote

st.set_page_config(page_title="SR Importer", page_icon="📥", layout="wide")

# ── Query Mapping ─────────────────────────────────────────────────────────────
QUERY_MAP = {
    "D1Q1": "D1_Standardization_AI", "D1Q2": "D1_Standardization_AI",
    "D2Q1": "D2_Context_Engineering", "D2Q2": "D2_Context_Engineering", "D2Q3": "D2_Context_Engineering",
    "D3Q1": "D3_Token_Efficiency",   "D3Q2": "D3_Token_Efficiency",   "D3Q3": "D3_Token_Efficiency",
}

DIMENSION_NAMES = {
    "D1": "D1_Standardization_AI",
    "D2": "D2_Context_Engineering", 
    "D3": "D3_Token_Efficiency"
}

EXCLUSION_CRITERIA = [
    "E1: Outside year range (2015-2026)",
    "E2: Not English",
    "E3: Not journal/conference/review paper",
    "E4: Not relevant to dimension topic",
    "E5: Duplicate",
    "E6: Full text not accessible",
    "E7: Abstract only / insufficient detail",
    "E8: Not peer-reviewed",
]

SCREENING_STATUS = ["Pending", "Include", "Exclude"]

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
                "screening_status": "Pending",
                "exclusion_reason": "",
                "notes": "",
                "auto_excluded": False,
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
                "screening_status": "Pending",
                "exclusion_reason": "",
                "notes": "",
                "auto_excluded": False,
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
                "screening_status": "Pending",
                "exclusion_reason": "",
                "notes": "",
                "auto_excluded": False,
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
                "screening_status": "Pending",
                "exclusion_reason": "",
                "notes": "",
                "auto_excluded": False,
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
            "screening_status": "Pending",
            "exclusion_reason": "",
            "notes": "",
            "auto_excluded": False,
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

def is_english_text(text):
    """Check if text is English. Returns (is_english, reason)"""
    if not text or len(text.strip()) < 5:
        return True, ""  # Too short to judge, assume English
    non_ascii = sum(1 for c in text if ord(c) > 127)
    ratio = non_ascii / len(text)
    if ratio > 0.25:
        return False, f"Non-ASCII ratio: {ratio:.1%}"
    return True, ""

def auto_screen_papers(papers):
    """Auto-screen papers for E1 (year), E2 (language), E7 (insufficient detail)"""
    auto_excluded = {"E1": 0, "E2": 0, "E7": 0}

    for p in papers:
        # Check E1: Year
        year = str(p.get("year", "")).strip()
        if not year or not year.isdigit() or not is_valid_year(year):
            p["screening_status"] = "Exclude"
            p["exclusion_reason"] = "E1"
            p["notes"] = f"Auto-excluded: Year '{year}' is missing or outside 2015-2026"
            p["auto_excluded"] = True
            auto_excluded["E1"] += 1
            continue

        # Check E2: Language (title + source + abstract if available)
        text_to_check = p.get("title", "") + " " + p.get("source", "") + " " + p.get("abstract", "")
        is_eng, reason = is_english_text(text_to_check)
        if not is_eng:
            p["screening_status"] = "Exclude"
            p["exclusion_reason"] = "E2"
            p["notes"] = f"Auto-excluded: Not English. {reason}"
            p["auto_excluded"] = True
            auto_excluded["E2"] += 1
            continue

        # Check E7: Insufficient detail (no title or no authors)
        if not p.get("title", "").strip() or not p.get("authors", "").strip():
            p["screening_status"] = "Exclude"
            p["exclusion_reason"] = "E7"
            p["notes"] = "Auto-excluded: Missing title or authors"
            p["auto_excluded"] = True
            auto_excluded["E7"] += 1
            continue

    return papers, auto_excluded

# ── Enhanced Abstract Fetching ──────────────────────────────────────────────

import requests as _req
from bs4 import BeautifulSoup

_lock = threading.Lock()
_request_times = []
MAX_RPS = 3

def rate_limit():
    with _lock:
        now = time.time()
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
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'^(Abstract|ABSTRACT|Summary|SUMMARY)\s*[:\-]?\s*', '', text, flags=re.I)
    return text

def normalize_doi(doi):
    if not doi:
        return ""
    doi = doi.strip()
    doi = re.sub(r'/(abstract|full|pdf|reference|v2|v1|fulltext|advance-article-abstract|article-abstract|article-pdf)$', '', doi, flags=re.I)
    doi = re.sub(r'\.short$', '', doi, flags=re.I)
    doi = re.sub(r'\.abstract$', '', doi, flags=re.I)
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.I)
    doi = re.sub(r'^doi:', '', doi, flags=re.I)
    doi = doi.rstrip('/')
    return doi

def is_pdf_url(url):
    if not url:
        return False
    url_lower = url.lower()
    pdf_indicators = [
        '.pdf', '/pdf/', '/content/pdf/', '/download?filename=', 
        '/download_pub', '/article-pdf/', '/fulltext.pdf',
        'pdf?download=1', '.pdf?download', '/pdfdownload',
        '/bitstream/handle/', '/download/',
        '/doi/pdf/', '/doi/abs/',
    ]
    return any(ind in url_lower for ind in pdf_indicators)

def is_blocked_site(url):
    if not url:
        return False
    blocked = [
        'researchgate.net', 'ssrn.com', 'papers.ssrn',
        'ebscohost.com', 
        'cabidigitallibrary.org', 'ovid.com',
        'google.com/books', 'books.google',
        'sciengine.com',
        'jstage.jst.go.jp',
        'pubpub.org', 'assets.pubpub.org',
    ]
    url_lower = url.lower()
    return any(b in url_lower for b in blocked)

def is_scopus_inward(url):
    if not url:
        return False
    return 'scopus.com/inward' in url.lower()

def is_preprint_server(url):
    if not url:
        return False
    preprints = [
        'techrxiv.org', 'biorxiv.org', 'medrxiv.org', 'chemrxiv.org',
        'preprints.org', 'arxiv.org', 'osf.io', 'researchsquare.com',
        'hal.science', 'hal.archives-ouvertes',
    ]
    url_lower = url.lower()
    return any(p in url_lower for p in preprints)

def fetch_with_retry(url, headers=None, timeout=15, max_retries=2):
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    for attempt in range(max_retries + 1):
        try:
            rate_limit()
            r = _req.get(url, headers=headers, timeout=timeout, 
                        allow_redirects=True, verify=False)
            if r.status_code == 200:
                return r
            elif r.status_code in [301, 302, 307, 308]:
                if 'location' in r.headers:
                    return fetch_with_retry(r.headers['location'], headers, timeout, max_retries=0)
            elif attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
        except Exception:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return None
    return None

def fetch_crossref(doi):
    if not doi: 
        return ""
    try:
        rate_limit()
        r = _req.get(
            f"https://api.crossref.org/works/{doi}",
            headers={"User-Agent": "SystematicReview/1.0 (mailto:research@example.com)"}, 
            timeout=10
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
    if not doi: 
        return ""
    try:
        rate_limit()
        r = _req.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
            params={"fields": "title,abstract,authors,year"}, 
            timeout=10
        )
        if r.ok:
            data = r.json()
            abstract = data.get("abstract", "")
            if abstract and len(abstract) > 50 and is_english(abstract):
                return abstract
    except Exception:
        pass
    try:
        rate_limit()
        r = _req.get(
            f"https://api.semanticscholar.org/graph/v1/paper/{doi}",
            params={"fields": "title,abstract,authors,year"}, 
            timeout=10
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
    if not doi: 
        return ""
    try:
        rate_limit()
        r = _req.get(
            f"https://api.openalex.org/works/doi:{doi}",
            timeout=10
        )
        if r.ok:
            data = r.json()
            abstract = data.get("abstract", "")
            if abstract and len(abstract) > 50 and is_english(abstract):
                return abstract
            abstract_inv = data.get("abstract_inverted_index")
            if abstract_inv:
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

def fetch_europepmc(doi):
    if not doi:
        return ""
    try:
        rate_limit()
        r = _req.get(
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{doi}&format=json&resultType=core",
            timeout=10
        )
        if r.ok:
            data = r.json()
            results = data.get("resultList", {}).get("result", [])
            if results:
                abstract = results[0].get("abstractText", "")
                if abstract and len(abstract) > 50 and is_english(abstract):
                    return abstract
    except Exception:
        pass
    return ""

def fetch_by_doi(doi):
    if not doi: 
        return ""
    for fetch_func in [fetch_crossref, fetch_semantic_scholar, fetch_openalex, fetch_europepmc]:
        abstract = fetch_func(doi)
        if abstract:
            return abstract
    return ""

def scrape_abstract_from_html(html_content, url=""):
    if not html_content:
        return ""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()

        selectors = [
            "div.abstract", "section.abstract", "div#abstract", 
            "div.abstractSection", "p.abstract", "#Abs1-content",
            "div[class*='abstract']", "section[class*='abstract']",
            "section[data-title='Abstract']", "div.c-article-section__content",
            "div.Abstract", "div#Abs1",
            "div.abstract-text", "div.u-mb-1", "div.abstract-body",
            "div.Abstracts", "div#abstracts", "div.abstract.content",
            "div.article-section__content", "section.article-section",
            "div.abstractSection", "div.NLM_sec",
            "div.abstract-content", "section.abstract",
            "blockquote.abstract", "div.abstract",
            "meta[name='description']", "meta[property='og:description']",
            "meta[name='citation_abstract']", "meta[name='DC.Description']",
            "article div.abstract", "#abstract", ".abstract",
            "div[role='main'] p", "main p",
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

        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'strong', 'b']):
            heading_text = heading.get_text(strip=True).lower()
            if 'abstract' in heading_text and len(heading_text) < 20:
                next_el = heading.find_next(['p', 'div'])
                if next_el:
                    text = next_el.get_text(" ", strip=True)
                    text = clean_abstract(text)
                    if len(text) > 80 and is_english(text) and len(text) < 5000:
                        return text

        paragraphs = soup.find_all('p')
        best_abstract = ""
        for p in paragraphs:
            text = p.get_text(" ", strip=True)
            if len(text) > len(best_abstract) and len(text) > 100 and len(text) < 3000:
                academic_words = ['study', 'research', 'method', 'results', 'analysis', 
                                'data', 'model', 'system', 'proposed', 'approach']
                text_lower = text.lower()
                if any(word in text_lower for word in academic_words):
                    best_abstract = text

        if best_abstract:
            return clean_abstract(best_abstract)
    except Exception:
        pass
    return ""

def fetch_by_url(url):
    if not url: 
        return ""
    if is_pdf_url(url):
        return "[PDF - cannot extract abstract from PDF file]"
    if is_blocked_site(url):
        return "[Blocked site - requires login or anti-bot protection]"
    if is_scopus_inward(url):
        return "[Scopus inward link - redirect only, no content]"

    r = fetch_with_retry(url)
    if not r:
        return ""
    content_type = r.headers.get('Content-Type', '')
    if 'pdf' in content_type.lower():
        return "[PDF - cannot extract abstract from PDF file]"
    return scrape_abstract_from_html(r.text, url)

def build_doi_url(doi):
    if not doi: 
        return ""
    doi = doi.strip()
    if doi.startswith("http"): 
        return doi
    return f"https://doi.org/{doi}"

def fetch_abstract_for_paper(paper):
    doi = normalize_doi(paper.get("doi", ""))
    url = paper.get("url", "").strip()

    if doi:
        abstract = fetch_by_doi(doi)
        if abstract: 
            return abstract
        doi_url = build_doi_url(doi)
        abstract = fetch_by_url(doi_url)
        if abstract and not abstract.startswith('['):
            return abstract

    if url and url != build_doi_url(doi):
        if not is_pdf_url(url) and not is_blocked_site(url) and not is_scopus_inward(url):
            abstract = fetch_by_url(url)
            if abstract and not abstract.startswith('['):
                return abstract
    return ""

def fetch_abstracts_concurrent(papers, max_workers=3):
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
            if abstract and not abstract.startswith('['):
                found += 1
    return results, found

# ── Excel Builder ─────────────────────────────────────────────────────────────

def build_dimension_excel(papers, stats, dupe_list, dimension_name, dimension_code):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, Protection
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    H_FILL  = PatternFill("solid", start_color="1F4E79")
    H_FONT  = Font(bold=True, color="FFFFFF", name="Arial", size=10)
    W_FILL  = PatternFill("solid", start_color="FFF2CC")
    M_FILL  = PatternFill("solid", start_color="FFE0E0")
    D_FILL  = PatternFill("solid", start_color="E8EAF6")
    AUTO_FILL = PatternFill("solid", start_color="E8F5E9")  # Light green for auto-excluded
    THIN    = Side(style="thin", color="BFBFBF")
    BDR     = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    PH_CLR  = {"Identification":"D6E4F0","Screening":"D5E8D4","Eligibility":"FFF2CC","Included":"FCE4D6"}

    dim_papers = [p for p in papers if dimension_code in p.get("dimension", "")]
    dim_dupes = [p for p in dupe_list if dimension_code in p.get("dimension", "")]

    if not dim_papers:
        return None

    main_papers  = dim_papers

    # Count auto-exclusions
    auto_e1 = sum(1 for p in dim_papers if p.get("exclusion_reason") == "E1")
    auto_e2 = sum(1 for p in dim_papers if p.get("exclusion_reason") == "E2")
    auto_e7 = sum(1 for p in dim_papers if p.get("exclusion_reason") == "E7")
    auto_total = auto_e1 + auto_e2 + auto_e7

    # Papers needing manual screening (still Pending)
    manual_screen = [p for p in dim_papers if p.get("screening_status") == "Pending"]

    # Missing year/DOI (already handled by auto-screening, but keep for reference)
    missing_year = [p for p in dim_papers if not str(p.get("year", "")).strip().isdigit() or not is_valid_year(p.get("year", ""))]
    missing_doi  = [p for p in dim_papers if not p.get("doi", "").strip()]

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
        ("Screening Status", 14),
        ("Exclusion Reason", 20),
        ("Notes",          30),
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
            elif p.get("auto_excluded"):
                fill = AUTO_FILL
            else:
                fill = PatternFill("solid", start_color="FFFFFF")

            vals = [
                p.get("database", ""),
                p.get("title", ""),
                p.get("authors", "")[:120],
                p.get("year", ""),
                p.get("source", "")[:60],
                p.get("doi", ""),
                p.get("url", "")[:100],
                p.get("abstract", ""),
                p.get("screening_status", "Pending"),
                p.get("exclusion_reason", ""),
                p.get("notes", ""),
            ]
            for ci, val in enumerate(vals, 1):
                c = ws.cell(row=ri, column=ci, value=val)
                c.fill = fill
                c.border = BDR
                c.font = Font(name="Arial", size=9)
                c.alignment = Alignment(wrap_text=True, vertical="top")

        ws.auto_filter.ref = f"A{start_row}:{get_column_letter(len(SCREEN_COLS))}{start_row+len(paper_list)}"

        # Add data validation for Screening Status
        if len(paper_list) > 0:
            dv_status = DataValidation(type="list", formula1='"Pending,Include,Exclude"', allow_blank=True)
            dv_status.error = "Please select from dropdown"
            dv_status.errorTitle = "Invalid Entry"
            ws.add_data_validation(dv_status)
            dv_status.add(f'I{start_row+1}:I{start_row+len(paper_list)}')

            # Add data validation for Exclusion Reason
            dv_excl = DataValidation(type="list", formula1='"E1,E2,E3,E4,E5,E6,E7,E8,"', allow_blank=True)
            ws.add_data_validation(dv_excl)
            dv_excl.add(f'J{start_row+1}:J{start_row+len(paper_list)}')

    # ── Sheet 1: PRISMA Flow ──────────────────────────────────────────────────
    ws = wb.active
    ws.title = "PRISMA_Flow"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 3
    ws["B2"].value = f"PRISMA 2020 Flow Tracker — {dimension_name}"
    ws["B2"].font = Font(bold=True, size=14, color="1F4E79", name="Arial")
    ws.merge_cells("B2:H2")

    total_raw = len(dim_papers) + len(dim_dupes)
    total_dupes = len(dim_dupes)
    after_dedup = len(dim_papers)
    after_auto_screen = len(manual_screen)

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

    rows = [
        ["Identification", f"Records identified: {dimension_name}", "All", "ALL", total_raw, "", "Sum of all DB results for this dimension"],
        ["Identification", "Duplicate records removed", "All", "ALL", total_dupes, "", "See Duplicates_Removed sheet"],
        ["Identification", "Records after deduplication", "All", "ALL", after_dedup, "", ""],
        ["Screening", "Auto-excluded: E1 (invalid year)", "All", "ALL", auto_e1, "", "Auto-detected missing/invalid year"],
        ["Screening", "Auto-excluded: E2 (not English)", "All", "ALL", auto_e2, "", "Auto-detected non-English title/abstract"],
        ["Screening", "Auto-excluded: E7 (insufficient detail)", "All", "ALL", auto_e7, "", "Auto-detected missing title/authors"],
        ["Screening", "Records after auto-screening", "All", "ALL", after_auto_screen, "", "Papers needing manual review"],
        ["Screening", "Records screened (title/abstract)", "All", "ALL", after_auto_screen, "", "Manual screening required"],
        ["Screening", "Records excluded - title screen", "All", "ALL", "", "", "Fill after manual screening"],
        ["Screening", "Records excluded - abstract", "All", "ALL", "", "", "Fill after manual screening"],
        ["Screening", "Reports sought for retrieval", "All", "ALL", "", "", ""],
        ["Screening", "Reports not retrieved", "All", "ALL", "", "", ""],
        ["Eligibility", "Reports assessed for eligibility", "All", "ALL", "", "", ""],
        ["Eligibility", "Reports excluded with reasons", "All", "ALL", "", "", "E1-E8 see Exclusion_Criteria"],
        ["Included", "Studies included in final review", "All", "ALL", "", "", "Fill after full screening"],
    ]
    for ri, row in enumerate(rows, 5):
        fill = PatternFill("solid", start_color=PH_CLR.get(row[0], "FFFFFF"))
        if "missing" in str(row[1]).lower() or "duplicate" in str(row[1]).lower():
            fill = W_FILL
        if "auto-excluded" in str(row[1]).lower():
            fill = AUTO_FILL
        for ci, val in enumerate(row, 2):
            c = ws.cell(row=ri, column=ci, value=val)
            c.fill = fill
            c.border = BDR
            c.font = Font(name="Arial", size=9)
            c.alignment = Alignment(wrap_text=True, vertical="center")

    # ── Sheet 2: Screening Sheet ────────────────────────────────────────────────
    ws2 = wb.create_sheet("Screening_Sheet")
    write_screen(ws2, main_papers)

    # Add legend for colors
    ws2["A" + str(len(main_papers) + 3)].value = "Legend:"
    ws2["A" + str(len(main_papers) + 3)].font = Font(bold=True, name="Arial", size=9)
    ws2["B" + str(len(main_papers) + 3)].value = "Light Green = Auto-excluded (E1/E2/E7)"
    ws2["B" + str(len(main_papers) + 3)].fill = AUTO_FILL
    ws2["B" + str(len(main_papers) + 3)].font = Font(name="Arial", size=9)
    ws2["B" + str(len(main_papers) + 4)].value = "White = Needs manual screening"
    ws2["B" + str(len(main_papers) + 4)].font = Font(name="Arial", size=9)

    # ── Sheet 3: Duplicates Removed ───────────────────────────────────────────
    ws_dup = wb.create_sheet("Duplicates_Removed")
    ws_dup["A1"].value = f"Duplicates removed ({len(dim_dupes)}) — verify deduplication is correct"
    ws_dup["A1"].font = Font(bold=True, size=12, color="2E4057", name="Arial")
    ws_dup.merge_cells(f"A1:{get_column_letter(len(SCREEN_COLS))}1")
    ws_dup.row_dimensions[1].height = 20
    write_screen(ws_dup, dim_dupes, row_fill_fn=lambda p: D_FILL, start_row=2)

    # ── Sheet 4: Missing Year ─────────────────────────────────────────────────
    ws_my = wb.create_sheet("Missing_Year")
    ws_my["A1"].value = f"Missing/invalid year ({len(missing_year)}) — already auto-excluded with E1"
    ws_my["A1"].font = Font(bold=True, size=12, color="7F6000", name="Arial")
    ws_my.merge_cells(f"A1:{get_column_letter(len(SCREEN_COLS))}1")
    ws_my.row_dimensions[1].height = 20
    write_screen(ws_my, missing_year, row_fill_fn=lambda p: W_FILL, start_row=2)

    # ── Sheet 5: Missing DOI ──────────────────────────────────────────────────
    ws_md = wb.create_sheet("Missing_DOI")
    ws_md["A1"].value = f"Missing DOI ({len(missing_doi)}) — check if full text accessible"
    ws_md["A1"].font = Font(bold=True, size=12, color="8B1A1A", name="Arial")
    ws_md.merge_cells(f"A1:{get_column_letter(len(SCREEN_COLS))}1")
    ws_md.row_dimensions[1].height = 20
    write_screen(ws_md, missing_doi, row_fill_fn=lambda p: M_FILL, start_row=2)

    # ── Sheet 6: Concept Matrix ───────────────────────────────────────────────
    ws3 = wb.create_sheet("Concept_Matrix_W&W")
    ws3.column_dimensions["A"].width = 3
    ws3.column_dimensions["B"].width = 4
    ws3["C2"].value = f"Webster & Watson (2002) Concept Matrix — {dimension_name}"
    ws3["C2"].font = Font(bold=True, size=14, color="1F4E79", name="Arial")
    ws3.merge_cells("C2:T2")
    ws3["C3"].value = "After screening, add included papers as rows. Mark with 'X' where concept is addressed."
    ws3["C3"].font = Font(italic=True, size=9, color="595959")

    # Dimension-specific concepts
    if dimension_code == "D1":
        concepts = [
            "Data\nStandards", "AI-\nReadiness", "Machine-\nReadable", "Semantic\nAnnotation",
            "Standard-\nization", "Technical\nStandards", "Digital-\nReady", "AI-Native",
            "Metadata", "Ontology", "Automation", "Compliance", "Validation",
            "LLM", "Generative AI", "Interoperability"
        ]
        cfills = ["D6E4F0"] * 16
    elif dimension_code == "D2":
        concepts = [
            "Context\nEngineering", "Context\nDesign", "Context\nConstruction",
            "Structured\nData", "Knowledge\nRepresentation", "Context\nWindow",
            "Context\nSelection", "Answer\nQuality", "Accuracy", "Hallucination",
            "Semantic\nContext", "Context\nPackage", "Prompt\nContext",
            "Efficiency", "Token\nEfficiency", "Cost"
        ]
        cfills = ["D5E8D4"] * 16
    else:  # D3
        concepts = [
            "Token\nEfficiency", "Context\nCompression", "Prompt\nCompression",
            "Answer\nQuality", "Accuracy", "Performance", "Cost\nEfficiency",
            "Inference\nCost", "Token\nCost", "RAG", "Context\nSelection",
            "Context\nPruning", "Question\nAnswering", "Document\nQA",
            "LLM", "Retrieval"
        ]
        cfills = ["FFF2CC"] * 16

    ws3.merge_cells("C5:R5")
    c = ws3["C5"]
    c.value = f"{dimension_code}: {dimension_name}"
    c.fill = PatternFill("solid", start_color="1F4E79")
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
    ws4["B2"].value = f"Exclusion Criteria Reference (PRISMA) — {dimension_name}"
    ws4["B2"].font = Font(bold=True, size=13, color="1F4E79", name="Arial")
    ws4.column_dimensions["B"].width = 65
    ecolors = ["FFE0E0", "FFE0E0", "FFF2CC", "FFF2CC", "D5E8D4", "D5E8D4", "D6E4F0", "D6E4F0"]
    for ri, crit in enumerate(EXCLUSION_CRITERIA, 4):
        c = ws4.cell(row=ri, column=2, value=crit)
        c.font = Font(name="Arial", size=10)
        c.fill = PatternFill("solid", start_color=ecolors[ri-4])
        c.border = BDR
        ws4.row_dimensions[ri].height = 22

    # Add auto-exclusion note
    ws4["B13"].value = "Note: E1, E2, E7 are auto-detected by the script. E3, E4, E5, E6, E8 require manual screening."
    ws4["B13"].font = Font(italic=True, name="Arial", size=9, color="595959")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()

# ── Word Document Template Generator ─────────────────────────────────────────

def generate_word_template():
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # Title
    title = doc.add_heading('Systematic Literature Review: Method & Findings', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Author info
    doc.add_paragraph('Prepared by: [Your Name]')
    doc.add_paragraph('Date: [Date]')
    doc.add_paragraph('Supervisor: [Supervisor Name]')
    doc.add_paragraph()

    # 1. Introduction
    doc.add_heading('1. Introduction', level=1)
    doc.add_paragraph(
        'This systematic literature review examines three dimensions related to Large Language Models (LLMs): '
        '(1) Standardization & AI, (2) Context Engineering, and (3) Token Efficiency. '
        'The review follows the PRISMA 2020 guidelines for transparent reporting.'
    )
    doc.add_paragraph('[Add your introduction text here...]')

    # 2. Methodology
    doc.add_heading('2. Methodology', level=1)

    doc.add_heading('2.1 Search Strategy', level=2)
    doc.add_paragraph('Database searches were conducted in the following databases:')
    doc.add_paragraph('• Springer Link', style='List Bullet')
    doc.add_paragraph('• Scopus / Elsevier', style='List Bullet')
    doc.add_paragraph('• ACM Digital Library', style='List Bullet')
    doc.add_paragraph('• Google Scholar (via Publish or Perish)', style='List Bullet')
    doc.add_paragraph()
    doc.add_paragraph('Search strings for each dimension:')

    # D1 Search String
    doc.add_heading('Dimension 1: Standardization & AI', level=3)
    doc.add_paragraph(
        '("data standards" OR "technical standards" OR "semantic standards" OR "standardization" OR "data standardization") '
        'AND ("machine-readable" OR "AI-ready" OR "AI-native" OR "digital-ready") '
        'AND ("large language models" OR LLM OR "generative AI")'
    )
    doc.add_paragraph(
        '("machine-readable standards" OR "digital standards") '
        'AND ("semantic annotation" OR metadata OR ontology) '
        'AND (automation OR compliance OR validation)'
    )

    # D2 Search String
    doc.add_heading('Dimension 2: Context Engineering', level=3)
    doc.add_paragraph(
        '("large language models" OR LLM) '
        'AND ("context engineering" OR "context design" OR "context construction" OR "context provisioning") '
        'AND ("structured data" OR "structured context" OR "knowledge representation")'
    )
    doc.add_paragraph(
        '("large language models" OR LLM) '
        'AND ("prompt context" OR "context window" OR "context selection") '
        'AND ("answer quality" OR accuracy OR hallucination)'
    )
    doc.add_paragraph(
        '("structured context" OR "semantic context" OR "context package") '
        'AND ("large language models" OR LLM) '
        'AND (efficiency OR "token efficiency" OR cost)'
    )

    # D3 Search String
    doc.add_heading('Dimension 3: Token Efficiency', level=3)
    doc.add_paragraph(
        '("large language models" OR LLM) '
        'AND ("token efficiency" OR "context compression" OR "prompt compression") '
        'AND ("answer quality" OR accuracy OR performance)'
    )
    doc.add_paragraph(
        '("large language models" OR LLM) '
        'AND ("cost efficiency" OR "inference cost" OR "token cost") '
        'AND ("retrieval augmented generation" OR RAG OR "context selection")'
    )
    doc.add_paragraph(
        '("context compression" OR "prompt compression" OR "context pruning") '
        'AND ("large language models" OR LLM) '
        'AND ("question answering" OR "document QA")'
    )

    doc.add_heading('2.2 PRISMA Flow', level=2)
    doc.add_paragraph(
        'The PRISMA 2020 flow diagram documents the identification, screening, eligibility, '
        'and inclusion phases for each dimension. See the attached Excel files for detailed flow trackers.'
    )
    doc.add_paragraph('[Insert PRISMA flow diagram or reference to Excel sheets]')

    doc.add_heading('2.3 Exclusion Criteria', level=2)
    doc.add_paragraph('Papers were excluded based on the following criteria:')
    for crit in EXCLUSION_CRITERIA:
        doc.add_paragraph(f'• {crit}', style='List Bullet')
    doc.add_paragraph()
    doc.add_paragraph('Note: E1 (invalid year), E2 (not English), and E7 (insufficient detail) were auto-detected by the screening script. '
                     'E3, E4, E5, E6, and E8 required manual screening.')

    doc.add_heading('2.4 Analysis Method', level=2)
    doc.add_paragraph(
        'The Webster & Watson (2002) concept matrix approach was used to analyze the literature. '
        'Papers were mapped against dimension-specific concepts to identify research themes and gaps.'
    )

    # 3. Findings by Dimension
    doc.add_heading('3. Findings', level=1)

    # D1 Findings
    doc.add_heading('3.1 Dimension 1: Standardization & AI', level=2)
    doc.add_heading('3.1.1 Synthesis', level=3)
    doc.add_paragraph('[Synthesize findings from included papers. Key themes to address:]')
    doc.add_paragraph('• How do data standards enable AI-readiness?', style='List Bullet')
    doc.add_paragraph('• What semantic annotation approaches support LLM integration?', style='List Bullet')
    doc.add_paragraph('• How does standardization impact automation and compliance?', style='List Bullet')
    doc.add_paragraph('[Your synthesis text here...]')

    doc.add_heading('3.1.2 Summary Table', level=3)
    table = doc.add_table(rows=1, cols=4)
    table.style = 'Light Grid Accent 1'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Paper (Author, Year)'
    hdr_cells[1].text = 'Key Contribution'
    hdr_cells[2].text = 'Concepts Addressed'
    hdr_cells[3].text = 'Relevance to Dimension'
    doc.add_paragraph('[Add rows for each included paper...]')

    # D2 Findings
    doc.add_heading('3.2 Dimension 2: Context Engineering', level=2)
    doc.add_heading('3.2.1 Synthesis', level=3)
    doc.add_paragraph('[Synthesize findings from included papers. Key themes to address:]')
    doc.add_paragraph('• How is context engineered for LLM performance?', style='List Bullet')
    doc.add_paragraph('• What structured context approaches improve answer quality?', style='List Bullet')
    doc.add_paragraph('• How do context window limitations affect design?', style='List Bullet')
    doc.add_paragraph('[Your synthesis text here...]')

    doc.add_heading('3.2.2 Summary Table', level=3)
    table = doc.add_table(rows=1, cols=4)
    table.style = 'Light Grid Accent 1'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Paper (Author, Year)'
    hdr_cells[1].text = 'Key Contribution'
    hdr_cells[2].text = 'Concepts Addressed'
    hdr_cells[3].text = 'Relevance to Dimension'
    doc.add_paragraph('[Add rows for each included paper...]')

    # D3 Findings
    doc.add_heading('3.3 Dimension 3: Token Efficiency', level=2)
    doc.add_heading('3.3.1 Synthesis', level=3)
    doc.add_paragraph('[Synthesize findings from included papers. Key themes to address:]')
    doc.add_paragraph('• What token compression techniques exist?', style='List Bullet')
    doc.add_paragraph('• How does compression affect answer quality?', style='List Bullet')
    doc.add_paragraph('• What is the cost-performance trade-off?', style='List Bullet')
    doc.add_paragraph('[Your synthesis text here...]')

    doc.add_heading('3.3.2 Summary Table', level=3)
    table = doc.add_table(rows=1, cols=4)
    table.style = 'Light Grid Accent 1'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Paper (Author, Year)'
    hdr_cells[1].text = 'Key Contribution'
    hdr_cells[2].text = 'Concepts Addressed'
    hdr_cells[3].text = 'Relevance to Dimension'
    doc.add_paragraph('[Add rows for each included paper...]')

    # 4. Discussion
    doc.add_heading('4. Discussion', level=1)
    doc.add_paragraph('[Discuss cross-dimensional themes, research gaps, and implications]')

    # 5. Conclusion
    doc.add_heading('5. Conclusion', level=1)
    doc.add_paragraph('[Summarize key findings and future research directions]')

    # References
    doc.add_heading('References', level=1)
    doc.add_paragraph('[List all included papers in APA format]')

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()

# ── Professional UI Styling ───────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: linear-gradient(135deg, #0d1117 0%, #161b22 100%); }

h1 { font-family: 'Inter', sans-serif !important; font-weight: 700 !important; letter-spacing: -0.02em !important; }
h2, h3 { font-family: 'Inter', sans-serif !important; font-weight: 600 !important; letter-spacing: -0.01em !important; }

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

.warn-box {
    background: rgba(210, 153, 34, 0.1);
    border: 1px solid rgba(210, 153, 34, 0.25);
    border-radius: 8px;
    padding: 12px 16px;
    margin: 8px 0;
    font-size: 0.9rem;
    color: #e3b341;
}

.success-box {
    background: rgba(46, 160, 67, 0.1);
    border: 1px solid rgba(46, 160, 67, 0.25);
    border-radius: 8px;
    padding: 12px 16px;
    margin: 8px 0;
    font-size: 0.9rem;
    color: #3fb950;
}

.info-box {
    background: rgba(88, 166, 255, 0.08);
    border: 1px solid rgba(88, 166, 255, 0.2);
    border-radius: 8px;
    padding: 12px 16px;
    margin: 8px 0;
    font-size: 0.9rem;
    color: #58a6ff;
}

.stProgress > div > div {
    background: linear-gradient(90deg, #58a6ff 0%, #3fb950 100%) !important;
    border-radius: 4px !important;
}

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

[data-testid="stFileUploader"] {
    border: 2px dashed rgba(88, 166, 255, 0.3) !important;
    border-radius: 12px !important;
    background: rgba(22, 27, 34, 0.5) !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: rgba(88, 166, 255, 0.6) !important;
    background: rgba(22, 27, 34, 0.8) !important;
}

hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent 0%, rgba(88, 166, 255, 0.3) 50%, transparent 100%) !important;
    margin: 24px 0 !important;
}

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
        Upload CSV/BIB files → Auto-Screen (E1/E2/E7) → Fetch Abstracts → Generate 3 Dimension Workbooks + Word Template
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

    # ── Auto-Screening (E1, E2, E7) ──────────────────────────────────────────
    st.markdown("""
    <div class="sr-card">
        <h3 style="margin-top: 0;">🤖 Step 2 — Auto-Screening</h3>
        <p style="color: #8b949e; margin-bottom: 12px;">
            Automatically detecting E1 (invalid year), E2 (not English), E7 (insufficient detail)
        </p>
    </div>
    """, unsafe_allow_html=True)

    unique, auto_excluded = auto_screen_papers(unique)

    stats.update({
        "total_raw": len(all_papers),
        "duplicates": len(dupe_list),
        "after_dedup": len(unique),
        "auto_e1": auto_excluded["E1"],
        "auto_e2": auto_excluded["E2"],
        "auto_e7": auto_excluded["E7"],
        "auto_total": sum(auto_excluded.values()),
        "manual_screen": len([p for p in unique if p.get("screening_status") == "Pending"])
    })

    # Show auto-screening results
    c1, c2, c3, c4 = st.columns(4)
    with c1: 
        st.markdown(f'<div class="stat-box"><div class="stat-num">{auto_excluded["E1"]}</div><div class="stat-lbl">Auto E1 (Year)</div></div>', unsafe_allow_html=True)
    with c2: 
        st.markdown(f'<div class="stat-box"><div class="stat-num">{auto_excluded["E2"]}</div><div class="stat-lbl">Auto E2 (Language)</div></div>', unsafe_allow_html=True)
    with c3: 
        st.markdown(f'<div class="stat-box"><div class="stat-num">{auto_excluded["E7"]}</div><div class="stat-lbl">Auto E7 (Detail)</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="stat-box"><div class="stat-num">{stats["manual_screen"]}</div><div class="stat-lbl">Need Manual Screen</div></div>', unsafe_allow_html=True)

    # ── Show parse log ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("""
    <div class="sr-card">
        <h3 style="margin-top: 0;">📊 Step 3 — Files Parsed</h3>
    </div>
    """, unsafe_allow_html=True)

    for fname, db, qid, n in parse_log:
        db_cls = {"Springer": "springer", "ACM": "acm", "Elsevier/Scopus": "scopus", "Google Scholar": "scholar"}.get(db, "springer")
        st.markdown(f"<div style='margin: 4px 0;'><code>{fname}</code> → <span class='tag tag-{db_cls}'>{db}</span> <code>{qid}</code> → <b>{n} papers</b></div>", unsafe_allow_html=True)

    # ── Summary ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("""
    <div class="sr-card">
        <h3 style="margin-top: 0;">📈 Step 4 — Summary by Dimension</h3>
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

    # ── GENERATE BUTTON ───────────────────────────────────────────────────────
    st.markdown("---")

    need_abstract = [p for p in unique if p.get("screening_status") == "Pending" and (p.get("doi", "").strip() or p.get("url", "").strip())]
    est_mins = max(1, len(need_abstract) // 15)

    st.markdown(f"""
    <div class="sr-card">
        <h3 style="margin-top: 0;">🚀 Step 5 — Generate Workbooks</h3>
        <p style="color: #8b949e; margin-bottom: 0;">
            Will fetch abstracts for <b>{len(need_abstract)} papers</b> needing manual review and generate 3 dimension-specific Excel files + Word template (~{est_mins} min)
        </p>
    </div>
    """, unsafe_allow_html=True)

    fetch_toggle = st.checkbox("Fetch abstracts automatically", value=True)

    with st.expander("⚙️ Advanced Options"):
        max_workers = st.slider("Concurrent fetch workers", 1, 5, 3, 
                                help="Higher = faster but may hit rate limits. Recommended: 3")
        st.info("💡 Many URLs are PDFs, blocked sites, or preprints that cannot be scraped. These will be skipped automatically.")

    generate_clicked = st.button("🚀 Generate All Workbooks", type="primary", use_container_width=True)

    if generate_clicked:
        progress_container = st.container()

        with progress_container:
            prog_bar = st.progress(0)
            status_text = st.empty()
            detail_text = st.empty()

            if fetch_toggle and need_abstract:
                t0 = time.time()
                total = len(need_abstract)

                status_text.markdown("🔄 **Fetching abstracts for manually-screened papers...**")

                pdf_count = sum(1 for p in need_abstract if is_pdf_url(p.get("url", "")))
                blocked_count = sum(1 for p in need_abstract if is_blocked_site(p.get("url", "")))
                scopus_count = sum(1 for p in need_abstract if is_scopus_inward(p.get("url", "")))
                preprint_count = sum(1 for p in need_abstract if is_preprint_server(p.get("url", "")))

                if pdf_count or blocked_count or scopus_count or preprint_count:
                    st.info(f"📋 Auto-skipping: {pdf_count} PDFs, {blocked_count} blocked sites, {scopus_count} Scopus links, {preprint_count} preprints (limited abstract availability)")

                # Fetch abstracts concurrently
                results = {}
                found = 0
                completed = 0
                skipped = 0

                def fetch_one(idx_paper):
                    idx, paper = idx_paper
                    abstract = fetch_abstract_for_paper(paper)
                    return idx, abstract

                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(fetch_one, (i, p)): i for i, p in enumerate(need_abstract)}
                    for future in concurrent.futures.as_completed(futures):
                        idx, abstract = future.result()
                        results[idx] = abstract
                        if abstract and not abstract.startswith('['):
                            found += 1
                        elif abstract.startswith('['):
                            skipped += 1
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
                            f"**{pct}%** · ⏱ {t_str} · ✅ {found} fetched · ⏭️ {skipped} skipped · 📄 {completed}/{total}"
                        )

                # Apply results to papers
                for idx, abstract in results.items():
                    need_abstract[idx]["abstract"] = abstract

                prog_bar.progress(1.0)
                total_sec = int(time.time() - t0)
                status_text.markdown(f"✅ **Done!** Fetched {found}/{total} abstracts in {total_sec}s ({skipped} auto-skipped)")
                detail_text.empty()

            # Build 3 dimension Excel files
            status_text.markdown("📊 **Building dimension workbooks...**")

            dim_files = {}
            for dim_code, dim_name in DIMENSION_NAMES.items():
                excel_bytes = build_dimension_excel(unique, stats, dupe_list, dim_name, dim_code)
                if excel_bytes:
                    dim_files[dim_code] = excel_bytes
                    st.session_state[f"excel_{dim_code}"] = excel_bytes
                    st.session_state[f"fname_{dim_code}"] = f"{dim_name}_{datetime.now():%Y%m%d_%H%M}.xlsx"

            # Build Word template
            status_text.markdown("📝 **Generating Word template...**")
            try:
                word_bytes = generate_word_template()
                st.session_state["word_template"] = word_bytes
                st.session_state["word_fname"] = f"SR_Method_and_Findings_{datetime.now():%Y%m%d_%H%M}.docx"
            except Exception as e:
                st.warning(f"Word template generation failed: {e}. Install python-docx: pip install python-docx")

            st.session_state["excel_ready"] = True
            st.session_state["abstracts_filled"] = sum(1 for p in unique if p.get("abstract", "").strip() and not p.get("abstract", "").startswith('['))
            st.session_state["total_papers"] = stats["after_dedup"]
            st.session_state["dupe_count"] = len(dupe_list)

            status_text.empty()
            prog_bar.empty()

    # ── Download (only shown after Generate) ─────────────────────────────────
    if st.session_state.get("excel_ready"):
        st.markdown("---")
        st.markdown("""
        <div class="sr-card">
            <h3 style="margin-top: 0;">📥 Step 6 — Download</h3>
        </div>
        """, unsafe_allow_html=True)

        # Dimension Excel files
        st.markdown("#### 📊 Dimension Workbooks")
        for dim_code in ["D1", "D2", "D3"]:
            if f"excel_{dim_code}" in st.session_state:
                dim_name = DIMENSION_NAMES[dim_code]
                st.markdown(f'<div class="sheet-card"><b>{dim_name}</b> — PRISMA Flow + Auto-Screened + Manual Screening + Concept Matrix</div>', unsafe_allow_html=True)
                st.download_button(
                    f"📥 Download {dim_name}",
                    data=st.session_state[f"excel_{dim_code}"],
                    file_name=st.session_state[f"fname_{dim_code}"],
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_{dim_code}"
                )

        # Word template
        if "word_template" in st.session_state:
            st.markdown("#### 📝 Word Template")
            st.markdown(f'<div class="sheet-card"><b>Method & Findings Template</b> — Structured document with all 3 dimensions</div>', unsafe_allow_html=True)
            st.download_button(
                "📥 Download Word Template",
                data=st.session_state["word_template"],
                file_name=st.session_state["word_fname"],
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="dl_word"
            )

        n = st.session_state.get("total_papers", 0)
        a = st.session_state.get("abstracts_filled", 0)
        d = st.session_state.get("dupe_count", 0)
        st.success(f"✅ {n} total papers · {a} with abstract · {d} dupes removed · {stats['auto_total']} auto-excluded (E1/E2/E7)")

else:
    st.markdown("---")
    st.markdown("""
    <div class="sr-card">
        <h3 style="margin-top: 0;">📋 File Naming Convention</h3>
    </div>
    """, unsafe_allow_html=True)

    st.dataframe(pd.DataFrame({
        "File":   ["springer_d1q1.csv", "springer_d1q2.csv", "acm_d1q1.bib", "acm_d1q2.bib", "scopus_d2q1.csv", "scholar_d3q1.csv"],
        "DB":     ["Springer", "Springer", "ACM", "ACM", "Elsevier/Scopus", "Google Scholar"],
        "Query":  ["D1Q1", "D1Q2", "D1Q1", "D1Q2", "D2Q1", "D3Q1"],
        "Format": ["CSV", "CSV", "BibTeX", "BibTeX", "CSV", "CSV"],
    }), use_container_width=True, hide_index=True)

    st.info("💡 Query ID (d1q1, d2q2 etc.) must be in filename.")
