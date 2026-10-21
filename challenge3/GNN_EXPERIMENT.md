# Challenge 3 GNN message-passing experiment

This small experiment extends the existing Neo4j GraphRAG project. It reads
`Customer → Invoice → OrderLine → Product` paths from the **existing** Neo4j
database and collapses them into 59 distinct customer–product purchase edges.
The KG has two customers and 58 products in the selected date window.

Run from the repository root after starting local Neo4j and importing the KG:

```powershell
pip install -r challenge3/requirements.txt
python challenge3/gnn_experiment.py --credentials path/to/private-credentials.json
```

Alternatively set `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` and omit
`--credentials`. Do not commit the private credentials file.

## Method and result

This is a **fixed-weight, one-layer GraphSAGE-style mean aggregator**, using a
one-hot product vector as each product's initial feature. Each customer
receives the mean of its unique purchased-product vectors. The experiment
demonstrates message passing; it does **not** train a GNN or establish an
improvement in retrieval quality. See [GraphSAGE](https://arxiv.org/abs/1706.02216)
for the trainable method that motivates the aggregation.

For customer 12347, product 21791 contributes `1/50 = 0.020` to the matching
coordinate; for customer 13085, it contributes `1/9 ≈ 0.111`.
The pair's existing set-based Jaccard score is `1/58 = 0.017241`, whereas
the customer-vector cosine is `0.047140`. These are **different measures**, so
their values cannot establish a performance gain. Removing the one shared
product from customer 13085's messages reduces cosine to zero. The three
source invoices and original RowIDs are preserved in the result JSON.

The actual Neo4j run is saved in `results/gnn_message_passing.json`. Five
mechanical and provenance checks passed. The screenshot in
`screenshots/gnn-experiment.png` displays these saved results.

## Proposed GraphRAG connection

For a larger customer cohort, trained embeddings could rank candidate
customers before fixed Cypher traversal retrieves invoices, products, and
source rows. The existing local LLM would only select or explain *retrieved*
evidence. Human review would decide whether a candidate is genuinely useful.
Here there is only **one candidate customer**, so ranking quality cannot be
evaluated. The current experiment is a message-passing and retrieval-design
demonstration, not a proven GNN-enhanced GraphRAG application.

## Human–AI co-design

Human goal: explain customer similarity using real purchases and provenance.
Codex suggested an embedding experiment. Human review kept a transparent,
fixed-weight mean aggregator and an edge-removal check instead of claiming
that an untrained model improved performance. The next research step is a
larger customer graph, chronological holdout, a learned GraphSAGE model,
and comparison with the existing Jaccard/Cypher baseline using retrieval
metrics such as Recall@K or Precision@K.

This experiment was developed before receiving any October 20 classroom
exercise files. It does not claim to reproduce those class materials.
