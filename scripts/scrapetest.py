import requests
from bs4 import BeautifulSoup

def get_premier_league_managers(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # Find the "Personnel and kits" header
    header = soup.find('span', {'id': 'Personnel_and_kits'})

    # Navigate to the parent (usually an <h2> or <h3>) and then find the next table
    table = header.find_parent().find_next('table', {'class': 'wikitable'})

    if not table:
        return "Table not found"

    # Extract manager names
    managers = []
    rows = table.findAll('tr')
    for row in rows[1:]:  # Skip the header row
        columns = row.findAll('td')
        if columns:
            manager = columns[1].get_text(strip=True)
            managers.append(manager)

    return managers

url = "https://en.wikipedia.org/wiki/2023%E2%80%9324_Premier_League"
managers = get_premier_league_managers(url)
for manager in managers:
    print(manager)
