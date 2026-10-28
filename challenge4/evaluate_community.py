"""Small live regression/evidence check for the Neo4j community GraphRAG route."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'challenge3'))
from graphrag import answer


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--credentials',type=Path,required=True)
    p.add_argument('--no-llm',action='store_true')
    args=p.parse_args()
    conf=json.loads(args.credentials.read_text(encoding='utf-8'))
    question="Which customers in customer 15719's community bought similar products, and why?"
    result=answer(question,conf,with_llm=not args.no_llm)
    expected=json.loads((ROOT/'results'/'ai_design_demo.json').read_text(encoding='utf-8'))['exampleRetrieval']
    missing=answer('Which customers in customer 99999 community bought similar products?',conf,with_llm=False)
    old=answer('How similar are customer 12347 and customer 13085 based on purchased products?',conf,with_llm=False)
    checks={
        'neo4j_community_route_works':result['kind']=='community' and result['status']=='ok',
        'same_group_as_offline_experiment':result['facts']['groupId']==expected['groupId'] and result['facts']['groupSize']==expected['groupSize'],
        'top_peer_and_score_match_offline_experiment':result['facts']['peers'][0]['peer']==expected['peers'][0]['peer'] and abs(result['facts']['peers'][0]['jaccard']-expected['peers'][0]['jaccard'])<1e-6,
        'multi_hop_product_evidence':any(e['product']=='20713' and e['invoiceA']=='547359' and e['invoiceB']=='557233' for e in result['evidence']),
        'source_rows_visible':all(e['rowA'].startswith('Year 2010-2011:') and e['rowB'].startswith('Year 2010-2011:') for e in result['evidence']),
        'missing_customer_handled':missing['status']=='no_evidence' and not missing['evidence'],
        'old_similarity_route_preserved':old['kind']=='similarity' and old['status']=='ok' and old['facts']['jaccard']==0.017241,
    }
    if not args.no_llm:
        checks['local_llm_grounded']=result.get('llmVerified') is True and result['llm']['selectedEvidenceIndices'] and all(i<len(result['evidence']) for i in result['llm']['selectedEvidenceIndices'])
    report={'checks':checks,'passed':sum(checks.values()),'total':len(checks),
            'question':question,'answer':result['answer'],'facts':result['facts'],
            'llm':result.get('llm'),'evidence':result['evidence'][:3],
            'limitation':'Exploratory 300-customer sample; no validation of community stability or business value.'}
    output=ROOT/'results'/'neo4j_community_evaluation.json'
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'total':report['total'],'checks':checks,'output':str(output)},indent=2))
    assert all(checks.values()),'Community GraphRAG evaluation failed'


if __name__=='__main__': main()
