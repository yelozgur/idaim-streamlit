"""dash_app.py — IDAIM Plotly Dash app (v0.7+).

Multi-page: Dashboard / Data Entry / Admin / Reports.
Replaces Streamlit app at v0.6.10.

Run locally:
    .venv/bin/python dash_app.py
Open: http://127.0.0.1:8050

Production (HF Spaces / gunicorn):
    gunicorn dash_app:server --bind 0.0.0.0:7860 --workers 2
"""
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html


app = dash.Dash(
    __name__,
    use_pages=True,
    pages_folder="dash_pages",
    external_stylesheets=[dbc.themes.FLATLY],
    title="IDAIM Cyprus",
    update_title=None,
)

# ============== SIDEBAR NAV ==============

sidebar = dbc.Nav(
    [
        dbc.NavLink(
            [html.Span("🗺️ ", style={"fontSize": "1.2em"}), " Dashboard"],
            href="/",
            active="exact",
        ),
        dbc.NavLink(
            [html.Span("📥 ", style={"fontSize": "1.2em"}), " Data Entry"],
            href="/data-entry",
            active="exact",
        ),
        dbc.NavLink(
            [html.Span("⚙️ ", style={"fontSize": "1.2em"}), " Admin"],
            href="/admin",
            active="exact",
        ),
        dbc.NavLink(
            [html.Span("📊 ", style={"fontSize": "1.2em"}), " Reports"],
            href="/reports",
            active="exact",
        ),
    ],
    vertical=True,
    pills=True,
    className="pt-3",
)


# ============== LAYOUT ==============

app.layout = dbc.Container(
    [
        dcc.Location(id="url", refresh=False),
        dbc.Row(
            [
                dbc.Col(sidebar, width=2, className="bg-light border-end vh-100"),
                dbc.Col(
                    [
                        html.Div(
                            [
                                html.H2("IDAIM Cyprus", className="d-inline"),
                                html.Span(
                                    "  v0.7.0 (Plotly Dash)",
                                    className="text-muted ms-2",
                                ),
                            ],
                            className="pt-3",
                        ),
                        html.Hr(),
                        dash.page_container,
                    ],
                    width=10,
                    className="pt-2",
                ),
            ]
        ),
    ],
    fluid=True,
    className="p-0",
)

# Expose WSGI server for gunicorn / HF Spaces
server = app.server


if __name__ == "__main__":
    # Dev server: http://127.0.0.1:8050
    app.run(debug=True, host="127.0.0.1", port=8050)
