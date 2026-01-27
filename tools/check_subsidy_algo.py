from pathlib import Path
import sys
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.biologic_monthly import apply_monthly_subsidy_to_monthly_map

# Build a sample monthly_map with one month containing several events
monthly = {
    '2026-01': {
        'events': [
            {'order':1, 'actual_payment': 70000, 'gross': 100000},
            {'order':2, 'actual_payment': 50000, 'gross': 80000},
            {'order':3, 'actual_payment': 30000, 'gross': 50000},
        ],
    },
    '2026-02': {
        'events': [
            {'order':1, 'actual_payment': 40000, 'gross': 60000},
            {'order':2, 'actual_payment': 40000, 'gross': 60000},
        ],
    },
    '2026-03': {
        'events': [
            {'order':1, 'actual_payment': 10000, 'gross': 20000},
        ],
    }
}

print('Running subsidy algorithm with cap=30000')
apply_monthly_subsidy_to_monthly_map(monthly, 30000)

# Check per-month invariants
for ym, bucket in monthly.items():
    evs = bucket.get('events', [])
    sum_ev = sum(int(e.get('post_subsidy_payment') or 0) for e in evs)
    expected = int(bucket.get('post_subsidy_self_pay') or 0)
    print(ym, 'post_subsidy_self_pay=', expected, 'sum_events=', sum_ev)
    if sum_ev != expected:
        raise AssertionError(f'Mismatch for {ym}: sum_ev={sum_ev} expected={expected}')

# Annual base
base_annual = sum(int(monthly[m].get('post_subsidy_self_pay') or 0) for m in monthly)
print('base_annual=', base_annual)
if base_annual <= 100000:
    print('NOTE: base_annual <= 100000 (no medical deduction)')
else:
    deductible = max(0, base_annual - 100000)
    print('deductible=', deductible)

# Now test OFF subsidy (cap None)
monthly_off = {
    '2026-01': {'events':[{'actual_payment': 70000},{'actual_payment':50000}]},
}
apply_monthly_subsidy_to_monthly_map(monthly_off, None)
print('OFF subsidy month post_subsidy_self_pay=', monthly_off['2026-01']['post_subsidy_self_pay'])
print('OFF subsidy event posts=', [e.get('post_subsidy_payment') for e in monthly_off['2026-01']['events']])

# final_self_pay equivalence: in our model final_self_pay should equal month total before subsidy
month_total = sum(int(e.get('self_pay') or 0) for e in monthly_off['2026-01']['events'])
if monthly_off['2026-01']['post_subsidy_self_pay'] != month_total:
    raise AssertionError('OFF subsidy: post_subsidy_self_pay must equal month_total_self_pay')

print('All checks passed.')
