# IDAIM v0.7 — Plotly Dash Geçiş (Full App)

**Tarih:** 2026-07-12
**Yazar:** Mavis (Mavis)
**Durum:** Plan — onay bekliyor

## Background

Streamlit + Folium, 37K cell marker ile kullanıcı deneyimini bozuyor (v0.6.10 MarkerCluster denendi, yetersiz). Plotly Dash'e **full migration** kararı alındı.

**Hedef:** UNDP saha ekibinin pilot testi kabul olsun — hızlı çalışsın, kullanıcıyı zorlamasın.

## Kararlar

| Konu | Karar | Gerekçe |
|---|---|---|
| **Scope** | Full app (Map + Forms + Admin + Reports) | Saha ekibi zaten tüm sayfaları kullanıyor |
| **Stack** | Plotly Dash 2.18+ + dash-bootstrap-components + gunicorn | Plotly zaten kurulu, ek mature stack |
| **Deploy** | HuggingFace Spaces (16GB RAM, persistent, ücretsiz) | Render uyku sorunu, HF persistent + persistent volume |
| **Data source** | Google Sheets (gspread) — şema korunur | UNDP verisi orada, geçiş riski gereksiz |
| **Sheets creds** | HF Secrets (env var) + JSON dosya `data/ee-yelozgur.json` repo'da | Hızlı çalışsın (kullanıcı kararı, 2a) |
| **GPS UX** | 3-katmanlı korunur (auto → map click → manual) | Saha ekibi acı noktası, kabul kriteri |
| **Map engine** | Plotly Express `scatter_mapbox` (Mapbox public token free tier) | 37K point rahat, syntax basit |
| **Repo stratejisi** | Mevcut `idaim-streamlit` branch `feat/dash-port` | Sheets schema + history korunur |

## Mimari

```
┌─────────────────────────────────────────────────────┐
│ GitHub: yelozgur/idaim-streamlit (branch: feat/dash-port) │
│   - app code, Sheets schema, tests                  │
│   - data/ee-yelozgur.json (SA dosya)                │
│   - Dockerfile                                      │
│   - requirements.txt                                │
└──────────┬──────────────────────────────────────────┘
           │ git push origin feat/dash-port
           │ git push hf main
           ▼
┌─────────────────────────────────────────────────────┐
│ HuggingFace Space: yelozgur/idaim-dash              │
│   - otomatik Docker build                           │
│   - container: python:3.11-slim                     │
│   - 2 CPU, 16GB RAM, persistent                    │
│   - Secrets: SHEET_ID, GCP_SA_JSON_PATH            │
│   - URL: huggingface.co/spaces/yelozgur/idaim-dash │
└─────────────────────────────────────────────────────┘
```

## Adımlar ve Tahmini Süre

| # | Adım | Süre | Not |
|---|---|---|---|
| 1 | Branch `feat/dash-port` aç, .gitignore güncelle | 0.5 saat | SA dosya push'lanabilir olmalı |
| 2 | Dash app skeleton (`dash_app.py`, layout, data loaders) | 0.5 gün | sheets_client refactor (env-based) |
| 3 | Sheets creds refactor (env var → `data/ee-yelozgur.json`) | 0.5 gün | `GCP_SA_JSON_PATH` env, default `data/ee-yelozgur.json` |
| 4 | **Dashboard** (Plotly `scatter_mapbox` + filters callback) | 1 gün | MarkerCluster'a gerek yok, Plotly 100K point rahat |
| 5 | **Data Entry / Forms** (sampling_init, trap_check, lab_result) | 1.5 gün | **GPS 3-katman UX korunur** |
| 6 | **Admin** (kullanıcı yönetimi) | 0.5 gün | Sheets `users` tab |
| 7 | **Reports** (Plotly charts) | 0.5 gün | Mevcut Plotly kullanımı genişlet |
| 8 | Dockerfile (python:3.11-slim, port 7860, gunicorn) | 0.5 saat | HF default port |
| 9 | HF Space oluştur + Secrets konfig + ilk push | 0.5 gün | gcloud auth gerekli değil, HF token |
| 10 | E2E test (saha ekibi senaryosu) + iterasyon | 0.5 gün | GPS, form submit, map filter |
| | **Toplam** | **5 iş günü** | |

## GPS UX Koruma Detayı (KRİTİK)

Mevcut: `gps_component.py` → `streamlit_js_eval.get_geolocation()` + map click + manual input

**Dash karşılığı:**

```python
# 1. clientside_callback ile GPS auto
app.clientside_callback(
    """
    function(n_clicks) {
        if (n_clicks === 0) return window.dash_clientside.no_update;
        return new Promise((resolve) => {
            navigator.geolocation.getCurrentPosition(
                (pos) => resolve({lat: pos.coords.latitude, lon: pos.coords.longitude}),
                (err) => resolve(null)
            );
        });
    }
    """,
    Output("gps-output", "data"),
    Input("gps-btn", "n_clicks"),
)

# 2. dcc.Graph (scatter_mapbox) click → cell_id
# 3. dcc.Input numeric → manual lat/lon
```

3 katman korunur: GPS butonu → map click → manual input. Hiçbiri kalkmaz.

## Riskler ve Mitigation

| Risk | Etki | Mitigation |
|---|---|---|
| HF cold start | İlk request ~30s | Sık kullanılan cache precache |
| Dash öğrenme eğrisi (callback'ler) | Geliştirme hızı düşer | Streamlit'ten direkt geçiş yerine sayfa sayfa pilot |
| Sheets rate limit (60 write/min) | Form submit throttle | gspread append_rows batch |
| GPS iframe CSP engeli (HF'de) | Saha ekibi konum alamaz | `clientside_callback` iframe değil, doğrudan browser API → CSP sorunu yok |
| Mapbox token limit (50K load/ay) | Pilot overshoot | Fallback: MapLibre GL + OSM tile (token gereksiz) |

## Kabul Kriterleri (Definition of Done)

- [ ] Tüm 4 sayfa (Map, Forms, Admin, Reports) HF'de çalışıyor
- [ ] GPS 3-katman UX (auto + map click + manual) tam çalışıyor
- [ ] Sheets veri yazma/okuma hatasız
- [ ] 37K cell map < 2s render
- [ ] Saha ekibi senaryosu: form doldurma → Sheets'e yazma → haritada görünme
- [ ] HF Space URL paylaşılabilir, persistent (uyku yok)
- [ ] Mevcut Streamlit app deprecated (branch korunur, ana repo Dash)

## Out of Scope (v0.7'de yapılmayacak)

- DB'ye geçiş (Sheets devam)
- Auth sistemi değişikliği (mevcut gspread SA yeterli)
- Multi-language (English UI v0.6'da var, korunur)
- ML pipeline değişikliği (mevcut MiniRocket, Sheets'e yazıyor)

## Next Step

**Adım 1'i başlatmak için onay ver:**
1. `git checkout -b feat/dash-port`
2. `.gitignore`'a `data/ee-yelozgur.json` ekle VEYA SA dosyayı commit et (kullanıcı kararı)
3. `requirements.txt`'e dash eklensin mi?

Geçişe başlamak için yeşil ışık ver, branch açıp Dash skeleton'u kurarım.
