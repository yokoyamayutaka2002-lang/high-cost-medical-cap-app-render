import pandas as pd
import os
import sys
import unicodedata
import re

ROOT = os.path.dirname(os.path.dirname(__file__))
SOURCE_DIR = os.path.join(ROOT, 'data', 'source_excel')
OUT_DIR = os.path.join(ROOT, 'data')

_candidate_inhaled = os.path.join(SOURCE_DIR, 'mhlw_drug_price_inhaled_2025-04.xlsx')
_candidate_topical = os.path.join(SOURCE_DIR, 'mhlw_drug_price_topical_2025-04.xlsx')

# Prefer the explicit inhaled filename; if missing, try topical or any file containing 'topical'/'inhal'
def find_inhaled_file():
    # exact candidates first
    for p in (_candidate_inhaled, _candidate_topical):
        if os.path.exists(p):
            return p
    # scan directory for topical/inhal keywords (normalize filenames)
    for fn in os.listdir(SOURCE_DIR):
        norm = unicodedata.normalize('NFKC', fn).lower()
        if 'topical' in norm or 'inhal' in norm:
            return os.path.join(SOURCE_DIR, fn)
    return _candidate_inhaled

INHALED_XLSX = find_inhaled_file()
ORAL_XLSX = os.path.join(SOURCE_DIR, 'mhlw_drug_price_oral_2025-04.xlsx')
INHALED_MASTER = os.path.join(OUT_DIR, 'inhaled_drug_master_exact.csv')
DOSING_MASTER = os.path.join(OUT_DIR, 'dosing_master.csv')

OUT_INHALED = os.path.join(OUT_DIR, 'inhaled_drug_price_2025-04.csv')
OUT_ORAL = os.path.join(OUT_DIR, 'oral_drug_price_2025-04.csv')

PRICE_COL_CANDIDATES = ['薬価', '薬価（円）', 'price', 'price_yen']
NAME_COL_CANDIDATES = ['品名', '薬品名', '薬剤名', '成分名', '名称']


def find_column(columns, candidates):
    for c in candidates:
        if c in columns:
            return c
    return None


def load_excel(path):
    if not os.path.exists(path):
        return None
    try:
        return pd.read_excel(path)
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return None


def norm_price(x):
    if pd.isna(x):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace(',', '').strip()
    # drop non-numeric suffixes
    s = ''.join(ch for ch in s if (ch.isdigit() or ch == '.' or ch == '-'))
    try:
        return float(s)
    except:
        return None


def normalize_text(s):
    """Normalize text for comparison: NFKC and remove spaces (including full-width)."""
    if pd.isna(s):
        return ''
    t = str(s)
    t = unicodedata.normalize('NFKC', t)
    t = t.replace(' ', '').replace('\u3000', '')
    return t


def build_inhaled():
    print('Processing inhaled...')
    if not os.path.exists(INHALED_MASTER):
        print(f'Missing inhaled master: {INHALED_MASTER}')
        return
    df_master = pd.read_csv(INHALED_MASTER)
    df_excel = load_excel(INHALED_XLSX)
    if df_excel is None:
        print('Inhaled Excel not found or unreadable; skipping inhaled output.')
        return
    ex_cols = list(df_excel.columns)
    name_col = find_column(ex_cols, NAME_COL_CANDIDATES)
    price_col = find_column(ex_cols, PRICE_COL_CANDIDATES)
    if name_col is None or price_col is None:
        print('Could not find expected name/price columns in inhaled Excel.')
        print('Excel columns:', ex_cols)
        return
    # Use normalized substring-contains matching (similar to oral) for inhaled
    df_excel_sub = df_excel[[name_col, price_col]].rename(columns={name_col: '品名', price_col: '薬価'}).copy()
    df_excel_sub['norm_name'] = df_excel_sub['品名'].apply(normalize_text)

    # helper to parse package units from a name string (handles full-width digits via NFKC)
    def parse_package_units(name):
        if pd.isna(name) or not str(name).strip():
            return None
        n = normalize_text(name)
        # look for patterns like '60吸入', '60吸入用', '30吸入用', '30カプセル'
        m = re.search(r"(\d+)[^0-9\uFF10-\uFF19]*吸入", n)
        if m:
            try:
                return int(m.group(1))
            except:
                return None
        m2 = re.search(r"(\d+)[^0-9\uFF10-\uFF19]*(吸入用|カプセル|錠|カプセル用)", n)
        if m2:
            try:
                return int(m2.group(1))
            except:
                return None
        # fallback: any digits
        m3 = re.search(r"(\d+)", n)
        if m3:
            try:
                return int(m3.group(1))
            except:
                return None
        return None

    rows_out = []
    matched_excel_indices = set()
    burden_rate = 0.3
    for _, row in df_master.iterrows():
        master_name = row.get('exact_item_name', '')
        master_norm = normalize_text(master_name)
        master_base = re.sub(r'（.*?）|\(.*?\)', '', str(master_name))
        master_norm_base = normalize_text(master_base)
        # also prepare a base name with parenthetical suffix removed, to match entries
        master_base = re.sub(r'（.*?）|\(.*?\)', '', str(master_name))
        master_norm_base = normalize_text(master_base)
        pkg_price = None
        matched_idx = None
        matched_src_name = None
        if master_norm:
            mask = df_excel_sub['norm_name'].str.contains(master_norm, na=False)
            if not mask.any() and master_norm_base and master_norm_base != master_norm:
                # try base-name match if full master name (with parentheses) doesn't match
                mask = df_excel_sub['norm_name'].str.contains(master_norm_base, na=False)
            if mask.any():
                first_idx = df_excel_sub[mask].index[0]
                matched_excel_indices.add(first_idx)
                matched_idx = first_idx
                matched_src_name = df_excel_sub.at[first_idx, '品名']
                pkg_price = norm_price(df_excel_sub.at[first_idx, '薬価'])

        # Build audit row
        package_units = None
        per_unit_price = None
        daily_inhalations = None
        daily_price = None
        weekly_price = None
        note = ''

        try:
            daily_inhalations = int(row.get('daily_inhalations') or 0)
        except:
            daily_inhalations = 0

        # try parsing package units from price row name first, then master name
        if matched_idx is not None:
            package_units = parse_package_units(df_excel_sub.at[matched_idx, '品名'])
        if package_units is None:
            package_units = parse_package_units(master_name)

        if pkg_price is None:
            note = 'missing_price'
        else:
            if package_units and package_units > 0:
                per_unit_price = pkg_price / float(package_units)
            else:
                # cannot parse package size – assume price might be per-unit but mark for review
                per_unit_price = pkg_price
                note = note + (';assume_per_unit' if note else 'assume_per_unit')

        if per_unit_price is not None:
            daily_price = per_unit_price * float(daily_inhalations or 0)
            weekly_price = daily_price * 7.0 * burden_rate

        weekly_display = int(round(weekly_price)) if weekly_price is not None else None

        rows_out.append({
            'exact_item_name': master_name,
            'class': row.get('class') if 'class' in row else row.get('classification',''),
            'package_price_yen': pkg_price,
            'package_units': package_units,
            'per_unit_price': per_unit_price,
            'daily_inhalations': daily_inhalations,
            'daily_price': daily_price,
            'weekly_price_float': weekly_price,
            'weekly_price_display': weekly_display,
            'matched_price_name': matched_src_name,
            'note': note
        })

    out_df = pd.DataFrame(rows_out)
    # Provide a `unit_price_yen` column for compatibility with the webapp loader
    out_df['unit_price_yen'] = out_df['package_price_yen']
    out_df.to_csv(OUT_INHALED, index=False)
    audit_path = os.path.join(OUT_DIR, 'inhaled_price_audit.csv')
    out_df.to_csv(audit_path, index=False)
    missing = out_df['package_price_yen'].isna().sum()
    print(f'Wrote {OUT_INHALED} and audit {audit_path}; rows={len(out_df)}; missing_price={missing}')
    if missing:
        print('Sample missing price rows:')
        print(out_df[out_df['package_price_yen'].isna()].head(10).to_string(index=False))


def build_oral():
    print('Processing oral...')
    if not os.path.exists(DOSING_MASTER):
        print(f'Missing dosing master: {DOSING_MASTER}')
        return
    df_master = pd.read_csv(DOSING_MASTER)
    df_excel = load_excel(ORAL_XLSX)
    if df_excel is None:
        print('Oral Excel not found or unreadable; skipping oral output.')
        return
    ex_cols = list(df_excel.columns)
    name_col = find_column(ex_cols, NAME_COL_CANDIDATES)
    price_col = find_column(ex_cols, PRICE_COL_CANDIDATES + ['薬価'])
    if name_col is None or price_col is None:
        print('Could not find expected name/price columns in oral Excel.')
        print('Excel columns:', ex_cols)
        return
    # For ORAL: allow normalized substring matching (contains) per request.
    # Normalization: NFKC (full/half width) and remove spaces (including full-width space).
    def normalize_text(s):
        if pd.isna(s):
            return ''
        t = str(s)
        t = unicodedata.normalize('NFKC', t)
        t = t.replace(' ', '').replace('\u3000', '')
        return t

    df_excel_sub = df_excel[[name_col, price_col]].rename(columns={name_col: '品名', price_col: '薬価'}).copy()
    df_excel_sub['norm_name'] = df_excel_sub['品名'].apply(normalize_text)

    def parse_package_units(name):
        if pd.isna(name) or not str(name).strip():
            return None
        n = normalize_text(name)
        m = re.search(r"(\d+)[^0-9\uFF10-\uFF19]*錠", n)
        if m:
            try:
                return int(m.group(1))
            except:
                return None
        m2 = re.search(r"(\d+)[^0-9\uFF10-\uFF19]*(錠|包|カプセル|吸入)", n)
        if m2:
            try:
                return int(m2.group(1))
            except:
                return None
        m3 = re.search(r"(\d+)", n)
        if m3:
            try:
                return int(m3.group(1))
            except:
                return None
        return None

    rows_out = []
    matched_excel_indices = set()
    burden_rate = 0.3
    for _, row in df_master.iterrows():
        master_name = row.get('drug_name', '')
        master_norm = normalize_text(master_name)
        pkg_price = None
        matched_idx = None
        matched_src_name = None
        if master_norm:
            mask = df_excel_sub['norm_name'].str.contains(master_norm, na=False)
            if not mask.any() and master_norm_base and master_norm_base != master_norm:
                mask = df_excel_sub['norm_name'].str.contains(master_norm_base, na=False)
            if mask.any():
                first_idx = df_excel_sub[mask].index[0]
                matched_excel_indices.add(first_idx)
                matched_idx = first_idx
                matched_src_name = df_excel_sub.at[first_idx, '品名']
                pkg_price = norm_price(df_excel_sub.at[first_idx, '薬価'])

        package_units = None
        per_unit_price = None
        daily_dose = None
        daily_price = None
        weekly_price = None
        note = ''

        try:
            # dosing_master may have columns like 'daily_inhalations' or 'daily_dose'
            if 'daily_inhalations' in row:
                daily_dose = int(row.get('daily_inhalations') or 0)
            else:
                daily_dose = int(row.get('daily_dose') or row.get('dose_per_day') or 0)
        except:
            daily_dose = 0

        if matched_idx is not None:
            package_units = parse_package_units(df_excel_sub.at[matched_idx, '品名'])
        if package_units is None:
            package_units = parse_package_units(master_name)

        if pkg_price is None:
            note = 'missing_price'
        else:
            if package_units and package_units > 0:
                per_unit_price = pkg_price / float(package_units)
            else:
                per_unit_price = pkg_price
                note = note + (';assume_per_unit' if note else 'assume_per_unit')

        if per_unit_price is not None:
            daily_price = per_unit_price * float(daily_dose or 0)
            weekly_price = daily_price * 7.0 * burden_rate

        weekly_display = int(round(weekly_price)) if weekly_price is not None else None

        rows_out.append({
            'drug_name': master_name,
            'package_price_yen': pkg_price,
            'package_units': package_units,
            'per_unit_price': per_unit_price,
            'daily_dose': daily_dose,
            'daily_price': daily_price,
            'weekly_price_float': weekly_price,
            'weekly_price_display': weekly_display,
            'matched_price_name': matched_src_name,
            'note': note
        })

    out_df = pd.DataFrame(rows_out)
    # Provide a `unit_price_yen` column for compatibility with the webapp loader
    out_df['unit_price_yen'] = out_df['package_price_yen']
    out_df.to_csv(OUT_ORAL, index=False)
    audit_path = os.path.join(OUT_DIR, 'oral_price_audit.csv')
    out_df.to_csv(audit_path, index=False)

    # produce unmatched master / excel reports as before for traceability
    unmatched_master = out_df[out_df['package_price_yen'].isna()].copy()
    unmatched_master['reason'] = 'not found in MHLW Excel'
    unmatched_master[['drug_name','reason']].to_csv(os.path.join(OUT_DIR, 'oral_unmatched_master.csv'), index=False)

    df_excel_sub['matched'] = df_excel_sub.index.map(lambda i: i in matched_excel_indices)
    unmatched_excel = df_excel_sub[~df_excel_sub['matched']].copy()
    unmatched_excel = unmatched_excel.rename(columns={'品名':'excel_品名'})
    unmatched_excel['reason'] = 'not in dosing_master.csv'
    unmatched_excel[['excel_品名','薬価','reason']].to_csv(os.path.join(OUT_DIR, 'oral_unmatched_excel.csv'), index=False)

    matched_count = out_df['package_price_yen'].notna().sum()
    unmatched_master_count = len(unmatched_master)
    unmatched_excel_count = len(unmatched_excel)

    print(f'Wrote {OUT_ORAL} and audit {audit_path}; rows={len(out_df)}; matched_rows={matched_count}; unmatched_master={unmatched_master_count}; unmatched_excel={unmatched_excel_count}')


if __name__ == '__main__':
    build_inhaled()
    build_oral()
    print('Done.')
