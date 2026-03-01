from __future__ import annotations

from typing import Any, Iterable
import pandas as pd


def norm_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    return str(v).strip()


def ensure_cols(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=list(cols))
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df


def to_df(result: Any) -> pd.DataFrame:
    if result is None:
        return pd.DataFrame()

    if isinstance(result, pd.DataFrame):
        df = result.copy()
    elif isinstance(result, list):
        df = pd.DataFrame(result)
    else:
        df = pd.DataFrame(result)

    if "Nome da Peça" not in df.columns and "Nome" in df.columns:
        df.rename(columns={"Nome": "Nome da Peça"}, inplace=True)

    if "Link da Peça" not in df.columns:
        for alt in ("Link", "URL", "url", "link"):
            if alt in df.columns:
                df.rename(columns={alt: "Link da Peça"}, inplace=True)
                break

    df = ensure_cols(df, ["Nome da Peça", "Data Fim", "Link da Peça", "Horários", "Preço Formatado"])

    if "Data Fim" in df.columns:
        df["Data Fim"] = df["Data Fim"].fillna("N/A")

    return df


def build_known_links(df_existentes: pd.DataFrame) -> set[str]:
    if df_existentes is None or df_existentes.empty:
        return set()
    if "Link da Peça" not in df_existentes.columns:
        return set()

    return set(
        df_existentes["Link da Peça"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.lower()
        .unique()
    )

def build_known_links(df_existentes: pd.DataFrame) -> set[str]:
    if df_existentes is None or df_existentes.empty:
        return set()
    if "Link da Peça" not in df_existentes.columns:
        return set()

    return set(
        df_existentes["Link da Peça"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.lower()
        .str.rstrip("/")   # <<< ADICIONAR
        .unique()
    )