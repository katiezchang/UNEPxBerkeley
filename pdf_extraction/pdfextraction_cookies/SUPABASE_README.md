# Supabase Integration Guide

This guide explains how to upload the extracted climate policy sections to your Supabase database.

## Setup

### 1. Create the Database Table

Before uploading data, you need to create the table in Supabase:

1. Go to your Supabase project dashboard: https://tulbxwdifnzquliytsog.supabase.co
2. Navigate to **SQL Editor**
3. Copy and paste the contents of `create_table.sql`
4. Run the SQL script to create the `climate_policy_sections` table

### 2. Verify Configuration

The Supabase credentials are stored in `supabase_config.json`:
- Project URL: `https://tulbxwdifnzquliytsog.supabase.co`
- API Key: Already configured

## Usage

### Test Connection

Test that the Supabase connection works:

```bash
python upload_to_supabase.py --test
```

### Upload All Bundle Files

Upload all bundle JSON files to Supabase:

```bash
python upload_to_supabase.py
```

This will upload entries from:
- `data/Institutional_framework_bundle.json`
- `data/National_policy_framework_bundle.json`

### Upload a Specific Bundle

Upload a specific bundle file:

```bash
python upload_to_supabase.py --bundle Institutional_framework_bundle.json
```

### Custom Table Name

If you want to use a different table name:

```bash
python upload_to_supabase.py --table my_custom_table_name
```

## Database Schema

The `climate_policy_sections` table has the following structure:

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL | Primary key (auto-generated) |
| `country` | TEXT | Country name (e.g., "Cuba", "Jordan") |
| `section` | TEXT | Section name (e.g., "Institutional framework for climate action") |
| `source_doc` | TEXT | Source document type (e.g., "BUR1", "NDC", "NC") |
| `doc_url` | TEXT | URL of the source PDF document |
| `extracted_text` | TEXT | Full extracted text from the section |
| `created_utc` | TIMESTAMPTZ | UTC timestamp when the entry was created |
| `created_at` | TIMESTAMPTZ | Database insertion timestamp |
| `updated_at` | TIMESTAMPTZ | Last update timestamp |

## Querying the Data

Once uploaded, you can query the data in Supabase:

### Get all entries for a country:
```sql
SELECT * FROM climate_policy_sections 
WHERE country = 'Cuba';
```

### Get all institutional framework entries:
```sql
SELECT * FROM climate_policy_sections 
WHERE section = 'Institutional framework for climate action';
```

### Get entries by document type:
```sql
SELECT * FROM climate_policy_sections 
WHERE source_doc = 'BUR1';
```

### Search within extracted text:
```sql
SELECT country, section, source_doc 
FROM climate_policy_sections 
WHERE extracted_text ILIKE '%CITMA%';
```

## Notes

- The script uses the **service role key** (secret key) which has full database access
- Duplicate entries (same country, section, source_doc, doc_url) are prevented by a unique constraint
- The script will log progress and any errors during upload
- Large text fields are stored as TEXT type to accommodate long extracted sections

## Troubleshooting

### Connection Errors
- Verify your Supabase project URL and API key in `supabase_config.json`
- Check that your Supabase project is active

### Table Not Found
- Make sure you've run the `create_table.sql` script in the Supabase SQL Editor
- Verify the table name matches (default: `climate_policy_sections`)

### Upload Failures
- Check the logs for specific error messages
- Verify that the JSON bundle files are valid
- Ensure the table schema matches the expected structure

