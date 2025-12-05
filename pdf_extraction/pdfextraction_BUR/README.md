# Adaptation and GHG Inventory Module Extraction

This module extracts and processes two key PIF sections from Biennial Update Reports (BURs):
- **Adaptation and Vulnerability Module**
- **GHG Inventory Module**

## Structure

```
pdfextraction_BUR/
├── src/                          # Source scripts
│   ├── bur_webscraper.py        # Unified BUR web scraper and extractor
│   ├── CBITCheck.py              # CBIT project checker and document handler
│   ├── ICAT_PATPA_Processor.py   # ICAT/PATPA document processor
│   └── export_cookies.py          # UNFCCC cookie exporter
├── data/                         # Extracted data
│   └── bur_modules/              # JSON bundles and individual extractions
│       ├── Adaptation_and_vulnerability_module/
│       ├── GHG_inventory_module/
│       ├── Adaptation_vulnerability_bundle.json
│       └── GHG_inventory_bundle.json
├── downloads/                    # Downloaded PDFs
│   └── bur_modules/              # BUR PDF files
├── input/                        # User-provided input files
│   ├── ICAT_PATPA/              # ICAT and PATPA documents
│   └── CBIT/                    # CBIT project documents
├── output/                       # Generated output files
├── config/                       # Configuration files
│   ├── unfccc_cookies.json      # UNFCCC authentication cookies
│   └── projects.csv             # CBIT projects database
├── reference_docs/               # Reference documents and examples
│   ├── Section Examples.txt     # Example section formats
│   └── *.pdf                    # Reference PDF documents
├── requirements.txt              # Python dependencies
├── RUN_INSTRUCTIONS.md          # Detailed usage instructions
└── README.md                     # This file
```

## Quick Start

### 1. Install Dependencies

```bash
cd pdfextraction_BUR
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root with Supabase credentials:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_API_KEY=your_api_key_here
```

### 3. Extract BUR Modules

**Option A: Using bur_webscraper.py (Recommended)**
```bash
cd src
python bur_webscraper.py --country "Cuba"
```
- Prompts for country name
- Searches for BUR PDFs
- Extracts Adaptation/Vulnerability and GHG Inventory modules
- Uploads to Supabase

**Option B: Using unified scraper (from pdfextraction_cookies)**
```bash
cd ../pdfextraction_cookies
python scrape_unfccc.py --country "Cuba" --sections "GHG Inventory Module" "Adaptation and Vulnerability Module" --cookies-file ../pdfextraction_BUR/config/unfccc_cookies.json
```

### 4. Process ICAT/PATPA Documents

```bash
cd src
python CBITCheck.py
```
- Checks for CBIT projects
- Handles document downloads
- Processes ICAT/PATPA files
- Generates output text files

## Scripts Overview

### `bur_webscraper.py`
Unified scraper for extracting BUR modules. Features:
- Downloads BURs from UNFCCC website or processes local PDFs
- Extracts multiple section types:
  - Transparency sections: Climate Transparency, Official Reporting, Key Barriers
  - Other sections: NDC Tracking Module, Support Needed and Received Module, Other baseline initiatives
- Uses AI (OpenAI) or keyword-based fallback extraction
- Uploads extracted data to Supabase
- Supports multiple document types (BUR1, BUR2, etc.)

**Usage:**
```bash
# Download from web and extract all sections
python src/bur_webscraper.py --country "Cuba"

# Process local PDFs only
python src/bur_webscraper.py --country "Cuba" --local

# Extract only transparency sections
python src/bur_webscraper.py --country "Cuba" --transparency-only

# Extract only other sections
python src/bur_webscraper.py --country "Cuba" --other-only

# Use OpenAI for extraction
python src/bur_webscraper.py --country "Cuba" --openai-key YOUR_KEY
```


### `CBITCheck.py`
Checks for CBIT projects and processes related documents. Features:
- Queries `config/projects.csv` for CBIT projects
- Downloads CBIT documents if available
- Calls ICAT/PATPA processor
- Optional OpenAI API key for enhanced extraction

**Usage:**
```bash
python src/CBITCheck.py
```

### `ICAT_PATPA_Processor.py`
Processes ICAT and PATPA documents. Features:
- Extracts information from ICAT/PATPA PDFs
- Processes CBIT documents
- Uses AI for enhanced extraction (if API key provided)
- Generates output text files

**Usage:**
```bash
python src/ICAT_PATPA_Processor.py "Cuba"
```

### `export_cookies.py`
Exports UNFCCC cookies for authentication.

## Data Flow

```
BUR PDFs (downloads/bur_modules/)
    ↓
[bur_webscraper.py or unified scrape_unfccc.py]
    ↓
Extracted JSON (data/bur_modules/)
    ↓
[Upload to Supabase]
    ↓
[Used by PIF generators]
```

## Configuration

### Supabase Setup
1. Create `.env` file in project root:
   ```env
   SUPABASE_URL=your_url
   SUPABASE_API_KEY=your_key
   ```

2. Or set environment variables directly

### UNFCCC Cookies
Place cookies in `config/unfccc_cookies.json` for authenticated scraping.

### CBIT Projects
Update `config/projects.csv` with CBIT project information.

## Output Files

### Extracted Data
- `data/bur_modules/Adaptation_vulnerability_bundle.json` - All adaptation extractions
- `data/bur_modules/GHG_inventory_bundle.json` - All GHG inventory extractions
- `data/bur_modules/{Country}_{Module}_{DocType}.json` - Individual extractions

### Generated Outputs
- `output/{country} ICAT and PATPA text.txt` - Processed ICAT/PATPA content

## Notes

- **AI Extraction**: Requires OpenAI API key for best results. Falls back to keyword-based extraction if not provided.
- **Supabase Integration**: Extracted data is automatically uploaded to Supabase for use by other components.
- **File Organization**: Input files should be placed in `input/ICAT_PATPA/` or `input/CBIT/` folders.
- **Reference Documents**: Example sections and reference PDFs are in `reference_docs/`.

## Troubleshooting

### Supabase Connection Issues
- Verify `.env` file exists and contains correct credentials
- Check that Supabase project is active
- Ensure network connectivity

### PDF Extraction Failures
- Verify PDF files are not corrupted
- Check that PDFs contain the expected sections
- Try using AI extraction if keyword-based fails

### Missing Dependencies
```bash
pip install -r requirements.txt
```

## Related Components

- **PDF Extraction** (`../pdf_extraction/`) - General UNFCCC scraping
- **Section Generators** (`../section_generator/`) - PIF section generation

---

For detailed instructions, see `RUN_INSTRUCTIONS.md`.

