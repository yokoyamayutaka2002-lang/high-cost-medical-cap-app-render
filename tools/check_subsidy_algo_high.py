from pathlib import Path
import sys
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.biologic_monthly import apply_monthly_subsidy_to_monthly_map

# Build sample months that produce base_annual > 100000
monthly = {
    '2026-01': {'events':[{'actual_payment': 80000},{'actual_payment':50000}]},
    '2026-02': {'events':[{'actual_payment': 30000},{'actual_payment':20000}]},
}
apply_monthly_subsidy_to_monthly_map(monthly, 30000)
for ym, b in monthly.items():
    print(ym, 'post_subsidy_self_pay=', b.get('post_subsidy_self_pay'), 'events=', [e.get('post_subsidy_payment') for e in b.get('events',[])])
base_annual = sum(int(monthly[m].get('post_subsidy_self_pay') or 0) for m in monthly)
print('base_annual=', base_annual)
if base_annual > 100000:
    deductible = max(0, base_annual - 100000)
    print('deductible=', deductible)
else:
    print('deductible=0')
