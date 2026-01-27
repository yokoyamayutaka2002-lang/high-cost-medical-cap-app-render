from runpy import run_path
from pathlib import Path

# Resolve webapp/app.py relative to repository root (two levels up from this script)
root = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(root))
app_path = str(root / 'webapp' / 'app.py')
g = run_path(app_path)
app = g['app']

from datetime import date

d = date.today().isoformat()

# minimal form data sent by the UI
form = {
    'start_date': d,
    'drug_id': 'dupixent_300',
    'income_category': '',
    'prescription_interval_weeks': '12',
}

with app.test_client() as client:
    resp = client.post('/calculate', data=form)
    print('STATUS:', resp.status_code)
    body = resp.data.decode('utf-8', errors='ignore')
    print('BODY (truncated):')
    print(body[:4000])
