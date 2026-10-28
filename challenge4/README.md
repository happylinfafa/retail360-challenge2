# Challenge 4 AI Design: community-aware retrieval preview

This folder contains a small AI Design experiment, based on the Challenge 4 Human Design, **and a local Neo4j GraphRAG integration**. The user-defined priorities are customer communities based on similar purchased products, a customer relationship graph, and evidence-backed descriptions of observed buying tendencies. Codex proposed a larger deterministic cohort, a weighted customer projection, a simple community prototype, a comparison chart, and a provenance-first retrieval card.

The integration adds community and purchase-evidence relationships to the existing local Challenge 3 Neo4j database, preserving its original nodes and relationships. It extends the existing local GraphRAG question router and Streamlit app. It does **not** change the separate deployed Challenge 2 cloud application or implement full Louvain or Leiden.

## Data and reproducibility

Download the public [UCI Online Retail II workbook](https://archive.ics.uci.edu/dataset/502/online+retail+ii). Run:

```powershell
pip install openpyxl
python challenge4/ai_design_demo.py --xlsx path/to/online_retail_II.xlsx
```

The default workbook path is `../data/online_retail_ii/online_retail_II.xlsx` relative to the repository. The script reads the `Year 2010-2011` worksheet and keeps valid positive purchases in `[2011-03-05, 2011-09-01)`. It excludes cancellations, missing customer/product IDs, and nonpositive quantity/price. Eligible customers have at least three invoices and eight distinct products. A seeded random sample of 300 eligible customers (seed 5588) forms the exploratory cohort. No individual purchase rows or the full workbook are committed. The script saves only aggregate and example evidence in `results/ai_design_demo.json`.

For each pair of selected customers, a link requires at least three shared distinct products and Jaccard similarity of at least 0.10. A first-phase local modularity optimizer assigns exploratory groups. This has no graph coarsening and is **not** full Louvain or Leiden. Thresholds and cohort selection are design choices that need sensitivity analysis before using groups for decisions.

## Actual preliminary result

The selected window had 155,362 valid rows from 2,772 customers, of whom 888 met the eligibility rule. The 300-customer projection has 1,684 similarity edges. The local optimizer produced 68 groups, including 17 of size three or more. The three largest have 54, 42, and 34 customers. Four arithmetic/provenance checks pass.

For a concrete community-aware retrieval question, the sample result asks which members of customer 15719's 54-customer group bought similar products and why. Its top same-group peer, 15356, shares 64 distinct products (Jaccard 0.218430). Example evidence includes StockCode 20713 in invoice 547359, source row `Year 2010-2011:128739`, and invoice 557233, source row `Year 2010-2011:231094`. The JSON includes two further peers and more source rows.

These are observed purchases, not direct measures of customer preference. A large group can contain weak edges; group stability, coverage, and usefulness for retrieval have not yet been evaluated.

## Local Neo4j + GraphRAG integration

Start the same local Neo4j used by Challenge 3. Download the workbook above, then run:

```powershell
python challenge4/community_neo4j.py --credentials path/to/private-neo4j-credentials.json --xlsx path/to/online_retail_II.xlsx
python challenge4/evaluate_community.py --credentials path/to/private-neo4j-credentials.json
$env:RETAIL360_NEO4J_CREDENTIALS='path/to/private-neo4j-credentials.json'
streamlit run challenge3/graphrag_app.py
python challenge4/test_streamlit_ui.py
```

The credentials JSON contains `uri`, `username`, and `password`; keep it outside Git. The importer adds 300 Customer memberships, 68 Community nodes, 23,702 `CH4_BOUGHT` relationships with source invoice and worksheet row, and 1,684 `CH4_SIMILAR` relationships. It preserves existing Challenge 3 data. Import results are in `results/neo4j_community_import.json`.

Ask: **“Which customers in customer 15719's community bought similar products, and why?”** The original GraphRAG entry point now uses a parameterized multi-hop Cypher query, finds same-community peers, retrieves shared Product nodes and source purchases, computes an exact response, and asks the local Qwen model to select relevant evidence descriptions. The Streamlit page shows a relationship preview, exact facts, model interpretation, and original row IDs. The integration evaluation in `results/neo4j_community_evaluation.json` passed 8/8 checks, including matching the offline top peer/score, source evidence, missing-customer handling, an old-route regression, and local-model evidence selection.

This is a **local prototype**. It is not deployed to Streamlit Cloud. Community stability and usefulness for downstream marketing decisions remain untested. The next research step is to compare community algorithms and cutoff windows, then evaluate whether filtering by community improves retrieval and decisions.

## Research and comparison

- [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) supplies the transaction fields and source workbook.
- [Neo4j Leiden documentation](https://neo4j.com/docs/graph-data-science/current/algorithms/leiden/) motivates testing a full community algorithm on the weighted projection later.
- [Neo4j Label Propagation documentation](https://neo4j.com/docs/graph-data-science/current/algorithms/label-propagation/) provides a simpler alternative.
- [Neo4j GraphRAG for Python](https://neo4j.com/docs/neo4j-graphrag-python/current/) describes graph retrieval followed by grounded generation. The local integration uses the existing Challenge 3 retrieval and LLM answer path with a new community query route.

Human Design selected the community meaning and graph output. AI Design added a reproducible cohort, explicit similarity and source-row rules, and a community-size chart. It rejected speech/video for this analyst workflow and does not infer hidden preferences from purchase records. Human review should now assess whether these additions match the original project goals.
