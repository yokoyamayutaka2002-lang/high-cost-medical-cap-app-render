# E2E Dry-run Report
- Excel file: data\source_excel\mhlw_drug_price_oral_2025-04.xlsx
- Status: pass

## Key metrics
- New drugs (resolved): 85
- Unmapped rows: 6936
- Possible matches: 0
- Price change warnings: 0
- Price change errors: 0

## Validator reports
- reports/validate_mapping.json: fail
- reports/validate_unit_map.json: fail
- reports/validate_master_id_map.json: fail
- reports/validate_drug_price.json: fail

## Manual checks / notes
- There are unmapped rows: manual mapping required before production import.