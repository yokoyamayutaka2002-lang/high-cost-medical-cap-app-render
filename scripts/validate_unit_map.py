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


def load_rules(rpath: Path):
    if not rpath.exists():
        return None
    if yaml is None:
        raise RuntimeError('PyYAML is required to read validator_rules.yaml')
    return yaml.safe_load(rpath.read_text(encoding='utf8'))


def main():
    if len(sys.argv) < 2:
        print('Usage: validate_unit_map.py data/unit_map.csv')
        return 1
    unit_map_path = Path(sys.argv[1])
    REPORT_DIR.mkdir(exist_ok=True)
    out_path = REPORT_DIR / 'validate_unit_map.json'
    issues = []

    if not unit_map_path.exists():
        issues.append(rec('FILE_NOT_FOUND', str(unit_map_path), '', 'unit_map.csv not found'))
        report = {'status': 'fail', 'errors': issues, 'summary': {'error_count': len(issues), 'warning_count': 0}}
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        return 1

    # load rules
    rules_path = Path('data') / 'validator_rules.yaml'
    rules = load_rules(rules_path) or {}
    allowed_price_basis = rules.get('allowed_price_basis') if isinstance(rules, dict) else None
    if allowed_price_basis is None:
        issues.append(rec('MISSING_RULE', str(rules_path), 'allowed_price_basis', 'validator_rules.yaml missing allowed_price_basis'))

    required_cols = ['unit_text_raw', 'unit_text_normalized', 'price_basis', 'units_per_day', 'weeks_per_unit']
    try:
        with unit_map_path.open(encoding='utf8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            for c in required_cols:
                if c not in headers:
                    issues.append(rec('MISSING_COLUMN', str(unit_map_path), c, f'Required column {c} missing'))
            if issues:
                report = {'status': 'fail', 'errors': issues, 'summary': {'error_count': len([i for i in issues if i['type'].startswith('MISSING')]), 'warning_count': 0}}
                out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
                return 1

            seen_norm = set()
            rowno = 1
            for row in reader:
                rowno += 1
                norm = (row.get('unit_text_normalized') or '').strip()
                if not norm:
                    issues.append(rec('EMPTY_NORMALIZED', str(unit_map_path), rowno, 'unit_text_normalized empty'))
                else:
                    if norm in seen_norm:
                        issues.append(rec('DUPLICATE_UNIT', str(unit_map_path), norm, f'Duplicate unit_text_normalized: {norm}'))
                    seen_norm.add(norm)

                # weeks_per_unit check
                wpu_raw = (row.get('weeks_per_unit') or '').strip()
                try:
                    wpu = float(wpu_raw)
                    if wpu <= 0:
                        issues.append(rec('WPU_NOT_POSITIVE', str(unit_map_path), rowno, f'weeks_per_unit not positive: {wpu_raw}'))
                except Exception:
                    issues.append(rec('WPU_NOT_POSITIVE', str(unit_map_path), rowno, f'weeks_per_unit invalid: {wpu_raw}'))

                # price_basis
                pb = (row.get('price_basis') or '').strip()
                if allowed_price_basis is not None and pb not in allowed_price_basis:
                    issues.append(rec('INVALID_PRICE_BASIS', str(unit_map_path), rowno, f'price_basis "{pb}" not allowed'))

                # units_per_day logical check
                upd_raw = (row.get('units_per_day') or '').strip()
                try:
                    upd = float(upd_raw)
                    if upd <= 0:
                        issues.append(rec('LOGIC_INCONSISTENCY', str(unit_map_path), rowno, f'units_per_day not positive: {upd_raw}'))
                except Exception:
                    issues.append(rec('LOGIC_INCONSISTENCY', str(unit_map_path), rowno, f'units_per_day invalid: {upd_raw}'))

    except Exception as e:
        issues.append(rec('FILE_READ_ERROR', str(unit_map_path), '', f'Failed to read unit_map.csv: {e}'))

    status = 'ok' if not issues else 'fail'
    error_count = len([i for i in issues if i['type'] in ('WPU_NOT_POSITIVE','INVALID_PRICE_BASIS','DUPLICATE_UNIT','LOGIC_INCONSISTENCY','MISSING_COLUMN') or i['type'].endswith('_ERROR')])
    warn_count = max(0, len(issues) - error_count)
    report = {'status': status, 'errors': issues, 'summary': {'error_count': error_count, 'warning_count': warn_count}}
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')

    if issues:
        print(f'Unit map validation failed: {len(issues)} issues -> {out_path}', file=sys.stderr)
        return 1

    print(f'Unit map validation passed: {unit_map_path} -> {out_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
