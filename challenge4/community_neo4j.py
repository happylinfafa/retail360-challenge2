"""Import the exploratory customer communities into the existing local Neo4j KG.

Only Challenge 4 relationships and Community nodes are added; existing Challenge 3
nodes and relationships are preserved. The public workbook stays on the local disk.
"""
import argparse
import json
from pathlib import Path

from neo4j import GraphDatabase

from ai_design_demo import (DEFAULT_XLSX, END, MIN_JACCARD, MIN_SHARED,
                            SEED, START, community_profiles, load_rows,
                            local_modularity_groups, make_cohort, make_graph)

RUN_ID = f'uci-retail-ii-{START:%Y%m%d}-{END:%Y%m%d}-seed{SEED}'
ROOT = Path(__file__).resolve().parent

CUSTOMERS = """
UNWIND $rows AS r
MERGE (c:Customer {customerId:r.customerId})
MERGE (g:Community {communityKey:r.communityKey})
SET g.runId=$runId, g.groupId=r.groupId, g.size=r.groupSize,
    g.windowStart=$start, g.windowEndExclusive=$end,
    g.method='first-phase local modularity optimization'
MERGE (c)-[:CH4_MEMBER_OF {runId:$runId}]->(g)
"""
PURCHASES = """
UNWIND $rows AS r
MATCH (c:Customer {customerId:r.customerId})
MERGE (p:Product {stockCode:r.stockCode})
SET p.description=coalesce(p.description,r.description)
MERGE (c)-[b:CH4_BOUGHT {runId:$runId,stockCode:r.stockCode}]->(p)
SET b.invoiceId=r.invoiceId, b.sourceRow=r.sourceRow,
    b.sourceFile='online_retail_II.xlsx', b.worksheet='Year 2010-2011',
    b.purchaseDate=r.purchaseDate
"""
SIMILAR = """
UNWIND $rows AS r
MATCH (a:Customer {customerId:r.a}),(b:Customer {customerId:r.b})
MERGE (a)-[s:CH4_SIMILAR {runId:$runId}]->(b)
SET s.jaccard=r.jaccard, s.sharedProductCount=r.sharedProductCount,
    s.minSharedProducts=$minShared, s.minJaccard=$minJaccard
"""


def batches(rows, size=500):
    for offset in range(0, len(rows), size):
        yield rows[offset:offset + size]


def build_rows(path):
    customers, valid_rows = load_rows(path)
    eligible, selected = make_cohort(customers)
    graph, edge_count = make_graph(customers, selected)
    groups, passes = local_modularity_groups(graph)
    profiles = community_profiles(customers, selected, groups)
    sizes = {p['groupId']: p['size'] for p in profiles}
    customer_rows = [{'customerId':c, 'communityKey':RUN_ID+'|'+groups[c],
                      'groupId':groups[c], 'groupSize':sizes[groups[c]]} for c in selected]
    purchase_rows = []
    for cid in selected:
        first_by_product = {}
        for r in customers[cid]['rows']:
            first_by_product.setdefault(r['product'], r)
        for code, r in first_by_product.items():
            purchase_rows.append({'customerId':cid, 'stockCode':code,
                                  'description':r['description'], 'invoiceId':r['invoice'],
                                  'sourceRow':r['sourceRow'], 'purchaseDate':r['date']})
    similarity_rows = [{'a':a, 'b':b, 'jaccard':round(score, 9),
                        'sharedProductCount':len(customers[a]['products'] & customers[b]['products'])}
                       for a in selected for b, score in graph[a].items() if a < b]
    assert len(similarity_rows) == edge_count
    return customer_rows, purchase_rows, similarity_rows, profiles, valid_rows, len(eligible), passes


def import_graph(conf, path):
    customers, purchases, similarities, profiles, valid_rows, eligible, passes = build_rows(path)
    with GraphDatabase.driver(conf['uri'], auth=(conf['username'],conf['password'])) as driver:
        driver.verify_connectivity()
        with driver.session(database='neo4j') as db:
            db.run('CREATE CONSTRAINT ch4_community_key IF NOT EXISTS FOR (g:Community) REQUIRE g.communityKey IS UNIQUE').consume()
            parameters={'runId':RUN_ID,'start':START.date().isoformat(),
                        'end':END.date().isoformat(),'minShared':MIN_SHARED,
                        'minJaccard':MIN_JACCARD}
            for query, rows in ((CUSTOMERS,customers),(PURCHASES,purchases),(SIMILAR,similarities)):
                for batch in batches(rows):
                    db.run(query, rows=batch, **parameters).consume()
            counts=db.run("""
                MATCH (c:Customer)-[:CH4_MEMBER_OF {runId:$runId}]->(g:Community)
                RETURN count(DISTINCT c) AS customers,count(DISTINCT g) AS communities
                """,runId=RUN_ID).single().data()
            counts['purchases']=db.run('MATCH ()-[r:CH4_BOUGHT {runId:$runId}]->() RETURN count(r) AS n',runId=RUN_ID).single()['n']
            counts['similarityEdges']=db.run('MATCH ()-[r:CH4_SIMILAR {runId:$runId}]->() RETURN count(r) AS n',runId=RUN_ID).single()['n']
            assert counts=={'customers':len(customers),'communities':len(profiles),
                            'purchases':len(purchases),'similarityEdges':len(similarities)},counts
            original=db.run('MATCH (c:Customer {customerId:"12347"})-[:PLACED]->(i:Invoice) RETURN count(i) AS n').single()['n']
            assert original > 0, 'Existing Challenge 3 KG not found; import it first.'
    return {'runId':RUN_ID,'window':{'startInclusive':START.date().isoformat(),
            'endExclusive':END.date().isoformat()},'validRowsInWindow':valid_rows,
            'eligibleCustomers':eligible,'passes':passes,'counts':counts,
            'existingChallenge3InvoicesFor12347':original,
            'note':'Exploratory sampled communities, not validated preference groups.'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--xlsx',type=Path,default=DEFAULT_XLSX)
    p.add_argument('--credentials',type=Path,required=True)
    args=p.parse_args()
    conf=json.loads(args.credentials.read_text(encoding='utf-8'))
    result=import_graph(conf,args.xlsx)
    output=ROOT/'results'/'neo4j_community_import.json'
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
