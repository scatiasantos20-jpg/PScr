from __future__ import annotations

from typing import Tuple
import pandas as pd

from scrapers.common.df_utils import ensure_cols, norm_str
from scrapers.common.logging_ptpt import info

def filter_new_or_changed_with_logs(
    df_new: pd.DataFrame,
    df_existing: pd.DataFrame,
    *,
    logger,
    label: str,
    fields: Tuple[str, ...] = ("Data Fim", "Link da Peça"),
) -> pd.DataFrame:
    if df_new is None or df_new.empty:
        return pd.DataFrame()

    df_existing = ensure_cols(df_existing, ["Nome da Peça", "Data Fim", "Link da Peça", "Horários", "Preço Formatado"])
    df_new = ensure_cols(df_new, ["Nome da Peça", "Data Fim", "Link da Peça", "Horários", "Preço Formatado"])

    if df_existing.empty:
        info(logger, "dfcompare.info.primeira_sincronizacao", label=label)
        for _, r in df_new.iterrows():
            titulo = norm_str(r.get("Nome da Peça"))
            if titulo:
                info(logger, "dfcompare.info.novo_registo", label=label, titulo=titulo)
        return df_new.copy()

    # Índices: primeiro Link, depois Nome
    idx_link = {}
    idx_nome = {}

    for _, r in df_existing.iterrows():
        link = norm_str(r.get("Link da Peça")).lower()
        if link and link not in idx_link:
            idx_link[link] = r

        nome = norm_str(r.get("Nome da Peça"))
        if nome and nome not in idx_nome:
            idx_nome[nome] = r

    out = []
    for _, novo in df_new.iterrows():
        titulo = norm_str(novo.get("Nome da Peça"))
        link_novo = norm_str(novo.get("Link da Peça")).lower()

        existente = None
        if link_novo and link_novo in idx_link:
            existente = idx_link[link_novo]
        elif titulo and titulo in idx_nome:
            existente = idx_nome[titulo]

        if existente is None:
            if titulo:
                info(logger, "dfcompare.info.novo_registo", label=label, titulo=titulo)
            out.append(novo)
            continue

        alterado = False
        for f in fields:
            v_old = norm_str(existente.get(f)) or "N/A"
            v_new = norm_str(novo.get(f)) or "N/A"
            if v_old != v_new:
                info(
                    logger,
                    "dfcompare.info.alteracao_detectada",
                    label=label,
                    campo=f,
                    titulo=titulo or "Sem título",
                    antes=v_old,
                    agora=v_new,
                )
                alterado = True

        if alterado:
            out.append(novo)

    return pd.DataFrame(out)