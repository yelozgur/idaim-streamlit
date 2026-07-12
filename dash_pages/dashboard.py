"""Dashboard page (v0.7) — Plotly scatter_mapbox + filters + overlays.

Architecture:
- 37K cells (lat/lon/district from Parquet, ML proba from Sheets)
- Plotly Express scatter_mapbox with WebGL rendering (smooth at 100K+ points)
- mapbox_style="open-street-map" (no token required)
- Callback: district / confidence / species filters
- Toggles: show_watch_list, show_traps, show_labs
- Cell click → detail panel
"""
import dash
from dash import dcc, html, Input, Output, State, callback, no_update
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import numpy as np

import utils
import config


dash.register_page(__name__, path="/", name="Dashboard", order=0)


# ============== DATA LOAD (on page load) ==============

@callback(
    Output("dash-data-store", "data"),
    Input("url", "pathname"),
)
def load_dash_data(_pathname):
    """Load all datasets on Dashboard mount. Stored in dcc.Store, reused by callbacks."""
    cells = utils.load_cells()
    watch = utils.load_watch_list()
    traps = utils.load_traps_with_state()
    labs = utils.load_lab_results()

    # Defensive: drop rows with NaN lat/lon (Sheets import bug)
    cells = cells.dropna(subset=["lat", "lon"]).copy()

    # Convert to records (JSON-serializable for dcc.Store)
    return {
        "cells": cells.head(40000).to_dict("records"),  # safety cap
        "watch": watch.to_dict("records") if len(watch) > 0 else [],
        "traps": traps.to_dict("records") if len(traps) > 0 else [],
        "labs": labs.to_dict("records") if len(labs) > 0 else [],
    }


# ============== LAYOUT ==============

layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="dash-data-store", storage_type="memory"),

        html.H3("🗺️ Dashboard"),

        # Metrics row
        dbc.Row(
            [
                dbc.Col(html.Div(id="metric-cells", className="text-center"), width=3),
                dbc.Col(html.Div(id="metric-traps", className="text-center"), width=3),
                dbc.Col(html.Div(id="metric-labs", className="text-center"), width=3),
                dbc.Col(html.Div(id="metric-watch", className="text-center"), width=3),
            ],
            className="mb-3",
        ),

        html.Hr(),

        # Filters row
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Label("Color scale"),
                        dcc.RadioItems(
                            id="dash-species",
                            options=[
                                {"label": " Culex (proba)", "value": "culex_proba"},
                                {"label": " Aedes (proba)", "value": "aedes_proba"},
                            ],
                            value="culex_proba",
                            inline=True,
                            className="mt-1",
                        ),
                    ],
                    width=3,
                ),
                dbc.Col(
                    [
                        html.Label("District"),
                        dcc.Dropdown(
                            id="dash-district",
                            options=[{"label": d, "value": d} for d in config.DISTRICTS],
                            value=config.DISTRICTS,
                            multi=True,
                        ),
                    ],
                    width=3,
                ),
                dbc.Col(
                    [
                        html.Label("Confidence"),
                        dcc.Dropdown(
                            id="dash-confidence",
                            options=[
                                {"label": "All", "value": "all"},
                                {"label": "High only (>=0.7)", "value": "high"},
                                {"label": "Medium+High (>=0.4)", "value": "medium"},
                                {"label": "Unknown only", "value": "unknown"},
                            ],
                            value="all",
                            clearable=False,
                        ),
                    ],
                    width=3,
                ),
                dbc.Col(
                    [
                        html.Label("Layers"),
                        dbc.Checklist(
                            id="dash-toggles",
                            options=[
                                {"label": " Watch list", "value": "watch"},
                                {"label": " Traps", "value": "traps"},
                                {"label": " Lab markers", "value": "labs"},
                            ],
                            value=["watch", "traps", "labs"],
                            inline=True,
                            className="mt-1",
                        ),
                    ],
                    width=3,
                ),
            ],
            className="mb-3",
        ),

        # Map
        dcc.Loading(
            dcc.Graph(
                id="dash-map",
                style={"height": "70vh"},
                config={
                    "scrollZoom": True,
                    "displayModeBar": True,
                    "displaylogo": False,
                },
            ),
            type="default",
        ),

        # Cell detail panel
        html.Div(id="cell-detail", className="mt-3"),
    ]
)


# ============== METRICS ==============

@callback(
    Output("metric-cells", "children"),
    Output("metric-traps", "children"),
    Output("metric-labs", "children"),
    Output("metric-watch", "children"),
    Input("dash-data-store", "data"),
)
def update_metrics(data):
    if not data:
        return no_update, no_update, no_update, no_update
    n_cells = len(data.get("cells", []))
    n_watch = len(data.get("watch", []))
    n_traps = len(data.get("traps", []))
    n_labs = len(data.get("labs", []))
    return (
        dbc.Card([dbc.CardBody([html.H4(f"{n_cells:,}"), html.Small("Cells")])]),
        dbc.Card([dbc.CardBody([html.H4(f"{n_traps:,}"), html.Small("Traps")])]),
        dbc.Card([dbc.CardBody([html.H4(f"{n_labs:,}"), html.Small("Lab Results")])]),
        dbc.Card([dbc.CardBody([html.H4(f"{n_watch:,}"), html.Small("Watch List")])]),
    )


# ============== MAP ==============

@callback(
    Output("dash-map", "figure"),
    Input("dash-data-store", "data"),
    Input("dash-species", "value"),
    Input("dash-district", "value"),
    Input("dash-confidence", "value"),
    Input("dash-toggles", "value"),
)
def update_map(data, species, districts, confidence, toggles):
    if not data or not data.get("cells"):
        return px.scatter_mapbox(lat=[], lon=[]).update_layout(
            mapbox_style="open-street-map",
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
        )

    cells = pd.DataFrame(data["cells"])
    watch = pd.DataFrame(data.get("watch", []))
    traps = pd.DataFrame(data.get("traps", []))
    labs = pd.DataFrame(data.get("labs", []))

    # Filter: district
    if districts and len(districts) < len(config.DISTRICTS):
        cells = cells[cells["district"].isin(districts)]
    if len(cells) == 0:
        return px.scatter_mapbox(lat=[], lon=[]).update_layout(
            mapbox_style="open-street-map",
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
        )

    # Filter: confidence
    if confidence == "high":
        cells = cells[cells[species] >= 0.7]
    elif confidence == "medium":
        cells = cells[cells[species] >= 0.4]
    elif confidence == "unknown":
        cells = cells[cells[species].isna()]

    # Hover text
    cells = cells.copy()
    cells["hover"] = (
        "Cell #" + cells["cell_id"].astype(str)
        + " | " + cells["district"].astype(str)
        + " | " + species.replace("_proba", "") + ": "
        + cells[species].fillna(-1).apply(lambda v: f"{v:.2f}" if v >= 0 else "—")
    )

    # Main scatter: 37K cells colored by species proba
    fig = px.scatter_mapbox(
        cells,
        lat="lat",
        lon="lon",
        color=species,
        color_continuous_scale="Reds",
        range_color=(0, 1),
        hover_name="hover",
        hover_data={"lat": False, "lon": False, species: False},
        zoom=8,
        height=600,
    )

    # Watch list overlay
    if "watch" in (toggles or []) and len(watch) > 0 and "lon" in watch.columns:
        watch_clean = watch.dropna(subset=["lat", "lon"]).copy()
        if len(watch_clean) > 0:
            fig.add_trace(
                px.scatter_mapbox(
                    watch_clean,
                    lat="lat",
                    lon="lon",
                    hover_name="cell_id",
                    hover_data={"lat": False, "lon": False},
                ).data[0].update(
                    marker=dict(size=14, color="orange", symbol="circle", line=dict(width=2, color="black")),
                    name="Watch list",
                )
            )

    # Traps overlay
    if "traps" in (toggles or []) and len(traps) > 0 and "lon" in traps.columns:
        traps_clean = traps.dropna(subset=["lat", "lon"]).copy()
        if len(traps_clean) > 0:
            trap_colors = traps_clean.get("last_check", "active").map(
                {"Valid": "green", "active": "green", "Missing": "red", "Disturbed": "orange", "Battery out": "gray"}
            ).fillna("gray")
            fig.add_trace(
                go.Scattermapbox(
                    lat=traps_clean["lat"],
                    lon=traps_clean["lon"],
                    mode="markers",
                    marker=dict(size=12, color=trap_colors, symbol="circle", line=dict(width=1, color="white")),
                    text=traps_clean.get("trap_id", ""),
                    name="Traps",
                    hovertemplate="<b>Trap %{text}</b><br>Lat: %{lat}<br>Lon: %{lon}<extra></extra>",
                )
            )

    # Lab markers
    if "labs" in (toggles or []) and len(labs) > 0 and "lon" in labs.columns:
        labs_clean = labs.dropna(subset=["lat", "lon"]).copy()
        if len(labs_clean) > 0:
            species_colors = labs_clean.get("species", "Other").map(
                {"Culex": "blue", "Aedes": "red", "Mixed": "purple", "Negative": "lightgray", "Other": "gray"}
            ).fillna("gray")
            fig.add_trace(
                go.Scattermapbox(
                    lat=labs_clean["lat"],
                    lon=labs_clean["lon"],
                    mode="markers",
                    marker=dict(size=10, color=species_colors, symbol="diamond", line=dict(width=1, color="white")),
                    text=labs_clean.get("species", ""),
                    name="Lab results",
                    hovertemplate="<b>%{text}</b><br>Lat: %{lat}<br>Lon: %{lon}<extra></extra>",
                )
            )

    fig.update_layout(
        mapbox_style="open-street-map",
        mapbox=dict(center=dict(lat=35.0, lon=33.4), zoom=8),
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        coloraxis_colorbar=dict(title=species.replace("_proba", "").title()),
    )
    return fig


# ============== CELL DETAIL ==============

@callback(
    Output("cell-detail", "children"),
    Input("dash-map", "clickData"),
    State("dash-data-store", "data"),
)
def show_cell_detail(click_data, data):
    if not click_data or not data:
        return ""
    try:
        # Extract cell_id from clicked point's customdata or hover
        point = click_data["points"][0]
        cell_id = point.get("customdata", [None])[0] if "customdata" in point else None
        if cell_id is None:
            # Try hover_name
            hn = point.get("hovertext", "")
            if hn and "Cell #" in hn:
                cell_id = int(hn.split("Cell #")[1].split(" ")[0])
        if cell_id is None:
            return ""

        # Find cell in dataset
        cells = pd.DataFrame(data["cells"])
        row = cells[cells["cell_id"] == cell_id]
        if len(row) == 0:
            return ""
        r = row.iloc[0]
        return dbc.Card(
            dbc.CardBody(
                [
                    html.H5(f"Cell #{int(r['cell_id'])} — {r.get('district', '?')}"),
                    html.P(
                        f"Lat: {r['lat']:.4f}, Lon: {r['lon']:.4f}",
                        className="text-muted",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Strong("Culex proba: "),
                                    utils.fmt_proba(r.get("culex_proba")),
                                ],
                                width=4,
                            ),
                            dbc.Col(
                                [
                                    html.Strong("Aedes proba: "),
                                    utils.fmt_proba(r.get("aedes_proba")),
                                ],
                                width=4,
                            ),
                            dbc.Col(
                                [
                                    html.Strong("Confidence: "),
                                    str(r.get("confidence_tier", "—")),
                                ],
                                width=4,
                            ),
                        ]
                    ),
                ]
            ),
            className="mt-2",
        )
    except Exception:
        return ""


# Note: go.Scattermapbox needs the import. We use plotly.express + plotly.graph_objects.
import plotly.graph_objects as go
