from contextlib import contextmanager
from flask import template_rendered
from datetime import date

import importlib

# Import the Flask app object from the webapp package's app module explicitly.
app = importlib.import_module('webapp.app').app


@contextmanager
def captured_templates(app):
    recorded = []

    def record(sender, template, context, **extra):
        # copy minimal context snapshot
        recorded.append((template, dict(context)))

    template_rendered.connect(record, app)
    try:
        yield recorded
    finally:
        try:
            template_rendered.disconnect(record, app)
        except Exception:
            pass


def _tax_rate_for_income(ti):
    if ti <= 1950000:
        return 0.05
    if ti <= 3300000:
        return 0.10
    if ti <= 6950000:
        return 0.20
    if ti <= 9000000:
        return 0.23
    if ti <= 18000000:
        return 0.33
    if ti <= 40000000:
        return 0.40
    return 0.45


def run_check():
    # Test payload: choose an available biologic and a manual existing weekly
    payload = {
        'system_version': 'R9',
        'age_group': 'under70',
        'drug_id': 'tezspire',
        'qty2': '1',
        'qty3': '1',
        'start_date': date.today().isoformat(),
        'existing_mode': 'manual',
        'existing_weekly_cost_yen': '3000',
        'use_medical_deduction': 'on',
        'taxable_income': '4000000',
        'use_subsidy': 'on',
        'subsidy_cap': '20000',
    }

    with app.test_client() as client:
        with captured_templates(app) as templates:
            resp = client.post('/calculate', data=payload)

    if not templates:
        print('ERROR: no template rendered')
        return 2

    template, ctx = templates[0]

    # Extract SSOT-backed values (ctx keys were overwritten in app)
    existing_a = int(ctx.get('existing_annual') or ctx.get('existing_only_annual') or 0)
    biologic_a = int(ctx.get('biologic_annual') or 0)
    total_a = int(ctx.get('total_medical_annual') or 0)
    post_subsidy = int(ctx.get('post_subsidy_total_annual') or 0)
    med_refund = int(ctx.get('medical_tax_refund_total') or 0)
    annual_diff = int(ctx.get('annual_difference') or (biologic_a - existing_a))

    ok = True

    # 1) existing_weekly * 52
    expected_existing = int(payload['existing_weekly_cost_yen']) * 52
    if existing_a != expected_existing:
        print(f'FAIL existing_annual: got {existing_a}, expected {expected_existing}')
        ok = False
    else:
        print(f'OK existing_annual == {existing_a} (weekly*52)')

    # 2) medical deduction should be computed from post_subsidy
    try:
        taxable_income = int(payload.get('taxable_income') or 0)
    except Exception:
        taxable_income = 0
    tax_rate = _tax_rate_for_income(taxable_income)
    deductible = max(int(post_subsidy) - 100000, 0)
    expected_income_refund = int(round(deductible * tax_rate)) if deductible > 0 else 0
    expected_resident_refund = int(round(deductible * 0.10)) if deductible > 0 else 0
    expected_total_refund = int(expected_income_refund + expected_resident_refund)

    if med_refund != expected_total_refund:
        print(f'FAIL medical_tax_refund_total: got {med_refund}, expected {expected_total_refund} (deductible base={deductible})')
        ok = False
    else:
        print(f'OK medical_tax_refund_total == {med_refund} (from post_subsidy={post_subsidy})')

    # 3) difference = biologic_annual - existing_annual
    if annual_diff != (biologic_a - existing_a):
        print(f'FAIL annual_difference: got {annual_diff}, expected {biologic_a - existing_a}')
        ok = False
    else:
        print(f'OK annual_difference == {annual_diff} (biologic - existing)')

    # Summary
    print('\nSummary: existing={}, biologic={}, total={}, post_subsidy={}, med_refund={}, diff={}'.format(
        existing_a, biologic_a, total_a, post_subsidy, med_refund, annual_diff
    ))

    return 0 if ok else 1


if __name__ == '__main__':
    exit(run_check())
