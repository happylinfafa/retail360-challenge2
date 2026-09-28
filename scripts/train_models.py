"""Train on frozen history, select on validation, then evaluate the held-out test once."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, davies_bouldin_score, adjusted_rand_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from threadpoolctl import threadpool_limits
from modeling import RFM, GRAPH_FEATURE, SEED, feature_input, make_model, choose_threshold, evaluate, load_partition
from repurchase import ROOT, FEATURE_COLUMNS, load_protocol


def run(data, output):
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output is not empty. Preserve previous results; choose a new --output.')
    protocol = load_protocol()
    manifest_path = data/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if manifest['protocol'] != protocol or manifest['feature_columns'] != FEATURE_COLUMNS:
        raise ValueError('Prepared data do not match the frozen protocol.')
    train = load_partition(data, protocol, 'train')
    valid = load_partition(data, protocol, 'validation')
    # Selection below has no access to test data or labels.
    output.mkdir(parents=True, exist_ok=True)
    candidates, results = {}, []
    for family, columns in [('rfm', RFM), ('full', FEATURE_COLUMNS),
                            ('full_plus_graph', FEATURE_COLUMNS + [GRAPH_FEATURE])]:
        for name in ['dummy', 'logistic', 'boosted_tree']:
            key = f'{family}_{name}'
            model = make_model(name)
            model.fit(feature_input(train, columns), train.repurchase_60d)
            scores = model.predict_proba(feature_input(valid, columns))[:, 1]
            threshold = choose_threshold(valid.repurchase_60d, scores)
            metrics = evaluate(valid.repurchase_60d, scores, threshold)
            candidates[key] = (model, columns, threshold)
            results.append({'model': key, 'split': 'validation', **metrics})
            print(f'{key}: validation AP={metrics["average_precision"]:.4f}', flush=True)
    selected = max(results, key=lambda row: row['average_precision'])['model']
    selection = {'selected_model': selected, 'criterion': 'Highest validation average precision; ties use fixed candidate order.',
                 'threshold_rule': 'Validation F1, fixed grid 0.05..0.95 step 0.05.',
                 'test_used_for_selection': False, 'seed': SEED, 'sklearn_version': sklearn.__version__,
                 'protocol_version': protocol['version'],
                 'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    (output/'selection.json').write_text(json.dumps(selection, indent=2))

    # Fit segmentation on the latest training snapshot: one row per customer.
    cluster_train = train[train.cutoff == train.cutoff.max()]
    transform = Pipeline([('log', FunctionTransformer(np.log1p)), ('scale', StandardScaler())])
    z = transform.fit_transform(feature_input(cluster_train, RFM))
    cluster_options = []
    for k in range(2, 6):
        km = KMeans(n_clusters=k, n_init=20, random_state=SEED).fit(z)
        cluster_options.append((silhouette_score(z, km.labels_, sample_size=min(2000, len(z)), random_state=SEED), k, km))
    silhouette, k, cluster_model = max(cluster_options, key=lambda entry: entry[0])
    stability = []
    for seed in range(5):
        rng = np.random.default_rng(seed)
        boot = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(z[rng.integers(0, len(z), len(z))])
        stability.append(float(adjusted_rand_score(cluster_model.labels_, boot.predict(z))))
    cluster_report = {'fit_cutoff': str(cluster_train.cutoff.max()), 'k': k,
        'selection': 'Largest training silhouette among k=2..5; no future outcomes used.',
        'silhouette_train': float(silhouette), 'davies_bouldin_train': float(davies_bouldin_score(z, cluster_model.labels_)),
        'candidates': [{'k': count, 'silhouette': float(score)} for score, count, _ in cluster_options],
        'bootstrap_ari_fixed_train_transform': stability,
        'stability_note': 'Five bootstrap K-means refits with fixed training transform; not proof of temporal stability.'}
    (output/'clustering.json').write_text(json.dumps(cluster_report, indent=2))

    # Selection and clustering are frozen before loading held-out test.
    test = load_partition(data, protocol, 'test')
    for key, (model, columns, threshold) in candidates.items():
        probabilities = model.predict_proba(feature_input(test, columns))[:, 1]
        results.append({'model': key, 'split': 'test', **evaluate(test.repurchase_60d, probabilities, threshold)})
    pd.DataFrame(results).to_csv(output/'metrics.csv', index=False)
    model, columns, threshold = candidates[selected]
    predictions, profiles = [], []
    for split, table in [('train', train), ('validation', valid), ('test', test)]:
        table = table.copy()
        table['cluster'] = cluster_model.predict(transform.transform(feature_input(table, RFM)))
        table['repurchase_probability'] = model.predict_proba(feature_input(table, columns))[:, 1]
        table['predicted_label'] = (table.repurchase_probability >= threshold).astype(int)
        table['split'] = split
        predictions.append(table)
        profile = table.groupby(['cutoff', 'cluster']).agg(customers=('CustomerID', 'size'),
            median_recency=('recency_days', 'median'), median_frequency=('frequency', 'median'),
            median_spending=('monetary_gbp', 'median'), observed_repurchase_rate=('repurchase_60d', 'mean')).reset_index()
        profile['split'] = split
        profiles.append(profile)
    all_predictions = pd.concat(predictions, ignore_index=True)
    all_predictions.to_csv(output/'customer_predictions.csv', index=False)
    pd.concat(profiles, ignore_index=True).to_csv(output/'cluster_profiles.csv', index=False)
    final = all_predictions[all_predictions.split == 'test'].copy()
    final['frequency_band'] = np.where(final.frequency == 1, 'one invoice', np.where(final.frequency <= 4, '2-4 invoices', '5+ invoices'))
    slices = []
    for field in ['frequency_band', 'last_observed_country']:
        for group, table in final.groupby(field):
            slices.append({'field': field, 'group': group, **evaluate(table.repurchase_60d, table.repurchase_probability, threshold)})
    pd.DataFrame(slices).to_csv(output/'test_slices.csv', index=False)
    final['probability_bin'] = pd.cut(final.repurchase_probability, np.linspace(0, 1, 11), include_lowest=True)
    calibration = final.groupby('probability_bin', observed=True).agg(n=('CustomerID', 'size'),
        mean_probability=('repurchase_probability', 'mean'), observed_rate=('repurchase_60d', 'mean'))
    calibration.to_csv(output/'test_calibration.csv')
    joblib.dump({'model': model, 'columns': columns, 'threshold': threshold,
                 'cluster_transform': transform, 'cluster_model': cluster_model,
                 'protocol': protocol, 'selection': selection}, output/'models.joblib')
    print(f'Completed. Selected {selected}; K-means k={k}. Results: {output}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=ROOT/'data/repurchase_v1')
    parser.add_argument('--output', type=Path, default=ROOT/'runtime/models_v2_graph')
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        run(args.data, args.output)
