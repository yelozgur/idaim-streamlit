"""ml_pipeline.py — Per-species MiniRocket training + per-district threshold.

Backend: training data hazırlama, MiniRocket eğitimi, predict_all,
per-district threshold tuning.

Mevcut pipeline (29_train_minirocket.py, 30_ablation_hybrid.py) ile aynı
mantık ama Sheets'ten okur, Sheets'e yazar.
"""
import streamlit as st
import pandas as pd
import numpy as np
import pickle
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from sklearn.impute import SimpleImputer
from sklearn.model_selection import LeaveOneOut, StratifiedKFold
from sklearn.metrics import (
    precision_recall_curve, cohen_kappa_score, roc_auc_score, auc
)

from config import DYNAMIC_FEATURES, MIN_SAMPLES, DISTRICTS
from utils import (
    load_static_cells, load_static_features, load_labeled_cells, load_watch_list,
    clear_all_caches, update_ml_output,
)
import sheets_client
import gee_client


# ============== FEATURE HAZIRLAMA ==============

def build_3d_array(df: pd.DataFrame, feature_cols: list[str]) -> np.ndarray:
    """Build (samples, 5, 12) array."""
    X = np.zeros((len(df), len(DYNAMIC_FEATURES), 12))
    for i, feat in enumerate(DYNAMIC_FEATURES):
        for m in range(12):
            col = f"{feat}_{m+1:02d}"
            if col in df.columns:
                X[:, i, m] = pd.to_numeric(df[col], errors="coerce").values
            else:
                X[:, i, m] = np.nan
    return X


def get_features_for_cell(cell_id: int, year: int = 2024) -> Optional[np.ndarray]:
    """Bir hücre için (5, 12) feature array getir.

    Statik parquet'tan okur (features_cache_active.parquet).
    Returns: shape (5, 12) veya None
    """
    cache = load_static_features()
    if len(cache) == 0:
        return None
    row = cache[cache["cell_id"] == cell_id]
    if len(row) == 0:
        return None
    return _row_to_5x12(row.iloc[0])


def _row_to_5x12(row: pd.Series) -> np.ndarray:
    """DataFrame satırını (5, 12) numpy array'e çevir."""
    arr = np.zeros((5, 12))
    for i, feat in enumerate(DYNAMIC_FEATURES):
        for m in range(12):
            col = f"{feat}_{m+1:02d}"
            if col in row.index:
                arr[i, m] = pd.to_numeric(row[col], errors="coerce")
    return arr


def get_features_for_cells(cell_ids: list[int], year: int = 2024) -> tuple[np.ndarray, list[int]]:
    """Birden fazla hücre için (n, 5, 12) array getir. None dönenler skip edilir.

    Returns:
        X: shape (n_valid, 5, 12)
        valid_ids: X ile aynı sırada cell_id'ler
    """
    cache = load_static_features()
    if len(cache) == 0:
        return np.zeros((0, 5, 12)), []

    X_list = []
    valid_ids = []

    for cid in cell_ids:
        row = cache[cache["cell_id"] == cid]
        if len(row) == 0:
            continue
        feat = _row_to_5x12(row.iloc[0])
        # Eğer tüm değerler NaN ise skip
        if not np.any(np.isfinite(feat)):
            continue
        # NaN'leri 0 ile doldur (imputer sonra halleder)
        feat = np.nan_to_num(feat, nan=0.0)
        X_list.append(feat)
        valid_ids.append(cid)

    if not X_list:
        return np.zeros((0, 5, 12)), []
    return np.stack(X_list), valid_ids


# ============== TRAINING DATA HAZIRLAMA ==============

def prepare_training_data(species: str) -> tuple[Optional[np.ndarray], Optional[np.ndarray], list, list]:
    """Per-species training data hazırla.

    species: 'culex' veya 'aedes'

    Returns:
        X: shape (n, 5, 12)
        y: shape (n,) binary 0/1
        cell_ids: paralel liste
        districts: paralel liste
    """
    labeled = load_labeled_cells()
    if len(labeled) == 0:
        return None, None, [], []

    # Per-species binary label
    target_species = species.capitalize()  # Culex, Aedes

    if target_species not in labeled["species"].unique():
        # Hiç örnek yok
        n_pos = 0
    else:
        n_pos = (labeled["species"] == target_species).sum()

    if n_pos < MIN_SAMPLES[species]:
        st.info(f"ℹ️ {species}: {n_pos} pozitif örnek (min {MIN_SAMPLES[species]} gerekli). Skip.")
        return None, None, [], []

    # Yalnızca lab_confidence != 'low' olanları al (veya low'ları düşük ağırlıkla)
    if "lab_confidence" in labeled.columns:
        # Low confidence'ı sample_weight ile düşür
        labeled_filtered = labeled.copy()
        labeled_filtered["weight"] = labeled_filtered["lab_confidence"].map({
            "high": 1.0,
            "medium": 0.8,
            "low": 0.5,
        }).fillna(0.8)
    else:
        labeled_filtered = labeled.copy()
        labeled_filtered["weight"] = 1.0

    # Binary label
    labeled_filtered["is_positive"] = (labeled_filtered["species"] == target_species).astype(int)

    # Negatif = bu tür değil (Culex/Aedes/Mixed/Other/Negative hepsi negatif olabilir)
    # Veya sadece 'Negative' olanlar — ikinci yaklaşım daha iyi
    # Negatif: species='Negative' veya 'Other'

    # Negatif olarak kabul et: species != target_species
    # Bu sayede: Culex varsa ve Aedes de varsa, diğeri için negatif olur

    # Cell_id unique (bir hücrede birden fazla trap olabilir)
    labeled_unique = labeled_filtered.drop_duplicates(subset=["cell_id"], keep="first")

    n_pos_unique = (labeled_unique["is_positive"] == 1).sum()
    n_neg_unique = (labeled_unique["is_positive"] == 0).sum()

    # ============ PSEUDO-NEGATİF SAMPLING ============
    # Yeni başlayan sahada: lab_results çok az, negatif örnek 0 olabiliyor.
    # Bu durumda Cyprus grid'den (37K hücre) rastgele hücreleri
    # "pseudo-negatif" olarak ekle (background distribution temsilcisi).
    PSEUDO_NEG_RATIO = 20  # Her pozitif için max 20 pseudo-negatif
    target_neg = min(int(n_pos_unique * PSEUDO_NEG_RATIO), 200) if n_pos_unique > 0 else 50
    if n_neg_unique < 5 and target_neg > 0:
        # cells_full'dan rastgele pseudo-negatif hücreler çek
        try:
            all_cells = load_static_cells()
            if len(all_cells) > 0:
                # Lab yapılmış hücreleri çıkar
                labeled_cell_ids = set(labeled_unique["cell_id"].astype(int).tolist())
                pool = all_cells[~all_cells["cell_id"].isin(labeled_cell_ids)]
                if len(pool) > 0:
                    n_pseudo = min(target_neg, len(pool))
                    pseudo = pool.sample(n=n_pseudo, random_state=42).copy()
                    pseudo["species"] = "PseudoNegative"
                    pseudo["is_positive"] = 0
                    pseudo["weight"] = 0.3  # Pseudo-negatif düşük ağırlık
                    pseudo["lab_confidence"] = "low"
                    # labeled_unique'ı birleştir
                    cols_to_keep = ["cell_id", "species", "is_positive", "weight", "lab_confidence"]
                    pseudo_subset = pseudo[[c for c in cols_to_keep if c in pseudo.columns]]
                    labeled_unique = pd.concat(
                        [labeled_unique[[c for c in cols_to_keep if c in labeled_unique.columns]],
                         pseudo_subset],
                        ignore_index=True,
                    )
                    n_neg_unique = (labeled_unique["is_positive"] == 0).sum()
                    st.caption(f"   + {n_pseudo} pseudo-negatif eklendi (lab yapılmamış hücrelerden)")
        except Exception as e:
            st.caption(f"⚠️ Pseudo-negatif eklenemedi: {e}")

    st.caption(f"📊 {species} training: {n_pos_unique} pozitif, {n_neg_unique} negatif (unique cells)")

    # Feature'ları yükle
    cell_ids = labeled_unique["cell_id"].astype(int).tolist()
    X, valid_ids = get_features_for_cells(cell_ids)

    if len(X) == 0:
        return None, None, [], []

    # y'yi valid_ids ile hizala
    y = []
    weights = []
    districts = []
    for cid in valid_ids:
        row = labeled_unique[labeled_unique["cell_id"] == cid].iloc[0]
        y.append(int(row["is_positive"]))
        weights.append(float(row["weight"]))
        districts.append(str(row.get("district", "Unknown")))

    y = np.array(y, dtype=int)
    weights = np.array(weights, dtype=float)
    districts = np.array(districts)

    return X, y, valid_ids, districts  # weights şimdilik kullanılmıyor


# ============== MINIROCKET TRAINING ==============

def train_minirocket(X: np.ndarray, y: np.ndarray, n_jobs: int = -1):
    """MiniRocketClassifier eğit.

    Returns: (clf, imputer)
    """
    from aeon.classification.convolution_based import MiniRocketClassifier

    # NaN impute
    imp = SimpleImputer(strategy="mean")
    X_flat = imp.fit_transform(X.reshape(len(X), -1))
    X_3d = X_flat.reshape(X.shape)

    clf = MiniRocketClassifier(n_jobs=n_jobs, random_state=42)
    clf.fit(X_3d, y)

    return clf, imp


def predict_proba(clf, imp, X: np.ndarray) -> np.ndarray:
    """Predict probabilities."""
    if len(X) == 0:
        return np.array([])
    X_flat = imp.transform(X.reshape(len(X), -1))
    X_3d = X_flat.reshape(X.shape)
    return clf.predict_proba(X_3d)[:, 1]


# ============== VALIDATION ==============

def loocv_metrics(X: np.ndarray, y: np.ndarray) -> dict:
    """Leave-one-out CV metrikleri."""
    from aeon.classification.convolution_based import MiniRocketClassifier

    if len(X) < 2:
        return {"pr_auc": None, "kappa": None, "roc_auc": None, "failed": 0}

    imp = SimpleImputer(strategy="mean")
    X_flat = imp.fit_transform(X.reshape(len(X), -1))
    X_3d = X_flat.reshape(X.shape)

    loo = LeaveOneOut()
    probas = np.zeros(len(y))
    failed = 0
    for train_idx, test_idx in loo.split(X_3d):
        try:
            clf = MiniRocketClassifier(n_jobs=-1, random_state=42)
            clf.fit(X_3d[train_idx], y[train_idx])
            probas[test_idx] = clf.predict_proba(X_3d[test_idx])[:, 1]
        except Exception:
            probas[test_idx] = 0.5
            failed += 1

    if len(np.unique(y)) < 2:
        return {"pr_auc": None, "kappa": None, "roc_auc": None, "failed": failed}

    p, r, _ = precision_recall_curve(y, probas)
    pr_auc = auc(r, p)
    pred = (probas >= 0.5).astype(int)
    kappa = cohen_kappa_score(y, pred) if len(np.unique(pred)) > 1 else 0.0
    roc_auc = roc_auc_score(y, probas)

    return {
        "pr_auc": float(pr_auc),
        "kappa": float(kappa),
        "roc_auc": float(roc_auc),
        "failed": int(failed),
    }


# ============== THRESHOLD TUNING ==============

def tune_thresholds_per_district(
    clf, imp, X: np.ndarray, y: np.ndarray, districts: np.ndarray
) -> dict:
    """Her district için en iyi threshold bul (Kappa max).

    Returns: {district: {"threshold": float, "kappa": float}}
    """
    probas = predict_proba(clf, imp, X)
    if len(probas) == 0:
        return {}

    result = {}
    unique_districts = np.unique(districts)
    for d in unique_districts:
        mask = districts == d
        if mask.sum() < 3 or y[mask].sum() == 0 or y[mask].sum() == mask.sum():
            continue

        d_proba = probas[mask]
        d_y = y[mask]

        best_kappa = -1
        best_t = 0.10
        for t in np.arange(0.05, 0.95, 0.05):
            pred = (d_proba >= t).astype(int)
            try:
                k = cohen_kappa_score(d_y, pred) if len(np.unique(pred)) > 1 else 0
            except Exception:
                k = 0
            if k > best_kappa:
                best_kappa = k
                best_t = t

        result[str(d)] = {
            "threshold": float(best_t),
            "kappa": float(best_kappa),
        }
    return result


# ============== WATCH LIST GENERATION ==============

def build_watch_list(
    species: str,
    proba_all: np.ndarray,
    cells: pd.DataFrame,
    thresholds: dict,
    strategy: str = "per_district",
    global_threshold: float = 0.10,
) -> pd.DataFrame:
    """642 hücre için watch list oluştur.

    Args:
        species: 'culex' / 'aedes'
        proba_all: 642 hücrenin olasılıkları
        cells: cells DataFrame
        thresholds: {district: {threshold, kappa}}
        strategy: 'per_district' | 'global' | 'custom'
        global_threshold: strategy='global' ise kullanılacak

    Returns:
        watch_list DataFrame (cell_id, species, proba, threshold_used, district, added_at)
    """
    if len(cells) == 0 or len(proba_all) == 0:
        return pd.DataFrame()

    # Önce kurulmuş trap'leri al (watch list bunları skip eder)
    inits = sheets_client.get_sampling_initiations(active_only=False)
    if len(inits) > 0:
        existing_cells = inits["cell_id"].dropna().astype(int).unique().tolist()
    else:
        existing_cells = []

    # Ziyaret edilmişleri de al
    existing_watch = sheets_client.get_watch_list(species=species)
    visited_cells = []
    if len(existing_watch) > 0 and "visited" in existing_watch.columns:
        visited_cells = existing_watch[existing_watch["visited"] == True]["cell_id"].astype(int).tolist()

    skip_cells = set(existing_cells + visited_cells)

    rows = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for i, cell in cells.iterrows():
        cid = int(cell["cell_id"])
        if cid in skip_cells:
            continue
        if i >= len(proba_all):
            break

        p = float(proba_all[i])
        if pd.isna(p):
            continue

        district = str(cell.get("district", "Unknown"))

        # Threshold seç
        if strategy == "per_district" and district in thresholds:
            t = thresholds[district]["threshold"]
        elif strategy == "global":
            t = global_threshold
        else:
            t = global_threshold

        if p >= t:
            rows.append({
                "cell_id": cid,
                "species": species,
                "proba": p,
                "threshold_used": float(t),
                "district": district,
                "added_at": now,
                "visited": False,
                "trap_id": "",
            })

    return pd.DataFrame(rows).sort_values("proba", ascending=False).head(50)


# ============== FULL PIPELINE ==============

def run_species_pipeline(
    species: str,
    strategy: str = "per_district",
    custom_threshold: float = 0.10,
) -> dict:
    """Bir tür için full pipeline: data → train → predict → write.

    Returns: dict (status, metrics, watch_list_size, ...)
    """
    if species not in MIN_SAMPLES:
        return {"status": "error", "reason": f"Unknown species: {species}"}

    # 1. Training data
    X_train, y_train, train_cell_ids, train_districts = prepare_training_data(species)
    if X_train is None or len(X_train) == 0:
        return {"status": "skip", "reason": "Yetersiz veri"}

    if y_train.sum() < MIN_SAMPLES[species]:
        return {"status": "skip", "reason": f"{species}: {y_train.sum()} pozitif (min {MIN_SAMPLES[species]})"}

    # 2. Validation (LOOCV)
    with st.spinner(f"🔄 {species} LOOCV validation..."):
        val_metrics = loocv_metrics(X_train, y_train)

    # 3. Final model (tüm training data)
    with st.spinner(f"🤖 {species} final model eğitiliyor..."):
        clf, imp = train_minirocket(X_train, y_train)

    # 4. Tüm hücreler için predict (statik parquet'tan)
    cells = load_static_cells()
    all_cell_ids = cells["cell_id"].astype(int).tolist()
    with st.spinner(f"📊 {len(all_cell_ids)} hücre predict ediliyor..."):
        X_all, valid_ids = get_features_for_cells(all_cell_ids)
        proba_all = predict_proba(clf, imp, X_all) if len(X_all) > 0 else np.array([])

    # 5. ML output'u Sheets'e yaz (sadece proba kolonları, küçük write)
    if len(proba_all) > 0:
        proba_map = dict(zip(valid_ids, [float(p) for p in proba_all]))
        update_ml_output(species, proba_map)

    # 6. Per-district threshold tuning (training data üzerinden)
    if strategy == "per_district" and len(train_districts) > 0:
        with st.spinner("🎯 Per-district threshold tuning..."):
            thresholds = tune_thresholds_per_district(clf, imp, X_train, y_train, np.array(train_districts))
    else:
        thresholds = {}

    # 7. Watch list oluştur
    if len(proba_all) > 0:
        # cells sırasıyla proba_all'ı hizala
        proba_ordered = []
        for cid in all_cell_ids:
            if cid in proba_map:
                proba_ordered.append(proba_map[cid])
            else:
                proba_ordered.append(np.nan)
        proba_ordered = np.array(proba_ordered)

        watch = build_watch_list(
            species, proba_ordered, cells, thresholds, strategy, custom_threshold
        )

        # Eski watch list'i temizle (bu tür için)
        old_watch = load_watch_list()
        if len(old_watch) > 0:
            # Eski listeyi silmek için sheet'i yeniden yazmak gerekir
            # Basit yaklaşım: sadece visited=True olanları tut
            pass  # POC için skip, yeni watch direkt eklenir

        # Sheets'e yaz
        if len(watch) > 0:
            watch_rows = watch.to_dict("records")
            for r in watch_rows:
                r["proba"] = float(r["proba"])
                r["threshold_used"] = float(r["threshold_used"])
                r["visited"] = bool(r["visited"])
            sheets_client.append_rows("watch_list", watch_rows)

        watch_size = len(watch)
    else:
        watch_size = 0

    # 8. Cache temizle
    clear_all_caches()

    return {
        "status": "ok",
        "species": species,
        "n_train": int(len(y_train)),
        "n_positive": int(y_train.sum()),
        "n_negative": int((1 - y_train).sum()),
        "n_predicted": int(len(proba_all)),
        "val_metrics": val_metrics,
        "thresholds": thresholds,
        "watch_list_size": watch_size,
        "strategy": strategy,
    }
