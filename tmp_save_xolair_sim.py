from src.xolair import get_xolair_dose
from src.calculator import simulate_selected_system
import json

dose = get_xolair_dose(350, 65)
res = simulate_selected_system(
    system_version='R7',
    income_code='A',
    age_group='under70',
    drug_id='xolair',
    prescription_interval_weeks=12,
    existing_weekly_cost_yen=0,
    existing_dispense_weeks=12,
    include_existing=True,
    xolair_dose_info=dose,
)
with open('tmp_xolair_sim_result.json', 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print('WROTE tmp_xolair_sim_result.json')
