from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest


def test_prediction_evidence_and_review_reset():
    root = Path(__file__).resolve().parents[1]
    if not (root/'runtime/models_v2_graph/customer_predictions.csv').exists():
        pytest.skip('Run the real training pipeline before this integration test.')
    app = AppTest.from_file(str(root/'pages/2_Repurchase.py'), default_timeout=30).run()
    assert not app.exception
    assert len(app.metric) == 3 and len(app.dataframe) >= 3
    app.radio(key='prediction_review').set_value('Reject / investigate').run()
    app.text_area(key='prediction_note').input('Check source purchase rows.').run()
    customers = app.selectbox(key='prediction_customer').options
    app.selectbox(key='prediction_customer').select(customers[1]).run()
    assert not app.exception
    assert app.radio(key='prediction_review').value == 'Needs review'
    assert app.text_area(key='prediction_note').value == ''
