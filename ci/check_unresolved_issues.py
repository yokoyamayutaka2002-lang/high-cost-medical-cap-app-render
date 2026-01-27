#!/usr/bin/env python3
"""
CI merge-gate: check for unresolved issues in artifacts/validation/validation_report.json

Exit codes:
 0 -> merge allowed
 2 -> unresolved ERROR
 3 -> unresolved WARNING requiring ack
 4 -> invalid waiver

Produces: reports/merge_gate.json and human-readable stdout
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import datetime
import os


def load_json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf8'))
    except Exception as e:
        print(f'Failed to read JSON {p}: {e}', file=sys.stderr)
        return None


def normalize_level(v: str | None) -> str:
    if not v:
        return ''
    return v.strip().upper()


def main():
    repo_root = Path.cwd()
    val_path = repo_root / 'artifacts' / 'validation' / 'validation_report.json'
    manifest_path = repo_root / 'artifacts' / 'manifest.json'

    val = load_json(val_path)
    manifest = load_json(manifest_path) or {}

    if val is None:
        print('Validation report not found at artifacts/validation/validation_report.json', file=sys.stderr)
        # nothing to validate - treat as failure
        sys.exit(3)

    issues = val.get('issues') if isinstance(val, dict) else val
    if not isinstance(issues, list):
        print('validation_report.json format invalid: expected top-level issues array', file=sys.stderr)
        sys.exit(3)

    # allowed approvers list for waivers
    allowed_approvers = []
    # prefer manifest field 'waiver_approved_by_allowed' or env var
    if manifest and isinstance(manifest, dict):
        allowed_approvers = manifest.get('waiver_approved_by_allowed') or []
    if not allowed_approvers:
        env = os.environ.get('WAIVER_ALLOWED_APPROVERS')
        if env:
            allowed_approvers = [e.strip() for e in env.split(',') if e.strip()]

    # read waivers list in manifest
    waivers = manifest.get('waivers') or []
    waiver_map = { w.get('issue_id'): w for w in waivers if isinstance(w, dict) and w.get('issue_id') }

    unresolved_errors = []
    unresolved_warnings = []
    invalid_waivers = []

    for it in issues:
        if not isinstance(it, dict):
            continue
        issue_id = it.get('issue_id') or it.get('rule') or ''
        level = normalize_level(it.get('level'))
        requires_ack = bool(it.get('requires_ack'))
        res = it.get('resolution') or {}
        res_status = (res.get('status') or 'unresolved').strip().lower()

        is_unresolved = res_status != 'resolved' and res_status != 'waived'

        if level == 'ERROR':
            if is_unresolved:
                unresolved_errors.append({ 'issue_id': issue_id, 'row': it.get('row'), 'column': it.get('column') })
        elif level == 'WARNING':
            if requires_ack:
                if res_status == 'resolved':
                    pass
                elif res_status == 'waived':
                    # verify waiver exists and approved
                    w = waiver_map.get(issue_id)
                    if not w:
                        invalid_waivers.append({ 'issue_id': issue_id, 'reason': 'no waiver entry in manifest' })
                    else:
                        approved_by = w.get('approved_by')
                        reason = w.get('reason')
                        if not approved_by or not reason:
                            invalid_waivers.append({ 'issue_id': issue_id, 'reason': 'waiver missing approved_by or reason' })
                        else:
                            # check approver allowed
                            if allowed_approvers and approved_by not in allowed_approvers:
                                invalid_waivers.append({ 'issue_id': issue_id, 'reason': f'approved_by {approved_by} not in allowed approvers' })
                else:
                    # unresolved warning requiring ack
                    unresolved_warnings.append({ 'issue_id': issue_id })
        else:
            # INFO or unknown: ignore for gate
            pass

    # Determine exit status per rules
    out = {
        'checked_at': datetime.utcnow().isoformat() + 'Z',
        'unresolved_errors': unresolved_errors,
        'unresolved_warnings': unresolved_warnings,
        'invalid_waivers': invalid_waivers,
        'allowed_approvers': allowed_approvers,
    }

    # write reports/merge_gate.json
    reports_dir = repo_root / 'reports'
    reports_dir.mkdir(exist_ok=True)
    report_path = reports_dir / 'merge_gate.json'
    report_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf8')

    # human-readable stdout
    if unresolved_errors or unresolved_warnings or invalid_waivers:
        print('❌ PR merge blocked')
        print()
        if unresolved_errors:
            print(f"Unresolved ERROR issues: {len(unresolved_errors)}")
            for e in unresolved_errors:
                print(f"- {e.get('issue_id')} (row {e.get('row')}, column {e.get('column')})")
            print()
        if unresolved_warnings:
            print(f"Unresolved WARNING issues requiring ack: {len(unresolved_warnings)}")
            for w in unresolved_warnings:
                print(f"- {w.get('issue_id')}")
            print()
        if invalid_waivers:
            print(f"Invalid or missing waivers: {len(invalid_waivers)}")
            for iv in invalid_waivers:
                print(f"- {iv.get('issue_id')}: {iv.get('reason')}")
            print()
        print('➡ Resolve or waive issues before merging.')
    else:
        print('✅ Merge allowed: no unresolved blocking issues')

    # exit codes precedence: ERROR unresolved > invalid waiver > WARNING unresolved
    if unresolved_errors:
        sys.exit(2)
    if invalid_waivers:
        sys.exit(4)
    if unresolved_warnings:
        sys.exit(3)

    sys.exit(0)


if __name__ == '__main__':
    main()
