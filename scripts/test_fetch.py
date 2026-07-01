import requests
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
url = 'https://datachart.500.com/ssq/history/inc/history.php?start=00001&end=99999'
r = requests.get(url, headers=headers, timeout=30)
r.encoding = 'gb2312'
html = r.text
print('Length:', len(html))

soup = BeautifulSoup(html, 'lxml')
# Try different table IDs
table_ids = ['tdata', 'tablelist', None]
for tid in table_ids:
    if tid:
        table = soup.find('table', id=tid)
    else:
        table = soup.find('table')
    if table:
        rows = table.find_all('tr')
        print(f'Table {tid}: {len(rows)} rows')
        if rows:
            cols = rows[0].find_all('td')
            print([c.get_text(strip=True) for c in cols[:10]])
    else:
        print(f'Table {tid}: not found')
