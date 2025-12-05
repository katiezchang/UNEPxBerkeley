#!/usr/bin/env python3
"""
Helper script to export browser cookies from unfccc.int for use with the unified scrape_unfccc.py

This script uses Selenium to automate a browser, navigate to UNFCCC, and export
cookies as JSON that can be used with the --cookies-file flag.

Usage:
    python3 src/export_cookies.py

The script will:
1. Open a browser window
2. Navigate to https://unfccc.int
3. Wait for you to manually navigate/authenticate if needed
4. Extract cookies and save to unfccc_cookies.json
"""

import json
import time
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    print("Selenium is not installed. Installing...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "selenium"])
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC


def export_cookies(output_file: Path = None) -> None:
    """
    Export cookies from unfccc.int using Selenium.
    
    Args:
        output_file: Path to save cookies JSON (default: unfccc_cookies.json in script dir)
    """
    if output_file is None:
        script_dir = Path(__file__).parent.resolve()
        output_file = script_dir / "unfccc_cookies.json"
    
    print("=" * 60)
    print("UNFCCC Cookie Exporter")
    print("=" * 60)
    print(f"\nThis script will:")
    print("1. Open a Chrome browser window")
    print("2. Navigate to https://unfccc.int")
    print("3. Wait for you to manually browse/authenticate if needed")
    print("4. Extract cookies and save to: {output_file}")
    print("\nPress Enter when you're ready to start...")
    input()
    
    # Set up Chrome options
    chrome_options = Options()
    # Uncomment the next line if you want headless mode (no browser window)
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    driver = None
    try:
        print("\nOpening browser...")
        driver = webdriver.Chrome(options=chrome_options)
        
        print("Navigating to https://unfccc.int...")
        driver.get("https://unfccc.int")
        
        print("\n" + "=" * 60)
        print("Browser is now open!")
        print("=" * 60)
        print("\nPlease:")
        print("1. Navigate to the BURs page or any UNFCCC page you need")
        print("2. If you need to log in or accept cookies, do so now")
        print("3. Once you're on the page you want, come back here")
        print("\nPress Enter when you're done browsing...")
        input()
        
        # Get all cookies
        cookies = driver.get_cookies()
        
        if not cookies:
            print("\n⚠️  Warning: No cookies found. Make sure you've navigated to unfccc.int")
            return
        
        # Convert Selenium cookie format to simple dict
        cookie_dict = {}
        for cookie in cookies:
            cookie_dict[cookie["name"]] = cookie["value"]
        
        # Save to JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(cookie_dict, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Success! Exported {len(cookie_dict)} cookies to:")
        print(f"   {output_file}")
        print("\nYou can now use this file with the unified scraper:")
        print(f'   python3 ../pdfextraction_cookies/scrape_unfccc.py --country "Jordan" --cookies-file "{output_file}"')
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure you have Chrome installed and chromedriver available.")
        print("You can install chromedriver with:")
        print("  brew install chromedriver  # on macOS")
        print("Or download from: https://chromedriver.chromium.org/")
        
    finally:
        if driver:
            print("\nClosing browser in 3 seconds...")
            time.sleep(3)
            driver.quit()


if __name__ == "__main__":
    export_cookies()

