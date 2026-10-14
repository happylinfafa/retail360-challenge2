"""Retail360 GraphRAG: fixed Neo4j retrieval + local LLM interpretation.

The query router only selects reviewed, parameterized Cypher templates. The
LLM never writes Cypher or computes the numbers displayed in the answer.
"""
import argparse
import json
import os
import re
from pathlib import Path

import requests
from neo4j import GraphDatabase

from knowledge_graph import START, END

OLLAMA = 'http://127.0.0.1:11434'
MODEL = 'qwen2.5:1.5b'
WINDOW = {'start': START+'T00:00:00', 'end': END+'T00:00:00'}

INVOICE = """
MATCH (c:Customer {customerId:$customer})-[:PLACED]->(i:Invoice {invoiceId:$invoice})
      -[:HAS_LINE]->(l:OrderLine)-[:OF_PRODUCT]->(p:Product)
MATCH (l)-[:DERIVED_FROM]->(s:DataSource)
RETURN c.customerId AS customer, i.invoiceId AS invoice,
       toString(i.invoiceDate) AS date, p.stockCode AS product,
       l.description AS description, l.quantity AS quantity,
       l.rowId AS rowId, s.fileName AS sourceFile
ORDER BY product, rowId
"""
SHARED = """
MATCH (a:Customer {customerId:$a})-[:PLACED]->(i:Invoice)-[:HAS_LINE]->(l:OrderLine)
      -[:OF_PRODUCT]->(p:Product)<-[:OF_PRODUCT]-(m:OrderLine)<-[:HAS_LINE]-(j:Invoice)<-[:PLACED]-(b:Customer {customerId:$b})
MATCH (l)-[:DERIVED_FROM]->(s1:DataSource)
MATCH (m)-[:DERIVED_FROM]->(s2:DataSource)
WHERE i.invoiceDate >= localdatetime($start) AND i.invoiceDate < localdatetime($end)
  AND j.invoiceDate >= localdatetime($start) AND j.invoiceDate < localdatetime($end)
RETURN DISTINCT p.stockCode AS product, l.description AS description,
       i.invoiceId AS invoiceA, toString(i.invoiceDate) AS dateA,
       l.rowId AS rowA, s1.fileName AS fileA,
       j.invoiceId AS invoiceB, toString(j.invoiceDate) AS dateB,
       m.rowId AS rowB, s2.fileName AS fileB
ORDER BY product, invoiceA, invoiceB
"""
SETS = """
MATCH (c:Customer)-[:PLACED]->(i:Invoice)-[:HAS_LINE]->(:OrderLine)-[:OF_PRODUCT]->(p:Product)
WHERE c.customerId IN [$a,$b] AND i.invoiceDate >= localdatetime($start)
  AND i.invoiceDate < localdatetime($end)
RETURN c.customerId AS customer, collect(DISTINCT p.stockCode) AS products
"""

def credentials(path=None):
    if path:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    return {'uri':os.getenv('NEO4J_URI','bolt://localhost:7687'),
            'username':os.getenv('NEO4J_USER','neo4j'),
            'password':os.environ['NEO4J_PASSWORD']}

def route(question):
    q=question.lower()
    customer_ids=re.findall(r'\b\d{5}\b', question)
    if any(word in q for word in ['similar','similarity','jaccard','相似','相似度']):
        kind='similarity'
    elif any(word in q for word in ['both','shared','common','两位','共同','都买']):
        kind='shared'
    elif any(word in q for word in ['invoice','order','bought','purchase','订单','购买']):
        kind='invoice'
    else:
        raise ValueError('Ask about an invoice, shared purchases, or customer similarity.')
    if kind in ('shared','similarity'):
        if len(customer_ids)<2: raise ValueError('Provide two five-digit customer IDs.')
        return kind,{'a':customer_ids[0], 'b':customer_ids[1], **WINDOW}
    invoices=re.findall(r'\b\d{6}\b', question)
    if not customer_ids or not invoices:
        raise ValueError('Provide a five-digit CustomerID and six-digit Invoice ID.')
    return kind,{'customer':customer_ids[0], 'invoice':invoices[0]}

def retrieve(db,question):
    kind,params=route(question)
    if kind=='invoice':
        rows=db.run(INVOICE,**params).data()
        if not rows: return {'kind':kind,'status':'no_evidence','facts':{},'evidence':[]}
        facts={'customer':params['customer'],'invoice':params['invoice'],
               'date':rows[0]['date'],'lineCount':len(rows),
               'distinctProducts':len({r['product'] for r in rows})}
        return {'kind':kind,'status':'ok','facts':facts,'evidence':rows}
    shared=db.run(SHARED,**params).data()
    if kind=='shared':
        if not shared: return {'kind':kind,'status':'no_evidence','facts':{'sharedProducts':0},'evidence':[]}
        invoices_a=sorted({r['invoiceA'] for r in shared})
        invoices_b=sorted({r['invoiceB'] for r in shared})
        return {'kind':kind,'status':'ok','facts':{'customers':[params['a'],params['b']],
                'sharedProducts':len({r['product'] for r in shared}),
                'invoicesA':invoices_a,'invoicesB':invoices_b},'evidence':shared}
    sets={r['customer']:set(r['products']) for r in db.run(SETS,**params)}
    if params['a'] not in sets or params['b'] not in sets:
        return {'kind':kind,'status':'no_evidence','facts':{},'evidence':[]}
    a,b=sets[params['a']],sets[params['b']]
    intersection=a&b;union=a|b
    facts={'customers':[params['a'],params['b']],'productsA':len(a),
           'productsB':len(b),'sharedProducts':sorted(intersection),
           'unionProducts':len(union),'jaccard':round(len(intersection)/len(union),6),
           'windowStart':START,'windowEndExclusive':END}
    return {'kind':kind,'status':'ok','facts':facts,'evidence':shared}

def exact_answer(result):
    f=result['facts']; kind=result['kind']
    if result['status']!='ok': return 'The selected graph contains insufficient evidence to answer this question.'
    if kind=='invoice':
        return (f"Customer {f['customer']} placed invoice {f['invoice']} on {f['date']}. "
                f"The graph contains {f['lineCount']} order lines and {f['distinctProducts']} distinct products for it.")
    if kind=='shared':
        return (f"Customers {f['customers'][0]} and {f['customers'][1]} share "
                f"{f['sharedProducts']} distinct purchased product(s) in the selected historical window. "
                f"Supporting invoices: {f['customers'][0]}: {', '.join(f['invoicesA'])}; "
                f"{f['customers'][1]}: {', '.join(f['invoicesB'])}.")
    return (f"Customers {f['customers'][0]} and {f['customers'][1]} bought "
            f"{f['productsA']} and {f['productsB']} distinct products, respectively. "
            f"They share {len(f['sharedProducts'])} product(s) out of {f['unionProducts']} "
            f"in the union. Jaccard similarity is {f['jaccard']:.6f}.")

def local_interpretation(question,result):
    if result['status']!='ok': return 'No interpretation generated because the graph evidence is insufficient.'
    # A small local LLM previously omitted invoices and inferred preferences.
    # Its revised role is evidence selection, with all final prose and numbers
    # assembled from verified graph facts rather than unconstrained model text.
    descriptions=list(dict.fromkeys(r['description'] for r in result['evidence']))[:12]
    schema={'type':'object','additionalProperties':False,'properties':{
        'selectedIndices':{'type':'array','items':{'type':'integer'}}},
        'required':['selectedIndices']}
    messages=[{'role':'system','content':
        'Select relevant product descriptions from the retrieved graph evidence. '
        'Return JSON containing only selectedIndices, an array of zero-based indices. '
        'For an invoice, select up to three representative items. '
        'For a shared-purchase or similarity question, select the shared product. '
        'Do not invent products or add any prose. Return at least one index.'},
        {'role':'user','content':json.dumps({'task':result['kind'],
            'productDescriptions':descriptions})}]
    response=requests.post(OLLAMA+'/api/chat',json={'model':MODEL,'messages':messages,
        'stream':False,'format':schema,'options':{'temperature':0,'num_predict':180},
        'keep_alive':'5m'},timeout=(5,180))
    response.raise_for_status();raw=response.json()
    if not raw.get('done') or raw.get('done_reason')=='length':
        raise ValueError('Local model response was incomplete.')
    selection=json.loads(raw['message']['content'])
    indices=selection.get('selectedIndices')
    if not isinstance(indices,list) or not 1<=len(indices)<=3 or \
       any(type(i) is not int or i<0 or i>=len(descriptions) for i in indices):
        raise ValueError('Model selected an invalid evidence index.')
    chosen=[descriptions[i] for i in dict.fromkeys(indices)]
    if result['kind']=='invoice':
        interpretation='The retrieved invoice includes '+', '.join(chosen)+'.'
        limitation='This invoice alone cannot describe the customer’s broader purchase history.'
    elif result['kind']=='shared':
        interpretation='Both customers bought '+', '.join(chosen)+' in the selected history.'
        limitation='A shared product does not establish broad customer similarity.'
    else:
        overlap='low' if result['facts']['jaccard']<0.05 else 'measurable'
        interpretation=f'The observed product overlap is {overlap}; a shared item is '+', '.join(chosen)+'.'
        limitation='This small sample does not establish customer preferences or future purchases.'
    return {'interpretation':interpretation,'limitation':limitation,
            'selectedEvidenceIndices':list(dict.fromkeys(indices))}

def answer(question,conf,with_llm=True):
    with GraphDatabase.driver(conf['uri'],auth=(conf['username'],conf['password'])) as driver:
        driver.verify_connectivity()
        with driver.session(database='neo4j') as db:
            result=retrieve(db,question)
    result['question']=question
    result['answer']=exact_answer(result)
    if with_llm:
        result['model']=MODEL
        try:
            result['llm']=local_interpretation(question,result)
            result['llmVerified']=result['status']=='ok'
        except (ValueError, KeyError, json.JSONDecodeError, requests.RequestException) as exc:
            result['llm']={'interpretation':'Interpretation withheld because it did not pass the evidence check.',
                           'limitation':'Review the exact answer and source rows below.'}
            result['llmVerified']=False
            result['llmCheck']=str(exc)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('question');p.add_argument('--credentials')
    p.add_argument('--no-llm',action='store_true');args=p.parse_args()
    print(json.dumps(answer(args.question,credentials(args.credentials),not args.no_llm),indent=2))

if __name__=='__main__':main()
