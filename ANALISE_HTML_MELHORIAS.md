# Análise profunda de melhorias (com base nos HTML em `html/`)

## Contexto

Esta análise foca-se no que pode ser melhorado no pipeline de scraping e upload, usando os HTML de referência que estão no repositório (BOL, Ticketline, Imperdível e Teatro.app).

Objetivo: transformar estes HTML em **contratos de regressão** e reduzir risco de quebra quando os sites mudam layout.

---

## 1) Leitura dos HTML disponíveis e cobertura atual

### 1.1. Estado atual dos fixtures

Os HTML existentes já cobrem cenários importantes:

- **BOL**: listagem, detalhe e sessões.
- **Ticketline**: listagem, versão multi/lista, calendário.
- **Imperdível**: lista + evento.
- **Teatro.app**: fluxo quase completo de criação/edição de peça (lista, dados, folha de sala, cartaz/fotos, sessões).

**Valor**: este conjunto é suficiente para criar uma suíte de “testes de contrato” robusta por plataforma.

### 1.2. Lacuna principal

Há testes para BOL, mas a cobertura de parsing por fixture ainda é muito limitada para Ticketline/Imperdível/Teatro.app.

Impacto: quando um seletor quebra, o erro tende a surgir só em runtime (produção), não em CI.

---

## 2) Melhorias prioritárias (alto impacto)

## P0 — Transformar HTML em “contratos de parsing”

### O que fazer

1. Criar testes por plataforma com estes HTML locais (sem rede):
   - deteção de tipo de página;
   - extração de links/eventos;
   - campos mínimos obrigatórios (nome, link, sessões ou indicação de ausência);
   - deduplicação e normalização.

2. Definir uma pequena matriz por fixture:
   - `fixture`
   - `tipo esperado`
   - `contagem mínima de eventos/sessões`
   - `campos obrigatórios`

### Porque melhora

- Dá “alarme cedo” quando o layout muda.
- Evita regressões silenciosas.
- Acelera manutenção (debug orientado por fixture específica).

---

## P0 — Endurecer deteção de tipo de página (Ticketline)

A deteção atual depende de sinais estruturais específicos (calendar/single/multi). Isso é bom, mas pode falhar quando há pequenas mudanças de classes/containers.

### O que melhorar

- Introduzir **scoring por sinais** (em vez de condição única), por exemplo:
  - calendar: `calendar-data`, `#calendar`, `ui-datepicker`;
  - single: `sessions_list` + blocos de sessão;
  - multi: `events_list` + `itemtype=Event`.
- Em empate/ambiguidade, registrar razão da decisão no log.

### Benefício

Menos falsos “desconhecido”, menos fallback manual, melhor observabilidade.

---

## P0 — Pipeline offline para validação de seletores

### O que fazer

Criar um comando/script de diagnóstico, ex.: `python tools/diagnostico_fixtures.py`, que para cada HTML:

- roda o parser correspondente;
- reporta campos extraídos vs ausentes;
- marca severidade (erro/aviso/info);
- produz saída em markdown/json para CI artefact.

### Benefício

Padroniza debugging e acelera investigação de quebras.

---

## 3) Melhorias de robustez por plataforma

## Ticketline

### Riscos observáveis

- Múltiplas variantes de listagem (lista simples, highlights/top list, calendário interativo).
- Cadeia multi → single/calendar pode introduzir duplicação ou perda parcial de metadados.

### Melhorias

1. **Canonização forte de URL** (query params irrelevantes, trailing slash, case).
2. **Dedupe em dois níveis**:
   - por URL canónica;
   - por par `(titulo normalizado, local, data)` como fallback.
3. Guardar no output metadados de origem:
   - `source_page_type` (`multi`, `single`, `calendar`),
   - `source_fixture` (em testes),
   - `extraction_path` (ex.: `multi->calendar`).
4. Cobrir com testes todos os HTML `ticketline/*.html` existentes.

## BOL

### Pontos fortes

- Já existe extração por seletores + JSON-LD e testes iniciais.

### Melhorias

1. Nos testes, validar também:
   - fallback de seletores (quando um falha);
   - coexistência de múltiplos blocos JSON-LD (Event + Product);
   - normalização de horas (`19h`, `19h30`, `19:30`).
2. Adicionar “quality gates” por evento:
   - sem título => rejeita;
   - sem URL => rejeita;
   - sem data/sessão => marca incompleto (não falha total).

## Imperdível

### Riscos

- Parsing de texto livre para `DATA`, `HORA`, `CLASSIFICAÇÃO` depende de regex e normalização de rótulos.

### Melhorias

1. Testes parametrizados para os formatos de data já suportados (intervalos, listas, meses múltiplos).
2. Criar camada `parse_result` com:
   - `value`,
   - `confidence`,
   - `raw_fragment`.
3. Em baixa confiança, manter evento mas com flag de revisão.

## Teatro.app (uploader)

### Oportunidade

Os HTML de Teatro.app permitem validar o fluxo de campos e navegabilidade sem depender de ambiente real.

### Melhorias

1. Snapshot de seletores críticos por etapa (`part1_details`, `part2_media`, `part3_sessions`).
2. Teste de “drift de UI”:
   - se seletor crítico desaparecer, apontar etapa afetada.
3. Catálogo central de seletores por etapa (evitar strings soltas em múltiplos pontos).

---

## 4) Arquitetura e qualidade de código

## P1 — Separar parsing puro de I/O

### Problema

Alguns módulos misturam rede, parsing, normalização e regras de negócio no mesmo fluxo.

### Proposta

- Funções puras: `parse_*_from_html(html) -> ParsedEvent/ParsedSession`.
- Adapters de I/O: fetch, retry, timeout, backoff.
- Orquestrador apenas compõe blocos.

### Resultado

- Mais testável (fixtures locais).
- Menor acoplamento.
- Refatoração mais segura.

## P1 — Modelo de domínio comum de “qualidade de extração”

Adicionar a cada evento:

- `required_fields_ok: bool`
- `missing_fields: list[str]`
- `warnings: list[str]`
- `parser_version: str`

Assim, o export pode decidir: bloquear, degradar ou publicar com aviso.

## P1 — Logging estruturado e métricas

Padronizar logs com chaves fixas (por plataforma e etapa):

- `events_found`
- `events_parsed`
- `events_rejected`
- `selector_fallback_used`
- `duration_ms`

Isto permite dashboard simples e detecção de regressões de volume.

---

## 5) Plano prático (curto prazo)

## Semana 1

1. ~~Criar suíte `tests/test_ticketline_fixtures.py` com os 4 HTML da pasta `html/ticketline`.~~ ✅
2. ~~Criar `tests/test_imperdivel_parsing.py` com casos de datas e labels.~~ ✅
3. ~~Expandir `tests/test_bol_scraper_parsing.py` com cenários de fallback e normalização.~~ ✅

## Semana 2

1. ~~Implementar `tools/diagnostico_fixtures.py`.~~ ✅
2. ~~Definir relatório de qualidade de extração por run.~~ ✅
3. ~~Começar refatoração orientada por função pura (primeiro Ticketline multi/single/calendar).~~ ✅

## Semana 3

1. ~~Catálogo central de seletores do uploader Teatro.app.~~ ✅
2. ~~Testes de drift de UI por etapa.~~ ✅
3. ~~Integração CI para rodar parsing offline em todos os fixtures.~~ ✅

---

## 6) Quick wins imediatos (baixo custo)

1. Criar um índice dos fixtures em `html/README.md` (plataforma, tipo, data de captura).
2. Definir nomenclatura consistente dos ficheiros HTML (evitar ambiguidades de “versão 2”).
3. Garantir encoding de leitura uniforme (`utf-8` com `errors='ignore'`) em todos os testes.
4. Adicionar marcador de versão dos parsers para facilitar rollback quando houver mudança de site.

---

## 7) Resultado esperado com estas melhorias

- Menos quebras em produção após alterações de layout.
- Mais previsibilidade no ciclo scrape → diff → export.
- Maior velocidade de manutenção (debug guiado por fixture e relatório).
- Base sólida para expandir plataformas sem aumentar risco operacional.

