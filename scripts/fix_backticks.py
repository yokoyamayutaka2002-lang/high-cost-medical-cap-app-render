from pathlib import Path

# List files to clean (relative to repo root)
files = [
    "tests/test_biologic_schedule.py",
    "tests/test_biologic_monthly.py",
    "scripts/collect_results.py",
    "run_calc.py",
    "src/biologic_monthly.py",
    "src/biologic_price.py",
    "src/biologic_events.py",
]

root = Path(__file__).resolve().parents[1]

for rel in files:
    p = root / rel
    if not p.exists():
        print(f"skip (not found): {rel}")
        continue
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()
    new_lines = [ln for ln in lines if not (ln.strip().startswith('```'))]
    if new_lines != lines:
        p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print(f"cleaned: {rel}")
    else:
        print(f"no change: {rel}")
