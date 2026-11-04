# B3 Valuation

Pipeline de indicadores fundamentalistas de ações da B3 (pacote `valuationb3`). Consolida dados
públicos de quatro fontes num banco DuckDB local, calcula indicadores e rankings e os exibe num
painel Streamlit somente leitura.

!!! warning "Não é recomendação de investimento"
    Os sinais de Compra/Manter/Venda são relativos e mecânicos, derivados de 10 rankings sobre
    uma fotografia de dados. **Não constituem recomendação de investimento.**

## Fontes

| Fonte | O que traz | Tabela Bronze |
|---|---|---|
| B3 — empresas listadas | Cadastro das companhias e tickers negociáveis | `raw.b3_empresas` |
| Fundamentus | Indicadores fundamentalistas por ticker | `raw.fundamentus_acoes` |
| Minha Receita | Dados cadastrais por CNPJ | `raw.minhareceita_empresas` |
| Yahoo Finance (yfinance) | Histórico diário de cotações | `raw.yfinance_cotacoes` |

## Por onde começar

- [Instalação e uso](uso.md): preparar o ambiente e executar o pipeline e o painel.
- [Arquitetura](arquitetura.md): camadas Bronze → Silver → Gold e garantias de cada etapa.
- [Referência da API](referencia/api.md): módulos, funções, tabelas e comandos.
- [Marts](referencia/marts.md) e [Rankings](referencia/rankings.md): indicadores, rankings e a
  recomendação consolidada.
- [Decisões](decisoes.md): decisões transversais e especificações que orientaram a implementação.
