"""Smoke-test the local community flow in the existing Streamlit app."""
import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

root=Path(__file__).resolve().parents[2]
os.environ.setdefault('RETAIL360_NEO4J_CREDENTIALS',str(root/'.neo4j-local'/'credentials.json'))
app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'challenge3'/'graphrag_app.py'),default_timeout=40)
app.run()
question="Which customers in customer 15719's community bought similar products, and why?"
app.text_input[0].set_value(question)
app.button[0].click().run()
assert not app.exception, [e.message for e in app.exception]
assert len(app.get('vega_lite_chart'))==1
assert len(app.get('dataframe'))==1
print('Streamlit community input, relationship chart, and evidence table: pass')
