"""Reproducible historical models. Never use labels as feature inputs."""
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, roc_auc_score, f1_score,
                             brier_score_loss, precision_score, recall_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from repurchase import FEATURE_COLUMNS

RFM = ['recency_days', 'frequency', 'monetary_gbp']
GRAPH_FEATURE = 'mean_log_product_customer_degree'
MODELING_FEATURES = FEATURE_COLUMNS + [GRAPH_FEATURE]
SEED = 42


def feature_input(table, columns):
    if not set(columns).issubset(MODELING_FEATURES):
        raise ValueError('Only the frozen historical and graph feature allowlist is permitted.')
    values = table[columns].apply(pd.to_numeric, errors='raise')
    if (values < 0).any().any() or np.isinf(values.to_numpy()).any():
        raise ValueError('Features must be nonnegative and finite, or missing.')
    return values


def make_model(name):
    if name == 'dummy':
        estimator = DummyClassifier(strategy='prior')
    elif name == 'logistic':
        estimator = LogisticRegression(C=1.0, max_iter=2000, random_state=SEED)
    elif name == 'boosted_tree':
        estimator = HistGradientBoostingClassifier(max_iter=150, max_leaf_nodes=15,
            learning_rate=0.05, l2_regularization=1.0, early_stopping=False, random_state=SEED)
    else:
        raise ValueError('Unknown model')
    return Pipeline([('imputer', SimpleImputer(strategy='median', add_indicator=True)),
                     ('log', FunctionTransformer(np.log1p, feature_names_out='one-to-one')),
                     ('scale', StandardScaler()), ('model', estimator)])


def choose_threshold(y, probabilities):
    # Fixed small grid; ties prefer the value closest to 0.5, then the smaller value.
    grid = np.linspace(0.05, 0.95, 19)
    return float(max(grid, key=lambda t: (f1_score(y, probabilities >= t, zero_division=0),
                                          -abs(t-0.5), -t)))


def evaluate(y, probabilities, threshold):
    y, probabilities = np.asarray(y), np.asarray(probabilities)
    count = max(1, int(np.ceil(0.1*len(y))))
    # Stable tie breaking preserves the customer order, independent of labels.
    top = np.argsort(-probabilities, kind='stable')[:count]
    base = float(y.mean())
    predictions = probabilities >= threshold
    two_classes = len(np.unique(y)) == 2
    return {'n': len(y), 'positive_rate': base,
            'average_precision': float(average_precision_score(y, probabilities)) if y.sum() else None,
            'roc_auc': float(roc_auc_score(y, probabilities)) if two_classes else None,
            'f1': float(f1_score(y, predictions, zero_division=0)),
            'precision': float(precision_score(y, predictions, zero_division=0)),
            'recall': float(recall_score(y, predictions, zero_division=0)),
            'brier': float(brier_score_loss(y, probabilities)),
            'precision_top_10pct': float(y[top].mean()),
            'lift_top_10pct': float(y[top].mean()/base) if base else None,
            'threshold': float(threshold)}


def graph_feature_from_history(history, cutoff):
    """One bipartite customer--product graph feature, built strictly before cutoff.

    Product degree is the number of distinct historical customers attached to a
    product node. The customer feature is the mean log1p product degree across
    the customer's distinct purchased products. No labels or post-cutoff rows
    are used.
    """
    required = {'CustomerID', 'StockCode', 'InvoiceDate'}
    if not required.issubset(history.columns):
        raise ValueError('Historical graph input lacks required columns.')
    dates = pd.to_datetime(history['InvoiceDate'])
    if (dates >= pd.Timestamp(cutoff)).any():
        raise ValueError('Post-cutoff transaction reached graph construction.')
    edges = history[['CustomerID', 'StockCode']].drop_duplicates()
    product_degree = edges.groupby('StockCode')['CustomerID'].nunique()
    edges = edges.assign(product_degree=edges['StockCode'].map(product_degree))
    output = edges.assign(log_degree=np.log1p(edges['product_degree'])).groupby('CustomerID')['log_degree'].mean()
    return output.rename(GRAPH_FEATURE).reset_index()


def load_partition(root, protocol, split):
    frames = []
    for spec in protocol['snapshots']:
        if spec['split'] != split:
            continue
        folder = root/split/spec['cutoff']
        features = pd.read_csv(folder/'features.csv', dtype={'CustomerID': str, 'cutoff': str})
        labels = pd.read_csv(folder/'labels.csv', dtype={'CustomerID': str, 'cutoff': str})
        audit = pd.read_csv(folder/'audit.csv', dtype={'CustomerID': str, 'cutoff': str})
        keys = ['cutoff', 'CustomerID']
        if set(map(tuple, features[keys].values)) != set(map(tuple, labels[keys].values)):
            raise ValueError('Feature and label keys differ.')
        joined = features.merge(labels[keys+['repurchase_60d']], on=keys, validate='one_to_one')
        joined = joined.merge(audit[keys+['last_observed_country']], on=keys, validate='one_to_one')
        history = pd.read_csv(folder/'history_transactions.csv.gz', dtype={'CustomerID': str, 'StockCode': str})
        graph = graph_feature_from_history(history, spec['cutoff'])
        joined = joined.merge(graph, on='CustomerID', validate='one_to_one')
        if len(joined) != len(features) or not joined.repurchase_60d.isin([0, 1]).all():
            raise ValueError('Invalid audit join or labels.')
        frames.append(joined)
    return pd.concat(frames, ignore_index=True).sort_values(['cutoff', 'CustomerID']).reset_index(drop=True)
