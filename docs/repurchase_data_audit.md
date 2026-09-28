# Data foundation verification — 2026-09-28

Protocol: `repurchase-180d-60d-v1`. Full workbook processed successfully: 1,067,371 original rows, 805,549 valid positive purchase rows retained. First-reason exclusions: 243,007 missing customer IDs, 18,744 cancellation invoices, 71 non-positive prices. Source checksum and complete machine-readable results are stored in the generated `data/repurchase_v1/manifest.json`.

| Split | Cutoff | Customers | Positive labels | Negative labels |
| --- | --- | ---: | ---: | ---: |
| Train | 2010-09-01 | 2,831 | 1,413 | 1,418 |
| Train | 2010-12-01 | 3,479 | 1,072 | 2,407 |
| Train | 2011-03-01 | 3,349 | 1,116 | 2,233 |
| Validation | 2011-06-01 | 2,659 | 1,130 | 1,529 |
| Test | 2011-09-01 | 2,772 | 1,360 | 1,412 |

There are 9,659 training customer-snapshot rows, not 9,659 distinct people. Customer IDs may recur across dates. Counts describe this fixed eligibility rule; they do not describe every original customer.

Executed `python -m pytest -q -p no:cacheprovider`: **16 passed** (8 existing application tests and 8 new temporal-data tests). An empty-future datetime mapping error was found and corrected; the zero-repurchase case now passes. The full real workbook also completed all five snapshot exports successfully.

No model was trained, no prediction performance is claimed, and no new live LLM tests were needed for this data-only change. Generated benchmark files remain local and ignored by Git. Existing working-tree changes were preserved.
