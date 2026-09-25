"""Primeira aba do Analisador de Resultados do COBRE: distribuição de vazões."""

import importlib  # Atualiza o módulo percentual quando o servidor mantém uma versão anterior em memória.
import json  # Lê os identificadores e os nomes cadastrados no hydros.json.
import math  # Normaliza os kernels gaussianos usados na KDE.
from datetime import date  # Valida as datas mensais registradas no stages.json.
from pathlib import Path  # Trabalha com os arquivos escolhidos sem fixar seus caminhos no programa.
import subprocess  # Inicia o Streamlit quando este arquivo é executado diretamente.
import sys  # Localiza o mesmo interpretador Python utilizado pelo usuário.
import time  # Aguarda o servidor local ficar pronto antes de abrir o navegador.
import tkinter as tk  # Cria a janela auxiliar do seletor nativo de arquivo.
from tkinter import filedialog, messagebox  # Mostra o Explorador de Arquivos e eventuais falhas de inicialização.
from urllib.request import urlopen  # Verifica se o Streamlit já responde no computador local.
import webbrowser  # Abre a aplicação no navegador padrão.

from preparar_ambiente import garantir_dependencias  # Prepara automaticamente as bibliotecas ausentes na primeira execução.

garantir_dependencias(  # Permite iniciar pelo botão Run sem executar previamente um comando de instalação.
    {
        "duckdb": "duckdb>=0.10",
        "openpyxl": "openpyxl>=3.1",
        "pandas": "pandas>=2.0",
        "plotly": "plotly>=5.18",
        "streamlit": "streamlit>=1.28",
    }
)

import duckdb  # Consulta diretamente as colunas necessárias do Parquet grande.
import numpy as np  # Calcula a KDE gaussiana usando a dependência numérica do Pandas.
import pandas as pd  # Organiza as distribuições históricas repetidas por mês em cada estágio.
import plotly.graph_objects as go  # Constrói os boxplots e os gráficos de linhas interativos.
import streamlit as st  # Organiza a interface, os controles, o cache e os gráficos.
from streamlit.runtime.scriptrunner import get_script_run_ctx  # Distingue execução direta da execução pelo Streamlit.
from relatorio_estatistico_cobre import (  # Isola os cálculos e a exportação da segunda aba.
    JANELAS,
    exportar_xlsx,
    filtrar_relatorio,
    gerar_relatorio,
    nome_arquivo_exportacao,
    tabela_visivel,
)
import analise_percentuais_cobre as modulo_percentuais

VERSAO_RESUMO_PERCENTUAIS = 5
if getattr(modulo_percentuais, "VERSAO_ESQUEMA_PERCENTUAIS", None) != VERSAO_RESUMO_PERCENTUAIS:
    modulo_percentuais = importlib.reload(modulo_percentuais)

from analise_percentuais_cobre import (
    PERCENTUAIS,
    exportar_percentuais_xlsx,
    filtrar_percentuais,
    gerar_resumo_percentuais,
    nome_arquivo_percentuais,
    selecionar_menores_valores,
    tabela_percentuais_visivel,
)
from graficos_percentuais_cobre import criar_graficos_percentuais
import autocorrelacao_cobre as modulo_autocorrelacao

VERSAO_RESUMO_AUTOCORRELACAO = 2
if getattr(modulo_autocorrelacao, "VERSAO_FORMULA", None) != VERSAO_RESUMO_AUTOCORRELACAO:
    modulo_autocorrelacao = importlib.reload(modulo_autocorrelacao)

from autocorrelacao_cobre import (
    CORES_LAGS, VERSAO_FORMULA, exportar_autocorrelacao_xlsx,
    filtrar_autocorrelacao, gerar_autocorrelacao,
)
import correlacao_espacial_cobre as modulo_correlacao_espacial

VERSAO_RESUMO_CORRELACAO_ESPACIAL = 2
if getattr(modulo_correlacao_espacial, "VERSAO_CORRELACAO_ESPACIAL", None) != VERSAO_RESUMO_CORRELACAO_ESPACIAL:
    modulo_correlacao_espacial = importlib.reload(modulo_correlacao_espacial)

from correlacao_espacial_cobre import (
    MOTIVOS as MOTIVOS_CORRELACAO_ESPACIAL,
    VERSAO_CORRELACAO_ESPACIAL,
    diagnosticar_par,
    exportar_correlacao_espacial_xlsx,
    gerar_correlacao_espacial,
    tabela_espacial,
)
import autocorrelacao_anual_cobre as modulo_autocorrelacao_anual

VERSAO_RESUMO_AUTOCORRELACAO_ANUAL = 1
if getattr(modulo_autocorrelacao_anual, "VERSAO_AUTOCORRELACAO_ANUAL", None) != VERSAO_RESUMO_AUTOCORRELACAO_ANUAL:
    modulo_autocorrelacao_anual = importlib.reload(modulo_autocorrelacao_anual)

from autocorrelacao_anual_cobre import (
    LAGS_ANUAIS, VERSAO_AUTOCORRELACAO_ANUAL,
    exportar_autocorrelacao_anual_xlsx,
    filtrar_autocorrelacao_anual,
    gerar_autocorrelacao_anual,
)
import comparacao_ks_cobre as modulo_ks

VERSAO_RESUMO_KS = 1
if getattr(modulo_ks, "VERSAO_COMPARACAO_KS", None) != VERSAO_RESUMO_KS:
    modulo_ks = importlib.reload(modulo_ks)

from comparacao_ks_cobre import (
    VERSAO_COMPARACAO_KS, calcular_distancia_ks, exportar_ks_xlsx,
    gerar_tabela_ks_usina, nome_arquivo_ks, tabela_ks_visivel,
)


TITULO = "Analisador de Resultados do COBRE"  # Guarda o título principal da aplicação.
COLUNAS_NECESSARIAS = ["scenario_id", "stage_id", "node_id", "hydro_id", "incremental_inflow_m3s"]  # Define somente os dados desta aba.
COLUNA_SLACK = "inflow_nonnegativity_slack_m3s"  # Identifica a coluna opcional de slack de não negatividade.
CIANO_FORTE = "#09b6cb"  # Destaca a linha da média e os contornos principais.
ROXO_FORTE = "#8b5cf6"  # Destaca a média e os boxplots do histórico mensal.
VERMELHO_FORTE = "#ef233c"  # Destaca o slack com um vermelho vivo e distinto do roxo.
NOMES_MESES = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}  # Traduz o mês numérico para o rótulo em português.


# O estilo aplica ciano aos elementos principais e conserva as cores de fundo do tema do usuário.
ESTILO = (  # Reúne regras visuais simples, sem depender de outra biblioteca.
    "<style>"  # Inicia o bloco de estilos da interface.
    "h1 { color: #16b9ca !important; }"  # Destaca o título principal em ciano.
    "h2, h3 { color: #27aabd !important; }"  # Usa ciano moderado nos títulos das seções.
    "div.stButton > button[kind='primary'] {"  # Seleciona o botão principal de arquivo.
    "background-color: #079bb3; border-color: #079bb3; color: white; }"  # Aplica o destaque ciano ao botão.
    "div.stButton > button[kind='primary']:hover {"  # Seleciona o botão quando o mouse passa por ele.
    "background-color: #067f94; border-color: #067f94; color: white; }"  # Escurece levemente o botão durante a interação.
    "button[data-baseweb='tab'][aria-selected='true'] { color: #16b9ca !important; }"  # Destaca a aba ativa em ciano.
    "div[data-baseweb='tab-highlight'] { background-color: #16b9ca !important; }"  # Colore o sublinhado da aba selecionada.
    "div[data-testid='stMetric'] {"  # Seleciona os indicadores resumidos da usina.
    "border: 1px solid rgba(9, 182, 203, 0.35);"  # Desenha uma borda discreta em ciano.
    "border-radius: 0.6rem; padding: 0.5rem 0.7rem; }"  # Melhora o espaçamento dos indicadores.
    "div[data-testid='stMetricValue'] { font-size: 1.35rem; }"  # Reserva largura suficiente para mostrar o expoente na caixa.
    ".cobre-divisao-secao { margin: 2.2rem 0 1.1rem; padding: 0.9rem 1.1rem; "
    "border-top: 4px solid #09b6cb; border-left: 4px solid #09b6cb; "
    "border-radius: 0.45rem; background: rgba(9, 182, 203, 0.08); }"
    ".cobre-divisao-secao h2 { color: #27aabd; font-size: 1.25rem; margin: 0; }"
    "</style>"  # Encerra o bloco de estilos.
)  # Guarda o CSS completo para aplicação na página.


def mostrar_divisao_visual(titulo: str) -> None:
    """Destaca a passagem entre grupos de gráficos sem alterar seus controles."""
    st.markdown(
        f'<div class="cobre-divisao-secao"><h2>{titulo}</h2></div>',
        unsafe_allow_html=True,
    )


def selecionar_parquet() -> str:  # Permite selecionar o arquivo local sem enviá-lo ao navegador.
    janela = tk.Tk()  # Cria a janela necessária ao diálogo nativo do Windows.
    janela.withdraw()  # Esconde a janela vazia atrás do seletor de arquivo.
    janela.attributes("-topmost", True)  # Mantém o Explorador de Arquivos visível à frente do navegador.
    try:  # Garante que a janela auxiliar seja encerrada após escolha ou cancelamento.
        caminho = filedialog.askopenfilename(  # Abre a seleção de um Parquet no computador local.
            parent=janela,  # Associa o diálogo à janela auxiliar do Tkinter.
            title="Selecionar Parquet consolidado de vazões do COBRE",  # Explica o arquivo necessário.
            initialdir=Path(__file__).resolve().parent,  # Começa na pasta dos programas sem fixar o Parquet.
            filetypes=[("Arquivos Parquet", "*.parquet"), ("Todos os arquivos", "*.*")],  # Destaca a extensão adequada.
        )  # Guarda o caminho escolhido ou uma string vazia quando a seleção é cancelada.
    finally:  # Executa a limpeza mesmo se o diálogo não abrir corretamente.
        janela.destroy()  # Fecha a janela auxiliar.
    return caminho  # Entrega o caminho para ser mantido na sessão do Streamlit.


def guardar_arquivo_escolhido() -> bool:  # Atualiza a fonte da sessão após o seletor nativo.
    escolhido = selecionar_parquet()  # Pede ao usuário o caminho completo do Parquet.
    if not escolhido:  # Reconhece um cancelamento sem apagar a fonte anterior.
        return False  # Informa ao botão que nada foi selecionado.
    st.session_state["arquivo_parquet"] = escolhido  # Mantém o caminho para as próximas interações.
    st.session_state["excedeu_limite"] = False  # Limpa o aviso de limite da seleção anterior.
    return True  # Informa que existe um novo arquivo escolhido.


def selecionar_hydros_json() -> str:  # Permite escolher o cadastro de usinas pelo Explorador de Arquivos.
    janela = tk.Tk()  # Cria a janela auxiliar para o diálogo nativo do Windows.
    janela.withdraw()  # Oculta a janela vazia enquanto o seletor está aberto.
    janela.attributes("-topmost", True)  # Mantém o seletor visível à frente do navegador.
    try:  # Garante o fechamento da janela após escolha ou cancelamento.
        caminho = filedialog.askopenfilename(  # Solicita ao usuário um arquivo JSON local.
            parent=janela,  # Associa o diálogo à janela auxiliar.
            title="Selecionar hydros.json do COBRE",  # Identifica o cadastro necessário.
            initialdir=Path(__file__).resolve().parent,  # Começa na pasta deste programa.
            filetypes=[("Arquivos JSON", "*.json"), ("Todos os arquivos", "*.*")],  # Prioriza arquivos JSON.
        )  # Recebe o caminho escolhido ou vazio após cancelamento.
    finally:  # Executa a limpeza mesmo se o diálogo falhar.
        janela.destroy()  # Fecha a janela auxiliar do Tkinter.
    return caminho  # Entrega o caminho para a sessão do Streamlit.


def guardar_hydros_escolhido() -> bool:  # Atualiza o cadastro somente quando houver uma nova escolha.
    escolhido = selecionar_hydros_json()  # Abre o seletor nativo para o hydros.json.
    if not escolhido:  # Reconhece o cancelamento sem apagar o cadastro anterior.
        return False  # Informa que o usuário não escolheu outro arquivo.
    st.session_state["arquivo_hydros_json"] = escolhido  # Conserva o caminho entre interações.
    return True  # Informa que existe um novo cadastro para validar.


def selecionar_historico() -> str:  # Permite escolher o inflow_history.parquet sem enviar o arquivo ao navegador.
    janela = tk.Tk()  # Cria a janela auxiliar exigida pelo diálogo nativo.
    janela.withdraw()  # Esconde a janela vazia atrás do Explorador de Arquivos.
    janela.attributes("-topmost", True)  # Mantém o seletor à frente do navegador.
    try:  # Garante o encerramento da janela auxiliar após a escolha.
        caminho = filedialog.askopenfilename(  # Abre a seleção do histórico no computador local.
            parent=janela,  # Associa o diálogo à janela auxiliar.
            title="Selecionar inflow_history.parquet do COBRE",  # Explica qual arquivo histórico é necessário.
            initialdir=Path(__file__).resolve().parent,  # Começa na pasta deste programa.
            filetypes=[("Arquivos Parquet", "*.parquet"), ("Todos os arquivos", "*.*")],  # Prioriza a extensão adequada.
        )  # Recebe o caminho escolhido ou vazio após cancelamento.
    finally:  # Executa a limpeza mesmo se o seletor falhar.
        janela.destroy()  # Fecha a janela auxiliar.
    return caminho  # Entrega o caminho escolhido para a sessão.


def guardar_historico_escolhido() -> bool:  # Atualiza o histórico somente após uma escolha válida.
    escolhido = selecionar_historico()  # Solicita o caminho do inflow_history.parquet.
    if not escolhido:  # Reconhece o cancelamento sem apagar o caminho anterior.
        return False  # Informa que nenhum novo histórico foi escolhido.
    st.session_state["arquivo_historico"] = escolhido  # Conserva o histórico entre interações.
    return True  # Informa que existe um novo arquivo para validar.


def selecionar_stages_json() -> str:  # Permite escolher o calendário de estágios pelo Explorador de Arquivos.
    janela = tk.Tk()  # Cria a janela auxiliar para o diálogo nativo.
    janela.withdraw()  # Oculta a janela vazia durante a escolha.
    janela.attributes("-topmost", True)  # Mantém o diálogo visível à frente do navegador.
    try:  # Garante o encerramento da janela após escolha ou cancelamento.
        caminho = filedialog.askopenfilename(  # Abre a seleção do stages.json no computador local.
            parent=janela,  # Associa o diálogo à janela auxiliar.
            title="Selecionar stages.json do COBRE",  # Identifica o calendário necessário.
            initialdir=Path(__file__).resolve().parent,  # Começa na pasta deste programa.
            filetypes=[("Arquivos JSON", "*.json"), ("Todos os arquivos", "*.*")],  # Prioriza arquivos JSON.
        )  # Recebe o caminho escolhido ou vazio após cancelamento.
    finally:  # Executa a limpeza mesmo se houver falha na abertura.
        janela.destroy()  # Fecha a janela auxiliar do Tkinter.
    return caminho  # Entrega o caminho para a sessão.


def guardar_stages_escolhido() -> bool:  # Atualiza o calendário apenas quando o usuário escolhe um arquivo.
    escolhido = selecionar_stages_json()  # Solicita o caminho do stages.json.
    if not escolhido:  # Reconhece um cancelamento sem apagar o calendário anterior.
        return False  # Informa que nenhum novo arquivo foi escolhido.
    st.session_state["arquivo_stages_json"] = escolhido  # Conserva o caminho nas próximas interações.
    return True  # Informa que existe um novo calendário para validar.


# O cache evita reler e reconstruir o cadastro enquanto caminho, tamanho e data forem iguais.
@st.cache_data(show_spinner="Lendo nomes das usinas...")  # Reaproveita o de-para entre interações no Streamlit.
def carregar_cadastro_hidros(caminho: str, tamanho: int, modificado: int) -> dict[int, str]:  # Lê somente id e name do JSON real do COBRE.
    try:  # Transforma problemas comuns de codificação ou sintaxe em uma mensagem clara.
        with open(caminho, "r", encoding="utf-8") as arquivo:  # Abre o cadastro selecionado sem alterar seu conteúdo.
            dados = json.load(arquivo)  # Converte o JSON em objetos Python.
    except (json.JSONDecodeError, UnicodeError) as erro:  # Reconhece JSON corrompido ou texto inválido.
        raise ValueError("O hydros.json não contém um JSON válido em UTF-8.") from erro  # Evita traceback técnico na interface.
    if not isinstance(dados, dict) or not isinstance(dados.get("hydros"), list):  # Confere a estrutura encontrada em 33_C/system/hydros.json.
        raise ValueError("Estrutura inválida: o hydros.json deve conter uma lista 'hydros'.")  # Não inventa um cadastro para outro esquema.
    if not dados["hydros"]:  # Detecta um cadastro sem usinas.
        raise ValueError("O hydros.json não possui usinas na lista 'hydros'.")  # Explica por que não há nomes a carregar.
    nomes_por_id = {}  # Guarda o identificador técnico associado ao nome exibido.
    for posicao, usina in enumerate(dados["hydros"], start=1):  # Examina cada registro cadastral do COBRE.
        if not isinstance(usina, dict):  # Recusa uma entrada sem campos identificáveis.
            raise ValueError(f"Usina {posicao} do hydros.json não é um objeto.")  # Mostra a posição problemática.
        if "id" not in usina:  # Distingue a ausência do identificador de um valor inválido.
            raise ValueError(f"Usina {posicao} do hydros.json não possui o campo 'id'.")  # Aponta o campo ausente.
        if "name" not in usina:  # Distingue a ausência do nome de um valor inválido.
            raise ValueError(f"Usina {posicao} do hydros.json não possui o campo 'name'.")  # Aponta o campo ausente.
        hydro_id = usina["id"]  # Lê o identificador numérico usado no Parquet.
        nome = usina["name"]  # Lê o nome destinado à interface.
        if isinstance(hydro_id, bool) or not isinstance(hydro_id, int):  # Rejeita IDs não inteiros, inclusive booleanos.
            raise ValueError(f"Usina {posicao} do hydros.json possui 'id' inválido: {hydro_id!r}.")  # Evita chave ambígua.
        if not isinstance(nome, str) or not nome.strip():  # Recusa nome ausente, vazio ou composto só de espaços.
            raise ValueError(f"hydro_id {hydro_id} do hydros.json não possui um 'name' válido.")  # Explica o nome inválido.
        if hydro_id in nomes_por_id:  # Impede dois registros para a mesma chave técnica.
            raise ValueError(f"hydro_id {hydro_id} aparece mais de uma vez no hydros.json.")  # Não escolhe silenciosamente um nome.
        nomes_por_id[hydro_id] = nome.strip()  # Guarda o nome sem espaços acidentais nas extremidades.
    return nomes_por_id  # Entrega o de-para validado para uso na interface.


def criar_rotulos_das_usinas(usinas: list[int], nomes_por_id: dict[int, str]) -> tuple[list[int], dict[int, str], int]:  # Prepara opções visuais sem trocar a chave interna.
    rotulos = {}  # Associa cada ID do Parquet ao texto apresentado no seletor.
    for hydro_id in usinas:  # Inclui apenas usinas que realmente existem no Parquet.
        nome = nomes_por_id.get(hydro_id)  # Procura o nome cadastral sem descartar IDs ausentes.
        rotulos[hydro_id] = f"{nome} — hydro_id {hydro_id}" if nome else f"Usina sem nome — hydro_id {hydro_id}"  # Identifica inclusive nomes repetidos.
    ordenadas = sorted(usinas)  # Exibe as usinas em ordem crescente de hydro_id no seletor.
    quantidade_sem_nome = sum(hydro_id not in nomes_por_id for hydro_id in usinas)  # Conta IDs sem correspondência para o aviso.
    return ordenadas, rotulos, quantidade_sem_nome  # Entrega opções, rótulos e total de nomes ausentes.


# O cache evita reler e validar o calendário enquanto o mesmo stages.json permanecer selecionado.
@st.cache_data(show_spinner="Lendo calendário dos estágios...")
def carregar_calendario_dos_estagios(caminho: str, tamanho: int, modificado: int) -> dict[int, dict]:
    """Lê o calendário mensal e conserva datas, mês e ordem cronológica."""
    try:  # Transforma problemas de sintaxe e codificação em mensagens curtas.
        with open(caminho, "r", encoding="utf-8") as arquivo:  # Abre o calendário sem modificar seu conteúdo.
            dados = json.load(arquivo)  # Converte o JSON em objetos Python.
    except (json.JSONDecodeError, UnicodeError) as erro:  # Reconhece um JSON corrompido ou texto inválido.
        raise ValueError("O stages.json não contém um JSON válido em UTF-8.") from erro  # Evita traceback técnico na interface.
    if not isinstance(dados, dict) or not isinstance(dados.get("stages"), list):  # Confere a seção usada pelo COBRE.
        raise ValueError("Estrutura inválida: o stages.json deve conter uma lista 'stages'.")  # Não adivinha outro formato.
    if not dados["stages"]:  # Detecta um calendário vazio.
        raise ValueError("O stages.json não possui estágios na lista 'stages'.")  # Explica a ausência de correspondências.
    registros = []
    ids = set()
    for posicao, estagio in enumerate(dados["stages"], start=1):  # Examina cada estágio declarado no calendário.
        if not isinstance(estagio, dict):  # Recusa uma entrada sem campos identificáveis.
            raise ValueError(f"Estágio {posicao} do stages.json não é um objeto.")  # Informa a posição problemática.
        for campo in ("id", "start_date", "end_date"):  # Confere os três campos definidos para o calendário.
            if campo not in estagio:  # Detecta cada campo ausente separadamente.
                raise ValueError(f"Estágio {posicao} do stages.json não possui o campo '{campo}'.")  # Mostra o campo obrigatório ausente.
        stage_id = estagio["id"]  # Obtém a chave técnica usada no Parquet consolidado.
        if isinstance(stage_id, bool) or not isinstance(stage_id, int):  # Rejeita chaves que não sejam números inteiros.
            raise ValueError(f"Estágio {posicao} do stages.json possui 'id' inválido: {stage_id!r}.")  # Evita uma associação ambígua.
        if stage_id in ids:  # Impede duas datas diferentes para o mesmo stage_id.
            raise ValueError(f"stage_id {stage_id} aparece mais de uma vez no stages.json.")  # Não escolhe uma das datas silenciosamente.
        try:  # Valida as duas datas no formato ISO usado pelo COBRE.
            inicio = date.fromisoformat(estagio["start_date"])  # Converte o início em uma data real.
            fim = date.fromisoformat(estagio["end_date"])  # Converte o fim em uma data real.
        except (TypeError, ValueError) as erro:  # Captura texto ausente ou data impossível.
            raise ValueError(f"stage_id {stage_id} possui start_date ou end_date inválida no stages.json.") from erro  # Identifica o estágio inválido.
        if fim <= inicio:  # Confirma que o intervalo do estágio avança no tempo.
            raise ValueError(f"stage_id {stage_id} possui end_date anterior ou igual a start_date.")  # Evita um calendário incoerente.
        proximo_mes = date(inicio.year + (inicio.month == 12), 1 if inicio.month == 12 else inicio.month + 1, 1)
        if inicio.day != 1 or fim != proximo_mes:
            raise ValueError(f"stage_id {stage_id} não representa um mês calendário completo.")
        ids.add(stage_id)
        registros.append((stage_id, inicio, fim))
    registros.sort(key=lambda registro: registro[1])
    for anterior, atual in zip(registros, registros[1:]):
        if atual[1] != anterior[2]:
            raise ValueError(
                f"Há lacuna ou sobreposição entre os stage_id {anterior[0]} e {atual[0]}."
            )
    return {
        stage_id: {"inicio": inicio, "fim": fim, "mes": inicio.month, "ordem": ordem}
        for ordem, (stage_id, inicio, fim) in enumerate(registros)
    }


def carregar_meses_dos_estagios(caminho: str, tamanho: int, modificado: int) -> dict[int, int]:
    """Mantém o mapa simples utilizado pelos gráficos já existentes."""
    calendario = carregar_calendario_dos_estagios(caminho, tamanho, modificado)
    return {stage_id: registro["mes"] for stage_id, registro in calendario.items()}


def rotulo_estagio_mes_ano(stage_id: int, calendario: dict[int, dict] | None) -> str:
    """Mostra o mês e o ano do stages.json sem alterar o stage_id selecionado."""
    registro = calendario.get(int(stage_id)) if calendario else None
    if registro is None:
        return f"Estágio {stage_id}"
    return f"{NOMES_MESES[registro['mes']]} de {registro['inicio'].year}"


# O cache valida o esquema e as datas do histórico somente quando o arquivo muda.
@st.cache_data(show_spinner="Validando histórico mensal...")  # Reutiliza a validação entre seleções de usinas.
def validar_arquivo_historico(caminho: str, tamanho: int, modificado: int) -> None:  # Confere o inflow_history.parquet antes das consultas.
    colunas_necessarias = ["hydro_id", "start_date", "end_date", "value_m3s"]  # Define o esquema mínimo do histórico.
    conexao = duckdb.connect(database=":memory:")  # Usa uma conexão temporária sem criar arquivos.
    try:  # Garante o fechamento da conexão em sucesso ou falha.
        descricao = conexao.execute("DESCRIBE SELECT * FROM read_parquet(?)", [caminho]).fetchall()  # Lê apenas o esquema do Parquet.
        colunas = [linha[0] for linha in descricao]  # Extrai os nomes realmente encontrados.
        faltantes = [coluna for coluna in colunas_necessarias if coluna not in colunas]  # Localiza campos obrigatórios ausentes.
        if faltantes:  # Impede consultas sobre um histórico incompatível.
            raise ValueError(f"Colunas obrigatórias ausentes no histórico: {', '.join(faltantes)}.")  # Informa exatamente o problema.
        invalidas = conexao.execute("SELECT COUNT(*) FROM read_parquet(?) WHERE start_date IS NULL OR TRY_CAST(start_date AS DATE) IS NULL", [caminho]).fetchone()[0]  # Conta datas que não identificam mês.
        if invalidas:  # Não permite adivinhar o mês de registros inválidos.
            raise ValueError(f"O histórico possui {invalidas} valores de start_date nulos ou inválidos.")  # Explica a falha de calendário.
        intervalos_invalidos = conexao.execute(
            """
            SELECT COUNT(*)
            FROM read_parquet(?)
            WHERE TRY_CAST(end_date AS DATE) IS NULL
               OR TRY_CAST(start_date AS DATE)
                    <> CAST(DATE_TRUNC('month', TRY_CAST(start_date AS DATE)) AS DATE)
               OR TRY_CAST(end_date AS DATE)
                    <> CAST(TRY_CAST(start_date AS DATE) + INTERVAL 1 MONTH AS DATE)
            """,
            [caminho],
        ).fetchone()[0]
        if intervalos_invalidos:
            raise ValueError(
                f"O histórico possui {intervalos_invalidos} registros que não representam meses completos."
            )
        duplicados = conexao.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT hydro_id, TRY_CAST(start_date AS DATE) AS inicio
                FROM read_parquet(?)
                GROUP BY hydro_id, inicio
                HAVING COUNT(*) > 1
            )
            """,
            [caminho],
        ).fetchone()[0]
        if duplicados:
            raise ValueError(
                f"O histórico possui {duplicados} combinações repetidas de UHE e mês."
            )
    finally:  # Libera o leitor do Parquet após a validação.
        conexao.close()  # Fecha a conexão temporária.


# O cache lê apenas uma usina histórica e evita repetir a consulta em cada interação visual.
@st.cache_data(show_spinner=False)  # Mantém a distribuição mensal enquanto arquivo e hydro_id não mudarem.
def consultar_historico(caminho: str, tamanho: int, modificado: int, hydro_id: int):  # Lê mês e vazão histórica da usina selecionada.
    conexao = duckdb.connect(database=":memory:")  # Abre uma conexão temporária para o histórico filtrado.
    try:  # Garante a liberação do arquivo depois da consulta.
        consulta = (  # Monta uma leitura pequena destinada aos boxplots e cálculos mensais.
            "SELECT hydro_id, TRY_CAST(start_date AS DATE) AS start_date, "
            "TRY_CAST(end_date AS DATE) AS end_date, "
            "EXTRACT(MONTH FROM TRY_CAST(start_date AS DATE))::INTEGER AS mes, value_m3s "
            "FROM read_parquet(?) WHERE hydro_id = ? ORDER BY start_date"  # Filtra pela mesma chave técnica dos cenários.
        )  # Fecha o texto da consulta histórica.
        return conexao.execute(consulta, [caminho, hydro_id]).df()  # Entrega apenas os registros desta UHE.
    finally:  # Executa a limpeza após sucesso ou erro.
        conexao.close()  # Fecha o DuckDB sem alterar o histórico.


# O cache evita ler o esquema e descobrir a lista de usinas a cada interação com o seletor.
@st.cache_data(show_spinner="Lendo estrutura e usinas do Parquet...")  # Reutiliza metadados enquanto caminho, tamanho e data não mudarem.
def ler_metadados(caminho: str, tamanho: int, modificado: int) -> dict:  # Examina somente chaves e esquema do arquivo selecionado.
    conexao = duckdb.connect(database=":memory:")  # Usa uma conexão temporária sem criar banco permanente.
    try:  # Fecha a conexão tanto em sucesso quanto em arquivo inválido.
        descricao = conexao.execute("DESCRIBE SELECT * FROM read_parquet(?)", [caminho]).fetchall()  # Lê os nomes das colunas sem carregar as linhas.
        colunas = [linha[0] for linha in descricao]  # Extrai as colunas realmente presentes no arquivo.
        faltantes = [coluna for coluna in COLUNAS_NECESSARIAS if coluna not in colunas]  # Identifica campos indispensáveis à análise.
        if faltantes:  # Impede a consulta de um Parquet que não possui o esquema esperado.
            raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(faltantes)}. Colunas encontradas: {', '.join(colunas)}")  # Mostra o que falta.
        consulta = (  # Prepara uma varredura apenas das colunas de identificação.
            "SELECT COUNT(*) AS registros, "  # Conta as linhas do arquivo.
            "COUNT(DISTINCT scenario_id) AS cenarios, "  # Conta os cenários efetivamente presentes.
            "COUNT(DISTINCT stage_id) AS estagios, "  # Conta os estágios efetivamente presentes.
            "LIST(DISTINCT hydro_id) AS usinas, "  # Descobre os IDs das usinas para o seletor.
            "LIST(DISTINCT stage_id) AS ids_estagios "  # Descobre os estágios que precisam existir no calendário.
            "FROM read_parquet(?)"  # Consulta o arquivo escolhido sem ler as colunas de lag.
        )  # Fecha o texto da consulta de metadados.
        linha = conexao.execute(consulta, [caminho]).fetchone()  # Obtém os totais e a pequena lista de usinas.
        usinas = sorted(valor for valor in (linha[3] or []) if valor is not None)  # Ordena numericamente os IDs válidos.
        ids_estagios = sorted(valor for valor in (linha[4] or []) if valor is not None)  # Ordena os stage_id para validar o stages.json.
        return {"registros": linha[0], "cenarios": linha[1], "estagios": linha[2], "usinas": usinas, "ids_estagios": ids_estagios, "colunas": colunas}  # Entrega também o esquema para validar a coluna opcional do slack.
    finally:  # Libera recursos após a consulta ou uma falha de validação.
        conexao.close()  # Fecha o DuckDB sem modificar o Parquet de origem.


# Cada consulta abaixo tem uma única hydro_id e nunca solicita as colunas de lag.
def consultar_usina(caminho: str, hydro_id: int):  # Traz somente as cinco colunas usadas nos gráficos de uma usina.
    conexao = duckdb.connect(database=":memory:")  # Abre uma conexão temporária para a usina atual.
    try:  # Garante que a conexão seja fechada depois de trazer a pequena tabela filtrada.
        consulta = (  # Seleciona explicitamente as colunas necessárias à primeira aba.
            "SELECT scenario_id, stage_id, node_id, hydro_id, incremental_inflow_m3s "  # Exclui os lags e outras colunas.
            "FROM read_parquet(?) WHERE hydro_id = ? "  # Aplica o filtro de usina dentro do DuckDB.
            "ORDER BY stage_id, scenario_id, node_id"  # Organiza estágios e cenários para inspeção e gráficos.
        )  # Fecha a consulta de uma usina.
        dados = conexao.execute(consulta, [caminho, hydro_id]).df()  # Converte apenas essa usina em um DataFrame Pandas.
        return dados  # Entrega os registros sem alterar as vazões de origem.
    finally:  # Libera a conexão assim que a usina foi consultada.
        conexao.close()  # Fecha o DuckDB antes de construir os gráficos.


@st.cache_data(show_spinner=False, max_entries=3)
def consultar_usina_em_cache(assinatura: tuple, hydro_id: int):
    """Reutiliza as observações da UHE enquanto o Parquet não mudar."""
    return consultar_usina(assinatura[0], hydro_id)


def consultar_slack(caminho: str, hydro_id: int):  # Consulta o slack válido e calcula sua média sem carregar outras UHEs.
    conexao = duckdb.connect(database=":memory:")  # Abre uma conexão temporária somente para a UHE escolhida.
    try:  # Garante que a conexão seja liberada após a leitura da variável opcional.
        consulta = (  # Calcula no DuckDB a média sobre os mesmos registros enviados ao boxplot.
            "SELECT scenario_id, stage_id, inflow_nonnegativity_slack_m3s, "  # Mantém cada cenário individual para a distribuição.
            "AVG(inflow_nonnegativity_slack_m3s) OVER (PARTITION BY stage_id) AS mean_slack "  # Calcula uma única média por estágio no banco.
            "FROM read_parquet(?) WHERE hydro_id = ? "  # Restringe a consulta à UHE selecionada.
            "AND isfinite(inflow_nonnegativity_slack_m3s) "  # Exclui nulos, NaN e infinitos sem substituí-los por zero.
            "ORDER BY stage_id, scenario_id"  # Organiza a distribuição na mesma ordem dos gráficos.
        )  # Fecha o texto da consulta opcional.
        return conexao.execute(consulta, [caminho, hydro_id]).df()  # Entrega somente os valores válidos da UHE e suas médias.
    finally:  # Executa a limpeza após sucesso ou falha da consulta.
        conexao.close()  # Fecha o DuckDB sem modificar o Parquet.


# A validação ocorre antes de qualquer média para não misturar nós ou cenários ambíguos.
def validar_usina(dados, hydro_id: int) -> None:  # Confere a chave esperada para cada cenário e estágio.
    if dados.empty:  # Trata uma usina sem registros no arquivo selecionado.
        raise ValueError(f"A usina {hydro_id} não possui registros no Parquet.")  # Explica a ausência de dados.
    if not dados["hydro_id"].eq(hydro_id).all():  # Confirma que a consulta não trouxe outra usina.
        raise ValueError(f"A consulta da usina {hydro_id} retornou outra hydro_id.")  # Interrompe a análise dessa seção.
    chaves = ["scenario_id", "stage_id", "node_id", "hydro_id"]  # Identifica os campos que não podem estar ausentes.
    if dados[chaves].isna().any().any():  # Procura identificadores nulos que tornariam a associação incerta.
        raise ValueError(f"A usina {hydro_id} possui identificadores de cenário, estágio ou nó ausentes.")  # Mostra a falha estrutural.
    repetidos = dados.duplicated(subset=["scenario_id", "stage_id", "hydro_id"], keep=False)  # Procura mais de um nó ou registro por cenário e estágio.
    if repetidos.any():  # Impede uma média que misturaria registros de nós diferentes.
        exemplo = dados.loc[repetidos].iloc[0]  # Obtém uma chave concreta que apresentou duplicidade.
        cenario = int(exemplo["scenario_id"])  # Mantém o identificador do cenário inteiro na mensagem.
        estagio = int(exemplo["stage_id"])  # Mantém o identificador do estágio inteiro na mensagem.
        raise ValueError(f"A usina {hydro_id} possui múltiplos nós ou registros no cenário {cenario}, estágio {estagio}. A análise precisa ser ajustada antes de prosseguir.")  # Explica a ambiguidade.


def limites_y(minimo: float, maximo: float) -> list[float]:  # Define um eixo que contém negativos, positivos e a referência zero.
    amplitude = max(maximo - minimo, abs(minimo), abs(maximo), 1.0)  # Escolhe uma margem estável mesmo para valores quase nulos.
    inferior = min(minimo, 0.0) - 0.05 * amplitude  # Reserva espaço abaixo do menor valor real, inclusive se for negativo.
    superior = max(maximo, 0.0) + 0.05 * amplitude  # Reserva espaço acima do maior valor real e da linha zero.
    return [inferior, superior]  # Entrega uma escala que nunca trunca a região negativa.


def formatar_vazao_resumo(valor: float) -> str:  # Mantém os números dos indicadores curtos e legíveis.
    if valor == 0:  # Trata o zero sem criar um expoente desnecessário.
        return "0,00"  # Mostra o zero com duas casas decimais.
    tamanho = abs(valor)  # Examina a grandeza sem perder o sinal original.
    if tamanho < 0.1 or tamanho >= 10000:  # Usa notação científica quando o formato decimal ocuparia espaço ou esconderia o valor.
        return f"{valor:.2e}".replace(".", ",")  # Conserva o expoente visível com duas casas decimais.
    return f"{valor:.2f}".replace(".", ",")  # Mostra os valores usuais com duas casas decimais.


def formatar_vazao_percentual(valor: float) -> str:
    """Mostra duas casas nos cartões percentuais, sem expoente ou zero negativo."""
    texto = f"{valor:.2f}"
    return ("0.00" if texto == "-0.00" else texto).replace(".", ",")


def mostrar_indicadores_percentuais(fatias: pd.DataFrame, percentuais: list[int]) -> None:
    """Resume cada fatia exibida sem somar estágios nem repetir meses históricos."""
    st.caption("As quantidades selecionadas são por estágio nos cenários e por mês no histórico.")
    for percentual in sorted(percentuais):
        for fonte, unidade in (("Cenários", "estágio"), ("Histórico", "mês")):
            grupo = fatias.loc[
                fatias["percentual"].eq(percentual) & fatias["fonte"].eq(fonte)
                & fatias["n_selecionados"].gt(0)
            ]
            if grupo.empty:
                continue
            st.markdown(f"**p{percentual}% — {fonte}**")
            contagens = grupo["n_selecionados"].astype(int)
            menor_contagem, maior_contagem = int(contagens.min()), int(contagens.max())
            quantidade = f"{menor_contagem:,}".replace(",", ".")
            if menor_contagem != maior_contagem:
                quantidade += f" a {maior_contagem:,}".replace(",", ".")
            colunas = st.columns(4)
            colunas[0].metric(f"Valores selecionados por {unidade}", quantidade)
            colunas[1].metric(
                "Estágios com dados" if fonte == "Cenários" else "Meses com dados",
                len(grupo),
            )
            colunas[2].metric("Menor vazão (m³/s)", formatar_vazao_percentual(float(grupo["minimo"].min())))
            colunas[3].metric("Maior vazão (m³/s)", formatar_vazao_percentual(float(grupo["maximo"].max())))


# O boxplot recebe cada vazão válida, sem eliminar negativos nem outliers.
def criar_boxplot(dados_validos, historico_por_estagio, rotulo_usina: str, estagios: list[int], meses_por_estagio: dict[int, int], limites: list[float], dados_slack=None):  # Compara PAR(p), histórico e slack quando disponíveis.
    categorias = dados_validos["stage_id"].astype(str)  # Representa cada estágio como uma categoria distinta no eixo X.
    ordem_categorias = [str(estagio) for estagio in estagios]  # Mantém os estágios em ordem numérica crescente.
    passo = max(1, len(ordem_categorias) // 12)  # Reduz apenas a quantidade de rótulos quando há muitos estágios.
    posicoes_rotulos = list(range(0, len(ordem_categorias), passo))  # Guarda as posições dos rótulos espaçados.
    valores_rotulos = [ordem_categorias[posicao] for posicao in posicoes_rotulos]  # Seleciona as categorias que receberão texto.
    textos_rotulos = [f"{estagio}<br>{NOMES_MESES[meses_por_estagio[int(estagio)]]}" if meses_por_estagio else estagio for estagio in valores_rotulos]  # Acrescenta o mês real quando há calendário.
    figura = go.Figure()  # Cria a figura interativa do Plotly.
    figura.add_trace(go.Box(  # Usa as vazões originais de todos os cenários em cada estágio.
        x=categorias,  # Coloca cada cenário na categoria do seu stage_id.
        y=dados_validos["incremental_inflow_m3s"],  # Mantém todos os valores numéricos, inclusive negativos.
        name="Cenários PAR(p)",  # Identifica a fonte ciano na legenda.
        boxpoints="outliers",  # Mostra os pontos considerados outliers em vez de ocultá-los.
        quartilemethod="linear",  # Usa os valores sem agregação prévia para calcular quartis e mediana.
        marker=dict(color="rgba(9,182,203,0.65)", size=3),  # Destaca outliers em ciano discreto.
        line=dict(color=CIANO_FORTE, width=1.4),  # Contorna as caixas com a cor do PAR(p).
        fillcolor="rgba(9,182,203,0.25)",  # Aplica um preenchimento suave às caixas.
        hoveron="boxes+points",  # Permite inspecionar tanto o resumo da caixa quanto os pontos.
    ))  # Fecha a série dos cenários PAR(p).
    if historico_por_estagio is not None and not historico_por_estagio.empty:  # Acrescenta a distribuição histórica somente quando há valores.
        figura.add_trace(go.Box(  # Repete a distribuição mensal correta ao lado de cada stage.
            x=historico_por_estagio["stage_id"].astype(str),  # Posiciona o histórico no mesmo stage do PAR(p).
            y=historico_por_estagio["value_m3s"],  # Usa todos os valores históricos válidos daquele mês.
            customdata=historico_por_estagio[["mes_nome"]].to_numpy(),  # Disponibiliza o mês real no cursor.
            name="Histórico mensal",  # Identifica a fonte roxa na legenda.
            boxpoints="outliers",  # Preserva os outliers históricos.
            boxmean=False,  # Mantém somente mediana, quartis, whiskers e outliers no boxplot histórico.
            quartilemethod="linear",  # Calcula quartis sobre todos os anos disponíveis.
            marker=dict(color="rgba(139,92,246,0.65)", size=3),  # Destaca outliers históricos em roxo.
            line=dict(color=ROXO_FORTE, width=1.4),  # Contorna as caixas históricas em roxo.
            fillcolor="rgba(139,92,246,0.25)",  # Aplica preenchimento roxo transparente.
            hoveron="boxes+points",  # Mantém estatísticas tradicionais e pontos inspecionáveis.
            hovertemplate=f"Fonte: Histórico mensal<br>Stage: %{{x}}<br>Mês: %{{customdata[0]}}<br>Usina: {rotulo_usina}<br>Vazão: %{{y:.6g}} m³/s<extra></extra>",  # Identifica fonte, mês e UHE.
        ))  # Fecha a série histórica mensal.
    if dados_slack is not None and not dados_slack.empty:  # Acrescenta o slack somente quando a opção está ativa e há valores válidos.
        figura.add_trace(go.Box(  # Usa todos os valores válidos de slack dos cenários em cada estágio.
            x=dados_slack["stage_id"].astype(str),  # Posiciona cada valor de slack ao lado das outras fontes do mesmo estágio.
            y=dados_slack[COLUNA_SLACK],  # Preserva os valores originais do slack, inclusive os negativos.
            name="Slack de não negatividade",  # Identifica claramente a distribuição vermelha na legenda.
            boxpoints="outliers",  # Mostra os pontos considerados outliers do slack.
            boxmean=False,  # Omite o marcador da média dentro do boxplot.
            quartilemethod="linear",  # Calcula mediana e quartis sobre todos os cenários válidos.
            marker=dict(color="rgba(239,35,60,0.72)", size=3),  # Destaca os outliers do slack em vermelho vivo.
            line=dict(color=VERMELHO_FORTE, width=1.6),  # Contorna as caixas do slack com vermelho forte.
            fillcolor="rgba(239,35,60,0.28)",  # Preenche as caixas sem esconder as outras distribuições.
            hoveron="boxes+points",  # Permite inspecionar as estatísticas e os valores individuais.
            hovertemplate=f"Fonte: Slack de não negatividade<br>Stage: %{{x}}<br>Usina: {rotulo_usina}<br>Slack: %{{y:.6g}} m³/s<extra></extra>",  # Mostra somente estágio e slack no cursor dos pontos.
        ))  # Fecha a distribuição completa do slack.
    figura.add_hline(y=0, line_dash="dot", line_color="#a8b3bc", line_width=1, annotation_text="0 m³/s", annotation_position="top left")  # Marca o zero sem alterar as vazões.
    figura.update_xaxes(title_text="Estágio (stage_id) e mês", type="category", categoryorder="array", categoryarray=ordem_categorias, tickmode="array", tickvals=valores_rotulos, ticktext=textos_rotulos)  # Ordena os stages e mostra o calendário real.
    figura.update_yaxes(title_text="Vazão incremental (m³/s)", range=limites, zeroline=False)  # Mantém todos os extremos no eixo vertical comum.
    mostrar_legenda = (historico_por_estagio is not None and not historico_por_estagio.empty) or (dados_slack is not None and not dados_slack.empty)  # Exibe a legenda quando existe outra fonte além do PAR(p).
    figura.update_layout(title=f"Distribuição das Vazões Incrementais por Estágio — {rotulo_usina}", height=480, showlegend=mostrar_legenda, boxmode="group", margin=dict(l=45, r=20, t=65, b=60), hovermode="closest", legend=dict(orientation="h", y=1.02, x=0))  # Agrupa PAR(p), histórico e slack lado a lado.
    return figura  # Entrega o boxplot interativo para a seção da usina.


# As estatísticas usam desvio padrão populacional, com denominador N.
def calcular_series(dados_validos, coluna_valor: str = "incremental_inflow_m3s"):  # Resume os cenários de cada estágio sem misturar usinas.
    agrupados = dados_validos.groupby("stage_id", sort=True)[coluna_valor]  # Agrupa somente o valor da usina atual por estágio.
    series = agrupados.agg(mean="mean", std_pop=lambda valores: valores.std(ddof=0), n="count").reset_index()  # Calcula média, sigma populacional e quantidade válida.
    series["menos_sigma"] = series["mean"] - series["std_pop"]  # Calcula o limite inferior de média menos um sigma.
    series["mais_sigma"] = series["mean"] + series["std_pop"]  # Calcula o limite superior de média mais um sigma.
    return series  # Entrega uma linha de estatísticas por estágio, em ordem crescente.


def preparar_historico(historico_validos, estagios: list[int], meses_por_estagio: dict[int, int]):  # Calcula as referências mensais e as repete no horizonte.
    agrupados = historico_validos.groupby("mes", sort=True)["value_m3s"]  # Reúne todos os anos disponíveis do mesmo mês.
    mensais = agrupados.agg(mean="mean", std_pop=lambda valores: valores.std(ddof=0), n="count").reset_index()  # Calcula média, sigma populacional e quantidade histórica.
    mensais["menos_sigma"] = mensais["mean"] - mensais["std_pop"]  # Calcula a faixa histórica inferior de um sigma.
    mensais["mais_sigma"] = mensais["mean"] + mensais["std_pop"]  # Calcula a faixa histórica superior de um sigma.
    estatisticas_por_mes = mensais.set_index("mes").to_dict("index")  # Prepara uma consulta simples pelo mês do stage.
    linhas_estagios = []  # Acumula as estatísticas mensais repetidas em cada stage correspondente.
    distribuicoes = []  # Acumula os valores individuais exigidos pelos boxplots históricos.
    for stage_id in estagios:  # Percorre os stages reais presentes nos cenários desta UHE.
        mes = meses_por_estagio[stage_id]  # Descobre o mês por start_date do stages.json.
        if mes not in estatisticas_por_mes:  # Mantém uma lacuna quando o mês histórico não tem valores.
            lacuna = {  # Cria um ponto vazio para interromper as linhas históricas neste stage.
                "stage_id": stage_id,  # Conserva a posição real do stage no eixo horizontal.
                "mes": mes,  # Conserva o mês correto mesmo sem observações históricas.
                "mes_nome": NOMES_MESES[mes],  # Mantém o nome disponível para o cursor.
                "mean": float("nan"),  # Não inventa uma média histórica.
                "std_pop": float("nan"),  # Não inventa um desvio padrão histórico.
                "n": 0,
                "menos_sigma": float("nan"),  # Interrompe o limite inferior da faixa.
                "mais_sigma": float("nan"),  # Interrompe o limite superior da faixa.
            }  # Fecha a representação explícita da lacuna.
            linhas_estagios.append(lacuna)  # Impede que o Plotly ligue os meses vizinhos através da lacuna.
            continue  # Não preenche com zero, outro mês ou interpolação.
        estatisticas = estatisticas_por_mes[mes]  # Recupera média e sigma do mês correto.
        linhas_estagios.append({"stage_id": stage_id, "mes": mes, "mes_nome": NOMES_MESES[mes], **estatisticas})  # Repete as mesmas referências em anos futuros.
        distribuicao = historico_validos.loc[historico_validos["mes"].eq(mes), ["value_m3s"]].copy()  # Copia todos os valores históricos daquele mês.
        distribuicao["stage_id"] = stage_id  # Posiciona a distribuição ao lado do stage correspondente.
        distribuicao["mes_nome"] = NOMES_MESES[mes]  # Guarda o mês para o tooltip.
        distribuicoes.append(distribuicao)  # Conserva a distribuição completa para concatenação.
    series_historicas = pd.DataFrame(linhas_estagios) if distribuicoes else pd.DataFrame()  # Mantém lacunas entre meses e omite toda a série quando nenhum stage possui histórico.
    historico_por_estagio = pd.concat(distribuicoes, ignore_index=True) if distribuicoes else pd.DataFrame(columns=["value_m3s", "stage_id", "mes_nome"])  # Junta as distribuições sem inventar linhas.
    return historico_por_estagio, series_historicas  # Entrega valores individuais e estatísticas repetidas.


def calcular_somas_moveis_cenarios(
    dados: pd.DataFrame,
    janela: int,
    calendario: dict[int, dict],
) -> pd.DataFrame:
    """Soma a janela no eixo temporal sem misturar scenario_id nem pular estágio."""
    ordem_estagios = [
        stage_id for stage_id, _ in sorted(calendario.items(), key=lambda item: item[1]["ordem"])
    ]
    desconhecidos = sorted(set(dados["stage_id"].astype(int)) - set(ordem_estagios))
    if desconhecidos:
        raise ValueError(
            "O stages.json não contém os stage_id usados nas somas: "
            + ", ".join(str(valor) for valor in desconhecidos[:20])
        )
    valores = dados.copy()
    valores["incremental_inflow_m3s"] = pd.to_numeric(
        valores["incremental_inflow_m3s"], errors="coerce"
    )
    valores.loc[~np.isfinite(valores["incremental_inflow_m3s"]), "incremental_inflow_m3s"] = np.nan
    matriz = valores.pivot(
        index="scenario_id", columns="stage_id", values="incremental_inflow_m3s"
    ).reindex(columns=ordem_estagios)
    somas = matriz.T.rolling(janela, min_periods=janela).sum().T
    somas = somas.loc[:, ordem_estagios[janela - 1:]]
    empilhadas = somas.stack().rename("soma_vazoes_m3s").reset_index()
    empilhadas["stage_id"] = empilhadas["stage_id"].astype(int)
    return empilhadas


def calcular_somas_moveis_historicas(historico: pd.DataFrame, janela: int) -> pd.DataFrame:
    """Soma meses consecutivos, inclusive quando a janela atravessa dezembro e janeiro."""
    if historico.empty:
        return pd.DataFrame(columns=["start_date", "mes", "value_m3s"])
    dados = historico.copy()
    dados["periodo"] = pd.to_datetime(dados["start_date"], errors="coerce").dt.to_period("M")
    if dados["periodo"].isna().any():
        raise ValueError("O histórico possui start_date inválida para a soma móvel.")
    duplicados = dados.duplicated("periodo", keep=False)
    if duplicados.any():
        periodo = dados.loc[duplicados, "periodo"].iloc[0]
        raise ValueError(f"O histórico possui mais de um registro no mês {periodo}.")
    serie = pd.to_numeric(dados.set_index("periodo")["value_m3s"], errors="coerce").sort_index()
    indice = pd.period_range(serie.index.min(), serie.index.max(), freq="M")
    serie = serie.reindex(indice)
    serie = serie.where(np.isfinite(serie))
    somas = serie.rolling(janela, min_periods=janela).sum().dropna()
    return pd.DataFrame({
        "start_date": somas.index.to_timestamp(),
        "mes": somas.index.month.astype(int),
        "value_m3s": somas.to_numpy(dtype=float),
    })


def criar_boxplot_somas(
    dados_somas: pd.DataFrame,
    historico_por_estagio: pd.DataFrame | None,
    rotulo_usina: str,
    janela: int,
    estagios: list[int],
    meses_por_estagio: dict[int, int],
    limites: list[float],
) -> go.Figure:
    """Mostra a distribuição das somas por estágio terminal."""
    ordem = [str(stage_id) for stage_id in estagios]
    passo = max(1, len(ordem) // 12)
    rotulos = ordem[::passo]
    textos = [
        f"{stage_id}<br>{NOMES_MESES[meses_por_estagio[int(stage_id)]]}"
        for stage_id in rotulos
    ]
    st.caption(f"UHE selecionada: {rotulo_usina}")
    figura = go.Figure()
    figura.add_trace(go.Box(
        x=dados_somas["stage_id"].astype(str),
        y=dados_somas["soma_vazoes_m3s"],
        name="Cenários PAR(p)",
        boxpoints="outliers",
        quartilemethod="linear",
        marker=dict(color="rgba(9,182,203,0.65)", size=3),
        line=dict(color=CIANO_FORTE, width=1.4),
        fillcolor="rgba(9,182,203,0.25)",
        hoveron="boxes+points",
        hovertemplate=(
            f"Fonte: Cenários PAR(p)<br>Janela: {janela} estágios<br>"
            f"Usina: {rotulo_usina}<br>Stage terminal: %{{x}}<br>"
            "Soma: %{y:.6g} m³/s<extra></extra>"
        ),
    ))
    if historico_por_estagio is not None and not historico_por_estagio.empty:
        figura.add_trace(go.Box(
            x=historico_por_estagio["stage_id"].astype(str),
            y=historico_por_estagio["value_m3s"],
            customdata=historico_por_estagio[["mes_nome"]].to_numpy(),
            name="Histórico mensal",
            boxpoints="outliers",
            quartilemethod="linear",
            marker=dict(color="rgba(139,92,246,0.65)", size=3),
            line=dict(color=ROXO_FORTE, width=1.4),
            fillcolor="rgba(139,92,246,0.25)",
            hoveron="boxes+points",
            hovertemplate=(
                f"Fonte: Histórico mensal<br>Janela: {janela} meses<br>"
                f"Usina: {rotulo_usina}<br>Stage terminal: %{{x}}<br>"
                "Mês terminal: %{customdata[0]}<br>Soma: %{y:.6g} m³/s<extra></extra>"
            ),
        ))
    figura.add_hline(y=0, line_dash="dot", line_color="#a8b3bc", line_width=1)
    figura.update_xaxes(
        title_text="Estágio terminal (stage_id) e mês",
        type="category", categoryorder="array", categoryarray=ordem,
        tickmode="array", tickvals=rotulos, ticktext=textos,
    )
    figura.update_yaxes(title_text="Soma das vazões na janela (m³/s)", range=limites, zeroline=False)
    figura.update_layout(
        title=f"Distribuição das Somas em {janela} Estágios — {rotulo_usina}",
        height=480,
        showlegend=historico_por_estagio is not None and not historico_por_estagio.empty,
        boxmode="group", margin=dict(l=45, r=20, t=65, b=60),
        hovermode="closest", legend=dict(orientation="h", y=1.02, x=0),
    )
    return figura


def criar_grafico_linhas_somas(
    series: pd.DataFrame,
    series_historicas: pd.DataFrame | None,
    rotulo_usina: str,
    janela: int,
    estagios: list[int],
    limites: list[float],
) -> go.Figure:
    """Mostra média e sigma populacional das mesmas somas usadas no boxplot."""
    x = series["stage_id"].astype(str)
    detalhes = series[["std_pop", "n"]].to_numpy()
    figura = go.Figure()
    figura.add_trace(go.Scatter(
        x=x, y=series["mais_sigma"], mode="lines",
        name="Limite +1σ PAR(p)", showlegend=False,
        line=dict(color="rgba(9,182,203,0.35)", width=0.8),
        hovertemplate="Stage terminal %{x}<br>Média +1σ: %{y:.6g} m³/s<extra></extra>",
    ))
    figura.add_trace(go.Scatter(
        x=x, y=series["menos_sigma"], mode="lines",
        name="±1σ PAR(p)", legendrank=2,
        line=dict(color="rgba(9,182,203,0.35)", width=0.8),
        fill="tonexty", fillcolor="rgba(9,182,203,0.25)",
        hovertemplate="Stage terminal %{x}<br>Média −1σ: %{y:.6g} m³/s<extra></extra>",
    ))
    figura.add_trace(go.Scatter(
        x=x, y=series["mean"], mode="lines",
        name="Média PAR(p)", legendrank=1,
        line=dict(color=CIANO_FORTE, width=3), customdata=detalhes,
        hovertemplate=(
            f"Janela: {janela} estágios<br>Stage terminal %{{x}}<br>"
            "Média: %{y:.6g} m³/s<br>σ populacional: %{customdata[0]:.6g} m³/s"
            "<br>n: %{customdata[1]:.0f}<extra></extra>"
        ),
    ))
    if series_historicas is not None and not series_historicas.empty:
        x_hist = series_historicas["stage_id"].astype(str)
        detalhes_hist = series_historicas[["mes_nome", "std_pop", "n"]].to_numpy()
        figura.add_trace(go.Scatter(
            x=x_hist, y=series_historicas["mais_sigma"], mode="lines",
            name="Limite +1σ histórico", showlegend=False,
            line=dict(color="rgba(139,92,246,0.35)", width=0.8, dash="dot"),
            hovertemplate="Stage terminal %{x}<br>Média histórica +1σ: %{y:.6g} m³/s<extra></extra>",
        ))
        figura.add_trace(go.Scatter(
            x=x_hist, y=series_historicas["menos_sigma"], mode="lines",
            name="±1σ histórico", legendrank=4,
            line=dict(color="rgba(139,92,246,0.35)", width=0.8, dash="dot"),
            fill="tonexty", fillcolor="rgba(139,92,246,0.22)",
            hovertemplate="Stage terminal %{x}<br>Média histórica −1σ: %{y:.6g} m³/s<extra></extra>",
        ))
        figura.add_trace(go.Scatter(
            x=x_hist, y=series_historicas["mean"], mode="lines",
            name="Média histórica", legendrank=3,
            line=dict(color=ROXO_FORTE, width=3, dash="dash"),
            customdata=detalhes_hist,
            hovertemplate=(
                f"Janela: {janela} meses<br>Stage terminal %{{x}}<br>"
                "Mês terminal: %{customdata[0]}<br>Média histórica: %{y:.6g} m³/s"
                "<br>σ populacional: %{customdata[1]:.6g} m³/s"
                "<br>n: %{customdata[2]:.0f}<extra></extra>"
            ),
        ))
    figura.add_hline(y=0, line_dash="dot", line_color="#a8b3bc", line_width=1)
    figura.update_xaxes(
        title_text="Estágio terminal (stage_id)", type="category",
        categoryorder="array", categoryarray=[str(stage_id) for stage_id in estagios],
    )
    figura.update_yaxes(title_text="Soma das vazões na janela (m³/s)", range=limites, zeroline=False)
    figura.update_layout(
        title=f"Média e Desvio Padrão das Somas em {janela} Estágios — {rotulo_usina}",
        height=480, margin=dict(l=45, r=20, t=65, b=60),
        hovermode="x unified", legend=dict(orientation="h", y=1.02, x=0),
    )
    return figura


def mostrar_vazoes_somadas(
    dados: pd.DataFrame,
    historico: pd.DataFrame | None,
    rotulo_usina: str,
    calendario: dict[int, dict],
    mostrar_historico: bool,
) -> None:
    """Renderiza a seção de janelas móveis imediatamente antes da KDE geral."""
    st.subheader("Soma de vazões em janela móvel")
    st.caption(
        "Cada valor soma a vazão do estágio terminal e dos estágios anteriores da janela. "
        "A unidade permanece m³/s; não há conversão para volume."
    )
    janela = st.selectbox(
        "Tamanho da janela", options=[6, 12],
        format_func=lambda valor: f"{valor} estágios",
        key="janela_soma_vazoes",
    )
    somas = calcular_somas_moveis_cenarios(dados, janela, calendario)
    if somas.empty:
        st.info("Não há janelas completas para o tamanho selecionado.")
        return
    estagios = [
        stage_id for stage_id, _ in sorted(calendario.items(), key=lambda item: item[1]["ordem"])
        if stage_id in set(somas["stage_id"].astype(int))
    ]
    meses = {stage_id: calendario[stage_id]["mes"] for stage_id in estagios}
    series = calcular_series(somas, "soma_vazoes_m3s")
    historico_por_estagio = None
    series_historicas = None
    if mostrar_historico and historico is not None and not historico.empty:
        somas_historicas = calcular_somas_moveis_historicas(historico, janela)
        if not somas_historicas.empty:
            historico_por_estagio, series_historicas = preparar_historico(
                somas_historicas, estagios, meses
            )
    minimo = float(somas["soma_vazoes_m3s"].min())
    maximo = float(somas["soma_vazoes_m3s"].max())
    minimo = min(minimo, float(series["menos_sigma"].min()))
    maximo = max(maximo, float(series["mais_sigma"].max()))
    if historico_por_estagio is not None and not historico_por_estagio.empty:
        minimo = min(minimo, float(historico_por_estagio["value_m3s"].min()))
        maximo = max(maximo, float(historico_por_estagio["value_m3s"].max()))
    if series_historicas is not None and not series_historicas.empty:
        minimo = min(minimo, float(series_historicas["menos_sigma"].min()))
        maximo = max(maximo, float(series_historicas["mais_sigma"].max()))
    faixa = limites_y(minimo, maximo)
    boxplot = criar_boxplot_somas(
        somas, historico_por_estagio, rotulo_usina, janela, estagios, meses, faixa
    )
    linhas = criar_grafico_linhas_somas(
        series, series_historicas, rotulo_usina, janela, estagios, faixa
    )
    esquerda, direita = st.columns(2)
    with esquerda:
        st.plotly_chart(boxplot, width="stretch", config={"displaylogo": False})
    with direita:
        st.plotly_chart(linhas, width="stretch", config={"displaylogo": False})


def criar_grafico_linhas(series, series_historicas, rotulo_usina: str, limites: list[float], media_slack=None):  # Desenha médias, faixas de um sigma e a média opcional do slack.
    estagios = series["stage_id"]  # Usa os stage_id reais e ordenados no eixo horizontal.
    detalhes_media = series[["std_pop"]].to_numpy()  # Disponibiliza o sigma populacional no cursor da média PAR(p).
    figura = go.Figure()  # Cria a segunda figura interativa da mesma usina.
    figura.add_trace(go.Scatter(x=estagios, y=series["mais_sigma"], mode="lines", name="Limite +1σ PAR(p)", showlegend=False, line=dict(color="rgba(9,182,203,0.35)", width=0.8), hovertemplate="Stage %{x}<br>Média +1σ PAR(p): %{y:.6g} m³/s<extra></extra>"))  # Desenha o limite superior da faixa PAR(p).
    figura.add_trace(go.Scatter(x=estagios, y=series["menos_sigma"], mode="lines", name="±1σ PAR(p)", legendrank=2, line=dict(color="rgba(9,182,203,0.35)", width=0.8), fill="tonexty", fillcolor="rgba(9,182,203,0.25)", hovertemplate="Stage %{x}<br>Média −1σ PAR(p): %{y:.6g} m³/s<extra></extra>"))  # Preenche somente a faixa de um sigma do PAR(p).
    figura.add_trace(go.Scatter(x=estagios, y=series["mean"], mode="lines", name="Média PAR(p)", legendrank=1, line=dict(color=CIANO_FORTE, width=3), customdata=detalhes_media, hovertemplate="Stage %{x}<br>Média PAR(p): %{y:.6g} m³/s<br>σ PAR(p): %{customdata[0]:.6g} m³/s<extra></extra>"))  # Mostra somente média e sigma PAR(p) no cursor.
    if series_historicas is not None and not series_historicas.empty:  # Acrescenta as referências históricas quando há dados mensais.
        estagios_hist = series_historicas["stage_id"]  # Usa os stages que possuem o mês histórico correspondente.
        detalhes_hist = series_historicas[["mes_nome", "std_pop"]].to_numpy()  # Disponibiliza somente mês e sigma histórico no cursor.
        figura.add_trace(go.Scatter(x=estagios_hist, y=series_historicas["mais_sigma"], mode="lines", name="Limite +1σ histórico", showlegend=False, line=dict(color="rgba(139,92,246,0.35)", width=0.8, dash="dot"), hovertemplate="Stage %{x}<br>Média histórica +1σ: %{y:.6g} m³/s<extra></extra>"))  # Desenha o limite superior da faixa histórica.
        figura.add_trace(go.Scatter(x=estagios_hist, y=series_historicas["menos_sigma"], mode="lines", name="±1σ histórico", legendrank=4, line=dict(color="rgba(139,92,246,0.35)", width=0.8, dash="dot"), fill="tonexty", fillcolor="rgba(139,92,246,0.22)", hovertemplate="Stage %{x}<br>Média histórica −1σ: %{y:.6g} m³/s<extra></extra>"))  # Preenche somente a faixa de um sigma histórico.
        figura.add_trace(go.Scatter(x=estagios_hist, y=series_historicas["mean"], mode="lines", name="Média histórica", legendrank=3, line=dict(color=ROXO_FORTE, width=3, dash="dash"), customdata=detalhes_hist, hovertemplate="Stage %{x}<br>Mês: %{customdata[0]}<br>Média histórica: %{y:.6g} m³/s<br>σ histórico: %{customdata[1]:.6g} m³/s<extra></extra>"))  # Mostra somente mês, média e sigma históricos no cursor.
    if media_slack is not None and not media_slack.empty:  # Acrescenta somente a média do slack quando há valores válidos.
        figura.add_trace(go.Scatter(x=media_slack["stage_id"], y=media_slack["mean_slack"], mode="lines", name="Média do slack", legendrank=5, line=dict(color=VERMELHO_FORTE, width=3.2), hovertemplate="Stage %{x}<br>Média do slack: %{y:.6g} m³/s<extra></extra>"))  # Desenha a linha vermelha sem desvio, mínimo, máximo ou preenchimento.
    figura.add_hline(y=0, line_dash="dot", line_color="#a8b3bc", line_width=1, annotation_text="0 m³/s", annotation_position="top left")  # Mostra a referência de zero.
    figura.update_xaxes(title_text="Estágio (stage_id)", type="linear")  # Mantém os estágios numéricos em ordem crescente.
    figura.update_yaxes(title_text="Vazão incremental (m³/s)", range=limites, zeroline=False)  # Usa uma escala comum para cenários e histórico.
    figura.update_layout(title=f"Média e Desvio Padrão por Estágio — {rotulo_usina}", height=480, margin=dict(l=45, r=20, t=65, b=60), hovermode="x unified", legend=dict(orientation="h", y=1.02, x=0))  # Organiza o título e a legenda simplificados.
    return figura  # Entrega o gráfico complementar da usina.


def calcular_kde(valores, fonte: str, cor: str):  # Desenha a KDE com caudas além dos extremos observados nesta fonte.
    numericos = pd.to_numeric(valores, errors="coerce").to_numpy(dtype=float)  # Rejeita textos ou valores ausentes sem criar zeros.
    numericos = numericos[np.isfinite(numericos)]  # Evita NaN e infinitos somente nesta nova visualização.
    if numericos.size < 2:  # Uma observação não define uma distribuição de densidade.
        return None, f"{fonte}: são necessários pelo menos dois valores finitos para calcular a KDE."
    sigma = float(np.std(numericos, ddof=0))  # Mantém o desvio populacional usado para a largura da KDE.
    tolerancia = 1e-12 * max(1.0, float(np.max(np.abs(numericos))))  # Evita dividir por um desvio quase nulo.
    if not math.isfinite(sigma) or sigma <= tolerancia:  # Não atribui uma forma artificial a dados constantes.
        return None, f"{fonte}: valores constantes ou com desvio-padrão próximo de zero; KDE indisponível."
    largura = sigma * numericos.size ** (-1 / 5)  # Aplica a mesma regra de Scott em cada estágio e fonte.
    if not math.isfinite(largura) or largura <= tolerancia:  # Impede uma KDE instável numericamente.
        return None, f"{fonte}: não foi possível calcular uma largura de suavização estável."
    minimo = float(np.min(numericos))  # Guarda o menor valor observado para marcar no gráfico.
    maximo = float(np.max(numericos))  # Guarda o maior valor observado para marcar no gráfico.
    limite_inferior = minimo - 6 * largura  # Inclui a cauda gaussiana abaixo do mínimo observado.
    limite_superior = maximo + 6 * largura  # Inclui a cauda gaussiana acima do máximo observado.
    quantidade_pontos = min(16001, max(1024, int(math.ceil((limite_superior - limite_inferior) * 5 / largura)) + 1))  # Preserva resolução suficiente em torno dos kernels sem criar uma grade excessiva.
    x = np.linspace(limite_inferior, limite_superior, quantidade_pontos)  # Estende cada fonte até seis larguras de banda além de seus extremos.
    kde = np.zeros_like(x)  # Acumula os kernels gaussianos sem montar uma matriz grande para todo o histórico.
    for valor in numericos:  # Todos os valores recebem o mesmo peso e a mesma largura.
        kde += np.exp(-0.5 * ((x - valor) / largura) ** 2)
    kde /= numericos.size * largura * math.sqrt(2 * math.pi)  # Normaliza a área total da KDE para um.
    area_exibida = float(np.sum((kde[:-1] + kde[1:]) * np.diff(x) / 2))  # Integra numericamente a curva no intervalo efetivamente desenhado.
    if not math.isfinite(area_exibida) or area_exibida <= 0:  # Não apresenta uma curva sem área válida.
        return None, f"{fonte}: não foi possível normalizar a KDE."
    kde /= area_exibida  # Ajusta a discretização para que a área desenhada seja um.
    curva = go.Scatter(x=x, y=kde, mode="lines", name=f"KDE {fonte}", line=dict(color=cor, width=3), hovertemplate="Vazão: %{x:.6g} m³/s<br>Densidade KDE: %{y:.6g}<extra></extra>")
    alturas_extremos = np.interp([minimo, maximo], x, kde)  # Marca os extremos observados sobre a própria curva.
    valores_extremos_formatados = [f"{0.0 if round(valor, 2) == 0 else valor:.2f}".replace(".", ",") for valor in (minimo, maximo)]  # Evita notação científica e o rótulo -0,00.
    textos_extremos = [f"mín. {valores_extremos_formatados[0]}", f"máx. {valores_extremos_formatados[1]}"]  # Mostra duas casas decimais junto dos pontos.
    marcadores = go.Scatter(x=[minimo, maximo], y=alturas_extremos, mode="markers+text", name=f"Extremos — {fonte}", text=textos_extremos, textposition="top center", customdata=valores_extremos_formatados, marker=dict(color=cor, size=10, symbol=["triangle-down", "triangle-up"], line=dict(color="white", width=1)), hovertemplate="%{text} m³/s<br>Vazão observada: %{customdata} m³/s<br>Densidade KDE: %{y:.6g} s/m³<extra></extra>")
    return (curva, marcadores), None  # Entrega a KDE, seus extremos observados ou um aviso quando a fonte não permite calculá-la.


def calcular_assimetria_curtose(valores):  # Calcula momentos padronizados da amostra exibida na distribuição.
    numericos = pd.to_numeric(valores, errors="coerce").to_numpy(dtype=float)  # Converte valores sem transformar ausências em zero.
    numericos = numericos[np.isfinite(numericos)]  # Exclui somente valores não finitos do cálculo estatístico.
    if numericos.size < 2:  # Exige observações suficientes para estimar a forma.
        return None
    media = float(np.mean(numericos))  # Calcula a média da amostra selecionada.
    desvios = numericos - media  # Centraliza cada observação na média.
    m2 = float(np.mean(desvios ** 2))  # Calcula o segundo momento central populacional.
    if not math.isfinite(m2) or m2 <= 0:  # Evita divisão por zero em amostras constantes.
        return {"n": int(numericos.size), "media": media, "m2": m2, "m3": 0.0, "m4": 0.0, "sigma": 0.0, "assimetria": None, "curtose": None}
    m3 = float(np.mean(desvios ** 3))  # Calcula o terceiro momento central para a assimetria.
    m4 = float(np.mean(desvios ** 4))  # Calcula o quarto momento central para a curtose.
    sigma = math.sqrt(m2)  # Obtém o desvio padrão populacional da amostra.
    return {"n": int(numericos.size), "media": media, "m2": m2, "m3": m3, "m4": m4, "sigma": sigma, "assimetria": m3 / sigma ** 3, "curtose": m4 / sigma ** 4 - 3}  # Usa excesso de curtose de Fisher, cujo valor normal é zero.


def resumir_forma_por_estagio(dados_validos, historico_por_estagio):
    """Calcula a forma das distribuições completas, por estágio e fonte."""
    fontes = [("Cenários", dados_validos, "incremental_inflow_m3s")]
    if historico_por_estagio is not None and not historico_por_estagio.empty:
        fontes.append(("Histórico", historico_por_estagio, "value_m3s"))
    resumo = {}
    for fonte, dados_fonte, coluna in fontes:
        por_estagio = {}
        for stage_id, grupo in dados_fonte.groupby("stage_id", sort=True):
            por_estagio[int(stage_id)] = calcular_assimetria_curtose(grupo[coluna])
        resumo[fonte] = por_estagio
    return resumo


def resumir_forma_percentual_por_estagio(
    fatias: pd.DataFrame,
    percentual: int,
    estagios: list[int],
    meses_por_estagio: dict[int, int] | None,
    incluir_historico: bool,
) -> dict:
    """Projeta nos estágios os momentos já calculados para cada fatia."""
    if not {"assimetria", "curtose"}.issubset(fatias.columns):
        raise ValueError("O resumo percentual precisa ser atualizado para incluir assimetria e curtose.")
    selecionadas = fatias.loc[fatias["percentual"].eq(percentual)]

    def medida(registro) -> dict | None:
        if registro is None or int(registro.n_selecionados) == 0:
            return None
        return {
            "n_validos": int(registro.n_validos),
            "n_selecionados": int(registro.n_selecionados),
            "assimetria": float(registro.assimetria) if pd.notna(registro.assimetria) else None,
            "curtose": float(registro.curtose) if pd.notna(registro.curtose) else None,
        }

    cenarios = {
        int(registro.stage_id): medida(registro)
        for registro in selecionadas.loc[selecionadas["fonte"].eq("Cenários")].itertuples(index=False)
    }
    resumo = {"Cenários": {stage_id: cenarios.get(stage_id) for stage_id in estagios}}
    if incluir_historico and meses_por_estagio:
        meses = {
            int(registro.mes_num): medida(registro)
            for registro in selecionadas.loc[selecionadas["fonte"].eq("Histórico")].itertuples(index=False)
        }
        if meses:
            resumo["Histórico"] = {
                stage_id: meses.get(meses_por_estagio[stage_id]) for stage_id in estagios
            }
    return resumo


def criar_grafico_forma_por_estagio(resumo, medida: str, estagios: list[int],
                                   meses_por_estagio: dict[int, int], rotulo_usina: str,
                                   percentual: int | None = None):
    """Exibe a curtose ou assimetria dos dados gerais ou de uma fatia."""
    titulo = "Curtose de Fisher" if medida == "curtose" else "Assimetria"
    figura = go.Figure()
    for fonte, cor in (("Cenários", CIANO_FORTE), ("Histórico", ROXO_FORTE)):
        if fonte not in resumo:
            continue
        valores = [resumo[fonte].get(int(stage_id)) for stage_id in estagios]
        alturas = [resultado[medida] if resultado is not None else None for resultado in valores]
        if not any(valor is not None for valor in alturas):
            continue
        figura.add_trace(go.Bar(
            x=[str(stage_id) for stage_id in estagios],
            y=alturas,
            name=fonte,
            marker_color=cor,
            customdata=[
                [NOMES_MESES[meses_por_estagio[int(stage_id)]] if fonte == "Histórico" and meses_por_estagio else "—",
                 resultado.get("n_validos", resultado.get("n", 0)) if resultado is not None else 0,
                 resultado.get("n_selecionados") if resultado is not None else None]
                for stage_id, resultado in zip(estagios, valores)
            ],
            hovertemplate=(
                f"UHE: {rotulo_usina}<br>Fonte: {fonte}<br>Estágio: %{{x}}<br>"
                + ("Mês: %{customdata[0]}<br>" if fonte == "Histórico" else "")
                + (f"Fatia: p{percentual}%<br>" if percentual is not None else "")
                + "Observações válidas: %{customdata[1]}<br>"
                + ("Observações selecionadas: %{customdata[2]}<br>" if percentual is not None else "")
                + f"{titulo}: %{{y:.4f}}<extra></extra>"
            ),
        ))
    passo = max(1, len(estagios) // 12)
    rotulados = estagios[::passo]
    figura.add_hline(y=0, line_dash="dot", line_color="#a8b3bc", line_width=1)
    figura.update_xaxes(
        title_text="Estágio (stage_id) e mês", type="category",
        categoryorder="array", categoryarray=[str(stage_id) for stage_id in estagios],
        tickmode="array", tickvals=[str(stage_id) for stage_id in rotulados],
        ticktext=[
            f"{stage_id}<br>{NOMES_MESES[meses_por_estagio[int(stage_id)]]}"
            if meses_por_estagio else str(stage_id) for stage_id in rotulados
        ],
    )
    figura.update_yaxes(title_text=titulo, zeroline=False)
    figura.update_layout(
        title=f"{titulo} por Estágio — {rotulo_usina}" + (f" — p{percentual}%" if percentual is not None else ""),
        height=360, barmode="group", bargap=0.18,
        showlegend=any(serie.name == "Histórico" for serie in figura.data),
        margin=dict(l=45, r=20, t=65, b=60),
        legend=dict(orientation="h", y=1.02, x=0),
    )
    return figura


def mostrar_box_assimetria_curtose(dados_estagio, historico_estagio):  # Mostra métricas dinâmicas para as fontes do estágio selecionado.
    fontes = [("cenários", dados_estagio["incremental_inflow_m3s"])]  # Calcula primeiro a forma dos cenários exibidos na KDE.
    if historico_estagio is not None and not historico_estagio.empty:  # Inclui o histórico somente quando está disponível e habilitado.
        fontes.append(("histórico", historico_estagio["value_m3s"]))  # Calcula o mês histórico associado ao estágio selecionado.
    resultados = [(nome, calcular_assimetria_curtose(valores)) for nome, valores in fontes]  # Mantém cada distribuição estatisticamente separada.
    colunas = st.columns(2 * len(resultados))  # Cria dois indicadores para cada fonte, no estilo dos cartões de métricas existentes.
    for indice, (nome, resultado) in enumerate(resultados):  # Preenche os cartões na mesma ordem das fontes plotadas.
        if resultado is None:  # Informa quando não existem observações suficientes.
            colunas[2 * indice].metric(f"Assimetria — {nome}", "indisponível")
            colunas[2 * indice + 1].metric(f"Curtose de Fisher — {nome}", "indisponível")
            continue
        assimetria = resultado["assimetria"]  # Recupera a medida de inclinação da distribuição.
        curtose = resultado["curtose"]  # Recupera o excesso de curtose relativo à normal.
        colunas[2 * indice].metric(f"Assimetria — {nome} (n={resultado['n']})", "indisponível" if assimetria is None else f"{assimetria:.4f}")
        colunas[2 * indice + 1].metric(f"Curtose de Fisher — {nome}", "indisponível" if curtose is None else f"{curtose:.4f}")


def criar_grafico_distribuicao(dados_estagio, historico_estagio, rotulo_usina: str, stage_id: int, mes_nome: str | None, percentual: int | None = None):  # Sobrepõe as distribuições da seleção atual.
    fontes = [("cenários PAR(p)", CIANO_FORTE, dados_estagio["incremental_inflow_m3s"])]  # Mantém os cenários sem filtragem de outliers ou negativos.
    if historico_estagio is not None and not historico_estagio.empty:  # Reutiliza a associação mês/estágio do boxplot.
        fontes.append(("histórico mensal", ROXO_FORTE, historico_estagio["value_m3s"]))
    figura = go.Figure()  # Usa a mesma biblioteca e as mesmas interações dos demais gráficos.
    avisos = []
    for fonte, cor, valores in fontes:
        curvas, aviso = calcular_kde(valores, fonte, cor)
        if curvas is not None:
            figura.add_trace(curvas[0])
            figura.add_trace(curvas[1])
        if aviso:
            avisos.append(aviso)
    if not figura.data:  # Comunica dados insuficientes sem deixar um gráfico vazio.
        return None, avisos
    linhas_kde = [trace for trace in figura.data if trace.mode == "lines"]  # Usa somente as linhas para definir o domínio completo das caudas.
    limite_inferior = min(float(curva.x[0]) for curva in linhas_kde)  # Inclui a fonte que alcançar o menor valor.
    limite_superior = max(float(curva.x[-1]) for curva in linhas_kde)  # Inclui a fonte que alcançar o maior valor.
    referencia_mes = f" — {mes_nome}" if mes_nome else ""
    figura.update_xaxes(title_text="Vazão incremental (m³/s)", range=[limite_inferior, limite_superior], autorange=False)  # Exibe a união dos intervalos das fontes plotadas.
    figura.update_yaxes(title_text="Densidade (s/m³)", rangemode="tozero")
    referencia_percentual = f" — p{percentual}%" if percentual is not None else ""
    figura.update_layout(title=f"Distribuição das Vazões{referencia_percentual} — {rotulo_usina} — Estágio {stage_id}{referencia_mes}", height=480, margin=dict(l=45, r=20, t=65, b=60), hovermode="closest", legend=dict(orientation="h", y=1.02, x=0))
    return figura, avisos


def mostrar_comparacao_ks(dados_estagio, historico_estagio, rotulo_usina: str, periodo: str) -> None:
    """Mostra as duas ECDFs e o D calculado sobre os mesmos valores da KDE geral."""
    st.subheader("Kolmogorov–Smirnov — Cenários × Histórico")
    if historico_estagio is None or historico_estagio.empty:
        st.info("Não há histórico do mês selecionado para comparar com os cenários.")
        return
    resultado = calcular_distancia_ks(
        dados_estagio["incremental_inflow_m3s"], historico_estagio["value_m3s"]
    )
    if resultado["d"] is None:
        st.info(f"Comparação KS indisponível: {resultado['situacao']}.")
        return

    d = resultado["d"]
    colunas = st.columns(4)
    colunas[0].metric("Distância KS (D)", f"{d:.6f}")
    colunas[1].metric("Diferença máxima (p.p.)", f"{100 * d:.2f}")
    colunas[2].metric(
        "Vazão da maior diferença (m³/s)",
        "—" if resultado["x_max"] is None else formatar_vazao_percentual(resultado["x_max"]),
    )
    colunas[3].metric(
        "Valores válidos: cenários / histórico",
        f"{resultado['cenarios_validos']:,} / {resultado['historico_valido']:,}".replace(",", "."),
    )

    x = resultado["valores_x"]
    amplitude = float(x[-1] - x[0])
    margem = 0.03 * amplitude if amplitude > 0 else max(abs(float(x[0])) * 0.05, 1e-6)
    x_desenho = np.r_[x[0] - margem, x, x[-1] + margem]
    figura = go.Figure()
    for nome, cor, acumulados, contagens, total in (
        ("Cenários", CIANO_FORTE, resultado["acumulados_cenarios"],
         resultado["contagens_cenarios"], resultado["cenarios_validos"]),
        ("Histórico", ROXO_FORTE, resultado["acumulados_historico"],
         resultado["contagens_historico"], resultado["historico_valido"]),
    ):
        y_desenho = np.r_[0.0, acumulados, 1.0]
        textos = [f"{nome}: antes do menor valor observado — 0/{total} (0%)"]
        textos.extend(
            f"{nome}<br>Vazão ≤ {valor:.4f} m³/s<br>"
            f"Acumulado: {int(contagem)}/{total} ({100 * acumulado:.2f}%)"
            for valor, contagem, acumulado in zip(x, contagens, acumulados)
        )
        textos.append(f"{nome}: após o maior valor observado — {total}/{total} (100%)")
        figura.add_trace(go.Scatter(
            x=x_desenho, y=y_desenho, mode="lines", line_shape="hv",
            line=dict(color=cor, width=2.8), name=nome, text=textos,
            hovertemplate="%{text}<extra></extra>",
        ))
    if d > 0:
        figura.add_trace(go.Scatter(
            x=[resultado["x_max"], resultado["x_max"]],
            y=[resultado["acumulado_cenarios_x"], resultado["acumulado_historico_x"]],
            mode="lines+markers", line=dict(color="#374151", width=3, dash="dot"),
            marker=dict(color="#374151", size=8), name=f"Maior distância: {100 * d:.2f} p.p.",
            hovertemplate=(
                f"Vazão: {resultado['x_max']:.4f} m³/s<br>"
                f"Distância KS: {d:.6f} ({100 * d:.2f} p.p.)<extra></extra>"
            ),
        ))
    figura.update_layout(
        title=f"Distribuições acumuladas — {rotulo_usina} — {periodo}",
        xaxis=dict(title="Vazão incremental (m³/s)", range=[float(x_desenho[0]), float(x_desenho[-1])]),
        yaxis=dict(title="Percentual acumulado", range=[0, 1.02], tickformat=".0%"),
        height=480, hovermode="closest", margin=dict(l=45, r=20, t=65, b=60),
        legend=dict(orientation="h", y=1.02, x=0),
    )
    st.plotly_chart(figura, width="stretch", config={"displaylogo": False})
    if resultado["situacao"] != "calculado":
        st.warning("A distância foi calculada com apenas um valor em uma das amostras; interprete-a com cautela.")
    st.caption("D é a maior diferença entre as frações acumuladas; é uma comparação descritiva, sem valor-p.")


def mostrar_distribuicao_por_estagio(
    dados,
    historico_por_estagio,
    rotulo_usina: str,
    estagios_disponiveis: list[int],
    meses_por_estagio: dict[int, int] | None,
    chave_seletor: str,
    percentual: int | None = None,
    historico_solicitado: bool = False,
    calendario_estagios: dict[int, dict] | None = None,
) -> None:
    """Exibe seletor, indicadores e KDE geral ou da fatia percentual escolhida."""
    if not estagios_disponiveis:
        st.info("Não há estágios com valores suficientes para esta distribuição.")
        return
    stage_id = st.selectbox(
        "Selecione o estágio para comparar as distribuições",
        options=estagios_disponiveis,
        key=chave_seletor,
        format_func=lambda valor: rotulo_estagio_mes_ano(valor, calendario_estagios),
    )
    dados_estagio = dados.loc[
        dados["stage_id"].eq(stage_id), ["incremental_inflow_m3s"]
    ].copy()
    historico_estagio = (
        historico_por_estagio.loc[historico_por_estagio["stage_id"].eq(stage_id)].copy()
        if historico_por_estagio is not None else None
    )
    if percentual is not None:
        valores_cenarios = selecionar_menores_valores(
            dados_estagio["incremental_inflow_m3s"], percentual
        )
        dados_estagio = pd.DataFrame({"incremental_inflow_m3s": valores_cenarios})
        if historico_estagio is not None and not historico_estagio.empty:
            valores_historicos = selecionar_menores_valores(
                historico_estagio["value_m3s"], percentual
            )
            historico_estagio = pd.DataFrame({"value_m3s": valores_historicos})
    if historico_solicitado and (
        historico_estagio is None or historico_estagio.empty
    ):
        st.info("Não há valores históricos para o mês correspondente a este estágio; a distribuição mostrará apenas os cenários.")
    mes_nome = NOMES_MESES[meses_por_estagio[stage_id]] if meses_por_estagio else None
    mostrar_box_assimetria_curtose(dados_estagio, historico_estagio)
    distribuicao, avisos = criar_grafico_distribuicao(
        dados_estagio, historico_estagio, rotulo_usina, stage_id, mes_nome, percentual
    )
    for aviso in avisos:
        st.info(aviso)
    if distribuicao is not None:
        st.plotly_chart(distribuicao, width="stretch", config={"displaylogo": False})
    if percentual is None and historico_solicitado:
        mostrar_comparacao_ks(
            dados_estagio, historico_estagio, rotulo_usina,
            rotulo_estagio_mes_ano(stage_id, calendario_estagios),
        )


def mostrar_usina(
    caminho: str,
    hydro_id: int,
    rotulo_usina: str,
    mostrar_historico: bool = False,
    assinatura_historico: tuple | None = None,
    meses_por_estagio: dict[int, int] | None = None,
    mostrar_slack: bool = False,
    assinatura_cenarios: tuple | None = None,
    calendario_estagios: dict[int, dict] | None = None,
    assinatura_stages: tuple | None = None,
    assinatura_cadastro: tuple | None = None,
) -> None:  # Consulta pelo ID e compara as fontes opcionais solicitadas.
    st.subheader(f"Usina: {rotulo_usina}")  # Exibe nome e identificador acima do resumo da usina.
    with st.spinner(f"Consultando {rotulo_usina}..."):  # Informa qual usina está sendo consultada.
        dados = consultar_usina_em_cache(assinatura_cenarios, hydro_id) if assinatura_cenarios else consultar_usina(caminho, hydro_id)  # Reusa a UHE nas trocas de percentual.
    validar_usina(dados, hydro_id)  # Impede mistura de cenários, estágios, nós ou usinas.

    # A contagem de cenários inclui também registros cujo valor de vazão esteja ausente.
    cenarios_por_estagio = dados.groupby("stage_id")["scenario_id"].nunique().sort_index()  # Conta cenários distintos em cada estágio.
    if cenarios_por_estagio.nunique() > 1:  # Detecta estágios com quantidades diferentes de cenários.
        menor_contagem = int(cenarios_por_estagio.min())  # Descobre a menor quantidade presente em um estágio.
        maior_contagem = int(cenarios_por_estagio.max())  # Descobre a maior quantidade presente em um estágio.
        st.warning(f"A quantidade de cenários varia entre estágios desta usina: de {menor_contagem} a {maior_contagem}. Nenhum cenário foi preenchido artificialmente.")  # Explica a diferença.
        with st.expander("Ver quantidade de cenários por estágio"):  # Oferece os detalhes apenas quando desejados.
            st.dataframe(cenarios_por_estagio.rename("cenarios").reset_index(), hide_index=True, width="stretch")  # Mostra a contagem de cada estágio.

    # Valores nulos ou NaN são informados e excluídos apenas da matemática que exige números.
    coluna_vazao = "incremental_inflow_m3s"  # Identifica a coluna original que alimenta ambos os gráficos.
    quantidade_nulos = int(dados[coluna_vazao].isna().sum())  # Conta vazões sem valor numérico, sem transformá-las em zero.
    dados_validos = dados.dropna(subset=[coluna_vazao])  # Mantém todos os valores numéricos, inclusive negativos e outliers.
    metricas = st.columns(4)  # Reserva espaço para um resumo compacto da usina.
    metricas[0].metric("Cenários encontrados", f"{dados['scenario_id'].nunique():,}".replace(",", "."))  # Mostra cenários distintos da usina.
    metricas[1].metric("Estágios encontrados", dados["stage_id"].nunique())  # Mostra estágios distintos da usina.
    if not dados_validos.empty:  # Mostra extremos somente quando existe vazão numérica.
        minimo = float(dados_validos[coluna_vazao].min())  # Obtém o menor valor real, mesmo que negativo.
        maximo = float(dados_validos[coluna_vazao].max())  # Obtém o maior valor real da mesma usina.
        metricas[2].metric("Menor vazão (m³/s)", formatar_vazao_percentual(minimo))  # Arredonda a exibição para duas casas, sem expoente nem zero negativo.
        metricas[3].metric("Maior vazão (m³/s)", formatar_vazao_resumo(maximo))  # Mantém a mesma apresentação compacta para o máximo.
    else:  # Trata uma usina cuja vazão está ausente em todos os registros.
        metricas[2].metric("Menor vazão (m³/s)", "—")  # Evita inventar um valor mínimo.
        metricas[3].metric("Maior vazão (m³/s)", "—")  # Evita inventar um valor máximo.
    if quantidade_nulos:  # Informa quando os gráficos precisaram desconsiderar valores ausentes.
        st.warning(f"Valores nulos ou NaN de vazão nesta usina: {quantidade_nulos}. Eles não foram substituídos; os gráficos usam somente valores numéricos disponíveis.")  # Explica a limitação.
    if dados_validos.empty:  # Evita gráficos sem dados numéricos.
        st.info("Esta usina não possui vazões numéricas para os gráficos.")  # Informa por que não há gráficos.
        return  # Encerra apenas a seção desta usina.

    # Os dois gráficos usam exatamente dados_validos, sem filtro de negativos ou de outliers.
    estagios = sorted(dados_validos["stage_id"].unique().tolist())  # Organiza os estágios que têm valores numéricos.
    series = calcular_series(dados_validos)  # Calcula as três linhas sobre os mesmos registros.
    historico_por_estagio = None  # Mantém o boxplot original quando a comparação está desligada.
    series_historicas = None  # Mantém apenas as linhas PAR(p) quando não há histórico habilitado.
    historico_percentuais = None  # Guarda o mês original para os novos resumos, sem repetir os ciclos.
    historico_janelas = None  # Conserva datas e valores para as janelas móveis históricas.
    dados_slack = None  # Mantém os gráficos originais quando a opção de slack está desligada.
    media_slack = None  # Evita criar uma linha vazia quando o slack não foi solicitado.
    if mostrar_historico and assinatura_historico and meses_por_estagio:  # Consulta o histórico somente após validação dos arquivos auxiliares.
        historico = consultar_historico(*assinatura_historico, hydro_id)  # Lê somente o histórico desta UHE.
        historico_janelas = historico.copy()
        quantidade_nulos_hist = int(historico["value_m3s"].isna().sum())  # Conta vazões históricas ausentes sem convertê-las em zero.
        historico_validos = historico.dropna(subset=["value_m3s"])  # Preserva todos os valores numéricos, inclusive negativos e outliers.
        historico_percentuais = historico_validos  # A rotina percentual filtra também infinitos.
        if quantidade_nulos_hist:  # Informa valores excluídos apenas das operações numéricas.
            st.warning(f"Valores históricos nulos ou NaN nesta usina: {quantidade_nulos_hist}. Eles não foram substituídos.")  # Explica a regra aplicada.
        if historico_validos.empty:  # Trata UHE ausente ou sem qualquer valor histórico válido.
            st.info("Não foram encontrados dados históricos para esta usina.")  # Mantém os gráficos PAR(p) disponíveis.
        else:  # Prepara a comparação apenas quando há valores históricos válidos.
            meses_necessarios = sorted({meses_por_estagio[stage_id] for stage_id in estagios})  # Descobre os meses usados pelo horizonte desta UHE.
            meses_disponiveis = set(historico_validos["mes"].astype(int).unique().tolist())  # Descobre os meses históricos realmente presentes.
            meses_ausentes = [NOMES_MESES[mes] for mes in meses_necessarios if mes not in meses_disponiveis]  # Traduz meses sem dados para o aviso.
            if meses_ausentes:  # Não inventa valores para um mês histórico ausente.
                st.warning(f"Sem dados históricos válidos para: {', '.join(meses_ausentes)}. Nesses stages será mostrado apenas o PAR(p).")  # Explica as lacunas.
            historico_por_estagio, series_historicas = preparar_historico(historico_validos, estagios, meses_por_estagio)  # Repete cada distribuição no mês correspondente.
            minimo = min(minimo, float(historico_validos["value_m3s"].min()))  # Inclui os menores outliers históricos na escala comum.
            maximo = max(maximo, float(historico_validos["value_m3s"].max()))  # Inclui os maiores outliers históricos na escala comum.
        del historico, historico_validos  # Libera os registros históricos antes de desenhar os gráficos.
    if mostrar_slack:  # Consulta o slack somente quando a caixa independente está marcada.
        dados_slack = consultar_slack(caminho, hydro_id)  # Lê todos os cenários válidos e a média calculada no DuckDB.
        if dados_slack.empty:  # Trata uma UHE sem nenhum valor válido de slack.
            st.info("Não foram encontrados valores válidos de slack para esta usina.")  # Mantém disponíveis os gráficos das outras fontes.
        else:  # Prepara a linha e a escala apenas quando existem valores de slack.
            media_slack = dados_slack[["stage_id", "mean_slack"]].drop_duplicates(subset=["stage_id"]).sort_values("stage_id")  # Retém uma média por estágio já calculada pelo DuckDB.
            minimo = min(minimo, float(dados_slack[COLUNA_SLACK].min()))  # Inclui o menor slack real na escala comum.
            maximo = max(maximo, float(dados_slack[COLUNA_SLACK].max()))  # Inclui o maior slack real na escala comum.
    minimo = min(minimo, float(series["menos_sigma"].min()))  # Inclui o limite inferior da faixa PAR(p) na escala comum.
    maximo = max(maximo, float(series["mais_sigma"].max()))  # Inclui o limite superior da faixa PAR(p) na escala comum.
    if series_historicas is not None and not series_historicas.empty:  # Confere se a faixa histórica foi calculada.
        minimo = min(minimo, float(series_historicas["menos_sigma"].min()))  # Inclui o limite inferior histórico na escala comum.
        maximo = max(maximo, float(series_historicas["mais_sigma"].max()))  # Inclui o limite superior histórico na escala comum.
    faixa_y = limites_y(minimo, maximo)  # Define uma escala comum que inclui extremos reais e zero.
    boxplot = criar_boxplot(dados_validos, historico_por_estagio, rotulo_usina, estagios, meses_por_estagio or {}, faixa_y, dados_slack=dados_slack)  # Constrói as distribuições completas habilitadas.
    linhas = criar_grafico_linhas(series, series_historicas, rotulo_usina, faixa_y, media_slack=media_slack)  # Constrói as médias e apenas as faixas de um sigma previstas.
    resumo_forma = resumir_forma_por_estagio(dados_validos, historico_por_estagio)
    grafico_curtose = criar_grafico_forma_por_estagio(resumo_forma, "curtose", estagios, meses_por_estagio or {}, rotulo_usina)
    grafico_assimetria = criar_grafico_forma_por_estagio(resumo_forma, "assimetria", estagios, meses_por_estagio or {}, rotulo_usina)
    esquerda, direita = st.columns(2)  # Coloca os gráficos da mesma usina lado a lado quando há largura.
    with esquerda:  # Reserva a coluna esquerda ao boxplot da usina atual.
        st.plotly_chart(boxplot, width="stretch", config={"displaylogo": False})  # Exibe caixas, outliers, zoom e cursor.
        st.plotly_chart(grafico_curtose, width="stretch", config={"displaylogo": False})
    with direita:  # Reserva a coluna direita à série estatística da mesma usina.
        st.plotly_chart(linhas, width="stretch", config={"displaylogo": False})  # Exibe as médias e as faixas preenchidas de um sigma.
        st.plotly_chart(grafico_assimetria, width="stretch", config={"displaylogo": False})
    if calendario_estagios:
        mostrar_vazoes_somadas(
            dados, historico_janelas, rotulo_usina, calendario_estagios, mostrar_historico
        )
    else:
        st.subheader("Soma de vazões em janela móvel")
        st.info("Selecione o stages.json para calcular corretamente as janelas de 6 e 12 estágios.")
    area_distribuicao = st.container()  # Reserva a posição da KDE sem mudar a ordem dos cálculos.
    mostrar_divisao_visual("Distribuição dos menores valores por percentual")
    st.caption("p5% usa os 5% menores valores de cada estágio ou mês; as fatias são acumuladas.")
    percentual_selecionado = st.selectbox(
        "Percentual dos menores valores",
        options=PERCENTUAIS,
        index=PERCENTUAIS.index(5),
        format_func=lambda percentual: f"p{percentual}%",
        key="percentual_graficos",
    )
    percentuais_selecionados = [percentual_selecionado]
    if assinatura_cenarios:
        resumo_percentuais = carregar_resumo_percentuais(
            assinatura_cenarios,
            assinatura_historico if mostrar_historico else None,
            assinatura_stages,
            hydro_id,
            rotulo_usina,
            VERSAO_RESUMO_PERCENTUAIS,
        )
    else:
        resumo_percentuais = gerar_resumo_percentuais(
            dados, historico_percentuais if mostrar_historico else None,
            hydro_id, rotulo_usina,
        )
    estagios_percentuais = sorted(int(valor) for valor in dados["stage_id"].unique())
    box_percentuais, linhas_percentuais = criar_graficos_percentuais(
        resumo_percentuais,
        percentuais_selecionados,
        estagios_percentuais,
        meses_por_estagio,
        rotulo_usina,
        mostrar_historico,
    )
    fatias_exibidas = filtrar_percentuais(
        resumo_percentuais, percentuais_selecionados, [JANELAS[0]]
    )
    if not mostrar_historico:
        fatias_exibidas = fatias_exibidas.loc[fatias_exibidas["fonte"].eq("Cenários")]
    elif meses_por_estagio:
        meses_exibidos = set(meses_por_estagio.values())
        fatias_exibidas = fatias_exibidas.loc[
            fatias_exibidas["fonte"].eq("Cenários")
            | fatias_exibidas["mes_num"].isin(meses_exibidos)
        ]
    mostrar_indicadores_percentuais(fatias_exibidas, percentuais_selecionados)
    forma_percentual = resumir_forma_percentual_por_estagio(
        fatias_exibidas, percentual_selecionado, estagios_percentuais,
        meses_por_estagio, mostrar_historico,
    )
    grafico_curtose_percentual = criar_grafico_forma_por_estagio(
        forma_percentual, "curtose", estagios_percentuais,
        meses_por_estagio or {}, rotulo_usina, percentual_selecionado,
    )
    grafico_assimetria_percentual = criar_grafico_forma_por_estagio(
        forma_percentual, "assimetria", estagios_percentuais,
        meses_por_estagio or {}, rotulo_usina, percentual_selecionado,
    )
    caixas_colapsadas = (
        fatias_exibidas["n_selecionados"].gt(0)
        & fatias_exibidas["q1"].eq(fatias_exibidas["q3"])
    )
    if caixas_colapsadas.any():
        st.caption(
            "Quando Q1 e Q3 coincidem, a caixa tem altura zero. "
            "Um traço colorido marca sua posição; os pontos separados são outliers da mesma fatia."
        )
    coluna_box, coluna_linhas = st.columns(2)
    with coluna_box:
        st.plotly_chart(box_percentuais, width="stretch", config={"displaylogo": False})
        if grafico_curtose_percentual.data:
            st.plotly_chart(grafico_curtose_percentual, width="stretch", config={"displaylogo": False})
        else:
            st.info("Curtose de Fisher indisponível nesta fatia: são necessárias ao menos duas observações distintas por grupo.")
    with coluna_linhas:
        st.plotly_chart(linhas_percentuais, width="stretch", config={"displaylogo": False})
        if grafico_assimetria_percentual.data:
            st.plotly_chart(grafico_assimetria_percentual, width="stretch", config={"displaylogo": False})
        else:
            st.info("Assimetria indisponível nesta fatia: são necessárias ao menos duas observações distintas por grupo.")
    st.subheader(f"Menores somas de vazões para p{percentual_selecionado}%")
    st.caption(
        "Primeiro são calculadas as somas completas de cada cenário. "
        f"Depois são selecionados os p{percentual_selecionado}% menores totais "
        "independentemente em cada estágio terminal."
    )
    if calendario_estagios:
        janela_percentual = st.selectbox(
            "Tamanho da janela para os menores totais",
            options=[6, 12],
            format_func=lambda valor: f"{valor} estágios",
            key="janela_soma_vazoes_percentual",
        )
        rotulo_janela = JANELAS[1] if janela_percentual == 6 else JANELAS[2]
        fatias_somas = filtrar_percentuais(
            resumo_percentuais, percentuais_selecionados, [rotulo_janela]
        )
        if not mostrar_historico:
            fatias_somas = fatias_somas.loc[fatias_somas["fonte"].eq("Cenários")]
        estagios_somas = [
            stage_id for stage_id, _ in sorted(
                calendario_estagios.items(), key=lambda item: item[1]["ordem"]
            )
            if (
                fatias_somas["fonte"].eq("Cenários")
                & fatias_somas["stage_id"].eq(stage_id)
            ).any()
        ]
        box_somas_percentuais, linhas_somas_percentuais = criar_graficos_percentuais(
            fatias_somas,
            percentuais_selecionados,
            estagios_somas,
            meses_por_estagio,
            rotulo_usina,
            mostrar_historico,
            janela_analise=rotulo_janela,
        )
        caixas_somas_colapsadas = (
            fatias_somas["n_selecionados"].gt(0)
            & fatias_somas["q1"].eq(fatias_somas["q3"])
        )
        if caixas_somas_colapsadas.any():
            st.caption(
                "Quando Q1 e Q3 coincidem, a caixa tem altura zero. "
                "O traço colorido marca sua posição."
            )
        coluna_box_somas, coluna_linhas_somas = st.columns(2)
        with coluna_box_somas:
            if box_somas_percentuais.data:
                st.plotly_chart(
                    box_somas_percentuais, width="stretch",
                    config={"displaylogo": False},
                )
            else:
                st.info("Não há somas completas para esta seleção.")
        with coluna_linhas_somas:
            if linhas_somas_percentuais.data:
                st.plotly_chart(
                    linhas_somas_percentuais, width="stretch",
                    config={"displaylogo": False},
                )
            else:
                st.info("Não há médias de somas disponíveis para esta seleção.")
    else:
        st.info("Selecione o stages.json para calcular as menores somas de 6 e 12 estágios.")
    st.subheader(f"Distribuição para p{percentual_selecionado}%")
    st.caption(
        f"A curva utiliza somente os p{percentual_selecionado}% menores valores "
        "do estágio e do mês histórico correspondentes."
    )
    linhas_cenarios_percentuais = fatias_exibidas.loc[
        fatias_exibidas["fonte"].eq("Cenários")
        & fatias_exibidas["n_selecionados"].gt(0)
        & fatias_exibidas["stage_id"].notna()
    ]
    estagios_distribuicao_percentual = sorted(
        int(valor) for valor in linhas_cenarios_percentuais["stage_id"].unique()
    )
    mostrar_distribuicao_por_estagio(
        dados,
        historico_por_estagio,
        rotulo_usina,
        estagios_distribuicao_percentual,
        meses_por_estagio,
        "estagio_distribuicao_percentual",
        percentual=percentual_selecionado,
        historico_solicitado=mostrar_historico,
        calendario_estagios=calendario_estagios,
    )
    with area_distribuicao:
        mostrar_distribuicao_por_estagio(
            dados,
            historico_por_estagio,
            rotulo_usina,
            sorted(int(valor) for valor in dados["stage_id"].unique()),
            meses_por_estagio,
            "estagio_distribuicao",
            historico_solicitado=mostrar_historico,
            calendario_estagios=calendario_estagios,
        )
    mostrar_divisao_visual("Funções de correlação")
    mostrar_autocorrelacao_usina(
        assinatura_cenarios, assinatura_stages, hydro_id, rotulo_usina,
        calendario_estagios,
    )
    mostrar_correlacao_espacial_usina(
        assinatura_cenarios, assinatura_cadastro, assinatura_stages,
        hydro_id, rotulo_usina, calendario_estagios,
        sorted(int(valor) for valor in dados["stage_id"].unique()),
    )
    mostrar_autocorrelacao_anual_usina(
        assinatura_cenarios, assinatura_cadastro, assinatura_stages,
        hydro_id, rotulo_usina,
    )
    st.divider()  # Encerra visualmente a seção da usina.
    del dados, dados_validos, boxplot, linhas, series, historico_por_estagio, series_historicas, dados_slack, media_slack  # Libera referências intermediárias antes da próxima usina.


@st.cache_data(show_spinner=False, max_entries=2)
def carregar_relatorio_estatistico(
    assinatura_cenarios: tuple,
    assinatura_historico: tuple,
    assinatura_cadastro: tuple,
    assinatura_stages: tuple,
):
    """Calcula a tabela completa uma vez para cada versão das quatro fontes."""
    ler_metadados(*assinatura_cenarios)  # Confere o esquema do consolidado antes das agregações.
    validar_arquivo_historico(*assinatura_historico)  # Confere o esquema e as datas históricas.
    nomes_por_id = carregar_cadastro_hidros(*assinatura_cadastro)  # Usa o mesmo cadastro da primeira aba.
    carregar_calendario_dos_estagios(*assinatura_stages)
    return gerar_relatorio(
        assinatura_cenarios[0], assinatura_historico[0],
        nomes_por_id, assinatura_stages[0],
    )


@st.cache_data(show_spinner=False, max_entries=4)
def preparar_xlsx_relatorio(relatorio_filtrado: pd.DataFrame) -> bytes:
    """Reaproveita o XLSX enquanto as linhas visíveis não mudarem."""
    return exportar_xlsx(relatorio_filtrado)


@st.cache_data(show_spinner=False, max_entries=4)
def _carregar_resumo_percentuais_em_cache(
    assinatura_cenarios: tuple,
    assinatura_historico: tuple | None,
    assinatura_stages: tuple | None,
    hydro_id: int,
    nome_usina: str,
    versao_calculo: int,
) -> pd.DataFrame:
    """Calcula todas as fatias uma vez por versão das fontes e por UHE."""
    dados = consultar_usina_em_cache(assinatura_cenarios, hydro_id)
    validar_usina(dados, hydro_id)
    historico = (
        consultar_historico(*assinatura_historico, hydro_id)
        if assinatura_historico else None
    )
    cenarios_somados = None
    historicos_somados = None
    estagios_ordenados = None
    if assinatura_stages:
        calendario = carregar_calendario_dos_estagios(*assinatura_stages)
        estagios_presentes = set(int(valor) for valor in dados["stage_id"].unique())
        calendario = {
            stage_id: registro for stage_id, registro in calendario.items()
            if stage_id in estagios_presentes
        }
        ausentes = estagios_presentes.difference(calendario)
        if ausentes:
            raise ValueError(
                "O stages.json não contém os stage_id: "
                + ", ".join(str(valor) for valor in sorted(ausentes)[:20])
            )
        estagios_ordenados = [
            stage_id for stage_id, _ in sorted(
                calendario.items(), key=lambda item: item[1]["ordem"]
            )
        ]
        cenarios_somados = {
            janela: calcular_somas_moveis_cenarios(dados, janela, calendario)
            for janela in (6, 12)
        }
        if historico is not None:
            historicos_somados = {
                janela: calcular_somas_moveis_historicas(historico, janela)
                for janela in (6, 12)
            }
    return modulo_percentuais.gerar_resumo_percentuais(
        dados, historico, hydro_id, nome_usina,
        cenarios_somados, historicos_somados, estagios_ordenados,
    )


def carregar_resumo_percentuais(
    assinatura_cenarios: tuple,
    assinatura_historico: tuple | None,
    assinatura_stages: tuple | None,
    hydro_id: int,
    nome_usina: str,
    versao_calculo: int,
) -> pd.DataFrame:
    """Valida também os resultados recuperados do cache e renova os incompatíveis."""
    argumentos = (
        assinatura_cenarios, assinatura_historico, assinatura_stages,
        hydro_id, nome_usina, versao_calculo,
    )
    esperadas = {chave for chave, _ in modulo_percentuais.COLUNAS_PERCENTUAIS} | {"mes_num", "outliers"}
    resumo = _carregar_resumo_percentuais_em_cache(*argumentos)
    if not esperadas.issubset(resumo.columns):
        _carregar_resumo_percentuais_em_cache.clear()
        resumo = _carregar_resumo_percentuais_em_cache(*argumentos)
    faltantes = esperadas.difference(resumo.columns)
    if faltantes:
        raise ValueError("Não foi possível atualizar o resumo percentual. Colunas ausentes: " + ", ".join(sorted(faltantes)))
    return resumo


@st.cache_data(show_spinner=False, max_entries=4)
def preparar_xlsx_percentuais(resumo: pd.DataFrame) -> bytes:
    """Prepara a exportação completa da UHE após gerar a segunda tabela."""
    return exportar_percentuais_xlsx(resumo)


def mostrar_primeira_tabela_relatorio() -> None:
    """Mostra o primeiro log estatístico com seus próprios filtros e XLSX."""
    st.subheader("Relatório estatístico por UHE e estágio")
    st.caption(
        "O histórico aparece antes dos cenários. A coluna Janela da análise distingue "
        "os valores originais das somas móveis de 6 e 12 estágios ou meses."
    )
    especificacoes = [
        ("arquivo_parquet", ".parquet", "Parquet consolidado"),
        ("arquivo_historico", ".parquet", "inflow_history.parquet"),
        ("arquivo_hydros_json", ".json", "hydros.json"),
        ("arquivo_stages_json", ".json", "stages.json"),
    ]
    assinaturas = []
    faltantes = []
    for chave, extensao, nome in especificacoes:
        caminho_texto = st.session_state.get(chave, "")
        if not caminho_texto:
            faltantes.append(nome)
            continue
        caminho = Path(caminho_texto)
        if not caminho.is_file() or caminho.suffix.lower() != extensao:
            st.error(f"Arquivo inválido ou não encontrado para {nome}: {caminho}")
            return
        assinaturas.append((str(caminho), caminho.stat().st_size, caminho.stat().st_mtime_ns))
    if faltantes:
        st.info("Selecione na barra lateral: " + ", ".join(faltantes) + ".")
        return
    assinatura_atual = tuple(assinaturas)
    if st.session_state.get("relatorio_assinatura") != assinatura_atual:
        st.session_state["relatorio_assinatura"] = assinatura_atual
        st.session_state["relatorio_pronto"] = False
        for chave in (
            "relatorio_usinas", "relatorio_fonte", "relatorio_janelas",
            "relatorio_meses", "relatorio_estagios",
        ):
            st.session_state.pop(chave, None)

    if st.button("Gerar tabela estatística", type="primary", key="gerar_relatorio_estatistico"):
        st.session_state["relatorio_pronto"] = True
    if not st.session_state.get("relatorio_pronto", False):
        st.info("Gere a tabela para consultar todas as UHEs e exportar o relatório.")
        return
    try:
        with st.spinner("Calculando valores originais e janelas móveis de cenários e histórico..."):
            relatorio = carregar_relatorio_estatistico(*assinatura_atual)
    except (ValueError, duckdb.Error, OSError) as erro:
        st.session_state["relatorio_pronto"] = False
        st.error(f"Não foi possível gerar o relatório: {erro}")
        return

    calendario_filtros = carregar_calendario_dos_estagios(*assinaturas[-1])
    usinas = sorted(int(hydro_id) for hydro_id in relatorio["hydro_id"].unique())
    nomes = relatorio.drop_duplicates("hydro_id").set_index("hydro_id")["usina"].to_dict()
    colunas_filtro = st.columns(3)
    with colunas_filtro[0]:
        filtro_usinas = st.multiselect(
            "Filtrar UHEs (vazio = todas)", usinas,
            format_func=lambda hydro_id: f"{nomes[hydro_id]} — hydro_id {hydro_id}",
            key="relatorio_usinas",
        )
    with colunas_filtro[1]:
        filtro_fonte = st.selectbox("Fonte", ["Todas", "Histórico", "Cenários"], key="relatorio_fonte")
    with colunas_filtro[2]:
        filtro_janelas = st.multiselect(
            "Janela da análise (vazio = todas)",
            list(JANELAS),
            key="relatorio_janelas",
        )
    colunas_periodo = st.columns(2)
    with colunas_periodo[0]:
        filtro_meses = st.multiselect(
            "Meses do histórico (vazio = todos)", list(NOMES_MESES),
            format_func=NOMES_MESES.__getitem__, key="relatorio_meses",
        )
    with colunas_periodo[1]:
        estagios_disponiveis = sorted(int(valor) for valor in relatorio["stage_id"].dropna().unique())
        filtro_estagios = st.multiselect(
            "Estágios dos cenários (vazio = todos)", estagios_disponiveis,
            format_func=lambda valor: rotulo_estagio_mes_ano(valor, calendario_filtros),
            key="relatorio_estagios",
        )
    filtrado = filtrar_relatorio(
        relatorio, filtro_usinas, filtro_fonte,
        filtro_meses, filtro_estagios, filtro_janelas,
    )
    st.caption(f"{len(filtrado):,} linhas exibidas de {len(relatorio):,} no relatório completo.".replace(",", "."))
    if filtrado.empty:
        st.info("Nenhuma linha corresponde aos filtros escolhidos.")
        return
    visivel = tabela_visivel(filtrado)
    formatos = {
        coluna: st.column_config.NumberColumn(coluna, format="%.2f")
        for coluna in ("Média (m³/s)", "Desvio padrão populacional (m³/s)", "Assimetria", "Curtose de Fisher", "Mínimo (m³/s)", "Máximo (m³/s)")
    }
    st.dataframe(visivel, hide_index=True, width="stretch", height=520, column_config=formatos)
    with st.spinner("Preparando arquivo Excel..."):
        arquivo_xlsx = preparar_xlsx_relatorio(filtrado)
    st.download_button(
        "Exportar tabela exibida para XLSX", data=arquivo_xlsx,
        file_name=nome_arquivo_exportacao(),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="exportar_relatorio_estatistico",
    )
    st.caption("O XLSX mostra ponto decimal. Uma aba auxiliar oculta conserva os valores numéricos completos.")


def mostrar_segunda_tabela_percentuais() -> None:
    """Mostra todas as fatias de uma UHE, com seleção múltipla para a tela."""
    st.subheader("Relatório dos menores valores por percentual")
    st.caption("Cada percentual reúne os menores valores de cada mês histórico ou estágio. As fatias são acumuladas.")
    arquivos = [
        ("arquivo_parquet", ".parquet", "Parquet consolidado"),
        ("arquivo_historico", ".parquet", "inflow_history.parquet"),
        ("arquivo_hydros_json", ".json", "hydros.json"),
        ("arquivo_stages_json", ".json", "stages.json"),
    ]
    assinaturas = []
    faltantes = []
    for chave, extensao, nome in arquivos:
        caminho_texto = st.session_state.get(chave, "")
        if not caminho_texto:
            faltantes.append(nome)
            continue
        caminho = Path(caminho_texto)
        if not caminho.is_file() or caminho.suffix.lower() != extensao:
            st.error(f"Arquivo inválido ou não encontrado para {nome}: {caminho}")
            return
        assinaturas.append((str(caminho), caminho.stat().st_size, caminho.stat().st_mtime_ns))
    if faltantes:
        st.info("Selecione na barra lateral: " + ", ".join(faltantes) + ".")
        return

    assinatura_cenarios, assinatura_historico, assinatura_cadastro, assinatura_stages = assinaturas
    try:
        metadados = ler_metadados(*assinatura_cenarios)
        validar_arquivo_historico(*assinatura_historico)
        nomes = carregar_cadastro_hidros(*assinatura_cadastro)
        carregar_calendario_dos_estagios(*assinatura_stages)
    except (ValueError, duckdb.Error, OSError) as erro:
        st.error(f"Não foi possível preparar a segunda tabela: {erro}")
        return
    usinas = [int(valor) for valor in metadados["usinas"]]
    hydro_id = st.selectbox(
        "UHE da segunda tabela",
        options=usinas,
        index=None,
        placeholder="Selecione uma UHE",
        format_func=lambda valor: f"{nomes.get(valor, f'Usina sem nome — hydro_id {valor}')} — hydro_id {valor}",
        key="percentuais_relatorio_usina",
    )
    percentuais = st.multiselect(
        "Percentuais exibidos na segunda tabela",
        options=PERCENTUAIS,
        default=[5],
        format_func=lambda percentual: f"p{percentual}%",
        key="percentuais_relatorio_filtro",
    )
    janelas_percentuais = st.multiselect(
        "Janelas exibidas na segunda tabela",
        options=list(JANELAS),
        default=[JANELAS[0]],
        key="percentuais_relatorio_janelas",
    )
    if hydro_id is None:
        st.info("Selecione uma UHE para gerar a segunda tabela e exportar seus percentuais.")
        return

    assinatura_selecao = (
        assinatura_cenarios, assinatura_historico,
        assinatura_cadastro, assinatura_stages, hydro_id,
    )
    if st.session_state.get("percentuais_relatorio_assinatura") != assinatura_selecao:
        st.session_state["percentuais_relatorio_assinatura"] = assinatura_selecao
        st.session_state["percentuais_relatorio_pronto"] = False
    if st.button("Gerar tabela dos percentuais", key="gerar_relatorio_percentuais"):
        st.session_state["percentuais_relatorio_pronto"] = True
    if not st.session_state.get("percentuais_relatorio_pronto", False):
        st.info("Gere a tabela para calcular p5% a p95% dessa UHE.")
        return

    nome_usina = nomes.get(hydro_id, f"Usina sem nome — hydro_id {hydro_id}")
    try:
        with st.spinner(f"Calculando percentuais de {nome_usina}..."):
            resumo = carregar_resumo_percentuais(
                assinatura_cenarios, assinatura_historico, assinatura_stages,
                hydro_id, nome_usina,
                VERSAO_RESUMO_PERCENTUAIS,
            )
    except (ValueError, duckdb.Error, OSError) as erro:
        st.session_state["percentuais_relatorio_pronto"] = False
        st.error(f"Não foi possível gerar a segunda tabela: {erro}")
        return
    if percentuais and janelas_percentuais:
        visivel = tabela_percentuais_visivel(
            filtrar_percentuais(resumo, percentuais, janelas_percentuais)
        )
        st.caption(
            f"{len(visivel):,} linhas exibidas; a exportação inclui todos os "
            "19 percentuais e as três janelas.".replace(",", ".")
        )
        formatos = {
            coluna: st.column_config.NumberColumn(coluna, format="%.2f")
            for coluna in visivel.columns
            if coluna.endswith("(m³/s)") or coluna in ("Assimetria", "Curtose de Fisher")
        }
        st.dataframe(visivel, hide_index=True, width="stretch", height=520, column_config=formatos)
    else:
        st.info("Selecione ao menos um percentual e uma janela para visualizar as linhas.")
    with st.spinner("Preparando o XLSX completo da UHE..."):
        arquivo = preparar_xlsx_percentuais(resumo)
    st.download_button(
        "Exportar todos os percentuais desta UHE para XLSX",
        data=arquivo,
        file_name=nome_arquivo_percentuais(hydro_id),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="exportar_relatorio_percentuais",
    )
    st.caption(
        "O XLSX reúne p5% a p95%, as três janelas e conserva os números completos "
        "em uma aba auxiliar oculta."
    )


def mostrar_aba_relatorio() -> None:
    """Exibe os seis relatórios independentes na segunda aba."""
    mostrar_primeira_tabela_relatorio()
    st.divider()
    mostrar_segunda_tabela_percentuais()
    st.divider()
    mostrar_terceira_tabela_autocorrelacao()
    st.divider()
    mostrar_quarta_tabela_correlacao_espacial()
    st.divider()
    mostrar_quinta_tabela_autocorrelacao_anual()
    st.divider()
    mostrar_sexta_tabela_ks()


@st.cache_data(show_spinner=False, max_entries=3)
def carregar_autocorrelacao_usina(
    assinatura_cenarios: tuple, assinatura_stages: tuple, hydro_id: int,
    rotulo_usina: str, versao_formula: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    calendario = carregar_calendario_dos_estagios(*assinatura_stages)
    nome = rotulo_usina.split(" — hydro_id ")[0]
    return gerar_autocorrelacao(assinatura_cenarios[0], {hydro_id: nome}, calendario, hydro_id)


@st.cache_data(show_spinner=False, max_entries=2)
def carregar_autocorrelacao_completa(
    assinatura_cenarios: tuple, assinatura_cadastro: tuple,
    assinatura_stages: tuple, versao_formula: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    nomes = carregar_cadastro_hidros(*assinatura_cadastro)
    calendario = carregar_calendario_dos_estagios(*assinatura_stages)
    return gerar_autocorrelacao(assinatura_cenarios[0], nomes, calendario)


@st.cache_data(show_spinner=False, max_entries=3)
def preparar_xlsx_autocorrelacao(tabela: pd.DataFrame, diagnosticos: pd.DataFrame) -> bytes:
    return exportar_autocorrelacao_xlsx(tabela, diagnosticos)


def mostrar_autocorrelacao_usina(
    assinatura_cenarios: tuple | None, assinatura_stages: tuple | None,
    hydro_id: int, rotulo_usina: str, calendario: dict[int, dict] | None,
) -> None:
    st.subheader("Função de Autocorrelação")
    st.caption(
        "Correlação entre a vazão atual e as vazões passadas do mesmo cenário, "
        "calculada separadamente em cada estágio. Sem corte percentual ou série histórica independente."
    )
    if assinatura_cenarios is None or assinatura_stages is None or calendario is None:
        st.info("Selecione o stages.json para mostrar a autocorrelação e os períodos passados.")
        return
    selecionados = st.multiselect(
        "Lags exibidos", options=list(CORES_LAGS), default=list(CORES_LAGS),
        format_func=lambda lag: f"Lag {lag}", key="lags_autocorrelacao_grafico",
    )
    if not selecionados:
        st.info("Selecione ao menos um lag para visualizar as barras.")
        return
    try:
        with st.spinner(f"Calculando autocorrelação de {rotulo_usina}..."):
            tabela, diagnosticos = carregar_autocorrelacao_usina(
                assinatura_cenarios, assinatura_stages, hydro_id, rotulo_usina,
                VERSAO_FORMULA,
            )
    except (ValueError, duckdb.Error, OSError) as erro:
        st.error(f"Autocorrelação indisponível: {erro}")
        return
    figura = go.Figure()
    x = tabela["stage_id"].astype(str).tolist()
    rotulos_estagios = [
        f"{stage_id}<br>{NOMES_MESES[calendario[int(stage_id)]['mes']][0]}"
        for stage_id in x
    ]
    for lag in sorted(selecionados):
        diagnostico_lag = diagnosticos.loc[diagnosticos.lag.eq(lag)]
        detalhes = diagnostico_lag[[
            "UHE", "hydro_id", "período atual", "período passado", "origem", "pares válidos"
        ]].astype(str).to_numpy()
        figura.add_trace(go.Bar(
            x=x, y=tabela[f"Lag {lag}"].tolist(), name=f"Lag {lag}",
            marker=dict(color=CORES_LAGS[lag], line=dict(color="#695F42" if lag == 3 else CORES_LAGS[lag], width=0.5)),
            customdata=detalhes,
            hovertemplate=(
                "UHE: %{customdata[0]} — hydro_id %{customdata[1]}<br>"
                "Estágio: %{x} (%{customdata[2]})<br>"
                f"Lag {lag}: %{{customdata[3]}} — %{{customdata[4]}}<br>"
                "Correlação: %{y:.4f}<br>Pares válidos: %{customdata[5]}<extra></extra>"
            ),
        ))
    figura.update_layout(
        title="Função de Autocorrelação",
        barmode="group", bargap=0.12, bargroupgap=0,
        yaxis=dict(title="Correlação", range=[-1, 1], zeroline=True, zerolinecolor="#596873"),
        xaxis=dict(
            title="Estágio (stage_id)", type="category",
            tickmode="array", tickvals=x, ticktext=rotulos_estagios,
            tickangle=0, tickfont=dict(size=9), automargin=True,
        ),
        legend=dict(orientation="h", y=1.08),
        height=540, margin=dict(t=90),
    )
    st.plotly_chart(figura, width="stretch", config={"displaylogo": False})
    indisponiveis = diagnosticos.loc[
        diagnosticos.lag.isin(selecionados) & diagnosticos.status.ne("calculado")
    ]
    if not indisponiveis.empty:
        st.caption(
            f"{len(indisponiveis)} combinações estágio/lag sem correlação definida. "
            "Barras ausentes não significam correlação zero."
        )
        with st.expander("Ver lags indisponíveis"):
            st.dataframe(
                indisponiveis[["stage_id", "lag", "período passado", "origem", "pares válidos", "motivo"]],
                hide_index=True, width="stretch",
            )


def mostrar_terceira_tabela_autocorrelacao() -> None:
    st.subheader("Autocorrelação por UHE e estágio")
    st.caption("Cada linha corresponde a uma UHE e um estágio. Lag 0 é a correlação da vazão consigo mesma quando definida.")
    chaves = ("arquivo_parquet", "arquivo_hydros_json", "arquivo_stages_json")
    nomes_arquivos = ("Parquet consolidado", "hydros.json", "stages.json")
    assinaturas = []
    faltantes = []
    for chave, nome in zip(chaves, nomes_arquivos):
        texto_caminho = st.session_state.get(chave, "")
        if not texto_caminho:
            faltantes.append(nome)
            continue
        caminho = Path(texto_caminho)
        if not caminho.is_file():
            st.error(f"Arquivo de autocorrelação não encontrado: {caminho}")
            return
        assinaturas.append((str(caminho), caminho.stat().st_size, caminho.stat().st_mtime_ns))
    if faltantes:
        st.info("Selecione na barra lateral: " + ", ".join(faltantes) + ".")
        return
    assinatura_atual = tuple(assinaturas) + (VERSAO_FORMULA,)
    if st.session_state.get("assinatura_relatorio_autocorrelacao") != assinatura_atual:
        st.session_state["assinatura_relatorio_autocorrelacao"] = assinatura_atual
        st.session_state["relatorio_autocorrelacao_pronto"] = False
    if st.button("Gerar tabela de autocorrelação", key="gerar_relatorio_autocorrelacao"):
        st.session_state["relatorio_autocorrelacao_pronto"] = True
    if not st.session_state.get("relatorio_autocorrelacao_pronto", False):
        st.info("Gere a terceira tabela para calcular todas as UHEs e estágios.")
        return
    try:
        with st.spinner("Calculando e auditando os lags de todas as UHEs..."):
            tabela, diagnosticos = carregar_autocorrelacao_completa(*assinaturas, VERSAO_FORMULA)
    except (ValueError, duckdb.Error, OSError) as erro:
        st.session_state["relatorio_autocorrelacao_pronto"] = False
        st.error(f"Não foi possível gerar a tabela de autocorrelação: {erro}")
        return
    calendario_filtros = carregar_calendario_dos_estagios(*assinaturas[-1])
    nomes_por_id = dict(zip(tabela.hydro_id, tabela.UHE))
    colunas_filtro = st.columns(2)
    with colunas_filtro[0]:
        usinas = st.multiselect(
            "UHEs da autocorrelação (vazio = todas)",
            options=sorted(int(valor) for valor in tabela.hydro_id.unique()),
            format_func=lambda valor: f"{nomes_por_id[valor]} — hydro_id {valor}",
            key="autocorrelacao_relatorio_usinas",
        )
    with colunas_filtro[1]:
        estagios = st.multiselect(
            "Estágios da autocorrelação (vazio = todos)",
            options=[int(valor) for valor in tabela.stage_id.drop_duplicates()],
            format_func=lambda valor: rotulo_estagio_mes_ano(valor, calendario_filtros),
            key="autocorrelacao_relatorio_estagios",
        )
    exibida, diagnostico_exibido = filtrar_autocorrelacao(tabela, diagnosticos, usinas, estagios)
    st.caption(f"{len(exibida):,} linhas exibidas de {len(tabela):,}. Células vazias indicam correlação indefinida.".replace(",", "."))
    formatos = {f"Lag {k}": st.column_config.NumberColumn(f"Lag {k}", format="%.2f") for k in range(7)}
    st.dataframe(exibida, hide_index=True, width="stretch", height=520, column_config=formatos)
    with st.expander("Diagnóstico dos cálculos de autocorrelação"):
        somente_indisponiveis = st.checkbox(
            "Mostrar apenas lags indisponíveis", value=True,
            key="autocorrelacao_diagnostico_indisponiveis",
        )
        detalhe_visivel = diagnostico_exibido.loc[
            diagnostico_exibido.status.ne("calculado")
        ] if somente_indisponiveis else diagnostico_exibido
        st.dataframe(detalhe_visivel, hide_index=True, width="stretch", height=440)
    if not exibida.empty:
        assinatura_exportacao = (assinatura_atual, tuple(usinas), tuple(estagios))
        if st.session_state.get("assinatura_exportacao_autocorrelacao") != assinatura_exportacao:
            st.session_state["assinatura_exportacao_autocorrelacao"] = assinatura_exportacao
            st.session_state["exportacao_autocorrelacao_pronta"] = False
        if st.button("Preparar XLSX da autocorrelação", key="preparar_exportacao_autocorrelacao"):
            st.session_state["exportacao_autocorrelacao_pronta"] = True
        if not st.session_state.get("exportacao_autocorrelacao_pronta", False):
            return
        with st.spinner("Preparando XLSX da autocorrelação..."):
            arquivo = preparar_xlsx_autocorrelacao(exibida, diagnostico_exibido)
        st.download_button(
            "Exportar tabela de autocorrelação exibida para XLSX", data=arquivo,
            file_name="autocorrelacao_cobre.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="exportar_relatorio_autocorrelacao",
        )
        st.caption("O XLSX inclui uma aba de diagnóstico e uma aba numérica oculta com os coeficientes completos.")


@st.cache_data(show_spinner=False, max_entries=6)
def carregar_correlacao_espacial_estagio(
    assinatura_cenarios: tuple, assinatura_cadastro: tuple,
    assinatura_stages: tuple, stage_id: int, hydro_id: int, versao: int,
):
    nomes = carregar_cadastro_hidros(*assinatura_cadastro)
    calendario = carregar_calendario_dos_estagios(*assinatura_stages)
    return gerar_correlacao_espacial(
        assinatura_cenarios[0], nomes, calendario, stage_id,
        hydro_id_referencia=hydro_id,
    )


@st.cache_data(show_spinner=False, max_entries=2)
def carregar_correlacao_espacial_completa(
    assinatura_cenarios: tuple, assinatura_cadastro: tuple,
    assinatura_stages: tuple, versao: int,
):
    nomes = carregar_cadastro_hidros(*assinatura_cadastro)
    calendario = carregar_calendario_dos_estagios(*assinatura_stages)
    return gerar_correlacao_espacial(assinatura_cenarios[0], nomes, calendario)


@st.cache_data(show_spinner=False, max_entries=2)
def preparar_xlsx_correlacao_espacial(resultado, referencias: tuple[int, ...], estagios: tuple[int, ...]) -> bytes:
    return exportar_correlacao_espacial_xlsx(resultado, list(referencias), list(estagios))


def limites_grafico_espacial(valores: np.ndarray) -> list[float]:
    definidos = np.asarray(valores, dtype=float)
    definidos = definidos[np.isfinite(definidos)]
    if definidos.size == 0 or np.all(definidos == 0):
        return [-0.05, 0.05]
    menor = min(0.0, float(np.min(definidos)))
    maior = max(0.0, float(np.max(definidos)))
    margem = max(0.02, (maior - menor) * 0.06)
    return [max(-1.0, menor - margem), min(1.0, maior + margem)]


def mostrar_correlacao_espacial_usina(
    assinatura_cenarios: tuple | None, assinatura_cadastro: tuple | None,
    assinatura_stages: tuple | None, hydro_id: int, rotulo_usina: str,
    calendario: dict[int, dict] | None, estagios_usina: list[int],
) -> None:
    st.subheader("Correlação espacial — lag 0")
    st.caption("Comparação da vazão da UHE selecionada com as demais UHEs no mesmo cenário e estágio, usando todos os cenários válidos.")
    if not all((assinatura_cenarios, assinatura_cadastro, assinatura_stages, calendario)):
        st.info("Selecione o Parquet, hydros.json e stages.json para mostrar a correlação espacial.")
        return
    estagios = sorted(
        (valor for valor in estagios_usina if valor in calendario),
        key=lambda item: calendario[item]["ordem"],
    )
    if not estagios:
        st.info("Esta UHE não possui estágios para a correlação espacial.")
        return
    stage_id = st.selectbox(
        "Estágio da correlação espacial", estagios,
        format_func=lambda valor: rotulo_estagio_mes_ano(valor, calendario),
        key="estagio_correlacao_espacial",
    )
    try:
        with st.spinner(f"Calculando correlações espaciais do estágio {stage_id}..."):
            resultado = carregar_correlacao_espacial_estagio(
                assinatura_cenarios, assinatura_cadastro, assinatura_stages,
                stage_id, hydro_id, VERSAO_CORRELACAO_ESPACIAL,
            )
    except (ValueError, duckdb.Error, OSError) as erro:
        st.error(f"Correlação espacial indisponível: {erro}")
        return
    if hydro_id not in resultado.hydro_ids:
        st.info("A UHE selecionada não possui registros neste estágio.")
        return
    s, u, _ = resultado.posicoes(stage_id, hydro_id, hydro_id)
    ids_outros = [valor for valor in resultado.hydro_ids if valor != hydro_id]
    validos = [
        valor for valor in ids_outros
        if resultado.estados[s, u, resultado.hydro_ids.index(valor)] == 0
    ]
    periodo = f"{NOMES_MESES[calendario[stage_id]['mes']]} de {calendario[stage_id]['inicio'].year}"
    figura = go.Figure()
    if validos:
        indices = [resultado.hydro_ids.index(valor) for valor in validos]
        ids_eixo = [str(valor) for valor in validos]
        nomes_eixo = [resultado.nomes[valor] for valor in validos]
        y = resultado.correlacoes[s, u, indices]
        detalhes = [
            [resultado.nomes[valor], valor, int(resultado.pares_validos[s, u, indice])]
            for valor, indice in zip(validos, indices)
        ]
        figura.add_trace(go.Bar(
            x=ids_eixo, y=y, marker_color=CIANO_FORTE,
            name="Correlação espacial", customdata=detalhes,
            hovertemplate=(
                f"Referência: {rotulo_usina}<br>Comparada: %{{customdata[0]}} — hydro_id %{{customdata[1]}}<br>"
                f"Estágio {stage_id} — {periodo}<br>Correlação: %{{y:.4f}}<br>"
                "Pares válidos: %{customdata[2]}<extra></extra>"
            ),
        ))
        zeros = [i for i, valor in enumerate(y) if valor == 0]
        if zeros:
            figura.add_trace(go.Scatter(
                x=[str(validos[i]) for i in zeros], y=[0.0] * len(zeros),
                customdata=[[resultado.nomes[validos[i]], validos[i]] for i in zeros],
                mode="markers", marker=dict(color=CIANO_FORTE, size=8, symbol="circle-open", line=dict(width=2)),
                name="Correlação igual a zero", showlegend=True,
                hovertemplate="%{customdata[0]} — hydro_id %{customdata[1]}<br>Correlação: 0,0000<extra></extra>",
            ))
        limites = limites_grafico_espacial(y)
    else:
        limites = [-0.05, 0.05]
    figura.update_layout(
        title=f"Correlação espacial — {rotulo_usina} — estágio {stage_id}",
        xaxis=dict(
            title="UHE comparada", type="category", tickmode="array",
            tickvals=ids_eixo if validos else [], ticktext=nomes_eixo if validos else [],
            tickangle=-90, tickfont=dict(size=9), automargin=True,
        ),
        yaxis=dict(title="Correlação de Pearson", range=limites, zeroline=True, zerolinecolor="#596873"),
        bargap=0.18, height=600, margin=dict(t=90, b=150),
    )
    st.plotly_chart(figura, width="stretch", config={"displaylogo": False})
    indefinidos = [
        valor for valor in ids_outros
        if resultado.estados[s, u, resultado.hydro_ids.index(valor)] != 0
    ]
    st.caption(f"{len(validos)} correlações definidas; {len(indefinidos)} indisponíveis. Uma barra ausente não representa correlação zero.")
    if indefinidos:
        with st.expander("Consultar correlações espaciais indisponíveis"):
            st.dataframe(pd.DataFrame([
                {
                    "hydro_id": valor, "UHE": resultado.nomes[valor],
                    "Pares válidos": int(resultado.pares_validos[s, u, resultado.hydro_ids.index(valor)]),
                    "Motivo": MOTIVOS_CORRELACAO_ESPACIAL[int(resultado.estados[s, u, resultado.hydro_ids.index(valor)])],
                }
                for valor in indefinidos
            ]), hide_index=True, width="stretch")


def mostrar_quarta_tabela_correlacao_espacial() -> None:
    st.subheader("Correlação espacial por UHE e estágio")
    st.caption("Cada linha compara uma UHE de referência com as demais no mesmo estágio. A célula da própria UHE fica vazia.")
    chaves = ("arquivo_parquet", "arquivo_hydros_json", "arquivo_stages_json")
    nomes_arquivos = ("Parquet consolidado", "hydros.json", "stages.json")
    assinaturas = []
    faltantes = []
    for chave, nome in zip(chaves, nomes_arquivos):
        texto_caminho = st.session_state.get(chave, "")
        if not texto_caminho:
            faltantes.append(nome)
            continue
        caminho = Path(texto_caminho)
        if not caminho.is_file():
            st.error(f"Arquivo de correlação espacial não encontrado: {caminho}")
            return
        assinaturas.append((str(caminho), caminho.stat().st_size, caminho.stat().st_mtime_ns))
    if faltantes:
        st.info("Selecione na barra lateral: " + ", ".join(faltantes) + ".")
        return
    assinatura_atual = tuple(assinaturas) + (VERSAO_CORRELACAO_ESPACIAL,)
    if st.session_state.get("assinatura_relatorio_espacial") != assinatura_atual:
        st.session_state["assinatura_relatorio_espacial"] = assinatura_atual
        st.session_state["relatorio_espacial_pronto"] = False
    if st.button("Gerar tabela de correlação espacial", key="gerar_relatorio_espacial"):
        st.session_state["relatorio_espacial_pronto"] = True
    if not st.session_state.get("relatorio_espacial_pronto", False):
        st.info("Gere a quarta tabela para calcular todas as UHEs e estágios.")
        return
    try:
        with st.spinner("Calculando correlação espacial de todas as UHEs e estágios..."):
            resultado = carregar_correlacao_espacial_completa(*assinaturas, VERSAO_CORRELACAO_ESPACIAL)
    except (ValueError, duckdb.Error, OSError) as erro:
        st.session_state["relatorio_espacial_pronto"] = False
        st.error(f"Não foi possível gerar a tabela de correlação espacial: {erro}")
        return
    calendario_filtros = carregar_calendario_dos_estagios(*assinaturas[-1])
    filtros = st.columns(2)
    with filtros[0]:
        referencias = st.multiselect(
            "UHEs de referência da correlação espacial (vazio = todas)",
            options=list(resultado.hydro_ids),
            format_func=lambda valor: f"{resultado.nomes[valor]} — hydro_id {valor}",
            key="espacial_relatorio_usinas",
        )
    with filtros[1]:
        estagios = st.multiselect(
            "Estágios da correlação espacial (vazio = todos)",
            options=list(resultado.stage_ids),
            format_func=lambda valor: rotulo_estagio_mes_ano(valor, calendario_filtros),
            key="espacial_relatorio_estagios",
        )
    tabela = tabela_espacial(resultado, referencias, estagios)
    numericas = tabela.iloc[:, 3:].to_numpy(dtype=float)
    definidas = int(np.count_nonzero(np.isfinite(numericas)))
    possiveis = len(tabela) * max(0, len(resultado.hydro_ids) - 1)
    st.caption(
        f"{len(tabela):,} linhas; {definidas:,} correlações definidas; "
        f"{possiveis - definidas:,} indisponíveis. Células vazias distinguem a diagonal e resultados indefinidos.".replace(",", ".")
    )
    formatos = {
        coluna: st.column_config.NumberColumn(coluna, format="%.2f")
        for coluna in tabela.columns[3:]
    }
    st.dataframe(tabela, hide_index=True, width="stretch", height=520, column_config=formatos)
    with st.expander("Diagnóstico de um par de UHEs"):
        opcoes_ref = referencias or list(resultado.hydro_ids)
        opcoes_estagio = estagios or list(resultado.stage_ids)
        colunas = st.columns(3)
        with colunas[0]:
            referencia = st.selectbox("UHE de referência", opcoes_ref, key="espacial_diagnostico_referencia",
                                     format_func=lambda valor: f"{resultado.nomes[valor]} — {valor}")
        with colunas[1]:
            comparada = st.selectbox("UHE comparada", [i for i in resultado.hydro_ids if i != referencia],
                                    key="espacial_diagnostico_comparada",
                                    format_func=lambda valor: f"{resultado.nomes[valor]} — {valor}")
        with colunas[2]:
            stage_id = st.selectbox(
                "Estágio", opcoes_estagio, key="espacial_diagnostico_estagio",
                format_func=lambda valor: rotulo_estagio_mes_ano(valor, calendario_filtros),
            )
        st.dataframe(pd.DataFrame([diagnosticar_par(resultado, stage_id, referencia, comparada)]),
                     hide_index=True, width="stretch")
    assinatura_exportacao = (assinatura_atual, tuple(referencias), tuple(estagios))
    if st.session_state.get("assinatura_exportacao_espacial") != assinatura_exportacao:
        st.session_state["assinatura_exportacao_espacial"] = assinatura_exportacao
        st.session_state["exportacao_espacial_pronta"] = False
    if st.button("Preparar XLSX da correlação espacial", key="preparar_exportacao_espacial"):
        st.session_state["exportacao_espacial_pronta"] = True
    if st.session_state.get("exportacao_espacial_pronta", False):
        try:
            with st.spinner("Preparando XLSX da correlação espacial e diagnóstico..."):
                arquivo = preparar_xlsx_correlacao_espacial(resultado, tuple(referencias), tuple(estagios))
        except (ValueError, OSError) as erro:
            st.session_state["exportacao_espacial_pronta"] = False
            st.error(f"Não foi possível preparar o XLSX: {erro}")
            return
        st.download_button(
            "Exportar tabela de correlação espacial para XLSX", data=arquivo,
            file_name="correlacao_espacial_cobre.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="exportar_relatorio_espacial",
        )
        st.caption("O XLSX inclui diagnóstico dos pares e uma aba numérica oculta com os coeficientes completos.")


@st.cache_data(show_spinner=False, max_entries=3)
def carregar_autocorrelacao_anual_usina(
    assinatura_cenarios: tuple, assinatura_cadastro: tuple,
    assinatura_stages: tuple, hydro_id: int, versao: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    nomes = carregar_cadastro_hidros(*assinatura_cadastro)
    calendario = carregar_calendario_dos_estagios(*assinatura_stages)
    return gerar_autocorrelacao_anual(
        assinatura_cenarios[0], nomes, calendario, hydro_id,
    )


@st.cache_data(show_spinner=False, max_entries=2)
def carregar_autocorrelacao_anual_completa(
    assinatura_cenarios: tuple, assinatura_cadastro: tuple,
    assinatura_stages: tuple, versao: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    nomes = carregar_cadastro_hidros(*assinatura_cadastro)
    calendario = carregar_calendario_dos_estagios(*assinatura_stages)
    return gerar_autocorrelacao_anual(assinatura_cenarios[0], nomes, calendario)


@st.cache_data(show_spinner=False, max_entries=3)
def preparar_xlsx_autocorrelacao_anual(
    tabela: pd.DataFrame, diagnosticos: pd.DataFrame,
) -> bytes:
    return exportar_autocorrelacao_anual_xlsx(tabela, diagnosticos)


def mostrar_autocorrelacao_anual_usina(
    assinatura_cenarios: tuple | None, assinatura_cadastro: tuple | None,
    assinatura_stages: tuple | None, hydro_id: int, rotulo_usina: str,
) -> None:
    st.subheader("Função de Autocorrelação Anual")
    st.caption(
        "Somas de janeiro a dezembro de cada cenário da UHE selecionada; "
        "cada lag compara a soma anual atual com a do mesmo cenário em ano anterior."
    )
    if not all((assinatura_cenarios, assinatura_cadastro, assinatura_stages)):
        st.info("Selecione o Parquet, hydros.json e stages.json para calcular os anos civis completos.")
        return
    selecionados = st.multiselect(
        "Lags anuais exibidos", options=list(LAGS_ANUAIS),
        default=list(LAGS_ANUAIS),
        format_func=lambda lag: f"Lag {lag}",
        key="lags_autocorrelacao_anual_grafico",
    )
    if not selecionados:
        st.info("Selecione o lag 1 ou o lag 2 para visualizar a autocorrelação anual.")
        return
    try:
        with st.spinner(f"Calculando autocorrelação anual de {rotulo_usina}..."):
            tabela, diagnosticos = carregar_autocorrelacao_anual_usina(
                assinatura_cenarios, assinatura_cadastro, assinatura_stages,
                hydro_id, VERSAO_AUTOCORRELACAO_ANUAL,
            )
    except (ValueError, duckdb.Error, OSError) as erro:
        st.error(f"Autocorrelação anual indisponível: {erro}")
        return
    if tabela.empty:
        st.info("O horizonte não contém um ano civil completo de janeiro a dezembro.")
        return
    x = tabela["Ano"].astype(str).tolist()
    diagnostico_visivel = diagnosticos.loc[diagnosticos["Lag"].isin(selecionados)]
    definidos = int(sum(tabela[f"Lag {lag}"].notna().sum() for lag in selecionados))
    if definidos:
        figura = go.Figure()
        for lag in sorted(selecionados):
            detalhes = diagnosticos.loc[diagnosticos["Lag"].eq(lag)].sort_values("Ano")
            figura.add_trace(go.Bar(
                x=x, y=tabela[f"Lag {lag}"].tolist(),
                name=f"Lag {lag}",
                marker=dict(color=CORES_LAGS[lag], line=dict(color=CORES_LAGS[lag], width=0.5)),
                customdata=detalhes[["Ano passado", "Pares válidos"]].to_numpy(),
                hovertemplate=(
                    f"UHE: {rotulo_usina}<br>Ano atual: %{{x}}<br>"
                    f"Lag {lag} — ano passado: %{{customdata[0]}}<br>"
                    "Correlação: %{y:.4f}<br>"
                    "Pares válidos: %{customdata[1]}<extra></extra>"
                ),
            ))
        figura.update_layout(
            title=f"Função de Autocorrelação Anual — {rotulo_usina}",
            barmode="group", bargap=0.16, bargroupgap=0,
            xaxis=dict(title="Ano civil atual", type="category",
                       categoryorder="array", categoryarray=x),
            yaxis=dict(title="Correlação de Pearson", range=[-1, 1],
                       zeroline=True, zerolinecolor="#596873"),
            legend=dict(orientation="h", y=1.08),
            height=500, margin=dict(t=90),
        )
        st.plotly_chart(figura, width="stretch", config={"displaylogo": False})
    else:
        st.info("Não há pares de anos completos suficientes para os lags selecionados.")
    indisponiveis = diagnostico_visivel.loc[
        diagnostico_visivel["Status"].ne("calculado")
    ]
    st.caption(
        f"{definidos} correlações anuais definidas; "
        f"{len(indisponiveis)} combinações ano/lag indisponíveis. "
        "Ausência de barra não significa correlação zero."
    )
    if not indisponiveis.empty:
        with st.expander("Consultar lags anuais indisponíveis"):
            st.dataframe(
                indisponiveis[[
                    "Ano", "Lag", "Ano passado",
                    "Somas completas atuais", "Somas completas passadas",
                    "Pares válidos", "Motivo",
                ]], hide_index=True, width="stretch",
            )


def mostrar_quinta_tabela_autocorrelacao_anual() -> None:
    st.subheader("Autocorrelação anual por UHE e ano")
    st.caption(
        "Uma linha por UHE e ano civil completo; lag 1 e lag 2 "
        "pareiam somas anuais dos mesmos cenários."
    )
    chaves = ("arquivo_parquet", "arquivo_hydros_json", "arquivo_stages_json")
    nomes_arquivos = ("Parquet consolidado", "hydros.json", "stages.json")
    assinaturas = []
    faltantes = []
    for chave, nome in zip(chaves, nomes_arquivos):
        texto_caminho = st.session_state.get(chave, "")
        if not texto_caminho:
            faltantes.append(nome)
            continue
        caminho = Path(texto_caminho)
        if not caminho.is_file():
            st.error(f"Arquivo de autocorrelação anual não encontrado: {caminho}")
            return
        assinaturas.append(
            (str(caminho), caminho.stat().st_size, caminho.stat().st_mtime_ns)
        )
    if faltantes:
        st.info("Selecione na barra lateral: " + ", ".join(faltantes) + ".")
        return
    assinatura_atual = tuple(assinaturas) + (VERSAO_AUTOCORRELACAO_ANUAL,)
    if st.session_state.get("assinatura_relatorio_anual") != assinatura_atual:
        st.session_state["assinatura_relatorio_anual"] = assinatura_atual
        st.session_state["relatorio_anual_pronto"] = False
    if st.button("Gerar tabela de autocorrelação anual", key="gerar_relatorio_anual"):
        st.session_state["relatorio_anual_pronto"] = True
    if not st.session_state.get("relatorio_anual_pronto", False):
        st.info("Gere a quinta tabela para calcular todas as UHEs e anos civis completos.")
        return
    try:
        with st.spinner("Calculando somas anuais e autocorrelações de todas as UHEs..."):
            tabela, diagnosticos = carregar_autocorrelacao_anual_completa(
                *assinaturas, VERSAO_AUTOCORRELACAO_ANUAL,
            )
    except (ValueError, duckdb.Error, OSError) as erro:
        st.session_state["relatorio_anual_pronto"] = False
        st.error(f"Não foi possível gerar a tabela anual: {erro}")
        return
    if tabela.empty:
        st.info("O horizonte não contém anos civis completos de janeiro a dezembro.")
        return
    nomes_por_id = dict(zip(tabela["hydro_id"], tabela["UHE"]))
    filtros = st.columns(2)
    with filtros[0]:
        usinas = st.multiselect(
            "UHEs da autocorrelação anual (vazio = todas)",
            options=sorted(int(v) for v in tabela["hydro_id"].unique()),
            format_func=lambda valor: f"{nomes_por_id[valor]} — hydro_id {valor}",
            key="anual_relatorio_usinas",
        )
    with filtros[1]:
        anos = st.multiselect(
            "Anos civis da autocorrelação anual (vazio = todos)",
            options=sorted(int(v) for v in tabela["Ano"].unique()),
            key="anual_relatorio_anos",
        )
    exibida, diagnostico_exibido = filtrar_autocorrelacao_anual(
        tabela, diagnosticos, usinas, anos,
    )
    definidos = int(exibida[["Lag 1", "Lag 2"]].notna().sum().sum())
    possiveis = 2 * len(exibida)
    resumo_contagens = (
        f"{len(exibida):,} linhas de {len(tabela):,}; "
        f"{definidos:,} correlações definidas e "
        f"{possiveis - definidos:,} indisponíveis. "
        "Células vazias não representam zero."
    )
    st.caption(resumo_contagens.replace(",", "."))
    formatos = {
        f"Lag {lag}": st.column_config.NumberColumn(
            f"Lag {lag}", format="%.2f",
        )
        for lag in LAGS_ANUAIS
    }
    st.dataframe(
        exibida, hide_index=True, width="stretch", height=480,
        column_config=formatos,
    )
    with st.expander("Diagnóstico dos cálculos de autocorrelação anual"):
        somente_indisponiveis = st.checkbox(
            "Mostrar apenas lags anuais indisponíveis", value=True,
            key="anual_diagnostico_indisponiveis",
        )
        detalhe_visivel = (
            diagnostico_exibido.loc[diagnostico_exibido["Status"].ne("calculado")]
            if somente_indisponiveis else diagnostico_exibido
        )
        st.dataframe(
            detalhe_visivel, hide_index=True, width="stretch", height=420,
        )
    assinatura_exportacao = (assinatura_atual, tuple(usinas), tuple(anos))
    if st.session_state.get("assinatura_exportacao_anual") != assinatura_exportacao:
        st.session_state["assinatura_exportacao_anual"] = assinatura_exportacao
        st.session_state["exportacao_anual_pronta"] = False
    if st.button("Preparar XLSX da autocorrelação anual", key="preparar_exportacao_anual"):
        st.session_state["exportacao_anual_pronta"] = True
    if st.session_state.get("exportacao_anual_pronta", False):
        try:
            with st.spinner("Preparando XLSX da autocorrelação anual..."):
                arquivo = preparar_xlsx_autocorrelacao_anual(
                    exibida, diagnostico_exibido,
                )
        except (ValueError, OSError) as erro:
            st.session_state["exportacao_anual_pronta"] = False
            st.error(f"Não foi possível preparar o XLSX anual: {erro}")
            return
        st.download_button(
            "Exportar tabela de autocorrelação anual para XLSX",
            data=arquivo,
            file_name="autocorrelacao_anual_cobre.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="exportar_relatorio_anual",
        )
        st.caption(
            "O XLSX inclui os termos dos cálculos e uma folha numérica oculta "
            "com os coeficientes antes do arredondamento."
        )


@st.cache_data(show_spinner=False, max_entries=4)
def carregar_tabela_ks_usina(
    assinatura_cenarios: tuple, assinatura_historico: tuple,
    assinatura_stages: tuple, hydro_id: int, nome_usina: str, versao: int,
) -> pd.DataFrame:
    """Calcula todos os estágios de uma UHE apenas quando a sexta tabela é solicitada."""
    dados = consultar_usina_em_cache(assinatura_cenarios, hydro_id)
    validar_usina(dados, hydro_id)
    historico = consultar_historico(*assinatura_historico, hydro_id)
    calendario = carregar_calendario_dos_estagios(*assinatura_stages)
    return gerar_tabela_ks_usina(dados, historico, calendario, hydro_id, nome_usina)


@st.cache_data(show_spinner=False, max_entries=4)
def preparar_xlsx_ks(tabela: pd.DataFrame) -> bytes:
    return exportar_ks_xlsx(tabela)


def mostrar_sexta_tabela_ks() -> None:
    """Consulta e exporta a distância KS completa por estágio de uma UHE."""
    st.subheader("Comparação KS entre cenários e histórico")
    st.caption(
        "Uma linha por UHE e estágio, usando todos os cenários e o histórico do mês correspondente. "
        "D é a maior distância entre as distribuições acumuladas, sem valor-p."
    )
    arquivos = (
        ("arquivo_parquet", ".parquet", "Parquet consolidado"),
        ("arquivo_historico", ".parquet", "inflow_history.parquet"),
        ("arquivo_hydros_json", ".json", "hydros.json"),
        ("arquivo_stages_json", ".json", "stages.json"),
    )
    assinaturas = []
    faltantes = []
    for chave, extensao, nome in arquivos:
        texto_caminho = st.session_state.get(chave, "")
        if not texto_caminho:
            faltantes.append(nome)
            continue
        caminho = Path(texto_caminho)
        if not caminho.is_file() or caminho.suffix.lower() != extensao:
            st.error(f"Arquivo inválido ou não encontrado para {nome}: {caminho}")
            return
        assinaturas.append((str(caminho), caminho.stat().st_size, caminho.stat().st_mtime_ns))
    if faltantes:
        st.info("Selecione na barra lateral: " + ", ".join(faltantes) + ".")
        return

    assinatura_cenarios, assinatura_historico, assinatura_cadastro, assinatura_stages = assinaturas
    try:
        metadados = ler_metadados(*assinatura_cenarios)
        validar_arquivo_historico(*assinatura_historico)
        nomes = carregar_cadastro_hidros(*assinatura_cadastro)
        calendario = carregar_calendario_dos_estagios(*assinatura_stages)
    except (ValueError, duckdb.Error, OSError) as erro:
        st.error(f"Não foi possível preparar a comparação KS: {erro}")
        return
    hydro_id = st.selectbox(
        "UHE da comparação KS", options=[int(valor) for valor in metadados["usinas"]],
        index=None, placeholder="Selecione uma UHE",
        format_func=lambda valor: f"{nomes.get(valor, f'Usina sem nome — hydro_id {valor}')} — hydro_id {valor}",
        key="ks_relatorio_usina",
    )
    if hydro_id is None:
        st.info("Selecione uma UHE para consultar a comparação KS por estágio.")
        return
    nome_usina = nomes.get(hydro_id, f"Usina sem nome — hydro_id {hydro_id}")
    assinatura_selecao = (tuple(assinaturas), hydro_id, VERSAO_COMPARACAO_KS)
    if st.session_state.get("ks_relatorio_assinatura") != assinatura_selecao:
        st.session_state["ks_relatorio_assinatura"] = assinatura_selecao
        st.session_state["ks_relatorio_pronto"] = False
        st.session_state["ks_exportacao_pronta"] = False
        st.session_state.pop("ks_relatorio_estagios", None)
    if st.button("Gerar tabela KS", key="gerar_relatorio_ks"):
        st.session_state["ks_relatorio_pronto"] = True
    if not st.session_state.get("ks_relatorio_pronto", False):
        st.info("Gere a tabela para calcular todos os estágios da UHE escolhida.")
        return
    try:
        with st.spinner(f"Calculando a comparação KS de {nome_usina}..."):
            tabela = carregar_tabela_ks_usina(
                assinatura_cenarios, assinatura_historico, assinatura_stages,
                hydro_id, nome_usina, VERSAO_COMPARACAO_KS,
            )
    except (ValueError, duckdb.Error, OSError) as erro:
        st.session_state["ks_relatorio_pronto"] = False
        st.error(f"Não foi possível gerar a tabela KS: {erro}")
        return
    estagios = st.multiselect(
        "Meses/anos da comparação KS (vazio = todos)",
        options=[int(valor) for valor in tabela["stage_id"]],
        format_func=lambda valor: rotulo_estagio_mes_ano(valor, calendario),
        key="ks_relatorio_estagios",
    )
    exibida = tabela.loc[tabela["stage_id"].isin(estagios)] if estagios else tabela
    legenda_linhas = (
        f"{len(exibida):,} linhas exibidas de {len(tabela):,}; "
        f"{int(exibida['d'].notna().sum()):,} distâncias calculadas. "
        "A exportação inclui todos os estágios da UHE."
    )
    st.caption(legenda_linhas.replace(",", "."))
    formatos = {
        "Distância KS (D)": st.column_config.NumberColumn("Distância KS (D)", format="%.6f"),
        "Diferença máxima (p.p.)": st.column_config.NumberColumn("Diferença máxima (p.p.)", format="%.2f"),
        "Vazão da diferença máxima (m³/s)": st.column_config.NumberColumn("Vazão da diferença máxima (m³/s)", format="%.2f"),
        "Cenários acumulados em x* (%)": st.column_config.NumberColumn("Cenários acumulados em x* (%)", format="%.2f"),
        "Histórico acumulado em x* (%)": st.column_config.NumberColumn("Histórico acumulado em x* (%)", format="%.2f"),
    }
    st.dataframe(tabela_ks_visivel(exibida), hide_index=True, width="stretch", height=520, column_config=formatos)
    if st.button("Preparar XLSX da comparação KS", key="preparar_exportacao_ks"):
        st.session_state["ks_exportacao_pronta"] = True
    if st.session_state.get("ks_exportacao_pronta", False):
        try:
            with st.spinner("Preparando XLSX da comparação KS..."):
                arquivo = preparar_xlsx_ks(tabela)
        except (ValueError, OSError) as erro:
            st.session_state["ks_exportacao_pronta"] = False
            st.error(f"Não foi possível preparar o XLSX KS: {erro}")
            return
        st.download_button(
            "Exportar todos os estágios desta UHE para XLSX", data=arquivo,
            file_name=nome_arquivo_ks(hydro_id),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="exportar_relatorio_ks",
        )
        st.caption("O XLSX conserva os números completos em uma aba auxiliar oculta.")


def main() -> None:  # Constrói as duas abas do analisador dentro do Streamlit.
    st.set_page_config(page_title=TITULO, layout="wide")  # Usa o título solicitado e toda a largura disponível.
    st.markdown(ESTILO, unsafe_allow_html=True)  # Aplica o tema técnico com detalhes ciano.
    st.title(TITULO)  # Exibe o nome principal da aplicação.
    st.caption("Vazões incrementais simuladas por estágio e por usina.")  # Descreve de forma breve a primeira análise.
    st.session_state.setdefault("arquivo_parquet", "")  # Conserva o caminho selecionado entre interações.
    st.session_state.setdefault("arquivo_hydros_json", "")  # Conserva o cadastro selecionado entre interações.
    st.session_state.setdefault("arquivo_historico", "")  # Conserva o histórico mensal opcional entre interações.
    st.session_state.setdefault("arquivo_stages_json", "")  # Conserva o calendário opcional entre interações.
    st.session_state.setdefault("usina_selecionada", None)  # Mantém somente uma UHE selecionada na sessão.

    # O seletor lateral usa um diálogo local e não faz upload do arquivo de vários gigabytes.
    st.sidebar.header("Arquivo e controles")  # Organiza o espaço lateral da aplicação.
    if st.sidebar.button("Selecionar arquivo Parquet", type="primary", key="botao_arquivo_sidebar"):  # Permite selecionar ou substituir a fonte.
        try:  # Captura falhas do seletor nativo sem mostrar traceback técnico.
            escolhido = guardar_arquivo_escolhido()  # Abre o Explorador e guarda uma nova fonte, quando escolhida.
        except Exception:  # Trata uma falha de abertura do diálogo.
            st.sidebar.error("Não foi possível abrir o seletor de arquivos neste computador.")  # Mostra uma mensagem simples.
            return  # Encerra esta atualização sem consultar um caminho inexistente.
        if not escolhido:  # Preserva a fonte anterior quando o diálogo foi cancelado.
            st.sidebar.info("Nenhum novo arquivo foi selecionado.")  # Informa o cancelamento sem falhar.
    if st.session_state["arquivo_parquet"]:  # Oferece o cadastro depois de uma seleção de Parquet.
        if st.sidebar.button("Selecionar hydros.json", key="botao_hydros_sidebar"):  # Permite escolher ou trocar os nomes das usinas.
            try:  # Trata uma falha do seletor nativo sem traceback na página.
                escolhido = guardar_hydros_escolhido()  # Guarda o novo cadastro sem trocar o Parquet.
            except Exception:  # Captura uma falha de abertura do diálogo local.
                st.sidebar.error("Não foi possível abrir o seletor de arquivos neste computador.")  # Orienta o usuário sem apagar a seleção atual.
                return  # Encerra esta atualização sem usar um caminho incompleto.
            if not escolhido:  # Mantém o cadastro anterior após cancelamento.
                st.sidebar.info("Nenhum novo arquivo foi selecionado.")  # Informa que nada mudou.
        if st.sidebar.button("Selecionar inflow_history.parquet", key="botao_historico_sidebar"):  # Permite escolher ou trocar o histórico mensal.
            try:  # Trata uma falha do seletor nativo sem traceback na página.
                escolhido = guardar_historico_escolhido()  # Guarda o novo histórico sem trocar os outros arquivos.
            except Exception:  # Captura uma falha de abertura do diálogo local.
                st.sidebar.error("Não foi possível abrir o seletor de arquivos neste computador.")  # Orienta o usuário sem apagar as seleções atuais.
                return  # Encerra esta atualização sem usar um caminho incompleto.
            if not escolhido:  # Mantém o histórico anterior após cancelamento.
                st.sidebar.info("Nenhum novo arquivo foi selecionado.")  # Informa que nada mudou.
        if st.sidebar.button("Selecionar stages.json", key="botao_stages_sidebar"):  # Permite escolher ou trocar o calendário dos estágios.
            try:  # Trata uma falha do seletor nativo sem traceback na página.
                escolhido = guardar_stages_escolhido()  # Guarda o novo calendário sem trocar os outros arquivos.
            except Exception:  # Captura uma falha de abertura do diálogo local.
                st.sidebar.error("Não foi possível abrir o seletor de arquivos neste computador.")  # Orienta o usuário sem apagar as seleções atuais.
                return  # Encerra esta atualização sem usar um caminho incompleto.
            if not escolhido:  # Mantém o calendário anterior após cancelamento.
                st.sidebar.info("Nenhum novo arquivo foi selecionado.")  # Informa que nada mudou.

    abas = st.tabs(["Distribuição de Vazões", "Relatório Estatístico"])  # Reserva a segunda aba aos logs exportáveis.
    with abas[1]:  # Renderiza a aba independente antes das saídas antecipadas da primeira.
        mostrar_aba_relatorio()
    with abas[0]:  # Mantém a análise de vazões dentro da aba correspondente.
        st.write("Distribuição dos cenários por estágio e comparação das médias com suas faixas de um desvio padrão populacional.")  # Explica os dois gráficos atuais.
        caminho_texto = st.session_state["arquivo_parquet"]  # Recupera a escolha preservada durante esta sessão.
        if not caminho_texto:  # Evita consultas antes de o usuário escolher uma fonte.
            st.info("Selecione o Parquet consolidado e o arquivo hydros.json para iniciar a análise.")  # Orienta as duas entradas necessárias.
            if st.button("Selecionar arquivo Parquet", type="primary", key="botao_arquivo_aba"):  # Mostra o seletor também quando a barra lateral está recolhida.
                try:  # Trata uma falha da janela nativa de seleção.
                    escolhido = guardar_arquivo_escolhido()  # Guarda o arquivo selecionado sem upload pelo navegador.
                except Exception:  # Captura uma falha do diálogo local.
                    st.error("Não foi possível abrir o seletor de arquivos neste computador.")  # Mostra uma mensagem simples.
                    return  # Evita continuar sem uma fonte válida.
                if escolhido:  # Atualiza a aba após uma seleção bem-sucedida.
                    st.rerun()  # Recarrega a interface para mostrar as usinas do arquivo escolhido.
                else:  # Trata o cancelamento do diálogo.
                    st.info("Nenhum arquivo foi selecionado.")  # Informa o cancelamento sem traceback.
            return  # Deixa a aba leve enquanto não existe arquivo selecionado.
        caminho = Path(caminho_texto)  # Converte o caminho escolhido em um objeto de arquivo.
        if not caminho.is_file():  # Confere se o Parquet ainda existe no local escolhido.
            st.error(f"Arquivo não encontrado: {caminho}")  # Mostra o caminho problemático.
            return  # Evita uma consulta a um arquivo ausente.
        if caminho.suffix.lower() != ".parquet":  # Confere a extensão antes de abrir o arquivo.
            st.error("Selecione um arquivo com extensão .parquet.")  # Explica o formato exigido.
            return  # Não tenta ler outro tipo de arquivo como Parquet.

        cadastro_texto = st.session_state["arquivo_hydros_json"]  # Recupera o caminho do cadastro preservado na sessão.
        if not cadastro_texto:  # Espera o JSON antes de mostrar a lista de usinas.
            st.info("Parquet selecionado. Agora selecione o hydros.json para carregar os nomes das usinas.")  # Indica a segunda entrada.
            if st.button("Selecionar hydros.json", key="botao_hydros_aba"):  # Mantém o seletor acessível quando a barra lateral está recolhida.
                try:  # Trata uma falha da janela nativa sem traceback.
                    escolhido = guardar_hydros_escolhido()  # Guarda o cadastro escolhido pelo usuário.
                except Exception:  # Captura uma falha do diálogo local.
                    st.error("Não foi possível abrir o seletor de arquivos neste computador.")  # Explica a falha comum.
                    return  # Evita continuar sem cadastro.
                if escolhido:  # Atualiza a interface após uma escolha válida.
                    st.rerun()  # Recarrega os nomes do arquivo selecionado.
                else:  # Trata o cancelamento sem apagar o Parquet.
                    st.info("Nenhum arquivo foi selecionado.")  # Informa que ainda falta o cadastro.
            return  # Evita consultar o Parquet antes de receber os dois arquivos.
        cadastro = Path(cadastro_texto)  # Converte a escolha do JSON em caminho de arquivo.
        if not cadastro.is_file():  # Confere se o cadastro ainda existe.
            st.error(f"Arquivo hydros.json não encontrado: {cadastro}")  # Identifica o caminho inválido.
            return  # Evita tentar ler um arquivo ausente.
        if cadastro.suffix.lower() != ".json":  # Confere a extensão antes da leitura.
            st.error("Selecione um arquivo com extensão .json para o cadastro de usinas.")  # Explica o formato exigido.
            return  # Não interpreta outro tipo de arquivo como cadastro.
        assinatura_cadastro = (str(cadastro), cadastro.stat().st_size, cadastro.stat().st_mtime_ns)  # Identifica a versão do JSON para o cache.
        try:  # Trata problemas comuns de conteúdo do cadastro.
            nomes_por_id = carregar_cadastro_hidros(*assinatura_cadastro)  # Lê os campos reais id e name das usinas.
        except (ValueError, OSError) as erro:  # Intercepta JSON inválido, estrutura incompatível ou falha de leitura.
            st.error(f"Não foi possível usar o cadastro: {erro}")  # Mostra uma causa legível sem traceback.
            return  # Evita associar nomes inventados aos IDs do Parquet.
        st.sidebar.caption("Cadastro selecionado")  # Identifica a segunda entrada na barra lateral.
        st.sidebar.code(str(cadastro), language=None)  # Mostra o caminho e o nome do JSON atualmente em uso.

        assinatura = (str(caminho), caminho.stat().st_size, caminho.stat().st_mtime_ns)  # Identifica a versão atual do arquivo.
        if st.session_state.get("assinatura_arquivo") != assinatura:  # Detecta troca ou alteração externa da fonte.
            st.session_state["usina_selecionada"] = None  # Evita reutilizar a UHE de um arquivo anterior.
            st.session_state.pop("estagio_distribuicao", None)  # Evita reutilizar um stage indisponível na nova fonte.
            st.session_state["assinatura_arquivo"] = assinatura  # Guarda a versão que será validada agora.
        st.sidebar.caption("Arquivo selecionado")  # Identifica o caminho exibido na barra lateral.
        st.sidebar.code(str(caminho), language=None)  # Mostra exatamente o arquivo consultado, sem enviá-lo ao navegador.

        # O resumo e a lista de usinas vêm apenas das colunas de chave e são guardados em cache.
        try:  # Trata arquivos corrompidos ou que não possuem o esquema necessário.
            metadados = ler_metadados(*assinatura)  # Valida o Parquet e descobre as usinas disponíveis.
        except ValueError as erro:  # Trata a ausência de colunas obrigatórias.
            st.error(str(erro))  # Mostra quais colunas faltam e quais foram encontradas.
            return  # Impede gráficos baseados em um esquema incompatível.
        except (duckdb.Error, OSError):  # Trata falha de leitura ou Parquet inválido.
            st.error("O arquivo não pôde ser lido como Parquet válido.")  # Evita traceback técnico para erro comum.
            return  # Encerra a atualização sem consultar usinas.

        opcoes, rotulos, quantidade_sem_nome = criar_rotulos_das_usinas(metadados["usinas"], nomes_por_id)  # Associa apenas usinas presentes no Parquet.
        ids_disponiveis = set(opcoes)  # Prepara a remoção de seleções inexistentes no novo Parquet.
        if st.session_state["usina_selecionada"] not in ids_disponiveis:
            st.session_state["usina_selecionada"] = None  # Descarta uma seleção que não existe no arquivo atual.
        st.sidebar.metric("Cenários no arquivo", f"{metadados['cenarios']:,}".replace(",", "."))  # Exibe a quantidade descoberta.
        st.sidebar.metric("Estágios no arquivo", metadados["estagios"])  # Exibe os estágios realmente presentes.
        st.sidebar.metric("Usinas disponíveis", len(metadados["usinas"]))  # Exibe quantas usinas podem ser escolhidas.
        st.sidebar.caption("Selecione uma UHE para analisar seus cenários.")
        st.info("Dados carregados. Selecione uma UHE para visualizar os gráficos.")
        if quantidade_sem_nome:  # Detecta IDs do Parquet sem nome no cadastro selecionado.
            texto_ausentes = "usina do Parquet não possui" if quantidade_sem_nome == 1 else "usinas do Parquet não possuem"  # Ajusta a concordância do aviso.
            st.warning(f"{quantidade_sem_nome} {texto_ausentes} correspondência no hydros.json.")  # Informa o uso do rótulo de fallback.

        mostrar_historico = st.checkbox("Mostrar histórico mensal", value=False, key="mostrar_historico_mensal")  # Ativa a comparação histórica somente quando solicitada.
        solicitar_slack = st.checkbox("Mostrar slack de não negatividade da vazão", value=False, key="mostrar_slack_nao_negatividade")  # Cria o controle independente e desmarcado por padrão.
        mostrar_slack = solicitar_slack and COLUNA_SLACK in metadados["colunas"]  # Habilita a consulta somente quando a coluna opcional existe.
        if solicitar_slack and not mostrar_slack:  # Detecta um Parquet antigo sem a variável solicitada.
            st.warning("A coluna inflow_nonnegativity_slack_m3s não foi encontrada no Parquet selecionado.")  # Avisa claramente sem interromper os outros gráficos.
        assinatura_historico = None  # Mantém a consulta histórica desativada por padrão.
        assinatura_stages = None
        meses_por_estagio = None  # Mantém os rótulos mensais desativados por padrão.
        calendario_estagios = None
        stages_texto = st.session_state["arquivo_stages_json"]
        if stages_texto:
            caminho_stages = Path(stages_texto)
            if not caminho_stages.is_file():
                st.error(f"Arquivo stages.json não encontrado: {caminho_stages}")
                return
            if caminho_stages.suffix.lower() != ".json":
                st.error("Selecione um arquivo .json para o calendário de estágios.")
                return
            assinatura_stages = (
                str(caminho_stages), caminho_stages.stat().st_size,
                caminho_stages.stat().st_mtime_ns,
            )
            try:
                calendario_completo = carregar_calendario_dos_estagios(*assinatura_stages)
            except (ValueError, OSError) as erro:
                st.error(f"Não foi possível usar o calendário de estágios: {erro}")
                return
            estagios_sem_calendario = [
                stage_id for stage_id in metadados["ids_estagios"]
                if stage_id not in calendario_completo
            ]
            if estagios_sem_calendario:
                amostra = ", ".join(str(stage_id) for stage_id in estagios_sem_calendario[:20])
                complemento = "..." if len(estagios_sem_calendario) > 20 else ""
                st.error(f"O stages.json não possui os seguintes stage_id do Parquet: {amostra}{complemento}")
                return
            calendario_estagios = {
                stage_id: calendario_completo[stage_id]
                for stage_id in metadados["ids_estagios"]
            }
            meses_por_estagio = {
                stage_id: registro["mes"]
                for stage_id, registro in calendario_estagios.items()
            }
            st.sidebar.caption("Calendário de estágios selecionado")
            st.sidebar.code(str(caminho_stages), language=None)
        elif mostrar_historico:
            st.warning("Para mostrar o histórico mensal, selecione o stages.json na barra lateral.")
            return

        if mostrar_historico:  # Exige e valida o histórico somente durante a comparação.
            historico_texto = st.session_state["arquivo_historico"]  # Recupera o caminho do histórico preservado na sessão.
            if not historico_texto:
                st.warning("Para mostrar o histórico mensal, selecione inflow_history.parquet na barra lateral.")
                return  # Evita uma comparação sem calendário ou sem observações históricas.
            caminho_historico = Path(historico_texto)  # Converte a escolha do histórico em caminho de arquivo.
            if not caminho_historico.is_file():  # Confere se o histórico ainda existe no local selecionado.
                st.error(f"Arquivo histórico não encontrado: {caminho_historico}")  # Identifica o caminho inválido.
                return  # Evita consultar um arquivo ausente.
            if caminho_historico.suffix.lower() != ".parquet":  # Confere a extensão do histórico antes da leitura.
                st.error("Selecione um arquivo .parquet para o histórico mensal.")  # Explica o formato exigido.
                return  # Não interpreta outro formato como Parquet.
            assinatura_historico = (str(caminho_historico), caminho_historico.stat().st_size, caminho_historico.stat().st_mtime_ns)  # Identifica a versão do histórico para o cache.
            try:  # Trata esquema inválido, datas incorretas e falhas de leitura das fontes adicionais.
                validar_arquivo_historico(*assinatura_historico)  # Confere as colunas e as datas usadas para obter o mês.
            except (ValueError, duckdb.Error, OSError) as erro:  # Intercepta entradas incompatíveis sem exibir traceback.
                st.error(f"Não foi possível usar a comparação histórica: {erro}")  # Mostra a causa legível para correção.
                return  # Evita produzir uma comparação parcial ou incorreta.
            st.sidebar.caption("Histórico mensal selecionado")  # Identifica a terceira entrada na barra lateral.
            st.sidebar.code(str(caminho_historico), language=None)  # Mostra o arquivo histórico atualmente em uso.

        hydro_id = st.selectbox("Selecione a UHE", options=opcoes, index=None, placeholder="Selecione uma UHE", format_func=rotulos.__getitem__, key="usina_selecionada")  # Restringe a seleção a uma UHE.
        if hydro_id is None:  # Mantém a aba leve antes de existir alguma usina escolhida.
            st.info("Selecione uma UHE para visualizar os gráficos.")
            return  # Evita ler registros de todas as usinas.

        try:  # Mantém o tratamento de falhas da seção individual da UHE.
            mostrar_usina(
                str(caminho), hydro_id, rotulos[hydro_id], mostrar_historico,
                assinatura_historico, meses_por_estagio, mostrar_slack, assinatura,
                calendario_estagios, assinatura_stages, assinatura_cadastro,
            )
        except ValueError as erro:
            st.error(str(erro))
        except (duckdb.Error, OSError):
            st.error(f"Não foi possível consultar os registros da usina {hydro_id}.")


# Quando aberto como .py, o arquivo inicia o próprio servidor; sob Streamlit, executa somente a interface.
def servidor_disponivel(endereco: str) -> bool:  # Verifica se a página local já pode receber o navegador.
    try:  # Uma conexão recusada indica que ainda é necessário iniciar ou aguardar o servidor.
        with urlopen(endereco + "/_stcore/health", timeout=1) as resposta:  # Consulta apenas a rota de saúde local.
            return resposta.status == 200  # Confirma uma resposta correta do Streamlit.
    except OSError:  # Trata a ausência do servidor sem mostrar erro técnico.
        return False  # Pede ao inicializador que aguarde ou inicie o servidor.


def abrir_aplicacao() -> None:  # Faz o duplo clique ou Run Python File abrir a aplicação no navegador.
    endereco = "http://127.0.0.1:8503"  # Usa uma porta própria para o terceiro programa neste computador.
    if not servidor_disponivel(endereco):  # Evita iniciar uma segunda cópia quando esta aplicação já responde.
        arquivo = Path(__file__).resolve()  # Descobre o caminho deste próprio arquivo Python.
        comando = [  # Prepara a execução correta do módulo Streamlit.
            sys.executable,  # Usa o Python pelo qual o usuário iniciou este programa.
            "-m",  # Pede a execução de um módulo instalado.
            "streamlit",  # Escolhe o servidor Streamlit do ambiente atual.
            "run",  # Informa que este arquivo deve ser executado como aplicação.
            str(arquivo),  # Aponta o servidor para este terceiro programa.
            "--server.address=127.0.0.1",  # Restringe o acesso ao computador local.
            "--server.port=8503",  # Usa a porta reservada para o analisador.
            "--server.headless=true",  # Deixa a abertura do navegador para depois da verificação de saúde.
            "--browser.gatherUsageStats=false",  # Desliga a telemetria opcional do Streamlit.
        ]  # Fecha a lista de argumentos do novo processo.
        sinalizadores = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Evita uma segunda janela de terminal no Windows.
        try:  # Trata falhas ao criar o processo do Streamlit.
            subprocess.Popen(comando, cwd=arquivo.parent, creationflags=sinalizadores, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # Inicia o servidor em segundo plano.
        except OSError as erro:  # Captura uma falha de execução do Python ou do Streamlit.
            messagebox.showerror(TITULO, f"Não foi possível iniciar o Streamlit:\n{erro}")  # Explica a falha em janela visível.
            return  # Não tenta abrir uma página inexistente.
        for tentativa in range(120):  # Dá até trinta segundos para o primeiro início do Streamlit.
            if servidor_disponivel(endereco):  # Verifica se a aplicação já está pronta.
                break  # Para a espera quando a página fica disponível.
            time.sleep(0.25)  # Aguarda um quarto de segundo antes de repetir a verificação.
    if not servidor_disponivel(endereco):  # Confere se a inicialização terminou com sucesso.
        messagebox.showerror(TITULO, "O Streamlit não iniciou. Verifique as dependências streamlit, duckdb, pandas e plotly.")  # Dá uma orientação simples.
        return  # Encerra sem abrir uma página indisponível.
    abriu = webbrowser.open(endereco, new=2)  # Abre o analisador em uma aba do navegador padrão.
    if not abriu:  # Trata um navegador padrão indisponível.
        messagebox.showinfo(TITULO, f"Abra este endereço no navegador:\n{endereco}")  # Entrega o endereço para abertura manual.


if __name__ == "__main__":  # Distingue a execução direta da execução da página pelo Streamlit.
    if get_script_run_ctx(suppress_warning=True) is None:  # Identifica o duplo clique ou Run Python File.
        abrir_aplicacao()  # Inicia o servidor e abre a aplicação automaticamente.
    else:  # Entra aqui quando o Streamlit já está executando o arquivo.
        main()  # Desenha a interface e a única aba implementada nesta etapa.
