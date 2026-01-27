import pandas as pd
import os

ORAL_XLSX = os.path.join('data','source_excel','mhlw_drug_price_oral_2025-04.xlsx')
DOSING_MASTER = os.path.join('data','dosing_master.csv')

print('Oral Excel path:', ORAL_XLSX)
if os.path.exists(ORAL_XLSX):
    df = pd.read_excel(ORAL_XLSX)
    if '品名' in df.columns:
        print('\nExcel sample 品名 values:')
        print(df['品名'].head(20).to_list())
    else:
        print('Excel does not have 品名 column; columns=', list(df.columns))
else:
    print('Oral Excel not found')

print('\nDosing master sample drug_name values:')
if os.path.exists(DOSING_MASTER):
    dm = pd.read_csv(DOSING_MASTER)
    print(dm['drug_name'].unique().tolist()[:20])
else:
    print('Dosing master not found')
