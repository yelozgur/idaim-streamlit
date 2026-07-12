"""Data Entry page (v0.7) — Forms: Sampling Init / Trap Check / Lab Result.

GPS UX (saha ekibi için kritik, 3-katman):
- Katman 1: "Get my location" button (clientside_callback + navigator.geolocation)
- Katman 2: Cyprus Plotly map click (select cell)
- Katman 3: Manual lat/lon dcc.Input

cell_id otomatik: GPS coords → utils.find_nearest_cell → cell_id

Sheets şeması (doğrulandı 2026-07-12):
- sampling_initiation: init_id, trap_id, cell_id, sampling_start_time, operator,
  sampling_method, site_description, comments, photo_urls, state
- trap_checks: check_id, trap_id, check_datetime, trap_status, comments,
  image_urls, sampling_finish_id
- lab_results: lab_id, trap_id, sampling_lab_id, cell_id, lab_date, lab_operator,
  specimen_lifecycle, identification_method, species, count, lab_confidence,
  comments, image_urls
"""
import time
import json
import dash
from dash import dcc, html, Input, Output, State, callback, no_update, clientside_callback, ctx
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

import sheets_client
import utils


dash.register_page(__name__, path="/data-entry", name="Data Entry", order=1)


# ============== DATA (for dropdowns) ==============

@callback(
    Output("de-data-store", "data"),
    Input("url", "pathname"),
)
def load_de_data(_pathname):
    cells = utils.load_cells().dropna(subset=["lat", "lon"])
    inits = utils.load_sampling_initiations()
    checks = utils.load_trap_checks()
    return {
        "cells_for_map": cells[["cell_id", "lat", "lon", "district"]].to_dict("records"),
        "active_traps": inits[inits["state"] == "active"]["trap_id"].tolist() if "state" in inits.columns and len(inits) > 0 else [],
        "all_traps": inits["trap_id"].tolist() if len(inits) > 0 else [],
        "valid_checks": checks[checks["trap_status"] == "Trap valid"]["trap_id"].unique().tolist() if "trap_status" in checks.columns and len(checks) > 0 else [],
    }


# ============== GPS CLIENTSIDE (ortak) ==============

# 3 ayrı button için 3 ayrı clientside_callback (her biri kendi store'una yazar)
GPS_CLIENTSIDE_JS = """
function(n_clicks) {
    if (!n_clicks) return window.dash_clientside.no_update;
    return new Promise((resolve) => {
        if (!navigator.geolocation) {
            resolve({lat: null, lon: null, source: "unsupported"});
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (pos) => resolve({
                lat: pos.coords.latitude,
                lon: pos.coords.longitude,
                source: "gps"
            }),
            (err) => resolve({lat: null, lon: null, source: "denied: " + err.message}),
            { enableHighAccuracy: true, timeout: 10000 }
        );
    });
}
"""


def make_gps_clientside(button_id: str, store_id: str):
    clientside_callback(
        GPS_CLIENTSIDE_JS,
        Output(store_id, "data"),
        Input(button_id, "n_clicks"),
    )


# ============== GPS WIDGETS (per tab) ==============

def gps_block(tab: str) -> html.Div:
    """GPS 3-katman widget set: button + lat/lon inputs + map + store."""
    return html.Div(
        [
            dcc.Store(id=f"{tab}-gps-store", storage_type="memory", data={"lat": None, "lon": None, "source": None}),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Label("📍 Location (3-katman: GPS / Map / Manual)", className="fw-bold"),
                            dbc.Button(
                                "Get my location",
                                id=f"{tab}-gps-btn",
                                color="info",
                                size="sm",
                                className="me-2 mt-1",
                            ),
                            html.Span(id=f"{tab}-gps-status", className="ms-2 text-muted small"),
                        ],
                        width=12,
                    ),
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Label("Lat (auto from GPS or map)"),
                            dcc.Input(id=f"{tab}-lat", type="number", step="any", className="form-control", placeholder="35.1856"),
                        ],
                        width=6,
                    ),
                    dbc.Col(
                        [
                            html.Label("Lon (auto from GPS or map)"),
                            dcc.Input(id=f"{tab}-lon", type="number", step="any", className="form-control", placeholder="33.3823"),
                        ],
                        width=6,
                    ),
                ],
                className="mt-2",
            ),
            dcc.Graph(id=f"{tab}-map", style={"height": "35vh"}, className="mt-2",
                      config={"scrollZoom": True, "displaylogo": False}),
        ]
    )


# ============== TAB 1: SAMPLING INITIATION ==============

OPERATORS = ["Ceyda", "Marlen", "Yesim", "Gregoris", "Mustafa", "Costas", "Other"]
METHODS = ["Ovitraps", "Larvae Collection", "BG Sentinel", "EVS", "Human Land Catching"]


def sampling_init_tab() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H4("🪤 Sampling Initiation (Trap kurulumu)"),
                html.P("Yeni bir trap kurulumu kaydı oluştur.", className="text-muted"),
                html.Hr(),

                gps_block("init"),

                html.Hr(),
                dbc.Row(
                    [
                        dbc.Col([html.Label("Trap ID *"), dcc.Input(id="init-trap-id", className="form-control", placeholder="T001")], width=4),
                        dbc.Col([html.Label("Sampling start time"), dcc.Input(id="init-start", type="datetime-local", className="form-control")], width=4),
                        dbc.Col(
                            [
                                html.Label("Operator"),
                                dcc.Dropdown(id="init-operator", options=[{"label": o, "value": o} for o in OPERATORS], placeholder="Seçiniz..."),
                            ],
                            width=4,
                        ),
                    ]
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Label("Sampling method"),
                                dcc.Dropdown(id="init-method", options=[{"label": m, "value": m} for m in METHODS], placeholder="Seçiniz..."),
                            ],
                            width=6,
                        ),
                    ],
                    className="mt-2",
                ),
                dbc.Row(
                    [
                        dbc.Col([html.Label("Site description"), dcc.Textarea(id="init-site", className="form-control", rows=2)], width=12),
                    ],
                    className="mt-2",
                ),
                dbc.Row(
                    [
                        dbc.Col([html.Label("Comments"), dcc.Textarea(id="init-comments", className="form-control", rows=2)], width=12),
                    ],
                    className="mt-2",
                ),
                dbc.Row(
                    [
                        dbc.Col([html.Label("cell_id (auto from GPS)"), html.Span(id="init-cell-id", className="ms-2 badge bg-secondary")], width=12),
                    ],
                    className="mt-2",
                ),
                html.Hr(),
                dbc.Button("Submit Sampling Initiation", id="init-submit", color="primary", size="lg"),
                html.Div(id="init-status", className="mt-3"),
            ]
        )
    )


# ============== TAB 2: TRAP CHECK ==============

TRAP_STATUSES = ["Trap valid", "Trap Disturbed", "Trap Missing", "Battery out", "Other"]


def trap_check_tab() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H4("🔍 Trap Check (Saha kontrolü)"),
                html.P("Bir trap için kontrol kaydı oluştur (bir trap'ın birden fazla check'i olabilir).", className="text-muted"),
                html.Hr(),

                gps_block("check"),

                html.Hr(),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Label("Trap ID *"),
                                dcc.Dropdown(id="check-trap-id", placeholder="Aktif trap seçiniz..."),
                            ],
                            width=4,
                        ),
                        dbc.Col([html.Label("Check datetime"), dcc.Input(id="check-datetime", type="datetime-local", className="form-control")], width=4),
                        dbc.Col(
                            [
                                html.Label("Status *"),
                                dcc.Dropdown(id="check-status", options=[{"label": s, "value": s} for s in TRAP_STATUSES], placeholder="Seçiniz..."),
                            ],
                            width=4,
                        ),
                    ]
                ),
                dbc.Row(
                    [
                        dbc.Col([html.Label("Comments"), dcc.Textarea(id="check-comments", className="form-control", rows=2)], width=12),
                    ],
                    className="mt-2",
                ),
                dbc.Row(
                    [
                        dbc.Col([html.Label("cell_id (auto from GPS)"), html.Span(id="check-cell-id", className="ms-2 badge bg-secondary")], width=12),
                    ],
                    className="mt-2",
                ),
                html.Hr(),
                dbc.Button("Submit Trap Check", id="check-submit", color="primary", size="lg"),
                html.Div(id="check-status-msg", className="mt-3"),
            ]
        )
    )


# ============== TAB 3: LAB RESULT ==============

LAB_OPERATORS = ["Gregoris", "Ceyda", "Operator1", "Operator2"]
LIFECYCLES = ["Egg", "Larva", "Adult"]
ID_METHODS = ["Morphological", "Molecular"]
SPECIES = ["Culex", "Aedes", "Mixed", "Negative", "Other"]


def lab_result_tab() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H4("🔬 Lab Result (Laboratuvar sonucu)"),
                html.P("Trap'ın lab analiz sonucunu girin (Trap valid status'lu check'lerden sonra).", className="text-muted"),
                html.Hr(),

                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Label("Trap ID * (Trap valid check'li)"),
                                dcc.Dropdown(id="lab-trap-id", placeholder="Trap seçiniz..."),
                            ],
                            width=6,
                        ),
                        dbc.Col([html.Label("Lab date"), dcc.Input(id="lab-date", type="date", className="form-control")], width=6),
                    ]
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Label("Lab operator"),
                                dcc.Dropdown(id="lab-operator", options=[{"label": o, "value": o} for o in LAB_OPERATORS]),
                            ],
                            width=4,
                        ),
                        dbc.Col(
                            [
                                html.Label("Specimen lifecycle"),
                                dcc.Dropdown(id="lab-lifecycle", options=[{"label": l, "value": l} for l in LIFECYCLES]),
                            ],
                            width=4,
                        ),
                        dbc.Col(
                            [
                                html.Label("Identification method"),
                                dcc.Dropdown(id="lab-id-method", options=[{"label": m, "value": m} for m in ID_METHODS]),
                            ],
                            width=4,
                        ),
                    ],
                    className="mt-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Label("Species *"),
                                dcc.Dropdown(id="lab-species", options=[{"label": s, "value": s} for s in SPECIES]),
                            ],
                            width=6,
                        ),
                        dbc.Col(
                            [
                                html.Label("Count"),
                                dcc.Input(id="lab-count", type="number", min=0, className="form-control", placeholder="0"),
                            ],
                            width=3,
                        ),
                        dbc.Col(
                            [
                                html.Label("Confidence"),
                                dcc.Input(id="lab-confidence", className="form-control", placeholder="high/medium/low"),
                            ],
                            width=3,
                        ),
                    ],
                    className="mt-2",
                ),
                dbc.Row(
                    [
                        dbc.Col([html.Label("Comments"), dcc.Textarea(id="lab-comments", className="form-control", rows=2)], width=12),
                    ],
                    className="mt-2",
                ),
                html.Hr(),
                dbc.Button("Submit Lab Result", id="lab-submit", color="primary", size="lg"),
                html.Div(id="lab-status", className="mt-3"),
            ]
        )
    )


# ============== LAYOUT ==============

layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="de-data-store", storage_type="memory"),

        html.H3("📥 Data Entry"),
        html.P("Saha verisi girişi — 3 form. GPS 3-katman: buton / harita / manual.", className="text-muted"),
        html.Hr(),

        dbc.Tabs(
            [
                dbc.Tab(sampling_init_tab(), label="🪤 Sampling Initiation", tab_id="tab-init"),
                dbc.Tab(trap_check_tab(), label="🔍 Trap Check", tab_id="tab-check"),
                dbc.Tab(lab_result_tab(), label="🔬 Lab Result", tab_id="tab-lab"),
            ],
            id="de-tabs",
            active_tab="tab-init",
        ),
    ]
)


# ============== GPS CLIENTSIDE CALLBACKS (her tab için) ==============

make_gps_clientside("init-gps-btn", "init-gps-store")
make_gps_clientside("check-gps-btn", "check-gps-store")


# ============== GPS STORE → LAT/LON INPUTS ==============

@callback(
    Output("init-gps-status", "children"),
    Output("init-lat", "value"),
    Output("init-lon", "value"),
    Input("init-gps-store", "data"),
    prevent_initial_call=True,
)
def init_gps_to_inputs(data):
    if not data:
        return "", no_update, no_update
    src = data.get("source", "")
    if data.get("lat") is None:
        return f"⚠️ GPS: {src}", no_update, no_update
    return f"✅ GPS: {src}", data["lat"], data["lon"]


@callback(
    Output("check-gps-status", "children"),
    Output("check-lat", "value"),
    Output("check-lon", "value"),
    Input("check-gps-store", "data"),
    prevent_initial_call=True,
)
def check_gps_to_inputs(data):
    if not data:
        return "", no_update, no_update
    src = data.get("source", "")
    if data.get("lat") is None:
        return f"⚠️ GPS: {src}", no_update, no_update
    return f"✅ GPS: {src}", data["lat"], data["lon"]


# ============== MAP CLICK → LAT/LON INPUTS ==============

@callback(
    Output("init-lat", "value", allow_duplicate=True),
    Output("init-lon", "value", allow_duplicate=True),
    Input("init-map", "clickData"),
    prevent_initial_call=True,
)
def init_map_to_inputs(click_data):
    if not click_data or not click_data.get("points"):
        return no_update, no_update
    p = click_data["points"][0]
    return p.get("lat"), p.get("lon")


@callback(
    Output("check-lat", "value", allow_duplicate=True),
    Output("check-lon", "value", allow_duplicate=True),
    Input("check-map", "clickData"),
    prevent_initial_call=True,
)
def check_map_to_inputs(click_data):
    if not click_data or not click_data.get("points"):
        return no_update, no_update
    p = click_data["points"][0]
    return p.get("lat"), p.get("lon")


# ============== MAPS (Cyprus scatter_mapbox) ==============

@callback(
    Output("init-map", "figure"),
    Input("de-data-store", "data"),
)
def init_map(data):
    return _cyprus_map(data)


@callback(
    Output("check-map", "figure"),
    Input("de-data-store", "data"),
)
def check_map(data):
    return _cyprus_map(data)


def _cyprus_map(data):
    cells = pd.DataFrame((data or {}).get("cells_for_map", []))
    if len(cells) == 0:
        return px.scatter_mapbox(lat=[], lon=[]).update_layout(
            mapbox_style=utils.get_mapbox_style(),
            mapbox=dict(center=dict(lat=35.0, lon=33.4), zoom=8),
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
        )
    fig = px.scatter_mapbox(
        cells.sample(min(len(cells), 5000), random_state=42),  # subsample for click target
        lat="lat", lon="lon",
        hover_data={"cell_id": True, "district": True, "lat": False, "lon": False},
        zoom=8, height=350,
    )
    fig.update_layout(
        mapbox_style=utils.get_mapbox_style(),
        mapbox=dict(center=dict(lat=35.0, lon=33.4), zoom=8),
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
    )
    return fig


# ============== CELL_ID AUTO-FILL (GPS → find_nearest_cell) ==============

@callback(
    Output("init-cell-id", "children"),
    Input("init-lat", "value"),
    Input("init-lon", "value"),
    State("de-data-store", "data"),
)
def init_cell_id(lat, lon, data):
    return _auto_cell_id(lat, lon, data)


@callback(
    Output("check-cell-id", "children"),
    Input("check-lat", "value"),
    Input("check-lon", "value"),
    State("de-data-store", "data"),
)
def check_cell_id(lat, lon, data):
    return _auto_cell_id(lat, lon, data)


def _auto_cell_id(lat, lon, data):
    if lat is None or lon is None:
        return "—"
    cells = pd.DataFrame((data or {}).get("cells_for_map", []))
    if len(cells) == 0:
        return "—"
    cid = utils.find_nearest_cell(cells, lat, lon)
    return f"#{cid}" if cid else "—"


# ============== TRAP_ID DROPDOWNS ==============

@callback(
    Output("check-trap-id", "options"),
    Input("de-data-store", "data"),
)
def check_trap_options(data):
    traps = (data or {}).get("active_traps", [])
    return [{"label": t, "value": t} for t in traps]


@callback(
    Output("lab-trap-id", "options"),
    Input("de-data-store", "data"),
)
def lab_trap_options(data):
    # Lab için valid check'li trap'ler
    valid = (data or {}).get("valid_checks", [])
    if not valid:
        # Fallback: tüm trap'ler
        valid = (data or {}).get("all_traps", [])
    return [{"label": t, "value": t} for t in valid]


# ============== SUBMIT CALLBACKS ==============

@callback(
    Output("init-status", "children"),
    Input("init-submit", "n_clicks"),
    State("init-trap-id", "value"),
    State("init-start", "value"),
    State("init-operator", "value"),
    State("init-method", "value"),
    State("init-site", "value"),
    State("init-comments", "value"),
    State("init-lat", "value"),
    State("init-lon", "value"),
    State("de-data-store", "data"),
    prevent_initial_call=True,
)
def submit_init(n, trap_id, start, operator, method, site, comments, lat, lon, data):
    if not n:
        return ""
    if not trap_id:
        return dbc.Alert("Trap ID zorunlu", color="warning")
    cells = pd.DataFrame((data or {}).get("cells_for_map", []))
    cell_id = utils.find_nearest_cell(cells, lat, lon) if lat and lon else None
    init_id = f"INIT-{int(time.time())}"
    row = {
        "init_id": init_id,
        "trap_id": str(trap_id),
        "cell_id": cell_id if cell_id is not None else "",
        "sampling_start_time": start or "",
        "operator": operator or "",
        "sampling_method": method or "",
        "site_description": site or "",
        "comments": comments or "",
        "photo_urls": "",
        "state": "active",
    }
    try:
        sheets_client.append_row("sampling_initiation", row)
        utils.clear_all_caches()
        return dbc.Alert(f"✅ Kaydedildi: {init_id} (trap: {trap_id}, cell: {cell_id})", color="success")
    except Exception as e:
        logger.error(f"Init submit error: {e}")
        return dbc.Alert(f"❌ Hata: {e}", color="danger")


@callback(
    Output("check-status-msg", "children"),
    Input("check-submit", "n_clicks"),
    State("check-trap-id", "value"),
    State("check-datetime", "value"),
    State("check-status", "value"),
    State("check-comments", "value"),
    State("check-lat", "value"),
    State("check-lon", "value"),
    State("de-data-store", "data"),
    prevent_initial_call=True,
)
def submit_check(n, trap_id, dt, status, comments, lat, lon, data):
    if not n:
        return ""
    if not trap_id or not status:
        return dbc.Alert("Trap ID ve status zorunlu", color="warning")
    cells = pd.DataFrame((data or {}).get("cells_for_map", []))
    cell_id = utils.find_nearest_cell(cells, lat, lon) if lat and lon else None
    check_id = f"CHK-{int(time.time())}"
    sampling_finish_id = ""  # auto: TRAPID+start+finish (skip MVP)
    row = {
        "check_id": check_id,
        "trap_id": str(trap_id),
        "check_datetime": dt or "",
        "trap_status": status,
        "comments": comments or "",
        "image_urls": "",
        "sampling_finish_id": sampling_finish_id,
    }
    try:
        sheets_client.append_row("trap_checks", row)
        utils.clear_all_caches()
        return dbc.Alert(f"✅ Check kaydedildi: {check_id} ({trap_id} → {status}, cell: {cell_id})", color="success")
    except Exception as e:
        logger.error(f"Check submit error: {e}")
        return dbc.Alert(f"❌ Hata: {e}", color="danger")


@callback(
    Output("lab-status", "children"),
    Input("lab-submit", "n_clicks"),
    State("lab-trap-id", "value"),
    State("lab-date", "value"),
    State("lab-operator", "value"),
    State("lab-lifecycle", "value"),
    State("lab-id-method", "value"),
    State("lab-species", "value"),
    State("lab-count", "value"),
    State("lab-confidence", "value"),
    State("lab-comments", "value"),
    State("de-data-store", "data"),
    prevent_initial_call=True,
)
def submit_lab(n, trap_id, date, operator, lifecycle, id_method, species, count, confidence, comments, data):
    if not n:
        return ""
    if not trap_id or not species:
        return dbc.Alert("Trap ID ve species zorunlu", color="warning")
    # cell_id: ilgili init'ten çek
    cell_id = ""
    inits = utils.load_sampling_initiations()
    if len(inits) > 0 and "trap_id" in inits.columns and "cell_id" in inits.columns:
        match = inits[inits["trap_id"] == str(trap_id)]
        if len(match) > 0:
            cid = match.iloc[0].get("cell_id")
            if pd.notna(cid):
                cell_id = int(cid)
    lab_id = f"LAB-{int(time.time())}"
    sampling_lab_id = ""  # auto (skip MVP)
    row = {
        "lab_id": lab_id,
        "trap_id": str(trap_id),
        "sampling_lab_id": sampling_lab_id,
        "cell_id": cell_id if cell_id else "",
        "lab_date": date or "",
        "lab_operator": operator or "",
        "specimen_lifecycle": lifecycle or "",
        "identification_method": id_method or "",
        "species": species,
        "count": int(count) if count is not None else "",
        "lab_confidence": confidence or "",
        "comments": comments or "",
        "image_urls": "",
    }
    try:
        sheets_client.append_row("lab_results", row)
        utils.clear_all_caches()
        return dbc.Alert(f"✅ Lab kaydedildi: {lab_id} ({trap_id} → {species}, cell: {cell_id})", color="success")
    except Exception as e:
        logger.error(f"Lab submit error: {e}")
        return dbc.Alert(f"❌ Hata: {e}", color="danger")
