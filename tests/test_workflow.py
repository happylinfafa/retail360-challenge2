import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from analytics import load_rows, build_evidence, exclusion
from ai import validate_response, explain

@pytest.fixture
def rows(): return load_rows()

@pytest.fixture
def package(rows): return build_evidence(rows,'13085','2009-12-01','2011-12-10')

def checked_output(package):
    return {'customer_id':package['customer_id'],'claims':[
        {'metric':key,'value':fact['value'],'explanation':'This is an observed purchase measure, limited to the selected period.',
         'evidence_refs':fact['evidence']} for key,fact in package['facts'].items()],
        'limitations':['The observed history does not establish future purchasing behavior.']}

def test_01_real_customer_values(package):
    assert {k:v['value'] for k,v in package['facts'].items()}=={
        'recency':'158','frequency':'8','monetary':'2433.28','aov':'304.16','diversity':'50'}
    assert len(package['rows'])==84

def test_02_invoice_and_row_provenance(package):
    assert {i['Invoice'] for i in package['invoices']}=={'489434','489435','490068','490069','496092','496166','544306','558996'}
    assert all(r['RowID']==f"{r['Worksheet']}:{r['ExcelRow']}" and int(r['ExcelRow'])>=2 for r in package['rows'])
    assert all(r['CustomerID']=='13085' for r in package['rows'])

def test_03_filter_recalculates(rows,package):
    reduced=build_evidence(rows,'13085','2011-01-01','2011-12-10')
    assert reduced['facts']['frequency']['value']=='2'
    assert reduced['evidence_id']!=package['evidence_id']
    assert all(r['InvoiceDate']>='2011-01-01' for r in reduced['rows'])

def test_04_missing_or_invalid_input(rows):
    with pytest.raises(ValueError,match='not found'): build_evidence(rows,'NOT-A-CUSTOMER','2009-12-01','2011-12-10')
    with pytest.raises(ValueError,match='No valid purchases'): build_evidence(rows,'13085','2011-12-01','2011-12-10')
    with pytest.raises(ValueError,match='must precede'): build_evidence(rows,'13085','2011-12-10','2009-12-01')

def test_05_cancellations_and_missing_customer(rows,package):
    assert any(exclusion(r)=='Cancellation invoice' for r in rows)
    assert sum(exclusion(r)=='Missing Customer ID' for r in rows)==6
    assert all(not r['Invoice'].upper().startswith('C') for r in package['rows'])
    assert all(exclusion(r) for r in package['excluded_rows'])

def test_06_output_checks_and_missing_evidence(package):
    good=checked_output(package); assert validate_response(good,package)==[]
    bad=copy.deepcopy(good);bad['claims'][0]['value']='999';bad['claims'][0]['evidence_refs']=['FAKE_INVOICE']
    assert len(validate_response(bad,package))>=2
    bad['customer_id']='17850'; assert 'Wrong customer ID.' in validate_response(bad,package)
    missing=copy.deepcopy(package);missing['facts'].pop('monetary')
    with pytest.raises(ValueError,match='evidence is missing'): explain(missing,'test-only','model','Overall profile')

def test_07_mocked_provider_and_no_key(package):
    # Integration contract only: this is NOT a live LLM evaluation.
    with pytest.raises(ValueError,match='API key'): explain(package,'','model','Overall profile')
    with patch('openai.OpenAI') as Client:
        Client.return_value.responses.create.return_value=SimpleNamespace(status='completed',output_text=json.dumps(checked_output(package)),id='mock-response')
        result=explain(package,'test-key','test-model','Overall profile')
        kwargs=Client.return_value.responses.create.call_args.kwargs
        assert kwargs['store'] is False
        assert result['response_id']=='mock-response'
        assert result['evidence_id']==package['evidence_id']

def test_08_streamlit_human_review_and_refinement():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert app.button(key='generate').disabled
    app.radio(key='human_decision').set_value('Accept')
    app.text_area(key='review_note').set_value('Checked the invoice count against the order table.')
    app.button(key='record_review').click().run()
    assert app.session_state['review_export']['target']=='computed_evidence_only'
    app.text_input(key='customer').set_value('17850').run()
    assert not app.exception
    assert 'review_export' not in app.session_state
    app.text_input(key='customer').set_value('NOT-A-CUSTOMER').run()
    assert any('not found' in e.value for e in app.error)
