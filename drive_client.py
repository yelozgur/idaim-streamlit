"""drive_client.py — Google Drive'a fotoğraf yükleme.

Sheets'te sadece URL tutulur (cell_id, trap_id bazlı organize).
Drive klasör yapısı:
  /IDAIM-Cyprus-Photos/
    ├── sampling/{trap_id}_{timestamp}.jpg
    ├── checks/{trap_id}_{timestamp}.jpg
    └── lab/{trap_id}_{timestamp}.jpg
"""
import os
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import io
import uuid

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


@st.cache_resource
def get_drive_service():
    """Drive API v3 service (cache'li)."""
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=DRIVE_SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _get_or_create_subfolder(service, parent_id: str, folder_name: str) -> str:
    """Drive'da alt klasör varsa ID'sini döner, yoksa oluşturur."""
    # Ara
    query = f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    # Yoksa oluştur
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def upload_photos(
    files: list,
    category: str,   # "sampling" | "checks" | "lab"
    trap_id: str,
) -> list[str]:
    """Birden fazla fotoğrafı Drive'a yükle, URL listesi döner.

    Args:
        files: streamlit UploadedFile listesi
        category: hangi alt klasör
        trap_id: dosya adı için

    Returns:
        URL listesi (https://drive.google.com/uc?id=...)
    """
    if not files:
        return []

    try:
        service = get_drive_service()
        root_id = st.secrets.get("drive", {}).get("root_folder_id")
        if not root_id:
            st.warning("⚠️ Drive root_folder_id secrets.toml'da tanımlı değil, fotoğraflar yüklenmedi")
            return []
    except Exception as e:
        st.error(f"❌ Drive bağlantı hatası: {e}")
        return []

    # Alt klasör
    subfolder_id = _get_or_create_subfolder(service, root_id, category)

    urls = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for i, f in enumerate(files):
        try:
            # Unique dosya adı
            ext = os.path.splitext(f.name)[1] or ".jpg"
            unique_id = uuid.uuid4().hex[:8]
            file_name = f"{trap_id}_{timestamp}_{i+1}_{unique_id}{ext}"

            # Upload
            media = MediaIoBaseUpload(
                io.BytesIO(f.getvalue()),
                mimetype=f.type or "image/jpeg",
                resumable=False,
            )
            metadata = {"name": file_name, "parents": [subfolder_id]}
            uploaded = service.files().create(
                body=metadata, media_body=media, fields="id, webViewLink"
            ).execute()

            # Public link için izin ver
            service.permissions().create(
                fileId=uploaded["id"],
                body={"role": "reader", "type": "anyone"},
            ).execute()

            url = f"https://drive.google.com/uc?id={uploaded['id']}"
            urls.append(url)
        except Exception as e:
            st.warning(f"⚠️ Fotoğraf yüklenemedi ({f.name}): {e}")

    return urls


def urls_to_string(urls: list[str]) -> str:
    """URL listesini virgülle ayrılmış string yap (Sheets için)."""
    return ",".join(urls) if urls else ""


def string_to_urls(s: str) -> list[str]:
    """Sheets'ten okunan string'i liste yap."""
    if not s or pd_is_empty(s):
        return []
    return [u.strip() for u in s.split(",") if u.strip()]


def pd_is_empty(val) -> bool:
    """pandas NaN veya None kontrolü."""
    try:
        import pandas as pd
        if pd.isna(val):
            return True
    except (ImportError, ValueError):
        pass
    return val is None
