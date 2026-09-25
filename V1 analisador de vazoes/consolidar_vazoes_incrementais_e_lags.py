"""Consolida as vazões incrementais atuais e os lags da simulação do COBRE."""

from pathlib import Path  # Permite trabalhar com pastas e arquivos sem fixar caminhos no código.
import os  # Permite substituir o arquivo final somente depois de concluir a escrita.
import sys  # Permite sinalizar erro quando o programa é executado diretamente.
import tkinter as tk  # Cria a janela básica usada pelos seletores de pastas.
from tkinter import filedialog, messagebox  # Abre os seletores e mostra mensagens ao usuário.

from preparar_ambiente import garantir_dependencias  # Prepara automaticamente as bibliotecas ausentes na primeira execução.

garantir_dependencias(  # Permite iniciar pelo botão Run sem executar previamente um comando de instalação.
    {
        "polars": "polars>=0.20",
        "pyarrow": "pyarrow>=14",
    }
)

import polars as pl  # Lê, verifica, transforma e junta as tabelas de cada cenário.
import pyarrow.parquet as pq  # Grava vários cenários em um único arquivo Parquet.


CHAVE = ["scenario_id", "stage_id", "node_id", "hydro_id"]  # Define os quatro identificadores que impedem misturas entre registros.
COLUNA_SLACK = "inflow_nonnegativity_slack_m3s"  # Identifica a folga de não negatividade copiada diretamente da saída hydros.
COLUNAS_HYDROS = CHAVE + ["block_id", "incremental_inflow_m3s", COLUNA_SLACK]  # Lê apenas os campos necessários do arquivo hydros.
COLUNAS_LAGS = CHAVE + ["lag_index", "inflow_m3s"]  # Lê apenas os campos necessários do arquivo inflow_lags.


def encontrar_cenarios(pasta: Path, nome_fonte: str) -> dict[int, Path]:  # Localiza os arquivos de cada cenário de uma fonte.
    if not pasta.is_dir():  # Verifica se a pasta principal existe e é um diretório.
        raise ValueError(f"A pasta {nome_fonte} não existe: {pasta}")  # Explica qual pasta selecionada está incorreta.

    cenarios = {}  # Guarda cada caminho pelo número do cenário, sem depender da ordem dos arquivos.
    for subpasta in pasta.glob("scenario_id=*"):  # Procura somente as entradas com o nome esperado.
        if not subpasta.is_dir():  # Verifica se a entrada encontrada é realmente uma pasta.
            raise ValueError(f"Entrada de cenário não é uma pasta: {subpasta}")  # Rejeita uma estrutura inesperada.
        identificador = subpasta.name.removeprefix("scenario_id=")  # Extrai o identificador escrito no nome da pasta.
        if not identificador.isdecimal():  # Exige um identificador numérico para associar os cenários com segurança.
            raise ValueError(f"Identificador de cenário inválido: {subpasta}")  # Mostra a pasta com nome inválido.
        numero = int(identificador)  # Converte o identificador para comparar pastas com diferentes quantidades de zeros.
        if numero in cenarios:  # Detecta duas pastas que representam o mesmo cenário numérico.
            raise ValueError(f"Cenário {numero} repetido em {nome_fonte}: {subpasta}")  # Impede uma associação ambígua.
        arquivo = subpasta / "data.parquet"  # Monta o caminho do Parquet esperado dentro da pasta do cenário.
        if not arquivo.is_file():  # Confirma que o Parquet correspondente existe.
            raise ValueError(f"Arquivo ausente em {nome_fonte}: {arquivo}")  # Informa precisamente o arquivo faltante.
        cenarios[numero] = arquivo  # Associa o número do cenário ao respectivo Parquet.

    if not cenarios:  # Verifica se a pasta selecionada continha pelo menos um cenário.
        raise ValueError(f"Nenhuma pasta scenario_id=* encontrada em {nome_fonte}: {pasta}")  # Informa a estrutura esperada.
    return cenarios  # Entrega o mapa de cenários para a associação entre as fontes.


def preparar_cenarios(pasta_hydros: Path, pasta_lags: Path) -> tuple[dict[int, Path], dict[int, Path]]:  # Valida as duas fontes antes da leitura.
    hydros = encontrar_cenarios(pasta_hydros, "hydros")  # Descobre os arquivos de vazão atual.
    lags = encontrar_cenarios(pasta_lags, "inflow_lags")  # Descobre os arquivos das vazões passadas.
    print(f"Cenários em hydros: {len(hydros)}", flush=True)  # Mostra quantos cenários de vazão atual existem.
    print(f"Cenários em inflow_lags: {len(lags)}", flush=True)  # Mostra quantos cenários de lags existem.

    faltam_lags = sorted(set(hydros) - set(lags))  # Identifica cenários que aparecem apenas em hydros.
    faltam_hydros = sorted(set(lags) - set(hydros))  # Identifica cenários que aparecem apenas em inflow_lags.
    if faltam_lags or faltam_hydros:  # Interrompe a execução se as duas fontes não tiverem os mesmos cenários.
        raise ValueError(f"Cenários sem inflow_lags: {faltam_lags}; cenários sem hydros: {faltam_hydros}")  # Lista os cenários ausentes.
    print(f"Cenários encontrados: {len(hydros)}", flush=True)  # Mostra o total de cenários associados com segurança.
    return hydros, lags  # Entrega os dois mapas associados pelo identificador numérico.


def verificar_cenario(tabela: pl.DataFrame, numero: int, fonte: str) -> None:  # Confere o identificador armazenado no próprio Parquet.
    if tabela.is_empty():  # Rejeita um cenário sem linhas, que não produziria informações úteis.
        raise ValueError(f"{fonte}, cenário {numero}: o Parquet está vazio")  # Explica qual arquivo precisa de atenção.
    if tabela.select(pl.col("scenario_id").is_null().any()).item():  # Procura identificadores de cenário ausentes.
        raise ValueError(f"{fonte}, cenário {numero}: scenario_id nulo")  # Evita associar uma linha sem cenário definido.
    if tabela.filter(pl.col("scenario_id") != numero).height:  # Compara cada linha com o identificador da pasta.
        raise ValueError(f"{fonte}, cenário {numero}: scenario_id do arquivo difere do nome da pasta")  # Evita misturar cenários.
    for coluna in CHAVE:  # Examina cada identificador necessário à junção.
        if tabela.select(pl.col(coluna).is_null().any()).item():  # Procura valores ausentes na chave.
            raise ValueError(f"{fonte}, cenário {numero}: {coluna} nulo")  # Informa qual identificador está incompleto.


def verificar_chave_unica(tabela: pl.DataFrame, colunas: list[str], fonte: str, numero: int) -> None:  # Detecta linhas repetidas sem agregá-las.
    repetidas = tabela.group_by(colunas).agg(pl.len().alias("quantidade"))  # Conta quantas linhas existem por chave.
    repetidas = repetidas.filter(pl.col("quantidade") > 1)  # Mantém apenas as chaves que aparecem mais de uma vez.
    if not repetidas.is_empty():  # Interrompe o processamento diante de qualquer duplicidade.
        exemplo = repetidas.row(0, named=True)  # Guarda uma chave repetida para a mensagem de erro.
        raise ValueError(f"{fonte}, cenário {numero}: chave duplicada {exemplo}")  # Mostra a chave problemática sem escolher uma linha.


def selecionar_vazao_atual(tabela: pl.DataFrame, numero: int) -> pl.DataFrame:  # Obtém uma única vazão atual por estágio e usina.
    verificar_cenario(tabela, numero, "hydros")  # Confere as chaves e o cenário dentro do arquivo hydros.
    registros_de_estagio = tabela.filter(pl.col("block_id").is_null())  # Procura o registro de estágio indicado pelo COBRE atual.
    total_chaves = tabela.select(CHAVE).unique().height  # Conta as combinações de cenário, estágio, nó e usina.
    bloco_zero = tabela.filter(pl.col("block_id") == 0)  # Separa o bloco escolhido explicitamente para copiar o slack.
    verificar_chave_unica(bloco_zero, CHAVE, "hydros com block_id=0", numero)  # Exige uma só cópia do bloco 0 por chave.
    if bloco_zero.height != total_chaves:  # Confirma que o slack do bloco 0 existe para todas as combinações.
        raise ValueError(f"hydros, cenário {numero}: falta block_id=0 para alguma chave")  # Não substitui o slack por outro bloco.
    slack_bloco_zero = bloco_zero.select(CHAVE + [COLUNA_SLACK])  # Guarda o slack do bloco 0 sem comparar seu valor com os demais blocos.

    if not registros_de_estagio.is_empty():  # Prioriza os registros de estágio quando block_id é nulo.
        verificar_chave_unica(registros_de_estagio, CHAVE, "hydros com block_id nulo", numero)  # Exige uma só linha de estágio por chave.
        if registros_de_estagio.height != total_chaves:  # Confirma que todas as chaves possuem registro de estágio.
            raise ValueError(f"hydros, cenário {numero}: nem todas as chaves têm block_id nulo")  # Evita perder usinas ou estágios.
        vazoes = registros_de_estagio.select(CHAVE + ["incremental_inflow_m3s"])  # Usa a vazão de estágio, mantendo o slack separado no bloco 0.
    else:  # Trata versões em que a vazão incremental é repetida em todos os blocos.
        valores_por_chave = tabela.group_by(CHAVE).agg(  # Conta somente os valores distintos da vazão incremental entre os blocos.
            pl.col("incremental_inflow_m3s").n_unique().alias("quantidade_vazao"),  # Verifica a repetição segura da vazão entre patamares.
        )
        divergentes = valores_por_chave.filter(pl.col("quantidade_vazao") != 1)  # Identifica somente vazões incrementais diferentes entre blocos.
        if not divergentes.is_empty():  # Rejeita a escolha de um bloco quando os valores divergem.
            exemplo = divergentes.row(0, named=True)  # Guarda uma chave com valores conflitantes.
            raise ValueError(f"hydros, cenário {numero}: vazão incremental difere entre blocos em {exemplo}")  # Explica a ambiguidade restante.
        vazoes = bloco_zero.select(CHAVE + ["incremental_inflow_m3s"])  # Usa a vazão repetida do bloco 0 após validar somente essa variável.

    vazoes = vazoes.join(slack_bloco_zero, on=CHAVE, how="left", validate="1:1")  # Acrescenta sempre o slack vindo do bloco 0.
    return vazoes.select(CHAVE + ["incremental_inflow_m3s", COLUNA_SLACK])  # Entrega uma linha por chave sem manter block_id.


def descobrir_indices_lag(arquivos_lags: dict[int, Path]) -> tuple[list[int], int]:  # Descobre todas as ordens de lag existentes.
    indices = set()  # Acumula os índices encontrados em todos os cenários.
    for numero in sorted(arquivos_lags):  # Percorre cada cenário antes de definir as colunas do arquivo final.
        coluna = pl.read_parquet(arquivos_lags[numero], columns=["lag_index"])  # Lê somente o pequeno campo de índice de lag.
        if coluna.select(pl.col("lag_index").is_null().any()).item():  # Impede que um lag sem índice seja colocado na coluna errada.
            raise ValueError(f"inflow_lags, cenário {numero}: lag_index nulo")  # Informa o cenário com índice ausente.
        indices.update(coluna.get_column("lag_index").unique().to_list())  # Acrescenta os índices realmente presentes no cenário.

    if not indices:  # Confirma que existe ao menos um índice de lag.
        raise ValueError("Nenhum lag_index encontrado nos arquivos inflow_lags")  # Impede produzir uma saída sem lags.
    if min(indices) < 0:  # Rejeita índices negativos, que não representam uma ordem de lag válida.
        raise ValueError(f"lag_index negativo encontrado: {min(indices)}")  # Informa o menor índice inválido.
    deslocamento = 1 if 0 in indices else 0  # Mapeia o índice zero das saídas antigas para a coluna lag_1.
    return sorted(indices), deslocamento  # Entrega os índices em ordem numérica e a convenção de numeração.


def preparar_lags(tabela: pl.DataFrame, numero: int, indices: list[int], deslocamento: int) -> pl.DataFrame:  # Converte os lags do formato longo para o largo.
    verificar_cenario(tabela, numero, "inflow_lags")  # Confere os identificadores dentro do arquivo de lags.
    if tabela.select(pl.col("lag_index").is_null().any()).item():  # Garante que cada vazão passada tem um índice.
        raise ValueError(f"inflow_lags, cenário {numero}: lag_index nulo")  # Evita criar uma coluna sem nome confiável.
    verificar_chave_unica(tabela, CHAVE + ["lag_index"], "inflow_lags", numero)  # Proíbe dois valores para a mesma chave e lag.

    larga = tabela.pivot(on="lag_index", index=CHAVE, values="inflow_m3s", aggregate_function=None)  # Coloca cada índice de lag em sua coluna.
    for indice in indices:  # Cria as colunas na mesma ordem para todos os cenários.
        coluna_original = str(indice)  # Obtém o nome numérico criado pela pivotagem do Polars.
        coluna_final = f"lag_{indice + deslocamento}_m3s"  # Nomeia o lag conforme sua posição efetiva, começando em 1.
        if coluna_original in larga.columns:  # Verifica se o cenário contém esse índice de lag.
            larga = larga.rename({coluna_original: coluna_final})  # Renomeia a coluna sem alterar os valores de vazão.
        else:  # Preserva como ausente um índice que não existe no cenário atual.
            larga = larga.with_columns(pl.lit(None, dtype=pl.Float64).alias(coluna_final))  # Adiciona uma coluna nula, sem preencher com zero.

    verificar_chave_unica(larga, CHAVE, "lags após pivotagem", numero)  # Confirma uma única linha de lags por chave.
    return larga  # Entrega os lags em colunas prontas para a junção.


def consolidar(pasta_hydros: Path, pasta_lags: Path, arquivo_saida: Path | None = None) -> Path:  # Processa todos os cenários e grava um Parquet único.
    pasta_hydros = Path(pasta_hydros)  # Aceita um caminho Path ou texto sem depender do diretório de execução.
    pasta_lags = Path(pasta_lags)  # Converte o caminho de lags para o mesmo formato.
    if arquivo_saida is None:  # Define o local padrão quando o usuário não especifica outro local.
        arquivo_saida = Path(__file__).resolve().parent / "inflows_with_lags.parquet"  # Salva ao lado deste programa Python.
    arquivo_saida = Path(arquivo_saida)  # Garante que a saída pode ser manipulada como caminho de arquivo.
    if not arquivo_saida.parent.is_dir():  # Confere que o diretório de saída já existe.
        raise ValueError(f"Pasta de saída inexistente: {arquivo_saida.parent}")  # Evita iniciar o processamento sem destino válido.

    hydros, lags = preparar_cenarios(pasta_hydros, pasta_lags)  # Valida as pastas e associa os arquivos pelo cenário.
    indices, deslocamento = descobrir_indices_lag(lags)  # Descobre os índices presentes antes de definir o esquema final.
    colunas_lag = [f"lag_{indice + deslocamento}_m3s" for indice in indices]  # Ordena numericamente as colunas de lag.
    colunas_saida = CHAVE + ["incremental_inflow_m3s", COLUNA_SLACK] + colunas_lag  # Acrescenta o slack sem alterar nomes ou ordem dos lags.
    print(f"Índices de lag encontrados: {', '.join(map(str, indices))}", flush=True)  # Mostra os índices originais dos Parquets.
    if deslocamento:  # Informa a convenção especial dos arquivos que começam no índice zero.
        print("Convenção encontrada: lag_index=0 corresponde a lag_1_m3s.", flush=True)  # Explica a renumeração de colunas.

    temporario = arquivo_saida.with_name(arquivo_saida.name + ".tmp")  # Define um arquivo temporário ao lado da saída final.
    if temporario.exists():  # Evita misturar uma execução anterior incompleta com a execução atual.
        temporario.unlink()  # Remove somente o temporário desta rotina.
    escritor = None  # Guarda o gravador único, iniciado após o primeiro cenário válido.
    esquema = None  # Guarda o esquema de colunas e tipos do primeiro cenário.
    estagios = set()  # Acumula os identificadores de estágio observados.
    usinas = set()  # Acumula os identificadores de usina observados.
    total_linhas = 0  # Conta as linhas escritas no Parquet final.

    try:  # Garante que uma falha feche o gravador e remova a saída temporária.
        for posicao, numero in enumerate(sorted(hydros), start=1):  # Processa os cenários em ordem numérica crescente.
            if posicao == 1 or posicao % 50 == 0 or posicao == len(hydros):  # Limita as mensagens de progresso para manter o terminal legível.
                print(f"Processando cenário {numero:04d} ({posicao}/{len(hydros)})...", flush=True)  # Informa o cenário atual.

            colunas_disponiveis = pq.read_schema(hydros[numero]).names  # Verifica o esquema antes de tentar ler a nova variável.
            if COLUNA_SLACK not in colunas_disponiveis:  # Impede criar uma saída parcial ou inventar um valor para o slack.
                raise ValueError(  # Informa precisamente o cenário, o arquivo e a coluna ausente.
                    f"A coluna {COLUNA_SLACK} não foi encontrada no arquivo hydros do cenário {numero:04d}: {hydros[numero]}"
                )
            dados_hydros = pl.read_parquet(hydros[numero], columns=COLUNAS_HYDROS)  # Lê vazão e slack diretamente do mesmo arquivo hydros.
            vazoes = selecionar_vazao_atual(dados_hydros, numero)  # Obtém uma vazão incremental por estágio, nó e usina.
            dados_lags = pl.read_parquet(lags[numero], columns=COLUNAS_LAGS)  # Lê somente as colunas de lag necessárias.
            lags_largos = preparar_lags(dados_lags, numero, indices, deslocamento)  # Verifica e transforma os lags em colunas.

            sem_vazao_atual = lags_largos.select(CHAVE).join(vazoes.select(CHAVE), on=CHAVE, how="anti")  # Procura lags sem vazão atual correspondente.
            if not sem_vazao_atual.is_empty():  # Impede descartar silenciosamente um registro de lag.
                exemplo = sem_vazao_atual.row(0, named=True)  # Guarda uma chave de lag sem correspondência.
                raise ValueError(f"cenário {numero}: lags sem vazão atual para {exemplo}")  # Mostra a chave órfã.

            resultado = vazoes.join(lags_largos, on=CHAVE, how="left", validate="1:1")  # Junta somente chaves idênticas nas quatro dimensões.
            if resultado.height != vazoes.height:  # Confirma que a junção não multiplicou nem descartou linhas de vazão atual.
                raise ValueError(f"cenário {numero}: a junção alterou a quantidade de vazões atuais")  # Explica a falha de integridade.
            resultado = resultado.select(colunas_saida).sort(CHAVE)  # Organiza colunas e linhas na ordem solicitada.
            estagios.update(resultado.get_column("stage_id").unique().to_list())  # Registra os estágios encontrados no cenário.
            usinas.update(resultado.get_column("hydro_id").unique().to_list())  # Registra as usinas encontradas no cenário.
            tabela_arrow = resultado.to_arrow()  # Converte apenas o cenário atual para a tabela usada pelo gravador Parquet.

            if escritor is None:  # Cria o único gravador quando a primeira tabela estiver pronta.
                esquema = tabela_arrow.schema  # Preserva os tipos das colunas observados no primeiro cenário.
                escritor = pq.ParquetWriter(temporario, esquema, compression="zstd")  # Abre um único arquivo Parquet temporário.
            tabela_arrow = tabela_arrow.cast(esquema, safe=True)  # Exige o mesmo esquema sem converter valores de forma insegura.
            escritor.write_table(tabela_arrow)  # Acrescenta as linhas do cenário ao mesmo arquivo Parquet.
            total_linhas += resultado.height  # Atualiza a quantidade total de registros consolidados.

        escritor.close()  # Fecha o arquivo temporário após escrever todos os cenários.
        escritor = None  # Marca o gravador como fechado para não tentar fechá-lo novamente.
        os.replace(temporario, arquivo_saida)  # Publica a saída única somente depois de concluir todas as verificações.
    except Exception:  # Trata qualquer falha de leitura, validação ou escrita.
        if escritor is not None:  # Verifica se o gravador ainda precisa ser fechado.
            escritor.close()  # Libera o arquivo temporário antes de removê-lo.
        if temporario.exists():  # Confere se foi criado algum arquivo intermediário.
            temporario.unlink()  # Remove o arquivo incompleto e preserva eventual saída anterior.
        raise  # Repassa a falha com sua mensagem original para o usuário.

    print(f"Estágios encontrados: {len(estagios)}", flush=True)  # Mostra quantos estágios distintos aparecem na saída.
    print(f"Usinas encontradas: {len(usinas)}", flush=True)  # Mostra quantas usinas distintas aparecem na saída.
    print(f"Linhas consolidadas: {total_linhas}", flush=True)  # Mostra o total de combinações consolidadas.
    print(f"Dataset salvo em: {arquivo_saida}", flush=True)  # Informa o caminho do único arquivo final.
    return arquivo_saida  # Permite que outra rotina também use o resultado produzido.


def main() -> None:  # Apresenta os dois seletores de pastas ao executar o programa normalmente.
    janela = tk.Tk()  # Inicializa a janela necessária aos diálogos nativos do sistema.
    janela.withdraw()  # Esconde a janela vazia e deixa apenas os diálogos visíveis.
    try:  # Garante que a janela seja encerrada mesmo se o usuário cancelar ou ocorrer um erro.
        messagebox.showinfo("Selecionar hydros", "Selecione a pasta HYDROS da saída simulation do COBRE.", parent=janela)  # Explica a primeira seleção.
        pasta_hydros = filedialog.askdirectory(title="Selecione a pasta HYDROS", mustexist=True, parent=janela)  # Abre o seletor da pasta hydros inteira.
        if not pasta_hydros:  # Detecta se o usuário cancelou a primeira seleção.
            messagebox.showinfo("Seleção cancelada", "A seleção da pasta hydros foi cancelada.", parent=janela)  # Informa o cancelamento.
            return  # Encerra sem criar arquivos.

        messagebox.showinfo("Selecionar inflow_lags", "Selecione a pasta INFLOW_LAGS da saída simulation do COBRE.", parent=janela)  # Explica a segunda seleção.
        pasta_lags = filedialog.askdirectory(title="Selecione a pasta INFLOW_LAGS", mustexist=True, parent=janela)  # Abre o seletor da pasta inflow_lags inteira.
        if not pasta_lags:  # Detecta se o usuário cancelou a segunda seleção.
            messagebox.showinfo("Seleção cancelada", "A seleção da pasta inflow_lags foi cancelada.", parent=janela)  # Informa o cancelamento.
            return  # Encerra sem criar arquivos.

        try:  # Mostra qualquer problema estrutural encontrado durante a consolidação.
            saida = consolidar(Path(pasta_hydros), Path(pasta_lags))  # Processa as duas pastas selecionadas visualmente.
        except Exception as erro:  # Captura a explicação da falha sem ocultá-la.
            messagebox.showerror("Falha na consolidação", str(erro), parent=janela)  # Exibe o problema em uma janela legível.
            raise  # Mantém a falha visível também no terminal, quando houver.
        messagebox.showinfo("Consolidação concluída", f"Dataset salvo em:\n{saida}", parent=janela)  # Mostra o caminho do resultado.
    finally:  # Executa a limpeza tanto em sucesso quanto em cancelamento ou erro.
        janela.destroy()  # Fecha a janela de suporte aos diálogos.


if __name__ == "__main__":  # Executa a interface somente quando este arquivo Python é aberto diretamente.
    try:  # Converte uma falha não tratada em um código de saída compreensível.
        main()  # Inicia a seleção visual e a consolidação.
    except Exception as erro:  # Recebe qualquer erro já informado pela interface.
        print(f"Erro: {erro}", file=sys.stderr)  # Repete a causa no terminal, quando ele estiver aberto.
        sys.exit(1)  # Encerra com código de erro para indicar que não houve saída nova válida.
