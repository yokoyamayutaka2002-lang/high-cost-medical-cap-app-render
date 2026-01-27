import requests, time, sys

time.sleep(1)
url = 'http://127.0.0.1:5000/'
print('Requesting', url)
try:
    r = requests.get(url, timeout=5)
    print('Status:', r.status_code)
    found = '/print' in r.text
    print("Contains '/print':", found)
    # also check for result section id
    print("Contains id=\"result-section\":", 'id="result-section"' in r.text)
except Exception as e:
    print('ERROR:', repr(e))
    sys.exit(1)
