--- CHANGELOG ---
## Added
- income_category_master.csv に canonical income codes を追加
  - R7R8 / R9plus × under70 / over70 に対し、
    E1–E9, G1–G3, L1, L2, I, U を明示定義
  - display_name / description を明確化（所得区分の注釈付き）
  - display_order を追加し、UI 表示順を安定化

- limit_to_master_map.csv を追加
  - limit_table.csv の legacy income_code と
    canonical master income_code の対応を明示的に定義
  - 表示ロジックと計算ロジックの分離を保証

- scripts/validate_csv.py を追加
  - master / limit / mapping のキー整合性チェック
  - CSV スキーマ検証
  - run_calc.py による回帰テストを統合

## Changed
- app.py
  - 所得区分の UI 表示を income_category_master.csv に完全移行
  - limit_to_master_map.csv を優先参照し、明示 mapping を利用
  - 計算に渡す income_code / age_group / system_version は変更なし

## Unchanged
- calculator.py
  - 月額・年額・多数回該当の計算ロジックは一切変更なし
- 数値計算結果
  - validate_csv.py / run_calc.py によりパッチ前後で完全一致を確認

## Notes
- 将来の制度改定（R10+）は limit_table.csv の差し替えのみで対応可能
- UI 表示変更が計算ロジックへ影響しない設計を保証

## Added - Inhaled drug pricing pipeline (2025-04)
- Source: topical MHLW Excel (official prices)
- Exact item-name matching (`exact_item_name`) is used to extract prices from the topical Excel.
- Master-driven workflow: `data/inhaled_drug_master_exact.csv` is authoritative; duplicates were deduplicated and master order preserved.
- Extracted prices are deduplicated at write-time by `exact_item_name`.
- 12-week cost calculation implemented and output to `reports/inhaled_drug_12w_cost_2025-04.csv`.
- Combination rules applied in `scripts/evaluate_inhaled_combinations.py`:
  - Triple products (e.g. テリルジー, エナジア) override other inhalers.
  - If any Triple product is present, non-Triple inhalers are excluded.
  - If a master product is not found in the Excel, it is reported as `selected=false` with reason `not found in Excel`.
- Final consolidated report: `reports/inhaled_summary_2025-04.csv` (master order, selected/exclusion reasons).

Purpose: this pipeline establishes the canonical approach for future high-cost drug integrations (e.g. biologics). It documents why the master-led, exact-match design was chosen and preserves an auditable CSV output for review.
--- END CHANGELOG ---
