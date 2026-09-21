# Retail360 — Challenge 2

A small Streamlit application for retail analysts to inspect customer behavior and review an evidence-grounded AI explanation.

## The task

Select a real customer and observation period. Python calculates recency, invoice frequency, positive purchase amount, average invoice value, and distinct product codes. Structured retrieval assembles invoice aggregates and source rows. A live OpenAI Responses API call explains those results. The user inspects evidence, changes filters, requests clarification, and records an acceptance, rejection, or correction.

## Run locally

Python 3.12 is recommended.

```sh
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

No database or full workbook is needed for the bundled demonstration. Without an API key the calculations, evidence inspection, filtering, and evidence review work. The app explicitly states that no AI explanation has been generated.

## Connect live AI

Create a project API key at https://platform.openai.com/api-keys and ensure that the API project has usable billing/quota. Enter the key in the app sidebar password field. Alternatively set `OPENAI_API_KEY` in the process environment. Enter a model available to your API account that supports the Responses API and JSON Schema structured output. The default is `gpt-4.1-mini`; account access is not assumed. Set `OPENAI_MODEL` to override it.

The app sends selected public UCI evidence to OpenAI only when Generate is clicked. It uses `store=False`. Keys are not written to files, evidence downloads, review records, or Git. Do not commit keys. A failed provider request produces a visible error, never a fabricated AI answer.

## Real data and provenance

Source: Chen, D. (2012). **Online Retail II**. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D

Dataset: https://archive.ics.uci.edu/dataset/502/online+retail+ii

Data license: **CC BY 4.0**. The CSV is a transformed subset containing complete source histories for customers 13085, 12347, and 17850, plus six missing-ID audit records. It is a demonstration sample, not a representative customer population. Original values are preserved as strings/dates; column names are normalized, descriptions trimmed, and workbook/worksheet/Excel-row provenance added. `data/manifest.json` records the source hash and extraction scope.

To rebuild after downloading the official workbook:

```sh
python scripts/prepare_sample.py /path/to/online_retail_II.xlsx
```

## Calculation rules

Observation start is inclusive; end is exclusive and also the recency reference date. Defaults cover the full source period, 2009-12-01 through 2011-12-09. This descriptive task is separate from the later 180-day predictive window.

Exclude missing customer/invoice/product IDs, C-prefixed invoices, non-positive quantities/prices, and invalid dates/numerics. Excluded customer rows remain in the audit view. Decimal line amounts are rounded half-up to pennies before aggregation. Frequency counts distinct invoice IDs, not transaction rows. Monetary is retained positive purchases, not refund-reconciled net revenue. Exact repeated source rows remain visible because duplicate status has not been independently established.

## AI, evidence, and human review

`analytics.py` performs exact calculations and retrieval. `ai.py` sends fixed facts and complete invoice aggregates to an LLM. `app.py` shows the result and evidence. Each AI claim names a metric, exact value, and evidence keys. The validator rejects wrong customers, numbers, missing metrics, or invalid references. This mechanical validation does not prove the prose is semantically correct. Human review is required, especially for unsupported comparative or causal claims.

Reviews remain in session memory until downloaded as JSON. The record identifies the evidence hash and model response. Filter or focus/model changes clear the old AI result, preventing it from appearing under a different customer. A review without a model response is explicitly labeled `computed_evidence_only`.

## Tests

```sh
python -m pytest -q
```

Tests cover real-data calculations, date refinement, row provenance, missing customers/evidence, cancellations, output validation, and Streamlit review interaction. Provider calls in unit tests are mocks and must never be reported as live model evaluation. See `docs/test_results.md` for the current execution status.

## Scope and next steps

Human Design defined customer features. AI Design selected exact structured retrieval and grounded explanation. Human–AI Co-Design adds user filters, invoice inspection, clarification, and explicit review. Codex assisted implementation and debugging. No vector database or multi-agent framework is needed.

Live API evaluation requires a configured key. Later work includes broader customer tests, semantic evaluation of explanations, verified duplicate/refund rules, customer segmentation, and eventually community features and 60-day prediction. The current app does not predict churn.
