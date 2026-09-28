"""Historical snapshots for 60-day repurchase; no training or model fitting here."""
from collections import Counter
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pandas as pd
from analytics import exclusion, money

ROOT = Path(__file__).resolve().parent
FEATURE_COLUMNS = ['recency_days', 'frequency', 'monetary_gbp', 'aov_gbp',
                   'product_diversity', 'orders_last_30d', 'active_purchase_days',
                   'mean_invoice_gap_days']
TRANSACTION_COLUMNS = ['CustomerID', 'Invoice', 'StockCode', 'InvoiceDate',
                       'AmountPence', 'Country', 'RowID']


def load_protocol(path=None):
    protocol = json.loads(Path(path or ROOT/'config/repurchase_protocol.json').read_text())
    validate_protocol(protocol)
    return protocol


def windows(cutoff, protocol):
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is not None or cutoff != cutoff.normalize():
        raise ValueError('Cutoff must be a timezone-naive midnight date.')
    return (cutoff - pd.Timedelta(days=protocol['lookback_days']), cutoff,
            cutoff + pd.Timedelta(days=protocol['horizon_days']))


def validate_protocol(protocol):
    for key in ['lookback_days', 'horizon_days', 'minimum_history_invoices']:
        if not isinstance(protocol[key], int) or protocol[key] < 1:
            raise ValueError(f'{key} must be a positive integer.')
    start, end = pd.Timestamp(protocol['coverage_start']), pd.Timestamp(protocol['coverage_end_exclusive'])
    if start >= end:
        raise ValueError('Invalid source coverage.')
    snapshots = protocol['snapshots']
    if not snapshots:
        raise ValueError('At least one snapshot is required.')
    dates = [pd.Timestamp(s['cutoff']) for s in snapshots]
    if dates != sorted(set(dates)):
        raise ValueError('Snapshot cutoffs must be unique and chronological.')
    ranks = {'train': 0, 'validation': 1, 'test': 2}
    splits = [s['split'] for s in snapshots]
    if set(splits) != set(ranks) or [ranks[x] for x in splits] != sorted(ranks[x] for x in splits):
        raise ValueError('Require chronological train, validation, and test blocks.')
    for snapshot in snapshots:
        begin, _, finish = windows(snapshot['cutoff'], protocol)
        if begin < start:
            raise ValueError('Insufficient historical coverage for a full observation window.')
        if finish > end:
            raise ValueError('Insufficient follow-up: do not label censored customers as zero.')
    for earlier, later in [('train', 'validation'), ('validation', 'test')]:
        labels_ready = max(windows(s['cutoff'], protocol)[2] for s in snapshots if s['split'] == earlier)
        next_prediction = min(pd.Timestamp(s['cutoff']) for s in snapshots if s['split'] == later)
        if labels_ready > next_prediction:
            raise ValueError('Label windows overlap a later split cutoff: future information would leak.')


def read_workbook(path, expected_sha256):
    """Read the complete source once; retain integer pennies and original row IDs."""
    import openpyxl
    path = Path(path)
    with path.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    if digest != expected_sha256:
        raise ValueError('Workbook differs from the frozen source. Review source coverage and update protocol explicitly.')
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    retained, counts, sheets = [], Counter(), {}
    first_seen, last_seen = None, None
    try:
        for sheet in book.worksheets:
            iterator = sheet.iter_rows(values_only=True)
            header = next(iterator)
            required = {'Customer ID', 'Invoice', 'StockCode', 'InvoiceDate', 'Quantity', 'Price', 'Country'}
            if not required.issubset(header):
                raise ValueError(f'Unexpected schema in {sheet.title}.')
            sheet_count = 0
            for excel_row, values in enumerate(iterator, 2):
                raw = dict(zip(header, values))
                if all(value is None for value in values):
                    continue
                sheet_count += 1
                stamp = raw['InvoiceDate']
                if isinstance(stamp, datetime):
                    first_seen = min(first_seen, stamp) if first_seen else stamp
                    last_seen = max(last_seen, stamp) if last_seen else stamp
                cid = raw['Customer ID']
                record = {
                    'CustomerID': str(int(cid)) if cid is not None else '',
                    'Invoice': str(raw['Invoice'] or '').strip(),
                    'StockCode': str(raw['StockCode'] or '').strip(),
                    'InvoiceDate': stamp.isoformat() if isinstance(stamp, datetime) else '',
                    'Quantity': str(raw['Quantity']), 'Price': str(raw['Price']),
                }
                reason = exclusion(record)
                if reason:
                    counts[reason] += 1
                    continue
                pennies = int(Decimal(money(Decimal(record['Quantity']) * Decimal(record['Price']))) * 100)
                retained.append((record['CustomerID'], record['Invoice'], record['StockCode'],
                                 stamp, pennies, str(raw['Country'] or ''), f'{sheet.title}:{excel_row}'))
            sheets[sheet.title] = sheet_count
            print(f'Read {sheet.title}: {sheet_count:,} rows', flush=True)
    finally:
        book.close()
    frame = pd.DataFrame.from_records(retained, columns=TRANSACTION_COLUMNS)
    frame['InvoiceDate'] = pd.to_datetime(frame['InvoiceDate'])
    if not frame['RowID'].is_unique:
        raise ValueError('Source row identifiers are not unique.')
    return frame, {
        'file': path.name, 'sha256': digest, 'raw_rows': sum(sheets.values()),
        'retained_rows': len(frame), 'excluded_by_first_reason': dict(counts), 'sheets': sheets,
        'first_observed_timestamp': str(first_seen), 'last_observed_timestamp': str(last_seen),
    }


def feature_table(history, cutoff):
    """Only pre-cutoff transactions enter this function. Future labels are separate."""
    cutoff = pd.Timestamp(cutoff)
    if history.empty:
        raise ValueError('No valid historical purchases.')
    if (history['InvoiceDate'] >= cutoff).any():
        raise ValueError('Future transaction reached feature calculation.')
    orders = history.groupby(['CustomerID', 'Invoice'], sort=True).agg(
        date=('InvoiceDate', 'min'), amount_pence=('AmountPence', 'sum')).reset_index()
    grouped = history.groupby('CustomerID', sort=True)
    result = pd.DataFrame(index=sorted(history['CustomerID'].unique()))
    result.index.name = 'CustomerID'
    result['recency_days'] = (cutoff - grouped['InvoiceDate'].max().dt.normalize()).dt.days
    result['frequency'] = orders.groupby('CustomerID').size()
    amounts = grouped['AmountPence'].sum()
    # Store money as exact decimal strings in CSV; the later training layer can cast it.
    result['monetary_gbp'] = amounts.map(lambda n: money(Decimal(int(n))/100))
    result['aov_gbp'] = [money(Decimal(int(amounts[c]))/100/int(result.loc[c, 'frequency'])) for c in result.index]
    result['product_diversity'] = grouped['StockCode'].nunique()
    recent = orders[orders['date'] >= cutoff-pd.Timedelta(days=30)].groupby('CustomerID').size()
    result['orders_last_30d'] = recent.reindex(result.index, fill_value=0)
    result['active_purchase_days'] = history.assign(day=history['InvoiceDate'].dt.normalize()).groupby('CustomerID')['day'].nunique()
    gaps = orders.sort_values(['CustomerID', 'date', 'Invoice']).groupby('CustomerID')['date'].diff().dt.total_seconds()/86400
    result['mean_invoice_gap_days'] = orders.assign(gap=gaps).groupby('CustomerID')['gap'].mean()
    return result.reset_index()


def build_snapshot(transactions, cutoff, protocol):
    begin, cutoff, finish = windows(cutoff, protocol)
    if begin < pd.Timestamp(protocol['coverage_start']):
        raise ValueError('Insufficient historical coverage.')
    if finish > pd.Timestamp(protocol['coverage_end_exclusive']):
        raise ValueError('Insufficient follow-up: labels would be censored.')
    history = transactions[(transactions['InvoiceDate'] >= begin) & (transactions['InvoiceDate'] < cutoff)].copy()
    future = transactions[(transactions['InvoiceDate'] >= cutoff) & (transactions['InvoiceDate'] < finish)]
    features = feature_table(history, cutoff)
    candidates = len(features)
    features = features[features['frequency'] >= protocol['minimum_history_invoices']].copy()
    if features.empty:
        raise ValueError('No eligible customers for this cutoff.')
    eligible = set(features['CustomerID'])
    history = history[history['CustomerID'].isin(eligible)].copy()
    matched = future[future['CustomerID'].isin(eligible)]
    counts = matched.groupby('CustomerID')['Invoice'].nunique()
    labels = features[['CustomerID']].copy()
    labels['repurchase_60d'] = labels['CustomerID'].isin(counts.index).astype(int)
    labels['label_invoice_count'] = labels['CustomerID'].map(counts).fillna(0).astype(int)
    first_purchase = matched.groupby('CustomerID')['InvoiceDate'].min()
    labels['first_label_purchase'] = first_purchase.reindex(labels['CustomerID']).to_numpy()
    labels['label_end_exclusive'] = finish.isoformat()
    # Metadata remains separate so future outcomes / IDs cannot accidentally become features.
    audit = history.groupby('CustomerID').agg(
        first_feature_transaction=('InvoiceDate', 'min'), last_feature_transaction=('InvoiceDate', 'max'),
        retained_history_rows=('RowID', 'size')).reset_index()
    latest = history.sort_values(['InvoiceDate', 'RowID']).groupby('CustomerID').tail(1)
    audit['last_observed_country'] = audit['CustomerID'].map(latest.set_index('CustomerID')['Country'])
    for table in [features, labels, audit]:
        table.insert(0, 'cutoff', cutoff.date().isoformat())
    summary = {
        'cutoff': cutoff.date().isoformat(), 'history_start_inclusive': begin.date().isoformat(),
        'history_end_exclusive': cutoff.date().isoformat(), 'label_start_inclusive': cutoff.date().isoformat(),
        'label_end_exclusive': finish.date().isoformat(), 'candidate_customers': candidates,
        'eligible_customers': len(features), 'excluded_by_minimum_history': candidates-len(features),
        'positive_labels': int(labels['repurchase_60d'].sum()), 'negative_labels': int((labels['repurchase_60d']==0).sum()),
        'positive_rate': float(labels['repurchase_60d'].mean()), 'history_rows': len(history),
        'label_purchase_rows': len(matched),
        'previously_observed_customers_not_eligible': len(set(transactions.loc[transactions['InvoiceDate'] < cutoff, 'CustomerID'])-eligible),
    }
    return features, labels, audit, history, matched.copy(), summary
