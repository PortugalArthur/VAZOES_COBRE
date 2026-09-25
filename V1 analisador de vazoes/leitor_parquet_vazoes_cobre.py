"""Lê o Parquet consolidado de vazões do COBRE em páginas no Streamlit."""

from pathlib import Path  # Trabalha com o arquivo escolhido sem fixar o seu caminho no programa.
import re  # Reconhece e ordena os nomes das colunas de lag.
import subprocess  # Inicia o servidor Streamlit quando o arquivo Python é aberto diretamente.
import sys  # Localiza o mesmo interpretador Python usado para abrir este programa.
import tkinter as tk  # Abre a janela nativa de seleção de arquivo no computador local.
from tkinter import filedialog, messagebox  # Mostra o seletor de Parquet e eventuais falhas de abertura.
import time  # Aguarda o servidor ficar pronto antes de abrir a página.
from urllib.request import urlopen  # Verifica se a página local do Streamlit está disponível.
import webbrowser  # Abre a aplicação pronta no navegador padrão do Windows.

from preparar_ambiente import garantir_dependencias  # Prepara automaticamente as bibliotecas ausentes na primeira execução.

garantir_dependencias(  # Permite iniciar pelo botão Run sem executar previamente um comando de instalação.
    {
        "duckdb": "duckdb>=0.10",
        "streamlit": "streamlit>=1.28",
    }
)

import duckdb  # Consulta o Parquet diretamente, sem colocá-lo inteiro na memória do Python.
import streamlit as st  # Constrói a interface de filtros, tabela e paginação.
from streamlit.runtime.scriptrunner import get_script_run_ctx  # Diferencia o duplo clique da execução feita pelo Streamlit.


TITULO = "Leitor de Parquet de Vazões do COBRE"  # Guarda o título exato solicitado para a aplicação.
OBRIGATORIAS = ["scenario_id", "stage_id", "node_id", "hydro_id", "incremental_inflow_m3s"]  # Define as colunas mínimas válidas.
TAMANHOS_PAGINA = [100, 500, 1000, 5000]  # Oferece quantidades controladas de linhas por página.


# O estilo usa ciano nos pontos de interação e mantém fundo e texto do tema do Streamlit.
ESTILO = (  # Define apenas pequenos detalhes visuais, sem adicionar outra biblioteca.
    "<style>"  # Inicia o bloco de estilo usado na página.
    "h1 { color: #14b8c8 !important; }"  # Colore o título principal com ciano.
    "div.stButton > button[kind='primary'] {"  # Seleciona o botão principal de escolha do arquivo.
    "background-color: #079bb3; border-color: #079bb3; color: white; }"  # Aplica ciano ao botão.
    "div.stButton > button[kind='primary']:hover {"  # Seleciona o botão quando o mouse passa sobre ele.
    "background-color: #067f94; border-color: #067f94; color: white; }"  # Escurece o ciano durante a interação.
    "div[data-testid='stMetric'] {"  # Seleciona os indicadores do resumo.
    "border: 1px solid rgba(7, 155, 179, 0.38);"  # Desenha uma borda ciano discreta.
    "border-radius: 0.65rem; padding: 0.7rem 0.9rem; }"  # Dá espaço e arredondamento aos indicadores.
    "div[data-baseweb='select'] > div:focus-within {"  # Seleciona um filtro que esteja em uso.
    "border-color: #079bb3; }"  # Destaca com ciano o filtro ativo.
    "</style>"  # Encerra o bloco de estilo.
)  # Guarda todas as regras em uma única string para o Streamlit.


def abrir_seletor_parquet() -> str:  # Pede um arquivo local por meio do Explorador de Arquivos.
    janela = tk.Tk()  # Cria a janela de suporte exigida pelo seletor nativo.
    janela.withdraw()  # Esconde a janela vazia para mostrar somente o diálogo de arquivo.
    janela.attributes("-topmost", True)  # Coloca o diálogo à frente do navegador no computador local.
    try:  # Garante que a janela auxiliar seja fechada mesmo se a escolha for cancelada.
        caminho = filedialog.askopenfilename(  # Abre o Explorador para selecionar um arquivo Parquet.
            parent=janela,  # Associa o diálogo à janela auxiliar oculta.
            title="Selecionar arquivo Parquet de vazões do COBRE",  # Explica qual arquivo deve ser escolhido.
            initialdir=Path(__file__).resolve().parent,  # Começa na pasta deste programa, sem fixar o arquivo.
            filetypes=[("Arquivos Parquet", "*.parquet"), ("Todos os arquivos", "*.*")],  # Destaca os arquivos Parquet.
        )  # Guarda o caminho escolhido ou uma string vazia quando o usuário cancela.
    finally:  # Executa a limpeza após escolha, cancelamento ou falha do diálogo.
        janela.destroy()  # Fecha a janela auxiliar do Tkinter.
    return caminho  # Entrega o caminho para a aplicação guardar na sessão.


def voltar_primeira_pagina() -> None:  # Recomeça a navegação quando algum controle da consulta muda.
    st.session_state["pagina_atual"] = 1  # Evita manter uma página que pode não existir após a mudança.


def alternar_filtro_negativo() -> None:  # Ajusta a navegação e a ordenação quando o checkbox muda.
    st.session_state["pagina_atual"] = 1  # Volta à primeira página do novo conjunto filtrado.
    if st.session_state["somente_negativos"]:  # Detecta a ativação do filtro global de vazões negativas.
        st.session_state["ordenar_por"] = "incremental_inflow_m3s"  # Coloca a vazão incremental como ordenação inicial do filtro.
        st.session_state["ordem"] = "Crescente"  # Mostra primeiro o registro mais negativo do conjunto.


def limpar_filtros() -> None:  # Repõe os quatro filtros e conserva o arquivo selecionado.
    st.session_state["cenario"] = "Todos"  # Volta a mostrar todos os cenários.
    st.session_state["estagio"] = "Todos"  # Volta a mostrar todos os estágios.
    st.session_state["usina"] = "Todas"  # Volta a mostrar todas as usinas.
    st.session_state["somente_negativos"] = False  # Desativa o filtro específico de vazões negativas.
    st.session_state["pagina_atual"] = 1  # Retorna à primeira página do resultado.


def ler_estrutura(conexao: duckdb.DuckDBPyConnection, caminho: str) -> tuple[list[str], list[str]]:  # Examina o esquema sem carregar as linhas.
    descricao = conexao.execute("DESCRIBE SELECT * FROM read_parquet(?)", [caminho]).fetchall()  # Pede ao DuckDB os nomes e tipos das colunas.
    colunas = [linha[0] for linha in descricao]  # Extrai os nomes reais do Parquet selecionado.
    faltantes = [coluna for coluna in OBRIGATORIAS if coluna not in colunas]  # Identifica as colunas fundamentais ausentes.
    if faltantes:  # Interrompe a leitura quando não é o Parquet de vazões esperado.
        faltam = ", ".join(faltantes)  # Organiza os nomes ausentes para a mensagem da interface.
        encontradas = ", ".join(colunas)  # Organiza os nomes encontrados para ajudar a identificar o arquivo.
        raise ValueError(f"Colunas obrigatórias ausentes: {faltam}. Colunas encontradas: {encontradas}")  # Explica o erro sem traceback.

    lags = []  # Guarda apenas os nomes que seguem o padrão lag_<número>_m3s.
    for coluna in colunas:  # Examina cada nome de coluna do arquivo escolhido.
        if re.fullmatch(r"lag_\d+_m3s", coluna):  # Verifica se a coluna representa uma ordem de lag.
            lags.append(coluna)  # Acrescenta o lag encontrado sem fixar a quantidade máxima.
    lags.sort(key=lambda nome: int(nome.split("_")[1]))  # Ordena lag_2 antes de lag_10 pelo número, não pelo texto.
    return colunas, lags  # Entrega o esquema completo e os lags ordenados numericamente.


def ler_resumo(conexao: duckdb.DuckDBPyConnection, caminho: str) -> dict:  # Descobre os filtros e totais sem usar Pandas.
    consulta = (  # Prepara uma única varredura das colunas pequenas necessárias ao resumo.
        "SELECT COUNT(*) AS total, "  # Conta todos os registros do Parquet.
        "LIST(DISTINCT scenario_id) AS cenarios, "  # Reúne os cenários disponíveis para o filtro.
        "LIST(DISTINCT stage_id) AS estagios, "  # Reúne os estágios disponíveis para o filtro.
        "LIST(DISTINCT hydro_id) AS usinas "  # Reúne as usinas disponíveis para o filtro.
        "FROM read_parquet(?)"  # Usa diretamente o arquivo selecionado como fonte.
    )  # Fecha a consulta que entrega totais e identificadores.
    linha = conexao.execute(consulta, [caminho]).fetchone()  # Executa a descoberta diretamente no Parquet.
    cenarios = sorted(valor for valor in (linha[1] or []) if valor is not None)  # Ordena os cenários realmente existentes.
    estagios = sorted(valor for valor in (linha[2] or []) if valor is not None)  # Ordena os estágios realmente existentes.
    usinas = sorted(valor for valor in (linha[3] or []) if valor is not None)  # Ordena as usinas realmente existentes.
    return {"total": linha[0], "cenarios": cenarios, "estagios": estagios, "usinas": usinas}  # Entrega valores pequenos à interface.


def montar_filtros(caminho: str, cenario: str | int, estagio: str | int, usina: str | int, somente_negativos: bool) -> tuple[str, list]:  # Monta condições com parâmetros seguros.
    condicoes = []  # Guarda apenas condições SQL previamente definidas pelo programa.
    parametros = [caminho]  # Passa o caminho do Parquet como parâmetro ao DuckDB.
    if cenario != "Todos":  # Aplica o filtro de cenário somente quando há uma escolha específica.
        condicoes.append("scenario_id = ?")  # Adiciona a comparação com um valor parametrizado.
        parametros.append(cenario)  # Envia o ID selecionado, que veio das opções do próprio arquivo.
    if estagio != "Todos":  # Aplica o filtro de estágio somente quando há uma escolha específica.
        condicoes.append("stage_id = ?")  # Adiciona a comparação de estágio à mesma consulta.
        parametros.append(estagio)  # Envia o estágio selecionado como parâmetro.
    if usina != "Todas":  # Aplica o filtro de usina somente quando há uma escolha específica.
        condicoes.append("hydro_id = ?")  # Adiciona a comparação de usina à mesma consulta.
        parametros.append(usina)  # Envia o ID da usina selecionada como parâmetro.
    if somente_negativos:  # Aplica a condição global somente quando o checkbox está marcado.
        condicoes.append("incremental_inflow_m3s < -0.01")  # Procura valores estritamente menores que -0,01 no Parquet inteiro.

    clausula = ""  # Representa a ausência de filtros quando todas as opções estão abertas.
    if condicoes:  # Verifica se ao menos um filtro foi escolhido.
        clausula = " WHERE " + " AND ".join(condicoes)  # Combina todos os filtros diretamente na consulta ao Parquet.
    return clausula, parametros  # Entrega a cláusula e os valores na mesma ordem dos pontos de interrogação.


def contar_registros(conexao: duckdb.DuckDBPyConnection, clausula: str, parametros: list) -> int:  # Conta todo o resultado filtrado.
    consulta = "SELECT COUNT(*) FROM read_parquet(?)" + clausula  # Monta a contagem com os filtros antes da paginação.
    total = conexao.execute(consulta, parametros).fetchone()[0]  # Consulta o Parquet sem copiar as linhas para a interface.
    return total  # Entrega o número usado no resumo e na quantidade de páginas.


def buscar_menor_vazao(conexao: duckdb.DuckDBPyConnection, clausula: str, parametros: list):  # Localiza o registro mais negativo de todo o conjunto filtrado.
    consulta = (  # Monta uma consulta pequena com os campos necessários para identificar o registro.
        "SELECT scenario_id, stage_id, node_id, hydro_id, incremental_inflow_m3s "  # Seleciona a chave completa e o valor encontrado.
        "FROM read_parquet(?)" + clausula  # Aplica exatamente os mesmos filtros usados na contagem e na tabela.
        + " ORDER BY incremental_inflow_m3s ASC, scenario_id ASC, stage_id ASC, node_id ASC, hydro_id ASC "  # Coloca o menor valor na primeira posição e estabiliza empates.
        "LIMIT 1"  # Transfere somente o registro mais negativo para a interface.
    )  # Fecha o texto da consulta global.
    return conexao.execute(consulta, parametros).fetchone()  # Entrega uma única linha sem carregar o conjunto em Pandas.


def formatar_decimal_br(valor: float) -> str:  # Formata a vazão com separadores brasileiros e duas casas decimais.
    texto = f"{valor:,.2f}"  # Produz uma representação curta com agrupamento de milhares.
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")  # Troca os separadores para o padrão brasileiro.


def carregar_pagina(conexao: duckdb.DuckDBPyConnection, clausula: str, parametros: list, colunas: list[str], coluna: str, ordem: str, tamanho: int, pagina: int):  # Lê só a página visível.
    nomes_sql = []  # Guarda os nomes reais das colunas na ordem desejada para a tabela.
    for nome in colunas:  # Percorre todas as colunas, incluindo os lags descobertos.
        nomes_sql.append('"' + nome.replace('"', '""') + '"')  # Protege cada nome de coluna usado na consulta SQL.
    selecao_sql = ", ".join(nomes_sql)  # Organiza as colunas, com os lags em ordem numérica.
    coluna_sql = '"' + coluna.replace('"', '""') + '"'  # Protege o nome real da coluna usado na ordenação.
    direcao_sql = "ASC" if ordem == "Crescente" else "DESC"  # Converte uma das duas opções da interface em direção SQL.
    deslocamento = (pagina - 1) * tamanho  # Calcula quantas linhas devem ser ignoradas antes da página atual.
    consulta = f"SELECT {selecao_sql} FROM read_parquet(?)" + clausula  # Seleciona todas as colunas e aplica os filtros no Parquet.
    consulta += f" ORDER BY {coluna_sql} {direcao_sql} NULLS LAST"  # Ordena todo o resultado filtrado antes da paginação.
    consulta += ", scenario_id ASC, stage_id ASC, node_id ASC, hydro_id ASC"  # Desempata resultados para manter as páginas estáveis.
    consulta += " LIMIT ? OFFSET ?"  # Restringe a transferência à página solicitada.
    valores = parametros + [tamanho, deslocamento]  # Acrescenta limite e deslocamento como parâmetros seguros.
    return conexao.execute(consulta, valores).fetchdf()  # Converte somente a página pequena para Pandas e a entrega ao Streamlit.


def main() -> None:  # Organiza a interface da seleção do arquivo até a tabela paginada.
    st.set_page_config(page_title=TITULO, layout="wide")  # Usa o título exato e aproveita a largura da tela.
    st.markdown(ESTILO, unsafe_allow_html=True)  # Aplica os detalhes ciano definidos acima.
    st.title(TITULO)  # Mostra o título principal solicitado.
    st.caption("Explore cenários, estágios, usinas e lags diretamente do arquivo Parquet.")  # Explica a finalidade da página.

    st.session_state.setdefault("arquivo_parquet", "")  # Mantém o caminho escolhido entre mudanças de filtro.
    st.session_state.setdefault("pagina_atual", 1)  # Inicia a navegação na primeira página.
    st.session_state.setdefault("cenario", "Todos")  # Inicia com todos os cenários disponíveis.
    st.session_state.setdefault("estagio", "Todos")  # Inicia com todos os estágios disponíveis.
    st.session_state.setdefault("usina", "Todas")  # Inicia com todas as usinas disponíveis.
    st.session_state.setdefault("somente_negativos", False)  # Inicia com o filtro global de vazões negativas desligado.
    st.session_state.setdefault("ordenar_por", "scenario_id")  # Usa cenário como ordenação inicial.
    st.session_state.setdefault("ordem", "Crescente")  # Usa ordem crescente como ponto de partida.
    st.session_state.setdefault("linhas_por_pagina", 1000)  # Mostra inicialmente mil registros por página.
    st.session_state.setdefault("contagens", {})  # Conserva contagens já calculadas para os filtros atuais.
    st.session_state.setdefault("resumos_negativos", {})  # Conserva o menor registro de cada combinação de filtros.

    # A seleção usa o diálogo do computador local; o Parquet não é enviado pelo navegador.
    if st.button("Selecionar arquivo Parquet", type="primary"):  # Permite escolher ou trocar o arquivo quando desejado.
        try:  # Trata uma eventual falha do seletor nativo sem mostrar traceback.
            selecionado = abrir_seletor_parquet()  # Abre o Explorador e recebe o caminho selecionado.
        except Exception:  # Captura um erro comum de abertura do diálogo local.
            st.error("Não foi possível abrir o seletor de arquivos neste computador.")  # Explica o problema em linguagem simples.
            return  # Encerra esta execução antes de usar uma seleção inexistente.
        if selecionado:  # Guarda o arquivo somente quando houve uma escolha.
            st.session_state["arquivo_parquet"] = selecionado  # Preserva o caminho durante os próximos filtros e páginas.
            st.session_state["assinatura_arquivo"] = None  # Obriga a leitura do esquema do novo arquivo.
            st.session_state["contagens"] = {}  # Descarta contagens calculadas para o arquivo anterior.
            st.session_state["cenario"] = "Todos"  # Reinicia o filtro de cenário para o novo arquivo.
            st.session_state["estagio"] = "Todos"  # Reinicia o filtro de estágio para o novo arquivo.
            st.session_state["usina"] = "Todas"  # Reinicia o filtro de usina para o novo arquivo.
            st.session_state["somente_negativos"] = False  # Desliga o filtro negativo ao trocar a fonte de dados.
            st.session_state["ordenar_por"] = "scenario_id"  # Reinicia a ordenação para uma coluna obrigatória.
            st.session_state["pagina_atual"] = 1  # Volta à primeira página do novo arquivo.
            st.session_state["resumos_negativos"] = {}  # Descarta menores valores calculados para o arquivo anterior.
        else:  # Trata o cancelamento sem perder um arquivo que já estava selecionado.
            st.info("Nenhum novo arquivo foi selecionado.")  # Informa que a seleção foi cancelada.

    caminho_texto = st.session_state["arquivo_parquet"]  # Recupera o arquivo selecionado anteriormente.
    if not caminho_texto:  # Evita qualquer consulta antes da seleção de um arquivo.
        st.info("Selecione o arquivo Parquet de vazões do COBRE para iniciar a leitura.")  # Orienta o usuário na tela inicial.
        return  # Termina a atualização sem abrir um Parquet.

    caminho = Path(caminho_texto)  # Converte o caminho guardado em um objeto de arquivo.
    if not caminho.is_file():  # Confere se o arquivo continua no local escolhido.
        st.error(f"Arquivo não encontrado: {caminho}")  # Mostra qual arquivo precisa ser selecionado novamente.
        return  # Evita consultas sobre um caminho inexistente.
    if caminho.suffix.lower() != ".parquet":  # Verifica a extensão antes de tentar a leitura.
        st.error("Selecione um arquivo com extensão .parquet.")  # Explica o formato aceito.
        return  # Evita tratar outro tipo de arquivo como Parquet.

    st.write(f"**Arquivo selecionado:** `{caminho}`")  # Mostra o caminho preservado na sessão.
    assinatura = (str(caminho), caminho.stat().st_size, caminho.stat().st_mtime_ns)  # Identifica mudanças no arquivo após a seleção.

    # O esquema e o resumo são lidos uma vez por versão do arquivo e guardados na sessão.
    if st.session_state.get("assinatura_arquivo") != assinatura:  # Recalcula apenas para um arquivo novo ou modificado.
        conexao = duckdb.connect(database=":memory:")  # Abre uma conexão temporária sem criar banco no disco.
        try:  # Valida o esquema e descobre os identificadores por uma consulta ao Parquet.
            colunas, lags = ler_estrutura(conexao, str(caminho))  # Confirma as colunas obrigatórias e identifica os lags.
            resumo = ler_resumo(conexao, str(caminho))  # Descobre totais, cenários, estágios e usinas existentes.
        except ValueError as erro:  # Mostra a relação de colunas ausentes e encontradas.
            st.error(str(erro))  # Apresenta o problema estrutural sem traceback técnico.
            return  # Não mostra filtros baseados em um esquema inválido.
        except (duckdb.Error, OSError):  # Captura arquivo inválido, corrompido ou ilegível.
            st.error("O arquivo não pôde ser lido como Parquet válido.")  # Informa a falha de leitura de forma simples.
            return  # Evita consultas adicionais ao arquivo problemático.
        finally:  # Libera a conexão mesmo quando a validação falha.
            conexao.close()  # Fecha o DuckDB sem modificar o Parquet.
        st.session_state["colunas"] = colunas  # Conserva os nomes das colunas para a ordenação.
        st.session_state["lags"] = lags  # Conserva os lags encontrados em ordem numérica.
        st.session_state["resumo"] = resumo  # Conserva as opções dos filtros e os totais do arquivo.
        st.session_state["assinatura_arquivo"] = assinatura  # Marca qual versão do arquivo já foi examinada.
        st.session_state["contagens"] = {}  # Reinicia as contagens dos filtros quando o arquivo muda.
        st.session_state["resumos_negativos"] = {}  # Reinicia os menores valores quando o arquivo muda.
        st.session_state["pagina_atual"] = 1  # Reinicia a navegação para a versão atual do arquivo.

    colunas = st.session_state["colunas"]  # Obtém os nomes reais do esquema validado.
    lags = st.session_state["lags"]  # Obtém a lista de lags detectados automaticamente.
    resumo = st.session_state["resumo"]  # Obtém os totais e as opções de filtros já calculados.
    colunas_exibicao = OBRIGATORIAS + lags  # Coloca as chaves, a vazão atual e os lags em ordem numérica.
    for coluna in colunas:  # Preserva também eventuais colunas adicionais existentes no Parquet.
        if coluna not in colunas_exibicao:  # Evita repetir as colunas fundamentais ou os lags.
            colunas_exibicao.append(coluna)  # Coloca a coluna adicional depois dos lags.

    # O resumo usa listas pequenas de IDs retornadas pelo DuckDB, não as linhas completas do Parquet.
    st.subheader("Resumo do arquivo")  # Identifica os indicadores gerais antes dos filtros.
    metrica_cenarios, metrica_estagios, metrica_usinas, metrica_linhas, metrica_lags = st.columns(5)  # Distribui os cinco totais na largura da tela.
    metrica_cenarios.metric("Cenários encontrados", f"{len(resumo['cenarios']):,}".replace(",", "."))  # Mostra cenários distintos.
    metrica_estagios.metric("Estágios encontrados", f"{len(resumo['estagios']):,}".replace(",", "."))  # Mostra estágios distintos.
    metrica_usinas.metric("Usinas encontradas", f"{len(resumo['usinas']):,}".replace(",", "."))  # Mostra usinas distintas.
    metrica_linhas.metric("Registros no arquivo", f"{resumo['total']:,}".replace(",", "."))  # Mostra todas as linhas do Parquet.
    metrica_lags.metric("Quantidade de lags", len(lags))  # Mostra quantas colunas lag_N_m3s foram descobertas.

    # O botão de limpeza aparece antes dos controles para poder redefinir seus valores nesta execução.
    st.subheader("Filtros e ordenação")  # Identifica a área de exploração da tabela.
    st.button("Limpar filtros", on_click=limpar_filtros)  # Restaura os três filtros sem esquecer o arquivo selecionado.
    campo_cenario, campo_estagio, campo_usina = st.columns(3)  # Coloca os três filtros principais lado a lado.
    opcoes_cenario = ["Todos"] + resumo["cenarios"]  # Oferece todos os cenários e a opção sem filtro.
    opcoes_estagio = ["Todos"] + resumo["estagios"]  # Oferece todos os estágios e a opção sem filtro.
    opcoes_usina = ["Todas"] + resumo["usinas"]  # Oferece todas as usinas e a opção sem filtro.
    cenario = campo_cenario.selectbox("Cenário (scenario_id)", opcoes_cenario, key="cenario", on_change=voltar_primeira_pagina)  # Escolhe um cenário real.
    estagio = campo_estagio.selectbox("Estágio (stage_id)", opcoes_estagio, key="estagio", on_change=voltar_primeira_pagina)  # Escolhe um estágio real.
    usina = campo_usina.selectbox("Usina (hydro_id)", opcoes_usina, key="usina", on_change=voltar_primeira_pagina)  # Escolhe uma usina real.
    somente_negativos = st.checkbox("Mostrar somente vazões incrementais < -0,01 m³/s", key="somente_negativos", on_change=alternar_filtro_negativo)  # Ativa a busca global antes da paginação.

    campo_ordenar, campo_ordem, campo_tamanho = st.columns([2, 1, 1])  # Agrupa ordenação, direção e tamanho da página.
    ordenar_por = campo_ordenar.selectbox("Ordenar por", colunas_exibicao, key="ordenar_por", on_change=voltar_primeira_pagina)  # Permite ordenar por uma coluna do esquema real.
    ordem = campo_ordem.selectbox("Ordem", ["Crescente", "Decrescente"], key="ordem", on_change=voltar_primeira_pagina)  # Escolhe maiores ou menores primeiro.
    tamanho = campo_tamanho.selectbox("Linhas por página", TAMANHOS_PAGINA, key="linhas_por_pagina", on_change=voltar_primeira_pagina)  # Limita o tamanho da tabela visível.

    # A contagem e a página são consultadas diretamente no Parquet com os quatro filtros combinados.
    clausula, parametros = montar_filtros(str(caminho), cenario, estagio, usina, somente_negativos)  # Monta as condições e seus valores parametrizados.
    chave_contagem = (cenario, estagio, usina, somente_negativos)  # Identifica todos os filtros para reutilizar a contagem correta.
    contagens = st.session_state["contagens"]  # Obtém o pequeno cache de contagens desta versão do arquivo.
    resumos_negativos = st.session_state["resumos_negativos"]  # Obtém o cache dos registros mais negativos já consultados.
    menor_registro = None  # Mantém o resumo negativo vazio enquanto o filtro estiver desligado.
    conexao = duckdb.connect(database=":memory:")  # Abre uma conexão temporária para as consultas atuais.
    try:  # Garante que qualquer erro de consulta seja apresentado de forma clara.
        if chave_contagem not in contagens:  # Evita repetir a contagem ao trocar apenas de página ou de ordenação.
            contagens[chave_contagem] = contar_registros(conexao, clausula, parametros)  # Conta todas as linhas filtradas uma vez.
        total_filtrado = contagens[chave_contagem]  # Recupera a quantidade completa de registros filtrados.
        if somente_negativos and total_filtrado:  # Busca o menor valor apenas quando existem registros negativos.
            if chave_contagem not in resumos_negativos:  # Evita repetir a busca ao trocar página ou ordenação manual.
                resumos_negativos[chave_contagem] = buscar_menor_vazao(conexao, clausula, parametros)  # Consulta o registro mais negativo do conjunto inteiro.
            menor_registro = resumos_negativos[chave_contagem]  # Recupera o registro global associado ao menor valor.
        total_paginas = max(1, (total_filtrado + tamanho - 1) // tamanho)  # Calcula quantas páginas existem para o tamanho escolhido.
        pagina = min(st.session_state["pagina_atual"], total_paginas)  # Corrige uma página antiga que deixou de existir.
        st.session_state["pagina_atual"] = pagina  # Guarda a página efetivamente mostrada.
        if total_filtrado:  # Evita executar uma consulta de página quando os filtros não encontram registros.
            dados_pagina = carregar_pagina(conexao, clausula, parametros, colunas_exibicao, ordenar_por, ordem, tamanho, pagina)  # Lê só a página atual.
    except (duckdb.Error, OSError, ValueError):  # Captura uma falha de leitura ou consulta ao Parquet.
        st.error("Não foi possível consultar o Parquet com os filtros selecionados.")  # Explica a falha sem mostrar SQL técnico.
        return  # Não tenta exibir uma tabela incompleta.
    finally:  # Fecha a conexão em qualquer resultado da consulta.
        conexao.close()  # Libera recursos sem escrever no arquivo original.

    if somente_negativos:  # Mostra os indicadores específicos somente quando o filtro estiver ativo.
        st.subheader("Resumo das vazões negativas")  # Identifica os resultados calculados sobre todo o conjunto filtrado.
        metrica_quantidade, metrica_menor = st.columns(2)  # Coloca quantidade e menor valor lado a lado.
        metrica_quantidade.metric("Registros com vazão < -0,01 m³/s", f"{total_filtrado:,}".replace(",", "."))  # Mostra a contagem anterior à paginação.
        menor_texto = formatar_decimal_br(float(menor_registro[4])) if menor_registro else "—"  # Formata o menor valor ou indica conjunto vazio.
        metrica_menor.metric("Menor vazão incremental encontrada", f"{menor_texto} m³/s" if menor_registro else "—")  # Mostra o extremo calculado globalmente.
        if menor_registro:  # Apresenta as chaves associadas ao menor valor encontrado.
            st.caption(f"Registro mais negativo — scenario_id: {menor_registro[0]} | stage_id: {menor_registro[1]} | node_id: {menor_registro[2]} | hydro_id: {menor_registro[3]}")  # Permite localizar exatamente o registro no resultado.

    # A tabela usa somente o pequeno resultado da consulta já filtrada, ordenada e paginada.
    st.subheader("Registros")  # Identifica a tabela principal.
    st.write(f"**Registros encontrados:** {total_filtrado:,}".replace(",", "."))  # Mostra a contagem de todos os filtros, não só da página.
    if total_filtrado == 0:  # Trata combinações de filtros que não encontram linhas.
        st.info("Nenhum registro encontrado para os filtros selecionados.")  # Mostra a mensagem solicitada para resultado vazio.
        return  # Dispensa tabela e navegação quando não há registros.
    st.dataframe(dados_pagina, width="stretch", height=600, hide_index=True)  # Mostra todas as colunas com rolagem vertical e horizontal.

    # Os botões alteram apenas o número da página e mantêm caminho, filtros e ordenação na sessão.
    anterior, indicador, proxima = st.columns([1, 2, 1])  # Distribui a navegação abaixo da tabela.
    if anterior.button("Página anterior", disabled=pagina <= 1):  # Permite voltar quando existe página anterior.
        st.session_state["pagina_atual"] = pagina - 1  # Escolhe a página imediatamente anterior.
        st.rerun()  # Refaz apenas as consultas necessárias para mostrar a nova página.
    indicador.markdown(f"<div style='text-align:center; padding-top:0.5rem; color:#078da4;'><b>Página {pagina:,} de {total_paginas:,}</b></div>".replace(",", "."), unsafe_allow_html=True)  # Mostra a posição atual.
    if proxima.button("Próxima página", disabled=pagina >= total_paginas):  # Permite avançar quando existe página seguinte.
        st.session_state["pagina_atual"] = pagina + 1  # Escolhe a próxima página.
        st.rerun()  # Atualiza a tabela mantendo os filtros e o arquivo.


def servidor_disponivel(endereco: str) -> bool:  # Verifica se o leitor local já pode responder ao navegador.
    try:  # Uma conexão recusada significa que o servidor ainda não está pronto.
        with urlopen(endereco + "/_stcore/health", timeout=1) as resposta:  # Consulta apenas a rota de saúde do Streamlit local.
            return resposta.status == 200  # Confirma que há um servidor respondendo corretamente.
    except OSError:  # Trata a ausência do servidor sem mostrar erro técnico ao usuário.
        return False  # Informa que ainda é necessário iniciar ou aguardar o servidor.


def abrir_aplicacao() -> None:  # Inicia o Streamlit e abre a página quando o usuário executa este arquivo diretamente.
    endereco = "http://127.0.0.1:8502"  # Usa somente o próprio computador para oferecer a interface.
    if not servidor_disponivel(endereco):  # Evita abrir uma segunda cópia quando o leitor já está em execução.
        arquivo = Path(__file__).resolve()  # Localiza este programa mesmo quando foi aberto por duplo clique.
        comando = [  # Monta os argumentos necessários para iniciar o Streamlit corretamente.
            sys.executable,  # Usa o mesmo Python que executou este arquivo.
            "-m",  # Executa o pacote Streamlit como módulo do Python.
            "streamlit",  # Escolhe o servidor Streamlit instalado neste ambiente.
            "run",  # Pede ao Streamlit que rode o programa de interface.
            str(arquivo),  # Passa o caminho completo deste leitor ao servidor.
            "--server.address=127.0.0.1",  # Mantém o servidor acessível somente neste computador.
            "--server.port=8502",  # Mantém o endereço usado por este projeto.
            "--server.headless=true",  # Deixa a abertura do navegador para as linhas abaixo.
            "--browser.gatherUsageStats=false",  # Desliga a coleta opcional de estatísticas do Streamlit.
        ]  # Fecha a lista de argumentos que será enviada ao novo processo.
        sinalizadores = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Evita abrir uma segunda janela de terminal no Windows.
        try:  # Trata uma instalação ausente ou uma falha ao iniciar o servidor.
            subprocess.Popen(comando, cwd=arquivo.parent, creationflags=sinalizadores, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # Inicia o servidor sem bloquear a abertura do navegador.
        except OSError as erro:  # Captura uma falha de execução do Python ou do Streamlit.
            messagebox.showerror("Leitor do COBRE", f"Não foi possível iniciar o Streamlit:\n{erro}")  # Explica a falha em uma janela visível.
            return  # Encerra sem tentar abrir uma página indisponível.
        for tentativa in range(120):  # Dá até trinta segundos para o primeiro início do Streamlit.
            if servidor_disponivel(endereco):  # Verifica se a página já pode ser aberta.
                break  # Para de esperar quando o servidor responde.
            time.sleep(0.25)  # Espera um quarto de segundo antes da próxima verificação.

    if not servidor_disponivel(endereco):  # Confirma o resultado da inicialização antes de abrir o navegador.
        messagebox.showerror("Leitor do COBRE", "O Streamlit não iniciou. Instale as dependências do requirements_leitor_parquet.txt e tente novamente.")  # Mostra uma orientação simples.
        return  # Não abre uma página que ainda não existe.
    abriu = webbrowser.open(endereco, new=2)  # Abre o leitor em uma nova aba do navegador padrão.
    if not abriu:  # Detecta quando o Windows não conseguiu acionar um navegador.
        messagebox.showinfo("Leitor do COBRE", f"Abra este endereço no navegador:\n{endereco}")  # Entrega o endereço para abertura manual.


if __name__ == "__main__":  # Decide entre a execução por duplo clique e a execução dentro do Streamlit.
    if get_script_run_ctx(suppress_warning=True) is None:  # Identifica a execução direta do arquivo Python.
        abrir_aplicacao()  # Inicia o servidor e mostra a página no navegador.
    else:  # Trata a execução normal feita pelo comando streamlit run.
        main()  # Constrói a interface visual solicitada.
