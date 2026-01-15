from webapp.app import app

# approximate inputs matching the screenshot: tezspire + existing テリルジー200
form = {
    'system_version': 'R9',
    'age_group': 'under70',
    'start_date': '2026-01-01',
    'drug_id': 'tezspire',
    'income_category': '',
    'prescription_interval_weeks': '12',
    'use_subsidy': 'on',
    'subsidy_cap': '20000',
    'existing_mode': 'csv',
    'primary_drug_ids': 'テリルジー200エリプタ30吸入用',
}

with app.test_request_context('/calculate', method='POST', data=form):
    rv = app.full_dispatch_request()
    html = rv.get_data(as_text=True)
    with open('response_user_case_tezspire.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('wrote response_user_case_tezspire.html, length=', len(html))
