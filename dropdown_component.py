import streamlit as st
from typing import List, Optional

def simple_multiselect_dropdown(
    label: str,
    options: List[str],
    key: Optional[str] = None,
    default_selected: Optional[List[str]] = None,
    select_all_text: str = "Marcar Todos",
    expander_expanded: bool = True,
    search_placeholder: str = "Filtre as opções...",
    no_results_text: str = "Nenhum resultado encontrado.",
    none_selected_text: str = "Nenhum selecionado"
) -> List[str]:
    """
    Cria um filtro dropdown customizado com espaçamento mínimo e preciso,
    substituindo o st.divider por um container com borda.

    Funcionalidades:
    1. Layout compacto com espaçamento mínimo garantido.
    2. 'Marcar Todos' sempre visível.
    3. Instrução estilizada com ícone, posicionada corretamente.
    4. Estilo com fundo branco e bordas arredondadas externas.
    
    Args:
        label (str): Rótulo do filtro.
        options (list): Lista de todas as opções disponíveis.
        key (str): Chave única e obrigatória para o componente.
        default_selected (list): Opções pré-selecionadas.
        select_all_text (str): Texto para o checkbox "Marcar Todos".
        expander_expanded (bool): Se o filtro deve iniciar aberto.
        search_placeholder (str): Placeholder para o campo de pesquisa.
        no_results_text (str): Texto exibido quando não há resultados.
        none_selected_text (str): Texto exibido quando nenhum item está selecionado.
        
    Returns:
        list: A lista atual de opções selecionadas.
    """
    if key is None:
        raise ValueError("O argumento 'key' é obrigatório para o componente simple_multiselect_dropdown.")

    # --- ESTILO CSS FINAL E CORRIGIDO ---
    st.markdown(
        f"""
        <style>
        /* Container do text_input para posicionamento da instrução */
        div[data-testid="stTextInput"] {{
            position: relative;
            margin-bottom: 0.5rem;
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }}
        div[data-testid="stTextInput"] > div {{
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }}
        div[data-testid="stTextInput"] > div > input {{
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }}
        div[data-testid="stTextInput"] input {{
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }}
        /* Adicionado para garantir que o container do input não tenha borda */
        div[data-testid="stTextInput"] > div[data-testid="stDecoration"] {{
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }}

        /* Container da instrução (Pressione Enter...) */
        div[data-testid="stTextInput"] > div[data-testid="InputInstructions"] {{
            position: absolute;
            top: 2.3rem;
            right: 0;
            width: auto;
            text-align: right;
        }}
        
        /* Tradução e estilização da instrução */
        [data-testid="InputInstructions"] span {{ visibility: hidden; }}
        [data-testid="InputInstructions"] span::after {{
            visibility: visible;
            content: "Pressione Enter para aplicar!"; 
            display: inline-flex;
            align-items: center;
            font-size: 0.65rem;
            color: #926c05;
            padding: 0.15rem 0.4rem;
            background-color: #fffce7;
            border-radius: 0.25rem;
            white-space: nowrap;
        }}

        /* Estilos do expander (dropdown) - Remove todas as bordas */
        div[data-testid="stExpander"] {{
            background-color: white !important;
            border: none !important;
            box-shadow: none !important;
            border-radius: 10px !important;
            overflow: hidden;
            outline: none !important;
        }}
        
        div[data-testid="stExpander"] * {{
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }}
        
        div[data-testid="stExpander"] > details {{
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }}
        
        div[data-testid="stExpander"] > details > summary {{
            border: none !important;
            box-shadow: none !important;
            padding: 0.5rem 1rem !important;
            outline: none !important;
        }}
        
        /* Remove todas as bordas do container principal */
        div[data-testid="stExpander"] > div {{
            border: none !important;
        }}
        
        /* Remove borda específica do container do campo de pesquisa */
        div[data-testid="stExpander"] div[data-testid="stVerticalBlock"]:has(div[data-testid="stTextInput"]) {{
            border: none !important;
            padding: 0 !important;
            margin: 0 !important;
        }}
        
        /* Remove borda do container de texto "Filtre as opções..." */
        div[data-testid="stExpander"] div[data-testid="stVerticalBlock"]:has(div[data-testid="stMarkdown"]:has(p)) {{
            border: none !important;
            padding: 0 !important;
            margin: 0 !important;
        }}
        
        /* Remove a borda do container interno dos checkboxes */
        div[data-testid="stExpander"] div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stCheckbox"]) {{
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
            padding: 0 !important;
            margin: 0 !important;
        }}
        
        div[data-testid="stExpander"] > details > summary:hover {{
            background-color: #f5f5f5 !important;
        }}
        .stCheckbox > label {{ 
            font-weight: 400 !important; 
            font-size: 14px !important; 
            padding: 0.25rem 0 !important;
            /* Removendo o fundo branco e a borda do rótulo */
            background-color: transparent !important;
            border: none !important;
        }}
        .stCheckbox {{
            margin-bottom: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

    # Chaves de estado internas
    state_key_selection = f"{key}_selected"
    state_key_search = f"{key}_search"
    state_key_select_all = f"{key}_select_all"
    state_key_initialized = f"{key}_initialized"

    # --- Inicialização do Estado da Sessão ---
    if state_key_initialized not in st.session_state:
        # PRIMEIRA INICIALIZAÇÃO - Forçar todas as opções selecionadas
        st.session_state[state_key_selection] = options.copy()
        st.session_state[state_key_search] = ""
        st.session_state[state_key_select_all] = True
        
        # Inicializar todos os checkboxes individuais como True
        for opt in options:
            checkbox_key = f"{key}_{opt}"
            st.session_state[checkbox_key] = True
            
        st.session_state[state_key_initialized] = True

    # Se default_selected foi fornecido, usar ele
    if default_selected is not None and state_key_initialized not in st.session_state:
        st.session_state[state_key_selection] = default_selected.copy()
        st.session_state[state_key_select_all] = set(options).issubset(set(default_selected))
        for opt in options:
            checkbox_key = f"{key}_{opt}"
            st.session_state[checkbox_key] = opt in default_selected

    # --- Funções de Callback ---
    def _on_search_change():
        # Apenas atualiza o estado do 'Marcar Todos' com base nas opções visíveis
        search_term = st.session_state.get(state_key_search, "")
        current_selection = set(st.session_state.get(state_key_selection, []))
        visible_options = {opt for opt in options if search_term.lower() in opt.lower()} if search_term else set(options)
        all_visible_selected = visible_options.issubset(current_selection) and bool(visible_options)
        st.session_state[state_key_select_all] = all_visible_selected

    def _handle_select_all():
        search_term = st.session_state.get(state_key_search, "")
        current_selection = set(st.session_state.get(state_key_selection, []))
        visible_options = {opt for opt in options if search_term.lower() in opt.lower()} if search_term else set(options)
        
        is_select_all = st.session_state[state_key_select_all]
        
        if is_select_all:
            current_selection.update(visible_options)
        else:
            current_selection.difference_update(visible_options)
        
        st.session_state[state_key_selection] = list(current_selection)
        
        # Atualiza o estado dos checkboxes individuais visíveis
        for opt in visible_options:
            checkbox_key = f"{key}_{opt}"
            st.session_state[checkbox_key] = is_select_all

    def _handle_individual_selection(option: str, checkbox_key: str):
        # O valor do checkbox (True/False) já foi atualizado pelo Streamlit no st.session_state[checkbox_key]
        is_checked = st.session_state[checkbox_key]
        current_selection = set(st.session_state.get(state_key_selection, []))
        
        if is_checked:
            current_selection.add(option)
        else:
            current_selection.discard(option)
        
        st.session_state[state_key_selection] = list(current_selection)
        
        # Sincroniza o 'Marcar Todos' após uma seleção individual
        _on_search_change()

    # --- Lógica de Exibição ---
    current_selection = st.session_state.get(state_key_selection, [])
    search_term = st.session_state.get(state_key_search, "")
    filtered_options = [opt for opt in options if search_term.lower() in opt.lower()] if search_term else options.copy()
    selected_count = len(current_selection)
    
    # Texto do cabeçalho do expander
    if selected_count == len(options) and len(options) > 0:
        header_text = f"Todos ({selected_count})"
    elif selected_count == 0:
        header_text = none_selected_text
    else:
        header_text = f"{selected_count}/{len(options)}"

    with st.expander(label=f"{label}: {header_text}", expanded=expander_expanded):
        st.text_input(
            "Pesquisar",
            key=state_key_search,
            placeholder=search_placeholder,
            on_change=_on_search_change,
            label_visibility="collapsed"
        )
        
        with st.container():
            st.checkbox(
                select_all_text,
                key=state_key_select_all,
                on_change=_handle_select_all,
                disabled=not filtered_options,
            )
                
            if not filtered_options:
                st.caption(no_results_text)
            else:
                for option in filtered_options:
                    checkbox_key = f"{key}_{option}"
                    # O valor do checkbox é lido do st.session_state[checkbox_key]
                    # que foi inicializado e é atualizado pelo Streamlit no clique.
                    st.checkbox(
                        option,
                        key=checkbox_key,
                        on_change=_handle_individual_selection,
                        args=(option, checkbox_key),
                    )
    
    return st.session_state.get(state_key_selection, [])

# EXEMPLO DE USO
def main():
    st.set_page_config(page_title="Dashboard UGBs", layout="wide")
    
    # Lista de UGBs baseada na sua imagem
    UGB_OPTIONS = ["CA", "CA02", "CA03", "GA", "IG", "JB", "SC", "eI"]
    
    st.title("Gantt Comparativo")
    
    # Conteúdo principal baseado nas seleções
    ugbs_selecionadas = simple_multiselect_dropdown(
        label="UGB",
        options=UGB_OPTIONS,
        key="filtro_ugb_principal",
        default_selected=UGB_OPTIONS,  # Todas as UGBs selecionadas inicialmente
        select_all_text="Marcar Todos",
        search_placeholder="Filtre as opções...",
        none_selected_text="Nenhum selecionado"
    )
    
    # Exibir conteúdo baseado na seleção
    if ugbs_selecionadas:
        st.success(f"Dados carregados para {len(ugbs_selecionadas)} UGB(s)")
    else:
        st.warning("Nenhum dado encontrado com os filtros aplicados.")

if __name__ == "__main__":
    main()
