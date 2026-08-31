# Radar das Funções de Produtividade Solar (art. 4º da Portaria MME 140/2026)

Página pública, sem marca, que ajuda gestores de usinas solares a identificar indícios de problema nas
funções de produtividade publicadas pelo ONS para a reapuração de set/2023 a mar/2024, usando **só dados
públicos**:

- funções de produtividade publicadas no SINtegre (produto "Funções de Produtividade": lote do art. 4º e
  revisões vigentes de 2024 a 2026);
- dados abertos do ONS (capacidade de geração, conjuntos de usinas, restrição de operação fotovoltaica em
  meia-hora desde abril/2024).

Nenhum dado privado, confidencial ou fornecido por agentes é usado.

## Estrutura

```
pipeline/01_parse_funcoes.py   lê os CSV das funções (art. 4º + vigentes) -> celulas.parquet, curvas100.parquet
pipeline/02_extrai_publico.py  lê o S3 público do ONS com DuckDB -> cadastro, conjuntos, agregados de meia-hora
pipeline/03_indicadores.py     indicadores por usina (buracos, teto, ONS x ONS, forma, versões, telemetria, viés)
pipeline/04_site.py            exporta site/data/*.json e a pré-visualização com dados embutidos
site/index.html                a página (HTML + JS puro, sem dependências além das fontes)
```

Os dados intermediários (Parquet) ficam fora do repositório. Os caminhos de entrada e saída vêm de
`pipeline/_caminhos.py` (arquivo local, ignorado pelo git) ou das variáveis de ambiente `RADAR_ART4_DIR`,
`RADAR_VIGENTES_DIR` e `RADAR_DADOS`.

## Como atualizar

1. Colocar os zips novos das funções no cache de curvas.
2. Rodar os quatro scripts em ordem com o Python 3.14 (`numpy`, `pandas`, `pyarrow`, `duckdb`).
3. Fazer commit da pasta `site/` e publicar (GitHub Pages).

## Ressalvas

Tudo o que a página mostra é indício, não erro: a função de produtividade é uma tendência central da nuvem de
medições, calibrada pelo ONS segundo a NT-ONS DPL 0031. Os limiares de cada sinal estão descritos na
página 8 do próprio site.
