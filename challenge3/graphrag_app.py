"""Local Streamlit demonstration of three grounded Retail360 GraphRAG tasks."""
import os
import streamlit as st
from graphrag import answer, credentials

st.set_page_config(page_title='Retail360 GraphRAG',layout='wide')
st.title('Retail360 GraphRAG')
st.caption('Neo4j evidence + local Qwen explanation. Illustrative UCI sample: two customers.')
examples=[
    'What did customer 12347 buy in invoice 549222?',
    'Which orders show both customer 12347 and customer 13085 bought a shared product?',
    'How similar are customer 12347 and customer 13085 based on purchased products?',
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
        st.subheader('Retrieved KG evidence')
        st.json(result['facts'])
        if result['evidence']: st.dataframe(result['evidence'],use_container_width=True)
        else: st.warning('No source records were retrieved. Review the IDs or question.')
        st.caption('Source row IDs and invoice IDs link this answer to the original UCI workbook. Human review is required.')
    except Exception as exc:
        st.error(f'Could not complete the question: {exc}')
