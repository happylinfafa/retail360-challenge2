"""Historical prediction review, separate from the free-form descriptive explorer."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from repurchase import FEATURE_COLUMNS
from modeling import GRAPH_FEATURE

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT/'runtime/models_v2_graph'
st.set_page_config(page_title='Retail360 | Repurchase', layout='wide')
st.title('Customer segments and 60-day repurchase')
st.caption('Historical evaluation · fixed 180-day lookback · no paid API')
if not (RESULTS/'selection.json').exists():
    st.info('Prepare the full dataset, then run python scripts/train_models.py. See README.')
    st.stop()


@st.cache_data
def read_results():
    return (pd.read_csv(RESULTS/'customer_predictions.csv', dtype={'CustomerID': str, 'cutoff': str}),
            pd.read_csv(RESULTS/'metrics.csv'), json.loads((RESULTS/'selection.json').read_text()),
            pd.read_csv(RESULTS/'cluster_profiles.csv'), json.loads((RESULTS/'clustering.json').read_text()))


predictions, metrics, selection, profiles, clustering = read_results()
st.write(f"Selected model: **{selection['selected_model']}** (chosen by validation average precision).")
st.caption('Cluster numbers are descriptive groups, not a ranking. Probabilities are estimates, not guarantees. These are historical dates, not predictions about today.')
split = st.selectbox('Evaluation partition', ['test', 'validation'], key='prediction_split')
subset = predictions[predictions.split == split]
cutoff = st.selectbox('Prediction cutoff', sorted(subset.cutoff.unique()))
subset = subset[subset.cutoff == cutoff]
customer = st.selectbox('Customer ID', subset.CustomerID.tolist(), key='prediction_customer')
row = subset[subset.CustomerID == customer].iloc[0]
context = (split, cutoff, customer)
if st.session_state.get('prediction_context') != context:
    st.session_state['prediction_context'] = context
    st.session_state.pop('prediction_review', None)
    st.session_state.pop('prediction_note', None)
threshold = float(metrics[(metrics.model == selection['selected_model']) & (metrics.split == split)].iloc[0].threshold)
left, middle, right = st.columns(3)
left.metric('Estimated purchase probability', f'{row.repurchase_probability:.1%}')
middle.metric('RFM cluster', str(int(row.cluster)))
right.metric('Prediction at validation-selected threshold', 'Purchase' if row.predicted_label else 'No purchase')
st.caption(f'Threshold: {threshold:.2f}. All features precede {cutoff}; the outcome window is the following 60 days.')
st.subheader('Historical evidence used by the models')
display_features = FEATURE_COLUMNS + [GRAPH_FEATURE]
st.dataframe(pd.DataFrame({'Feature': display_features, 'Value': [float(row[c]) for c in display_features]}), hide_index=True)
st.caption('The graph value is the average log product degree: how many historical customers were connected to the products this customer bought. These are model inputs, not causal explanations. One-invoice purchase gaps may be missing; preprocessing uses training-only medians.')
source = ROOT/'data/repurchase_v1'/split/cutoff
with st.expander('Inspect original purchase rows and provenance'):
    file = source/'history_transactions.csv.gz'
    if file.exists():
        historical = pd.read_csv(file, dtype={'CustomerID': str, 'Invoice': str, 'StockCode': str})
        evidence = historical[historical.CustomerID == customer]
        st.dataframe(evidence, hide_index=True)
        st.caption('Source: online_retail_II.xlsx. RowID = original worksheet:Excel row. AmountPence is in pennies.')
        st.download_button('Download customer evidence', evidence.to_csv(index=False), f'{customer}_{cutoff}_evidence.csv')
    else:
        st.warning('Original-row evidence is unavailable. Rebuild the frozen dataset to inspect provenance.')
with st.expander('Reveal observed outcome (evaluation only)'):
    st.write('Purchased within 60 days:', bool(row.repurchase_60d))
    st.caption('This outcome was not an input to the prediction. This view is a historical backtest, not a live deployment.')
st.subheader('Model comparison')
st.dataframe(metrics[metrics.split == split], hide_index=True)
st.caption('Average precision summarizes the precision–recall curve; it is not accuracy. Lift compares the top-ranked 10% with the overall purchase rate. Dummy ties are broken by fixed customer order.')
st.subheader('Customer groups')
st.dataframe(profiles[(profiles.split == split) & (profiles.cutoff == cutoff)], hide_index=True)
st.caption(f"K={clustering['k']} selected using training silhouette. Observed group purchase rates are evaluation results, not training inputs.")
st.subheader('Human review')
decision = st.radio('Review decision', ['Needs review', 'Accept for analysis', 'Reject / investigate'], key='prediction_review')
note = st.text_area('Reason or correction', key='prediction_note')
review = {'customer': customer, 'cutoff': cutoff, 'split': split, 'model': selection['selected_model'],
          'probability': float(row.repurchase_probability), 'decision': decision, 'note': note}
st.download_button('Download review', json.dumps(review, indent=2), 'prediction_review.json')
st.caption('Review does not automatically change labels or retrain the model. Investigate source evidence before changing the data.')
