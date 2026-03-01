#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico offline dos fixtures HTML.

Uso:
  python tools/diagnostico_fixtures.py
  python tools/diagnostico_fixtures.py --json-out .cache/diagnostico_fixtures.json --md-out .cache/diagnostico_fixtures.md
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional


@dataclass
class CheckResult:
    name: str
    ok: bool
    severity: str  # info|warning|error
    detail: str


@dataclass
class FixtureResult:
    fixture: str
    platform: str
    checks: list[CheckResult]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.severity == "error")

    @property
    def errors(self) -> int:
        return sum(1 for c in self.checks if c.severity == "error" and not c.ok)

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.severity == "warning" and not c.ok)


ROOT = Path(__file__).resolve().parents[1]
HTML_ROOT = ROOT / "html"

FIXTURES: list[tuple[str, str, Optional[str]]] = [
    ("bol", "1. Lista.htm", None),
    ("bol", "2. detalhe do evento.htm", None),
    ("bol", "3. Sessoes.htm", None),
    ("ticketline", "Lista.html", "multi"),
    ("ticketline", "2. versão em lista datas.html", "single"),
    ("ticketline", "2. versão lista do mesmo evento.html", "multi"),
    ("ticketline", "3. versão calendario.html", "calendar"),
    ("imperdivel", "1. Lista de eventos.html", None),
    ("imperdivel", "2. Evento.html", None),
    ("teatro.app", "1. lista de peças.htm", None),
    ("teatro.app", "2.Adicionar Nova Peça verificaçao.htm", None),
    ("teatro.app", "3. Adicionar Nova Peça nova.htm", None),
    ("teatro.app", "4. Folha de Sala.htm", None),
    ("teatro.app", "5.Cartaz e fotos.htm", None),
    ("teatro.app", "6.Sessões.htm", None),
]


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _contains_any(text: str, patterns: list[str]) -> bool:
    low = text.lower()
    return any(p.lower() in low for p in patterns)


def _detect_type_fallback(html: str) -> str:
    low = html.lower()
    if "data-name=\"calendar-data\"" in low or "id=\"calendar\"" in low or "ui-datepicker-calendar" in low:
        return "calendar"
    if "sessions_list" in low:
        return "single"
    if "events_list" in low and "schema.org/event" in low:
        return "multi"
    return "desconhecido"


def _build_ticketline_checks(html: str, expected_type: str | None) -> list[CheckResult]:
    checks: list[CheckResult] = []

    detected = None
    detector_err = None
    try:
        from scrapers.common.utils_scrapper import detectar_tipo_pagina  # type: ignore

        detected = detectar_tipo_pagina(html)
    except Exception as e:  # dependências opcionais
        detector_err = str(e)

    if detected is None:
        detected = _detect_type_fallback(html)
        checks.append(
            CheckResult(
                name="detetar_tipo_import",
                ok=False,
                severity="warning",
                detail=f"Falhou import do detector principal, usado fallback: {detector_err}",
            )
        )

    checks.append(
        CheckResult(
            name="ticketline_tipo_pagina",
            ok=(expected_type is None or detected == expected_type),
            severity="error",
            detail=f"detetado={detected}; esperado={expected_type}",
        )
    )

    has_events = bool(re.search(r"itemtype\s*=\s*\"http://schema\.org/Event\"", html, flags=re.I))
    checks.append(
        CheckResult(
            name="ticketline_event_markers",
            ok=has_events,
            severity="warning",
            detail="Presença de marcadores schema.org/Event",
        )
    )

    return checks


def _build_bol_checks(html: str) -> list[CheckResult]:
    checks: list[CheckResult] = []
    checks.append(
        CheckResult(
            name="bol_has_jsonld",
            ok=_contains_any(html, ["application/ld+json"]),
            severity="warning",
            detail="Presença de blocos JSON-LD",
        )
    )
    checks.append(
        CheckResult(
            name="bol_has_buy_links",
            ok=_contains_any(html, ["/Comprar/Bilhetes/"]),
            severity="warning",
            detail="Presença de links de compra/evento",
        )
    )
    return checks


def _build_imperdivel_checks(html: str) -> list[CheckResult]:
    return [
        CheckResult(
            name="imperdivel_has_product_or_event",
            ok=_contains_any(html, ["product", "evento", "woocommerce"]),
            severity="warning",
            detail="Marcadores gerais de lista/evento",
        )
    ]


def _build_teatroapp_checks(html: str) -> list[CheckResult]:
    return [
        CheckResult(
            name="teatroapp_has_form_or_list",
            ok=_contains_any(html, ["lista", "sess", "cartaz", "folha de sala", "adicionar"]),
            severity="warning",
            detail="Conteúdo textual esperado das páginas de workflow",
        )
    ]


def _build_checks(platform: str, html: str, expected_type: str | None) -> list[CheckResult]:
    if platform == "ticketline":
        return _build_ticketline_checks(html, expected_type)
    if platform == "bol":
        return _build_bol_checks(html)
    if platform == "imperdivel":
        return _build_imperdivel_checks(html)
    if platform == "teatro.app":
        return _build_teatroapp_checks(html)
    return [CheckResult(name="unknown_platform", ok=False, severity="error", detail=platform)]


def run_diagnostic() -> dict:
    rows: list[FixtureResult] = []

    for platform, filename, expected_type in FIXTURES:
        path = HTML_ROOT / platform / filename
        checks: list[CheckResult] = []

        if not path.exists():
            checks.append(CheckResult("fixture_exists", False, "error", f"Ficheiro não encontrado: {path}"))
            rows.append(FixtureResult(fixture=str(path.relative_to(ROOT)), platform=platform, checks=checks))
            continue

        html = _load_text(path)
        checks.append(CheckResult("fixture_non_empty", bool(html.strip()), "error", "HTML não vazio"))
        checks.extend(_build_checks(platform, html, expected_type))

        rows.append(FixtureResult(fixture=str(path.relative_to(ROOT)), platform=platform, checks=checks))

    total = len(rows)
    errors = sum(r.errors for r in rows)
    warnings = sum(r.warnings for r in rows)
    ok = errors == 0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "summary": {
            "fixtures": total,
            "errors": errors,
            "warnings": warnings,
            "ok": ok,
        },
        "results": [
            {
                "fixture": r.fixture,
                "platform": r.platform,
                "ok": r.ok,
                "errors": r.errors,
                "warnings": r.warnings,
                "checks": [asdict(c) for c in r.checks],
            }
            for r in rows
        ],
    }


def _render_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [
        "# Diagnóstico de fixtures HTML",
        "",
        f"Gerado em: `{report['generated_at']}`",
        "",
        "## Resumo",
        "",
        f"- Fixtures: **{s['fixtures']}**",
        f"- Erros: **{s['errors']}**",
        f"- Avisos: **{s['warnings']}**",
        f"- Estado: **{'OK' if s['ok'] else 'COM ERROS'}**",
        "",
        "## Detalhe",
        "",
    ]

    for row in report["results"]:
        status = "✅" if row["ok"] else "❌"
        lines.append(f"### {status} `{row['fixture']}` ({row['platform']})")
        lines.append("")
        for c in row["checks"]:
            emoji = "✅" if c["ok"] else ("⚠️" if c["severity"] == "warning" else "❌")
            lines.append(f"- {emoji} **{c['name']}** — {c['detail']}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico offline dos fixtures HTML")
    parser.add_argument("--json-out", default=".cache/diagnostico_fixtures.json", help="Caminho do relatório JSON")
    parser.add_argument("--md-out", default=".cache/diagnostico_fixtures.md", help="Caminho do relatório Markdown")
    args = parser.parse_args()

    report = run_diagnostic()

    json_path = ROOT / args.json_out
    md_path = ROOT / args.md_out
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")

    s = report["summary"]
    print(f"[diagnostico] fixtures={s['fixtures']} errors={s['errors']} warnings={s['warnings']} ok={s['ok']}")
    print(f"[diagnostico] json={json_path}")
    print(f"[diagnostico] md={md_path}")

    return 0 if s["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
