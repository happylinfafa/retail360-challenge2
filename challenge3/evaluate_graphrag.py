"""Run the three required live GraphRAG cases plus a missing-evidence case."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from graphrag import answer, credentials

CASES=[
    ('basic','What did customer 12347 buy in invoice 549222?'),
    ('multi_hop','Which orders show both customer 12347 and customer 13085 bought a shared product?'),
    ('research','How similar are customer 12347 and customer 13085 based on purchased products?'),
    ('failure','What did customer 99999 buy in invoice 999999?'),
]

def main():
    p=argparse.ArgumentParser();p.add_argument('--credentials');args=p.parse_args()
    conf=credentials(args.credentials);runs=[]
    for name,question in CASES:
        try:
            result=answer(question,conf)
            facts=result['facts']; evidence=result['evidence']
            checks={
                'basic':result['kind']=='invoice' and result.get('llmVerified') is True and facts.get('lineCount')==24 and
                    any(r['product']=='21791' and r['rowId']=='Year 2010-2011:148293' for r in evidence),
                'multi_hop':result['kind']=='shared' and result.get('llmVerified') is True and facts.get('sharedProducts')==1 and
                    {r['product'] for r in evidence}=={'21791'} and all(r['rowA'] and r['rowB'] for r in evidence),
                'research':result['kind']=='similarity' and result.get('llmVerified') is True and facts.get('jaccard')==0.017241 and
                    facts.get('sharedProducts')==['21791'],
                'failure':result['status']=='no_evidence' and result.get('llmVerified') is False and
                    not evidence and 'insufficient' in result['answer'],
            }
            runs.append({'case':name,'question':question,'passed':bool(checks[name]),
                'answer':result['answer'],'llm':result.get('llm'),
                'llmVerified':result.get('llmVerified'),'llmCheck':result.get('llmCheck'),
                'facts':facts,'evidence':evidence,'model':result.get('model'),
                'human_review':'LLM wording must be checked against the listed source rows.'})
        except Exception as exc:
            runs.append({'case':name,'question':question,'passed':False,'error':str(exc)})
    report={'generatedAt':datetime.now(timezone.utc).isoformat(),
            'context':'Real local Neo4j KG + local qwen2.5:1.5b, illustrative UCI sample',
            'passed':sum(r['passed'] for r in runs),'total':len(runs),'cases':runs}
    output=Path(__file__).resolve().parent/'results/graphrag_evaluation.json'
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'total':report['total'],
        'cases':[{'case':r['case'],'passed':r['passed'],'answer':r.get('answer'),
                  'llm':r.get('llm'),'error':r.get('error'),
                  'evidenceRows':len(r.get('evidence',[]))} for r in runs]},indent=2))

if __name__=='__main__':main()
