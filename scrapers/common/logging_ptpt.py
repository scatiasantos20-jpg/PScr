from __future__ import annotations

import logging
import sys
from typing import Any, Dict, Optional

# ──────────────────────────────────────────────────────────────────────────────
# Níveis em PT-PT (pré-Acordo)
# ──────────────────────────────────────────────────────────────────────────────
_NIVEIS_PT = {
    "DEBUG": "DEPURAÇÃO",
    "INFO": "INFORMAÇÃO",
    "WARNING": "AVISO",
    "ERROR": "ERRO",
    "CRITICAL": "CRÍTICO",
}


class _FormatterPtPt(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.levelname = _NIVEIS_PT.get(record.levelname, record.levelname)
        return super().format(record)


def configurar_logger(nome: str, nivel: int = logging.INFO) -> logging.Logger:
    """
    Configura um logger consistente em PT-PT, evitando handlers duplicados.
    """
    lg = logging.getLogger(nome)
    lg.setLevel(nivel)
    lg.propagate = False

    if not any(isinstance(h, logging.StreamHandler) for h in lg.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            _FormatterPtPt(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%d/%m/%Y %H:%M:%S",
            )
        )
        lg.addHandler(handler)

    return lg


# ──────────────────────────────────────────────────────────────────────────────
# Textos (centralização)
# ──────────────────────────────────────────────────────────────────────────────
_TEXTOS: Dict[str, str] = {
    # logging internals
    "logging.err.suprimido_alteracao": (
        "O erro anterior repetiu-se {repeticoes} vez(es) e foi suprimido até haver alteração. (chave: {chave})"
    ),
    "logging.err.suprimido_flush": (
        "O erro '{mensagem}' repetiu-se {repeticoes} vez(es) e foi suprimido. (chave: {chave})"
    ),

    # selector (main_scraper.py env-only)
    "selector.log.disponiveis": "Scrapers disponíveis: {lista}",
    "selector.err.env_vazio": (
        "A variável SCRAPERS (ou SCRAPER) não está definida no .env. "
        "Ex.: SCRAPERS=bol ou SCRAPERS=bol,ticketline"
    ),
    "selector.err.desconhecidos": "Scraper(s) desconhecido(s): {invalidos}. Opções: {opcoes}.",
    "selector.log.executar": "Selector: a executar {n} scraper(s): {lista}",


    # utils_scrapper (fetch/delay/imagens)
    "utils.fetch.iniciar": "A obter a página (via urllib): {url}",
    "utils.fetch.erro": "Erro ao obter a página: {url}",

    "utils.delay.geral": "A aguardar {segundos:.2f} segundos.",
    "utils.delay.com_descricao": "A aguardar {segundos:.2f} segundos ({descricao}).",
    "utils.delay.antes_sincronizar": "[{origem}] A aguardar {segundos:.2f} segundos antes de sincronizar.",
    "utils.delay.proximo_registo": "[{origem}] A aguardar {segundos:.2f} segundos antes do próximo registo.",

    "utils.imagem.falha_status": "Falha ao descarregar a imagem: {url} (HTTP {status}).",
    "utils.imagem.falha_excepcao": "Erro ao descarregar imagem para '{titulo}': {erro}",

    # utils_scrapper (User-Agent loading)
    "utils.ua.lidos_env": "Foram carregados {n} User-Agent(s) a partir do .env.",
    "utils.ua.lidos_ficheiro": "Foram carregados {n} User-Agent(s) a partir do ficheiro: {ficheiro}.",
    "utils.ua.fallback": "Não foi possível carregar User-Agent(s); será usado o conjunto por defeito.",
    "utils.ua.ficheiro_inexistente": "O ficheiro USER_AGENTS_FILE não existe: {ficheiro}.",

    # main_tickets (labels)
    "tickets.job.bol": "BOL.pt",
    "tickets.job.ticketline": "Ticketline",
    "tickets.job.imperdivel": "Imperdível",
    "tickets.job.teatrovariedades": "Teatro Variedades",

    # main_tickets (info)
    "tickets.info.disponiveis": "Scrapers disponíveis: {lista}",
    "tickets.info.inicio_run": "A iniciar execução: {n} scraper(s): {lista}",
    "tickets.info.inicio_job": "A correr: {label}",
    "tickets.info.sem_dados": "{label}: o scraper não retornou dados.",
    "tickets.info.sem_alteracoes": "{label}: nenhum evento novo ou alterado para sincronizar.",
    "tickets.info.para_sincronizar": "{label}: {n} evento(s) a sincronizar.",
    "tickets.info.concluido_job": "Concluído: {label}",

    # main_tickets (novo/alterado) — NECESSÁRIO p/ o main_tickets que montámos
    "tickets.info.novo_evento": "[{label}] Nova peça detectada: {titulo}",
    "tickets.info.alteracao_detectada": (
        "[{label}] Alteração detectada em '{campo}' para '{titulo}'. Antes: '{antes}' | Agora: '{agora}'"
    ),

    # main_tickets (delay)
    "tickets.delay.antes_processar": "[{label}] A aguardar {segundos:.2f} segundos antes de processar.",

    # main_tickets (erros)
    "tickets.err.env_vazio": "A variável SCRAPERS (ou SCRAPER) não está definida no .env. Opções: {opcoes}.",
    "tickets.err.env_desconhecidos": "Scraper(s) desconhecido(s) no .env: {invalidos}. Opções: {opcoes}.",
    "tickets.err.scraper_desconhecido": "Scraper desconhecido: '{key}'. Opções: {opcoes}.",
    "tickets.err.scrape": "[{label}] Erro durante o scraping.",

    # df_compare (commons)
    "dfcompare.info.primeira_sincronizacao": "[{label}] Primeira sincronização (sem cache anterior).",
    "dfcompare.info.novo_registo": "[{label}] Nova peça detectada: {titulo}",
    "dfcompare.info.alteracao_detectada": (
        "[{label}] Alteração detectada em '{campo}' para '{titulo}'. Antes: '{antes}' | Agora: '{agora}'"
    ),

    # cache
    "cache.info.inexistente": "[{label}] Cache inexistente: {ficheiro}",
    "cache.info.carregado": "[{label}] Cache carregada: {n} registo(s) ({ficheiro})",
    "cache.info.gravado": "[{label}] Cache gravada: {n} registo(s) ({ficheiro})",
    "cache.err.carregar": "[{label}] Erro ao carregar cache: {ficheiro}",
    "cache.err.gravar": "[{label}] Erro ao gravar cache: {ficheiro}",

    # Ticketline (interno)
    "ticketline.info.tipo_pagina": "Tipo de página detectado: {tipo}.",
    "ticketline.warn.sem_html": "Sem conteúdo HTML para a página: {url}.",
    "ticketline.warn.tipo_desconhecido": "Tipo de página desconhecido para o URL: {url}.",
    "ticketline.err.processar_pagina": "Erro ao processar a página: {url}.",

    "ticketline.info.paginas.total": "Número total de páginas encontrado: {max_page}.",
    "ticketline.info.meses.ativos": "Meses activos encontrados: {meses}.",

    "ticketline.warn.sem_lista_eventos": "Estrutura de eventos não encontrada na página: {url}.",
    "ticketline.warn.sem_eventos": "Nenhum evento encontrado na página: {url}.",
    "ticketline.info.eventos.acumulados": "Eventos acumulados: {n}.",
    "ticketline.info.eventos.seleccionados": "Eventos seleccionados (posição {intervalo}): {n}.",

    "ticketline.warn.evento_sem_link": "Evento sem link encontrado; a ignorar.",
    "ticketline.info.evento.processar": "[Evento {idx}] A processar: {titulo} — {url}.",
    "ticketline.warn.dados_none": "Dados do evento vieram vazios; ignorado: {url}.",
    "ticketline.warn.dados_tipo_invalido": "Tipo inesperado de dados para o evento; ignorado: {url}.",

    "ticketline.info.sub_evento": "A processar sub-evento: {url}.",

    "ticketline.delay.proxima_pagina": "A aguardar antes de carregar a próxima página.",
    "ticketline.delay.proximo_evento": "A aguardar antes do próximo evento.",
    "ticketline.delay.proximo_mes": "A aguardar antes do próximo mês.",

    "ticketline.err.calendar.timeout": "Timeout ao carregar o calendário: {url}.",
    "ticketline.err.calendar.falha": "Falha inesperada no calendário: {url}.",

    "ticketline.info.ignorado_existente": "Ignorado (já existente): {url}.",
    "ticketline.warn.data_sessao_invalida": "Data inválida em sessão: {data}.",
    "ticketline.err.formato_data_desconhecido": "Formato de data desconhecido: {data}.",
    "ticketline.info.sessao_ja_conhecida": "Sessão {data_hora} ignorada para '{titulo}' (já conhecida).",

    # BOL.pt
    "bol.info.carregar_listagem": "[BOL] A carregar a listagem: {url}",
    "bol.info.selecao_todos": "[BOL] A retirar: TODOS os eventos da listagem.",
    "bol.info.selecao_range": "[BOL] A retirar: posições {inicio}-{fim} da listagem.",
    "bol.info.processar_evento": "[BOL] A processar evento: {url}",
    "bol.info.evento_processado": "[BOL] Evento processado: {titulo}",
    "bol.info.recolhidos": "[BOL] Foram recolhidos {n} evento(s).",
    "bol.info.nenhum": "[BOL] Nenhum evento foi encontrado.",

    "bol.warn.jsonld_nao_encontrado": "[BOL] Bloco JSON-LD não encontrado.",
    "bol.warn.jsonld_formato_inesperado": "[BOL] Formato inesperado do JSON-LD.",
    "bol.warn.titulo_nao_encontrado": "[BOL] Título não encontrado no JSON-LD.",
    "bol.info.ignorar_conhecido": "[BOL] A ignorar evento já conhecido: {url}",

    "bol.warn.horarios_sem_tabela": "[BOL] Tabela de horários não encontrada: {url}",
    "bol.warn.horarios_erro": "[BOL] Ocorreu um erro ao recolher horários: {url}",

    "bol.err.obter_detalhes": "[BOL] Ocorreu um erro ao obter detalhes do evento: {url}",
    "bol.info.ignorar_categoria_familia": "[BOL] A ignorar evento de família por categoria '{categoria}': {url}",

    "bol.warn.http_retry_status": "[BOL] Retry HTTP por status {status} (tentativa {tentativa}). A aguardar {espera:.2f}s. URL: {url}",
    "bol.warn.http_retry_ex": "[BOL] Retry HTTP por erro de ligação (tentativa {tentativa}). A aguardar {espera:.2f}s. Erro: {erro}. URL: {url}",
    "bol.err.listagem_falhou": "[BOL] Falha a carregar listagem: {url}",
    "ticketline.warn.sem_paginas_env": "[Ticketline] Sem páginas definidas no .env (TICKETLINE_PAGE ou TICKETLINE_PAGES). Execução interrompida por segurança.",
    "ticketline.info.multi_resumo": "[Ticketline] Multi: total={total}, a processar={processar}, offset={offset}, limit={limit} | {url}",

}


def t(chave: str, **kwargs: Any) -> str:
    """
    Resolve uma chave para texto PT-PT. Se a chave não existir, devolve a própria chave.
    """
    template = _TEXTOS.get(chave, chave)
    try:
        return template.format(**kwargs)
    except Exception:
        return template


# ──────────────────────────────────────────────────────────────────────────────
# Erros com supressão (cache até alteração)
# ──────────────────────────────────────────────────────────────────────────────
_ERROR_CACHE: Dict[str, Dict[str, Any]] = {}


def info(logger: logging.Logger, chave: str, **kwargs: Any) -> None:
    logger.info(t(chave, **kwargs))


def aviso(logger: logging.Logger, chave: str, **kwargs: Any) -> None:
    logger.warning(t(chave, **kwargs))


def erro(
    logger: logging.Logger,
    chave: str,
    exc: Optional[BaseException] = None,
    *,
    cache_key: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """
    Emite erro com supressão: se a mensagem final se repetir, suprime até mudar.
    """
    msg_final = t(chave, **kwargs)
    key = cache_key or chave

    state = _ERROR_CACHE.get(key)
    if state is None:
        _ERROR_CACHE[key] = {"last": msg_final, "count": 0, "logger": logger}
        if exc is None:
            logger.error(msg_final)
        else:
            logger.error("%s | %s", msg_final, exc)
        return

    # Se repetido, suprime e incrementa
    if state.get("last") == msg_final:
        state["count"] = int(state.get("count", 0)) + 1
        return

    # Houve alteração -> emitir resumo das repetições suprimidas
    repeticoes = int(state.get("count", 0))
    if repeticoes > 0:
        lg0 = state.get("logger") or logger
        lg0.warning(t("logging.err.suprimido_alteracao", repeticoes=repeticoes, chave=key))

    # Registar novo erro e actualizar estado
    state["last"] = msg_final
    state["count"] = 0
    state["logger"] = logger

    if exc is None:
        logger.error(msg_final)
    else:
        logger.error("%s | %s", msg_final, exc)


def flush_erros(_logger: logging.Logger) -> None:
    """
    Emite resumos pendentes de repetições suprimidas (se existirem).
    Útil no fim de um run (ou entre scrapers).
    """
    for key, state in _ERROR_CACHE.items():
        repeticoes = int(state.get("count", 0))
        if repeticoes > 0:
            lg0 = state.get("logger") or _logger
            lg0.warning(
                t(
                    "logging.err.suprimido_flush",
                    mensagem=str(state.get("last", "")),
                    repeticoes=repeticoes,
                    chave=key,
                )
            )
            state["count"] = 0