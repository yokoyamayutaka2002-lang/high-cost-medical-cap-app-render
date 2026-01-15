from webapp.app import app

cases = [
    ('no_subsidy', {
        'system_version':'R9','age_group':'under70','start_date':'2025-01-01','drug_id':'dupixent_300','income_category':'R9_370_510','prescription_interval_weeks':'12'
    }),
    ('with_subsidy', {
        'system_version':'R9','age_group':'under70','start_date':'2025-01-01','drug_id':'dupixent_300','income_category':'R9_370_510','prescription_interval_weeks':'12','use_subsidy':'on','subsidy_cap':'20000'
    })
]

for name, data in cases:
    with app.test_request_context('/calculate', method='POST', data=data):
        rv = app.full_dispatch_request()
        html = rv.get_data(as_text=True)
        with open(f'response_{name}.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'saved response_{name}.html (len={len(html)})')
