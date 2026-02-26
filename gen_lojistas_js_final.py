import pandas as pd
import numpy as np
import json

# Load data
df = pd.read_csv('nps_lojistas_long_format_v2.csv', sep=';', on_bad_lines='skip', low_memory=False)

# Filter NPS Question ("O Shopping")
df_nps = df[df['Tema'].isin(['O Shopping'])].copy()

# Period Mapping
def map_period(p):
    if not isinstance(p, str): return str(p)
    if '2024/1' in p: return '2024/1'
    if '2024/2' in p: return '2024/2'
    if '2025' in p: return '2025'
    return p

df_nps['Period'] = df_nps['Pesquisa'].apply(map_period)

# --- CRITICAL FIX: FILTER ONLY COMPLETED SURVEYS (MOMENTO='Fim') ---
# This aligns with the system frontend count (e.g., 440 for 2025 vs 456 raw)
df_final = df_nps[df_nps['Momento'] == 'Fim'].copy()

# Deduplicate just in case (one 'Fim' per ResponseID per Period)
df_final.drop_duplicates(subset=['Period', 'ResponseID'], keep='first', inplace=True)

print(f"Total Valid Responses (All Periods): {len(df_final)}")
print(f"2025 Count Check: {len(df_final[df_final['Period']=='2025'])}") # Should be 440

# Metrics Function
def calculate_metrics(df_sub, period_name):
    total = len(df_sub)
    if total == 0: return None
    
    # Scale notes if needed (assuming 0-10)
    notes = df_sub['Nota'].values.copy()
    if notes.max() > 10:
        notes = notes / 10
        
    prom = (notes >= 9).sum()
    passives = ((notes >= 7) & (notes <= 8)).sum()
    det = (notes <= 6).sum()
    
    nps = ((prom - det) / total) * 100
    
    return {
        'period': period_name,
        'nps': round(nps, 1),
        'total': int(total),
        'prom_pct': round((prom/total)*100, 1),
        'pass_pct': round((passives/total)*100, 1),
        'det_pct': round((det/total)*100, 1),
        'prom_abs': int(prom),
        'pass_abs': int(passives),
        'det_abs': int(det)
    }

# Data Structure
output = {}
# Only interested in these specific periods
target_periods = ['2024/1', '2024/2', '2025']
shoppings = sorted([str(s) for s in df_final['ShoppingCode'].dropna().unique()])

# Per Shopping
for shop in shoppings:
    shop_data = []
    shop_df = df_final[df_final['ShoppingCode'] == shop]
    
    for p in target_periods:
        p_df = shop_df[shop_df['Period'] == p]
        metrics = calculate_metrics(p_df, p)
        if metrics:
            shop_data.append(metrics)
            
    output[shop] = shop_data

# Global Average
global_data = []
for p in target_periods:
    p_df = df_final[df_final['Period'] == p]
    metrics = calculate_metrics(p_df, p)
    if metrics:
        global_data.append(metrics)

output['GLOBAL'] = global_data

# --- PRINT DATA FOR HTML UPDATES ---
print("\n--- DATA FOR HTML UPDATES ---")
# 1. Global NPS 2025
g25 = next((x for x in output['GLOBAL'] if x['period'] == '2025'), None)
if g25:
    print(f"Global NPS 2025: {g25['nps']}")
    print(f"Global Passives %: {g25['pass_pct']}%")
    print(f"Global Passives Count: {g25['pass_abs']}")

# 2. Shopping NPS 2025
print("\nShopping NPS 2025:")
for s in shoppings:
    d = next((x for x in output[s] if x['period'] == '2025'), None)
    if d:
        print(f"  {s}: {d['nps']} (n={d['total']})")

# 3. SDI Evolution (2024.2 -> 2025)
sdi_24_2 = next((x for x in output['SDI'] if x['period'] == '2024/2'), None)
sdi_25 = next((x for x in output['SDI'] if x['period'] == '2025'), None)
if sdi_24_2 and sdi_25:
    print(f"\nSDI Evolution: {sdi_24_2['nps']} -> {sdi_25['nps']}")

# 4. Global Distribution 2025 (for cDistGlobal)
df_2025 = df_final[df_final['Period'] == '2025'].copy()
# Normalize notes if needed
if df_2025['Nota'].max() > 10:
    df_2025['Nota'] = df_2025['Nota'] / 10

dist = df_2025['Nota'].value_counts().sort_index()
# Ensure integer keys for 0-10
dist_arr = [int(dist.get(i, 0)) for i in range(11)]
print(f"\nGlobal Distribution Array (0-10): {dist_arr}")

# Save JS
with open('lojistas_data.js', 'w', encoding='utf-8') as f:
    f.write(f"const lojistasData = {json.dumps(output, ensure_ascii=False)};")

print("JS Data generated with validated logic.")
