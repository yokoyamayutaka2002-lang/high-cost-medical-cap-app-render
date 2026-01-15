import pandas as pd
import sys
import os

def print_df_info(path, label):
    print(f"=== {label} ===")
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
    try:
        df = pd.read_excel(path)
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return
    cols = list(df.columns)
    print("Columns:", cols)
    with pd.option_context('display.max_columns', None):
        print(df.head(3).to_string(index=False))

if __name__ == '__main__':
    print_df_info("data/source_excel/mhlw_drug_price_inhaled_2025-04.xlsx", "INHALED")
    print()
    print_df_info("data/source_excel/mhlw_drug_price_oral_2025-04.xlsx", "ORAL")
