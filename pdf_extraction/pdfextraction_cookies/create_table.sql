-- SQL script to create the climate_policy_sections table in Supabase
-- Run this in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS climate_policy_sections (
    id BIGSERIAL PRIMARY KEY,
    country TEXT NOT NULL,
    section TEXT NOT NULL,
    source_doc TEXT NOT NULL,
    doc_url TEXT NOT NULL,
    extracted_text TEXT NOT NULL,
    created_utc TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_climate_policy_country ON climate_policy_sections(country);
CREATE INDEX IF NOT EXISTS idx_climate_policy_section ON climate_policy_sections(section);
CREATE INDEX IF NOT EXISTS idx_climate_policy_source_doc ON climate_policy_sections(source_doc);
CREATE INDEX IF NOT EXISTS idx_climate_policy_created_utc ON climate_policy_sections(created_utc);

-- Create a composite index for common query patterns
CREATE INDEX IF NOT EXISTS idx_climate_policy_country_section ON climate_policy_sections(country, section);

-- Add a unique constraint to prevent duplicate entries
-- (same country, section, source_doc, and doc_url)
CREATE UNIQUE INDEX IF NOT EXISTS idx_climate_policy_unique 
ON climate_policy_sections(country, section, source_doc, doc_url);

-- Enable Row Level Security (RLS) - adjust policies as needed
ALTER TABLE climate_policy_sections ENABLE ROW LEVEL SECURITY;

-- Create a policy to allow all operations (adjust based on your security needs)
-- For public read access:
CREATE POLICY "Allow public read access" ON climate_policy_sections
    FOR SELECT USING (true);

-- For authenticated insert/update/delete (adjust as needed):
CREATE POLICY "Allow authenticated insert" ON climate_policy_sections
    FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow authenticated update" ON climate_policy_sections
    FOR UPDATE USING (true);

CREATE POLICY "Allow authenticated delete" ON climate_policy_sections
    FOR DELETE USING (true);

