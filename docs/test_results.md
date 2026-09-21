# Test execution status

Executed on 2026-09-21 with Python 3.12, Streamlit 1.64.0, pandas 3.0.1, OpenAI SDK 3.16.2, and pytest 9.1.1.

`python -m pytest -q --junitxml=docs/test_results.xml`: **8 tests passed**.

| Case | Checked behavior | Result |
|---|---|---|
| 1 | Real customer 13085 feature values | Pass |
| 2 | Invoice identity, customer ownership, original Excel row references | Pass |
| 3 | Date filtering recalculates facts and evidence identity | Pass |
| 4 | Unknown customer, empty period, reversed dates | Pass |
| 5 | Cancellation exclusions and missing-ID audit rows | Pass |
| 6 | Incorrect values/references/customer rejected; missing facts stop generation | Pass |
| 7 | Mocked provider contract and missing API-key handling | Pass, mocked only |
| 8 | Streamlit review recording and invalidation after customer change | Pass |

Browser verification also confirmed page rendering, the real-customer profile, and the customer-not-found message. Screenshots are from the actual running application.

## Not yet evaluated

No live model response has been generated because an API key has not been configured. The provider integration test uses a mock response. These results do not establish live LLM factuality, semantic quality, unsupported-inference refusal, latency, or robustness against malicious product descriptions. Run and record live cases once a key is configured.

The original eight-case design included an unsupported-inference test. That behavioral LLM case remains pending; the automated suite adds workflow-specific checks and is not a claim that all original live-model criteria passed.

## Manual live check

Enter an API key locally, generate an explanation for customer 13085, inspect every claim against the displayed facts and invoice evidence, and download the response. Request an unsupported age/churn inference and check that the answer avoids it. Accept or reject the response, record the reason, and download the review. Change the dates and confirm the old response disappears. Test an invalid key to verify a clear error with no fabricated answer.
