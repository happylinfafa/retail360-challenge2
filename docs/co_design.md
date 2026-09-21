# Human–AI Co-Design

Human Design: retail analysts need reliable customer features from transaction rows.

AI Design: Python computes exact metrics, structured retrieval supplies evidence, and an LLM explains the facts. Vector search and multiple agents were considered unnecessary for this first task.

Working interaction: the human selects a customer and dates, inspects invoices and the timeline, requests an explanation or clarification, reads source references and limitations, then accepts, rejects, or requests a correction. Refining customer/date/focus/model invalidates the previous response and review.

Codex inspected real data, generated the small application, added original Excel-row provenance, tested the calculation and review flow, and checked the browser. The user had previously accepted the architecture and evidence rules. Reviewing generated code remains an important user task: begin with analytics.py, then ai.py, then app.py.

A useful implementation correction was distinguishing computed evidence review from AI-response review. When the local model is unavailable, the app must not imply that a template or Python summary is an AI answer. Another correction was defining spending as positive purchase amount rather than net revenue.

First task: one customer profile with evidence and human review. Later work: live model evaluation, broader samples, segmentation, and a separate time-based prediction pipeline.


Cost-driven human revision: replace the paid cloud model with Qwen2.5 1.5B running locally through Ollama. Keep calculation, evidence retrieval and human review unchanged. Download once, then generate without a paid service. Small-model limitations require manual review; do not trade grounding checks for a successful-looking answer.

During real local tests, copying numbers through the model caused invalid values; Python now attaches values and provenance. A long customer history also produced unsupported prose, so the model receives all-history features plus at most ten clearly labeled recent invoice examples. The full evidence remains available to the human. A recency wording error prompted a clearer instruction and visible metric definitions. Initial and revised results are saved separately.
