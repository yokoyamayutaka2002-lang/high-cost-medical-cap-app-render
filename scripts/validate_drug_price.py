#!/usr/bin/env python3
import sys
import os
import json
import csv
from pathlib import Path
try:
    import yaml
except Exception:
    yaml = None

REPORT_DIR = Path('reports')


def rec(t, file, row_or_key, msg):
    return {'type': t, 'file': file, 'row_or_key': row_or_key, 'message': msg}


def load_rules(p: Path):
    if not p.exists():
        return {}
    if yaml is None:
        raise RuntimeError('PyYAML required to read validator_rules.yaml')
    return yaml.safe_load(p.read_text(encoding='utf8'))


def read_csv(p: Path):
    out = []
    if not p.exists():
        return out
    with p.open(encoding='utf8') as f:
        r = csv.DictReader(f)
        for row in r:
            out.append(row)
    return out


def main():
    if len(sys.argv) < 4:
        print('Usage: validate_drug_price.py current.csv previous.csv validator_rules.yaml')
        return 1

    current_p = Path(sys.argv[1])
    prev_p = Path(sys.argv[2])
    rules_p = Path(sys.argv[3])
    REPORT_DIR.mkdir(exist_ok=True)
    out_path = REPORT_DIR / 'validate_drug_price.json'
    issues = []

    rules = load_rules(rules_p) or {}
    pct_warn = rules.get('price_change_threshold', {}).get('warn')
    pct_err = rules.get('price_change_threshold', {}).get('error')
    if pct_warn is None or pct_err is None:
        issues.append(rec('MISSING_RULE', str(rules_p), 'price_change_threshold', 'Missing warn/error thresholds in validator_rules.yaml'))

    # read current and previous
    curr = read_csv(current_p)
    prev = read_csv(prev_p)

    if not curr:
        issues.append(rec('FILE_EMPTY', str(current_p), '', 'current CSV is empty or missing'))
        report = {'status': 'fail', 'errors': issues, 'summary': {'error_count': len(issues), 'warning_count': 0}}
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        return 1

    # schema match check
    with current_p.open(encoding='utf8') as f:
        cur_fields = csv.DictReader(f).fieldnames or []
    with prev_p.open(encoding='utf8') if prev_p.exists() else open(os.devnull) as f2:
        try:
            prev_fields = csv.DictReader(f2).fieldnames or []
        except Exception:
            prev_fields = []

    if prev and set(cur_fields) != set(prev_fields):
        issues.append(rec('SCHEMA_MISMATCH', str(current_p), '', 'Schema does not match previous CSV'))

    # build prev map
    prev_map = { r.get('drug_id'): r for r in prev }

    # load master map to validate drug_id existence
    master_path = Path('data') / 'master_id_map.csv'
    master_rows = []
    if master_path.exists():
        with master_path.open(encoding='utf8') as f:
            master_rows = [r for r in csv.DictReader(f)]
    master_ids = { r.get('drug_id') for r in master_rows }

    # check each current row
    for idx, row in enumerate(curr, start=2):
        drug = row.get('drug_id')
        if not drug:
            issues.append(rec('UNKNOWN_DRUG_ID', str(current_p), idx, 'drug_id missing'))
            continue
        # existence in master
        if master_rows and drug not in master_ids:
            issues.append(rec('UNKNOWN_DRUG_ID', str(current_p), drug, 'drug_id not found in master_id_map.csv'))

        # weeks_per_unit > 0
        wpu_raw = (row.get('weeks_per_unit') or '').strip()
        try:
            wpu = float(wpu_raw)
            if wpu <= 0:
                issues.append(rec('WEEKS_PER_UNIT_INVALID', str(current_p), idx, f'weeks_per_unit not > 0: {wpu_raw}'))
        except Exception:
            issues.append(rec('WEEKS_PER_UNIT_INVALID', str(current_p), idx, f'weeks_per_unit invalid: {wpu_raw}'))

        # price_per_unit >= 0
        ppu_raw = (row.get('price_per_unit') or '').strip()
        try:
            ppu = float(ppu_raw)
            if ppu < 0:
                issues.append(rec('PRICE_PER_UNIT_INVALID', str(current_p), idx, f'price_per_unit negative: {ppu_raw}'))
        except Exception:
            issues.append(rec('PRICE_PER_UNIT_INVALID', str(current_p), idx, f'price_per_unit invalid: {ppu_raw}'))

        # compare with prev
        if drug in prev_map:
            prev_row = prev_map[drug]
            prev_price_raw = (prev_row.get('price_per_unit') or '').strip()
            try:
                prev_price = float(prev_price_raw)
                if prev_price > 0:
                    change = abs(ppu - prev_price) / prev_price
                    if pct_err is not None and change >= float(pct_err):
                        issues.append(rec('PRICE_CHANGE_EXCEEDS_LIMIT', str(current_p), drug, f'Price change {change:.2%} >= error threshold {pct_err:.0%}'))
                    elif pct_warn is not None and change >= float(pct_warn):
                        issues.append(rec('PRICE_CHANGE_WARNING', str(current_p), drug, f'Price change {change:.2%} >= warn threshold {pct_warn:.0%}'))
            except Exception:
                # can't parse prev price
                issues.append(rec('PRICE_PREV_PARSE_ERROR', str(current_p), drug, f'Previous price invalid: {prev_price_raw}'))

    status = 'ok' if not any(i for i in issues if i['type'] in ('SCHEMA_MISMATCH','UNKNOWN_DRUG_ID','WEEKS_PER_UNIT_INVALID','PRICE_PER_UNIT_INVALID','PRICE_CHANGE_EXCEEDS_LIMIT')) else 'fail'
    error_count = len([i for i in issues if i['type'] in ('SCHEMA_MISMATCH','UNKNOWN_DRUG_ID','WEEKS_PER_UNIT_INVALID','PRICE_PER_UNIT_INVALID','PRICE_CHANGE_EXCEEDS_LIMIT')])
    warning_count = len(issues) - error_count

    report = {'status': status, 'errors': issues, 'summary': {'error_count': error_count, 'warning_count': warning_count}}
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')

    if status == 'fail':
        print(f'Drug price validation failed: {error_count} errors, {warning_count} warnings -> {out_path}', file=sys.stderr)
        return 1

    print(f'Drug price validation passed: {current_p} -> {out_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
