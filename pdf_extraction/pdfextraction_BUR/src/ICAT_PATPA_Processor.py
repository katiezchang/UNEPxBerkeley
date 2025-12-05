#!/usr/bin/env python3
"""
ICAT_PATPA_Processor.py - Processes files from ICAT:PATPA folder and CBIT folder,
extracts relevant information using AI, and generates output text files.

Note: For best results, set the OPENAI_API_KEY environment variable.
      If not set, the script will use basic keyword-based extraction as fallback.
"""

import os
import sys
from pathlib import Path

# Try to import required libraries with helpful error messages
try:
    import openai
except ImportError:
    print("Error: openai library not found. Please install it with: pip install openai")
    sys.exit(1)

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        print("Error: pypdf or PyPDF2 library not found. Please install it with: pip install pypdf")
        sys.exit(1)

def read_text_file(file_path):
    """Read text from a text file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading text file {file_path}: {e}")
        return None

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file."""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Error extracting text from PDF {pdf_path}: {e}")
        return None

def read_document(file_path):
    """Read text from a document (PDF or text file)."""
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"Warning: File {file_path} does not exist.")
        return None
    
    if file_path.suffix.lower() == '.pdf':
        return extract_text_from_pdf(str(file_path))
    else:
        # Try to read as text file
        return read_text_file(str(file_path))

def get_section_examples():
    """Read the Section Examples.txt file and parse into sections."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    examples_path = os.path.join(script_dir, 'Section Examples.txt')
    
    try:
        with open(examples_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse into sections
        sections = {
            'NDC Tracking Module': '',
            'Support Needed and Received Module': '',
            'Other Baseline Initiatives': ''
        }
        
        lines = content.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            upper_line = line.upper()
            
            # Detect section headers
            if 'NDC TRACKING MODULE' in upper_line and current_section != 'NDC Tracking Module':
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'NDC Tracking Module'
                current_content = [line]
            elif 'SUPPORT NEEDED AND RECEIVED MODULE' in upper_line and current_section != 'Support Needed and Received Module':
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'Support Needed and Received Module'
                current_content = [line]
            elif 'OTHER BASELINE INITIATIVES' in upper_line and current_section != 'Other Baseline Initiatives':
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'Other Baseline Initiatives'
                current_content = [line]
            else:
                if current_section:
                    current_content.append(line)
        
        # Save last section
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()
        
        return sections, content
    except Exception as e:
        print(f"Warning: Could not read Section Examples.txt: {e}")
        return {}, ""

def extract_relevant_info(document_text, country_name, section_examples, section_name):
    """
    Use AI to extract relevant information from document text for a specific section.
    """
    if not document_text or len(document_text.strip()) < 100:
        return f"[Document text too short or empty for {section_name}]"
    
    # Check if OpenAI API key is set
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print(f"  Warning: OPENAI_API_KEY not set. Using basic keyword-based extraction for {section_name}.")
        # Fallback: basic keyword search
        return basic_keyword_extraction(document_text, country_name, section_name)
    
    # Use more of the document text for comprehensive extraction (increased to 20000 chars)
    # Prioritize the beginning and end of the document for better context
    if len(document_text) > 20000:
        # Take first 15000 and last 5000 chars for better context
        doc_preview = document_text[:15000] + "\n\n[... document continues ...]\n\n" + document_text[-5000:]
    else:
        doc_preview = document_text
    
    # Prepare the prompt
    prompt = f"""You are analyzing documents related to {country_name} for climate transparency reporting.

The following are examples of what information should be extracted for the {section_name}:

{section_examples[:2000]}

IMPORTANT: Extract ALL information that is even slightly relevant to {country_name} for the {section_name}. Be comprehensive and thorough. Include:
- ALL quantitative facts: numbers, amounts, dates, percentages, metrics, statistics, financial figures, timelines, targets, goals
- ALL qualitative facts: descriptions, assessments, evaluations, challenges, opportunities, recommendations, status updates, progress reports
- Projects, programs, initiatives, activities, and actions related to {country_name}
- Institutional arrangements, organizational structures, capacity building efforts
- Technical details, methodologies, frameworks, systems, tools
- Gaps, needs, barriers, constraints, limitations
- Achievements, outcomes, results, impacts, successes
- MRV systems, transparency frameworks, CBIT, ICAT, PATPA, NDC tracking, BTR, ETF
- Support tracking, climate finance, funding sources, donors, grants, assistance
- Policy measures, regulations, laws, strategies, plans
- Stakeholder involvement, partnerships, collaborations
- Training, workshops, technical assistance, knowledge transfer
- Any other information that could be relevant, even tangentially

Extract EVERYTHING that relates to {country_name}, no matter how minor the connection. Organize the information clearly and preserve all quantitative data (numbers, dates, amounts) exactly as they appear. Include context and details.

Document text:
{doc_preview}

Extract and present ALL relevant information in a clear, structured format. If you find any information about {country_name} related to {section_name}, include it. Only state that no relevant information was found if absolutely nothing relates to {country_name}."""

    try:
        # Use OpenAI API
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Using a cost-effective model
            messages=[
                {"role": "system", "content": "You are an expert at extracting comprehensive information from climate change and transparency documents. Your task is to extract ALL relevant information, both quantitative and qualitative, that relates to the specified country and section. Be thorough and include everything that is even slightly relevant. Preserve all numbers, dates, amounts, and specific details exactly as they appear in the document."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000,  # Increased to allow for more comprehensive extraction
            temperature=0.2  # Lower temperature for more factual, comprehensive extraction
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        print(f"  Error calling OpenAI API: {e}")
        # Fallback: return basic extraction
        return basic_keyword_extraction(document_text, country_name, section_name)

def basic_keyword_extraction(document_text, country_name, section_name):
    """Fallback method: basic keyword-based extraction."""
    keywords = {
        'NDC Tracking Module': ['NDC', 'tracking', 'MRV', 'monitoring', 'reporting', 'transparency', 'mitigation', 'adaptation', 'BTR', 'sector'],
        'Support Needed and Received Module': ['support', 'finance', 'funding', 'grant', 'donor', 'GCF', 'GEF', 'financial', 'capacity', 'technical assistance'],
        'Other Baseline Initiatives': ['project', 'program', 'initiative', 'CBIT', 'ICAT', 'PATPA', 'baseline', 'ETF', 'transparency']
    }
    
    relevant_keywords = keywords.get(section_name, [])
    lines = document_text.split('\n')
    relevant_lines = []
    
    for line in lines:
        if country_name.lower() in line.lower():
            # Check if line contains relevant keywords
            line_lower = line.lower()
            if any(kw.lower() in line_lower for kw in relevant_keywords):
                relevant_lines.append(line.strip())
    
    if relevant_lines:
        return f"\nRelevant excerpts from document:\n" + "\n".join(relevant_lines[:20])  # Limit to 20 lines
    else:
        return f"[No clearly relevant information found for {country_name} in this document for {section_name}]"

def process_files_for_country(country_name, folder_path, section_examples, section_name):
    """Process all files in a folder that match the country name and extract relevant information."""
    folder = Path(folder_path)
    
    if not folder.exists():
        print(f"Warning: Folder {folder_path} does not exist.")
        return ""
    
    # First, check if there's a subfolder matching the country name
    country_folder = folder / country_name
    if country_folder.exists() and country_folder.is_dir():
        # Use the country-specific subfolder (search only in this folder, not recursively)
        search_folder = country_folder
        print(f"Found country-specific folder: {country_folder}")
        # Get files directly in this folder
        all_paths = list(search_folder.glob('*'))
    else:
        # Search in the main folder recursively
        search_folder = folder
        # Get all files recursively
        all_paths = list(search_folder.rglob('*'))
    
    # Filter files to only include those with country name in filename (case-insensitive)
    files = []
    country_name_lower = country_name.lower()
    for file_path in all_paths:
        if file_path.is_file():
            filename_lower = file_path.name.lower()
            if country_name_lower in filename_lower:
                files.append(file_path)
    
    if not files:
        print(f"No files found matching '{country_name}' in {folder_path}")
        return ""
    
    print(f"Found {len(files)} file(s) matching '{country_name}': {[f.name for f in files]}")
    
    all_extracted_info = []
    
    for file_path in files:
        print(f"Processing {file_path.name}...")
        document_text = read_document(file_path)
        
        if document_text:
            # Extract relevant information using AI
            extracted = extract_relevant_info(document_text, country_name, section_examples, section_name)
            all_extracted_info.append(f"\n--- Information from {file_path.name} ---\n{extracted}\n")
    
    return "\n".join(all_extracted_info)

def main():
    # Get country name from environment or command line
    country_name = os.environ.get('COUNTRY_NAME', '')
    cbit_files_env = os.environ.get('CBIT_FILES', '')
    
    if not country_name:
        if len(sys.argv) > 1:
            country_name = sys.argv[1]
        else:
            country_name = input("Please enter country name: ").strip()
    
    if not country_name:
        print("Error: Country name is required.")
        return
    
    print(f"\nProcessing files for {country_name}...")
    
    # Get section examples
    sections_dict, section_examples_full = get_section_examples()
    
    # Ensure we have all three sections with defaults
    sections = {
        'NDC Tracking Module': sections_dict.get('NDC Tracking Module', ''),
        'Support Needed and Received Module': sections_dict.get('Support Needed and Received Module', ''),
        'Other Baseline Initiatives': sections_dict.get('Other Baseline Initiatives', '')
    }
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # Step 1: Ask user to upload files to ICAT:PATPA folder
    print(f"\nPlease upload relevant files to the 'input/ICAT_PATPA' folder and press Enter when done...")
    input()
    
    # Step 2: Process ICAT:PATPA files
    icat_folder = os.path.join(project_root, 'input', 'ICAT_PATPA')
    os.makedirs(icat_folder, exist_ok=True)
    
    # Step 3: Process CBIT files if any
    cbit_folder = os.path.join(project_root, 'input', 'CBIT')
    os.makedirs(cbit_folder, exist_ok=True)
    cbit_files = []
    if cbit_files_env:
        cbit_files = [f.strip() for f in cbit_files_env.split(',') if f.strip()]
    
    # Extract information for each section
    output_content = {}
    
    for section_name, section_example in sections.items():
        print(f"\nExtracting information for: {section_name}")
        
        section_content = []
        
        # Process ICAT:PATPA files
        icat_info = process_files_for_country(country_name, icat_folder, section_example, section_name)
        if icat_info:
            section_content.append(f"=== Information from ICAT/PATPA documents ===\n{icat_info}")
        
        # Process CBIT files (only those matching country name)
        if cbit_files:
            for cbit_file in cbit_files:
                # Only process if filename contains country name
                filename_lower = os.path.basename(cbit_file).lower()
                country_name_lower = country_name.lower()
                if country_name_lower in filename_lower and os.path.exists(cbit_file):
                    print(f"Processing CBIT file: {cbit_file}")
                    document_text = read_document(cbit_file)
                    if document_text:
                        extracted = extract_relevant_info(document_text, country_name, section_example, section_name)
                        section_content.append(f"\n=== Information from CBIT document: {os.path.basename(cbit_file)} ===\n{extracted}")
                elif os.path.exists(cbit_file):
                    print(f"Skipping CBIT file {os.path.basename(cbit_file)} (does not match country '{country_name}')")
        
        # Also check all files in CBIT folder (filtered by country name)
        cbit_folder_info = process_files_for_country(country_name, cbit_folder, section_example, section_name)
        if cbit_folder_info:
            section_content.append(f"\n=== Information from CBIT folder ===\n{cbit_folder_info}")
        
        output_content[section_name] = "\n\n".join(section_content) if section_content else f"[No relevant information found for {section_name}]"
    
    # Step 4: Generate output file
    output_folder = os.path.join(project_root, 'output')
    os.makedirs(output_folder, exist_ok=True)
    
    output_filename = f"{country_name} ICAT and PATPA text.txt"
    output_path = os.path.join(output_folder, output_filename)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"EXTRACTED INFORMATION FOR {country_name.upper()}\n")
        f.write("=" * 80 + "\n\n")
        
        for section_name, section_content in output_content.items():
            f.write(f"\n{'=' * 80}\n")
            f.write(f"{section_name.upper()}\n")
            f.write(f"{'=' * 80}\n\n")
            f.write(section_content)
            f.write("\n\n")
    
    print(f"\n✓ Output file created: {output_path}")
    print(f"  Sections included: {', '.join(output_content.keys())}")

if __name__ == "__main__":
    main()

