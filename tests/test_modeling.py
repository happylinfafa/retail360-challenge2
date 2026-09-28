import numpy as np
import pandas as pd
import pytest
from modeling import RFM, GRAPH_FEATURE, feature_input, graph_feature_from_history, make_model, evaluate, choose_threshold


def test_future_outcome_cannot_be_selected_as_feature():
    with pytest.raises(ValueError, match='allowlist'):
        feature_input(pd.DataFrame({'repurchase_60d': [1]}), ['repurchase_60d'])


def test_preprocessing_is_not_refitted_when_predicting():
    train = pd.DataFrame({'recency_days': [1, 2, 30, 90], 'frequency': [5, 4, 2, 1],
                          'monetary_gbp': [100, 80, 20, 10]})
    model = make_model('logistic').fit(feature_input(train, RFM), [1, 1, 0, 0])
    original = model.named_steps['scale'].mean_.copy()
    future = train * 100
    probabilities = model.predict_proba(feature_input(future, RFM))[:, 1]
    np.testing.assert_array_equal(original, model.named_steps['scale'].mean_)
    assert np.isfinite(probabilities).all()


def test_metrics_and_failure_slice():
    perfect = evaluate([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9], 0.5)
    assert perfect['average_precision'] == perfect['roc_auc'] == perfect['f1'] == 1
    assert perfect['lift_top_10pct'] == 2
    no_positive = evaluate([0, 0], [0.2, 0.3], 0.5)
    assert no_positive['average_precision'] is None and no_positive['roc_auc'] is None
    assert no_positive['lift_top_10pct'] is None
    assert 0.2 < choose_threshold([0, 0, 1, 1], np.array([0.1, 0.2, 0.8, 0.9])) <= 0.8


def test_dummy_uses_training_prevalence():
    train = pd.DataFrame({'recency_days': [1, 3, 8, 10]})
    model = make_model('dummy').fit(train, [1, 0, 0, 0])
    np.testing.assert_allclose(model.predict_proba(train*100)[:, 1], 0.25)


def test_customer_product_graph_is_historical_and_label_free():
    history = pd.DataFrame({'CustomerID': ['A', 'A', 'B', 'C', 'C'],
                            'StockCode': ['p1', 'p2', 'p1', 'p1', 'p3'],
                            'InvoiceDate': ['2011-05-01'] * 5,
                            'repurchase_60d': [1, 1, 0, 0, 0]})
    graph = graph_feature_from_history(history, '2011-06-01').set_index('CustomerID')
    assert graph.loc['A', GRAPH_FEATURE] == pytest.approx((np.log(4)+np.log(2))/2)
    assert graph.loc['B', GRAPH_FEATURE] == pytest.approx(np.log(4))
    future = history.copy()
    future.loc[0, 'InvoiceDate'] = '2011-06-01'
    with pytest.raises(ValueError, match='Post-cutoff'):
        graph_feature_from_history(future, '2011-06-01')
