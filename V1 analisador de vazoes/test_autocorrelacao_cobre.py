"""Casos controlados para a fórmula e a auditoria dos lags."""

from datetime import date
from pathlib import Path
import tempfile
import unittest

import duckdb
import pandas as pd

from autocorrelacao_cobre import gerar_autocorrelacao


CALENDARIO = {
    0: {"inicio": date(2026, 1, 1), "ordem": 0},
    1: {"inicio": date(2026, 2, 1), "ordem": 1},
    2: {"inicio": date(2026, 3, 1), "ordem": 2},
}


def criar_dados() -> pd.DataFrame:
    series = {0: [1, 2, 3, 4], 1: [4, 3, 2, 1], 2: [1, 2, 3, 4]}
    linhas = []
    for stage_id in range(3):
        for indice in range(4):
            linha = {
                "hydro_id": 10, "node_id": stage_id, "stage_id": stage_id,
                "scenario_id": indice + 1,
                "incremental_inflow_m3s": float(series[stage_id][indice]),
            }
            for lag in range(1, 7):
                anterior = stage_id - lag
                linha[f"lag_{lag}_m3s"] = (
                    float(series[anterior][indice]) if anterior >= 0
                    else float(100 + anterior)
                )
            linhas.append(linha)
    return pd.DataFrame(linhas)


def calcular_fixture(dados: pd.DataFrame):
    with tempfile.TemporaryDirectory() as pasta:
        caminho = Path(pasta) / "fixture.parquet"
        conexao = duckdb.connect()
        try:
            conexao.register("fixture", dados)
            conexao.execute(f"COPY fixture TO '{caminho.as_posix()}' (FORMAT PARQUET)")
        finally:
            conexao.close()
        return gerar_autocorrelacao(str(caminho), {10: "Teste"}, CALENDARIO)


class AutocorrelacaoTeste(unittest.TestCase):
    def test_nos_distintos_por_cenario_preservam_pareamento(self):
        dados = criar_dados()
        dados["node_id"] = dados.stage_id * 100 + dados.scenario_id
        tabela, diagnostico = calcular_fixture(dados)
        self.assertAlmostEqual(tabela.loc[tabela.stage_id.eq(1), "Lag 1"].iloc[0], -1)
        self.assertTrue(diagnostico["pares esperados"].eq(4).all())
        self.assertTrue(diagnostico["pares válidos"].eq(4).all())

    def test_no_ausente_permanece_invalido(self):
        dados = criar_dados()
        dados["node_id"] = dados.node_id.astype(float)
        dados.loc[dados.stage_id.eq(1) & dados.scenario_id.eq(1), "node_id"] = None
        tabela, _ = calcular_fixture(dados)
        self.assertTrue(pd.isna(tabela.loc[tabela.stage_id.eq(1), "Lag 1"].iloc[0]))

    def test_correlacoes_e_lags_constantes(self):
        tabela, diagnostico = calcular_fixture(criar_dados())
        self.assertEqual(len(tabela), 3)
        self.assertEqual(len(diagnostico), 21)
        self.assertAlmostEqual(tabela.loc[tabela.stage_id.eq(1), "Lag 1"].iloc[0], -1)
        self.assertAlmostEqual(tabela.loc[tabela.stage_id.eq(2), "Lag 2"].iloc[0], 1)
        self.assertTrue(all(abs(valor - 1) < 1e-12 for valor in tabela["Lag 0"]))
        self.assertTrue(pd.isna(tabela.loc[tabela.stage_id.eq(0), "Lag 1"].iloc[0]))
        self.assertIn("constante", diagnostico.loc[
            diagnostico.stage_id.eq(0) & diagnostico.lag.eq(1), "motivo"
        ].iloc[0])
        self.assertEqual(diagnostico.loc[
            diagnostico.stage_id.eq(0) & diagnostico.lag.eq(1), "período passado"
        ].iloc[0], "12/2025")

    def test_par_faltante_reduz_amostra_sem_inventar_valor(self):
        dados = criar_dados()
        dados.loc[dados.stage_id.eq(2) & dados.scenario_id.eq(4), "lag_2_m3s"] = None
        tabela, diagnostico = calcular_fixture(dados)
        self.assertAlmostEqual(tabela.loc[tabela.stage_id.eq(2), "Lag 2"].iloc[0], 1)
        self.assertEqual(diagnostico.loc[
            diagnostico.stage_id.eq(2) & diagnostico.lag.eq(2), "pares válidos"
        ].iloc[0], 3)

    def test_covariancia_zero_continua_resultado_definido(self):
        dados = criar_dados()
        atuais = [1.0, -1.0, -1.0, 1.0]
        for scenario_id, atual in enumerate(atuais, start=1):
            dados.loc[
                dados.stage_id.eq(1) & dados.scenario_id.eq(scenario_id),
                "incremental_inflow_m3s",
            ] = atual
            dados.loc[
                dados.stage_id.eq(2) & dados.scenario_id.eq(scenario_id),
                "lag_1_m3s",
            ] = atual
        tabela, diagnostico = calcular_fixture(dados)
        self.assertAlmostEqual(tabela.loc[tabela.stage_id.eq(1), "Lag 1"].iloc[0], 0)
        self.assertEqual(diagnostico.loc[
            diagnostico.stage_id.eq(1) & diagnostico.lag.eq(1), "status"
        ].iloc[0], "calculado")

    def test_lag_divergente_invalida_apenas_resultado_afetado(self):
        dados = criar_dados()
        dados.loc[dados.stage_id.eq(2) & dados.scenario_id.eq(1), "lag_1_m3s"] = 999
        tabela, diagnostico = calcular_fixture(dados)
        linha = tabela.loc[tabela.stage_id.eq(2)].iloc[0]
        self.assertTrue(pd.isna(linha["Lag 1"]))
        self.assertAlmostEqual(linha["Lag 2"], 1)
        self.assertIn("divergem", diagnostico.loc[
            diagnostico.stage_id.eq(2) & diagnostico.lag.eq(1), "motivo"
        ].iloc[0])

    def test_cenario_duplicado_nao_e_agregado(self):
        dados = criar_dados()
        dados = pd.concat([dados, dados.iloc[[8]]], ignore_index=True)
        tabela, _ = calcular_fixture(dados)
        linha = tabela.loc[tabela.stage_id.eq(2)].iloc[0]
        self.assertTrue(pd.isna(linha["Lag 0"]))


if __name__ == "__main__":
    unittest.main()
