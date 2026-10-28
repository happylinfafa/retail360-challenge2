"""Local Streamlit demonstration of three grounded Retail360 GraphRAG tasks."""
import os
import streamlit as st
from graphrag import answer, credentials

st.set_page_config(page_title='Retail360 GraphRAG',layout='wide')
st.title('Retail360 GraphRAG')
st.caption('Neo4j evidence + local Qwen explanation. Community search uses a 300-customer exploratory UCI cohort; older examples use a two-customer sample.')
examples=[
    'What did customer 12347 buy in invoice 549222?',
    'Which orders show both customer 12347 and customer 13085 bought a shared product?',
    'How similar are customer 12347 and customer 13085 based on purchased products?',
    'Which customers in customer 15719’s community bought similar products, and why?',
]
example=st.selectbox('Example question',examples)
question=st.text_input('Your question',value=example)
if st.button('Retrieve and explain',type='primary'):
    try:
        with st.spinner('Retrieving graph evidence and asking the local model…'):
            private=os.getenv('RETAIL360_NEO4J_CREDENTIALS')
            result=answer(question,credentials(private))
        st.subheader('Answer from exact graph facts');st.write(result['answer'])
        st.subheader('Local LLM interpretation')
        if result.get('llmVerified') is False and result['status']=='ok':
            st.warning('The model explanation did not pass the evidence check. Use the exact facts and source rows below.')
        if isinstance(result['llm'],dict):
            st.write(result['llm']['interpretation'])
            st.info(result['llm']['limitation'])
        else: st.info(result['llm'])
        if result['kind']=='community' and result['status']=='ok':
            st.subheader('Customer relationship preview')
            target=result['facts']['customer']
            peers=result['facts']['peers']
            nodes=[{'id':target,'x':0.16,'y':0.5,'role':'Selected customer'}]
            edges=[]
            for index,peer in enumerate(peers):
                y=0.2+index*0.3
                nodes.append({'id':peer['peer'],'x':0.78,'y':y,
                              'role':f"{peer['sharedProductCount']} shared products; Jaccard {peer['jaccard']:.3f}"})
                edges.append({'x':0.16,'x2':0.78,'y':0.5,'y2':y,
                              'score':peer['jaccard']})
            chart={'width':'container','height':260,'layer':[
                {'data':{'values':edges},'mark':{'type':'rule','stroke':'#087f8c','strokeWidth':2},
                 'encoding':{'x':{'field':'x','type':'quantitative','scale':{'domain':[0,1]},'axis':None},
                             'x2':{'field':'x2'},'y':{'field':'y','type':'quantitative','scale':{'domain':[0,1]},'axis':None},
                             'y2':{'field':'y2'},'tooltip':[{'field':'score','title':'Jaccard'}]}},
                {'data':{'values':nodes},'mark':{'type':'circle','size':1900,'color':'#d9eef2','stroke':'#087f8c'},
                 'encoding':{'x':{'field':'x','type':'quantitative','scale':{'domain':[0,1]},'axis':None},
                             'y':{'field':'y','type':'quantitative','scale':{'domain':[0,1]},'axis':None},
                             'tooltip':[{'field':'id','title':'Customer'},{'field':'role','title':'Evidence'}]}},
                {'data':{'values':nodes},'mark':{'type':'text','fontSize':14,'fontWeight':'bold'},
                 'encoding':{'x':{'field':'x','type':'quantitative','scale':{'domain':[0,1]},'axis':None},
                             'y':{'field':'y','type':'quantitative','scale':{'domain':[0,1]},'axis':None},
                             'text':{'field':'id'}}}]}
            st.vega_lite_chart(chart,width='stretch')
            st.caption('Edges show the top three directly linked peers in the same exploratory community. Inspect the source rows below before drawing conclusions.')
        st.subheader('Retrieved KG evidence')
        st.json(result['facts'])
        if result['evidence']: st.dataframe(result['evidence'],width='stretch')
        else: st.warning('No source records were retrieved. Review the IDs or question.')
        st.caption('Source row IDs and invoice IDs link this answer to the original UCI workbook. Human review is required.')
    except Exception as exc:
        st.error(f'Could not complete the question: {exc}')
