"""
Unified BUR Web Scraper and Extractor

Combines functionality from:
- bur_transparency_extractor.py (BUR web scraping and transparency sections)
- pdf_scraper.py (local PDF processing and other sections)

Supports:
- Downloading BURs from UNFCCC website
- Processing local BUR PDF files
- Extracting multiple section types:
  - Climate Transparency
  - Official Reporting to the UNFCCC
  - Key Barriers
  - NDC Tracking Module
  - Support Needed and Received Module
  - Other baseline initiatives
- AI-powered extraction (OpenAI) with keyword fallback
- Supabase integration for data storage
"""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import pdfplumber
import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Load environment variables
load_dotenv()

# Configuration
BUR_LISTING_URL = "https://unfccc.int/BURs"
SCRIPT_DIR = Path(__file__).parent.resolve()
BUR_PDF_DIR = SCRIPT_DIR.parent / "downloads" / "bur_modules"
BUR_PDF_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class SupabaseConfig:
    """Configuration for Supabase REST API client."""
    url: str
    api_key: str
    table: str = "country_sections"
    country_column: str = "country"
    sections_column: str = "sections"

    @classmethod
    def from_env(cls) -> "SupabaseConfig":
        """
        Read Supabase configuration from environment variables or .env file.
        
        Required:
        - SUPABASE_URL
        - SUPABASE_API_KEY
        
        Optional (with defaults):
        - SUPABASE_TABLE
        - SUPABASE_COUNTRY_COLUMN
        - SUPABASE_SECTIONS_COLUMN
        """
        # Try to find .env file in project root
        project_root = SCRIPT_DIR.parent.parent.parent  # Go up to UNEPxBerkeley
        
        env_path = project_root / ".env"
        if env_path.exists():
            from dotenv import dotenv_values
            env_vars = dotenv_values(env_path)
            url = env_vars.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
            api_key = env_vars.get("SUPABASE_API_KEY") or os.getenv("SUPABASE_API_KEY")
        else:
            url = os.getenv("SUPABASE_URL")
            api_key = os.getenv("SUPABASE_API_KEY")
        
        if not url or not api_key:
            raise RuntimeError(
                "Supabase config missing. Please set SUPABASE_URL and SUPABASE_API_KEY "
                "environment variables (e.g. in a .env file in the project root)."
            )
        
        table = os.getenv("SUPABASE_TABLE", "country_sections")
        country_column = os.getenv("SUPABASE_COUNTRY_COLUMN", "country")
        sections_column = os.getenv("SUPABASE_SECTIONS_COLUMN", "sections")
        
        return cls(
            url=url.rstrip("/"),
            api_key=api_key,
            table=table,
            country_column=country_column,
            sections_column=sections_column,
        )


class SupabaseClient:
    """Client for interacting with Supabase REST API."""
    
    def __init__(self, config: SupabaseConfig):
        self.config = config
        self.base_rest_url = f"{config.url}/rest/v1"
        self.session = requests.Session()
        self.session.headers.update({
            "apikey": config.api_key,
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        })
    
    def get_country_record(self, country: str) -> Optional[Dict]:
        """Fetch existing record for a given country, if any."""
        params = {
            "select": "*",
            f"{self.config.country_column}": f"eq.{country}",
        }
        url = f"{self.base_rest_url}/{self.config.table}"
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return data[0]
    
    def upsert_country_sections(
        self,
        country: str,
        new_sections: Dict[str, Any],
        doc_type: Optional[str] = None,
    ) -> Dict:
        """
        Merge new section text into the country's existing sections JSON and upsert.
        
        Expected format for new_sections:
        Option 1 (transparency sections):
        {
            "ClimateTransparency": {"doc_type": "BUR", "text": "..."},
            "OfficialReportingUNFCCC": {"doc_type": "BUR", "text": "..."},
            "KeyBarriers": {"doc_type": "BUR", "text": "..."}
        }
        
        Option 2 (other sections with doc_type parameter):
        {
            "NDC Tracking Module": "text...",
            "Support Needed and Received Module": "text...",
            "Other baseline initiatives": "text..."
        }
        """
        existing = self.get_country_record(country)
        
        if existing and self.config.sections_column in existing:
            sections_data = existing.get(self.config.sections_column) or {}
        else:
            sections_data = {}
        
        # Ensure sections list exists
        if "sections" not in sections_data:
            sections_data["sections"] = []
        
        sections_list = sections_data["sections"]
        
        # Process each new section
        for section_key, section_value in new_sections.items():
            # Handle two different formats
            if isinstance(section_value, dict) and "text" in section_value:
                # Format 1: Transparency sections
                text = section_value.get("text", "")
                doc_type = section_value.get("doc_type", "BUR")
                section_name_map = {
                    "ClimateTransparency": "Climate Transparency",
                    "OfficialReportingUNFCCC": "Official Reporting to UNFCCC",
                    "KeyBarriers": "Key Barriers"
                }
                section_name = section_name_map.get(section_key, section_key)
            else:
                # Format 2: Other sections (string value)
                text = section_value if isinstance(section_value, str) else ""
                section_name = section_key
                if not doc_type:
                    doc_type = "BUR"
            
            if not text:
                continue  # Skip empty sections
            
            # Find or create the section object
            section_obj = None
            for sec in sections_list:
                if sec.get("name") == section_name:
                    section_obj = sec
                    break
            
            if section_obj is None:
                section_obj = {
                    "name": section_name,
                    "documents": []
                }
                sections_list.append(section_obj)
            
            # Ensure documents list exists
            if "documents" not in section_obj:
                section_obj["documents"] = []
            
            # Find or update the document for this doc_type
            doc_found = False
            for doc in section_obj["documents"]:
                if doc.get("doc_type") == doc_type:
                    doc["extracted_text"] = text
                    doc_found = True
                    break
            
            if not doc_found:
                section_obj["documents"].append({
                    "doc_type": doc_type,
                    "extracted_text": text
                })
        
        payload = {
            self.config.country_column: country,
            self.config.sections_column: sections_data,
        }
        
        url = f"{self.base_rest_url}/{self.config.table}"
        
        # Update if exists, insert if new
        if existing:
            row_id = existing.get("id")
            if row_id is not None:
                update_url = f"{url}?id=eq.{row_id}"
            else:
                update_url = f"{url}?{self.config.country_column}=eq.{country}"
            
            headers = {"Prefer": "return=representation"}
            resp = self.session.patch(
                update_url,
                data=json.dumps({self.config.sections_column: sections_data}),
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()[0] if resp.content else {}
        else:
            headers = {"Prefer": "return=representation"}
            resp = self.session.post(url, data=json.dumps(payload), headers=headers)
            resp.raise_for_status()
            return resp.json()[0] if resp.content else {}


# ============================================================================
# BUR Web Scraping Functions
# ============================================================================

def fetch_bur_listing_page() -> BeautifulSoup:
    """Fetch and parse the UNFCCC BUR listing page."""
    resp = requests.get(BUR_LISTING_URL)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def find_status_table(soup: BeautifulSoup):
    """Find the BUR status table on the listing page."""
    tables = soup.find_all("table")
    for t in tables:
        text = t.get_text(" ", strip=True)
        if (
            "Status of BUR submissions" in text
            or "Status of submission of biennial update reports" in text
        ):
            return t
    return tables[-1] if tables else None


def normalize_country_name_for_match(name: str) -> str:
    """Normalize country name for matching."""
    return re.sub(r"[\s\-]", "", name.lower())


def get_latest_bur_link_for_country(
    country: str, soup: Optional[BeautifulSoup] = None
) -> Optional[str]:
    """Find the latest BUR link for a given country."""
    if soup is None:
        soup = fetch_bur_listing_page()
    
    table = find_status_table(soup)
    if table is None:
        print("[SCRAPER] Could not find BUR status table.")
        return None
    
    target_norm = normalize_country_name_for_match(country)
    
    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if not cols:
            continue
        
        party_text = cols[0].get_text(strip=True)
        party_norm = normalize_country_name_for_match(party_text)
        
        if party_norm == target_norm:
            latest_link = None
            latest_label = None
            
            for idx, col in enumerate(cols[1:], start=1):
                a = col.find("a", href=True)
                if a:
                    href = a["href"]
                    latest_link = href
                    latest_label = f"BUR{idx}"
            
            if latest_link:
                if latest_link.startswith("/"):
                    latest_link = "https://unfccc.int" + latest_link
                print(
                    f"[SCRAPER] Latest BUR for {country}: {latest_label} -> {latest_link}"
                )
                return latest_link
    
    print(f"[SCRAPER] No BUR link found for {country} on listing page.")
    return None


def normalize_country_for_filename(country: str) -> str:
    """Normalize country name for use in filenames."""
    return re.sub(r"[\s\-]", "_", country.upper())


def download_bur_pdf(url: str, country: str) -> Path:
    """Download a BUR PDF from the given URL."""
    country_norm = normalize_country_for_filename(country)
    filename = f"{country_norm}_BUR_latest.pdf"
    path = BUR_PDF_DIR / filename
    
    resp = requests.get(url)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)
    
    print(f"[DOWNLOAD] Saved {country} BUR -> {path}")
    return path


def get_or_download_bur_pdf(country: str, bur_url: Optional[str] = None) -> Optional[Path]:
    """Get cached BUR PDF or download if not present."""
    country_norm = normalize_country_for_filename(country)
    path = BUR_PDF_DIR / f"{country_norm}_BUR_latest.pdf"
    
    if path.exists():
        print(f"[DOWNLOAD] Using cached BUR for {country}: {path}")
        return path
    
    if bur_url:
        return download_bur_pdf(bur_url, country)
    
    return None


# ============================================================================
# PDF Text Extraction
# ============================================================================

def extract_text_from_pdf(path: Path) -> str:
    """Extract raw text from a PDF file using pdfplumber."""
    texts: List[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            texts.append(page_text)
    return "\n".join(texts)


def load_pdf_text(path: Path) -> str:
    """Extract text from a PDF file using PyMuPDF (alternative method)."""
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    doc = fitz.open(str(path))
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return "\n".join(pages)


# ============================================================================
# Transparency Section Extraction (from bur_transparency_extractor.py)
# ============================================================================

def extract_between(
    text: str, start_patterns: List[str], end_patterns: Optional[List[str]] = None
) -> str:
    """Extract text between start and end patterns."""
    start_re = re.compile("|".join(start_patterns), re.IGNORECASE)
    m_start = start_re.search(text)
    if not m_start:
        return ""
    
    start_idx = m_start.end()
    
    if end_patterns:
        end_re = re.compile("|".join(end_patterns), re.IGNORECASE)
        m_end = end_re.search(text, start_idx)
        end_idx = m_end.start() if m_end else len(text)
    else:
        end_idx = len(text)
    
    snippet = text[start_idx:end_idx].strip()
    return snippet


def extract_climate_transparency(text: str, country: str) -> str:
    """Extract Climate Transparency section."""
    start_patterns = [
        rf"Climate transparency in {re.escape(country)}",
        r"Climate transparency in the country",
        r"Climate transparency",
        r"Progress in the four modules of the Enhanced Transparency Framework",
    ]
    end_patterns = [
        r"National transparency framework",
        r"Baseline",
        r"Official reports? to the UNFCCC",
        r"Official reporting to the UNFCCC",
        r"\n[A-Z][A-Za-z ]{6,}\n",
    ]
    return extract_between(text, start_patterns, end_patterns)


def extract_official_reporting(text: str) -> str:
    """Extract Official Reporting to UNFCCC section."""
    start_patterns = [
        r"Official reports? to the UNFCCC",
        r"Official reporting to the UNFCCC",
        r"Reports submitted to the UNFCCC",
        r"Table\s*\d+\.?\s*Official reports to the UNFCCC",
    ]
    end_patterns = [
        r"Progress in the four modules of the Enhanced Transparency Framework",
        r"Progress in the four modules",
        r"Greenhouse gas inventory module",
        r"GHG inventory module",
        r"\n[A-Z][A-Za-z ]{6,}\n",
    ]
    return extract_between(text, start_patterns, end_patterns)


def extract_key_barriers(text: str) -> str:
    """Extract Key Barriers section."""
    start_patterns = [
        r"Key barriers",
        r"Main barriers",
        r"Constraints and gaps",
        r"Constraints, gaps and needs",
        r"Challenges and gaps",
        r"Barriers to enhanced transparency",
    ]
    end_patterns = [
        r"Progress in the four modules",
        r"Greenhouse gas inventory module",
        r"Adaptation and vulnerability module",
        r"\n[A-Z][A-Za-z ]{6,}\n",
    ]
    return extract_between(text, start_patterns, end_patterns)


def build_transparency_sections_payload(text: str, country: str) -> Dict[str, Dict[str, str]]:
    """Build the transparency sections payload for Supabase upload."""
    climate = extract_climate_transparency(text, country)
    official = extract_official_reporting(text)
    barriers = extract_key_barriers(text)
    
    sections: Dict[str, Dict[str, str]] = {}
    
    if climate:
        sections["ClimateTransparency"] = {
            "doc_type": "BUR",
            "text": climate,
        }
    if official:
        sections["OfficialReportingUNFCCC"] = {
            "doc_type": "BUR",
            "text": official,
        }
    if barriers:
        sections["KeyBarriers"] = {
            "doc_type": "BUR",
            "text": barriers,
        }
    
    return sections


# ============================================================================
# Other Section Extraction (from pdf_scraper.py)
# ============================================================================

SECTION_NAMES = [
    "NDC Tracking Module",
    "Support Needed and Received Module",
    "Other baseline initiatives",
]

SECTION_KEYWORDS: Dict[str, List[str]] = {
    "NDC Tracking Module": [
        "ndc tracking module",
        "ndc tracking",
        "tracking progress",
        "progress toward achieving its 2030 emission reduction target",
        "progress toward achieving its",
        "description of kenya's ndc",
        "description of the ndc",
        "mitigation policies and measures",
        "mitigation actions and their effects",
        "tracking ndc",
        "tracking systems for nationally determined contributions",
        "ndc 2.0",
        "ndc 3.0",
        "ndcs",
    ],
    "Support Needed and Received Module": [
        "support needed and received module",
        "support needed and received",
        "information on financial support needed",
        "information on financial support received",
        "support flows",
        "support needed",
        "support received",
        "support for the implementation of the 2020 ndc",
        "support for the implementation of the ndc",
        "climate finance",
        "means of implementation",
        "technology development and transfer support needed",
        "capacity-building support needed",
        "capacity-building support received",
    ],
    "Other baseline initiatives": [
        "other baseline initiatives",
        "baseline analysis",
        "other initiatives",
        "ongoing transparency projects and initiatives",
        "transparency initiatives",
        "program / project and supporting",
        "leading ministry duration relationship with etf",
        "this cbit project is aligned with and complements other initiatives",
        "baseline of components",
        "baseline of component",
    ],
}


def validate_openai_api_key(api_key: str) -> bool:
    """Validate an OpenAI API key by making a simple API call."""
    if not OPENAI_AVAILABLE:
        return False
    
    if not api_key or not api_key.strip():
        return False
    
    try:
        client = OpenAI(api_key=api_key.strip())
        client.models.list()
        return True
    except Exception:
        return False


def load_examples_from_folder(examples_folder: Path) -> Dict[str, str]:
    """Load example PDFs from the Examples folder and extract their sections."""
    examples: Dict[str, str] = {}
    
    if not examples_folder.exists() or not examples_folder.is_dir():
        return examples
    
    for pdf_file in examples_folder.glob("*.pdf"):
        try:
            text = extract_text_from_pdf(pdf_file)
            examples[pdf_file.name] = text
        except Exception as exc:
            print(f"Warning: Could not load example {pdf_file.name}: {exc}")
    
    return examples


def extract_sections_with_openai(
    pdf_text: str,
    api_key: str,
    examples: Dict[str, str],
    keywords: Dict[str, List[str]],
    country: Optional[str] = None,
    extract_transparency: bool = True,
    extract_other: bool = True,
) -> Dict[str, str]:
    """
    Use OpenAI to extract all target sections from PDF text.
    
    Extracts:
    - Transparency sections: Climate Transparency, Official Reporting to UNFCCC, Key Barriers
    - Other sections: NDC Tracking Module, Support Needed and Received Module, Other baseline initiatives
    """
    if not OPENAI_AVAILABLE:
        raise RuntimeError("OpenAI library is not available")
    
    client = OpenAI(api_key=api_key)
    
    # Prepare examples text for the prompt
    examples_text = ""
    if examples:
        examples_text = "\n\n--- Example Documents ---\n"
        for example_name, example_text in examples.items():
            truncated_example = example_text[:5000] + "..." if len(example_text) > 5000 else example_text
            examples_text += f"\nExample: {example_name}\n{truncated_example}\n"
    
    # Prepare keywords text for other sections
    keywords_text = "\n\n--- Keywords to Look For ---\n"
    if extract_other:
        for section_name, kw_list in keywords.items():
            keywords_text += f"\n{section_name}: {', '.join(kw_list[:10])}...\n"
    
    # Truncate PDF text if too long (increase limit for all sections)
    truncated_pdf_text = pdf_text[:150000] + "\n[... text truncated ...]" if len(pdf_text) > 150000 else pdf_text
    
    # Build section list based on what to extract
    sections_to_extract = []
    section_descriptions = []
    
    if extract_transparency:
        sections_to_extract.extend([
            "Climate Transparency",
            "Official Reporting to UNFCCC",
            "Key Barriers"
        ])
        section_descriptions.extend([
            "Climate Transparency: Status and progress of transparency framework, Enhanced Transparency Framework (ETF) progress, transparency initiatives, reporting capabilities, and challenges related to climate transparency in the country.",
            "Official Reporting to UNFCCC: Reports submitted to UNFCCC (NCs, BURs, BTRs), recommendations and observations from National Communications, Biennial Update Reports, Biennial Transparency Reports, International Consultation and Analysis (ICA) findings, Technical Expert Reviews, and capacity gaps identified in reporting.",
            "Key Barriers: Barriers preventing full Enhanced Transparency Framework (ETF) compliance, including: 1) Lack of systematic climate-data organization and institutional protocols, 2) Incomplete ETF modules (GHG Inventory, Adaptation/Vulnerability, NDC Tracking, Support Needed & Received), 3) Dependence on project-based financing and external consultants for reporting. Include constraints, gaps, challenges, and needs."
        ])
    
    if extract_other:
        sections_to_extract.extend([
            "NDC Tracking Module",
            "Support Needed and Received Module",
            "Other baseline initiatives"
        ])
        section_descriptions.extend([
            "NDC Tracking Module: NDCs, emission targets, mitigation actions, progress tracking, implementation status, policies, measures, tracking systems for nationally determined contributions, and related climate actions.",
            "Support Needed and Received Module: Financial support, technical assistance, capacity building, technology transfer, funding, grants, loans, climate finance, means of implementation, and any form of support mechanisms.",
            "Other baseline initiatives: Ongoing projects, transparency initiatives, baseline analyses, complementary programs, and related climate and environmental initiatives."
        ])
    
    # Create the prompt
    sections_list = "\n".join([f"{i+1}. \"{section}\"" for i, section in enumerate(sections_to_extract)])
    descriptions_list = "\n".join([f"- {desc}" for desc in section_descriptions])
    
    prompt = f"""You are an expert at extracting structured information from climate change documents, specifically BURs (Biennial Update Reports).

Your task is to extract ALL relevant information related to {len(sections_to_extract)} specific sections from the provided document text:

{sections_list}

{examples_text}

{keywords_text if extract_other else ""}

--- Document to Analyze ---
{truncated_pdf_text}

IMPORTANT: Extract as much relevant information as possible for each section. Be INCLUSIVE and COMPREHENSIVE:
- Include information that directly matches the section name or keywords
- Include information that is remotely connected or related to the section, even if the connection is indirect
- Include contextual information that helps understand the section's content
- Include related policies, measures, initiatives, data, statistics, or discussions that are thematically related
- Look beyond explicit headings - search the entire document for any content that could be relevant

Section-specific guidance:
{descriptions_list}

Extract comprehensive, detailed text for each section. Include all paragraphs, sentences, and information that could be relevant, even if the connection is indirect. The goal is to capture as much related information as possible.

If a section truly has no relevant content anywhere in the document, return an empty string for that section.

Return your response as a JSON object with exactly these keys:
{chr(10).join([f'- "{section}"' for section in sections_to_extract])}

Each value should be the comprehensive extracted text for that section (as much relevant information as possible), or an empty string only if absolutely no relevant content exists.

Return ONLY valid JSON, no additional text or explanation."""

    response_text = ""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert document analyst that extracts comprehensive, detailed information from climate documents. Your goal is to be INCLUSIVE - extract all relevant content including remotely related information. Return only valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=16000  # Increased to handle all 6 sections
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Try to parse JSON from the response
        if response_text.startswith("```"):
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1)
        
        sections = json.loads(response_text)
        
        # Ensure all requested sections are present
        result: Dict[str, str] = {}
        all_section_names = []
        if extract_transparency:
            all_section_names.extend(["Climate Transparency", "Official Reporting to UNFCCC", "Key Barriers"])
        if extract_other:
            all_section_names.extend(SECTION_NAMES)
        
        for section_name in all_section_names:
            result[section_name] = sections.get(section_name, "").strip()
        
        return result
        
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse OpenAI response as JSON: {e}")
        if response_text:
            print(f"Response was: {response_text[:500]}")
        # Return empty dict with all section names
        all_section_names = []
        if extract_transparency:
            all_section_names.extend(["Climate Transparency", "Official Reporting to UNFCCC", "Key Barriers"])
        if extract_other:
            all_section_names.extend(SECTION_NAMES)
        return {name: "" for name in all_section_names}
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        raise


def normalize_whitespace(text: str) -> str:
    """Collapse multiple spaces and normalize line endings."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"\s+$", "", line) for line in text.split("\n")]
    return "\n".join(lines)


def find_section_ranges(lines: List[str]) -> Dict[str, Tuple[int, int]]:
    """Find index ranges (start, end) in `lines` for each section name."""
    patterns = {
        name: re.compile(re.escape(name), re.IGNORECASE)
        for name in SECTION_NAMES
    }
    
    starts: Dict[str, int] = {}
    for i, line in enumerate(lines):
        for section_name, pattern in patterns.items():
            if section_name in starts:
                continue
            if pattern.search(line):
                starts[section_name] = i
    
    ranges: Dict[str, Tuple[int, int]] = {}
    sorted_sections = [s for s in SECTION_NAMES if s in starts]
    for idx, section_name in enumerate(sorted_sections):
        start = starts[section_name]
        if idx + 1 < len(sorted_sections):
            next_section = sorted_sections[idx + 1]
            end = starts[next_section]
        else:
            end = len(lines)
        ranges[section_name] = (start, end)
    
    return ranges


def extract_sections_by_keywords(text: str) -> Dict[str, str]:
    """Fallback extraction based on keyword proximity."""
    cleaned = normalize_whitespace(text)
    lines = cleaned.split("\n")
    
    sections: Dict[str, str] = {}
    
    for section_name in SECTION_NAMES:
        keywords = [kw.lower() for kw in SECTION_KEYWORDS.get(section_name, [])]
        if not keywords:
            sections[section_name] = ""
            continue
        
        matched_indices: List[int] = []
        for idx, line in enumerate(lines):
            lower_line = line.lower()
            if any(kw in lower_line for kw in keywords):
                matched_indices.append(idx)
        
        if not matched_indices:
            sections[section_name] = ""
            continue
        
        # Cluster nearby matches and expand a context window around each cluster
        clusters: List[Tuple[int, int]] = []
        start = matched_indices[0]
        prev = matched_indices[0]
        for i in matched_indices[1:]:
            if i - prev <= 2:
                prev = i
                continue
            clusters.append((start, prev))
            start = i
            prev = i
        clusters.append((start, prev))
        
        context_lines: List[str] = []
        seen_spans: set[Tuple[int, int]] = set()
        for start_idx, end_idx in clusters:
            ctx_start = max(start_idx - 5, 0)
            ctx_end = min(end_idx + 5, len(lines) - 1)
            span = (ctx_start, ctx_end)
            if span in seen_spans:
                continue
            seen_spans.add(span)
            context_lines.extend(lines[ctx_start : ctx_end + 1])
            context_lines.append("")
        
        sections[section_name] = "\n".join(context_lines).strip()
    
    return sections


def extract_other_sections(text: str) -> Dict[str, str]:
    """Extract the three target sections from the full document text."""
    cleaned = normalize_whitespace(text)
    lines = cleaned.split("\n")
    ranges = find_section_ranges(lines)
    
    # If we find explicit headings, use the clean range-based extraction
    if ranges:
        sections: Dict[str, str] = {}
        for name in SECTION_NAMES:
            if name in ranges:
                start, end = ranges[name]
                body_lines = lines[start:end]
                extracted = "\n".join(body_lines).strip()
            else:
                extracted = ""
            sections[name] = extracted
        return sections
    
    # Otherwise, fall back to keyword-based extraction
    return extract_sections_by_keywords(text)


def infer_country_from_filename(path: Path) -> str:
    """Infer country name from filename."""
    stem = path.stem
    parts = re.split(r"[_\-]+", stem)
    
    metadata_tokens = {
        "GEF", "GEF8", "PIF", "PFD", "DRAFT", "FINAL", "REV", "V1", "V2", "V3"
    }
    tokens = [
        p
        for p in parts
        if p
        and not re.fullmatch(r"\d+(\.\d+)*", p)
    ]
    
    country_like = [
        t
        for t in tokens
        if t[0].isupper() and not t.isupper() and t.upper() not in metadata_tokens
    ]
    if country_like:
        return country_like[0]
    
    remaining = [t for t in tokens if t.upper() not in metadata_tokens]
    if remaining:
        return remaining[-1]
    
    return stem


def infer_doc_type_from_filename(path: Path) -> str:
    """Infer a simple 'doc type' identifier from the filename."""
    stem = path.stem.upper()
    
    bur_match = re.search(r'BUR(\d*)', stem)
    if bur_match:
        bur_num = bur_match.group(1)
        if bur_num:
            return f"BUR{bur_num}"
        else:
            return "BUR1"
    
    return path.stem


def find_bur_files_for_country(country_name: str, bur_folder: Path) -> List[Path]:
    """Find BUR PDF files in the BUR folder that match the given country name."""
    if not bur_folder.exists() or not bur_folder.is_dir():
        return []
    
    country_lower = country_name.lower()
    matching_files: List[Path] = []
    
    for pdf_file in bur_folder.glob("*.pdf"):
        filename_lower = pdf_file.stem.lower()
        if country_lower in filename_lower:
            matching_files.append(pdf_file)
    
    return sorted(matching_files)


# ============================================================================
# Main Processing Functions
# ============================================================================

def process_pdf_file(
    pdf_path: Path,
    supabase_client: SupabaseClient,
    country: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    examples: Optional[Dict[str, str]] = None,
    extract_transparency: bool = True,
    extract_other: bool = True,
) -> Dict:
    """
    Extract sections from one PDF and upsert into Supabase.
    
    Args:
        pdf_path: Path to the PDF file
        supabase_client: Supabase client instance
        country: Country name (inferred from filename if not provided)
        openai_api_key: Optional OpenAI API key for AI extraction
        examples: Optional dictionary of example PDF texts for OpenAI extraction
        extract_transparency: Whether to extract transparency sections
        extract_other: Whether to extract other sections (NDC Tracking, etc.)
    """
    print(f"Processing PDF: {pdf_path}")
    
    # Extract text
    try:
        raw_text = extract_text_from_pdf(pdf_path)
    except Exception:
        # Fallback to PyMuPDF
        raw_text = load_pdf_text(pdf_path)
    
    if not country:
        country = infer_country_from_filename(pdf_path)
    doc_type = infer_doc_type_from_filename(pdf_path)
    
    all_sections: Dict[str, Any] = {}
    
    # Use OpenAI to extract all sections if API key is provided
    if openai_api_key and examples is not None:
        print("Using OpenAI for extraction...")
        extracted_sections = extract_sections_with_openai(
            raw_text,
            openai_api_key,
            examples,
            SECTION_KEYWORDS,
            country=country,
            extract_transparency=extract_transparency,
            extract_other=extract_other,
        )
        
        # Process transparency sections (convert to expected format)
        if extract_transparency:
            for section_key in ["Climate Transparency", "Official Reporting to UNFCCC", "Key Barriers"]:
                if section_key in extracted_sections and extracted_sections[section_key]:
                    # Map to internal keys
                    if section_key == "Climate Transparency":
                        all_sections["ClimateTransparency"] = {"doc_type": doc_type, "text": extracted_sections[section_key]}
                    elif section_key == "Official Reporting to UNFCCC":
                        all_sections["OfficialReportingUNFCCC"] = {"doc_type": doc_type, "text": extracted_sections[section_key]}
                    elif section_key == "Key Barriers":
                        all_sections["KeyBarriers"] = {"doc_type": doc_type, "text": extracted_sections[section_key]}
        
        # Process other sections
        if extract_other:
            for section_name in SECTION_NAMES:
                if section_name in extracted_sections and extracted_sections[section_name]:
                    all_sections[section_name] = extracted_sections[section_name]
    else:
        # Use regex/keyword-based extraction
        # Extract transparency sections
        if extract_transparency:
            transparency_sections = build_transparency_sections_payload(raw_text, country)
            all_sections.update(transparency_sections)
        
        # Extract other sections
        if extract_other:
            print("Using keyword-based extraction...")
            other_sections = extract_other_sections(raw_text)
            
            # Convert to format expected by upsert
            for section_name, text in other_sections.items():
                if text:
                    all_sections[section_name] = text
    
    if not all_sections:
        print(f"[WARN] No sections extracted from {pdf_path.name}")
        return {}
    
    # Upload to Supabase
    result = supabase_client.upsert_country_sections(
        country=country,
        new_sections=all_sections,
        doc_type=doc_type,
    )
    
    print(f"Upserted data for country='{country}', doc_type='{doc_type}'.")
    return result


def process_country_from_web(
    country: str,
    supabase_client: SupabaseClient,
    force: bool = False,
    extract_transparency: bool = True,
    extract_other: bool = True,
    openai_api_key: Optional[str] = None,
    examples: Optional[Dict[str, str]] = None,
):
    """
    Process a single country: download BUR, extract sections, upload to Supabase.
    
    Args:
        country: Country name to process
        supabase_client: Supabase client instance
        force: If True, re-extract even if sections already exist
        extract_transparency: Whether to extract transparency sections
        extract_other: Whether to extract other sections
        openai_api_key: Optional OpenAI API key for AI extraction
        examples: Optional dictionary of example PDF texts
    """
    print("\n" + "=" * 60)
    print(f"Processing country: {country}")
    print("=" * 60)
    
    # Find latest BUR link
    soup = fetch_bur_listing_page()
    bur_url = get_latest_bur_link_for_country(country, soup)
    if not bur_url:
        print(f"[ERROR] Could not find BUR URL for {country}")
        return
    
    # Download or reuse cached PDF
    try:
        pdf_path = get_or_download_bur_pdf(country, bur_url)
        if not pdf_path:
            print(f"[ERROR] Could not get BUR PDF for {country}")
            return
    except Exception as e:
        print(f"[ERROR] Failed to download BUR PDF for {country}: {e}")
        return
    
    # Process the PDF
    try:
        process_pdf_file(
            pdf_path,
            supabase_client,
            country=country,
            openai_api_key=openai_api_key,
            examples=examples,
            extract_transparency=extract_transparency,
            extract_other=extract_other,
        )
        print(f"[DONE] Processed {country}")
    except Exception as e:
        print(f"[ERROR] Failed to process {country}: {e}")
        raise


def main():
    """Main entry point for the script."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Unified BUR Web Scraper and Extractor"
    )
    parser.add_argument(
        "--country",
        type=str,
        nargs="+",
        help="Country name(s) to process (e.g., 'Cuba' or 'Cuba Jordan')",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Process local PDF files instead of downloading from web",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract sections even if they already exist in Supabase",
    )
    parser.add_argument(
        "--transparency-only",
        action="store_true",
        help="Only extract transparency sections (Climate Transparency, Official Reporting, Key Barriers)",
    )
    parser.add_argument(
        "--other-only",
        action="store_true",
        help="Only extract other sections (NDC Tracking, Support Needed, Other baseline initiatives)",
    )
    parser.add_argument(
        "--openai-key",
        type=str,
        help="OpenAI API key for AI-powered extraction (optional)",
    )
    
    args = parser.parse_args()
    
    # Initialize Supabase client
    try:
        config = SupabaseConfig.from_env()
        client = SupabaseClient(config)
    except Exception as e:
        print(f"[ERROR] Failed to initialize Supabase client: {e}")
        print("Please ensure SUPABASE_URL and SUPABASE_API_KEY are set in .env file")
        return
    
    # Determine extraction modes
    extract_transparency = not args.other_only
    extract_other = not args.transparency_only
    
    # Get OpenAI API key and examples
    openai_api_key = args.openai_key
    examples = None
    if openai_api_key:
        if validate_openai_api_key(openai_api_key):
            print("OpenAI API key validated successfully.")
            examples_folder = SCRIPT_DIR.parent / "reference_docs"
            examples = load_examples_from_folder(examples_folder)
            if examples:
                print(f"Loaded {len(examples)} example document(s).")
        else:
            print("Warning: Invalid OpenAI API key. Falling back to keyword-based extraction.")
            openai_api_key = None
    
    # Get countries to process
    if args.country:
        countries = args.country
    else:
        # Default countries if none specified
        countries = ["Cuba", "Jordan", "Guinea-Bissau"]
        print(f"No countries specified. Using defaults: {countries}")
    
    # Process each country
    for country in countries:
        try:
            if args.local:
                # Process local PDFs
                bur_folder = SCRIPT_DIR.parent / "downloads" / "bur_modules"
                pdf_files = find_bur_files_for_country(country, bur_folder)
                
                if not pdf_files:
                    print(f"[WARN] No BUR files found for {country} in {bur_folder}")
                    continue
                
                print(f"Found {len(pdf_files)} BUR file(s) for {country}.")
                for pdf in pdf_files:
                    process_pdf_file(
                        pdf,
                        client,
                        country=country,
                        openai_api_key=openai_api_key,
                        examples=examples,
                        extract_transparency=extract_transparency,
                        extract_other=extract_other,
                    )
            else:
                # Download and process from web
                process_country_from_web(
                    country,
                    client,
                    force=args.force,
                    extract_transparency=extract_transparency,
                    extract_other=extract_other,
                    openai_api_key=openai_api_key,
                    examples=examples,
                )
        except Exception as e:
            print(f"[ERROR] Failed to process {country}: {e}")
            continue
    
    print("\n" + "=" * 60)
    print("Processing complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

