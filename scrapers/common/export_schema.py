from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


# Campo lógico -> aliases aceitáveis no input normalizado por scraper.
LOGICAL_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("Nome da Peça", "Title", "name", "title"),
    "event_url": ("Link da Peça", "URL", "Url", "Link", "Event URL", "event_url"),
    "sessions": ("Horários", "Horarios", "Schedule", "sessions"),
    "price": ("Preço Formatado", "Preço", "Price", "price"),
}

# Requisitos mínimos por plataforma antes de export para Teatro.app.
DEFAULT_REQUIRED_LOGICAL_FIELDS: tuple[str, ...] = ("title", "event_url")
PLATFORM_REQUIRED_LOGICAL_FIELDS: dict[str, tuple[str, ...]] = {
    "bol": ("title", "event_url", "sessions", "price"),
    "ticketline": ("title", "event_url", "sessions", "price"),
    "imperdivel": ("title", "event_url", "sessions"),
    "teatrovariedades": ("title", "event_url", "sessions"),
}


@dataclass(frozen=True)
class SchemaValidationResult:
    platform: str
    required_logical_fields: tuple[str, ...]
    available_columns: tuple[str, ...]
    missing_logical_fields: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_logical_fields



def _columns_from_rows(rows: Sequence[Mapping[str, object]]) -> set[str]:
    cols: set[str] = set()
    for row in rows:
        cols.update(str(k) for k in row.keys())
    return cols



def _resolve_columns(data: object) -> set[str]:
    # pandas.DataFrame
    if hasattr(data, "columns"):
        try:
            return {str(c) for c in list(data.columns)}
        except Exception:
            pass

    # lista/dicts
    if isinstance(data, list):
        dict_rows = [r for r in data if isinstance(r, Mapping)]
        return _columns_from_rows(dict_rows)

    # iterável genérico
    if isinstance(data, Iterable):
        dict_rows = [r for r in data if isinstance(r, Mapping)]
        return _columns_from_rows(dict_rows)

    return set()



def _required_for_platform(platform: str) -> tuple[str, ...]:
    p = (platform or "").strip().lower()
    return PLATFORM_REQUIRED_LOGICAL_FIELDS.get(p, DEFAULT_REQUIRED_LOGICAL_FIELDS)



def validate_export_schema(platform: str, data: object) -> SchemaValidationResult:
    columns = _resolve_columns(data)
    required = _required_for_platform(platform)

    missing: list[str] = []
    for logical_field in required:
        aliases = LOGICAL_FIELD_ALIASES.get(logical_field, ())
        if not any(alias in columns for alias in aliases):
            missing.append(logical_field)

    return SchemaValidationResult(
        platform=(platform or "").strip().lower(),
        required_logical_fields=required,
        available_columns=tuple(sorted(columns)),
        missing_logical_fields=tuple(missing),
    )



def ensure_export_schema(platform: str, data: object) -> None:
    result = validate_export_schema(platform, data)
    if result.ok:
        return

    raise ValueError(
        "schema inválido para export teatro.app "
        f"(platform={result.platform or 'desconhecida'}): "
        f"missing={', '.join(result.missing_logical_fields)} | "
        f"available={', '.join(result.available_columns) if result.available_columns else '(sem colunas)'}"
    )
