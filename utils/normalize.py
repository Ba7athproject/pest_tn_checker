# -*- coding: utf-8 -*-
"""
utils/normalize.py
Forwarding module to preserve legacy imports while removing duplicated logic.
All implementations are now imported from centralized src.common modules.
"""
from src.common.text_normalization import (
    normalize_text,
    clean_substance_name_for_match,
    is_trivial_token,
)
from src.common.substance_splitting import (
    split_substances_advanced,
    split_and_extract_substances,
)
