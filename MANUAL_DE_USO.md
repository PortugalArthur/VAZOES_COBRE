# Manual rápido — programas de vazões do COBRE

Este manual mostra como gerar o arquivo consolidado, analisar os resultados e consultar os registros. Os três programas ficam na pasta `V1 analisador de vazoes`. Não é preciso editar o código.

## Antes de começar

- Use um computador Windows com Python 3.10 ou mais recente e o VS Code com a extensão **Python**.
- Abra a pasta `V1 analisador de vazoes` no VS Code. Na primeira execução, mantenha a internet disponível: o programa pode instalar as bibliotecas necessárias automaticamente. Aguarde a instalação terminar.
- Tenha em mãos os arquivos de **um mesmo estudo do COBRE**. Não misture saídas de estudos diferentes.

Para executar qualquer programa, abra seu arquivo `.py` no VS Code e clique em **Run Python File** (botão triangular, no canto superior direito). Se preferir o terminal, abra-o nessa mesma pasta e use os comandos indicados em cada etapa.

## 1. Gerar o Parquet consolidado

Execute `consolidar_vazoes_incrementais_e_lags.py`:

```powershell
python consolidar_vazoes_incrementais_e_lags.py
```

1. Na primeira janela, selecione a pasta **`hydros`** da saída `simulation` do COBRE. Selecione a pasta inteira, não um `data.parquet` individual.
2. Na segunda janela, selecione a pasta **`inflow_lags`** do mesmo estudo.
3. Aguarde o processamento. O terminal mostra o progresso, e uma janela informa quando a consolidação terminar.

O resultado é `inflows_with_lags.parquet`, salvo na mesma pasta dos programas. Guarde uma cópia antes de gerar outro estudo: uma nova execução concluída substitui esse arquivo. Se alguma entrada estiver incompatível, o programa mostra a causa e não publica um Parquet incompleto.

## 2. Analisar os resultados

Execute `analisador_resultados_cobre.py`:

```powershell
python analisador_resultados_cobre.py
```

O analisador abre no navegador. Na barra lateral, selecione:

1. **Arquivo Parquet:** o `inflows_with_lags.parquet` gerado na etapa 1.
2. **`hydros.json`:** cadastro das usinas do mesmo estudo.
3. **`stages.json`:** calendário dos estágios do mesmo estudo.
4. **`inflow_history.parquet`:** histórico mensal do mesmo estudo, necessário para as análises históricas e de sequências negativas.

Na aba **Distribuição de Vazões**, escolha uma UHE no campo **Selecione a UHE** para ver os gráficos. A opção **Mostrar histórico mensal** controla apenas a comparação histórica; não liga nem desliga a análise de sequências negativas. Na aba **Relatório Estatístico**, escolha os filtros de cada seção para consultar as tabelas e, quando disponível, exportar os resultados.

Os arquivos podem continuar nas pastas originais; os botões apenas selecionam seus caminhos no computador. Não é necessário copiá-los para a pasta do programa.

## 3. Visualizar os registros do Parquet

Execute `leitor_parquet_vazoes_cobre.py`:

```powershell
python leitor_parquet_vazoes_cobre.py
```

Também é possível dar dois cliques em `ABRIR_LEITOR_COBRE.bat` no Windows. Na página aberta, clique em **Selecionar arquivo Parquet** e escolha `inflows_with_lags.parquet`. Use os filtros de cenário, estágio e usina para encontrar registros. É possível ordenar as colunas, avançar pelas páginas e mostrar somente vazões incrementais menores que `-0,01 m³/s`. O leitor apenas consulta o arquivo; não o altera.

## Se a página não abrir automaticamente

Espere a primeira instalação terminar. Depois, tente abrir manualmente no navegador:

- Analisador: <http://127.0.0.1:8503>
- Leitor de Parquet: <http://127.0.0.1:8502>

Se ainda houver erro, confira a mensagem mostrada na janela ou no terminal, se o Python está instalado e se os arquivos selecionados existem. O gerador deve terminar antes de o Parquet consolidado ser usado nos outros dois programas.
