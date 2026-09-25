"""Extrai evidências de um arquivo Parquet do COBRE para um Excel.

Como usar:
1. Execute este arquivo com Python.
2. Selecione o data.parquet na janela que abrir.
3. Informe scenario_id, stage_id e hydro_id (o caso 0/19/86 já vem preenchido).
4. Escolha onde salvar o .xlsx.
"""

from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from preparar_ambiente import garantir_dependencias

garantir_dependencias(
    {
        "pandas": "pandas>=2.0",
        "pyarrow": "pyarrow>=14",
        "openpyxl": "openpyxl>=3.1",
    }
)

import pandas as pd


def pedir_inteiro(titulo: str, mensagem: str, valor_inicial: int) -> int | None:
    return simpledialog.askinteger(
        titulo,
        mensagem,
        initialvalue=valor_inicial,
        minvalue=0,
    )


def main() -> None:
    root = tk.Tk()
    root.withdraw()

    parquet_path = filedialog.askopenfilename(
        title="Selecione o arquivo Parquet do COBRE",
        filetypes=[("Arquivos Parquet", "*.parquet"), ("Todos os arquivos", "*.*")],
    )
    if not parquet_path:
        return

    scenario_id = pedir_inteiro("Filtro", "scenario_id:", 0)
    if scenario_id is None:
        return
    stage_id = pedir_inteiro("Filtro", "stage_id:", 19)
    if stage_id is None:
        return
    hydro_id = pedir_inteiro("Filtro", "hydro_id:", 86)
    if hydro_id is None:
        return

    origem = Path(parquet_path)
    sugestao = (
        f"extracao_cobre_scenario{scenario_id}_stage{stage_id}_hydro{hydro_id}.xlsx"
    )
    output_path = filedialog.asksaveasfilename(
        title="Salvar Excel de evidências",
        initialdir=origem.parent,
        initialfile=sugestao,
        defaultextension=".xlsx",
        filetypes=[("Arquivo Excel", "*.xlsx")],
    )
    if not output_path:
        return

    try:
        df = pd.read_parquet(parquet_path)

        required = {
            "scenario_id",
            "stage_id",
            "hydro_id",
            "incremental_inflow_m3s",
            "inflow_nonnegativity_slack_m3s",
        }
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                "O Parquet selecionado não contém as colunas esperadas:\n"
                + ", ".join(sorted(missing))
            )

        caso_principal = df.loc[
            (df["scenario_id"] == scenario_id)
            & (df["stage_id"] == stage_id)
            & (df["hydro_id"] == hydro_id)
        ].copy()

        casos_semelhantes = df.loc[
            (df["incremental_inflow_m3s"] > 0)
            & (df["inflow_nonnegativity_slack_m3s"] > 0)
        ].copy()

        # Organiza os campos mais úteis à análise no início de cada aba.
        campos_prioritarios = [
            "scenario_id",
            "stage_id",
            "node_id",
            "block_id",
            "hydro_id",
            "incremental_inflow_m3s",
            "inflow_nonnegativity_slack_m3s",
            "evaporation_m3s",
            "turbined_m3s",
            "spillage_m3s",
            "outflow_m3s",
            "storage_initial_hm3",
            "storage_final_hm3",
        ]

        def reorganizar_colunas(tabela: pd.DataFrame) -> pd.DataFrame:
            inicio = [col for col in campos_prioritarios if col in tabela.columns]
            restantes = [col for col in tabela.columns if col not in inicio]
            return tabela[inicio + restantes]

        caso_principal = reorganizar_colunas(caso_principal)
        casos_semelhantes = reorganizar_colunas(casos_semelhantes)

        resumo = pd.DataFrame(
            [
                ["Arquivo de origem", str(origem)],
                ["Filtro do caso principal", f"scenario_id={scenario_id}; stage_id={stage_id}; hydro_id={hydro_id}"],
                ["Linhas do caso principal", len(caso_principal)],
                ["Casos com afluência incremental > 0 e slack > 0", len(casos_semelhantes)],
            ],
            columns=["Item", "Valor"],
        )

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            resumo.to_excel(writer, sheet_name="Resumo", index=False)
            caso_principal.to_excel(writer, sheet_name="Caso principal", index=False)
            casos_semelhantes.to_excel(writer, sheet_name="Casos semelhantes", index=False)

            for sheet_name, worksheet in writer.sheets.items():
                worksheet.freeze_panes = "A2"
                worksheet.auto_filter.ref = worksheet.dimensions
                for column_cells in worksheet.columns:
                    maior_largura = max(
                        len(str(cell.value)) if cell.value is not None else 0
                        for cell in column_cells
                    )
                    worksheet.column_dimensions[column_cells[0].column_letter].width = min(
                        max(maior_largura + 2, 12), 45
                    )

        messagebox.showinfo(
            "Exportação concluída",
            "Excel criado com sucesso.\n\n"
            f"Caso principal: {len(caso_principal)} linha(s)\n"
            f"Casos semelhantes: {len(casos_semelhantes)} linha(s)\n\n"
            f"Arquivo salvo em:\n{output_path}",
        )

    except Exception as exc:
        messagebox.showerror("Não foi possível exportar", str(exc))


if __name__ == "__main__":
    main()
