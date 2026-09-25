"""Autocorrelação das somas anuais de vazões por UHE e cenário."""

from __future__ import annotations

from io import BytesIO
import math

from preparar_ambiente import garantir_dependencias


garantir_dependencias({
    "duckdb": "duckdb>=0.10",
    "pandas": "pandas>=2.0",
    "xlsxwriter": "XlsxWriter>=3.2",
})

import duckdb
import numpy as np
import pandas as pd
import xlsxwriter


VERSAO_AUTOCORRELACAO_ANUAL = 1
LAGS_ANUAIS = (1, 2)
COLUNAS_FONTE = {
    "scenario_id", "stage_id", "node_id", "hydro_id",
    "incremental_inflow_m3s",
}
COLUNAS_TABELA = ["UHE", "hydro_id", "Ano", "Lag 1", "Lag 2"]
COLUNAS_DIAGNOSTICO = [
    "UHE", "hydro_id", "Ano", "Lag", "Ano passado",
    "Cenários da UHE", "Somas completas atuais", "Somas completas passadas",
    "Pares válidos", "Média atual (soma m³/s)",
    "Média passada (soma m³/s)", "Desvio atual (soma m³/s)",
    "Desvio passado (soma m³/s)", "Covariância (soma m³/s)²",
    "Correlação", "Status", "Motivo",
]


def _anos_completos(
    calendario: dict[int, dict], estagios_presentes: set[int],
) -> tuple[int, ...]:
    if not calendario:
        raise ValueError("Selecione o stages.json para identificar os anos civis.")
    faltantes = sorted(estagios_presentes - set(calendario))
    if faltantes:
        raise ValueError(
            "Estágios do Parquet sem data no stages.json: "
            + ", ".join(map(str, faltantes[:20]))
        )
    meses: dict[int, set[int]] = {}
    contagens: dict[int, int] = {}
    for stage_id in estagios_presentes:
        inicio = calendario[stage_id]["inicio"]
        meses.setdefault(inicio.year, set()).add(inicio.month)
        contagens[inicio.year] = contagens.get(inicio.year, 0) + 1
    return tuple(sorted(
        ano for ano, meses_ano in meses.items()
        if meses_ano == set(range(1, 13)) and contagens[ano] == 12
    ))


def _carregar_grupos(
    caminho: str, calendario: dict[int, dict], hydro_id: int | None,
) -> tuple[pd.DataFrame, tuple[int, ...]]:
    conexao = duckdb.connect(database=":memory:")
    try:
        colunas = {
            linha[0] for linha in conexao.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [caminho]
            ).fetchall()
        }
        faltantes = sorted(COLUNAS_FONTE - colunas)
        if faltantes:
            raise ValueError(
                "O Parquet não possui as colunas da autocorrelação anual: "
                + ", ".join(faltantes)
            )
        estagios = conexao.execute(
            "SELECT DISTINCT stage_id FROM read_parquet(?)", [caminho]
        ).fetchall()
        if not estagios or any(linha[0] is None for linha in estagios):
            raise ValueError("O Parquet possui stage_id ausente ou nenhum estágio.")
        anos = _anos_completos(calendario, {int(linha[0]) for linha in estagios})
        mapa = pd.DataFrame([
            (int(stage_id), int(dados["inicio"].year))
            for stage_id, dados in calendario.items()
        ], columns=["stage_id", "ano"])
        conexao.register("calendario_anual", mapa)
        filtro = " WHERE p.hydro_id = ?" if hydro_id is not None else ""
        consulta = (
            "SELECT p.hydro_id, p.scenario_id, c.ano, "
            "COUNT(*) AS registros, "
            "COUNT(DISTINCT p.stage_id) AS estagios_distintos, "
            "COUNT(p.node_id) AS nos_preenchidos, "
            "COUNT(*) FILTER (WHERE isfinite(p.incremental_inflow_m3s)) AS validos, "
            "SUM(CASE WHEN isfinite(p.incremental_inflow_m3s) "
            "THEN p.incremental_inflow_m3s END) AS soma "
            "FROM read_parquet(?) AS p "
            "LEFT JOIN calendario_anual AS c ON p.stage_id = c.stage_id"
            + filtro + " GROUP BY p.hydro_id, p.scenario_id, c.ano"
        )
        parametros = [caminho] + ([int(hydro_id)] if hydro_id is not None else [])
        grupos = conexao.execute(consulta, parametros).df()
    finally:
        conexao.close()
    if grupos.empty:
        raise ValueError("Não há registros para a UHE selecionada no Parquet.")
    if grupos[["hydro_id", "scenario_id", "ano"]].isna().any().any():
        raise ValueError(
            "Há hydro_id, scenario_id ou stage_id ausente em registros do Parquet."
        )
    invalidos = grupos.loc[
        grupos["registros"].ne(grupos["estagios_distintos"])
        | grupos["registros"].ne(grupos["nos_preenchidos"])
    ]
    if not invalidos.empty:
        exemplo = invalidos.iloc[0]
        raise ValueError(
            "Chave hydro_id × scenario_id × stage_id duplicada ou node_id ausente "
            f"em hydro_id {int(exemplo.hydro_id)}, scenario_id "
            f"{int(exemplo.scenario_id)}, ano {int(exemplo.ano)}."
        )
    return grupos, anos


def _calcular_par(x: np.ndarray, y: np.ndarray) -> dict:
    """Momentos populacionais centralizados sobre a interseção dos cenários."""
    validos = np.isfinite(x) & np.isfinite(y)
    x = x[validos]
    y = y[validos]
    n = int(len(x))
    resultado = {
        "Pares válidos": n,
        "Média atual (soma m³/s)": None,
        "Média passada (soma m³/s)": None,
        "Desvio atual (soma m³/s)": None,
        "Desvio passado (soma m³/s)": None,
        "Covariância (soma m³/s)²": None,
        "Correlação": None,
        "Status": "indisponível",
        "Motivo": "Menos de dois pares anuais finitos.",
    }
    if n == 0:
        return resultado
    mx = float(np.mean(x))
    my = float(np.mean(y))
    dx = x - mx
    dy = y - my
    vx = float(np.mean(dx * dx))
    vy = float(np.mean(dy * dy))
    cov = float(np.mean(dx * dy))
    sx = math.sqrt(vx) if math.isfinite(vx) and vx >= 0 else math.nan
    sy = math.sqrt(vy) if math.isfinite(vy) and vy >= 0 else math.nan
    resultado.update({
        "Média atual (soma m³/s)": mx if math.isfinite(mx) else None,
        "Média passada (soma m³/s)": my if math.isfinite(my) else None,
        "Desvio atual (soma m³/s)": sx if math.isfinite(sx) else None,
        "Desvio passado (soma m³/s)": sy if math.isfinite(sy) else None,
        "Covariância (soma m³/s)²": cov if math.isfinite(cov) else None,
    })
    if n < 2:
        return resultado
    if not math.isfinite(sx) or not math.isfinite(sy):
        resultado["Motivo"] = "Desvio padrão numericamente indisponível."
        return resultado
    if sx == 0 or sy == 0 or np.min(x) == np.max(x) or np.min(y) == np.max(y):
        resultado["Motivo"] = "Soma anual constante entre os pares."
        return resultado
    if sx * math.sqrt(n) < 1e-13 * abs(mx) or sy * math.sqrt(n) < 1e-13 * abs(my):
        resultado["Motivo"] = "Somas quase constantes; correlação numericamente instável."
        return resultado
    rho = cov / (sx * sy)
    if not math.isfinite(rho) or abs(rho) > 1 + 1e-10:
        resultado["Motivo"] = "Coeficiente numérico inválido ou fora de [-1, 1]."
        return resultado
    resultado.update({
        "Correlação": max(-1.0, min(1.0, rho)),
        "Status": "calculado",
        "Motivo": "",
    })
    return resultado


def gerar_autocorrelacao_anual(
    caminho: str,
    nomes_por_id: dict[int, str],
    calendario: dict[int, dict],
    hydro_id: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna as duas colunas de lags e o diagnóstico da mesma conta."""
    grupos, anos = _carregar_grupos(caminho, calendario, hydro_id)
    usinas = sorted(int(valor) for valor in grupos["hydro_id"].unique())
    cenarios_por_usina = grupos.groupby("hydro_id")["scenario_id"].nunique().to_dict()
    anuais = grupos.loc[
        grupos["ano"].isin(anos)
        & grupos["registros"].eq(12)
        & grupos["estagios_distintos"].eq(12)
        & grupos["validos"].eq(12)
        & np.isfinite(grupos["soma"])
    , ["hydro_id", "scenario_id", "ano", "soma"]]
    linhas, diagnosticos = [], []
    for usina in usinas:
        nome = nomes_por_id.get(usina, f"Usina sem nome — hydro_id {usina}")
        subconjunto = anuais.loc[anuais["hydro_id"].eq(usina)]
        if subconjunto.empty:
            matriz = pd.DataFrame()
        else:
            matriz = subconjunto.pivot(
                index="scenario_id", columns="ano", values="soma"
            )
        totais = {
            ano: int(matriz[ano].notna().sum()) if ano in matriz else 0
            for ano in anos
        }
        for ano in anos:
            linha = {"UHE": nome, "hydro_id": usina, "Ano": ano}
            for lag in LAGS_ANUAIS:
                anterior = ano - lag
                comum = {
                    "UHE": nome,
                    "hydro_id": usina,
                    "Ano": ano,
                    "Lag": lag,
                    "Ano passado": anterior,
                    "Cenários da UHE": int(cenarios_por_usina[usina]),
                    "Somas completas atuais": totais[ano],
                    "Somas completas passadas": totais.get(anterior, 0),
                }
                if anterior not in anos:
                    calculo = _calcular_par(np.array([]), np.array([]))
                    calculo["Motivo"] = (
                        f"Ano civil {anterior} incompleto ou ausente no horizonte."
                    )
                elif totais[ano] == 0 or totais[anterior] == 0:
                    calculo = _calcular_par(np.array([]), np.array([]))
                else:
                    calculo = _calcular_par(
                        matriz[ano].to_numpy(dtype=float),
                        matriz[anterior].to_numpy(dtype=float),
                    )
                linha[f"Lag {lag}"] = calculo["Correlação"]
                diagnosticos.append({**comum, **calculo})
            linhas.append(linha)
    return (
        pd.DataFrame(linhas, columns=COLUNAS_TABELA),
        pd.DataFrame(diagnosticos, columns=COLUNAS_DIAGNOSTICO),
    )


def filtrar_autocorrelacao_anual(
    tabela: pd.DataFrame, diagnosticos: pd.DataFrame,
    usinas: list[int], anos: list[int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica os mesmos filtros às duas saídas sem remover colunas de lag."""
    visivel = tabela
    detalhe = diagnosticos
    if usinas:
        visivel = visivel.loc[visivel["hydro_id"].isin(usinas)]
        detalhe = detalhe.loc[detalhe["hydro_id"].isin(usinas)]
    if anos:
        visivel = visivel.loc[visivel["Ano"].isin(anos)]
        detalhe = detalhe.loc[detalhe["Ano"].isin(anos)]
    return visivel.copy(), detalhe.copy()


def exportar_autocorrelacao_anual_xlsx(
    tabela: pd.DataFrame, diagnosticos: pd.DataFrame,
) -> bytes:
    """Folha de leitura, números completos ocultos e memória de cálculo."""
    if len(tabela) >= 1_048_576 or len(diagnosticos) >= 1_048_576:
        raise ValueError("O relatório supera o limite de linhas de uma folha XLSX.")
    saida = BytesIO()
    livro = xlsxwriter.Workbook(saida, {"constant_memory": True})
    cabecalho = livro.add_format({
        "bold": True, "font_color": "#FFFFFF", "bg_color": "#078FA8",
        "border": 1, "border_color": "#B6E3EB", "align": "center",
    })
    texto = [
        livro.add_format({"border": 1, "border_color": "#B6E3EB", "bg_color": cor})
        for cor in ("#FFFFFF", "#E9F9FC")
    ]
    numero = [
        livro.add_format({
            "border": 1, "border_color": "#B6E3EB", "bg_color": cor,
            "num_format": "0.000000000000000",
        })
        for cor in ("#FFFFFF", "#E9F9FC")
    ]
    for titulo, numerica in (
        ("Autocorrelação anual", False), ("Valores completos", True),
    ):
        folha = livro.add_worksheet(titulo)
        folha.set_tab_color("#078FA8")
        if numerica:
            folha.hide()
        for coluna, nome in enumerate(COLUNAS_TABELA):
            largura = max(15, len(nome) + 2)
            if coluna == 0:
                largura = max(largura, max((len(str(v)) + 2 for v in tabela["UHE"]), default=15))
            folha.set_column(coluna, coluna, min(80, largura))
            folha.write(0, coluna, nome, cabecalho)
        folha.freeze_panes(1, 3)
        folha.autofilter(0, 0, len(tabela), len(COLUNAS_TABELA) - 1)
        for linha, registro in enumerate(tabela.itertuples(index=False, name=None), start=1):
            estilo = texto[linha % 2]
            estilo_num = numero[linha % 2]
            for coluna, valor in enumerate(registro):
                if pd.isna(valor):
                    folha.write_blank(linha, coluna, None, estilo)
                elif coluna >= 3 and not numerica:
                    folha.write_string(linha, coluna, f"{float(valor):.2f}", estilo)
                elif isinstance(valor, str):
                    folha.write_string(linha, coluna, valor, estilo)
                else:
                    folha.write_number(linha, coluna, float(valor), estilo_num)
    folha = livro.add_worksheet("Diagnóstico")
    folha.set_tab_color("#078FA8")
    for coluna, nome in enumerate(COLUNAS_DIAGNOSTICO):
        largura = max(23, len(nome) + 2)
        if coluna == 0:
            largura = max(largura, max((len(str(v)) + 2 for v in diagnosticos["UHE"]), default=23))
        folha.set_column(coluna, coluna, min(80, largura))
        folha.write(0, coluna, nome, cabecalho)
    folha.freeze_panes(1, 5)
    folha.autofilter(0, 0, len(diagnosticos), len(COLUNAS_DIAGNOSTICO) - 1)
    for linha, registro in enumerate(diagnosticos.itertuples(index=False, name=None), start=1):
        estilo = texto[linha % 2]
        estilo_num = numero[linha % 2]
        for coluna, valor in enumerate(registro):
            if pd.isna(valor):
                folha.write_blank(linha, coluna, None, estilo)
            elif isinstance(valor, str):
                folha.write_string(linha, coluna, valor, estilo)
            else:
                folha.write_number(linha, coluna, float(valor), estilo_num)
    livro.close()
    return saida.getvalue()
