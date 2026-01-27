from webapp.app import app

cases = [
    # baseline (no subsidy)
    ('baseline_no_subsidy', {'system_version':'R9','age_group':'under70','start_date':'2025-01-01','drug_id':'dupixent_300','income_category':'R9_370_510','prescription_interval_weeks':'12'}),
    # subsidy applied
    ('baseline_with_subsidy', {'system_version':'R9','age_group':'under70','start_date':'2025-01-01','drug_id':'dupixent_300','income_category':'R9_370_510','prescription_interval_weeks':'12','use_subsidy':'on','subsidy_cap':'20000'}),
    # existing treatment present (manual existing weekly)
    ('existing_weekly_2000_no_subsidy', {'system_version':'R9','age_group':'under70','start_date':'2025-01-01','drug_id':'dupixent_300','income_category':'R9_370_510','prescription_interval_weeks':'12','existing_weekly_cost_yen':'2000'}),
    ('existing_weekly_2000_with_subsidy', {'system_version':'R9','age_group':'under70','start_date':'2025-01-01','drug_id':'dupixent_300','income_category':'R9_370_510','prescription_interval_weeks':'12','existing_weekly_cost_yen':'2000','use_subsidy':'on','subsidy_cap':'20000'}),
    # different income bracket (high cap)
    ('high_income_with_subsidy', {'system_version':'R9','age_group':'under70','start_date':'2025-01-01','drug_id':'dupixent_300','income_category':'R9_1650_PLUS','prescription_interval_weeks':'12','use_subsidy':'on','subsidy_cap':'20000'}),
]

for name, data in cases:
    with app.test_request_context('/calculate', method='POST', data=data):
        rv = app.full_dispatch_request()
        html = rv.get_data(as_text=True)
        path = f'response_more_{name}.html'
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'saved {path} (len={len(html)})')
