import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from analytics import load_rows, build_evidence, exclusion, llm_evidence
from ai import validate_response, explain, DEFAULT_MODEL, local_models

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
    large=build_evidence(rows,'17850','2009-12-01','2011-12-10')
    compact=llm_evidence(large)
    assert compact['facts']==large['facts']
    assert len(compact['recent_invoice_examples'])==10
    assert compact['coverage']['total_invoices']==155

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
    numeric=copy.deepcopy(good);numeric['claims'][0]['explanation']='The last purchase was 158 days before the reference date.'
    assert validate_response(numeric,package)==[]
    numeric['claims'][0]['explanation']='The last purchase was 999 days before the reference date.'
    assert 'Unverified numerical text in explanation.' in validate_response(numeric,package)
    numeric['claims'][0]['explanation']='The last purchase was July 5, 2011, which is 158 days before the reference date.'
    assert validate_response(numeric,package)==[]
    numeric['claims'][0]['explanation']='The last purchase was July 6, 2011.'
    assert 'Unverified numerical text in explanation.' in validate_response(numeric,package)
    missing=copy.deepcopy(package);missing['facts'].pop('monetary')
    with pytest.raises(ValueError,match='evidence is missing'): explain(missing)

def test_07_mocked_local_provider_and_failure(package):
    # Integration contract only: this is NOT a live LLM evaluation.
    import requests
    with pytest.raises(ValueError,match='local qwen'): explain(package,'cloud-model')
    with patch('requests.post') as post:
        generated={'explanations':{k:'This describes observed purchases in the selected period.' for k in package['facts']},'limitations':['No prediction of future behavior.']}
        post.return_value.json.return_value={'done':True,'message':{'content':json.dumps(generated)}}
        result=explain(package)
        assert post.call_args.args[0]=='http://127.0.0.1:11434/api/chat'
        assert post.call_args.kwargs['json']['model']==DEFAULT_MODEL
        assert result['response_id'].startswith('local-')
        assert result['evidence_id']==package['evidence_id']
    with patch('requests.post',side_effect=requests.ConnectionError):
        with pytest.raises(ValueError,match='Local model unavailable'): explain(package)
    with patch('requests.post',side_effect=requests.Timeout):
        with pytest.raises(ValueError,match='timed out'): explain(package)
    with patch('requests.get',side_effect=requests.ConnectionError): assert local_models()==[]

def test_08_streamlit_human_review_and_refinement():
    from streamlit.testing.v1 import AppTest
    with patch('ai.local_models',return_value=[]):
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
