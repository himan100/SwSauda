"""ML pipeline for index trend prediction using minute aggregated index and option data.

This module provides:
 - Data extraction from MongoDB (IndexTick, v_option_pair_base view)
 - Minute aggregation of tick data
 - Feature engineering (returns, rolling stats, EMAs, option pair metrics, time to expiry)
 - Label creation for future horizon classification (direction up/down)
 - Model training (simple Logistic Regression baseline)
 - Prediction interface

Design goals:
 - Keep heavy CPU-bound model fitting off the event loop (run in thread)
 - Avoid large memory usage; operations are vectorized with pandas
 - Be resilient to missing option view (attempt to create it via provided script)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Dict

import pandas as pd
import numpy as np
from joblib import dump, load
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from database import db
from main import execute_mongo_views_script  # reuse existing view creation

MODEL_DIR = Path("trained_models")
MODEL_DIR.mkdir(exist_ok=True)


@dataclass
class TrainConfig:
    database_name: str
    horizon_minutes: int = 5              # Predict direction over next N minutes
    lookback_minutes: int = 60            # Feature window size
    test_size: float = 0.2
    min_samples: int = 200               # Require at least this many rows
    random_state: int = 42


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


async def _fetch_index_ticks(database_name: str) -> pd.DataFrame:
    """Fetch raw index ticks (ft seconds, lp) from MongoDB and return as DataFrame sorted ascending.
    Assumes collection name 'IndexTick'."""
    collection = db.client[database_name]["IndexTick"]
    cursor = collection.find({}, {"ft": 1, "lp": 1, "rt": 1, "_id": 0}).sort("ft", 1)
    docs: List[Dict] = []
    async for doc in cursor:
        if doc.get("lp") is not None:
            docs.append(doc)
    if not docs:
        return pd.DataFrame(columns=["ft", "lp", "rt"])  # empty
    df = pd.DataFrame(docs)
    return df


async def _fetch_option_pair_view(database_name: str) -> pd.DataFrame:
    """Fetch option pair base view (created every 300s) to derive option-based features.
    Columns of interest: ft, sum_lp, risk_prec.
    Returns empty DataFrame if view absent or empty."""
    collection = db.client[database_name].get_collection("v_option_pair_base", None)
    if collection is None:
        # Try creating views (will no-op if fails)
        await execute_mongo_views_script(database_name)
        collection = db.client[database_name].get_collection("v_option_pair_base", None)
        if collection is None:
            return pd.DataFrame(columns=["ft", "sum_lp", "risk_prec"])
    try:
        cursor = collection.find({}, {"ft": 1, "sum_lp": 1, "risk_prec": 1, "_id": 0}).sort("ft", 1)
    except Exception:
        return pd.DataFrame(columns=["ft", "sum_lp", "risk_prec"])
    docs: List[Dict] = []
    async for doc in cursor:
        docs.append(doc)
    if not docs:
        return pd.DataFrame(columns=["ft", "sum_lp", "risk_prec"])
    return pd.DataFrame(docs)


def _aggregate_minutes(index_df: pd.DataFrame) -> pd.DataFrame:
    if index_df.empty:
        return index_df
    # ft is seconds epoch; derive minute epoch anchor
    index_df = index_df.copy()
    index_df["minute_ft"] = (index_df.ft // 60) * 60
    # For each minute choose the last lp within that minute (since sorted ascending)
    minute_df = index_df.groupby("minute_ft", as_index=False).agg({"lp": "last"})
    minute_df = minute_df.sort_values("minute_ft").reset_index(drop=True)
    return minute_df.rename(columns={"minute_ft": "ft"})


def _add_features(minute_df: pd.DataFrame, option_df: pd.DataFrame, config: TrainConfig, expiry_ts: Optional[int]) -> pd.DataFrame:
    df = minute_df.copy()
    # Basic returns
    df["return_1m"] = df.lp.pct_change()
    for w in [3, 5, 10, 15]:
        df[f"ret_mean_{w}"] = df.return_1m.rolling(w).mean()
        df[f"ret_std_{w}"] = df.return_1m.rolling(w).std()
    # EMAs
    for span in [9, 21, 50]:
        df[f"ema_{span}"] = _ema(df.lp, span)
    df["ema_diff_9_21"] = df["ema_9"] - df["ema_21"]
    # Option features (resample to minute)
    if not option_df.empty:
        option_df = option_df.copy()
        option_df["minute_ft"] = (option_df.ft // 60) * 60
        option_min = option_df.groupby("minute_ft", as_index=False).agg({"sum_lp": "last", "risk_prec": "last"})
        option_min = option_min.rename(columns={"minute_ft": "ft"})
        df = df.merge(option_min, on="ft", how="left")
        # Forward fill infrequent 5-min values
        df["sum_lp"] = df["sum_lp"].ffill()
        df["risk_prec"] = df["risk_prec"].ffill()
    else:
        df["sum_lp"] = np.nan
        df["risk_prec"] = np.nan
    # Minutes to expiry feature
    if expiry_ts:
        df["minutes_to_expiry"] = (expiry_ts - df.ft) / 60.0
    else:
        df["minutes_to_expiry"] = np.nan
    # Clip negative (past expiry)
    df.loc[df.minutes_to_expiry < 0, "minutes_to_expiry"] = 0
    # Lookback-based normalized price features
    df["rolling_min_lookback"] = df.lp.rolling(config.lookback_minutes, min_periods=1).min()
    df["rolling_max_lookback"] = df.lp.rolling(config.lookback_minutes, min_periods=1).max()
    df["price_pos_pct"] = (df.lp - df.rolling_min_lookback) / (df.rolling_max_lookback - df.rolling_min_lookback + 1e-9)
    return df


def _create_labels(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    df = df.copy()
    df["future_lp"] = df.lp.shift(-horizon)
    df["future_return"] = (df.future_lp - df.lp) / df.lp
    df["label"] = (df.future_return > 0).astype(int)
    return df


def _prepare_ml_dataset(df: pd.DataFrame, config: TrainConfig) -> Tuple[pd.DataFrame, pd.Series]:
    # Drop rows with NaNs in feature window or labels
    feature_cols = [c for c in df.columns if c not in {"future_lp", "future_return", "label", "lp"} and not c.startswith("rolling_")]
    # Keep engineered rolling columns if desired
    feature_cols.extend([c for c in df.columns if c.startswith("ret_mean_") or c.startswith("ret_std_") or c.startswith("ema_") or c in ["ema_diff_9_21", "sum_lp", "risk_prec", "minutes_to_expiry", "price_pos_pct"]])
    feature_cols = sorted(set(feature_cols))
    ml_df = df.dropna(subset=feature_cols + ["label"]).copy()
    X = ml_df[feature_cols]
    y = ml_df["label"].astype(int)
    return X, y

async def _fetch_expiry(database_name: str) -> Optional[int]:
    """Attempt to infer a representative expiry timestamp.
    Strategy: find earliest ATM option in Option collection with highest occurrence of expiry.
    Fallback None if not found."""
    try:
        option_coll = db.client[database_name]["Option"]
        cursor = option_coll.find({}, {"expiry": 1, "_id": 0}).limit(50)
        expiries = []
        async for doc in cursor:
            exp = doc.get("expiry")
            if isinstance(exp, (int, float)) and exp > 0:
                expiries.append(int(exp))
        if not expiries:
            return None
        values, counts = np.unique(expiries, return_counts=True)
        return int(values[np.argmax(counts)])
    except Exception:
        return None

async def build_training_frame(config: TrainConfig) -> pd.DataFrame:
    index_df, option_df, expiry_ts = await asyncio.gather(
        _fetch_index_ticks(config.database_name),
        _fetch_option_pair_view(config.database_name),
        _fetch_expiry(config.database_name)
    )
    minute_df = _aggregate_minutes(index_df)
    feature_df = _add_features(minute_df, option_df, config, expiry_ts)
    labeled_df = _create_labels(feature_df, config.horizon_minutes)
    return labeled_df

async def train_index_model(config: TrainConfig) -> Dict:
    df = await build_training_frame(config)
    if df.empty or len(df) < config.min_samples:
        return {"status": "error", "message": f"Insufficient data rows: {len(df)}"}
    X, y = _prepare_ml_dataset(df, config)
    if len(X) < config.min_samples:
        return {"status": "error", "message": f"Insufficient feature rows after cleaning: {len(X)}"}
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=config.test_size, random_state=config.random_state, stratify=y if y.nunique() > 1 else None
    )
    def _fit():
        model = LogisticRegression(max_iter=500, n_jobs=1)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        model_path = MODEL_DIR / f"index_trend_{config.database_name}.joblib"
        dump({
            "model": model,
            "features": list(X.columns),
            "config": config.__dict__,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "accuracy": acc
        }, model_path)
        return acc, model_path
    acc, model_path = await asyncio.to_thread(_fit)
    return {
        "status": "ok",
        "samples": len(X),
        "features": list(X.columns),
        "accuracy": acc,
        "model_path": str(model_path)
    }

def _load_model(database_name: str):
    path = MODEL_DIR / f"index_trend_{database_name}.joblib"
    if not path.exists():
        return None
    return load(path)

def get_model_status(database_name: str) -> Dict:
    bundle = _load_model(database_name)
    if bundle is None:
        return {"exists": False}
    return {
        "exists": True,
        "trained_at": bundle.get("trained_at"),
        "features": bundle.get("features"),
        "config": bundle.get("config"),
        "accuracy": bundle.get("accuracy")
    }

async def predict_index_direction(database_name: str, lookback_minutes: int = 60) -> Dict:
    bundle = _load_model(database_name)
    if bundle is None:
        return {"status": "error", "message": "Model not trained"}
    features = bundle["features"]
    config_data = bundle["config"]
    cfg = TrainConfig(database_name=database_name, horizon_minutes=config_data.get("horizon_minutes", 5), lookback_minutes=lookback_minutes)
    df = await build_training_frame(cfg)
    if df.empty:
        return {"status": "error", "message": "No data"}
    last_row = df.dropna(subset=features).iloc[-1:]
    if last_row.empty:
        return {"status": "error", "message": "No complete feature row for prediction"}
    model = bundle["model"]
    proba = model.predict_proba(last_row[features])[0].tolist()
    pred = int(np.argmax(proba))
    return {
        "status": "ok",
        "prediction": pred,
        "probabilities": {"down": proba[0], "up": proba[1] if len(proba) > 1 else None},
        "ft": int(last_row.ft.values[0]),
        "price": float(last_row.lp.values[0]),
        "minutes_to_expiry": float(last_row.minutes_to_expiry.values[0]) if "minutes_to_expiry" in last_row else None
    }
