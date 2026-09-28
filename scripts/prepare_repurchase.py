"""Build the frozen temporal benchmark from the full UCI workbook."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repurchase import ROOT, FEATURE_COLUMNS, load_protocol, read_workbook, build_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('workbook', type=Path)
    parser.add_argument('--protocol', type=Path, default=ROOT/'config/repurchase_protocol.json')
    parser.add_argument('--output', type=Path, default=ROOT/'data/repurchase_v1')
    args = parser.parse_args()
    protocol = load_protocol(args.protocol)
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError('Output directory is not empty. Choose a new --output to preserve prior results.')
    transactions, source = read_workbook(args.workbook, protocol['source_sha256'])
    args.output.mkdir(parents=True, exist_ok=True)
    snapshots = []
    for spec in protocol['snapshots']:
        features, labels, audit, history, future, summary = build_snapshot(transactions, spec['cutoff'], protocol)
        dest = args.output/spec['split']/spec['cutoff']
        dest.mkdir(parents=True)
        features.to_csv(dest/'features.csv', index=False)
        labels.to_csv(dest/'labels.csv', index=False)
        audit.to_csv(dest/'audit.csv', index=False)
        history.to_csv(dest/'history_transactions.csv.gz', index=False, compression='gzip')
        future.to_csv(dest/'label_transactions.csv.gz', index=False, compression='gzip')
        summary['split'] = spec['split']
        snapshots.append(summary)
        print(f"{spec['split']} {spec['cutoff']}: {len(features):,} eligible customers", flush=True)
    manifest = {'protocol': protocol, 'source': source, 'feature_columns': FEATURE_COLUMNS,
                'primary_key': ['cutoff', 'CustomerID'], 'snapshots': snapshots,
                'status': 'Data prepared only; no model trained and no test model scores computed.'}
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Completed: {args.output}', flush=True)


if __name__ == '__main__':
    main()
