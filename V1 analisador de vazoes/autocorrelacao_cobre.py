"""Correlação entre vazões atuais e lags do mesmo cenário, por UHE e estágio."""

from __future__ import annotations

from datetime import date
from io import BytesIO
import math

from preparar_ambiente import garantir_dependencias

garantir_dependencias({
    "duckdb": "duckdb>=0.10", "pandas": "pandas>=2.0",
    "xlsxwriter": "XlsxWriter>=3.2",
})

import duckdb
import numpy as np
import pandas as pd
import xlsxwriter


VERSAO_FORMULA = 2
CORES_LAGS = {
    1: "#E53935", 2: "#F57C00", 3: "#FDD835",
    4: "#43A047", 5: "#1E88E5", 6: "#8E24AA",
}
COLUNAS_RESULTADO = ["UHE", "hydro_id", "stage_id"] + [f"Lag {k}" for k in range(7)]
COLUNAS_FONTE = ["scenario_id", "stage_id", "node_id", "hydro_id", "incremental_inflow_m3s"] + [f"lag_{k}_m3s" for k in range(1, 7)]


def _mes_anterior(inicio: date, quantidade: int) -> date:
    indice = inicio.year * 12 + inicio.month - 1 - quantidade
    return date(indice // 12, indice % 12 + 1, 1)


def _numero(valor) -> float | None:
    if valor is None or pd.isna(valor):
        return None
    resultado = float(valor)
    return resultado if math.isfinite(resultado) else None


def _consulta_agregada(caminho: str, hydro_id: int | None) -> pd.DataFrame:
    """DuckDB usa acumuladores online centralizados para CORR/COVAR/STDDEV."""
    conexao = duckdb.connect(database=":memory:")
    try:
        colunas = {linha[0] for linha in conexao.execute("DESCRIBE SELECT * FROM read_parquet(?)", [caminho]).fetchall()}
        faltantes = sorted(set(COLUNAS_FONTE) - colunas)
        if faltantes:
            raise ValueError("O Parquet não possui as colunas de autocorrelação: " + ", ".join(faltantes))
        expressoes = [
            "COUNT(*) AS n_esperado",
            "COUNT(DISTINCT scenario_id) AS cenarios_distintos",
            "COUNT(node_id) AS nos_preenchidos",
        ]
        for lag in range(7):
            x = "incremental_inflow_m3s"
            y = x if lag == 0 else f"lag_{lag}_m3s"
            mascara = f"isfinite({x}) AND isfinite({y})"
            sufixo = f"l{lag}"
            expressoes.extend([
                f"COUNT(*) FILTER (WHERE {mascara}) AS n_{sufixo}",
                f"AVG({x}) FILTER (WHERE {mascara}) AS mx_{sufixo}",
                f"AVG({y}) FILTER (WHERE {mascara}) AS my_{sufixo}",
                f"STDDEV_POP({x}) FILTER (WHERE {mascara}) AS sx_{sufixo}",
                f"STDDEV_POP({y}) FILTER (WHERE {mascara}) AS sy_{sufixo}",
                f"COVAR_POP({x}, {y}) FILTER (WHERE {mascara}) AS cov_{sufixo}",
                f"CORR({x}, {y}) FILTER (WHERE {mascara}) AS rho_{sufixo}",
                f"MIN({x}) FILTER (WHERE {mascara}) AS minx_{sufixo}",
                f"MAX({x}) FILTER (WHERE {mascara}) AS maxx_{sufixo}",
                f"MIN({y}) FILTER (WHERE {mascara}) AS miny_{sufixo}",
                f"MAX({y}) FILTER (WHERE {mascara}) AS maxy_{sufixo}",
            ])
        filtro = " WHERE hydro_id = ?" if hydro_id is not None else ""
        consulta = (
            "SELECT hydro_id, stage_id, " + ", ".join(expressoes)
            + " FROM read_parquet(?)" + filtro + " GROUP BY hydro_id, stage_id"
        )
        parametros = [caminho] + ([int(hydro_id)] if hydro_id is not None else [])
        return conexao.execute(consulta, parametros).df()
    finally:
        conexao.close()


def _auditar_lags(caminho: str, calendario: dict[int, dict], hydro_id: int | None) -> dict[tuple[int, int, int], int]:
    """Confere cada lag já dentro do horizonte contra o estágio anterior do cenário."""
    conexao = duckdb.connect(database=":memory:")
    try:
        mapa = pd.DataFrame(
            [(int(stage_id), int(registro["ordem"])) for stage_id, registro in calendario.items()],
            columns=["stage_id", "ordem"],
        )
        conexao.register("calendario_autocorrelacao", mapa)
        anteriores = ", ".join(
            f"LAG(incremental_inflow_m3s, {k}) OVER "
            f"(PARTITION BY hydro_id, scenario_id ORDER BY ordem) AS esperado_{k}, "
            f"LAG(ordem, {k}) OVER "
            f"(PARTITION BY hydro_id, scenario_id ORDER BY ordem) AS ordem_anterior_{k}"
            for k in range(1, 7)
        )
        contagens = ", ".join(
            f"COUNT(*) FILTER (WHERE ordem >= {k} AND ("
            f"ordem_anterior_{k} IS NULL OR ordem - ordem_anterior_{k} <> {k} OR "
            f"isfinite(esperado_{k}) AND isfinite(lag_{k}_m3s) AND "
            f"abs(esperado_{k}-lag_{k}_m3s)>1e-8*greatest(1,abs(esperado_{k}))"
            f")) AS divergencias_{k}"
            for k in range(1, 7)
        )
        filtro = "WHERE p.hydro_id = ?" if hydro_id is not None else ""
        consulta = (
            "WITH ordenado AS (SELECT p.hydro_id, p.stage_id, c.ordem, "
            + ", ".join(f"p.lag_{k}_m3s" for k in range(1, 7)) + ", "
            + anteriores
            + " FROM read_parquet(?) p JOIN calendario_autocorrelacao c ON p.stage_id=c.stage_id "
            + filtro + ") SELECT hydro_id, stage_id, " + contagens
            + " FROM ordenado GROUP BY hydro_id, stage_id"
        )
        parametros = [caminho] + ([int(hydro_id)] if hydro_id is not None else [])
        quadro = conexao.execute(consulta, parametros).df()
        return {
            (int(linha.hydro_id), int(linha.stage_id), k): int(getattr(linha, f"divergencias_{k}"))
            for linha in quadro.itertuples(index=False) for k in range(1, 7)
            if int(getattr(linha, f"divergencias_{k}")) > 0
        }
    finally:
        conexao.close()


def _avaliar_coeficiente(registro, lag: int) -> tuple[float | None, str, str]:
    suf = f"l{lag}"
    n = int(getattr(registro, f"n_{suf}"))
    if n < 2:
        return None, "indisponível", "Menos de dois pares finitos."
    # Cada cenário/estágio deve ter uma única linha com nó preenchido.
    # O identificador do nó pode variar entre estágios e entre cenários.
    if (int(registro.n_esperado) != int(registro.cenarios_distintos)
            or int(registro.nos_preenchidos) != int(registro.n_esperado)):
        return None, "indisponível", "Chaves de cenário duplicadas ou identificadores ausentes."
    sx, sy = _numero(getattr(registro, f"sx_{suf}")), _numero(getattr(registro, f"sy_{suf}"))
    if sx is None or sy is None:
        return None, "indisponível", "Desvio padrão indisponível."
    if sx == 0 or sy == 0 or getattr(registro, f"minx_{suf}") == getattr(registro, f"maxx_{suf}") or getattr(registro, f"miny_{suf}") == getattr(registro, f"maxy_{suf}"):
        return None, "indisponível", "Vazão atual ou passada constante entre os cenários."
    mx, my = _numero(getattr(registro, f"mx_{suf}")), _numero(getattr(registro, f"my_{suf}"))
    if (mx is not None and sx * math.sqrt(n) < 1e-13 * abs(mx)) or (my is not None and sy * math.sqrt(n) < 1e-13 * abs(my)):
        return None, "indisponível", "Valores quase constantes; correlação numericamente instável."
    rho = _numero(getattr(registro, f"rho_{suf}"))
    if rho is None:
        return None, "indisponível", "Correlação numérica indisponível."
    if abs(rho) > 1 + 1e-10:
        return None, "indisponível", "Coeficiente fora de [-1, 1]; verificar os dados."
    return max(-1.0, min(1.0, rho)), "calculado", ""


def gerar_autocorrelacao(
    caminho: str,
    nomes_por_id: dict[int, str],
    calendario: dict[int, dict],
    hydro_id: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna tabela principal e diagnóstico de cada lag, com a mesma fórmula."""
    if not calendario:
        raise ValueError("Selecione o stages.json para localizar os períodos dos lags.")
    agregada = _consulta_agregada(caminho, hydro_id)
    if agregada.empty:
        raise ValueError("A UHE selecionada não possui registros no Parquet.")
    ordem = {int(chave): int(valor["ordem"]) for chave, valor in calendario.items()}
    ausentes = set(int(v) for v in agregada.stage_id.unique()) - set(ordem)
    if ausentes:
        raise ValueError("Estágios sem data no stages.json: " + ", ".join(map(str, sorted(ausentes))))
    agregada["ordem"] = agregada.stage_id.map(ordem)
    agregada = agregada.sort_values(["hydro_id", "ordem"])
    divergencias = _auditar_lags(caminho, calendario, hydro_id)
    resultados, diagnosticos = [], []
    for registro in agregada.itertuples(index=False):
        usina = nomes_por_id.get(int(registro.hydro_id), f"Usina sem nome — hydro_id {registro.hydro_id}")
        inicio = calendario[int(registro.stage_id)]["inicio"]
        resultado = {"UHE": usina, "hydro_id": int(registro.hydro_id), "stage_id": int(registro.stage_id)}
        for lag in range(7):
            rho, status, motivo = _avaliar_coeficiente(registro, lag)
            quantidade_divergente = divergencias.get((int(registro.hydro_id), int(registro.stage_id), lag), 0)
            if quantidade_divergente:
                rho, status = None, "indisponível"
                motivo = f"{quantidade_divergente} lags exportados divergem da vazão anterior do mesmo cenário."
            resultado[f"Lag {lag}"] = rho
            passado = _mes_anterior(inicio, lag)
            fonte = "vazão atual" if lag == 0 else ("horizonte simulado" if int(registro.ordem) >= lag else "inicialização anterior ao estudo")
            suf = f"l{lag}"
            diagnosticos.append({
                "UHE": usina, "hydro_id": int(registro.hydro_id),
                "stage_id": int(registro.stage_id), "período atual": inicio.strftime("%m/%Y"),
                "lag": lag, "período passado": passado.strftime("%m/%Y"), "origem": fonte,
                "pares esperados": int(registro.n_esperado), "pares válidos": int(getattr(registro, f"n_{suf}")),
                "média atual": _numero(getattr(registro, f"mx_{suf}")),
                "média passada": _numero(getattr(registro, f"my_{suf}")),
                "desvio atual": _numero(getattr(registro, f"sx_{suf}")),
                "desvio passado": _numero(getattr(registro, f"sy_{suf}")),
                "covariância": _numero(getattr(registro, f"cov_{suf}")),
                "coeficiente": rho, "status": status, "motivo": motivo,
            })
        resultados.append(resultado)
    return pd.DataFrame(resultados, columns=COLUNAS_RESULTADO), pd.DataFrame(diagnosticos)


def filtrar_autocorrelacao(tabela: pd.DataFrame, diagnosticos: pd.DataFrame,
                           usinas: list[int], estagios: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica os mesmos filtros às duas saídas, preservando a ordem original."""
    mascara = pd.Series(True, index=tabela.index)
    if usinas:
        mascara &= tabela.hydro_id.isin(usinas)
    if estagios:
        mascara &= tabela.stage_id.isin(estagios)
    exibida = tabela.loc[mascara].copy()
    diagnostico = diagnosticos
    if usinas:
        diagnostico = diagnostico.loc[diagnostico.hydro_id.isin(usinas)]
    if estagios:
        diagnostico = diagnostico.loc[diagnostico.stage_id.isin(estagios)]
    return exibida, diagnostico.copy()


def exportar_autocorrelacao_xlsx(tabela: pd.DataFrame, diagnosticos: pd.DataFrame) -> bytes:
    """Folha visível textual com ponto decimal; auxiliares numéricas completas."""
    saida = BytesIO()
    livro = xlsxwriter.Workbook(saida, {"constant_memory": True})
    cabecalho = livro.add_format({
        "bold": True, "font_color": "#FFFFFF", "bg_color": "#078FA8",
        "border": 1, "border_color": "#B6E3EB", "align": "center",
    })
    linhas = [
        livro.add_format({"border": 1, "border_color": "#B6E3EB", "bg_color": fundo})
        for fundo in ("#FFFFFF", "#E9F9FC")
    ]
    numeros = [
        livro.add_format({
            "border": 1, "border_color": "#B6E3EB", "bg_color": fundo,
            "num_format": "0.000000000000000",
        })
        for fundo in ("#FFFFFF", "#E9F9FC")
    ]

    def valor_excel(valor, formatado: bool, pos: int):
        if pd.isna(valor):
            return None
        if formatado and pos >= 4:
            return f"{float(valor):.2f}"
        if isinstance(valor, np.integer):
            return int(valor)
        if isinstance(valor, np.floating):
            return float(valor)
        return valor

    for titulo, quadro, formatado in [
        ("Autocorrelação", tabela, True),
        ("Valores completos", tabela, False),
        ("Diagnóstico", diagnosticos, False),
    ]:
        planilha = livro.add_worksheet(titulo)
        if titulo == "Valores completos":
            planilha.hide()
        larguras = [len(str(coluna)) + 3 for coluna in quadro.columns]
        for linha in quadro.itertuples(index=False, name=None):
            for pos, valor in enumerate(linha):
                escrito = valor_excel(valor, formatado, pos + 1)
                larguras[pos] = max(larguras[pos], len(str(escrito or "")) + 2)
        for pos, largura in enumerate(larguras):
            planilha.set_column(pos, pos, min(max(largura, 12), 255))
            planilha.write(0, pos, str(quadro.columns[pos]), cabecalho)
        planilha.freeze_panes(1, 3)
        planilha.autofilter(0, 0, max(0, len(quadro)), len(quadro.columns) - 1)
        planilha.set_tab_color("#078FA8")
        for indice, linha in enumerate(quadro.itertuples(index=False, name=None), start=1):
            alternancia = indice % 2
            for pos, valor in enumerate(linha):
                escrito = valor_excel(valor, formatado, pos + 1)
                estilo = numeros[alternancia] if isinstance(escrito, float) else linhas[alternancia]
                planilha.write(indice, pos, escrito, estilo)
    livro.close()
    return saida.getvalue()
