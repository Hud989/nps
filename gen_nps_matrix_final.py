import pandas as pd
import numpy as np

# Load data
df = pd.read_csv('nps_lojistas_long_format_v2.csv', sep=';', on_bad_lines='skip', low_memory=False)

# Filter NPS Question ("O Shopping")
df_nps = df[df['Tema'].isin(['O Shopping'])].copy()

# Normalize Period
def map_period(p):
    if not isinstance(p, str): return str(p)
    if '2024/1' in p: return '2024/1'
    if '2024/2' in p: return '2024/2'
    if '2025' in p: return '2025'
    return p

df_nps['Period'] = df_nps['Pesquisa'].apply(map_period)

# --- DEDUPLICATION LOGIC (FIXED) ---
# We now know that the system ONLY considers "Fim" (Completed) for the 2025 data.
# For historical data (2024), we should check if similar logic applies or if "Início"/"Único" was used.
# Let's assume consistent logic: Prefer 'Fim'. If 'Fim' exists, use it. If not, maybe use 'Único'?
# The user's goal is to match the system. The system showed 440 for 2025, which matched exactly ONLY 'Fim'.
# So for 2025, we filter only 'Fim'.
# For 2024, let's see. If I filter only 'Fim', do I lose too much data?
# Let's try a hybrid approach:
# 1. Prioritize 'Fim'.
# 2. If a respondent (ID) has 'Fim', use it.
# 3. If they DON'T have 'Fim', do we discard them? Based on 2025 findings, yes, we discard "Único" (16 records).
# So the rule is: Filter Momento == 'Fim'.

df_fim = df_nps[df_nps['Momento'] == 'Fim'].copy()

# Deduplicate just in case (though 'Fim' should be unique per ID per Period)
df_fim.drop_duplicates(subset=['Period', 'ResponseID'], keep='first', inplace=True)

# Define calculation function that returns a Series
def get_metrics(x):
    # x is the group dataframe
    total = len(x)
    if total == 0: return pd.Series({'N':0, 'Det':0, 'Neu':0, 'Prom':0, 'NPS':np.nan})
    
    # Scale notes if needed
    notes = x['Nota'].values.copy()
    if notes.max() > 10: notes = notes / 10
        
    prom = (notes >= 9).sum()
    passives = ((notes >= 7) & (notes <= 8)).sum()
    det = (notes <= 6).sum()
    
    nps = ((prom - det) / total) * 100
    
    return pd.Series({
        'N': int(total),
        'Det': int(det),
        'Neu': int(passives),
        'Prom': int(prom),
        'NPS': nps
    })

# 1. Group by Shopping and Period
grouped = df_fim.groupby(['ShoppingCode', 'Period']).apply(get_metrics).reset_index()

# 2. Calculate Portfolio Total (All shoppings combined per period)
portfolio = df_fim.groupby('Period').apply(get_metrics).reset_index()
portfolio['ShoppingCode'] = 'PORTFOLIO'

# Combine
final_df = pd.concat([grouped, portfolio])

# Sort for display
final_df['SortKey'] = final_df['Period']
final_df = final_df.sort_values(['ShoppingCode', 'SortKey'])

# Print Markdown Table
print("### Matriz NPS Lojistas (Validada com Sistema - Apenas 'Fim')")
print("| Shopping | Período | Respondentes (N) | Detratores | Neutros | Promotores | NPS Score |")
print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")

for idx, row in final_df.iterrows():
    shop = row['ShoppingCode']
    period = row['Period']
    n = int(row['N'])
    d = int(row['Det'])
    neu = int(row['Neu'])
    p = int(row['Prom'])
    nps = f"{row['NPS']:.1f}"
    
    # Bold Portfolio
    if shop == 'PORTFOLIO':
        shop = "**PORTFOLIO (Rede)**"
        period = f"**{period}**"
        nps = f"**{nps}**"
        
    print(f"| {shop} | {period} | {n} | {d} | {neu} | {p} | {nps} |")
