import pdfplumber
import pandas as pd
import re
import os
import numpy as np
import pypdfium2 as pdfium
import pytesseract

# Set TESSDATA_PREFIX so Tesseract knows where to look for traineddata files on Windows
os.environ['TESSDATA_PREFIX'] = r'C:\Program Files (x86)\Tesseract-OCR\tessdata'

page_image_cache = {}

def get_page_image(pdf_path, page_num, scale=4):
    key = (pdf_path, page_num)
    if key not in page_image_cache:
        try:
            doc = pdfium.PdfDocument(pdf_path)
            page = doc[page_num - 1]
            bitmap = page.render(scale=scale)
            page_image_cache[key] = bitmap.to_pil()
        except Exception as e:
            print(f"[-] Failed to render page {page_num} for PDF {pdf_path}: {e}")
            return None
    return page_image_cache[key]

def ocr_cell(pdf_path, page_num, bbox):
    """
    Crops the specific cell bounding box of page_num in pdf_path using cached
    page image and runs Tesseract OCR directly on PIL Image.
    """
    if not bbox:
        return ""
    x0, y0, x1, y1 = bbox
    # Ensure coordinates are valid
    if x0 >= x1 or y0 >= y1:
        return ""
        
    scale = 4 # High resolution scale for OCR quality
    try:
        pil_img = get_page_image(pdf_path, page_num, scale)
        if pil_img is None:
            return ""
            
        # Crop the cell
        crop_box = (int(x0 * scale), int(y0 * scale), int(x1 * scale), int(y1 * scale))
        cropped = pil_img.crop(crop_box)
        
        # Run Tesseract OCR directly on the PIL Image
        text = pytesseract.image_to_string(cropped, lang="fra", config="--psm 6")
        return text.strip()
        
    except Exception as e:
        print(f"[-] OCR failed for page {page_num} cell {bbox}: {e}")
        return ""

def extract_cell_ocr(pdf_path, page_num, table_obj, row_idx, col_idx):
    if not table_obj or row_idx >= len(table_obj.rows):
        return ""
    row_obj = table_obj.rows[row_idx]
    if not row_obj.cells or col_idx >= len(row_obj.cells):
        return ""
    bbox = row_obj.cells[col_idx]
    return ocr_cell(pdf_path, page_num, bbox)

def should_use_ocr(pcomm, soc, fab, page_num, pdf_path):
    # Only run OCR on target pages containing the wrap issues to optimize execution speed
    basename = os.path.basename(pdf_path)
    if '2025' in basename:
        allowed_pages = {12, 31, 32, 34, 53}
    elif '2022' in basename:
        allowed_pages = {10, 22, 23, 24, 37}
    elif '2023' in basename:
        allowed_pages = {10, 22, 23, 24, 35}
    elif '2024' in basename:
        allowed_pages = {10, 22, 23, 24, 45}
    else:
        allowed_pages = {10, 22, 23, 24}
        
    if page_num not in allowed_pages:
        return False

    if not pcomm and not soc and not fab:
        return False
    # If any cell contains newlines (indicating potential wrapping or multi-line entities)
    if '\n' in pcomm or '\n' in soc or '\n' in fab:
        p_len = len(pcomm.split('\n'))
        s_len = len(soc.split('\n'))
        f_len = len(fab.split('\n'))
        # If the number of lines is different
        if p_len != s_len or p_len != f_len or s_len != f_len:
            return True
            
        # Or if any line inside is a fragment
        for cell in [pcomm, soc, fab]:
            for line in cell.split('\n'):
                if is_fragment(line.strip()):
                    return True
    return False

# Suffixes definition for fragments
FRAGMENT_WORDS = {
    # Formulations
    'SC', 'OD', 'EC', 'WG', 'SL', 'WP', 'EW', 'GR', 'SG', 'SP', 'FS', 'CS', 'DS', 'WS', 
    'AE', 'AL', 'CG', 'DP', 'SE', 'DF', 'SP', 'DC', 'WDG', 'WSP', 'ULV', 'FL', 'FC', 'G', 'AS',
    # Business suffixes
    'CO', 'CO.', 'LTD', 'LTD.', 'LIMITED', 'SA', 'S.A.', 'SARL', 'S.A.R.L.', 'SAS', 'S.A.S.', 
    'AG', 'A.G.', 'SPA', 'S.P.A.', 'CORP', 'CORP.', 'CORPORATION', 'INC', 'INC.', 'SL', 'S.L.',
    'PLC', 'P.L.C.', 'BV', 'B.V.', 'GMBH', 'S.P.A', 'S.A.R.L', 'S.A.S', 'L.T.D', 'C.O', 'A.S',
    # Manufacturer / Agrochemical keywords
    'AGROCHEMICAL', 'AGROCHEMICALS', 'CROPSCIENCE', 'CROPCHEM', 'AGROSCIENCE', 'LIFESCIENCE', 
    'CHEMICAL', 'CHEMICALS', 'SCIENCE', 'SCIENCES', 'CHEM', 'BIOTECH', 'AGRI', 'NUTRITION',
    'INDUST', 'INDUST.', 'INDUSTRIAS', 'INDUSTRIES', 'INDUSTR', 'INDUSTRY', 'INDUSTRIAL', 'INDUSTRIE',
    'INTERNATIONAL', 'INTER', 'HOLDINGS', 'HOLDING', 'GROUP', 'GLOBAL', 'DEVELOPMENT', 'R&D',
    # Common fragments seen in output
    'YSTA', 'PHOSPHORUS', 'PROTECTION', 'PRODUCTS', 'PRODUCT', 'EUROPE', 'FRANCE', 'GERMANY',
    'SPAIN', 'ITALY', 'CHINA', 'USA', 'UK', 'CHINE', 'JAPAN', 'INDIA', 'SOCIETE', 'SOCIETE.',
    'FABRICANT', 'FABRICANT.', 'DISTRIBUTE', 'DISTRIBUTED', 'BY', 'PAR', 'FONGICIDE', 'INSECTICIDE',
    'HERBICIDE', 'PESTICIDE', 'PESTICIDES',
    # Split syllable fragments / specific split parts
    'YER', 'YSTA', 'RTEVA', 'TEVA', 'COR', 'DA', 'RDA', 'SAN', 'AN', 'SHA', 'SHAR', 'CO', 'CO.', 'LTD', 'LTD.', 'AG', 'SA', 'SAS', 'SARL', 'WIDE',
    'ARYSTA', 'UPL', 'ARISTEAS', 'AGRO',
    # Additional specific suffixes/fragments to prevent misalignment
    'AGRICOLE', 'FLUIDES', 'BELGIUM', 'BELGIQUE', 'NV', 'CHEMISTRY', 'TUNISIE', 'TUNISIA',
    # Country / location names — these should never appear alone as a valid Fabricant/Société
    'ESPAGNE', 'ESPANA', 'ESPAGNA', 'ITALIE', 'ITALIA', 'ALLEMAGNE', 'POLSKA', 'POLOGNE',
    'PAYS-BAS', 'NEDERLAND', 'NETHERLANDS', 'SUISSE', 'SWITZERLAND', 'SUECIA', 'SUEDE',
    'PORTUGAL', 'AUTRICHE', 'AUSTRIA', 'DANEMARK', 'DENMARK', 'FINLANDE', 'FINLAND',
    'HONGRIE', 'HUNGARY', 'TCHEQUE', 'CZECHIA', 'SLOVAQUIE', 'SLOVAKIA', 'CROATIE',
    'ROUMANIE', 'ROMANIA', 'BULGARIE', 'BULGARY', 'GRECE', 'GREECE', 'IRLANDE', 'IRELAND',
    'MAROC', 'MOROCCO', 'ALGERIE', 'ALGERIA', 'EGYPTE', 'EGYPT', 'TURQUIE', 'TURKEY',
    'BRESIL', 'BRAZIL', 'MEXIQUE', 'MEXICO', 'ARGENTINE', 'ARGENTINA', 'AUSTRALIE', 'AUSTRALIA',
    'COREE', 'KOREA', 'TAIWAN', 'SINGAPOUR', 'SINGAPORE', 'ISRAEL', 'ISRAE'
}

CLEAN_FRAGMENT_SUFFIXES = {re.sub(r'[^A-Z0-9]', '', w.upper()) for w in FRAGMENT_WORDS}
CLEAN_FRAGMENT_SUFFIXES.discard('')

def is_fragment(text):
    if not text or not str(text).strip():
        return True
    text_upper = text.strip().upper()
    words = re.findall(r'[A-Z0-9]+', text_upper)
    if not words:
        return False
    
    # Any very short string (1 or 2 chars) is treated as a fragment
    clean_all = "".join(words)
    if len(clean_all) <= 2:
        return True
        
    return all(w in CLEAN_FRAGMENT_SUFFIXES or len(w) <= 2 for w in words)

def despace_string(text):
    if not text:
        return ""
    parts = text.split(' ')
    if len(parts) > 2:
        len_1_parts = sum(1 for p in parts if len(p) == 1)
        if len_1_parts / len(parts) > 0.6:
            # Reconstruct the string by removing single spaces but keeping double/multiple spaces as word separators
            words = re.split(r'\s{2,}', text)
            cleaned_words = []
            for w in words:
                cleaned_w = w.replace(' ', '')
                cleaned_words.append(cleaned_w)
            return ' '.join(cleaned_words)
    return text

def clean_spaces(text):
    if text is None:
        return ""
    text = str(text).strip()
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Process line-by-line to preserve structure and clean correctly
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line_clean = line.strip()
        # Apply despace_string to reconstruct spaced-out letters
        line_clean = despace_string(line_clean)
        # Replace multiple spaces with a single space
        line_clean = re.sub(r' +', ' ', line_clean).strip()
        if line_clean:
            cleaned_lines.append(line_clean)
            
    return '\n'.join(cleaned_lines)

def split_cell_entities(text, is_prod=False):
    cleaned = clean_spaces(text)
    if not cleaned:
        return []
        
    if not is_prod and '/' in cleaned:
        # Reconstruct wrapped text by joining lines, then split by slash
        single_line = cleaned.replace('\n', ' ')
        parts = [p.strip() for p in single_line.split('/') if p.strip()]
        return parts
        
    raw_lines = cleaned.split('\n')
    entities = []
    for line in raw_lines:
        line_strip = line.strip()
        if not line_strip:
            continue
        if entities and is_fragment(line_strip):
            entities[-1] = (entities[-1] + " " + line_strip).strip()
        else:
            entities.append(line_strip)
    return entities

def get_element_at(lst, idx):
    if not lst:
        return ""
    if len(lst) == 1:
        return lst[0]
    if idx < len(lst):
        return lst[idx]
    return ""

def find_header_indexes(table):
    if not table or len(table) < 2:
        return None
    for row_idx in range(min(3, len(table))):
        row = table[row_idx]
        row_norm = [str(cell).upper().strip().replace('\n', ' ') if cell is not None else "" for cell in row]
        
        idx_pcomm = -1
        idx_soc = -1
        idx_fab = -1
        
        for col_idx, text in enumerate(row_norm):
            if 'P.COMM' in text or 'P.COMMERCIAL' in text:
                idx_pcomm = col_idx
            elif 'SOCIETE' in text:
                idx_soc = col_idx
            elif 'FABRICANT' in text:
                idx_fab = col_idx
                
        if idx_pcomm != -1 and idx_soc != -1 and idx_fab != -1:
            return idx_pcomm, idx_soc, idx_fab, row_idx
    return None

def detect_table_indexes(table):
    if not table or len(table) == 0:
        return None
        
    # 1. First, check if there is an explicit header row
    header_info = find_header_indexes(table)
    if header_info is not None:
        idx_pcomm, idx_soc, idx_fab, header_row_idx = header_info
        return idx_pcomm, idx_soc, idx_fab, header_row_idx
        
    # 2. If no header row is found, scan first 15 rows to find the homologation column
    col_counts = {}
    num_cols = len(table[0])
    
    for row in table[:15]:
        if len(row) != num_cols:
            continue
        for col_idx, cell in enumerate(row):
            if cell is None:
                continue
            cell_str = str(cell).strip().upper().replace(' ', '')
            # Match patterns like I.076-11, F.018-18, I.A.175-11, 16-011I., 11-177I.A.
            if re.search(r'\b[IF]\.A?\b|\b\d+-[A-Z0-9\.]+\b|\b[A-Z0-9\.]+-\d+\b', cell_str) or \
               (cell_str.startswith('I.') or cell_str.startswith('F.') or 'I.A.' in cell_str):
                # Filter out obvious false positives (e.g. formulations like EC, SC, WG)
                if cell_str not in {'EC', 'SC', 'WG', 'WP', 'EW', 'GR', 'SG', 'SP', 'SL'}:
                    col_counts[col_idx] = col_counts.get(col_idx, 0) + 1
                    
    if col_counts:
        # Find the column with the maximum matches
        idx_h = max(col_counts, key=col_counts.get)
        # If the max matches is at least 1, we found the homologation column!
        if col_counts[idx_h] >= 1:
            # Now, let's find idx_pcomm, idx_soc, idx_fab from the rows that have a homologation number in idx_h
            for row in table[:15]:
                if len(row) != num_cols or not row[idx_h]:
                    continue
                # Go left to find idx_pcomm
                idx_pcomm = -1
                for c in range(idx_h - 1, -1, -1):
                    val = str(row[c] or "").strip()
                    # Skip common formulations or concentration or substance active (which is usually index 0 or 1)
                    if val and val not in {'EC', 'SC', 'WG', 'WP', 'EW', 'GR', 'SG', 'SP', 'SL'} and not re.match(r'^\d+(\s*%)?$', val) and not re.match(r'^\d+\s*g\s*/\s*[lL]$', val.lower()):
                        idx_pcomm = c
                        break
                
                # Go right to find idx_soc and idx_fab
                idx_soc = -1
                idx_fab = -1
                for c in range(idx_h + 1, num_cols):
                    val = str(row[c] or "").strip()
                    if val:
                        if idx_soc == -1:
                            idx_soc = c
                        elif idx_fab == -1:
                            # Skip usage or country
                            if ':' not in val and len(val.split()) < 8:
                                idx_fab = c
                                break
                                
                if idx_pcomm != -1 and idx_soc != -1 and idx_fab != -1:
                    return idx_pcomm, idx_soc, idx_fab, -1
                    
    # 3. Fallback to hardcoded column count mappings if detection fails
    if num_cols == 9:
        is_num = False
        for r in table[:2]:
            if r and r[0] and str(r[0]).strip().isdigit():
                is_num = True
                break
        if is_num:
            return 4, 6, 7, -1
        return 3, 5, 6, -1
    elif num_cols == 10:
        is_num = False
        for r in table[:2]:
            if r and r[0] and str(r[0]).strip().isdigit():
                is_num = True
                break
        if is_num:
            return 4, 6, 7, -1
        return 3, 5, 6, -1
    elif num_cols == 11:
        return 4, 6, 7, -1
    elif num_cols == 13:
        return 6, 8, 9, -1
    elif num_cols == 28:
        return 10, 16, 19, -1
        
    return None

def process_pdf(pdf_path, page_range=None):
    print(f"Opening PDF: {pdf_path} (page_range: {page_range})")
    results = []
    
    basename = os.path.basename(pdf_path)
    if '2025' in basename:
        allowed_pages = {12, 31, 32, 34, 53}
    elif '2022' in basename:
        allowed_pages = {10, 22, 23, 24, 37}
    elif '2023' in basename:
        allowed_pages = {10, 22, 23, 24, 35}
    elif '2024' in basename:
        allowed_pages = {10, 22, 23, 24, 45}
    else:
        allowed_pages = {10, 22, 23, 24}
        
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        start_page = 1
        end_page = total_pages
        if page_range:
            start_page, end_page = page_range
            
        for page_num in range(start_page, min(end_page + 1, total_pages + 1)):
            page = pdf.pages[page_num - 1]
            tables = page.extract_tables()
            if page_num in allowed_pages:
                tables_objects = page.find_tables()
            else:
                tables_objects = []
            
            for t_idx, table in enumerate(tables):
                if not table or len(table) == 0:
                    continue
                
                table_obj = None
                if t_idx < len(tables_objects):
                    candidate = tables_objects[t_idx]
                    if len(candidate.rows) == len(table):
                        table_obj = candidate
                
                indexes_info = detect_table_indexes(table)
                if indexes_info is None:
                    continue
                    
                idx_pcomm, idx_soc, idx_fab, header_row_idx = indexes_info
                
                last_valid_soc = ""
                last_valid_fab = ""
                
                for r_idx, row in enumerate(table):
                    if r_idx <= header_row_idx:
                        continue
                    if len(row) <= max(idx_pcomm, idx_soc, idx_fab):
                        continue
                    
                    pcomm_raw = row[idx_pcomm]
                    soc_raw = row[idx_soc]
                    fab_raw = row[idx_fab]
                    
                    # Skip header rows
                    pcomm_str = str(pcomm_raw or "").upper()
                    soc_str = str(soc_raw or "").upper()
                    if 'P.COMM' in pcomm_str or 'SOCIETE' in soc_str:
                        continue
                    
                    # Skip continuation rows or empty rows that don't contain any target columns
                    if not pcomm_raw and not soc_raw and not fab_raw:
                        continue
                    
                    # OCR Check: if the row has wraps or alignment fragments, run OCR on cell visual boxes
                    if table_obj and should_use_ocr(pcomm_raw or "", soc_raw or "", fab_raw or "", page_num, pdf_path):
                        pcomm_ocr = extract_cell_ocr(pdf_path, page_num, table_obj, r_idx, idx_pcomm)
                        soc_ocr = extract_cell_ocr(pdf_path, page_num, table_obj, r_idx, idx_soc)
                        fab_ocr = extract_cell_ocr(pdf_path, page_num, table_obj, r_idx, idx_fab)
                        
                        pcomm_val = pcomm_ocr if pcomm_ocr else (pcomm_raw or "")
                        soc_val = soc_ocr if soc_ocr else (soc_raw or "")
                        fab_val = fab_ocr if fab_ocr else (fab_raw or "")
                    else:
                        pcomm_val = pcomm_raw or ""
                        soc_val = soc_raw or ""
                        fab_val = fab_raw or ""
                    
                    # Clean spaces (retaining newlines)
                    pcomm_clean = clean_spaces(pcomm_val)
                    soc_clean = clean_spaces(soc_val)
                    fab_clean = clean_spaces(fab_val)
                    
                    # Cell-level forward fill with last valid complete names
                    if not soc_clean and last_valid_soc:
                        soc_clean = last_valid_soc
                    if not fab_clean and last_valid_fab:
                        fab_clean = last_valid_fab
                        
                    # Update last valid values (joining multiple lines with space for tracking)
                    if soc_clean:
                        soc_joined = " ".join(split_cell_entities(soc_clean))
                        if is_fragment(soc_joined) and last_valid_soc:
                            last_valid_soc = (last_valid_soc + " " + soc_joined).strip()
                        else:
                            last_valid_soc = soc_joined
                            
                    if fab_clean:
                        fab_joined = " ".join(split_cell_entities(fab_clean))
                        if is_fragment(fab_joined) and last_valid_fab:
                            last_valid_fab = (last_valid_fab + " " + fab_joined).strip()
                        else:
                            last_valid_fab = fab_joined
                    
                    # Split cells by newline
                    produits = split_cell_entities(pcomm_clean, is_prod=True)
                    societes = split_cell_entities(soc_clean)
                    fabricants = split_cell_entities(fab_clean)
                    
                    n = max(len(produits), len(societes), len(fabricants))
                    if n == 0:
                        continue
                        
                    for i in range(n):
                        prod = get_element_at(produits, i)
                        soc = get_element_at(societes, i)
                        fab = get_element_at(fabricants, i)
                        
                        if prod or soc or fab:
                            results.append({
                                'Produit_Commercial': prod,
                                'Société': soc,
                                'Fabricant': fab,
                                'source': pdf_path
                            })
                            
            if page_num % 20 == 0 or page_num == total_pages:
                print(f"Processed page {page_num}/{total_pages}")
                
    return results

def merge_fragments(df):
    records = df.to_dict('records')
    merged_records = []
    merged_count = 0
    
    for rec in records:
        prod = rec['Produit_Commercial']
        soc = rec['Société']
        fab = rec['Fabricant']
        source = rec.get('source', '')
        
        is_p_frag = is_fragment(prod)
        is_s_frag = is_fragment(soc)
        is_f_frag = is_fragment(fab)
        
        is_row_frag = (is_p_frag or is_s_frag or is_f_frag)
        if is_row_frag:
            # Exclude if both product and society are non-empty and non-fragments
            if prod and not is_p_frag and soc and not is_s_frag:
                is_row_frag = False
        
        # If any field is a fragment, the row is treated as a fragment row
        if is_row_frag and merged_records:
            prev_rec = merged_records[-1]
            same_source = (prev_rec.get('source', '') == source)
            
            if same_source:
                can_merge_prod = prod and not prev_rec['Produit_Commercial'].upper().endswith(prod.upper())
                can_merge_soc = soc and not prev_rec['Société'].upper().endswith(soc.upper())
                can_merge_fab = fab and not prev_rec['Fabricant'].upper().endswith(fab.upper())
                
                if can_merge_prod or can_merge_soc or can_merge_fab:
                    if can_merge_prod:
                        prev_rec['Produit_Commercial'] = (prev_rec['Produit_Commercial'] + " " + prod).strip()
                    if can_merge_soc:
                        prev_rec['Société'] = (prev_rec['Société'] + " " + soc).strip()
                    if can_merge_fab:
                        prev_rec['Fabricant'] = (prev_rec['Fabricant'] + " " + fab).strip()
                    merged_count += 1
                    continue
                    
        merged_records.append(rec)
        
    print(f"[+] Total fragments merged: {merged_count}")
    return pd.DataFrame(merged_records)

def split_slashed_entities(df):
    new_records = []
    for _, row in df.iterrows():
        prod = row['Produit_Commercial']
        soc = row['Société']
        fab = row['Fabricant']
        source = row.get('source', '')
        
        # Split Société by '/'
        soc_parts = [s.strip() for s in str(soc).split('/') if s.strip()]
        if not soc_parts:
            soc_parts = [str(soc)]
            
        # Split Fabricant by '/'
        fab_parts = [f.strip() for f in str(fab).split('/') if f.strip()]
        if not fab_parts:
            fab_parts = [str(fab)]
            
        # Generate cross product
        for s_part in soc_parts:
            for f_part in fab_parts:
                rec = {
                    'Produit_Commercial': prod,
                    'Société': s_part,
                    'Fabricant': f_part
                }
                if 'source' in row:
                    rec['source'] = source
                new_records.append(rec)
                
    return pd.DataFrame(new_records)

# Known OCR bad-reads → correct form. Populated from observed errors.
OCR_CORRECTIONS = {
    # JIANGYIN SULI CHEMICAL variants
    'JJANGY': 'JIANGYIN SULI CHEMICAL',
    'JJANGYIN': 'JIANGYIN SULI CHEMICAL',
    'JJANGYIN SULI CHEMICAL': 'JIANGYIN SULI CHEMICAL',
    'JTANGYIN SULI CHEMICAL': 'JIANGYIN SULI CHEMICAL',
    'JLANGY IN SULI CHEMICAL': 'JIANGYIN SULI CHEMICAL',
    'JIANGYIN SULI CHEMICA': 'JIANGYIN SULI CHEMICAL',
    # ALBAU is a truncated read of ALBAU GH EUROPE SARL
    'ALBAU': 'ALBAU GH EUROPE SARL',
    # Add more entries here as discovered
}


def apply_ocr_corrections(df, col):
    """Replace known OCR misreads with their correct canonical form."""
    fixed = 0
    def _fix(val):
        nonlocal fixed
        upper = str(val).strip().upper()
        for bad, good in OCR_CORRECTIONS.items():
            if upper == bad.upper():
                fixed += 1
                return good
        return val
    df = df.copy()
    df[col] = df[col].apply(_fix)
    print(f"[+] OCR hard corrections: {fixed} value(s) replaced in '{col}'.")
    return df


def filter_isolated_fragments(df):
    """
    Remove rows where the Fabricant field is *only* a fragment/country name
    AND the Société field doesn't help disambiguate (i.e. there exists a better
    row for the same (Produit, Société) pair with a real Fabricant).
    """
    fab_is_frag = df['Fabricant'].apply(lambda x: is_fragment(str(x).strip()))
    soc_is_frag = df['Société'].apply(lambda x: is_fragment(str(x).strip()))

    # For each (Produit, Société) pair, purge fragment Fabricant rows only if
    # a non-fragment Fabricant already exists for the same pair.
    key = df['Produit_Commercial'] + '|||' + df['Société']
    frag_keys = set(key[fab_is_frag])
    good_keys  = set(key[~fab_is_frag])
    to_drop = fab_is_frag & key.isin(frag_keys & good_keys)

    # Same logic for Société fragments
    key2 = df['Produit_Commercial'] + '|||' + df['Fabricant']
    frag_keys2 = set(key2[soc_is_frag])
    good_keys2  = set(key2[~soc_is_frag])
    to_drop2 = soc_is_frag & key2.isin(frag_keys2 & good_keys2)

    n_dropped = int((to_drop | to_drop2).sum())
    print(f"[+] Isolated-fragment filter: {n_dropped} parasitic row(s) removed.")
    df_clean = df[~(to_drop | to_drop2)].reset_index(drop=True)

    # Remove concatenation artifacts: rows where Produit_Commercial looks like
    # multiple product names fused together (> 6 distinct tokens).
    prod_token_count = df_clean['Produit_Commercial'].str.split().str.len().fillna(0)
    is_concat_artifact = prod_token_count > 6
    n_concat = int(is_concat_artifact.sum())
    if n_concat:
        print(f"[+] Concatenation artifact filter: {n_concat} fused-product row(s) removed.")
    return df_clean[~is_concat_artifact].reset_index(drop=True)


def normalize_ocr_variants(df, col='Fabricant', threshold=0.82):
    """
    Within each (Produit_Commercial, Société) group, consolidate OCR-garbled variants
    of the same string in `col` by fuzzy-matching them with difflib SequenceMatcher.
    
    For each cluster of similar strings, the canonical form is chosen as:
      - The most frequent value in the cluster, or
      - The longest one on tie.
    """
    import difflib

    def _canonical(cluster_values):
        """Pick the best representative from a list of similar strings."""
        from collections import Counter
        counts = Counter(cluster_values)
        max_count = max(counts.values())
        candidates = [v for v, c in counts.items() if c == max_count]
        # Among the most frequent, pick the longest (most complete OCR read)
        return max(candidates, key=len)

    def _cluster(values):
        """Greedy single-linkage clustering by SequenceMatcher ratio."""
        unique_vals = list(dict.fromkeys(values))  # preserve first-seen order, deduplicated
        clusters = []  # list of lists
        assigned = {}  # value -> cluster index

        for v in unique_vals:
            matched = False
            for idx, cluster in enumerate(clusters):
                rep = cluster[0]  # compare against the first element of the cluster
                ratio = difflib.SequenceMatcher(None, v.upper(), rep.upper()).ratio()
                if ratio >= threshold:
                    cluster.append(v)
                    assigned[v] = idx
                    matched = True
                    break
            if not matched:
                assigned[v] = len(clusters)
                clusters.append([v])

        # Build mapping: original value -> canonical
        mapping = {}
        for cluster in clusters:
            canon = _canonical(cluster)
            for v in cluster:
                mapping[v] = canon
        return mapping

    group_cols = ['Produit_Commercial', 'Société']
    df = df.copy()
    total_replaced = 0

    for key, group in df.groupby(group_cols, sort=False):
        vals = group[col].tolist()
        if len(set(vals)) <= 1:
            continue  # Nothing to normalize
        mapping = _cluster(vals)
        replacements = {v: c for v, c in mapping.items() if v != c}
        if replacements:
            mask = df[group_cols[0]] == key[0]
            if len(group_cols) > 1:
                mask &= df[group_cols[1]] == key[1]
            df.loc[mask, col] = df.loc[mask, col].map(lambda x: mapping.get(x, x))
            total_replaced += len(replacements)

    print(f"[+] OCR normalization: {total_replaced} variant(s) consolidated in '{col}'.")
    return df


def main():
    pdfs = [
        "pdf/liste-des-pesticides-homologues-en-tunisie_13-02-2020.pdf",
        "pdf/liste-des-pesticides-homologues-27-dec-2022-.pdf",
        "pdf/liste-des-produits-pesticides-homologues_ver.finale-19-avril-2023.pdf",
        "pdf/liste-des-produits-homologues-22-mai-2024.pdf",
        "pdf/liste-des-produits-pesticides-homologues-16-juillet-2025-vf-1.pdf"
    ]
    
    from concurrent.futures import ProcessPoolExecutor
    import json
    cache_file = "scratch/extracted_raw_cache.json"
    
    all_records = []
    if os.path.exists(cache_file):
        print(f"Loading raw records from cache file: {cache_file}")
        with open(cache_file, "r", encoding="utf-8") as f:
            all_records = json.load(f)
    else:
        from concurrent.futures import ProcessPoolExecutor
        existing_pdfs = [pdf for pdf in pdfs if os.path.exists(pdf)]
        for pdf in pdfs:
            if not os.path.exists(pdf):
                print(f"File not found: {pdf}")
                
        print(f"Starting parallel processing of {len(existing_pdfs)} PDFs...")
        with ProcessPoolExecutor() as executor:
            results = list(executor.map(process_pdf, existing_pdfs))
            for pdf, records in zip(existing_pdfs, results):
                all_records.extend(records)
                print(f"Extracted {len(records)} raw entries from {pdf}")
                
        try:
            os.makedirs("scratch", exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(all_records, f, ensure_ascii=False, indent=2)
            print(f"Saved raw records to cache: {cache_file}")
        except Exception as e:
            print(f"[-] Failed to save cache: {e}")
            
    df_all = pd.DataFrame(all_records)
    print(f"Total raw entries extracted: {len(df_all)}")
    
    # Clean up nan strings
    df_all = df_all.replace('nan', '')
    df_all = df_all.fillna('')
    
    # Remove leading/trailing spaces
    df_all['Produit_Commercial'] = df_all['Produit_Commercial'].str.strip()
    df_all['Société'] = df_all['Société'].str.strip()
    df_all['Fabricant'] = df_all['Fabricant'].str.strip()
    
    # Apply fragment merging
    df_merged = merge_fragments(df_all)
    
    # Forward-fill any remaining empty values within each PDF source
    df_merged['Société'] = df_merged['Société'].replace('', np.nan)
    df_merged['Société'] = df_merged.groupby('source')['Société'].ffill().fillna('')
    df_merged['Fabricant'] = df_merged['Fabricant'].replace('', np.nan)
    df_merged['Fabricant'] = df_merged.groupby('source')['Fabricant'].ffill().fillna('')
    
    # Clean up again after merging/filling (applying strict normalization from Request 1)
    df_merged['Produit_Commercial'] = df_merged['Produit_Commercial'].str.strip().str.replace(r'\s+', ' ', regex=True)
    df_merged['Société'] = df_merged['Société'].str.strip().str.replace(r'\s+', ' ', regex=True).str.upper()
    df_merged['Fabricant'] = df_merged['Fabricant'].str.strip().str.replace(r'\s+', ' ', regex=True)
    
    # Split slashed entities in Société and Fabricant and duplicate rows
    print(f"[DEBUG] Row count before split: {len(df_merged)}")
    df_merged = split_slashed_entities(df_merged)
    print(f"[DEBUG] Row count after split: {len(df_merged)}")
    
    # Clean up again after splitting (applying strict normalization to the newly split parts)
    df_merged['Société'] = df_merged['Société'].str.strip().str.replace(r'\s+', ' ', regex=True).str.upper()
    df_merged['Fabricant'] = df_merged['Fabricant'].str.strip().str.replace(r'\s+', ' ', regex=True)
    
    # Remove empty rows or incomplete rows where both Produit and Société are empty
    df_merged = df_merged[
        (df_merged['Produit_Commercial'] != '') & 
        (df_merged['Société'] != '')
    ]
    
    # Drop source column before deduplication
    if 'source' in df_merged.columns:
        df_merged = df_merged.drop(columns=['source'])
        
    print('Normalizing OCR variants (Fabricant)...')
    df_merged = normalize_ocr_variants(df_merged, col='Fabricant', threshold=0.82)
    # Also normalize Société variants
    df_merged = normalize_ocr_variants(df_merged, col='Société', threshold=0.85)

    # Hard-coded OCR corrections for known bad reads
    df_merged = apply_ocr_corrections(df_merged, col='Fabricant')
    df_merged = apply_ocr_corrections(df_merged, col='Société')

    # Deduplicate first, then remove parasitic fragment-only rows
    df_dedup = df_merged.drop_duplicates()
    df_dedup = filter_isolated_fragments(df_dedup)
    df_dedup = df_dedup.sort_values(by=['Société', 'Produit_Commercial'])
    
    # Export to root CWD
    output_path = "dictionnaire_exhaustif_complet.csv"
    abs_path = os.path.abspath(output_path)
    print(f"Exporting to absolute path: {abs_path}")
    df_dedup.to_csv(abs_path, index=False, encoding='utf-8-sig')
    print(f"Deduplicated to {len(df_dedup)} unique entries. Exported to {abs_path}")

if __name__ == "__main__":
    main()
