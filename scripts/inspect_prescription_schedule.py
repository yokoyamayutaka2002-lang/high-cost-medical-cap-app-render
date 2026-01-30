from contextlib import contextmanager
from flask import template_rendered
import importlib, sys
from datetime import date
from pathlib import Path

# Ensure project root is on sys.path so `import webapp.app` works when running script directly
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

app = importlib.import_module('webapp.app').app

@contextmanager
def captured_templates(app):
    recorded = []
    def record(sender, template, context, **extra):
        recorded.append((template, dict(context)))
    template_rendered.connect(record, app)
    try:
        yield recorded
    finally:
        try:
            template_rendered.disconnect(record, app)
        except Exception:
            pass


def run_case():
    payload = {
        'system_version': 'R7',
        'income_category': 'U',
        'age_group': 'under70',
        'drug_id': 'tezspire',
        'qty2': '1',
        'qty3': '1',
        # choose start date so that order1 and order2 fall in January 2026
        'start_date': '2026-01-01',
        'existing_mode': 'manual',
        # set to 817 so monthly existing = 817*4 = 3,268 -> pre_adjust = 51,296 + 3,268 = 54,564
        'existing_weekly_cost_yen': '817',
        'use_medical_deduction': 'on',
        'taxable_income': '4000000',
        'use_subsidy': 'on',
        'subsidy_cap': '20000',
    }

    with app.test_client() as client:
        with captured_templates(app) as templates:
            resp = client.post('/calculate', data=payload)

    if not templates:
        print('No template captured')
        return 2
    template, ctx = templates[0]
    ps = ctx.get('prescription_schedule') or []
    print('Captured prescription_schedule rows (full event dicts):')
    for i, ev in enumerate(ps, start=1):
        print(f'-- Event #{i} --')
        for k, v in ev.items():
            print(f'{k}: {v}')
        print('-----')

    # Verify 2026-01 two events post_highcost values if present
    jan_events = [e for e in ps if (hasattr(e.get('date'), 'year') and e.get('date').year == 2026 and e.get('date').month == 1)]
    if len(jan_events) >= 2:
        v1 = int(jan_events[0].get('post_highcost_self_pay') or 0)
        v2 = int(jan_events[1].get('post_highcost_self_pay') or 0)
        print('\nVerification for 2026-01: post_highcost_self_pay values ->', v1, v2)
        # expected: 54,564 and 25,536 (monthly cap 80,100)
        assert v1 == 54564 and v2 == 25536, f"High-cost allocation mismatch: got {v1}, {v2}"
        print('Assertion passed: values match expected 54,564 / 25,536')
    else:
        print('\nNot enough events in 2026-01 to verify high-cost allocation')

    # Also print some period_aggregates keys for cross-check
    pa = ctx.get('period_aggregates') or {}
    cs = pa.get('calendar_start') or {}
    print('\nPeriod aggregates (calendar_start subset):')
    for k in ['existing_total_self_pay_annual', 'biologic_annual', 'biologic_with_subsidy_annual', 'after_medical_annual_self_pay']:
        print(k, cs.get(k))

    return 0

if __name__ == '__main__':
    exit(run_case())
