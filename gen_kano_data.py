import pandas as pd
import numpy as np
import json

# Load data
print("Loading data...")
df = pd.read_csv('nps_lojistas_long_format_v2.csv', sep=';', on_bad_lines='skip', low_memory=False)

# Map Period
def map_period(p):
    if not isinstance(p, str): return str(p)
    if '2025' in p: return '2025'
    return p

df['Period'] = df['Pesquisa'].apply(map_period)

# Filter 2025
df_2025_raw = df[df['Period'] == '2025'].copy()

# Identify Valid IDs (those who completed the survey -> Momento='Fim' in 'O Shopping')
valid_ids = df_2025_raw[(df_2025_raw['Tema'] == 'O Shopping') & (df_2025_raw['Momento'] == 'Fim')]['ResponseID'].unique()

print(f"Valid ResponseIDs: {len(valid_ids)}")

# Filter dataframe to valid IDs only
df_2025 = df_2025_raw[df_2025_raw['ResponseID'].isin(valid_ids)].copy()

# Filter Rows to keep:
# 1. 'O Shopping' MUST be 'Fim' (we discard 'Início' for these valid IDs)
# 2. Other themes (keep as is)
condition = (
    ((df_2025['Tema'] == 'O Shopping') & (df_2025['Momento'] == 'Fim')) |
    (df_2025['Tema'] != 'O Shopping')
)
df_2025 = df_2025[condition].copy()

# Normalize Nota (0-10)
if df_2025['Nota'].max() > 10:
    df_2025['Nota'] = df_2025['Nota'] / 10

# Pivot: Rows=ResponseID, Cols=Tema, Vals=Nota
# We need ShoppingCode for grouping
# First, get a mapping of ResponseID -> ShoppingCode
shop_map = df_2025[['ResponseID', 'ShoppingCode']].drop_duplicates().set_index('ResponseID')['ShoppingCode'].to_dict()

# Pivot
print("Pivoting data...")
pivot = df_2025.pivot_table(index='ResponseID', columns='Tema', values='Nota', aggfunc='mean')

# Join ShoppingCode
pivot['ShoppingCode'] = pivot.index.map(shop_map)

# Target Column
TARGET = 'O Shopping'

# Themes to analyze (exclude Target and metadata)
themes = [c for c in pivot.columns if c not in [TARGET, 'ShoppingCode']]

# --- HELPER: Calculate Stats ---
def calculate_stats(df_sub, themes):
    stats = []
    if TARGET not in df_sub.columns:
        return []
    
    # NPS of the Target (O Shopping)
    # Actually, the Kano chart uses Correlation vs Mean Score.
    # NPS of the theme itself is also used in the visual tooltips/table sometimes?
    # In storytelling_nps_kano.html, the table shows: Theme | Mean | r | cat
    # The 'nps' field in the JSON seems to be the NPS of the *Theme* itself (treating its score as NPS)
    # or the NPS of the Shopping *for that theme*? 
    # Let's calculate NPS of the Theme itself.
    
    for t in themes:
        if t not in df_sub.columns: continue
        
        # Valid pairs for correlation (drop NaN in either T or Target)
        valid = df_sub[[t, TARGET]].dropna()
        
        if len(valid) < 5: continue # Skip if too few samples
        
        # Correlation
        r = valid[t].corr(valid[TARGET])
        
        # Mean
        mean = valid[t].mean()
        
        # NPS of the Theme
        # Promoters (9-10), Detractors (0-6)
        prom = (valid[t] >= 9).sum()
        det = (valid[t] <= 6).sum()
        total = len(valid)
        nps = ((prom - det) / total) * 100
        
        # Category Logic (Simplified based on existing logic in HTML)
        # Basico: High Mean (>8.5), Low/Mod Corr (<0.2)
        # Performance: Mod/Low Mean, Mod Corr
        # Encantador: High Corr (>0.25)
        # Critico: Low Mean, Low Corr
        # Reverso: Negative Corr
        
        cat = 'per' # Default
        if r < 0: cat = 'rev'
        elif mean >= 8.5 and r < 0.2: cat = 'bas'
        elif r >= 0.25: cat = 'enc'
        elif mean < 8.0 and r < 0.2: cat = 'crit'
        
        stats.append({
            't': t,
            'm': round(mean, 2),
            'nps': round(nps, 1),
            'r': round(r, 3) if not np.isnan(r) else 0,
            'n': int(total),
            'cat': cat
        })
        
    return stats

# --- 1. Global Kano ---
print("Calculating Global Kano...")
kano_global = calculate_stats(pivot, themes)

# --- 2. Kano By Shopping ---
print("Calculating Kano By Shopping...")
kano_by_shop = {}
shoppings = sorted(pivot['ShoppingCode'].dropna().unique())

for s in shoppings:
    s_df = pivot[pivot['ShoppingCode'] == s]
    kano_by_shop[s] = calculate_stats(s_df, themes)

# --- 3. Heatmap Data (Shop x Theme Mean) ---
# shopTema2025 = { 'SDI': {'Limpeza': 8.93, ...}, ... }
print("Calculating Heatmap...")
heatmap = {}
for s in shoppings:
    s_df = pivot[pivot['ShoppingCode'] == s]
    heatmap[s] = s_df[themes].mean().round(2).to_dict()

# --- 4. NPS 2025 Static Data (for HTML header/JS) ---
# nps2025 = { 'SDI': {nps:..., media:..., n:..., prom:..., neu:..., detr:...} }
print("Calculating NPS Static Data...")
nps_static = {}
for s in shoppings:
    s_df = df_2025[(df_2025['ShoppingCode'] == s) & (df_2025['Tema'] == TARGET)]
    if s_df.empty: continue
    
    notes = s_df['Nota'].values
    prom = (notes >= 9).sum()
    det = (notes <= 6).sum()
    pas = ((notes >= 7) & (notes <= 8)).sum()
    total = len(notes)
    nps = ((prom - det) / total) * 100
    mean = notes.mean()
    
    nps_static[s] = {
        'nps': round(nps, 1),
        'media': round(mean, 2),
        'n': int(total),
        'prom': round((prom/total)*100, 1),
        'neu': round((pas/total)*100, 1),
        'detr': round((det/total)*100, 1)
    }

# --- 5. Lojistas List (Mock/Sample) ---
# The HTML uses 'todosLojistas' with names.
# Our CSV has 'Loja' column? Let's check columns.
# We will use a simplified approach: export what we have.
# If we have 'Loja' in df, we can group by ResponseID and get the Loja name.
print("Extracting Lojistas List...")
lojistas_list = {}

# We need Loja name per ResponseID
# Check if 'Loja' exists
col_loja = 'NomeLoja_NPS' if 'NomeLoja_NPS' in df.columns else ('Loja' if 'Loja' in df.columns else None)

if col_loja:
    # Group by Shopping, then get list
    for s in shoppings:
        # Get ResponseIDs for this shopping
        s_ids = pivot[pivot['ShoppingCode'] == s].index
        
        # Get data for these IDs (Target question)
        s_data = df_2025[(df_2025['ResponseID'].isin(s_ids)) & (df_2025['Tema'] == TARGET)]
        
        l_list = []
        for _, row in s_data.iterrows():
            rid = row['ResponseID']
            score = row['Nota']
            cat = 'prom' if score >= 9 else ('pass' if score >= 7 else 'detr')
            # Clean name
            name = str(row[col_loja]).upper().strip(' "')[:30]
            
            # Get Details (Scores) from Pivot
            # pivot has index ResponseID
            details = {}
            if rid in pivot.index:
                # Get series, drop NaNs, convert to dict
                p_row = pivot.loc[rid]
                # Filter out metadata columns if any remain (ShoppingCode is one)
                d_dict = p_row.drop(['ShoppingCode', TARGET], errors='ignore').dropna().to_dict()
                # Round values
                details = {k: round(v, 1) for k, v in d_dict.items()}
            
            # Get Comments
            # Filter df_2025 for this RID and non-null comments
            # Comments might be in any row for this RID
            comments = df_2025[
                (df_2025['ResponseID'] == rid) & 
                (df_2025['Comentario'].notna()) & 
                (df_2025['Comentario'] != '')
            ]['Comentario'].unique()
            
            comment_text = " | ".join([str(c).strip() for c in comments if str(c).strip()])
            
            obj = {
                'n': name, 
                's': float(score), 
                'c': cat,
                'd': details
            }
            if comment_text:
                obj['t'] = comment_text
                
            l_list.append(obj)
            
        lojistas_list[s] = l_list
else:
    print("Warning: Store Name column not found. Skipping Lojistas List.")
    lojistas_list = {}


# --- OUTPUT ---
print("Saving output...")
# We will print the JSON strings so I can copy-paste them into the HTML or save to a file
# Actually, I'll save to 'kano_data.js' and then I can read it to update HTML.

output_js = f"""
const kanoGlobal = {json.dumps(kano_global, ensure_ascii=False)};
const kanoByShop = {json.dumps(kano_by_shop, ensure_ascii=False)};
const shopTema2025 = {json.dumps(heatmap, ensure_ascii=False)};
const nps2025 = {json.dumps(nps_static, ensure_ascii=False)};
const todosLojistas = {json.dumps(lojistas_list, ensure_ascii=False)};
"""

with open('kano_data.js', 'w', encoding='utf-8') as f:
    f.write(output_js)

print("Done.")
