import streamlit as st
import pandas as pd
import numpy as np
import matplotlib as mpl
from pathlib import Path
mpl.use('agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
from datetime import datetime
from matplotlib.legend_handler import HandlerTuple
from dropdown_component import simple_multiselect_dropdown
from popup import show_welcome_screen
import time 

from calculate_business_days import calculate_business_days
from fullscreen_image_component import create_fullscreen_image_viewer
try:
    from processa_neo import tratar_e_retornar_dados_previstos
    from processa_neo_smartsheet import main as processar_smartsheet_main
except ImportError:
    st.warning("Scripts de processamento não encontrados. O app usará dados de exemplo.")
    tratar_e_retornar_dados_previstos = None
    processar_smartsheet_main = None

 
# --- Configurações de Estilo ---
class StyleConfig:
    LARGURA_GANTT = 10
    ALTURA_GANTT_POR_ITEM = 1.2
    ALTURA_BARRA_GANTT = 0.35
    LARGURA_TABELA = 5
    COR_PREVISTO = '#A8C5DA'
    COR_REAL = '#174c66'
    COR_HOJE = 'red'
    COR_CONCLUIDO = '#047031'
    COR_ATRASADO = '#a83232'
    COR_META_ASSINATURA = '#8e44ad'
    FONTE_TITULO = {'size': 10, 'weight': 'bold', 'color': 'black'}
    FONTE_ETAPA = {'size': 12, 'weight': 'bold', 'color': '#2c3e50'}
    FONTE_DATAS = {'family': 'monospace', 'size': 10, 'color': '#2c3e50'}
    FONTE_PORCENTAGEM = {'size': 12, 'weight': 'bold'}
    FONTE_VARIACAO = {"size": 8, "weight": "bold"}
    CABECALHO = {'facecolor': '#2c3e50', 'edgecolor': 'none', 'pad': 4.0, 'color': 'white'}
    CELULA_PAR = {'facecolor': 'white', 'edgecolor': '#d1d5db', 'lw': 0.8}
    CELULA_IMPAR = {'facecolor': '#f1f3f5', 'edgecolor': '#d1d5db', 'lw': 0.8}
    FUNDO_TABELA = '#f8f9fa'
    ESPACO_ENTRE_EMPREENDIMENTOS = 1.5
    OFFSET_VARIACAO_TERMINO = 0.31 # Posição vertical variação

    # Cores por fase (para barras previstas e reais)
    CORES_POR_FASE = {
        "ENG.PROD": {"previsto": "#ffe1af", "real": "#be5900"},
        "INFRA": {"previsto": "#b9ddfc", "real": "#003C6C"},
        "LEG.": {"previsto": "#ebc7ef", "real": "#63006E"},
        "ORÇ.": {"previsto": "#f8cd7c", "real": "#6C3F00"},
        "PROD.": {"previsto": "#bdbdbd", "real": "#3a3a3a"},
        "SUP.": {"previsto": "#c6e7c8", "real": "#014606"}
    }

# --- MAPA DE FASE PARA ETAPAS ---
FASE_POR_ETAPA = {
    "PL-ER-E-IP": "ENG.PROD",
    "APROV-ER-(NEO)": "LEG.",
    "APROV-IP-(NEO)": "LEG.",
    "PIQ": "INFRA",
    "SOLIC-CONEXÃO": "LEG.",
    "CONEXÃO": "LEG.",
    "PROJ-EXEC": "ENG.PROD",
    "ORÇ": "ORÇ.",
    "SUP": "SUP.",
    "EXECUÇÃO-TER": "INFRA",
    "EXECUÇÃO-ER": "INFRA",
    "EXECUÇÃO-IP": "INFRA",
    "INCORPORAÇÃO": "LEG.",
    "PINT-BAR": "INFRA",
    "COMISSIONAMENTO": "LEG.",
    "LIG-IP": "LEG.",
    "CARTA": "LEG.",
    "ENTREGA": "PROD."
}

# --- Função para abreviar nomes longos ---
def abreviar_nome(nome):
    if pd.isna(nome):
        return nome

    nome = nome.replace('CONDOMINIO ', '')
    palavras = nome.split()

    if len(palavras) > 3:
        nome = ' '.join(palavras[:3])

    return nome

# --- Funções Utilitárias e Mapeamentos ---
def converter_porcentagem(valor):
    if pd.isna(valor) or valor == '': return 0.0
    if isinstance(valor, str):
        valor = ''.join(c for c in valor if c.isdigit() or c in ['.', ',']).replace(',', '.').strip()
        if not valor: return 0.0
    try:
        return float(valor) * 100 if float(valor) <= 1 else float(valor)
    except (ValueError, TypeError):
        return 0.0

def formatar_data(data):
    return data.strftime("%d/%m/%y") if pd.notna(data) else "N/D"

def calcular_dias_uteis(inicio, fim):
    """Calcula o número de dias úteis entre duas datas."""
    if pd.notna(inicio) and pd.notna(fim):
        data_inicio = np.datetime64(inicio.date())
        data_fim = np.datetime64(fim.date())
        return np.busday_count(data_inicio, data_fim) + 1
    return 0

def calcular_porcentagem_correta(grupo):
    if '% concluído' not in grupo.columns:
        return 0.0

    porcentagens = grupo['% concluído'].astype(str).apply(converter_porcentagem)
    porcentagens = porcentagens[(porcentagens >= 0) & (porcentagens <= 100)]

    if len(porcentagens) == 0:
        return 0.0

    porcentagens_validas = porcentagens[pd.notna(porcentagens)]
    if len(porcentagens_validas) == 0:
        return 0.0
    return porcentagens_validas.mean()

# --- MAPA DE ORDEM DAS ETAPAS ---
mapa_ordem = {
    "PL-ER-E-IP": 1,
    "APROV-ER-(NEO)": 2,
    "APROV-IP-(NEO)": 3,
    "PIQ": 4,
    "SOLIC-CONEXÃO": 5,
    "CONEXÃO": 6,
    "PROJ-EXEC": 7,
    "ORÇ": 8,
    "SUP": 9,
    "EXECUÇÃO-TER": 10,
    "EXECUÇÃO-ER": 11,
    "EXECUÇÃO-IP": 12,
    "INCORPORAÇÃO": 13,
    "PINT-BAR": 14,
    "COMISSIONAMENTO": 15,
    "LIG-IP": 16,
    "CARTA": 17,
    "ENTREGA": 18
}

# ORDEM CORRIGIDA DAS ETAPAS
sigla_para_nome_completo = {
    "PL-ER-E-IP":    "PL ER E IP",
    "APROV-ER-(NEO)": "APROVAÇÃO E.R. (NEO)",
    "APROV-IP-(NEO)": "APROVAÇÃO IP (NEO)",
    "PIQ":           "EXECUÇÃO PIQUETE PDE",
    "SOLIC-CONEXÃO": "SOLICITAÇÃO DE CONEXÃO",
    "CONEXÃO":       "CONEXÃO",
    "PROJ-EXEC":     "PROJETO EXECUTIVO",
    "ORÇ":          "ORÇAMENTO",
    "SUP":          "SUPRIMENTOS",
    "EXECUÇÃO-TER":  "EXECUÇÃO TER",
    "EXECUÇÃO-ER":   "EXECUÇÃO ER",
    "EXECUÇÃO-IP":   "EXECUÇÃO IP",
    "INCORPORAÇÃO":  "INCORPORAÇÃO",
    "PINT-BAR":     "PINTURA DE BARRAMENTOS",
    "COMISSIONAMENTO": "COMISSIONAMENTO",
    "LIG-IP":        "LIGAÇÃO DA IP",
    "CARTA":         "CARTA DE ENTREGA ER",
    "ENTREGA":       "NECESSIDADE DE ENTREGA"
}

nome_completo_para_sigla = {v: k for k, v in sigla_para_nome_completo.items()}
mapeamento_variacoes_real = {
    "PL ER E IP": "1. PL ER E IP",
}

def padronizar_etapa(etapa_str):
    if pd.isna(etapa_str): return 'UNKNOWN'
    etapa_limpa = str(etapa_str).strip().upper()
    if etapa_limpa in mapeamento_variacoes_real: return mapeamento_variacoes_real[etapa_limpa]
    if etapa_limpa in nome_completo_para_sigla: return nome_completo_para_sigla[etapa_limpa]
    if etapa_limpa in sigla_para_nome_completo: return etapa_limpa
    return 'UNKNOWN'

# NOVA FUNÇÃO: Filtrar etapas não concluídas
def filtrar_etapas_nao_concluidas(df):
    """
    Filtra o DataFrame para mostrar apenas etapas que não estão 100% concluídas.
    """
    if df.empty or '% concluído' not in df.columns:
        return df

    # Converter porcentagens para formato numérico
    df_copy = df.copy()
    df_copy['% concluído'] = df_copy['% concluído'].apply(converter_porcentagem)

    # Filtrar apenas etapas com menos de 100% de conclusão
    df_filtrado = df_copy[df_copy['% concluído'] < 100]

    return df_filtrado
def formatar_data(data):
    return data.strftime("%d/%m/%y") if pd.notna(data) else "N/D"

def calcular_dias_uteis(inicio, fim):
    if pd.notna(inicio) and pd.notna(fim):
        data_inicio = np.datetime64(inicio.date())
        data_fim = np.datetime64(fim.date())
        return np.busday_count(data_inicio, data_fim) + 1
    return 0

def calcular_variacao_duracao(duracao_real, duracao_prevista):
    """
    Calcula a variação entre a duração real e a duração prevista em dias.
    Retorna uma tupla (texto_variacao, cor_variacao).
    """
    if duracao_real > 0 and duracao_prevista > 0:
        diferenca_dias = duracao_real - duracao_prevista
        
        if diferenca_dias > 0:
            # Demorou mais que o previsto - vermelho
            return f"VD: +{diferenca_dias}d", "#89281d"
        elif diferenca_dias < 0:
            # Demorou menos que o previsto - verde
            return f"VD: {diferenca_dias}d", "#0b803c"
        else:
            # No prazo - cinza
            return "VD: 0d", "#666666"
    else:
        # Sem dados suficientes - cinza
        return "VD: -", "#666666"

def calcular_variacao_termino(termino_real, termino_previsto):
    """
    Calcula a variação entre o término real e o término previsto.
    Retorna uma tupla (texto_variacao, cor_variacao)
    """
    if pd.notna(termino_real) and pd.notna(termino_previsto):
        diferenca_dias = calculate_business_days(termino_previsto, termino_real)
        if pd.isna(diferenca_dias): diferenca_dias = 0 # Lidar com casos em que calculate_business_days retorna NA
        
        if diferenca_dias > 0:
            # Atrasado - vermelho
            return f"VT: +{diferenca_dias}d", "#89281d"
        elif diferenca_dias < 0:
            # Adiantado - verde
            return f"VT: {diferenca_dias}d", "#0b803c"
        else:
            # No prazo - cinza
            return "VT: 0d", "#666666"
    else:
        # Sem dados suficientes - cinza
        return "VT: -", "#666666"


def obter_data_meta_assinatura(df_original, empreendimento):
    df_meta = df_original[(df_original['Empreendimento'] == empreendimento) & (df_original['Etapa'] == 'M')]
    
    if df_meta.empty:
        return pd.Timestamp.max
    
    if pd.notna(df_meta['Termino_Prevista'].iloc[0]):
        return df_meta['Termino_Prevista'].iloc[0]
    elif pd.notna(df_meta['Inicio_Prevista'].iloc[0]):
        return df_meta['Inicio_Prevista'].iloc[0]
    elif pd.notna(df_meta['Termino_Real'].iloc[0]):
        return df_meta['Termino_Real'].iloc[0]
    elif pd.notna(df_meta['Inicio_Real'].iloc[0]):
        return df_meta['Inicio_Real'].iloc[0]
    else:
        return pd.Timestamp.max
    
def criar_ordenacao_empreendimentos(df_original):
    empreendimentos_meta = {}
    
    for empreendimento in df_original['Empreendimento'].unique():
        data_meta = obter_data_meta_assinatura(df_original, empreendimento)
        empreendimentos_meta[empreendimento] = data_meta
    
    empreendimentos_ordenados = sorted(
        empreendimentos_meta.keys(),
        key=lambda x: empreendimentos_meta[x]
    )
    
    return empreendimentos_ordenados

def aplicar_ordenacao_final(df, empreendimentos_ordenados):
    if df.empty:
        return df
    
    ordem_empreendimentos = {emp: idx for idx, emp in enumerate(empreendimentos_ordenados)}
    df['ordem_empreendimento'] = df['Empreendimento'].map(ordem_empreendimentos)
    
    ordem_etapas = {etapa: idx for idx, etapa in enumerate(sigla_para_nome_completo.keys())}
    df['ordem_etapa'] = df['Etapa'].map(ordem_etapas).fillna(len(ordem_etapas))
    
    df_ordenado = df.sort_values(['ordem_empreendimento', 'ordem_etapa']).drop(
        ['ordem_empreendimento', 'ordem_etapa'], axis=1
    )
    
    return df_ordenado.reset_index(drop=True)

# --- Funções de Geração do Gráfico ---

def gerar_gantt(df, tipo_visualizacao="Ambos", filtrar_nao_concluidas=False):
    if df.empty:
        st.warning("Sem dados disponíveis para exibir o Gantt.")
        return

    plt.rcParams['figure.dpi'] = 150
    plt.rcParams['savefig.dpi'] = 150

    df_original_completo = df.copy()

    if 'Empreendimento' in df.columns:
        df['Empreendimento'] = df['Empreendimento'].apply(abreviar_nome)
        df_original_completo['Empreendimento'] = df_original_completo['Empreendimento'].apply(abreviar_nome)

    if '% concluído' in df.columns:
        df_porcentagem = df.groupby(['Empreendimento', 'Etapa']).apply(calcular_porcentagem_correta).reset_index(name='%_corrigido')
        df = pd.merge(df, df_porcentagem, on=['Empreendimento', 'Etapa'], how='left')
        df['% concluído'] = df['%_corrigido'].fillna(0)
        df.drop('%_corrigido', axis=1, inplace=True)
    else:
        df['% concluído'] = 0.0

    for col in ['Inicio_Prevista', 'Termino_Prevista', 'Inicio_Real', 'Termino_Real']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
            df_original_completo[col] = pd.to_datetime(df_original_completo[col], errors='coerce')

    empreendimentos_ordenados = criar_ordenacao_empreendimentos(df_original_completo)

    if filtrar_nao_concluidas:
        df = filtrar_etapas_nao_concluidas(df)
    
    df = aplicar_ordenacao_final(df, empreendimentos_ordenados)

    if df.empty:
        st.warning("Sem dados disponíveis para exibir o Gantt após a filtragem.")
        return

    num_empreendimentos = df['Empreendimento'].nunique()
    num_etapas = df['Etapa'].nunique()

    # REGRA ESPECÍFICA: Quando há múltiplos empreendimentos e apenas uma etapa
    if num_empreendimentos > 1 and num_etapas == 1:
        # Para este caso especial, geramos apenas UM gráfico comparativo
        gerar_gantt_comparativo(df, tipo_visualizacao, df_original_completo)
    elif num_empreendimentos > 1 and num_etapas > 1:
        # Caso tradicional: múltiplos empreendimentos com múltiplas etapas
        for empreendimento in empreendimentos_ordenados:
            if empreendimento in df['Empreendimento'].unique():
                # REMOVIDO: st.subheader(f"Empreendimento: {empreendimento.replace('CONDOMINIO ', '')}")
                df_filtrado = df[df['Empreendimento'] == empreendimento]
                df_original_filtrado = df_original_completo[df_original_completo['Empreendimento'] == empreendimento]
                
                gerar_gantt_individual(df_filtrado, tipo_visualizacao, df_original=df_original_filtrado)
                # REMOVIDO: st.markdown("---")
    else:
        # Caso único empreendimento (com uma ou múltiplas etapas)
        gerar_gantt_individual(df, tipo_visualizacao, df_original=df_original_completo)

def gerar_gantt_comparativo(df, tipo_visualizacao="Ambos", df_original=None):
    """
    Gera um gráfico Gantt comparativo para múltiplos empreendimentos com apenas uma etapa.
    Ordena os empreendimentos pela data de início e exibe em um único gráfico.
    """
    if df.empty:
        return

    if df_original is None:
        df_original = df.copy()
    
    hoje = pd.Timestamp.now()
    
    # Ordenação específica para o caso comparativo
    sort_col = 'Inicio_Real' if tipo_visualizacao == "Real" else 'Inicio_Prevista'
    df = df.sort_values(by=sort_col, ascending=True, na_position='last').reset_index(drop=True)
    
    # Configuração do mapeamento de posições
    rotulo_para_posicao = {}
    posicao = 0
    
    # Para o caso comparativo, uma linha por empreendimento
    for empreendimento in df['Empreendimento'].unique():
        rotulo_para_posicao[empreendimento] = posicao
        posicao += 1
    
    df['Posicao'] = df['Empreendimento'].map(rotulo_para_posicao)
    df.dropna(subset=['Posicao'], inplace=True)
    
    if df.empty:
        return

    # Configuração da figura
    num_linhas = len(rotulo_para_posicao)
    altura_total = max(10, num_linhas * StyleConfig.ALTURA_GANTT_POR_ITEM)
    figura = plt.figure(figsize=(StyleConfig.LARGURA_TABELA + StyleConfig.LARGURA_GANTT, altura_total))
    grade = gridspec.GridSpec(1, 2, width_ratios=[StyleConfig.LARGURA_TABELA, StyleConfig.LARGURA_GANTT], wspace=0.01)

    eixo_tabela = figura.add_subplot(grade[0], facecolor=StyleConfig.FUNDO_TABELA)
    eixo_gantt = figura.add_subplot(grade[1], sharey=eixo_tabela)
    eixo_tabela.axis('off')

    # Consolidação dos dados
    dados_consolidados = df.groupby('Posicao').agg({
        'Empreendimento': 'first', 'Etapa': 'first',
        'Inicio_Prevista': 'min', 'Termino_Prevista': 'max',
        'Inicio_Real': 'min', 'Termino_Real': 'max',
        '% concluído': 'max'
    }).reset_index()


    # Desenho da tabela
    for _, linha in dados_consolidados.iterrows():
        y_pos = linha['Posicao']
        
        estilo_celula = StyleConfig.CELULA_PAR if int(y_pos) % 2 == 0 else StyleConfig.CELULA_IMPAR
        eixo_tabela.add_patch(Rectangle((0.01, y_pos - 0.5), 0.98, 1.0,
                             facecolor=estilo_celula["facecolor"], edgecolor=estilo_celula["edgecolor"], lw=estilo_celula["lw"]))

        # Texto principal: nome do empreendimento
        eixo_tabela.text(0.04, y_pos - 0.2, linha['Empreendimento'], va="center", ha="left", **StyleConfig.FONTE_ETAPA)
        
        # Informações de datas e dias úteis
        dias_uteis_prev = calcular_dias_uteis(linha['Inicio_Prevista'], linha['Termino_Prevista'])
        dias_uteis_real = calcular_dias_uteis(linha['Inicio_Real'], linha['Termino_Real'])
        
        texto_prev = f"Prev: {formatar_data(linha['Inicio_Prevista'])} → {formatar_data(linha['Termino_Prevista'])}-({dias_uteis_prev}d)"
        texto_real = f"Real: {formatar_data(linha['Inicio_Real'])} → {formatar_data(linha['Termino_Real'])}-({dias_uteis_real}d)"
        
        eixo_tabela.text(0.04, y_pos + 0.05, f"{texto_prev:<32}", va="center", ha="left", **StyleConfig.FONTE_DATAS)
        eixo_tabela.text(0.04, y_pos + 0.28, f"{texto_real:<32}", va="center", ha="left", **StyleConfig.FONTE_DATAS)

        # Indicador de porcentagem com cores
        percentual = linha['% concluído']
        termino_real = linha['Termino_Real']
        termino_previsto = linha['Termino_Prevista']
        
    # --- BLOCO DE STATUS COM TRÊS CAIXAS ALINHADAS ---

        # 1. Lógica de cores CORRIGIDA
        cor_status = {'face': '#e9ecef', 'text': '#495057', 'edge': '#ced4da'} # Padrão: Cinza (Não Iniciado)
        hoje = pd.Timestamp.now().normalize()

        if percentual == 100:
            if pd.notna(termino_real) and pd.notna(termino_previsto):
                if termino_real < termino_previsto:
                    cor_status = {'face': '#d4edda', 'text': "#1F8944", 'edge': '#c3e6cb'} # Verde: Concluído no Prazo/Adiantado
                elif termino_real > termino_previsto:
                    cor_status = {'face': '#f8d7da', 'text': '#721c24', 'edge': '#f5c6cb'} # Vermelho: Concluído com Atraso

        # CORREÇÃO PRINCIPAL ESTÁ AQUI
        elif percentual < 100:
            if pd.notna(termino_real) and (termino_real < hoje):
                cor_status = {'face': '#fff3cd', 'text': '#856404', 'edge': "#f9e29c"} # Amarelo: Em Andamento, Atrasado
            
    
        # 2. Definir a geometria para as três caixas empilhadas (com mais espaçamento)
        largura_caixa = 0.2
        altura_caixa = 0.25  # <-- ALTURA REDUZIDA AQUI (era 0.3)
        gap_vertical = 0.02  # Espaço entre as caixas da mesma etapa

        # Lógica de posicionamento aprimorada para garantir a centralização vertical
        altura_total_bloco = (3 * altura_caixa) + (2 * gap_vertical)
        y_inicial_topo = y_pos - (altura_total_bloco / 2)

        # Posições Y finais para cada caixa
        y_caixa_topo = y_inicial_topo
        y_caixa_meio = y_inicial_topo + altura_caixa + gap_vertical
        y_caixa_base = y_inicial_topo + (2 * altura_caixa) + (2 * gap_vertical)

        # 3. Desenhar a Caixa 1 (Topo): Percentual
        percentual_texto = f"{int(percentual)}%"
        eixo_tabela.add_patch(
            Rectangle((0.78, y_caixa_topo), largura_caixa, altura_caixa, 
                      facecolor=cor_status['face'], edgecolor=cor_status['edge'], lw=1)
        )
        eixo_tabela.text(0.88, y_caixa_topo + altura_caixa / 2, percentual_texto, 
                         va="center", ha="center", color=cor_status['text'], **StyleConfig.FONTE_PORCENTAGEM)

        # 4. Desenhar a Caixa 2 (Meio): Variação de Término (V:)
        variacao_term_texto, _ = calcular_variacao_termino(termino_real, termino_previsto)
        eixo_tabela.add_patch(
            Rectangle((0.78, y_caixa_meio), largura_caixa, altura_caixa, 
                      facecolor=cor_status['face'], edgecolor=cor_status['edge'], lw=1)
        )
        eixo_tabela.text(0.88, y_caixa_meio + altura_caixa / 2, variacao_term_texto, 
                         va="center", ha="center", color=cor_status['text'], **StyleConfig.FONTE_VARIACAO)
        
        # 5. Desenhar a Caixa 3 (Base): Variação de Duração (D:)
        variacao_dur_texto, _ = calcular_variacao_duracao(dias_uteis_real, dias_uteis_prev)
        eixo_tabela.add_patch(
            Rectangle((0.78, y_caixa_base), largura_caixa, altura_caixa, 
                      facecolor=cor_status['face'], edgecolor=cor_status['edge'], lw=1)
        )
        eixo_tabela.text(0.88, y_caixa_base + altura_caixa / 2, variacao_dur_texto, 
                         va="center", ha="center", color=cor_status['text'], **StyleConfig.FONTE_VARIACAO)

        # --- FIM DO BLOCO DE STATUS ---

    # Desenho das barras do Gantt
    datas_relevantes = []
    for _, linha in dados_consolidados.iterrows():
        y_pos = linha['Posicao']
        ALTURA_BARRA = StyleConfig.ALTURA_BARRA_GANTT
        ESPACAMENTO = 0 if tipo_visualizacao != "Ambos" else StyleConfig.ALTURA_BARRA_GANTT * 0.5

        # Barra prevista
        if tipo_visualizacao in ["Ambos", "Previsto"] and pd.notna(linha['Inicio_Prevista']) and pd.notna(linha['Termino_Prevista']):
            duracao = (linha['Termino_Prevista'] - linha['Inicio_Prevista']).days + 1
            eixo_gantt.barh(y=y_pos - ESPACAMENTO, width=duracao, left=linha['Inicio_Prevista'],
                            height=ALTURA_BARRA, color=StyleConfig.COR_PREVISTO, alpha=0.9,
                            antialiased=False)
            datas_relevantes.extend([linha['Inicio_Prevista'], linha['Termino_Prevista']])

        # Barra real
        if tipo_visualizacao in ["Ambos", "Real"] and pd.notna(linha['Inicio_Real']):
            termino_real = linha['Termino_Real'] if pd.notna(linha['Termino_Real']) else hoje
            duracao = (termino_real - linha['Inicio_Real']).days + 1
            eixo_gantt.barh(y=y_pos + ESPACAMENTO, width=duracao, left=linha['Inicio_Real'],
                            height=ALTURA_BARRA, color=StyleConfig.COR_REAL, alpha=0.9,
                            antialiased=False)
            datas_relevantes.extend([linha['Inicio_Real'], termino_real])

    if datas_relevantes:
        datas_validas = [pd.Timestamp(d) for d in datas_relevantes if pd.notna(d)]
        if datas_validas:
            # --- MODIFICAÇÃO: AJUSTE DO LIMITE DO EIXO X PARA INCLUIR "HOJE" ---
            data_min_do_grafico = min(datas_validas)
            data_max_do_grafico = max(datas_validas)
            
            data_min_final = min(hoje, data_min_do_grafico)
            limite_superior = max(hoje, data_max_do_grafico) + pd.Timedelta(days=90)
            
            eixo_gantt.set_xlim(left=data_min_final - pd.Timedelta(days=5), right=limite_superior)
            # --- FIM DA MODIFICAÇÃO ---

    max_pos = max(rotulo_para_posicao.values())
    eixo_gantt.set_ylim(max_pos + 1, -1)
    eixo_gantt.set_yticks([])
    
    # Linhas horizontais de separação
    for pos in rotulo_para_posicao.values():
        eixo_gantt.axhline(y=pos + 0.5, color='#dcdcdc', linestyle='-', alpha=0.7, linewidth=0.8)
    
    # --- MODIFICAÇÃO: LÓGICA CONDICIONAL PARA A LINHA E TEXTO "HOJE" ---
    limite_esquerdo, limite_direito = eixo_gantt.get_xlim()
    margem_fixa = pd.Timedelta(days=30)
    data_fim_projeto = max([d for d in [df['Termino_Real'].max(), df['Termino_Prevista'].max()] if pd.notna(d)], default=pd.Timestamp.min)
    
    if hoje <= data_fim_projeto + margem_fixa:
        eixo_gantt.axvline(hoje, color=StyleConfig.COR_HOJE, linestyle='--', linewidth=1.5)
        eixo_gantt.text(hoje, eixo_gantt.get_ylim()[1], 'Hoje', color=StyleConfig.COR_HOJE, fontsize=10, ha='center', va='bottom')
    else:
        eixo_gantt.axvline(limite_direito, color=StyleConfig.COR_HOJE, linestyle='--', linewidth=1.5)
        eixo_gantt.text(limite_direito, eixo_gantt.get_ylim()[1], 'Hoje >', color=StyleConfig.COR_HOJE, fontsize=10, ha='right', va='bottom')
    # --- FIM DA MODIFICAÇÃO ---

    # Grade e formatação
    eixo_gantt.grid(axis='x', linestyle='--', alpha=0.6)
    eixo_gantt.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    eixo_gantt.xaxis.set_major_formatter(mdates.DateFormatter('%m/%y'))
    plt.setp(eixo_gantt.get_xticklabels(), rotation=90, ha='center')

    # Cria os handles em pares para cada fase
    handles_legenda = []
    labels_legenda = []

    for fase in StyleConfig.CORES_POR_FASE:
        if fase in StyleConfig.CORES_POR_FASE:
            prev_patch = Patch(color=StyleConfig.CORES_POR_FASE[fase]["previsto"])
            real_patch = Patch(color=StyleConfig.CORES_POR_FASE[fase]["real"])
            handles_legenda.append((prev_patch, real_patch))
            labels_legenda.append(fase)

    # Adiciona a legenda com pares de cores (mantendo posição original)
    eixo_gantt.legend(
        handles=handles_legenda,
        labels=labels_legenda,
        handler_map={tuple: HandlerTuple(ndivide=None)},
        loc='upper center',
        bbox_to_anchor=(1.1, 1),  # Posição original ao lado do gráfico
        frameon=False,
        borderaxespad=0.1,
        fontsize=8,
        title=" (Previsto | Real)"
    )

    plt.tight_layout(rect=[0, 0.03, 1, 1])

    # CORREÇÃO: Definir unique_key apropriadamente
    if empreendimento is not None:
        unique_key = empreendimento
    else:
        # Se não há empreendimento específico, criar uma chave única
        unique_key = f"gantt_{int(time.time() * 1000)}"

    create_fullscreen_image_viewer(
        figure=figura, 
        empreendimento=unique_key
    )

def gerar_gantt_individual(df, tipo_visualizacao="Ambos", df_original=None):
    if df.empty:
        return

    if df_original is None:
        df_original = df.copy()
    
    hoje = pd.Timestamp.now()
    
    num_empreendimentos = df['Empreendimento'].nunique()
    num_etapas = df['Etapa'].nunique()
    
    # Lógica de posicionamento
    rotulo_para_posicao = {}
    posicao = 0
    
    if num_empreendimentos > 1 and num_etapas == 1:
        # Para o caso comparativo, a ordem das linhas é definida pela ordenação do DataFrame
        for rotulo in df['Empreendimento'].unique():
            rotulo_para_posicao[rotulo] = posicao
            posicao += 1
        df['Posicao'] = df['Empreendimento'].map(rotulo_para_posicao)
    else:
        # Para o caso tradicional, a ordem é baseada em como os dados chegam
        empreendimentos_unicos = df['Empreendimento'].unique()
        for empreendimento in empreendimentos_unicos:
            etapas_do_empreendimento = df[df['Empreendimento'] == empreendimento]['Etapa'].unique()
            for etapa in etapas_do_empreendimento:
                rotulo = f'{empreendimento}||{etapa}'
                rotulo_para_posicao[rotulo] = posicao
                posicao += 1
            if len(empreendimentos_unicos) > 1:
                    posicao += StyleConfig.ESPACO_ENTRE_EMPREENDIMENTOS / 2
        df['Posicao'] = (df['Empreendimento'] + '||' + df['Etapa']).map(rotulo_para_posicao)

    df.dropna(subset=['Posicao'], inplace=True)
    if df.empty:
        return

    # --- Configuração da Figura ---
    num_linhas = len(rotulo_para_posicao)
    altura_total = max(10, num_linhas * StyleConfig.ALTURA_GANTT_POR_ITEM)
    figura = plt.figure(figsize=(StyleConfig.LARGURA_TABELA + StyleConfig.LARGURA_GANTT, altura_total))
    grade = gridspec.GridSpec(1, 2, width_ratios=[StyleConfig.LARGURA_TABELA, StyleConfig.LARGURA_GANTT], wspace=0.01)

    eixo_tabela = figura.add_subplot(grade[0], facecolor=StyleConfig.FUNDO_TABELA)
    eixo_gantt = figura.add_subplot(grade[1], sharey=eixo_tabela)
    eixo_tabela.axis('off')

    # --- Consolidação e Desenho (sem alterações) ---
    dados_consolidados = df.groupby('Posicao').agg({
        'Empreendimento': 'first', 'Etapa': 'first',
        'Inicio_Prevista': 'min', 'Termino_Prevista': 'max',
        'Inicio_Real': 'min', 'Termino_Real': 'max',
        '% concluído': 'max'
    }).reset_index()

    empreendimento_atual = None
    for _, linha in dados_consolidados.iterrows():
        y_pos = linha['Posicao']
        
        if not (num_empreendimentos > 1 and num_etapas == 1) and linha['Empreendimento'] != empreendimento_atual:
            empreendimento_atual = linha['Empreendimento']
            nome_formatado = empreendimento_atual.replace('CONDOMINIO ', '')
            y_cabecalho = y_pos - (StyleConfig.ALTURA_GANTT_POR_ITEM / 2) - 0.2
            eixo_tabela.text(0.5, y_cabecalho, nome_formatado,
                             va="center", ha="center", bbox=StyleConfig.CABECALHO, **StyleConfig.FONTE_TITULO)

        estilo_celula = StyleConfig.CELULA_PAR if int(y_pos) % 2 == 0 else StyleConfig.CELULA_IMPAR
        eixo_tabela.add_patch(Rectangle((0.01, y_pos - 0.5), 0.98, 1.0,
                             facecolor=estilo_celula["facecolor"], edgecolor=estilo_celula["edgecolor"], lw=estilo_celula["lw"]))

        texto_principal = linha['Empreendimento'] if (num_empreendimentos > 1 and num_etapas == 1) else sigla_para_nome_completo.get(linha['Etapa'], linha['Etapa'])
        eixo_tabela.text(0.04, y_pos - 0.2, texto_principal, va="center", ha="left", **StyleConfig.FONTE_ETAPA)
        
        dias_uteis_prev = calcular_dias_uteis(linha['Inicio_Prevista'], linha['Termino_Prevista'])
        dias_uteis_real = calcular_dias_uteis(linha['Inicio_Real'], linha['Termino_Real'])
        
        texto_prev = f"Prev: {formatar_data(linha['Inicio_Prevista'])} → {formatar_data(linha['Termino_Prevista'])}-({dias_uteis_prev}d)"
        texto_real = f"Real: {formatar_data(linha['Inicio_Real'])} → {formatar_data(linha['Termino_Real'])}-({dias_uteis_real}d)"
        
        eixo_tabela.text(0.04, y_pos + 0.05, f"{texto_prev:<32}", va="center", ha="left", **StyleConfig.FONTE_DATAS)
        eixo_tabela.text(0.04, y_pos + 0.28, f"{texto_real:<32}", va="center", ha="left", **StyleConfig.FONTE_DATAS)

        percentual = linha['% concluído']
        termino_real = linha['Termino_Real']
        termino_previsto = linha['Termino_Prevista']

    # --- BLOCO DE STATUS COM TRÊS CAIXAS ALINHADAS ---

        # 1. Lógica de cores CORRIGIDA
        cor_status = {'face': '#e9ecef', 'text': '#495057', 'edge': '#ced4da'} # Padrão: Cinza (Não Iniciado)
        hoje = pd.Timestamp.now().normalize()

        if percentual == 100:
            if pd.notna(termino_real) and pd.notna(termino_previsto):
                if termino_real < termino_previsto:
                    cor_status = {'face': '#d4edda', 'text': "#1F8944", 'edge': '#c3e6cb'} # Verde: Concluído no Prazo/Adiantado
                elif termino_real > termino_previsto:
                    cor_status = {'face': '#f8d7da', 'text': '#721c24', 'edge': '#f5c6cb'} # Vermelho: Concluído com Atraso

        elif percentual < 100:
            if pd.notna(termino_real) and (termino_real < hoje):
                cor_status = {'face': '#fff3cd', 'text': '#856404', 'edge': "#f9e29c"} # Amarelo: Em Andamento, Atrasado
            
    
        # 2. Definir a geometria para as três caixas empilhadas (com mais espaçamento)
        largura_caixa = 0.2
        altura_caixa = 0.25  # <-- ALTURA REDUZIDA AQUI (era 0.3)
        gap_vertical = 0.02  # Espaço entre as caixas da mesma etapa

        # Lógica de posicionamento aprimorada para garantir a centralização vertical
        altura_total_bloco = (3 * altura_caixa) + (2 * gap_vertical)
        y_inicial_topo = y_pos - (altura_total_bloco / 2)

        # Posições Y finais para cada caixa
        y_caixa_topo = y_inicial_topo
        y_caixa_meio = y_inicial_topo + altura_caixa + gap_vertical
        y_caixa_base = y_inicial_topo + (2 * altura_caixa) + (2 * gap_vertical)

        # 3. Desenhar a Caixa 1 (Topo): Percentual
        percentual_texto = f"{int(percentual)}%"
        eixo_tabela.add_patch(
            Rectangle((0.78, y_caixa_topo), largura_caixa, altura_caixa, 
                      facecolor=cor_status['face'], edgecolor=cor_status['edge'], lw=1)
        )
        eixo_tabela.text(0.88, y_caixa_topo + altura_caixa / 2, percentual_texto, 
                         va="center", ha="center", color=cor_status['text'], **StyleConfig.FONTE_PORCENTAGEM)

        # 4. Desenhar a Caixa 2 (Meio): Variação de Término (V:)
        variacao_term_texto, _ = calcular_variacao_termino(termino_real, termino_previsto)
        eixo_tabela.add_patch(
            Rectangle((0.78, y_caixa_meio), largura_caixa, altura_caixa, 
                      facecolor=cor_status['face'], edgecolor=cor_status['edge'], lw=1)
        )
        eixo_tabela.text(0.88, y_caixa_meio + altura_caixa / 2, variacao_term_texto, 
                         va="center", ha="center", color=cor_status['text'], **StyleConfig.FONTE_VARIACAO)
        
        # 5. Desenhar a Caixa 3 (Base): Variação de Duração (D:)
        variacao_dur_texto, _ = calcular_variacao_duracao(dias_uteis_real, dias_uteis_prev)
        eixo_tabela.add_patch(
            Rectangle((0.78, y_caixa_base), largura_caixa, altura_caixa, 
                      facecolor=cor_status['face'], edgecolor=cor_status['edge'], lw=1)
        )
        eixo_tabela.text(0.88, y_caixa_base + altura_caixa / 2, variacao_dur_texto, 
                         va="center", ha="center", color=cor_status['text'], **StyleConfig.FONTE_VARIACAO)

        # --- FIM DO BLOCO DE STATUS ---


    datas_relevantes = []
    for _, linha in dados_consolidados.iterrows():
        y_pos = linha['Posicao']
        ALTURA_BARRA = StyleConfig.ALTURA_BARRA_GANTT
        ESPACAMENTO = 0 if tipo_visualizacao != "Ambos" else StyleConfig.ALTURA_BARRA_GANTT * 0.5

        if tipo_visualizacao in ["Ambos", "Previsto"] and pd.notna(linha['Inicio_Prevista']) and pd.notna(linha['Termino_Prevista']):
            duracao = (linha['Termino_Prevista'] - linha['Inicio_Prevista']).days + 1
            eixo_gantt.barh(y=y_pos - ESPACAMENTO, width=duracao, left=linha['Inicio_Prevista'],
                            height=ALTURA_BARRA, color=StyleConfig.COR_PREVISTO, alpha=0.9,
                            antialiased=False)
            datas_relevantes.extend([linha['Inicio_Prevista'], linha['Termino_Prevista']])

        if tipo_visualizacao in ["Ambos", "Real"] and pd.notna(linha['Inicio_Real']):
            termino_real = linha['Termino_Real'] if pd.notna(linha['Termino_Real']) else hoje
            duracao = (termino_real - linha['Inicio_Real']).days + 1
            eixo_gantt.barh(y=y_pos + ESPACAMENTO, width=duracao, left=linha['Inicio_Real'],
                            height=ALTURA_BARRA, color=StyleConfig.COR_REAL, alpha=0.9,
                            antialiased=False)
            datas_relevantes.extend([linha['Inicio_Real'], termino_real])
            
# --- Desenho das Barras ---
    datas_relevantes = []
    for _, linha in dados_consolidados.iterrows():
        y_pos = linha['Posicao']
        ALTURA_BARRA = StyleConfig.ALTURA_BARRA_GANTT
        ESPACAMENTO = 0 if tipo_visualizacao != "Ambos" else StyleConfig.ALTURA_BARRA_GANTT * 0.5

        # Determina a fase da etapa atual
        fase = FASE_POR_ETAPA.get(linha['Etapa'], "OUTROS")
        cor_previsto = StyleConfig.CORES_POR_FASE.get(fase, {}).get("previsto", "#A8C5DA")
        cor_real = StyleConfig.CORES_POR_FASE.get(fase, {}).get("real", "#174c66")

        if tipo_visualizacao in ["Ambos", "Previsto"] and pd.notna(linha['Inicio_Prevista']) and pd.notna(linha['Termino_Prevista']):
            duracao = (linha['Termino_Prevista'] - linha['Inicio_Prevista']).days + 3
            eixo_gantt.barh(y=y_pos - ESPACAMENTO, width=duracao, left=linha['Inicio_Prevista'],
                           height=ALTURA_BARRA, color=cor_previsto, alpha=0.9,
                           antialiased=False)
            datas_relevantes.extend([linha['Inicio_Prevista'], linha['Termino_Prevista']])

        if tipo_visualizacao in ["Ambos", "Real"] and pd.notna(linha['Inicio_Real']):
            termino_real = linha['Termino_Real'] if pd.notna(linha['Termino_Real']) else hoje
            duracao = (termino_real - linha['Inicio_Real']).days + 3
            eixo_gantt.barh(y=y_pos + ESPACAMENTO, width=duracao, left=linha['Inicio_Real'],
                           height=ALTURA_BARRA, color=cor_real, alpha=0.9,
                           antialiased=False)
            datas_relevantes.extend([linha['Inicio_Real'], termino_real])

    if datas_relevantes:
        datas_validas = [pd.Timestamp(d) for d in datas_relevantes if pd.notna(d)]
        if datas_validas:
            # --- MODIFICAÇÃO: AJUSTE DO LIMITE DO EIXO X PARA INCLUIR "HOJE" ---
            data_min_do_grafico = min(datas_validas)
            data_max_do_grafico = max(datas_validas)
            
            data_min_final = min(hoje, data_min_do_grafico)
            limite_superior = max(hoje, data_max_do_grafico) + pd.Timedelta(days=90)
            
            eixo_gantt.set_xlim(left=data_min_final - pd.Timedelta(days=5), right=limite_superior)
            # --- FIM DA MODIFICAÇÃO ---
            
    if not rotulo_para_posicao:
           # CORREÇÃO SIMPLIFICADA
        unique_key = f"empty_{int(time.time() * 1000)}"
        create_fullscreen_image_viewer(
            figura, 
            show_regular=True, 
            button_text=f"🔍 Visualizar {empreendimento.replace('CONDOMINIO ', '')} em Tela Cheia",
            empreendimento=unique_key
        )
        plt.close(figura)
        return

    max_pos = max(rotulo_para_posicao.values())
    eixo_gantt.set_ylim(max_pos + 1, -1)
    eixo_gantt.set_yticks([])
    
    for pos in rotulo_para_posicao.values():
        eixo_gantt.axhline(y=pos + 0.5, color='#dcdcdc', linestyle='-', alpha=0.7, linewidth=0.8)

    # --- MODIFICAÇÃO: LÓGICA CONDICIONAL PARA A LINHA E TEXTO "HOJE" ---
    limite_esquerdo, limite_direito = eixo_gantt.get_xlim()
    margem_fixa = pd.Timedelta(days=30)
    data_fim_projeto = max([d for d in [df['Termino_Real'].max(), df['Termino_Prevista'].max()] if pd.notna(d)], default=pd.Timestamp.min)
    
    if hoje <= data_fim_projeto + margem_fixa:
        eixo_gantt.axvline(hoje, color=StyleConfig.COR_HOJE, linestyle='--', linewidth=1.5)
        eixo_gantt.text(hoje, eixo_gantt.get_ylim()[0], 'Hoje', color=StyleConfig.COR_HOJE, fontsize=10, ha='center', va='bottom')
    else:
        eixo_gantt.axvline(limite_direito, color=StyleConfig.COR_HOJE, linestyle='--', linewidth=1.5)
        eixo_gantt.text(limite_direito, eixo_gantt.get_ylim()[1], 'Hoje >', color=StyleConfig.COR_HOJE, fontsize=10, ha='right', va='bottom')
    # --- FIM DA MODIFICAÇÃO ---

    if num_empreendimentos == 1 and num_etapas > 1:
        empreendimento = df["Empreendimento"].unique()[0]
        df_assinatura = df[(df["Empreendimento"] == empreendimento) & (df["Etapa"] == "ENTREGA")]
        if not df_assinatura.empty:
            data_meta, tipo_meta = (None, "")
            if pd.notna(df_assinatura["Inicio_Prevista"].iloc[0]):
                data_meta, tipo_meta = df_assinatura["Termino_Prevista"].iloc[0], "Prevista"
            elif pd.notna(df_assinatura["Inicio_Real"].iloc[0]):
                data_meta, tipo_meta = df_assinatura["Inicio_Real"].iloc[0], "Real" 

            if data_meta is not None:
                eixo_gantt.axvline(data_meta, color=StyleConfig.COR_META_ASSINATURA, linestyle="--", linewidth=1.7, alpha=0.7)
                y_texto = eixo_gantt.get_ylim()[1] + 0.2
                eixo_gantt.text(data_meta, y_texto,
                               f"Meta Assinatura\n{tipo_meta}: {data_meta.strftime('%d/%m/%y')}",
                               color=StyleConfig.COR_META_ASSINATURA, fontsize=10, ha="center", va="top",
                               bbox=dict(facecolor="white", alpha=0.8, edgecolor=StyleConfig.COR_META_ASSINATURA, boxstyle="round,pad=0.5"))

    eixo_gantt.grid(axis='x', linestyle='--', alpha=0.6)
    eixo_gantt.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    eixo_gantt.xaxis.set_major_formatter(mdates.DateFormatter('%m/%y'))
    plt.setp(eixo_gantt.get_xticklabels(), rotation=90, ha='center')

    # Cria os handles em pares para cada fase
    handles_legenda = []
    labels_legenda = []

    for fase in StyleConfig.CORES_POR_FASE:
        if fase in StyleConfig.CORES_POR_FASE:
            prev_patch = Patch(color=StyleConfig.CORES_POR_FASE[fase]["previsto"])
            real_patch = Patch(color=StyleConfig.CORES_POR_FASE[fase]["real"])
            handles_legenda.append((prev_patch, real_patch))
            labels_legenda.append(fase)
            
    # Adiciona a legenda com pares de cores (mantendo posição original)
    eixo_gantt.legend(
        handles=handles_legenda,
        labels=labels_legenda,
        handler_map={tuple: HandlerTuple(ndivide=None)},
        loc='upper center',
        bbox_to_anchor=(1.1, 1),  # Posição original ao lado do gráfico
        frameon=False,
        borderaxespad=0.1,
        fontsize=8,
        title=" (Previsto | Real)"
    )

    plt.tight_layout(rect=[0, 0.03, 1, 1])
# CORREÇÃO: Definir unique_key apropriadamente antes de usar
    if empreendimento is not None:
        unique_key = empreendimento
    else:
        # Se não há empreendimento específico, criar uma chave única
        if not df.empty and 'Empreendimento' in df.columns:
            unique_key = df['Empreendimento'].iloc[0] if len(df['Empreendimento'].unique()) == 1 else f"gantt_{int(time.time() * 1000)}"
        else:
            unique_key = f"gantt_{int(time.time() * 1000)}"

    create_fullscreen_image_viewer(
    figure=figura, 
    empreendimento=unique_key

    )

    plt.close(figura)


#========================================================================================================

st.set_page_config(layout="wide", page_title="Dashboard de Gantt Comparativo")

@st.cache_data
def load_data():
    df_real = pd.DataFrame()
    df_previsto = pd.DataFrame()

    if processar_smartsheet_main:
        try:
            processar_smartsheet_main()
            df_real = pd.read_csv("Dados Reais Tratados e Ordenados.csv")
        except Exception as e:
            st.warning(f"Erro ao carregar dados reais do Smartsheet: {e}")

    if tratar_e_retornar_dados_previstos:
        try:
            df_previsto = tratar_e_retornar_dados_previstos()
            if df_previsto is None:
                df_previsto = pd.DataFrame()
        except Exception as e:
            st.warning(f"Erro ao carregar dados previstos: {e}")

    if df_real.empty and df_previsto.empty:
        st.warning("Nenhuma fonte de dados carregada. Usando dados de exemplo.")
        return 

    # Padronização e Merge
    if not df_real.empty:
        df_real["Etapa"] = df_real["Etapa"].apply(padronizar_etapa)
        # CORREÇÃO: Verificar se as colunas existem antes de renomear
        if "Data de Início" in df_real.columns and "Data de Fim" in df_real.columns:
            df_real.rename(
                columns={
                    "Emp": "Empreendimento",
                    "Data de Início": "Inicio_Real",
                    "Data de Fim": "Termino_Real",
                },
                inplace=True,
            )
        else:
            # Se as colunas não existirem, criar com valores vazios
            if "Inicio_Real" not in df_real.columns:
                df_real["Inicio_Real"] = pd.NaT
            if "Termino_Real" not in df_real.columns:
                df_real["Termino_Real"] = pd.NaT
            if "Empreendimento" not in df_real.columns and "Emp" in df_real.columns:
                df_real.rename(columns={"Emp": "Empreendimento"}, inplace=True)
        
        df_real["% concluído"] = df_real.get("% concluído", pd.Series(0.0)).apply(
            converter_porcentagem
        )
        # Garantir que a coluna FASE existe nos dados reais
        if "FASE" not in df_real.columns:
            df_real["FASE"] = df_real["Etapa"].map(FASE_POR_ETAPA).fillna("Não especificada")

    df_previsto_pivot = pd.DataFrame() # Inicializa como DataFrame vazio
    if not df_previsto.empty:
        df_previsto["Etapa"] = df_previsto["Etapa"].apply(padronizar_etapa)
        df_previsto.rename(
            columns={
                "EMP": "Empreendimento",
                "Valor": "Data_Prevista",
            },
            inplace=True,
        )
        df_previsto_pivot = (
            df_previsto.pivot_table(
                index=["UGB", "Empreendimento", "Etapa"],
                columns="Inicio_Fim",
                values="Data_Prevista",
                aggfunc="first",
            )
            .reset_index()
        )
        df_previsto_pivot.rename(
            columns={
                "INÍCIO": "Inicio_Prevista",
                "TÉRMINO": "Termino_Prevista",
            },
            inplace=True,
        )
        # Garantir que a coluna FASE existe nos dados previstos
        if "FASE" not in df_previsto_pivot.columns:
            df_previsto_pivot["FASE"] = df_previsto_pivot["Etapa"].map(FASE_POR_ETAPA).fillna("Não especificada")

    # --- CORREÇÃO PRINCIPAL: Verificar se as colunas existem antes do merge ---
    # Define a lista de colunas desejadas do df_real
    colunas_real_desejadas = ["UGB", "Empreendimento", "Etapa", "Inicio_Real", "Termino_Real", "% concluído", "FASE"]
    
    # Filtra a lista para incluir apenas as colunas que realmente existem no df_real
    colunas_real_existentes = [col for col in colunas_real_desejadas if col in df_real.columns]
    
    # Se não existirem as colunas de datas reais, criar colunas vazias
    if "Inicio_Real" not in colunas_real_existentes:
        df_real["Inicio_Real"] = pd.NaT
        colunas_real_existentes.append("Inicio_Real")
    
    if "Termino_Real" not in colunas_real_existentes:
        df_real["Termino_Real"] = pd.NaT
        colunas_real_existentes.append("Termino_Real")

    # Merge considerando apenas UGB, Empreendimento e Etapa
    if not df_real.empty and not df_previsto_pivot.empty:
        df_merged = pd.merge(
            df_previsto_pivot,
            df_real[colunas_real_existentes], # Usa a lista de colunas filtrada
            on=["UGB", "Empreendimento", "Etapa"],
            how="outer",
            suffixes=["_prev", "_real"],
        )

        # Combinar as colunas FASE (priorizando a dos dados reais se disponível)
        if "FASE_real" in df_merged.columns and "FASE_prev" in df_merged.columns:
            df_merged["FASE"] = df_merged["FASE_real"].combine_first(df_merged["FASE_prev"])
            df_merged.drop(["FASE_prev", "FASE_real"], axis=1, inplace=True)
        elif "FASE_real" in df_merged.columns:
            df_merged.rename(columns={"FASE_real": "FASE"}, inplace=True)
        elif "FASE_prev" in df_merged.columns:
            df_merged.rename(columns={"FASE_prev": "FASE"}, inplace=True)

    elif not df_previsto_pivot.empty:
        df_merged = df_previsto_pivot
    elif not df_real.empty:
        df_merged = df_real
    else:
        df_merged = pd.DataFrame()

    # Preencher valores faltantes
    if "% concluído" in df_merged.columns:
        df_merged["% concluído"] = df_merged["% concluído"].fillna(0)
    else:
        df_merged["% concluído"] = 0.0
    
    # Garantir que todas as colunas necessárias existam
    colunas_necessarias = ["Inicio_Real", "Termino_Real", "Inicio_Prevista", "Termino_Prevista", "FASE"]
    for col in colunas_necessarias:
        if col not in df_merged.columns:
            df_merged[col] = pd.NaT if col in ["Inicio_Real", "Termino_Real", "Inicio_Prevista", "Termino_Prevista"] else "Não especificada"

    # Remover linhas sem informações essenciais
    if not df_merged.empty:
        df_merged.dropna(subset=["Empreendimento", "Etapa"], inplace=True)

    return df_merged

# --- Interface do Streamlit ---

# Verificar se o popup deve ser exibido
if show_welcome_screen():
    st.stop()  # Para a execução do resto do app enquanto o popup está ativo

# --- INÍCIO DA IMPLEMENTAÇÃO DO MENU FLUTUANTE ---
# CSS customizado
st.markdown("""
<style>
    /* Altera APENAS os checkboxes dos multiselects */
    div.stMultiSelect div[role="option"] input[type="checkbox"]:checked + div > div:first-child {
        background-color: #4a0101 !important;
        border-color: #4a0101 !important;
    }
    
    /* Cor de fundo dos itens selecionados */
    div.stMultiSelect [aria-selected="true"] {
        background-color: #f8d7da !important;
        color: #333 !important;
        border-radius: 4px;
    }
    
    /* Estilo do "×" de remoção */
    div.stMultiSelect [aria-selected="true"]::after {
        color: #4a0101 !important;
        font-weight: bold;
    }
    
    /* Espaçamento entre os filtros */
    .stSidebar .stMultiSelect, .stSidebar .stSelectbox, .stSidebar .stRadio {
        margin-bottom: 1rem;
    }
    
    /* Estilo para botões de navegação */
    .nav-button-container {
        position: fixed;
        right: 20px;
        top: 20%;
        transform: translateY(-20%);
        z-index: 80;
        background: white;
        padding: 5px;
        border-radius: 15px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
            
    /* Estilo padrão */
    .nav-link {
        display: block;
        background-color: #a6abb5;
        color: white !important;
        text-decoration: none !important;
        border-radius: 10px;
        padding: 5px 10px;
        margin: 5px 0;
        text-align: center;
        font-weight: bold;
        font-size: 14px;
        transition: all 0.3s ease;
    }
            
    /* Estilo para quando selecionado */
    .nav-link:hover {
        background-color: #ff4b4b; 
        transform: scale(1.05);
    }
</style>
""", unsafe_allow_html=True)
# --- FIM DA IMPLEMENTAÇÃO DO MENU FLUTUANTE ---


# CSS customizado (mantido igual)
st.markdown(
    """
<style>
    /* Altera APENAS os checkboxes dos multiselects */
    div.stMultiSelect div[role="option"] input[type="checkbox"]:checked + div > div:first-child {
        background-color: #4a0101 !important;
        border-color: #4a0101 !important;
    }
    
    /* Cor de fundo dos itens selecionados */
    div.stMultiSelect [aria-selected="true"] {
        background-color: #f8d7da !important;
        color: #333 !important;
        border-radius: 4px;
    }
    
    /* Estilo do "×" de remoção */
    div.stMultiSelect [aria-selected="true"]::after {
        color: #4a0101 !important;
        font-weight: bold;
    }
    
    /* Espaçamento entre os filtros */
    .stSidebar .stMultiSelect, .stSidebar .stSelectbox, .stSidebar .stRadio, .stSidebar .stCheckbox {
        margin-bottom: 1rem;
    }
</style>
""",
    unsafe_allow_html=True,
)

st.title("Neoenergia")

# Cache para melhorar performance
@st.cache_data
def get_unique_values(df, column):
    """Função para cachear valores únicos de uma coluna"""
    return sorted(df[column].dropna().unique().tolist())

@st.cache_data
def filter_dataframe(df, ugb_filter, emp_filter, fase_filter):
    """Função para cachear filtragem do DataFrame"""
    if not ugb_filter:
        return df.iloc[0:0]  # DataFrame vazio se nenhuma UGB selecionada

    df_filtered = df[df["UGB"].isin(ugb_filter)]

    if emp_filter:
        df_filtered = df_filtered[df_filtered["Empreendimento"].isin(emp_filter)]

    if fase_filter:
        df_filtered = df_filtered[df_filtered["FASE"].isin(fase_filter)]

    return df_filtered

with st.spinner("Carregando e processando dados..."):
    df_data = load_data()

if df_data is not None and not df_data.empty:
    # Logo no sidebar
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)  # Espaço no topo

        # Centraliza a imagem
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            try:
                st.image("logoNova.png", width=200)
            except FileNotFoundError:
                st.warning(
                    "Logo não encontrada. Verifique se o arquivo 'logoNova.png' está no diretório correto."
                )

        # 1️⃣ Filtro UGB (Componente personalizado)
        ugb_options = get_unique_values(df_data, "UGB")
        selected_ugb = simple_multiselect_dropdown(
            label="Filtrar por UGB",
            options=ugb_options,
            key="ugb_filter",
            default_selected=ugb_options,
        )

        # 2️⃣ Filtro Empreendimento (Componente personalizado)
        # Otimização: só calcular opções de empreendimento se UGB foi selecionada
        if selected_ugb:
            emp_options = get_unique_values(
                df_data[df_data["UGB"].isin(selected_ugb)], "Empreendimento"
            )
        else:
            emp_options = []

        selected_emp = simple_multiselect_dropdown(
            label="Filtrar por Empreendimento",
            options=emp_options,
            key="empreendimento_filter",
            default_selected=emp_options,
        )

        # 3️⃣ Filtro FASE (NOVO FILTRO - mesmo estilo dos anteriores)
        # Otimização: só calcular opções de fase se UGB e Empreendimento foram selecionados
        if selected_ugb:
            # Primeiro filtra por UGB
            df_temp = df_data[df_data["UGB"].isin(selected_ugb)]

            # Depois filtra por Empreendimento se houver seleção
            if selected_emp:
                df_temp = df_temp[df_temp["Empreendimento"].isin(selected_emp)]

            fase_options = get_unique_values(df_temp, "FASE")
        else:
            fase_options = []

        selected_fase = simple_multiselect_dropdown(
            label="Filtrar por FASE",
            options=fase_options,
            key="fase_filter",
            default_selected=fase_options,
        )

        # 4️⃣ Filtro Etapa (agora depende também do filtro de FASE)
        # Aplicar todos os filtros antes de mostrar etapas
        df_temp_filtered = filter_dataframe(
            df_data, selected_ugb, selected_emp, selected_fase
        )

        if not df_temp_filtered.empty:
            etapas_disponiveis = get_unique_values(df_temp_filtered, "Etapa")

            # Ordenar etapas se sigla_para_nome_completo estiver definido
            try:
                etapas_disponiveis = sorted(
                    etapas_disponiveis,
                    key=lambda x:
                        list(sigla_para_nome_completo.keys()).index(x)
                        if x in sigla_para_nome_completo
                        else 99,
                )
                etapas_para_exibir = ["Todos"] + [
                    sigla_para_nome_completo.get(e, e) for e in etapas_disponiveis
                ]
            except NameError:
                # Se sigla_para_nome_completo não estiver definido, usar as etapas como estão
                etapas_para_exibir = ["Todos"] + etapas_disponiveis
        else:
            etapas_para_exibir = ["Todos"]

        selected_etapa_nome = st.selectbox(
            "Filtrar por Etapa", options=etapas_para_exibir
        )

    # 4️⃣ NOVO FILTRO: Etapas não concluídas
    st.sidebar.markdown("---")
    filtrar_nao_concluidas = st.sidebar.checkbox(
        "Mostrar apenas etapas não concluídas",
        value=False,
        help="Quando marcado, mostra apenas etapas com menos de 100% de conclusão",
    )

    # 5️⃣ Opção de visualização
    st.sidebar.markdown("---")
    tipo_visualizacao = st.sidebar.radio("Mostrar dados:", ("Ambos", "Previsto", "Real"))

    # Aplica todos os filtros finais
    df_filtered = filter_dataframe(df_data, selected_ugb, selected_emp, selected_fase)

    # Aplica o filtro de etapa final
    if selected_etapa_nome != "Todos" and not df_filtered.empty:
        try:
            sigla_selecionada = nome_completo_para_sigla.get(
                selected_etapa_nome, selected_etapa_nome
            )
            df_filtered = df_filtered[df_filtered["Etapa"] == sigla_selecionada]
        except NameError:
            # Se nome_completo_para_sigla não estiver definido, usar o nome como está
            df_filtered = df_filtered[df_filtered["Etapa"] == selected_etapa_nome]

    # APLICAR NOVO FILTRO: Etapas não concluídas
    if filtrar_nao_concluidas and not df_filtered.empty:
        df_filtered = filtrar_etapas_nao_concluidas(df_filtered)

        # Mostrar informação sobre o filtro aplicado
        if not df_filtered.empty:
            total_etapas_nao_concluidas = len(df_filtered)
            st.sidebar.success(f"✅ Mostrando {total_etapas_nao_concluidas} etapas não concluídas")
        else:
            st.sidebar.info("ℹ️ Todas as etapas estão 100% concluídas")


    # Abas principais
    tab1, tab2 = st.tabs(["Gantt – Previsto vs Real", "Tabelão Horizontal"])
#========================================================================================================
# --- Início do Bloco de Código Fornecido ---

    with tab1:
        # --- INÍCIO DA IMPLEMENTAÇÃO DO MENU FLUTUANTE ---
        # Botões de navegação simples usando HTML com âncoras
        st.markdown("""
        <div class="nav-button-container">
            <a href="#inicio" class="nav-link">↑</a>
            <a href="#visao-detalhada" class="nav-link">↓</a>
        </div>
        """, unsafe_allow_html=True)
        
        # Âncora para o início
        st.markdown('<div id="inicio"></div>', unsafe_allow_html=True)
        # --- FIM DA IMPLEMENTAÇÃO DO MENU FLUTUANTE ---

        st.subheader("Gantt Comparativo")
        if df_filtered.empty:
            st.warning("⚠️ Nenhum dado encontrado com os filtros aplicados.")
        else:
            # Passa o parâmetro filtrar_nao_concluidas para a função de Gantt
            gerar_gantt(df_filtered.copy(), tipo_visualizacao)

        # --- INÍCIO DA IMPLEMENTAÇÃO DO MENU FLUTUANTE ---
        # Âncora para a tabela
        st.markdown('<div id="visao-detalhada"></div>', unsafe_allow_html=True)
        # --- FIM DA IMPLEMENTAÇÃO DO MENU FLUTUANTE ---

        st.subheader("Visão Detalhada por Empreendimento")
        if df_filtered.empty:
            st.warning("⚠️ Nenhum dado encontrado com os filtros aplicados.")
        else:
            # --- INÍCIO DA LÓGICA CORRIGIDA (DENTRO DO ELSE) ---
            df_detalhes = df_filtered.copy()
            hoje = pd.Timestamp.now().normalize()

            # Converter colunas para datetime, tratando '-' como NaN
            for col in ['Inicio_Prevista', 'Termino_Prevista', 'Inicio_Real', 'Termino_Real']:
                df_detalhes[col] = df_detalhes[col].replace('-', pd.NA)
                df_detalhes[col] = pd.to_datetime(df_detalhes[col], errors='coerce')

            # Criar flag de validação de conclusão
            df_detalhes['Conclusao_Valida'] = False
            if '% concluído' in df_detalhes.columns:
                mask = (
                    (df_detalhes['% concluído'] == 100) & 
                    (df_detalhes['Termino_Real'].notna()) &
                    ((df_detalhes['Termino_Prevista'].isna()) | 
                    (df_detalhes['Termino_Real'] <= df_detalhes['Termino_Prevista']))
                )
                df_detalhes.loc[mask, 'Conclusao_Valida'] = True

            # Agregar dados
            df_agregado = df_detalhes.groupby(['Empreendimento', 'Etapa']).agg(
                Inicio_Prevista=('Inicio_Prevista', 'min'),
                Termino_Prevista=('Termino_Prevista', 'max'),
                Inicio_Real=('Inicio_Real', 'min'),
                Termino_Real=('Termino_Real', 'max'),
                Concluido_Valido=('Conclusao_Valida', 'any'),
                Percentual_Concluido=('% concluído', 'max') if '% concluído' in df_detalhes.columns else ('% concluído', lambda x: 0)
            ).reset_index()

            # Converter para porcentagem (0-100) se estiver em formato decimal (0-1)
            if '% concluído' in df_detalhes.columns:
                if not df_agregado.empty and df_agregado['Percentual_Concluido'].max() <= 1:
                    df_agregado['Percentual_Concluido'] = df_agregado['Percentual_Concluido'] * 100

            # Calcular variação de término
            df_agregado['Var. Term'] = df_agregado.apply(lambda row: calculate_business_days(row['Termino_Real'], row['Termino_Prevista']), axis=1)
            
            # NOVA FUNCIONALIDADE: Calcular duração real (oculta)
            df_agregado['Duracao_Real'] = (df_agregado['Termino_Real'] - df_agregado['Inicio_Real']).dt.days

            # --- Controles de Classificação ---
            st.write("---")
            col1, col2 = st.columns(2)
            
            opcoes_classificacao = {
                'Padrão (Empreendimento e Etapa)': ['Empreendimento', 'Etapa_Ordem'],
                'Empreendimento (A-Z)': ['Empreendimento'],
                'Data de Início Previsto (Mais antiga)': ['Inicio_Prevista'],
                'Data de Término Previsto (Mais recente)': ['Termino_Prevista'],
                'Variação de Prazo (Pior para Melhor)': ['Var. Term']
            }

            with col1:
                classificar_por = st.selectbox("Ordenar tabela por:", options=list(opcoes_classificacao.keys()))
            with col2:
                ordem = st.radio("Ordem:", options=['Crescente', 'Decrescente'], horizontal=True)

            ordem_bool = (ordem == 'Crescente')
            colunas_para_ordenar = opcoes_classificacao[classificar_por]
            
            ordem_etapas = list(sigla_para_nome_completo.keys())
            df_agregado['Etapa_Ordem'] = df_agregado['Etapa'].apply(lambda x: ordem_etapas.index(x) if x in ordem_etapas else len(ordem_etapas))
            
            df_ordenado = df_agregado.sort_values(by=colunas_para_ordenar, ascending=ordem_bool)
            st.write("---")

            # --- Montagem da Estrutura Hierárquica ---
            tabela_final_lista = []
            for empreendimento, grupo in df_ordenado.groupby('Empreendimento', sort=False):
                var_term_assinatura = grupo[grupo['Etapa'] == 'ASS']['Var. Term']
                var_term_cabecalho = var_term_assinatura.iloc[0] if not var_term_assinatura.empty and pd.notna(var_term_assinatura.iloc[0]) else grupo['Var. Term'].mean()
                
                percentuais = grupo['Percentual_Concluido']
                # ALTERAÇÃO: Usar duração real ao invés de variação de término
                duracao_real = grupo['Duracao_Real']
                valid_mask = (~duracao_real.isna()) & (~percentuais.isna())
                percentuais_validos = percentuais[valid_mask]
                duracao_real_validos = duracao_real[valid_mask]
                
                if len(percentuais_validos) > 0 and len(duracao_real_validos) > 0 and duracao_real_validos.sum() != 0:
                    soma_ponderada = (percentuais_validos * duracao_real_validos).sum()
                    soma_pesos = duracao_real_validos.sum()
                    percentual_medio = soma_ponderada / soma_pesos
                else:
                    percentual_medio = percentuais.mean()
                
                cabecalho = pd.DataFrame([{
                    'Hierarquia': f'📂 {empreendimento}', 
                    'Inicio_Prevista': grupo['Inicio_Prevista'].min(), 
                    'Termino_Prevista': grupo['Termino_Prevista'].max(),
                    'Inicio_Real': grupo['Inicio_Real'].min(), 
                    'Termino_Real': grupo['Termino_Real'].max(), 
                    'Var. Term': var_term_cabecalho,
                    'Percentual_Concluido': percentual_medio
                }])
                tabela_final_lista.append(cabecalho)
                
                grupo_formatado = grupo.copy()
                grupo_formatado['Hierarquia'] = ' &nbsp; &nbsp; ' + grupo_formatado['Etapa'].map(sigla_para_nome_completo)
                tabela_final_lista.append(grupo_formatado)

            tabela_final = pd.concat(tabela_final_lista, ignore_index=True)

            # --- Aplicação de Estilo Condicional e Formatação ---
            def aplicar_estilo(df_para_estilo):
                if df_para_estilo.empty:
                    return df_para_estilo.style

                def estilo_linha(row):
                    style = [None] * len(row)
                    
                    if str(row['Empreendimento / Etapa']).startswith('📂'):
                        for i in range(len(style)):
                            style[i] = "font-weight: 500; color: #000000; background-color: #F0F2F6; border-left: 4px solid #000000; padding-left: 10px;"
                            if i > 0:
                                style[i] = "background-color: #F0F2F6;"
                        return style
                    
                    percentual = row.get('% Concluído', 0)
                    if isinstance(percentual, str) and '%' in percentual:
                        try: percentual = int(percentual.replace('%', ''))
                        except: percentual = 0

                    termino_real, termino_previsto, hoje_data = row["Término Real"], row["Término Prev."], pd.Timestamp.now()
                    cor = "#000000"
                    if percentual == 100:
                        if pd.notna(termino_real) and pd.notna(termino_previsto):
                            if termino_real < termino_previsto: cor = "#2EAF5B"
                            elif termino_real > termino_previsto: cor = "#C30202"
                    elif pd.notna(termino_real) and (termino_real < hoje_data):
                        cor = "#A38408"

                    for i, col in enumerate(df_para_estilo.columns):
                        if col in ['Início Real', 'Término Real']:
                            style[i] = f"color: {cor};"

                    if pd.notna(row.get("Var. Term", None)):
                        val = row["Var. Term"]
                        if isinstance(val, str):
                            try: val = int(val.split()[1]) * (-1 if '▲' in val else 1)
                            except: val = 0
                        cor_texto = "#e74c3c" if val < 0 else "#2ecc71"
                        style[df_para_estilo.columns.get_loc("Var. Term")] = f"color: {cor_texto}; font-weight: 600; font-size: 12px; text-align: center;"
                    return style

                styler = df_para_estilo.style.format({
                    "Início Prev.": lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else "-",
                    "Término Prev.": lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else "-",
                    "Início Real": lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else "-",
                    "Término Real": lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else "-",
                    "Var. Term": lambda x: f"{'▼' if isinstance(x, (int, float)) and x > 0 else '▲'} {abs(int(x))} dias" if pd.notna(x) else "-",
                    "% Concluído": lambda x: f"{int(x)}%" if pd.notna(x) and str(x) != 'nan' else "-"
                }, na_rep="-")
                
                styler = styler.set_properties(**{'white-space': 'nowrap', 'text-overflow': 'ellipsis', 'overflow': 'hidden', 'max-width': '380px'})
                styler = styler.apply(estilo_linha, axis=1).hide(axis="index")
                return styler

            st.markdown("""
            <style>
                .stDataFrame { width: 100%; }
                .stDataFrame td, .stDataFrame th { white-space: nowrap !important; text-overflow: ellipsis !important; overflow: hidden !important; max-width: 380px !important; }
            </style>
            """, unsafe_allow_html=True)

            tabela_para_exibir = tabela_final.rename(columns={
                'Hierarquia': 'Empreendimento / Etapa', 'Inicio_Prevista': 'Início Prev.',
                'Termino_Prevista': 'Término Prev.', 'Inicio_Real': 'Início Real',
                'Termino_Real': 'Término Real', 'Percentual_Concluido': '% Concluído'
            })
            # A coluna 'Duracao_Real' não é incluída nas colunas para exibir, mantendo-a oculta
            colunas_para_exibir = ['Empreendimento / Etapa', '% Concluído', 'Início Prev.', 'Término Prev.', 'Início Real', 'Término Real', 'Var. Term']
            tabela_estilizada = aplicar_estilo(tabela_para_exibir[colunas_para_exibir])
            st.markdown(tabela_estilizada.to_html(), unsafe_allow_html=True)
            
#========================================================================================================

    with tab2:
        st.subheader("Tabelão Horizontal")

        if df_filtered.empty:
            st.warning("⚠️ Nenhum dado encontrado com os filtros aplicados.")
        else:
            # --- DATA PREPARATION ---
            df_detalhes = df_filtered.copy()
            hoje = pd.Timestamp.now().normalize()

            # Column renaming and cleaning
            df_detalhes = df_detalhes.rename(columns={
                'Termino_prevista': 'Termino_Prevista', 
                'Termino_real': 'Termino_Real'
            })
            
            # Date conversion
            for col in ['Inicio_Prevista', 'Termino_Prevista', 'Inicio_Real', 'Termino_Real']:
                if col in df_detalhes.columns:
                    df_detalhes[col] = df_detalhes[col].replace('-', pd.NA)
                    df_detalhes[col] = pd.to_datetime(df_detalhes[col], errors='coerce')

            # Completion validation
            df_detalhes['Conclusao_Valida'] = False
            if '% concluído' in df_detalhes.columns:
                mask = (
                    (df_detalhes['% concluído'] == 100) & 
                    (df_detalhes['Termino_Real'].notna()) & 
                    ((df_detalhes['Termino_Prevista'].isna()) | 
                    (df_detalhes['Termino_Real'] <= df_detalhes['Termino_Prevista']))
                )
                df_detalhes.loc[mask, 'Conclusao_Valida'] = True

            # --- SORTING OPTIONS ---
            st.write("---")
            col1, col2 = st.columns(2)
            
            opcoes_classificacao = {
                'Padrão (UGB, Empreendimento e Etapa)': ['UGB', 'Empreendimento', 'Etapa_Ordem'], 
                'UGB (A-Z)': ['UGB'],
                'Empreendimento (A-Z)': ['Empreendimento'], 
                'Data de Início Previsto (Mais antiga)': ['Inicio_Prevista'],
                'Data de Término Previsto (Mais recente)': ['Termino_Prevista'], 
            }
            
            with col1:
                classificar_por = st.selectbox(
                    "Ordenar tabela por:", 
                    options=list(opcoes_classificacao.keys()), 
                    key="classificar_por_selectbox"
                )
                
            with col2:
                ordem = st.radio(
                    "Ordem:", 
                    options=['Crescente', 'Decrescente'], 
                    horizontal=True, 
                    key="ordem_radio"
                )

            # NOVA ABORDAGEM: Ordenar ANTES da agregação para preservar ordem cronológica
            ordem_etapas_completas = list(sigla_para_nome_completo.keys())
            df_detalhes['Etapa_Ordem'] = df_detalhes['Etapa'].apply(
                lambda x: ordem_etapas_completas.index(x) if x in ordem_etapas_completas else len(ordem_etapas_completas)
            )
            
            # Para ordenações por data, ordenar os dados originais primeiro
            if classificar_por in ['Data de Início Previsto (Mais antiga)', 'Data de Término Previsto (Mais recente)']:
                coluna_data = 'Inicio_Prevista' if 'Início' in classificar_por else 'Termino_Prevista'
                
                # Ordenar os dados originais pela data escolhida
                df_detalhes_ordenado = df_detalhes.sort_values(
                    by=[coluna_data, 'UGB', 'Empreendimento', 'Etapa'], 
                    ascending=[ordem == 'Crescente', True, True, True],
                    na_position='last'
                )
                
                # Criar um mapeamento de ordem para UGB/Empreendimento baseado na primeira ocorrência
                ordem_ugb_emp = df_detalhes_ordenado.groupby(['UGB', 'Empreendimento']).first().reset_index()
                ordem_ugb_emp = ordem_ugb_emp.sort_values(
                    by=coluna_data, 
                    ascending=(ordem == 'Crescente'),
                    na_position='last'
                )
                ordem_ugb_emp['ordem_index'] = range(len(ordem_ugb_emp))
                
                # Mapear a ordem de volta para os dados originais
                df_detalhes = df_detalhes.merge(
                    ordem_ugb_emp[['UGB', 'Empreendimento', 'ordem_index']], 
                    on=['UGB', 'Empreendimento'], 
                    how='left'
                )
                
            # --- DATA AGGREGATION ---
            agg_dict = {
                'Inicio_Prevista': ('Inicio_Prevista', 'min'), 
                'Termino_Prevista': ('Termino_Prevista', 'max'),
                'Inicio_Real': ('Inicio_Real', 'min'), 
                'Termino_Real': ('Termino_Real', 'max'),
                'Concluido_Valido': ('Conclusao_Valida', 'any')
            }
            
            if '% concluído' in df_detalhes.columns:
                agg_dict['Percentual_Concluido'] = ('% concluído', 'max')
                if not df_detalhes.empty and df_detalhes['% concluído'].max() <= 1:
                    df_detalhes['% concluído'] *= 100

            # Adicionar ordem_index à agregação se existir
            if 'ordem_index' in df_detalhes.columns:
                agg_dict['ordem_index'] = ('ordem_index', 'first')

            # Aggregate data
            df_agregado = df_detalhes.groupby(['UGB', 'Empreendimento', 'Etapa']).agg(**agg_dict).reset_index()
            
            # Calculate variation
            df_agregado['Var. Term'] = df_agregado.apply(lambda row: calculate_business_days(row['Termino_Prevista'], row['Termino_Real']), axis=1)

            # Adicionar Etapa_Ordem
            df_agregado['Etapa_Ordem'] = df_agregado['Etapa'].apply(
                lambda x: ordem_etapas_completas.index(x) if x in ordem_etapas_completas else len(ordem_etapas_completas)
            )

            # Aplicar ordenação baseada na escolha do usuário
            if classificar_por in ['Data de Início Previsto (Mais antiga)', 'Data de Término Previsto (Mais recente)']:
                # Para ordenações por data, usar a ordem_index criada anteriormente
                df_ordenado = df_agregado.sort_values(
                    by=['ordem_index', 'UGB', 'Empreendimento', 'Etapa_Ordem'], 
                    ascending=[True, True, True, True]
                )
            else:
                # Para outras ordenações, usar o método original
                df_ordenado = df_agregado.sort_values(
                    by=opcoes_classificacao[classificar_por], 
                    ascending=(ordem == 'Crescente')
                )
            
            st.write("---")

            # --- PIVOT TABLE CREATION ---
            df_pivot = df_ordenado.pivot_table(
                index=['UGB', 'Empreendimento'], 
                columns='Etapa', 
                values=['Inicio_Prevista', 'Termino_Prevista', 'Inicio_Real', 'Termino_Real', 'Var. Term'], 
                aggfunc='first'
            )

            # Column ordering for pivot table
            etapas_existentes_no_pivot = df_pivot.columns.get_level_values(1).unique()
            colunas_ordenadas = []
            
            for etapa in ordem_etapas_completas:
                if etapa in etapas_existentes_no_pivot:
                    for tipo in ['Inicio_Prevista', 'Termino_Prevista', 'Inicio_Real', 'Termino_Real', 'Var. Term']:
                        if (tipo, etapa) in df_pivot.columns:
                            colunas_ordenadas.append((tipo, etapa))
            
            df_final = df_pivot[colunas_ordenadas].reset_index()

            # Para ordenações por data, reordenar o df_final baseado na ordem correta
            if classificar_por in ['Data de Início Previsto (Mais antiga)', 'Data de Término Previsto (Mais recente)']:
                # Obter ordem única de UGB/Empreendimento do df_ordenado
                ordem_linhas_final = df_ordenado[['UGB', 'Empreendimento']].drop_duplicates().reset_index(drop=True)
                
                # Reordenar df_final
                df_final = df_final.set_index(['UGB', 'Empreendimento'])
                df_final = df_final.reindex(pd.MultiIndex.from_frame(ordem_linhas_final))
                df_final = df_final.reset_index()

            # --- COLUMN RENAMING FOR MULTIINDEX ---
            novos_nomes = []
            for col in df_final.columns:
                if col[0] in ['UGB', 'Empreendimento']: 
                    novos_nomes.append((col[0], ''))  # Segundo nível vazio para colunas simples
                else:
                    tipo, etapa = col[0], col[1]
                    nome_etapa = sigla_para_nome_completo.get(etapa, etapa)
                    nome_tipo = {
                        'Inicio_Prevista': 'Início Prev.', 
                        'Termino_Prevista': 'Término Prev.', 
                        'Inicio_Real': 'Início Real', 
                        'Termino_Real': 'Término Real', 
                        'Var. Term': 'VarTerm'
                    }[tipo]
                    novos_nomes.append((nome_etapa, nome_tipo))
            
            df_final.columns = pd.MultiIndex.from_tuples(novos_nomes)

            # --- FORMATTING FUNCTIONS ---
            def formatar_valor(valor, tipo):
                if pd.isna(valor): 
                    return "-"
                if tipo == 'data': 
                    return valor.strftime("%d/%m/%Y")
                if tipo == 'variacao': 
                    return f"{'▼' if valor > 0 else '▲'} {abs(int(valor))} dias"
                return str(valor)

            def determinar_cor(row, col_tuple):
                """Determina a cor baseada no status da etapa"""
                if len(col_tuple) == 2 and (col_tuple[1] in ['Início Real', 'Término Real']):
                    etapa_nome_completo = col_tuple[0]
                    etapa_sigla = nome_completo_para_sigla.get(etapa_nome_completo)
                    
                    if etapa_sigla:
                        # Busca os dados da etapa específica no df_agregado
                        etapa_data = df_agregado[
                            (df_agregado['UGB'] == row[('UGB', '')]) & 
                            (df_agregado['Empreendimento'] == row[('Empreendimento', '')]) & 
                            (df_agregado['Etapa'] == etapa_sigla)
                        ]
                        
                        if not etapa_data.empty:
                            etapa_data = etapa_data.iloc[0]
                            percentual = etapa_data.get('Percentual_Concluido', 0)
                            termino_real = etapa_data['Termino_Real']
                            termino_previsto = etapa_data['Termino_Prevista']
                            
                            # Verifica se está 100% concluído
                            if percentual == 100:
                                if pd.notna(termino_real) and pd.notna(termino_previsto):
                                    if termino_real < termino_previsto: 
                                        return "color: #2EAF5B; font-weight: bold;"  # Concluído antes
                                    elif termino_real > termino_previsto: 
                                        return "color: #C30202; font-weight: bold;"  # Concluído com atraso
                            # Verifica se está atrasado (data passou mas não está 100%)
                            elif pd.notna(termino_real) and (termino_real < hoje): 
                                return "color: #A38408; font-weight: bold;"  # Aguardando atualização
                
                # Padrão para outras colunas ou casos não especificados
                return ""

            # --- DATA FORMATTING (APLICAR APENAS APÓS ORDENAÇÃO) ---
            df_formatado = df_final.copy()
            for col_tuple in df_formatado.columns:
                if len(col_tuple) == 2 and col_tuple[1] != '':  # Ignorar colunas sem segundo nível
                    if any(x in col_tuple[1] for x in ["Início Prev.", "Término Prev.", "Início Real", "Término Real"]): 
                        df_formatado[col_tuple] = df_formatado[col_tuple].apply(lambda x: formatar_valor(x, "data"))
                    elif "VarTerm" in col_tuple[1]: 
                        df_formatado[col_tuple] = df_formatado[col_tuple].apply(lambda x: formatar_valor(x, "variacao"))

            # --- STYLING FUNCTION ---
            def aplicar_estilos(df):
                # Cria um DataFrame de estilos vazio com as mesmas dimensões do DataFrame original
                styles = pd.DataFrame('', index=df.index, columns=df.columns)
                
                for i, row in df.iterrows():
                    # Aplicar zebra striping (cor de fundo alternada) para todas as células da linha
                    cor_fundo = "#fbfbfb" if i % 2 == 0 else '#ffffff'
                    
                    for col_tuple in df.columns:
                        # Estilo base com zebra striping
                        cell_style = f"background-color: {cor_fundo};"
                        
                        # Aplicar estilo para células de dados
                        if len(col_tuple) == 2 and col_tuple[1] != '':
                            # Dados faltantes
                            if row[col_tuple] == '-':
                                cell_style += ' color: #999999; font-style: italic;'
                            else:
                                # Aplicar cores condicionais para Início/Término Real
                                if col_tuple[1] in ['Início Real', 'Término Real']:
                                    row_dict = {('UGB', ''): row[('UGB', '')], 
                                            ('Empreendimento', ''): row[('Empreendimento', '')]}
                                    cor_condicional = determinar_cor(row_dict, col_tuple)
                                    if cor_condicional:
                                        cell_style += f' {cor_condicional}'
                                
                                # Estilo para variação de prazo
                                elif 'VarTerm' in col_tuple[1]:
                                    if '▲' in str(row[col_tuple]):  # Atraso
                                        cell_style += ' color: #e74c3c; font-weight: 600;'
                                    elif '▼' in str(row[col_tuple]):  # Adiantamento
                                        cell_style += ' color: #2ecc71; font-weight: 600;'
                        else:
                            # Para colunas UGB e Empreendimento, manter apenas o fundo zebrado
                            pass
                        
                        styles.at[i, col_tuple] = cell_style
                
                return styles

            # --- TABLE STYLING ---
            header_styles = [
                # Estilo para o nível superior (etapas)
                {
                    'selector': 'th.level0',
                    'props': [
                        ('font-size', '12px'),
                        ('font-weight', 'bold'),
                        ('background-color', "#6c6d6d"),
                        ('border-bottom', '2px solid #ddd'),
                        ('text-align', 'center'),
                        ('white-space', 'nowrap')
                    ]
                },
                # Estilo para o nível inferior (tipos de data)
                {
                    'selector': 'th.level1',
                    'props': [
                        ('font-size', '11px'),
                        ('font-weight', 'normal'),
                        ('background-color', '#f8f9fa'),
                        ('text-align', 'center'),
                        ('white-space', 'nowrap')
                    ]
                },
                # Estilo para células de dados
                {
                    'selector': 'td',
                    'props': [
                        ('font-size', '12px'),
                        ('text-align', 'center'),
                        ('padding', '5px 8px'),
                        ('border', '1px solid #f0f0f0')
                    ]
                },
                # Estilo para cabeçalho das colunas UGB e Empreendimento
                {
                    'selector': 'th.col_heading.level0',
                    'props': [
                        ('font-size', '12px'),
                        ('font-weight', 'bold'),
                        ('background-color', '#6c6d6d'),
                        ('text-align', 'center')
                    ]
                }
            ]

            # Adicionar bordas entre grupos de colunas
            for i, etapa in enumerate(ordem_etapas_completas):
                if i > 0:  # Não aplicar para a primeira etapa
                    # Encontrar a primeira coluna de cada etapa
                    etapa_nome = sigla_para_nome_completo.get(etapa, etapa)
                    col_idx = next((idx for idx, col in enumerate(df_final.columns) 
                                if col[0] == etapa_nome), None)
                    if col_idx:
                        header_styles.append({
                            'selector': f'th:nth-child({col_idx+1})',
                            'props': [('border-left', '2px solid #ddd')]
                        })
                        header_styles.append({
                            'selector': f'td:nth-child({col_idx+1})',
                            'props': [('border-left', '2px solid #ddd')]
                        })

            # Aplicar estilos condicionais
            styled_df = df_formatado.style.apply(aplicar_estilos, axis=None)
            styled_df = styled_df.set_table_styles(header_styles)

            # --- DISPLAY RESULTS ---
            st.dataframe(
                styled_df, 
                height=min(35 * len(df_final) + 40, 600), 
                hide_index=True, 
                use_container_width=True
            )
            
            # Legend
            st.markdown("""<div style="margin-top: 10px; font-size: 12px; color: #555;">
                <strong>Legenda:</strong> 
                <span style="color: #2EAF5B; font-weight: bold;">■ Concluído antes do prazo</span> | 
                <span style="color: #C30202; font-weight: bold;">■ Concluído com atraso</span> | 
                <span style="color: #A38408; font-weight: bold;">■ Aguardando atualização</span> | 
                <span style="color: #000000; font-weight: bold;">■ Em andamento</span> | 
                <span style="color: #999; font-style: italic;"> - Dados não disponíveis</span>
            </div>""", unsafe_allow_html=True)
else:
    st.error("❌ Não foi possível carregar ou gerar os dados.")
