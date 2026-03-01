from __future__ import annotations

"""Catálogo central de seletores críticos do uploader Teatro.app."""

SELECTORS = {
    "part1": {
        "form": "form",
        "next_button": r"button:has-text('Próximo'), button:has-text('Seguinte'), button:has-text('Continuar')",
        "title_fallback": "input[aria-label], input[placeholder], textarea[aria-label], textarea[placeholder]",
    },
    "part2": {
        "poster_input": "input[type='file']",
        "next_button": r"button:has-text('Próximo'), button:has-text('Seguinte'), button:has-text('Continuar')",
    },
    "part3": {
        "form": "form:has(input#ticketUrl)",
        "target_form": "form:has(input#ticketUrl)",
        "ticket_url_input": "input#ticketUrl",
        "sala_label": "label",
        "sala_combobox": "button[role='combobox']",
        "calendar_button": "button[type='button']",
        "dialog": "[role='dialog']",
        "options": "[role='option'], [data-radix-collection-item], [cmdk-item]",
    },
}


def get_selectors(part: str) -> dict[str, str]:
    return dict(SELECTORS.get(part, {}))


def all_critical_tokens() -> dict[str, list[str]]:
    """Tokens textuais para testes offline de drift contra fixtures HTML."""
    return {
        "part1": ["form", "Adicionar Nova Peça", "Folha de Sala"],
        "part2": ["Cartaz", "Fotos", "input"],
        "part3": ["Sess", "ticketUrl", "combobox", "dialog"],
    }
