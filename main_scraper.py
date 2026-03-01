import sys

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

from scrapers.common.logging_ptpt import configurar_logger, erro, flush_erros, t
from scrapers.main_tickets import run_many, available
from scrapers.common.selector_env import read_scrapers_from_env

logger = configurar_logger("scrapers.main")

def _validar(keys: list[str]) -> tuple[list[str], list[str]]:
    ops = set(available())
    validos = [k for k in keys if k in ops]
    invalidos = [k for k in keys if k not in ops]
    return validos, invalidos


def main(argv: list[str]) -> int:
    # Única opção por CLI: listar disponíveis (sem argparse para evitar strings soltas)
    if "--listar" in argv:
        logger.info(t("selector.log.disponiveis", lista=", ".join(available())))
        return 0

    keys = read_scrapers_from_env()
    if keys == ["all"]:
        keys = available()
    if not keys:
        erro(logger, t("selector.err.env_vazio"), cache_key="selector:env_vazio")
        return 2

    validos, invalidos = _validar(keys)
    if invalidos:
        erro(
            logger,
            t(
                "selector.err.desconhecidos",
                invalidos=", ".join(invalidos),
                opcoes=", ".join(available()),
            ),
            cache_key="selector:unknown",
        )
        return 2

    logger.info(t("selector.log.executar", n=len(validos), lista=", ".join(validos)))
    code = run_many(validos)

    flush_erros(logger)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))