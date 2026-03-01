# Análise geral do repositório PScr

## 1) Resumo executivo

Este repositório é uma pipeline de scraping + preparação de dados para sincronização com o Teatro.app. A arquitetura está funcional e relativamente modular (scrapers por fonte/plataforma, utilitários comuns, uploader em pacote separado), mas há sinais de crescimento orgânico que aumentam risco operacional:

- ficheiros muito longos e com múltiplas responsabilidades;
- artefactos de build/versionamento no repositório (`__pycache__`, binário de chromedriver);
- ausência de testes automatizados versionados;
- presença de ficheiro duplicado/legado (`bol_scraper copy.py`).

## 2) O que foi analisado

### Inventário rápido

- Linguagem principal: Python.
- Ficheiros `.py` (sem `__pycache__`): **46**.
- Linhas aproximadas de código Python: **9.144**.
- Áreas principais:
  - `scrapers/`: recolha e normalização por plataformas/fontes;
  - `teatroapp_uploader/`: automação de upload por etapas;
  - entry points em `main_scraper.py` e `teatroapp_uploader.py`.

### Pontos de entrada

- `main_scraper.py` valida seleção de scrapers e delega para `scrapers.main_tickets`.
- `scrapers/main_tickets.py` orquestra execução por job (`bol`, `ticketline`, `imperdivel`, `teatrovariedades`), aplica diff, atualiza cache e aciona export/autorun para Teatro.app.
- `teatroapp_uploader.py` atua como shim para `python -m teatroapp_uploader`.

## 3) Leitura arquitetural

### Forças

1. **Boa separação por domínio/fonte**: cada plataforma em pasta própria.
2. **Orquestrador explícito** (`JOBS` com metadados) facilita adicionar/remover scrapers.
3. **Ciclo de dados consistente**: carregar baseline → scrape → diff/filtragem → cache/export.
4. **Uso de flags de ambiente** para controlar comportamentos de execução (export, autorun, strict mode).

### Fragilidades

1. **Acoplamento alto em módulos grandes**
   - `scrapers/common/teatroapp_export.py`, `teatroapp_uploader/part3_sessions.py`, `scrapers/ticket_platforms/BOL/bol_scraper.py` são extensos, dificultando manutenção e testes.
2. **Higiene de repositório**
   - `__pycache__/` versionado;
   - `scrapers/common/chromedriver-win64/chromedriver.exe` no repositório;
   - ficheiro `bol_scraper copy.py` sugere código paralelo/legado.
3. **Qualidade sem rede de segurança**
   - não há testes `test_*.py` versionados;
   - sem suite de regressão para validar regras de parsing/diff.
4. **Confiabilidade operacional**
   - grande dependência de comportamento de sites externos;
   - risco de regressões silenciosas sem testes de contrato por scraper.

## 4) Prioridades recomendadas (ordem prática)

1. **Higiene imediata (baixo custo / alto impacto)**
   - remover artefactos de execução (`__pycache__`) do controlo de versão;
   - decidir política para `chromedriver.exe` (vendorizado vs setup automatizado);
   - eliminar/arquivar `bol_scraper copy.py`.

2. **Cobertura de testes mínima viável**
   - adicionar testes unitários para funções puras (`selector_env`, `df_utils`, comparadores);
   - criar testes de parsing com HTML fixture para cada scraper crítico.

3. **Refatoração progressiva de ficheiros críticos**
   - dividir módulos grandes por responsabilidade:
     - parsing
     - transformação de dados
     - integração I/O (rede, ficheiros, subprocessos)

4. **Observabilidade e robustez**
   - padronizar códigos de erro por etapa;
   - registrar métricas de execução por scraper (contagem de itens, tempo, taxa de erro).

## 5) Riscos técnicos identificados

- Mudanças de layout dos sites podem interromper scraping sem alarme precoce.
- Falta de testes dificulta distinguir erro de infra vs regressão de código.
- Módulos extensos aumentam risco de efeitos colaterais em alterações simples.

## 6) Plano de ação em 2 semanas (sugestão)

### Semana 1

- Limpeza de repositório e `.gitignore`.
- Testes unitários para utilitários críticos.
- CI básica: `compileall` + `pytest`.

### Semana 2

- Refatorar 1 módulo grande (começar por BOL scraper).
- Criar 1 teste de contrato de parsing por plataforma principal.
- Definir baseline de métricas operacionais.

## 7) Verificações executadas nesta análise

- Compilação de todo o repositório para bytecode (`compileall`) com sucesso.
- Mapeamento de volume e distribuição de código Python.
- Leitura dos entry points e orquestrador principal para avaliação arquitetural.

