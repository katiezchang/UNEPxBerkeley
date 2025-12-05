#!/usr/bin/env python3
"""
Unified scraper for extracting PIF-relevant sections from UNFCCC country reports.

Supports extraction of:
- Institutional framework for climate action
- National policy framework
- GHG Inventory Module
- Adaptation and Vulnerability Module
- Climate Transparency
- Official Reporting to UNFCCC
- Key Barriers

Expected usage:
    # Extract all sections
    python scrape_unfccc.py --country "Cuba"
    
    # Extract specific sections only
    python scrape_unfccc.py --country "Cuba" --sections "GHG Inventory Module" "Adaptation and Vulnerability Module"

Dependencies:
    pip install requests beautifulsoup4 PyMuPDF
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterable
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup  # type: ignore
except ImportError as import_error:  # pragma: no cover - dependency guard
    raise SystemExit(
        "Missing dependencies. Please run: pip install requests beautifulsoup4"
    ) from import_error

try:
    import fitz  # PyMuPDF
except ImportError as import_error:  # pragma: no cover - dependency guard
    raise SystemExit(
        "Missing dependency 'PyMuPDF'. Please run: pip install PyMuPDF"
    ) from import_error

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    # Don't log here as logging may not be configured yet


BASE_URL = "https://unfccc.int"
REPORTS_URL = f"{BASE_URL}/reports"
REPORTS_AJAX_URL = f"{BASE_URL}/views/ajax"

REQUEST_TIMEOUT = 45
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# Combined section definitions for all PIF sections
SECTION_DEFINITIONS: Dict[str, Dict[str, object]] = {
    # Institutional and Policy Framework sections (from original scrape_unfccc.py)
    "Institutional framework for climate action": {
        "bundle": "Institutional_framework_bundle.json",
        "directory": "Institutional_framework_for_climate_action",
        "headings": (
            r"^\s*[ivxlcdm]+\.\s*Institutional\sframework[^\n]*",
            r"^\s*Institutional\sframework[^\n]*",
            r"^\s*Institutional\sarrangements[^\n]*",
        ),
        "patterns": (
            r"(Institutional\sframework(?:\sfor\s(?:climate|mitigation|adaptation|the\simplementation))?.*?)"
            r"(?=\n[A-Z][^\n]+|$)",
            r"(Institutional\sarrangements\s(?:for|on)\s(?:climate|implementation).*?)"
            r"(?=\n[A-Z][^\n]+|$)",
            r"(Institutional\ssetup.*?)(?=\n[A-Z][^\n]+|$)",
        )
    },
    "National policy framework": {
        "bundle": "National_policy_framework_bundle.json",
        "directory": "National_policy_framework",
        "headings": (
            r"^\s*[ivxlcdm]+\.\s*National\s(?:policy|strategic)\sframework[^\n]*",
            r"^\s*National\s(?:policy|strategic)\sframework[^\n]*",
            r"^\s*Policy\sand\sregulatory\sframework[^\n]*",
        ),
        "patterns": (
            r"(National\s(?:policy|strategic)\sframework.*?)(?=\n[A-Z][^\n]+|$)",
            r"(National\s(?:strategy|policies)\s(?:for|on)\sclimate.*?)(?=\n[A-Z][^\n]+|$)",
            r"(Policy\sand\sregulatory\sframework.*?)(?=\n[A-Z][^\n]+|$)",
        )
    },
    # Adaptation and GHG Inventory sections (from pdfextraction_BUR/bur_webscraper.py)
    "GHG Inventory Module": {
        "bundle": "GHG_inventory_bundle.json",
        "directory": "GHG_inventory_module",
        "headings": (
            r"^\s*[IVXLCDM]+\.\s*National\s+greenhouse\s+gas\s+inventory[^\n]*",
            r"^\s*National\s+greenhouse\s+gas\s+inventory[^\n]*",
            r"^\s*National\s+GHG\s+inventory[^\n]*",
            r"^\s*Greenhouse\s+gas\s+emissions[^\n]*",
        ),
        "patterns": (
            r"(National\s+greenhouse\s+gas\s+inventory.*?)(?=\n[A-Z][^\n]+|$)",
            r"(Greenhouse\s+gas\s+emissions.*?)(?=\n[A-Z][^\n]+|$)",
        ),
    },
    "Adaptation and Vulnerability Module": {
        "bundle": "Adaptation_vulnerability_bundle.json",
        "directory": "Adaptation_and_vulnerability_module",
        "headings": (
            r"^\s*[IVXLCDM]+\.\s*Vulnerability\s+and\s+adaptation[^\n]*",
            r"^\s*Vulnerability\s+and\s+adaptation[^\n]*",
            r"^\s*Climate\s+change\s+impacts\s+and\s+adaptation[^\n]*",
            r"^\s*Adaptation\s+actions[^\n]*",
        ),
        "patterns": (
            r"(Vulnerability\s+and\s+adaptation.*?)(?=\n[A-Z][^\n]+|$)",
            r"(Climate\s+change\s+impacts\s+and\s+adaptation.*?)(?=\n[A-Z][^\n]+|$)",
            r"(Adaptation\s+actions.*?)(?=\n[A-Z][^\n]+|$)",
        ),
    },
    # Transparency sections (from pdfextraction_BUR.ipynb)
    "Climate Transparency": {
        "bundle": "Climate_transparency_bundle.json",
        "directory": "Climate_transparency",
        "headings": (
            r"^\s*Climate\s+transparency\s+in\s+[^\n]*",
            r"^\s*Climate\s+transparency\s+in\s+the\s+country[^\n]*",
            r"^\s*Climate\s+transparency[^\n]*",
            r"^\s*Progress\s+in\s+the\s+four\s+modules\s+of\s+the\s+Enhanced\s+Transparency\s+Framework[^\n]*",
        ),
        "patterns": (
            r"(Climate\s+transparency\s+in\s+[^\n]+.*?)(?=\n(?:National\s+transparency\s+framework|Baseline|Official\s+reports?\s+to\s+the\s+UNFCCC|Official\s+reporting\s+to\s+the\s+UNFCCC|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
            r"(Climate\s+transparency\s+in\s+the\s+country.*?)(?=\n(?:National\s+transparency\s+framework|Baseline|Official\s+reports?\s+to\s+the\s+UNFCCC|Official\s+reporting\s+to\s+the\s+UNFCCC|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
            r"(Climate\s+transparency.*?)(?=\n(?:National\s+transparency\s+framework|Baseline|Official\s+reports?\s+to\s+the\s+UNFCCC|Official\s+reporting\s+to\s+the\s+UNFCCC|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
            r"(Progress\s+in\s+the\s+four\s+modules\s+of\s+the\s+Enhanced\s+Transparency\s+Framework.*?)(?=\n(?:National\s+transparency\s+framework|Baseline|Official\s+reports?\s+to\s+the\s+UNFCCC|Official\s+reporting\s+to\s+the\s+UNFCCC|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
        ),
    },
    "Official Reporting to UNFCCC": {
        "bundle": "Official_reporting_UNFCCC_bundle.json",
        "directory": "Official_reporting_UNFCCC",
        "headings": (
            r"^\s*Official\s+reports?\s+to\s+the\s+UNFCCC[^\n]*",
            r"^\s*Official\s+reporting\s+to\s+the\s+UNFCCC[^\n]*",
            r"^\s*Reports\s+submitted\s+to\s+the\s+UNFCCC[^\n]*",
            r"^\s*Table\s*\d+\.?\s*Official\s+reports\s+to\s+the\s+UNFCCC[^\n]*",
        ),
        "patterns": (
            r"(Official\s+reports?\s+to\s+the\s+UNFCCC.*?)(?=\n(?:Progress\s+in\s+the\s+four\s+modules\s+of\s+the\s+Enhanced\s+Transparency\s+Framework|Progress\s+in\s+the\s+four\s+modules|Greenhouse\s+gas\s+inventory\s+module|GHG\s+inventory\s+module|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
            r"(Official\s+reporting\s+to\s+the\s+UNFCCC.*?)(?=\n(?:Progress\s+in\s+the\s+four\s+modules\s+of\s+the\s+Enhanced\s+Transparency\s+Framework|Progress\s+in\s+the\s+four\s+modules|Greenhouse\s+gas\s+inventory\s+module|GHG\s+inventory\s+module|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
            r"(Reports\s+submitted\s+to\s+the\s+UNFCCC.*?)(?=\n(?:Progress\s+in\s+the\s+four\s+modules\s+of\s+the\s+Enhanced\s+Transparency\s+Framework|Progress\s+in\s+the\s+four\s+modules|Greenhouse\s+gas\s+inventory\s+module|GHG\s+inventory\s+module|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
        ),
    },
    "Key Barriers": {
        "bundle": "Key_barriers_bundle.json",
        "directory": "Key_barriers",
        "headings": (
            r"^\s*Key\s+barriers[^\n]*",
            r"^\s*Main\s+barriers[^\n]*",
            r"^\s*Constraints\s+and\s+gaps[^\n]*",
            r"^\s*Constraints,\s+gaps\s+and\s+needs[^\n]*",
            r"^\s*Challenges\s+and\s+gaps[^\n]*",
            r"^\s*Barriers\s+to\s+enhanced\s+transparency[^\n]*",
        ),
        "patterns": (
            r"(Key\s+barriers.*?)(?=\n(?:Progress\s+in\s+the\s+four\s+modules|Greenhouse\s+gas\s+inventory\s+module|Adaptation\s+and\s+vulnerability\s+module|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
            r"(Main\s+barriers.*?)(?=\n(?:Progress\s+in\s+the\s+four\s+modules|Greenhouse\s+gas\s+inventory\s+module|Adaptation\s+and\s+vulnerability\s+module|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
            r"(Constraints\s+and\s+gaps.*?)(?=\n(?:Progress\s+in\s+the\s+four\s+modules|Greenhouse\s+gas\s+inventory\s+module|Adaptation\s+and\s+vulnerability\s+module|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
            r"(Constraints,\s+gaps\s+and\s+needs.*?)(?=\n(?:Progress\s+in\s+the\s+four\s+modules|Greenhouse\s+gas\s+inventory\s+module|Adaptation\s+and\s+vulnerability\s+module|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
            r"(Challenges\s+and\s+gaps.*?)(?=\n(?:Progress\s+in\s+the\s+four\s+modules|Greenhouse\s+gas\s+inventory\s+module|Adaptation\s+and\s+vulnerability\s+module|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
            r"(Barriers\s+to\s+enhanced\s+transparency.*?)(?=\n(?:Progress\s+in\s+the\s+four\s+modules|Greenhouse\s+gas\s+inventory\s+module|Adaptation\s+and\s+vulnerability\s+module|\n[A-Z][A-Za-z\s]{6,}\n)|$)",
        ),
    },
}

DOC_TYPE_HINTS: Tuple[Tuple[str, str], ...] = (
    ("BUR", "BUR"),
    ("Biennial Update Report", "BUR"),
    ("BTR", "BTR"),
    ("Biennial Transparency Report", "BTR"),
    ("NDC", "NDC"),
    ("Nationally Determined Contribution", "NDC"),
    ("National Communication", "NC"),
    ("NC", "NC"),
    ("Fourth National Communication", "NC4"),
    ("Third National Communication", "NC3"),
    ("Second National Communication", "NC2"),
    ("Initial National Communication", "NC1"),
)

TARGET_DOC_PREFIXES: Tuple[str, ...] = ("BUR", "BTR", "NDC", "NC")


@dataclass
class PDFLink:
    """Representation of a PDF resource of interest."""

    title: str
    url: str
    source_doc: str
    local_path: Optional[Path] = None


def slugify(value: str) -> str:
    """Convert a string into a safe filesystem slug."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return re.sub(r"_{2,}", "_", value).strip("_")


def ensure_directory(path: Path) -> None:
    """Create a directory path if it does not already exist."""
    path.mkdir(parents=True, exist_ok=True)


def request_session(cookies: Optional[Dict[str, str]] = None) -> requests.Session:
    """Create a configured requests session."""
    session = requests.Session()
    session.headers.update(HEADERS)
    session.max_redirects = 10
    if cookies:
        session.cookies.update(cookies)
    return session


def get_country_page(session: requests.Session, country_name: str) -> Tuple[str, str]:
    """
    Retrieve the HTML for the UNFCCC reports listing filtered by country.

    The site is Drupal-based; the simplest approach is to hit the reports
    listing with a full-text filter, then filter in get_pdf_links.
    """
    params = {"search_api_fulltext": country_name}
    logging.info("Fetching report listing for %s", country_name)
    response = session.get(REPORTS_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    if "_Incapsula_Resource" in response.text or "Request unsuccessful" in response.text:
        logging.error(
            "Blocked by site protection when requesting %s. Try refreshing cookies or rerunning "
            "with a cookies file captured directly from a successful browser request.",
            response.url,
        )
    logging.debug("Resolved listing URL: %s", response.url)
    return response.text, response.url


def fetch_country_results_via_ajax(session: requests.Session, country_name: str, items_per_page: int = 50) -> Optional[str]:
    """
    Query the Drupal views AJAX endpoint to retrieve filtered HTML for a country.

    Returns the concatenated HTML snippets if successful, otherwise None.
    """
    params = {
        "_wrapper_format": "drupal_ajax",
        "search3": country_name,
        "items_per_page": items_per_page,
        "view_name": "documents",
        "view_display_id": "block_4",
        "view_args": "",
        "view_path": "/reports",
        "view_base_path": "",
        "pager_element": 2,
        "_drupal_ajax": 1,
    }
    headers = {
        "Referer": REPORTS_URL,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    logging.info("Fetching AJAX listings for %s", country_name)
    response = session.get(
        REPORTS_AJAX_URL,
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        logging.warning("Unexpected content type from AJAX endpoint: %s", content_type)
        return None

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        logging.error("Failed to decode AJAX response JSON: %s", exc)
        return None

    html_fragments: List[str] = []
    if isinstance(payload, list):
        for command in payload:
            if not isinstance(command, dict):
                continue
            data = command.get("data")
            if isinstance(data, str):
                html_fragments.append(data)
    elif isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, str):
            html_fragments.append(data)

    if not html_fragments:
        logging.warning("AJAX endpoint returned no HTML fragments for %s", country_name)
        return None

    combined_html = "\n".join(html_fragments)
    logging.debug("Retrieved %d HTML fragments via AJAX", len(html_fragments))
    return combined_html


def deduce_doc_type(label: str) -> str:
    """Infer a canonical source doc label from link text or URL."""
    upper_label = label.upper()
    for needle, mapped in DOC_TYPE_HINTS:
        if needle.upper() in upper_label:
            bur_match = re.search(r"(BUR\s*\d+)", upper_label)
            if bur_match:
                return bur_match.group(1).replace(" ", "")
            btr_match = re.search(r"(BTR\s*\d+)", upper_label)
            if btr_match:
                return btr_match.group(1).replace(" ", "")
            ndc_match = re.search(r"(NDC\s*\d+)", upper_label)
            if ndc_match:
                return ndc_match.group(1).replace(" ", "")
            return mapped
    # Fallback: return uppercase alphanumeric words to avoid Unknown
    fallback = re.findall(r"[A-Z]{2,}\d*", upper_label)
    return fallback[0] if fallback else "UNKNOWN"


def build_local_pdf_link(path: Path) -> PDFLink:
    """Create a PDFLink instance for a local PDF."""
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Local PDF not found: {path}")
    title = path.stem
    doc_type = deduce_doc_type(title)
    url = path.resolve().as_uri()
    return PDFLink(title=title, url=url, source_doc=doc_type, local_path=path.resolve())


def resolve_pdf_url(session: requests.Session, href: str) -> Optional[str]:
    """Resolve a PDF URL, following detail pages if necessary."""
    absolute_url = urljoin(BASE_URL, href)
    if absolute_url.lower().endswith(".pdf"):
        return absolute_url

    logging.debug("Resolving PDF from %s", absolute_url)
    response = session.get(absolute_url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for anchor in soup.select("a[href]"):
        link = anchor["href"]
        if link.lower().endswith(".pdf"):
            logging.debug("Found PDF %s within %s", link, absolute_url)
            return urljoin(BASE_URL, link)
    logging.warning("No PDF link found within %s", absolute_url)
    return None


def get_pdf_links(session: requests.Session, html: str, country_name: str) -> List[PDFLink]:
    """
    Extract all PDF links matching BUR, BTR, NDC, or NC for the provided country.
    """
    soup = BeautifulSoup(html, "html.parser")
    table_rows = soup.select("table tbody tr")
    pdf_links: List[PDFLink] = []
    seen_urls: set[str] = set()

    if table_rows:
        for row in table_rows:
            cells = row.select("td")
            if not cells:
                continue
            row_text = " ".join(cell.get_text(" ", strip=True) for cell in cells)
            if country_name.lower() not in row_text.lower():
                continue

            file_cell_text = cells[-1].get_text(" ", strip=True).lower()
            if "pdf" not in file_cell_text:
                continue

            link_element = row.select_one("a[href*='/documents/']")
            if not link_element:
                continue
            href = link_element.get("href")
            if not href:
                continue

            doc_name = cells[0].get_text(" ", strip=True)
            doc_type_text = row_text
            doc_type = deduce_doc_type(doc_type_text or doc_name)

            if doc_type == "UNKNOWN":
                continue
            normalized_type = re.sub(r"\s+", "", doc_type.upper())
            if not any(normalized_type.startswith(prefix) for prefix in TARGET_DOC_PREFIXES):
                continue

            pdf_url = resolve_pdf_url(session, href)
            if not pdf_url:
                continue
            if pdf_url in seen_urls:
                continue
            seen_urls.add(pdf_url)
            title = doc_name or doc_type
            pdf_links.append(PDFLink(title=title, url=pdf_url, source_doc=doc_type))
    else:
        anchors = soup.select("a[href]")
        for anchor in anchors:
            href = anchor.get("href")
            if not href:
                continue
            parent = anchor.find_parent(["article", "div", "li"])
            parent_text = parent.get_text(" ", strip=True) if parent else ""
            text_blob = " ".join(
                filter(None, [anchor.get_text(strip=True), parent_text, href])
            )
            if country_name.lower() not in text_blob.lower():
                continue

            doc_type = deduce_doc_type(text_blob)
            if doc_type == "UNKNOWN":
                continue

            pdf_url = resolve_pdf_url(session, href)
            if not pdf_url:
                continue
            if pdf_url in seen_urls:
                continue
            seen_urls.add(pdf_url)
            title = anchor.get_text(strip=True) or doc_type
            pdf_links.append(PDFLink(title=title, url=pdf_url, source_doc=doc_type))

    logging.info("Identified %d candidate PDFs", len(pdf_links))
    return pdf_links


def download_pdf(session: requests.Session, pdf: PDFLink, download_dir: Path) -> Path:
    """Download a PDF if not already present."""
    if pdf.local_path:
        logging.info("Using local PDF: %s", pdf.local_path)
        return pdf.local_path

    ensure_directory(download_dir)
    parsed = urlparse(pdf.url)
    filename = Path(parsed.path).name or slugify(pdf.title) + ".pdf"
    file_path = download_dir / filename

    if file_path.exists():
        logging.info("Skipping download (exists): %s", file_path.name)
        return file_path

    logging.info("Downloading %s", pdf.url)
    with session.get(pdf.url, stream=True, timeout=REQUEST_TIMEOUT) as response:
        response.raise_for_status()
        with open(file_path, "wb") as file_handle:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if chunk:
                    file_handle.write(chunk)

    return file_path


def clean_extracted_text(text: str) -> str:
    """Normalize extracted PDF text for consistent regex processing."""
    text = text.replace("\r", "\n")
    text = re.sub(r"-\n(?=\w)", "", text)  # fix hyphenated line breaks
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def extract_sections_from_pdf(
    file_path: Path, 
    section_definitions: Dict[str, Dict[str, object]], 
    country: Optional[str] = None
) -> Dict[str, str]:
    """Extract configured sections from a PDF using regex patterns."""
    logging.info("Extracting sections from %s", file_path.name)
    with fitz.open(file_path) as document:
        pages = [page.get_text("text") for page in document]
    combined_text = clean_extracted_text("\n".join(pages))
    
    # For "Climate Transparency in [Country]" section, add country-specific patterns if country is provided
    # Create a copy of section_definitions to avoid modifying the original
    working_definitions = {k: dict(v) for k, v in section_definitions.items()}
    if country and "Climate Transparency in [Country]" in working_definitions:
        config = working_definitions["Climate Transparency in [Country]"]
        # Add country-specific heading pattern
        country_escaped = re.escape(country)
        country_specific_heading = rf"^\s*Climate\s+transparency\s+in\s+{country_escaped}[^\n]*"
        # Add country-specific pattern
        country_specific_pattern = rf"(Climate\s+transparency\s+in\s+{country_escaped}.*?)(?=\n(?:National\s+transparency\s+framework|Baseline|Official\s+reports?\s+to\s+the\s+UNFCCC|Official\s+reporting\s+to\s+the\s+UNFCCC|\n[A-Z][A-Za-z\s]{{6,}}\n)|$)"
        
        # Update the config copy with country-specific patterns
        original_headings = config.get("headings", ())
        original_patterns = config.get("patterns", ())
        config["headings"] = (country_specific_heading,) + original_headings
        config["patterns"] = (country_specific_pattern,) + original_patterns

    extracted: Dict[str, str] = {}
    section_spans: Dict[str, Tuple[int, int]] = {}
    heading_flags = re.IGNORECASE | re.MULTILINE

    for section, config in working_definitions.items():
        # First, try to locate the heading.
        raw_headings = config.get("headings", [])
        if isinstance(raw_headings, (str, bytes)):
            heading_patterns: Iterable[str] = [raw_headings]  # type: ignore[list-item]
        elif isinstance(raw_headings, Iterable):
            heading_patterns = raw_headings  # type: ignore[assignment]
        else:
            heading_patterns = []

        heading_match = None
        for pattern in heading_patterns:
            try:
                heading_match = re.search(pattern, combined_text, flags=heading_flags)
            except re.error as exc:
                logging.error("Invalid heading regex '%s': %s", pattern, exc)
                continue
            if heading_match:
                section_spans[section] = (heading_match.start(), heading_match.end())
                logging.debug("Located heading for %s via pattern %s", section, pattern)
                break

        if section in section_spans:
            continue

        # Fallback to legacy full-section patterns.
        raw_patterns = config.get("patterns", [])
        if isinstance(raw_patterns, (str, bytes)):
            patterns: Iterable[str] = [raw_patterns]  # type: ignore[list-item]
        elif isinstance(raw_patterns, Iterable):
            patterns = raw_patterns  # type: ignore[assignment]
        else:
            patterns = []

        for pattern in patterns:
            try:
                match = re.search(pattern, combined_text, flags=re.IGNORECASE | re.DOTALL)
            except re.error as exc:
                logging.error("Invalid regex '%s': %s", pattern, exc)
                continue
            if match:
                section_spans[section] = (match.start(), match.end())
                logging.debug("Matched section %s via fallback pattern %s", section, pattern)
                break

        if section not in section_spans:
            logging.warning("Section '%s' not found in %s", section, file_path.name)

    if not section_spans:
        return extracted

    ordered_sections = sorted(section_spans.items(), key=lambda item: item[1][0])
    for index, (section, (start, _)) in enumerate(ordered_sections):
        next_start = (
            ordered_sections[index + 1][1][0]
            if index + 1 < len(ordered_sections)
            else len(combined_text)
        )

        # Include preceding roman numeral label if present.
        previous_newline = combined_text.rfind("\n", 0, start)
        if previous_newline != -1:
            line = combined_text[previous_newline + 1 : start]
            if re.match(r"^\s*[ivxlcdm]+\.\s*$", line, flags=re.IGNORECASE):
                start = previous_newline + 1

        section_text = combined_text[start:next_start].strip()
        if section_text:
            extracted[section] = section_text
        else:
            logging.warning("Section '%s' text empty after extraction in %s", section, file_path.name)

    return extracted


def build_json_entry(
    country: str,
    section: str,
    source_doc: str,
    url: str,
    text: str,
    timestamp: datetime,
) -> Dict[str, object]:
    """Return a structured JSON entry ready for persistence."""
    return {
        "country": country,
        "section": section,
        "source_doc": source_doc,
        "doc_url": url,
        "extracted_text": text,
        "created_utc": timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def merge_bundles(
    bundle_path: Path,
    new_entries: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    """Merge new entries with existing bundle file, marking stale ones as needed."""
    if bundle_path.exists():
        with open(bundle_path, "r", encoding="utf-8") as handle:
            existing_entries = json.load(handle)
    else:
        existing_entries = []

    key_fields = ("country", "section", "source_doc", "doc_url")
    existing_lookup = {
        tuple(entry[field] for field in key_fields): entry for entry in existing_entries
    }

    merged_entries: Dict[Tuple[str, ...], Dict[str, object]] = {}

    for entry in new_entries:
        key = tuple(entry[field] for field in key_fields)
        existing = existing_lookup.get(key)
        if existing and existing.get("extracted_text") == entry["extracted_text"]:
            entry["created_utc"] = existing.get("created_utc", entry["created_utc"])
        merged_entries[key] = entry

    sorted_entries = sorted(
        merged_entries.values(),
        key=lambda item: (item["country"], item["source_doc"], item["created_utc"]),
    )
    return sorted_entries


def write_section_outputs(
    data_dir: Path,
    section: str,
    entries: List[Dict[str, object]],
) -> None:
    """Persist bundle and per-document JSONs for a section."""
    ensure_directory(data_dir)
    section_config = SECTION_DEFINITIONS.get(section, {})
    bundle_name = section_config.get("bundle") or f"{slugify(section)}_bundle.json"
    directory_name = section_config.get("directory") or slugify(section)

    section_dir = data_dir / directory_name
    ensure_directory(section_dir)

    bundle_path = data_dir / bundle_name
    merged_entries = merge_bundles(bundle_path, entries)

    with open(bundle_path, "w", encoding="utf-8") as handle:
        json.dump(merged_entries, handle, ensure_ascii=False, indent=2)
    logging.info("Wrote %s (%d records)", bundle_path, len(merged_entries))

    # Write per source_doc files inside section directory for inspection.
    docs: Dict[str, List[Dict[str, object]]] = {}
    for entry in entries:
        docs.setdefault(entry["source_doc"], []).append(entry)

    for source_doc, doc_entries in docs.items():
        # Use proper naming convention: {Country}_{SectionName}_{DocType}.json
        if doc_entries:
            country = doc_entries[0].get("country", "Unknown")
            # Convert section name to PascalCase format (e.g., "Institutional framework for climate action" -> "InstitutionalFrameworkForClimateAction")
            section_pascal = "".join(word.capitalize() for word in section.split())
            doc_name = f"{{{country}}}_{{{section_pascal}}}_{{{source_doc or 'document'}}}.json"
        else:
            doc_name = slugify(source_doc or "document") + ".json"
        doc_path = section_dir / doc_name
        with open(doc_path, "w", encoding="utf-8") as handle:
            json.dump(doc_entries, handle, ensure_ascii=False, indent=2)
        logging.debug("Wrote %s", doc_path)


def connect_to_supabase() -> Optional[Client]:
    """Connect to Supabase and return client, or None if unavailable."""
    if not SUPABASE_AVAILABLE:
        return None
    
    try:
        config_path = Path(__file__).parent / "supabase_config.json"
        if not config_path.exists():
            logging.debug("Supabase config not found, skipping database check")
            return None
        
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        url = config.get("project_url")
        key = config.get("api_key")
        
        if not url or not key:
            logging.debug("Supabase credentials incomplete, skipping database check")
            return None
        
        return create_client(url, key)
    except Exception as exc:
        logging.debug("Failed to connect to Supabase: %s", exc)
        return None


def get_country_from_database(client: Client, country_name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve country data from Supabase countries table.
    
    Returns:
        Dictionary with 'name' and 'sections' keys, or None if not found
    """
    try:
        response = client.table("countries").select("name, sections").eq("name", country_name).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as exc:
        logging.debug("Error querying database for %s: %s", country_name, exc)
        return None


def convert_db_sections_to_entries(
    country: str,
    db_data: Dict[str, Any],
    timestamp: datetime,
    section_definitions: Optional[Dict[str, Dict[str, object]]] = None,
) -> Dict[str, List[Dict[str, object]]]:
    """
    Convert database sections JSON to the format expected by the pipeline.
    
    Args:
        country: Country name
        db_data: Database record with 'sections' jsonb field
        timestamp: Timestamp to use for entries
        section_definitions: Section definitions to filter by (default: all sections)
        
    Returns:
        Dictionary mapping section names to lists of entries
    """
    section_defs = section_definitions or SECTION_DEFINITIONS
    collected: Dict[str, List[Dict[str, object]]] = {
        section: [] for section in section_defs
    }
    
    sections_data = db_data.get("sections", {})
    if not isinstance(sections_data, dict) or "sections" not in sections_data:
        logging.warning("Invalid sections format in database for %s", country)
        return collected
    
    for section_obj in sections_data.get("sections", []):
        section_name = section_obj.get("name", "")
        if section_name not in section_defs:
            continue
        
        for doc in section_obj.get("documents", []):
            doc_type = doc.get("doc_type", "")
            extracted_text = doc.get("extracted_text", "")
            
            entry = build_json_entry(
                country=country,
                section=section_name,
                source_doc=doc_type,
                url="",  # Not stored in new format
                text=extracted_text,
                timestamp=timestamp,
            )
            collected[section_name].append(entry)
    
    return collected


def check_and_use_database_data(
    country: str,
    output_root: Path,
    force_scrape: bool = False,
    section_definitions: Optional[Dict[str, Dict[str, object]]] = None,
) -> bool:
    """
    Check if country data exists in database and use it if available.
    
    Args:
        country: Country name to check
        output_root: Output directory for writing JSON files
        force_scrape: If True, skip database check and always scrape
        
    Returns:
        True if database data was used, False if scraping should proceed
    """
    if force_scrape:
        return False
    
    client = connect_to_supabase()
    if not client:
        logging.debug("Supabase not available, proceeding with scrape")
        return False
    
    db_data = get_country_from_database(client, country)
    if not db_data:
        logging.info("No existing data found in database for %s, proceeding with scrape", country)
        return False
    
    logging.info("Found existing data in database for %s, using database data instead of scraping", country)
    
    # Convert database data to entries format
    timestamp = datetime.now(timezone.utc)
    collected = convert_db_sections_to_entries(country, db_data, timestamp, section_definitions)
    
    # Write the data to output files (same format as scraping would produce)
    for section_name, entries in collected.items():
        if entries:
            write_section_outputs(output_root, section_name, entries)
        else:
            logging.warning("No entries found for section '%s' in database data", section_name)
    
    return True


def check_cbit_database(country: str) -> bool:
    """
    Check GEF database for completed CBIT projects for a given country.
    Returns True if a CBIT project exists (CBIT Yes, Completed), False otherwise.
    Source: https://www.thegef.org/projects-operations/database
    """
    # Known CBIT projects from GEF database (hardcoded for speed)
    # Source: https://www.thegef.org/projects-operations/database?f%5B0%5D=capacity_building_initiative_for_transparency%3A2071&f%5B1%5D=latest_timeline_status%3A396
    known_cbit_countries = {
        "Kenya", "Armenia", "Bosnia-Herzegovina", "Cambodia", "Chile", "China",
        "Costa Rica", "Cote d'Ivoire", "Georgia", "Ghana", "Jamaica", "Liberia",
        "Madagascar", "Mongolia", "Nicaragua", "North Macedonia", "Panama",
        "Papua New Guinea", "Serbia", "Uganda", "Uruguay"
    }
    
    # Use print with flush for immediate feedback before logging is fully configured
    print(f"[INFO] Checking CBIT database for {country}...", flush=True)
    
    if country in known_cbit_countries:
        print(f"[INFO] Found CBIT project for {country} in known CBIT projects list", flush=True)
        logging.info("Found CBIT project for %s in known CBIT projects list", country)
        return True
    
    # For unknown countries, try to check the database (with timeout)
    print(f"[INFO] {country} not in known list, checking GEF database (this may take a few seconds)...", flush=True)
    try:
        base_url = "https://www.thegef.org/projects-operations/database"
        url = f"{base_url}?f%5B0%5D=capacity_building_initiative_for_transparency%3A2071&f%5B1%5D=latest_timeline_status%3A396"
        
        logging.info("Checking GEF database for CBIT projects for %s...", country)
        response = requests.get(url, timeout=5, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        if response.status_code == 200:
            country_regex = re.compile(rf'\b{re.escape(country)}\b', re.IGNORECASE)
            has_country = bool(country_regex.search(response.text))
            if has_country:
                print(f"[INFO] Found CBIT project for {country} in GEF database")
                logging.info("Found CBIT project for %s in GEF database", country)
                return True
            else:
                print(f"[INFO] No CBIT project found for {country} in GEF database")
                logging.info("No CBIT project found for %s in GEF database", country)
                return False
        else:
            print(f"[WARNING] Failed to fetch GEF database: {response.status_code}")
            logging.warning("Failed to fetch GEF database: %s", response.status_code)
            return False
    except Exception as exc:
        print(f"[WARNING] Error checking CBIT database: {exc}. Proceeding without CBIT check.")
        logging.warning("Error checking CBIT database: %s. Proceeding without CBIT check.", exc)
        return False


def prompt_for_file(prompt_message: str) -> Optional[str]:
    """
    Generic function to prompt user for document upload (supports both local file paths and URLs).
    Returns the file content as a string, or None if user presses enter.
    """
    print(f"\n{prompt_message}", flush=True)
    print("File path or URL: ", end="", flush=True)
    user_input = input().strip()
    
    if not user_input:
        return None
    
    # Check if input is a URL
    is_url = user_input.startswith("http://") or user_input.startswith("https://")
    
    if is_url:
        # Fetch from URL
        try:
            logging.info("Fetching content from URL: %s", user_input)
            response = requests.get(user_input, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            if not response.ok:
                logging.error("HTTP error! status: %s", response.status_code)
                return None
            
            content_type = response.headers.get("content-type", "").lower()
            
            if "application/pdf" in content_type or user_input.lower().endswith(".pdf"):
                # Handle PDF: extract text
                logging.info("Detected PDF file, extracting text...")
                import io
                pdf_bytes = io.BytesIO(response.content)
                pdf_bytes.seek(0)  # Ensure stream is at the beginning
                try:
                    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                        text_parts = []
                        page_count = len(doc)
                        for page in doc:
                            text_parts.append(page.get_text("text"))
                        extracted_text = "\n".join(text_parts)
                        logging.info("Successfully extracted text from PDF (%d characters, %d pages)", 
                                   len(extracted_text), page_count)
                    return extracted_text
                except Exception as pdf_error:
                    logging.error("Error extracting text from PDF: %s", pdf_error)
                    return None
            else:
                # Handle text-based content
                content = response.text
                logging.info("Successfully fetched content from URL (%d characters)", len(content))
                return content
        except Exception as error:
            logging.error("Error fetching URL: %s", error)
            return None
    else:
        # Handle as local file path
        try:
            file_path = Path(user_input)
            if not file_path.is_absolute():
                file_path = Path.cwd() / file_path
            
            if not file_path.exists():
                logging.error("File not found: %s", file_path)
                return None
            
            if file_path.suffix.lower() == ".pdf":
                # Extract text from PDF
                logging.info("Extracting text from PDF: %s", file_path)
                try:
                    with fitz.open(str(file_path)) as doc:
                        text_parts = []
                        page_count = len(doc)
                        for page in doc:
                            text_parts.append(page.get_text("text"))
                        extracted_text = "\n".join(text_parts)
                        logging.info("Successfully extracted text from PDF (%d characters, %d pages)",
                                   len(extracted_text), page_count)
                    return extracted_text
                except Exception as pdf_error:
                    logging.error("Error extracting text from PDF: %s", pdf_error)
                    return None
            else:
                # Read as text file
                content = file_path.read_text(encoding="utf-8")
                logging.info("Successfully loaded file: %s", file_path)
                return content
        except Exception as error:
            logging.error("Error reading file: %s", error)
            return None


def prompt_for_cbit_file(country: str) -> Optional[str]:
    """
    Prompt user for CBIT document upload (supports both local file paths and URLs).
    Returns the file content as a string, or None if user presses enter.
    """
    prompt_message = f"There was CBIT 1 for {country} published. Are there any relevant documents you can upload? If not, press enter"
    return prompt_for_file(prompt_message)


def main(
    country: str,
    output_root: Optional[Path] = None,
    download_root: Optional[Path] = None,
    cookies: Optional[Dict[str, str]] = None,
    local_pdfs: Optional[List[Path]] = None,
    local_pdf_dir: Optional[Path] = None,
    skip_scrape: bool = False,
    force_scrape: bool = False,
    sections: Optional[List[str]] = None,
) -> None:
    """End-to-end pipeline orchestrator."""
    # Filter section definitions based on requested sections
    requested_sections = sections or list(SECTION_DEFINITIONS.keys())
    active_section_definitions = {
        name: config for name, config in SECTION_DEFINITIONS.items()
        if name in requested_sections
    }
    
    if not active_section_definitions:
        logging.error("No valid sections specified. Available: %s", ", ".join(SECTION_DEFINITIONS.keys()))
        return
    
    output_root = output_root or Path(__file__).resolve().parent / "data"
    ensure_directory(output_root)
    
    # ICAT/PATPA Prompt: Ask for relevant transparency framework documents
    print(f"\n[INFO] === Starting process for {country} ===\n", flush=True)
    print("[INFO] Step 0: Checking for ICAT/PATPA documents...", flush=True)
    logging.info("=== Starting process for %s ===", country)
    logging.info("Step 0: Checking for ICAT/PATPA documents...")
    
    icat_patpa_info: Optional[str] = None
    icat_patpa_prompt = (
        f"Are there any documents relevant to Initiative for Climate Action Transparency (ICAT) "
        f"or Partnership on Transparency in the Paris Agreement (PATPA) for {country}? "
        f"If not, press enter"
    )
    icat_patpa_info = prompt_for_file(icat_patpa_prompt)
    
    if icat_patpa_info:
        # Check for transparency framework keywords
        transparency_keywords = ["transparency framework", "enhanced transparency", "ETF", 
                                "ICAT", "PATPA", "biennial transparency report", "BTR"]
        has_relevant_content = any(keyword.lower() in icat_patpa_info.lower() for keyword in transparency_keywords)
        
        if has_relevant_content:
            print(f"[INFO] ICAT/PATPA document loaded with relevant transparency framework content. Proceeding with creating PIF.")
            logging.info("ICAT/PATPA document loaded with relevant transparency framework content.")
            # Save ICAT/PATPA info to a file for later use in PDF generation
            icat_patpa_file = output_root / f"{country}_icat_patpa_info.txt"
            icat_patpa_file.write_text(icat_patpa_info, encoding="utf-8")
            print(f"[INFO] Saved ICAT/PATPA information to {icat_patpa_file}")
            logging.info("Saved ICAT/PATPA information to %s", icat_patpa_file)
        else:
            print(f"[INFO] ICAT/PATPA document loaded but does not contain relevant transparency framework keywords. Proceeding with creating PIF.")
            logging.info("ICAT/PATPA document loaded but does not contain relevant transparency framework keywords.")
    else:
        print(f"[INFO] No ICAT/PATPA document provided for {country}. Proceeding with creating PIF.")
        logging.info("No ICAT/PATPA document provided for %s. Proceeding with creating PIF.", country)
    
    # CBIT Check: Check database for completed CBIT projects
    print("[INFO] Step 1: Checking CBIT database...", flush=True)
    logging.info("=== Starting process for %s ===", country)
    logging.info("Step 1: Checking CBIT database...")
    cbit_info: Optional[str] = None
    has_cbit_project = check_cbit_database(country)
    
    if has_cbit_project:
        print(f"[INFO] CBIT Check: Found a completed CBIT project for {country}.", flush=True)
        logging.info("CBIT Check: Found a completed CBIT project for %s.", country)
        cbit_info = prompt_for_cbit_file(country)
        
        if cbit_info:
            print(f"[INFO] CBIT document loaded. Proceeding with creating PIF.")
            logging.info("CBIT document loaded. Proceeding with creating PIF.")
            # Save CBIT info to a file for later use in PDF generation
            cbit_file = output_root / f"{country}_cbit_info.txt"
            cbit_file.write_text(cbit_info, encoding="utf-8")
            print(f"[INFO] Saved CBIT information to {cbit_file}")
            logging.info("Saved CBIT information to %s", cbit_file)
        else:
            print(f"[INFO] No CBIT document provided for {country}. Proceeding with creating PIF.")
            logging.info("No CBIT document provided for %s. Proceeding with creating PIF.", country)
    else:
        print(f"[INFO] CBIT Check: No completed CBIT project found for {country}. Proceeding with creating PIF.")
        logging.info("CBIT Check: No completed CBIT project found for %s. Proceeding with creating PIF.", country)
    
    # Check database first before scraping
    if not force_scrape and not skip_scrape:
        if check_and_use_database_data(country, output_root, force_scrape, active_section_definitions):
            logging.info("Using database data for %s, skipping scrape", country)
            return
    
    # Proceed with scraping if database check didn't find data or force_scrape is True
    session = request_session(cookies=cookies)
    pdf_links: List[PDFLink] = []

    if not skip_scrape:
        try:
            ajax_html = fetch_country_results_via_ajax(session, country)
            if ajax_html:
                logging.info("Processing AJAX listings for %s", country)
                pdf_links.extend(get_pdf_links(session, ajax_html, country))
            else:
                html, resolved_url = get_country_page(session, country)
                logging.info("Processing listings from %s", resolved_url)
                pdf_links.extend(get_pdf_links(session, html, country))
        except requests.HTTPError as exc:
            logging.error("Failed to scrape UNFCCC site: %s", exc)
        except Exception as exc:  # pragma: no cover - network guard
            logging.error("Unexpected scraping error: %s", exc)

    local_pdfs = local_pdfs or []
    for local_path in local_pdfs:
        try:
            pdf_links.append(build_local_pdf_link(local_path))
        except Exception as exc:
            logging.error("Failed to register local PDF %s: %s", local_path, exc)

    if local_pdf_dir:
        for pdf_path in sorted(Path(local_pdf_dir).glob("*.pdf")):
            try:
                pdf_links.append(build_local_pdf_link(pdf_path))
            except Exception as exc:
                logging.error("Failed to register local PDF %s: %s", pdf_path, exc)

    deduped: List[PDFLink] = []
    seen_urls: set[str] = set()
    for link in pdf_links:
        key = link.url if link.url else str(link.local_path)
        if key in seen_urls:
            continue
        seen_urls.add(key)
        deduped.append(link)
    pdf_links = deduped

    if not pdf_links:
        logging.warning("No PDFs found for %s. Exiting.", country)
        return

    timestamp = datetime.now(timezone.utc)
    download_root = download_root or Path(__file__).resolve().parent / "downloads"
    ensure_directory(download_root)

    collected: Dict[str, List[Dict[str, object]]] = {
        section: [] for section in active_section_definitions
    }

    for pdf in pdf_links:
        file_path = download_pdf(session, pdf, download_root)
        extracted_sections = extract_sections_from_pdf(file_path, active_section_definitions, country)
        for section_name, text in extracted_sections.items():
            entry = build_json_entry(
                country=country,
                section=section_name,
                source_doc=pdf.source_doc,
                url=pdf.url,
                text=text,
                timestamp=timestamp,
            )
            collected[section_name].append(entry)

    for section_name, entries in collected.items():
        if entries:
            write_section_outputs(output_root, section_name, entries)
        else:
            logging.warning("No entries extracted for section '%s'", section_name)


def load_cookies(filepath: Path) -> Dict[str, str]:
    """Load cookies from a JSON file."""
    with open(filepath, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Cookie file must contain a JSON object of name/value pairs.")
    # Ensure all values are strings
    return {str(key): str(value) for key, value in data.items()}


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Scrape UNFCCC reports for PIF sections.")
    parser.add_argument("--country", required=True, help="Country name to filter UNFCCC reports.")
    parser.add_argument(
        "--sections",
        nargs="+",
        choices=list(SECTION_DEFINITIONS.keys()),
        default=list(SECTION_DEFINITIONS.keys()),
        help="Sections to extract (default: all sections). Available: " + ", ".join(SECTION_DEFINITIONS.keys()),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional override for the output data directory.",
    )
    parser.add_argument(
        "--download-dir",
        default=None,
        help="Optional override for the PDF download directory.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity.",
    )
    parser.add_argument(
        "--cookies-file",
        default=None,
        help="Optional path to a JSON file containing cookie name/value pairs to bypass WAF.",
    )
    parser.add_argument(
        "--local-pdf",
        action="append",
        default=[],
        help="Path to a local PDF to process (can be passed multiple times).",
    )
    parser.add_argument(
        "--local-pdf-dir",
        default=None,
        help="Process all PDFs inside this directory.",
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Skip remote scraping and use only local PDFs.",
    )
    parser.add_argument(
        "--force-scrape",
        action="store_true",
        help="Force scraping even if country data exists in database.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = parse_args()
    
    logging.basicConfig(
        level=getattr(logging, arguments.log_level.upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )
    output_dir = Path(arguments.output_dir) if arguments.output_dir else None
    download_dir = Path(arguments.download_dir) if arguments.download_dir else None

    cookies: Optional[Dict[str, str]] = None
    if arguments.cookies_file:
        cookies = load_cookies(Path(arguments.cookies_file))

    local_pdf_paths = [Path(item) for item in arguments.local_pdf] if arguments.local_pdf else None
    local_pdf_directory = Path(arguments.local_pdf_dir) if arguments.local_pdf_dir else None

    try:
        main(
            arguments.country,
            output_dir,
            download_dir,
            cookies,
            local_pdf_paths,
            local_pdf_directory,
            arguments.skip_scrape,
            arguments.force_scrape,
            arguments.sections,
        )
    except requests.HTTPError as err:
        logging.error("HTTP error: %s", err)
        sys.exit(1)
    except Exception as err:  # pragma: no cover - top-level guard
        logging.exception("Unexpected error: %s", err)
        sys.exit(1)

