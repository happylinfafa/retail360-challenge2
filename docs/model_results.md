# Segmentation and repurchase baselines — 2026-09-28

This stage extends the frozen data protocol with real model training and a historical Streamlit prediction-review page. It includes one customer--product graph-feature ablation. Models run locally without paid APIs.

## Fixed experiment

Training uses 9,659 customer-snapshot rows from the three training dates. Validation has 2,659 customers and test has 2,772. All models use identical temporal partitions. The full baseline is the eight historical features in `repurchase.FEATURE_COLUMNS`; the smaller set is recency, frequency and monetary value only. The graph ablation adds `mean_log_product_customer_degree`: for each cutoff, it builds a bipartite graph from pre-cutoff customer--product edges, calculates each product's number of distinct historical customers, then averages `log(1 + product degree)` over each customer's products. It uses no future rows or labels.

All pipelines use training-fitted median imputation with missing indicators, log1p transformation and standardization. Logistic regression uses C=1 and max_iter=2000. Histogram gradient boosting uses 150 iterations, 15 maximum leaf nodes, learning rate 0.05, L2=1 and no internal random early-stopping split. Dummy probabilities equal the training positive rate. Random seed is 42. Scikit-learn version is 1.9.1. These are fixed baseline configurations, not an extensive tuning search.

Select the model with the highest validation average precision (AP). Choose each classification threshold on validation F1 using the fixed 0.05–0.95 grid. Freeze selection before loading test data. The selected model is **full_plus_graph_boosted_tree**, with threshold **0.30**. No refitting on validation data was performed. Test comparisons below are descriptive reporting, not a new selection round.

## Measured prediction results

| Model | Validation AP | Test AP | Test ROC-AUC |
| --- | ---: | ---: | ---: |
| Dummy (either feature set) | 0.4250 | 0.4906 | 0.5000 |
| RFM logistic regression | 0.7153 | 0.7502 | 0.7281 |
| RFM boosted tree | 0.7178 | 0.7523 | 0.7267 |
| Full logistic regression — selected | 0.7227 | 0.7551 | 0.7348 |
| Full boosted tree | 0.7210 | 0.7507 | 0.7295 |
| Full + graph logistic regression | 0.7225 | 0.7550 | 0.7345 |
| Full + graph boosted tree — validation selected | 0.7238 | 0.7494 | 0.7258 |

AP is the non-interpolated average-precision summary of the precision–recall curve; it is not accuracy or trapezoidal PR-AUC. We report its exact definition to make comparisons reproducible.

For the validation-selected graph model, test F1 is **0.6635**, precision **0.6594**, recall **0.6676**, and Brier score **0.2212** (dummy: 0.2638; lower is better). The top-ranked 10% contains 278 customers and has **91.73%** observed repurchase, compared with **49.06%** overall, for **1.8696× lift**. This is historical ranking performance, not a guarantee or an estimated marketing treatment effect. Ties are broken by fixed customer order, so dummy top-10% lift need not equal exactly one.

The graph boosted tree is selected because its validation AP (0.7238) exceeds the non-graph boosted tree (0.7210) by 0.0028. On the held-out test it is lower (0.7494 versus 0.7507). Therefore the correct conclusion is: **this one graph feature did not show a stable improvement in this first ablation**. This is a useful research result, not a failure. There is no significance claim. Temporal and diversity features are currently added together, so the analysis is still not a complete feature-family ablation or a community-detection study.

## Customer segmentation

Fit log-transformed, standardized RFM K-means on the latest training snapshot (2011-03-01; 3,349 customers). Select k among 2–5 by training silhouette, using a fixed sample of up to 2,000 points. Selected **k=2**, silhouette **0.4663**, Davies–Bouldin **0.9130**. Five bootstrap K-means refits with the fixed training transform yield ARI **0.9493–0.9976**. This measures sensitivity to resampling; it does not prove stability across time or all preprocessing choices.

| Test group | Customers | Median recency (days) | Median invoice count | Median positive spending | Observed next-60-day purchase rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cluster 0 | 1,839 | 85 | 1 | £314.45 | 37.30% |
| Cluster 1 | 933 | 18 | 4 | £1,516.00 | 72.24% |

Cluster 1 describes more recent and frequent purchasing in this sample. Group IDs are arbitrary, and future purchase rates were not used to create clusters. Cluster IDs are not included in the baseline prediction feature set.

## Application and artifacts

The Repurchase page shows validation/test customers, a fixed-cutoff probability, historical feature values, source worksheet/row IDs, comparison results and customer-group summaries. Future outcomes are explicitly labeled as evaluation-only. A reviewer can inspect evidence, switch customers and download an accept/reject/comment record; switching customers clears the prior review.

`runtime/models_v2_graph/` contains saved models, validation selection metadata, metrics, cluster profiles, customer predictions, test country/frequency slices and calibration bins. Generated customer-level data and serialized models stay local.

Limitations: one retailer and one held-out test date; repeated customers across snapshots; unverified duplicate rows; positive purchases rather than refund-adjusted revenue; no confidence intervals; country slices with small samples are unreliable; no separate new-versus-established customer analysis yet; calibration bins and Brier do not establish that probabilities are well calibrated. These are strong conventional baselines, not a state-of-the-art claim.

Verification: **22 tests passed** with `python -m pytest tests -q -p no:cacheprovider --basetemp=runtime/pytest_graph_final2`. These include existing data/application checks, feature-allowlist protection, preprocessing fit isolation, known-value metrics, dummy prevalence, a real-artifact Streamlit AppTest, and the graph-feature test that confirms product degree math and rejects a transaction at or after the cutoff. Tests do not establish statistical significance or validate causal explanations.

Next work is a second, distinct historical-only graph or community feature, a staged feature-family ablation on the same protocol, and evidence-based explanation of any improvement or lack of improvement. Since test results have now been viewed, future development decisions must remain validation-driven; repeated inspection of this same test set weakens its independence and should be disclosed.
