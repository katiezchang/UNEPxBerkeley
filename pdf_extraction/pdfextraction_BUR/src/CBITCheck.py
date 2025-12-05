#!/usr/bin/env python3
"""
CBITCheck.py - Checks projects.csv for CBIT projects matching user's country,
handles document downloads, and calls the ICAT/PATPA processor.
"""

import pandas as pd
import os
import requests
import subprocess
from urllib.parse import urlparse, unquote

def validate_openai_api_key(api_key):
    """
    Validate an OpenAI API key by making a test API call.
    Returns True if valid, False otherwise.
    """
    if not api_key or not api_key.strip():
        return False
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip())
        
        # Make a simple test call to validate the key
        # Using a minimal request to check if the key works
        response = client.models.list()
        return True
    except Exception as e:
        # If there's any error, the key is invalid
        return False

def get_openai_api_key():
    """
    Prompt user for OpenAI API key with validation.
    Returns the API key string if valid, or None if user presses enter.
    """
    while True:
        user_input = input("Please enter OpenAI API key (if not, press enter): ").strip()
        
        # If user pressed enter (empty input), return None
        if not user_input:
            print("No API key provided. Will use basic keyword-based extraction.")
            return None
        
        # Validate the API key
        print("Validating API key...")
        if validate_openai_api_key(user_input):
            print("✓ Valid API key. Will use AI for extraction.")
            return user_input
        else:
            print("✗ Invalid API key. Please try again or press enter to skip.")
            # Loop continues to ask again

def check_cbit_projects(country_name, csv_path='config/projects.csv'):
    """
    Check if there are any CBIT projects for the given country.
    Returns True if found, False otherwise.
    """
    try:
        # Get the script directory and navigate to project root
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        csv_path = os.path.join(project_root, csv_path)
        
        if not os.path.exists(csv_path):
            print(f"Warning: {csv_path} not found.")
            return False
        
        df = pd.read_csv(csv_path)
        
        # Check if any project matches the country and is CBIT-related
        # CBIT projects have "CBIT Trust Fund" in Funding Source or "Yes" in Capacity-building column
        country_match = df['Countries'].str.contains(country_name, case=False, na=False, regex=False)
        cbit_funding = df['Funding Source (indexed field)'].str.contains('CBIT', case=False, na=False, regex=False)
        cbit_capacity = df['Capacity-building Initiative for Transparency'] == 'Yes'
        
        # Check if there's at least one CBIT project for this country
        cbit_match = (country_match & (cbit_funding | cbit_capacity)).any()
        
        return cbit_match
    except Exception as e:
        print(f"Error reading projects.csv: {e}")
        return False

def download_file(url, output_folder='input/CBIT'):
    """
    Download a file from a URL and save it to the specified folder.
    Returns the path to the downloaded file or None if failed.
    """
    try:
        # Get script directory and navigate to project root
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        output_folder = os.path.join(project_root, output_folder)
        
        # Create output folder if it doesn't exist
        os.makedirs(output_folder, exist_ok=True)
        
        # Get filename from URL
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        
        # Decode URL-encoded filename
        filename = unquote(filename)
        
        # If no filename found, generate one
        if not filename or '.' not in filename:
            filename = f"cbit_document_{hash(url)}.pdf"
        
        output_path = os.path.join(output_folder, filename)
        
        # Download the file
        print(f"Downloading file from {url}...")
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Save to file
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"File successfully downloaded to {output_path}")
        return output_path
    
    except Exception as e:
        print(f"Error downloading file: {e}")
        return None

def main():
    # Get OpenAI API key from user (first step)
    api_key = get_openai_api_key()
    
    # Get country name from user
    country_name = input("\nPlease enter name of country: ").strip()
    
    if not country_name:
        print("Error: Country name cannot be empty.")
        return
    
    # Check for CBIT projects
    has_cbit = check_cbit_projects(country_name)
    
    cbit_file_paths = []
    
    if has_cbit:
        print(f"There was CBIT 1 for {country_name} published. Are there any relevant documents you can upload? If not, press enter")
        user_input = input().strip()
        
        if user_input:
            # User provided a link
            downloaded_file = download_file(user_input)
            if downloaded_file:
                cbit_file_paths.append(downloaded_file)
                print(f"File has been added and saved to the input/CBIT folder.")
            else:
                print("Failed to download the file. Continuing anyway...")
        else:
            # User pressed enter
            print(f"No prior CBIT initiative information for {country_name}. Proceeding with creating PIF.")
    else:
        print(f"No CBIT projects found for {country_name}. Proceeding with creating PIF.")
    
    # Automatically call the second script
    print("\nStarting ICAT/PATPA processing...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    icat_script = os.path.join(script_dir, 'ICAT_PATPA_Processor.py')
    
    # Pass country name, CBIT file paths, and API key as environment variables
    env = os.environ.copy()
    env['COUNTRY_NAME'] = country_name
    env['CBIT_FILES'] = ','.join(cbit_file_paths) if cbit_file_paths else ''
    if api_key:
        env['OPENAI_API_KEY'] = api_key
    
    try:
        subprocess.run(['python3', icat_script], env=env, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running ICAT/PATPA processor: {e}")
    except FileNotFoundError:
        print(f"Error: Could not find {icat_script}")

if __name__ == "__main__":
    main()

