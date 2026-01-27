from src.xolair import get_xolair_dose
from src.calculator import simulate_selected_system
import json

dose = get_xolair_dose(350,65)
print('dose:', dose)
res = simulate_selected_system(system_version='R7', income_code='A', age_group='under70', drug_id='xolair', prescription_interval_weeks=12, existing_weekly_cost_yen=0, existing_dispense_weeks=12, include_existing=True, xolair_dose_info=dose)
print('type:', type(res))
print(json.dumps(res, ensure_ascii=False, indent=2))
