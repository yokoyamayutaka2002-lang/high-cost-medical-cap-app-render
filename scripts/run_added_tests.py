import importlib
import inspect
import sys

MODS = ['tests.test_billing']
failed = 0
for modname in MODS:
    try:
        mod = importlib.import_module(modname)
    except Exception as e:
        print(f'IMPORT ERROR {modname}: {e}')
        failed += 1
        continue
    for name, obj in inspect.getmembers(mod, inspect.isfunction):
        if name.startswith('test_'):
            try:
                obj()
                print(f'OK {modname}::{name}')
            except AssertionError as ae:
                print(f'FAIL {modname}::{name} - AssertionError: {ae}')
                failed += 1
            except Exception as e:
                print(f'ERROR {modname}::{name} - Exception: {e}')
                failed += 1

if failed == 0:
    print('ALL ADDED TESTS PASSED')
    sys.exit(0)
else:
    print(f'ADDED TESTS FAILED: {failed}')
    sys.exit(2)
