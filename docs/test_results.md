# Test execution status — local model version

Executed September 21, 2026. Python 3.12, Streamlit 1.64.0, pandas 3.0.1, pytest 9.1.1. Ollama 0.34.2 with Qwen2.5 1.5B (Q4_K_M), CPU execution on a Windows computer with 12 GB installed RAM. No paid service or API key was used.

## Automated regression tests

`python -m pytest -q -p no:cacheprovider --junitxml=docs/test_results.xml`: **8 passed**.

| Case | Checked behavior | Result |
|---|---|---|
| 1 | Customer 13085: exact feature values and retained rows | Pass |
| 2 | Invoice identity and original Excel row provenance | Pass |
| 3 | Date refinement; bounded model evidence preserves complete-history facts | Pass |
| 4 | Unknown customer, empty period, reversed dates | Pass |
| 5 | Cancellations and missing customer IDs | Pass |
| 6 | Incorrect values/references/customer and unsupported numerical prose rejected; exact source dates allowed | Pass |
| 7 | Mocked local request, unavailable service, timeout, cloud-model rejection | Pass; transport mocks |
| 8 | Streamlit evidence review and invalidation after customer change | Pass |

## Actual local-model evaluation

Executed `python scripts/evaluate_local.py`. These are real model outputs, distinct from the mocked tests. The final generated outputs are saved in `local_model_results.json`.

| Scenario | Automatic grounding result | Seconds |
|---|---|---|
| default | grounding_checks_passed | 25.84 |
| shorter_window | grounding_checks_passed | 19.73 |
| other_customer | grounding_checks_passed | 24.55 |
| unsupported_request | grounding_checks_passed | 26.45 |
| large_history | grounding_checks_passed | 27.22 |

Five of five completed and passed mechanical checks. This is a small exploratory evaluation, not an accuracy benchmark. Timings are single observations and include local processing; they are not guaranteed response times.

Manual inspection by the implementation assistant found that final examples use the supplied metrics. The shortened-window recency sentence describes elapsed time correctly after the prompt revision. The unsupported-request case did not invent age or promise a future purchase; it stayed with observed facts and noted that the measures do not predict churn or intent. The long-history case used all 155 invoices for facts while receiving only ten labeled recent invoice examples. Wording can remain awkward, and “days ago” must be interpreted relative to the selected historical analysis date.

## Failures and design improvements

Initial local attempts failed: numeric copying produced values that the validator rejected. The final design attaches values and references with Python; the model supplies prose. A later large-history answer invented totals and was blocked. We capped invoice examples while retaining all-history computed features and the complete human-visible evidence. An initial shorter-window answer incorrectly described recency as days of purchasing activity; explicit metric instructions and visible definitions were added. `local_model_initial_results.json` preserves that intermediate five-case run, including the blocked long-history answer and the semantic recency failure. It must not be mistaken for accepted final output.

## Browser workflow

Verified actual Streamlit generation for customer 13085, visible values/references/definitions, model identity, and a saved **Needs correction** review asking to replace “days ago” with “days before the selected analysis date.” This is a demonstration review entered during implementation, not a claim that the student personally approved the answer. Screenshots in the presentation show the real local application. The export controls include evidence, AI output, and review.

## Remaining limits

Mechanical checks do not prove semantic correctness. Spelled-out numbers, causal claims, malicious source text and paraphrased unsupported statements need broader evaluation. Human review remains required. The three-customer sample is not a representative population. This release is a local demonstration; a cloud Streamlit deployment would require its own model runtime.
