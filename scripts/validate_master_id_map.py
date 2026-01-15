#!/usr/bin/env python3
import sys
import os
import json
import csv
from pathlib import Path

REPORT_DIR = Path('reports')


def rec(t, file, row_or_key, msg):
    return {'type': t, 'file': file, 'row_or_key': row_or_key, 'message': msg}


def read_csv_map(p: Path, key_col: str = 'canonical_key'):
    rows = []
    if not p.exists():
        return rows
    with p.open(encoding='utf8') as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows


def main():
    if len(sys.argv) < 3:
        print('Usage: validate_master_id_map.py data/master_id_map.csv history/master_id_map_latest.csv')
        return 1

    current_path = Path(sys.argv[1])
    previous_path = Path(sys.argv[2])
    REPORT_DIR.mkdir(exist_ok=True)
    out_path = REPORT_DIR / 'validate_master_id_map.json'
    issues = []

    if not current_path.exists():
        issues.append(rec('FILE_NOT_FOUND', str(current_path), '', 'master_id_map.csv not found'))
        out = {'status': 'fail', 'errors': issues, 'summary': {'error_count': len(issues), 'warning_count': 0}}
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf8')
        return 1

    current = read_csv_map(current_path)
    prev = read_csv_map(previous_path) if previous_path.exists() else []

    # uniqueness checks
    seen_canonical = {}
    seen_drug = {}
    for idx, row in enumerate(current, start=2):
        key = row.get('canonical_key')
        drug = row.get('drug_id')
        if not key:
            issues.append(rec('MISSING_CANONICAL_KEY', str(current_path), idx, 'canonical_key missing'))
            continue
        if key in seen_canonical:
            issues.append(rec('DUPLICATE_CANONICAL_KEY', str(current_path), key, f'canonical_key duplicated at row {idx}'))
        seen_canonical[key] = idx
        if not drug:
            issues.append(rec('MISSING_DRUG_ID', str(current_path), key, 'drug_id missing'))
            continue
        if drug in seen_drug:
            issues.append(rec('DUPLICATE_DRUG_ID', str(current_path), drug, f'drug_id duplicated at row {idx}'))
        seen_drug[drug] = key

    # check against previous for identity preservation
    prev_map_by_drug = { r.get('drug_id'): r for r in prev }
    prev_keys_by_drug = { r.get('drug_id'): r.get('canonical_key') for r in prev }
    prev_set = set([r.get('drug_id') for r in prev if r.get('drug_id')])

    for row in current:
        drug = row.get('drug_id')
        key = row.get('canonical_key')
        status = (row.get('status') or '').strip().lower()

        # if appeared before, canonical_key must be unchanged
        if drug in prev_keys_by_drug:
            prev_key = prev_keys_by_drug.get(drug)
            if prev_key and prev_key != key:
                issues.append(rec('DRUG_ID_MUTATION', str(current_path), drug, f'drug_id {drug} has changed canonical_key from {prev_key} to {key}'))

        # new additions must not be status=active
        if drug not in prev_set:
            if status == 'active':
                issues.append(rec('INVALID_STATUS_TRANSITION', str(current_path), drug, 'Newly added drug_id must not be status=active; use provisional'))

    # retired drug_id reappearance: if prev had status retired and current contains it -> invalid
    prev_retired = { r.get('drug_id') for r in prev if (r.get('status') or '').strip().lower() == 'retired' }
    for row in current:
        if row.get('drug_id') in prev_retired:
            issues.append(rec('INVALID_STATUS_TRANSITION', str(current_path), row.get('drug_id'), 'Previously retired drug_id reappears in current mapping'))

    status = 'ok' if not issues else 'fail'
    report = {'status': status, 'errors': issues, 'summary': {'error_count': len(issues), 'warning_count': 0}}
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')

    if issues:
        print(f'Master ID map validation failed: {len(issues)} issues -> {out_path}', file=sys.stderr)
        return 1

    print(f'Master ID map validation passed: {current_path} -> {out_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
