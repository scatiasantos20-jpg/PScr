# COLAR no bol_scraper.py (após _extrair_calendario_e_horarios)
# NOTA: este bloco só é necessário se preferires chamar directamente o bol_scraper
#       para obter sessões individuais. Se usares o scrapers/common/teatroapp_export.py,
#       não precisas disto.

def _extrair_sessoes_individuais(soup: BeautifulSoup, *, ano_base: int, mes_base: int) -> list[dict]:
    out: list[dict] = []
    table = soup.find("table", class_="Dias")
    tbody = table.find("tbody") if table else None
    if not tbody:
        return out

    ano = ano_base
    mes = mes_base
    prev_day: int | None = None

    for row in tbody.find_all("tr"):
        cols = row.find_all("td")
        for col in cols:
            if "DiaEvento" not in (col.get("class") or []):
                continue

            day_num: int | None = None
            for s in col.stripped_strings:
                if re.fullmatch(r"\d{1,2}", s):
                    day_num = int(s)
                    break
            if not day_num or day_num < 1 or day_num > 31:
                continue

            if prev_day is not None and day_num < prev_day:
                mes += 1
                if mes > 12:
                    mes = 1
                    ano += 1
            prev_day = day_num

            try:
                d = date(ano, mes, day_num)
            except Exception:
                continue

            for a in col.find_all("a"):
                t_raw = a.get_text(" ", strip=True)
                t_norm = _normalizar_hora_bol(t_raw) or ""
                if not t_norm:
                    continue
                hh_s, mm_s = t_norm.split(":", 1)
                try:
                    hh = int(hh_s)
                    mm = int(mm_s)
                except Exception:
                    continue
                out.append({"date": d.isoformat(), "hour": hh, "minute": mm})

    seen: set[tuple[str, int, int]] = set()
    uniq: list[dict] = []
    for s in out:
        key = (str(s.get("date")), int(s.get("hour", 0)), int(s.get("minute", 0)))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)
    return uniq
