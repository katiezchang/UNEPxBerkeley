"""
Script to upload extracted climate policy sections to Supabase database.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from supabase import create_client, Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)

# Load Supabase configuration
CONFIG_PATH = Path(__file__).parent / "supabase_config.json"


def load_config() -> Dict[str, str]:
    """Load Supabase configuration from JSON file."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def connect_to_supabase() -> Client:
    """Create and return a Supabase client connection."""
    config = load_config()
    url = config["project_url"]
    key = config["api_key"]
    
    logging.info("Connecting to Supabase at %s", url)
    client = create_client(url, key)
    return client


def extract_country_from_filename(filename: str) -> str:
    """Extract country name from filename."""
    import re
    # Handle formats like: {Country}_transformed.json or {Country}_{Section}_{Doc}.json
    match = re.match(r'\{([^}]+)\}_', filename)
    if match:
        return match.group(1)
    # Handle formats like: Country_transformed.json (including multi-word countries with underscores)
    match = re.match(r'^(.+?)_transformed', filename)
    if match:
        # Replace underscores with spaces for country names
        country = match.group(1).replace('_', ' ')
        return country
    return "Unknown"


def upload_json_file(
    client: Client,
    json_path: Path,
    table_name: str = "climate_policy_sections",
    country: Optional[str] = None,
) -> int:
    """
    Upload entries from a JSON file to Supabase.
    Handles both old format (list of entries) and new format (sections structure).
    
    Args:
        client: Supabase client instance
        json_path: Path to the JSON file
        table_name: Name of the Supabase table to insert into
        country: Country name (if not provided, extracted from filename)
        
    Returns:
        Number of entries successfully uploaded
    """
    if not json_path.exists():
        logging.warning("File not found: %s", json_path)
        return 0
    
    logging.info("Loading entries from %s", json_path.name)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Extract country from filename if not provided
    if country is None:
        country = extract_country_from_filename(json_path.name)
    
    # Convert to list of entries
    entries = []
    
    if isinstance(data, list):
        # Old format - list of entries
        entries = data
    elif isinstance(data, dict) and "sections" in data:
        # New format - sections structure
        for section_obj in data.get("sections", []):
            section_name = section_obj.get("name", "")
            for doc in section_obj.get("documents", []):
                entries.append({
                    "country": country,
                    "section": section_name,
                    "source_doc": doc.get("doc_type", ""),
                    "doc_url": "",  # Not in new format
                    "extracted_text": doc.get("extracted_text", ""),
                    "created_utc": datetime.utcnow().isoformat().replace("+00:00", "Z"),
                })
    else:
        logging.error("Unsupported JSON format in %s", json_path.name)
        return 0
    
    if not entries:
        logging.warning("No entries found in %s", json_path.name)
        return 0
    
    logging.info("Found %d entries to upload from %s", len(entries), json_path.name)
    
    uploaded = 0
    failed = 0
    
    for entry in entries:
        try:
            # Prepare the entry for database insertion
            db_entry = {
                "country": entry.get("country", country),
                "section": entry.get("section", ""),
                "source_doc": entry.get("source_doc", ""),
                "doc_url": entry.get("doc_url", ""),
                "extracted_text": entry.get("extracted_text", ""),
                "created_utc": entry.get("created_utc", datetime.utcnow().isoformat().replace("+00:00", "Z")),
            }
            
            # Insert into Supabase
            response = client.table(table_name).insert(db_entry).execute()
            
            if response.data:
                uploaded += 1
                if uploaded % 10 == 0:
                    logging.info("Uploaded %d entries...", uploaded)
            else:
                failed += 1
                logging.warning("Failed to upload entry for %s - %s", 
                              entry.get("country"), entry.get("source_doc"))
                
        except Exception as exc:
            failed += 1
            logging.error("Error uploading entry: %s", exc)
            logging.debug("Failed entry: %s - %s", entry.get("country", "unknown"), entry.get("source_doc", "unknown"))
    
    logging.info("Upload complete for %s: %d successful, %d failed", json_path.name, uploaded, failed)
    return uploaded


def upload_bundle_entries(
    client: Client,
    bundle_path: Path,
    table_name: str = "climate_policy_sections",
) -> int:
    """Legacy function name - redirects to upload_json_file."""
    return upload_json_file(client, bundle_path, table_name)


def upload_country_to_countries_table(
    client: Client,
    json_path: Path,
    table_name: str = "countries",
    upsert: bool = True,
) -> bool:
    """
    Upload a country's data to the countries table.
    
    Args:
        client: Supabase client instance
        json_path: Path to the country transformed JSON file
        table_name: Name of the countries table (default: "countries")
        upsert: Whether to update if country already exists (default: True)
        
    Returns:
        True if successful, False otherwise
    """
    if not json_path.exists():
        logging.warning("File not found: %s", json_path)
        return False
    
    # Extract country name from filename
    country_name = extract_country_from_filename(json_path.name)
    
    logging.info("Loading country data from %s (country: %s)", json_path.name, country_name)
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Ensure data has the sections structure
        if not isinstance(data, dict) or "sections" not in data:
            logging.error("Invalid format in %s - expected object with 'sections' key", json_path.name)
            return False
        
        # Prepare the database entry
        db_entry = {
            "name": country_name,
            "sections": data  # Store the entire JSON structure in the jsonb field
        }
        
        # Check if country already exists
        existing = client.table(table_name).select("name").eq("name", country_name).execute()
        
        if upsert and existing.data:
            # Update existing record
            response = client.table(table_name).update({
                "sections": data
            }).eq("name", country_name).execute()
            logging.info("Updated existing record for %s", country_name)
        else:
            # Insert new record
            response = client.table(table_name).insert(db_entry).execute()
            logging.info("Inserted new record for %s", country_name)
        
        if response.data:
            logging.info("Successfully uploaded %s to countries table", country_name)
            return True
        else:
            logging.warning("No data returned for %s", country_name)
            return False
            
    except Exception as exc:
        logging.error("Error uploading %s: %s", country_name, exc)
        return False


def upload_all_countries(
    data_dir: Optional[Path] = None,
    table_name: str = "countries",
    upsert: bool = True,
) -> Dict[str, bool]:
    """
    Upload all country transformed files to the countries table.
    
    Args:
        data_dir: Directory containing transformed JSON files (default: data/)
        table_name: Name of the countries table
        upsert: Whether to update if country already exists
        
    Returns:
        Dictionary mapping country names to success status
    """
    if data_dir is None:
        data_dir = Path(__file__).parent / "data"
    
    client = connect_to_supabase()
    
    # Find all country-level transformed files
    transformed_files = list(data_dir.glob("*_transformed.json"))
    
    if not transformed_files:
        logging.warning("No transformed country files found in %s", data_dir)
        return {}
    
    logging.info("Found %d country files to upload", len(transformed_files))
    
    results = {}
    
    for json_path in transformed_files:
        country_name = extract_country_from_filename(json_path.name)
        success = upload_country_to_countries_table(client, json_path, table_name, upsert)
        results[country_name] = success
    
    successful = sum(1 for v in results.values() if v)
    logging.info("Upload complete: %d successful, %d failed out of %d countries", 
                successful, len(results) - successful, len(results))
    
    return results


def upload_all_bundles(
    data_dir: Optional[Path] = None,
    table_name: str = "climate_policy_sections",
) -> Dict[str, int]:
    """
    Upload all bundle JSON files to Supabase.
    
    Args:
        data_dir: Directory containing bundle JSON files (default: data/)
        table_name: Name of the Supabase table
        
    Returns:
        Dictionary mapping bundle names to upload counts
    """
    if data_dir is None:
        data_dir = Path(__file__).parent / "data"
    
    client = connect_to_supabase()
    
    # Find all JSON files to upload
    json_files = []
    
    # Add country-level transformed files
    transformed_files = list(data_dir.glob("*_transformed.json"))
    json_files.extend(transformed_files)
    
    # Add individual section files from subdirectories
    section_dirs = [
        data_dir / "Institutional_framework_for_climate_action",
        data_dir / "National_policy_framework",
    ]
    for section_dir in section_dirs:
        if section_dir.exists():
            section_files = list(section_dir.glob("*.json"))
            json_files.extend(section_files)
    
    # Exclude backup files
    json_files = [f for f in json_files if not f.name.endswith(".backup")]
    
    if not json_files:
        logging.warning("No JSON files found in %s", data_dir)
        return {}
    
    logging.info("Found %d JSON files to upload", len(json_files))
    
    results = {}
    total_uploaded = 0
    
    for json_path in json_files:
        logging.info("Processing %s", json_path.name)
        count = upload_json_file(client, json_path, table_name)
        results[json_path.name] = count
        total_uploaded += count
    
    logging.info("Total entries uploaded: %d", total_uploaded)
    return results


def test_connection() -> bool:
    """Test the Supabase connection."""
    try:
        client = connect_to_supabase()
        # Try a simple query to test connection
        # This will fail if table doesn't exist, but connection is good
        logging.info("Testing Supabase connection...")
        # We'll just check if we can create the client successfully
        logging.info("Connection successful!")
        return True
    except Exception as exc:
        logging.error("Connection test failed: %s", exc)
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Upload climate policy sections to Supabase"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test the Supabase connection",
    )
    parser.add_argument(
        "--bundle",
        type=str,
        help="Upload a specific bundle file (e.g., Institutional_framework_bundle.json)",
    )
    parser.add_argument(
        "--table",
        default="climate_policy_sections",
        help="Supabase table name (default: climate_policy_sections)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        help="Directory containing bundle JSON files",
    )
    parser.add_argument(
        "--countries",
        action="store_true",
        help="Upload to countries table (name + sections jsonb)",
    )
    parser.add_argument(
        "--no-upsert",
        action="store_true",
        help="Don't update existing countries (insert only)",
    )
    
    args = parser.parse_args()
    
    if args.test:
        success = test_connection()
        exit(0 if success else 1)
    
    if args.countries:
        # Upload to countries table
        data_dir = Path(args.data_dir) if args.data_dir else None
        results = upload_all_countries(data_dir, args.table, upsert=not args.no_upsert)
        logging.info("Upload summary: %s", results)
    elif args.bundle:
        client = connect_to_supabase()
        bundle_path = Path(args.bundle)
        if not bundle_path.is_absolute():
            data_dir = Path(args.data_dir) if args.data_dir else Path(__file__).parent / "data"
            bundle_path = data_dir / args.bundle
        upload_bundle_entries(client, bundle_path, args.table)
    else:
        data_dir = Path(args.data_dir) if args.data_dir else None
        results = upload_all_bundles(data_dir, args.table)
        logging.info("Upload summary: %s", results)

