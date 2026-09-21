"""Retail360: select, calculate, inspect, explain, and review."""
import json
import os
from datetime import date, datetime, timezone
import pandas as pd
import streamlit as st
from analytics import load_rows, build_evidence, exclusion
from ai import explain, local_models, DEFAULT_MODEL

st.set_page_config(page_title='Retail360 | Customer evidence',page_icon='🛍️',layout='wide')

@st.cache_data
def data():
    return load_rows()

st.title('Retail360')
st.write('Understand a customer’s purchases. Check the evidence. Review the explanation.')
st.caption('Challenge 2 · Customer behavior evidence explorer · UCI Online Retail II')
rows=data()
with st.sidebar:
    st.header('Analysis settings')
    customer=st.text_input('Customer ID',value='13085',help='Bundled customers: 13085, 12347, 17850',key='customer')
    start=st.date_input('Start date (inclusive)',value=date(2009,12,1),min_value=date(2009,12,1),max_value=date(2011,12,10),key='start')
    end=st.date_input('End / analysis date (exclusive)',value=date(2011,12,10),min_value=date(2009,12,1),max_value=date(2011,12,10),key='end')
    focus=st.selectbox('Explanation focus',['Overall profile','Recent purchase activity','Spending and order frequency','Product variety'],key='focus')
    st.caption('All metrics recalculate when you change the customer or dates.')
    st.divider()
    st.subheader('Free local AI')
    model=DEFAULT_MODEL
    available=model in local_models()
    st.write('Model: '+model)
    st.caption('Runs on this computer. No API key, account, or paid service is required.')
    if available: st.success('Local model ready')
    else:
        st.warning('Start Ollama and download the model first.')
        st.code('ollama pull qwen2.5:1.5b')
    if st.button('Refresh model status'): st.rerun()


try:
    package=build_evidence(rows,customer,start,end)
except ValueError as exc:
    st.error(str(exc)); st.stop()

context=(package['evidence_id'],focus,model)
if st.session_state.get('analysis_context') != context:
    for key in ['ai_result','review_export','review_note','human_decision','correction']:
        st.session_state.pop(key,None)
    st.session_state['analysis_context']=context

st.subheader(f'Customer {package["customer_id"]}')
st.caption(f'{start} ≤ transaction date < {end} · Recency reference: {end} · Evidence ID: {package["evidence_id"]}')
names={'recency':'Days since purchase','frequency':'Valid invoices','monetary':'Purchase amount','aov':'Average invoice','diversity':'Product codes'}
for column,(key,fact) in zip(st.columns(5),package['facts'].items()):
    value=('£' if key in ['monetary','aov'] else '')+fact['value']
    column.metric(names[key],value)
st.caption('Purchase-only amounts. Refunds are excluded, not reconciled against original purchases. Product codes do not represent semantic categories.')

left,right=st.columns([1.2,1])
with left:
    st.subheader('Order evidence')
    invoice_df=pd.DataFrame(package['invoices'])
    st.dataframe(invoice_df[['Invoice','Date','AmountGBP','LineCount']],hide_index=True,use_container_width=True)
    st.caption(f'{len(package["rows"])} retained product lines across {len(package["invoices"])} distinct invoices.')
with right:
    st.subheader('Purchase timeline')
    chart=invoice_df[['Date','AmountGBP']].copy()
    chart['Date']=pd.to_datetime(chart['Date']); chart['GBP']=chart['AmountGBP'].astype(float)
    st.bar_chart(chart.set_index('Date')['GBP'],color='#17654F',height=250)
    st.caption('Order amounts come from Python calculations, not the language model.')

st.subheader('AI explanation')
st.caption('The local model receives all-history features, up to ten recent invoice examples, selected product descriptions, and source references. Full invoice evidence remains below.')
st.caption('All explanations refer to the selected historical analysis date, not today. Values and source references are attached by Python.')
correction=st.text_area('What should the explanation clarify?',placeholder='For example: Explain why product rows are different from order count.',key='correction')
if not available:
    st.info('The local model is not ready. Calculations and evidence review still work. No AI explanation has been generated.')
if st.button('Generate AI explanation',type='primary',disabled=not available,key='generate'):
    st.session_state.pop('ai_result',None)
    st.session_state.pop('review_export',None)
    st.session_state.pop('human_decision',None)
    st.session_state.pop('review_note',None)
    try:
        with st.spinner('Retrieving evidence and generating explanation…'):
            st.session_state['ai_result']=explain(package,model,focus,correction)
    except ValueError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error('Local AI could not complete the request. Evidence is still available; check Ollama and retry.')

result=st.session_state.get('ai_result')
if result:
    st.success('Local model response received. Python attaches the verified values and evidence references.')
    for claim in result['content']['claims']:
        fact=package['facts'][claim['metric']]
        st.markdown(f'**{names[claim["metric"]]}: {claim["value"]} {fact["unit"]}**')
        st.write(claim['explanation'])
        st.caption('Metric definition: '+fact['meaning'])
        st.caption('Evidence: '+', '.join(claim['evidence_refs']))
    st.write('Model limitations: '+' '.join(result['content']['limitations']))
    st.caption(f'Model: {result["model"]} · Response: {result["response_id"]} · {result["generated_at"]}')
    st.warning('Automated checks cover numbers and reference keys. Please review the meaning of the prose before accepting it.')

with st.expander('Inspect original transaction rows and provenance'):
    invoice=st.selectbox('Inspect one invoice',['All invoices']+[x['Invoice'] for x in package['invoices']],key=f'invoice_{package["evidence_id"]}')
    detail=[x for x in package['rows'] if invoice=='All invoices' or x['Invoice']==invoice]
    st.dataframe(pd.DataFrame(detail),hide_index=True,use_container_width=True)
    st.write('ALL_INVOICES = the complete order table. ALL_ROWS = all retained rows. LAST_PURCHASE = the latest retained transaction. WINDOW = the selected dates.')
    st.write(f'Latest retained purchase: {package["last_purchase"]}')
    st.caption('SourceFile + Worksheet + ExcelRow locate each original Excel row. Selecting one invoice here does not change the overall profile.')

with st.expander('Cleaning decisions and limitations'):
    st.write('Rule version: '+package['source']['policy'])
    st.write(f'Excluded rows for this customer and period: {len(package["excluded_rows"])}')
    if package['excluded_rows']: st.dataframe(pd.DataFrame(package['excluded_rows']),hide_index=True)
    st.caption(f'The sample also includes {sum(exclusion(x)=="Missing Customer ID" for x in rows)} unassigned rows. They cannot be attributed to any customer.')
    for limitation in package['limitations']: st.write(limitation)

st.subheader('Human review')
st.caption('Review applies to the current AI answer when available; otherwise it applies only to the computed evidence.')
decision=st.radio('Your decision',['Not reviewed','Accept','Reject','Needs correction'],horizontal=True,key='human_decision')
review_note=st.text_area('Review note / correction',key='review_note')
if st.button('Record review',key='record_review'):
    if decision=='Not reviewed': st.warning('Choose a review decision first.')
    else:
        st.session_state['review_export']={'evidence_id':package['evidence_id'],'customer_id':package['customer_id'],
            'target':'live_ai_response' if result else 'computed_evidence_only','response_id':result['response_id'] if result else None,
            'decision':decision,'note':review_note,'recorded_at':datetime.now(timezone.utc).isoformat()}
        st.success('Review recorded in this session. Download it below to keep a copy.')
if st.session_state.get('review_export'):
    st.download_button('Download review (JSON)',json.dumps(st.session_state['review_export'],indent=2),'retail360_review.json','application/json')
st.download_button('Download evidence package (JSON)',json.dumps(package,indent=2),'retail360_evidence.json','application/json')
if result:
    st.download_button('Download AI result (JSON)',json.dumps(result,indent=2),'retail360_ai_result.json','application/json')
st.caption('Source: Chen, D. (2012), Online Retail II, UCI Machine Learning Repository, CC BY 4.0. Selected public customer IDs are dataset identifiers.')
st.link_button('Original dataset and documentation',package['source']['url'])
