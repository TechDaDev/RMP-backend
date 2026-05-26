# External Medical Sources Exploration (RMP)

This folder contains standalone Python scripts for testing external medical data APIs and analyzing their response structures before any integration into Django production code.

## Scope
- API exploration only.
- Response structure inspection only.
- Field selection planning for future local catalog import.
- No Django model creation.
- No production API integration.

## Files
- `test_rxnorm_api.py`: Tests RxNorm/RxNav endpoints for drug concept normalization (RxCUI, names, synonyms, TTY, ranking).
- `test_openfda_api.py`: Tests openFDA drug label endpoint for clinical enrichment fields (warnings, contraindications, adverse reactions, dosage, etc.).
- `test_loinc_api.py`: Tests LOINC FHIR terminology expansion for lab terminology mapping (code, display, designations, properties).
- `test_drugbank_api.py`: Tests DrugBank only when `DRUGBANK_API_KEY` is available; otherwise skips gracefully.
- `analyze_api_responses.py`: Reads generated JSON outputs and creates final planning report.
- `outputs/`: Stores generated JSON and Markdown artifacts.

## Requirements
Install required package:

```bash
pip install -r requirements.txt
```

## Environment Variables
Optional/required variables by script:

- LOINC (required for real LOINC calls):
  - `LOINC_USERNAME`
  - `LOINC_PASSWORD`

- DrugBank (required for real DrugBank calls):
  - `DRUGBANK_API_KEY`
  - Optional override: `DRUGBANK_BASE_URL` (default `https://api.drugbank.com/v1`)

If missing:
- LOINC script still generates output files with a clear "skipped due to missing credentials" note.
- DrugBank script still generates output files with a clear "skipped due to missing API key" note.

## How To Run
From this folder:

```bash
python test_rxnorm_api.py
python test_openfda_api.py
python test_loinc_api.py
python test_drugbank_api.py
python analyze_api_responses.py
```

## Output Files
For each service, scripts generate:
- `outputs/{service_name}_raw_results.json`
- `outputs/{service_name}_simplified_results.json`
- `outputs/{service_name}_field_analysis.json`

Generated report:
- `outputs/external_medical_sources_report.md`

## How To Interpret The Report
The report includes:
- Which APIs were tested and with what terms.
- Important fields observed per source.
- Recommended fields for future local storage.
- Fields to ignore for now.
- Weaknesses and inconsistencies in source responses.
- Final recommendation for local-first RMP catalog strategy.

Use this report to design future import/sync pipelines and local database schema decisions, while keeping production autocomplete local.
