# Simple CLI that uses `simulate_selected_system` and `generate_patient_explanation`
# from `src.calculator` to collect inputs and display results.

from typing import Optional
import csv
from pathlib import Path
from datetime import datetime, timedelta
from src.calculator import simulate_selected_system, generate_patient_explanation


def get_income_display_info(
    system_base: str,
    age_group: str,
    income_code: str
) -> dict:
    """
    income_category_master.csv から
    表示用ラベル（display_name, description）を取得する。
    計算ロジックには一切関与しない。
    """
    # repository layout: data/ is at workspace root, app.py is in src/
    path = Path(__file__).parent.parent / "data" / "income_category_master.csv"

    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (
                row["system_base"] == system_base
                and row["age_group"] == age_group
                and row["income_code"] == income_code
            ):
                return {
                    "display_name": row["display_name"],
                    "description": row["description"],
                }

    raise ValueError(
        f"income category not found: "
        f"{system_base=}, {age_group=}, {income_code=}"
    )


def _load_limit_to_master_map():
    """Load scripts/limit_to_master_map.csv into a dict keyed by (system_version, age_group).

    Returns: {(system_version, age_group): {limit_income_code: master_income_code}}
    """
    mapping_fn = Path(__file__).parent.parent / "scripts" / "limit_to_master_map.csv"
    mapping = {}
    try:
        if mapping_fn.exists():
            with mapping_fn.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sv = (row.get("system_version") or "").strip()
                    ag = (row.get("age_group") or "").strip()
                    lim = (row.get("limit_income_code") or "").strip()
                    mast = (row.get("master_income_code") or "").strip()
                    if sv and ag and lim and mast:
                        mapping.setdefault((sv, ag), {})[lim] = mast
    except Exception:
        # on any parse error, treat as empty mapping (fall back to previous behavior)
        return {}
    return mapping


def resolve_master_code_via_map(system_version: str, age_group: str, limit_income_code: str):
    """Return master_income_code if an explicit mapping exists, otherwise None.

    This function does NOT attempt fuzzy or label-based guessing — it only
    consults the explicit CSV mapping file.
    """
    mapping = _load_limit_to_master_map()
    return mapping.get((system_version, age_group), {}).get(limit_income_code)

# 制度選択定数
SYSTEM_VERSIONS = ["R7", "R8", "R9"]

# 各制度ごとの income_code 候補（limit_table.csv の income_code と一致）
INCOME_CODES = {
    "R7": ["1", "2", "3", "4", "5", "6", "7"],
    "R8": ["1", "2", "3", "4", "5", "6", "7"],
    "R9": [
        "R9_1650_PLUS",
        "R9_1410_1650",
        "R9_1160_1410",
        "R9_1040_1160",
        "R9_950_1040",
        "R9_770_950",
        "R9_650_770",
        "R9_510_650",
        "R9_370_510",
        "R9_260_370",
        "R9_200_260",
        "R9_UNDER_200",
        "R9_EXEMPT_UNDER70",
        "R9_EXEMPT_OVER70",
        "R9_LOW_INCOME_OVER70",
    ],
}

# 年齢区分定義（キーは limit_table.csv と一致させる）
AGE_GROUPS = {
    "under70": "70歳未満",
    "over70": "70歳以上",
}


def _prompt(prompt: str, default: Optional[str] = None) -> str:
    s = input(prompt)
    if s is None:
        return "" if default is None else default
    s = s.strip()
    if s == "" and default is not None:
        return default
    return s


def main() -> None:
    print("高額療養費シミュレーター（簡易CLI）")

    # 制度: 番号選択式
    print("制度を選択してください:")
    for idx, sv in enumerate(SYSTEM_VERSIONS, start=1):
        print(f"  {idx}. {sv}")
    while True:
        sel = _prompt("番号を入力してください: ")
        try:
            n = int(sel)
            if 1 <= n <= len(SYSTEM_VERSIONS):
                system_version = SYSTEM_VERSIONS[n - 1]
                break
        except Exception:
            pass
        print("有効な番号を入力してください。")

    # 年齢区分: 選択式（表示は日本語、内部キーは AGE_GROUPS のキー）
    print("年齢区分を選択してください:")
    age_keys = list(AGE_GROUPS.keys())
    for idx, ag_key in enumerate(age_keys, start=1):
        print(f"  {idx}. {AGE_GROUPS.get(ag_key, ag_key)}")
    while True:
        sel = _prompt("番号を入力してください: ")
        try:
            n = int(sel)
            if 1 <= n <= len(age_keys):
                age_group = age_keys[n - 1]
                break
        except Exception:
            pass
        print("有効な番号を入力してください。")

    # 所得区分: limit_table.csv から system_version と age_group に該当する income_code を抽出
    data_dir = Path(__file__).parent.parent / "data"
    limit_table_path = data_dir / "limit_table.csv"
    income_entries = []  # list of (income_code, income_label)
    try:
        with limit_table_path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = [row for row in reader if row.get("system_version") == system_version and row.get("age_group") == age_group]

        # If age_group is over70, present options in this order: ア -> イ -> ウ -> 一般 -> 非課税
        if age_group == "over70":
            groups = {
                "A": [],
                "I": [],
                "U": [],
                "G": [],
                "L": [],
                "other": [],
            }

            for row in rows:
                code = row.get("income_code")
                label = row.get("income_label") or ""
                if not code:
                    continue

                # Primary classification by code letters
                if "A" in code:
                    groups["A"].append((code, label, "A"))
                    continue
                if "I" in code:
                    groups["I"].append((code, label, "I"))
                    continue
                if "U" in code:
                    groups["U"].append((code, label, "U"))
                    continue
                if code in ("G",):
                    groups["G"].append((code, label, "G"))
                    continue
                if code in ("L1", "L2"):
                    groups["L"].append((code, label, "L"))
                    continue

                # Secondary classification by label (for numeric or R9_* codes)
                if "区分ア" in label:
                    groups["A"].append((code, label, "A"))
                elif "区分イ" in label:
                    groups["I"].append((code, label, "I"))
                elif "区分ウ" in label:
                    groups["U"].append((code, label, "U"))
                elif "非課税" in label or "一定所得以下" in label or "低所得" in label:
                    groups["L"].append((code, label, "L"))
                else:
                    # treat as general if not classified
                    groups["G"].append((code, label, "G"))

            # Build final ordered list: A, I, U, G, L, then any other leftovers (dedupe preserving order)
            final = []
            seen = set()
            for key in ("A", "I", "U", "G", "L", "other"):
                for code_label in groups.get(key, []):
                    if code_label[0] not in seen:
                        final.append(code_label)
                        seen.add(code_label[0])

            income_entries = final
            # Supplement missing 現役並み (ア/イ) entries from under70 rows if CSV lacks them
            # We try to find income_code '1' (区分ア) and '2' (区分イ) from the under70 rows
            # for the same system_version and insert them in order if found and not already present.
            need_codes = [("A", "1"), ("I", "2")]
            # build a set of existing codes
            existing_codes = {c for (c, *_) in income_entries}
            if rows is not None:
                # read under70 rows for same system_version
                under_rows = [r for r in rows if False]  # placeholder
                with limit_table_path.open(encoding="utf-8") as uf:
                    ureader = csv.DictReader(uf)
                    under_rows = [r for r in ureader if r.get("system_version") == system_version and r.get("age_group") == "under70"]

                # Insert at the front of the A or I group position if missing
                insert_at = 0
                for grp, code_needed in need_codes:
                    if code_needed not in existing_codes:
                        # find matching under70 row
                        found = None
                        for ur in under_rows:
                            if ur.get("income_code") == code_needed:
                                found = ur
                                break
                        if found:
                            label = found.get("income_label") or ""
                            # insert preserving order: A then I at the beginning
                            income_entries.insert(insert_at, (code_needed, label, grp))
                            insert_at += 1
        else:
            # For under70 (or other age groups), use all matching rows in stable order
            seen = set()
            for row in rows:
                code = row.get("income_code")
                label = row.get("income_label") or ""
                if code and code not in seen:
                    income_entries.append((code, label))
                    seen.add(code)
    except Exception:
        # fallback: use INCOME_CODES constant (no labels)
        income_entries = [(c, "") for c in INCOME_CODES.get(system_version, [])]

    if not income_entries:
        print("該当する所得区分が見つかりません。プログラムを終了します。")
        return

    # Display: prefer showing income_code; use income_category_master.csv for labels
    # income_entries may be (code,label) or (code,label,group)
    # Map system_version to the master CSV `system_base` values
    system_base = "R9plus" if system_version == "R9" else "R7R8"

    print("所得区分を選択してください:")
    for idx, entry in enumerate(income_entries, start=1):
        code = entry[0]
        label = entry[1] if len(entry) > 1 else ""
        # Prefer the master CSV display label via explicit mapping; fall back to the
        # label from limit_table.csv when no mapping or master entry exists.
        try:
            master_code = resolve_master_code_via_map(system_version, age_group, code)
            if master_code:
                info = get_income_display_info(system_base, age_group, master_code)
            else:
                # no mapping — try the previous behavior (may raise)
                info = get_income_display_info(system_base, age_group, code)
            disp = info.get("display_name") or label
        except Exception:
            disp = label

        if disp:
            print(f"  {idx}. {code} （{disp}）")
        else:
            print(f"  {idx}. {code}")

    while True:
        sel = _prompt("番号を入力してください: ")
        try:
            n = int(sel)
            if 1 <= n <= len(income_entries):
                chosen = income_entries[n - 1]
                income_code = chosen[0]
                chosen_label = chosen[1] if len(chosen) > 1 else ""
                chosen_group = chosen[2] if len(chosen) > 2 else None
                # fetch display info for the chosen code; do not alter calculation inputs
                try:
                    master_code = resolve_master_code_via_map(system_version, age_group, income_code)
                    if master_code:
                        chosen_info = get_income_display_info(system_base, age_group, master_code)
                    else:
                        chosen_info = get_income_display_info(system_base, age_group, income_code)
                    chosen_display = chosen_info.get("display_name")
                    chosen_description = chosen_info.get("description")
                except Exception:
                    chosen_display = chosen_label
                    chosen_description = ""
                break
        except Exception:
            pass
        print("有効な番号を入力してください。")

    # Show selected display name and description (UI only — does not affect calculation)
    # `chosen_display` / `chosen_description` were retrieved from income_category_master.csv
    try:
        if chosen_display and (chosen_display.strip() != ""):
            print(f"\n{chosen_display}")
        if chosen_description and chosen_description.strip() != "":
            # lightweight supplemental note; do not modify the description text itself
            print(f"※ {chosen_description}")
    except NameError:
        # defensive: if chosen_display/description not set for some reason, skip showing
        pass

    # 薬剤ID / 薬剤名
    drug_id = _prompt("薬剤ID を入力してください (drug_id): ")
    drug_name = _prompt("薬剤名を入力してください: ")

    # 投与間隔の候補制御
    # デュピクセントのみ2週/4週、その他は4週のみ
    dupixent_ids = {"dupixent_300"}
    if drug_id in dupixent_ids or "デュピクセント" in drug_name:
        interval_options = [2, 4]
    else:
        interval_options = [4]

    print("投与間隔を選択してください:")
    for idx, weeks in enumerate(interval_options, start=1):
        print(f"  {idx}. {weeks}週ごと")
    while True:
        sel = _prompt("番号を入力してください: ")
        try:
            n = int(sel)
            if 1 <= n <= len(interval_options):
                basic_interval_weeks = interval_options[n - 1]
                break
        except Exception:
            pass
        print("有効な番号を入力してください。")

    # 初回処方本数の決定
    # デュピクセントを2週毎かつ初回ローディングは2本で自動確定
    # それ以外は drug_price.csv の initial_units を参照（なければ units_per_12w を代替）
    data_dir = Path(__file__).parent.parent / "data"
    drug_price_path = data_dir / "drug_price.csv"
    initial_units = None
    units_per_12w = None
    with drug_price_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("drug_id") == drug_id:
                try:
                    units_per_12w = int(row.get("units_per_12w") or 0)
                except Exception:
                    units_per_12w = None
                # initial_units may not exist in CSV; try to read if present
                if "initial_units" in row:
                    try:
                        initial_units = int(row.get("initial_units") or 0)
                    except Exception:
                        initial_units = None
                break

    if basic_interval_weeks == 2 and (drug_id in dupixent_ids or "デュピクセント" in drug_name):
        first_units = 2
        loading_note = "初回ローディング（2本）を自動適用します。"
    else:
        # use initial_units from CSV when available, otherwise fallback to units_per_12w
        first_units = initial_units if initial_units and initial_units > 0 else (units_per_12w or 0)
        loading_note = f"初回処方本数はデータに基づき {first_units} 本です（入力不可）。"

    print(loading_note)

    # 投与間隔（週）
    # 開始日入力（YYYY-MM-DD）
    while True:
        start_date_s = _prompt("開始日を YYYY-MM-DD 形式で入力してください (1回目投与日): ")
        try:
            start_date = datetime.strptime(start_date_s, "%Y-%m-%d").date()
            break
        except Exception:
            print("日付の形式が不正です。YYYY-MM-DD 形式で入力してください。")

    # 2回目の処方本数（整数）
    while True:
        second_units_s = _prompt("2回目の処方本数を入力してください（整数）: ")
        try:
            second_units = int(second_units_s)
            if second_units <= 0:
                raise ValueError()
            break
        except Exception:
            print("正の整数を入力してください。")

    # 3回目の処方本数（整数）
    while True:
        third_units_s = _prompt("3回目の処方本数を入力してください（整数）: ")
        try:
            third_units = int(third_units_s)
            if third_units <= 0:
                raise ValueError()
            break
        except Exception:
            print("正の整数を入力してください。")

    # prescription_interval_weeks is the basic interval selected earlier
    prescription_interval_weeks = basic_interval_weeks

    # Build dosing event list (Step1: only 初回〜3回目を扱う)
    events = []
    # Event 1: 初回投与日はユーザ入力の開始日
    event1_date = start_date
    events.append({"event": 1, "date": event1_date.isoformat(), "units": first_units})

    # Event 2: 初回 + 28日
    event2_date = event1_date + timedelta(days=28)
    events.append({"event": 2, "date": event2_date.isoformat(), "units": second_units})

    # Event 3: 2回目 + 28日
    event3_date = event2_date + timedelta(days=28)
    events.append({"event": 3, "date": event3_date.isoformat(), "units": third_units})

    # Display the generated events for user confirmation
    print("\n--- 生成された投与イベント ---")
    for ev in events:
        print(f"event {ev['event']}: {ev['date']} ／ 本数 {ev['units']}")

    # 実行
    # If user selected a 現役並み (ア/イ/ウ) while choosing 70歳以上, per rules the calculation
    # uses the same limits as 70歳未満. Therefore, pass age_group='under70' to the calculator
    # when the selected income is classified as A/I/U.
    calc_age_group = age_group
    if age_group == "over70" and chosen_group in ("A", "I", "U"):
        calc_age_group = "under70"

    try:
        simulation = simulate_selected_system(
            system_version=system_version,
            income_code=income_code,
            age_group=calc_age_group,
            drug_id=drug_id,
            prescription_interval_weeks=prescription_interval_weeks,
        )
    except Exception as e:
        print(f"シミュレーション中にエラーが発生しました: {e}")
        return

    try:
        explanation = generate_patient_explanation(
            system_version=system_version,
            income_code=income_code,
            age_group=calc_age_group,
            drug_name=drug_name,
            drug_id=drug_id,
            prescription_interval_weeks=prescription_interval_weeks,
        )
    except Exception as e:
        print(f"説明文生成中にエラーが発生しました: {e}")
        return

    # 結果表示
    annual_cost = int(simulation.get("annual_cost", 0))
    monthly_average = int(simulation.get("monthly_average_cost", 0))
    many_applied = bool(simulation.get("is_many_times_applied", False))

    print("\n--- シミュレーション結果 ---")
    print(f"年間の自己負担合計: {annual_cost:,} 円")
    print(f"月平均の自己負担: {monthly_average:,} 円")
    print(f"多数回該当: {'該当する' if many_applied else '該当しない'}")

    print("\n--- 患者向け説明 ---")
    print(explanation)


if __name__ == "__main__":
    main()
