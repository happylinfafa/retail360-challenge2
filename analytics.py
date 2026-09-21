"""Exact structured retrieval and deterministic purchase-only calculations."""
import csv
import hashlib
import json
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path

ROOT=Path(__file__).resolve().parent
POLICY='purchase-positive-v1'

def load_rows(path=None):
    with Path(path or ROOT/'data/transactions_sample.csv').open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def money(value):
    return str(Decimal(value).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))

def exclusion(row):
    if not row.get('CustomerID'): return 'Missing Customer ID'
    if not row.get('Invoice'): return 'Missing invoice'
    if row['Invoice'].upper().startswith('C'): return 'Cancellation invoice'
    try:
        qty, price=Decimal(row['Quantity']), Decimal(row['Price'])
        if not qty.is_finite() or not price.is_finite(): return 'Non-finite amount'
        if qty <= 0: return 'Non-positive quantity'
        if price <= 0: return 'Non-positive price'
        datetime.fromisoformat(row['InvoiceDate'])
    except (KeyError,ValueError,InvalidOperation): return 'Invalid numeric/date value'
    if not row.get('StockCode'): return 'Missing product code'
    return None

def build_evidence(rows, customer, start, end):
    """start inclusive, end exclusive; end also serves as recency reference date."""
    start,end=date.fromisoformat(str(start)),date.fromisoformat(str(end))
    if start >= end: raise ValueError('Start date must precede the exclusive end date.')
    customer=str(customer).strip()
    owned=[r for r in rows if r.get('CustomerID')==customer]
    if not owned: raise ValueError('Customer not found in the bundled sample. Try 13085, 12347, or 17850.')
    retained, rejected=[],[]
    for row in owned:
        try: day=datetime.fromisoformat(row['InvoiceDate']).date()
        except ValueError:
            rejected.append({**row,'Reason':'Invalid date'}); continue
        if not start <= day < end: continue
        reason=exclusion(row)
        if reason: rejected.append({**row,'Reason':reason})
        else: retained.append({**row,'LineAmountGBP':money(Decimal(row['Quantity'])*Decimal(row['Price']))})
    if not retained: raise ValueError('No valid purchases in this period. Widen the date range.')
    groups=defaultdict(list)
    for row in retained: groups[row['Invoice']].append(row)
    invoices=[]
    for invoice, members in sorted(groups.items()):
        invoices.append({'Invoice':invoice,'Date':min(x['InvoiceDate'] for x in members),
            'AmountGBP':money(sum((Decimal(x['LineAmountGBP']) for x in members),Decimal(0))),
            'LineCount':len(members),'RowIDs':[x['RowID'] for x in members]})
    total=sum((Decimal(x['AmountGBP']) for x in invoices),Decimal(0))
    last=max(datetime.fromisoformat(x['InvoiceDate']).date() for x in retained)
    n=len(invoices)
    facts={
        'recency':{'value':str((end-last).days),'unit':'days','meaning':'Days since the latest retained purchase','evidence':['LAST_PURCHASE','WINDOW']},
        'frequency':{'value':str(n),'unit':'invoices','meaning':'Distinct retained invoices','evidence':['ALL_INVOICES']},
        'monetary':{'value':money(total),'unit':'GBP','meaning':'Positive purchase amount, not net revenue','evidence':['ALL_INVOICES']},
        'aov':{'value':money(total/n),'unit':'GBP/invoice','meaning':'Purchase amount divided by distinct invoices','evidence':['ALL_INVOICES']},
        'diversity':{'value':str(len({x['StockCode'] for x in retained})),'unit':'product codes','meaning':'Distinct retained StockCodes, not semantic categories','evidence':['ALL_ROWS']},
    }
    package={'customer_id':customer,'window':{'start_inclusive':start.isoformat(),'end_exclusive':end.isoformat(),'analysis_date':end.isoformat()},
        'facts':facts,'invoices':invoices,'rows':retained,'excluded_rows':rejected,
        'source':{'file':'online_retail_II.xlsx','url':'https://archive.ics.uci.edu/dataset/502/online+retail+ii','policy':POLICY},
        'last_purchase':last.isoformat(),
        'limitations':['Only this retailer and selected customers are represented.','Canceled and non-positive records are excluded; refunds are not matched to original purchases.','Repeated source rows remain visible; no unverified duplicate removal.','These descriptive measures do not predict churn or customer intent.']}
    package['evidence_id']=hashlib.sha256(json.dumps(package,sort_keys=True).encode()).hexdigest()[:16]
    return package

def llm_evidence(package):
    """Send complete aggregates, exact facts and capped product examples, not every raw row."""
    return {k:package[k] for k in ['customer_id','window','facts','source','last_purchase','limitations','evidence_id']} | {
        'invoices':[{k:v for k,v in invoice.items() if k!='RowIDs'} for invoice in package['invoices']],
        'product_examples':[{'StockCode':r['StockCode'],'Description':r['Description'],'RowID':r['RowID']} for r in package['rows'][:6]],
        'excluded_count':len(package['excluded_rows']),
        'instruction':'Product examples are selected lines, not a complete product ranking.'}
