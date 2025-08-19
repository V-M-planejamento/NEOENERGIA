import pandas as pd
import smartsheet
import os
from dotenv import load_dotenv
import sys
from datetime import datetime

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
        sheet = client.Sheets.get_sheet(sheet_id)
        
        # Converter para DataFrame
        rows = []
        for row in sheet.rows:
            row_data = {}
            for cell in row.cells:
                column_name = next((col.title for col in sheet.columns if col.id == cell.column_id), None)
                if column_name:
                    row_data[column_name] = cell.value
            rows.append(row_data)
        
        df = pd.DataFrame(rows)
        print(f"✅ Dados obtidos ({len(df)} linhas)")
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
        # 1. Remover primeiras 915 linhas (equivalente a Table.Skip)
        print("📉 Removendo primeiras 915 linhas...")
        df = df.iloc[915:].reset_index(drop=True)
        
        # 2. Remover colunas específicas (equivalente a Table.RemoveColumns)
        colunas_remover = [
            "RowNumber", "CATEGORIA", "Destaque", "Atualizar", 
            "Antecessores", "Duração", "Variação (LB-Termino)", 
            "Início LB", "Término LB", "Dur LB", "Atribuído a", "PRAZO CARTAS"
        ]
        
        print("🗑️ Removendo colunas desnecessárias...")
        df = df.drop(columns=[col for col in colunas_remover if col in df.columns], errors='ignore')
        
        # 3. Converter tipos de dados (equivalente a Table.TransformColumnTypes)
        print("🔄 Convertendo tipos de dados...")
        
        # Converter datas
        for col in ["Terminar", "Iniciar"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Converter porcentagem
        if "% concluído" in df.columns:
            df["% concluído"] = (
                pd.to_numeric(
                    df["% concluído"].astype(str)
                    .str.replace('%', '')
                    .str.replace(',', '.'), 
                    errors='coerce'
                ) / 100
            ).fillna(0)
        
        # Converter colunas de texto
        text_columns = ["SERVIÇO", "FASE", "EMP", "UGB", "Nome da tarefa"]
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].astype(str)
        
        # 4. Filtrar linhas onde FASE não é nula (equivalente a Table.SelectRows)
        print("🔍 Filtrando linhas com FASE não nula...")
        if "FASE" in df.columns:
            df = df[df["FASE"].notna() & (df["FASE"] != "None") & (df["FASE"] != "nan")]
        
        print("✅ Dados processados com sucesso")
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
        print("\n📋 Visualização dos dados:")
        print(df.head())
        print("\n📝 Colunas disponíveis:")
        print(df.columns.tolist())
        return True
    except Exception as e:
        print(f"\n❌ ERRO AO SALVAR: {str(e)}")
        return False

def main():
    print("\n" + "="*50)
    print(" INÍCIO DO PROCESSAMENTO ".center(50, "="))
    print("="*50)

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
        sys.exit(1)

    # 5. Processar dados (adaptação do DAX)
    processed_data = process_data(raw_data)
    if processed_data.empty:
        sys.exit(1)

    # 6. Salvar resultados
    if not salvar_resultados(processed_data):
        sys.exit(1)

if __name__ == "__main__":
    main()