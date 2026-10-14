# Challenge 3: Neo4j knowledge graph

Goal: explain observed customer similarity through shared products and source transactions. This stage implements a knowledge graph, not GraphRAG.

## Data and semantics
Uses the existing public `data/transactions_sample.csv`. Retains positive purchases within [2011-03-05, 2011-09-01). This is an illustrative sample, not the full customer population. Five node types: Customer, Invoice, OrderLine, Product, DataSource. Five relationship types: PLACED, HAS_LINE, OF_PRODUCT, DERIVED_FROM, RECORDED_IN.

## Run
Use a dedicated empty Neo4j database named `neo4j`. Install `pandas` and `neo4j==6.4.0`. Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD locally, then run:

```text
python challenge3/knowledge_graph.py
```

Alternatively supply `--credentials` pointing to a private JSON containing uri, username, password. Never commit this file. The script creates uniqueness constraints, imports using MERGE, runs ten checks, and writes `results/verification.json`. It never clears existing data. Use a dedicated database because verification counts assume no unrelated nodes.

## Results
138 nodes, 227 relationships. Customer 12347 has 50 distinct products and 13085 has 9. They share product 21791. Jaccard is 1/58 = 0.01724. This demonstrates weak overlap, not strong similarity or repurchase probability. Graph results agree with independent pandas set calculations. All ten recorded checks passed, including missing-customer and empty-window cases.

## Research and human review
- [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii): real identifiers, transaction fields and timestamps.
- [Schema.org OrderItem](https://schema.org/OrderItem): transaction-specific quantities and the connection to a product support OrderLine.
- [W3C PROV-O](https://www.w3.org/TR/prov-o/): wasDerivedFrom motivates line-level source provenance. This is a conceptual adaptation, not RDF/OWL conformance.

Human design originally used Customer, Invoice, Product. Codex proposed OrderLine and DataSource to preserve quantity/price and source-row evidence. The user explicitly accepted five node types and chose free local Neo4j. Similarity remains a date-dependent query result. Codex assisted with import, queries and verification. No training-completion claim is made.

## Classroom demonstration
Open http://localhost:7474/browser/ after starting the local server. Connect with your local credentials. Run the following graph view:

```cypher
MATCH path=(c:Customer)-[:PLACED]->(i:Invoice)-[:HAS_LINE]->(l:OrderLine)-[:OF_PRODUCT]->(p:Product {stockCode:'21791'})
MATCH source=(l)-[:DERIVED_FROM]->(s:DataSource)
MATCH recorded=(i)-[:RECORDED_IN]->(s)
RETURN path,source,recorded
```

Then run `queries/02_similarity.cypher` with customer `12347`, start `2011-03-05T00:00:00`, end `2011-09-01T00:00:00`. Run `03_evidence.cypher` with product `21791` to inspect original invoices and source rows. The import query expects `$rows` supplied by the Python script.

Next: broaden the customer cohort, evaluate ranking quality, then integrate grounded explanations during the GraphRAG stage. Existing Challenge 2 Streamlit deployment does not host this local Neo4j server.

## GraphRAG prototype (October 14)

`graphrag.py` accepts natural-language questions about an invoice, shared purchases, or customer similarity. It chooses a fixed, parameterized Cypher query, retrieves connected rows, computes exact facts in Python, and sends product descriptions to a **local** Qwen2.5 1.5B model through Ollama. The model selects relevant evidence indices; Python verifies the selection and builds a concise grounded explanation. Exact answers, source invoice IDs, RowIDs, scores, and limitations remain under Python's control. `graphrag_app.py` provides the Streamlit interface and evidence table.

This follows the retrieval-to-LLM pipeline described by [Neo4j GraphRAG for Python](https://neo4j.com/docs/neo4j-graphrag-python/current/), using the Neo4j Python driver directly because this small graph needs explicit multi-hop Cypher rather than vector indexing. No paid API key or embedding index is required.

Run locally after starting Neo4j and Ollama and pulling `qwen2.5:1.5b`:

```powershell
pip install -r challenge3/requirements.txt
$env:NEO4J_URI='bolt://localhost:7687'
$env:NEO4J_USER='neo4j'
$env:NEO4J_PASSWORD='<your local password>'
streamlit run challenge3/graphrag_app.py
python challenge3/evaluate_graphrag.py
```

On the configured local machine, `RETAIL360_NEO4J_CREDENTIALS` may point to the private JSON credentials file instead of setting three Neo4j variables. The evaluation script accepts `--credentials <private-json-path>`. Never commit credentials.

Three required questions and a missing-customer case are in `evaluate_graphrag.py`. Their **live local-model results** are saved in `results/graphrag_evaluation.json`. The first model attempt abbreviated the invoice evidence for the shared-purchase question and inferred customer interests from transactions. Human review led us to list all invoices in Python, restrict the model to evidence selection, and verify every selected index. The model can no longer write unsupported numerical or preference claims. Human review remains necessary to judge whether the selected examples are helpful.

GraphRAG remains an illustrative local prototype on a two-customer sample. Wider evaluation and persistent deployment are later work. The Challenge 2 Streamlit Cloud instance does not host this local Neo4j/Ollama application.

The eight-slide submission deck is `Retail360_Challenge3_GraphRAG_CoDesign_Final.pptx`; it includes actual Neo4j and local Streamlit screenshots. For a live class demo, open Neo4j Browser at `http://localhost:7474/browser/` and the local Streamlit app at `http://localhost:8503/` (when run on port 8503), then use the three example questions in the app.
