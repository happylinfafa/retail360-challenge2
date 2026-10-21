"""Small, auditable message-passing experiment on the existing Neo4j KG.

This is fixed-weight, one-layer GraphSAGE-style mean aggregation, not a
trained GNN. It demonstrates mechanics and candidate ranking only.
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from neo4j import GraphDatabase

from graphrag import credentials

ROOT = Path(__file__).resolve().parent
PURCHASE_EDGES = """
MATCH (c:Customer)-[:PLACED]->(i:Invoice)-[:HAS_LINE]->(l:OrderLine)-[:OF_PRODUCT]->(p:Product)
MATCH (l)-[:DERIVED_FROM]->(s:DataSource)
RETURN c.customerId AS customer, p.stockCode AS product,
       i.invoiceId AS invoice, l.rowId AS sourceRow, s.fileName AS sourceFile
ORDER BY customer, product, sourceRow
"""


def cosine(a, b):
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denominator) if denominator else 0.0


def experiment(rows):
    """Aggregate one-hot product messages into customer embeddings."""
    baskets = {}
    evidence = {}
    for row in rows:
        customer, product = str(row['customer']), str(row['product'])
        baskets.setdefault(customer, set()).add(product)
        evidence.setdefault((customer, product), []).append({
            'invoice': row['invoice'], 'sourceRow': row['sourceRow'],
            'sourceFile': row['sourceFile'],
        })
    if len(baskets) < 2:
        raise ValueError('Need at least two customers with purchases')
    products = sorted(set().union(*baskets.values()))
    customers = sorted(baskets)
    index = {product: i for i, product in enumerate(products)}
    identity = np.eye(len(products), dtype=float)

    def aggregate(basket):
        # h_c^(1) = mean_{p in N(c)} h_p^(0); h_p^(0) is a product one-hot.
        return identity[[index[p] for p in sorted(basket)]].mean(axis=0)

    embeddings = {c: aggregate(baskets[c]) for c in customers}
    pairs = []
    for i, customer in enumerate(customers):
        for other in customers[i + 1:]:
            shared = sorted(baskets[customer] & baskets[other])
            union = baskets[customer] | baskets[other]
            pairs.append({
                'customer': customer, 'other': other,
                'productsCustomer': len(baskets[customer]),
                'productsOther': len(baskets[other]),
                'sharedProducts': shared,
                'jaccardBaseline': len(shared) / len(union),
                'embeddingCosine': cosine(embeddings[customer], embeddings[other]),
                'sharedEvidence': {p: evidence[(customer, p)] + evidence[(other, p)] for p in shared},
            })
    pairs.sort(key=lambda p: (-p['embeddingCosine'], p['customer'], p['other']))
    focus = pairs[0]
    shared = focus['sharedProducts']
    ablated = set(baskets[focus['other']]) - set(shared)
    ablated_cosine = cosine(embeddings[focus['customer']], aggregate(ablated)) if ablated else 0.0
    checks = {
        'one_hot_dimension_matches_product_count': len(products) == len(identity),
        'every_customer_has_embedding': len(embeddings) == len(customers),
        'baseline_is_exact_set_jaccard': math.isclose(
            focus['jaccardBaseline'], len(shared) /
            len(baskets[focus['customer']] | baskets[focus['other']])
        ),
        'removing_shared_edges_does_not_increase_cosine': ablated_cosine <= focus['embeddingCosine'] + 1e-12,
        'shared_items_have_source_rows': all(
            item['sourceRow'] for product in shared for item in focus['sharedEvidence'][product]
        ),
    }
    assert all(checks.values()), checks
    return {
        'method': 'Fixed-weight one-layer GraphSAGE-style mean aggregator; no training',
        'nodeFeatures': 'One-hot StockCode vectors; customer initial vectors are zero',
        'source': 'Existing Neo4j Customer→Invoice→OrderLine→Product paths',
        'customerCount': len(customers), 'productCount': len(products),
        'purchaseEdges': sum(len(b) for b in baskets.values()),
        'messagePassingExample': {
            'customer': focus['customer'],
            'neighborCount': len(baskets[focus['customer']]),
            'sharedProduct': shared[0] if shared else None,
            'sharedProductContribution': 1 / len(baskets[focus['customer']]) if shared else 0,
            'formula': 'h_customer^(1) = mean(one_hot(product) for product in unique purchases)',
        },
        'candidateRanking': pairs,
        'edgeAblation': {
            'removedFromCustomer': focus['other'],
            'removedSharedProducts': shared,
            'cosineAfterRemoval': ablated_cosine,
        },
        'checks': checks,
        'interpretation': 'A positive cosine shows shared product messages. It does not establish improved retrieval quality or predictive performance.',
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--credentials', type=Path)
    args = parser.parse_args()
    conf = credentials(args.credentials)
    with GraphDatabase.driver(conf['uri'], auth=(conf['username'], conf['password'])) as driver:
        driver.verify_connectivity()
        with driver.session(database='neo4j') as session:
            rows = session.run(PURCHASE_EDGES).data()
    result = experiment(rows)
    target = ROOT / 'results' / 'gnn_message_passing.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    print(f'Saved {target}')


if __name__ == '__main__':
    main()
