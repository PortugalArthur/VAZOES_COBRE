# Analisador de Vazões do COBRE — V1

Este diretório reúne os programas e módulos necessários para gerar o Parquet consolidado, consultar seus registros e analisar as vazões no dashboard Streamlit. Os caminhos dos dados são escolhidos por janelas do sistema; **não é necessário editar o código**.

## Requisitos do computador

- Windows com Python 3.10 ou mais recente, instalado com `pip` e `tkinter`.
- VS Code com a extensão **Python** da Microsoft.
- Acesso à internet na primeira execução para instalar automaticamente bibliotecas que ainda não estejam disponíveis.

As bibliotecas são instaladas em `.python_packages` dentro desta pasta e reutilizadas nas próximas execuções. O processo Streamlit aberto pelos programas recebe o mesmo ambiente. `requirements.txt` também está disponível para quem preferir preparar um ambiente Python manualmente.

## Executar no VS Code

1. Abra **esta pasta** (`V1 analisador de vazoes`) no VS Code.
2. Abra um dos arquivos da tabela abaixo.
3. Clique em **Run Python File** (o botão triangular do VS Code). Também há configurações com nomes em **Run and Debug**.

| Programa | Função ao clicar em Run |
|---|---|
| `consolidar_vazoes_incrementais_e_lags.py` | Pede as pastas `hydros` e `inflow_lags` da saída `simulation` do COBRE e cria `inflows_with_lags.parquet` nesta pasta. |
| `leitor_parquet_vazoes_cobre.py` | Abre o leitor paginado no navegador e pede o Parquet que será consultado. |
| `analisador_resultados_cobre.py` | Abre o dashboard no navegador. Na barra lateral, selecione o Parquet consolidado, `hydros.json`, `inflow_history.parquet` e `stages.json` correspondentes ao mesmo estudo. |
| `extrair_parquet_cobre_para_excel.py` | Ferramenta auxiliar que pede um Parquet, os identificadores do caso e onde salvar a extração XLSX. |

O leitor e o analisador usam portas locais diferentes e podem ser executados separadamente. Os seletores aceitam arquivos fora desta pasta; os dados não precisam ser copiados para dentro do projeto.

## Entradas do gerador

Selecione as duas pastas da saída do COBRE que contêm subpastas `scenario_id=*` com um `data.parquet` em cada cenário:

```text
simulation/
  hydros/
    scenario_id=0/data.parquet
    scenario_id=1/data.parquet
    ...
  inflow_lags/
    scenario_id=0/data.parquet
    scenario_id=1/data.parquet
    ...
```

O gerador confere a correspondência dos cenários, chaves e lags antes de substituir a saída. A versão atual exige a coluna `inflow_nonnegativity_slack_m3s` nos Parquets `hydros`; se a saída do COBRE não a trouxer, o programa informa qual arquivo está incompatível, sem fabricar valores.

## Entradas do analisador

- **Parquet consolidado:** produzido pelo gerador acima, com cenários, estágios, UHEs, vazão incremental e lags.
- **`hydros.json`:** cadastro de nomes das UHEs do mesmo estudo.
- **`stages.json`:** calendário real dos estágios do mesmo estudo. É necessário para identificar mês/ano, somas de 6 e 12 meses e as correlações que dependem do calendário.
- **`inflow_history.parquet`:** histórico mensal do mesmo estudo. É necessário para a comparação histórica, o gráfico KS e os relatórios que incluem histórico.

O dashboard permite selecionar uma UHE na Aba 1. A Aba 2 contém seis relatórios auditáveis, com exportações XLSX próprias. Os resultados são calculados dos arquivos escolhidos; nenhum conjunto de dados é gerado artificialmente ao abrir o visual.

## Arquivos incluídos

O analisador usa os módulos `relatorio_estatistico_cobre.py`, `analise_percentuais_cobre.py`, `graficos_percentuais_cobre.py`, `autocorrelacao_cobre.py`, `autocorrelacao_anual_cobre.py`, `correlacao_espacial_cobre.py` e `comparacao_ks_cobre.py`. Os quatro programas de entrada usam `preparar_ambiente.py` para preparar as dependências quando necessário. Os testes `test_*.py` ficam nesta pasta para verificar os principais cálculos.

Para executar os testes, caso queira conferir a instalação: `python -m pip install -r requirements-dev.txt` e `python -m pytest -q` nesta pasta. Os testes não são necessários para abrir os programas pelo botão Run.

## Arquivos de dados e GitHub

Esta V1 contém **código, configuração do VS Code, dependências e testes**. Os Parquets e JSONs de uma execução específica do COBRE não foram incluídos: podem ser grandes e devem corresponder ao estudo que cada usuário deseja analisar. O `.gitignore` evita incluir por engano Parquets, planilhas geradas, cadastros locais, caches e bibliotecas instaladas automaticamente.
