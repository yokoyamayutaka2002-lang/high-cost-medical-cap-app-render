import importlib.util
import sys
from pathlib import Path

# Ensure repository root is on sys.path so `src` can be imported
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

spec = importlib.util.spec_from_file_location('webapp.app', 'webapp/app.py')
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
    print('IMPORT_OK')
except Exception:
    print('IMPORT_FAILED')
    raise
