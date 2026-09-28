from copy import deepcopy
import hashlib

import pandas as pd
import pytest

from repurchase import (TRANSACTION_COLUMNS, build_snapshot, feature_table,
                        load_protocol, read_workbook, validate_protocol, windows)


def frame(records):
    data = [(customer, invoice, 'P1', pd.Timestamp(date), 125, 'UK', str(i))
            for i, (customer, invoice, date) in enumerate(records)]
    return pd.DataFrame(data, columns=TRANSACTION_COLUMNS)


def test_frozen_protocol_and_split_embargo():
    protocol = load_protocol()
    invalid = deepcopy(protocol)
    invalid['snapshots'][2]['cutoff'] = '2011-05-01'
    with pytest.raises(ValueError, match='overlap'):
        validate_protocol(invalid)


def test_exact_window_boundaries():
    protocol = load_protocol()
    begin, cutoff, end = windows('2011-06-01', protocol)
    data = frame([('A', 'old', begin-pd.Timedelta(seconds=1)),
                  ('A', 'first', begin), ('A', 'last', cutoff-pd.Timedelta(seconds=1)),
                  ('A', 'future1', cutoff), ('A', 'future2', end-pd.Timedelta(seconds=1)),
                  ('A', 'outside', end), ('B', 'new-only', cutoff)])
    features, labels, _, history, future, _ = build_snapshot(data, cutoff, protocol)
    assert features.CustomerID.tolist() == ['A']
    assert features.frequency.tolist() == [2]
    assert features.monetary_gbp.tolist() == ['2.50']
    assert set(history.Invoice) == {'first', 'last'}
    assert set(future.Invoice) == {'future1', 'future2'}
    assert labels.label_invoice_count.tolist() == [2]
    assert labels.repurchase_60d.tolist() == [1]


def test_future_changes_cannot_change_features_or_eligibility():
    protocol = load_protocol()
    past = frame([('A', '1', '2011-05-01'), ('B', '2', '2011-05-02')])
    extended = pd.concat([past, frame([('A', '3', '2011-06-15'), ('C', '4', '2011-06-20')])])
    before = build_snapshot(past, '2011-06-01', protocol)
    after = build_snapshot(extended, '2011-06-01', protocol)
    pd.testing.assert_frame_equal(before[0], after[0])
    assert before[1].repurchase_60d.tolist() == [0, 0]
    assert after[1].repurchase_60d.tolist() == [1, 0]


def test_insufficient_followup_is_error_not_negative_label():
    protocol = load_protocol()
    protocol['coverage_end_exclusive'] = '2011-06-15'
    with pytest.raises(ValueError, match='follow-up'):
        build_snapshot(frame([('A', '1', '2011-05-01')]), '2011-06-01', protocol)


def test_insufficient_history_rejected():
    with pytest.raises(ValueError, match='historical'):
        build_snapshot(frame([('A', '1', '2010-01-01')]), '2010-02-01', load_protocol())


def test_frequency_is_orders_not_rows_and_single_order_gap_missing():
    data = frame([('A', '1', '2011-05-01'), ('A', '1', '2011-05-01'),
                  ('B', '2', '2011-05-01'), ('B', '3', '2011-05-11')])
    table = feature_table(data, '2011-06-01').set_index('CustomerID')
    assert table.loc['A', 'frequency'] == 1
    assert table.loc['A', 'aov_gbp'] == '2.50'
    assert pd.isna(table.loc['A', 'mean_invoice_gap_days'])
    assert table.loc['B', 'mean_invoice_gap_days'] == 10
    protocol = load_protocol()
    protocol['minimum_history_invoices'] = 2
    assert build_snapshot(data, '2011-06-01', protocol)[0].CustomerID.tolist() == ['B']


def test_feature_function_blocks_future():
    with pytest.raises(ValueError, match='Future'):
        feature_table(frame([('A', '1', '2011-06-01')]), '2011-06-01')


def test_workbook_cleaning_hash_and_original_provenance(tmp_path):
    from openpyxl import Workbook
    from datetime import datetime
    book = Workbook()
    sheet = book.active
    sheet.title = 'Original'
    sheet.append(['Customer ID', 'Invoice', 'StockCode', 'InvoiceDate', 'Quantity', 'Price', 'Country'])
    for customer, invoice, quantity in [(123, '1', 2), (None, '2', 1), (123, 'C3', 1), (123, '4', 0)]:
        sheet.append([customer, invoice, 'P1', datetime(2011, 5, 1), quantity, 1.25, 'UK'])
    path = tmp_path/'source.xlsx'
    book.save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    data, audit = read_workbook(path, digest)
    assert audit['raw_rows'] == 4 and audit['retained_rows'] == 1
    assert data.RowID.tolist() == ['Original:2']
    assert data.AmountPence.tolist() == [250]
    with pytest.raises(ValueError, match='differs'):
        read_workbook(path, 'wrong')
