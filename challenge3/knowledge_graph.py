"""Small, reproducible Neo4j KG from real Retail360 source rows.

Credentials: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, or --credentials JSON.
Only MERGE is used: existing databases are never cleared.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent
START, END = '2011-03-05', '2011-09-01'
IMPORT = """
UNWIND $rows AS r
MERGE (s:DataSource {sourceId:r.sourceId})
SET s.fileName=r.SourceFile, s.worksheet=r.Worksheet,
    s.url='https://archive.ics.uci.edu/dataset/502/online+retail+ii'
MERGE (c:Customer {customerId:r.CustomerID})
MERGE (i:Invoice {invoiceKey:r.invoiceKey})
SET i.invoiceId=r.Invoice, i.invoiceDate=localdatetime(r.InvoiceDate), i.country=r.Country
MERGE (p:Product {stockCode:r.StockCode})
SET p.description=r.Description
MERGE (l:OrderLine {lineId:r.lineId})
SET l.quantity=r.Quantity, l.unitPriceGBP=r.Price, l.rowId=r.RowID,
    l.excelRow=r.ExcelRow, l.description=r.Description
MERGE (c)-[:PLACED]->(i)
MERGE (i)-[:HAS_LINE]->(l)
MERGE (l)-[:OF_PRODUCT]->(p)
MERGE (l)-[:DERIVED_FROM]->(s)
MERGE (i)-[:RECORDED_IN]->(s)
"""
SIMILARITY = """
MATCH (a:Customer {customerId:$customer})-[:PLACED]->(i:Invoice)-[:HAS_LINE]->(:OrderLine)-[:OF_PRODUCT]->(p:Product)
WHERE i.invoiceDate >= localdatetime($start) AND i.invoiceDate < localdatetime($end)
WITH a, collect(DISTINCT p.stockCode) AS aProducts
MATCH (b:Customer)-[:PLACED]->(j:Invoice)-[:HAS_LINE]->(:OrderLine)-[:OF_PRODUCT]->(q:Product)
WHERE b <> a AND j.invoiceDate >= localdatetime($start) AND j.invoiceDate < localdatetime($end)
WITH a,b,aProducts,collect(DISTINCT q.stockCode) AS bProducts
WITH a,b,aProducts,bProducts,[x IN aProducts WHERE x IN bProducts] AS shared
RETURN a.customerId AS customer, b.customerId AS other,
size(aProducts) AS productsA,size(bProducts) AS productsB,shared,
toFloat(size(shared))/(size(aProducts)+size(bProducts)-size(shared)) AS jaccard
ORDER BY jaccard DESC,other
"""
EVIDENCE = """
MATCH (c:Customer)-[:PLACED]->(i:Invoice)-[:HAS_LINE]->(l:OrderLine)-[:OF_PRODUCT]->(p:Product {stockCode:$product})
MATCH (l)-[:DERIVED_FROM]->(s:DataSource)
RETURN c.customerId AS customer,i.invoiceId AS invoice,toString(i.invoiceDate) AS date,
p.stockCode AS product,l.quantity AS quantity,l.rowId AS sourceRow,s.fileName AS file
ORDER BY customer,date
"""

def prepare():
    path=ROOT.parent/'data/transactions_sample.csv'
    df=pd.read_csv(path,dtype={'CustomerID':str,'Invoice':str,'StockCode':str})
    dates=pd.to_datetime(df.InvoiceDate,errors='coerce')
    valid=(dates>=START)&(dates<END)&(df.Quantity>0)&(df.Price>0)&df.CustomerID.notna()&~df.Invoice.str.upper().str.startswith('C')
    df=df.loc[valid].copy().sort_values(['InvoiceDate','RowID'])
    assert df.RowID.is_unique, 'Duplicate provenance IDs require review'
    df['sourceId']=df.SourceFile+'|'+df.Worksheet
    df['lineId']=df.SourceFile+'|'+df.RowID
    df['invoiceKey']=df.SourceFile+'|'+df.CustomerID+'|'+df.Invoice
    df['InvoiceDate']=pd.to_datetime(df.InvoiceDate).dt.strftime('%Y-%m-%dT%H:%M:%S')
    assert (df.groupby('invoiceKey').InvoiceDate.nunique()==1).all()
    return df,hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--credentials',type=Path)
    args=parser.parse_args()
    conf=json.loads(args.credentials.read_text()) if args.credentials else {'uri':os.getenv('NEO4J_URI','bolt://localhost:7687'),'username':os.getenv('NEO4J_USER','neo4j'),'password':os.environ['NEO4J_PASSWORD']}
    df,sha=prepare()
    out=ROOT/'results';out.mkdir(exist_ok=True)
    (ROOT/'queries').mkdir(exist_ok=True)
    (ROOT/'queries/01_import.cypher').write_text(IMPORT,encoding='utf-8')
    (ROOT/'queries/02_similarity.cypher').write_text(SIMILARITY,encoding='utf-8')
    (ROOT/'queries/03_evidence.cypher').write_text(EVIDENCE,encoding='utf-8')
    tests=[]
    def check(name,actual,expected):
        passed=actual==expected
        tests.append({'test':name,'actual':actual,'expected':expected,'passed':passed})
        assert passed,(name,actual,expected)
    with GraphDatabase.driver(conf['uri'],auth=(conf['username'],conf['password'])) as driver:
        driver.verify_connectivity()
        with driver.session(database='neo4j') as db:
            for label,key in [('Customer','customerId'),('Invoice','invoiceKey'),('Product','stockCode'),('OrderLine','lineId'),('DataSource','sourceId')]:
                db.run(f'CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{key} IS UNIQUE').consume()
            db.run(IMPORT,rows=df.to_dict('records')).consume()
            counts={r['label']:r['n'] for r in db.run('MATCH (n) RETURN labels(n)[0] AS label,count(*) AS n')}
            rels={r['type']:r['n'] for r in db.run('MATCH ()-[r]->() RETURN type(r) AS type,count(*) AS n')}
            params={'customer':'12347','start':START+'T00:00:00','end':END+'T00:00:00'}
            sim=db.run(SIMILARITY,**params).data()
            ev=db.run(EVIDENCE,product='21791').data()
            check('Imported line count',counts['OrderLine'],len(df))
            check('Original five node types present',{'Customer','Invoice','Product','OrderLine','DataSource'} <= set(counts),True)
            check('Original five relationship types present',{'PLACED','HAS_LINE','OF_PRODUCT','DERIVED_FROM','RECORDED_IN'} <= set(rels),True)
            check('Every line has source',rels['DERIVED_FROM'],len(df))
            sets=df.groupby('CustomerID').StockCode.apply(set).to_dict()
            a,b=sets['12347'],sets['13085']
            check('Graph shared products match pandas',sorted(sim[0]['shared']),sorted(a&b))
            check('Graph Jaccard matches pandas',round(sim[0]['jaccard'],12),round(len(a&b)/len(a|b),12))
            check('Evidence has source row',all(x['sourceRow'] for x in ev),True)
            check('Missing customer returns no result',db.run(SIMILARITY,**{**params,'customer':'MISSING'}).data(),[])
            check('Empty future window returns no result',db.run(SIMILARITY,**{**params,'start':'2020-01-01T00:00:00','end':'2020-02-01T00:00:00'}).data(),[])
            db.run(IMPORT,rows=df.to_dict('records')).consume()
            check('Import is idempotent',db.run('MATCH (n) RETURN count(n) AS n').single()['n'],sum(counts.values()))
    report={'window':{'startInclusive':START,'endExclusive':END},'sourceSampleSha256':sha,'scope':'All valid rows in this window from the existing illustrative sample, NOT the complete UCI dataset','counts':counts,'relationships':rels,'similarity':sim,'evidence':ev,'tests':tests}
    (out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
