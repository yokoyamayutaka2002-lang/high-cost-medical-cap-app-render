import requests, sys
url='http://127.0.0.1:5000/print'
print('Requesting', url)
try:
    r=requests.get(url, timeout=5)
    print('Status:', r.status_code)
    print(r.text[:800])
except Exception as e:
    print('ERROR', repr(e))
    sys.exit(1)
