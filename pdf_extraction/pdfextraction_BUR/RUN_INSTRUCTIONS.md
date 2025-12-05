# How to Run the Programs

This document provides instructions for running all three programs in this project.

---

## 1. Ass8 Scraper and Supabase

### Setup:
```bash
cd "/Users/andrewchung/Desktop/Project UN/Ass8 Scraper and Supabase"
pip install -r requirements.txt
```

### Supabase Configuration:
The program automatically reads Supabase credentials from `PIF Generator/SupaBase Info.rtf`.

**Optional:** You can also set environment variables in a `.env` file (takes precedence):
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_API_KEY=your_api_key_here
```

**SECURITY NOTE:** Never commit actual API keys to version control. Use environment variables or `.env` files (which should be in `.gitignore`).

### To Run:
```bash
cd "/Users/andrewchung/Desktop/Project UN/Ass8 Scraper and Supabase"
python3 bur_webscraper.py --country "CountryName"
```

### What it does:
1. Asks for country name
2. Asks for OpenAI API key (optional - press enter to skip)
3. Searches BUR folder for country-specific PDF files
4. Extracts sections from PDFs and uploads to Supabase

---

## 2. Ass9 File Upload

### Setup:
```bash
cd "/Users/andrewchung/Desktop/Project UN/Ass9 File Upload"
pip install -r requirements.txt
```

### To Run:
```bash
cd "/Users/andrewchung/Desktop/Project UN/Ass9 File Upload"
python3 CBITCheck.py
```

### What it does:
1. **First**: Asks for OpenAI API key (press enter to skip and use basic extraction)
2. Asks for country name
3. Checks `projects.csv` for CBIT projects for that country
4. If CBIT projects found, asks if you want to upload/download CBIT documents
5. Prompts you to upload files to `ICAT:PATPA` folder
6. Processes files from both `ICAT:PATPA` and `CBIT` folders (only files matching country name)
7. Generates output text file in `Output` folder: `{country name} ICAT and PATPA text.txt`

### Alternative (Direct):
You can also run the processor directly:
```bash
cd "/Users/andrewchung/Desktop/Project UN/Ass9 File Upload"
python3 ICAT_PATPA_Processor.py Kenya
```

---

## 3. PIF Generator

### Setup:
```bash
cd "/Users/andrewchung/Desktop/Project UN/PIF Generator"
pip install -r requirements.txt
```

### To Run:
```bash
cd "/Users/andrewchung/Desktop/Project UN/PIF Generator"
python3 PIF_Generator.py
```

### What it does:
1. Asks for country name
2. Searches `Ass9 File Upload/Output` folder for country-related files
3. Queries Supabase database for country information
4. Extracts three sections from Supabase data:
   - NDC Tracking Module
   - Support Needed and Received Module
   - Other Baseline Initiatives
5. Asks for OpenAI API key (validates it - keeps asking until valid)
6. Uses AI to generate the three sections based on all gathered information
7. Saves output to `Output/{country name} section draft.txt`

---

## Quick Reference

### All Programs at Once:
```bash
# Ass8 Scraper
cd "/Users/andrewchung/Desktop/Project UN/Ass8 Scraper and Supabase"
python3 bur_webscraper.py --country "CountryName"

# Ass9 File Upload
cd "/Users/andrewchung/Desktop/Project UN/Ass9 File Upload"
python3 CBITCheck.py

# PIF Generator
cd "/Users/andrewchung/Desktop/Project UN/PIF Generator"
python3 PIF_Generator.py
```

### Notes:
- **Ass8 Scraper**: Automatically reads Supabase credentials from `PIF Generator/SupaBase Info.rtf` (or `.env` file if provided)
- **Ass9 File Upload**: OpenAI API key is optional (press enter to skip)
- **PIF Generator**: OpenAI API key is required (validates before proceeding)

