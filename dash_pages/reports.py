"""Reports page (v0.7) — Plotly charts.

Tabs:
- Trap Activity: active/closed/missing counts, checks per trap
- Lab Coverage: cells with labs, species breakdown
- ML Metrics: PR-AUC, ROC-AUC, Kappa (from training data, TODO: load from sheet)
"""
import dash
from dash import dcc, html, Input, Output, callback
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

import utils


dash.register_page(__name__, path="/reports", name="Reports", order=3)


# ============== DATA ==============

@callback(
    Output("reports-data-store", "data"),
    Input("url", "pathname"),
)
def load_reports_data(_pathname):
    inits = utils.load_sampling_initiations()
    checks = utils.load_trap_checks()
    labs = utils.load_lab_results()
    traps_state = utils.load_traps_with_state()
    return {
        "n_init": len(inits),
        "n_checks": len(checks),
        "n_labs": len(labs),
        "inits": inits.to_dict("records") if len(inits) > 0 else [],
        "labs": labs.to_dict("records") if len(labs) > 0 else [],
        "traps_state": traps_state.to_dict("records") if len(traps_state) > 0 else [],
    }


# ============== LAYOUT ==============

layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="reports-data-store", storage_type="memory"),

        html.H3("📊 Reports"),
        html.P("Pilot metrikleri: trap aktivitesi, lab coverage, ML performansı.", className="text-muted"),
        html.Hr(),

        # Summary cards
        dbc.Row(
            [
                dbc.Col(dbc.Card(dbc.CardBody([html.H4(id="r-n-init"), html.Small("Sampling inits")])), width=3),
                dbc.Col(dbc.Card(dbc.CardBody([html.H4(id="r-n-checks"), html.Small("Trap checks")])), width=3),
                dbc.Col(dbc.Card(dbc.CardBody([html.H4(id="r-n-labs"), html.Small("Lab results")])), width=3),
                dbc.Col(dbc.Card(dbc.CardBody([html.H4(id="r-n-active"), html.Small("Active traps")])), width=3),
            ],
            className="mb-3",
        ),

        dbc.Tabs(
            [
                dbc.Tab(dbc.Card(dbc.CardBody([dcc.Graph(id="r-trap-activity")])), label="🪤 Trap Activity", tab_id="tab-traps"),
                dbc.Tab(dbc.Card(dbc.CardBody([dcc.Graph(id="r-lab-coverage")])), label="🔬 Lab Coverage", tab_id="tab-labs"),
                dbc.Tab(dbc.Card(dbc.CardBody([
                    html.P("ML metrikleri (PR-AUC, ROC-AUC, Kappa) — şu an eğitim verisinden türetiliyor, Sheets'ten yüklenmesi TODO v0.7.1.", className="text-muted"),
                    dcc.Graph(id="r-ml-metrics"),
                ])), label="🤖 ML Metrics", tab_id="tab-ml"),
            ]
        ),
    ]
)


# ============== METRICS CARDS ==============

@callback(
    Output("r-n-init", "children"),
    Output("r-n-checks", "children"),
    Output("r-n-labs", "children"),
    Output("r-n-active", "children"),
    Input("reports-data-store", "data"),
)
def update_metric_cards(data):
    if not data:
        return "—", "—", "—", "—"
    inits = pd.DataFrame(data.get("inits", []))
    active = 0
    if len(inits) > 0 and "state" in inits.columns:
        active = int((inits["state"] == "active").sum())
    return (
        f"{data.get('n_init', 0):,}",
        f"{data.get('n_checks', 0):,}",
        f"{data.get('n_labs', 0):,}",
        f"{active:,}",
    )


# ============== TRAP ACTIVITY ==============

@callback(
    Output("r-trap-activity", "figure"),
    Input("reports-data-store", "data"),
)
def render_trap_activity(data):
    inits = pd.DataFrame((data or {}).get("inits", []))
    if len(inits) == 0 or "state" not in inits.columns:
        return _empty_fig("Trap verisi yok")

    state_counts = inits["state"].value_counts().reset_index()
    state_counts.columns = ["state", "count"]
    fig = px.bar(
        state_counts, x="state", y="count",
        color="state",
        color_discrete_map={"active": "#4caf50", "closed": "#9e9e9e", "missing": "#f44336"},
        title="Trap States",
    )
    fig.update_layout(showlegend=False, height=400)
    return fig


# ============== LAB COVERAGE ==============

@callback(
    Output("r-lab-coverage", "figure"),
    Input("reports-data-store", "data"),
)
def render_lab_coverage(data):
    labs = pd.DataFrame((data or {}).get("labs", []))
    if len(labs) == 0 or "species" not in labs.columns:
        return _empty_fig("Lab verisi yok")

    species_counts = labs["species"].value_counts().reset_index()
    species_counts.columns = ["species", "count"]
    fig = px.pie(
        species_counts, names="species", values="count",
        title="Lab Species Distribution",
        color_discrete_sequence=px.colors.qualitative.Set2,
        hole=0.4,
    )
    fig.update_layout(height=400)
    return fig


# ============== ML METRICS (TODO) ==============

@callback(
    Output("r-ml-metrics", "figure"),
    Input("reports-data-store", "data"),
)
def render_ml_metrics(data):
    # TODO v0.7.1: load latest training metrics from Sheets or parquet
    # For now, show static placeholder (last known POC values)
    metrics = pd.DataFrame([
        {"metric": "PR-AUC", "value": 0.933, "model": "MiniRocket (per-district)"},
        {"metric": "ROC-AUC", "value": 0.812, "model": "MiniRocket (per-district)"},
        {"metric": "Kappa", "value": 0.819, "model": "MiniRocket (per-district)"},
        {"metric": "PR-AUC", "value": 0.667, "model": "LogisticRegression"},
        {"metric": "ROC-AUC", "value": 0.250, "model": "LogisticRegression"},
    ])
    fig = px.bar(
        metrics, x="metric", y="value", color="model",
        barmode="group", title="ML Metrics (last POC run, 15 noisy samples)",
    )
    fig.update_layout(yaxis=dict(range=[0, 1]), height=400)
    return fig


def _empty_fig(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    fig.update_layout(height=400, xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig
