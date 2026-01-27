import json
from src.calculator import simulate_annual_cost
from src.calculator import simulate_selected_system

result = simulate_annual_cost("R9","R9_370_510","under70","dupixent_300",12)
print(json.dumps(result, ensure_ascii=False))

# -------------------------
# Regression tests (UI changes must not affect numeric outputs)
# These print the live results first, then assert against observed values.
# -------------------------
tests = [
	# (system_version, income_code, age_group, expected_annual, expected_monthly, expected_many)
	("R7", "3", "under70", 284700, 23725, True),           # observed: R7 under70 code '3'
	("R7", "3", "over70", 72000, 6000, False),             # observed: R7 over70 general ('3')
	("R9", "L1", "over70", 32000, 2667, False),            # observed: R9 low-income L1 direct special-case
	("R9", "R9_370_510", "over70", 301800, 25150, True),   # observed: R9 over70 R9_370_510
]

for sys_ver, inc_code, age_grp, exp_ann, exp_mon, exp_many in tests:
	res = simulate_selected_system(
		system_version=sys_ver,
		income_code=inc_code,
		age_group=age_grp,
		drug_id="dupixent_300",
		prescription_interval_weeks=12,
	)
	print(sys_ver, inc_code, age_grp, json.dumps(res, ensure_ascii=False))

	# Assertions (guard numeric regression). These assert the three numeric outputs.
	assert int(res.get("annual_cost", 0)) == exp_ann
	assert int(res.get("monthly_average_cost", 0)) == exp_mon
	assert bool(res.get("is_many_times_applied", False)) is exp_many

print("All regression checks passed.")

# -------------------------
# Existing-treatment aggregation checks (Step3-1 minimal tests)
# -------------------------
# Use a small existing weekly cost to verify aggregation/comparison logic.
only = simulate_annual_cost("R9", "R9_370_510", "under70", "dupixent_300", 12)
plus = simulate_annual_cost(
	"R9",
	"R9_370_510",
	"under70",
	"dupixent_300",
	12,
	existing_weekly_cost_yen=1000,
	existing_dispense_weeks=12,
	include_existing=True,
)

print("biologic only annual:", only.get("annual_cost"))
print("biologic + existing annual:", plus.get("annual_cost"))

# include_existing=False must match prior behavior
assert int(only.get("annual_cost", 0)) == int(simulate_selected_system(
	system_version="R9",
	income_code="R9_370_510",
	age_group="under70",
	drug_id="dupixent_300",
	prescription_interval_weeks=12,
).get("annual_cost", 0))

# When existing is included, annual should be >= biologic-only
assert int(plus.get("annual_cost", 0)) >= int(only.get("annual_cost", 0))

# Difference must be present and equal to the numeric delta
assert "difference_annual_cost" in plus
assert int(plus.get("difference_annual_cost", 0)) == int(plus.get("annual_cost", 0)) - int(only.get("annual_cost", 0))

print("Existing-treatment aggregation checks passed.")
