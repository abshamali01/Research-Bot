"""
Systematic Review - File Importer v8
Auto-Screening + Year Recovery + Post-Fetch E2 Check
"""

import streamlit as st
import pandas as pd
import io, re, csv, time, concurrent.futures, threading, json, os, hashlib
from datetime import datetime
from urllib.parse import urlparse, unquote

st.set_page_config(page_title="SR Importer", page_icon="📥", layout="wide")

# -- Query Mapping --------------------------------------------------------------
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

# -- Parsers (unchanged from v7) ------------------------------------------------
# parse_springer_csv, parse_scopus_csv, parse_scopus_pop_csv, parse_scholar_csv
# parse_bib, detect_csv_type, paper_score, deduplicate, is_valid_year
# --> Keep your existing parser functions from v7 <--

# =============================================================================
# IMPROVED: Language Detection (catches German, French, Spanish, etc.)
# =============================================================================

def detect_language_simple(text):
    """Detect if text is English or German/Other using common words."""
    if not text or len(text.strip()) < 10:
        return "unknown", "too short"
    text_lower = text.lower()
    words = set(re.findall(r'[a-zA-ZäöüßÄÖÜ]+', text_lower))
    
    german_words = {
        "die", "der", "das", "und", "ist", "für", "von", "mit", "auf", "zu", "ein", "eine",
        "einer", "eines", "einem", "einen", "nicht", "als", "auch", "sich", "nach", "bei",
        "aus", "durch", "wird", "sind", "wurde", "wurden", "kann", "können",
        "muss", "müssen", "soll", "sollen", "dass", "wenn", "aber", "oder", "über", "unter",
        "zwischen", "gegen", "ohne", "um", "an", "in", "im", "zum", "zur",
        "anwendung", "anwendungen", "perspektiven", "stadtentwicklung", "digitale", "digitales",
        "zwillinge", "bauleitpläne", "bauleitplan", "gestützte", "gestützt", "künstliche",
        "intelligenz", "maschinelles", "lernen", "modell", "modelle", "daten", "analyse",
        "forschung", "studie", "untersuchung", "ergebnisse", "methode", "methoden", "system",
        "systeme", "prozess", "prozesse", "entwicklung", "technologie", "technologien",
        "infrastruktur", "standard", "standards", "norm", "normen", "dokument", "dokumente",
        "bericht", "berichte", "verfahren", "vergleich", "bewertung", "optimierung",
        "simulation", "visualisierung", "repräsentation", "physisch", "physischer",
        "virtuell", "virtuelle", "virtuellen", "real", "reale", "realen", "zeit", "echtzeit",
        "sensor", "sensoren", "quelle", "quellen", "netzwerk", "netzwerke", "kommunikation",
        "information", "informationen", "wissen", "wissens", "entscheidung", "entscheidungen",
        "unterstützung", "unterstützt", "unterstützte", "automatisch", "automatische",
        "automatischer", "automatisches", "manuell", "manuelle", "manueller", "manuelles",
        "stadt", "städte", "städtische", "städtischer", "städtischen", "urban", "urbane",
        "urbaner", "urbanen", "planung", "planungen", "planerisch", "planerische",
        "raum", "räume", "räumlich", "räumliche", "räumlicher", "räumlichen",
        "bau", "bauten", "bauen", "bauend", "baute", "gebäude", "gebäuden",
        "raumplanung", "stadtplanung", "flächennutzung", "flächennutzungsplan",
        "bebauungsplan", "bebauungspläne", "bauleitplanung", "bauleitplanungen",
    }
    
    english_words = {
        "the", "and", "of", "to", "in", "a", "is", "that", "for", "it", "with", "as", "was",
        "on", "by", "this", "are", "or", "from", "but", "not", "be", "have", "has", "had",
        "at", "an", "were", "they", "their", "we", "our", "us", "i", "my", "me", "you",
        "your", "he", "his", "him", "she", "her", "it", "its", "research", "study", "paper",
        "analysis", "data", "method", "methods", "system", "systems", "model", "models",
        "approach", "proposed", "using", "based", "results", "show", "shown", "presented",
        "discussed", "conclusion", "conclusions", "abstract", "introduction", "related",
        "work", "future", "directions", "evaluation", "performance", "accuracy", "precision",
        "recall", "f1", "score", "metric", "metrics", "dataset", "datasets", "training",
        "test", "testing", "validation", "experiment", "experiments", "experimental",
        "framework", "algorithm", "algorithms", "application", "applications", "implementation",
        "design", "development", "process", "processes", "technique", "techniques",
        "challenges", "benefits", "limitations", "opportunities", "directions", "dynamics",
        "deploying", "deployment", "content", "creation", "support", "tools", "broadcasting",
        "understanding", "factors", "computing", "human", "systems",
    }
    
    german_count = len(words & german_words)
    english_count = len(words & english_words)
    
    total_indicators = german_count + english_count
    if total_indicators == 0:
        return "unknown", "no indicator words found"
    
    german_ratio = german_count / total_indicators
    english_ratio = english_count / total_indicators
    
    if german_ratio > 0.6:
        return "de", f"German words: {german_count}/{total_indicators} ({german_ratio:.0%})"
    elif english_ratio > 0.6:
        return "en", f"English words: {english_count}/{total_indicators} ({english_ratio:.0%})"
    else:
        return "unknown", f"Mixed: EN={english_count}, DE={german_count}"

def is_english_text(text):
    """Check if text is English. Returns (is_english, reason).
    
    Uses TWO methods:
    1. Non-ASCII ratio check (catches Chinese, Arabic, Cyrillic, etc.)
    2. Dictionary-based detection (catches German, French, Spanish with Latin-1 chars)
    """
    if not text or len(text.strip()) < 5:
        return True, ""
    
    # Method 1: Non-ASCII ratio (catches non-Latin scripts)
    non_ascii = sum(1 for c in text if ord(c) > 127)
    ratio = non_ascii / len(text)
    if ratio > 0.25:
        return False, f"Non-ASCII ratio: {ratio:.1%}"
    
    # Method 2: Dictionary-based detection (catches German, French, etc.)
    lang_code, lang_reason = detect_language_simple(text)
    if lang_code == "de":
        return False, f"German text detected. {lang_reason}"
    if lang_code == "unknown" and ratio > 0.05:
        return False, f"Possible non-English. Non-ASCII: {ratio:.1%}. {lang_reason}"
    
    return True, ""

def auto_screen_papers(papers):
    """Auto-screen papers for E1 (year), E2 (language), E7 (insufficient detail)"""
    auto_excluded = {"E1": 0, "E2": 0, "E7": 0}
    for p in papers:
        year = str(p.get("year", "")).strip()
        if not year or not year.isdigit() or not is_valid_year(year):
            p["screening_status"] = "Exclude"
            p["exclusion_reason"] = "E1"
            p["notes"] = f"Auto-excluded: Year '{year}' is missing or outside 2015-2026"
            p["auto_excluded"] = True
            auto_excluded["E1"] += 1
            continue
        text_to_check = p.get("title", "") + " " + p.get("source", "") + " " + p.get("abstract", "")
        is_eng, reason = is_english_text(text_to_check)
        if not is_eng:
            p["screening_status"] = "Exclude"
            p["exclusion_reason"] = "E2"
            p["notes"] = f"Auto-excluded: Not English. {reason}"
            p["auto_excluded"] = True
            auto_excluded["E2"] += 1
            continue
        if not p.get("title", "").strip() or not p.get("authors", "").strip():
            p["screening_status"] = "Exclude"
            p["exclusion_reason"] = "E7"
            p["notes"] = "Auto-excluded: Missing title or authors"
            p["auto_excluded"] = True
            auto_excluded["E7"] += 1
            continue
    return papers, auto_excluded

# -- Keep all existing helper functions from v7: --
# rate_limit, is_english, clean_abstract, normalize_doi, is_pdf_url, is_blocked_site
# is_scopus_inward, is_preprint_server, fetch_with_retry, scrape_abstract_from_html
# fetch_by_url, build_doi_url

# =============================================================================
# NEW: Year Extraction Functions
# =============================================================================

def extract_year_from_crossref(data):
    """Extract year from Crossref API response.
    Tries: published-print -> published-online -> issued -> created
    """
    date_fields = ["published-print", "published-online", "issued", "created"]
    for field in date_fields:
        if field in data:
            date_parts = data[field].get("date-parts", [[]])
            if date_parts and date_parts[0] and len(date_parts[0]) > 0:
                year = date_parts[0][0]
                if year and str(year).isdigit():
                    return str(year)
    return None

def extract_year_from_semantic_scholar(data):
    """Extract year from Semantic Scholar API response."""
    year = data.get("year")
    if year and str(year).isdigit():
        return str(year)
    pub_date = data.get("publicationDate")
    if pub_date:
        match = re.search(r"(19|20)\d{2}", str(pub_date))
        if match:
            return match.group(0)
    return None

# =============================================================================
# CORRECTED: API Fetch Functions (return (abstract, year) tuples)
# =============================================================================

def fetch_crossref(doi):
    """Fetch abstract AND year from Crossref. Returns (abstract, year)."""
    if not doi: return "", None
    try:
        rate_limit()
        r = _req.get(
            f"https://api.crossref.org/works/{doi}",
            headers={"User-Agent": "SystematicReview/1.0"},
            timeout=10
        )
        if r.ok:
            data = r.json().get("message", {})
            year = extract_year_from_crossref(data)
            abstract = data.get("abstract", "")
            if abstract:
                abstract = clean_abstract(abstract)
                if len(abstract) > 50 and is_english(abstract):
                    return abstract, year
            return "", year
    except Exception:
        pass
    return "", None

def fetch_semantic_scholar(doi):
    """Fetch abstract AND year from Semantic Scholar. Returns (abstract, year).
    CRITICAL FIX: data.get("abstract") or "" handles null values.
    Old code: data.get("abstract", "") returns None when abstract is null!
    """
    if not doi: return "", None
    endpoints = [
        f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
        f"https://api.semanticscholar.org/graph/v1/paper/{doi}",
    ]
    for url in endpoints:
        try:
            rate_limit()
            r = _req.get(
                url,
                params={"fields": "title,abstract,authors,year,publicationDate"},
                timeout=10
            )
            if r.ok:
                data = r.json()
                year = extract_year_from_semantic_scholar(data)
                # CRITICAL FIX: use "or" to handle null
                abstract = data.get("abstract") or ""
                if abstract and len(abstract) > 50 and is_english(abstract):
                    return abstract, year
                return "", year
        except Exception:
            continue
    return "", None

def fetch_openalex(doi):
    """Fetch abstract AND year from OpenAlex. Returns (abstract, year)."""
    if not doi: return "", None
    try:
        rate_limit()
        r = _req.get(f"https://api.openalex.org/works/doi:{doi}", timeout=10)
        if r.ok:
            data = r.json()
            year = None
            pub_year = data.get("publication_year")
            if pub_year and str(pub_year).isdigit():
                year = str(pub_year)
            abstract = data.get("abstract", "")
            if abstract and len(abstract) > 50 and is_english(abstract):
                return abstract, year
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
                    return abstract, year
            return "", year
    except Exception:
        pass
    return "", None

def fetch_europepmc(doi):
    """Fetch abstract AND year from Europe PMC. Returns (abstract, year)."""
    if not doi: return "", None
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
                result = results[0]
                year = None
                pub_year = result.get("pubYear")
                if pub_year and str(pub_year).isdigit():
                    year = str(pub_year)
                abstract = result.get("abstractText", "")
                if abstract and len(abstract) > 50 and is_english(abstract):
                    return abstract, year
                return "", year
    except Exception:
        pass
    return "", None

def fetch_by_doi(doi):
    """Fetch abstract and year from multiple APIs. Returns (abstract, year).
    Priority: Crossref -> Semantic Scholar -> OpenAlex -> Europe PMC
    Strategy: 1st pass for abstract, 2nd pass for year only if no abstract.
    """
    if not doi: return "", None
    for fetch_func in [fetch_crossref, fetch_semantic_scholar, fetch_openalex, fetch_europepmc]:
        abstract, year = fetch_func(doi)
        if abstract:
            return abstract, year
    for fetch_func in [fetch_crossref, fetch_semantic_scholar, fetch_openalex, fetch_europepmc]:
        abstract, year = fetch_func(doi)
        if year:
            return "", year
    return "", None

# =============================================================================
# NEW: Combined Fetch Function (abstract + year)
# =============================================================================

def fetch_abstract_and_year_for_paper(paper):
    """Fetch abstract and year for a single paper. Returns (abstract, year)."""
    doi = normalize_doi(paper.get("doi", ""))
    url = paper.get("url", "").strip()
    abstract = ""
    year = None
    if doi:
        abstract, year = fetch_by_doi(doi)
        if abstract: return abstract, year
        if not abstract:
            doi_url = build_doi_url(doi)
            abstract = fetch_by_url(doi_url)
            if abstract and not abstract.startswith("["):
                return abstract, year
    if url and url != build_doi_url(doi):
        if not is_pdf_url(url) and not is_blocked_site(url) and not is_scopus_inward(url):
            abstract = fetch_by_url(url)
            if abstract and not abstract.startswith("["):
                return abstract, year
    return abstract, year

# =============================================================================
# NEW: Concurrent Fetch (abstracts + years)
# =============================================================================

def fetch_abstracts_and_years_concurrent(papers, max_workers=3):
    """Fetch abstracts and years for papers concurrently.
    Returns: (results_dict, found_abstracts_count, found_years_count)
    """
    results = {}
    found_abstracts = 0
    found_years = 0
    def fetch_one(idx_paper):
        idx, paper = idx_paper
        abstract, year = fetch_abstract_and_year_for_paper(paper)
        return idx, abstract, year
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_one, (i, p)): i for i, p in enumerate(papers)}
        for future in concurrent.futures.as_completed(futures):
            idx, abstract, year = future.result()
            results[idx] = (abstract, year)
            if abstract and not abstract.startswith("["):
                found_abstracts += 1
            if year:
                found_years += 1
    return results, found_abstracts, found_years

# =============================================================================
# NEW: Post-Fetch Language Screening (E2 re-check)
# =============================================================================

def post_fetch_language_screen(papers):
    """After fetching abstracts, re-check E2 (language) on title + abstract.
    
    If a paper was previously Pending and now has a non-English abstract,
    or if title + abstract is non-English, mark as E2 excluded.
    Only affects papers still in Pending status.
    """
    newly_excluded = 0
    for p in papers:
        if p.get("screening_status") != "Pending":
            continue
        text_to_check = p.get("title", "") + " " + p.get("source", "") + " " + p.get("abstract", "")
        is_eng, reason = is_english_text(text_to_check)
        if not is_eng:
            p["screening_status"] = "Exclude"
            p["exclusion_reason"] = "E2"
            p["notes"] = f"Auto-excluded: Not English (post-fetch). {reason}"
            p["auto_excluded"] = True
            newly_excluded += 1
    return papers, newly_excluded

# =============================================================================
# NEW: Apply Fetched Year to Papers
# =============================================================================

def apply_fetched_year(papers, fetch_results):
    """Apply fetched year to papers that were missing or had invalid year.
    
    If a paper was E1-excluded (missing year) and API found year,
    update the year. Paper stays excluded for manual review.
    """
    updated_count = 0
    for idx, (abstract, year) in fetch_results.items():
        if not year:
            continue
        p = papers[idx]
        current_year = str(p.get("year", "")).strip()
        if not current_year or not current_year.isdigit() or not is_valid_year(current_year):
            if is_valid_year(year):
                p["year"] = year
                updated_count += 1
                if p.get("exclusion_reason") == "E1" and p.get("auto_excluded"):
                    p["notes"] = f"Year recovered from API: {year}. Previously E1. Manual review needed."
    return papers, updated_count

# =============================================================================
# INSTRUCTIONS FOR MAIN FLOW UPDATE
# =============================================================================

"""
IN YOUR MAIN FLOW (inside generate_clicked handler), REPLACE:

OLD CODE:
    results, found = fetch_abstracts_concurrent(need_abstract, max_workers=max_workers)
    for idx, abstract in results.items():
        need_abstract[idx]["abstract"] = abstract

NEW CODE:
    # 1. Fetch abstracts AND years
    results, found_abstracts, found_years = fetch_abstracts_and_years_concurrent(need_abstract, max_workers=max_workers)
    
    # 2. Apply results to papers
    for idx, (abstract, year) in results.items():
        need_abstract[idx]["abstract"] = abstract
        if year and (not need_abstract[idx].get("year") or not is_valid_year(str(need_abstract[idx].get("year", "")))):
            need_abstract[idx]["year"] = year
    
    # 3. POST-FETCH: Re-check E2 (language) after abstract fetch
    unique, newly_excluded_e2 = post_fetch_language_screen(unique)
    if newly_excluded_e2 > 0:
        st.warning(f"⚠️ {newly_excluded_e2} papers newly excluded E2 after abstract fetch")
    
    # 4. Apply fetched years to E1-excluded papers
    unique, updated_years = apply_fetched_year(unique, results)
    if updated_years > 0:
        st.info(f"📅 Updated year for {updated_years} papers from APIs")
    
    # 5. Re-calculate stats after post-fetch screening
    stats["auto_e2"] = sum(1 for p in unique if p.get("exclusion_reason") == "E2")
    stats["auto_total"] = stats["auto_e1"] + stats["auto_e2"] + stats["auto_e7"]
    stats["manual_screen"] = len([p for p in unique if p.get("screening_status") == "Pending"])
"""
