from webapp.app import app

form = {
    'system_version': 'R9',
    'age_group': 'under70',
    'start_date': '2026-01-01',
    'drug_id': 'tezspire',
    'income_category': '',
    'prescription_interval_weeks': '12',
    'use_subsidy': 'on',
    'subsidy_cap': '30000',
    'existing_mode': 'csv',
    'primary_drug_ids': 'テリルジー200エリプタ30吸入用',
    'use_medical_deduction': 'on',
    'taxable_income': '3000000',
}

with app.test_request_context('/calculate', method='POST', data=form):
    rv = app.full_dispatch_request()
    html = rv.get_data(as_text=True)
    with open('response_medical_deduction_3000000.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('wrote response_medical_deduction_3000000.html, length=', len(html))
