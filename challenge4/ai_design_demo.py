"""Challenge 4 AI-design experiment on public Online Retail II transactions.

This is an offline community/retrieval prototype, not the deployed GraphRAG app.
It uses a deterministic cohort and a first-phase local modularity optimizer.
It does not claim to implement full Louvain or Leiden.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random

import openpyxl

ROOT = Path(__file__).resolve().parent
DEFAULT_XLSX = ROOT.parents[1] / 'data' / 'online_retail_ii' / 'online_retail_II.xlsx'
START = datetime(2011, 3, 5)
END = datetime(2011, 9, 1)
SEED = 5588
COHORT_SIZE = 300
MIN_INVOICES = 3
MIN_PRODUCTS = 8
MIN_SHARED = 3
MIN_JACCARD = 0.10


def load_rows(path: Path):
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = book['Year 2010-2011']
    customers = defaultdict(lambda: {'products': set(), 'invoices': set(), 'rows': []})
    valid_rows = 0
    for row_no, row in enumerate(sheet.values, start=1):
        if row_no == 1:
            continue
        invoice, code, description, qty, date, price, customer, _country = row
        if not isinstance(date, datetime) or not (START <= date < END):
            continue
        if not customer or not code or not invoice:
            continue
        if str(invoice).upper().startswith('C'):
            continue
        if not isinstance(qty, (int, float)) or qty <= 0:
            continue
        if not isinstance(price, (int, float)) or price <= 0:
            continue
        cid = str(int(customer)) if isinstance(customer, (int, float)) else str(customer).strip()
        product = str(code).strip()
        invoice = str(invoice).strip()
        customers[cid]['products'].add(product)
        customers[cid]['invoices'].add(invoice)
        customers[cid]['rows'].append({
            'product': product, 'description': str(description or ''),
            'invoice': invoice, 'date': date.isoformat(),
            'sourceRow': f'Year 2010-2011:{row_no}',
        })
        valid_rows += 1
    return customers, valid_rows


def make_cohort(customers):
    eligible = sorted(cid for cid, v in customers.items()
                      if len(v['invoices']) >= MIN_INVOICES and len(v['products']) >= MIN_PRODUCTS)
    rng = random.Random(SEED)
    selected = sorted(rng.sample(eligible, min(COHORT_SIZE, len(eligible))))
    return eligible, selected


def make_graph(customers, selected):
    product_sets = {c: customers[c]['products'] for c in selected}
    graph = {c: {} for c in selected}
    edge_count = 0
    for i, a in enumerate(selected):
        for b in selected[i + 1:]:
            shared = len(product_sets[a] & product_sets[b])
            if shared < MIN_SHARED:
                continue
            score = shared / len(product_sets[a] | product_sets[b])
            if score >= MIN_JACCARD:
                graph[a][b] = score
                graph[b][a] = score
                edge_count += 1
    return graph, edge_count


def local_modularity_groups(graph):
    """One local moving phase, motivated by modularity; no graph coarsening."""
    nodes = sorted(graph)
    degrees = {n: sum(graph[n].values()) for n in nodes}
    total_degree = sum(degrees.values())
    if total_degree == 0:
        return {n: n for n in nodes}, 0
    groups = {n: n for n in nodes}
    community_degree = degrees.copy()
    rng = random.Random(SEED)
    for iteration in range(30):
        order = nodes[:]
        rng.shuffle(order)
        changes = 0
        for node in order:
            if not graph[node]:
                continue
            old = groups[node]
            degree = degrees[node]
            community_degree[old] -= degree
            neighboring = defaultdict(float)
            for other, weight in graph[node].items():
                neighboring[groups[other]] += weight
            best = old
            best_gain = neighboring.get(old, 0) - degree * community_degree[old] / total_degree
            for community, inside_weight in neighboring.items():
                gain = inside_weight - degree * community_degree[community] / total_degree
                if gain > best_gain + 1e-12:
                    best, best_gain = community, gain
            groups[node] = best
            community_degree[best] += degree
            changes += best != old
        if changes == 0:
            return groups, iteration + 1
    return groups, 30


def community_profiles(customers, selected, groups):
    members = defaultdict(list)
    for cid in selected:
        members[groups[cid]].append(cid)
    out = []
    descriptions = {}
    for cid in selected:
        for row in customers[cid]['rows']:
            if row['description'] and row['product'] not in descriptions:
                descriptions[row['product']] = row['description']
    for group_id, cohort in members.items():
        frequency = Counter(product for cid in cohort for product in customers[cid]['products'])
        out.append({'groupId': group_id, 'size': len(cohort),
                    'topProducts': [{'stockCode': p, 'description': descriptions.get(p, ''), 'customerCount': n}
                                    for p, n in frequency.most_common(5)]})
    return sorted(out, key=lambda x: (-x['size'], x['groupId']))


def select_retrieval_example(customers, selected, graph, groups, profiles):
    largest = profiles[0]['groupId']
    members = [c for c in selected if groups[c] == largest]
    target = max(members, key=lambda c: (sum(graph[c].get(b, 0) for b in members), c))
    peers = sorted((b for b in members if b != target and b in graph[target]),
                   key=lambda b: (-graph[target][b], b))[:3]
    global_peers = sorted(graph[target], key=lambda b: (-graph[target][b], b))[:3]
    rows = []
    for peer in peers:
        shared = sorted(customers[target]['products'] & customers[peer]['products'])
        evidence = []
        for product in shared[:3]:
            each = {}
            for cid in (target, peer):
                matches = [r for r in customers[cid]['rows'] if r['product'] == product]
                each[cid] = min(matches, key=lambda r: (r['date'], r['invoice'], r['sourceRow']))
            evidence.append({'stockCode': product, 'targetRow': each[target], 'peerRow': each[peer]})
        rows.append({'peer': peer, 'jaccard': round(graph[target][peer], 6),
                     'sharedProductCount': len(shared), 'sharedProducts': shared,
                     'evidence': evidence})
    return {'question': f'Which customers in {target}\'s community bought similar products, and why?',
            'target': target, 'groupId': largest, 'groupSize': len(members), 'peers': rows,
            'globalTop3': [{'peer': p, 'jaccard': round(graph[target][p], 6),
                            'sameCommunity': groups[p] == largest} for p in global_peers],
            'limitation': 'Observed purchases in one period; not direct evidence of personal preferences.'}


def graph_preview(customers, selected, graph, groups, profiles):
    """Small evidence-backed stars for an editable presentation diagram."""
    result = []
    for profile in profiles[:2]:
        group_id = profile['groupId']
        members = [c for c in selected if groups[c] == group_id]
        center = max(members, key=lambda c: (sum(graph[c].get(b, 0) for b in members), c))
        peers = sorted((b for b in members if b != center and b in graph[center]),
                       key=lambda b: (-graph[center][b], b))[:3]
        result.append({'groupId': group_id, 'groupSize': len(members), 'center': center,
                       'links': [{'peer': b, 'jaccard': round(graph[center][b], 6),
                                  'sharedProductCount': len(customers[center]['products'] & customers[b]['products'])}
                                 for b in peers]})
    return result


def run(path: Path):
    customers, valid_rows = load_rows(path)
    eligible, selected = make_cohort(customers)
    graph, edge_count = make_graph(customers, selected)
    groups, passes = local_modularity_groups(graph)
    profiles = community_profiles(customers, selected, groups)
    example = select_retrieval_example(customers, selected, graph, groups, profiles)
    checks = {
        'all_customers_assigned': sum(p['size'] for p in profiles) == len(selected),
        'example_peers_in_same_community': all(groups[p['peer']] == example['groupId'] for p in example['peers']),
        'example_evidence_has_source_rows': all(e['targetRow']['sourceRow'] and e['peerRow']['sourceRow']
                                                 for p in example['peers'] for e in p['evidence']),
        'example_jaccard_matches_sets': all(abs(p['jaccard'] - len(customers[example['target']]['products'] & customers[p['peer']]['products']) /
                                                 len(customers[example['target']]['products'] | customers[p['peer']]['products'])) < 1e-6
                                            for p in example['peers']),
    }
    assert all(checks.values()), checks
    return {
        'status': 'exploratory AI Design; not a deployed Neo4j/GraphRAG integration',
        'source': 'UCI Online Retail II, Year 2010-2011 worksheet',
        'sourceURL': 'https://archive.ics.uci.edu/dataset/502/online+retail+ii',
        'sourceSha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'window': {'startInclusive': START.date().isoformat(), 'endExclusive': END.date().isoformat()},
        'filters': 'known Customer ID, valid StockCode, non-cancelled invoice, positive Quantity and Price',
        'cohort': {'validRowsInWindow': valid_rows, 'customersInWindow': len(customers),
                   'eligibleCustomers': len(eligible), 'selection': f'seeded random {len(selected)} of eligible, seed {SEED}',
                   'minInvoices': MIN_INVOICES, 'minDistinctProducts': MIN_PRODUCTS},
        'projection': {'customerNodes': len(selected), 'similarityEdges': edge_count,
                       'minSharedProducts': MIN_SHARED, 'minJaccard': MIN_JACCARD},
        'method': {'name': 'first-phase local modularity optimization',
                   'fullLouvainOrLeiden': False, 'randomSeed': SEED, 'passes': passes},
        'communityCount': len(profiles), 'communitiesAtLeastThree': sum(p['size'] >= 3 for p in profiles),
        'topCommunities': profiles[:8], 'graphPreview': graph_preview(customers, selected, graph, groups, profiles),
        'exampleRetrieval': example, 'checks': checks,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--xlsx', type=Path, default=DEFAULT_XLSX)
    parser.add_argument('--output', type=Path, default=ROOT / 'results' / 'ai_design_demo.json')
    args = parser.parse_args()
    if not args.xlsx.exists():
        parser.error(f'Excel file not found: {args.xlsx}; download it from the UCI page and pass --xlsx')
    result = run(args.xlsx)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('cohort','projection','method','communityCount','communitiesAtLeastThree','topCommunities')}, indent=2))
    print('Example:', result['exampleRetrieval']['question'])
    print('Results:', args.output)
