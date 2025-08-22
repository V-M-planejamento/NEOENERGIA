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
        
        if not token:
            raise ValueError("Token não encontrado no arquivo .env")
        
        return token
    
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
        for sheet in response.data[:5]:  # Mostra as primeiras 5 planilhas
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
        # Incluir mais parâmetros para melhor performance
        sheet = client.Sheets.get_sheet(
            sheet_id,
            include=['format', 'discussions', 'attachments', 'columnType'],
            page_size=5000
        )
        
        # Converter para DataFrame de forma mais eficiente
        column_map = {}
        for column in sheet.columns:
            column_map[column.id] = column.title
        
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
        return df
    
    except Exception as e:
        print(f"\n❌ Falha ao obter dados: {str(e)}")
        return pd.DataFrame()

def process_data(df):
    """Processa e limpa os dados - Adaptado do DAX"""
    if df.empty:
        print("⚠️ Aviso: Nenhum dado recebido para processamento")
        return df

    try:
        original_rows = len(df)
        print(f"📊 Iniciando processamento de {original_rows} linhas...")
        
        # 1. Verificar se precisamos realmente remover as primeiras 915 linhas
        if len(df) > 915:
            print("📉 Removendo primeiras 915 linhas...")
            df = df.iloc[915:].reset_index(drop=True)
            print(f"   → {len(df)} linhas restantes")
        else:
            print("⚠️  Aviso: Planilha tem menos de 915 linhas, pulando esta etapa")
        
        # 2. Remover colunas específicas
        colunas_remover = [
            "RowNumber", "CATEGORIA", "Destaque", "Atualizar", 
            "Antecessores", "Duração", "Variação (LB-Termino)", 
            "Início LB", "Término LB", "Dur LB", "Atribuído a", "PRAZO CARTAS"
        ]
        
        print("🗑️ Removendo colunas desnecessárias...")
        colunas_existentes = [col for col in colunas_remover if col in df.columns]
        df = df.drop(columns=colunas_existentes, errors='ignore')
        print(f"   → Colunas restantes: {list(df.columns)}")
        
        # 3. Converter colunas de texto primeiro
        print("🔄 Convertendo colunas de texto...")
        text_columns = ["SERVIÇO", "FASE", "EMP", "UGB", "Nome da tarefa", "Empreendimento"]
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].astype(str)
                df[col] = df[col].replace(['nan', 'None', 'NONE', 'none', 'NaN', 'NaT'], np.nan)
                df[col] = df[col].str.strip()
        
        # 4. DEBUG CRÍTICO: Mostrar análise completa da coluna Empreendimento
        if "Empreendimento" in df.columns:
            print("\n" + "="*80)
            print("ANÁLISE COMPLETA DA COLUNA 'EMPREENDIMENTO'")
            print("="*80)
            
            # Mostrar todos os valores únicos
            unique_vals = df["Empreendimento"].unique()
            print(f"Valores únicos encontrados ({len(unique_vals)}):")
            for i, val in enumerate(unique_vals):
                print(f"  {i+1:3d}. '{val}'")
            
            # Mostrar distribuição
            print(f"\nDistribuição dos valores:")
            value_counts = df["Empreendimento"].value_counts()
            for valor, count in value_counts.items():
                print(f"  '{valor}': {count} linhas")
        
        # 5. FILTRAGEM SUPER AGRESSIVA - REMOVER TUDO QUE PARECER COM OS VALORES INDESEJADOS
        if "Empreendimento" in df.columns:
            print("\n" + "="*80)
            print("INICIANDO FILTRAGEM SUPER AGRESSIVA")
            print("="*80)
            
            antes = len(df)
            
            # Lista de padrões a serem removidos (case insensitive)
            padroes_remover = [
                r'none', r'base', r'j\.ser.*2', r'lar.*f1', r'sviii.*f2', 
                r'qdr\.g', r'ba.*4f1', r'^$', r'^\s*$'
            ]
            
            # Criar máscara para remoção
            mask = pd.Series(False, index=df.index)
            
            for padrao in padroes_remover:
                try:
                    # Buscar por regex case insensitive
                    mask = mask | df["Empreendimento"].str.contains(padrao, case=False, na=False, regex=True)
                except:
                    continue
            
            # Também remover valores nulos
            mask = mask | df["Empreendimento"].isna()
            
            # Mostrar o que será removido
            if mask.any():
                print("VALORES QUE SERÃO REMOVIDOS:")
                removidos_df = df[mask]
                for valor, count in removidos_df["Empreendimento"].value_counts().items():
                    print(f"  - '{valor}': {count} linhas")
            
            # Aplicar filtro (manter apenas os que NÃO estão na máscara)
            df = df[~mask]
            
            print(f"\nRESULTADO DA FILTRAGEM:")
            print(f"  Linhas antes: {antes}")
            print(f"  Linhas removidas: {antes - len(df)}")
            print(f"  Linhas restantes: {len(df)}")
        
        # 6. Converter outros tipos de dados
        date_columns = ["Terminar", "Iniciar"]
        for col in date_columns:
            if col in df.columns:
                print(f"   → Convertendo {col} para data")
                df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
        
        if "% concluído" in df.columns:
            print("   → Convertendo % concluído para numérico")
            df["% concluído"] = (
                pd.to_numeric(
                    df["% concluído"].astype(str)
                    .str.replace('%', '')
                    .str.replace(',', '.'), 
                    errors='coerce'
                ) / 100
            ).fillna(0)
        
        # 7. Filtrar linhas onde FASE não é nula
        if "FASE" in df.columns:
            print("🔍 Filtrando linhas com FASE não nula...")
            antes = len(df)
            df = df[df["FASE"].notna() & (df["FASE"] != "None")]
            print(f"   → Removidas {antes - len(df)} linhas com FASE nula")
        
        # 8. Mostrar resultado final
        if "Empreendimento" in df.columns:
            print("\n" + "="*80)
            print("RESULTADO FINAL - EMPREENDIMENTOS RESTANTES")
            print("="*80)
            final_values = df["Empreendimento"].value_counts()
            for valor, count in final_values.items():
                print(f"  '{valor}': {count} linhas")
        
        print(f"✅ Dados processados com sucesso: {len(df)}/{original_rows} linhas mantidas")
        return df

    except Exception as e:
        print(f"\n❌ ERRO NO PROCESSAMENTO: {str(e)}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

def salvar_resultados(df):
    """Salva os dados processados em CSV"""
    try:
        df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
        print(f"\n💾 Arquivo salvo com sucesso: {OUTPUT_CSV}")
        print(f"📊 Total de linhas: {len(df)}")
        
        # Mostrar estatísticas dos empreendimentos no arquivo final
        if "Empreendimento" in df.columns:
            print("\n📊 DISTRIBUIÇÃO FINAL DOS EMPREENDIMENTOS:")
            dist_empreendimentos = df["Empreendimento"].value_counts()
            for empreendimento, count in dist_empreendimentos.items():
                print(f"   - '{empreendimento}': {count} linhas")
        
        print("\n📋 Visualização dos dados:")
        print(df.head(10))
        return True
    except Exception as e:
        print(f"\n❌ ERRO AO SALVAR: {str(e)}")
        return False

def main():
    print("\n" + "="*60)
    print(" INÍCIO DO PROCESSAMENTO ".center(60, "="))
    print("="*60)

    # 1. Carregar configurações
    token = carregar_configuracao()
    if not token:
        sys.exit(1)

    # 2. Configurar cliente Smartsheet
    client = setup_smartsheet_client(token)
    if not client:
        sys.exit(1)

    # 3. Obter ID da planilha
    sheet_id = get_sheet_id(client, SHEET_NAME)
    if not sheet_id:
        sys.exit(1)

    # 4. Obter dados
    raw_data = get_sheet_data(client, sheet_id)
    if raw_data.empty:
        print("❌ Nenhum dado obtido da planilha")
        sys.exit(1)

    # 5. Processar dados (adaptação do DAX)
    processed_data = process_data(raw_data)
    if processed_data.empty:
        print("❌ Nenhum dado restante após processamento")
        sys.exit(1)

    # 6. Salvar resultados
    if not salvar_resultados(processed_data):
        sys.exit(1)

    print("\n" + "="*60)
    print(" PROCESSAMENTO CONCLUÍDO ".center(60, "="))
    print("="*60)

if __name__ == "__main__":
    main()