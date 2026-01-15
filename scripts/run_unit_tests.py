import importlib
import inspect
import sys
from pathlib import Path

# ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_MODULES = [
    'tests.test_biologic_schedule',
    'tests.test_biologic_monthly',
    'tests.test_biologic_maintenance',
]

results = []
failed = 0
for modname in TEST_MODULES:
    try:
        mod = importlib.import_module(modname)
    except Exception as e:
        print(f"IMPORT ERROR {modname}: {e}")
        failed += 1
        continue
    for name, obj in inspect.getmembers(mod, inspect.isfunction):
        if name.startswith('test_'):
            try:
                obj()
                print(f"OK {modname}::{name}")
            except AssertionError as ae:
                print(f"FAIL {modname}::{name} - AssertionError: {ae}")
                failed += 1
            except Exception as e:
                print(f"ERROR {modname}::{name} - Exception: {e}")
                failed += 1

if failed == 0:
    print('ALL TESTS PASSED')
    sys.exit(0)
else:
    print(f'TESTS FAILED: {failed}')
    sys.exit(2)
