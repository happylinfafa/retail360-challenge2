# Retail360 — Challenge 2

A small Streamlit application for retail analysts to inspect customer behavior and review an evidence-grounded AI explanation.

## The task

Select a real customer and observation period. Python calculates recency, invoice frequency, positive purchase amount, average invoice value, and distinct product codes. Structured retrieval assembles invoice aggregates and source rows. A local Qwen2.5 1.5B model running through Ollama explains those results. The user inspects evidence, changes filters, requests clarification, and records an acceptance, rejection, or correction.

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

No database or full workbook is needed for the bundled demonstration.

## Free local AI (no key or paid service)

Install Ollama from https://ollama.com/download/windows (macOS/Linux versions are also available). Open a terminal and run:

```sh
ollama pull qwen2.5:1.5b
```

Start Ollama, then run Streamlit. Click **Refresh model status**, select a customer, and click **Generate AI explanation**. The model is about 986 MB; the Ollama runtime requires additional disk space. Initial downloads require internet; inference runs locally after download. No OpenAI account, subscription, API key, or paid credit is required. Generation uses your computer's memory and may take a few minutes on CPU.

The application sends evidence only to `127.0.0.1:11434`, the Ollama service on the same computer. It uses only the fixed local model `qwen2.5:1.5b`; it does not offer cloud models. Technically this is a local HTTP interface, not a paid online API. This setup is intended for local demonstration; deploying Streamlit alone to a cloud host will not carry over your local model.

If Ollama is unavailable, calculations and evidence review remain usable, but the application does not invent an AI answer. Failed numeric/provenance checks display an error instead of an explanation.

Model: https://ollama.com/library/qwen2.5:1.5b (Apache 2.0). Runtime: https://github.com/ollama/ollama. Structured output: https://docs.ollama.com/capabilities/structured-outputs.

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

`analytics.py` performs exact calculations and retrieval. `ai.py` sends fixed facts and complete computed features and up to ten recent invoice examples to an LLM. `app.py` shows the result and evidence. The model generates explanations and limitations. Python attaches each metric value and source-reference keys directly from the evidence package. The validator checks the assembled customer, numbers and references, and rejects numerical prose outside the relevant supplied facts and exact source dates. This mechanical validation does not prove the prose is semantically correct. Human review is required, especially for unsupported comparative or causal claims.

Reviews remain in session memory until downloaded as JSON. The record identifies the evidence hash and model response. Filter or focus/model changes clear the old AI result, preventing it from appearing under a different customer. A review without a model response is explicitly labeled `computed_evidence_only`.

## Tests

```sh
python -m pytest -q
```

Tests cover real-data calculations, date refinement, row provenance, missing customers/evidence, cancellations, output validation, and Streamlit review interaction. Provider calls in unit tests are mocks and must never be reported as live model evaluation. See `docs/test_results.md` for the current execution status.

## Scope and next steps

Human Design defined customer features. AI Design selected exact structured retrieval and grounded explanation. Human–AI Co-Design adds user filters, invoice inspection, clarification, and explicit review. Codex assisted implementation and debugging. No vector database or multi-agent framework is needed.

Local model generation must be evaluated separately from mocked transport tests. Later work includes broader customer tests, semantic evaluation of explanations, verified duplicate/refund rules, customer segmentation, and eventually community features and 60-day prediction. The current app does not predict churn.

## Local validation

Run python scripts/evaluate_local.py with Ollama running to execute five real-model cases; results are saved to docs/local_model_results.json. These are distinct from the eight offline regression tests. Inspect the wording manually: a valid number alone does not establish that an interpretation is correct. Historical recency refers to the selected analysis date, not today.

The model input is deliberately smaller than the evidence store: full invoice and row tables remain accessible in Streamlit, while the local model receives computed all-history metrics and an explicitly labeled subset of recent invoices. This prevents long histories from overwhelming the small model.
