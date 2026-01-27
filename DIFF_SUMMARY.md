--- DIFF SUMMARY ---
Files added:
- `scripts/validate_csv.py`
- `scripts/limit_to_master_map.csv`

Files modified:
- `data/income_category_master.csv`
  - canonical income_code 行を追記（削除なし）
  - `display_order` / `description` を追加
- `src/app.py`
  - UI 表示ロジックを master CSV + mapping CSV に切替
  - 計算ロジックは不変

Files NOT modified:
- `src/calculator.py`
- `data/limit_table.csv`

Validation:
- `python scripts/validate_csv.py` → PASS
- `python run_calc.py` → PASS
--- END DIFF SUMMARY ---
