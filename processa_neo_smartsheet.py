import pandas as pd
import smartsheet
import os
from dotenv import load_dotenv
import sys
from datetime import datetime 
import numpy as np
import re

# Configurações
SHEET_NAME = "ACOMPANHAMENTOS NEOERNERGIA"
OUTPUT_CSV = "Dados Reais Tratados e Ordenados.csv"

def carregar_configuracao():
    """Carrega as configurações e verifica o ambiente"""
    try:
        if not os.path.exists('.env'):
            raise FileNotFoundError("Arquivo .env não encontrado")
        
        load_dotenv()
        token = os.getenv("SMARTSHEET_ACCESS_TOKEN")
        
        # 2. Se não achou, tenta carregar dos segredos do Streamlit
        if not token:
            try:
                import streamlit as st
                
                # Debug: Listar chaves disponíveis para ajudar no diagnóstico
                try:
                    available_keys = list(st.secrets.keys())
                    print(f"DEBUG: Chaves encontradas em st.secrets: {available_keys}")
                except:
                    print("DEBUG: Não foi possível listar chaves de st.secrets")

                # Verifica se existe nos secrets (suporta acesso direto)
                if "SMARTSHEET_ACCESS_TOKEN" in st.secrets:
                    token = st.secrets["SMARTSHEET_ACCESS_TOKEN"]
                    print("INFO: Token carregado via Streamlit Secrets (raiz).")
                
                # Fallback: Tenta procurar dentro de seções comuns (ex: [smartsheet])
                elif "smartsheet" in st.secrets and "access_token" in st.secrets["smartsheet"]:
                    token = st.secrets["smartsheet"]["access_token"]
                    print("INFO: Token carregado via Streamlit Secrets (seção [smartsheet]).")
                    
                elif "env" in st.secrets and "SMARTSHEET_ACCESS_TOKEN" in st.secrets["env"]:
                    token = st.secrets["env"]["SMARTSHEET_ACCESS_TOKEN"]
                    print("INFO: Token carregado via Streamlit Secrets (seção [env]).")
                    
            except Exception as e:
                # Se não estiver rodando no Streamlit ou secrets não configurados
                print(f"AVISO: Falha ao tentar ler Streamlit Secrets: {e}")
                pass
                
        if token:
            return token
        
        print("\nERRO DE CONFIGURAÇÃO: Token 'SMARTSHEET_ACCESS_TOKEN' não encontrado nem no .env nem no st.secrets.")
        return None
    except Exception as e:
        print(f"\nERRO DE CONFIGURAÇÃO: {str(e)}")
        print("\nPor favor, crie um arquivo .env na mesma pasta do script com:")
        print("SMARTSHEET_ACCESS_TOKEN=seu_token_aqui\n")
        return None

def setup_smartsheet_client(token):
    """Configura o cliente Smartsheet"""
    try:
        client = smartsheet.Smartsheet(token)
        client.errors_as_exceptions(True)
        return client
    except Exception as e:
        print(f"\nERRO: Falha ao configurar cliente Smartsheet - {str(e)}")
        return None

def get_sheet_id(client, sheet_name):
    """Obtém o ID da planilha"""
    try:
        print(f"\nBuscando planilha '{sheet_name}'...")
        response = client.Sheets.list_sheets(include_all=True)
        
        for sheet in response.data:
            if sheet.name == sheet_name:
                print(f"Planilha encontrada (ID: {sheet.id})")
                return sheet.id
        
        print(f"\nERRO: Planilha '{sheet_name}' não encontrada")
        print("Planilhas disponíveis:")
        for sheet in response.data[:5]:
            print(f" - {sheet.name} (ID: {sheet.id})")
        if len(response.data) > 5:
            print(f" - ... e mais {len(response.data) - 5} planilhas")
        return None
        
    except smartsheet.exceptions.ApiError as api_error:
        print(f"\nERRO DE API: {api_error.message}")
        return None
    except Exception as e:
        print(f"\nErro inesperado ao buscar planilhas: {str(e)}")
        return None

def get_sheet_data(client, sheet_id):
    """Obtém os dados da planilha"""
    try:
        print("\nObtendo dados da planilha...")
        sheet = client.Sheets.get_sheet(
            sheet_id,
            include=['format', 'discussions', 'attachments', 'columnType'],
            page_size=5000
        )
        
        column_map = {column.id: column.title for column in sheet.columns}
        
        rows = []
        for row in sheet.rows:
            row_data = {}
            for cell in row.cells:
                if cell.column_id in column_map:
                    column_name = column_map[cell.column_id]
                    row_data[column_name] = cell.value
            rows.append(row_data)
        
        df = pd.DataFrame(rows)
        print(f"✅ Dados obtidos ({len(df)} linhas, {len(df.columns)} colunas)")
        
        # Verificação inicial dos dados
        print("\n🔍 VERIFICAÇÃO INICIAL DOS DADOS:")
        print(f"Valores únicos na coluna 'Empreendimento': {df['Empreendimento'].nunique() if 'Empreendimento' in df.columns else 'Coluna não encontrada'}")
        
        if 'FASE' in df.columns:
            print(f"Valores únicos na coluna 'FASE': {df['FASE'].nunique()}")
            print("Top 10 valores em 'FASE':")
            print(df['FASE'].value_counts().head(10))
        
        return df
    
    except Exception as e:
        print(f"\n❌ Falha ao obter dados: {str(e)}")
        return pd.DataFrame()

def filtrar_linhas_invalidas(df):
    """
    Filtra linhas que contêm valores 'UNKNOWN' ou outros padrões inválidos
    em colunas críticas como Empreendimento, FASE, SERVIÇO, etc.
    """
    print("\n🚫 FILTRANDO LINHAS COM VALORES INVÁLIDOS...")
    
    linhas_antes = len(df)
    
    if df.empty:
        print("⚠️ Nenhum dado para filtrar")
        return df
    
    # Padrões de valores inválidos para remover (mais abrangente)
    padroes_invalidos = [
        r'^unknown$', r'^none$', r'^nan$', r'^nat$', r'^\s*$',
        r'base', r'teste', r'exemplo', r'^$',
        r'j\.ser.*2', r'lar.*f1', r'sviii.*f2', r'qdr\.g', r'ba.*4f1'
    ]
    
    # Colunas críticas para verificar
    colunas_criticas = ['Empreendimento', 'FASE', 'Nome da tarefa', 'EMP', 'UGB']
    colunas_existentes = [col for col in colunas_criticas if col in df.columns]
    
    print(f"Colunas críticas para verificação: {colunas_existentes}")
    
    if not colunas_existentes:
        print("⚠️ Nenhuma coluna crítica encontrada para verificação")
        return df
    
    # Criar máscara para identificar linhas a serem removidas
    mascara_remover = pd.Series([False] * len(df), index=df.index)
    
    for coluna in colunas_existentes:
        if coluna in df.columns:
            # Converter para string para verificação segura e em minúsculas
            coluna_str = df[coluna].astype(str).str.strip().str.lower()
            
            # Verificar valores nulos ou vazios primeiro
            mascara_nulos = coluna_str.isna() | (coluna_str == '') | (coluna_str == 'nan')
            
            # Criar máscara para valores inválidos nesta coluna
            mascara_invalida_coluna = mascara_nulos.copy()
            for padrao in padroes_invalidos:
                mascara_invalida_coluna = mascara_invalida_coluna | coluna_str.str.contains(padrao, regex=True, na=True)
            
            # Verificar explicitamente por "unknown" (case insensitive)
            mascara_unknown = coluna_str.str.contains('unknown', case=False, na=True)
            mascara_invalida_coluna = mascara_invalida_coluna | mascara_unknown
            
            # Contar inválidos
            invalidos_count = mascara_invalida_coluna.sum()
            if invalidos_count > 0:
                print(f"   → Coluna '{coluna}': {invalidos_count} valores inválidos encontrados")
                # Mostrar exemplos dos valores problemáticos
                valores_problematicos = df.loc[mascara_invalida_coluna, coluna].unique()[:5]
                print(f"      Valores problemáticos: {valores_problematicos}")
            
            # Atualizar máscara geral (remove a linha se QUALQUER coluna crítica for inválida)
            mascara_remover = mascara_remover | mascara_invalida_coluna
    
    # Aplicar filtro para manter apenas as linhas que NÃO estão na máscara de remoção
    df_filtrado = df[~mascara_remover].copy()
    
    linhas_removidas = linhas_antes - len(df_filtrado)
    print(f"   → Linhas removidas: {linhas_removidas}")
    print(f"   → Linhas restantes: {len(df_filtrado)}")
    
    return df_filtrado

def process_data(df):
    """Processa e limpa os dados com foco em remover valores 'UNKNOWN'"""
    if df.empty:
        print("⚠️ Aviso: Nenhum dado recebido para processamento.")
        return df

    try:
        original_rows = len(df)
        print(f"📊 Iniciando processamento de {original_rows} linhas...")

        # 1. Remover as primeiras 915 linhas (se aplicável)
        if len(df) > 915:
            print("📉 Removendo primeiras 915 linhas...")
            df = df.iloc[915:].reset_index(drop=True)
            print(f"   → Linhas após remoção: {len(df)}")
        else:
            print("⚠️ Aviso: Planilha tem menos de 915 linhas, pulando esta etapa.")

        # 2. FILTRAGEM PRINCIPAL - Remover linhas com valores 'UNKNOWN' e outros inválidos
        df = filtrar_linhas_invalidas(df)
        
        if df.empty:
            print("❌ Todas as linhas foram removidas durante a filtragem!")
            return df

        # 3. Remover colunas desnecessárias
        colunas_remover = [
            "SERVIÇO","RowNumber", "CATEGORIA", "Destaque", "Atualizar", "Antecessores", 
            "Duração", "Variação (LB-Termino)", "Início LB", "Término LB", 
            "Dur LB", "Atribuído a", "PRAZO CARTAS"
        ]
        colunas_existentes = [col for col in colunas_remover if col in df.columns]
        if colunas_existentes:
            df = df.drop(columns=colunas_existentes, errors='ignore')
            print(f"🗑️ Colunas removidas: {colunas_existentes}")

        # 4. Limpeza adicional de valores nulos
        print("\n🧹 Limpeza final de valores nulos...")
        colunas_para_verificar = ['Empreendimento', 'FASE', 'SERVIÇO']
        colunas_existentes = [col for col in colunas_para_verificar if col in df.columns]
        
        if colunas_existentes:
            linhas_antes = len(df)
            df = df.dropna(subset=colunas_existentes, how='all')
            removidas = linhas_antes - len(df)
            if removidas > 0:
                print(f"   → {removidas} linhas removidas por valores nulos em colunas críticas")

        # 5. Converter tipos de dados
        print("\n🔄 Convertendo tipos de dados...")
        date_columns = ["Data de Fim", "Data de Início"]
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)

        if "% concluído" in df.columns:
            df["% concluído"] = pd.to_numeric(
                df["% concluído"].astype(str).str.replace('%', '').str.replace(',', '.'), 
                errors='coerce'
            ) / 100
            df["% concluído"].fillna(0, inplace=True)

        # 6. VERIFICAÇÃO FINAL - Garantir que não há mais 'UNKNOWN'
        print("\n🔍 VERIFICAÇÃO FINAL - VALORES 'UNKNOWN':")
        colunas_para_verificar = ['Empreendimento', 'FASE', 'SERVIÇO', 'Nome da tarefa']
        
        unknown_total = 0
        for coluna in colunas_para_verificar:
            if coluna in df.columns:
                # Verificação mais robusta para unknown
                unknown_mask = (
                    df[coluna].astype(str).str.strip().str.lower()
                    .str.contains('unknown', case=False, na=False)
                )
                unknown_count = unknown_mask.sum()
                unknown_total += unknown_count
                
                print(f"   → Coluna '{coluna}': {unknown_count} valores 'unknown' encontrados")
                
                if unknown_count > 0:
                    # Mostrar exemplos dos valores problemáticos
                    problematicos = df[unknown_mask]
                    print(f"      Exemplos: {problematicos[coluna].unique()[:3]}")
        
        if unknown_total > 0:
            print(f"⚠️  ATENÇÃO: Ainda existem {unknown_total} valores 'unknown' no dataset!")
        else:
            print("✅ Nenhum valor 'unknown' encontrado na verificação final!")

        # 7. Análise dos dados resultantes
        print(f"\n✅ PROCESSAMENTO CONCLUÍDO: {len(df)}/{original_rows} linhas mantidas.")
        
        if "Empreendimento" in df.columns:
            print("\n📊 DISTRIBUIÇÃO DOS EMPREENDIMENTOS:")
            dist = df["Empreendimento"].value_counts()
            for emp, count in dist.items():
                print(f"   - '{emp}': {count} linhas")
        
        if "FASE" in df.columns:
            print("\n📊 DISTRIBUIÇÃO DAS FASES:")
            dist = df["FASE"].value_counts()
            for fase, count in dist.items():
                print(f"   - '{fase}': {count} linhas")

        return df

    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO NO PROCESSAMENTO: {str(e)}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

def salvar_resultados(df):
    """Salva os dados processados em CSV"""
    try:
        df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
        print(f"\n💾 Arquivo salvo com sucesso: {OUTPUT_CSV}")
        print(f"📊 Total de linhas: {len(df)}")
        
        # Verificação final no arquivo salvo
        if os.path.exists(OUTPUT_CSV):
            df_verificacao = pd.read_csv(OUTPUT_CSV, nrows=5)
            print("\n📋 PRIMEIRAS LINHAS DO ARQUIVO SALVO:")
            print(df_verificacao.to_string(index=False))
            
            # Verificar se há UNKNOWN no arquivo salvo
            with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'unknown' in content.lower():
                    print("⚠️  ATENÇÃO: Ainda existem valores 'unknown' no arquivo CSV!")
                else:
                    print("✅ Nenhum valor 'unknown' encontrado no arquivo CSV!")
        
        return True
    except Exception as e:
        print(f"\n❌ ERRO AO SALVAR: {str(e)}")
        return False

def main():
    """
    Função principal que processa dados do Smartsheet
    RETORNA: DataFrame com dados processados ou DataFrame vazio em caso de erro
    """
    try:
        print("\n" + "="*60)
        print(" INÍCIO DO PROCESSAMENTO ".center(60, "="))
        print("="*60)

        token = carregar_configuracao()
        if not token:
            print("❌ Falha ao carregar configuração")
            return pd.DataFrame()

        client = setup_smartsheet_client(token)
        if not client:
            print("❌ Falha ao configurar cliente Smartsheet")
            return pd.DataFrame()

        sheet_id = get_sheet_id(client, SHEET_NAME)
        if not sheet_id:
            print("❌ Falha ao obter ID da planilha")
            return pd.DataFrame()

        raw_data = get_sheet_data(client, sheet_id)
        if raw_data.empty:
            print("❌ Nenhum dado obtido da planilha")
            return pd.DataFrame()

        processed_data = process_data(raw_data)
        if processed_data.empty:
            print("❌ Nenhum dado restante após processamento")
            return pd.DataFrame()

        if not salvar_resultados(processed_data):
            print("❌ Falha ao salvar resultados")
            return pd.DataFrame()

        print("\n" + "="*60)
        print(" PROCESSAMENTO CONCLUÍDO ".center(60, "="))
        print("="*60)
        
        # *** CORREÇÃO PRINCIPAL: SEMPRE retornar um DataFrame ***
        return processed_data

    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO NA FUNÇÃO MAIN: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return pd.DataFrame()  # *** SEMPRE retornar DataFrame, mesmo em caso de erro ***

if __name__ == "__main__":
    main()
