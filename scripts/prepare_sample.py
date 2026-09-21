"""Extract full histories for three real customers; retain Excel row provenance."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime
import openpyxl

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('workbook', type=Path)
    args = parser.parse_args()
    selected = {'13085', '12347', '17850'}
    records, missing = [], 0
    workbook = openpyxl.load_workbook(args.workbook, read_only=True, data_only=True)
    for sheet in workbook.worksheets:
        rows = sheet.iter_rows(values_only=True)
        fields = next(rows)
        for number, values in enumerate(rows, 2):
            record = dict(zip(fields, values))
            customer = record.get('Customer ID')
            customer = str(int(customer)) if customer is not None else ''
            if customer not in selected and not (not customer and missing < 6):
                continue
            if not customer:
                missing += 1
            records.append({
                'CustomerID':customer, 'Invoice':str(record.get('Invoice') or ''),
                'StockCode':str(record.get('StockCode') or ''),
                'Description':str(record.get('Description') or '').strip(),
                'Quantity':str(record.get('Quantity') or 0), 'Price':str(record.get('Price') or 0),
                'InvoiceDate':record['InvoiceDate'].isoformat(sep=' ') if isinstance(record.get('InvoiceDate'),datetime) else '',
                'Country':str(record.get('Country') or ''), 'SourceFile':args.workbook.name,
                'Worksheet':sheet.title, 'ExcelRow':number,
                'RowID':f'{sheet.title}:{number}',
            })
    out = ROOT / 'data'
    out.mkdir(exist_ok=True)
    with (out/'transactions_sample.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    manifest = {
        'source':'https://archive.ics.uci.edu/dataset/502/online+retail+ii',
        'attribution':'Chen, D. (2012). Online Retail II. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D',
        'license':'CC BY 4.0', 'source_sha256':hashlib.sha256(args.workbook.read_bytes()).hexdigest(),
        'customers':sorted(selected), 'rows':len(records),
        'sampling':'Complete source histories for three selected customers plus six missing-ID rows for cleaning audit. Not a population-representative sample.',
        'observation_start':'2009-12-01', 'observation_end_exclusive':'2011-12-10',
    }
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2))

if __name__ == '__main__':
    main()
