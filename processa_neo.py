import pandas as pd
import os

def tratar_e_retornar_dados_previstos():
    """Carrega e trata os dados, retornando apenas os dados PREV com a nova ordem de etapas."""
    try:
        # 1. CARREGAR OS DADOS
        diretorio_atual = os.path.dirname(os.path.abspath(__file__))
        caminho_arquivo = os.path.join(diretorio_atual, "PROGRAMAÇÃO NEOENERGIA.xlsx")
        
        if not os.path.exists(caminho_arquivo):
            print(f"Erro: Arquivo não encontrado no caminho: {caminho_arquivo}")
            return None

        df = pd.read_excel(caminho_arquivo, sheet_name="PROGRAMAÇÃO", header=None)

        # 2. REMOVER COLUNAS ESPECÍFICAS
        colunas_para_remover = [0, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34, 37, 40, 43, 46, 49, 52, 55, 58]
        df = df.drop(columns=colunas_para_remover)

        # 3. FILTRAR LINHAS
        df = df[df[1].notna() & df[4].notna()].copy()

        # 4. PROMOVER CABEÇALHOS
        df.columns = df.iloc[0]
        df = df.drop(df.index[0]).reset_index(drop=True)

        print(f"Colunas encontradas no DataFrame: {list(df.columns)}")  # DEBUG
        
        if 'UGB' not in df.columns or 'Nº LOTES' not in df.columns:
            print("Erro: Estrutura de colunas diferente do esperado.")
            return None

        # 5. UNPIVOT (transformar colunas em linhas)
        # CORRIGIDO: 'PINT-BAR.PREV.INÍCIO' → 'PINT-BAR.PREV.INÍCIO' (com acento)
        colunas_unpivot = [
            "PL-ER-E-IP.PREV.INÍCIO", "PL-ER-E-IP.PREV.TÉRMINO",
            "APROV-ER-(NEO).PREV.INÍCIO", "APROV-ER-(NEO).PREV.TÉRMINO",
            "APROV-IP-(NEO).PREV.INÍCIO", "APROV-IP-(NEO).PREV.TÉRMINO",
            "PIQ.PREV.INÍCIO", "PIQ.PREV.TÉRMINO",
            "SOLIC-CONEXÃO.PREV.INÍCIO", "SOLIC-CONEXÃO.PREV.TÉRMINO",
            "CONEXÃO.PREV.INÍCIO", "CONEXÃO.PREV.TÉRMINO",
            "PROJ-EXEC.PREV.INÍCIO", "PROJ-EXEC.PREV.TÉRMINO",
            "ORÇ.PREV.INÍCIO", "ORÇ.PREV.TÉRMINO",
            "SUP.PREV.INÍCIO", "SUP.PREV.TÉRMINO",
            "EXECUÇÃO-TER.PREV.INÍCIO", "EXECUÇÃO-TER.PREV.TÉRMINO",
            "EXECUÇÃO-ER.PREV.INÍCIO", "EXECUÇÃO-ER.PREV.TÉRMINO",
            "EXECUÇÃO-IP.PREV.INÍCIO", "EXECUÇÃO-IP.PREV.TÉRMINO",
            "INCORPORAÇÃO.PREV.INÍCIO", "INCORPORAÇÃO.PREV.TÉRMINO",
            "PINT-BAR.PREV.INÍCIO", "PINT-BAR.PREV.TÉRMINO",  
            "COMISSIONAMENTO.PREV.INÍCIO", "COMISSIONAMENTO.PREV.TÉRMINO",
            "LIG-IP.PREV.INÍCIO", "LIG-IP.PREV.TÉRMINO",
            "CARTA.PREV.INÍCIO", "CARTA.PREV.TÉRMINO",
            "ENTREGA.PREV.INÍCIO", "ENTREGA.PREV.TÉRMINO"
        ]
        
        # Verificar se todas as colunas de unpivot existem no DataFrame
        colunas_inexistentes = [col for col in colunas_unpivot if col not in df.columns]
        if colunas_inexistentes:
            print(f"Aviso: Algumas colunas não existem no DataFrame: {colunas_inexistentes}")
            # Remover colunas inexistentes da lista
            colunas_unpivot = [col for col in colunas_unpivot if col in df.columns]
        
        colunas_fixas = [col for col in df.columns if col not in colunas_unpivot]
        df_unpivoted = pd.melt(
            df,
            id_vars=colunas_fixas,
            value_vars=colunas_unpivot,
            var_name="Atributo",
            value_name="Valor"
        )

        # 6. DIVIDIR COLUNA "Atributo"
        split_cols = df_unpivoted['Atributo'].str.split('.', expand=True)
        split_cols.columns = ['Etapa', 'Tipo', 'Inicio_Fim']
        df_final = pd.concat([df_unpivoted, split_cols], axis=1)
        df_final = df_final.drop(columns=['Atributo'])

        # 7. CONVERTER TIPOS DE COLUNAS - CORRIGIDO: Removida coluna 'Avaliação' que não existe
        # Primeiro verificar quais colunas realmente existem
        colunas_para_converter = {}
        if 'UGB' in df_final.columns:
            colunas_para_converter['UGB'] = 'str'
        if 'EMP' in df_final.columns:
            colunas_para_converter['EMP'] = 'str'
        if 'MÓDULO' in df_final.columns:
            colunas_para_converter['MÓDULO'] = 'str'
        if 'Nº LOTES' in df_final.columns:
            colunas_para_converter['Nº LOTES'] = 'int64'
        
        if colunas_para_converter:
            df_final = df_final.astype(colunas_para_converter)
        
        df_final['Valor'] = pd.to_datetime(df_final['Valor'], errors='coerce').dt.date

        # 8. FILTRAR APENAS "PREV"
        df_final = df_final[df_final['Tipo'] == 'PREV'].copy()
        
        # 9. CRIAR ORDEM DAS ETAPAS E ORDENAR
        mapa_ordem = {
            'PL-ER-E-IP': 1,
            'APROV-ER-(NEO)': 2,
            'APROV-IP-(NEO)': 3,
            'PIQ': 4,
            'SOLIC-CONEXÃO': 5,
            'CONEXÃO': 6,
            'PROJ-EXEC': 7,
            'ORÇ': 8,
            'SUP': 9,
            'EXECUÇÃO-TER': 10,
            'EXECUÇÃO-ER': 11,
            'EXECUÇÃO-IP': 12,
            'INCORPORAÇÃO': 13,
            'PINT-BAR': 14,
            'COMISSIONAMENTO': 15,
            'LIG-IP': 16,
            'CARTA': 17,
            'ENTREGA': 18
        }
        
        df_final['Ordem_Etapa'] = df_final['Etapa'].map(mapa_ordem)
        
        # Ordena o DataFrame final pela ordem definida
        df_final = df_final.sort_values(by=['UGB', 'MÓDULO', 'Ordem_Etapa']).reset_index(drop=True)

        return df_final

    except Exception as e:
        print(f"Erro durante o processamento: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

# Executa a função e mostra o resultado
if __name__ == "__main__":
    dados_previstos = tratar_e_retornar_dados_previstos()
    if dados_previstos is not None:
        print("\nDados Previstos Tratados e Ordenados:")
        print(f"Total de registros: {len(dados_previstos)}")
        print(f"Etapas únicas: {dados_previstos['Etapa'].unique()}")
        print(f"Ordem das etapas: {sorted(dados_previstos['Ordem_Etapa'].unique())}")
        
        print("\nPrimeiras 20 linhas:")
        print(dados_previstos[['UGB', 'MÓDULO', 'Etapa', 'Ordem_Etapa', 'Inicio_Fim', 'Valor']].head(20))
        
        # Opcional: Salvar em CSV
        dados_previstos.to_csv('dados_previstos_tratados_ordenados.csv', index=False)
        print("\nArquivo 'dados_previstos_tratados_ordenados.csv' salvo com sucesso!")
    else:
        print("\nNão foi possível obter os dados previstos.")