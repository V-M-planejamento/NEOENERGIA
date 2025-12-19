import streamlit as st
import pandas as pd
import numpy as np
import matplotlib as mpl
mpl.use("agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle
from matplotlib.legend_handler import HandlerTuple
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
from datetime import datetime, timedelta
import holidays
from dateutil.relativedelta import relativedelta #baseline
import json

import streamlit.components.v1 as components  
import random
import time
import urllib.parse
import mysql.connector
from mysql.connector import Error
from datetime import datetime
try:
    from dropdown_component import simple_multiselect_dropdown
    from popup import show_welcome_screen
    from calculate_business_days import calculate_business_days
except ImportError:
    st.warning("Componentes 'dropdown_component', 'popup' ou 'calculate_business_days' não encontrados. Alguns recursos podem não funcionar como esperado.")
    # Definir valores padrão ou mocks se necessário
    def simple_multiselect_dropdown(label, options, key, default_selected):
        return st.multiselect(label, options, default=default_selected, key=key)
    def show_welcome_screen():
        return False
    def calculate_business_days(start, end):
        if pd.isna(start) or pd.isna(end):
            return None
        return np.busday_count(pd.to_datetime(start).date(), pd.to_datetime(end).date())

# --- Bloco de Importação de Dados ---
try:
    from tratamento_dados_reais import buscar_e_processar_dados_completos
    from tratamento_macrofluxo import tratar_macrofluxo
    MODO_REAL = True
except ImportError:
    st.warning("Scripts de processamento não encontrados. O app usará dados de exemplo.")
    buscar_e_processar_dados_completos = None
    tratar_macrofluxo = None
    MODO_REAL = False

# --- Configurações do Banco AWS ---
try:
    DB_CONFIG = {
        'host': st.secrets["aws_db"]["host"],
        'user': st.secrets["aws_db"]["user"],
        'password': st.secrets["aws_db"]["password"],
        'database': st.secrets["aws_db"]["database"],
        'port': 3306
    }
except Exception:
    DB_CONFIG = {
        'host': "mock_host",
        'user': "mock_user", 
        'password': "mock_password",
        'database': "mock_db",
        'port': 3306
    }

if 'current_baseline' not in st.session_state:
    st.session_state.current_baseline = None
if 'current_baseline_data' not in st.session_state:
    st.session_state.current_baseline_data = None
if 'current_empreendimento' not in st.session_state:
    st.session_state.current_empreendimento = None

# Mostrar popup de boas-vindas com campo de email
show_welcome_screen()

# --- ORDEM DAS ETAPAS (DEFINIDA PELO USUÁRIO) ---
ORDEM_ETAPAS_GLOBAL = [
    "PROSPEC", "LEGVENDA", "PULVENDA", "PL.LIMP", "LEG.LIMP", "ENG.LIMP", "PE. LIMP.", "ORÇ. LIMP.", "SUP. LIMP.", "EXECLIMP",
    "PL.TER", "LEG.TER", "ENG. TER", "PE. TER.", "ORÇ. TER.", "SUP. TER.", "EXECTER", "PL.INFRA", "LEG.INFRA", "ENG.INFRA", "PE. INFRA", "ORÇ. INFRA", "SUP. INFRA",
    "EXECINFRA", "ENG.PAV", "PE. PAV", "ORÇ. PAV", "SUP. PAV", "EXEC.PAV", "PUL.INFRA", "PL.RAD", "LEG.RAD", "PUL.RAD",
    "RAD", "DEM.MIN", "PE. ÁREAS COMUNS (URB)", "PE. ÁREAS COMUNS (ENG)", "ORÇ. ÁREAS COMUNS", "SUP. ÁREAS COMUNS", "EXECUÇÃO ÁREAS COMUNS",
]

# --- Definição dos Grupos ---
GRUPOS = {
    "VENDA": ["PROSPECÇÃO", "LEGALIZAÇÃO PARA VENDA", "PULMÃO VENDA"],
    "LIMPEZA": ["PL.LIMP", "LEG.LIMP", "ENG. LIMP.", "EXECUÇÃO LIMP.", "PE. LIMP.", "ORÇ. LIMP.", "SUP. LIMP."],
    "TERRAPLANAGEM": ["PL.TER.", "LEG.TER.", "ENG. TER.", "EXECUÇÃO TER.", "PE. TER.", "ORÇ. TER.", "SUP. TER."],
    "INFRA INCIDENTE": ["PL.INFRA", "LEG.INFRA", "ENG. INFRA", "EXECUÇÃO INFRA", "PE. INFRA", "ORÇ. INFRA", "SUP. INFRA"],
    "PAVIMENTAÇÃO": ["ENG. PAV", "EXECUÇÃO PAV.", "PE. PAV", "ORÇ. PAV", "SUP. PAV"],
    "PULMÃO": ["PULMÃO INFRA"],
    "RADIER": ["PL.RADIER", "PL.RAD", "LEG.RADIER", "LEG.RAD", "PULMÃO RADIER", "PUL.RAD", "RADIER", "RAD"],
    "DM": ["DEMANDA MÍNIMA"],
    "EQUIPANENTOS COMUNS": ["PE. ÁREAS COMUNS (URB)", "PE. ÁREAS COMUNS (ENG)", "ORÇ. ÁREAS COMUNS", "SUP. ÁREAS COMUNS", "EXECUÇÃO ÁREAS COMUNS"],
}

SETOR = {
    "PROSPECÇÃO": ["PROSPECÇÃO"],
    "LEGALIZAÇÃO": ["LEGALIZAÇÃO PARA VENDA", "LEG.LIMP", "LEG.TER.", "LEG.INFRA", "LEG.RADIER"],
    "PULMÃO": ["PULMÃO VENDA", "PULMÃO INFRA", "PULMÃO RADIER"],
    "ENGENHARIA": ["PL.LIMP", "ENG. LIMP.", "PL.TER.", "ENG. TER.", "PL.INFRA", "ENG. INFRA", "ENG. PAV", "PE. LIMP.", "ORÇ. LIMP.", "SUP. LIMP.",
     "PE. TER.", "ORÇ. TER.", "SUP. TER.", "PE. INFRA", "ORÇ. INFRA", "SUP. INFRA", "PE. PAV", "ORÇ. PAV", "SUP. PAV", "PE. ÁREAS COMUNS (ENG)", "ORÇ. ÁREAS COMUNS", "SUP. ÁREAS COMUNS"],
    "INFRA": ["EXECUÇÃO LIMP.", "EXECUÇÃO TER.", "EXECUÇÃO INFRA", "EXECUÇÃO PAV.", "EXECUÇÃO ÁREAS COMUNS"],
    "PRODUÇÃO": ["RADIER"],
    "ARQUITETURA & URBANISMO": ["PL.RADIER", "PE. ÁREAS COMUNS (URB)"],
    "VENDA": ["DEMANDA MÍNIMA"],
}

# --- Mapeamentos e Padronização ---
mapeamento_etapas_usuario = {
    "PROSPECÇÃO": "PROSPEC", "LEGALIZAÇÃO PARA VENDA": "LEGVENDA", "PULMÃO VENDA": "PULVENDA",
    "PL.LIMP": "PL.LIMP", "LEG.LIMP": "LEG.LIMP", "ENG. LIMP.": "ENG.LIMP",
    "EXECUÇÃO LIMP.": "EXECLIMP", "PL.TER.": "PL.TER", "LEG.TER.": "LEG.TER",
    "ENG. TER.": "ENG. TER", "EXECUÇÃO TER.": "EXECTER", "PL.INFRA": "PL.INFRA",
    "LEG.INFRA": "LEG.INFRA", "ENG. INFRA": "ENG.INFRA", "EXECUÇÃO INFRA": "EXECINFRA",
    "ENG. PAV": "ENG.PAV", "EXECUÇÃO PAV.": "EXEC.PAV", "PULMÃO INFRA": "PUL.INFRA",
    "PL.RADIER": "PL.RAD", "LEG.RADIER": "LEG.RAD", "PULMÃO RADIER": "PUL.RAD",
    "RADIER": "RAD", "DEMANDA MÍNIMA": "DEM.MIN",
    "PE. LIMP.":"PE. LIMP.", "ORÇ. LIMP.":"ORÇ. LIMP.", "SUP. LIMP.":"SUP. LIMP.", "PE. TER.":"PE. TER.", "ORÇ. TER.":"ORÇ. TER.", "SUP. TER.":"SUP. TER.", "PE. INFRA":"PE. INFRA", 
    "ORÇ. INFRA":"ORÇ. INFRA", "SUP. INFRA":"SUP. INFRA",
    "PE. PAV":"PE. PAV", "ORÇ. PAV":"ORÇ. PAV", "SUP. PAV":"SUP. PAV",
    "PE. ÁREAS COMUNS (ENG)":"PE. ÁREAS COMUNS (ENG)", "PE. ÁREAS COMUNS (URB)":"PE. ÁREAS COMUNS (URB)", "ORÇ. ÁREAS COMUNS":"ORÇ. ÁREAS COMUNS", "SUP. ÁREAS COMUNS":"SUP. ÁREAS COMUNS", "EXECUÇÃO ÁREAS COMUNS":"EXECUÇÃO ÁREAS COMUNS",
}

mapeamento_reverso = {v: k for k, v in mapeamento_etapas_usuario.items()}

sigla_para_nome_completo = {
    "PROSPEC": "PROSPECÇÃO", "LEGVENDA": "LEGALIZAÇÃO PARA VENDA", "PULVENDA": "PULMÃO VENDA",
    "PL.LIMP": "PL.LIMP", "LEG.LIMP": "LEG.LIMP", "ENG.LIMP": "ENG. LIMP.", "EXECLIMP": "EXECUÇÃO LIMP.",
    "PL.TER": "PL.TER.", "LEG.TER": "LEG.TER.", "ENG. TER": "ENG. TER.", "EXECTER": "EXECUÇÃO TER.",
    "PL.INFRA": "PL.INFRA", "LEG.INFRA": "LEG.INFRA", "ENG.INFRA": "ENG. INFRA",
    "EXECINFRA": "EXECUÇÃO INFRA", "LEG.PAV": "LEG.PAV", "ENG.PAV": "ENG. PAV",
    "EXEC.PAV": "EXECUÇÃO PAV.", "PUL.INFRA": "PULMÃO INFRA", "PL.RAD": "PL.RADIER",
    "LEG.RAD": "LEG.RADIER", "PUL.RAD": "PULMÃO RADIER", "RAD": "RADIER", "DEM.MIN": "DEMANDA MÍNIMA",
    "PE. LIMP.":"PE. LIMP.", "ORÇ. LIMP.":"ORÇ. LIMP.", "SUP. LIMP.":"SUP. LIMP.", "PE. TER.":"PE. TER.", "ORÇ. TER.":"ORÇ. TER.", "SUP. TER.":"SUP. TER.", "PE. INFRA":"PE. INFRA", 
    "ORÇ. INFRA":"ORÇ. INFRA", "SUP. INFRA":"SUP. INFRA",
    "PE. ÁREAS COMUNS (ENG)":"PE. ÁREAS COMUNS (ENG)", "PE. ÁREAS COMUNS (URB)":"PE. ÁREAS COMUNS (URB)", "ORÇ. ÁREAS COMUNS":"ORÇ. ÁREAS COMUNS", "SUP. ÁREAS COMUNS":"SUP. ÁREAS COMUNS", "EXECUÇÃO ÁREAS COMUNS":"EXECUÇÃO ÁREAS COMUNS",
    "PE. PAV":"PE. PAV", "ORÇ. PAV":"ORÇ. PAV", "SUP. PAV":"SUP. PAV"
}

SUBETAPAS = {
    "ENG. LIMP.": ["PE. LIMP.", "ORÇ. LIMP.", "SUP. LIMP."],
    "ENG. TER.": ["PE. TER.", "ORÇ. TER.", "SUP. TER."],
    "ENG. INFRA": ["PE. INFRA", "ORÇ. INFRA", "SUP. INFRA"],
    "ENG. PAV": ["PE. PAV", "ORÇ. PAV", "SUP. PAV"]
}

# Mapeamento reverso para encontrar a etapa pai a partir da subetapa
ETAPA_PAI_POR_SUBETAPA = {}
for etapa_pai, subetapas in SUBETAPAS.items():
    for subetapa in subetapas:
        ETAPA_PAI_POR_SUBETAPA[subetapa] = etapa_pai

ORDEM_ETAPAS_NOME_COMPLETO = [sigla_para_nome_completo.get(s, s) for s in ORDEM_ETAPAS_GLOBAL]
nome_completo_para_sigla = {v: k for k, v in sigla_para_nome_completo.items()}

GRUPO_POR_ETAPA = {}
for grupo, etapas in GRUPOS.items():
    for etapa in etapas:
        GRUPO_POR_ETAPA[etapa] = grupo

SETOR_POR_ETAPA = {mapeamento_etapas_usuario.get(etapa, etapa): setor for setor, etapas in SETOR.items() for etapa in etapas}


# --- Configurações de Estilo ---
class StyleConfig:
    CORES_POR_SETOR = {
        "PROSPECÇÃO": {"previsto": "#FEEFC4", "real": "#AE8141"},
        "LEGALIZAÇÃO": {"previsto": "#fadbfe", "real": "#BF08D3"},
        "PULMÃO": {"previsto": "#E9E8E8", "real": "#535252"},
        "ENGENHARIA": {"previsto": "#fbe3cf", "real": "#be5900"},
        "INFRA": {"previsto": "#daebfb", "real": "#125287"},
        "PRODUÇÃO": {"previsto": "#E1DFDF", "real": "#252424"},
        "ARQUITETURA & URBANISMO": {"previsto": "#D4D3F9", "real": "#453ECC"},
        "VENDA": {"previsto": "#dffde1", "real": "#096710"},
        "Não especificado": {"previsto": "#ffffff", "real": "#FFFFFF"}
    }

    @classmethod
    def set_offset_variacao_termino(cls, novo_offset):
        cls.OFFSET_VARIACAO_TERMINO = novo_offset


# --- Funções de Banco de Dados (VERSÃO ROBUSTA AWS) ---

def get_db_connection():
    if not DB_CONFIG: return None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"❌ Erro de Conexão MySQL: {e}") # Log no terminal
        return None

def create_baselines_table():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Cria tabela garantindo coluna tipo_visualizacao
            create_table_query = """
            CREATE TABLE IF NOT EXISTS gantt_baselines (
                id INT AUTO_INCREMENT PRIMARY KEY,
                empreendimento VARCHAR(255) NOT NULL,
                version_name VARCHAR(255) NOT NULL,
                baseline_data JSON NOT NULL,
                created_date VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tipo_visualizacao VARCHAR(50) DEFAULT 'Gantt',
                UNIQUE KEY unique_baseline (empreendimento, version_name)
            )
            """
            cursor.execute(create_table_query)
            conn.commit()
        except Error as e:
            print(f"Erro tabela: {e}")
        finally:
            conn.close()

def save_baseline(empreendimento, version_name, baseline_data, created_date, tipo_visualizacao="Gantt"):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            baseline_json = json.dumps(baseline_data, ensure_ascii=False, default=str)
            
            # Query robusta com ON DUPLICATE KEY UPDATE
            insert_query = """
            INSERT INTO gantt_baselines (empreendimento, version_name, baseline_data, created_date, tipo_visualizacao)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                baseline_data = VALUES(baseline_data), 
                created_date = VALUES(created_date),
                created_at = CURRENT_TIMESTAMP
            """
            cursor.execute(insert_query, (empreendimento, version_name, baseline_json, created_date, tipo_visualizacao))
            conn.commit()
            print(f"✅ SAVE AWS SUCESSO: {version_name}")
            return True
        except Error as e:
            print(f"❌ ERRO SQL AWS: {e}")
            return False
        finally:
            conn.close()
    else:
        print("❌ FALHA CONEXÃO: Não foi possível conectar para salvar.")
        return False
    
def take_baseline(df, empreendimento):
    # 1. Filtra o DataFrame atual
    df_emp = df[df['Empreendimento'] == empreendimento].copy()

    # 2. Define o nome da nova versão (ex: P1, P2...)
    # (Adicione aqui a lógica de contagem de versões existente no exemplo)
    version_name = "P_NOVA" # Exemplo simplificado

    # 3. Prepara os dados para salvar (Snapshot)
    # Aqui você define o que quer salvar. No exemplo, ele salva Inicio/Fim.
    baseline_data = []
    for _, row in df_emp.iterrows():
        baseline_data.append({
            "tarefa": row['Etapa'], # Ou o ID da tarefa se tiver
            "inicio_previsto": row['Inicio_Real'].strftime('%Y-%m-%d') if pd.notna(row['Inicio_Real']) else None,
            "termino_previsto": row['Termino_Real'].strftime('%Y-%m-%d') if pd.notna(row['Termino_Real']) else None
        })

    # 4. Salva no banco
    save_baseline(empreendimento, version_name, baseline_data, datetime.now().strftime("%d/%m/%Y"))
    return version_name

def process_baseline_change():
    """
    Processa mudanças de baseline via query parameters.
    """
    query_params = st.query_params
    
    # Verificar se é um pedido para LIMPAR baseline
    if 'clear_baseline' in query_params:
        st.query_params.clear()
        st.session_state.current_baseline = None
        st.session_state.current_baseline_data = None
        st.session_state.current_empreendimento = None
        st.rerun()
        return
    
    # Usar 'baseline_target' ao invés de 'empreendimento' para evitar conflito com filtros
    if 'change_baseline' in query_params and 'baseline_target' in query_params:
        baseline_name = query_params['change_baseline']
        empreendimento = query_params['baseline_target']
        
        # Limpar os parâmetros IMEDIATAMENTE
        st.query_params.clear()
        
        if baseline_name == 'P0-(padrão)':
            # Limpar baseline apenas se for do mesmo empreendimento
            current_emp = st.session_state.get('current_empreendimento')
            if current_emp == empreendimento:
                st.session_state.current_baseline = None
                st.session_state.current_baseline_data = None
                st.session_state.current_empreendimento = None
                st.rerun()
        else:
            # Carregar baseline selecionada
            baseline_data = get_baseline_data(empreendimento, baseline_name)
            if baseline_data:
                st.session_state.current_baseline = baseline_name
                st.session_state.current_baseline_data = baseline_data
                st.session_state.current_empreendimento = empreendimento
                st.rerun()

def aplicar_baseline_automaticamente(empreendimento):
    """
    Callback chamado automaticamente quando usuário troca a baseline no dropdown.
    Aplica a baseline selecionada sem necessidade de clicar em botão.
    """
    selected_baseline = st.session_state.get('quick_baseline_select', 'P0-(padrão)')
    
    if selected_baseline == "P0-(padrão)":
        # Voltar ao padrão (sem baseline)
        st.session_state.current_baseline = None
        st.session_state.current_baseline_data = None
        st.session_state.current_empreendimento = None
    else:
        # Carregar baseline selecionada
        baseline_data = get_baseline_data(empreendimento, selected_baseline)
        if baseline_data:
            st.session_state.current_baseline = selected_baseline
            st.session_state.current_baseline_data = baseline_data
            st.session_state.current_empreendimento = empreendimento
        else:
            # Se não encontrar, voltar para padrão
            st.session_state.current_baseline = None
            st.session_state.current_baseline_data = None
            st.session_state.current_empreendimento = None
            

# --- Processar Ações (ADAPTADO DO SEU EXEMPLO) ---
def process_context_menu_actions(df=None):
    query_params = st.query_params
    
    if 'context_action' in query_params and query_params['context_action'] == 'take_baseline':
        # 1. Decodifica parâmetros
        raw_emp = query_params.get('empreendimento', None)
        empreendimento = urllib.parse.unquote(raw_emp) if raw_emp else None
        
        print(f"🔔 BACKEND: Recebido comando para '{empreendimento}'")

        # 2. Garantia de Dados (Pois o iframe é uma sessão nova)
        if df is None or df.empty:
            print("⚠️ Sessão Iframe. Carregando dados...")
            try:
                df = load_data() # Sua função de carregar Excel/SQL
            except Exception as e:
                print(f"❌ Erro load_data: {e}")
                return

        # 3. Executa Salvamento
        if empreendimento and df is not None:
            try:
                # Cria a baseline (usa sua função take_gantt_baseline existente)
                version_name = take_gantt_baseline(df, empreendimento, "Gantt")
                print(f"✅ FINALIZADO: {version_name} criado.")
                # Limpa URL
                st.query_params.clear()
            except Exception as e:
                print(f"❌ Erro take_gantt_baseline: {e}")

        # 4. Executa a criação
        if empreendimento and df is not None and not df.empty:
            try:
                # Cria e Salva no MySQL
                version_name = take_gantt_baseline(df, empreendimento, "Gantt")
                print(f"✅ SUCESSO: Baseline '{version_name}' salva no banco!")
                
                # Limpa params para não repetir na próxima carga
                st.query_params.clear()
                
            except Exception as e:
                print(f"❌ Erro ao salvar baseline: {e}")
        else:
            print(f"❌ Erro: Empreendimento não encontrado ou dados vazios.")

# --- Funções do Novo Gráfico Gantt ---
def ajustar_datas_com_pulmao(df, meses_pulmao=0):
    df_copy = df.copy()
    if meses_pulmao > 0:
        for i, row in df_copy.iterrows():
            if "PULMÃO" in row["Etapa"].upper(): # Identifica etapas de pulmão
                # Ajusta APENAS datas PREVISTAS do pulmão
                if pd.notna(row["Termino_Prevista"]):
                    df_copy.loc[i, "Termino_Prevista"] = row["Termino_Prevista"] + relativedelta(months=meses_pulmao)
                # DATAS REAIS PERMANECEM INALTERADAS
            else:
                # Para outras etapas, ajusta APENAS datas PREVISTAS
                if pd.notna(row["Inicio_Prevista"]):
                    df_copy.loc[i, "Inicio_Prevista"] = row["Inicio_Prevista"] + relativedelta(months=meses_pulmao)
                if pd.notna(row["Termino_Prevista"]):
                    df_copy.loc[i, "Termino_Prevista"] = row["Termino_Prevista"] + relativedelta(months=meses_pulmao)
                # DATAS REAIS PERMANECEM INALTERADAS
    return df_copy

def calcular_periodo_datas(df, meses_padding_inicio=1, meses_padding_fim=36):
    if df.empty:
        hoje = datetime.now()
        data_min_default = (hoje - relativedelta(months=2)).replace(day=1)
        data_max_default = (hoje + relativedelta(months=4))
        data_max_default = (data_max_default.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)
        return data_min_default, data_max_default

    datas = []
    colunas_data = ["Inicio_Prevista", "Termino_Prevista", "Inicio_Real", "Termino_Real"]
    for col in colunas_data:
        if col in df.columns:
            datas_validas = pd.to_datetime(df[col], errors='coerce').dropna()
            datas.extend(datas_validas.tolist())

    if not datas:
        return calcular_periodo_datas(pd.DataFrame())

    data_min_real = min(datas)
    data_max_real = max(datas)

    data_inicio_final = (data_min_real - relativedelta(months=meses_padding_inicio)).replace(day=1)
    data_fim_temp = data_max_real + relativedelta(months=meses_padding_fim)
    data_fim_final = (data_fim_temp.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)

    return data_inicio_final, data_fim_final

def calcular_dias_uteis_novo(data_inicio, data_fim):
    if pd.isna(data_inicio) or pd.isna(data_fim):
        return None

    data_inicio = pd.to_datetime(data_inicio).normalize()
    data_fim = pd.to_datetime(data_fim).normalize()

    sinal = 1
    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio
        sinal = -1

    return np.busday_count(data_inicio.date(), data_fim.date()) * sinal

def obter_data_meta_assinatura_novo(df_empreendimento):
    df_meta = df_empreendimento[df_empreendimento["Etapa"] == "DEMANDA MÍNIMA"]
    if df_meta.empty:
        return None
    for col in ["Inicio_Prevista", "Inicio_Real", "Termino_Prevista", "Termino_Real"]:
        if col in df_meta.columns and pd.notna(df_meta[col].iloc[0]):
            return pd.to_datetime(df_meta[col].iloc[0])
    return None


# --- FUNÇÕES DE BANCO DE DADOS PARA BASELINES ---

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        return None

def create_baselines_table():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            create_table_query = """
            CREATE TABLE IF NOT EXISTS gantt_baselines (
                id INT AUTO_INCREMENT PRIMARY KEY,
                empreendimento VARCHAR(255) NOT NULL,
                version_name VARCHAR(255) NOT NULL,
                baseline_data JSON NOT NULL,
                created_date VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tipo_visualizacao VARCHAR(50) NOT NULL,
                UNIQUE KEY unique_baseline (empreendimento, version_name)
            )
            """
            cursor.execute(create_table_query)
            conn.commit()
        except Error as e:
            st.error(f"Erro ao criar tabela: {e}")
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        if 'mock_baselines' not in st.session_state:
            st.session_state.mock_baselines = {}

@st.cache_resource(ttl=3600) # Cache por 1 hora, ou até ser invalidado
def load_baselines():
    return _fetch_baselines_from_db()

def _fetch_baselines_from_db():
    conn = get_db_connection()
    if conn:
        baselines = {}
        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT empreendimento, version_name, baseline_data, created_date, tipo_visualizacao FROM gantt_baselines ORDER BY created_at DESC"
            cursor.execute(query)
            results = cursor.fetchall()
            
            # DEBUG
            print(f"DEBUG load_baselines: {len(results)} registros encontrados no banco")
            
            for row in results:
                empreendimento = row['empreendimento']
                version_name = row['version_name']
                
                print(f"DEBUG: Carregando baseline - Empreendimento: {empreendimento}, Versão: {version_name}")
                
                if empreendimento not in baselines:
                    baselines[empreendimento] = {}
                
                try:
                    baseline_data = json.loads(row['baseline_data'])
                    baselines[empreendimento][version_name] = {
                        "date": row['created_date'],
                        "data": baseline_data,
                        "tipo_visualizacao": row['tipo_visualizacao']
                    }
                except Exception as e:
                    print(f"DEBUG: Erro ao carregar baseline {version_name}: {e}")
                    continue
                    
            return baselines
        except Error as e:
            print(f"DEBUG: Erro no banco: {e}")
            return {}
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        print("DEBUG: Usando mock_baselines")
        return st.session_state.get('mock_baselines', {})

def converter_df_para_baseline_format(df):
    """
    Converte DataFrame agregado para formato de baseline JSON.
    Retorna lista de dicionários com etapa e datas previstas.
    """
    baseline_tasks = []
    
    for _, row in df.iterrows():
        # Obter datas previstas
        inicio_prev = row.get('Inicio_Prevista')
        termino_prev = row.get('Termino_Prevista')
        
        task = {
            'etapa': row['Etapa'],
            'inicio_previsto': inicio_prev.strftime('%Y-%m-%d') if pd.notna(inicio_prev) else None,
            'termino_previsto': termino_prev.strftime('%Y-%m-%d') if pd.notna(termino_prev) else None
        }
        baseline_tasks.append(task)
    
    return baseline_tasks


def save_baseline(empreendimento, version_name, baseline_data, created_date, tipo_visualizacao):
    # Invalida o cache antes de salvar para garantir que a próxima leitura pegue o novo dado
    load_baselines.clear()
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Validar dados antes de serializar
            if not baseline_data or not isinstance(baseline_data, dict):
                raise ValueError("Dados da baseline inválidos")
            
            # Serializar com tratamento de caracteres especiais
            baseline_json = json.dumps(baseline_data, ensure_ascii=False, default=str)
            
            insert_query = """
            INSERT INTO gantt_baselines (empreendimento, version_name, baseline_data, created_date, tipo_visualizacao)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                baseline_data = VALUES(baseline_data), 
                created_date = VALUES(created_date), 
                tipo_visualizacao = VALUES(tipo_visualizacao),
                created_at = CURRENT_TIMESTAMP
            """
            
            cursor.execute(insert_query, (empreendimento, version_name, baseline_json, created_date, tipo_visualizacao))
            conn.commit()
            
            # Verificar se a inserção foi bem-sucedida
            if cursor.rowcount > 0:
                return True
            else:
                return False
                
        except Error as e:
            st.error(f"Erro de banco de dados ao salvar baseline: {e}")
            return False
        except Exception as e:
            st.error(f"Erro inesperado ao salvar baseline: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        # Fallback para dados mock
        if 'mock_baselines' not in st.session_state:
            st.session_state.mock_baselines = {}
        
        if empreendimento not in st.session_state.mock_baselines:
            st.session_state.mock_baselines[empreendimento] = {}
        
        st.session_state.mock_baselines[empreendimento][version_name] = {
            "date": created_date,
            "data": baseline_data,
            "tipo_visualizacao": tipo_visualizacao
        }
        return True

def delete_baseline(empreendimento, version_name):
    """Deleta uma baseline do banco de dados"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            delete_query = "DELETE FROM gantt_baselines WHERE empreendimento = %s AND version_name = %s"
            cursor.execute(delete_query, (empreendimento, version_name))
            conn.commit()
            
            if cursor.rowcount > 0:
                print(f"✅ Baseline {version_name} excluída com sucesso")
                return True
            else:
                print(f"⚠️ Baseline {version_name} não encontrada no banco")
                return False
                
        except Error as e:
            print(f"❌ Erro SQL ao excluir baseline: {e}")
            st.error(f"Erro de banco de dados: {e}")
            return False
        except Exception as e:
            print(f"❌ Erro inesperado ao excluir baseline: {e}")
            st.error(f"Erro inesperado: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        # Fallback para modo mock (sem banco de dados)
        if 'mock_baselines' in st.session_state:
            if empreendimento in st.session_state.mock_baselines:
                if version_name in st.session_state.mock_baselines[empreendimento]:
                    del st.session_state.mock_baselines[empreendimento][version_name]
                    print(f"✅ Baseline {version_name} excluída do mock")
                    return True
        
        st.error("Erro: Não foi possível conectar ao banco de dados")
        return False

# --- CÓDIGO MODIFICADO ---
def converter_dados_para_gantt(df):
    if df.empty:
        return []

    gantt_data = []

    for empreendimento in df["Empreendimento"].unique():
        df_emp = df[df["Empreendimento"] == empreendimento].copy()

        # DEBUG: Verificar etapas disponíveis
        etapas_disponiveis = df_emp["Etapa"].unique()
        # print(f"=== ETAPAS PARA {empreendimento} ===")
        for etapa in etapas_disponiveis:
            # print(f"Etapa no DF: {etapa}")

        # --- NOVA LÓGICA: Calcular datas reais para etapas pai a partir das subetapas ---
            etapas_pai_para_calcular = {}
        for etapa_pai, subetapas in SUBETAPAS.items():
            subetapas_emp = df_emp[df_emp["Etapa"].isin([nome_completo_para_sigla.get(sub, sub) for sub in subetapas])]
            
            if not subetapas_emp.empty:
                inicio_real_min = subetapas_emp["Inicio_Real"].min()
                termino_real_max = subetapas_emp["Termino_Real"].max()
                
                etapas_pai_para_calcular[etapa_pai] = {
                    "inicio_real": inicio_real_min,
                    "termino_real": termino_real_max
                }

        tasks = []
        df_emp['Etapa'] = pd.Categorical(df_emp['Etapa'], categories=ORDEM_ETAPAS_NOME_COMPLETO, ordered=True)
        df_emp_sorted = df_emp.sort_values(by='Etapa').reset_index()

        for i, (idx, row) in enumerate(df_emp_sorted.iterrows()):
            start_date = row.get("Inicio_Prevista")
            end_date = row.get("Termino_Prevista")
            start_real = row.get("Inicio_Real")
            end_real_original = row.get("Termino_Real")
            progress = row.get("% concluído", 0)

            etapa_sigla = row.get("Etapa", "UNKNOWN")
            etapa_nome_completo = sigla_para_nome_completo.get(etapa_sigla, etapa_sigla)

            # --- VERIFICAR SE É UMA ETAPA PAI E TEM DATAS CALCULADAS DAS SUBETAPAS ---
            if etapa_nome_completo in etapas_pai_para_calcular:
                dados_pai = etapas_pai_para_calcular[etapa_nome_completo]
                
                if pd.notna(dados_pai["inicio_real"]):
                    start_real = dados_pai["inicio_real"]
                if pd.notna(dados_pai["termino_real"]):
                    end_real_original = dados_pai["termino_real"]
                
                subetapas_emp = df_emp[df_emp["Etapa"].isin([nome_completo_para_sigla.get(sub, sub) for sub in SUBETAPAS[etapa_nome_completo]])]
                if not subetapas_emp.empty and "% concluído" in subetapas_emp.columns:
                    progress_subetapas = subetapas_emp["% concluído"].apply(converter_porcentagem)
                    progress = progress_subetapas.mean()

            # Verificar se é subetapa (para skip se não tiver dados reais)
            etapa_eh_subetapa = etapa_nome_completo in ETAPA_PAI_POR_SUBETAPA
            
            # NOVA LÓGICA: No modo padrão (sem baseline), subetapas não mostram barras previstas
            # Apenas quando uma baseline está aplicada é que as subetapas mostram as barras
            baseline_ativa = st.session_state.get('current_baseline') is not None
            
            if etapa_eh_subetapa and not baseline_ativa:
                # Modo padrão (P0): subetapas não têm barras previstas
                start_date = None
                end_date = None
            
            # REMOVIDO: O código que zerava start_date e end_date para subetapas
            # Isso quebrava a baseline porque as datas previstas são necessárias
            # para mostrar o snapshot da baseline
            
            # Skip apenas se subetapa NÃO tem dados reais E não está em uma baseline
            if etapa_eh_subetapa:
                if pd.isna(start_real) and pd.isna(end_real_original):
                    # Se não tem dados reais e não tem previstos também, skip
                    if pd.isna(start_date) and pd.isna(end_date):
                        continue

            # Lógica para tratar datas vazias (apenas para etapas que não são subetapas)
            # IMPORTANTE: Se AMBAS as datas previstas estão vazias, não criar datas padrão
            # Isso permite que etapas não presentes em uma baseline apareçam como linhas vazias
            if not etapa_eh_subetapa:
                # Só criar datas padrão se pelo menos UMA das datas previstas existir
                if pd.notna(start_date) or pd.notna(end_date):
                    if pd.isna(start_date) or start_date is None: 
                        start_date = datetime.now()
                    if pd.isna(end_date) or end_date is None: 
                        end_date = start_date + timedelta(days=30)

            end_real_visual = end_real_original
            if pd.notna(start_real) and progress < 100 and pd.isna(end_real_original):
                end_real_visual = datetime.now()

            # --- CORREÇÃO DO MAPEAMENTO DE GRUPO - LÓGICA MELHORADA ---
            grupo = "Não especificado"
            
            # Tenta pelo nome completo primeiro
            if etapa_nome_completo in GRUPO_POR_ETAPA:
                grupo = GRUPO_POR_ETAPA[etapa_nome_completo]
            # Se não encontrar, tenta pela sigla
            elif etapa_sigla in GRUPO_POR_ETAPA:
                grupo = GRUPO_POR_ETAPA[etapa_sigla]
            
            # DEBUG: Mostrar mapeamento
            # print(f"Etapa: {etapa_nome_completo} (sigla: {etapa_sigla}) -> Grupo: {grupo}")

            # Duração em Meses
            dur_prev_meses = None
            if pd.notna(start_date) and pd.notna(end_date):
                dur_prev_meses = (end_date - start_date).days / 30.4375

            dur_real_meses = None
            if pd.notna(start_real) and pd.notna(end_real_original):
                dur_real_meses = (end_real_original - start_real).days / 30.4375

            # Variação de Término (VT) - em dias úteis
            vt = calculate_business_days(end_date, end_real_original)

            # Duração em dias úteis
            duracao_prevista_uteis = calculate_business_days(start_date, end_date)
            duracao_real_uteis = calculate_business_days(start_real, end_real_original)

            # Variação de Duração (VD) - em dias úteis
            vd = None
            if pd.notna(duracao_real_uteis) and pd.notna(duracao_prevista_uteis):
                vd = duracao_real_uteis - duracao_prevista_uteis

            # Lógica de Cor do Status
            status_color_class = 'status-default'
            hoje = pd.Timestamp.now().normalize()

            if progress == 100:
                if pd.notna(end_real_original) and pd.notna(end_date):
                    if end_real_original <= end_date:
                        status_color_class = 'status-green'
                    else:
                        status_color_class = 'status-red'
            elif progress < 100 and pd.notna(start_real) and pd.notna(end_real_original) and (end_real_original < hoje):
                status_color_class = 'status-yellow'  # Em andamento, mas data real já passou

            # --- CORREÇÃO: Buscar UGB do DataFrame original, não do row ---
            # O row pode não ter a coluna UGB após todas as transformações
            # Buscar UGB do empreendimento no DataFrame original
            ugb_value = "N/D"
            if "UGB" in df_emp.columns:
                # Pegar a primeira UGB não-nula do empreendimento
                ugb_series = df_emp["UGB"].dropna()
                if not ugb_series.empty:
                    ugb_value = str(ugb_series.iloc[0])
            
            task = {
                "id": f"t{i}", "name": etapa_nome_completo, "numero_etapa": i + 1,
                "start_previsto": start_date.strftime("%Y-%m-%d") if pd.notna(start_date) and start_date is not None else None,
                "end_previsto": end_date.strftime("%Y-%m-%d") if pd.notna(end_date) and end_date is not None else None,
                "start_real": pd.to_datetime(start_real).strftime("%Y-%m-%d") if pd.notna(start_real) else None,
                "end_real": pd.to_datetime(end_real_visual).strftime("%Y-%m-%d") if pd.notna(end_real_visual) else None,
                "end_real_original_raw": pd.to_datetime(end_real_original).strftime("%Y-%m-%d") if pd.notna(end_real_original) else None,
                "ugb": ugb_value,
                "setor": row.get("SETOR", "Não especificado"),
                "grupo": grupo,
                "progress": int(progress),
                "inicio_previsto": start_date.strftime("%d/%m/%y") if pd.notna(start_date) and start_date is not None else "N/D",
                "termino_previsto": end_date.strftime("%d/%m/%y") if pd.notna(end_date) and end_date is not None else "N/D",
                "inicio_real": pd.to_datetime(start_real).strftime("%d/%m/%y") if pd.notna(start_real) else "N/D",
                "termino_real": pd.to_datetime(end_real_original).strftime("%d/%m/%y") if pd.notna(end_real_original) else "N/D",
                "duracao_prev_meses": f"{dur_prev_meses:.1f}".replace('.', ',') if dur_prev_meses is not None else "-",
                "duracao_real_meses": f"{dur_real_meses:.1f}".replace('.', ',') if dur_real_meses is not None else "-",

                "vt_text": f"{int(vt):+d}d" if pd.notna(vt) else "-",
                "vd_text": f"{int(vd):+d}d" if pd.notna(vd) else "-",

                "status_color_class": status_color_class,
                
                # *** NOVO: Campo para baselines locais (client-side switching) ***
                "baselines": {}  # Será populado após criar todas tasks do empreendimento
            }
            tasks.append(task)

        # *** POPULAR BASELINES LOCAIS EM CADA TASK ***
        # Carregar todas as baselines disponíveis para este empreendimento
        try:
            all_baselines_dict = load_baselines()  # Carrega do MySQL
            
            # P0 = dados atuais (padrão)
            for task in tasks:
                task["baselines"]["P0-(padrão)"] = {
                    "start": task["start_previsto"],
                    "end": task["end_previsto"]
                }
            
            # Adicionar outras baselines se existirem
            if empreendimento in all_baselines_dict:
                baselines_emp = all_baselines_dict[empreendimento]
                
                for baseline_name, baseline_info in baselines_emp.items():
                    baseline_data = get_baseline_data(empreendimento, baseline_name)
                    
                    if baseline_data:
                        if isinstance(baseline_data, dict) and 'tasks' in baseline_data:
                            baseline_tasks = baseline_data['tasks']
                        elif isinstance(baseline_data, list):
                            baseline_tasks = baseline_data
                        else:
                            baseline_tasks = []
                        
                        # Matching de etapas com baselines
                        for task in tasks:
                            task_name = task["name"]
                            baseline_task = None
                            
                            # Tentar nome exato
                            baseline_task = next(
                                (bt for bt in baseline_tasks if bt.get('etapa') == task_name or bt.get('Etapa') == task_name),
                                None
                            )
                            
                            # Tentar mapeamento reverso (nome completo → sigla)
                            if not baseline_task and task_name in mapeamento_etapas_usuario:
                                sigla = mapeamento_etapas_usuario[task_name]
                                baseline_task = next(
                                    (bt for bt in baseline_tasks if bt.get('etapa') == sigla or bt.get('Etapa') == sigla),
                                    None
                                )
                            
                            # Tentar mapeamento direto (sigla → nome completo)
                            if not baseline_task and task_name in mapeamento_reverso:
                                nome_completo = mapeamento_reverso[task_name]
                                baseline_task = next(
                                    (bt for bt in baseline_tasks if bt.get('etapa') == nome_completo or bt.get('Etapa') == nome_completo),
                                    None
                                )
                            
                            # Tentar sigla_para_nome_completo
                            if not baseline_task and task_name in sigla_para_nome_completo:
                                nome_alt = sigla_para_nome_completo[task_name]
                                baseline_task = next(
                                    (bt for bt in baseline_tasks if bt.get('etapa') == nome_alt or bt.get('Etapa') == nome_alt),
                                    None
                                )
                            
                            # Tentar normalizado (fallback)
                            if not baseline_task:
                                task_name_norm = task_name.strip().upper()
                                baseline_task = next(
                                    (bt for bt in baseline_tasks 
                                     if (bt.get('etapa', '').strip().upper() == task_name_norm or 
                                         bt.get('Etapa', '').strip().upper() == task_name_norm)),
                                    None
                                )
                            
                            if baseline_task:
                                task["baselines"][baseline_name] = {
                                    "start": baseline_task.get('inicio_previsto', baseline_task.get('Inicio_Prevista')),
                                    "end": baseline_task.get('termino_previsto', baseline_task.get('Termino_Prevista'))
                                }
                            else:
                                # CORREÇÃO: Marcar explicitamente que esta tarefa não existe nesta baseline
                                # Isso permite que o JavaScript diferencie "sem dados" de "não processado"
                                task["baselines"][baseline_name] = {
                                    "start": None,
                                    "end": None
                                }
        except Exception as e:
            print(f"Erro ao popular baselines locais: {e}")
            # Se falhar, pelo menos P0 já foi adicionado

        data_meta = obter_data_meta_assinatura_novo(df_emp)

        project = {
            "id": f"p{len(gantt_data)}", "name": empreendimento,
            "tasks": tasks,
            "meta_assinatura_date": data_meta.strftime("%Y-%m-%d") if data_meta else None
        }
        gantt_data.append(project)

    return gantt_data

# --- FUNÇÕES DE BASELINE DO GANTT ---

def take_gantt_baseline(df, empreendimento, tipo_visualizacao, created_by=None):
    """Cria uma linha de base do estado atual do Gantt"""
    
    try:
        # Se não foi fornecido created_by, tentar capturar automaticamente
        if not created_by:
            import os
            import getpass
            try:
                created_by = getpass.getuser()
            except:
                created_by = os.environ.get('USERNAME', 'Não informado')
        
        # Filtrar dados do empreendimento
        df_empreendimento = df[df['Empreendimento'] == empreendimento].copy()
        
        if df_empreendimento.empty:
            st.error(f"Nenhum dado encontrado para o empreendimento: {empreendimento}")
            raise Exception("Nenhum dado encontrado para o empreendimento selecionado")
        
        # Preparar dados para baseline com validação
        baseline_data = {
            'empreendimento': empreendimento,
            'tipo_visualizacao': tipo_visualizacao,
            'data_criacao': datetime.now().strftime("%d/%m/%Y %H:%M"),
            'created_by': created_by,  # Email ou username do criador
            'total_tasks': 0,  # Será atualizado dinamicamente com apenas etapas que têm dados reais
            'tasks': []
        }
        
        # IMPORTANTE: Calcular datas REAIS para etapas pai a partir das subetapas
        # Isso garante que as baselines capturem as datas reais calculadas das etapas pai
        etapas_pai_datas_calculadas = {}
        for etapa_pai, subetapas in SUBETAPAS.items():
            # Converter nomes completos para siglas
            subetapas_siglas = [nome_completo_para_sigla.get(sub, sub) for sub in subetapas]
            subetapas_df = df_empreendimento[df_empreendimento['Etapa'].isin(subetapas_siglas)]
            
            if not subetapas_df.empty:
                # Calcular datas reais mínima/máxima das subetapas
                inicio_real_min = subetapas_df['Inicio_Real'].min()
                termino_real_max = subetapas_df['Termino_Real'].max()
                
                # Guardar para usar no loop de criação de tasks
                etapa_pai_sigla = nome_completo_para_sigla.get(etapa_pai, etapa_pai)
                etapas_pai_datas_calculadas[etapa_pai_sigla] = {
                    'inicio_real': inicio_real_min,
                    'termino_real': termino_real_max
                }
        
        # Converter tasks para formato serializável com validação
        task_count = 0
        for _, row in df_empreendimento.iterrows():
            try:
                task = {
                    'etapa': row.get('Etapa', ''),
                    'etapa_nome_completo': sigla_para_nome_completo.get(row.get('Etapa', ''), row.get('Etapa', '')),
                    'inicio_previsto': None,
                    'termino_previsto': None,
                    'inicio_real': None,
                    'termino_real': None,
                    'percentual_concluido': row.get('% concluído', 0),
                    'setor': row.get('SETOR', ''),
                    'grupo': row.get('GRUPO', ''),
                    'ugb': row.get('UGB', '')
                }
                
                # Converter datas para string com tratamento seguro
                date_fields = {
                    # O Planejado da Baseline (P1, P2...) será o Real atual (requisito do usuário)
                    # MAS se Real não existir, usa Prevista como fallback
                    'inicio_previsto': 'Inicio_Real',
                    'termino_previsto': 'Termino_Real', 
                    'inicio_real': 'Inicio_Real',
                    'termino_real': 'Termino_Real'
                }
                
                for task_field, df_field in date_fields.items():
                    date_val = row.get(df_field)
                    if date_val is not None and pd.notna(date_val):
                        if hasattr(date_val, 'strftime'):
                            task[task_field] = date_val.strftime("%Y-%m-%d")
                        else:
                            # Tentar converter para datetime se não for
                            try:
                                parsed_date = pd.to_datetime(date_val)
                                task[task_field] = parsed_date.strftime("%Y-%m-%d")
                            except:
                                task[task_field] = None
                
                # IMPORTANTE: Para etapas PAI, usar datas REAIS calculadas das subetapas
                etapa_sigla = row.get('Etapa', '')
                if etapa_sigla in etapas_pai_datas_calculadas:
                    datas_calculadas = etapas_pai_datas_calculadas[etapa_sigla]
                    
                    # Usar datas reais calculadas tanto para inicio_previsto quanto inicio_real
                    # (seguindo a lógica: baseline captura o "real" como "previsto")
                    if pd.notna(datas_calculadas['inicio_real']):
                        task['inicio_previsto'] = datas_calculadas['inicio_real'].strftime("%Y-%m-%d")
                        task['inicio_real'] = datas_calculadas['inicio_real'].strftime("%Y-%m-%d")
                    if pd.notna(datas_calculadas['termino_real']):
                        task['termino_previsto'] = datas_calculadas['termino_real'].strftime("%Y-%m-%d")
                        task['termino_real'] = datas_calculadas['termino_real'].strftime("%Y-%m-%d")
                
                # ✅ VERIFICAÇÃO CRÍTICA: Só continuar se tiver dados reais
                # DEVE acontecer ANTES do fallback para Previstas
                has_real_data = (task['inicio_real'] is not None or task['termino_real'] is not None)
                is_parent_with_calculated_data = etapa_sigla in etapas_pai_datas_calculadas
                
                # Se NÃO tem dados reais E NÃO é etapa pai, SKIP (não salva na baseline)
                if not (has_real_data or is_parent_with_calculated_data):
                    # DEBUG: Opcional - descomentar para ver quais etapas foram puladas
                    # print(f"DEBUG: Etapa '{etapa_sigla}' PULADA - sem dados reais")
                    continue  # ← Pula para próxima etapa sem adicionar na baseline
                
                # FALLBACK: Se não tem datas Reais, usar Previstas
                # Isso é importante para etapas que não têm datas próprias E não são pais
                # NOTA: Só chega aqui se a etapa passou na verificação acima
                if task['inicio_previsto'] is None:
                    date_val = row.get('Inicio_Prevista')
                    if date_val is not None and pd.notna(date_val):
                        if hasattr(date_val, 'strftime'):
                            task['inicio_previsto'] = date_val.strftime("%Y-%m-%d")
                        else:
                            try:
                                parsed_date = pd.to_datetime(date_val)
                                task['inicio_previsto'] = parsed_date.strftime("%Y-%m-%d")
                            except:
                                pass
                
                if task['termino_previsto'] is None:
                    date_val = row.get('Termino_Prevista')
                    if date_val is not None and pd.notna(date_val):
                        if hasattr(date_val, 'strftime'):
                            task['termino_previsto'] = date_val.strftime("%Y-%m-%d")
                        else:
                            try:
                                parsed_date = pd.to_datetime(date_val)
                                task['termino_previsto'] = parsed_date.strftime("%Y-%m-%d")
                            except:
                                pass
                
                # Adicionar task (já passou na verificação de dados reais)
                baseline_data['tasks'].append(task)
                task_count += 1
                
            except Exception as task_error:
                st.warning(f"Erro ao processar task {task_count}: {task_error}")
                continue
        
        # Atualizar o total de tasks com o valor real (apenas etapas com dados reais)
        baseline_data['total_tasks'] = task_count
        
        if task_count == 0:
            raise Exception("Nenhuma task válida encontrada para salvar")
        
        # Gerar nome da versão
        existing_baselines = load_baselines()
        empreendimento_baselines = existing_baselines.get(empreendimento, {})
        existing_versions = [k for k in empreendimento_baselines.keys() if k.startswith('P') and k.split('-')[0][1:].isdigit()]
        
        next_n = 1
        if existing_versions:
            max_n = 0
            for version_name in existing_versions:
                try:
                    n_str = version_name.split('-')[0][1:]
                    n = int(n_str)
                    if n > max_n:
                        max_n = n
                except ValueError:
                    continue
            next_n = max_n + 1
        
        version_prefix = f"P{next_n}"
        current_date_str = datetime.now().strftime("%d/%m/%Y")
        version_name = f"{version_prefix}-({current_date_str})"
        
        # Salvar baseline
        success = save_baseline(empreendimento, version_name, baseline_data, current_date_str, tipo_visualizacao)
        
        if success:
            # Marcar como não enviada para AWS
            if 'unsent_baselines' not in st.session_state:
                st.session_state.unsent_baselines = {}
            
            if empreendimento not in st.session_state.unsent_baselines:
                st.session_state.unsent_baselines[empreendimento] = []
            
            if version_name not in st.session_state.unsent_baselines[empreendimento]:
                st.session_state.unsent_baselines[empreendimento].append(version_name)
            
            st.success(f"Linha de base {version_name} salva com sucesso!")
            return version_name
        else:
            raise Exception("Falha ao salvar linha de base no banco de dados")
            
    except Exception as e:
        st.error(f"Erro ao criar linha de base: {e}")
        raise
def debug_baseline_system():
    """Função para debug do sistema de baselines"""
    st.markdown("### 🔧 Debug do Sistema de Baselines")
    
    # Testar conexão com banco
    conn = get_db_connection()
    if conn:
        st.success("✅ Conexão com banco de dados: OK")
        conn.close()
    else:
        st.error("❌ Conexão com banco de dados: FALHA")
    
    # Verificar tabela
    try:
        baselines = load_baselines()
        st.success(f"✅ Tabela de baselines: OK ({len(baselines)} empreendimentos com baselines)")
    except Exception as e:
        st.error(f"❌ Tabela de baselines: FALHA - {e}")
    
    # Verificar session state
    if 'unsent_baselines' in st.session_state:
        st.success(f"✅ Session state: OK ({len(st.session_state.unsent_baselines)} empreendimentos não enviados)")
    else:
        st.error("❌ Session state: FALHA - unsent_baselines não encontrado")

def get_baseline_data(empreendimento, version_name):
    """Carrega os dados específicos de uma baseline"""
    # Usa a função load_baselines que é cacheada
    baselines = load_baselines()
    if empreendimento in baselines and version_name in baselines[empreendimento]:
        return baselines[empreendimento][version_name]['data']
    return None

def apply_baseline_to_dataframe(df, baseline_data):
    """Aplica os dados da baseline ao DataFrame principal"""
    if not baseline_data or 'tasks' not in baseline_data:
        return df
    
    df_baseline = df.copy()
    
    # Criar conjunto de etapas que estão na baseline
    etapas_na_baseline = set()
    for task in baseline_data['tasks']:
        etapas_na_baseline.add(task['etapa'])
    
    # Para etapas do empreendimento da baseline que NÃO estão na baseline,
    # limpar as datas previstas para aparecerem como linhas vazias
    mask_empreendimento = df_baseline['Empreendimento'] == baseline_data['empreendimento']
    for idx, row in df_baseline[mask_empreendimento].iterrows():
        etapa = row['Etapa']
        if etapa not in etapas_na_baseline:
            # Etapa não está na baseline - limpar datas previstas
            df_baseline.loc[idx, 'Inicio_Prevista'] = pd.NaT
            df_baseline.loc[idx, 'Termino_Prevista'] = pd.NaT
    
    # Para cada task na baseline, atualizar as datas no DataFrame
    for task in baseline_data['tasks']:
        etapa = task['etapa']
        
        # Encontrar TODAS as linhas correspondentes no DataFrame
        mask = (df_baseline['Empreendimento'] == baseline_data['empreendimento']) & \
               (df_baseline['Etapa'] == etapa)
        
        if mask.any():
            # Atualizar TODAS as linhas que correspondem (não só a primeira!)
            # Atualizar datas previstas da baseline
            if task['inicio_previsto']:
                try:
                    new_date = pd.to_datetime(task['inicio_previsto'], errors='coerce')
                    if pd.notna(new_date):
                        df_baseline.loc[mask, 'Inicio_Prevista'] = new_date
                except Exception:
                    pass
            
            if task['termino_previsto']:
                try:
                    new_date = pd.to_datetime(task['termino_previsto'], errors='coerce')
                    if pd.notna(new_date):
                        df_baseline.loc[mask, 'Termino_Prevista'] = new_date
                except Exception:
                    pass
            
            # Atualizar percentual de conclusão
            if 'percentual_concluido' in task:
                df_baseline.loc[mask, '% concluído'] = task['percentual_concluido']
    
    return df_baseline

def get_baseline_options(empreendimento):
    """Retorna opções de baselines disponíveis para um empreendimento"""
    if not empreendimento:
        return []
    
    baselines = load_baselines()
    
    # DEBUG: Mostrar o que está carregando
    print(f"DEBUG: Buscando baselines para '{empreendimento}'")
    print(f"DEBUG: Baselines carregadas: {list(baselines.keys())}")
    
    if empreendimento in baselines:
        options = list(baselines[empreendimento].keys())
        print(f"DEBUG: Baselines encontradas para {empreendimento}: {options}")
        return options
    else:
        print(f"DEBUG: Nenhuma baseline encontrada para {empreendimento}")
        return []

def send_to_aws(empreendimento, version_name):
    """Simula o envio de dados para AWS"""
    try:
        import time
        time.sleep(1)  # Simular delay
        
        # Remover da lista de não enviados
        if ('unsent_baselines' in st.session_state and 
            empreendimento in st.session_state.unsent_baselines and 
            version_name in st.session_state.unsent_baselines[empreendimento]):
            
            st.session_state.unsent_baselines[empreendimento].remove(version_name)
            
            if not st.session_state.unsent_baselines[empreendimento]:
                del st.session_state.unsent_baselines[empreendimento]
        
        return True
    except Exception as e:
        st.error(f"Erro ao enviar para AWS: {e}")
        return False
    
# --- Funções Utilitárias ---
def abreviar_nome(nome):
    if pd.isna(nome):
        return nome
    nome = nome.replace("CONDOMINIO ", "")
    palavras = nome.split()
    if len(palavras) > 3:
        nome = " ".join(palavras[:3])
    return nome

def converter_porcentagem(valor):
    if pd.isna(valor) or valor == "":
        return 0.0
    if isinstance(valor, str):
        valor = "".join(c for c in valor if c.isdigit() or c in [".", ","]).replace(",", ".").strip()
        if not valor: return 0.0
    try:
        val_float = float(valor)
        return val_float * 100 if val_float <= 1 else val_float
    except (ValueError, TypeError):
        return 0.0

def formatar_data(data):
    return data.strftime("%d/%m/%y") if pd.notna(data) else "N/D"

def calcular_dias_uteis(inicio, fim):
    if pd.notna(inicio) and pd.notna(fim):
        data_inicio = np.datetime64(inicio.date())
        data_fim = np.datetime64(fim.date())
        return np.busday_count(data_inicio, data_fim) + 1
    return 0

def calcular_variacao_termino(termino_real, termino_previsto):
    if pd.notna(termino_real) and pd.notna(termino_previsto):
        diferenca_dias = calculate_business_days(termino_previsto, termino_real)
        if pd.isna(diferenca_dias): diferenca_dias = 0
        if diferenca_dias > 0: return f"V: +{diferenca_dias}d", "#89281d"
        elif diferenca_dias < 0: return f"V: {diferenca_dias}d", "#0b803c"
        else: return "V: 0d", "#666666"
    else:
        return "V: -", "#666666"
def debug_baseline_system():
    """Função para debug do sistema de baselines"""
    st.markdown("### 🔧 Debug do Sistema de Baselines")
    
    # Testar conexão com banco
    conn = get_db_connection()
    if conn:
        st.success("✅ Conexão com banco de dados: OK")
        conn.close()
    else:
        st.error("❌ Conexão com banco de dados: FALHA")
    
    # Verificar tabela
    try:
        baselines = load_baselines()
        st.success(f"✅ Tabela de baselines: OK ({len(baselines)} empreendimentos com baselines)")
        
        # Mostrar todas as baselines disponíveis
        for empreendimento, versions in baselines.items():
            st.write(f"**{empreendimento}**: {list(versions.keys())}")
            
    except Exception as e:
        st.error(f"❌ Tabela de baselines: FALHA - {e}")
    
    # Verificar session state
    if 'unsent_baselines' in st.session_state:
        st.success(f"✅ Session state: OK ({len(st.session_state.unsent_baselines)} empreendimentos não enviados)")
    else:
        st.error("❌ Session state: FALHA - unsent_baselines não encontrado")
def calcular_porcentagem_correta(grupo):
    if "% concluído" not in grupo.columns: return 0.0
    porcentagens = grupo["% concluído"].astype(str).apply(converter_porcentagem)
    porcentagens = porcentagens[(porcentagens >= 0) & (porcentagens <= 100)]
    if porcentagens.empty: return 0.0
    porcentagens_validas = porcentagens.dropna()
    if porcentagens_validas.empty: return 0.0
    return porcentagens_validas.mean()

def padronizar_etapa(etapa_str):
    if pd.isna(etapa_str): return "UNKNOWN"
    etapa_limpa = str(etapa_str).strip().upper()
    return mapeamento_etapas_usuario.get(etapa_limpa, etapa_limpa)


# --- Funções de Filtragem e Ordenação ---
def filtrar_etapas_nao_concluidas_func(df):
    if df.empty or "% concluído" not in df.columns: return df
    df_copy = df.copy()
    df_copy["% concluído"] = df_copy["% concluído"].apply(converter_porcentagem)
    return df_copy[df_copy["% concluído"] < 100]

def obter_data_meta_assinatura(df_original, empreendimento):
    df_meta = df_original[(df_original["Empreendimento"] == empreendimento) & (df_original["Etapa"] == "DEM.MIN")]
    if df_meta.empty: 
        return None
    
    for col in ["Termino_Prevista", "Inicio_Prevista", "Termino_Real", "Inicio_Real"]:
        if col in df_meta.columns and pd.notna(df_meta[col].iloc[0]): 
            return df_meta[col].iloc[0]
    return None

def criar_ordenacao_empreendimentos(df_original):
    """
    Cria uma lista ordenada dos nomes COMPLETOS dos empreendimentos
    com base na data da meta de assinatura (DEMANDA MÍNIMA).
    """
    empreendimentos_meta = {}
    
    for emp in df_original["Empreendimento"].unique():
        data_meta = obter_data_meta_assinatura(df_original, emp)
        # Converter para timestamp Unix para ordenação segura
        if pd.notna(data_meta) and hasattr(data_meta, 'timestamp'):
            empreendimentos_meta[emp] = data_meta.timestamp()
        else:
            # Se não houver data, usar um valor muito grande para colocar no final
            empreendimentos_meta[emp] = float('inf')
    
    # Retorna a lista de nomes COMPLETOS ordenados pela data meta (timestamp)
    return sorted(empreendimentos_meta.keys(), key=lambda x: empreendimentos_meta[x])

def aplicar_ordenacao_final(df, empreendimentos_ordenados):
    if df.empty: return df
    ordem_empreendimentos = {emp: idx for idx, emp in enumerate(empreendimentos_ordenados)}
    df["ordem_empreendimento"] = df["Empreendimento"].map(ordem_empreendimentos)
    ordem_etapas = {etapa: idx for idx, etapa in enumerate(ORDEM_ETAPAS_GLOBAL)}
    df["ordem_etapa"] = df["Etapa"].map(ordem_etapas).fillna(len(ordem_etapas))
    df_ordenado = df.sort_values(["ordem_empreendimento", "ordem_etapa"]).drop(["ordem_empreendimento", "ordem_etapa"], axis=1)
    return df_ordenado.reset_index(drop=True)


# --- *** FUNÇÃO gerar_gantt_por_projeto MODIFICADA *** ---
def gerar_gantt_por_projeto(df, tipo_visualizacao, df_original_para_ordenacao, pulmao_status, pulmao_meses, titulo_extra="", baseline_name=None):
        """
        Gera um único gráfico de Gantt com todos os projetos.
        """
        # --- Processar DF SEM PULMÃO ---
        df_sem_pulmao = df.copy()
        df_gantt_sem_pulmao = df_sem_pulmao.copy()



        for col in ["Inicio_Prevista", "Termino_Prevista", "Inicio_Real", "Termino_Real"]:
            if col in df_gantt_sem_pulmao.columns:
                df_gantt_sem_pulmao[col] = pd.to_datetime(df_gantt_sem_pulmao[col], errors="coerce")

        if "% concluído" not in df_gantt_sem_pulmao.columns:
            df_gantt_sem_pulmao["% concluído"] = 0
        df_gantt_sem_pulmao["% concluído"] = df_gantt_sem_pulmao["% concluído"].fillna(0).apply(converter_porcentagem)

        # --- APLICAÇÃO DA BASELINE ANTES DA AGREGAÇÃO ---
        # Verificar se há uma baseline ativa no session state
        baseline_name = st.session_state.get('current_baseline')
        baseline_data = st.session_state.get('current_baseline_data')
        current_empreendimento_baseline = st.session_state.get('current_empreendimento')
        
        # Aplicar baseline ANTES da agregação, se houver
        if baseline_name and baseline_data and current_empreendimento_baseline:
            # Aplicar baseline apenas às linhas do empreendimento correspondente
            df_gantt_sem_pulmao = apply_baseline_to_dataframe(df_gantt_sem_pulmao, baseline_data)
        # --- FIM APLICAÇÃO DA BASELINE ---

        # Agrega os dados (usando nomes completos)
        df_gantt_agg_sem_pulmao = df_gantt_sem_pulmao.groupby(['Empreendimento', 'Etapa']).agg(
            Inicio_Prevista=('Inicio_Prevista', 'min'),
            Termino_Prevista=('Termino_Prevista', 'max'),
            Inicio_Real=('Inicio_Real', 'min'),
            Termino_Real=('Termino_Real', 'max'),
            **{'% concluído': ('% concluído', 'mean')},
            UGB=('UGB', 'first'),  # ← ADICIONADO: preservar UGB
            SETOR=('SETOR', 'first')
        ).reset_index()
        
        # CRÍTICO: Remover NaT (Not a Time) values para evitar datas inválidas no JavaScript
        for col in ['Inicio_Prevista', 'Termino_Prevista', 'Inicio_Real', 'Termino_Real']:
            if col in df_gantt_agg_sem_pulmao.columns:
                # Substituir NaT por None (que vira null em JSON)
                df_gantt_agg_sem_pulmao[col] = df_gantt_agg_sem_pulmao[col].apply(
                    lambda x: None if pd.isna(x) else x
                )

        df_gantt_agg_sem_pulmao["Etapa"] = df_gantt_agg_sem_pulmao["Etapa"].map(sigla_para_nome_completo).fillna(df_gantt_agg_sem_pulmao["Etapa"])
        # Obter baselines disponíveis
        if not df.empty:
                # Se estamos em visão consolidada por etapa, pode ter múltiplos empreendimentos
                # Mas no modo projeto, geralmente temos um empreendimento principal
                empreendimentos_no_grafico = df["Empreendimento"].unique()
                empreendimento_principal = empreendimentos_no_grafico[0] if len(empreendimentos_no_grafico) == 1 else "Múltiplos"
        else:
            empreendimento_principal = ""
        # Mapear o SETOR e GRUPO
        df_gantt_agg_sem_pulmao["SETOR"] = df_gantt_agg_sem_pulmao["Etapa"].map(SETOR_POR_ETAPA).fillna(df_gantt_agg_sem_pulmao["SETOR"])
        df_gantt_agg_sem_pulmao["GRUPO"] = df_gantt_agg_sem_pulmao["Etapa"].map(GRUPO_POR_ETAPA).fillna("Não especificado")

        # Converte o DataFrame FILTRADO agregado em lista de projetos
        gantt_data_base = converter_dados_para_gantt(df_gantt_agg_sem_pulmao)

        # --- SE NÃO HÁ DADOS FILTRADOS, NÃO FAZ NADA ---
        if not gantt_data_base:
            st.warning("Nenhum dado disponível para exibir.")
            return

        # --- Prepara opções de filtro ---
        # Obter UGBs únicas dos dados
        ugbs_disponiveis = sorted(df["UGB"].dropna().unique().tolist()) if not df.empty and "UGB" in df.columns else []
        
        filter_options = {
            "ugbs": ["Todas"] + ugbs_disponiveis,
            "setores": ["Todos"] + sorted(list(SETOR.keys())),
            "grupos": ["Todos"] + sorted(list(GRUPOS.keys())),
            "etapas": ["Todas"] + ORDEM_ETAPAS_NOME_COMPLETO
        }
            # DEBUG: Verificar dados
        print(f"DEBUG gerar_gantt_por_projeto:")
        print(f"  - DF vazio: {df.empty}")
        if not df.empty:
            print(f"  - Empreendimentos: {df['Empreendimento'].unique()}")

        # *** CORREÇÃO: USAR O PRIMEIRO PROJETO DA LISTA EM VEZ DE CRIAR "TODOS OS EMPREENDIMENTOS" ***
        if gantt_data_base:
            # Usa o primeiro projeto da lista
            project = gantt_data_base[0]
            project_id = f"p_{project['name'].replace(' ', '_').lower()}"
            correct_project_index_for_js = 0
        else:
            return

        # Filtra o DF agregado para cálculo de data_min/max
        df_para_datas = df_gantt_agg_sem_pulmao

        tasks_base_data = project['tasks'] if project else []

        data_min_proj, data_max_proj = calcular_periodo_datas(df_para_datas)
        total_meses_proj = ((data_max_proj.year - data_min_proj.year) * 12) + (data_max_proj.month - data_min_proj.month) + 1

        num_tasks = len(project["tasks"]) if project else 0
        if num_tasks == 0:
            st.warning("Nenhuma tarefa disponível para exibir.")
            return
        
        # Add baseline indicator to project title for visual feedback
        if baseline_name:
            project["name"] += f" - 📊 {baseline_name}"
        elif titulo_extra:
            project["name"] += titulo_extra

        # --- NOVA LÓGICA: Carregar baselines para TODOS os empreendimentos disponíveis ---
        baselines_data = {}
        baselines_por_empreendimento = {}
        baseline_options_por_empreendimento = {}

        # Carregar baselines para todos os empreendimentos nos dados
        todos_empreendimentos = df["Empreendimento"].unique().tolist() if not df.empty else []
        for emp in todos_empreendimentos:
            # Obter opções de baseline para este empreendimento
            emp_baseline_options = get_baseline_options(emp)
            baseline_options_por_empreendimento[emp] = emp_baseline_options
            
            # Carregar dados das baselines
            baselines = load_baselines()
            if emp in baselines:
                baselines_por_empreendimento[emp] = baselines[emp]
                
                # Preparar dados para JavaScript (apenas para o primeiro empreendimento inicial)
                if emp == (df["Empreendimento"].iloc[0] if not df.empty else ""):
                    for version_name in emp_baseline_options:
                        if version_name in baselines[emp]:
                            baselines_data[version_name] = baselines[emp][version_name]['data']

        # Determinar empreendimento atual
        empreendimento_atual = todos_empreendimentos[0] if len(todos_empreendimentos) == 1 else "Múltiplos"
        baseline_options = baseline_options_por_empreendimento.get(empreendimento_atual, []) if empreendimento_atual != "Múltiplos" else []
        
        # Obter todos os empreendimentos disponíveis nos dados filtrados
        todos_empreendimentos = df["Empreendimento"].unique().tolist() if not df.empty else []
        
        # Determinar empreendimento atual baseado no filtro ou no primeiro da lista
        empreendimento_atual = todos_empreendimentos[0] if len(todos_empreendimentos) == 1 else "Múltiplos"
        
        # Obter baselines para o empreendimento atual (se for único)
        baseline_options = []
        if empreendimento_atual != "Múltiplos":
            baseline_options = get_baseline_options(empreendimento_atual)
        
        # Preparar dados para o JavaScript
        baselines_por_empreendimento = {}
        for emp in todos_empreendimentos:
            emp_baselines = get_baseline_options(emp)
            if emp_baselines:
                baselines_por_empreendimento[emp] = emp_baselines
        
        # --- PREPARAR BASELINES PARA JAVASCRIPT ---
        available_baselines_for_js = {}
        
        all_baselines_from_db = load_baselines()
        
        # P0 = dados atuais (sem baseline)
        available_baselines_for_js["P0-(padrão)"] = converter_df_para_baseline_format(df_gantt_agg_sem_pulmao)
        
        # Carregar baselines de todos os empreendimentos
        for empreendimento_loop in todos_empreendimentos:
            if empreendimento_loop in all_baselines_from_db:
                baselines_dict = all_baselines_from_db[empreendimento_loop]
                
                for baseline_name in baselines_dict.keys():
                    baseline_data = get_baseline_data(empreendimento_loop, baseline_name)
                    
                    if baseline_data:
                        try:
                            formatted_tasks = []
                            
                            if isinstance(baseline_data, dict):
                                if 'tasks' in baseline_data:
                                    tasks_list = baseline_data['tasks']
                                else:
                                    tasks_list = list(baseline_data.values())
                            elif isinstance(baseline_data, list):
                                tasks_list = baseline_data
                            else:
                                tasks_list = []
                            
                            for i, task in enumerate(tasks_list):
                                if isinstance(task, str):
                                    if not task or not task.strip():
                                        continue
                                    try:
                                        task_dict = json.loads(task)
                                    except json.JSONDecodeError:
                                        continue
                                elif isinstance(task, dict):
                                    task_dict = task
                                else:
                                    continue
                                
                                if task_dict:
                                    formatted_tasks.append({
                                        'etapa': task_dict.get('etapa', task_dict.get('Etapa', '')),
                                        'inicio_previsto': task_dict.get('inicio_previsto', task_dict.get('Inicio_Prevista', task_dict.get('start_date'))),
                                        'termino_previsto': task_dict.get('termino_previsto', task_dict.get('Termino_Prevista', task_dict.get('end_date')))
                                    })
                            
                            available_baselines_for_js[baseline_name] = formatted_tasks
                        except Exception as e:
                            print(f"Erro ao processar baseline {baseline_name}: {e}")
                            continue
        
        
        # Reduz o fator de multiplicação para evitar excesso de espaço
        altura_gantt = max(400, min(800, (num_tasks * 25) + 200))  # Limita a altura máxima

        # --- Geração do HTML ---
        gantt_html = f"""
            <!DOCTYPE html>
            <html lang="pt-BR">
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/virtual-select-plugin@1.0.39/dist/virtual-select.min.css">
                
                <style>
                    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                    html, body {{ width: 100%; height: 100%; font-family: 'Segoe UI', sans-serif; background-color: #f5f5f5; color: #333; overflow: hidden; }}
                    .gantt-container {{ width: 100%; height: 100%; background-color: white; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); overflow: hidden; position: relative; display: flex; flex-direction: column; }}
                    .gantt-main {{ display: flex; flex: 1; overflow: hidden; }}
                    .gantt-sidebar-wrapper {{ width: 680px; display: flex; flex-direction: column; flex-shrink: 0; transition: width 0.3s ease-in-out; border-right: 2px solid #e2e8f0; overflow: hidden; }}
                    .gantt-sidebar-header {{ background: linear-gradient(135deg, #4a5568, #2d3748); display: flex; flex-direction: column; height: 60px; flex-shrink: 0; }}
                    .project-title-row {{ display: flex; justify-content: space-between; align-items: center; padding: 0 15px; height: 30px; color: white; font-weight: 600; font-size: 14px; }}
                    .toggle-sidebar-btn {{ background: rgba(255,255,255,0.2); border: none; color: white; width: 24px; height: 24px; border-radius: 5px; cursor: pointer; font-size: 14px; display: flex; align-items: center; justify-content: center; transition: background-color 0.2s, transform 0.3s ease-in-out; }}
                    .toggle-sidebar-btn:hover {{ background: rgba(255,255,255,0.4); }}
                    .sidebar-grid-header-wrapper {{ display: grid; grid-template-columns: 30px 1fr; color: #d1d5db; font-size: 9px; font-weight: 600; text-transform: uppercase; height: 30px; align-items: center; }}
                    .sidebar-grid-header {{ display: grid; grid-template-columns: 2.5fr 0.9fr 0.9fr 0.6fr 0.9fr 0.9fr 0.6fr 0.5fr 0.6fr 0.6fr; padding: 0 10px; align-items: center; }}
                    .sidebar-row {{ display: grid; grid-template-columns: 2.5fr 0.9fr 0.9fr 0.6fr 0.9fr 0.9fr 0.6fr 0.5fr 0.6fr 0.6fr; border-bottom: 1px solid #eff2f5; height: 30px; padding: 0 10px; background-color: white; transition: all 0.2s ease-in-out; }}
                    .sidebar-cell {{ display: flex; align-items: center; justify-content: center; font-size: 11px; color: #4a5568; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 8px; border: none; }}
                    .header-cell {{ text-align: center; }}
                    .header-cell.task-name-cell {{ text-align: left; }}
                    .gantt-sidebar-content {{ background-color: #f8f9fa; flex: 1; overflow-y: auto; overflow-x: hidden; }}
                    
                    /* --- CSS DEFINITIVO PARA FULLSCREEN --- */
                    /* Novos estilos para seletor de baseline - Alinhado com menu de filtros */
                    .baseline-selector {{
                        display: none;
                        position: absolute;
                        top: 10px;
                        right: 50px;
                        width: 280px;
                        background: white;
                        border-radius: 8px;
                        box-shadow: 0 5px 15px rgba(0,0,0,0.3);
                        z-index: 99;
                        padding: 15px;
                        border: 1px solid #e2e8f0;
                    }}
                    
                    .baseline-selector.is-open {{
                        display: block;
                    }}
                    
                    .baseline-selector label {{
                        display: block;
                        font-size: 11px;
                        font-weight: 600;
                        color: #4a5568;
                        margin-bottom: 4px;
                        text-transform: uppercase;
                    }}
                    
                    .baseline-selector select {{
                        width: 100%;
                        padding: 6px 8px;
                        border: 1px solid #cbd5e0;
                        border-radius: 4px;
                        font-size: 13px;
                        background: white;
                        margin-bottom: 12px;
                    }}
                    
                    .baseline-selector button {{
                        width: 100%;
                        padding: 8px;
                        font-size: 14px;
                        font-weight: 600;
                        color: white;
                        background-color: #2d3748;
                        border: none;
                        border-radius: 4px;
                        cursor: pointer;
                        margin-top: 5px;
                        transition: background-color 0.2s;
                    }}
                    
                    .baseline-selector button:hover {{
                        background-color: #1a202c;
                    }}
                    
                    
                    .baseline-current {{
                        background: #f8fafc;
                        padding: 8px 12px;
                        border-radius: 4px;
                        font-size: 12px;
                        margin-bottom: 12px;
                        border-left: 3px solid #2d3748;
                        font-weight: 500;
                        color: #1a202c;
                        transition: all 0.2s ease;
                    }}
                    
                    .baseline-current.changed {{
                        background: #fffbeb;
                        border-left-color: #f59e0b;
                        color: #92400e;
                    }}

                    .baseline-selector-container {{
                        position: absolute;
                        top: 10px;
                        right: 100px;
                        z-index: 1000;
                        background: {'#f0f7ff' if baseline_name else 'white'};
                        border-radius: 6px;
                        padding: 8px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                        border: 1px solid {'#3b82f6' if baseline_name else '#ccc'};
                        min-width: 240px;
                        max-width: 300px;
                    }}
                    
                    .baseline-selector-container select {{
                        width: 100%;
                        padding: 6px 8px;
                        border: 1px solid #aaa;
                        border-radius: 4px;
                        font-size: 12px;
                        background: white;
                        margin-bottom: 4px;
                    }}
                    
                    .baseline-label {{
                        font-size: 11px;
                        color: #333;
                        margin-bottom: 6px;
                        font-weight: bold;
                    }}
                    
                    .baseline-info {{
                        font-size: 10px;
                        color: #666;
                        line-height: 1.3;
                    }}
                    
                    .baseline-disabled {{
                        background: #f5f5f5;
                        opacity: 0.7;
                    }}
                    
                    .empreendimento-atual {{
                        font-weight: bold;
                        color: #3b82f6;
                    }}
                    #context-menu {{
                        position: fixed; /* MUDANÇA: Fixed funciona melhor se estiver dentro do container */
                        background: white;
                        border: 1px solid #ccc;
                        border-radius: 5px;
                        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
                        z-index: 2147483647; /* Máximo Z-Index possível no navegador */
                        display: none;
                        font-family: 'Segoe UI', sans-serif;
                        min-width: 160px;
                    }}
                    .context-menu-item {{
                        padding: 12px 16px;
                        cursor: pointer;
                        border-bottom: 1px solid #eee;
                        font-size: 13px;
                        color: #333;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                        transition: background 0.1s;
                    }}
                    .context-menu-item:hover {{
                        background: #f1f3f5;
                        color: #000;
                    }}
                    /* Estilo para o Toast Dinâmico */
                    .js-toast-loading {{
                        position: absolute !important; /* Absolute relativo ao container fullscreen */
                        bottom: 20px;
                        right: 20px;
                        background: #333;
                        color: white;
                        padding: 12px 24px;
                        border-radius: 5px;
                        z-index: 2147483647 !important;
                        font-size: 14px;
                        box-shadow: 0 4px 15px rgba(0,0,0,0.5);
                        display: none;
                        animation: fadeIn 0.3s;
                    }}
                    @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
                    /* Iframe invisível mas renderizado */
                    #hidden-iframe {{
                        position: absolute;
                        width: 0;
                        height: 0;
                        border: 0;
                        visibility: hidden;
                    }}
                    /* Toast de Loading */
                    .toast-loading {{
                        position: fixed;
                        bottom: 20px;
                        right: 20px;
                        background: #333;
                        color: white;
                        padding: 12px 24px;
                        border-radius: 4px;
                        z-index: 10001;
                        display: none;
                        font-size: 13px;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                    }}

                    /* Estilos para agrupamento */
                    .main-task-row {{ font-weight: 600; }}
                    .main-task-row.has-subtasks {{ cursor: pointer; }}
                    .expand-collapse-btn {{
                        background: none;
                        border: none;
                        cursor: pointer;
                        width: 20px;
                        height: 20px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 12px;
                        color: #4a5568;
                        margin-right: 5px;
                    }}
                    .subtask-row {{ 
                        display: none;
                        background-color: #f8fafc;
                        padding-left: 40px;
                    }}
                    .subtask-row.visible {{ display: grid; }}
                    .gantt-subtask-row {{ 
                        display: none;
                        background-color: #f8fafc;
                    }}
                    .gantt-subtask-row.visible {{ 
                        display: block !important;
                    }}
                    
                    /* Estilo para barras de etapas pai quando subetapas estão expandidas */
                    .gantt-bar.parent-task-real.expanded {{
                        background-color: transparent !important;
                        border: 2px solid;
                        box-shadow: none;
                    }}
                    .gantt-bar.parent-task-real.expanded .bar-label {{
                        color: #000000 !important;
                        text-shadow: 0 1px 2px rgba(255,255,255,0.8);
                    }}
                    
                    .sidebar-group-wrapper {{
                        display: flex;
                        border-bottom: 1px solid #e2e8f0;
                    }}
                    .gantt-sidebar-content > .sidebar-group-wrapper:last-child {{ border-bottom: none; }}
                    .sidebar-group-title-vertical {{
                        width: 30px; background-color: #f8fafc; color: #4a5568;
                        font-size: 8px; 
                        font-weight: 700; text-transform: uppercase;
                        display: flex; align-items: center; justify-content: center;
                        writing-mode: vertical-rl; transform: rotate(180deg);
                        flex-shrink: 0; border-right: 1px solid #e2e8f0;
                        text-align: center; white-space: nowrap; overflow: hidden;
                        text-overflow: ellipsis; padding: 5px 0; letter-spacing: -0.5px;
                        align-self: flex-start;
                    }}
                    .sidebar-group-spacer {{ display: none; }}
                    .sidebar-rows-container {{ flex-grow: 1; }}
                    .sidebar-row.odd-row {{ background-color: #fdfdfd; }}
                    .sidebar-rows-container .sidebar-row:last-child {{ border-bottom: none; }}
                    .sidebar-row:hover {{ background-color: #f5f8ff; }}
                    .sidebar-cell.task-name-cell {{ justify-content: flex-start; font-weight: 600; color: #2d3748; }}
                    .sidebar-cell.status-green {{ color: #1E8449; font-weight: 700; }}
                    .sidebar-cell.status-red    {{ color: #C0392B; font-weight: 700; }}
                    .sidebar-cell.status-yellow{{ color: #B9770E; font-weight: 700; }}
                    .sidebar-cell.status-default{{ color: #566573; font-weight: 700; }}
                    .sidebar-row .sidebar-cell:nth-child(2),
                    .sidebar-row .sidebar-cell:nth-child(3),
                    .sidebar-row .sidebar-cell:nth-child(4),
                    .sidebar-row .sidebar-cell:nth-child(5),
                    .sidebar-row .sidebar-cell:nth-child(6),
                    .sidebar-row .sidebar-cell:nth-child(7),
                    .sidebar-row .sidebar-cell:nth-child(8),
                    .sidebar-row .sidebar-cell:nth-child(9),
                    .sidebar-row .sidebar-cell:nth-child(10) {{ font-size: 8px; }}
                    .gantt-row-spacer, .sidebar-row-spacer {{
                        height: 15px;
                        border: none;
                        border-bottom: 1px solid #e2e8f0; 
                        box-sizing: border-box; 
                    }}
                    .gantt-row-spacer {{ background-color: #ffffff; position: relative; z-index: 5; }}
                    .sidebar-row-spacer {{ background-color: #f8f9fa; }}
                    .gantt-sidebar-wrapper.collapsed {{ width: 250px; }}
                    .gantt-sidebar-wrapper.collapsed .sidebar-grid-header, .gantt-sidebar-wrapper.collapsed .sidebar-row {{ grid-template-columns: 1fr; padding: 0 15px 0 10px; }}
                    .gantt-sidebar-wrapper.collapsed .header-cell:not(.task-name-cell), .gantt-sidebar-wrapper.collapsed .sidebar-cell:not(.task-name-cell) {{ display: none; }}
                    .gantt-sidebar-wrapper.collapsed .toggle-sidebar-btn {{ transform: rotate(180deg); }}
                    .gantt-chart-content {{ flex: 1; overflow: auto; position: relative; background-color: white; user-select: none; cursor: grab; }}
                    .gantt-chart-content.active {{ cursor: grabbing; }}
                    .chart-container {{ position: relative; min-width: {total_meses_proj * 30}px; }}
                    .chart-header {{ background: linear-gradient(135deg, #4a5568, #2d3748); color: white; height: 60px; position: sticky; top: 0; z-index: 9; display: flex; flex-direction: column; }}
                    .year-header {{ height: 30px; display: flex; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.2); }}
                    .year-section {{ text-align: center; font-weight: 600; font-size: 12px; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.1); height: 100%; }}
                    .month-header {{ height: 30px; display: flex; align-items: center; }}
                    .month-cell {{ width: 30px; height: 30px; border-right: 1px solid rgba(255,255,255,0.2); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 500; }}
                    .chart-body {{ position: relative; }}
                    .gantt-row {{ position: relative; height: 30px; border-bottom: 1px solid #eff2f5; background-color: white; }}
                    .gantt-bar {{ position: absolute; height: 14px; top: 8px; border-radius: 3px; cursor: pointer; transition: all 0.2s ease; display: flex; align-items: center; padding: 0 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    .gantt-bar-overlap {{ position: absolute; height: 14px; top: 8px; background-image: linear-gradient(45deg, rgba(0, 0, 0, 0.25) 25%, transparent 25%, transparent 50%, rgba(0, 0, 0, 0.25) 50%, rgba(0, 0, 0, 0.25) 75%, transparent 75%, transparent); background-size: 8px 8px; z-index: 9; pointer-events: none; border-radius: 3px; }}
                    .gantt-bar:hover {{ transform: translateY(-1px) scale(1.01); box-shadow: 0 4px 8px rgba(0,0,0,0.2); z-index: 10 !important; }}
                    .gantt-bar.previsto {{ z-index: 7; }}
                    .gantt-bar.real {{ z-index: 8; }}
                    .bar-label {{ font-size: 8px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-shadow: 0 1px 2px rgba(0,0,0,0.4); }}
                    .gantt-bar.real .bar-label {{ color: white; }}
                    .gantt-bar.previsto .bar-label {{ color: #6C6C6C; }}
                    .tooltip {{ position: fixed; background-color: #2d3748; color: white; padding: 6px 10px; border-radius: 4px; font-size: 11px; z-index: 1000; box-shadow: 0 2px 8px rgba(0,0,0,0.3); pointer-events: none; opacity: 0; transition: opacity 0.2s ease; max-width: 220px; }}
                    .tooltip.show {{ opacity: 1; }}
                    .today-line {{ position: absolute; top: 60px; bottom: 0; width: 1px; background-color: #fdf1f1; z-index: 5; box-shadow: 0 0 1px rgba(229, 62, 62, 0.6); }}
                    .month-divider {{ position: absolute; top: 60px; bottom: 0; width: 1px; background-color: #fcf6f6; z-index: 4; pointer-events: none; }}
                    .month-divider.first {{ background-color: #eeeeee; width: 1px; }}
                    .meta-line {{ position: absolute; top: 60px; bottom: 0; width: 2px; border-left: 2px dashed #8e44ad; z-index: 5; box-shadow: 0 0 4px rgba(142, 68, 173, 0.6); }}
                    .meta-line-label {{ position: absolute; top: 65px; background-color: #8e44ad; color: white; padding: 2px 5px; border-radius: 4px; font-size: 9px; font-weight: 600; white-space: nowrap; z-index: 8; transform: translateX(-50%); }}
                    .gantt-chart-content, .gantt-sidebar-content {{
                        scrollbar-width: thin;
                        scrollbar-color: transparent transparent;
                    }}
                    .gantt-chart-content:hover, .gantt-sidebar-content:hover {{
                        scrollbar-color: #d1d5db transparent;
                    }}
                    .gantt-chart-content::-webkit-scrollbar,
                    .gantt-sidebar-content::-webkit-scrollbar {{
                        height: 8px;
                        width: 8px;
                    }}
                    .gantt-chart-content::-webkit-scrollbar-track,
                    .gantt-sidebar-content::-webkit-scrollbar-track {{
                        background: transparent;
                    }}
                    .gantt-chart-content::-webkit-scrollbar-thumb,
                    .gantt-sidebar-content::-webkit-scrollbar-thumb {{
                        background-color: transparent;
                        border-radius: 4px;
                    }}
                    .gantt-chart-content:hover::-webkit-scrollbar-thumb,
                    .gantt-sidebar-content:hover::-webkit-scrollbar-thumb {{
                        background-color: #d1d5db;
                    }}
                    .gantt-chart-content:hover::-webkit-scrollbar-thumb:hover,
                    .gantt-sidebar-content:hover::-webkit-scrollbar-thumb:hover {{
                        background-color: #a8b2c1;
                    }}
                    .gantt-toolbar {{
                        position: absolute; top: 10px; right: 10px;
                        z-index: 100;
                        display: flex;
                        flex-direction: column;
                        gap: 5px;
                        background: rgba(45, 55, 72, 0.9); /* Cor de fundo escura para minimalismo */
                        border-radius: 6px;
                        padding: 5px;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                    }}
                    .toolbar-btn {{
                        background: none;
                        border: none;
                        width: 36px;
                        height: 36px;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 20px;
                        color: white;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: background-color 0.2s, box-shadow 0.2s;
                        padding: 0;
                    }}
                    .toolbar-btn:hover {{
                        background-color: rgba(255, 255, 255, 0.1);
                        box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.2);
                    }}
                    .toolbar-btn.is-fullscreen {{
                        background-color: #3b82f6; /* Cor de destaque para o botão ativo */
                        box-shadow: 0 0 0 2px #3b82f6;
                    }}
                    .toolbar-btn.is-fullscreen:hover {{
                        background-color: #2563eb;
                    }}
                    .floating-filter-menu {{
                        display: none;
                        position: absolute;
                        top: 10px; right: 50px; /* Ajuste a posição para abrir ao lado da barra de ferramentas */
                        width: 280px;
                        background: white;
                        border-radius: 8px;
                        box-shadow: 0 5px 15px rgba(0,0,0,0.3);
                        z-index: 99;
                        padding: 15px;
                        border: 1px solid #e2e8f0;
                    }}
                    .floating-filter-menu.is-open {{
                        display: block;
                    }}
                    .filter-group {{ margin-bottom: 12px; }}
                    .filter-group label {{
                        display: block;
                        font-size: 11px; font-weight: 600;
                        color: #4a5568; margin-bottom: 4px;
                        text-transform: uppercase;
                    }}
                    .filter-group select, .filter-group input[type=number] {{
                        width: 100%;
                        padding: 6px 8px;
                        border: 1px solid #cbd5e0;
                        border-radius: 4px;
                        font-size: 13px;
                    }}
                    .filter-group-radio, .filter-group-checkbox {{
                        display: flex; align-items: center;
                        padding: 5px 0;
                    }}
                    .filter-group-radio input, .filter-group-checkbox input {{
                        width: auto; margin-right: 8px;
                    }}
                    .filter-group-radio label, .filter-group-checkbox label {{
                        font-size: 13px; font-weight: 500;
                        color: #2d3748; margin-bottom: 0; text-transform: none;
                    }}
                    .filter-apply-btn {{
                        width: 100%; padding: 8px; font-size: 14px; font-weight: 600;
                        color: white; background-color: #2d3748;
                        border: none; border-radius: 4px; cursor: pointer;
                        margin-top: 5px;
                    }}

                    .floating-filter-menu .vscomp-toggle-button {{
                        border: 1px solid #cbd5e0;
                        border-radius: 4px;
                        padding: 6px 8px;
                        font-size: 13px;
                        min-height: 30px;
                    }}
                    .floating-filter-menu .vscomp-options {{
                        font-size: 13px;
                    }}
                    .floating-filter-menu .vscomp-option {{
                        min-height: 30px;
                    }}
                    .floating-filter-menu .vscomp-search-input {{
                        height: 30px;
                        font-size: 13px;
                    }}
                </style>
            </head>
            <body>
                <script id="grupos-gantt-data" type="application/json">{json.dumps(GRUPOS)}</script>
                <script id="subetapas-data" type="application/json">{json.dumps(SUBETAPAS)}</script>
                <!-- Adicionar dados de todas as baselines -->
                <script id="all-baselines-data" type="application/json">{json.dumps(baselines_por_empreendimento)}</script>
                <script id="baseline-options-por-empreendimento" type="application/json">{json.dumps(baseline_options_por_empreendimento)}</script>
                <div id="context-menu">
                    <div class="context-menu-item" id="ctx-baseline">📸 Criar Linha de Base</div>
                    <div class="context-menu-item" style="color: #999; cursor: default;">🚫 Deletar (Em breve)</div>
                </div>
                
                <iframe id="hidden-iframe" name="hidden-iframe"></iframe>
                <div id="toast-loading" class="toast-loading">🔄 Processando...</div>
                <div class="gantt-container" id="gantt-container-{project['id']}">
                    <div class="gantt-toolbar" id="gantt-toolbar-{project["id"]}">
                        <button class="toolbar-btn" id="filter-btn-{project["id"]}" title="Filtros">
                            <span>
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon>
                                </svg>
                            </span>
                        </button>
                        <button class="toolbar-btn" id="fullscreen-btn-{project["id"]}" title="Tela Cheia">
                            <span>
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
                                </svg>
                            </span>
                        </button>
                    </div>
                    <!-- Seletor de Baseline -->
                    <div class="baseline-selector" id="baseline-selector-{project['id']}">
                        <div class="baseline-current" id="current-baseline-{project['id']}">
                            {f"Baseline Ativa: {baseline_name}" if baseline_name else "Baseline Ativa: P0-(padrão)"}
                        </div>
                        <label for="baseline-dropdown-{project['id']}">Selecionar Linha de Base</label>
                        <select id="baseline-dropdown-{project['id']}">
                            <option value="P0-(padrão)">P0-(padrão)</option>
                            {"".join([f'<option value="{name}" {"selected" if name == baseline_name else ""}>{name}</option>' for name in baseline_options])}
                        </select>
                        <button onclick="switchBaselineLocal(document.getElementById('baseline-dropdown-{project['id']}').value, 'MANUAL_CLICK')">
                            Aplicar Linha de Base
                        </button>
                    </div>
                    <div class="floating-filter-menu" id="filter-menu-{project['id']}">
                        <div class="filter-group">
                            <label for="filter-ugb-{project['id']}">UGB</label>
                            <div id="filter-ugb-{project['id']}"></div>
                        </div>
                        <div class="filter-group">
                            <label for="filter-project-{project['id']}">Empreendimento</label>
                            <select id="filter-project-{project['id']}"></select>
                        </div>
                        <div class="filter-group">
                            <label for="filter-setor-{project['id']}">Setor</label>
                            <div id="filter-setor-{project['id']}"></div>
                        </div>
                        <div class="filter-group">
                            <label for="filter-grupo-{project['id']}">Grupo</label>
                            <div id="filter-grupo-{project['id']}"></div>
                        </div>
                        <div class="filter-group">
                            <label for="filter-etapa-{project['id']}">Etapa</label>
                            <div id="filter-etapa-{project['id']}"></div>
                        </div>
                        <div class="filter-group">
                            <div class="filter-group-checkbox">
                                <input type="checkbox" id="filter-concluidas-{project['id']}">
                                <label for="filter-concluidas-{project['id']}">Mostrar apenas não concluídas</label>
                            </div>
                        </div>
                        <div class="filter-group">
                            <label>Visualização</label>
                            <div class="filter-group-radio">
                                <input type="radio" id="filter-vis-ambos-{project['id']}" name="filter-vis-{project['id']}" value="Ambos" checked>
                                <label for="filter-vis-ambos-{project['id']}">Ambos</label>
                            </div>
                            <div class="filter-group-radio">
                                <input type="radio" id="filter-vis-previsto-{project['id']}" name="filter-vis-{project['id']}" value="Previsto">
                                <label for="filter-vis-previsto-{project['id']}">Previsto</label>
                            </div>
                            <div class="filter-group-radio">
                                <input type="radio" id="filter-vis-real-{project['id']}" name="filter-vis-{project['id']}" value="Real">
                                <label for="filter-vis-real-{project['id']}">Real</label>
                            </div>
                        </div>
                        <div class="filter-group">
                            <label>Simulação Pulmão</label>
                            <div class="filter-group-radio">
                                <input type="radio" id="filter-pulmao-sem-{project['id']}" name="filter-pulmao-{project['id']}" value="Sem Pulmão">
                                <label for="filter-pulmao-sem-{project['id']}">Sem Pulmão</label>
                            </div>
                            <div class="filter-group-radio">
                                <input type="radio" id="filter-pulmao-com-{project['id']}" name="filter-pulmao-{project['id']}" value="Com Pulmão">
                                <label for="filter-pulmao-com-{project['id']}">Com Pulmão</label>
                            </div>
                            <div class="filter-group" id="pulmao-meses-group-{project['id']}" style="margin-top: 8px; display: none; padding-left: 25px;">
                                <label for="filter-pulmao-meses-{project['id']}" style="font-size: 12px; font-weight: 500;">Meses de Pulmão:</label>
                                <input type="number" id="filter-pulmao-meses-{project['id']}" value="{pulmao_meses}" min="0" max="36" step="1" style="padding: 4px 6px; font-size: 12px; height: 28px; width: 80px;">
                            </div>
                        </div>
                        <button class="filter-apply-btn" id="filter-apply-btn-{project['id']}">Aplicar Filtros</button>
                    </div>

                    <div class="gantt-main">
                        <div class="gantt-sidebar-wrapper" id="gantt-sidebar-wrapper-{project['id']}">
                            <div class="gantt-sidebar-header">
                                <div class="project-title-row">
                                    <span>{project["name"]}</span>
                                    <button class="toggle-sidebar-btn" id="toggle-sidebar-btn-{project['id']}" title="Recolher/Expandir Tabela">«</button>
                                </div>
                                <div class="sidebar-grid-header-wrapper">
                                    <div></div>
                                    <div class="sidebar-grid-header">
                                        <div class="header-cell task-name-cell">SERVIÇO</div>
                                        <div class="header-cell">INÍCIO-P</div>
                                        <div class="header-cell">TÉRMINO-P</div>
                                        <div class="header-cell">DUR-P</div>
                                        <div class="header-cell">INÍCIO-R</div>
                                        <div class="header-cell">TÉRMINO-R</div>
                                        <div class="header-cell">DUR-R</div>
                                        <div class="header-cell">%</div>
                                        <div class="header-cell">VT</div>
                                        <div class="header-cell">VD</div>
                                    </div>
                                </div>
                            </div>
                            <div class="gantt-sidebar-content" id="gantt-sidebar-content-{project['id']}"></div>
                        </div>
                        <div class="gantt-chart-content" id="gantt-chart-content-{project['id']}">
                            <div class="chart-container" id="chart-container-{project["id"]}">
                                <div class="chart-header">
                                    <div class="year-header" id="year-header-{project["id"]}"></div>
                                    <div class="month-header" id="month-header-{project["id"]}"></div>
                                </div>
                                <div class="chart-body" id="chart-body-{project["id"]}"></div>
                                <div class="today-line" id="today-line-{project["id"]}"></div>
                                <div class="meta-line" id="meta-line-{project["id"]}"></div>
                                <div class="meta-line-label" id="meta-line-label-{project["id"]}"></div>
                            </div>
                        </div>
                    </div>
                    <div class="tooltip" id="tooltip-{project["id"]}"></div>

                    <iframe id="hidden-iframe" name="hidden-iframe" style="display:none;"></iframe>
                </div>
                
                <script src="https://cdn.jsdelivr.net/npm/virtual-select-plugin@1.0.39/dist/virtual-select.min.js"></script>
                
                <script>
                    const allBaselinesData = JSON.parse(document.getElementById('all-baselines-data').textContent);
                    const baselineOptionsPorEmpreendimento = JSON.parse(document.getElementById('baseline-options-por-empreendimento').textContent);
                    
                    let currentBaseline = null;
                    
                    const coresPorSetor = {json.dumps(StyleConfig.CORES_POR_SETOR)};

                    const allProjectsData = {json.dumps(gantt_data_base)};

                    let currentProjectIndex = {correct_project_index_for_js};
                    const initialProjectIndex = {correct_project_index_for_js};

                    let projectData = {json.dumps([project])};

                    // Datas originais (Python)
                    const dataMinStr = '{data_min_proj.strftime("%Y-%m-%d")}';
                    const dataMaxStr = '{data_max_proj.strftime("%Y-%m-%d")}';

                    let activeDataMinStr = dataMinStr;
                    let activeDataMaxStr = dataMaxStr;

                    const initialTipoVisualizacao = '{tipo_visualizacao}';
                    let tipoVisualizacao = '{tipo_visualizacao}';
                    const PIXELS_PER_MONTH = 30;

                    // --- ESTRUTURA DE SUBETAPAS ---
                    const SUBETAPAS = JSON.parse(document.getElementById('subetapas-data').textContent);
                    
                    // Mapeamento reverso para encontrar etapa pai
                    const ETAPA_PAI_POR_SUBETAPA = {{}};
                    for (const [etapaPai, subetapas] of Object.entries(SUBETAPAS)) {{
                        for (const subetapa of subetapas) {{
                            ETAPA_PAI_POR_SUBETAPA[subetapa] = etapaPai;
                        }}
                    }}

                    // --- INÍCIO HELPERS DE DATA E PULMÃO ---
                    const etapas_pulmao = ["PULMÃO VENDA", "PULMÃO INFRA", "PULMÃO RADIER"];
                    const etapas_sem_alteracao = ["PROSPECÇÃO", "RADIER", "DEMANDA MÍNIMA", "PE. ÁREAS COMUNS (URB)", "PE. ÁREAS COMUNS (ENG)", "ORÇ. ÁREAS COMUNS", "SUP. ÁREAS COMUNS", "EXECUÇÃO ÁREAS COMUNS"];

                    const formatDateDisplay = (dateStr) => {{
                        if (!dateStr) return "N/D";
                        const d = parseDate(dateStr);
                        if (!d || isNaN(d.getTime())) return "N/D";
                        const day = String(d.getUTCDate()).padStart(2, '0');
                        const month = String(d.getUTCMonth() + 1).padStart(2, '0');
                        const year = String(d.getUTCFullYear()).slice(-2);
                        return `${{day}}/${{month}}/${{year}}`;
                    }};
                    
                    function addMonths(dateStr, months) {{
                        if (!dateStr) return null;
                        const date = parseDate(dateStr);
                        if (!date || isNaN(date.getTime())) return null;
                        const originalDay = date.getUTCDate();
                        date.setUTCMonth(date.getUTCMonth() + months);
                        if (date.getUTCDate() !== originalDay) {{
                            date.setUTCDate(0);
                        }}
                        return date.toISOString().split('T')[0];
                    }}
                    
                    // Funções stub (vazias) - a funcionalidade já existe no HTML
                    function addBaselineButtonToToolbar() {{
                        // Não faz nada - botão já existe no HTML
                    }}
                    
                    // *** NOVA FUNÇÃO: Atualizar campos de exibição da sidebar ***
                    function updateTaskDisplayFields(task) {{
                        // Atualizar datas formatadas
                        task.inicio_previsto = formatDateDisplay(task.start_previsto);
                        task.termino_previsto = formatDateDisplay(task.end_previsto);
                        
                        // Recalcular duração em meses
                        if (task.start_previsto && task.end_previsto) {{
                            const startDate = parseDate(task.start_previsto);
                            const endDate = parseDate(task.end_previsto);
                            if (startDate && endDate) {{
                                const diffMs = endDate - startDate;
                                const diffDays = diffMs / (1000 * 60 * 60 * 24);
                                const duracao = diffDays / 30.4375; // Dias por mês médio
                                task.duracao_prev_meses = duracao > 0 ? duracao.toFixed(1).replace('.', ',') : '-';
                            }} else {{
                                task.duracao_prev_meses = '-';
                            }}
                        }} else {{
                            task.duracao_prev_meses = '-';
                        }}
                        
                        // Recalcular VT (Variação de Término)
                        if (task.end_real_original_raw && task.end_previsto) {{
                            const endReal = parseDate(task.end_real_original_raw);
                            const endPrev = parseDate(task.end_previsto);
                            if (endReal && endPrev) {{
                                const diffDays = Math.round((endReal - endPrev) / (1000 * 60 * 60 * 24));
                                task.vt_text = diffDays > 0 ? `+${{diffDays}}d` : diffDays < 0 ? `${{diffDays}}d` : '0d';
                            }} else {{
                                task.vt_text = '-';
                            }}
                        }} else {{
                            task.vt_text = '-';
                        }}
                        
                        // Recalcular VD (Variação de Duração)
                        if (task.duracao_real_meses !== '-' && task.duracao_prev_meses !== '-') {{
                            const duracaoReal = parseFloat(task.duracao_real_meses.replace(',', '.'));
                            const duracaoPrev = parseFloat(task.duracao_prev_meses.replace(',', '.'));
                            if (!isNaN(duracaoReal) && !isNaN(duracaoPrev)) {{
                                // Converter meses para dias úteis (aproximadamente)
                                const diffMeses = duracaoReal - duracaoPrev;
                                const diffDias = Math.round(diffMeses * 22); // ~22 dias úteis por mês
                                task.vd_text = diffDias > 0 ? `+${{diffDias}}d` : diffDias < 0 ? `${{diffDias}}d` : '0d';
                            }} else {{
                                task.vd_text = '-';
                            }}
                        }} else {{
                            task.vd_text = '-';
                        }}
                    }}
                    
                    // *** FUNÇÃO: Reaplicar baseline ativa após filtros ***
                    function reapplyActiveBaseline(tasks) {{
                        if (currentActiveBaseline === 'P0-(padrão)') {{
                            // P0 = dados originais, nada a fazer
                            console.log('📋 Baseline P0 ativa - usando dados originais');
                            return;
                        }}
                        
                        console.log(`🔄 Reaplicando baseline: ${{currentActiveBaseline}}`);
                        let reappliedCount = 0;
                        let clearedCount = 0;
                        
                        tasks.forEach(task => {{
                            if (task.baselines && task.baselines[currentActiveBaseline]) {{
                                const baselineData = task.baselines[currentActiveBaseline];
                                
                                if (baselineData.start !== null && baselineData.end !== null) {{
                                    task.start_previsto = baselineData.start;
                                    task.end_previsto = baselineData.end;
                                    reappliedCount++;
                                }} else {{
                                    task.start_previsto = null;
                                    task.end_previsto = null;
                                    clearedCount++;
                                }}
                                
                                // Recalcular campos de exibição
                                updateTaskDisplayFields(task);
                            }}
                        }});
                        
                        console.log(`✅ Baseline ${{currentActiveBaseline}} reaplicada: ${{reappliedCount}} atualizadas, ${{clearedCount}} limpas`);
                    }}
                    
                    function updateBaselineDropdownForProject(projectName) {{
                        console.log('📋 updateBaselineDropdownForProject chamada para:', projectName);
                        
                        const dropdown = document.getElementById('baseline-dropdown-{project["id"]}');
                        const currentIndicator = document.getElementById('current-baseline-{project["id"]}');
                        
                        if (!dropdown || !currentIndicator) {{
                            console.warn('⚠️ Dropdown ou indicador não encontrado');
                            return;
                        }}
                        
                        // Armazenar baseline original
                        const originalBaselineValue = dropdown.value;
                        console.log('🔍 Baseline original:', originalBaselineValue);
                        
                        // Clonar dropdown para remover event listeners externos
                        const newDropdown = dropdown.cloneNode(true);
                        dropdown.parentNode.replaceChild(newDropdown, dropdown);
                        console.log('🔒 Event listeners externos removidos');
                        
                        // NOVA ABORDAGEM: Monitor contínuo em vez de event listener
                        // Isso evita que o event listener seja sobrescrito por código externo
                        let lastKnownValue = originalBaselineValue;
                        
                        const monitorInterval = setInterval(function() {{
                            const dropdown = document.getElementById('baseline-dropdown-{project["id"]}');
                            const indicator = document.getElementById('current-baseline-{project["id"]}');
                            
                            if (!dropdown || !indicator) {{
                                clearInterval(monitorInterval);
                                return;
                            }}
                            
                            const currentValue = dropdown.value;
                            
                            // Detectar mudança de valor
                            if (currentValue !== lastKnownValue) {{
                                lastKnownValue = currentValue;
                                
                                if (currentValue !== originalBaselineValue) {{
                                    indicator.classList.add('changed');
                                    indicator.textContent = `Nova seleção: ${{currentValue}}`;
                                    console.log('🟠 MUDANÇA DETECTADA: Indicador → LARANJA (baseline diferente)');
                                }} else {{
                                    indicator.classList.remove('changed');
                                    indicator.textContent = `Baseline Ativa: ${{currentValue}}`;
                                    console.log('🔵 MUDANÇA DETECTADA: Indicador → AZUL (baseline original)');
                                }}
                            }}
                        }}, 100); // Verifica a cada 100ms
                        
                        console.log('✅ Monitor contínuo iniciado');
                    }}
                    
                    // Flag de controle para evitar execução automática
                    let baselineChangeInProgress = false;
                    
                    // Função de troca de baseline instantânea (client-side)
                    // IMPORTANTE: Segundo parâmetro é um token de segurança
                    function switchBaselineLocal(baselineName, securityToken) {{
                        // 🛡️ PROTEÇÃO: Só executa se chamada manualmente via botão com token correto
                        if (securityToken !== 'MANUAL_CLICK') {{
                            console.warn('⛔ Tentativa de aplicar baseline sem autorização bloqueada!');
                            console.warn('   Baseline tentada:', baselineName);
                            console.warn('   Token recebido:', securityToken);
                            return;  // BLOQUEIA a execução
                        }}
                        
                        // Proteção: só executa se não estiver sendo chamada automaticamente
                        if (baselineChangeInProgress) {{
                            console.log('⚠️ Mudança de baseline já em progresso, ignorando chamada duplicada');
                            return;
                        }}
                        
                        baselineChangeInProgress = true;
                        console.log('✅ Aplicando baseline AUTORIZADA:', baselineName);
                        
                        // *** SALVAR BASELINE ATIVA ***
                        currentActiveBaseline = baselineName;
                        console.log(`📌 Baseline ativa definida como: ${{baselineName}}`);
                        
                        if (!projectData || !projectData[0] || !projectData[0].tasks) {{
                            console.error('❌ Dados do projeto não disponíveis');
                            return;
                        }}
                        
                        const tasks = projectData[0].tasks;
                        let updatedCount = 0;
                        let clearedCount = 0;
                        
                        tasks.forEach(task => {{
                            if (task.baselines && task.baselines[baselineName]) {{
                                const baselineData = task.baselines[baselineName];
                                
                                // CORREÇÃO: Verificar se a baseline tem dados válidos (não-null)
                                // Se start e end são null, significa que a tarefa NÃO existia nesta baseline
                                if (baselineData.start !== null && baselineData.end !== null) {{
                                    // Tarefa existe na baseline - aplicar datas
                                    task.start_previsto = baselineData.start;
                                    task.end_previsto = baselineData.end;
                                    updatedCount++;
                                }} else {{
                                    // Tarefa NÃO existe na baseline - limpar datas previstas
                                    task.start_previsto = null;
                                    task.end_previsto = null;
                                    clearedCount++;
                                }}
                                
                                // *** NOVO: Recalcular campos de exibição da sidebar ***
                                updateTaskDisplayFields(task);
                            }}
                        }});
                        
                        console.log(`✅ Baseline aplicada: ${{updatedCount}} tarefas atualizadas, ${{clearedCount}} tarefas limpas`);
                        
                        const currentDiv = document.getElementById('current-baseline-{project["id"]}');
                        if (currentDiv) {{
                            currentDiv.textContent = `Baseline Ativa: ${{baselineName}}`;
                            currentDiv.classList.remove('changed');  // Remove cor laranja, volta para azul
                        }}
                        
                        // Fechar o seletor de baseline (igual ao menu de filtros)
                        const baselineSelector = document.getElementById('baseline-selector-{project["id"]}');
                        if (baselineSelector) {{
                            baselineSelector.classList.remove('is-open');
                            baselineSelector.style.display = 'none';  // Force close
                        }}
                        
                        // Redesenhar gráfico
                        try {{
                            renderChart();
                            renderSidebar();
                        }} catch (e) {{
                            console.error('Erro ao redesenhar:', e);
                            window.location.reload();
                        }} finally {{
                            // Resetar flag para permitir futuras mudanças
                            baselineChangeInProgress = false;
                        }}
                    }}
                    
                    const filterOptions = {json.dumps(filter_options)};
                    
                    // Debug: verificar se ugbs está presente
                    console.log('filterOptions:', filterOptions);
                    if (!filterOptions.ugbs) {{
                        console.warn('⚠️ filterOptions.ugbs está undefined! Usando fallback.');
                    }}

                    let allTasks_baseData = {json.dumps(tasks_base_data)};

                    const initialPulmaoStatus = '{pulmao_status}';
                    const initialPulmaoMeses = {pulmao_meses};

                    let pulmaoStatus = '{pulmao_status}';
                    let filtersPopulated = false;

                    // *** Variáveis Globais para Virtual Select ***
                    let vsUgb, vsSetor, vsGrupo, vsEtapa;
                    // *** FIM: Variáveis Globais para Virtual Select ***
                    
                    // *** RASTREAMENTO DE BASELINE ATIVA ***
                    let currentActiveBaseline = 'P0-(padrão)'; // Baseline atualmente aplicada

                    function parseDate(dateStr) {{ 
                        if (!dateStr) return null; 
                        const [year, month, day] = dateStr.split('-').map(Number); 
                        return new Date(Date.UTC(year, month - 1, day)); 
                    }}

                    function findNewDateRange(tasks) {{
                        let minDate = null;
                        let maxDate = null;

                        const updateRange = (dateStr) => {{
                            if (!dateStr) return;
                            const date = parseDate(dateStr);
                            if (!date || isNaN(date.getTime())) return;

                            if (!minDate || date < minDate) {{
                                minDate = date;
                            }}
                            if (!maxDate || date > maxDate) {{
                                maxDate = date;
                            }}
                        }};

                        tasks.forEach(task => {{
                            updateRange(task.start_previsto);
                            updateRange(task.end_previsto);
                            updateRange(task.start_real);
                            updateRange(task.end_real_original_raw || task.end_real);
                        }});

                        return {{
                            min: minDate ? minDate.toISOString().split('T')[0] : null,
                            max: maxDate ? maxDate.toISOString().split('T')[0] : null
                        }};
                    }}

                    // --- FUNÇÕES DE AGRUPAMENTO ---
                    function organizarTasksComSubetapas(tasks) {{
                        const tasksOrganizadas = [];
                        const tasksProcessadas = new Set();
                        
                        // Primeiro, adiciona todas as etapas principais
                        tasks.forEach(task => {{
                            if (tasksProcessadas.has(task.name)) return;
                            
                            const etapaPai = ETAPA_PAI_POR_SUBETAPA[task.name];
                            
                            // Se é uma subetapa, pula por enquanto
                            if (etapaPai) return;
                            
                            // Se é uma etapa principal que tem subetapas
                            if (SUBETAPAS[task.name]) {{
                                const taskPrincipal = {{...task, isMainTask: true, expanded: false}};
                                tasksOrganizadas.push(taskPrincipal);
                                tasksProcessadas.add(task.name);
                                
                                // Adiciona subetapas
                                SUBETAPAS[task.name].forEach(subetapaNome => {{
                                    const subetapa = tasks.find(t => t.name === subetapaNome);
                                    if (subetapa) {{
                                        const subetapaComPai = {{
                                            ...subetapa, 
                                            isSubtask: true, 
                                            parentTask: task.name,
                                            visible: false
                                        }};
                                        tasksOrganizadas.push(subetapaComPai);
                                        tasksProcessadas.add(subetapaNome);
                                    }}
                                }});
                            }} else {{
                                // É uma etapa principal sem subetapas
                                tasksOrganizadas.push({{...task, isMainTask: true}});
                                tasksProcessadas.add(task.name);
                            }}
                        }});
                        
                        // Adiciona quaisquer tasks que não foram processadas (não estão no mapeamento)
                        tasks.forEach(task => {{
                            if (!tasksProcessadas.has(task.name)) {{
                                tasksOrganizadas.push({{...task, isMainTask: true}});
                                tasksProcessadas.add(task.name);
                            }}
                        }});
                        
                        return tasksOrganizadas;
                    }}
                    
                    // *** NOVA FUNÇÃO: Atualizar dropdown de baseline ***
                    function updateBaselineDropdownForProject(projectName) {{
                        console.log('Atualizando baseline dropdown para:', projectName);
                        
                        const dropdown = document.getElementById('baseline-dropdown-{project['id']}');
                        const currentDiv = document.getElementById('current-baseline-{project['id']}');
                        
                        if (!dropdown || !currentDiv) {{
                            console.error('Elementos do dropdown de baseline não encontrados');
                            return;
                        }}
                        
                        // Obter baselines para este empreendimento
                        const baselinesDoEmpreendimento = baselineOptionsPorEmpreendimento[projectName] || [];
                        
                        // Salvar valor selecionado atual
                        const currentValue = dropdown.value;
                        
                        // Limpar dropdown
                        dropdown.innerHTML = '<option value="P0-(padrão)">P0-(padrão)</option>';
                        
                        // Adicionar novas opções
                        if (baselinesDoEmpreendimento.length > 0) {{
                            baselinesDoEmpreendimento.forEach(baselineName => {{
                                const isSelected = baselineName === currentBaseline;
                                dropdown.innerHTML += `<option value="${{baselineName}}" ${{isSelected ? 'selected' : ''}}>${{baselineName}}</option>`;
                            }});
                        }}
                        
                        // Restaurar valor selecionado se ainda existir
                        if (currentValue && Array.from(dropdown.options).some(opt => opt.value === currentValue)) {{
                            dropdown.value = currentValue;
                        }}
                        
                        // Atualizar texto atual
                        if (currentBaseline && currentBaseline !== 'P0-(padrão)') {{
                            currentDiv.textContent = `Baseline: ${{currentBaseline}}`;
                        }} else {{
                            currentDiv.textContent = 'Baseline: P0-(padrão)';
                        }}
                        
                        console.log('Dropdown atualizado com', baselinesDoEmpreendimento.length, 'baselines');
                        
                        // IMPORTANTE: Re-adicionar event listener após atualizar dropdown
                        // (necessário porque innerHTML foi modificado)
                        dropdown.onchange = function() {{
                            const selectedBaseline = dropdown.value;
                            console.log('📊 Baseline selecionada no dropdown:', selectedBaseline);
                            switchBaselineLocal(selectedBaseline); // ← NOVA FUNÇÃO CLIENT-SIDE
                        }};
                    }}
                    
                    
                    // FUNÇÃO GLOBAL para compatibilidade com onchange inline no HTML
                    // Agora chama diretamente switchBaselineLocal (client-side)
                    window.handleBaselineChange = function(selectedBaseline) {{
                        switchBaselineLocal(selectedBaseline);
                    }};
                    
                    
                    // *** NOVA FUNÇÃO: Alternar visibilidade do seletor de baseline ***
                    function toggleBaselineSelector() {{
                        const selector = document.getElementById('baseline-selector-{project['id']}');
                        if (selector) {{
                            selector.style.display = selector.style.display === 'none' ? 'block' : 'none';
                        }}
                    }}
                    
                    // *** NOVA FUNÇÃO: Adicionar botão de baseline na toolbar ***
                    function addBaselineButtonToToolbar() {{
                        const toolbar = document.getElementById('gantt-toolbar-{project["id"]}');
                        if (toolbar) {{
                            // Verificar se o botão já existe
                            if (document.getElementById('baseline-btn-{project["id"]}')) return;
                            
                            const baselineBtn = document.createElement('button');
                            baselineBtn.id = 'baseline-btn-{project["id"]}';
                            baselineBtn.className = 'toolbar-btn';
                            baselineBtn.innerHTML = '<span><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14,2 14,8 20,8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10,9 9,9 8,9"></polyline></svg></span>';
                            baselineBtn.title = 'Selecionar Baseline';
                            baselineBtn.onclick = toggleBaselineSelector;
                            
                            // Inserir após o botão de filtro
                            const filterBtn = document.getElementById('filter-btn-{project["id"]}');
                            if (filterBtn && filterBtn.parentNode) {{
                                filterBtn.parentNode.insertBefore(baselineBtn, filterBtn.nextSibling);
                            }} else {{
                                toolbar.appendChild(baselineBtn);
                            }}
                            
                            console.log('Botão de baseline adicionado à toolbar');
                        }}
                    }}

                    function toggleSubtasks(taskName) {{
                        const subtaskRows = document.querySelectorAll('.subtask-row[data-parent="' + taskName + '"]');
                        const ganttSubtaskRows = document.querySelectorAll('.gantt-subtask-row[data-parent="' + taskName + '"]');
                        const button = document.querySelector('.expand-collapse-btn[data-task="' + taskName + '"]');
                        
                        const isVisible = subtaskRows[0]?.classList.contains('visible');
                        
                        // Alterna visibilidade
                        subtaskRows.forEach(row => {{
                            row.classList.toggle('visible', !isVisible);
                        }});
                        
                        ganttSubtaskRows.forEach(row => {{
                            row.style.display = isVisible ? 'none' : 'block';
                            row.classList.toggle('visible', !isVisible);
                        }});
                        
                        // Atualiza ícone do botão
                        if (button) {{
                            button.textContent = isVisible ? '+' : '-';
                        }}
                        
                        // Atualiza estado no array de tasks
                        const taskIndex = projectData[0].tasks.findIndex(t => t.name === taskName && t.isMainTask);
                        if (taskIndex !== -1) {{
                            projectData[0].tasks[taskIndex].expanded = !isVisible;
                        }}

                        // Aplica/remove estilo nas barras reais da etapa pai
                        updateParentTaskBarStyle(taskName, !isVisible);
                    }}

                    function updateParentTaskBarStyle(taskName, isExpanded) {{
                        const parentTaskRow = document.querySelector('.gantt-row[data-task="' + taskName + '"]');
                        if (parentTaskRow) {{
                            const realBars = parentTaskRow.querySelectorAll('.gantt-bar.real');
                            realBars.forEach(bar => {{
                                if (isExpanded) {{
                                    bar.classList.add('parent-task-real', 'expanded');
                                    // Define a cor da borda com a mesma cor original
                                    const originalColor = bar.style.backgroundColor;
                                    bar.style.borderColor = originalColor;
                                }} else {{
                                    bar.classList.remove('parent-task-real', 'expanded');
                                    bar.style.borderColor = '';
                                }}
                            }});
                        }}
                    }}
                    
                    // --- LÓGICA V6: NOME DINÂMICO (CORREÇÃO FINAL) ---
                    // --- LÓGICA V15: IFRAME SEGURO + URL VIA REFERRER (DEFINITIVA) ---
                    (function() {{
                        // 1. Configuração
                        const containerId = 'gantt-container-' + '{project["id"]}';
                        const container = document.getElementById(containerId);
                        
                        // Garante iframe
                        let iframe = document.getElementById('hidden-iframe');
                        if (!iframe) {{
                            iframe = document.createElement('iframe');
                            iframe.id = 'hidden-iframe';
                            iframe.style.display = 'none';
                            if(container) container.appendChild(iframe);
                        }}

                        if (!container) return;

                        // Limpeza visual
                        const oldMenu = container.querySelector('#context-menu');
                        if (oldMenu) oldMenu.remove();
                        const oldToast = container.querySelector('.js-toast-loading');
                        if (oldToast) oldToast.remove();

                        // 2. Criar Menu Radial
                        const menu = document.createElement('div');
                        menu.id = 'radial-menu';
                        menu.style.cssText = "position:fixed; z-index:2147483647; display:none; font-family:'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;";
                        menu.innerHTML = `
                            <style>
                                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
                                
                                .radial-menu-wrapper {{
                                    position: relative;
                                    width: 260px;
                                    height: 260px;
                                }}
                                
                                .radial-center {{
                                    position: absolute;
                                    top: 50%;
                                    left: 50%;
                                    transform: translate(-50%, -50%);
                                    width: 44px;
                                    height: 44px;
                                    border: 3px solid #007AFF;
                                    border-radius: 50%;
                                    background: transparent;
                                    cursor: pointer;
                                    transition: all 0.2s ease;
                                    z-index: 10;
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                }}
                                
                                .radial-center:hover {{
                                    transform: translate(-50%, -50%) scale(1.1);
                                    border-width: 4px;
                                }}
                                
                                .radial-center-play {{
                                    width: 0;
                                    height: 0;
                                    border-left: 11px solid #007AFF;
                                    border-top: 7px solid transparent;
                                    border-bottom: 7px solid transparent;
                                    margin-left: 3px;
                                }}
                                
                                /* Círculo de fundo que passa por baixo dos ícones */
                                .radial-background-circle {{
                                    position: absolute;
                                    top: 50%;
                                    left: 50%;
                                    transform: translate(-50%, -50%);
                                    width: 140px;
                                    height: 140px;
                                    border: 4px solid #f0f0f0;
                                    border-radius: 50%;
                                    background: transparent;
                                    z-index: 1;
                                }}
                                
                                .radial-item {{
                                    position: absolute;
                                    width: 32px;
                                    height: 32px;
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                    cursor: pointer;
                                    transition: all 0.2s ease;
                                    z-index: 5;
                                    background: white;
                                    border: 2px solid #f0f0f0;
                                    border-radius: 7px;
                                    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
                                }}
                                
                                .radial-item:hover {{
                                    background: #f5f5f5;
                                    transform: scale(1.1);
                                    box-shadow: 0 3px 8px rgba(0, 0, 0, 0.15);
                                    border-color: #007AFF;
                                }}
                                
                                .radial-item svg {{
                                    width: 20px;
                                    height: 20px;
                                    transition: all 0.2s ease;
                                    fill: #333333;
                                    stroke: #333333;
                                }}
                                
                                .radial-item:hover svg {{
                                    fill: #007AFF;
                                    stroke: #007AFF;
                                }}
                                
                                /* Modo de Foco - Escurecer barras */
                                .gantt-bar.focus-mode {{
                                    filter: grayscale(100%) brightness(0.4) !important;
                                    opacity: 0.5 !important;
                                    transition: all 0.3s ease;
                                }}
                                
                                .gantt-bar.focus-mode.focused {{
                                    filter: none !important;
                                    opacity: 1 !important;
                                }}
                                
                                .radial-tooltip {{
                                    position: absolute;
                                    padding: 5px 9px;
                                    border-radius: 14px;
                                    font-size: 10px;
                                    font-weight: 500;
                                    white-space: nowrap;
                                    display: flex;
                                    align-items: center;
                                    gap: 5px;
                                    pointer-events: none;
                                    transition: background 0.2s ease, color 0.2s ease;
                                    z-index: 15;
                                    background: #f5f5f5;
                                    color: #333;
                                }}
                                
                                .radial-item:hover + .radial-tooltip {{
                                    background: #007AFF;
                                    color: white;
                                }}
                                
                                .radial-item:hover + .radial-tooltip .tooltip-badge {{
                                    background: white;
                                    color: #007AFF;
                                }}
                                
                                /* Tooltip amarelo para "Em produção" - apenas no hover */
                                .radial-item:hover + .radial-tooltip.yellow-tooltip {{
                                    background: #FFC107 !important;
                                    color: #333 !important;
                                }}
                                
                                .radial-item:hover + .radial-tooltip.yellow-tooltip .tooltip-badge {{
                                    background: #333;
                                    color: #FFC107;
                                }}
                                
                                .radial-tooltip.active {{
                                    background: #007AFF;
                                    color: white;
                                    box-shadow: 0 2px 12px rgba(0, 122, 255, 0.3);
                                    opacity: 1 !important;
                                    transform: scale(1) !important;
                                }}
                                
                                .radial-tooltip:not(.active) {{
                                    background: #f5f5f5;
                                    color: #333;
                                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                                }}
                                
                                .tooltip-badge {{
                                    padding: 3px 8px;
                                    border-radius: 5px;
                                    font-size: 11px;
                                    font-weight: 600;
                                    min-width: 20px;
                                    text-align: center;
                                    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
                                }}
                                
                                .tooltip-badge.active-badge {{
                                    background: white;
                                    color: #007AFF;
                                }}
                                
                                .tooltip-badge.inactive-badge {{
                                    background: #e0e0e0;
                                    color: #666;
                                }}
                                
                                .radial-more {{
                                    position: absolute;
                                    padding: 10px 18px;
                                    background: #f5f5f5;
                                    color: #666;
                                    border-radius: 20px;
                                    font-size: 13px;
                                    font-weight: 500;
                                    cursor: pointer;
                                    transition: all 0.2s ease;
                                    z-index: 5;
                                    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
                                }}
                                
                                .radial-more:hover {{
                                    background: #e8e8e8;
                                    transform: scale(1.05);
                                }}
                                
                                @keyframes fadeIn {{
                                    from {{ opacity: 0; transform: scale(0.8); }}
                                    to {{ opacity: 1; transform: scale(1); }}
                                }}
                                
                                .radial-item, .radial-tooltip, .radial-more {{
                                    animation: fadeIn 0.3s ease-out;
                                }}
                            </style>
                            
                            <div class="radial-menu-wrapper">
                                <!-- Círculo de fundo -->
                                <div class="radial-background-circle"></div>
                                
                                <!-- Centro com play button -->
                                <div class="radial-center" title="Menu Radial"></div>
                                
                                <!-- Topo: Move Tool (Criar Baseline) -->
                                <div class="radial-item" id="btn-create-baseline" style="top: 44px; left: 114px;">
                                    <svg viewBox="0 0 24 24">
                                        <path d="M3 3l7.07 16.97 2.51-7.39 7.39-2.51L3 3z"/>
                                    </svg>
                                </div>
                                <div class="radial-tooltip yellow-tooltip" style="top: 10px; left: 50%; transform: translateX(-50%);">
                                    Em produção
                                    <span class="tooltip-badge inactive-badge">X</span>
                                </div>
                                
                                <!-- Direita: Pen Tool (Caneta) -->
                                <div class="radial-item" style="top: 114px; left: 184px;">
                                    <svg viewBox="0 0 24 24">
                                        <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                                    </svg>
                                </div>
                                <div class="radial-tooltip" style="top: 114px; left: 224px;">
                                    Notas
                                    <span class="tooltip-badge inactive-badge">N</span>
                                </div>
                                
                                <!-- Esquerda: Actions (Ações) -->
                                <div class="radial-item" style="top: 114px; left: 44px;">
                                    <svg viewBox="0 0 24 24">
                                        <rect x="3" y="3" width="7" height="7" rx="1"/>
                                        <rect x="14" y="3" width="7" height="7" rx="1"/>
                                        <rect x="3" y="14" width="7" height="7" rx="1"/>
                                        <path d="M18 18l-3-3m3 3l3-3m-3 3v-6" stroke="currentColor" fill="none" stroke-width="2"/>
                                    </svg>
                                </div>
                                <div class="radial-tooltip" style="top: 114px; right: 224px;">
                                    Modo Foco
                                    <span class="tooltip-badge inactive-badge">F</span>
                                </div>
                            </div>
                        `;
                        container.appendChild(menu);
                        
                        // Bloquinho de Notas Flutuante
                        const notepad = document.createElement('div');
                        notepad.id = 'floating-notepad';
                        notepad.style.cssText = "display:none; position:fixed; top:100px; right:50px; width:320px; height:420px; background:white; border:1px solid #e8e8e8; border-radius:16px; box-shadow:0 8px 32px rgba(0,0,0,0.08); z-index:9999; flex-direction:column; font-family:'Inter', sans-serif; overflow:hidden;";
                        notepad.innerHTML = `
                            <style>
                                .notepad-header {{
                                    padding: 14px 18px;
                                    background: #2E384A;
                                    color: white;
                                    display: flex;
                                    justify-content: space-between;
                                    align-items: center;
                                    cursor: move;
                                    user-select: none;
                                    border-bottom: 1px solid rgba(255,255,255,0.1);
                                }}
                                
                                .notepad-header-title {{
                                    display: flex;
                                    align-items: center;
                                    gap: 8px;
                                }}
                                
                                .notepad-header-title svg {{
                                    width: 18px;
                                    height: 18px;
                                    fill: white;
                                }}
                                
                                .notepad-header span {{
                                    font-size: 13px;
                                    font-weight: 600;
                                    letter-spacing: 0.3px;
                                }}
                                
                                .notepad-close {{
                                    background: rgba(255,255,255,0.15);
                                    border: none;
                                    color: white;
                                    font-size: 20px;
                                    cursor: pointer;
                                    padding: 4px 8px;
                                    line-height: 1;
                                    border-radius: 6px;
                                    transition: all 0.2s ease;
                                }}
                                
                                .notepad-close:hover {{
                                    background: rgba(255,255,255,0.25);
                                    transform: scale(1.05);
                                }}
                                
                                .notepad-content {{
                                    flex: 1;
                                    padding: 20px;
                                    border: none;
                                    resize: none;
                                    font-family: 'Inter', sans-serif;
                                    font-size: 14px;
                                    line-height: 1.6;
                                    outline: none;
                                    color: #333;
                                    background: #fafafa;
                                }}
                                
                                .notepad-content::placeholder {{
                                    color: #aaa;
                                }}
                            </style>
                            <div class="notepad-header">
                                <div class="notepad-header-title">
                                    <svg viewBox="0 0 24 24">
                                        <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                                    </svg>
                                    <span>Notas</span>
                                </div>
                                <button class="notepad-close">×</button>
                            </div>
                            <textarea class="notepad-content" placeholder="Digite suas notas aqui..."></textarea>
                        `;
                        container.appendChild(notepad);

                        // 3. Criar Toast
                        const toast = document.createElement('div');
                        toast.className = 'js-toast-loading';
                        toast.style.cssText = "position:fixed; bottom:20px; right:20px; background:#2c3e50; color:white; padding:15px 25px; border-radius:8px; z-index:2147483647; display:none; font-family:sans-serif; box-shadow:0 5px 15px rgba(0,0,0,0.3); transition: all 0.3s ease;";
                        container.appendChild(toast);

                        // 4. Listeners
                        container.addEventListener('contextmenu', function(e) {{
                            if (e.target.closest('.gantt-chart-content') || e.target.closest('.gantt-sidebar-wrapper') || e.target.closest('.gantt-row')) {{
                                e.preventDefault();
                                menu.style.display = 'block';
                                menu.style.left = (e.clientX - 130) + 'px';  // Centraliza menu de 260px
                                menu.style.top = (e.clientY - 130) + 'px';
                            }}
                        }});

                        document.addEventListener('click', function(e) {{
                            if (menu.style.display === 'block' && !menu.contains(e.target)) {{
                                menu.style.display = 'none';
                            }}
                        }}, true);
                        
                        // Fechar ao clicar no centro
                        const centerBtn = menu.querySelector('.radial-center');
                        if (centerBtn) {{
                            centerBtn.addEventListener('click', function(e) {{
                                e.stopPropagation();
                                menu.style.display = 'none';
                            }});
                        }}

                        // --- 5. AÇÃO DO BOTÃO ---
                        const btnCreate = menu.querySelector('#btn-create-baseline');
                        
                        btnCreate.addEventListener('click', function(e) {{
                            e.stopPropagation();
                            e.preventDefault();

                            // A. Nome do Projeto
                            let currentProjectName = "Desconhecido";
                            if (typeof projectData !== 'undefined' && projectData.length > 0) {{
                                currentProjectName = projectData[0].name;
                            }} else {{
                                const titleEl = container.querySelector('.project-title-row span');
                                if (titleEl) currentProjectName = titleEl.textContent;
                            }}

                            // B. Feedback Visual (Laranja = Processando)
                            menu.style.display = 'none';
                            toast.style.display = 'block';
                            toast.style.backgroundColor = "#e67e22"; // Laranja
                            toast.innerHTML = `⏳ Processando baseline de <b>${{currentProjectName}}</b>...`; 

                            // C. Montar URL CORRETA
                            const encodedProject = encodeURIComponent(currentProjectName);
                            const timestamp = new Date().getTime();
                            
                            // Usa REFERRER para pegar a URL real do app (ex: https://app.streamlit...)
                            // Isso corrige o bug do "about:srcdoc"
                            let baseUrl = document.referrer;
                            if (!baseUrl || baseUrl === "") {{
                                // Fallback raro
                                baseUrl = window.location.ancestorOrigins && window.location.ancestorOrigins[0] ? window.location.ancestorOrigins[0] : "";
                            }}
                            // Remove barra final
                            if (baseUrl.endsWith('/')) baseUrl = baseUrl.slice(0, -1);

                            // Se falhar tudo, tenta relativo (mas geralmente referrer resolve no Streamlit Cloud)
                            const finalUrl = baseUrl ? (baseUrl + `/?context_action=take_baseline&empreendimento=${{encodedProject}}&t=${{timestamp}}`) : `?context_action=take_baseline&empreendimento=${{encodedProject}}`;

                            console.log("🚀 URL Iframe:", finalUrl);
                            
                            // D. Enviar via Iframe (Não recarrega a página, mas salva no banco)
                            if (iframe) iframe.src = finalUrl;

                            // E. Feedback Final
                            // Espera 4 segundos (tempo pro Python salvar) e avisa para atualizar
                            setTimeout(() => {{
                                toast.style.backgroundColor = "#27ae60"; // Verde
                                toast.innerHTML = `
                                    <div style="display:flex; flex-direction:column; gap:5px;">
                                        <span style="font-weight:bold; font-size:14px;">✅ Salvo no Banco!</span>
                                        <span style="font-size:12px;">Dados processados em segundo plano.</span>
                                        <span style="font-weight:bold; text-decoration:underline; cursor:pointer;">🔄 Pressione F5 agora para ver.</span>
                                    </div>
                                `;
                                setTimeout(() => {{ toast.style.display = 'none'; }}, 12000);
                            }}, 4000);
                        }});
                        
                        // --- 6. BLOQUINHO DE NOTAS ---
                        let notepadActive = false;
                        const penIcon = menu.querySelector('[style*="top: 114px; left: 184px"]'); // Ícone Caneta (reposicionado)
                        const notepadTextarea = notepad.querySelector('.notepad-content');
                        const NOTEPAD_STORAGE_KEY = 'gantt_notepad_content';
                        
                        // Carregar texto salvo do localStorage ao iniciar
                        const savedContent = localStorage.getItem(NOTEPAD_STORAGE_KEY);
                        if (savedContent && notepadTextarea) {{
                            notepadTextarea.value = savedContent;
                        }}
                        
                        // Salvar texto no localStorage sempre que digitar
                        if (notepadTextarea) {{
                            notepadTextarea.addEventListener('input', () => {{
                                localStorage.setItem(NOTEPAD_STORAGE_KEY, notepadTextarea.value);
                            }});
                        }}
                        
                        // Toggle notepad ao clicar no ícone Caneta
                        if (penIcon) {{
                            penIcon.addEventListener('click', (e) => {{
                                e.stopPropagation();
                                notepadActive = !notepadActive;
                                notepad.style.display = notepadActive ? 'flex' : 'none';
                                
                                // Marcar ícone como ativo/inativo
                                if (notepadActive) {{
                                    penIcon.style.borderColor = '#007AFF';
                                    penIcon.style.background = '#e6f2ff';
                                }} else {{
                                    penIcon.style.borderColor = '';
                                    penIcon.style.background = '';
                                }}
                                
                                menu.style.display = 'none';
                            }});
                        }}
                        
                        // Fechar notepad com botão X
                        const closeBtn = notepad.querySelector('.notepad-close');
                        if (closeBtn) {{
                            closeBtn.addEventListener('click', () => {{
                                notepadActive = false;
                                notepad.style.display = 'none';
                                if (penIcon) {{
                                    penIcon.style.borderColor = '';
                                    penIcon.style.background = '';
                                }}
                                // NÃO limpar localStorage aqui - apenas fechar visualmente
                            }});
                        }}
                        
                        // Drag-and-drop do bloquinho
                        let isDragging = false;
                        let offsetX, offsetY;
                        const notepadHeader = notepad.querySelector('.notepad-header');
                        
                        if (notepadHeader) {{
                            notepadHeader.addEventListener('mousedown', (e) => {{
                                isDragging = true;
                                offsetX = e.clientX - notepad.offsetLeft;
                                offsetY = e.clientY - notepad.offsetTop;
                                notepadHeader.style.cursor = 'grabbing';
                            }});
                        }}
                        
                        document.addEventListener('mousemove', (e) => {{
                            if (isDragging) {{
                                notepad.style.left = (e.clientX - offsetX) + 'px';
                                notepad.style.top = (e.clientY - offsetY) + 'px';
                                notepad.style.right = 'auto';
                            }}
                        }});
                        
                        document.addEventListener('mouseup', () => {{
                            if (isDragging) {{
                                isDragging = false;
                                if (notepadHeader) notepadHeader.style.cursor = 'move';
                            }}
                        }});
                        
                        // --- 7. MODO DE FOCO (BOTÃO AÇÕES) ---
                        let focusModeActive = false;
                        const actionsIcon = menu.querySelector('[style*="top: 114px; left: 44px"]'); // Botão Ações (reposicionado)
                        
                        // Toggle modo de foco ao clicar no botão Ações
                        if (actionsIcon) {{
                            actionsIcon.addEventListener('click', (e) => {{
                                e.stopPropagation();
                                focusModeActive = !focusModeActive;
                                
                                const allBars = container.querySelectorAll('.gantt-bar');
                                
                                if (focusModeActive) {{
                                    // Ativar modo foco - escurecer todas as barras
                                    allBars.forEach(bar => bar.classList.add('focus-mode'));
                                    actionsIcon.style.borderColor = '#007AFF';
                                    actionsIcon.style.background = '#e6f2ff';
                                }} else {{
                                    // Desativar modo foco - restaurar todas as cores
                                    allBars.forEach(bar => {{
                                        bar.classList.remove('focus-mode', 'focused');
                                    }});
                                    actionsIcon.style.borderColor = '';
                                    actionsIcon.style.background = '';
                                }}
                                
                                menu.style.display = 'none';
                            }});
                        }}
                        
                        // Click em barras para focar/desfocar (seleção múltipla com toggle)
                        container.addEventListener('click', (e) => {{
                            if (!focusModeActive) return;
                            
                            const clickedBar = e.target.closest('.gantt-bar');
                            if (!clickedBar) return;
                            
                            // Toggle: se já está focada, remove foco; senão, adiciona
                            if (clickedBar.classList.contains('focused')) {{
                                clickedBar.classList.remove('focused');
                            }} else {{
                                clickedBar.classList.add('focused');
                            }}
                        }});

                    }})();
                    
                    function initGantt() {{
                        console.log('Iniciando Gantt com dados:', projectData);
                        
                        // Verificar se há dados para renderizar
                        if (!projectData || !projectData[0] || !projectData[0].tasks || projectData[0].tasks.length === 0) {{
                            console.error('Nenhum dado disponível para renderizar');
                            document.getElementById('chart-body-{project["id"]}').innerHTML = '<div style="padding: 20px; text-align: center; color: red;">Erro: Nenhum dado disponível</div>';
                            return;
                        }}

                        // Organizar tasks com estrutura de subetapas
                        projectData[0].tasks = organizarTasksComSubetapas(projectData[0].tasks);
                        allTasks_baseData = JSON.parse(JSON.stringify(projectData[0].tasks));

                        applyInitialPulmaoState();

                        if (initialPulmaoStatus === 'Com Pulmão' && initialPulmaoMeses > 0) {{
                            const {{ min: newMinStr, max: newMaxStr }} = findNewDateRange(projectData[0].tasks);
                            const newMin = parseDate(newMinStr);
                            const newMax = parseDate(newMaxStr);
                            const originalMin = parseDate(activeDataMinStr);
                            const originalMax = parseDate(activeDataMaxStr);

                            let finalMinDate = originalMin;
                            if (newMin && newMin < finalMinDate) {{
                                finalMinDate = newMin;
                            }}
                            let finalMaxDate = originalMax;
                            if (newMax && newMax > finalMaxDate) {{
                                finalMaxDate = newMax;
                            }}

                            finalMinDate = new Date(finalMinDate.getTime());
                            finalMaxDate = new Date(finalMaxDate.getTime());

                            finalMinDate.setUTCDate(1);
                            finalMaxDate.setUTCMonth(finalMaxDate.getUTCMonth() + 1, 0);

                            activeDataMinStr = finalMinDate.toISOString().split('T')[0];
                            activeDataMaxStr = finalMaxDate.toISOString().split('T')[0];
                        }}


                        // *** ADICIONAR BOTÃO DE BASELINE ***
                        addBaselineButtonToToolbar();
                        
                        // *** ATUALIZAR DROPDOWN DE BASELINE ***

                        renderSidebar();
                        renderHeader();
                        renderChart();
                        renderMonthDividers();
                        setupEventListeners();
                        positionTodayLine();
                        positionMetaLine();
                        populateFilters();
                        
                        // Inicializar monitoramento do dropdown de baseline
                        updateBaselineDropdownForProject(projectData[0].name);
                    }}

                    function applyInitialPulmaoState() {{
                        if (initialPulmaoStatus === 'Com Pulmão' && initialPulmaoMeses > 0) {{
                            const offsetMeses = -initialPulmaoMeses;
                            let baseTasks = projectData[0].tasks;

                            baseTasks.forEach(task => {{
                                const etapaNome = task.name;
                                if (etapas_sem_alteracao.includes(etapaNome)) {{
                                    // Não altera datas
                                }}
                                else if (etapas_pulmao.includes(etapaNome)) {{
                                    // APENAS PREVISTO
                                    task.start_previsto = addMonths(task.start_previsto, offsetMeses);
                                    task.inicio_previsto = formatDateDisplay(task.start_previsto);
                                }}
                                else {{
                                    // APENAS PREVISTO
                                    task.start_previsto = addMonths(task.start_previsto, offsetMeses);
                                    task.end_previsto = addMonths(task.end_previsto, offsetMeses);
                                    task.inicio_previsto = formatDateDisplay(task.start_previsto);
                                    task.termino_previsto = formatDateDisplay(task.end_previsto);
                                    // NÃO modificar dados reais
                                }}
                            }});

                            allTasks_baseData = JSON.parse(JSON.stringify(baseTasks));
                        }}
                    }}

                    function renderSidebar() {{
                        const sidebarContent = document.getElementById('gantt-sidebar-content-{project['id']}');
                        const gruposGantt = JSON.parse(document.getElementById('grupos-gantt-data').textContent);
                        const tasks = projectData[0].tasks;
                        
                        if (!tasks || tasks.length === 0) {{
                            sidebarContent.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">Nenhuma tarefa disponível para os filtros aplicados</div>';
                            return;
                        }}
                        
                        let html = '';
                        let globalRowIndex = 0;
                        const groupKeys = Object.keys(gruposGantt);
                        
                        for (let i = 0; i < groupKeys.length; i++) {{
                            const grupo = groupKeys[i];
                            const tasksInGroupNames = gruposGantt[grupo].filter(etapaNome => tasks.some(t => t.name === etapaNome && !t.isSubtask));
                            if (tasksInGroupNames.length === 0) continue;
                            
                            const groupHeight = (tasksInGroupNames.length * 30);
                            html += `<div class="sidebar-group-wrapper">`;
                            html += `<div class="sidebar-group-title-vertical" style="height: ${{groupHeight}}px;"><span>${{grupo}}</span></div>`;
                            html += `<div class="sidebar-rows-container">`;
                            
                            gruposGantt[grupo].forEach(etapaNome => {{
                                const task = tasks.find(t => t.name === etapaNome && !t.isSubtask);
                                if (task) {{
                                    globalRowIndex++;
                                    const rowClass = globalRowIndex % 2 !== 0 ? 'odd-row' : '';
                                    const hasSubtasks = SUBETAPAS[task.name] && SUBETAPAS[task.name].length > 0;
                                    const mainTaskClass = hasSubtasks ? 'main-task-row has-subtasks' : 'main-task-row';
                                    
                                    html += `<div class="sidebar-row ${{mainTaskClass}} ${{rowClass}}" data-task="${{task.name}}">`;
                                    
                                    // Coluna do botão de expandir/recolher
                                    if (hasSubtasks) {{
                                        html += `<div class="sidebar-cell task-name-cell" style="display: flex; align-items: center;">`;
                                        html += `<button class="expand-collapse-btn" data-task="${{task.name}}">${{task.expanded ? '-' : '+'}}</button>`;
                                        html += `<span title="${{task.numero_etapa}}. ${{task.name}}">${{task.numero_etapa}}. ${{task.name}}</span>`;
                                        html += `</div>`;
                                    }} else {{
                                        html += `<div class="sidebar-cell task-name-cell" title="${{task.numero_etapa}}. ${{task.name}}">${{task.numero_etapa}}. ${{task.name}}</div>`;
                                    }}
                                    
                                    html += `<div class="sidebar-cell">${{task.inicio_previsto}}</div>`;
                                    html += `<div class="sidebar-cell">${{task.termino_previsto}}</div>`;
                                    html += `<div class="sidebar-cell">${{task.duracao_prev_meses}}</div>`;
                                    html += `<div class="sidebar-cell">${{task.inicio_real}}</div>`;
                                    html += `<div class="sidebar-cell">${{task.termino_real}}</div>`;
                                    html += `<div class="sidebar-cell">${{task.duracao_real_meses}}</div>`;
                                    html += `<div class="sidebar-cell ${{task.status_color_class}}">${{task.progress}}%</div>`;
                                    html += `<div class="sidebar-cell ${{task.status_color_class}}">${{task.vt_text}}</div>`;
                                    html += `<div class="sidebar-cell ${{task.status_color_class}}">${{task.vd_text}}</div>`;
                                    html += `</div>`;
                                    
                                    // Adicionar subetapas se existirem
                                    if (hasSubtasks && SUBETAPAS[task.name]) {{
                                        SUBETAPAS[task.name].forEach(subetapaNome => {{
                                            const subetapa = tasks.find(t => t.name === subetapaNome && t.isSubtask);
                                            if (subetapa) {{
                                                globalRowIndex++;
                                                const subtaskRowClass = globalRowIndex % 2 !== 0 ? 'odd-row' : '';
                                                const visibleClass = task.expanded ? 'visible' : '';
                                                html += `<div class="sidebar-row subtask-row ${{subtaskRowClass}} ${{visibleClass}}" data-parent="${{task.name}}">`;
                                                html += `<div class="sidebar-cell task-name-cell" title="${{subetapa.numero_etapa}}. • ${{subetapa.name}}">${{subetapa.numero_etapa}}. • ${{subetapa.name}}</div>`;
                                                html += `<div class="sidebar-cell">${{subetapa.inicio_previsto}}</div>`;
                                                html += `<div class="sidebar-cell">${{subetapa.termino_previsto}}</div>`;
                                                html += `<div class="sidebar-cell">${{subetapa.duracao_prev_meses}}</div>`;
                                                html += `<div class="sidebar-cell">${{subetapa.inicio_real}}</div>`;
                                                html += `<div class="sidebar-cell">${{subetapa.termino_real}}</div>`;
                                                html += `<div class="sidebar-cell">${{subetapa.duracao_real_meses}}</div>`;
                                                html += `<div class="sidebar-cell ${{subetapa.status_color_class}}">${{subetapa.progress}}%</div>`;
                                                html += `<div class="sidebar-cell ${{subetapa.status_color_class}}">${{subetapa.vt_text}}</div>`;
                                                html += `<div class="sidebar-cell ${{subetapa.status_color_class}}">${{subetapa.vd_text}}</div>`;
                                                html += `</div>`;
                                            }}
                                        }});
                                    }}
                                }}
                            }});
                            html += `</div></div>`;
                            
                            const tasksInGroup = tasksInGroupNames;
                            if (i < groupKeys.length - 1 && tasksInGroup.length > 0) {{
                                const nextGroupKey = groupKeys[i + 1];
                                const nextGroupTasks = gruposGantt[nextGroupKey].filter(etapaNome => tasks.some(t => t.name === etapaNome && !t.isSubtask));
                                if (nextGroupTasks.length > 0) {{
                                    html += `<div class="sidebar-row-spacer"></div>`;
                                }}
                            }}
                        }}
                        sidebarContent.innerHTML = html;
                        
                        // Adicionar event listeners para os botões de expandir/recolher
                        document.querySelectorAll('.expand-collapse-btn').forEach(button => {{
                            button.addEventListener('click', function(e) {{
                                e.stopPropagation();
                                const taskName = this.getAttribute('data-task');
                                toggleSubtasks(taskName);
                            }});
                        }});
                        
                        // Adicionar event listeners para as linhas principais com subetapas
                        document.querySelectorAll('.main-task-row.has-subtasks').forEach(row => {{
                            row.addEventListener('click', function() {{
                                const taskName = this.getAttribute('data-task');
                                toggleSubtasks(taskName);
                            }});
                        }});
                    }}

                    function renderHeader() {{
                        const yearHeader = document.getElementById('year-header-{project["id"]}');
                        const monthHeader = document.getElementById('month-header-{project["id"]}');
                        let yearHtml = '', monthHtml = '';
                        const yearsData = [];

                        let currentDate = parseDate(activeDataMinStr);
                        const dataMax = parseDate(activeDataMaxStr);

                        if (!currentDate || !dataMax || isNaN(currentDate.getTime()) || isNaN(dataMax.getTime())) {{
                            yearHeader.innerHTML = "Datas inválidas";
                            monthHeader.innerHTML = "";
                            return;
                        }}

                        // DECLARE estas variáveis
                        let currentYear = -1, monthsInCurrentYear = 0;

                        let totalMonths = 0;
                        while (currentDate <= dataMax && totalMonths < 240) {{
                            const year = currentDate.getUTCFullYear();
                            if (year !== currentYear) {{
                                if (currentYear !== -1) yearsData.push({{ year: currentYear, count: monthsInCurrentYear }});
                                currentYear = year; 
                                monthsInCurrentYear = 0;
                            }}
                            const monthNumber = String(currentDate.getUTCMonth() + 1).padStart(2, '0');
                            monthHtml += `<div class="month-cell">${{monthNumber}}</div>`;
                            monthsInCurrentYear++;
                            currentDate.setUTCMonth(currentDate.getUTCMonth() + 1);
                            totalMonths++;
                        }}
                        if (currentYear !== -1) yearsData.push({{ year: currentYear, count: monthsInCurrentYear }});
                        yearsData.forEach(data => {{ 
                            const yearWidth = data.count * PIXELS_PER_MONTH; 
                            yearHtml += `<div class="year-section" style="width:${{yearWidth}}px">${{data.year}}</div>`; 
                        }});

                        const chartContainer = document.getElementById('chart-container-{project["id"]}');
                        if (chartContainer) {{
                            chartContainer.style.minWidth = `${{totalMonths * PIXELS_PER_MONTH}}px`;
                        }}

                        yearHeader.innerHTML = yearHtml;
                        monthHeader.innerHTML = monthHtml;
                    }}

                    function renderChart() {{
                        const chartBody = document.getElementById('chart-body-{project["id"]}');
                        const gruposGantt = JSON.parse(document.getElementById('grupos-gantt-data').textContent);
                        const tasks = projectData[0].tasks;
                        
                        if (!tasks || tasks.length === 0) {{
                            chartBody.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">Nenhuma tarefa disponível</div>';
                            return;
                        }}
                        
                        chartBody.innerHTML = '';
                        const groupKeys = Object.keys(gruposGantt);
                        let rowIndex = 0;
                        
                        for (let i = 0; i < groupKeys.length; i++) {{
                            const grupo = groupKeys[i];
                            const tasksInGroup = gruposGantt[grupo].filter(etapaNome => tasks.some(t => t.name === etapaNome && !t.isSubtask));
                            if (tasksInGroup.length === 0) continue;
                            
                            gruposGantt[grupo].forEach(etapaNome => {{
                                const task = tasks.find(t => t.name === etapaNome && !t.isSubtask);
                                if (task) {{
                                    // Linha principal
                                    const row = document.createElement('div'); 
                                    row.className = 'gantt-row';
                                    row.setAttribute('data-task', task.name);
                                    
                                    let barPrevisto = null;
                                    if (tipoVisualizacao === 'Ambos' || tipoVisualizacao === 'Previsto') {{ 
                                        barPrevisto = createBar(task, 'previsto'); 
                                        if (barPrevisto) row.appendChild(barPrevisto); 
                                    }}
                                    let barReal = null;
                                    if ((tipoVisualizacao === 'Ambos' || tipoVisualizacao === 'Real') && task.start_real && (task.end_real_original_raw || task.end_real)) {{ 
                                        barReal = createBar(task, 'real'); 
                                        if (barReal) row.appendChild(barReal); 
                                    }}
                                    if (barPrevisto && barReal) {{
                                        const s_prev = parseDate(task.start_previsto), e_prev = parseDate(task.end_previsto), s_real = parseDate(task.start_real), e_real = parseDate(task.end_real_original_raw || task.end_real);
                                        if (s_prev && e_prev && s_real && e_real && s_real <= s_prev && e_real >= e_prev) {{ 
                                            barPrevisto.style.zIndex = '8'; 
                                            barReal.style.zIndex = '7'; 
                                        }}
                                        renderOverlapBar(task, row);
                                    }}
                                    chartBody.appendChild(row);
                                    rowIndex++;
                                    
                                    // Aplica estilo se a tarefa pai estiver expandida
                                    if (task.expanded) {{
                                        updateParentTaskBarStyle(task.name, true);
                                    }}
                                    
                                    // Subetapas - SEMPRE criar as linhas, mas controlar visibilidade via CSS
                                    if (SUBETAPAS[task.name]) {{
                                        SUBETAPAS[task.name].forEach(subetapaNome => {{
                                            const subetapa = tasks.find(t => t.name === subetapaNome && t.isSubtask);
                                            if (subetapa) {{
                                                const subtaskRow = document.createElement('div'); 
                                                subtaskRow.className = 'gantt-row gantt-subtask-row';
                                                subtaskRow.setAttribute('data-parent', task.name);
                                                // Inicialmente oculto - será mostrado via toggle
                                                subtaskRow.style.display = task.expanded ? 'block' : 'none';
                                                if (task.expanded) {{
                                                    subtaskRow.classList.add('visible');
                                                }}
                                                
                                                let subBarPrevisto = null;
                                                if (tipoVisualizacao === 'Ambos' || tipoVisualizacao === 'Previsto') {{ 
                                                    subBarPrevisto = createBar(subetapa, 'previsto'); 
                                                    if (subBarPrevisto) subtaskRow.appendChild(subBarPrevisto); 
                                                }}
                                                let subBarReal = null;
                                                if ((tipoVisualizacao === 'Ambos' || tipoVisualizacao === 'Real') && subetapa.start_real && (subetapa.end_real_original_raw || subetapa.end_real)) {{ 
                                                    subBarReal = createBar(subetapa, 'real'); 
                                                    if (subBarReal) subtaskRow.appendChild(subBarReal); 
                                                }}
                                                if (subBarPrevisto && subBarReal) {{
                                                    const s_prev = parseDate(subetapa.start_previsto), e_prev = parseDate(subetapa.end_previsto), s_real = parseDate(subetapa.start_real), e_real = parseDate(subetapa.end_real_original_raw || subetapa.end_real);
                                                    if (s_prev && e_prev && s_real && e_real && s_real <= s_prev && e_real >= e_prev) {{ 
                                                        subBarPrevisto.style.zIndex = '8'; 
                                                        subBarReal.style.zIndex = '7'; 
                                                    }}
                                                    renderOverlapBar(subetapa, subtaskRow);
                                                }}
                                                chartBody.appendChild(subtaskRow);
                                                rowIndex++;
                                            }}
                                        }});
                                    }}
                                }}
                            }});
                            
                            if (i < groupKeys.length - 1 && tasksInGroup.length > 0) {{
                                const nextGroupKey = groupKeys[i + 1];
                                const nextGroupTasks = gruposGantt[nextGroupKey].filter(etapaNome => tasks.some(t => t.name === etapaNome && !t.isSubtask));
                                if (nextGroupTasks.length > 0) {{
                                    const spacerRow = document.createElement('div');
                                    spacerRow.className = 'gantt-row-spacer';
                                    chartBody.appendChild(spacerRow);
                                    rowIndex++;
                                }}
                            }}
                        }}
                    }}

                    function createBar(task, tipo) {{
                        const startDate = parseDate(tipo === 'previsto' ? task.start_previsto : task.start_real);
                        const endDate = parseDate(tipo === 'previsto' ? task.end_previsto : (task.end_real_original_raw || task.end_real));

                        if (!startDate || !endDate) {{
                            console.log('Datas inválidas para barra:', task.name, tipo);
                            return null;
                        }}
                        
                        const left = getPosition(startDate);
                        const width = Math.max(getPosition(endDate) - left + (PIXELS_PER_MONTH / 30), 5); // Mínimo de 5px
                        
                        if (width <= 0) {{
                            console.log('Largura inválida para barra:', task.name, tipo, width);
                            return null;
                        }}
                        
                        const bar = document.createElement('div'); 
                        bar.className = `gantt-bar ${{tipo}}`;
                        const coresSetor = coresPorSetor[task.setor] || coresPorSetor['Não especificado'] || {{previsto: '#cccccc', real: '#888888'}};
                        bar.style.backgroundColor = tipo === 'previsto' ? coresSetor.previsto : coresSetor.real;
                        bar.style.left = `${{left}}px`; 
                        bar.style.width = `${{width}}px`;
                        
                        // Adicionar rótulo apenas se houver espaço suficiente
                        if (width > 40) {{
                            const barLabel = document.createElement('span'); 
                            barLabel.className = 'bar-label'; 
                            barLabel.textContent = `${{task.name}} (${{task.progress}}%)`; 
                            bar.appendChild(barLabel);
                        }}
                        
                        bar.addEventListener('mousemove', e => showTooltip(e, task, tipo));
                        bar.addEventListener('mouseout', () => hideTooltip());
                        return bar;
                    }}

                    function renderOverlapBar(task, row) {{
                        if (!task.start_real || !(task.end_real_original_raw || task.end_real)) return;
                        const s_prev = parseDate(task.start_previsto), e_prev = parseDate(task.end_previsto), s_real = parseDate(task.start_real), e_real = parseDate(task.end_real_original_raw || task.end_real);
                        const overlap_start = new Date(Math.max(s_prev, s_real)), overlap_end = new Date(Math.min(e_prev, e_real));
                        if (overlap_start < overlap_end) {{
                            const left = getPosition(overlap_start), width = getPosition(overlap_end) - left + (PIXELS_PER_MONTH / 30);
                            if (width > 0) {{ 
                                const overlapBar = document.createElement('div'); 
                                overlapBar.className = 'gantt-bar-overlap'; 
                                overlapBar.style.left = `${{left}}px`; 
                                overlapBar.style.width = `${{width}}px`; 
                                row.appendChild(overlapBar); 
                            }}
                        }}
                    }}

                    function getPosition(date) {{
                        if (!date) return 0;
                        const chartStart = parseDate(activeDataMinStr);
                        if (!chartStart || isNaN(chartStart.getTime())) return 0;

                        const monthsOffset = (date.getUTCFullYear() - chartStart.getUTCFullYear()) * 12 + (date.getUTCMonth() - chartStart.getUTCMonth());
                        const dayOfMonth = date.getUTCDate() - 1;
                        const daysInMonth = new Date(date.getUTCFullYear(), date.getUTCMonth() + 1, 0).getUTCDate();
                        const fractionOfMonth = daysInMonth > 0 ? dayOfMonth / daysInMonth : 0;
                        return (monthsOffset + fractionOfMonth) * PIXELS_PER_MONTH;
                    }}

                    function positionTodayLine() {{
                        const todayLine = document.getElementById('today-line-{project["id"]}');
                        const today = new Date(), todayUTC = new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()));

                        const chartStart = parseDate(activeDataMinStr);
                        const chartEnd = parseDate(activeDataMaxStr);

                        if (chartStart && chartEnd && !isNaN(chartStart.getTime()) && !isNaN(chartEnd.getTime()) && todayUTC >= chartStart && todayUTC <= chartEnd) {{ 
                            const offset = getPosition(todayUTC); 
                            todayLine.style.left = `${{offset}}px`; 
                            todayLine.style.display = 'block'; 
                        }} else {{ 
                            todayLine.style.display = 'none'; 
                        }}
                    }}

                    function positionMetaLine() {{
                        const metaLine = document.getElementById('meta-line-{project["id"]}'), metaLabel = document.getElementById('meta-line-label-{project["id"]}');
                        const metaDateStr = projectData[0].meta_assinatura_date;
                        if (!metaDateStr) {{ metaLine.style.display = 'none'; metaLabel.style.display = 'none'; return; }}

                        const metaDate = parseDate(metaDateStr);
                        const chartStart = parseDate(activeDataMinStr);
                        const chartEnd = parseDate(activeDataMaxStr);

                        if (metaDate && chartStart && chartEnd && !isNaN(metaDate.getTime()) && !isNaN(chartStart.getTime()) && !isNaN(chartEnd.getTime()) && metaDate >= chartStart && metaDate <= chartEnd) {{ 
                            const offset = getPosition(metaDate); 
                            metaLine.style.left = `${{offset}}px`; 
                            metaLabel.style.left = `${{offset}}px`; 
                            metaLine.style.display = 'block'; 
                            metaLabel.style.display = 'block'; 
                            metaLabel.textContent = `Meta: ${{metaDate.toLocaleDateString('pt-BR', {{day: '2-digit', month: '2-digit', year: '2-digit', timeZone: 'UTC'}})}}`; 
                        }} else {{ 
                            metaLine.style.display = 'none'; 
                            metaLabel.style.display = 'none'; 
                        }}
                    }}

                    function showTooltip(e, task, tipo) {{
                        const tooltip = document.getElementById('tooltip-{project["id"]}');
                        let content = `<b>${{task.name}}</b><br>`;
                        if (tipo === 'previsto') {{ content += `Previsto: ${{task.inicio_previsto}} - ${{task.termino_previsto}}<br>Duração: ${{task.duracao_prev_meses}}M`; }} else {{ content += `Real: ${{task.inicio_real}} - ${{task.termino_real}}<br>Duração: ${{task.duracao_real_meses}}M<br>Variação Término: ${{task.vt_text}}<br>Variação Duração: ${{task.vd_text}}`; }}
                        content += `<br><b>Progresso: ${{task.progress}}%</b><br>Setor: ${{task.setor}}<br>Grupo: ${{task.grupo}}`;
                        tooltip.innerHTML = content;
                        tooltip.classList.add('show');
                        const tooltipWidth = tooltip.offsetWidth;
                        const tooltipHeight = tooltip.offsetHeight;
                        const viewportWidth = window.innerWidth;
                        const viewportHeight = window.innerHeight;
                        const mouseX = e.clientX; 
                        const mouseY = e.clientY;
                        const padding = 15;
                        let left, top;
                        if ((mouseX + padding + tooltipWidth) > viewportWidth) {{
                            left = mouseX - padding - tooltipWidth;
                        }} else {{
                            left = mouseX + padding;
                        }}
                        if ((mouseY + padding + tooltipHeight) > viewportHeight) {{
                            top = mouseY - padding - tooltipHeight;
                        }} else {{
                            top = mouseY + padding;
                        }}
                        if (left < padding) left = padding;
                        if (top < padding) top = padding;
                        tooltip.style.left = `${{left}}px`;
                        tooltip.style.top = `${{top}}px`;
                    }}

                    function hideTooltip() {{ 
                        document.getElementById('tooltip-{project["id"]}').classList.remove('show'); 
                    }}

                    function renderMonthDividers() {{
                        const chartContainer = document.getElementById('chart-container-{project["id"]}');
                        chartContainer.querySelectorAll('.month-divider, .month-divider-label').forEach(el => el.remove());

                        let currentDate = parseDate(activeDataMinStr);
                        const dataMax = parseDate(activeDataMaxStr);

                        if (!currentDate || !dataMax || isNaN(currentDate.getTime()) || isNaN(dataMax.getTime())) return;

                        let totalMonths = 0;
                        while (currentDate <= dataMax && totalMonths < 240) {{
                            const left = getPosition(currentDate);
                            const divider = document.createElement('div'); 
                            divider.className = 'month-divider';
                            if (currentDate.getUTCMonth() === 0) divider.classList.add('first');
                            divider.style.left = `${{left}}px`; 
                            chartContainer.appendChild(divider);
                            currentDate.setUTCMonth(currentDate.getUTCMonth() + 1);
                            totalMonths++;
                        }}
                    }}

                    function setupEventListeners() {{
                        const ganttChartContent = document.getElementById('gantt-chart-content-{project["id"]}'), sidebarContent = document.getElementById('gantt-sidebar-content-{project['id']}');
                        const fullscreenBtn = document.getElementById('fullscreen-btn-{project["id"]}'), toggleBtn = document.getElementById('toggle-sidebar-btn-{project['id']}');
                        const filterBtn = document.getElementById('filter-btn-{project["id"]}');
                        const filterMenu = document.getElementById('filter-menu-{project['id']}');
                        const container = document.getElementById('gantt-container-{project["id"]}');

                        const applyBtn = document.getElementById('filter-apply-btn-{project["id"]}');
                        if (applyBtn) applyBtn.addEventListener('click', () => applyFiltersAndRedraw());

                        if (fullscreenBtn) fullscreenBtn.addEventListener('click', () => toggleFullscreen());

                        // Adiciona listener para o botão de filtro
                        if (filterBtn) {{
                            filterBtn.addEventListener('click', () => {{
                                filterMenu.classList.toggle('is-open');
                            }});
                        }}

                        // Fecha o menu de filtro ao clicar fora
                        document.addEventListener('click', (event) => {{
                            if (filterMenu && filterBtn && !filterMenu.contains(event.target) && !filterBtn.contains(event.target)) {{
                                filterMenu.classList.remove('is-open');
                            }}
                        }});

                        if (container) container.addEventListener('fullscreenchange', () => handleFullscreenChange());

                        if (toggleBtn) toggleBtn.addEventListener('click', () => toggleSidebar());
                        if (ganttChartContent && sidebarContent) {{
                            let isSyncing = false;
                            ganttChartContent.addEventListener('scroll', () => {{ if (!isSyncing) {{ isSyncing = true; sidebarContent.scrollTop = ganttChartContent.scrollTop; isSyncing = false; }} }});
                            sidebarContent.addEventListener('scroll', () => {{ if (!isSyncing) {{ isSyncing = true; ganttChartContent.scrollTop = sidebarContent.scrollTop; isSyncing = false; }} }});
                            let isDown = false, startX, scrollLeft;
                            ganttChartContent.addEventListener('mousedown', (e) => {{ isDown = true; ganttChartContent.classList.add('active'); startX = e.pageX - ganttChartContent.offsetLeft; scrollLeft = ganttChartContent.scrollLeft; }});
                            ganttChartContent.addEventListener('mouseleave', () => {{ isDown = false; ganttChartContent.classList.remove('active'); }});
                            ganttChartContent.addEventListener('mouseup', () => {{ isDown = false; ganttChartContent.classList.remove('active'); }});
                            ganttChartContent.addEventListener('mousemove', (e) => {{ if (!isDown) return; e.preventDefault(); const x = e.pageX - ganttChartContent.offsetLeft; const walk = (x - startX) * 2; ganttChartContent.scrollLeft = scrollLeft - walk; }});
                        }}
                    }}

                    function toggleSidebar() {{ 
                        document.getElementById('gantt-sidebar-wrapper-{project["id"]}').classList.toggle('collapsed'); 
                    }}

                    function updatePulmaoInputVisibility() {{
                        const radioCom = document.getElementById('filter-pulmao-com-{project["id"]}');
                        const mesesGroup = document.getElementById('pulmao-meses-group-{project["id"]}');
                        if (radioCom && mesesGroup) {{ 
                            if (radioCom.checked) {{
                                mesesGroup.style.display = 'block';
                            }} else {{
                                mesesGroup.style.display = 'none';
                            }}
                        }}
                    }}

                    function resetToInitialState() {{
                        currentProjectIndex = initialProjectIndex;
                        const initialProject = allProjectsData[initialProjectIndex];

                        projectData = [JSON.parse(JSON.stringify(initialProject))];
                        // Reorganizar tasks com estrutura de subetapas
                        projectData[0].tasks = organizarTasksComSubetapas(projectData[0].tasks);
                        allTasks_baseData = JSON.parse(JSON.stringify(projectData[0].tasks));

                        tipoVisualizacao = initialTipoVisualizacao;
                        pulmaoStatus = initialPulmaoStatus;

                        applyInitialPulmaoState();

                        activeDataMinStr = dataMinStr;
                        activeDataMaxStr = dataMaxStr;

                        if (initialPulmaoStatus === 'Com Pulmão' && initialPulmaoMeses > 0) {{
                            const {{ min: newMinStr, max: newMaxStr }} = findNewDateRange(projectData[0].tasks);
                            const newMin = parseDate(newMinStr);
                            const newMax = parseDate(newMaxStr);
                            const originalMin = parseDate(activeDataMinStr);
                            const originalMax = parseDate(activeDataMaxStr);

                            let finalMinDate = originalMin;
                            if (newMin && newMin < finalMinDate) {{
                                finalMinDate = newMin;
                            }}
                            let finalMaxDate = originalMax;
                            if (newMax && newMax > finalMaxDate) {{
                                finalMaxDate = newMax;
                            }}

                            finalMinDate = new Date(finalMinDate.getTime());
                            finalMaxDate = new Date(finalMaxDate.getTime());
                            finalMinDate.setUTCDate(1);
                            finalMaxDate.setUTCMonth(finalMaxDate.getUTCMonth() + 1, 0);

                            activeDataMinStr = finalMinDate.toISOString().split('T')[0];
                            activeDataMaxStr = finalMaxDate.toISOString().split('T')[0];
                        }}

                        document.getElementById('filter-project-{project["id"]}').value = initialProjectIndex;
                        
                        // *** CORREÇÃO: Reset Virtual Select ***
                        if(vsUgb) vsUgb.setValue(["Todas"]);
                        if(vsSetor) vsSetor.setValue(["Todos"]);
                        if(vsGrupo) vsGrupo.setValue(["Todos"]);
                        if(vsEtapa) vsEtapa.setValue(["Todas"]);
                        
                        document.getElementById('filter-concluidas-{project["id"]}').checked = false;

                        const visRadio = document.querySelector('input[name="filter-vis-{project['id']}"][value="' + initialTipoVisualizacao + '"]');
                        if (visRadio) visRadio.checked = true;

                        const pulmaoRadio = document.querySelector('input[name="filter-pulmao-{project['id']}"][value="' + initialPulmaoStatus + '"]');
                        if (pulmaoRadio) pulmaoRadio.checked = true;

                        document.getElementById('filter-pulmao-meses-{project["id"]}').value = initialPulmaoMeses;

                        updatePulmaoInputVisibility();

                        renderHeader();
                        renderMonthDividers();
                        renderSidebar();
                        renderChart();
                        positionTodayLine();
                        positionMetaLine();
                        updateProjectTitle();
                        
                        // *** ATUALIZAR BASELINE PARA O EMPREENDIMENTO INICIAL ***
                        updateBaselineDropdownForProject(projectData[0].name);
                    }}

                    function updateProjectTitle() {{
                        const projectTitle = document.querySelector('#gantt-sidebar-wrapper-{project["id"]} .project-title-row span');
                        if (projectTitle) {{
                            projectTitle.textContent = projectData[0].name;
                        }}
                    }}

                    function toggleFullscreen() {{
                        const container = document.getElementById('gantt-container-{project["id"]}');
                        if (!document.fullscreenElement) {{
                            container.requestFullscreen().catch(err => alert('Erro: ' + err.message));
                        }} else {{
                            document.exitFullscreen();
                        }}
                    }}

                    function toggleFullscreen() {{
                        const container = document.getElementById('gantt-container-{project["id"]}');
                        if (!document.fullscreenElement) {{
                            container.requestFullscreen().catch(err => console.error('Erro ao tentar entrar em tela cheia: ' + err.message));
                        }} else {{
                            document.exitFullscreen();
                        }}
                    }}

                    function handleFullscreenChange() {{
                        const btn = document.getElementById('fullscreen-btn-{project["id"]}');
                        const container = document.getElementById('gantt-container-{project["id"]}');
                        if (document.fullscreenElement === container) {{
                            btn.innerHTML = '<span><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 9l6 6m0-6l-6 6M3 20.29V5a2 2 0 012-2h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2v-.29"></path></svg></span>';
                            btn.classList.add('is-fullscreen');
                        }} else {{
                            btn.innerHTML = '<span><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path></svg></span>';
                            btn.classList.remove('is-fullscreen');
                            document.getElementById('filter-menu-{project["id"]}').classList.remove('is-open');
                        }}
                    }}
                    
                    // Função para atualizar opções de empreendimento baseado nas UGBs selecionadas
                    function updateEmpreendimentoOptions() {{
                        console.log('🔄 updateEmpreendimentoOptions() chamada');
                        
                        const selUgbArray = vsUgb ? vsUgb.getValue() || [] : [];
                        console.log('📋 UGBs selecionadas:', selUgbArray);
                        
                        const selProject = document.getElementById('filter-project-{project["id"]}');
                        
                        // Debug: mostrar todos os projetos e suas UGBs
                        console.log('📊 Total de projetos disponíveis:', allProjectsData.length);
                        allProjectsData.forEach((proj, idx) => {{
                            const ugbsDoProjeto = [...new Set(proj.tasks.map(t => t.ugb).filter(u => u))];
                            console.log(`  Projeto ${{idx}}: ${{proj.name}} - UGBs: [${{ugbsDoProjeto.join(', ')}}]`);
                        }});
                        
                        // Limpar opções atuais
                        selProject.innerHTML = '';
                        
                        // Filtrar projetos por UGB
                        let filteredProjects = allProjectsData;
                        if (selUgbArray.length > 0 && !selUgbArray.includes('Todas')) {{
                            console.log('🔍 Filtrando por UGBs:', selUgbArray);
                            filteredProjects = allProjectsData.filter(proj => {{
                                // Verificar se o projeto tem tasks com UGB selecionada
                                const hasMatchingUgb = proj.tasks.some(task => {{
                                    const match = selUgbArray.includes(task.ugb);
                                    if (match) {{
                                        console.log(`    ✓ Match: ${{proj.name}} tem task com UGB=${{task.ugb}}`);
                                    }}
                                    return match;
                                }});
                                return hasMatchingUgb;
                            }});
                            console.log('✅ Projetos após filtro:', filteredProjects.length);
                        }} else {{
                            console.log('📌 Mostrando todos os projetos (UGB = Todas ou vazio)');
                        }}
                        
                        // Repovoar select de empreendimento com projetos filtrados
                        filteredProjects.forEach((proj, index) => {{
                            const originalIndex = allProjectsData.indexOf(proj);
                            const isSelected = (originalIndex === currentProjectIndex) ? 'selected' : '';
                            selProject.innerHTML += '<option value="' + originalIndex + '" ' + isSelected + '>' + proj.name + '</option>';
                        }});
                        
                        console.log('✅ Opções de empreendimento atualizadas. Total:', filteredProjects.length);
                    }}
                    
                    function populateFilters() {{
                        if (filtersPopulated) return;

                        // Nota: Select de projeto agora é populado por updateEmpreendimentoOptions()
                        // após inicializar vsUgb, para garantir consistência com filtro UGB

                        // Configurações comuns para Virtual Select
                        const vsConfig = {{
                            multiple: true,
                            search: true,
                            optionsCount: 6,
                            showResetButton: true,
                            resetButtonText: 'Limpar',
                            selectAllText: 'Selecionar Todos',
                            allOptionsSelectedText: 'Todos',
                            optionsSelectedText: 'selecionados',
                            searchPlaceholderText: 'Buscar...',
                            optionHeight: '30px',
                            popupDropboxBreakpoint: '3000px',
                            noOptionsText: 'Nenhuma opção encontrada',
                            noSearchResultsText: 'Nenhum resultado encontrado',
                        }};

                        // Prepara opções e inicializa Virtual Select para UGB
                        // Validação de segurança: garantir que ugbs existe
                        const ugbOptions = (filterOptions.ugbs || ["Todas"]).map(u => ({{ label: u, value: u }}));
                        vsUgb = VirtualSelect.init({{
                            ...vsConfig,
                            ele: '#filter-ugb-{project["id"]}',
                            options: ugbOptions,
                            placeholder: "Selecionar UGB(s)",
                            selectedValue: ["Todas"]
                        }});
                        
                        // Listener para atualizar opções de empreendimento quando UGB mudar
                        document.querySelector('#filter-ugb-{project["id"]}').addEventListener('change', function() {{
                            updateEmpreendimentoOptions();
                        }});
                        
                        // Popular select de empreendimento inicialmente
                        updateEmpreendimentoOptions();

                        // Prepara opções e inicializa Virtual Select para Setor
                        const setorOptions = filterOptions.setores.map(s => ({{ label: s, value: s }}));
                        vsSetor = VirtualSelect.init({{
                            ...vsConfig,
                            ele: '#filter-setor-{project["id"]}',
                            options: setorOptions,
                            placeholder: "Selecionar Setor(es)",
                            selectedValue: ["Todos"]
                        }});

                        // Prepara opções e inicializa Virtual Select para Grupo
                        const grupoOptions = filterOptions.grupos.map(g => ({{ label: g, value: g }}));
                        vsGrupo = VirtualSelect.init({{
                            ...vsConfig,
                            ele: '#filter-grupo-{project["id"]}',
                            options: grupoOptions,
                            placeholder: "Selecionar Grupo(s)",
                            selectedValue: ["Todos"]
                        }});

                        // Prepara opções e inicializa Virtual Select para Etapa
                        const etapaOptions = filterOptions.etapas.map(e => ({{ label: e, value: e }}));
                        vsEtapa = VirtualSelect.init({{
                            ...vsConfig,
                            ele: '#filter-etapa-{project["id"]}',
                            options: etapaOptions,
                            placeholder: "Selecionar Etapa(s)",
                            selectedValue: ["Todas"]
                        }});

                        // Configura os radios de visualização
                        const visRadio = document.querySelector('input[name="filter-vis-{project['id']}"][value="' + initialTipoVisualizacao + '"]');
                        if (visRadio) visRadio.checked = true;

                        // Configura os radios e input de Pulmão
                        const radioCom = document.getElementById('filter-pulmao-com-{project["id"]}');
                        const radioSem = document.getElementById('filter-pulmao-sem-{project["id"]}');

                        radioCom.addEventListener('change', updatePulmaoInputVisibility);
                        radioSem.addEventListener('change', updatePulmaoInputVisibility);

                        const pulmaoRadioInitial = document.querySelector('input[name="filter-pulmao-{project['id']}"][value="' + initialPulmaoStatus + '"]');
                        if(pulmaoRadioInitial) pulmaoRadioInitial.checked = true;

                        document.getElementById('filter-pulmao-meses-{project["id"]}').value = initialPulmaoMeses;

                        updatePulmaoInputVisibility();

                        filtersPopulated = true;
                    }}

                    // *** FUNÇÃO applyFiltersAndRedraw ATUALIZADA ***
                    function applyFiltersAndRedraw() {{
                        try {{
                            const selProjectElement = document.getElementById('filter-project-{project["id"]}');
                            
                            // Validar se o select tem opções
                            if (!selProjectElement || selProjectElement.options.length === 0) {{
                                console.warn('⚠️ Select de empreendimento está vazio. Não é possível aplicar filtros.');
                                alert('Nenhum empreendimento disponível com as UGBs selecionadas. Ajuste o filtro de UGB.');
                                return;
                            }}
                            
                            const selProjectIndex = parseInt(selProjectElement.value, 10);
                            
                            // Validar se o índice é válido
                            if (isNaN(selProjectIndex)) {{
                                console.warn('⚠️ Índice de projeto inválido:', selProjectElement.value);
                                return;
                            }}
                            
                            // *** LEITURA CORRIGIDA dos Virtual Select ***
                            // Nota: UGB não é lido aqui pois apenas filtra opções de empreendimento, não tarefas
                            const selSetorArray = vsSetor ? vsSetor.getValue() || [] : [];
                            const selGrupoArray = vsGrupo ? vsGrupo.getValue() || [] : [];
                            const selEtapaArray = vsEtapa ? vsEtapa.getValue() || [] : [];
                            
                            const selConcluidas = document.getElementById('filter-concluidas-{project["id"]}').checked;
                            const selVis = document.querySelector('input[name="filter-vis-{project['id']}"]:checked').value;
                            const selPulmao = document.querySelector('input[name="filter-pulmao-{project['id']}"]:checked').value;
                            const selPulmaoMeses = parseInt(document.getElementById('filter-pulmao-meses-{project["id"]}').value, 10) || 0;

                            console.log('Filtros aplicados:', {{
                                projeto: selProjectIndex,
                                setor: selSetorArray,
                                grupo: selGrupoArray,
                                etapa: selEtapaArray,
                                concluidas: selConcluidas,
                                visualizacao: selVis,
                                pulmao: selPulmao,
                                mesesPulmao: selPulmaoMeses
                            }});

                            // *** FECHAR MENU DE FILTROS ***
                            document.getElementById('filter-menu-{project["id"]}').classList.remove('is-open');

                            if (selProjectIndex !== currentProjectIndex) {{
                                currentProjectIndex = selProjectIndex;
                                const newProject = allProjectsData[selProjectIndex];
                                projectData = [JSON.parse(JSON.stringify(newProject))];
                                // Reorganizar tasks com estrutura de subetapas
                                projectData[0].tasks = organizarTasksComSubetapas(projectData[0].tasks);
                                allTasks_baseData = JSON.parse(JSON.stringify(projectData[0].tasks));
                                
                                // *** ATUALIZAR BASELINE PARA O NOVO EMPREENDIMENTO ***
                                const newProjectName = newProject.name;
                                updateBaselineDropdownForProject(newProjectName);
                            }}

                            let baseTasks = JSON.parse(JSON.stringify(allTasks_baseData));

                            // *** DEBUG DETALHADO DOS GRUPOS ***
                            console.log('=== DEBUG GRUPOS ===');
                            console.log('Total de tasks base:', baseTasks.length);
                            console.log('Grupos disponíveis nas tasks:', [...new Set(baseTasks.map(t => t.grupo))]);
                            console.log('Filtrando por grupo:', selGrupoArray);
                            
                            // Verificar tasks que deveriam passar no filtro
                            const tasksComGrupoFiltrado = baseTasks.filter(t => {{
                                const passaFiltro = selGrupoArray.includes(t.grupo);
                                if (passaFiltro) {{
                                    console.log('Task que passa no filtro:', t.name, '- Grupo:', t.grupo);
                                }}
                                return passaFiltro;
                            }});
                            console.log('Tasks que pertencem ao grupo filtrado:', tasksComGrupoFiltrado.length);
                            console.log('=== FIM DEBUG ===');

                            // *** APLICAR FILTROS PRIMEIRO (antes de pulmão/baseline) ***
                            let filteredTasks = baseTasks;

                            // *** LÓGICA DE FILTRO CORRIGIDA ***
                            // Nota: Filtro de UGB não filtra tarefas, apenas opções de empreendimento
                            
                            // Filtro por Setor
                            if (selSetorArray.length > 0 && !selSetorArray.includes('Todos')) {{
                                filteredTasks = filteredTasks.filter(t => selSetorArray.includes(t.setor));
                                console.log('Após filtro setor:', filteredTasks.length);
                            }}
                            
                            // Filtro por Grupo - CORREÇÃO PRINCIPAL
                            if (selGrupoArray.length > 0 && !selGrupoArray.includes('Todos')) {{
                                filteredTasks = filteredTasks.filter(t => selGrupoArray.includes(t.grupo));
                                console.log('Após filtro grupo:', filteredTasks.length);
                                
                                // DEBUG adicional
                                if (filteredTasks.length === 0) {{
                                    console.warn('⚠️ NENHUMA TASK PASSOU NO FILTRO DE GRUPO!');
                                    console.log('Grupos filtrados:', selGrupoArray);
                                    console.log('Grupos disponíveis:', [...new Set(baseTasks.map(t => t.grupo))]);
                                }}
                            }}
                            
                            // Filtro por Etapa
                            if (selEtapaArray.length > 0 && !selEtapaArray.includes('Todas')) {{
                                filteredTasks = filteredTasks.filter(t => selEtapaArray.includes(t.name));
                                console.log('Após filtro etapa:', filteredTasks.length);
                            }}

                            // Filtro por Concluídas
                            if (selConcluidas) {{
                                filteredTasks = filteredTasks.filter(t => t.progress < 100);
                                console.log('Após filtro concluídas:', filteredTasks.length);
                            }}

                            console.log('Tasks após filtros:', filteredTasks.length);
                            console.log('Tasks filtradas:', filteredTasks);

                            // Se não há tasks após filtrar, mostrar mensagem mas permitir continuar
                            if (filteredTasks.length === 0) {{
                                console.warn('Nenhuma task passou pelos filtros aplicados');
                                // Não interromper o processo, deixar que o renderSidebar mostre a mensagem apropriada
                            }}

                            // Atualizar dados
                            projectData[0].tasks = filteredTasks;
                            tipoVisualizacao = selVis;
                            
                            // *** NOVA ORDEM: 1) REAPLICAR BASELINE (se ativa) ***
                            console.log('🔄 Verificando baseline ativa:', currentActiveBaseline);
                            if (currentActiveBaseline && currentActiveBaseline !== 'P0-(padrão)') {{
                                console.log('📊 Reaplicando baseline:', currentActiveBaseline);
                                reapplyActiveBaseline(projectData[0].tasks);
                            }} else {{
                                console.log('📋 Usando dados P0 (padrão - sem baseline)');
                            }}
                            
                            // *** NOVA ORDEM: 2) APLICAR PULMÃO SOBRE A BASELINE ***
                            if (selPulmao === 'Com Pulmão' && selPulmaoMeses > 0) {{
                                const offsetMeses = -selPulmaoMeses;
                                console.log("🔧 Aplicando pulmão de", selPulmaoMeses, "meses SOBRE a baseline ativa");
                                
                                projectData[0].tasks.forEach(task => {{
                                    const etapaNome = task.name;
                                    
                                    if (etapas_sem_alteracao.includes(etapaNome)) {{
                                        // Não altera datas
                                        console.log('  ⏸️ Etapa protegida (sem alteração):', etapaNome);
                                    }}
                                    else if (etapas_pulmao.includes(etapaNome)) {{
                                        // Apenas datas previstas - só ajusta início
                                        const oldStart = task.start_previsto;
                                        task.start_previsto = addMonths(task.start_previsto, offsetMeses);
                                        task.inicio_previsto = formatDateDisplay(task.start_previsto);
                                        console.log('  📅 Pulmão ' + etapaNome + ':', oldStart, '→', task.start_previsto);
                                        
                                        // Recalcular campos de exibição
                                        updateTaskDisplayFields(task);
                                    }}
                                    else {{
                                        // Apenas datas previstas - ajusta início e término
                                        const oldStart = task.start_previsto;
                                        const oldEnd = task.end_previsto;
                                        task.start_previsto = addMonths(task.start_previsto, offsetMeses);
                                        task.end_previsto = addMonths(task.end_previsto, offsetMeses);
                                        
                                        task.inicio_previsto = formatDateDisplay(task.start_previsto);
                                        task.termino_previsto = formatDateDisplay(task.end_previsto);
                                        console.log('  ⏩ ' + etapaNome + ':', oldStart, '→', task.start_previsto);
                                        
                                        // Recalcular campos de exibição
                                        updateTaskDisplayFields(task);
                                    }}
                                }});
                            }} else {{
                                console.log('⏸️ Pulmão desativado');
                            }}

                            // Recalcular range de datas apenas se houver tasks
                            if (filteredTasks.length > 0) {{
                                const {{ min: newMinStr, max: newMaxStr }} = findNewDateRange(filteredTasks);
                                const newMin = parseDate(newMinStr);
                                const newMax = parseDate(newMaxStr);
                                const originalMin = parseDate(dataMinStr);
                                const originalMax = parseDate(dataMaxStr);

                                let finalMinDate = originalMin;
                                if (newMin && newMin < finalMinDate) {{
                                    finalMinDate = newMin;
                                }}

                                let finalMaxDate = originalMax;
                                if (newMax && newMax > finalMaxDate) {{
                                    finalMaxDate = newMax;
                                }}

                                finalMinDate = new Date(finalMinDate.getTime());
                                finalMaxDate = new Date(finalMaxDate.getTime());
                                finalMinDate.setUTCDate(1);
                                finalMaxDate.setUTCMonth(finalMaxDate.getUTCMonth() + 1, 0);

                                activeDataMinStr = finalMinDate.toISOString().split('T')[0];
                                activeDataMaxStr = finalMaxDate.toISOString().split('T')[0];
                            }}

                            renderSidebar();
                            renderHeader();
                            renderChart();
                            positionTodayLine();
                            positionMetaLine();
                            updateProjectTitle();

                        }} catch (error) {{
                            console.error('Erro ao aplicar filtros:', error);
                            alert('Erro ao aplicar filtros: ' + error.message);
                        }}
                    }}
                    
                    // DEBUG: Verificar se há dados antes de inicializar
                    console.log('Dados do projeto:', projectData);
                    console.log('Tasks base:', allTasks_baseData);
                    console.log('Dados de baseline completos:', allBaselinesData);
                    
                    // Inicializar o Gantt
                    initGantt();
                </script>
            </body>
            </html>
            """
        # Exibe o componente HTML no Streamlit
        components.html(gantt_html, height=altura_gantt, scrolling=True)
        st.markdown("---")
# --- *** FUNÇÃO gerar_gantt_consolidado MODIFICADA *** ---
def converter_dados_para_gantt_consolidado(df, etapa_selecionada):
    """
    Versão modificada para o Gantt consolidado que também calcula datas de etapas pai
    a partir das subetapas.
    """
    if df.empty:
        return []

    # Filtrar pela etapa selecionada
    sigla_selecionada = nome_completo_para_sigla.get(etapa_selecionada, etapa_selecionada)
    df_filtrado = df[df["Etapa"] == sigla_selecionada].copy()
    
    if df_filtrado.empty:
        return []

    gantt_data = []
    tasks = []

    # Para cada empreendimento na etapa selecionada
    for empreendimento in df_filtrado["Empreendimento"].unique():
        df_emp = df_filtrado[df_filtrado["Empreendimento"] == empreendimento].copy()

        # Aplicar a mesma lógica de cálculo de datas para etapas pai
        etapa_nome_completo = sigla_para_nome_completo.get(sigla_selecionada, sigla_selecionada)
        
        # Se esta etapa é uma etapa pai, calcular datas das subetapas
        if etapa_nome_completo in SUBETAPAS:
            # Buscar todas as subetapas deste empreendimento
            subetapas_siglas = [nome_completo_para_sigla.get(sub, sub) for sub in SUBETAPAS[etapa_nome_completo]]
            subetapas_emp = df[df["Empreendimento"] == empreendimento]
            subetapas_emp = subetapas_emp[subetapas_emp["Etapa"].isin(subetapas_siglas)]
            
            if not subetapas_emp.empty:
                # Calcular datas mínimas e máximas das subetapas
                inicio_real_min = subetapas_emp["Inicio_Real"].min()
                termino_real_max = subetapas_emp["Termino_Real"].max()
                
                # Atualizar as datas da etapa pai com os valores calculados
                if pd.notna(inicio_real_min):
                    df_emp["Inicio_Real"] = inicio_real_min
                if pd.notna(termino_real_max):
                    df_emp["Termino_Real"] = termino_real_max
                
                # Recalcular progresso baseado nas subetapas
                if not subetapas_emp.empty and "% concluído" in subetapas_emp.columns:
                    progress_subetapas = subetapas_emp["% concluído"].apply(converter_porcentagem)
                    df_emp["% concluído"] = progress_subetapas.mean()

        # Processar cada linha (deve ser apenas uma por empreendimento na visão consolidada)
        for i, (idx, row) in enumerate(df_emp.iterrows()):
            start_date = row.get("Inicio_Prevista")
            end_date = row.get("Termino_Prevista")
            start_real = row.get("Inicio_Real")
            end_real_original = row.get("Termino_Real")
            progress = row.get("% concluído", 0)

            # Lógica para tratar datas vazias
            if pd.isna(start_date): 
                start_date = datetime.now()
            if pd.isna(end_date): 
                end_date = start_date + timedelta(days=30)

            end_real_visual = end_real_original
            if pd.notna(start_real) and progress < 100 and pd.isna(end_real_original):
                end_real_visual = datetime.now()

            # Cálculos de duração e variação
            dur_prev_meses = None
            if pd.notna(start_date) and pd.notna(end_date):
                dur_prev_meses = (end_date - start_date).days / 30.4375

            dur_real_meses = None
            if pd.notna(start_real) and pd.notna(end_real_original):
                dur_real_meses = (end_real_original - start_real).days / 30.4375

            vt = calculate_business_days(end_date, end_real_original)
            
            duracao_prevista_uteis = calculate_business_days(start_date, end_date)
            duracao_real_uteis = calculate_business_days(start_real, end_real_original)
            
            vd = None
            if pd.notna(duracao_real_uteis) and pd.notna(duracao_prevista_uteis):
                vd = duracao_real_uteis - duracao_prevista_uteis

            # Lógica de Cor do Status
            status_color_class = 'status-default'
            hoje = pd.Timestamp.now().normalize()
            if progress == 100:
                if pd.notna(end_real_original) and pd.notna(end_date):
                    if end_real_original <= end_date:
                        status_color_class = 'status-green'
                    else:
                        status_color_class = 'status-red'
            elif progress < 100 and pd.notna(end_date) and (end_date < hoje):
                status_color_class = 'status-yellow'

            task = {
                "id": f"t{i}", 
                "name": empreendimento,  # No consolidado, o nome é o empreendimento
                "numero_etapa": i + 1,
                "start_previsto": start_date.strftime("%Y-%m-%d"),
                "end_previsto": end_date.strftime("%Y-%m-%d"),
                "start_real": pd.to_datetime(start_real).strftime("%Y-%m-%d") if pd.notna(start_real) else None,
                "end_real": pd.to_datetime(end_real_visual).strftime("%Y-%m-%d") if pd.notna(end_real_visual) else None,
                "end_real_original_raw": pd.to_datetime(end_real_original).strftime("%Y-%m-%d") if pd.notna(end_real_original) else None,
                "setor": row.get("SETOR", "Não especificado"),
                "grupo": "Consolidado",
                "progress": int(progress),
                "inicio_previsto": start_date.strftime("%d/%m/%y"),
                "termino_previsto": end_date.strftime("%d/%m/%y"),
                "inicio_real": pd.to_datetime(start_real).strftime("%d/%m/%y") if pd.notna(start_real) else "N/D",
                "termino_real": pd.to_datetime(end_real_original).strftime("%d/%m/%y") if pd.notna(end_real_original) else "N/D",
                "duracao_prev_meses": f"{dur_prev_meses:.1f}".replace('.', ',') if dur_prev_meses is not None else "-",
                "duracao_real_meses": f"{dur_real_meses:.1f}".replace('.', ',') if dur_real_meses is not None else "-",
                "vt_text": f"{int(vt):+d}d" if pd.notna(vt) else "-",
                "vd_text": f"{int(vd):+d}d" if pd.notna(vd) else "-",
                "status_color_class": status_color_class
            }
            tasks.append(task)

    # Criar um projeto único para a visão consolidada
    project = {
        "id": "p_consolidado",
        "name": f"Comparativo: {etapa_selecionada}",
        "tasks": tasks,
        "meta_assinatura_date": None
    }
    gantt_data.append(project)

    return gantt_data
# Substitua sua função gerar_gantt_consolidado inteira por esta
def gerar_gantt_consolidado(df, tipo_visualizacao, df_original_para_ordenacao, pulmao_status, pulmao_meses, etapa_selecionada_inicialmente):
    """
    Gera um gráfico de Gantt HTML consolidado que contém dados para TODAS as etapas
    e permite a troca de etapas via menu flutuante.
    
    'etapa_selecionada_inicialmente' define qual etapa mostrar no carregamento.
    """
    # # st.info(f"Exibindo visão comparativa. Etapa inicial: {etapa_selecionada_inicialmente}")

    # --- 1. Preparação dos Dados (MODIFICADO) ---
    df_gantt = df.copy() # df agora tem MÚLTIPLAS etapas

    for col in ["Inicio_Prevista", "Termino_Prevista", "Inicio_Real", "Termino_Real"]:
        if col in df_gantt.columns:
            df_gantt[col] = pd.to_datetime(df_gantt[col], errors="coerce")

    if "% concluído" not in df_gantt.columns: 
        df_gantt["% concluído"] = 0
    df_gantt["% concluído"] = df_gantt["% concluído"].fillna(0).apply(converter_porcentagem)

    # Agrupar por Etapa E Empreendimento
    df_gantt_agg = df_gantt.groupby(['Etapa', 'Empreendimento']).agg(
        Inicio_Prevista=('Inicio_Prevista', 'min'),
        Termino_Prevista=('Termino_Prevista', 'max'),
        Inicio_Real=('Inicio_Real', 'min'),
        Termino_Real=('Termino_Real', 'max'),
        **{'% concluído': ('% concluído', 'max')},
        SETOR=('SETOR', 'first'),
        UGB=('UGB', 'first')
    ).reset_index()
    
    all_data_by_stage_js = {}
    all_stage_names_full = [] # Para o novo filtro
    # Iterar por cada etapa única
    etapas_unicas_no_df = df_gantt_agg['Etapa'].unique()
    
    for i, etapa_sigla in enumerate(etapas_unicas_no_df):
        df_etapa_agg = df_gantt_agg[df_gantt_agg['Etapa'] == etapa_sigla]
        etapa_nome_completo = sigla_para_nome_completo.get(etapa_sigla, etapa_sigla)
        all_stage_names_full.append(etapa_nome_completo)
        
        tasks_base_data_for_stage = []
        
        for j, row in df_etapa_agg.iterrows():
            start_date = row.get("Inicio_Prevista")
            end_date = row.get("Termino_Prevista")
            start_real = row.get("Inicio_Real")
            end_real_original = row.get("Termino_Real")
            progress = row.get("% concluído", 0)

            if pd.isna(start_date): start_date = datetime.now()
            if pd.isna(end_date): end_date = start_date + timedelta(days=30)
            end_real_visual = end_real_original
            if pd.notna(start_real) and progress < 100 and pd.isna(end_real_original): end_real_visual = datetime.now()

            vt = calculate_business_days(end_date, end_real_original)
            duracao_prevista_uteis = calculate_business_days(start_date, end_date)
            duracao_real_uteis = calculate_business_days(start_real, end_real_original)
            vd = None
            if pd.notna(duracao_real_uteis) and pd.notna(duracao_prevista_uteis): vd = duracao_real_uteis - duracao_prevista_uteis
            status_color_class = 'status-default'
            hoje = pd.Timestamp.now().normalize()
            if progress == 100:
                if pd.notna(end_real_original) and pd.notna(end_date):
                    if end_real_original <= end_date: status_color_class = 'status-green'
                    else: status_color_class = 'status-red'
            elif progress < 100 and pd.notna(end_date) and (end_date < hoje): status_color_class = 'status-yellow'

            task = {
                "id": f"t{j}_{i}", # ID único
                "name": row["Empreendimento"], # O 'name' ainda é o Empreendimento
                "ugb": row.get("UGB", "N/D"),
                "numero_etapa": j + 1,
                "start_previsto": start_date.strftime("%Y-%m-%d"),
                "end_previsto": end_date.strftime("%Y-%m-%d"),
                "start_real": pd.to_datetime(start_real).strftime("%Y-%m-%d") if pd.notna(start_real) else None,
                "end_real": pd.to_datetime(end_real_visual).strftime("%Y-%m-%d") if pd.notna(end_real_visual) else None,
                "end_real_original_raw": pd.to_datetime(end_real_original).strftime("%Y-%m-%d") if pd.notna(end_real_original) else None,
                "setor": row.get("SETOR", "Não especificado"),
                "grupo": "Consolidado", # Correto
                "progress": int(progress),
                "inicio_previsto": start_date.strftime("%d/%m/%y"),
                "termino_previsto": end_date.strftime("%d/%m/%y"),
                "inicio_real": pd.to_datetime(start_real).strftime("%d/%m/%y") if pd.notna(start_real) else "N/D",
                "termino_real": pd.to_datetime(end_real_original).strftime("%d/%m/%y") if pd.notna(end_real_original) else "N/D",
                "duracao_prev_meses": f"{(end_date - start_date).days / 30.4375:.1f}".replace('.', ',') if pd.notna(start_date) and pd.notna(end_date) else "-",
                "duracao_real_meses": f"{(end_real_original - start_real).days / 30.4375:.1f}".replace('.', ',') if pd.notna(start_real) and pd.notna(end_real_original) else "-",
                "vt_text": f"{int(vt):+d}d" if pd.notna(vt) else "-",
                "vd_text": f"{int(vd):+d}d" if pd.notna(vd) else "-",
                "status_color_class": status_color_class
            }
            tasks_base_data_for_stage.append(task)
        
        # *** NOVO: Popular baselines em cada task do consolidado ***
        try:
            all_baselines_dict = load_baselines()  # Carregar todas as baselines
            
            for task in tasks_base_data_for_stage:
                empreendimento = task["name"]  # No consolidado, name = empreendimento
                
                # Inicializar campo baselines
                task["baselines"] = {}
                
                # P0 = dados atuais (padrão)
                task["baselines"]["P0-(padrão)"] = {
                    "start": task["start_previsto"],
                    "end": task["end_previsto"]
                }
                
                # Adicionar baselines salvas do empreendimento
                if empreendimento in all_baselines_dict:
                    baselines_emp = all_baselines_dict[empreendimento]
                    
                    for baseline_name, baseline_info in baselines_emp.items():
                        baseline_data = get_baseline_data(empreendimento, baseline_name)
                        
                        if baseline_data and 'tasks' in baseline_data:
                            baseline_tasks = baseline_data['tasks']
                            
                            # Buscar a etapa ATUAL (etapa_nome_completo) na baseline
                            baseline_task = None
                            
                            # Estratégia 1: Nome completo exato
                            baseline_task = next(
                                (bt for bt in baseline_tasks 
                                 if bt.get('etapa') == etapa_nome_completo or 
                                    bt.get('Etapa') == etapa_nome_completo),
                                None
                            )
                            
                            # Estratégia 2: Tentar com sigla
                            if not baseline_task:
                                baseline_task = next(
                                    (bt for bt in baseline_tasks 
                                     if bt.get('etapa') == etapa_sigla or 
                                        bt.get('Etapa') == etapa_sigla),
                                    None
                                )
                            
                            # Estratégia 3: Converter etapa da baseline para nome completo e comparar
                            if not baseline_task:
                                for bt in baseline_tasks:
                                    bt_etapa = bt.get('etapa', bt.get('Etapa', ''))
                                    bt_etapa_nome = sigla_para_nome_completo.get(bt_etapa, bt_etapa)
                                    if bt_etapa_nome == etapa_nome_completo:
                                        baseline_task = bt
                                        break
                            
                            if baseline_task:
                                task["baselines"][baseline_name] = {
                                    "start": baseline_task.get('inicio_previsto', baseline_task.get('Inicio_Prevista')),
                                    "end": baseline_task.get('termino_previsto', baseline_task.get('Termino_Prevista'))
                                }
                            else:
                                # Etapa não existe nesta baseline
                                task["baselines"][baseline_name] = {
                                    "start": None,
                                    "end": None
                                }
        except Exception as e:
            print(f"Erro ao popular baselines no consolidado: {e}")
            # Se falhar, pelo menos P0 já foi adicionado
            
        all_data_by_stage_js[etapa_nome_completo] = tasks_base_data_for_stage
    
    if not all_data_by_stage_js:
        st.warning("Nenhum dado válido para o Gantt Consolidado após a conversão.")
        return

    empreendimentos_no_df = sorted(list(df_gantt_agg["Empreendimento"].unique()))
    
    # Obter UGBs únicas dos dados
    ugbs_disponiveis = sorted(df["UGB"].dropna().unique().tolist()) if not df.empty and "UGB" in df.columns else []
    
    filter_options = {
        "ugbs": ["Todas"] + ugbs_disponiveis,
        "empreendimentos": ["Todos"] + empreendimentos_no_df, # Renomeado
        "etapas_consolidadas": sorted(all_stage_names_full) # Novo (sem "Todos")
    }

    # Pegar os dados da *primeira* etapa selecionada para a renderização inicial
    tasks_base_data_inicial = all_data_by_stage_js.get(etapa_selecionada_inicialmente, [])

    # Criar um "projeto" único
    project_id = f"p_cons_{random.randint(1000, 9999)}"
    project = {
        "id": project_id,
        "name": f"Comparativo: {etapa_selecionada_inicialmente}", # Nome inicial
        "tasks": tasks_base_data_inicial, # Dados iniciais
        "meta_assinatura_date": None
    }

    df_para_datas = df_gantt_agg
    data_min_proj, data_max_proj = calcular_periodo_datas(df_para_datas)
    total_meses_proj = ((data_max_proj.year - data_min_proj.year) * 12) + (data_max_proj.month - data_min_proj.month) + 1

    num_tasks = len(project["tasks"])
        
    altura_gantt = max(400, (len(empreendimentos_no_df) * 30) + 150)

    # *** MODIFICADO: Preparar baselines individuais por empreendimento ***
    baselines_por_empreendimento_html = {}
    
    try:
        all_baselines_dict = load_baselines()
        for emp in empreendimentos_no_df:
            emp_baseline_options = get_baseline_options(emp)
            if not emp_baseline_options or len(emp_baseline_options) == 0:
                emp_baseline_options = ["P0-(padrão)"]
            else:
                # Garantir que P0 está na lista
                if "P0-(padrão)" not in emp_baseline_options:
                    emp_baseline_options.insert(0, "P0-(padrão)")
            
            baselines_por_empreendimento_html[emp] = emp_baseline_options
    except Exception as e:
        print(f"Erro ao carregar baseline options no consolidado: {e}")
        # Fallback: P0 para todos
        for emp in empreendimentos_no_df:
            baselines_por_empreendimento_html[emp] = ["P0-(padrão)"]
    
    # Gerar HTML dos dropdowns por empreendimento
    baseline_rows_html = ""
    for emp in empreendimentos_no_df:
        emp_options = baselines_por_empreendimento_html.get(emp, ["P0-(padrão)"])
        # Usar JSON para escape seguro
        emp_json = json.dumps(emp)  # Gera "Nome do Emp" com aspas duplas
        
        options_html = "".join([
            f'<option value="{opt}">{opt}</option>' 
            for opt in emp_options
        ])
        
        baseline_rows_html += f"""
        <div class="baseline-row" data-empreendimento="{emp}">
            <label title="{emp}">{emp}</label>
            <select class="baseline-dropdown-emp" data-emp="{emp}" onchange='applyBaselineForEmp({emp_json}, this.value); var p0=document.getElementById("apply-p0-all-{project["id"]}"); var latest=document.getElementById("apply-latest-all-{project["id"]}"); if(p0)p0.checked=false; if(latest)latest.checked=false;'>
                {options_html}
            </select>
        </div>
        """


    # --- 4. Geração do HTML/JS Corrigido ---
    gantt_html = f"""
    <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            {'''
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/virtual-select-plugin@1.0.39/dist/virtual-select.min.css">
            '''}
            <style>
                /* CSS idêntico ao de gerar_gantt_por_projeto, exceto adaptações para consolidado */
                 * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                html, body {{ width: 100%; height: 100%; font-family: 'Segoe UI', sans-serif; background-color: #f5f5f5; color: #333; overflow: hidden; }}
                .gantt-container {{ width: 100%; height: 100%; background-color: white; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); overflow: hidden; position: relative; display: flex; flex-direction: column; }}
                .gantt-main {{ display: flex; flex: 1; overflow: hidden; }}
                .gantt-sidebar-wrapper {{ width: 680px; display: flex; flex-direction: column; flex-shrink: 0; transition: width 0.3s ease-in-out; border-right: 2px solid #e2e8f0; overflow: hidden; }}
                .gantt-sidebar-header {{ background: linear-gradient(135deg, #4a5568, #2d3748); display: flex; flex-direction: column; height: 60px; flex-shrink: 0; }}
                .project-title-row {{ display: flex; justify-content: space-between; align-items: center; padding: 0 15px; height: 30px; color: white; font-weight: 600; font-size: 14px; }}
                .toggle-sidebar-btn {{ background: rgba(255,255,255,0.2); border: none; color: white; width: 24px; height: 24px; border-radius: 5px; cursor: pointer; font-size: 14px; display: flex; align-items: center; justify-content: center; transition: background-color 0.2s, transform 0.3s ease-in-out; }}
                .toggle-sidebar-btn:hover {{ background: rgba(255,255,255,0.4); }}
                .sidebar-grid-header-wrapper {{ display: grid; grid-template-columns: 0px 1fr; color: #d1d5db; font-size: 9px; font-weight: 600; text-transform: uppercase; height: 30px; align-items: center; }}
                .sidebar-grid-header {{ display: grid; grid-template-columns: 2.5fr 0.6fr 0.9fr 0.9fr 0.6fr 0.9fr 0.9fr 0.6fr 0.5fr 0.6fr 0.6fr; padding: 0 10px; align-items: center; }}
                .sidebar-row {{ display: grid; grid-template-columns: 2.5fr 0.6fr 0.9fr 0.9fr 0.6fr 0.9fr 0.9fr 0.6fr 0.5fr 0.6fr 0.6fr; border-bottom: 1px solid #eff2f5; height: 30px; padding: 0 10px; background-color: white; transition: all 0.2s ease-in-out; }}
                .sidebar-cell {{ display: flex; align-items: center; justify-content: center; font-size: 11px; color: #4a5568; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 8px; border: none; }}
                .header-cell {{ text-align: center; }}
                .header-cell.task-name-cell {{ text-align: left; }}
                .gantt-sidebar-content {{ background-color: #f8f9fa; flex: 1; overflow-y: auto; overflow-x: hidden; }}
                .sidebar-group-wrapper {{ display: flex; border-bottom: none; }}
                .gantt-sidebar-content > .sidebar-group-wrapper:last-child {{ border-bottom: none; }}
                .sidebar-group-title-vertical {{ display: none; }}
                .sidebar-group-spacer {{ display: none; }}
                .sidebar-rows-container {{ flex-grow: 1; }}
                .sidebar-row.odd-row {{ background-color: #fdfdfd; }}
                .sidebar-rows-container .sidebar-row:last-child {{ border-bottom: none; }}
                .sidebar-row:hover {{ background-color: #f5f8ff; }}
                .sidebar-cell.task-name-cell {{ justify-content: flex-start; font-weight: 600; color: #2d3748; }}
                .sidebar-cell.status-green {{ color: #1E8449; font-weight: 700; }}
                .sidebar-cell.status-red   {{ color: #C0392B; font-weight: 700; }}
                .sidebar-cell.status-yellow{{ color: #B9770E; font-weight: 700; }}
                .sidebar-cell.status-default{{ color: #566573; font-weight: 700; }}
                .sidebar-row .sidebar-cell:nth-child(2),
                .sidebar-row .sidebar-cell:nth-child(3),
                .sidebar-row .sidebar-cell:nth-child(4),
                .sidebar-row .sidebar-cell:nth-child(5),
                .sidebar-row .sidebar-cell:nth-child(6),
                .sidebar-row .sidebar-cell:nth-child(7),
                .sidebar-row .sidebar-cell:nth-child(8),
                .sidebar-row .sidebar-cell:nth-child(9),
                .sidebar-row .sidebar-cell:nth-child(10),
                .sidebar-row .sidebar-cell:nth-child(11) {{ font-size: 8px; }}
                .gantt-row-spacer, .sidebar-row-spacer {{ display: none; }}
                .gantt-sidebar-wrapper.collapsed {{ width: 250px; }}
                .gantt-sidebar-wrapper.collapsed .sidebar-grid-header, .gantt-sidebar-wrapper.collapsed .sidebar-row {{ grid-template-columns: 1fr; padding: 0 15px 0 10px; }}
                .gantt-sidebar-wrapper.collapsed .header-cell:not(.task-name-cell), .gantt-sidebar-wrapper.collapsed .sidebar-cell:not(.task-name-cell) {{ display: none; }}
                .gantt-sidebar-wrapper.collapsed .toggle-sidebar-btn {{ transform: rotate(180deg); }}
                .gantt-chart-content {{ flex: 1; overflow: auto; position: relative; background-color: white; user-select: none; cursor: grab; }}
                .gantt-chart-content.active {{ cursor: grabbing; }}
                .chart-container {{ position: relative; min-width: {total_meses_proj * 30}px; }}
                .chart-header {{ background: linear-gradient(135deg, #4a5568, #2d3748); color: white; height: 60px; position: sticky; top: 0; z-index: 9; display: flex; flex-direction: column; }}
                .year-header {{ height: 30px; display: flex; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.2); }}
                .year-section {{ text-align: center; font-weight: 600; font-size: 12px; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.1); height: 100%; }}
                .month-header {{ height: 30px; display: flex; align-items: center; }}
                .month-cell {{ width: 30px; height: 30px; border-right: 1px solid rgba(255,255,255,0.2); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 500; }}
                .chart-body {{ position: relative; }}
                .gantt-row {{ position: relative; height: 30px; border-bottom: 1px solid #eff2f5; background-color: white; }}
                .gantt-bar {{ position: absolute; height: 14px; top: 8px; border-radius: 3px; cursor: pointer; transition: all 0.2s ease; display: flex; align-items: center; padding: 0 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .gantt-bar-overlap {{ position: absolute; height: 14px; top: 8px; background-image: linear-gradient(45deg, rgba(0, 0, 0, 0.25) 25%, transparent 25%, transparent 50%, rgba(0, 0, 0, 0.25) 50%, rgba(0, 0, 0, 0.25) 75%, transparent 75%, transparent); background-size: 8px 8px; z-index: 9; pointer-events: none; border-radius: 3px; }}
                .gantt-bar:hover {{ transform: translateY(-1px) scale(1.01); box-shadow: 0 4px 8px rgba(0,0,0,0.2); z-index: 10 !important; }}
                .gantt-bar.previsto {{ z-index: 7; }}
                .gantt-bar.real {{ z-index: 8; }}
                .bar-label {{ font-size: 8px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-shadow: 0 1px 2px rgba(0,0,0,0.4); }}
                .gantt-bar.real .bar-label {{ color: white; }}
                .gantt-bar.previsto .bar-label {{ color: #6C6C6C; }}
                .tooltip {{ position: fixed; background-color: #2d3748; color: white; padding: 6px 10px; border-radius: 4px; font-size: 11px; z-index: 1000; box-shadow: 0 2px 8px rgba(0,0,0,0.3); pointer-events: none; opacity: 0; transition: opacity 0.2s ease; max-width: 220px; }}
                .tooltip.show {{ opacity: 1; }}
                .today-line {{ position: absolute; top: 60px; bottom: 0; width: 1px; background-color: #fdf1f1; z-index: 5; box-shadow: 0 0 1px rgba(229, 62, 62, 0.6); }}
                .month-divider {{ position: absolute; top: 60px; bottom: 0; width: 1px; background-color: #fcf6f6; z-index: 4; pointer-events: none; }}
                .month-divider.first {{ background-color: #eeeeee; width: 1px; }}
                .meta-line, .meta-line-label {{ display: none; }}
                .gantt-chart-content, .gantt-sidebar-content {{ scrollbar-width: thin; scrollbar-color: transparent transparent; }}
                .gantt-chart-content:hover, .gantt-sidebar-content:hover {{ scrollbar-color: #d1d5db transparent; }}
                .gantt-chart-content::-webkit-scrollbar, .gantt-sidebar-content::-webkit-scrollbar {{ height: 8px; width: 8px; }}
                .gantt-chart-content::-webkit-scrollbar-track, .gantt-sidebar-content::-webkit-scrollbar-track {{ background: transparent; }}
                .gantt-chart-content::-webkit-scrollbar-thumb, .gantt-sidebar-content::-webkit-scrollbar-thumb {{ background-color: transparent; border-radius: 4px; }}
                .gantt-chart-content:hover::-webkit-scrollbar-thumb, .gantt-sidebar-content:hover::-webkit-scrollbar-thumb {{ background-color: #d1d5db; }}
                .gantt-chart-content:hover::-webkit-scrollbar-thumb:hover, .gantt-sidebar-content:hover::-webkit-scrollbar-thumb:hover {{ background-color: #a8b2c1; }}
                .gantt-toolbar {{
                    position: absolute; top: 10px; right: 10px;
                    z-index: 100;
                    display: flex;
                    flex-direction: column;
                    gap: 5px;
                    background: rgba(45, 55, 72, 0.9); /* Cor de fundo escura para minimalismo */
                    border-radius: 6px;
                    padding: 5px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                }}
                .toolbar-btn {{
                    background: none;
                    border: none;
                    width: 36px;
                    height: 36px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 20px;
                    color: white;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    transition: background-color 0.2s, box-shadow 0.2s;
                    padding: 0;
                }}
                .toolbar-btn:hover {{
                    background-color: rgba(255, 255, 255, 0.1);
                    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.2);
                }}
                .toolbar-btn.is-fullscreen {{
                    background-color: #3b82f6; /* Cor de destaque para o botão ativo */
                    box-shadow: 0 0 0 2px #3b82f6;
                }}
                .toolbar-btn.is-fullscreen:hover {{
                    background-color: #2563eb;
                }}
                 /* *** INÍCIO: Arredondar Dropdown Virtual Select *** */
                    .floating-filter-menu .vscomp-dropbox {{
                        border-radius: 8px; /* Controla o arredondamento dos cantos do dropdown */
                        overflow: hidden;   /* Necessário para que o conteúdo interno não "vaze" pelos cantos arredondados */
                        box-shadow: 0 5px 15px rgba(0,0,0,0.2); /* Sombra para melhor visualização (opcional) */
                        border: 1px solid #ccc; /* Borda sutil (opcional) */
                    }}

                    /* Opcional: Arredondar também o campo de busca interno, se ele ficar visível no topo */
                    .floating-filter-menu .vscomp-search-wrapper {{
                    /* Remove o arredondamento padrão se houver, para não conflitar com o container */
                    border-radius: 0;
                    }}

                    /* Opcional: Garantir que a lista de opções não ultrapasse */
                    .floating-filter-menu .vscomp-options-container {{
                        /* Geralmente não precisa de arredondamento próprio se o overflow:hidden funcionar */
                    }}
                    .floating-filter-menu .vscomp-toggle-button .vscomp-value-tag .vscomp-clear-button {{
                        display: inline-flex;    /* Usa flex para alinhar o ícone interno */
                        align-items: center;     /* Alinha verticalmente o ícone */
                        justify-content: center; /* Alinha horizontalmente o ícone */
                        vertical-align: middle;  /* Ajuda no alinhamento com o texto adjacente */
                        margin-left: 4px;        /* Espaçamento à esquerda (ajuste conforme necessário) */
                        padding: 0;            /* Remove padding interno se houver */
                        position: static;        /* Garante que não use posicionamento absoluto/relativo que possa quebrar o fluxo */
                        transform: none;         /* Remove qualquer translação que possa estar desalinhando */
                    }}

                    /* Opcional: Se o próprio ícone 'X' (geralmente uma tag <i>) precisar de ajuste */
                    .floating-filter-menu .vscomp-toggle-button .vscomp-value-tag .vscomp-clear-button i {{
                    }}
                .fullscreen-btn.is-fullscreen {{
	                    font-size: 24px; padding: 5px 10px; color: white;
	                }}
	                .floating-filter-menu {{
	                    display: none;
	                    position: absolute;
	                    top: 10px; right: 50px; /* Ajuste a posição para abrir ao lado da barra de ferramentas */
	                    width: 280px;
	                    background: white;
	                    border-radius: 8px;
	                    box-shadow: 0 5px 15px rgba(0,0,0,0.3);
	                    z-index: 99;
	                    padding: 15px;
	                    border: 1px solid #e2e8f0;
	                }}
	                .floating-filter-menu.is-open {{
	                    display: block;
	                }}
                .filter-group {{ margin-bottom: 12px; }}
                .filter-group label {{
                    display: block; font-size: 11px; font-weight: 600;
                    color: #4a5568; margin-bottom: 4px;
                    text-transform: uppercase;
                }}
                .filter-group select, .filter-group input[type=number] {{
                    width: 100%; padding: 6px 8px;
                    border: 1px solid #cbd5e0; border-radius: 4px;
                    font-size: 13px;
                }}
                .filter-group-radio, .filter-group-checkbox {{
                    display: flex; align-items: center; padding: 5px 0;
                }}
                .filter-group-radio input, .filter-group-checkbox input {{
                    width: auto; margin-right: 8px;
                }}
                .filter-group-radio label, .filter-group-checkbox label {{
                    font-size: 13px; font-weight: 500;
                    color: #2d3748; margin-bottom: 0; text-transform: none;
                }}
                .filter-apply-btn {{
                    width: 100%; padding: 8px; font-size: 14px; font-weight: 600;
                    color: white; background-color: #2d3748;
                    border: none; border-radius: 4px; cursor: pointer;
                    margin-top: 5px;
                }}
                .floating-filter-menu .vscomp-toggle-button {{
                    border: 1px solid #cbd5e0;
                    border-radius: 4px;
                    padding: 6px 8px;
                    font-size: 13px;
                    min-height: 30px;
                }}
                .floating-filter-menu .vscomp-options {{
                    font-size: 13px;
                }}
                .floating-filter-menu .vscomp-option {{
                    min-height: 30px;
                }}
                .floating-filter-menu .vscomp-search-input {{
                    height: 30px;
                    font-size: 13px;
                }}
            </style>
        </head>
        <body>
            <div class="gantt-container" id="gantt-container-{project['id']}">
                    <div class="gantt-toolbar" id="gantt-toolbar-{project["id"]}">
                        <button class="toolbar-btn" id="filter-btn-{project["id"]}" title="Filtros">
                        <span>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon>
                            </svg>
                        </span>
                    </button>
                    <button class="toolbar-btn" id="baseline-btn-{project["id"]}" title="Linhas de Base">
                        <span>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                <line x1="3" y1="9" x2="21" y2="9"></line>
                                <line x1="3" y1="15" x2="21" y2="15"></line>
                            </svg>
                        </span>
                    </button>
                    <button class="toolbar-btn" id="fullscreen-btn-{project["id"]}" title="Tela Cheia">
                        <span>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
                            </svg>
                        </span>
                    </button>
                </div>

                <!-- Seletor de Baseline (NOVO) -->
                <div class="baseline-selector" id="baseline-selector-{project['id']}" style="
                    display: none;
                    position: absolute;
                    top: 10px;
                    right: 50px;
                    width: 280px;
                    min-height: 200px;
                    background: white;
                    border-radius: 8px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.3);
                    z-index: 99;
                    padding: 15px;
                    border: 1px solid #e2e8f0;
                ">
                    <div style="margin-bottom: 12px; font-weight: 700; color: #1a202c; font-size: 14px; border-bottom: 2px solid #1a202c; padding-bottom: 8px;">
                        Selecione Linhas de Base
                    </div>
                    
                    <!-- Checkboxes de Aplicação Rápida -->
                    <div style="margin-bottom: 15px; padding: 10px; background: #f7fafc; border-radius: 6px; border: 1px solid #e2e8f0;">
                        <div style="font-weight: 600; color: #2d3748; font-size: 12px; margin-bottom: 10px;">
                            Aplicação Rápida
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 6px;">
                            <label style="display: flex; align-items: center; cursor: pointer;">
                                <input type="checkbox" id="apply-p0-all-{project['id']}" 
                                       onchange="handleQuickApply('p0')" 
                                       style="margin-right: 6px; cursor: pointer;">
                                <span style="font-size: 11px; color: #4a5568;">Aplicar P0 para todos</span>
                            </label>
                            <label style="display: flex; align-items: center; cursor: pointer;">
                                <input type="checkbox" id="apply-latest-all-{project['id']}" 
                                       onchange="handleQuickApply('latest')" 
                                       style="margin-right: 6px; cursor: pointer;">
                                <span style="font-size: 11px; color: #4a5568;">Aplicar última baseline para todos</span>
                            </label>
                        </div>
                    </div>
                    
                    <div class="baseline-selector-table" style="
                        max-height: 400px;
                        overflow-y: auto;
                        margin-top: 10px;
                    ">
                        {baseline_rows_html}
                    </div>
                    <div class="baseline-resize-corner" title="Arrastar para redimensionar"></div>
                </div>

                <style>
                    .baseline-row {{
                        display: grid;
                        grid-template-columns: 1.2fr 1fr;
                        gap: 10px;
                        padding: 8px 6px;
                        border-bottom: 1px solid #e2e8f0;
                        align-items: center;
                        transition: background-color 0.15s ease;
                    }}
                    
                    .baseline-row:hover {{
                        background-color: #f7fafc;
                    }}
                    
                    .baseline-row:last-child {{
                        border-bottom: none;
                    }}
                    
                    .baseline-row label {{
                        font-size: 11px;
                        font-weight: 500;
                        color: #2d3748;
                        display: flex;
                        align-items: center;
                        padding-left: 5px;
                        overflow: hidden;
                        text-overflow: ellipsis;
                        white-space: nowrap;
                    }}
                    
                    .baseline-resize-corner {{
                        position: absolute;
                        bottom: 0;
                        left: 0;
                        width: 16px;
                        height: 16px;
                        cursor: nwse-resize;
                        z-index: 100;
                    }}
                    
                    .baseline-resize-corner::before {{
                        content: '';
                        position: absolute;
                        bottom: -2px;
                        left: -2px;
                        width: 0;
                        height: 0;
                        border-style: solid;
                        border-width: 0 0 18px 18px;
                        border-color: transparent;
                        transform: rotate(-45deg);
                        transform-origin: bottom left;
                    }}
                    
                    .baseline-resize-corner:hover::before {{
                        border-color: transparent;
                    }}
                    
                    .baseline-resize-corner::after {{
                        content: '';
                        position: absolute;
                        bottom: 2px;
                        left: 2px;
                        width: 10px;
                        height: 10px;
                        transform: rotate(-45deg);
                        transform-origin: center;
                        background: 
                            linear-gradient(90deg, transparent 48%, #9ca3af 48%, #9ca3af 52%, transparent 52%),
                            linear-gradient(90deg, transparent 56%, #9ca3af 56%, #9ca3af 60%, transparent 60%),
                            linear-gradient(90deg, transparent 64%, #9ca3af 64%, #9ca3af 68%, transparent 68%);
                    }}
                    
                    .baseline-row select.baseline-dropdown-emp {{
                        width: 100%;
                        padding: 5px 8px;
                        border: 1px solid #cbd5e0;
                        border-radius: 5px;
                        font-size: 11px;
                        background-color: white;
                        transition: all 0.2s ease;
                        cursor: pointer;
                    }}
                    
                    .baseline-row select.baseline-dropdown-emp:hover {{
                        border-color: #4299e1;
                        box-shadow: 0 0 0 1px rgba(66, 153, 225, 0.1);
                    }}
                    
                    .baseline-row select.baseline-dropdown-emp:focus {{
                        outline: none;
                        border-color: #4299e1;
                        box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.1);
                    }}
                </style>

                <div class="floating-filter-menu" id="filter-menu-{project['id']}">
                    
                    <div class="filter-group">
                        <label for="filter-etapa-consolidada-{project['id']}">Etapa (Visão Atual)</label>
                        <select id="filter-etapa-consolidada-{project['id']}">
                            </select>
                    </div>
                    
                    <div class="filter-group">
                        <label for="filter-ugb-consolidado-{project['id']}">UGB</label>
                        <div id="filter-ugb-consolidado-{project['id']}"></div>
                    </div>

                    <div class="filter-group">
                        <label for="filter-empreendimento-{project['id']}">Empreendimento</label>
                        <div id="filter-empreendimento-{project['id']}"></div>
                    </div>

                    <div class="filter-group">
                        <div class="filter-group-checkbox">
                            <input type="checkbox" id="filter-concluidas-{project['id']}">
                            <label for="filter-concluidas-{project['id']}">Mostrar apenas não concluídas</label>
                        </div>
                    </div>
                    
                    <div class="filter-group">
                        <label>Visualização</label>
                        <div class="filter-group-radio">
                            <input type="radio" id="filter-vis-ambos-{project['id']}" name="filter-vis-{project['id']}" value="Ambos" checked>
                            <label for="filter-vis-ambos-{project['id']}">Ambos</label>
                        </div>
                        <div class="filter-group-radio">
                            <input type="radio" id="filter-vis-previsto-{project['id']}" name="filter-vis-{project['id']}" value="Previsto">
                            <label for="filter-vis-previsto-{project['id']}">Previsto</label>
                        </div>
                        <div class="filter-group-radio">
                            <input type="radio" id="filter-vis-real-{project['id']}" name="filter-vis-{project['id']}" value="Real">
                            <label for="filter-vis-real-{project['id']}">Real</label>
                        </div>
                    </div>

                    <div class="filter-group">
                        <label>Simulação Pulmão</label>
                        <div class="filter-group-radio">
                            <input type="radio" id="filter-pulmao-sem-{project['id']}" name="filter-pulmao-{project['id']}" value="Sem Pulmão">
                            <label for="filter-pulmao-sem-{project['id']}">Sem Pulmão</label>
                        </div>
                        <div class="filter-group-radio">
                            <input type="radio" id="filter-pulmao-com-{project['id']}" name="filter-pulmao-{project['id']}" value="Com Pulmão">
                            <label for="filter-pulmao-com-{project['id']}">Com Pulmão</label>
                        </div>
                        <div class="filter-group" id="pulmao-meses-group-{project['id']}" style="margin-top: 8px; display: none; padding-left: 25px;">
                            <label for="filter-pulmao-meses-{project['id']}" style="font-size: 12px; font-weight: 500;">Meses de Pulmão:</label>
                            <input type="number" id="filter-pulmao-meses-{project['id']}" value="{pulmao_meses}" min="0" max="36" step="1" style="padding: 4px 6px; font-size: 12px; height: 28px; width: 80px;">
                        </div>
                    </div>
                    <button class="filter-apply-btn" id="filter-apply-btn-{project['id']}">Aplicar Filtros</button>
                </div>

                <div class="gantt-main">
                    <div class="gantt-sidebar-wrapper" id="gantt-sidebar-wrapper-{project['id']}">
                        <div class="gantt-sidebar-header">
                            <div class="project-title-row">
                                <span>{project["name"]}</span>
                                <button class="toggle-sidebar-btn" id="toggle-sidebar-btn-{project['id']}" title="Recolher/Expandir Tabela">«</button>
                            </div>
                            <div class="sidebar-grid-header-wrapper">
                                <div style="width: 0px;"></div>
                                <div class="sidebar-grid-header">
                                    <div class="header-cell task-name-cell">EMPREENDIMENTO</div>
                                    <div class="header-cell">UGB</div>
                                    <div class="header-cell">INÍCIO-P</div>
                                    <div class="header-cell">TÉRMINO-P</div>
                                    <div class="header-cell">DUR-P</div>
                                    <div class="header-cell">INÍCIO-R</div>
                                    <div class="header-cell">TÉRMINO-R</div>
                                    <div class="header-cell">DUR-R</div>
                                    <div class="header-cell">%</div>
                                    <div class="header-cell">VT</div>
                                    <div class="header-cell">VD</div>
                                </div>
                            </div>
                        </div>
                        <div class="gantt-sidebar-content" id="gantt-sidebar-content-{project['id']}"></div>
                    </div>
                    <div class="gantt-chart-content" id="gantt-chart-content-{project['id']}">
                        <div class="chart-container" id="chart-container-{project["id"]}">
                            <div class="chart-header">
                                <div class="year-header" id="year-header-{project["id"]}"></div>
                                <div class="month-header" id="month-header-{project["id"]}"></div>
                            </div>
                            <div class="chart-body" id="chart-body-{project["id"]}"></div>
                            <div class="today-line" id="today-line-{project["id"]}"></div>
                            <div class="meta-line" id="meta-line-{project["id"]}" style="display: none;"></div>
                            <div class="meta-line-label" id="meta-line-label-{project["id"]}" style="display: none;"></div>
                        </div>
                    </div>
                </div>
                <div class="tooltip" id="tooltip-{project["id"]}"></div>
            </div>

            {''''''}
            <script src="https://cdn.jsdelivr.net/npm/virtual-select-plugin@1.0.39/dist/virtual-select.min.js"></script>
            {''''''}

            <script>
                // DEBUG: Verificar dados
                console.log('Inicializando Gantt Consolidado para:', '{project["name"]}');
                
                const coresPorSetor = {json.dumps(StyleConfig.CORES_POR_SETOR)};
                
                // --- NOVAS VARIÁVEIS DE DADOS ---
                // 'projectData' armazena o estado ATUAL (inicia com a etapa selecionada)
                const projectData = [{json.dumps(project)}]; 
                // 'allDataByStage' armazena TUDO, chaveado por nome de etapa
                const allDataByStage = {json.dumps(all_data_by_stage_js)};
                
                // 'allTasks_baseData' agora armazena os dados "crus" da etapa ATUAL
                let allTasks_baseData = {json.dumps(tasks_base_data_inicial)}; 
                
                const initialStageName = {json.dumps(etapa_selecionada_inicialmente)};
                let currentStageName = initialStageName;
                // --- FIM NOVAS VARIÁVEIS ---
                
                const dataMinStr = '{data_min_proj.strftime("%Y-%m-%d")}'; // Range global
                const dataMaxStr = '{data_max_proj.strftime("%Y-%m-%d")}'; // Range global
                let tipoVisualizacao = '{tipo_visualizacao}';
                const PIXELS_PER_MONTH = 30;

                // --- Helpers de Data ---
                const formatDateDisplay = (dateStr) => {{
                    if (!dateStr) return "N/D";
                    const d = parseDate(dateStr);
                    if (!d || isNaN(d.getTime())) return "N/D";
                    const day = String(d.getUTCDate()).padStart(2, '0');
                    const month = String(d.getUTCMonth() + 1).padStart(2, '0');
                    const year = String(d.getUTCFullYear()).slice(-2);
                    return `${{day}}/${{month}}/${{year}}`;
                }};

                function addMonths(dateStr, months) {{
                    if (!dateStr) return null;
                    const date = parseDate(dateStr);
                    if (!date || isNaN(date.getTime())) return null;
                    const originalDay = date.getUTCDate();
                    date.setUTCMonth(date.getUTCMonth() + months);
                    if (date.getUTCDate() !== originalDay) {{
                        date.setUTCDate(0);
                    }}
                    return date.toISOString().split('T')[0];
                }}

                function parseDate(dateStr) {{ 
                    if (!dateStr) return null; 
                    const [year, month, day] = dateStr.split('-').map(Number); 
                    return new Date(Date.UTC(year, month - 1, day)); 
                }}

                // --- Dados de Filtro e Tasks ---
                const filterOptions = {json.dumps(filter_options)};
                // 'allTasks_baseData' (definido acima) é a base da etapa inicial

                const initialPulmaoStatus = '{pulmao_status}';
                const initialPulmaoMeses = {pulmao_meses};

                let pulmaoStatus = '{pulmao_status}';
                let filtersPopulated = false;

                // *** Variáveis Globais para Filtros ***
                // let vsSetor, vsGrupo; // REMOVIDO
                let vsUgbConsolidado; // NOVO: Filtro de UGB
                let vsEmpreendimento; 
                let selEtapaConsolidada; // Novo <select>

                // *** CONSTANTES DE ETAPA ***
                const etapas_pulmao = ["PULMÃO VENDA", "PULMÃO INFRA", "PULMÃO RADIER"];
                const etapas_sem_alteracao = ["PROSPECÇÃO", "RADIER", "DEMANDA MÍNIMA", "PE. ÁREAS COMUNS (URB)", "PE. ÁREAS COMUNS (ENG)", "ORÇ. ÁREAS COMUNS", "SUP. ÁREAS COMUNS", "EXECUÇÃO ÁREAS COMUNS"];
                
                // --- Lógica de Pulmão para Consolidado ---
                // *** aplicarLogicaPulmaoConsolidado ***
                function aplicarLogicaPulmaoConsolidado(tasks, offsetMeses, stageName) {{
                    console.log(`Aplicando pulmão de ${{offsetMeses}}m para etapa: ${{stageName}}`);

                    // Verifica o *tipo* de etapa que estamos processando
                    if (etapas_sem_alteracao.includes(stageName)) {{
                        console.log("Etapa sem alteração, retornando tasks originais.");
                        return tasks; // Não altera datas
                    
                    }} else if (etapas_pulmao.includes(stageName)) {{
                        console.log("Etapa Pulmão: movendo apenas início PREVISTO.");
                        // Para etapas de pulmão, move apenas o Início PREVISTO
                        tasks.forEach(task => {{
                            task.start_previsto = addMonths(task.start_previsto, offsetMeses);
                            // DATAS REAIS PERMANECEM INALTERADAS
                            task.inicio_previsto = formatDateDisplay(task.start_previsto);
                            // Não mexe no 'end_date' real
                        }});
                    
                    }} else {{
                        console.log("Etapa Padrão: movendo apenas PREVISTO.");
                        // Para todas as outras etapas, move apenas Início e Fim PREVISTOS
                        tasks.forEach(task => {{
                            task.start_previsto = addMonths(task.start_previsto, offsetMeses);
                            task.end_previsto = addMonths(task.end_previsto, offsetMeses);
                            // DATAS REAIS PERMANECEM INALTERADAS

                            task.inicio_previsto = formatDateDisplay(task.start_previsto);
                            task.termino_previsto = formatDateDisplay(task.end_previsto);
                            // Datas reais mantêm seus valores originais
                        }});
                    }}
                    return tasks;
                }}

                // *** FUNÇÃO CORRIGIDA: applyInitialPulmaoState ***
                function applyInitialPulmaoState() {{
                    if (initialPulmaoStatus === 'Com Pulmão' && initialPulmaoMeses > 0) {{
                        const offsetMeses = -initialPulmaoMeses;
                        let baseTasks = JSON.parse(JSON.stringify(allTasks_baseData));
                        
                        // Passa o nome da etapa inicial - APENAS DATAS PREVISTAS SERÃO MODIFICADAS
                        const tasksProcessadas = aplicarLogicaPulmaoConsolidado(baseTasks, offsetMeses, initialStageName);
                        
                        projectData[0].tasks = tasksProcessadas;
                        // Atualiza também o 'allTasks_baseData' que é a fonte "crua" da etapa atual
                        allTasks_baseData = JSON.parse(JSON.stringify(tasksProcessadas));
                    }}
                }}


                function initGantt() {{
                    console.log('Iniciando Gantt Consolidado com dados:', projectData);
                    
                    if (!projectData || !projectData[0] || !projectData[0].tasks || projectData[0].tasks.length === 0) {{
                        console.warn('Nenhum dado disponível para renderizar na etapa inicial');
                    }}

                    // NOTA: applyInitialPulmaoState foi movida para DENTRO de initGantt
                    applyInitialPulmaoState(); 
                    
                    // Inicializar estado de baselines por empreendimento
                    initializeBaselineState();
                    
                    renderSidebar();
                    renderHeader();
                    renderChart();
                    renderMonthDividers();
                    setupEventListeners();
                    positionTodayLine();
                    populateFilters();
                }}

                // *** FUNÇÃO CORRIGIDA: renderSidebar para ordenação ***
                function renderSidebar() {{
                    const sidebarContent = document.getElementById('gantt-sidebar-content-{project["id"]}');
                    let tasks = projectData[0].tasks;

                    if (!tasks || tasks.length === 0) {{
                        sidebarContent.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">Nenhum empreendimento disponível</div>';
                        return;
                    }}

                    // Ordenação dinâmica
                    const dateSortFallback = new Date(8640000000000000);

                    if (tipoVisualizacao === 'Real') {{
                        tasks.sort((a, b) => {{
                            const dateA = a.start_real ? parseDate(a.start_real) : dateSortFallback;
                            const dateB = b.start_real ? parseDate(b.start_real) : dateSortFallback;
                            if (dateA > dateB) return 1;
                            if (dateA < dateB) return -1;
                            return a.name.localeCompare(b.name);
                        }});
                    }} else {{
                        tasks.sort((a, b) => {{
                            const dateA = a.start_previsto ? parseDate(a.start_previsto) : dateSortFallback;
                            const dateB = b.start_previsto ? parseDate(b.start_previsto) : dateSortFallback;
                            if (dateA > dateB) return 1;
                            if (dateA < dateB) return -1;
                            return a.name.localeCompare(b.name);
                        }});
                    }}

                    let html = '';
                    let globalRowIndex = 0;

                    html += '<div class="sidebar-rows-container">';
                    tasks.forEach(task => {{
                        globalRowIndex++;
                        const rowClass = globalRowIndex % 2 !== 0 ? 'odd-row' : '';
                        task.numero_etapa = globalRowIndex;

                        html += '<div class="sidebar-row ' + rowClass + '">' +
                            '<div class="sidebar-cell task-name-cell" title="' + task.numero_etapa + '. ' + task.name + '">' + task.numero_etapa + '. ' + task.name + '</div>' +
                            '<div class="sidebar-cell">' + (task.ugb || 'N/D') + '</div>' +
                            '<div class="sidebar-cell">' + task.inicio_previsto + '</div>' +
                            '<div class="sidebar-cell">' + task.termino_previsto + '</div>' +
                            '<div class="sidebar-cell">' + task.duracao_prev_meses + '</div>' +
                            '<div class="sidebar-cell">' + task.inicio_real + '</div>' +
                            '<div class="sidebar-cell">' + task.termino_real + '</div>' +
                            '<div class="sidebar-cell">' + task.duracao_real_meses + '</div>' +
                            '<div class="sidebar-cell ' + task.status_color_class + '">' + task.progress + '%</div>' +
                            '<div class="sidebar-cell ' + task.status_color_class + '">' + task.vt_text + '</div>' +
                            '<div class="sidebar-cell ' + task.status_color_class + '">' + task.vd_text + '</div>' +
                            '</div>';
                    }});
                    html += '</div>';
                    sidebarContent.innerHTML = html;
                }}

                // *** FUNÇÃO CORRIGIDA: renderHeader ***
                function renderHeader() {{
                    const yearHeader = document.getElementById('year-header-{project["id"]}');
                    const monthHeader = document.getElementById('month-header-{project["id"]}');
                    let yearHtml = '', monthHtml = '';
                    const yearsData = [];
                    let currentDate = parseDate(dataMinStr);
                    const dataMax = parseDate(dataMaxStr);

                    if (!currentDate || !dataMax || isNaN(currentDate.getTime()) || isNaN(dataMax.getTime())) {{
                         yearHeader.innerHTML = "Datas inválidas";
                         monthHeader.innerHTML = "";
                         return;
                    }}

                    // DECLARE estas variáveis
                    let currentYear = -1, monthsInCurrentYear = 0;

                    let totalMonths = 0;
                    while (currentDate <= dataMax && totalMonths < 240) {{
                        const year = currentDate.getUTCFullYear();
                        if (year !== currentYear) {{
                            if (currentYear !== -1) yearsData.push({{ year: currentYear, count: monthsInCurrentYear }});
                            currentYear = year; 
                            monthsInCurrentYear = 0;
                        }}
                        const monthNumber = String(currentDate.getUTCMonth() + 1).padStart(2, '0');
                        monthHtml += '<div class="month-cell">' + monthNumber + '</div>';
                        monthsInCurrentYear++;
                        currentDate.setUTCMonth(currentDate.getUTCMonth() + 1);
                        totalMonths++;
                    }}
                    if (currentYear !== -1) yearsData.push({{ year: currentYear, count: monthsInCurrentYear }});
                    yearsData.forEach(data => {{ 
                        const yearWidth = data.count * PIXELS_PER_MONTH; 
                        yearHtml += '<div class="year-section" style="width:' + yearWidth + 'px">' + data.year + '</div>'; 
                    }});

                    const chartContainer = document.getElementById('chart-container-{project["id"]}');
                    if (chartContainer) {{
                        chartContainer.style.minWidth = totalMonths * PIXELS_PER_MONTH + 'px';
                    }}

                    yearHeader.innerHTML = yearHtml;
                    monthHeader.innerHTML = monthHtml;
                }}

                function renderChart() {{
                    const chartBody = document.getElementById('chart-body-{project["id"]}');
                    const tasks = projectData[0].tasks;
                    
                    if (!tasks || tasks.length === 0) {{
                        chartBody.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">Nenhum empreendimento disponível</div>';
                        return;
                    }}
                    
                    chartBody.innerHTML = '';

                    tasks.forEach(task => {{
                        const row = document.createElement('div'); 
                        row.className = 'gantt-row';
                        let barPrevisto = null;
                        if (tipoVisualizacao === 'Ambos' || tipoVisualizacao === 'Previsto') {{ 
                            barPrevisto = createBar(task, 'previsto'); 
                            row.appendChild(barPrevisto); 
                        }}
                        let barReal = null;
                        if ((tipoVisualizacao === 'Ambos' || tipoVisualizacao === 'Real') && task.start_real && (task.end_real_original_raw || task.end_real)) {{ 
                            barReal = createBar(task, 'real'); 
                            row.appendChild(barReal); 
                        }}
                        if (barPrevisto && barReal) {{
                            const s_prev = parseDate(task.start_previsto), e_prev = parseDate(task.end_previsto), s_real = parseDate(task.start_real), e_real = parseDate(task.end_real_original_raw || task.end_real);
                            if (s_prev && e_prev && s_real && e_real && s_real <= s_prev && e_real >= e_prev) {{ 
                                barPrevisto.style.zIndex = '8'; 
                                barReal.style.zIndex = '7'; 
                            }}
                            renderOverlapBar(task, row);
                        }}
                        chartBody.appendChild(row);
                    }});
                }}

                function createBar(task, tipo) {{
                    const startDate = parseDate(tipo === 'previsto' ? task.start_previsto : task.start_real);
                    const endDate = parseDate(tipo === 'previsto' ? task.end_previsto : (task.end_real_original_raw || task.end_real));
                    if (!startDate || !endDate) return document.createElement('div');
                    const left = getPosition(startDate);
                    const width = getPosition(endDate) - left + (PIXELS_PER_MONTH / 30);
                    const bar = document.createElement('div'); 
                    bar.className = 'gantt-bar ' + tipo;
                    const coresSetor = coresPorSetor[task.setor] || coresPorSetor['Não especificado'] || {{previsto: '#cccccc', real: '#888888'}};
                    bar.style.backgroundColor = tipo === 'previsto' ? coresSetor.previsto : coresSetor.real;
                    bar.style.left = left + 'px'; 
                    bar.style.width = width + 'px';
                    const barLabel = document.createElement('span'); 
                    barLabel.className = 'bar-label'; 
                    barLabel.textContent = task.name + ' (' + task.progress + '%)'; 
                    bar.appendChild(barLabel);
                    bar.addEventListener('mousemove', e => showTooltip(e, task, tipo));
                    bar.addEventListener('mouseout', () => hideTooltip());
                    return bar;
                }}

                function renderOverlapBar(task, row) {{
                   if (!task.start_real || !(task.end_real_original_raw || task.end_real)) return;
                    const s_prev = parseDate(task.start_previsto), e_prev = parseDate(task.end_previsto), s_real = parseDate(task.start_real), e_real = parseDate(task.end_real_original_raw || task.end_real);
                    const overlap_start = new Date(Math.max(s_prev, s_real)), overlap_end = new Date(Math.min(e_prev, e_real));
                    if (overlap_start < overlap_end) {{
                        const left = getPosition(overlap_start), width = getPosition(overlap_end) - left + (PIXELS_PER_MONTH / 30);
                        if (width > 0) {{ 
                            const overlapBar = document.createElement('div'); 
                            overlapBar.className = 'gantt-bar-overlap'; 
                            overlapBar.style.left = left + 'px'; 
                            overlapBar.style.width = width + 'px'; 
                            row.appendChild(overlapBar); 
                        }}
                    }}
                }}

                function getPosition(date) {{
                    if (!date) return 0;
                    const chartStart = parseDate(dataMinStr);
                    if (!chartStart || isNaN(chartStart.getTime())) return 0;
                    const monthsOffset = (date.getUTCFullYear() - chartStart.getUTCFullYear()) * 12 + (date.getUTCMonth() - chartStart.getUTCMonth());
                    const dayOfMonth = date.getUTCDate() - 1;
                    const daysInMonth = new Date(date.getUTCFullYear(), date.getUTCMonth() + 1, 0).getUTCDate();
                    const fractionOfMonth = daysInMonth > 0 ? dayOfMonth / daysInMonth : 0;
                    return (monthsOffset + fractionOfMonth) * PIXELS_PER_MONTH;
                }}

                function positionTodayLine() {{
                    const todayLine = document.getElementById('today-line-{project["id"]}');
                    const today = new Date(), todayUTC = new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()));
                    const chartStart = parseDate(dataMinStr), chartEnd = parseDate(dataMaxStr);
                    if (chartStart && chartEnd && !isNaN(chartStart.getTime()) && !isNaN(chartEnd.getTime()) && todayUTC >= chartStart && todayUTC <= chartEnd) {{ 
                        const offset = getPosition(todayUTC); 
                        todayLine.style.left = offset + 'px'; 
                        todayLine.style.display = 'block'; 
                    }} else {{ 
                        todayLine.style.display = 'none'; 
                    }}
                }}

                function showTooltip(e, task, tipo) {{
                    const tooltip = document.getElementById('tooltip-{project["id"]}');
                    let content = '<b>' + task.name + '</b><br>';
                    if (tipo === 'previsto') {{ 
                        content += 'Previsto: ' + task.inicio_previsto + ' - ' + task.termino_previsto + '<br>Duração: ' + task.duracao_prev_meses + 'M'; 
                    }} else {{ 
                        content += 'Real: ' + task.inicio_real + ' - ' + task.termino_real + '<br>Duração: ' + task.duracao_real_meses + 'M<br>Variação Término: ' + task.vt_text + '<br>Variação Duração: ' + task.vd_text; 
                    }}
                    content += '<br><b>Progresso: ' + task.progress + '%</b><br>Setor: ' + task.setor + '<br>Grupo: ' + task.grupo;
                    tooltip.innerHTML = content;
                    tooltip.classList.add('show');
                    const tooltipWidth = tooltip.offsetWidth, tooltipHeight = tooltip.offsetHeight;
                    const viewportWidth = window.innerWidth, viewportHeight = window.innerHeight;
                    const mouseX = e.clientX, mouseY = e.clientY;
                    const padding = 15;
                    let left, top;
                    if ((mouseX + padding + tooltipWidth) > viewportWidth) {{ 
                        left = mouseX - padding - tooltipWidth; 
                    }} else {{ 
                        left = mouseX + padding; 
                    }}
                    if ((mouseY + padding + tooltipHeight) > viewportHeight) {{ 
                        top = mouseY - padding - tooltipHeight; 
                    }} else {{ 
                        top = mouseY + padding; 
                    }}
                    if (left < padding) left = padding;
                    if (top < padding) top = padding;
                    tooltip.style.left = left + 'px';
                    tooltip.style.top = top + 'px';
                }}

                function hideTooltip() {{ 
                    document.getElementById('tooltip-{project["id"]}').classList.remove('show'); 
                }}

                function renderMonthDividers() {{
                    const chartContainer = document.getElementById('chart-container-{project["id"]}');
                    chartContainer.querySelectorAll('.month-divider, .month-divider-label').forEach(el => el.remove());
                    let currentDate = parseDate(dataMinStr);
                    const dataMax = parseDate(dataMaxStr);
                     if (!currentDate || !dataMax || isNaN(currentDate.getTime()) || isNaN(dataMax.getTime())) return;
                    let totalMonths = 0;
                    while (currentDate <= dataMax && totalMonths < 240) {{
                        const left = getPosition(currentDate);
                        const divider = document.createElement('div'); 
                        divider.className = 'month-divider';
                        if (currentDate.getUTCMonth() === 0) divider.classList.add('first');
                        divider.style.left = left + 'px'; 
                        chartContainer.appendChild(divider);
                        currentDate.setUTCMonth(currentDate.getUTCMonth() + 1);
                        totalMonths++;
                    }}
                }}

                function setupEventListeners() {{
                    const ganttChartContent = document.getElementById('gantt-chart-content-{project["id"]}'), sidebarContent = document.getElementById('gantt-sidebar-content-{project['id']}');
                    const fullscreenBtn = document.getElementById('fullscreen-btn-{project["id"]}'), toggleBtn = document.getElementById('toggle-sidebar-btn-{project['id']}');
                    const filterBtn = document.getElementById('filter-btn-{project["id"]}');
                    const filterMenu = document.getElementById('filter-menu-{project['id']}');
                    const container = document.getElementById('gantt-container-{project["id"]}');

                    const applyBtn = document.getElementById('filter-apply-btn-{project["id"]}');
                    if (applyBtn) applyBtn.addEventListener('click', () => applyFiltersAndRedraw());

                    if (fullscreenBtn) fullscreenBtn.addEventListener('click', () => toggleFullscreen());

                    // Adiciona listener para o botão de filtro
                    if (filterBtn) {{
                        filterBtn.addEventListener('click', () => {{
                            filterMenu.classList.toggle('is-open');
                        }});
                    }}

                    // Fecha o menu de filtro ao clicar fora
                    document.addEventListener('click', (event) => {{ 
                        if (filterMenu && filterBtn && !filterMenu.contains(event.target) && !filterBtn.contains(event.target)) {{
                            filterMenu.classList.remove('is-open');
                        }}
                    }});

                    if (container) container.addEventListener('fullscreenchange', () => handleFullscreenChange());

                    if (toggleBtn) toggleBtn.addEventListener('click', () => toggleSidebar());
                    if (ganttChartContent && sidebarContent) {{
                        let isSyncing = false;
                        ganttChartContent.addEventListener('scroll', () => {{ if (!isSyncing) {{ isSyncing = true; sidebarContent.scrollTop = ganttChartContent.scrollTop; isSyncing = false; }} }});
                        sidebarContent.addEventListener('scroll', () => {{ if (!isSyncing) {{ isSyncing = true; ganttChartContent.scrollTop = sidebarContent.scrollTop; isSyncing = false; }} }});
                        let isDown = false, startX, scrollLeft;
                        ganttChartContent.addEventListener('mousedown', (e) => {{ isDown = true; ganttChartContent.classList.add('active'); startX = e.pageX - ganttChartContent.offsetLeft; scrollLeft = ganttChartContent.scrollLeft; }});
                        ganttChartContent.addEventListener('mouseleave', () => {{ isDown = false; ganttChartContent.classList.remove('active'); }});
                        ganttChartContent.addEventListener('mouseup', () => {{ isDown = false; ganttChartContent.classList.remove('active'); }});
                        ganttChartContent.addEventListener('mousemove', (e) => {{ if (!isDown) return; e.preventDefault(); const x = e.pageX - ganttChartContent.offsetLeft; const walk = (x - startX) * 2; ganttChartContent.scrollLeft = scrollLeft - walk; }});
                    }}
                }}

                function toggleSidebar() {{ 
                    document.getElementById('gantt-sidebar-wrapper-{project["id"]}').classList.toggle('collapsed'); 
                }}

                function toggleFullscreen() {{
                    const container = document.getElementById('gantt-container-{project["id"]}');
                    if (!document.fullscreenElement) {{
                        container.requestFullscreen().catch(err => alert('Erro: ' + err.message));
                    }} else {{
                        document.exitFullscreen();
                    }}
                }}

                function handleFullscreenChange() {{
                        const btn = document.getElementById('fullscreen-btn-{project["id"]}');
                        const container = document.getElementById('gantt-container-{project["id"]}');
                        if (document.fullscreenElement === container) {{
                            btn.innerHTML = '<span><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 9l6 6m0-6l-6 6M3 20.29V5a2 2 0 012-2h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2v-.29"></path></svg></span>';
                            btn.classList.add('is-fullscreen');
                        }} else {{
                            btn.innerHTML = '<span><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path></svg></span>';
                            btn.classList.remove('is-fullscreen');
                            document.getElementById('filter-menu-{project["id"]}').classList.remove('is-open');
                        }}
                    }}
                function updatePulmaoInputVisibility() {{
                    const radioCom = document.getElementById('filter-pulmao-com-{project["id"]}');
                    const mesesGroup = document.getElementById('pulmao-meses-group-{project["id"]}');
                    if (radioCom && mesesGroup) {{
                        if (radioCom.checked) {{ 
                            mesesGroup.style.display = 'block'; 
                        }} else {{ 
                            mesesGroup.style.display = 'none'; 
                        }}
                    }}
                 }}

                // Função para atualizar opções de empreendimento baseado nas UGBs selecionadas
                function updateEmpreendimentoOptionsConsolidado() {{
                    const selUgbArray = vsUgbConsolidado ? vsUgbConsolidado.getValue() || [] : [];
                    
                    // Obter tarefas da etapa atual (usar allTasks_baseData que é a fonte correta)
                    let tasksAtual = allTasks_baseData || [];
                    
                    if (!tasksAtual || tasksAtual.length === 0) {{
                        console.warn('Nenhuma task disponível para filtrar empreendimentos');
                        return;
                    }}
                    
                    // Filtrar empreendimentos por UGB
                    let filteredEmps = [...new Set(tasksAtual.map(t => t.name))];
                    if (selUgbArray.length > 0 && !selUgbArray.includes('Todas')) {{
                        filteredEmps = [...new Set(tasksAtual
                            .filter(t => selUgbArray.includes(t.ugb))
                            .map(t => t.name))];
                    }}
                    
                    // Atualizar opções do VirtualSelect de empreendimento
                    const empreendimentoOptions = ["Todos"].concat(filteredEmps).map(e => ({{ label: e, value: e }}));
                    
                    // Destruir e recriar o VirtualSelect para forçar re-render
                    if (vsEmpreendimento) {{
                        vsEmpreendimento.destroy();
                    }}
                    
                    vsEmpreendimento = VirtualSelect.init({{
                        multiple: true,
                        search: true,
                        optionsCount: 6,
                        showResetButton: true,
                        resetButtonText: 'Limpar',
                        selectAllText: 'Selecionar Todos',
                        allOptionsSelectedText: 'Todos',
                        optionsSelectedText: 'selecionados',
                        searchPlaceholderText: 'Buscar...',
                        optionHeight: '30px',
                        popupDropboxBreakpoint: '3000px',
                        noOptionsText: 'Nenhuma opção encontrada',
                        noSearchResultsText: 'Nenhum resultado encontrado',
                        ele: '#filter-empreendimento-{project["id"]}',
                        options: empreendimentoOptions,
                        placeholder: "Selecionar Empreendimento(s)",
                        selectedValue: ["Todos"]
                    }});
                    
                    console.log('Opções de empreendimento no consolidado atualizadas. Total:', filteredEmps.length);
                    console.log('Empreendimentos:', filteredEmps);
                }}

                // *** FUNÇÃO populateFilters MODIFICADA ***
                function populateFilters() {{
                    if (filtersPopulated) return;

                    // *** 1. NOVO FILTRO DE ETAPA (Single Select) ***
                    selEtapaConsolidada = document.getElementById('filter-etapa-consolidada-{project["id"]}');
                    filterOptions.etapas_consolidadas.forEach(etapaNome => {{
                        const isSelected = (etapaNome === initialStageName) ? 'selected' : '';
                        selEtapaConsolidada.innerHTML += `<option value="${{etapaNome}}" ${{isSelected}}>${{etapaNome}}</option>`;
                    }});

                    const vsConfig = {{
                        multiple: true,
                        search: true,
                        optionsCount: 6,
                        showResetButton: true,
                        resetButtonText: 'Limpar',
                        selectAllText: 'Selecionar Todos',
                        allOptionsSelectedText: 'Todos',
                        optionsSelectedText: 'selecionados',
                        searchPlaceholderText: 'Buscar...',
                        optionHeight: '30px',
                        popupDropboxBreakpoint: '3000px',
                        noOptionsText: 'Nenhuma opção encontrada',
                        noSearchResultsText: 'Nenhum resultado encontrado',
                    }};

                    // *** NOVO: FILTRO DE UGB ***
                    const ugbOptions = (filterOptions.ugbs || ["Todas"]).map(u => ({{ label: u, value: u }}));
                    vsUgbConsolidado = VirtualSelect.init({{
                        ...vsConfig,
                        ele: '#filter-ugb-consolidado-{project["id"]}',
                        options: ugbOptions,
                        placeholder: "Selecionar UGB(s)",
                        selectedValue: ["Todas"]
                    }});
                    
                    // Listener para atualizar opções de empreendimento quando UGB mudar
                    document.querySelector('#filter-ugb-consolidado-{project["id"]}').addEventListener('change', function() {{
                        updateEmpreendimentoOptionsConsolidado();
                    }});

                    // *** 2. FILTRO DE SETOR (REMOVIDO) ***
                    // if (filterOptions.setores) {{
                    //     const setorOptions = filterOptions.setores.map(s => ({{ label: s, value: s }}));
                    //     vsSetor = VirtualSelect.init({{ ... }});
                    // }}

                    // *** 3. FILTRO DE GRUPO (REMOVIDO) ***
                    // if (filterOptions.grupos) {{
                    //     const grupoOptions = filterOptions.grupos.map(g => ({{ label: g, value: g }}));
                    //     vsGrupo = VirtualSelect.init({{ ... }});
                    // }}

                    // *** 4. FILTRO DE EMPREENDIMENTO (Renomeado) ***
                    // Inicializar com todas as opções primeiro
                    const empreendimentoOptions = filterOptions.empreendimentos.map(e => ({{ label: e, value: e }}));
                    console.log('Inicializando vsEmpreendimento com opções:', empreendimentoOptions);
                    
                    vsEmpreendimento = VirtualSelect.init({{ // Renomeado de vsEtapa
                        ...vsConfig,
                        ele: '#filter-empreendimento-{project["id"]}', // ID Modificado
                        options: empreendimentoOptions,
                        placeholder: "Selecionar Empreendimento(s)",
                        selectedValue: ["Todos"]
                    }});
                    
                    console.log('vsEmpreendimento inicializado:', vsEmpreendimento ? 'OK' : 'FALHOU');

                    // *** 5. RESTO DOS FILTROS (Idêntico) ***
                    const visRadio = document.querySelector('input[name="filter-vis-{project['id']}"][value="' + tipoVisualizacao + '"]');
                    if(visRadio) visRadio.checked = true;

                    const radioCom = document.getElementById('filter-pulmao-com-{project["id"]}');
                    const radioSem = document.getElementById('filter-pulmao-sem-{project["id"]}');
                    radioCom.addEventListener('change', updatePulmaoInputVisibility);
                    radioSem.addEventListener('change', updatePulmaoInputVisibility);
                    const pulmaoRadioInitial = document.querySelector('input[name="filter-pulmao-{project['id']}"][value="' + initialPulmaoStatus + '"]');
                    if(pulmaoRadioInitial) pulmaoRadioInitial.checked = true;
                    document.getElementById('filter-pulmao-meses-{project["id"]}').value = {pulmao_meses};
                    updatePulmaoInputVisibility();

                    filtersPopulated = true;
                }}

                // *** FUNÇÃO updateProjectTitle (Nova/Modificada) ***
                function updateProjectTitle(newStageName) {{
                    const projectTitle = document.querySelector('#gantt-sidebar-wrapper-{project["id"]} .project-title-row span');
                    if (projectTitle) {{
                        projectTitle.textContent = `Comparativo: ${{newStageName}}`;
                        // Atualiza também o 'projectData' global se necessário, embora o 'name' não seja mais usado
                        projectData[0].name = `Comparativo: ${{newStageName}}`;
                    }}
                }}

                // *** FUNÇÃO applyFiltersAndRedraw MODIFICADA ***
                function applyFiltersAndRedraw() {{
                    try {{
                        // *** 1. LER A ETAPA PRIMEIRO ***
                        const selEtapaNome = selEtapaConsolidada.value;
                        
                        // *** 2. LER OUTROS FILTROS ***
                        // Nota: UGB não é lido aqui pois apenas filtra opções de empreendimento, não tarefas
                        const selEmpreendimentoArray = vsEmpreendimento ? vsEmpreendimento.getValue() || [] : []; // Renomeado
                        
                        const selConcluidas = document.getElementById('filter-concluidas-{project["id"]}').checked;
                        const selVis = document.querySelector('input[name="filter-vis-{project['id']}"]:checked').value;
                        const selPulmao = document.querySelector('input[name="filter-pulmao-{project['id']}"]:checked').value;
                        const selPulmaoMeses = parseInt(document.getElementById('filter-pulmao-meses-{project["id"]}').value, 10) || 0;

                        // *** FECHAR MENU DE FILTROS ***
                        document.getElementById('filter-menu-{project["id"]}').classList.remove('is-open');

                        // *** 3. ATUALIZAR DADOS BASE SE A ETAPA MUDOU ***
                        if (selEtapaNome !== currentStageName) {{
                            currentStageName = selEtapaNome;
                            // Pegar os dados "crus" para a nova etapa
                            allTasks_baseData = JSON.parse(JSON.stringify(allDataByStage[currentStageName] || []));
                            console.log(`Mudando para etapa: ${{currentStageName}}. Tasks carregadas: ${{allTasks_baseData.length}}`);
                        }}

                        // Começar com os dados da etapa (já atualizados ou não)
                        let baseTasks = JSON.parse(JSON.stringify(allTasks_baseData));

                        // *** 4. APLICAR LÓGICA DE PULMÃO (CORRIGIDO) ***
                        if (selPulmao === 'Com Pulmão' && selPulmaoMeses > 0) {{
                            const offsetMeses = -selPulmaoMeses;
                            // Passa o nome da etapa atual para a lógica - APENAS PREVISTO AFETADO
                            baseTasks = aplicarLogicaPulmaoConsolidado(baseTasks, offsetMeses, currentStageName);
                        }}

                        // *** 5. APLICAR FILTROS SECUNDÁRIOS ***
                        let filteredTasks = baseTasks;

                        // Nota: Filtro de UGB não filtra tarefas, apenas opções de empreendimento

                        // if (selSetorArray.length > 0 && !selSetorArray.includes('Todos')) {{
                        //     filteredTasks = filteredTasks.filter(t => selSetorArray.includes(t.setor));
                        // }} // REMOVIDO
                        
                        // if (selGrupoArray.length > 0 && !selGrupoArray.includes('Todos')) {{
                        //     filteredTasks = filteredTasks.filter(t => selGrupoArray.includes(t.grupo));
                        // }} // REMOVIDO
                        
                        // Lógica de filtro de empreendimento (antiga 'etapa')
                        if (selEmpreendimentoArray.length > 0 && !selEmpreendimentoArray.includes('Todos')) {{
                            filteredTasks = filteredTasks.filter(t => selEmpreendimentoArray.includes(t.name));
                        }}

                        if (selConcluidas) {{
                            filteredTasks = filteredTasks.filter(t => t.progress < 100);
                        }}

                        console.log('Empreendimentos após filtros:', filteredTasks.length);

                        // *** 6. ATUALIZAR DADOS E REDESENHAR ***
                        projectData[0].tasks = filteredTasks; // Atualiza as tarefas ativas
                        tipoVisualizacao = selVis;
                        pulmaoStatus = selPulmao;

                        // *** 7. REPLICAR BASELINES SELECIONADAS ***
                        // Após filtrar, reaplicar as baselines que o usuário selecionou
                        filteredTasks.forEach(task => {{
                            const emp = task.name;
                            const selectedBaseline = baselinesPorEmpreendimento[emp];
                            
                            if (selectedBaseline && selectedBaseline !== "P0-(padrão)") {{
                                // Aplicar baseline sem re-renderizar (será feito no final)
                                if (task.baselines && task.baselines[selectedBaseline]) {{
                                    const baselineData = task.baselines[selectedBaseline];
                                    
                                    if (baselineData.start !== null && baselineData.end !== null) {{
                                        // Aplicar dados da baseline
                                        let startPrevisto = baselineData.start;
                                        let endPrevisto = baselineData.end;
                                        
                                        // *** APLICAR PULMÃO SE NECESSÁRIO ***
                                        if (selPulmao === 'Com Pulmão' && selPulmaoMeses > 0) {{
                                            const offsetMeses = -selPulmaoMeses;
                                            const startDate = parseDate(startPrevisto);
                                            const endDate = parseDate(endPrevisto);
                                            
                                            if (startDate && endDate) {{
                                                startDate.setMonth(startDate.getMonth() + offsetMeses);
                                                endDate.setMonth(endDate.getMonth() + offsetMeses);
                                                
                                                startPrevisto = startDate.toISOString().split('T')[0];
                                                endPrevisto = endDate.toISOString().split('T')[0];
                                            }}
                                        }}
                                        
                                        task.start_previsto = startPrevisto;
                                        task.end_previsto = endPrevisto;
                                        task.inicio_previsto = formatDateDisplay(task.start_previsto);
                                        task.termino_previsto = formatDateDisplay(task.end_previsto);
                                        
                                        const startDate = parseDate(task.start_previsto);
                                        const endDate = parseDate(task.end_previsto);
                                        if (startDate && endDate) {{
                                            const diffDays = (endDate - startDate) / (1000 * 60 * 60 * 24);
                                            task.duracao_prev_meses = (diffDays / 30.4375).toFixed(1).replace('.', ',');
                                        }}
                                        
                                        if (task.end_real_original_raw && task.end_previsto) {{
                                            const endReal = parseDate(task.end_real_original_raw);
                                            const endPrev = parseDate(task.end_previsto);
                                            if (endReal && endPrev) {{
                                                const diffDays = Math.round((endReal - endPrev) / (1000 * 60 * 60 * 24));
                                                task.vt_text = diffDays > 0 ? `+${{diffDays}}d` : diffDays < 0 ? `${{diffDays}}d` : '0d';
                                            }}
                                        }}
                                    }}
                                }}
                            }}
                        }});

                        // *** 8. ATUALIZAR TÍTULO DO PROJETO ***
                        updateProjectTitle(currentStageName);

                        // Redesenhar
                        renderSidebar();
                        renderChart();

                    }} catch (error) {{
                        console.error('Erro ao aplicar filtros no consolidado:', error);
                        alert('Erro ao aplicar filtros: ' + error.message);
                    }}
                }}

                // DEBUG: Verificar dados antes de inicializar
                console.log('Dados do projeto consolidado (inicial):', projectData);
                console.log('Tasks base consolidado (inicial):', allTasks_baseData);
                console.log('TODOS os dados de etapa (full):', allDataByStage);
                
                //  FUNÇÃO GLOBAL PARA APLICAR BASELINE
                window.handleBaselineChange = function(empreendimento, baselineName) {{
                    console.log(`📊 Baseline selected: ${{baselineName}} for ${{empreendimento}}`);
                    
                    // Update URL parameters to trigger Streamlit rerun
                    const url = new URL(window.location.href);
                    url.searchParams.set('change_baseline', baselineName);
                    url.searchParams.set('empreendimento', empreendimento);
                    
                    // Reload page with new parameters
                    window.location.href = url.toString();
                }}
                
                // *** BASELINE INDIVIDUAL POR EMPREENDIMENTO (MODIFICADO) ***
                // Mapa para rastrear baseline ativa de cada empreendimento
                let baselinesPorEmpreendimento = {{}};
                
                // Inicializar estado com P0 para todos
                function initializeBaselineState() {{
                    const tasks = projectData[0].tasks;
                    if (tasks) {{
                        tasks.forEach(task => {{
                            baselinesPorEmpreendimento[task.name] = "P0-(padrão)";
                        }});
                    }}
                    console.log('Estado de baselines inicializado:', baselinesPorEmpreendimento);
                }}
                
                // Aplicar baseline para um empreendimento específico
                function applyBaselineForEmp(empreendimento, baselineName) {{
                    console.log(`🔄 Aplicando baseline "${{baselineName}}" para: ${{empreendimento}}`);
                    
                    const tasks = projectData[0].tasks;
                    if (!tasks || tasks.length === 0) {{
                        console.warn('Nenhuma task disponível');
                        return;
                    }}
                    
                    // Atualizar estado
                    baselinesPorEmpreendimento[empreendimento] = baselineName;
                    
                    // Encontrar a task deste empreendimento
                    const task = tasks.find(t => t.name === empreendimento);
                    
                    if (!task) {{
                        console.warn(`Task não encontrada para empreendimento: ${{empreendimento}}`);
                        return;
                    }}
                    
                    if (!task.baselines || !task.baselines[baselineName]) {{
                        console.warn(`Task ${{task.name}} não tem baseline ${{baselineName}}`);
                        return;
                    }}
                    
                    const baselineData = task.baselines[baselineName];
                    
                    if (baselineData.start !== null && baselineData.end !== null) {{
                        // Atualizar datas previstas
                        task.start_previsto = baselineData.start;
                        task.end_previsto = baselineData.end;
                        
                        // Recalcular campos de exibição
                        task.inicio_previsto = formatDateDisplay(task.start_previsto);
                        task.termino_previsto = formatDateDisplay(task.end_previsto);
                        
                        // Recalcular duração
                        const startDate = parseDate(task.start_previsto);
                        const endDate = parseDate(task.end_previsto);
                        if (startDate && endDate) {{
                            const diffDays = (endDate - startDate) / (1000 * 60 * 60 * 24);
                            task.duracao_prev_meses = (diffDays / 30.4375).toFixed(1).replace('.', ',');
                        }}
                        
                        // Recalcular VT (Variação de Término)
                        if (task.end_real_original_raw && task.end_previsto) {{
                            const endReal = parseDate(task.end_real_original_raw);
                            const endPrev = parseDate(task.end_previsto);
                            if (endReal && endPrev) {{
                                const diffDays = Math.round((endReal - endPrev) / (1000 * 60 * 60 * 24));
                                task.vt_text = diffDays > 0 ? `+${{diffDays}}d` : diffDays < 0 ? `${{diffDays}}d` : '0d';
                            }}
                        }}
                        
                        console.log(`✅ Baseline aplicada para ${{empreendimento}}: ${{baselineName}}`);
                    }} else {{
                        // Baseline não tem dados para esta etapa
                        task.start_previsto = null;
                        task.end_previsto = null;
                        task.inicio_previsto = "N/D";
                        task.termino_previsto = "N/D";
                        task.duracao_prev_meses = "-";
                        task.vt_text = "-";
                        
                        console.log(`⚠️ Baseline ${{baselineName}} não tem dados para ${{empreendimento}}`);
                    }}
                    
                    // Re-renderizar o gráfico
                    renderSidebar();
                    renderChart();
                    
                    console.log(`🎨 Gráfico re-renderizado após aplicar baseline`);
                }}
                
                // *** FUNÇÕES DE APLICAÇÃO RÁPIDA (NOVO) ***
                
                // Encontrar última baseline disponível para um empreendimento
                function findLatestBaseline(baselines) {{
                    if (!baselines) return "P0-(padrão)";
                    
                    const baselineNames = Object.keys(baselines);
                    
                    // Filtrar apenas baselines válidas (não P0)
                    const validBaselines = baselineNames.filter(name => name !== "P0-(padrão)");
                    
                    if (validBaselines.length === 0) {{
                        return "P0-(padrão)";
                    }}
                    
                    // Ordenar por hierarquia numérica (P10 > P9 > ... > P1)
                    validBaselines.sort((a, b) => {{
                        // Extrair número de P1, P2, P10, etc.
                        const numA = parseInt(a.match(/P(\d+)/)?.[1] || '0');
                        const numB = parseInt(b.match(/P(\d+)/)?.[1] || '0');
                        
                        // Maior número = mais recente
                        return numB - numA;
                    }});
                    
                    console.log(`Última baseline encontrada: ${{validBaselines[0]}}`);
                    return validBaselines[0];
                }}
                
                // Aplicar P0 para todos os empreendimentos
                function applyP0ToAll() {{
                    console.log('🔄 Aplicando P0 para todos os empreendimentos');
                    
                    const tasks = projectData[0].tasks;
                    if (!tasks) return;
                    
                    let count = 0;
                    tasks.forEach(task => {{
                        const emp = task.name;
                        const baselineName = "P0-(padrão)";
                        
                        // Atualizar estado
                        baselinesPorEmpreendimento[emp] = baselineName;
                        
                        // Aplicar baseline P0 diretamente
                        if (task.baselines && task.baselines[baselineName]) {{
                            const baselineData = task.baselines[baselineName];
                            
                            if (baselineData.start !== null && baselineData.end !== null) {{
                                task.start_previsto = baselineData.start;
                                task.end_previsto = baselineData.end;
                                task.inicio_previsto = formatDateDisplay(task.start_previsto);
                                task.termino_previsto = formatDateDisplay(task.end_previsto);
                                
                                const startDate = parseDate(task.start_previsto);
                                const endDate = parseDate(task.end_previsto);
                                if (startDate && endDate) {{
                                    const diffDays = (endDate - startDate) / (1000 * 60 * 60 * 24);
                                    task.duracao_prev_meses = (diffDays / 30.4375).toFixed(1).replace('.', ',');
                                }}
                                
                                if (task.end_real_original_raw && task.end_previsto) {{
                                    const endReal = parseDate(task.end_real_original_raw);
                                    const endPrev = parseDate(task.end_previsto);
                                    if (endReal && endPrev) {{
                                        const diffDays = Math.round((endReal - endPrev) / (1000 * 60 * 60 * 24));
                                        task.vt_text = diffDays > 0 ? `+${{diffDays}}d` : diffDays < 0 ? `${{diffDays}}d` : '0d';
                                    }}
                                }}
                            }}
                        }}
                        
                        // Atualizar dropdown visual
                        const dropdown = document.querySelector(`select[data-emp="${{emp}}"]`);
                        if (dropdown) {{
                            dropdown.value = baselineName;
                        }}
                        
                        count++;
                    }});
                    
                    // Renderizar apenas uma vez no final
                    renderSidebar();
                    renderChart();
                    
                    console.log(`✅ P0 aplicado para ${{count}} empreendimentos`);
                }}

                
                // Aplicar última baseline para todos os empreendimentos
                function applyLatestToAll() {{
                    console.log('🔄 Aplicando última baseline para todos os empreendimentos');
                    
                    const tasks = projectData[0].tasks;
                    if (!tasks) return;
                    
                    let count = 0;
                    tasks.forEach(task => {{
                        const emp = task.name;
                        
                        // Encontrar última baseline deste empreendimento
                        const latestBaseline = findLatestBaseline(task.baselines);
                        
                        if (latestBaseline) {{
                            // Atualizar estado
                            baselinesPorEmpreendimento[emp] = latestBaseline;
                            
                            // Aplicar baseline diretamente
                            if (task.baselines && task.baselines[latestBaseline]) {{
                                const baselineData = task.baselines[latestBaseline];
                                
                                if (baselineData.start !== null && baselineData.end !== null) {{
                                    task.start_previsto = baselineData.start;
                                    task.end_previsto = baselineData.end;
                                    task.inicio_previsto = formatDateDisplay(task.start_previsto);
                                    task.termino_previsto = formatDateDisplay(task.end_previsto);
                                    
                                    const startDate = parseDate(task.start_previsto);
                                    const endDate = parseDate(task.end_previsto);
                                    if (startDate && endDate) {{
                                        const diffDays = (endDate - startDate) / (1000 * 60 * 60 * 24);
                                        task.duracao_prev_meses = (diffDays / 30.4375).toFixed(1).replace('.', ',');
                                    }}
                                    
                                    if (task.end_real_original_raw && task.end_previsto) {{
                                        const endReal = parseDate(task.end_real_original_raw);
                                        const endPrev = parseDate(task.end_previsto);
                                        if (endReal && endPrev) {{
                                            const diffDays = Math.round((endReal - endPrev) / (1000 * 60 * 60 * 24));
                                            task.vt_text = diffDays > 0 ? `+${{diffDays}}d` : diffDays < 0 ? `${{diffDays}}d` : '0d';
                                        }}
                                    }}
                                }} else {{
                                    task.start_previsto = null;
                                    task.end_previsto = null;
                                    task.inicio_previsto = "N/D";
                                    task.termino_previsto = "N/D";
                                    task.duracao_prev_meses = "-";
                                    task.vt_text = "-";
                                }}
                            }}
                            
                            // Atualizar dropdown visual
                            const dropdown = document.querySelector(`select[data-emp="${{emp}}"]`);
                            if (dropdown) {{
                                dropdown.value = latestBaseline;
                            }}
                            
                            count++;
                        }}
                    }});
                    
                    // Renderizar apenas uma vez no final
                    renderSidebar();
                    renderChart();
                    
                    console.log(`✅ Última baseline aplicada para ${{count}} empreendimentos`);
                }}

                
                // Gerenciar checkboxes de aplicação rápida
                function handleQuickApply(mode) {{
                    const p0Checkbox = document.getElementById('apply-p0-all-{project["id"]}');
                    const latestCheckbox = document.getElementById('apply-latest-all-{project["id"]}');
                    
                    if (mode === 'p0') {{
                        // Desmarcar "latest"
                        if (latestCheckbox) latestCheckbox.checked = false;
                        
                        if (p0Checkbox && p0Checkbox.checked) {{
                            applyP0ToAll();
                        }}
                    }} else if (mode === 'latest') {{
                        // Desmarcar "p0"
                        if (p0Checkbox) p0Checkbox.checked = false;
                        
                        if (latestCheckbox && latestCheckbox.checked) {{
                            applyLatestToAll();
                        }}
                    }}
                }}
                
                // Configurar redimensionamento arrastável
                function setupBaselineResize() {{
                    const corner = document.querySelector('.baseline-resize-corner');
                    const selector = document.getElementById('baseline-selector-{project["id"]}');
                    const table = selector ? selector.querySelector('.baseline-selector-table') : null;
                    
                    if (!corner || !selector || !table) return;
                    
                    let isResizing = false;
                    let startX = 0;
                    let startY = 0;
                    let startWidth = 0;
                    let startHeight = 0;
                    
                    corner.addEventListener('mousedown', function(e) {{
                        isResizing = true;
                        startX = e.clientX;
                        startY = e.clientY;
                        startWidth = selector.offsetWidth;
                        startHeight = table.offsetHeight;
                        
                        // Prevenir seleção de texto
                        e.preventDefault();
                        e.stopPropagation();
                        document.body.style.userSelect = 'none';
                        document.body.style.cursor = 'nwse-resize';
                    }});
                    
                    document.addEventListener('mousemove', function(e) {{
                        if (!isResizing) return;
                        
                        // Calcular nova largura (arrastar para esquerda diminui, direita aumenta)
                        const diffX = startX - e.clientX; // Invertido porque é borda esquerda
                        const newWidth = Math.max(250, Math.min(600, startWidth + diffX));
                        selector.style.width = `${{newWidth}}px`;
                        
                        // Calcular nova altura (arrastar para baixo aumenta, cima diminui)
                        const diffY = e.clientY - startY;
                        const newHeight = Math.max(150, Math.min(600, startHeight + diffY));
                        table.style.maxHeight = `${{newHeight}}px`;
                    }});
                    
                    document.addEventListener('mouseup', function() {{
                        if (isResizing) {{
                            isResizing = false;
                            document.body.style.userSelect = '';
                            document.body.style.cursor = '';
                        }}
                    }});
                }}


                
                // Event Listeners para baseline
                function setupBaselineListeners() {{
                    const baselineBtn = document.getElementById('baseline-btn-{project["id"]}');
                    const baselineSelector = document.getElementById('baseline-selector-{project["id"]}');
                    const filterMenu = document.getElementById('filter-menu-{project["id"]}');
                    
                    if (baselineBtn) {{
                        baselineBtn.addEventListener('click', function(e) {{
                            e.stopPropagation();
                            
                            // Fechar filtro se aberto
                            if (filterMenu) {{
                                filterMenu.classList.remove('is-open');
                            }}
                            
                            // Toggle baseline selector
                            if (baselineSelector.style.display === 'block') {{
                                baselineSelector.style.display = 'none';
                            }} else {{
                                baselineSelector.style.display = 'block';
                            }}
                        }});
                    }}
                    
                    // Fechar ao clicar fora
                    document.addEventListener('click', function(e) {{
                        if (baselineSelector && baselineBtn && 
                            !baselineSelector.contains(e.target) && 
                            e.target !== baselineBtn && 
                            !baselineBtn.contains(e.target)) {{
                            baselineSelector.style.display = 'none';
                        }}
                    }});
                }}
                
                // Inicializar o Gantt Consolidado
                initGantt();
                setupBaselineListeners();  // *** NOVO: Ativar event listeners de baseline ***
                setupBaselineResize();      // *** NOVO: Ativar redimensionamento arrastável ***
            </script>
        </body>
        </html>
    """
    components.html(gantt_html, height=altura_gantt, scrolling=True)
    # st.markdown("---") no consolidado, pois ele não é parte de um loop

# --- *** FUNÇÃO gerar_gantt_por_setor (NOVA) *** ---
def gerar_gantt_por_setor(df, tipo_visualizacao, df_original_para_ordenacao, pulmao_status, pulmao_meses, setor_selecionado_inicialmente):
    """
    Gera um gráfico de Gantt HTML organizado por SETOR que contém dados para TODOS os setores
    e permite a troca de setores via menu flutuante.
    
    'setor_selecionado_inicialmente' define qual setor mostrar no carregamento.
    
    Diferente do consolidado (que agrupa por etapa), este agrupa por SETOR,
    mostrando todas as etapas de um setor em todos os empreendimentos.
    """
    
    # --- 1. Preparação dos Dados ---
    df_gantt = df.copy()
    
    for col in ["Inicio_Prevista", "Termino_Prevista", "Inicio_Real", "Termino_Real"]:
        if col in df_gantt.columns:
            df_gantt[col] = pd.to_datetime(df_gantt[col], errors="coerce")
    
    if "% concluído" not in df_gantt.columns:
        df_gantt["% concluído"] = 0
    df_gantt["% concluído"] = df_gantt["% concluído"].fillna(0).apply(converter_porcentagem)
    
    # --- FILTRO: Remover etapas pai ANTES da agregação ---
    # Etapas pai são aquelas que têm subetapas definidas em SUBETAPAS
    # Incluindo todas as variações possíveis de nomes
    etapas_pai = [
        # Variações de ENG. LIMP.
        "ENG. LIMP.", "ENG. LIMP", "ENG.LIMP", "ENG.LIMP.", "ENGLIMP", "ENG LIMP",
        # Variações de ENG. TER.
        "ENG. TER.", "ENG. TER", "ENG.TER", "ENG.TER.", "ENGTER", "ENG TER",
        # Variações de ENG. INFRA
        "ENG. INFRA", "ENG.INFRA", "ENGINFRA", "ENG INFRA",
        # Variações de ENG. PAV
        "ENG. PAV", "ENG.PAV", "ENGPAV", "ENG PAV",
        # Adicionar também as chaves do dicionário SUBETAPAS
    ] + list(SUBETAPAS.keys())
    
    # Remover duplicatas
    etapas_pai = list(set(etapas_pai))
    
    # DEBUG: Imprimir etapas únicas ANTES do filtro
    print("=" * 80)
    print("DEBUG - ETAPAS ÚNICAS NO DATAFRAME (ANTES DO FILTRO):")
    etapas_unicas = sorted(df_gantt['Etapa'].unique())
    for etapa in etapas_unicas:
        if any(pai.lower() in etapa.lower() for pai in ["eng", "limp", "ter", "infra", "pav"]):
            print(f"  - '{etapa}'")
    print(f"\nETAPAS PAI QUE SERÃO FILTRADAS: {etapas_pai}")
    print("=" * 80)
    
    df_gantt = df_gantt[~df_gantt['Etapa'].isin(etapas_pai)]
    
    # DEBUG: Imprimir etapas únicas DEPOIS do filtro
    print("DEBUG - ETAPAS ÚNICAS NO DATAFRAME (DEPOIS DO FILTRO):")
    etapas_unicas_depois = sorted(df_gantt['Etapa'].unique())
    for etapa in etapas_unicas_depois:
        if any(pai.lower() in etapa.lower() for pai in ["eng", "limp", "ter", "infra", "pav"]):
            print(f"  - '{etapa}'")
    print("=" * 80)
    
    # Agrupar por SETOR, Empreendimento e Etapa
    df_gantt_agg = df_gantt.groupby(['SETOR', 'Empreendimento', 'Etapa']).agg(
        Inicio_Prevista=('Inicio_Prevista', 'min'),
        Termino_Prevista=('Termino_Prevista', 'max'),
        Inicio_Real=('Inicio_Real', 'min'),
        Termino_Real=('Termino_Real', 'max'),
        **{'% concluído': ('% concluído', 'max')},
        UGB=('UGB', 'first'),
        GRUPO=('GRUPO', 'first')
    ).reset_index()
    
    # --- 2. Preparar Dados para TODOS os Setores ---
    all_data_by_sector_js = {}
    all_sector_names = []
    
    # Iterar por cada setor único
    setores_unicos_no_df = df_gantt_agg['SETOR'].unique()
    
    for i, setor in enumerate(setores_unicos_no_df):
        df_setor_agg = df_gantt_agg[df_gantt_agg['SETOR'] == setor]
        all_sector_names.append(setor)
        
        tasks_base_data_for_sector = []
        
        # Para cada linha (empreendimento + etapa) neste setor
        for j, row in df_setor_agg.iterrows():
            empreendimento = row["Empreendimento"]
            etapa = row["Etapa"]
            etapa_nome_completo = sigla_para_nome_completo.get(etapa, etapa)
            
            start_date = row.get("Inicio_Prevista")
            end_date = row.get("Termino_Prevista")
            start_real = row.get("Inicio_Real")
            end_real_original = row.get("Termino_Real")
            progress = row.get("% concluído", 0)
            
            # DEBUG: Verificar se datas previstas existem para PULMÃO
            if setor == "PULMÃO":
                print(f"DEBUG [{setor}] {empreendimento} - {etapa}: Inicio_Prevista={start_date}, Termino_Prevista={end_date}")
            
            if pd.isna(start_date): start_date = datetime.now()
            if pd.isna(end_date): end_date = start_date + timedelta(days=30)
            end_real_visual = end_real_original
            if pd.notna(start_real) and progress < 100 and pd.isna(end_real_original): 
                end_real_visual = datetime.now()
            
            vt = calculate_business_days(end_date, end_real_original)
            duracao_prevista_uteis = calculate_business_days(start_date, end_date)
            duracao_real_uteis = calculate_business_days(start_real, end_real_original)
            vd = None
            if pd.notna(duracao_real_uteis) and pd.notna(duracao_prevista_uteis): 
                vd = duracao_real_uteis - duracao_prevista_uteis
            
            status_color_class = 'status-default'
            hoje = pd.Timestamp.now().normalize()
            if progress == 100:
                if pd.notna(end_real_original) and pd.notna(end_date):
                    if end_real_original <= end_date: status_color_class = 'status-green'
                    else: status_color_class = 'status-red'
            elif progress < 100 and pd.notna(end_date) and (end_date < hoje): 
                status_color_class = 'status-yellow'
            
            task = {
                "id": f"t{j}_{i}",
                "name": f"{empreendimento} - {etapa_nome_completo}",  # Nome composto!
                "empreendimento": empreendimento,
                "etapa": etapa_nome_completo,
                "ugb": row.get("UGB", "N/D"),
                "numero_etapa": j + 1,
                "start_previsto": start_date.strftime("%Y-%m-%d"),
                "end_previsto": end_date.strftime("%Y-%m-%d"),
                "start_real": pd.to_datetime(start_real).strftime("%Y-%m-%d") if pd.notna(start_real) else None,
                "end_real": pd.to_datetime(end_real_visual).strftime("%Y-%m-%d") if pd.notna(end_real_visual) else None,
                "end_real_original_raw": pd.to_datetime(end_real_original).strftime("%Y-%m-%d") if pd.notna(end_real_original) else None,
                "setor": setor,
                "grupo": row.get("GRUPO", "N/D"),
                "progress": int(progress),
                "inicio_previsto": start_date.strftime("%d/%m/%y"),
                "termino_previsto": end_date.strftime("%d/%m/%y"),
                "inicio_real": pd.to_datetime(start_real).strftime("%d/%m/%y") if pd.notna(start_real) else "N/D",
                "termino_real": pd.to_datetime(end_real_original).strftime("%d/%m/%y") if pd.notna(end_real_original) else "N/D",
                "duracao_prev_meses": f"{(end_date - start_date).days / 30.4375:.1f}".replace('.', ',') if pd.notna(start_date) and pd.notna(end_date) else "-",
                "duracao_real_meses": f"{(end_real_original - start_real).days / 30.4375:.1f}".replace('.', ',') if pd.notna(start_real) and pd.notna(end_real_original) else "-",
                "vt_text": f"{int(vt):+d}d" if pd.notna(vt) else "-",
                "vd_text": f"{int(vd):+d}d" if pd.notna(vd) else "-",
                "status_color_class": status_color_class
            }
            tasks_base_data_for_sector.append(task)
        
        # Popular baselines em cada task
        try:
            all_baselines_dict = load_baselines()
            
            for task in tasks_base_data_for_sector:
                empreendimento = task["empreendimento"]
                etapa_nome = task["etapa"]
                
                task["baselines"] = {}
                task["baselines"]["P0-(padrão)"] = {
                    "start": task["start_previsto"],
                    "end": task["end_previsto"]
                }
                
                if empreendimento in all_baselines_dict:
                    baselines_emp = all_baselines_dict[empreendimento]
                    
                    for baseline_name, baseline_info in baselines_emp.items():
                        baseline_data = get_baseline_data(empreendimento, baseline_name)
                        
                        if baseline_data and 'tasks' in baseline_data:
                            baseline_tasks = baseline_data['tasks']
                            
                            # *** ESTRATÉGIA TRIPLA DE BUSCA (igual ao consolidado) ***
                            baseline_task = None
                            
                            # Estratégia 1: Nome completo exato
                            baseline_task = next(
                                (bt for bt in baseline_tasks 
                                 if bt.get('etapa') == etapa_nome or 
                                    bt.get('Etapa') == etapa_nome),
                                None
                            )
                            
                            # Estratégia 2: Tentar com sigla
                            if not baseline_task:
                                etapa_sigla = nome_completo_para_sigla.get(etapa_nome, etapa_nome)
                                baseline_task = next(
                                    (bt for bt in baseline_tasks 
                                     if bt.get('etapa') == etapa_sigla or 
                                        bt.get('Etapa') == etapa_sigla),
                                    None
                                )
                            
                            # Estratégia 3: Converter etapa da baseline para nome completo e comparar
                            if not baseline_task:
                                for bt in baseline_tasks:
                                    bt_etapa = bt.get('etapa', bt.get('Etapa', ''))
                                    bt_etapa_nome = sigla_para_nome_completo.get(bt_etapa, bt_etapa)
                                    if bt_etapa_nome == etapa_nome:
                                        baseline_task = bt
                                        break
                            
                            if baseline_task:
                                task["baselines"][baseline_name] = {
                                    "start": baseline_task.get('inicio_previsto', baseline_task.get('Inicio_Prevista')),
                                    "end": baseline_task.get('termino_previsto', baseline_task.get('Termino_Prevista'))
                                }
                            else:
                                # Etapa não existe nesta baseline
                                task["baselines"][baseline_name] = {
                                    "start": None,
                                    "end": None
                                }
        except Exception as e:
            print(f"Erro ao popular baselines no setor: {e}")
        
        # --- ORDENAÇÃO: Do mais antigo para o mais novo (por data de início prevista) ---
        tasks_base_data_for_sector.sort(key=lambda t: (
            datetime.strptime(t["start_previsto"], "%Y-%m-%d") if t.get("start_previsto") else datetime.max
        ))
        
        all_data_by_sector_js[setor] = tasks_base_data_for_sector
    
    if not all_data_by_sector_js:
        st.warning("Nenhum dado válido para o Gantt por Setor após a conversão.")
        return
    
    # --- 3. Preparar Dados Iniciais ---
    empreendimentos_no_df = sorted(list(df_gantt_agg["Empreendimento"].unique()))
    
    # Coletar todas as etapas únicas do setor atual
    # *** NOVO: Mapear etapas por setor para filtro dinâmico ***
    etapas_por_setor_dict = {}
    for setor_nome in all_sector_names:
        etapas_do_setor = sorted(list(df_gantt_agg[df_gantt_agg['SETOR'] == setor_nome]['Etapa'].unique()))
        etapas_data = []
        for e in etapas_do_setor:
            etapas_data.append({
                "sigla": e,
                "nome": sigla_para_nome_completo.get(e, e)
            })
        etapas_por_setor_dict[setor_nome] = etapas_data
    
    
    # *** NOVO: Determinar quais grupos do dicionário GRUPOS têm etapas presentes em cada setor ***
    grupos_por_setor_dict = {}
    for setor_nome in all_sector_names:
        etapas_do_setor = set(df_gantt_agg[df_gantt_agg['SETOR'] == setor_nome]['Etapa'].unique())
        grupos_presentes = set()
        
        # Para cada grupo no dicionário GRUPOS
        for grupo_nome, etapas_do_grupo in GRUPOS.items():
            # Normalizar etapas do grupo (remover pontos finais)
            etapas_normalizadas_grupo = set(e.strip().rstrip('.') for e in etapas_do_grupo)
            etapas_normalizadas_setor = set(e.strip().rstrip('.') for e in etapas_do_setor)
            
            # Se alguma etapa do grupo está presente no setor, incluir o grupo
            if etapas_normalizadas_grupo.intersection(etapas_normalizadas_setor):
                grupos_presentes.add(grupo_nome)
        
        grupos_por_setor_dict[setor_nome] = sorted(list(grupos_presentes))
    
    # *** NOVO: Identificar macroetapas (ORÇ, PE, PL, SUP) por setor ***
    MACROETAPAS_PREFIXOS = ['ORÇ', 'PE', 'PL', 'SUP']
    macroetapas_por_setor_dict = {}
    
    for setor_nome in all_sector_names:
        etapas_do_setor = df_gantt_agg[df_gantt_agg['SETOR'] == setor_nome]['Etapa'].unique()
        macroetapas_presentes = set()
        
        for etapa in etapas_do_setor:
            # Verificar se a etapa começa com algum dos prefixos de macroetapa
            for prefixo in MACROETAPAS_PREFIXOS:
                if str(etapa).startswith(prefixo):
                    macroetapas_presentes.add(prefixo)
                    break
        
        macroetapas_por_setor_dict[setor_nome] = sorted(list(macroetapas_presentes))
    
    # Definir etapas iniciais para HTML renderizado pelo Python (evita flicker com etapas erradas)
    etapas_iniciais_html = [e['nome'] for e in etapas_por_setor_dict.get(setor_selecionado_inicialmente, [])]
    grupos_iniciais_html = grupos_por_setor_dict.get(setor_selecionado_inicialmente, [])
    macroetapas_iniciais_html = macroetapas_por_setor_dict.get(setor_selecionado_inicialmente, [])
        
        
    # Obter UGBs únicas dos dados
    ugbs_disponiveis = sorted(df["UGB"].dropna().unique().tolist()) if not df.empty and "UGB" in df.columns else []
    
    filter_options = {
        "ugbs": ["Todas"] + ugbs_disponiveis,
        "empreendimentos": ["Todos"] + empreendimentos_no_df,
        "setores_disponiveis": sorted(all_sector_names),
        "etapas": etapas_iniciais_html,
        "etapas_por_setor": etapas_por_setor_dict,
        "grupos": grupos_iniciais_html,
        "grupos_por_setor": grupos_por_setor_dict,
        "macroetapas": macroetapas_iniciais_html,
        "macroetapas_por_setor": macroetapas_por_setor_dict,
        "mapeamento_grupos": GRUPOS
    }
    
    tasks_base_data_inicial = all_data_by_sector_js.get(setor_selecionado_inicialmente, [])
    
    project_id = f"p_setor_{random.randint(1000, 9999)}"
    project = {
        "id": project_id,
        "name": f"Setor: {setor_selecionado_inicialmente}",
        "tasks": tasks_base_data_inicial,
        "meta_assinatura_date": None
    }
    
    df_para_datas = df_gantt_agg
    data_min_proj, data_max_proj = calcular_periodo_datas(df_para_datas)
    total_meses_proj = ((data_max_proj.year - data_min_proj.year) * 12) + (data_max_proj.month - data_min_proj.month) + 1
    
    num_tasks = len(project["tasks"])
    altura_gantt = max(400, (num_tasks * 30) + 150)
    
    # --- 4. Preparar Baselines por Empreendimento ---
    baselines_por_empreendimento_html = {}
    
    try:
        all_baselines_dict = load_baselines()
        for emp in empreendimentos_no_df:
            emp_baseline_options = get_baseline_options(emp)
            if not emp_baseline_options or len(emp_baseline_options) == 0:
                emp_baseline_options = ["P0-(padrão)"]
            else:
                if "P0-(padrão)" not in emp_baseline_options:
                    emp_baseline_options.insert(0, "P0-(padrão)")
            
            baselines_por_empreendimento_html[emp] = emp_baseline_options
    except Exception as e:
        print(f"Erro ao carregar baseline options no setor: {e}")
        for emp in empreendimentos_no_df:
            baselines_por_empreendimento_html[emp] = ["P0-(padrão)"]
    
    # Gerar HTML dos dropdowns por empreendimento
    baseline_rows_html = ""
    for emp in empreendimentos_no_df:
        emp_options = baselines_por_empreendimento_html.get(emp, ["P0-(padrão)"])
        emp_json = json.dumps(emp)
        
        options_html = "".join([
            f'<option value="{opt}">{opt}</option>' 
            for opt in emp_options
        ])
        
        baseline_rows_html += f"""
        <div class="baseline-row" data-empreendimento="{emp}">
            <label title="{emp}">{emp}</label>
            <select class="baseline-dropdown-emp" data-emp="{emp}" onchange='applyBaselineForEmp({emp_json}, this.value); var p0=document.getElementById("apply-p0-all-{project["id"]}"); var latest=document.getElementById("apply-latest-all-{project["id"]}"); if(p0)p0.checked=false; if(latest)latest.checked=false;'>
                {options_html}
            </select>
        </div>
        """
    
    # Ícones por setor
    setor_icons = {
        "PROSPECÇÃO": "",
        "LEGALIZAÇÃO": "",
        "PULMÃO": "",
        "ENGENHARIA": "",
        "SUPRIMENTOS": "",
        "OBRAS": "",
        "ENTREGA": ""
    }
    
    # --- 5. Gerar HTML/CSS/JavaScript ---
    # (Baseado no consolidado mas adaptado para setores)
    gantt_html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/virtual-select-plugin@1.0.39/dist/virtual-select.min.css">
        
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            html, body {{ width: 100%; height: 100%; font-family: 'Segoe UI', sans-serif; background-color: #f5f5f5; color: #333; overflow: hidden; }}
            .gantt-container {{ width: 100%; height: 100%; background-color: white; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); overflow: hidden; position: relative; display: flex; flex-direction: column; }}
            .gantt-main {{ display: flex; flex: 1; overflow: hidden; }}
            .gantt-sidebar-wrapper {{ width: 750px; display: flex; flex-direction: column; flex-shrink: 0; transition: width 0.3s ease-in-out; border-right: 2px solid #e2e8f0; overflow: hidden; }}
            .gantt-sidebar-header {{ background: linear-gradient(135deg, #4a5568, #2d3748); display: flex; flex-direction: column; height: 60px; flex-shrink: 0; }}
            .project-title-row {{ display: flex; justify-content: space-between; align-items: center; padding: 0 15px; height: 30px; color: white; font-weight: 600; font-size: 14px; }}
            .toggle-sidebar-btn {{ background: rgba(255,255,255,0.2); border: none; color: white; width: 24px; height: 24px; border-radius: 5px; cursor: pointer; font-size: 14px; display: flex; align-items: center; justify-content: center; transition: background-color 0.2s, transform 0.3s ease-in-out; }}
            .toggle-sidebar-btn:hover {{ background: rgba(255,255,255,0.4); }}
            .sidebar-grid-header-wrapper {{ display: grid; grid-template-columns: 0px 1fr; color: #d1d5db; font-size: 9px; font-weight: 600; text-transform: uppercase; height: 30px; align-items: center; }}
            .sidebar-grid-header {{ display: grid; grid-template-columns: 2.8fr 0.6fr 0.9fr 0.9fr 0.6fr 0.9fr 0.9fr 0.6fr 0.5fr 0.6fr 0.6fr; padding: 0 10px; align-items: center; }}
            .sidebar-row {{ display: grid; grid-template-columns: 2.8fr 0.6fr 0.9fr 0.9fr 0.6fr 0.9fr 0.9fr 0.6fr 0.5fr 0.6fr 0.6fr; border-bottom: 1px solid #eff2f5; height: 30px; padding: 0 10px; background-color: white; transition: all 0.2s ease-in-out; }}
            .sidebar-cell {{ display: flex; align-items: center; justify-content: center; font-size: 10px; color: #4a5568; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 6px; border: none; }}
            .header-cell {{ text-align: center; }}
            .header-cell.task-name-cell {{ text-align: left; }}
            .gantt-sidebar-content {{ background-color: #f8f9fa; flex: 1; overflow-y: auto; overflow-x: hidden; }}
            .sidebar-row:hover {{ background-color: #f5f8ff; }}
            .sidebar-cell.task-name-cell {{ justify-content: flex-start; font-weight: 600; color: #2d3748; }}
            .sidebar-cell.status-green {{ color: #1E8449; font-weight: 700; }}
            .sidebar-cell.status-red {{ color: #C0392B; font-weight: 700; }}
            .sidebar-cell.status-yellow{{ color: #B9770E; font-weight: 700; }}
            .sidebar-cell.status-default{{ color: #566573; font-weight: 700; }}
            .gantt-sidebar-wrapper.collapsed {{ width: 250px; }}
            .gantt-sidebar-wrapper.collapsed .sidebar-grid-header, .gantt-sidebar-wrapper.collapsed .sidebar-row {{ grid-template-columns: 1fr; padding: 0 15px 0 10px; }}
            .gantt-sidebar-wrapper.collapsed .header-cell:not(.task-name-cell), .gantt-sidebar-wrapper.collapsed .sidebar-cell:not(.task-name-cell) {{ display: none; }}
            .gantt-sidebar-wrapper.collapsed .toggle-sidebar-btn {{ transform: rotate(180deg); }}
            .gantt-chart-content {{ flex: 1; overflow: auto; position: relative; background-color: white; user-select: none; cursor: grab; }}
            .gantt-chart-content.active {{ cursor: grabbing; }}
            .chart-container {{ position: relative; min-width: {total_meses_proj * 30}px; }}
            .chart-header {{ background: linear-gradient(135deg, #4a5568, #2d3748); color: white; height: 60px; position: sticky; top: 0; z-index: 9; display: flex; flex-direction: column; }}
            .year-header {{ height: 30px; display: flex; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.2); }}
            .year-section {{ text-align: center; font-weight: 600; font-size: 12px; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.1); height: 100%; }}
            .month-header {{ height: 30px; display: flex; align-items: center; }}
            .month-cell {{ width: 30px; height: 30px; border-right: 1px solid rgba(255,255,255,0.2); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 500; }}
            .chart-body {{ position: relative; }}
            .gantt-row {{ position: relative; height: 30px; border-bottom: 1px solid #eff2f5; background-color: white; }}
            .gantt-bar {{ position: absolute; height: 14px; top: 8px; border-radius: 3px; cursor: pointer; transition: all 0.2s ease; display: flex; align-items: center; padding: 0 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .gantt-bar-overlap {{ position: absolute; height: 14px; top: 8px; background-image: linear-gradient(45deg, rgba(0, 0, 0, 0.25) 25%, transparent 25%, transparent 50%, rgba(0, 0, 0, 0.25) 50%, rgba(0, 0, 0, 0.25) 75%, transparent 75%, transparent); background-size: 8px 8px; z-index: 9; pointer-events: none; border-radius: 3px; }}
            .gantt-bar:hover {{ transform: translateY(-1px) scale(1.01); box-shadow: 0 4px 8px rgba(0,0,0,0.2); z-index: 10 !important; }}
            .gantt-bar.previsto {{ z-index: 7; }}
            .gantt-bar.real {{ z-index: 8; }}
            .bar-label {{ font-size: 8px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-shadow: 0 1px 2px rgba(0,0,0,0.4); }}
            .gantt-bar.real .bar-label {{ color: white; }}
            .gantt-bar.previsto .bar-label {{ color: #6C6C6C; }}
            .tooltip {{ position: absolute; background-color: #2d3748; color: white; padding: 6px 10px; border-radius: 4px; font-size: 11px; z-index: 1000; box-shadow: 0 2px 8px rgba(0,0,0,0.3); pointer-events: none; opacity: 0; transition: opacity 0.2s ease; max-width: 220px; }}
            .tooltip.show {{ opacity: 1; }}
            .today-line {{ position: absolute; top: 0; bottom: 0; width: 1px; background-color: #fdf1f1; z-index: 5; box-shadow: 0 0 1px rgba(229, 62, 62, 0.6); }}
            .month-divider {{ position: absolute; top: 0; bottom: 0; width: 1px; background-color: #fcf6f6; z-index: 4; pointer-events: none; }}
            .month-divider.first {{ background-color: #eeeeee; width: 1px; }}
            .gantt-toolbar {{
                position: absolute; top: 10px; right: 10px;
                z-index: 100;
                display: flex;
                flex-direction: column;
                gap: 5px;
                background: rgba(45, 55, 72, 0.9);
                border-radius: 6px;
                padding: 5px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }}
            .toolbar-btn {{
                background: none;
                border: none;
                width: 36px;
                height: 36px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 20px;
                color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background-color 0.2s, box-shadow 0.2s;
                padding: 0;
            }}
            .toolbar-btn:hover {{
                background-color: rgba(255, 255, 255, 0.1);
                box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.2);
            }}
            .toolbar-btn.is-fullscreen {{
                background-color: #3b82f6;
                box-shadow: 0 0 0 2px #3b82f6;
            }}
            .floating-filter-menu {{
                display: none;
                position: absolute;
                top: 10px; right: 50px;
                width: 280px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.3);
                z-index: 99;
                padding: 15px;
                border: 1px solid #e2e8f0;
            }}
            .floating-filter-menu.is-open {{
                display: block;
            }}
            .filter-group {{ margin-bottom: 12px; }}
            .filter-group label {{
                display: block; font-size: 11px; font-weight: 600;
                color: #4a5568; margin-bottom: 4px;
                text-transform: uppercase;
            }}
            .filter-group select {{
                width: 100%; padding: 6px 8px;
                border: 1px solid #cbd5e0; border-radius: 4px;
                font-size: 13px;
            }}
            .filter-group-radio, .filter-group-checkbox {{
                display: flex; align-items: center; padding: 5px 0;
            }}
            .filter-group-radio input, .filter-group-checkbox input {{
                width: auto; margin-right: 8px;
            }}
            .filter-group-radio label, .filter-group-checkbox label {{
                font-size: 13px; font-weight: 500;
                color: #2d3748; margin-bottom: 0; text-transform: none;
            }}
            .filter-apply-btn {{
                width: 100%; padding: 8px; font-size: 14px; font-weight: 600;
                color: white; background-color: #2d3748;
                border: none; border-radius: 4px; cursor: pointer;
                margin-top: 5px;
                transition: background-color 0.2s ease;
            }}
            .filter-apply-btn:hover {{
                background-color: #1a202c;
            }}
            
            /* Estilos para Virtual Select nos filtros */
            .floating-filter-menu .vscomp-toggle-button {{
                border: 1px solid #cbd5e0;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
                min-height: 30px;
            }}
            .floating-filter-menu .vscomp-options {{
                font-size: 13px;
            }}
            .floating-filter-menu .vscomp-option {{
                min-height: 30px;
            }}
            .floating-filter-menu .vscomp-search-input {{
                height: 30px;
                font-size: 13px;
            }}
            .baseline-selector {{
                display: none;
                position: absolute;
                top: 10px;
                right: 50px;
                width: 280px;
                min-height: 200px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.3);
                z-index: 999;
                padding: 15px;
                border: 1px solid #e2e8f0;
                overflow: hidden;
            }}
            .baseline-selector.is-open {{
                display: block;
            }}
            .baseline-row {{
                display: grid;
                grid-template-columns: 1.2fr 1fr;
                gap: 10px;
                padding: 8px 6px;
                border-bottom: 1px solid #e2e8f0;
                align-items: center;
                transition: background-color 0.15s ease;
            }}
            .baseline-row:hover {{
                background-color: #f7fafc;
            }}
            .baseline-row label {{
                font-size: 11px;
                font-weight: 500;
                color: #2d3748;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }}
            .baseline-row select {{
                width: 100%;
                padding: 4px 6px;
                border: 1px solid #cbd5e0;
                border-radius: 4px;
                font-size: 11px;
            }}
            .baseline-resize-corner {{
                position: absolute;
                bottom: 0;
                left: 0;
                width: 16px;
                height: 16px;
                cursor: nesw-resize;
                z-index: 100;
            }}
            .baseline-resize-corner::before {{
                content: '';
                position: absolute;
                bottom: -2px;
                left: -2px;
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 0 0 18px 18px;
                border-color: transparent;
                transform: rotate(-45deg);
                transform-origin: bottom left;
            }}
            .baseline-resize-corner:hover::before {{
                border-color: transparent;
            }}
            .baseline-resize-corner::after {{
                content: '';
                position: absolute;
                bottom: 2px;
                left: 2px;
                width: 10px;
                height: 10px;
                transform: rotate(-45deg);
                transform-origin: center;
                background: 
                    linear-gradient(90deg, transparent 48%, #9ca3af 48%, #9ca3af 52%, transparent 52%),
                    linear-gradient(90deg, transparent 56%, #9ca3af 56%, #9ca3af 60%, transparent 60%),
                    linear-gradient(90deg, transparent 64%, #9ca3af 64%, #9ca3af 68%, transparent 68%);
            }}
        </style>
    </head>
    <body>
        <script id="all-data-by-sector" type="application/json">{json.dumps(all_data_by_sector_js)}</script>
        <script id="etapas-by-sector" type="application/json">{json.dumps(etapas_por_setor_dict)}</script>
        <script id="grupos-por-setor" type="application/json">{json.dumps(grupos_por_setor_dict)}</script>
        <script id="macroetapas-por-setor" type="application/json">{json.dumps(macroetapas_por_setor_dict)}</script>
        <script id="mapeamento-grupos" type="application/json">{json.dumps(GRUPOS)}</script>
        
        <div class="gantt-container" id="gantt-container-{project['id']}">
            <div class="gantt-toolbar" id="gantt-toolbar-{project["id"]}">
                <button class="toolbar-btn" id="filter-btn-{project["id"]}" title="Filtros">
                    <span>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon>
                        </svg>
                    </span>
                </button>
                <button class="toolbar-btn" id="baseline-btn-{project["id"]}" title="Linhas de Base">
                    <span>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                            <line x1="3" y1="9" x2="21" y2="9"></line>
                            <line x1="3" y1="15" x2="21" y2="15"></line>
                        </svg>
                    </span>
                </button>
                <button class="toolbar-btn" id="fullscreen-btn-{project["id"]}" title="Tela Cheia">
                    <span>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
                        </svg>
                    </span>
                </button>
            </div>
            
            <!-- Seletor de Setor (NOVO) -->
            <div class="floating-filter-menu" id="filter-menu-{project['id']}">
                <div class="filter-group">
                    <label for="filter-setor-{project['id']}">Setor</label>
                    <select id="filter-setor-{project['id']}">
                        {"".join([f'<option value="{s}" {"selected" if s == setor_selecionado_inicialmente else ""}>{setor_icons.get(s, "")} {s}</option>' for s in sorted(all_sector_names)])}
                    </select>
                </div>
                
                <div class="filter-group">
                    <label for="filter-ugb-setor-{project['id']}">UGB</label>
                    <div id="filter-ugb-setor-{project['id']}"></div>
                </div>
                
                <div class="filter-group">
                    <label for="filter-project-{project['id']}">Empreendimento</label>
                    <div id="filter-project-{project['id']}"></div>
                </div>
                <div class="filter-group">
                    <label for="filter-grupo-{project['id']}">Grupo</label>
                    <div id="filter-grupo-{project['id']}"></div>
                </div>
                <div class="filter-group">
                    <label for="filter-etapa-{project['id']}">Etapa</label>
                    <div id="filter-etapa-{project['id']}"></div>
                </div>
                <div class="filter-group">
                    <label for="filter-macroetapa-{project['id']}">Macroetapas</label>
                    <div id="filter-macroetapa-{project['id']}"></div>
                </div>
                <div class="filter-group">
                    <div class="filter-group-checkbox">
                        <input type="checkbox" id="filter-concluidas-{project['id']}">
                        <label for="filter-concluidas-{project['id']}">Mostrar apenas não concluídas</label>
                    </div>
                </div>
                <div class="filter-group">
                    <label>Visualização</label>
                    <div class="filter-group-radio">
                        <input type="radio" id="filter-vis-ambos-{project['id']}" name="filter-vis-{project['id']}" value="Ambos" checked>
                        <label for="filter-vis-ambos-{project['id']}">Ambos</label>
                    </div>
                    <div class="filter-group-radio">
                        <input type="radio" id="filter-vis-previsto-{project['id']}" name="filter-vis-{project['id']}" value="Previsto">
                        <label for="filter-vis-previsto-{project['id']}">Previsto</label>
                    </div>
                    <div class="filter-group-radio">
                        <input type="radio" id="filter-vis-real-{project['id']}" name="filter-vis-{project['id']}" value="Real">
                        <label for="filter-vis-real-{project['id']}">Real</label>
                    </div>
                </div>
                <button class="filter-apply-btn" id="filter-apply-btn-{project['id']}">Aplicar Filtros</button>
            </div>
            
            <!-- Seletor de Baselines -->
            <div class="baseline-selector" id="baseline-selector-{project['id']}">
                <div style="margin-bottom: 12px; font-weight: 700; color: #1a202c; font-size: 14px; border-bottom: 2px solid #1a202c; padding-bottom: 8px;">
                    Selecione Linhas de Base
                </div>
                
                <div style="margin-bottom: 15px; padding: 10px; background: #f7fafc; border-radius: 6px; border: 1px solid #e2e8f0;">
                    <div style="font-weight: 600; color: #2d3748; font-size: 12px; margin-bottom: 10px;">
                        Aplicação Rápida
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 6px;">
                        <label style="display: flex; align-items: center; cursor: pointer;">
                            <input type="checkbox" id="apply-p0-all-{project['id']}" 
                                   onchange="handleQuickApply('p0')"
                                   style="margin-right: 6px; cursor: pointer;">
                            <span style="font-size: 11px; color: #4a5568;">Aplicar P0 para todos</span>
                        </label>
                        <label style="display: flex; align-items: center; cursor: pointer;">
                            <input type="checkbox" id="apply-latest-all-{project['id']}" 
                                   onchange="handleQuickApply('latest')"
                                   style="margin-right: 6px; cursor: pointer;">
                            <span style="font-size: 11px; color: #4a5568;">Aplicar última baseline para todos</span>
                        </label>
                    </div>
                </div>
                
                <div class="baseline-selector-table" style="max-height: 400px; overflow-y: auto; margin-top: 10px;">
                    {baseline_rows_html}
                </div>
                <div class="baseline-resize-corner" title="Arrastar para redimensionar"></div>
            </div>
            
            <div class="gantt-main">
                <div class="gantt-sidebar-wrapper" id="gantt-sidebar-wrapper-{project['id']}">
                    <div class="gantt-sidebar-header">
                        <div class="project-title-row">
                            <span>{project["name"]}</span>
                            <button class="toggle-sidebar-btn" id="toggle-sidebar-btn-{project['id']}" title="Recolher/Expandir Tabela">«</button>
                        </div>
                        <div class="sidebar-grid-header-wrapper">
                            <div></div>
                            <div class="sidebar-grid-header">
                                <div class="header-cell task-name-cell">EMP + ETAPA</div>
                                <div class="header-cell">UGB</div>
                                <div class="header-cell">INÍCIO-P</div>
                                <div class="header-cell">TÉRMINO-P</div>
                                <div class="header-cell">DUR-P</div>
                                <div class="header-cell">INÍCIO-R</div>
                                <div class="header-cell">TÉRMINO-R</div>
                                <div class="header-cell">DUR-R</div>
                                <div class="header-cell">%</div>
                                <div class="header-cell">VT</div>
                                <div class="header-cell">VD</div>
                            </div>
                        </div>
                    </div>
                    <div class="gantt-sidebar-content" id="gantt-sidebar-content-{project['id']}"></div>
                </div>
                <div class="gantt-chart-content" id="gantt-chart-content-{project['id']}">
                    <div class="chart-container" id="chart-container-{project["id"]}"></div>
                </div>
            </div>
            
            <!-- Tooltip dentro do container para funcionar em fullscreen -->
            <div class="tooltip" id="tooltip"></div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/virtual-select-plugin@1.0.39/dist/virtual-select.min.js"></script>
        
        <script>
            // Dados de todos os setores
            const allDataBySector = JSON.parse(document.getElementById('all-data-by-sector').textContent);
            const etapasBySector = JSON.parse(document.getElementById('etapas-by-sector').textContent);
            const gruposPorSetor = JSON.parse(document.getElementById('grupos-por-setor').textContent);
            const macroetapasPorSetor = JSON.parse(document.getElementById('macroetapas-por-setor').textContent);
            const mapeamentoGrupos = JSON.parse(document.getElementById('mapeamento-grupos').textContent);
            
            // Opções de filtros
            const filterOptions = {json.dumps(filter_options)};
            
            // *** NOVAS VARIÁVEIS GLOBAIS ***
            const initialSectorName = "{setor_selecionado_inicialmente}";
            let currentSector = initialSectorName;
            let allTasks_baseData = JSON.parse(JSON.stringify(allDataBySector[currentSector] || []));
            let currentTasks = [...allTasks_baseData];
            
            // Variável para armazenar o tipo de visualização selecionado
            let savedVisualizationType = 'Ambos';
            
            // *** Variável Global para Virtual Select ***
            let vsEtapa;
            let vsGrupo;
            let vsMacroetapas;
            let vsUgbSetor; // NOVO: Filtro de UGB
            let vsEmpreendimentoSetor; // NOVO: Filtro de Empreendimento

            // *** FUNÇÃO AUXILIAR: Inicializar Virtual Select de Etapas ***
            function renderStageCheckboxes(sectorName) {{
                const etapas = etapasBySector[sectorName] || [];
                
                // Converter para formato do Virtual Select
                const options = etapas.map(etapa => ({{
                    label: etapa.nome,
                    value: etapa.nome
                }}));
                
                // Destruir instância anterior se existir
                if (vsEtapa) {{
                    vsEtapa.destroy();
                }}
                
                // Inicializar Virtual Select
                vsEtapa = VirtualSelect.init({{
                    ele: '#filter-etapa-{project["id"]}',
                    options: options,
                    multiple: true,
                    search: true,
                    selectedValue: options.map(o => o.value),  // TODAS selecionadas por padrão
                    placeholder: 'Selecione etapas',
                    noOptionsText: 'Nenhuma etapa disponível',
                    searchPlaceholderText: 'Buscar...',
                    selectAllText: 'Selecionar todas',
                    allOptionsSelectedText: 'Todas selecionadas'
                }});
                
                console.log(`🔄 Virtual Select Etapa renderizado: ${{options.length}} opções, todas selecionadas`);
            }}

            // *** FUNÇÃO AUXILIAR: Inicializar Virtual Select de Grupos ***
            function renderGroupCheckboxes(sectorName) {{
                // Usar apenas os grupos que têm etapas presentes neste setor
                const gruposDoSetor = gruposPorSetor[sectorName] || [];
                
                // Converter para formato do Virtual Select
                const options = gruposDoSetor.map(grupo => ({{
                    label: grupo,
                    value: grupo
                }}));
                
                // Destruir instância anterior se existir
                if (vsGrupo) {{
                    vsGrupo.destroy();
                }}
                
                // Inicializar Virtual Select
                vsGrupo = VirtualSelect.init({{
                    ele: '#filter-grupo-{project["id"]}',
                    options: options,
                    multiple: true,
                    search: true,
                    selectedValue: options.map(o => o.value),  // TODAS selecionadas por padrão
                    placeholder: 'Selecione grupos',
                    noOptionsText: 'Nenhum grupo disponível',
                    searchPlaceholderText: 'Buscar...',
                    selectAllText: 'Selecionar todos',
                    allOptionsSelectedText: 'Todos selecionados'
                }});
                
                console.log(`🔄 Virtual Select Grupo renderizado: ${{options.length}} opções, todas selecionadas`);
            }}
            
            // *** FUNÇÃO AUXILIAR: Inicializar Virtual Select de Macroetapas ***
            function renderMacroetapasCheckboxes(sectorName) {{
                // Usar macroetapas do setor selecionado
                const macroetapas = macroetapasPorSetor[sectorName] || [];
                
                // Converter para formato do Virtual Select
                const options = macroetapas.map(macro => ({{
                    label: macro,
                    value: macro
                }}));
                
                // Destruir instância anterior se existir
                if (vsMacroetapas) {{
                    vsMacroetapas.destroy();
                }}
                
                // Inicializar Virtual Select
                vsMacroetapas = VirtualSelect.init({{
                    ele: '#filter-macroetapa-{project["id"]}',
                    options: options,
                    multiple: true,
                    search: true,
                    selectedValue: options.map(o => o.value),  // TODAS selecionadas por padrão
                    placeholder: 'Selecione macroetapas',
                    noOptionsText: 'Nenhuma macroetapa disponível',
                    searchPlaceholderText: 'Buscar...',
                    selectAllText: 'Selecionar todas',
                    allOptionsSelectedText: 'Todas selecionadas'
                }});
                
                console.log(`🔄 Virtual Select Macroetapas renderizado: ${{options.length}} opções, todas selecionadas`);
            }}

            // *** FUNÇÃO: Inicializar Virtual Select de UGB ***
            function initUGBFilter() {{
                const ugbOptions = (filterOptions.ugbs || ["Todas"]).map(u => ({{ label: u, value: u }}));
                
                if (vsUgbSetor) {{
                    vsUgbSetor.destroy();
                }}
                
                vsUgbSetor = VirtualSelect.init({{
                    ele: '#filter-ugb-setor-{project["id"]}',
                    options: ugbOptions,
                    multiple: true,
                    search: true,
                    selectedValue: ["Todas"],
                    placeholder: 'Selecionar UGB(s)',
                    noOptionsText: 'Nenhuma UGB disponível',
                    searchPlaceholderText: 'Buscar...',
                    selectAllText: 'Selecionar todas',
                    allOptionsSelectedText: 'Todas selecionadas'
                }});
                
                // Listener para atualizar empreendimentos
                document.querySelector('#filter-ugb-setor-{project["id"]}').addEventListener('change', function() {{
                    updateEmpreendimentoOptionsSetor();
                }});
                
                console.log('🔄 Virtual Select UGB renderizado');
            }}

            // *** FUNÇÃO: Atualizar opções de empreendimento baseado em UGB ***
            function updateEmpreendimentoOptionsSetor() {{
                const selUgbArray = vsUgbSetor ? vsUgbSetor.getValue() || [] : [];
                let tasksAtual = allTasks_baseData || [];
                
                if (!tasksAtual || tasksAtual.length === 0) {{
                    console.warn('Nenhuma task disponível para filtrar empreendimentos');
                    return;
                }}
                
                // Filtrar empreendimentos por UGB
                let filteredEmps = [...new Set(tasksAtual.map(t => t.empreendimento))];
                if (selUgbArray.length > 0 && !selUgbArray.includes('Todas')) {{
                    filteredEmps = [...new Set(tasksAtual
                        .filter(t => selUgbArray.includes(t.ugb))
                        .map(t => t.empreendimento))];
                }}
                
                // Destruir e recriar VirtualSelect de empreendimento
                if (vsEmpreendimentoSetor) {{
                    vsEmpreendimentoSetor.destroy();
                }}
                
                const empreendimentoOptions = ["Todos"].concat(filteredEmps).map(e => ({{ label: e, value: e }}));
                vsEmpreendimentoSetor = VirtualSelect.init({{
                    ele: '#filter-project-{project["id"]}',
                    options: empreendimentoOptions,
                    multiple: true,
                    search: true,
                    selectedValue: ["Todos"],
                    placeholder: 'Selecionar Empreendimento(s)',
                    noOptionsText: 'Nenhum empreendimento disponível',
                    searchPlaceholderText: 'Buscar...',
                    selectAllText: 'Selecionar todos',
                    allOptionsSelectedText: 'Todos selecionados'
                }});
                
                console.log('Opções de empreendimento atualizadas no setor. Total:', filteredEmps.length);
            }}

            // *** FUNÇÃO AUXILIAR: Atualizar Título do Projeto ***
            function updateProjectTitle(newSectorName) {{
                const projectTitle = document.querySelector('#gantt-sidebar-wrapper-{project["id"]} .project-title-row span');
                if (projectTitle) {{
                    projectTitle.textContent = `Setor: ${{newSectorName}}`;
                }}
            }}
            
            // *** FUNÇÃO AUXILIAR: Formatar Data para Exibição ***
            function formatDateDisplay(dateStr) {{
                if (!dateStr) return "N/D";
                try {{
                    const date = new Date(dateStr);
                    if (isNaN(date.getTime())) return "N/D";
                    const day = String(date.getUTCDate()).padStart(2, '0');
                    const month = String(date.getUTCMonth() + 1).padStart(2, '0');
                    const year = String(date.getUTCFullYear()).slice(-2);
                    return `${{day}}/${{month}}/${{year}}`;
                }} catch (e) {{
                    return "N/D";
                }}
            }}
            
            // *** FUNÇÃO PRINCIPAL: Aplicar Filtros e Redesenhar ***
            function applyFiltersAndRedraw() {{
                try {{
                    console.log('=== APLICANDO FILTROS E REDESENHANDO ===');
                    
                    // 1. LER SETOR SELECIONADO
                    const selSetor = document.getElementById('filter-setor-{project["id"]}').value;
                    
                    // 2. LER OUTROS FILTROS
                    const selEmpArray = vsEmpreendimentoSetor ? vsEmpreendimentoSetor.getValue() || [] : ["Todos"];
                    
                    // *** ATUALIZADO: Obter etapas, grupos e macroetapas selecionados do Virtual Select ***
                    let etapasSelecionadas = vsEtapa ? vsEtapa.getValue() : [];
                    let gruposSelecionados = vsGrupo ? vsGrupo.getValue() : [];
                    let macroetapasSelecionadas = vsMacroetapas ? vsMacroetapas.getValue() : [];
                    
                    console.log('=== DEBUG FILTROS ===');
                    console.log('Setor atual:', currentSector);
                    console.log('Etapas selecionadas:', etapasSelecionadas.length, etapasSelecionadas);
                    console.log('Grupos selecionados:', gruposSelecionados.length, gruposSelecionados);
                    console.log('Macroetapas selecionadas:', macroetapasSelecionadas.length, macroetapasSelecionadas);
                    console.log('Macroetapas disponíveis no setor:', macroetapasPorSetor[currentSector]);
                    console.log('==================');
                    
                    const selConcluidas = document.getElementById('filter-concluidas-{project["id"]}').checked;
                    const selVis = document.querySelector('input[name="filter-vis-{project["id"]}"]:checked').value;
                    
                    console.log('Setor:', selSetor);
                    console.log('Empreendimento:', selEmpArray);
                    console.log('Visualização:', selVis);
                    console.log('Mostrar apenas não concluídas:', selConcluidas);
                    console.log('Etapas selecionadas:', etapasSelecionadas.length);
                    
                    // 3. ATUALIZAR DADOS BASE SE SETOR MUDOU
                    if (selSetor !== currentSector) {{
                        currentSector = selSetor;
                        allTasks_baseData = JSON.parse(JSON.stringify(allDataBySector[currentSector] || []));
                        console.log(`✅ Mudando para setor: ${{currentSector}}. Tasks carregadas: ${{allTasks_baseData.length}}`);
                        updateProjectTitle(currentSector);
                        
                        // *** NOVO: Atualizar filtros de etapas, grupos E macroetapas para o novo setor ***
                        renderStageCheckboxes(currentSector);
                        renderGroupCheckboxes(currentSector);
                        renderMacroetapasCheckboxes(currentSector);
                        initUGBFilter(); // NOVO: Inicializar filtro de UGB
                        
                        // Como os checkboxes foram recriados (e todos vêm checked por padrão na função render),
                        // atualizamos TODAS as listas de selecionadas para incluir as novas opções.
                        const novasEtapas = etapasBySector[currentSector] || [];
                        etapasSelecionadas = novasEtapas.map(e => e.nome);
                        
                        const novosGrupos = gruposPorSetor[currentSector] || [];
                        gruposSelecionados = novosGrupos;
                        
                        const novasMacroetapas = macroetapasPorSetor[currentSector] || [];
                        macroetapasSelecionadas = novasMacroetapas;
                        
                        console.log('🔄 Filtros atualizados para o setor:', currentSector);
                        console.log('  - Etapas:', etapasSelecionadas.length);
                        console.log('  - Grupos:', gruposSelecionados.length);
                        console.log('  - Macroetapas:', macroetapasSelecionadas.length);
                    }}
                    
                    // 4. COMEÇAR COM DADOS BASE DO SETOR ATUAL
                    let baseTasks = JSON.parse(JSON.stringify(allTasks_baseData));
                    
                    // 5. APLICAR FILTROS SECUNDÁRIOS
                    let filteredTasks = baseTasks;
                    
                    // Filtro de empreendimento (multiseleção)
                    if (selEmpArray.length > 0 && !selEmpArray.includes('Todos')) {{
                        filteredTasks = filteredTasks.filter(t => selEmpArray.includes(t.empreendimento));
                    }}
                    
                    // *** MODIFICADO: Filtro de grupos usando mapeamento ***
                    // Só aplicar se NÃO todos os grupos disponíveis estão selecionados
                    const gruposDisponiveis = gruposPorSetor[currentSector] || [];
                    const todosGruposSelecionados = gruposSelecionados.length === gruposDisponiveis.length && gruposDisponiveis.length > 0;
                    
                    if (gruposSelecionados.length > 0 && !todosGruposSelecionados) {{
                        const countAntes = filteredTasks.length;
                        filteredTasks = filteredTasks.filter(task => {{
                            // Verificar se a etapa da task pertence a algum dos grupos selecionados
                            // Normalizar nome da etapa (remover pontos finais)
                            const etapaNormalizada = task.etapa.trim().replace(/\.+$/, '');
                            
                            for (const grupoSelecionado of gruposSelecionados) {{
                                const etapasDoGrupo = mapeamentoGrupos[grupoSelecionado] || [];
                                // Normalizar etapas do grupo também
                                const etapasNormalizadas = etapasDoGrupo.map(e => e.trim().replace(/\.+$/, ''));
                                if (etapasNormalizadas.includes(etapaNormalizada)) {{
                                    return true; // Task pertence a um grupo selecionado
                                }}
                            }}
                            return false; // Task não pertence a nenhum grupo selecionado
                        }});
                        console.log(`📉 Filtro Grupos: ${{countAntes}} -> ${{filteredTasks.length}}`);
                    }} else if (todosGruposSelecionados) {{
                        console.log('⏭️ Filtro Grupos ignorado: todos os grupos disponíveis selecionados');
                    }}
                    
                    
                    // *** NOVO: Filtro de macroetapas ***
                    // Só aplicar se o setor TEM macroetapas disponíveis E não todas estão selecionadas
                    const macroetapasDisponiveis = macroetapasPorSetor[currentSector] || [];
                    const todasMacroetapasSelecionadas = macroetapasSelecionadas.length === macroetapasDisponiveis.length && macroetapasDisponiveis.length > 0;
                    
                    // Se o setor NÃO tem macroetapas (length === 0), pular este filtro completamente
                    if (macroetapasDisponiveis.length > 0 && macroetapasSelecionadas.length > 0 && !todasMacroetapasSelecionadas) {{
                        const countAntes = filteredTasks.length;
                        filteredTasks = filteredTasks.filter(task => {{
                            // Verificar se a etapa da task começa com alguma das macroetapas selecionadas
                            for (const macro of macroetapasSelecionadas) {{
                                if (task.etapa.startsWith(macro)) {{
                                    return true; // Task começa com uma macroetapa selecionada
                                }}
                            }}
                            return false; // Task não começa com nenhuma macroetapa selecionada
                        }});
                        console.log(`📉 Filtro Macroetapas: ${{countAntes}} -> ${{filteredTasks.length}}`);
                    }} else if (macroetapasDisponiveis.length === 0) {{
                        console.log('⏭️ Filtro Macroetapas ignorado: setor sem macroetapas');
                    }}
                    
                    
                    // Filtro de etapas (melhorado - comparação exata)
                    if (etapasSelecionadas.length > 0) {{
                        const countAntes = filteredTasks.length;
                        filteredTasks = filteredTasks.filter(task => {{
                            // Comparar diretamente a etapa da task com as selecionadas
                            const match = etapasSelecionadas.includes(task.etapa);
                            if (!match) {{
                                // Debug para entender o que está sendo filtrado
                                if (Math.random() < 0.001) {{
                                    console.log(`❌ Rejeitado: Task="${{task.etapa}}" vs Filtro=[${{etapasSelecionadas.slice(0,3)}}...]`);
                                }}
                            }}
                            return match;
                        }});
                        console.log(`📉 Filtro Etapas: ${{countAntes}} -> ${{filteredTasks.length}}`);
                    }}
                    
                    // Filtro de concluídas
                    if (selConcluidas) {{
                        filteredTasks = filteredTasks.filter(t => t.progress < 100);
                    }}
                    
                    console.log(`📊 Tasks após filtros: ${{filteredTasks.length}} de ${{baseTasks.length}}`);
                    
                    // 6. REAPLICAR BASELINES SELECIONADAS
                    filteredTasks.forEach(task => {{
                        const emp = task.empreendimento;
                        const dropdown = document.querySelector(`select[data-emp="${{emp}}"]`);
                        
                        if (dropdown && dropdown.value !== "P0-(padrão)") {{
                            const baselineName = dropdown.value;
                            
                            if (task.baselines && task.baselines[baselineName]) {{
                                const baselineData = task.baselines[baselineName];
                                
                                if (baselineData.start && baselineData.end) {{
                                    task.start_previsto = baselineData.start;
                                    task.end_previsto = baselineData.end;
                                    task.inicio_previsto = formatDateDisplay(baselineData.start);
                                    task.termino_previsto = formatDateDisplay(baselineData.end);
                                    console.log(`🔄 Baseline ${{baselineName}} reaplicada para ${{emp}}`);
                                }}
                            }}
                        }}
                    }});
                    
                    // 7. ATUALIZAR VARIÁVEIS GLOBAIS
                    currentTasks = filteredTasks;
                    savedVisualizationType = selVis;
                    
                    // 8. REDESENHAR GRÁFICO
                    renderGantt();
                    
                    // 9. FECHAR MENU DE FILTROS
                    document.getElementById('filter-menu-{project["id"]}').classList.remove('is-open');
                    
                    console.log('✅ Filtros aplicados e gráfico redesenhado');
                    
                }} catch (error) {{
                    console.error('❌ Erro ao aplicar filtros:', error);
                    alert('Erro ao aplicar filtros. Verifique o console para detalhes.');
                }}
            }}
            
            // Event listener para dropdown de setor (atualiza filtros, mas não renderiza)
            document.getElementById('filter-setor-{project["id"]}').addEventListener('change', function() {{
                const novoSetor = this.value;
                console.log(`🔄 Setor alterado para: ${{novoSetor}} (filtros serão atualizados)`);
                
                // Atualizar título do projeto
                updateProjectTitle(novoSetor);
                
                // Atualizar filtros de Etapas (CORRIGIDO: nome correto da função)
                renderStageCheckboxes(novoSetor);
                
                // Atualizar filtros de Grupos (CORRIGIDO: nome correto da função)
                renderGroupCheckboxes(novoSetor);
                
                // Atualizar filtros de Macroetapas
                renderMacroetapasCheckboxes(novoSetor);
                
                console.log(`✅ Filtros atualizados. Clique em "Aplicar Filtros" para visualizar.`);
                
                // NÃO chamar applyFiltersAndRedraw() - deixar para o botão
            }});
            
            // Event listener APENAS para botão "Aplicar Filtros"
            document.getElementById('filter-apply-btn-{project["id"]}')?.addEventListener('click', applyFiltersAndRedraw);
            
            // *** REMOVIDO: Event listeners de checkboxes - agora usa Virtual Select ***

            
            // Função para aplicar baseline em um empreendimento
            function applyBaselineForEmp(emp, baselineName) {{
                console.log('=== APLICANDO BASELINE ===');
                console.log('Empreendimento:', emp);
                console.log('Baseline:', baselineName);
                console.log('Total de tasks antes:', currentTasks.length);
                
                let tasksAtualizadas = 0;
                currentTasks.forEach(task => {{
                    if (task.empreendimento === emp) {{
                        console.log('Task encontrada:', task.name, 'Baselines:', task.baselines);
                        if (task.baselines && task.baselines[baselineName]) {{
                            const baselineData = task.baselines[baselineName];
                            if (baselineData.start && baselineData.end) {{
                                task.start_previsto = baselineData.start;
                                task.end_previsto = baselineData.end;
                                task.inicio_previsto = formatDateDisplay(task.start_previsto);
                                task.termino_previsto = formatDateDisplay(task.end_previsto);
                                tasksAtualizadas++;
                                console.log('Baseline aplicada:', task.name, 'Novo início:', task.inicio_previsto);
                            }}
                        }}
                    }}
                }});
                
                console.log('Tasks atualizadas:', tasksAtualizadas);
                console.log('Re-renderizando gráfico...');
                renderGantt();
            }}
            
            // Função para aplicação rápida (aplica imediatamente ao marcar checkbox)
            function handleQuickApply(mode) {{
                const emps = [...new Set(currentTasks.map(t => t.empreendimento))];
                
                emps.forEach(emp => {{
                    const empTasks = currentTasks.filter(t => t.empreendimento === emp);
                    if (empTasks.length === 0) return;
                    
                    let targetBaseline = "P0-(padrão)";
                    
                    if (mode === 'latest') {{
                        const baselines = empTasks[0].baselines || {{}};
                        const baselineNames = Object.keys(baselines).filter(b => b !== "P0-(padrão)");
                        if (baselineNames.length > 0) {{
                            targetBaseline = baselineNames[baselineNames.length - 1];
                        }}
                    }}
                    
                    applyBaselineForEmp(emp, targetBaseline);
                    
                    const dropdown = document.querySelector(`.baseline-dropdown-emp[data-emp="${{emp}}"]`);
                    if (dropdown) dropdown.value = targetBaseline;
                }});
                
                // Desmarcar o outro checkbox
                if (mode === 'p0') {{
                    const checkLatest = document.getElementById('apply-latest-all-{project["id"]}');
                    if (checkLatest) checkLatest.checked = false;
                }} else {{
                    const checkP0 = document.getElementById('apply-p0-all-{project["id"]}');
                    if (checkP0) checkP0.checked = false;
                }}
            }}
            
            // Funções auxiliares
            function formatDateDisplay(dateStr) {{
                if (!dateStr) return "N/D";
                const d = new Date(dateStr);
                return `${{String(d.getDate()).padStart(2,'0')}}/${{String(d.getMonth()+1).padStart(2,'0')}}/${{String(d.getFullYear()).slice(-2)}}`;
            }}
            
            function parseDate(dateStr) {{
                if (!dateStr || dateStr === "N/D") return null;
                return new Date(dateStr);
            }}
            
            // Cores por setor
            const coresPorSetor = {{
                "PROSPECÇÃO": {{"previsto": "#FEEFC4", "real": "#AE8141"}},
                "LEGALIZAÇÃO": {{"previsto": "#fadbfe", "real": "#BF08D3"}},
                "PULMÃO": {{"previsto": "#E9E8E8", "real": "#535252"}},
                "ENGENHARIA": {{"previsto": "#fbe3cf", "real": "#be5900"}},
                "INFRA": {{"previsto": "#daebfb", "real": "#125287"}},
                "PRODUÇÃO": {{"previsto": "#E1DFDF", "real": "#252424"}},
                "ARQUITETURA & URBANISMO": {{"previsto": "#D4D3F9", "real": "#453ECC"}},
                "VENDA": {{"previsto": "#dffde1", "real": "#096710"}},
                "Não especificado": {{"previsto": "#ffffff", "real": "#FFFFFF"}}
            }};
            
            // Dados do projeto
            const dataInicio = new Date("{data_min_proj.strftime('%Y-%m-%d')}");
            const dataFim = new Date("{data_max_proj.strftime('%Y-%m-%d')}");
            const totalMeses = {total_meses_proj};
            const larguraMes = 30;
            
            // Renderizar Gantt completo
            function renderGantt() {{
                const sidebarContent = document.getElementById('gantt-sidebar-content-{project["id"]}');
                const chartContainer = document.getElementById('chart-container-{project["id"]}');
                
                sidebarContent.innerHTML = '';
                chartContainer.innerHTML = '';
                
                // --- ORDENAÇÃO DINÂMICA: Por data de início (prevista ou real) ---
                // Usar o tipo de visualização SALVO
                const visualizacaoReal = savedVisualizationType === 'Real';
                
                // Ordenar tasks do mais antigo para o mais novo
                currentTasks.sort((a, b) => {{
                    let dateA, dateB;
                    
                    if (visualizacaoReal) {{
                        // Se visualização for "Real", ordenar por data real
                        dateA = a.start_real ? new Date(a.start_real) : new Date('9999-12-31');
                        dateB = b.start_real ? new Date(b.start_real) : new Date('9999-12-31');
                    }} else {{
                        // Caso contrário, ordenar por data prevista
                        dateA = a.start_previsto ? new Date(a.start_previsto) : new Date('9999-12-31');
                        dateB = b.start_previsto ? new Date(b.start_previsto) : new Date('9999-12-31');
                    }}
                    
                    return dateA - dateB;
                }});
                
                // --- 1. Renderizar Sidebar ---
                currentTasks.forEach((task, idx) => {{
                    const row = document.createElement('div');
                    row.className = 'sidebar-row';
                    row.innerHTML = `
                        <div class="sidebar-cell task-name-cell" title="${{task.name}}">${{task.name}}</div>
                        <div class="sidebar-cell">${{task.ugb}}</div>
                        <div class="sidebar-cell">${{task.inicio_previsto}}</div>
                        <div class="sidebar-cell">${{task.termino_previsto}}</div>
                        <div class="sidebar-cell">${{task.duracao_prev_meses}}</div>
                        <div class="sidebar-cell">${{task.inicio_real}}</div>
                        <div class="sidebar-cell">${{task.termino_real}}</div>
                        <div class="sidebar-cell">${{task.duracao_real_meses}}</div>
                        <div class="sidebar-cell ${{task.status_color_class}}">${{task.progress}}%</div>
                        <div class="sidebar-cell">${{task.vt_text}}</div>
                        <div class="sidebar-cell">${{task.vd_text}}</div>
                    `;
                    sidebarContent.appendChild(row);
                }});
                
                // --- 2. Renderizar Header do Gráfico (Anos e Meses) ---
                const header = document.createElement('div');
                header.className = 'chart-header';
                
                // Header de anos
                const yearHeader = document.createElement('div');
                yearHeader.className = 'year-header';
                
                let currentYear = dataInicio.getFullYear();
                let currentYearStart = 0;
                let currentYearWidth = 0;
                
                for (let m = 0; m < totalMeses; m++) {{
                    const date = new Date(dataInicio);
                    date.setMonth(dataInicio.getMonth() + m);
                    const year = date.getFullYear();
                    
                    if (year !== currentYear) {{
                        const yearSection = document.createElement('div');
                        yearSection.className = 'year-section';
                        yearSection.style.width = `${{currentYearWidth}}px`;
                        yearSection.textContent = currentYear;
                        yearHeader.appendChild(yearSection);
                        
                        currentYear = year;
                        currentYearStart = m * larguraMes;
                        currentYearWidth = larguraMes;
                    }} else {{
                        currentYearWidth += larguraMes;
                    }}
                }}
                
                // Adicionar último ano
                const lastYearSection = document.createElement('div');
                lastYearSection.className = 'year-section';
                lastYearSection.style.width = `${{currentYearWidth}}px`;
                lastYearSection.textContent = currentYear;
                yearHeader.appendChild(lastYearSection);
                
                header.appendChild(yearHeader);
                
                // Header de meses
                const monthHeader = document.createElement('div');
                monthHeader.className = 'month-header';
                
                for (let m = 0; m < totalMeses; m++) {{
                    // CORREÇÃO: Criar data corretamente usando UTC para evitar problemas de timezone
                    const year = dataInicio.getFullYear();
                    const month = dataInicio.getMonth();
                    const date = new Date(year, month + m, 1);
                    
                    const monthCell = document.createElement('div');
                    monthCell.className = 'month-cell';
                    // Usar número do mês com 2 dígitos (01, 02, 03...) igual aos outros gráficos
                    const monthNumber = String(date.getMonth() + 1).padStart(2, '0');
                    monthCell.textContent = monthNumber;
                    monthHeader.appendChild(monthCell);
                }}
                
                header.appendChild(monthHeader);
                chartContainer.appendChild(header);
                
                // --- 3. Renderizar Body do Gráfico (Barras) ---
                const body = document.createElement('div');
                body.className = 'chart-body';
                body.style.minWidth = `${{totalMeses * larguraMes}}px`;
                
                currentTasks.forEach((task, idx) => {{
                    const row = document.createElement('div');
                    row.className = 'gantt-row';
                    
                    // Obter cores do setor
                    const cores = coresPorSetor[task.setor] || coresPorSetor["Não especificado"];
                    
                    // Usar o tipo de visualização SALVO (não ler diretamente dos radio buttons)
                    // Isso garante que o filtro só seja aplicado ao clicar em "Aplicar Filtros"
                    const tipoVisualizacao = savedVisualizationType;
                    
                    let barPrevisto = null;
                    let barReal = null;
                    
                    // DEBUG: Verificar dados de previsto para PULMÃO
                    if (task.setor === 'PULMÃO') {{
                        console.log('DEBUG JS [' + task.setor + '] ' + task.name + ': start_previsto=' + task.start_previsto + ', end_previsto=' + task.end_previsto + ', tipoVis=' + tipoVisualizacao);
                    }}
                    
                    // Barra Prevista (só criar se visualização for "Previsto" ou "Ambos")
                    if ((tipoVisualizacao === 'Previsto' || tipoVisualizacao === 'Ambos') && task.start_previsto && task.end_previsto) {{
                        const startDate = new Date(task.start_previsto);
                        const endDate = new Date(task.end_previsto);
                        
                        const diffStart = (startDate - dataInicio) / (1000 * 60 * 60 * 24);
                        const diffEnd = (endDate - dataInicio) / (1000 * 60 * 60 * 24);
                        
                        const left = (diffStart / 30.4375) * larguraMes;
                        let width = ((diffEnd - diffStart) / 30.4375) * larguraMes;
                        
                        // Se início e fim são o mesmo dia (width = 0), definir largura mínima
                        if (width === 0) {{
                            width = larguraMes / 30.4375; // Largura de 1 dia
                        }}
                        
                        if (width > 0) {{
                            barPrevisto = document.createElement('div');
                            barPrevisto.className = 'gantt-bar previsto';
                            barPrevisto.style.left = `${{left}}px`;
                            barPrevisto.style.width = `${{width}}px`;
                            barPrevisto.style.backgroundColor = cores.previsto;
                            
                            const label = document.createElement('div');
                            label.className = 'bar-label';
                            label.textContent = task.empreendimento || task.name;
                            barPrevisto.appendChild(label);
                            
                            // Tooltip
                            barPrevisto.addEventListener('mouseenter', (e) => {{
                                showTooltip(e, task, 'previsto');
                            }});
                            barPrevisto.addEventListener('mouseleave', hideTooltip);
                            
                            row.appendChild(barPrevisto);
                        }}
                    }}
                    
                    // Barra Real (só criar se visualização for "Real" ou "Ambos")
                    if ((tipoVisualizacao === 'Real' || tipoVisualizacao === 'Ambos') && task.start_real && task.end_real) {{
                        const startDate = new Date(task.start_real);
                        const endDate = new Date(task.end_real);
                        
                        const diffStart = (startDate - dataInicio) / (1000 * 60 * 60 * 24);
                        const diffEnd = (endDate - dataInicio) / (1000 * 60 * 60 * 24);
                        
                        const left = (diffStart / 30.4375) * larguraMes;
                        let width = ((diffEnd - diffStart) / 30.4375) * larguraMes;
                        
                        // Se início e fim são o mesmo dia (width = 0), definir largura mínima
                        if (width === 0) {{
                            width = larguraMes / 30.4375; // Largura de 1 dia
                        }}
                        
                        if (width > 0) {{
                            barReal = document.createElement('div');
                            barReal.className = 'gantt-bar real';
                            barReal.style.left = `${{left}}px`;
                            barReal.style.width = `${{width}}px`;
                            barReal.style.backgroundColor = cores.real;
                            
                            const label = document.createElement('div');
                            label.className = 'bar-label';
                            label.textContent = `${{task.empreendimento}} - ${{task.etapa}} (${{task.progress}}%)`;
                            barReal.appendChild(label);
                            
                            // Tooltip
                            barReal.addEventListener('mouseenter', (e) => {{
                                showTooltip(e, task, 'real');
                            }});
                            barReal.addEventListener('mouseleave', hideTooltip);
                            
                            row.appendChild(barReal);
                        }}
                    }}
                    
                    // --- SOBREPOSIÇÃO: Ajustar z-index se real engloba previsto ---
                    if (barPrevisto && barReal) {{
                        const s_prev = new Date(task.start_previsto);
                        const e_prev = new Date(task.end_previsto);
                        const s_real = new Date(task.start_real);
                        const e_real = new Date(task.end_real);
                        
                        if (s_prev && e_prev && s_real && e_real && s_real <= s_prev && e_real >= e_prev) {{
                            barPrevisto.style.zIndex = '8';
                            barReal.style.zIndex = '7';
                        }}
                        
                        // Renderizar barra de overlap hachurada
                        const overlap_start = new Date(Math.max(s_prev, s_real));
                        const overlap_end = new Date(Math.min(e_prev, e_real));
                        
                        if (overlap_start < overlap_end) {{
                            const diffStart = (overlap_start - dataInicio) / (1000 * 60 * 60 * 24);
                            const diffEnd = (overlap_end - dataInicio) / (1000 * 60 * 60 * 24);
                            
                            const left = (diffStart / 30.4375) * larguraMes;
                            const width = ((diffEnd - diffStart) / 30.4375) * larguraMes;
                            
                            if (width > 0) {{
                                const overlapBar = document.createElement('div');
                                overlapBar.className = 'gantt-bar-overlap';
                                overlapBar.style.left = `${{left}}px`;
                                overlapBar.style.width = `${{width}}px`;
                                row.appendChild(overlapBar);
                            }}
                        }}
                    }}
                    
                    body.appendChild(row);
                }});
                
                chartContainer.appendChild(body);
                
                // --- 4. Adicionar Divisores de Mês ---
                for (let m = 0; m < totalMeses; m++) {{
                    const date = new Date(dataInicio);
                    date.setMonth(dataInicio.getMonth() + m);
                    
                    const divider = document.createElement('div');
                    divider.className = date.getDate() === 1 ? 'month-divider first' : 'month-divider';
                    divider.style.left = `${{m * larguraMes}}px`;
                    body.appendChild(divider);
                }}
                
                // --- 5. Adicionar Linha do Hoje ---
                const hoje = new Date();
                const diffHoje = (hoje - dataInicio) / (1000 * 60 * 60 * 24);
                const leftHoje = (diffHoje / 30.4375) * larguraMes;
                
                if (leftHoje >= 0 && leftHoje <= totalMeses * larguraMes) {{
                    const todayLine = document.createElement('div');
                    todayLine.className = 'today-line';
                    todayLine.style.left = `${{leftHoje}}px`;
                    body.appendChild(todayLine);
                }}
            }}
            
            // Funções de Tooltip
            function showTooltip(event, task, tipo) {{
                const tooltip = document.getElementById('tooltip');
                
                let content = `
                    <strong>${{task.name}}</strong><br>
                    <strong>Setor:</strong> ${{task.setor}}<br>
                    <strong>UGB:</strong> ${{task.ugb}}<br>
                `;
                
                if (tipo === 'previsto') {{
                    content += `
                        <strong>Previsto:</strong><br>
                        Início: ${{task.inicio_previsto}}<br>
                        Término: ${{task.termino_previsto}}<br>
                        Duração: ${{task.duracao_prev_meses}} meses
                    `;
                }} else {{
                    content += `
                        <strong>Real:</strong><br>
                        Início: ${{task.inicio_real}}<br>
                        Término: ${{task.termino_real}}<br>
                        Duração: ${{task.duracao_real_meses}} meses<br>
                        Progresso: ${{task.progress}}%<br>
                        VT: ${{task.vt_text}} | VD: ${{task.vd_text}}
                    `;
                }}
                
                tooltip.innerHTML = content;
                tooltip.classList.add('show');
                
                // Posicionar tooltip (relativo ao container para funcionar em fullscreen)
                const container = document.getElementById('gantt-container-{project["id"]}');
                const rect = container.getBoundingClientRect();
                const x = event.clientX - rect.left + 10;
                const y = event.clientY - rect.top + 10;
                tooltip.style.left = `${{x}}px`;
                tooltip.style.top = `${{y}}px`;
            }}
            
            function hideTooltip() {{
                const tooltip = document.getElementById('tooltip');
                tooltip.classList.remove('show');
            }}
            
            // Event listeners
            document.getElementById('filter-btn-{project["id"]}').addEventListener('click', () => {{
                document.getElementById('filter-menu-{project["id"]}').classList.toggle('is-open');
                document.getElementById('baseline-selector-{project["id"]}').classList.remove('is-open');
            }});
            
            document.getElementById('baseline-btn-{project["id"]}').addEventListener('click', () => {{
                document.getElementById('baseline-selector-{project["id"]}').classList.toggle('is-open');
                document.getElementById('filter-menu-{project["id"]}').classList.remove('is-open');
            }});
            
            document.getElementById('toggle-sidebar-btn-{project["id"]}').addEventListener('click', () => {{
                document.getElementById('gantt-sidebar-wrapper-{project["id"]}').classList.toggle('collapsed');
            }});
            
            document.getElementById('fullscreen-btn-{project["id"]}').addEventListener('click', () => {{
                const container = document.getElementById('gantt-container-{project["id"]}');
                if (!document.fullscreenElement) {{
                    container.requestFullscreen();
                }} else {{
                    document.exitFullscreen();
                }}
            }});
            
            // Event listeners para radio buttons de visualização (para reordenar ao mudar)
            document.querySelectorAll('input[name="filter-vis-{project["id"]}"]').forEach(radio => {{
                radio.addEventListener('change', () => {{
                    renderGantt(); // Re-renderizar com nova ordenação
                }});
            }});
            
            // --- DRAG TO SCROLL: Arrastar com mouse para navegar (2D - Diagonal) ---
            const chartContent = document.getElementById('gantt-chart-content-{project["id"]}');
            let isDragging = false;
            let startX;
            let startY;
            let scrollLeft;
            let scrollTop;
            
            chartContent.addEventListener('mousedown', (e) => {{
                isDragging = true;
                chartContent.classList.add('active');
                startX = e.pageX - chartContent.offsetLeft;
                startY = e.pageY - chartContent.offsetTop;
                scrollLeft = chartContent.scrollLeft;
                scrollTop = chartContent.scrollTop;
                chartContent.style.cursor = 'grabbing';
            }});
            
            chartContent.addEventListener('mouseleave', () => {{
                isDragging = false;
                chartContent.classList.remove('active');
                chartContent.style.cursor = 'grab';
            }});
            
            chartContent.addEventListener('mouseup', () => {{
                isDragging = false;
                chartContent.classList.remove('active');
                chartContent.style.cursor = 'grab';
            }});
            
            chartContent.addEventListener('mousemove', (e) => {{
                if (!isDragging) return;
                e.preventDefault();
                
                // Movimento horizontal
                const x = e.pageX - chartContent.offsetLeft;
                const walkX = (x - startX) * 2; // Multiplicador para velocidade horizontal
                chartContent.scrollLeft = scrollLeft - walkX;
                
                // Movimento vertical
                const y = e.pageY - chartContent.offsetTop;
                const walkY = (y - startY) * 2; // Multiplicador para velocidade vertical
                chartContent.scrollTop = scrollTop - walkY;
                
                // --- SINCRONIZAÇÃO: Sidebar acompanha scroll vertical do gráfico ---
                const sidebarContent = document.getElementById('gantt-sidebar-content-{project["id"]}');
                if (sidebarContent) {{
                    sidebarContent.scrollTop = chartContent.scrollTop;
                }}
            }});
            
            // --- SINCRONIZAÇÃO ADICIONAL: Scroll direto na sidebar também sincroniza ---
            const sidebarContent = document.getElementById('gantt-sidebar-content-{project["id"]}');
            if (sidebarContent) {{
                sidebarContent.addEventListener('scroll', () => {{
                    chartContent.scrollTop = sidebarContent.scrollTop;
                }});
            }}
            
            // --- REDIMENSIONAMENTO DO SELETOR DE BASELINE ---
            const baselineSelector = document.getElementById('baseline-selector-{project["id"]}');
            const resizeCorner = baselineSelector ? baselineSelector.querySelector('.baseline-resize-corner') : null;
            
            if (resizeCorner) {{
                let isResizing = false;
                let startX, startY, startWidth, startHeight, startRight;
                
                resizeCorner.addEventListener('mousedown', (e) => {{
                    isResizing = true;
                    startX = e.clientX;
                    startY = e.clientY;
                    startWidth = parseInt(document.defaultView.getComputedStyle(baselineSelector).width, 10);
                    startHeight = parseInt(document.defaultView.getComputedStyle(baselineSelector).height, 10);
                    startRight = parseInt(document.defaultView.getComputedStyle(baselineSelector).right, 10);
                    
                    e.preventDefault();
                    e.stopPropagation();
                }});
                
                document.addEventListener('mousemove', (e) => {{
                    if (!isResizing) return;
                    
                    // Calcular movimento
                    const deltaX = e.clientX - startX;
                    const deltaY = e.clientY - startY;
                    
                    // Canto na ESQUERDA: arrastar para ESQUERDA (deltaX negativo) aumenta largura
                    const newWidth = startWidth - deltaX;  // Inverte deltaX
                    const newHeight = startHeight + deltaY;
                    
                    // Aplicar largura com limites
                    if (newWidth >= 250 && newWidth <= 700) {{
                        baselineSelector.style.width = newWidth + 'px';
                        // Não precisa ajustar right pois está ancorado na direita
                    }}
                    
                    // Aplicar altura com limites
                    if (newHeight >= 200 && newHeight <= 800) {{
                        baselineSelector.style.height = newHeight + 'px';
                        
                        // Ajustar altura da tabela interna para preencher o espaço
                        const table = baselineSelector.querySelector('.baseline-selector-table');
                        if (table) {{
                            // Altura disponível = altura total - padding - título - aplicação rápida - margens
                            const availableHeight = newHeight - 150; // 150px para cabeçalho e padding
                            table.style.maxHeight = Math.max(200, availableHeight) + 'px';
                        }}
                    }}
                }});
                
                document.addEventListener('mouseup', () => {{
                    isResizing = false;
                }});
            }}
            
            // Inicializar filtros de etapas, grupos e macroetapas para o setor atual
            renderStageCheckboxes(initialSectorName);
            renderGroupCheckboxes(initialSectorName);
            renderMacroetapasCheckboxes(initialSectorName);
            initUGBFilter();
            
            // Renderizar inicial com filtros aplicados
            // Pequeno delay para garantir que Virtual Selects estão completamente inicializados
            setTimeout(() => {{
                applyFiltersAndRedraw();
            }}, 200);
        </script>
    </body>
    </html>
    """
    
    components.html(gantt_html, height=altura_gantt, scrolling=True)

# --- FUNÇÃO PRINCIPAL DE GANTT (DISPATCHER) ---
def gerar_gantt(df, tipo_visualizacao, filtrar_nao_concluidas, df_original_para_ordenacao, pulmao_status, pulmao_meses, etapa_selecionada_inicialmente, setor_selecionado_inicialmente=None):
    """
    Decide qual Gantt gerar com base na seleção da etapa inicial e do setor.
    
    Modos de visualização:
    1. Por Projeto: Mostra todas as etapas de um/vários empreendimentos (etapa="Todos", setor=None)
    2. Consolidado: Mostra uma etapa em múltiplos empreendimentos (etapa!=  "Todos", setor=None)
    3. Por Setor: Mostra todas as etapas de um setor em todos os empreendimentos (setor!="Todos")
    """
    if df.empty:
        st.warning("Sem dados disponíveis para exibir o Gantt.")
        return

    # Decisão do modo baseada nos parâmetros
    # Prioridade: Setor > Etapa > Projeto
    if setor_selecionado_inicialmente and setor_selecionado_inicialmente != "Todos":
        # Modo 3: Por Setor
        gerar_gantt_por_setor(
            df, 
            tipo_visualizacao, 
            df_original_para_ordenacao, 
            pulmao_status, 
            pulmao_meses,
            setor_selecionado_inicialmente
        )
    elif etapa_selecionada_inicialmente != "Todos":
        # Modo 2: Consolidado (por etapa)
        gerar_gantt_consolidado(
            df, 
            tipo_visualizacao, 
            df_original_para_ordenacao, 
            pulmao_status, 
            pulmao_meses,
            etapa_selecionada_inicialmente
        )
    else:
        # Modo 1: Por Projeto
        gerar_gantt_por_projeto(
            df, 
            tipo_visualizacao, 
            df_original_para_ordenacao, 
            pulmao_status, 
            pulmao_meses
        )
# O restante do código Streamlit...
st.set_page_config(layout="wide", page_title="Dashboard de Gantt Comparativo")

# Tente executar a tela de boas-vindas. Se os arquivos não existirem, apenas pule.
try:
    if show_welcome_screen():
        st.stop()
except NameError:
    st.warning("Arquivo `popup.py` não encontrado. Pulando tela de boas-vindas.")
except Exception as e:
    st.warning(f"Erro ao carregar `popup.py`: {e}")


st.markdown("""
<style>
    div.stMultiSelect div[role="option"] input[type="checkbox"]:checked + div > div:first-child { background-color: #4a0101 !important; border-color: #4a0101 !important; }
    div.stMultiSelect [aria-selected="true"] { background-color: #f8d7da !important; color: #333 !important; border-radius: 4px; }
    div.stMultiSelect [aria-selected="true"]::after { color: #4a0101 !important; font-weight: bold; }
    .stSidebar .stMultiSelect, .stSidebar .stSelectbox, .stSidebar .stRadio { margin-bottom: 1rem; }
    .nav-button-container { position: fixed; right: 20px; top: 20%; transform: translateY(-20%); z-index: 80; background: white; padding: 5px; border-radius: 15px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
    .nav-link { display: block; background-color: #a6abb5; color: white !important; text-decoration: none !important; border-radius: 10px; padding: 5px 10px; margin: 5px 0; text-align: center; font-weight: bold; font-size: 14px; transition: all 0.3s ease; }
    .nav-link:hover { background-color: #ff4b4b; transform: scale(1.05); }
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_data():
    df_real = pd.DataFrame()
    df_previsto = pd.DataFrame()
    
    # INICIALIZAR SISTEMA DE BASELINES (ADICIONE ESTAS LINHAS)
    create_baselines_table()
    if 'unsent_baselines' not in st.session_state:
        st.session_state.unsent_baselines = {}
    if 'mock_baselines' not in st.session_state:
        st.session_state.mock_baselines = {}

    if buscar_e_processar_dados_completos:
        try:
            df_real_resultado = buscar_e_processar_dados_completos()

            if df_real_resultado is not None and not df_real_resultado.empty:
                df_real = df_real_resultado.copy()
                df_real["Etapa"] = df_real["Etapa"].apply(padronizar_etapa)
                # Renomeia colunas ANTES do pivot se os nomes originais forem diferentes
                df_real = df_real.rename(columns={"EMP": "Empreendimento", "%_Concluido": "% concluído"})

                # Converte porcentagem antes do pivot
                if "% concluído" in df_real.columns:
                    df_real["% concluído"] = df_real["% concluído"].apply(converter_porcentagem)
                else:
                    # Adiciona a coluna se não existir, para evitar erro no pivot
                    df_real["% concluído"] = 0.0

                # Verifica se 'Inicio_Fim' e 'Valor' existem antes de pivotar
                if "Inicio_Fim" in df_real.columns and "Valor" in df_real.columns:
                    df_real_pivot = df_real.pivot_table(
                        index=["Empreendimento", "Etapa", "% concluído"], # Inclui % concluído no índice
                        columns="Inicio_Fim",
                        values="Valor",
                        aggfunc="first"
                    ).reset_index()
                    df_real_pivot.columns.name = None # Remove o nome do índice das colunas

                    # Renomeia APÓS o pivot
                    if "INICIO" in df_real_pivot.columns:
                        df_real_pivot = df_real_pivot.rename(columns={"INICIO": "Inicio_Real"})
                    if "TERMINO" in df_real_pivot.columns:
                        df_real_pivot = df_real_pivot.rename(columns={"TERMINO": "Termino_Real"})
                    df_real = df_real_pivot # Atualiza df_real com o resultado pivotado
                else:
                     # st.warning("Colunas 'Inicio_Fim' ou 'Valor' não encontradas nos dados reais. Pivot não aplicado.")
                     # Mantém df_real como está, mas garante colunas esperadas
                     if "Inicio_Real" not in df_real.columns: df_real["Inicio_Real"] = pd.NaT
                     if "Termino_Real" not in df_real.columns: df_real["Termino_Real"] = pd.NaT

            else:
                # st.info("Nenhum dado real retornado por buscar_e_processar_dados_completos().")
                df_real = pd.DataFrame() # Garante que seja um DF vazio
        except Exception as e:
            st.error(f"Erro detalhado ao processar dados reais: {e}")
            import traceback
            # st.error(traceback.format_exc()) # Mostra o traceback completo para depuração
            df_real = pd.DataFrame()

    if tratar_macrofluxo:
        try:
            df_previsto_resultado = tratar_macrofluxo()
            if df_previsto_resultado is not None and not df_previsto_resultado.empty:
                df_previsto = df_previsto_resultado.copy()
                df_previsto["Etapa"] = df_previsto["Etapa"].apply(padronizar_etapa)
                df_previsto = df_previsto.rename(columns={"EMP": "Empreendimento", "UGB": "UGB"})
                df_previsto_pivot = df_previsto.pivot_table(index=["UGB", "Empreendimento", "Etapa"], columns="Inicio_Fim", values="Valor", aggfunc="first").reset_index()
                df_previsto_pivot.columns.name = None
                if "INICIO" in df_previsto_pivot.columns:
                    df_previsto_pivot = df_previsto_pivot.rename(columns={"INICIO": "Inicio_Prevista"})
                if "TERMINO" in df_previsto_pivot.columns:
                    df_previsto_pivot = df_previsto_pivot.rename(columns={"TERMINO": "Termino_Prevista"})
                df_previsto = df_previsto_pivot
            else:
                df_previsto = pd.DataFrame()
        except Exception as e:
            st.warning(f"Erro ao carregar dados previstos: {e}")
            df_previsto = pd.DataFrame()

    if df_real.empty and df_previsto.empty:
        st.warning("Nenhuma fonte de dados carregada. Usando dados de exemplo.")
        return criar_dados_exemplo()

    etapas_base_oficial = set(sigla_para_nome_completo.keys())
    etapas_nos_dados = set()
    if not df_real.empty:
        etapas_nos_dados.update(df_real["Etapa"].unique())
    if not df_previsto.empty:
        etapas_nos_dados.update(df_previsto["Etapa"].unique())

    etapas_nao_mapeadas = etapas_nos_dados - etapas_base_oficial

    if "UNKNOWN" in etapas_nao_mapeadas:
       etapas_nao_mapeadas.remove("UNKNOWN")

    # CORREÇÃO: Remover a linha problemática que tenta usar df_data antes de ser definida
    # empreendimentos_baseline = df_data['Empreendimento'].unique().tolist() if not df_data.empty else []
    
    if not df_real.empty and not df_previsto.empty:
        df_merged = pd.merge(df_previsto, df_real[["Empreendimento", "Etapa", "Inicio_Real", "Termino_Real", "% concluído"]], on=["Empreendimento", "Etapa"], how="outer")

        # --- Lógica de Exceção para Etapas Apenas no Real ---
        etapas_excecao = [
            "PE. LIMP.", "ORÇ. LIMP.", "SUP. LIMP.",
            "PE. TER.", "ORÇ. TER.", "SUP. TER.", 
            "PE. INFRA", "ORÇ. INFRA", "SUP. INFRA",
            "PE. PAV", "ORÇ. PAV", "SUP. PAV"
        ]

        # Identifica linhas onde o previsto (Inicio_Prevista) é nulo, mas a etapa é de exceção
        filtro_excecao = df_merged["Etapa"].isin(etapas_excecao) & df_merged["Inicio_Prevista"].isna()
        df_merged.loc[filtro_excecao, "Inicio_Prevista"] = df_merged.loc[filtro_excecao, "Inicio_Real"]
        df_merged.loc[filtro_excecao, "Termino_Prevista"] = df_merged.loc[filtro_excecao, "Termino_Real"]

        # CORREÇÃO: Buscar UGB correta para as subetapas
        if not df_previsto.empty:
            # Criar mapeamento de UGB por empreendimento
            ugb_por_empreendimento = df_previsto.groupby('Empreendimento')['UGB'].first().to_dict()
            
            # Para cada subetapa sem UGB, buscar a UGB do empreendimento correspondente
            for idx in df_merged[filtro_excecao & df_merged["UGB"].isna()].index:
                empreendimento = df_merged.loc[idx, 'Empreendimento']
                if empreendimento in ugb_por_empreendimento:
                    df_merged.loc[idx, 'UGB'] = ugb_por_empreendimento[empreendimento]
    elif not df_previsto.empty:
        # Se só temos dados previstos
        df_merged = df_previsto.copy()
    elif not df_real.empty:
        # Se só temos dados reais
        df_merged = df_real.copy()
    else:
        # Nenhum dado disponível
        df_merged = pd.DataFrame()


        # Verifica se há etapas não mapeadas
    if etapas_nao_mapeadas:

        # CSS para estilizar o sininho e o popup
        st.markdown("""
        <style>
        .macrofluxo-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 20px;
        }

        .macrofluxo-title {
            font-size: 32px;
            font-weight: bold;
            color: #1f77b4;
            margin: 0;
        }

        .notification-bell {
            position: relative;
            display: inline-block;
            cursor: pointer;
            font-size: 24px;
            margin-left: -30px;
            margin-top: 7px;
        }

        .notification-icon {
            width: 24px;
            height: 24px;
            color: #ff6b00;
        }

        .notification-bell:hover .notification-icon {
            color: #ff4500;
        }

        .notification-popup {
            display: none;
            position: absolute;
            background-color: #ffcc00;
            border: 1px solid #ff9900;
            border-radius: 5px;
            padding: 15px;
            min-width: 300px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            z-index: 1000;
            left: 30px;
            top: 0;
        }

        .notification-bell:hover .notification-popup {
            display: block;
        }

        .notification-content {
            color: #333;
            font-size: 14px;
        }

        .etapa-code {
            background-color: #f8f9fa;
            padding: 5px;
            margin: 3px 0;
            border-radius: 3px;
            font-family: monospace;
            font-size: 12px;
        }
        </style>
        """, unsafe_allow_html=True)

        # HTML para o cabeçalho com título e ícone de notificação
        etapas_html = "".join([f'<div class="etapa-code">{etapa}</div>' for etapa in sorted(list(etapas_nao_mapeadas))])

        st.markdown(f"""
        <div class="macrofluxo-header">
            <h1 class="macrofluxo-title">Macrofluxo</h1>
            <div class="notification-bell">
                <svg class="notification-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                </svg>
                <div class="notification-popup">
                    <div class="notification-content">
                        <strong>⚠️ Alerta de Dados</strong><br><br>
                        As seguintes etapas foram encontradas nos dados, mas não são reconhecadas. 
                        Verifique a ortografia no arquivo de origem:
                        <br><br>
                        {etapas_html}
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    else:
        # Quando não há etapas não mapeadas, mostra apenas o título sem o ícone
        st.markdown("""
        <div class="macrofluxo-header">
            <h1 class="macrofluxo-title">Macrofluxo</h1>
        </div>
        """, unsafe_allow_html=True)

    df_merged["% concluído"] = df_merged["% concluído"].fillna(0)
    df_merged.dropna(subset=["Empreendimento", "Etapa"], inplace=True)

    df_merged["GRUPO"] = df_merged["Etapa"].map(GRUPO_POR_ETAPA).fillna("Não especificado")
    df_merged["SETOR"] = df_merged["Etapa"].map(SETOR_POR_ETAPA).fillna("Não especificado")

    return df_merged

def criar_dados_exemplo():
    dados = {
        "UGB": ["UGB1", "UGB1", "UGB1", "UGB2", "UGB2", "UGB1"],
        "Empreendimento": ["Residencial Alfa", "Residencial Alfa", "Residencial Alfa", "Condomínio Beta", "Condomínio Beta", "Projeto Gama"],
        "Etapa": ["PROSPEC", "LEGVENDA", "PL.LIMP", "PROSPEC", "LEGVENDA", "PROSPEC"],
        "Inicio_Prevista": pd.to_datetime(["2024-01-01", "2024-02-15", "2024-04-01", "2024-01-20", "2024-03-10", "2024-05-01"]),
        "Termino_Prevista": pd.to_datetime(["2024-02-14", "2024-03-31", "2024-05-15", "2024-03-09", "2024-04-30", "2024-06-15"]),
        "Inicio_Real": pd.to_datetime(["2024-01-05", "2024-02-20", pd.NaT, "2024-01-22", "2024-03-15", pd.NaT]),
        "Termino_Real": pd.to_datetime(["2024-02-18", pd.NaT, pd.NaT, "2024-03-12", pd.NaT, pd.NaT]),
        "% concluído": [100, 50, 0, 100, 25, 0],
    }
    df_exemplo = pd.DataFrame(dados)
    df_exemplo["GRUPO"] = df_exemplo["Etapa"].map(GRUPO_POR_ETAPA).fillna("PLANEJAMENTO MACROFLUXO")
    df_exemplo["SETOR"] = df_exemplo["Etapa"].map(SETOR_POR_ETAPA).fillna("PROSPECÇÃO")
    return df_exemplo

@st.cache_data
def get_unique_values(df, column):
    return sorted(df[column].dropna().unique().tolist())

@st.cache_data
def filter_dataframe(df, ugb_filter, emp_filter, grupo_filter, setor_filter):
    if not ugb_filter:
        return df.iloc[0:0]

    df_filtered = df[df["UGB"].isin(ugb_filter)]
    if emp_filter:
        df_filtered = df_filtered[df_filtered["Empreendimento"].isin(emp_filter)]
    if grupo_filter:
        df_filtered = df_filtered[df_filtered["GRUPO"].isin(grupo_filter)]
    if setor_filter:
        df_filtered = df_filtered[df_filtered["SETOR"].isin(setor_filter)]
    return df_filtered

# --- Bloco Principal ---
with st.spinner("Carregando e processando dados..."):
    # 1. Carrega os dados
    df_data = load_data()
    
    # 2. Verifica se carregou corretamente
    if df_data is not None:
        st.session_state.df_data = df_data
        
        # Inicializa variáveis de controle visual (prevenção de erro de chave)
        if 'show_context_success' not in st.session_state:
            st.session_state.show_context_success = False
        if 'show_context_error' not in st.session_state:
            st.session_state.show_context_error = False
        if 'context_menu_trigger' not in st.session_state:
            st.session_state.context_menu_trigger = False

        # --- AQUI ESTÁ A CORREÇÃO PRINCIPAL ---
        # Chamamos a função passando o df_data carregado AGORA.
        # Não confiamos apenas no session_state antigo.
        process_context_menu_actions(df_data)
        # --------------------------------------

        with st.sidebar:
            st.markdown("<br>", unsafe_allow_html=True)
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                try:
                    st.image("logoNova.png", width=200)
                except:
                    pass
        
            st.markdown("---")
            
            # Filtro UGB centralizado
            st.markdown("""
            <style>
            .stMultiSelect [data-baseweb="select"] {
                margin: 0 auto;
            }
            .stMultiSelect > div > div {
                display: flex;
                justify-content: center;
            }
            </style>
            """, unsafe_allow_html=True)
            
            ugb_options = get_unique_values(df_data, "UGB")
            
            # Inicializar selected_ugb com todas as UGBs para manter compatibilidade com filter_dataframe
            if 'selected_ugb' not in st.session_state:
                st.session_state.selected_ugb = ugb_options
            
            # UGB automaticamente selecionado (todas as opções) - filtro removido da sidebar
            selected_ugb = ugb_options  # Todas as UGBs sempre selecionadas
            st.session_state.selected_ugb = selected_ugb
            
            # Botão centralizado
            st.markdown("""
            <style>
            .stButton > button {
                width: 100%;
                display: block;
                margin: 0 auto;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # Definir valores padrão para os filtros removidos
            selected_emp = get_unique_values(df_data[df_data["UGB"].isin(selected_ugb)], "Empreendimento") if selected_ugb else []
            selected_grupo = get_unique_values(df_data, "GRUPO")
            selected_setor = list(SETOR.keys())

            # Filtrar o DataFrame com base apenas na UGB para determinar as etapas disponíveis
            df_temp_filtered = filter_dataframe(df_data, selected_ugb, selected_emp, selected_grupo, selected_setor)
            if not df_temp_filtered.empty:
                etapas_disponiveis = get_unique_values(df_temp_filtered, "Etapa")
                etapas_ordenadas = [etapa for etapa in ORDEM_ETAPAS_GLOBAL if etapa in etapas_disponiveis]
                etapas_para_exibir = ["Todos"] + [sigla_para_nome_completo.get(e, e) for e in etapas_ordenadas]
            else:
                etapas_para_exibir = ["Todos"]
            
            # Inicializa o estado da visualização se não existir
            if 'consolidated_view' not in st.session_state:
                st.session_state.consolidated_view = False
                st.session_state.selected_etapa_nome = "Todos" # Valor inicial

            # Inicializa o estado da visualização por setor se não existir
            if 'sector_view' not in st.session_state:
                st.session_state.sector_view = False
                st.session_state.selected_setor_nome = "Todos"
            
            # Funções de callback para cada modo de visualização
            def set_project_view():
                st.session_state.consolidated_view = False
                st.session_state.sector_view = False
                st.session_state.selected_etapa_nome = "Todos"
                st.session_state.selected_setor_nome = "Todos"
            
            def set_consolidated_view():
                st.session_state.consolidated_view = True
                st.session_state.sector_view = False
                # Pega a primeira etapa disponível
                etapa_para_consolidar = next((e for e in etapas_para_exibir if e != "Todos"), "Todos")
                st.session_state.selected_etapa_nome = etapa_para_consolidar
                st.session_state.selected_setor_nome = "Todos"
            
            def set_sector_view():
                st.session_state.consolidated_view = False
                st.session_state.sector_view = True
                st.session_state.selected_etapa_nome = "Todos"
                # Pega o primeiro setor disponível
                setores_disponiveis = sorted(list(SETOR.keys()))
                setor_para_exibir = setores_disponiveis[0] if setores_disponiveis else "Todos"
                st.session_state.selected_setor_nome = setor_para_exibir

            # --- TRÊS BOTÕES SEPARADOS PARA NAVEGAÇÃO ---
            st.markdown("Gráficos Gantt:")
            
            # Determinar qual está ativo
            projeto_ativo = not st.session_state.consolidated_view and not st.session_state.sector_view
            consolidado_ativo = st.session_state.consolidated_view
            setor_ativo = st.session_state.sector_view
            
            # Por Projeto - com checkmark se ativo
            st.button(
                f"{'✓ ' if projeto_ativo else ''}Por Projeto", 
                on_click=set_project_view, 
                use_container_width=True
            )
            
            # Por Etapa (Consolidado) - com checkmark se ativo
            st.button(
                f"{'✓ ' if consolidado_ativo else ''}Por Etapa", 
                on_click=set_consolidated_view, 
                use_container_width=True
            )
            
            # Por Setor - com checkmark se ativo
            st.button(
                f"{'✓ ' if setor_ativo else ''}Por Setor", 
                on_click=set_sector_view, 
                use_container_width=True
            )
            
            # Mensagens centralizadas
            st.markdown("""
            <style>
            .stSuccess, .stInfo {
                text-align: center;
            }
            </style>
            """, unsafe_allow_html=True)
            
            etapas_nao_mapeadas = []  # Você precisa definir esta variável com os dados apropriados
            
            # Define a variável que será usada no resto do código
            selected_etapa_nome = st.session_state.selected_etapa_nome
            selected_setor_nome = st.session_state.selected_setor_nome

            # Exibe a etapa selecionada quando no modo consolidado (alerta abaixo do botão)
            if st.session_state.consolidated_view:
                st.success(f"**Visão Consolidada Ativa:** {selected_etapa_nome}")
            
            # Exibe o setor selecionado quando no modo por setor
            if st.session_state.sector_view:
                st.info(f"**Visão por Setor Ativa:** {selected_setor_nome}")

            filtrar_nao_concluidas = False
            
            # Definir valores padrão para os filtros removidos
            pulmao_status = "Sem Pulmão"
            pulmao_meses = 0
            tipo_visualizacao = "Ambos"  

            # --- Menu de Contexto para Gantt ---
            def create_gantt_context_menu_component(selected_empreendimento):
                """Cria o componente do menu de contexto para o gráfico Gantt"""
                
                # Mostrar mensagens de sucesso/erro do menu de contexto
                if st.session_state.get('show_context_success'):
                    success_container = st.empty()
                    success_container.success(st.session_state.context_menu_success)
                    st.session_state.show_context_success = False
                    
                    # Remover a mensagem após 3 segundos
                    import time
                    time.sleep(3)
                    success_container.empty()
                
                if st.session_state.get('show_context_error'):
                    error_container = st.empty()
                    error_container.error(st.session_state.context_menu_error)
                    st.session_state.show_context_error = False
                    
                    import time
                    time.sleep(3)
                    error_container.empty()
                
                # HTML completo com CSS e JavaScript para o menu visual
                context_menu_html = f"""
                <style>
                #context-menu {{
                    position: fixed;
                    background: white;
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    box-shadow: 2px 2px 10px rgba(0,0,0,0.2);
                    z-index: 10000;
                    display: none;
                    font-family: Arial, sans-serif;
                }}
                .context-menu-item {{
                    padding: 12px 20px;
                    cursor: pointer;
                    border-bottom: 1px solid #eee;
                    font-size: 14px;
                    transition: background-color 0.2s;
                }}
                .context-menu-item:hover {{
                    background: #f0f0f0;
                }}
                .context-menu-item:last-child {{
                    border-bottom: none;
                }}
                #gantt-chart-area {{
                    position: relative;
                    border: 2px dashed #ccc;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background-color: #f9f9f9;
                    cursor: pointer;
                    margin: 10px 0;
                    user-select: none;
                    min-height: 100px;
                }}
                #baseline-status {{
                    margin-top: 10px;
                    padding: 10px;
                    border-radius: 5px;
                    text-align: center;
                    font-weight: bold;
                    display: none;
                }}
                .status-creating {{
                    background-color: #fff3cd;
                    border: 1px solid #ffeaa7;
                    color: #856404;
                }}
                .status-success {{
                    background-color: #d1ecf1;
                    border: 1px solid #bee5eb;
                    color: #0c5460;
                }}
                .status-error {{
                    background-color: #f8d7da;
                    border: 1px solid #f5c6cb;
                    color: #721c24;
                }}
                #hidden-iframe {{
                    position: absolute;
                    width: 1px;
                    height: 1px;
                    border: none;
                    opacity: 0;
                    pointer-events: none;
                }}
                .loading-overlay {{
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(255, 255, 255, 0.8);
                    display: none;
                    justify-content: center;
                    align-items: center;
                    z-index: 10001;
                    font-family: Arial, sans-serif;
                }}
                .loading-spinner {{
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    text-align: center;
                }}
                .gantt-context-hint {{
                    text-align: center;
                    color: #666;
                    font-size: 12px;
                    margin-top: 5px;
                }}
                </style>

                <div id="gantt-chart-area">
                    <div style="text-align: center;">
                        <h3>📊 Área do Gráfico de Gantt</h3>
                        <p>Clique com o botão direito para abrir o menu de linha de base</p>
                        <div class="gantt-context-hint">Empreendimento: {selected_empreendimento}</div>
                    </div>
                </div>

                <div id="baseline-status"></div>

                <!-- Overlay de loading -->
                <div id="loading-overlay" class="loading-overlay">
                    <div class="loading-spinner">
                        <h3>🔄 Criando Linha de Base</h3>
                        <p>Por favor, aguarde...</p>
                    </div>
                </div>

                <!-- Iframe invisível para carregamentos -->
                <iframe id="hidden-iframe" name="hidden-iframe"></iframe>

                <div id="context-menu">
                    <div class="context-menu-item" id="take-baseline">📸 Criar Linha de Base</div>
                    <div class="context-menu-item" id="restore-baseline">🔄 Restaurar Linha de Base</div>
                    <div class="context-menu-item" id="compare-baseline">📊 Comparar com Baseline</div>
                    <div class="context-menu-item" id="delete-baseline">🗑️ Deletar Linha de Base</div>
                </div>

                <script>
                // Elementos
                const ganttArea = document.getElementById('gantt-chart-area');
                const contextMenu = document.getElementById('context-menu');
                const statusDiv = document.getElementById('baseline-status');
                const takeBaselineBtn = document.getElementById('take-baseline');
                const loadingOverlay = document.getElementById('loading-overlay');
                const hiddenIframe = document.getElementById('hidden-iframe');
                
                // Função para mostrar o menu
                function showContextMenu(x, y) {{
                    contextMenu.style.left = x + 'px';
                    contextMenu.style.top = y + 'px';
                    contextMenu.style.display = 'block';
                }}
                
                // Função para esconder o menu
                function hideContextMenu() {{
                    contextMenu.style.display = 'none';
                }}
                
                // Função para mostrar/ocultar loading
                function showLoading() {{
                    loadingOverlay.style.display = 'flex';
                }}
                
                function hideLoading() {{
                    loadingOverlay.style.display = 'none';
                }}
                
                // Função para mostrar status
                function showStatus(message, type) {{
                    statusDiv.textContent = message;
                    statusDiv.className = '';
                    statusDiv.classList.add(type);
                    statusDiv.style.display = 'block';
                    
                    // Auto-esconder após 3 segundos
                    setTimeout(() => {{
                        statusDiv.style.display = 'none';
                    }}, 3000);
                }}
                
                // Função para criar linha de base via iframe invisível
                function executeTakeBaseline() {{
                    showStatus('🔄 Criando linha de base...', 'status-creating');
                    showLoading();
                    
                    // Criar URL com parâmetros para o Streamlit processar
                    const timestamp = new Date().getTime();
                    const url = `?context_action=take_baseline&empreendimento={selected_empreendimento}&t=${{timestamp}}`;
                    
                    // Usar iframe invisível para carregar a URL
                    hiddenIframe.src = url;
                    
                    // Quando o iframe terminar de carregar
                    hiddenIframe.onload = function() {{
                        hideLoading();
                        showStatus('✅ Linha de base criada! Verifique a barra lateral para enviar para AWS.', 'status-success');
                        
                        // Forçar uma atualização suave após 1 segundo
                        setTimeout(() => {{
                            // Disparar um evento customizado para atualizar a interface
                            const event = new Event('baselineCreated');
                            document.dispatchEvent(event);
                        }}, 1000);
                    }};
                    
                    hideContextMenu();
                }}
                
                // Event Listeners
                if (ganttArea) {{
                    ganttArea.addEventListener('contextmenu', function(e) {{
                        e.preventDefault();
                        e.stopPropagation();
                        showContextMenu(e.pageX, e.pageY);
                    }});
                }}
                
                // Event listener para o botão de criar linha de base
                if (takeBaselineBtn) {{
                    takeBaselineBtn.addEventListener('click', function() {{
                        executeTakeBaseline();
                    }});
                }}
                
                // Event listeners para outros botões (placeholder)
                const restoreBaselineBtn = document.getElementById('restore-baseline');
                const compareBaselineBtn = document.getElementById('compare-baseline');
                const deleteBaselineBtn = document.getElementById('delete-baseline');
                
                if (restoreBaselineBtn) {{
                    restoreBaselineBtn.addEventListener('click', function() {{
                        showStatus('🔄 Funcionalidade em desenvolvimento...', 'status-creating');
                        hideContextMenu();
                    }});
                }}
                
                if (compareBaselineBtn) {{
                    compareBaselineBtn.addEventListener('click', function() {{
                        showStatus('📊 Funcionalidade em desenvolvimento...', 'status-creating');
                        hideContextMenu();
                    }});
                }}
                
                if (deleteBaselineBtn) {{
                    deleteBaselineBtn.addEventListener('click', function() {{
                        showStatus('🗑️ Funcionalidade em desenvolvimento...', 'status-creating');
                        hideContextMenu();
                    }});
                }}
                
                // Fechar menu ao clicar fora
                document.addEventListener('click', function(e) {{
                    if (contextMenu && !contextMenu.contains(e.target) && e.target !== ganttArea) {{
                        hideContextMenu();
                    }}
                }});
                
                // Fechar menu com ESC
                document.addEventListener('keydown', function(e) {{
                    if (e.key === 'Escape') {{
                        hideContextMenu();
                    }}
                }});
                
                // Prevenir menu de contexto padrão na área do Gantt
                document.addEventListener('contextmenu', function(e) {{
                    if (e.target.id === 'gantt-chart-area' || e.target.closest('#gantt-chart-area')) {{
                        e.preventDefault();
                    }}
                }}, true);
                
                // Atualizar interface quando linha de base for criada
                document.addEventListener('baselineCreated', function() {{
                    console.log('Linha de base criada - interface pode ser atualizada');
                    // Aqui você pode adicionar lógica para atualizar elementos específicos
                }});
                </script>
                """
                
                # Usar html() para injetar o componente completo
                st.components.v1.html(context_menu_html, height=200)

        # --- FIM DO NOVO LAYOUT ---
        # Mantemos a chamada a filter_dataframe, mas com os valores padrão para EMP, GRUPO e SETOR
        df_filtered = filter_dataframe(df_data, selected_ugb, selected_emp, selected_grupo, selected_setor)

        # 2. Determinar o modo de visualização (agora baseado no st.session_state)
        is_consolidated_view = st.session_state.consolidated_view

        # 3. NOVO: Se for visão consolidada, AINDA filtramos pela etapa aqui.
        if is_consolidated_view and not df_filtered.empty:
            sigla_selecionada = nome_completo_para_sigla.get(selected_etapa_nome, selected_etapa_nome)
            df_filtered = df_filtered[df_filtered["Etapa"] == sigla_selecionada]
        df_para_exibir = df_filtered.copy()
        # Criar a lista de ordenação de empreendimentos (necessário para ambas as tabelas)
        empreendimentos_ordenados_por_meta = criar_ordenacao_empreendimentos(df_data)
        # Copiar o dataframe filtrado para ser usado nas tabelas
        df_detalhes = df_para_exibir.copy()
        # A lógica de pulmão foi removida da sidebar, então não é mais aplicada aqui.
        
        # CONTROLE DE ACESSO PARA ABA "LINHAS DE BASE"
        def verificar_acesso_baseline():
            """Verifica se o usuario tem acesso a aba Linhas de Base"""
            try:
                # Obter lista de emails autorizados do secrets
                authorized_emails = st.secrets.get('baseline_access', {}).get('authorized_emails', [])
                
                # Obter email do usuario logado
                user_email = st.session_state.get('user_email', '').strip().lower()
                
                # Verificar se o email esta na lista (case-insensitive)
                authorized_emails_lower = [email.strip().lower() for email in authorized_emails]
                
                return user_email in authorized_emails_lower
            except Exception as e:
                # Se houver erro ao carregar secrets, nao mostra a aba
                print(f"Erro ao verificar acesso baseline: {e}")
                return False
        
        # Criar tabs baseado no acesso do usuário
        has_baseline_access = verificar_acesso_baseline()
        
        if has_baseline_access:
            # Usuário autorizado - mostra todas as 3 tabs
            tab1, tab2, tab3 = st.tabs(["Gráfico de Gantt", "Tabelão Horizontal", "Linhas de Base"])
        else:
            # Usuário não autorizado - mostra apenas 2 tabs
            tab1, tab2 = st.tabs(["Gráfico de Gantt", "Tabelão Horizontal"])
            tab3 = None  # Define como None para evitar erros

    with tab1:
        st.subheader("Gantt Comparativo")
        
        # Processar mudança de baseline PRIMEIRO
        process_baseline_change()
        
        
        if df_para_exibir.empty:
            st.warning("⚠️ Nenhum dado encontrado com os filtros aplicados.")
        else:
            df_para_gantt = filter_dataframe(df_data, selected_ugb, selected_emp, selected_grupo, selected_setor)
            
            # gerar_gantt now reads baseline from session state internally
            gerar_gantt(
                df_para_gantt.copy(),
                tipo_visualizacao, 
                filtrar_nao_concluidas,
                df_data, 
                pulmao_status, 
                pulmao_meses,
                selected_etapa_nome,
                selected_setor_nome  # NOVO: Parâmetro para visualização por setor
            )
            # Botão para limpar baseline (se houver uma ativa)
                                                                                                                                                      
            st.markdown('<div id="visao-detalhada"></div>', unsafe_allow_html=True)
            st.subheader("Visão Detalhada por Empreendimento")

            if df_detalhes.empty: # Verifique df_detalhes
                st.warning("⚠️ Nenhum dado encontrado com os filtros aplicados.")
                pass
            else:
                hoje = pd.Timestamp.now().normalize()

                for col in ['Inicio_Prevista', 'Termino_Prevista', 'Inicio_Real', 'Termino_Real']:
                    if col in df_detalhes.columns:
                        df_detalhes[col] = pd.to_datetime(df_detalhes[col], errors='coerce')

                df_agregado = df_detalhes.groupby(['Empreendimento', 'Etapa']).agg(
                    Inicio_Prevista=('Inicio_Prevista', 'min'),
                    Termino_Prevista=('Termino_Prevista', 'max'),
                    Inicio_Real=('Inicio_Real', 'min'),
                    Termino_Real=('Termino_Real', 'max'),
                    Percentual_Concluido=('% concluído', 'max') if '% concluído' in df_detalhes.columns else ('% concluído', lambda x: 0)
                ).reset_index()

                if '% concluído' in df_detalhes.columns and not df_agregado.empty and (df_agregado['Percentual_Concluido'].fillna(0).max() <= 1):
                    df_agregado['Percentual_Concluido'] *= 100

                df_agregado['Var. Term'] = df_agregado.apply(
                    lambda row: calculate_business_days(row['Termino_Prevista'], row['Termino_Real']), axis=1
                )
                
                df_agregado['ordem_empreendimento'] = pd.Categorical(
                    df_agregado['Empreendimento'],
                    categories=empreendimentos_ordenados_por_meta,
                    ordered=True
                )
                
                # 1. Mapear a etapa para sua ordem global (agora incluindo subetapas)
                def get_global_order_linear(etapa):
                    try:
                        return ORDEM_ETAPAS_GLOBAL.index(etapa)
                    except ValueError:
                        return len(ORDEM_ETAPAS_GLOBAL) # Coloca no final se não for encontrada

                df_agregado['Etapa_Ordem'] = df_agregado['Etapa'].apply(get_global_order_linear)
                
                # 2. Ordenar: Empreendimento, Ordem da Etapa (linear)
                df_ordenado = df_agregado.sort_values(by=['ordem_empreendimento', 'Etapa_Ordem'])

                st.write("---")

                etapas_unicas = df_ordenado['Etapa'].unique()
                usar_layout_horizontal = len(etapas_unicas) == 1

                tabela_final_lista = []
                
                if usar_layout_horizontal:
                    tabela_para_processar = df_ordenado.copy()
                    tabela_para_processar['Etapa'] = tabela_para_processar['Etapa'].map(sigla_para_nome_completo)
                    tabela_final_lista.append(tabela_para_processar)
                else:
                    for _, grupo in df_ordenado.groupby('ordem_empreendimento', sort=False):
                        if grupo.empty:
                            continue

                        empreendimento = grupo['Empreendimento'].iloc[0]
                        
                        percentual_medio = grupo['Percentual_Concluido'].mean()
                        
                        cabecalho = pd.DataFrame([{
                            'Hierarquia': f'📂 {empreendimento}',
                            'Inicio_Prevista': grupo['Inicio_Prevista'].min(),
                            'Termino_Prevista': grupo['Termino_Prevista'].max(),
                            'Inicio_Real': grupo['Inicio_Real'].min(),
                            'Termino_Real': grupo['Termino_Real'].max(),
                            'Var. Term': grupo['Var. Term'].mean(),
                            'Percentual_Concluido': percentual_medio
                        }])
                        tabela_final_lista.append(cabecalho)

                        grupo_formatado = grupo.copy()
                        grupo_formatado['Hierarquia'] = ' &nbsp; &nbsp; ' + grupo_formatado['Etapa'].map(sigla_para_nome_completo)
                        tabela_final_lista.append(grupo_formatado)

                if not tabela_final_lista:
                    st.info("ℹ️ Nenhum dado para exibir na tabela detalhada com os filtros atuais")
                    pass
                else:
                    tabela_final = pd.concat(tabela_final_lista, ignore_index=True)

                    def aplicar_estilo(df_para_estilo, layout_horizontal):
                        if df_para_estilo.empty:
                            return df_para_estilo.style

                        def estilo_linha(row):
                            style = [''] * len(row)
                            
                            if not layout_horizontal and 'Empreendimento / Etapa' in row.index and str(row['Empreendimento / Etapa']).startswith('📂'):
                                style = ['font-weight: 500; color: #000000; background-color: #F0F2F6; border-left: 4px solid #000000; padding-left: 10px;'] * len(row)
                                for i in range(1, len(style)):
                                    style[i] = "background-color: #F0F2F6;"
                                return style
                            
                            percentual = row.get('% Concluído', 0)
                            if isinstance(percentual, str) and '%' in percentual:
                                try: percentual = int(percentual.replace('%', ''))
                                except: percentual = 0

                            termino_real, termino_previsto = pd.to_datetime(row.get("Término Real"), errors='coerce'), pd.to_datetime(row.get("Término Prev."), errors='coerce')
                            cor = "#000000"
                            if percentual == 100:
                                if pd.notna(termino_real) and pd.notna(termino_previsto):
                                    if termino_real < termino_previsto: cor = "#2EAF5B"
                                    elif termino_real > termino_previsto: cor = "#C30202"
                            elif pd.notna(termino_previsto) and (termino_previsto < pd.Timestamp.now()):
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

                    colunas_rename = {
                        'Inicio_Prevista': 'Início Prev.', 'Termino_Prevista': 'Término Prev.',
                        'Inicio_Real': 'Início Real', 'Termino_Real': 'Término Real',
                        'Percentual_Concluido': '% Concluído'
                    }
                    
                    if usar_layout_horizontal:
                        colunas_rename['Empreendimento'] = 'Empreendimento'
                        colunas_rename['Etapa'] = 'Etapa'
                        colunas_para_exibir = ['Empreendimento', 'Etapa', '% Concluído', 'Início Prev.', 'Término Prev.', 'Início Real', 'Término Real', 'Var. Term']
                    else:
                        colunas_rename['Hierarquia'] = 'Empreendimento / Etapa'
                        colunas_para_exibir = ['Empreendimento / Etapa', '% Concluído', 'Início Prev.', 'Término Prev.', 'Início Real', 'Término Real', 'Var. Term']

                    tabela_para_exibir = tabela_final.rename(columns=colunas_rename)
                    
                    tabela_estilizada = aplicar_estilo(tabela_para_exibir[colunas_para_exibir], layout_horizontal=usar_layout_horizontal)
                    
                    st.markdown(tabela_estilizada.to_html(), unsafe_allow_html=True)

    with tab2:
            st.subheader("Tabelão Horizontal")
            
            if df_detalhes.empty: # Usando df_detalhes
                st.warning("⚠️ Nenhum dado encontrado com os filtros aplicados.")
                pass
            else:
                hoje = pd.Timestamp.now().normalize()

                df_detalhes_tabelao = df_detalhes.rename(columns={
                    'Termino_prevista': 'Termino_Prevista',
                    'Termino_real': 'Termino_Real'
                })
                
                for col in ['Inicio_Prevista', 'Termino_Prevista', 'Inicio_Real', 'Termino_Real']:
                    if col in df_detalhes_tabelao.columns:
                        df_detalhes_tabelao[col] = df_detalhes_tabelao[col].replace('-', pd.NA)
                        df_detalhes_tabelao[col] = pd.to_datetime(df_detalhes_tabelao[col], errors='coerce')

                df_detalhes_tabelao['Conclusao_Valida'] = False
                if '% concluído' in df_detalhes_tabelao.columns:
                    mask = (
                        (df_detalhes_tabelao['% concluído'] == 100) &
                        (df_detalhes_tabelao['Termino_Real'].notna()) &
                        ((df_detalhes_tabelao['Termino_Prevista'].isna()) |
                        (df_detalhes_tabelao['Termino_Real'] <= df_detalhes_tabelao['Termino_Prevista']))
                    )
                    df_detalhes_tabelao.loc[mask, 'Conclusao_Valida'] = True

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

                # 1. Mapear a etapa para sua ordem global (agora incluindo subetapas)
                def get_global_order_linear_tabelao(etapa):
                    try:
                        return ORDEM_ETAPAS_GLOBAL.index(etapa)
                    except ValueError:
                        return len(ORDEM_ETAPAS_GLOBAL) # Coloca no final se não for encontrada

                df_detalhes_tabelao['Etapa_Ordem'] = df_detalhes_tabelao['Etapa'].apply(get_global_order_linear_tabelao)

                # Lógica para anular datas previstas de subetapas
                subetapas_list = list(ETAPA_PAI_POR_SUBETAPA.keys())
                
                # Cria uma máscara para identificar as linhas que são subetapas
                mask_subetapa = df_detalhes_tabelao['Etapa'].isin(subetapas_list)
                
                # Anula as datas previstas (Inicio_Prevista e Termino_Prevista) para as subetapas
                df_detalhes_tabelao.loc[mask_subetapa, 'Inicio_Prevista'] = pd.NaT
                df_detalhes_tabelao.loc[mask_subetapa, 'Termino_Prevista'] = pd.NaT
                
                if classificar_por in ['Data de Início Previsto (Mais antiga)', 'Data de Término Previsto (Mais recente)']:
                    coluna_data = 'Inicio_Prevista' if 'Início' in classificar_por else 'Termino_Prevista'
                    
                    df_detalhes_ordenado = df_detalhes_tabelao.sort_values(
                        by=[coluna_data, 'UGB', 'Empreendimento', 'Etapa'],
                        ascending=[ordem == 'Crescente', True, True, True],
                        na_position='last'
                    )
                    
                    ordem_ugb_emp = df_detalhes_ordenado.groupby(['UGB', 'Empreendimento']).first().reset_index()
                    ordem_ugb_emp = ordem_ugb_emp.sort_values(
                        by=coluna_data,
                        ascending=(ordem == 'Crescente'),
                        na_position='last'
                    )
                    ordem_ugb_emp['ordem_index'] = range(len(ordem_ugb_emp))
                    
                    df_detalhes_tabelao = df_detalhes_tabelao.merge(
                        ordem_ugb_emp[['UGB', 'Empreendimento', 'ordem_index']],
                        on=['UGB', 'Empreendimento'],
                        how='left'
                    )
                
                agg_dict = {
                    'Inicio_Prevista': ('Inicio_Prevista', 'min'),
                    'Termino_Prevista': ('Termino_Prevista', 'max'),
                    'Inicio_Real': ('Inicio_Real', 'min'),
                    'Termino_Real': ('Termino_Real', 'max'),
                    'Concluido_Valido': ('Conclusao_Valida', 'any')
                }
                
                if '% concluído' in df_detalhes_tabelao.columns:
                    agg_dict['Percentual_Concluido'] = ('% concluído', 'max')
                    if not df_detalhes_tabelao.empty and (df_detalhes_tabelao['% concluído'].fillna(0).max() <= 1):
                        df_detalhes_tabelao['% concluído'] *= 100

                if 'ordem_index' in df_detalhes_tabelao.columns:
                    agg_dict['ordem_index'] = ('ordem_index', 'first')

                df_agregado = df_detalhes_tabelao.groupby(['UGB', 'Empreendimento', 'Etapa']).agg(**agg_dict).reset_index()
                
                df_agregado['Var. Term'] = df_agregado.apply(lambda row: calculate_business_days(row['Termino_Prevista'], row['Termino_Real']), axis=1)

                # Variável que estava faltando, definida a partir da ORDEM_ETAPAS_GLOBAL
                ordem_etapas_completas = ORDEM_ETAPAS_GLOBAL

                df_agregado['Etapa_Ordem'] = df_agregado['Etapa'].apply(
                    lambda x: ordem_etapas_completas.index(x) if x in ordem_etapas_completas else len(ordem_etapas_completas)
                )

                if classificar_por in ['Data de Início Previsto (Mais antiga)', 'Data de Término Previsto (Mais recente)']:
                    df_ordenado = df_agregado.sort_values(
                        by=['ordem_index', 'UGB', 'Empreendimento', 'Etapa_Ordem'],
                        ascending=[True, True, True, True]
                    )
                else:
                    df_ordenado = df_agregado.sort_values(
                        by=opcoes_classificacao[classificar_por],
                        ascending=(ordem == 'Crescente')
                    )
                
                st.write("---")

                df_pivot = df_ordenado.pivot_table(
                    index=['UGB', 'Empreendimento'],
                    columns='Etapa',
                    values=['Inicio_Prevista', 'Termino_Prevista', 'Inicio_Real', 'Termino_Real', 'Var. Term'],
                    aggfunc='first'
                )

                etapas_existentes_no_pivot = df_pivot.columns.get_level_values(1).unique()
                colunas_ordenadas = []
                
                for etapa in ordem_etapas_completas:
                    if etapa in etapas_existentes_no_pivot:
                        for tipo in ['Inicio_Prevista', 'Termino_Prevista', 'Inicio_Real', 'Termino_Real', 'Var. Term']:
                            if (tipo, etapa) in df_pivot.columns:
                                colunas_ordenadas.append((tipo, etapa))
                
                df_final = df_pivot[colunas_ordenadas].reset_index()

                if classificar_por in ['Data de Início Previsto (Mais antiga)', 'Data de Término Previsto (Mais recente)']:
                    ordem_linhas_final = df_ordenado[['UGB', 'Empreendimento']].drop_duplicates().reset_index(drop=True)
                    
                    df_final = df_final.set_index(['UGB', 'Empreendimento'])
                    df_final = df_final.reindex(pd.MultiIndex.from_frame(ordem_linhas_final))
                    df_final = df_final.reset_index()

                novos_nomes = []
                for col in df_final.columns:
                    if col[0] in ['UGB', 'Empreendimento']:
                        novos_nomes.append((col[0], ''))
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

                def formatar_valor(valor, tipo):
                    if pd.isna(valor):
                        return "-"
                    if tipo == 'data':
                        return valor.strftime("%d/%m/%Y")
                    if tipo == 'variacao':
                        return f"{'▼' if valor > 0 else '▲'} {abs(int(valor))} dias"
                    return str(valor)

                def determinar_cor(row, col_tuple):
                    if len(col_tuple) == 2 and (col_tuple[1] in ['Início Real', 'Término Real']):
                        etapa_nome_completo = col_tuple[0]
                        etapa_sigla = nome_completo_para_sigla.get(etapa_nome_completo)
                        
                        if etapa_sigla:
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
                                
                                if percentual == 100:
                                    if pd.notna(termino_real) and pd.notna(termino_previsto):
                                        if termino_real < termino_previsto:
                                            return "color: #2EAF5B; font-weight: bold;"
                                        elif termino_real > termino_previsto:
                                            return "color: #C30202; font-weight: bold;"
                                elif pd.notna(termino_real) and (termino_real < hoje):
                                    return "color: #A38408; font-weight: bold;"
                    
                    return ""

                df_formatado = df_final.copy()
                for col_tuple in df_formatado.columns:
                    if len(col_tuple) == 2 and col_tuple[1] != '':
                        if any(x in col_tuple[1] for x in ["Início Prev.", "Término Prev.", "Início Real", "Término Real"]):
                            df_formatado[col_tuple] = df_formatado[col_tuple].apply(lambda x: formatar_valor(x, "data"))
                        elif "VarTerm" in col_tuple[1]:
                            df_formatado[col_tuple] = df_formatado[col_tuple].apply(lambda x: formatar_valor(x, "variacao"))

                def aplicar_estilos(df):
                    styles = pd.DataFrame('', index=df.index, columns=df.columns)
                    
                    for i, row in df.iterrows():
                        cor_fundo = "#fbfbfb" if i % 2 == 0 else '#ffffff'
                        
                        for col_tuple in df.columns:
                            cell_style = f"background-color: {cor_fundo};"
                            
                            if len(col_tuple) == 2 and col_tuple[1] != '':
                                if row[col_tuple] == '-':
                                    cell_style += ' color: #999999; font-style: italic;'
                                else:
                                    if col_tuple[1] in ['Início Real', 'Término Real']:
                                        row_dict = {('UGB', ''): row[('UGB', '')],
                                                    ('Empreendimento', ''): row[('Empreendimento', '')]}
                                        cor_condicional = determinar_cor(row_dict, col_tuple)
                                        if cor_condicional:
                                            cell_style += f' {cor_condicional}'
                                    
                                    elif 'VarTerm' in col_tuple[1]:
                                        if '▲' in str(row[col_tuple]):
                                            cell_style += ' color: #e74c3c; font-weight: 600;'
                                        elif '▼' in str(row[col_tuple]):
                                            cell_style += ' color: #2ecc71; font-weight: 600;'
                            
                            styles.at[i, col_tuple] = cell_style
                    
                    return styles

                header_styles = [
                    {'selector': 'th.level0', 'props': [('font-size', '12px'), ('font-weight', 'bold'), ('background-color', "#6c6d6d"), ('border-bottom', '2px solid #ddd'), ('text-align', 'center'), ('white-space', 'nowrap')]},
                    {'selector': 'th.level1', 'props': [('font-size', '11px'), ('font-weight', 'normal'), ('background-color', '#f8f9fa'), ('text-align', 'center'), ('white-space', 'nowrap')]},
                    {'selector': 'td', 'props': [('font-size', '12px'), ('text-align', 'center'), ('padding', '5px 8px'), ('border', '1px solid #f0f0f0')]},
                    {'selector': 'th.col_heading.level0', 'props': [('font-size', '12px'), ('font-weight', 'bold'), ('background-color', '#6c6d6d'), ('text-align', 'center')]}
                ]

                for i, etapa in enumerate(ordem_etapas_completas):
                    if i > 0:
                        etapa_nome = sigla_para_nome_completo.get(etapa, etapa)
                        col_idx = next((idx for idx, col in enumerate(df_final.columns) if col[0] == etapa_nome), None)
                        if col_idx:
                            header_styles.append({'selector': f'th:nth-child({col_idx+1})', 'props': [('border-left', '2px solid #ddd')]})
                            header_styles.append({'selector': f'td:nth-child({col_idx+1})', 'props': [('border-left', '2px solid #ddd')]})

                styled_df = df_formatado.style.apply(aplicar_estilos, axis=None)
                styled_df = styled_df.set_table_styles(header_styles)

                st.dataframe(
                    styled_df,
                    height=min(35 * len(df_final) + 40, 600),
                    hide_index=True,
                    use_container_width=True
                )
    

    # Tab3 - Linhas de Base (apenas para usuarios autorizados)
    if tab3 is not None:
        with tab3:
            st.title("Gerenciamento de Linhas de Base")
            
            # Seleção de empreendimento
            empreendimentos_baseline = df_data['Empreendimento'].unique().tolist() if not df_data.empty else []
            
            if not empreendimentos_baseline:
                st.warning("Nenhum empreendimento disponível")
            else:
                selected_empreendimento_baseline = st.selectbox(
                    "Selecione o Empreendimento",
                    empreendimentos_baseline,
                    key="baseline_emp_tab3"
                )
                
                st.divider()
                
                # === CRIAR BASELINE ===
                st.subheader("📝 Criar Nova Baseline")
                
                user_email = st.session_state.get('user_email', '')
                
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**Empreendimento:** {selected_empreendimento_baseline}")
                    if user_email:
                        st.write(f"**Responsável:** {user_email}")
                
                with col2:
                    if st.button("Criar Baseline", use_container_width=True, type="primary", key="create_baseline_main"):
                        try:
                            version_name = take_gantt_baseline(
                                df_data, 
                                selected_empreendimento_baseline, 
                                tipo_visualizacao,
                                created_by=user_email if user_email else "usuario"
                            )
                            st.success(f"✅ Baseline {version_name} criada!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro: {e}")
                
                st.divider()
                
                
                # === LISTA DE BASELINES ===
                st.subheader("📋 Baselines Existentes")
                
                baselines = load_baselines()
                unsent_baselines = st.session_state.get('unsent_baselines', {})
                emp_unsent = unsent_baselines.get(selected_empreendimento_baseline, [])
                emp_baselines = baselines.get(selected_empreendimento_baseline, {})
                
                if emp_baselines:
                    for i, version_name in enumerate(sorted(emp_baselines.keys(), reverse=True)):
                        is_unsent = version_name in emp_unsent
                        baseline_info = emp_baselines[version_name]
                        data_criacao = baseline_info.get('date', 'N/A')
                        baseline_data_info = baseline_info.get('data', {})
                        created_by = baseline_data_info.get('created_by', 'N/A')
                        
                        col1, col2, col3 = st.columns([4, 2, 1])
                        
                        with col1:
                            status = "🟡 Pendente" if is_unsent else "🟢 Enviada"
                            st.write(f"**{version_name}** - {status}")
                            st.caption(f"Criado por: {created_by} | Data: {data_criacao}")
                        
                        with col2:
                            st.write("")  # Espaçamento
                        
                        with col3:
                            if st.button("Excluir", key=f"del_{i}", use_container_width=True):
                                if delete_baseline(selected_empreendimento_baseline, version_name):
                                    if 'unsent_baselines' in st.session_state:
                                        if version_name in st.session_state.unsent_baselines.get(selected_empreendimento_baseline, []):
                                            st.session_state.unsent_baselines[selected_empreendimento_baseline].remove(version_name)
                                    st.success("Excluída")
                                    st.rerun()
                                else:
                                    st.error("Erro ao excluir")
                        
                        if i < len(emp_baselines) - 1:
                            st.divider()
                    
                    # Estatísticas simples
                    st.divider()
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total", len(emp_baselines))
                    with col2:
                        st.metric("Pendentes", len(emp_unsent))
                    with col3:
                        st.metric("Enviadas", len(emp_baselines) - len(emp_unsent))
                else:
                    st.info("Nenhuma baseline criada ainda")

def verificar_implementacao_baseline():
    """Verifica se todas as funcoes de baseline foram implementadas"""
    funcoes_necessarias = [
            'get_db_connection', 'create_baselines_table', 'load_baselines',
            'save_baseline', 'delete_baseline', 'take_gantt_baseline', 'send_to_aws'
    ]
    
    for func in funcoes_necessarias:
            if func not in globals():
                st.error(f"❌ Função {func} não encontrada na implementação")
            return False
    
    return True

# No final do arquivo, antes do if __name__:
if __name__ == "__main__":
    # Verificar implementação (pode remover depois)
    if 'df_data' in globals() and not df_data.empty:
            verificar_implementacao_baseline()

    else:
            st.error("❌ Não foi possível carregar ou gerar os dados.")
