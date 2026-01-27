import json
import sys
from pathlib import Path
# ensure repository root is on sys.path so `src` package can be imported
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.calculator import simulate_selected_system

cases = [
    ("R7", "1", "under70"),            # R7 区分ア 相当
    ("R7", "3", "over70"),             # R7 一般所得者の over70 例
    ("R9", "L1", "over70"),            # R9 低所得者Ⅰ (L1) を直接指定
    ("R9", "R9_370_510", "over70"),    # R9 現役並み相当 (R9_370_510)
]

for system_version, income_code, age_group in cases:
    try:
        res = simulate_selected_system(
            system_version=system_version,
            income_code=income_code,
            age_group=age_group,
            drug_id="dupixent_300",
            prescription_interval_weeks=12,
        )
        print(system_version, income_code, age_group, json.dumps(res, ensure_ascii=False))
    except Exception as e:
        print(system_version, income_code, age_group, "ERROR:", str(e))
