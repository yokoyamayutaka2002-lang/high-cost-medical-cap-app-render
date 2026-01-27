import csv
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

MASTER_FN = DATA_DIR / "income_category_master.csv"
LIMIT_FN = DATA_DIR / "limit_table.csv"

errors = []


def ok(msg):
    print(msg)


def ng(msg):
    print(msg)
    errors.append(msg)


# A: income_category_master.csv schema
print("[A] income_category_master.csv schema check...")
required_master_cols = [
    "system_base",
    "age_group",
    "income_code",
    "display_name",
    "description",
    "display_order",
    "short_name",
]

try:
    with MASTER_FN.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        missing = [c for c in required_master_cols if c not in headers]
        if missing:
            ng(f"income_category_master.csv missing columns: {missing}")
        else:
            # per-row checks
            row_no = 1
            for row in reader:
                row_no += 1
                sb = (row.get("system_base") or "").strip()
                ag = (row.get("age_group") or "").strip()
                ic = (row.get("income_code") or "").strip()
                do = (row.get("display_order") or "").strip()
                if not sb:
                    ng(f"income_category_master.csv row {row_no}: empty system_base")
                if not ag:
                    ng(f"income_category_master.csv row {row_no}: empty age_group")
                if not ic:
                    ng(f"income_category_master.csv row {row_no}: empty income_code")
                # display_order must be int-convertible
                try:
                    int(do)
                except Exception:
                    ng(f"income_category_master.csv row {row_no}: display_order not int: '{do}'")
            if not errors:
                ok("[A] OK")
except FileNotFoundError:
    ng(f"income_category_master.csv not found at {MASTER_FN}")
except Exception as e:
    ng(f"income_category_master.csv read error: {e}")


# B: limit_table.csv schema
print("[B] limit_table.csv schema check...")
required_limit_cols = [
    "system_version",
    "age_group",
    "income_code",
    "monthly_limit",
    "monthly_limit_after_many",
    "annual_limit",
    "outpatient_limit_70plus",
    "is_non_tax",
    "is_outpatient_special_70plus",
]

try:
    with LIMIT_FN.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        missing = [c for c in required_limit_cols if c not in headers]
        if missing:
            ng(f"limit_table.csv missing columns: {missing}")
        else:
            row_no = 1
            for row in reader:
                row_no += 1
                # numeric fields: allow empty or int
                for col in ["monthly_limit", "monthly_limit_after_many", "annual_limit", "outpatient_limit_70plus"]:
                    val = (row.get(col) or "").strip()
                    if val:
                        try:
                            int(val)
                        except Exception:
                            ng(f"limit_table.csv row {row_no}: column {col} not int-convertible: '{val}'")
                # boolean-ish fields
                for col in ["is_non_tax", "is_outpatient_special_70plus"]:
                    val = (row.get(col) or "").strip()
                    if val and val.lower() not in ("true", "false"):
                        # allow 1/0 as well
                        if val not in ("1", "0"):
                            ng(f"limit_table.csv row {row_no}: column {col} not boolean-like: '{val}'")
            if not errors:
                ok("[B] OK")
except FileNotFoundError:
    ng(f"limit_table.csv not found at {LIMIT_FN}")
except Exception as e:
    ng(f"limit_table.csv read error: {e}")


# C: key consistency
print("[C] key consistency check...")
try:
    # build master key set
    master_keys = set()
    with MASTER_FN.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sb = (row.get("system_base") or "").strip()
            ag = (row.get("age_group") or "").strip()
            ic = (row.get("income_code") or "").strip()
            master_keys.add((sb, ag, ic))

    # mapping function from system_version -> system_base
    def system_version_to_base(sv: str) -> str:
        sv = (sv or "").strip()
        if sv in ("R7", "R8"):
            return "R7R8"
        if sv == "R9":
            return "R9plus"
        return sv

    # load optional mapping file (limit -> master)
    MAPPING_FN = Path(__file__).parent / "limit_to_master_map.csv"
    mapping = {}
    mapping_exists = False
    if MAPPING_FN.exists():
        mapping_exists = True
        with MAPPING_FN.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                m_sv = (row.get("system_version") or "").strip()
                m_ag = (row.get("age_group") or "").strip()
                lim = (row.get("limit_income_code") or "").strip()
                mast = (row.get("master_income_code") or "").strip()
                if m_sv and m_ag and lim and mast:
                    mapping.setdefault((m_sv, m_ag), {})[lim] = mast

    direct_matches = 0
    mapping_matches = 0
    failures = 0

    with LIMIT_FN.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row_no = 1
        for row in reader:
            row_no += 1
            sv = (row.get("system_version") or "").strip()
            ag = (row.get("age_group") or "").strip()
            ic = (row.get("income_code") or "").strip()

            sb = system_version_to_base(sv)

            # C-1: direct match against master_keys
            if (sb, ag, ic) in master_keys:
                direct_matches += 1
                continue

            # C-2: consult explicit mapping (if present)
            if mapping_exists:
                mapped = mapping.get((sv, ag), {}).get(ic)
                if mapped:
                    # mapped master code should exist under the system_base
                    if (sb, ag, mapped) in master_keys:
                        mapping_matches += 1
                        continue
                    else:
                        ng(f"limit_table.csv row {row_no}: mapping present ({sv},{ag},{ic})->{mapped}, but master key ({sb},{ag},{mapped}) not found")
                        failures += 1
                        continue
                else:
                    ng(f"limit_table.csv row {row_no}: no mapping for ({sv},{ag},{ic}) in limit_to_master_map.csv")
                    failures += 1
                    continue

            # no direct match and no mapping file (or mapping not found)
            ng(f"limit_table.csv row {row_no}: key ({sv},{ag},{ic}) not found in income_category_master.csv")
            failures += 1

    # concise summary prints per spec
    if direct_matches:
        print("Check C-1: direct match OK")
    if mapping_matches:
        print("Check C-2: mapping match OK")
    if failures:
        if not mapping_exists:
            ng("Check C: FAILED (no mapping file present)")
        else:
            ng("Check C: FAILED (no mapping found for some rows)")
    if not errors:
        ok("[C] OK")
except Exception as e:
    ng(f"key consistency check error: {e}")


# D: regression check via run_calc.py
print("[D] regression check: running run_calc.py...")
if not errors:
    import shlex
    try:
        proc = subprocess.run([sys.executable, "run_calc.py"], cwd=str(ROOT), capture_output=True, text=True)
        print(proc.stdout)
        if proc.returncode != 0:
            ng(f"run_calc.py failed with exit {proc.returncode}")
            print(proc.stderr)
        else:
            ok("[D] run_calc.py OK")
    except Exception as e:
        ng(f"failed to run run_calc.py: {e}")
else:
    print("Skipping [D] because earlier checks failed")


if errors:
    print("CSV validation: NG - see errors above")
    sys.exit(1)
else:
    print("CSV validation and regression checks passed.")
    sys.exit(0)
