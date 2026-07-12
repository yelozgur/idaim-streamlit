"""Admin page (v0.7) — User management.

Sheets `users` tab:
  username, password_hash, role, last_login

Auth: v0.7 MVP — no login screen yet. Anyone with the URL is admin.
Future (TODO v0.7.1): basic auth, role-gated views.
"""
import time
import dash
from dash import dcc, html, Input, Output, State, callback, no_update
import dash_bootstrap_components as dbc
import pandas as pd
import hashlib

import sheets_client


dash.register_page(__name__, path="/admin", name="Admin", order=2)


# ============== DATA ==============

@callback(
    Output("admin-data-store", "data"),
    Input("url", "pathname"),
)
def load_admin_data(_pathname):
    try:
        df = sheets_client.read_sheet("users", ttl=0)
    except Exception:
        df = pd.DataFrame()
    if len(df) == 0:
        return {"users": [], "default_passwords": {}}
    # Sheet stores password_hash; show only username/role/last_login
    return {
        "users": df.fillna("").to_dict("records"),
        "default_passwords": {},  # Plaintext never leaves server (TODO: derive from hash)
    }


# ============== LAYOUT ==============

layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="admin-data-store", storage_type="memory"),

        html.H3("⚙️ Admin — User Management"),
        html.P("Kullanıcı listesi, role değişimi, şifre reset.", className="text-muted"),
        html.Hr(),

        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Label("Yeni kullanıcı adı"),
                        dcc.Input(id="new-username", className="form-control", placeholder="username"),
                    ],
                    width=4,
                ),
                dbc.Col(
                    [
                        html.Label("Şifre"),
                        dcc.Input(id="new-password", type="text", className="form-control", placeholder="password"),
                    ],
                    width=4,
                ),
                dbc.Col(
                    [
                        html.Label("Role"),
                        dcc.Dropdown(
                            id="new-role",
                            options=[{"label": r, "value": r} for r in ["admin", "operator", "viewer"]],
                            value="operator",
                            clearable=False,
                        ),
                    ],
                    width=3,
                ),
                dbc.Col(
                    [
                        html.Label(" "),
                        dbc.Button("Add user", id="add-user-btn", color="primary", className="w-100"),
                    ],
                    width=1,
                ),
            ]
        ),
        html.Div(id="add-status", className="mt-2"),

        html.Hr(),
        html.H5("Mevcut kullanıcılar"),
        html.Div(id="users-table"),

        html.Hr(),
        dbc.Button("Refresh", id="refresh-btn", color="secondary", size="sm"),
    ]
)


# ============== TABLE ==============

@callback(
    Output("users-table", "children"),
    Input("admin-data-store", "data"),
)
def render_users(data):
    users = (data or {}).get("users", [])
    if not users:
        return dbc.Alert("Henüz kullanıcı yok.", color="info")
    df = pd.DataFrame(users)
    cols_to_show = [c for c in ["username", "role", "last_login"] if c in df.columns]
    if not cols_to_show:
        return dbc.Alert("users sheet beklenen kolonları içermiyor.", color="warning")
    rows = []
    for _, r in df.iterrows():
        rows.append(
            html.Tr(
                [
                    html.Td(str(r.get("username", ""))),
                    html.Td(str(r.get("role", ""))),
                    html.Td(str(r.get("last_login", ""))),
                ]
            )
        )
    return dbc.Table(
        [
            html.Thead(html.Tr([html.Th(c) for c in cols_to_show])),
            html.Tbody(rows),
        ],
        bordered=True,
        hover=True,
        striped=True,
        size="sm",
    )


# ============== ADD USER ==============

@callback(
    Output("add-status", "children"),
    Input("add-user-btn", "n_clicks"),
    State("new-username", "value"),
    State("new-password", "value"),
    State("new-role", "value"),
    prevent_initial_call=True,
)
def add_user(n, username, password, role):
    if not n:
        return ""
    if not username or not password:
        return dbc.Alert("Kullanıcı adı ve şifre zorunlu", color="warning")
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    row = {
        "username": username,
        "password_hash": pw_hash,
        "role": role or "viewer",
        "last_login": "",
    }
    try:
        sheets_client.append_row("users", row)
        sheets_client.clear_read_cache("users")
        return dbc.Alert(f"✅ Kullanıcı eklendi: {username} ({role})", color="success")
    except Exception as e:
        return dbc.Alert(f"❌ Hata: {e}", color="danger")
