# Simple test harness for month-based many-times counting logic

def apply_month_caps(month_raws, monthly_limit, many_limit, many_applicable=True):
    """
    month_raws: list of tuples (month_label, month_raw_total)
    Returns list of dicts with applied cap and high_cost_month_count progression.
    """
    high_cost_month_count = 0
    results = []
    for label, raw in month_raws:
        cap = monthly_limit
        is_many = False
        if many_applicable and many_limit:
            if monthly_limit and raw >= monthly_limit:
                high_cost_month_count += 1
            if high_cost_month_count >= 4:
                cap = many_limit
                is_many = True
            else:
                cap = monthly_limit
                is_many = False
        else:
            cap = monthly_limit
            is_many = False
        results.append({'month': label, 'raw': raw, 'applied_cap': cap, 'is_many': is_many, 'count': high_cost_month_count})
    return results


def print_results(res):
    for r in res:
        print(f"{r['month']}: raw={r['raw']:6d} applied_cap={r['applied_cap']:6d} is_many={r['is_many']} count={r['count']}")


if __name__ == '__main__':
    MONTHLY = 80100
    MANY = 44400

    print('\nScenario 1: Interleaved non-qualifying months')
    months1 = [
        ('M1', 0),
        ('M2', 80100),
        ('M3', 0),
        ('M4', 80100),
        ('M5', 80100),
        ('M6', 80100),
    ]
    r1 = apply_month_caps(months1, MONTHLY, MANY)
    print_results(r1)

    print('\nScenario 2: Biologic absent then start')
    months2 = [
        ('M1', 0),
        ('M2', 0),
        ('M3', 80100),
        ('M4', 80100),
        ('M5', 80100),
        ('M6', 80100),
    ]
    r2 = apply_month_caps(months2, MONTHLY, MANY)
    print_results(r2)

    print('\nScenario 3: Year-crossing')
    # Constructed to ensure the 4th qualifying month falls on Feb (cross-year)
    months3 = [
        ('2025-10', 80100),
        ('2025-11', 0),
        ('2025-12', 80100),
        ('2026-01', 80100),
        ('2026-02', 80100),
    ]
    r3 = apply_month_caps(months3, MONTHLY, MANY)
    print_results(r3)

    # Simple assertions to ensure behavior
    assert r1[-1]['is_many'] == True and r1[-1]['applied_cap'] == MANY, 'Scenario1 failed: month6 should apply reduced cap'
    assert r2[2]['count'] == 1 and r2[-1]['count'] == 4, 'Scenario2 failed: counts incorrect'
    assert r3[4]['is_many'] == True, 'Scenario3 failed: Feb should apply reduced cap'
    print('\nAll scenario assertions passed')
