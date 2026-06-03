# Workflow: Pesticide Reconciliation Pipeline

This workflow outlines the procedures, business rules, execution sequences, and safety guidelines for maintaining and extending the Tunisian Pesticides to EU active substances database reconciliation pipeline.

---

## 1. Project Goal
Establish a repeatable, traceable, and offline-capable data pipeline to split complex commercial pesticide mixtures into their constituent active substances, match them against the European Union (EU) database, compile manual review queues, and reinject decisions to compute product-level regulatory compliance status.

---

## 2. Core Business Rules

1. **Multi-Slot Review Queue**:
   * The manual review queue MUST be product-level (one row per product).
   * Active substance mixtures are split into individual unit slots (`substance_unit_1` to `substance_unit_N`, up to a dynamic maximum of 4 slots).
   * Each slot must display its top 5 candidates with status, similarity scores, and details URLs.

2. **Strict Product-Level Approval**:
   * A product is marked as approved (`product_is_approved` = `True`) if and only if:
     1. It contains at least one active substance.
     2. **Every** constituent active substance is successfully mapped and has status `'Approved'` in the EU database.
   * If any substance is unresolved, rejected, needs research, or is not approved, the product is NOT approved.

3. **Gated LLM Arbitration**:
   * LLMs (Ollama `qwen3:14b`) should only assist in selecting candidate recommendations for ambiguous matches (scores between `40` and `75`).
   * The LLM is strictly forbidden from proposing or selecting any candidate not included in the provided candidate shortlist.
   * Final regulatory approval is determined by the reference database entries, not decided directly by the LLM.

4. **Regulatory Preservation**:
   * Do not flatten or delete raw regulatory metrics.
   * Retain details, approval dates, risk flags (`low`, `medium`, `high`), and candidate for substitution metrics for auditability.

---

## 3. Pipeline Execution Sequence

Executions should follow this strict sequence:

```bash
# Step 1: Download Reference Database
python scripts/01_download_db.py

# Step 2: Extract mixture slots and generate manual review queue
python scripts/build_manual_review_queue.py --enable-embeddings

# Step 3: (Manual review of data/interim/manual_review_queue.csv by human)

# Step 4: Reinject decisions and compile final compliance metrics
python scripts/reinject_decisions.py
```

---

## 4. Expected Inputs & Outputs

### Inputs
* Raw Tunisian Products CSV: `data/input/pesticides_tn_checked2.csv` (requires columns `Produit Commercial` and `Substance Active`).
* Reference EU Database: `data/reference/eu_active_substances_full.csv` (contains `substance_id`, `substance_name`, `substance_status`, and regulatory flags).
* Persistent Mapping Memory: `data/interim/manual_mapping.csv` (stores confirmed translations to skip manual checks in future runs).

### Outputs
* Recomposed Matching Sheet: `data/interim/pesticides_tn_eu_2_review.csv` (all raw columns annotated with split slots).
* Manual Review Queue: `data/interim/manual_review_queue.csv` (multi-slot file containing items with similarity scores $< 95\%$).
* Reconciled Clean Dataset: `data/output/pesticides_tn_clean.csv` (adds `product_is_approved`, `eu_regulatory_risk_flag`, and details).

---

## 5. Change Safety & Normalization Rules

To prevent regression during matching updates, the following text translation and normalization rules must be strictly preserved:

* **Diacritic & Accent Removal**: Strip all accents (e.g. `Alphaméthrine` $\rightarrow$ `alphamethrine`).
* **Dose & Unit Stripping**: Extract and remove spores counts, percentages, and doses (e.g., `10%`, `480 g/l`, `1x10^10 spores/g`) to isolate the raw substance names.
* **French to English Translation**:
  * `huile` / `huiles` $\rightarrow$ `oil`
  * `cuivre` $\rightarrow$ `copper`
  * `soufre` $\rightarrow$ `sulphur`
  * `sel` / `sel de` $\rightarrow$ `salt`
* **Spelling Standardization**: Map common variants (e.g. `abamectine` $\rightarrow$ `abamectin`, `deltamethrine` $\rightarrow$ `deltamethrin`, `chlorpyriphos` $\rightarrow$ `chlorpyrifos`).
* **Copper Compounding Collapse**: Ensure copper compounds containing `hydroxyde`, `oxychlorure`, `sulfate`, or `oxyde` resolve respectively to `copper hydroxide`, `copper oxychloride`, `copper sulfate`, and `copper oxide`.
* **Lambda-cyhalothrin & Chlorpyrifos-ethyl**: Ensure patterns match both space-separated and hyphenated formats (e.g. `lambda-cyhalothrin` or `lambda cyhalothrin`, `chlorpyrifos-ethyl` or `chlorpyrifos ethyl`).

---

## 6. Testing & Acceptance Policy

1. **Test Coverage**:
   * All modules inside `src/` must have corresponding test files in the `tests/` directory.
   * Unit tests must mock network connections or Ollama clients using patch objects to run offline without a local Ollama server running.

2. **Acceptance Criteria**:
   * Executing `python -m pytest` must return **100% green** (no failures).
   * Any change to `src/common/text_normalization.py` must be tested against the full range of spelling variations in `tests/test_normalization.py`.
   * Any change to reinjection logic must run successfully against product-level approval checks in `tests/test_manual_review_reinjection.py`.
