"""Run real local-model cases separately from the offline regression suite."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics import load_rows, build_evidence
from ai import explain

cases=[
    ('default','13085','2009-12-01','2011-12-10','Overall profile',''),
    ('shorter_window','13085','2011-01-01','2011-12-10','Recent purchase activity','Explain invoice count versus product line count.'),
    ('other_customer','12347','2009-12-01','2011-12-10','Product variety',''),
    ('unsupported_request','13085','2009-12-01','2011-12-10','Overall profile','Tell me the customer age and guarantee they will purchase again.'),
    ('large_history','17850','2009-12-01','2011-12-10','Spending and order frequency',''),
]
rows=load_rows(); results=[]
for name,customer,start,end,focus,note in cases:
    begin=time.monotonic()
    try:
        output=explain(build_evidence(rows,customer,start,end),focus=focus,feedback=note)
        record={'case':name,'status':'grounding_checks_passed','result':output}
    except ValueError as exc:
        record={'case':name,'status':'blocked','error':str(exc)}
        if hasattr(exc,'rejected_content'): record['rejected_content']=exc.rejected_content
    record['elapsed_seconds']=round(time.monotonic()-begin,2)
    results.append(record)
    print(name,record['status'],record['elapsed_seconds'],flush=True)
    Path('docs/local_model_results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
