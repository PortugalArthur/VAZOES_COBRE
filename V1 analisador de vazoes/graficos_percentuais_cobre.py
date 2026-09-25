"""Dois gráficos das fatias inferiores com as estatísticas do relatório."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from relatorio_estatistico_cobre import JANELAS, MESES


def _cor(historico: bool) -> str:
    """Mantém as cores dos gráficos gerais: roxo histórico e ciano cenários."""
    return "#8b5cf6" if historico else "#09b6cb"


def _rgba(cor: str, alfa: float) -> str:
    canais = [int(cor[indice:indice + 2], 16) for indice in (1, 3, 5)]
    return f"rgba({canais[0]},{canais[1]},{canais[2]},{alfa})"


def _limites_y(valores: list[float]) -> list[float]:
    minimo, maximo = min(valores), max(valores)
    amplitude = max(maximo - minimo, abs(minimo), abs(maximo), 1.0)
    return [min(minimo, 0.0) - 0.05 * amplitude, max(maximo, 0.0) + 0.05 * amplitude]


def criar_graficos_percentuais(
    resumo: pd.DataFrame,
    percentuais: list[int],
    estagios: list[int],
    meses_por_estagio: dict[int, int] | None,
    rotulo_usina: str,
    incluir_historico: bool,
    janela_analise: str = JANELAS[0],
) -> tuple[go.Figure, go.Figure]:
    """Usa os mesmos quartis, hastes, média e sigma da segunda tabela."""
    if "janela" in resumo.columns:
        resumo = resumo.loc[resumo["janela"].eq(janela_analise)]
    analise_somas = janela_analise != JANELAS[0]
    rotulo_valor = "Soma" if analise_somas else "Vazão"
    titulo_box = "Boxplot das menores somas" if analise_somas else "Boxplot dos menores valores"
    titulo_linhas = (
        "Média e desvio padrão das menores somas"
        if analise_somas else "Média e desvio padrão dos menores valores"
    )
    eixo_y = "Soma das vazões na janela (m³/s)" if analise_somas else "Vazão incremental (m³/s)"
    eixo_x = "Estágio terminal (stage_id)" if analise_somas else "Estágio (stage_id)"
    detalhe_janela = f"Janela: {janela_analise}<br>" if analise_somas else ""
    rotulo_estagio_hover = "Estágio terminal" if analise_somas else "Estágio"
    mapa = {}
    for registro in resumo.itertuples(index=False):
        grupo = int(registro.mes_num) if registro.fonte == "Histórico" else int(registro.stage_id)
        mapa[(registro.fonte, grupo, int(registro.percentual))] = registro

    series = []
    for percentual in sorted(percentuais):
        for fonte in ("Cenários", "Histórico"):
            if fonte == "Histórico" and not incluir_historico:
                continue
            registros = []
            for stage_id in estagios:
                mes = meses_por_estagio[stage_id] if fonte == "Histórico" else None
                grupo = mes if mes is not None else stage_id
                registros.append(mapa.get((fonte, grupo, percentual)))
            if any(registro is not None and registro.n_selecionados > 0 for registro in registros):
                series.append((fonte, percentual, registros))

    caixas, linhas = go.Figure(), go.Figure()
    if not series:
        return caixas, linhas
    largura = 0.78 / len(series)
    valores_y = []
    posicoes = {stage_id: indice for indice, stage_id in enumerate(estagios)}
    hover_caixa = (
        "UHE: %{customdata[0]}<br>Fonte: %{customdata[1]}<br>"
        "Fatia: %{customdata[2]}<br>" + detalhe_janela
        + f"{rotulo_estagio_hover}: %{{customdata[3]}}<br>"
        "Mês: %{customdata[4]}<br>Válidos: %{customdata[5]}<br>"
        "Selecionados: %{customdata[6]}<br>Q1: %{customdata[7]:.6g}<br>"
        "Mediana: %{customdata[8]:.6g}<br>Q3: %{customdata[9]:.6g}<br>"
        "Mínimo: %{customdata[10]:.6g}<br>Máximo: %{customdata[11]:.6g}<br>"
        "Hastes: %{customdata[12]:.6g} a %{customdata[13]:.6g} m³/s"
        "<extra></extra>"
    )
    hover_linha = (
        "UHE: %{customdata[0]}<br>Fonte: %{customdata[1]}<br>"
        "Fatia: %{customdata[2]}<br>" + detalhe_janela
        + f"{rotulo_estagio_hover}: %{{customdata[3]}}<br>"
        "Mês: %{customdata[4]}<br>Válidos: %{customdata[5]}<br>"
        "Selecionados: %{customdata[6]}<br>Média: %{customdata[7]:.6g} m³/s"
        "<br>σ populacional: %{customdata[8]:.6g} m³/s<extra></extra>"
    )
    for indice_serie, (fonte, percentual, registros) in enumerate(series):
        cor = _cor(fonte == "Histórico")
        nome = f"{fonte} p{percentual}%"
        grupo_legenda = f"{fonte}-{percentual}"
        deslocamento = -0.39 + largura * (indice_serie + 0.5)
        pontos_caixa, q1, medianas, q3, hastes_inferiores, hastes_superiores = [], [], [], [], [], []
        detalhes_caixa = []
        pontos_outliers_x, pontos_outliers_y, detalhes_outliers = [], [], []
        pontos_colapsados_x, pontos_colapsados_y, detalhes_colapsados = [], [], []
        medias, superiores, inferiores, detalhes_linha = [], [], [], []

        for stage_id, registro in zip(estagios, registros):
            mes_nome = (
                MESES[meses_por_estagio[stage_id]]
                if fonte == "Histórico" and meses_por_estagio else "—"
            )
            if registro is None or registro.n_selecionados == 0:
                medias.append(None)
                superiores.append(None)
                inferiores.append(None)
                detalhes_linha.append([rotulo_usina, fonte, f"p{percentual}%", stage_id, mes_nome, 0, 0, None, None])
                continue
            posicao = posicoes[stage_id] + deslocamento
            pontos_caixa.append(posicao)
            q1.append(float(registro.q1))
            medianas.append(float(registro.mediana))
            q3.append(float(registro.q3))
            hastes_inferiores.append(float(registro.haste_inferior))
            hastes_superiores.append(float(registro.haste_superior))
            detalhes = [
                rotulo_usina, fonte, f"p{percentual}%", stage_id, mes_nome,
                int(registro.n_validos), int(registro.n_selecionados),
                float(registro.q1), float(registro.mediana), float(registro.q3),
                float(registro.minimo), float(registro.maximo),
                float(registro.haste_inferior), float(registro.haste_superior),
                float(registro.media), float(registro.desvio),
            ]
            detalhes_caixa.append(detalhes)
            if registro.q1 == registro.q3:
                pontos_colapsados_x.append(posicao)
                pontos_colapsados_y.append(float(registro.mediana))
                detalhes_colapsados.append(detalhes)
            for outlier in registro.outliers:
                pontos_outliers_x.append(posicao)
                pontos_outliers_y.append(float(outlier))
                detalhes_outliers.append(detalhes)
            medias.append(float(registro.media))
            superiores.append(float(registro.media + registro.desvio))
            inferiores.append(float(registro.media - registro.desvio))
            detalhes_linha.append([
                rotulo_usina, fonte, f"p{percentual}%", stage_id, mes_nome,
                int(registro.n_validos), int(registro.n_selecionados),
                float(registro.media), float(registro.desvio),
            ])
            valores_y.extend((
                float(registro.minimo), float(registro.maximo),
                float(registro.media - registro.desvio),
                float(registro.media + registro.desvio),
            ))

        caixas.add_trace(go.Box(
            x=pontos_caixa, q1=q1, median=medianas, q3=q3,
            lowerfence=hastes_inferiores, upperfence=hastes_superiores,
            name=nome, legendgroup=grupo_legenda, width=largura * 0.88,
            boxpoints=False, fillcolor=_rgba(cor, 0.20),
            line=dict(color=cor, width=1.3), customdata=detalhes_caixa,
            hoveron="boxes", hovertemplate=hover_caixa,
        ))
        if pontos_outliers_y:
            caixas.add_trace(go.Scatter(
                x=pontos_outliers_x, y=pontos_outliers_y, mode="markers",
                name=f"Outliers — {nome}", legendgroup=grupo_legenda,
                showlegend=False, customdata=detalhes_outliers,
                marker=dict(color=cor, size=4, opacity=0.8),
                hovertemplate=(
                    "UHE: %{customdata[0]}<br>Fonte: %{customdata[1]}<br>"
                    "Fatia: %{customdata[2]}<br>" + detalhe_janela
                    + f"{rotulo_estagio_hover}: %{{customdata[3]}}<br>"
                    "Mês: %{customdata[4]}<br>Válidos: %{customdata[5]}<br>"
                    f"Selecionados: %{{customdata[6]}}<br>{rotulo_valor}: %{{y:.6g}} m³/s"
                    "<extra></extra>"
                ),
            ))
        if pontos_colapsados_x:
            caixas.add_trace(go.Scatter(
                x=pontos_colapsados_x, y=pontos_colapsados_y, mode="markers",
                name=f"Q1 = Q3 — {nome}", legendgroup=grupo_legenda,
                showlegend=False, customdata=detalhes_colapsados,
                marker=dict(
                    symbol="line-ew", size=13, color=cor,
                    line=dict(color=cor, width=3),
                ),
                hovertemplate=(
                    "UHE: %{customdata[0]}<br>Fonte: %{customdata[1]}<br>"
                    "Fatia: %{customdata[2]}<br>" + detalhe_janela
                    + f"{rotulo_estagio_hover}: %{{customdata[3]}}<br>"
                    "Mês: %{customdata[4]}<br>Válidos: %{customdata[5]}<br>"
                    "Selecionados: %{customdata[6]}<br>Q1 = mediana = Q3: %{y:.6g} m³/s"
                    "<br>Caixa com altura zero<extra></extra>"
                ),
            ))

        borda_faixa = dict(color=_rgba(cor, 0.28), width=0.6)
        linhas.add_trace(go.Scatter(
            x=estagios, y=superiores, mode="lines", name=f"+1σ — {nome}",
            legendgroup=grupo_legenda, showlegend=False,
            line=borda_faixa, hoverinfo="skip", connectgaps=False,
        ))
        linhas.add_trace(go.Scatter(
            x=estagios, y=inferiores, mode="lines", name=f"Faixa ±1σ — {nome}",
            legendgroup=grupo_legenda, showlegend=True,
            line=borda_faixa, fill="tonexty",
            fillcolor=_rgba(cor, 0.10 if fonte == "Histórico" else 0.08),
            hoverinfo="skip", connectgaps=False,
        ))
        linhas.add_trace(go.Scatter(
            x=estagios, y=medias, mode="lines", name=f"Média — {nome}",
            legendgroup=grupo_legenda, customdata=detalhes_linha,
            line=dict(color=cor, width=2.5, dash="dash" if fonte == "Histórico" else "solid"),
            connectgaps=False, hovertemplate=hover_linha,
        ))

    faixa_y = _limites_y(valores_y)
    passo = max(1, len(estagios) // 12)
    indices_rotulos = list(range(0, len(estagios), passo))
    rotulos = [
        f"{estagios[indice]}<br>{MESES[meses_por_estagio[estagios[indice]]]}"
        if meses_por_estagio else str(estagios[indice])
        for indice in indices_rotulos
    ]
    muitos_grupos = len(series) > 4
    altura = 520 if not muitos_grupos else 680
    configuracao_legenda = (
        dict(orientation="v", y=1, x=1.02, groupclick="togglegroup")
        if muitos_grupos else
        dict(orientation="h", y=1.02, x=0, groupclick="togglegroup")
    )
    margem = dict(l=45, r=180 if muitos_grupos else 20, t=85, b=65)
    limite_caixas = (
        [-0.55, min(len(estagios) - 0.45, 11.55)]
        if muitos_grupos else [-0.55, len(estagios) - 0.45]
    )
    caixas.add_hline(y=0, line_dash="dot", line_color="#a8b3bc", line_width=1, layer="below")
    caixas.update_xaxes(
        title_text=f"{eixo_x} e mês", tickmode="array",
        tickvals=indices_rotulos, ticktext=rotulos,
        range=limite_caixas, rangeslider_visible=muitos_grupos,
    )
    caixas.update_yaxes(title_text=eixo_y, range=faixa_y, zeroline=False)
    caixas.update_layout(
        title=f"{titulo_box} — {rotulo_usina}",
        height=altura, boxmode="overlay", hovermode="closest",
        margin=margem, legend=configuracao_legenda,
    )
    linhas.add_hline(y=0, line_dash="dot", line_color="#a8b3bc", line_width=1)
    linhas.update_xaxes(
        title_text=eixo_x, tickmode="array",
        tickvals=[estagios[indice] for indice in indices_rotulos], ticktext=rotulos,
        range=(
            [estagios[0] - 0.5, estagios[min(len(estagios) - 1, 11)] + 0.5]
            if muitos_grupos else None
        ),
        rangeslider_visible=muitos_grupos,
    )
    linhas.update_yaxes(title_text=eixo_y, range=faixa_y, zeroline=False)
    linhas.update_layout(
        title=f"{titulo_linhas} — {rotulo_usina}",
        height=altura, hovermode="x unified",
        margin=margem, legend=configuracao_legenda,
    )
    return caixas, linhas
