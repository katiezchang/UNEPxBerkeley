import requests
from bs4 import BeautifulSoup

BASE_URL = "https://unfccc.int/reports"

def get_country_reports(country_id):
    # Filter by corporate author = Guinea-Bissau. 442 is the ID used by UNFCCC.
    params = {
        "f[0]": "corporate_author:{country_id}",
        "items_per_page": 50,   # big enough to avoid "Load more" for now
        "view": "table",        # list view with the table (optional but nice)
    }

    resp = requests.get(BASE_URL, params=params)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the main results table
    table = soup.find("table")
    if not table:
        raise RuntimeError("Could not find results table on the page")

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")

    results = []

    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) < 4:
            # Unexpected format, skip
            continue

        # UNFCCC table layout (at time of writing) is:
        # [0] Document name, [1] Type of document, [2] Author, [3] Submission date
        name = tds[0].get_text(strip=True)
        submission_date = tds[3].get_text(strip=True)

        results.append({
            "name": name,
            "submission_date": submission_date
        })

    return results

if __name__ == "__main__":
    reports = get_country_reports("442")
    # Print in a nice table-like way
    for r in reports:
        print(f"{r['name']}  |  {r['submission_date']}")
