# IDAIM Dash app — HuggingFace Spaces
# v0.7+, replaces Streamlit Cloud deploy

FROM python:3.11-slim

WORKDIR /app

# System deps (gcc for any compiled extensions, cleanup to keep image small)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps — copy requirements first to leverage Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# HF Spaces default port
EXPOSE 7860

# Sheets creds: set in HF Spaces → Settings → Secrets:
#   GCP_SA_JSON = '{...service account JSON...}'
# (not committed to repo; sheets_client._get_creds_dict() reads from env)
#
# SHEET_ID can also be overridden via Secrets if needed.

# gunicorn: 2 workers, 120s timeout (Sheets API can be slow on cold start)
CMD ["gunicorn", "dash_app:server", "--bind", "0.0.0.0:7860", "--workers", "2", "--timeout", "120"]
