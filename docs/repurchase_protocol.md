# Frozen 60-day repurchase protocol — v1

## Purpose and scope

Predict whether an existing customer makes a valid purchase in the next 60 days. This is an observed purchase outcome at this retailer, not a causal marketing effect or a definitive churn label. This document freezes data preparation rules. The subsequent baseline training and historical prediction page are documented in [model results](model_results.md); graph ablations remain unfinished.

The teacher requires a fixed cutoff, future-only labels, chronological evaluation and explicit customer eligibility. The 180-day lookback, minimum one historical invoice and dates below are our implementation choices, frozen before model comparison.

## Windows and labels

For a prediction cutoff `t` at midnight, historical evidence is `[t - 180 days, t)`. The label window is `[t, t + 60 days)`. The left boundary is included and the right boundary excluded. A transaction exactly at the cutoff can affect the label but never the features.

A customer is eligible only if they have at least one distinct valid invoice within the historical window. Eligibility does not depend on future activity. Customers first appearing after the cutoff and customers without purchases in the historical window are outside this task. Frequency counts invoices, not product rows.

`repurchase_60d = 1` means at least one valid purchase during the label window. Otherwise it is `0`, provided the source covers the entire 60 days. Insufficient follow-up causes an error instead of an assumed zero. This assumes the supplied dataset covers the retailer's transactions continuously; individual customer activity outside this retailer is unknown.

Source coverage is conservatively treated as `[2009-12-01, 2011-12-09)`: the final partial day is excluded from the declared complete coverage. The workbook is pinned by SHA-256 in `config/repurchase_protocol.json`; a different source requires explicit protocol review.

| Partition | Prediction cutoff | Label end (exclusive) |
| --- | --- | --- |
| Train | 2010-09-01 | 2010-10-31 |
| Train | 2010-12-01 | 2011-01-30 |
| Train | 2011-03-01 | 2011-04-30 |
| Validation | 2011-06-01 | 2011-07-31 |
| Test | 2011-09-01 | 2011-10-31 |

Each earlier partition's labels are completely observable before the next partition's cutoff. Customers may recur across snapshots: the intended use is predicting later behavior of existing customers. Do not randomly split customer-snapshot rows. Historical windows may overlap; repeated customers are not independent observations, which must be considered when estimating uncertainty later.

## Cleaning and feature definitions

Read both sheets of the full UCI Online Retail II workbook. The bundled three-customer demonstration CSV is not the training dataset. Exclude missing customer/invoice/product IDs, invalid dates or numbers, C-prefixed invoices, and non-positive quantities or prices. Exclusion counts use the first detected reason. Keep repeated original rows because their duplicate status is unverified; this can affect spending totals and is a limitation. Returns are excluded rather than reconciled, so monetary values represent retained positive purchases, not net revenue.

Each line amount is rounded half-up to integer pennies before aggregation. The feature allowlist is:

| Feature | Historical calculation |
| --- | --- |
| recency_days | Calendar days since the latest retained purchase |
| frequency | Number of distinct invoices |
| monetary_gbp | Sum of retained line amounts |
| aov_gbp | Monetary value divided by invoice count |
| product_diversity | Number of distinct product codes |
| orders_last_30d | Distinct invoices whose first retained timestamp is in the last 30 days |
| active_purchase_days | Distinct calendar purchase dates |
| mean_invoice_gap_days | Mean elapsed days between ordered invoice timestamps; missing for one invoice |

Product diversity is a baseline feature, not proof of a graph contribution. Subsequent graph features must add information beyond these baseline features and use historical transactions only.

## Reproduction and evidence

Download the original workbook from https://archive.ics.uci.edu/dataset/502/online+retail+ii and run from the repository:

```sh
python scripts/prepare_repurchase.py /path/to/online_retail_II.xlsx
python -m pytest -q -p no:cacheprovider
```

Outputs are generated under `data/repurchase_v1/`, excluded from Git. The command refuses to overwrite a nonempty directory; use a different `--output` for a reviewed rerun. The manifest records the source checksum, cleaning counts, frozen protocol, feature allowlist and per-snapshot counts.

Every partition/cutoff folder contains `features.csv`, `labels.csv`, `audit.csv`, `history_transactions.csv.gz` and `label_transactions.csv.gz`. The primary key is `(cutoff, CustomerID)`. Source rows retain worksheet and original Excel row number in `RowID`; the manifest identifies the workbook. Audit metadata includes historical timestamps and last observed country for later subgroup evaluation.

## Rules for the next modeling stage

Only the explicit feature allowlist may enter baseline models. Customer IDs, cutoff keys, label counts, future purchase timestamps and audit metadata are not predictors. Labels and future source transactions are stored separately for evaluation and must never enter historical feature or graph construction.

Fit imputation, scaling, clustering and predictive models on training data only. Choose hyperparameters and thresholds using validation data; reserve test model scores for final evaluation. A missing single-invoice gap must be imputed using training data, not information from later partitions. Any unsupervised graph/community computation for a snapshot must use only evidence available before that snapshot's cutoff. Add a genuine graph feature and compare it against the same baseline, split and evaluation protocol.

Tests check window endpoints, future-data invariance, invoice-level eligibility, insufficient coverage, source cleaning and provenance, and the guard against future feature inputs. Existing application tests are retained. These checks validate the data pipeline; they do not establish predictive performance.
