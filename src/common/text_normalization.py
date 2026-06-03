# -*- coding: utf-8 -*-
"""
src/common/text_normalization.py
Text cleaning, diacritic removal, translation, and chemical name normalization helpers.
"""
import re
import math
import unicodedata
from typing import Any

def normalize_text(value: Any) -> str:
    """
    Lowercase, strip diacritics/accents, normalize whitespace and quotes.
    Handles numeric NaN cases gracefully by returning an empty string.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("’", "'").replace("`", "'").replace("´", "'")
    s = s.replace("piége", "piege").replace("piège", "piege")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def clean_substance_name_for_match(value: Any) -> str:
    """
    Normalizes a substance name for matching against the EU active substances database:
    - Removes complex dose, spore counts, percentages, and measurement units.
    - Standardizes terms and translations (e.g. French 'huile' -> English 'oil').
    - Standardizes common active substance spelling variants (e.g. abamectine -> abamectin).
    """
    s = str(value or "").strip().lower()
    if not s:
        return ""
    
    # 1. Lowercase and normalize accents
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("’", "'").replace("`", "'").replace("´", "'")

    # 2. Remove complex doses/concentrations (e.g. 1.1*10^10 spores/g, 7.5 1012 cfu/l, 5%, g/l, mg/kg, etc.)
    s = re.sub(
        r"\b\d+[\d.,*xX^eE\-\s/]*(?:spores/g|spores/l|spores|ufc/g|ufc/l|ufc|cfu/g|cfu/l|cfu|ui/mg|ui/g|ui|corps viraux/litre|corps viraux|g/l|g/kg|mg/kg|mg/l|%)\b",
        " ", s, flags=re.IGNORECASE
    )
    s = re.sub(
        r"\b(min|max)\b\s*[\d.,]+\s*[a-z/%µ]+(?:/[a-z]+)?",
        " ", s, flags=re.IGNORECASE
    )
    s = re.sub(
        r"\b[\d.,]+\s*(?:g|kg|mg|ug|µg|ml|l|%)(?:/[a-zA-Z]+)?",
        " ", s, flags=re.IGNORECASE
    )

    # Strip parentheses characters but keep contents
    s = s.replace("(", " ").replace(")", " ")

    # Remove "a base d'" / "a base de" / "based on"
    s = re.sub(r"\ba\s+base\s+d[’']", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\ba\s+base\s+de\s+", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bbased\s+on\s+", " ", s, flags=re.IGNORECASE)

    # Translations of common French terms to English
    s = re.sub(r"\bsouche\b", "strain", s, flags=re.IGNORECASE)
    s = re.sub(r"\bhuiles?\b", "oil", s, flags=re.IGNORECASE)
    s = re.sub(r"\bsel\s+de\b", "salt", s, flags=re.IGNORECASE)
    s = re.sub(r"\bsel\s+d'\b", "salt ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bsel\b", "salt", s, flags=re.IGNORECASE)
    s = re.sub(r"\bcuivre\b", "copper", s, flags=re.IGNORECASE)
    s = re.sub(r"\bsoufre\b", "sulphur", s, flags=re.IGNORECASE)
    s = re.sub(r"\bacide\b", "acid", s, flags=re.IGNORECASE)
    s = re.sub(r"\bextrait\b", "extract", s, flags=re.IGNORECASE)
    s = re.sub(r"\bpheromones?\b", "pheromone", s, flags=re.IGNORECASE)
    s = re.sub(r"\bsp\b\.?", "subsp", s, flags=re.IGNORECASE)
    s = re.sub(r"\bsubsp\b\.?", "subsp", s, flags=re.IGNORECASE)

    # Spelling corrections and standardizations
    s = re.sub(r"\bazadirachtine?\b", "azadirachtin", s, flags=re.IGNORECASE)
    s = re.sub(r"\blamb[ad]*a[\s-]*cyhalothrine?\b", "lambda-cyhalothrin", s, flags=re.IGNORECASE)
    s = re.sub(r"\bacetam[ei]pride?\b", "acetamiprid", s, flags=re.IGNORECASE)
    s = re.sub(r"\babamectine?\b", "abamectin", s, flags=re.IGNORECASE)
    s = re.sub(r"\bchlorpyri\s*phos\b", "chlorpyrifos", s, flags=re.IGNORECASE)
    s = re.sub(r"\bchlorpyrifos[\s-]+ethyl\b", "chlorpyrifos", s, flags=re.IGNORECASE)
    s = re.sub(r"\bimidach?lopride?\b", "imidacloprid", s, flags=re.IGNORECASE)
    s = re.sub(r"\bcypermethrine?\b", "cypermethrin", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdeltamethrine?\b", "deltamethrin", s, flags=re.IGNORECASE)
    s = re.sub(r"\bthiameth?oxame?\b", "thiamethoxam", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdimethoate?\b", "dimethoate", s, flags=re.IGNORECASE)
    s = re.sub(r"\blufenurone?\b", "lufenuron", s, flags=re.IGNORECASE)
    s = re.sub(r"\bmetam\s+(?:sodium|potassium)\b", "metam", s, flags=re.IGNORECASE)
    s = re.sub(r"\bphosphure\s+d[’']\s*al\b\.?", "aluminium phosphide", s, flags=re.IGNORECASE)
    s = re.sub(r"\bphosphure\s+d[’']\s*hy\b\.?", "phosphane", s, flags=re.IGNORECASE)
    s = re.sub(r"\bphosphure\s+de\s+magnesium\b", "magnesium phosphide", s, flags=re.IGNORECASE)
    
    s = re.sub(r"\bacetate\s+d[’']\s*ammonium\b", "ammonium acetate", s, flags=re.IGNORECASE)
    s = re.sub(r"\bhydrochlorure\s+de\s+trimethylamine\b", "trimethylamine hydrochloride", s, flags=re.IGNORECASE)
    s = re.sub(r"\barylex\s*active\b", "halauxifen-methyl", s, flags=re.IGNORECASE)
    s = re.sub(r"\bisoxabene?\b", "isoxaben", s, flags=re.IGNORECASE)
    s = re.sub(r"\bcycloxidime?\b", "cycloxydim", s, flags=re.IGNORECASE)
    s = re.sub(r"\bpropicinazole?\b", "propiconazole", s, flags=re.IGNORECASE)
    s = re.sub(r"\bpropiconazole?\b", "propiconazole", s, flags=re.IGNORECASE)
    s = re.sub(r"\bchlorothalonil\s+l\b", "chlorothalonil", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdimethomophe?\b", "dimethomorph", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdimethomorphe?\b", "dimethomorph", s, flags=re.IGNORECASE)
    s = re.sub(r"\bt+rifloxystrobine?\b", "trifloxystrobin", s, flags=re.IGNORECASE)

    # Copper compounds collapsing
    if "hydroxyde" in s and ("cuivre" in s or "copper" in s):
        s = "copper hydroxide"
    elif "oxychlorure" in s and ("cuivre" in s or "copper" in s):
        s = "copper oxychloride"
    elif "sulfate" in s and ("cuivre" in s or "copper" in s):
        s = "copper sulfate"
    elif "oxyde" in s and ("cuivre" in s or "copper" in s):
        s = "copper oxide"

    # Remove functional categories
    s = re.sub(
        r"\b(insecticide|fongicide|herbicide|acaricide|rodenticide|nematicide)\b",
        " ", s, flags=re.IGNORECASE
    )
    s = re.sub(
        r"\b(sachet|piege|ec|sc|wp|sl|dg|gr|fs|ks|mg|ml|l|kg|g)\b",
        " ", s, flags=re.IGNORECASE
    )

    # Spaces and commas normalization
    s = s.replace(",", " ")
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"[^a-z0-9+\- ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # Deduplicate consecutive repeating words (e.g. "bacillus thuringiensis bacillus thuringiensis")
    tokens = s.split()
    if len(tokens) >= 2:
        half = len(tokens) // 2
        if tokens[:half] == tokens[half:]:
            s = " ".join(tokens[:half])

    return s

def is_trivial_token(token: str) -> bool:
    """
    Identifies if a string is a non-significant fragment (units, short signs, numbers).
    """
    t = token.strip()
    if not t:
        return True
    if len(t) < 2:
        return True
    if re.fullmatch(r"[\d\-\+/\\%]+", t):
        return True
    if t in ["g", "kg", "mg", "ml", "l", "%", "h", "a", "e", "x", "i"]:
        return True
    if re.fullmatch(r"[^a-z]+", t, flags=re.IGNORECASE):
        return True
    return False
