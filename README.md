# GEF-8 Webscraping & PIF Generation Pipeline

A comprehensive pipeline for semi-automated drafting of GEF-8 Project Identification Forms (PIFs) for the Capacity-Building Initiative for Transparency (CBIT). This repository contains tools for extracting climate policy information from UNFCCC reports and generating structured PIF sections using AI-powered language models.

## Overview

This repository automates the process of:
- **Extracting** relevant text from UNFCCC country reports (BURs, BTRs, NCs, NDCs)
- **Storing** extracted data in Supabase for centralized access
- **Generating** structured PIF sections aligned with GEF-8 templates using AI
- **Formatting** outputs for official submission

The pipeline is designed to support transparency capacity-building projects by streamlining the creation of comprehensive PIF documents.

## Repository Structure

```
UNEPxBerkeley/
├── pdf_extraction/                    # PDF extraction and data collection tools
│   ├── pdfextraction_cookies/        # UNFCCC web scraping with cookie-based authentication
│   │   ├── scrape_unfccc.py         # Unified scraper for all PIF sections
│   │   ├── upload_to_supabase.py     # Database upload utility
│   │   ├── create_table.sql          # Supabase table schema
│   │   ├── SUPABASE_README.md        # Supabase integration guide
│   │   ├── data/                     # Extracted JSON bundles
│   │   └── downloads/                 # Downloaded PDF files
│   ├── bur_transparency_extractor.py # Consolidated BUR transparency extractor
│   ├── pdfextraction_BUR.ipynb       # Legacy notebook (deprecated)
│   └── pdfextraction_BUR/              # BUR web scraping and extraction tools
│       ├── src/                      # Source scripts
│       │   ├── pdf_scraper.py        # BUR module scraper with AI extraction
│       │   ├── CBITCheck.py           # CBIT project checker
│       │   ├── ICAT_PATPA_Processor.py # ICAT/PATPA document processor
│       │   └── export_cookies.py     # Cookie exporter utility
│       ├── config/                    # Configuration files
│       │   ├── unfccc_cookies.json   # UNFCCC authentication cookies
│       │   └── projects.csv          # CBIT projects database (download from web)
│       ├── data/                      # Extracted data (JSON bundles)
│       ├── downloads/                 # Downloaded PDFs
│       ├── input/                    # User-provided input files
│       │   ├── CBIT/                 # CBIT project documents
│       │   └── ICAT_PATPA/           # ICAT and PATPA documents
│       ├── output/                    # Generated output files
│       ├── reference_docs/           # Reference documents and examples
│       ├── requirements.txt           # Python dependencies
│       ├── README.md                  # Module-specific documentation
│       └── RUN_INSTRUCTIONS.md       # Detailed usage instructions
│
├── PIF Generator/                     # PIF section generation from extracted data
│   ├── PIF_Generator.py              # Main PIF section generator
│   ├── scrape_unfccc.py              # Helper scraper script
│   ├── requirements.txt               # Python dependencies
│   ├── Section Examples.txt           # Example section formats
│   ├── SupaBase Info.rtf              # Supabase configuration reference
│   ├── unfccc_cookies.json            # UNFCCC authentication cookies
│   └── Output/                        # Generated PIF sections
│
├── LICENSE                            # CC0 1.0 Universal License
└── README.md                          # This file
```

## Components

### PDF Extraction

The PDF extraction components are responsible for downloading, parsing, and extracting relevant sections from UNFCCC country reports.

#### 1. `pdfextraction_cookies/scrape_unfccc.py`

**Unified Web Scraper** - The primary tool for extracting PIF-relevant sections from UNFCCC country reports.

**Features:**
- Cookie-based authentication to bypass UNFCCC firewall -- need to open website and collect cookie information, update to json to bypass correctly
- Scrapes UNFCCC reports portal for country-specific documents
- Downloads and parses PDF files (BURs, BTRs, NCs, NDCs)
- Extracts multiple section types:
  - **Institutional Framework for Climate Action** - National institutions and coordination mechanisms
  - **National Policy Framework** - Laws, policies, decrees, and strategies
  - **GHG Inventory Module** - Greenhouse gas inventory information
  - **Adaptation and Vulnerability Module** - Climate adaptation and vulnerability assessments
  - **Climate Transparency** - Transparency framework status
  - **Official Reporting to UNFCCC** - Reporting history and recommendations
  - **Key Barriers** - Barriers to enhanced transparency
- Select specific sections via command-line arguments
- Outputs structured JSON bundles for downstream processing
- Optional Supabase integration for data storage

**Usage:**
```bash
cd pdf_extraction/pdfextraction_cookies

# Extract all sections for a country
python scrape_unfccc.py --country "Cuba" --cookies-file cookies.json

# Extract specific sections only
python scrape_unfccc.py --country "Cuba" \
    --sections "GHG Inventory Module" "Adaptation and Vulnerability Module" \
    --cookies-file cookies.json

# Upload extracted data to Supabase
python upload_to_supabase.py
```

**Dependencies:**
- `requests` - HTTP requests
- `beautifulsoup4` - HTML parsing
- `PyMuPDF` (fitz) - PDF parsing
- `supabase` - Database integration (optional)
- `python-dotenv` - Environment variable management

**Configuration:**
- Place UNFCCC cookies in `cookies.json` (see `export_cookies.py` for help)
- Configure Supabase credentials in `.env` file or environment variables

#### 2. `pdfextraction_BUR/`

**Unified BUR Web Scraping and Extraction** - Consolidated tool that combines functionality from:
- `bur_transparency_extractor.py` (BUR web scraping and transparency sections)
- `pdf_scraper.py` (local PDF processing and other sections)

**Features:**
- Downloads BURs from UNFCCC website or processes local PDF files
- Extracts multiple section types:
  - **Transparency sections**: Climate Transparency, Official Reporting to UNFCCC, Key Barriers
  - **Other sections**: NDC Tracking Module, Support Needed and Received Module, Other baseline initiatives
- AI-powered extraction (OpenAI) with keyword-based fallback
- Supabase integration for data storage
- Supports multiple document types (BUR1, BUR2, etc.)

**Usage:**
```bash
cd pdf_extraction/pdfextraction_BUR/src

# Download from web and extract all sections
python bur_webscraper.py --country "Cuba"

# Process local PDFs only
python bur_webscraper.py --country "Cuba" --local

# Extract only transparency sections
python bur_webscraper.py --country "Cuba" --transparency-only

# Extract only other sections
python bur_webscraper.py --country "Cuba" --other-only

# Use OpenAI for extraction
python bur_webscraper.py --country "Cuba" --openai-key YOUR_KEY

# Process multiple countries
python bur_webscraper.py --country "Cuba" "Jordan" "Guinea-Bissau"
```

**Additional Tools:**
- `CBITCheck.py` - CBIT project checker and document handler
- `ICAT_PATPA_Processor.py` - Processes ICAT and PATPA documents
- `export_cookies.py` - UNFCCC cookie exporter utility

**Configuration:**
- Requires Supabase credentials in `.env` file:
  ```
  SUPABASE_URL=your_supabase_url
  SUPABASE_API_KEY=your_api_key
  ```

**See `pdfextraction_BUR/README.md` for detailed documentation.**

#### 3. `pdfextraction_BUR.ipynb`

**Legacy Notebook** - Jupyter notebook for extracting transparency-related sections from BURs.

**Status:** Deprecated - functionality has been consolidated into `pdfextraction_BUR/src/bur_webscraper.py`. Kept for reference only.

### PIF Generation

#### `PIF Generator/PIF_Generator.py`

**Main PIF Section Generator** - Generates comprehensive PIF sections from extracted data stored in Supabase. Prompt engineered outputs, used as documentation to show processes we went through before switching to method outlined in https://github.com/amanshah0729/UN_pif

**Features:**
- Queries Supabase database for country information and extracted sections
- Searches local output files for additional context
- Uses OpenAI API to generate structured PIF sections
- Validates API keys and data sources
- Generates multiple section types:
  - Project Rationale
  - Paris Agreement and Enhanced Transparency Framework
  - Climate Transparency in [Country]
  - Baseline sections (National transparency framework, Institutional framework, Policy framework, etc.)
  - Stakeholder analysis
  - Barriers and constraints
- Exports to Word document format (.docx)
- Includes standard text segments and formatting requirements

**Usage:**
```bash
cd "PIF Generator"

# Install dependencies
pip install -r requirements.txt

# Run generator (interactive prompts)
python PIF_Generator.py
```

**Configuration:**
- Requires OpenAI API key (set in environment or `.env` file)
- Requires Supabase credentials for data access
- See `SupaBase Info.rtf` for Supabase configuration details

**Output:**
- Generated sections saved to `Output/` directory
- Word documents (.docx) and text files (.txt) per country

## Data Flow

```
UNFCCC Reports Portal
    ↓
[pdfextraction_cookies/scrape_unfccc.py]
    OR
[pdfextraction_BUR/src/bur_webscraper.py]
    OR
[pdfextraction_BUR/src/bur_webscraper.py]
    ↓
Extracted JSON Bundles (data/*.json)
    ↓
[upload_to_supabase.py] (optional)
    ↓
Supabase Database (country_sections table)
    ↓
[PIF_Generator.py]
    ↓
AI Generation (OpenAI GPT models)
    ↓
Word Documents (Output/*.docx)
```

## Setup Instructions

### Prerequisites

- **Python 3.8+** (for PDF extraction and PIF generation)
- **OpenAI API key** (for AI-powered generation)
- **Supabase account** (optional but recommended for data persistence)
- **UNFCCC account** (for cookie-based authentication)

### Installation

1. **Clone the repository:**
```bash
git clone <repository-url>
cd UNEPxBerkeley
```

2. **Install Python dependencies:**

For PDF extraction:
```bash
cd pdf_extraction/pdfextraction_cookies
pip install requests beautifulsoup4 PyMuPDF supabase python-dotenv
```

For pdfextraction_BUR:
```bash
cd pdf_extraction/pdfextraction_BUR
pip install -r requirements.txt
```

For PIF Generator:
```bash
cd "PIF Generator"
pip install -r requirements.txt
```

3. **Configure environment variables:**

Create `.env` files in relevant directories with:
```env
# Supabase Configuration
SUPABASE_URL=your_supabase_url
SUPABASE_API_KEY=your_api_key

# OpenAI Configuration
OPENAI_API_KEY=your_openai_key
```

4. **Set up UNFCCC cookies:**

For cookie-based authentication:
```bash
cd pdf_extraction/pdfextraction_BUR/src
python export_cookies.py
# Follow instructions to export cookies from browser
```

Place exported cookies in:
- `pdf_extraction/pdfextraction_cookies/cookies.json`
- `pdf_extraction/pdfextraction_BUR/config/unfccc_cookies.json`

5. **Set up Supabase (optional):**

```bash
cd pdf_extraction/pdfextraction_cookies
# Review create_table.sql and create the table in Supabase
# See SUPABASE_README.md for detailed instructions
```

## Usage Examples

### Complete Workflow: Extract and Generate PIF Sections

1. **Extract UNFCCC data:**
```bash
cd pdf_extraction/pdfextraction_cookies
python scrape_unfccc.py --country "Cuba" --cookies-file cookies.json
```

2. **Extract transparency sections:**
```bash
cd pdf_extraction
python bur_webscraper.py --country "Cuba"
```

3. **Upload to Supabase (optional):**
```bash
cd pdf_extraction/pdfextraction_cookies
python upload_to_supabase.py
```

4. **Generate PIF sections:**
```bash
cd "PIF Generator"
python PIF_Generator.py
# Follow interactive prompts to select country and sections
```

### Extract Specific Sections Only

```bash
cd pdf_extraction/pdfextraction_cookies
python scrape_unfccc.py \
    --country "Jordan" \
    --sections "GHG Inventory Module" "Adaptation and Vulnerability Module" \
    --cookies-file cookies.json
```

### Process Multiple Countries

```bash
cd pdf_extraction
python bur_webscraper.py --country "Cuba" "Jordan" "Guinea-Bissau"
```

## Output Files

### PDF Extraction Outputs

**JSON Bundles:**
- `pdf_extraction/pdfextraction_cookies/data/Institutional_framework_bundle.json`
- `pdf_extraction/pdfextraction_cookies/data/National_policy_framework_bundle.json`
- `pdf_extraction/pdfextraction_BUR/data/bur_modules/Adaptation_vulnerability_bundle.json`
- `pdf_extraction/pdfextraction_BUR/data/bur_modules/GHG_inventory_bundle.json`

**Individual Extractions:**
- `data/{Country}_{Section}_{DocType}.json` - Individual section extractions

**Downloaded PDFs:**
- `downloads/*.pdf` - Source PDF files from UNFCCC

### PIF Generation Outputs

- `PIF Generator/Output/{Country} section draft.docx` - Word document with generated sections
- `PIF Generator/Output/{Country} section draft.txt` - Plain text version

## Data Sources

All generators are restricted to approved sources:
- **UNFCCC reports portal** (unfccc.int/reports) - BURs, BTRs, NCs, NDCs
- **ICAT** (climateactiontransparency.org) - Climate action transparency
- **PATPA** (transparency-partnership.net) - Partnership for transparency
- **GEF/CBIT documents** (thegef.org) - Global Environment Facility
- **Official country environment ministry websites**

## Quality Assurance

- **Fact-checking**: All generated sections are verified against approved sources
- **Format compliance**: Outputs match GEF-8 PIF template requirements
- **Source verification**: Unverifiable information is flagged with `[Data gap: ...]` or `[Verify: ...]`
- **AI verification**: Generated sections can undergo AI-powered verification and revision
- **Manual review**: All generated sections should be reviewed by domain experts before submission

## Troubleshooting

### Common Issues

**UNFCCC Authentication Errors:**
- Ensure cookies are up-to-date (they expire periodically)
- Re-export cookies using `export_cookies.py`
- Check that `cookies.json` file is in the correct location

**Supabase Connection Issues:**
- Verify `.env` file exists and contains correct credentials
- Check that Supabase project is active
- Ensure network connectivity

**PDF Extraction Failures:**
- Verify PDF files are not corrupted
- Check that PDFs contain the expected sections
- Try using AI extraction if keyword-based fails (for pdfextraction_BUR)

**OpenAI API Errors:**
- Verify API key is valid and has sufficient credits
- Check rate limits and quota
- Ensure API key is set in environment or `.env` file

**Missing Dependencies:**
```bash
pip install -r requirements.txt
```

## License

This project is licensed under **CC0 1.0 Universal (Public Domain Dedication)**. See `LICENSE` file for details.

## Contributing

When contributing to this repository:

1. **Path References**: Ensure all path references are updated if moving files
2. **Data Structure**: Maintain compatibility with the existing data structure
3. **Code Style**: Follow the established code style and formatting
4. **Documentation**: Update documentation for any new features
5. **Testing**: Test changes with multiple countries and document types


## Support

For issues or questions:
- Check individual component README files for specific guidance
- Review code comments for implementation details
- Ensure all dependencies are properly installed
- Verify environment variables are correctly configured

## Related Resources

- **GEF-8 PIF Template**: Official template for Project Identification Forms
- **UNFCCC Transparency Framework**: Enhanced Transparency Framework documentation
- **CBIT Initiative**: Capacity-Building Initiative for Transparency

---