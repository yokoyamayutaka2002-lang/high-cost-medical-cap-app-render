import pandas as pd
import os

path = os.path.join('data','source_excel','mhlw_drug_price_oral_2025-04.xlsx')
if not os.path.exists(path):
    print('Oral Excel not found:', path)
    raise SystemExit(1)
df = pd.read_excel(path)
if '品名' not in df.columns:
    print('No 品名 column; columns=', list(df.columns))
    raise SystemExit(1)

names = ['モンテルカスト錠５ｍｇ','モンテルカスト錠１０ｍｇ','プランルカスト錠２２５ｍｇ']
for n in names:
    matches = df[df['品名'].astype(str)==n]
    print(f"Checking: {n} -> {len(matches)} matches")
    if len(matches)>0:
        print(matches[['品名','薬価']].head().to_string(index=False))
