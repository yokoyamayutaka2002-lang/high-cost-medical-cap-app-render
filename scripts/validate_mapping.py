#!/usr/bin/env python3
import sys
import os
import json
from pathlib import Path

try:
    import yaml
except Exception:
    yaml = None

REPORT_PATH = Path('reports')


def err_record(t, file, row_or_key, msg):
    return {'type': t, 'file': file, 'row_or_key': row_or_key, 'message': msg}


def load_yaml(p: Path):
    if yaml is None:
        raise RuntimeError('PyYAML is required to parse mapping.yaml')
    text = p.read_text(encoding='utf8')
    return yaml.safe_load(text)


def main():
    if len(sys.argv) < 2:
        print('Usage: validate_mapping.py mapping.yaml')
        return 1
    mapping_path = Path(sys.argv[1])
    REPORT_PATH.mkdir(exist_ok=True)
    out_path = REPORT_PATH / 'validate_mapping.json'
    issues = []

    if not mapping_path.exists():
        issues.append(err_record('FILE_NOT_FOUND', str(mapping_path), '', 'mapping.yaml not found'))
        report = {'status': 'fail', 'errors': issues, 'summary': {'error_count': len(issues), 'warning_count': 0}}
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        return 1

    try:
        data = load_yaml(mapping_path)
    except Exception as e:
        issues.append(err_record('YAML_PARSE_ERROR', str(mapping_path), '', f'Failed to parse YAML: {e}'))
        report = {'status': 'fail', 'errors': issues, 'summary': {'error_count': len(issues), 'warning_count': 0}}
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        return 1

    # Required top-level keys
    for key in ('required', 'recommended', 'optional'):
        if key not in data:
            issues.append(err_record('MISSING_TOPLEVEL_SECTION', str(mapping_path), key, f'Top-level section "{key}" is missing'))

    # Validate required fields structure
    required = data.get('required', {})
    for logical_field, spec in required.items():
        # candidates must exist and be list with at least one
        candidates = spec.get('candidates') if isinstance(spec, dict) else None
        if not candidates or not isinstance(candidates, list):
            issues.append(err_record('EMPTY_CANDIDATES', str(mapping_path), logical_field, f'Field "{logical_field}" missing candidates or empty'))
            continue
        # check duplicates within candidates
        seen = set()
        for c in candidates:
            if c in seen:
                issues.append(err_record('DUPLICATE_CANDIDATE', str(mapping_path), logical_field, f'Duplicate candidate "{c}" in {logical_field}'))
            seen.add(c)

    # Check same-candidate across logical fields (should not be duplicate inside same logical field only per spec)
    # The spec says duplicate candidate within same logical field is forbidden; across fields allowed.

    # Ensure required promotions: excel_strength & excel_unit_text exist in required
    for promoted in ('excel_strength', 'excel_unit_text'):
        if promoted not in required:
            issues.append(err_record('REQUIRED_FIELD_MISSING', str(mapping_path), promoted, f'Required promoted field "{promoted}" must be present in required section'))

    # Failure policy consistency
    settings = data.get('settings', {})
    fp = settings.get('failure_policy')
    fp_boot = settings.get('failure_policy_bootstrap')
    allowed_modes = {'FAIL', 'WARN', 'REPORT'}
    if fp:
        for k, v in fp.items():
            if isinstance(v, str) and v.upper() not in allowed_modes:
                issues.append(err_record('INVALID_FAILURE_POLICY', str(mapping_path), f'settings.failure_policy.{k}', f'Invalid policy value: {v}'))
    if fp_boot:
        for k, v in fp_boot.items():
            if isinstance(v, str) and v.upper() not in allowed_modes:
                issues.append(err_record('INVALID_FAILURE_POLICY', str(mapping_path), f'settings.failure_policy_bootstrap.{k}', f'Invalid policy value: {v}'))

    status = 'ok' if not issues else 'fail'
    report = {'status': status, 'errors': issues, 'summary': {'error_count': len(issues), 'warning_count': 0}}
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')

    if issues:
        print(f'Mapping validation failed: {len(issues)} issues written to {out_path}', file=sys.stderr)
        return 1

    print(f'Mapping validation succeeded: {mapping_path} -> {out_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
