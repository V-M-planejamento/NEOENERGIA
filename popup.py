import streamlit as st
import base64
import os

def show_welcome_screen():
    """
    Função que exibe um popup em tela cheia com botão 100% responsivo e corretamente posicionado.
    """
    
    if 'show_popup' not in st.session_state:
        st.session_state.show_popup = True
    
    if st.session_state.show_popup:
        
        def load_svg_as_base64():
            svg_path = 'Component 2.svg'
            if os.path.exists(svg_path):
                try:
                    with open(svg_path, 'rb') as f:
                        return base64.b64encode(f.read()).decode('utf-8')
                except Exception:
                    return ""
            return ""
        
        svg_base64 = load_svg_as_base64()
        
        # Injetamos o botão diretamente no HTML para controle total.
        # A mágica acontece aqui: criamos um contêiner flexível que ocupa a tela toda.
        button_html = f"""
        <div class="button-wrapper">
            <a href="?close_popup=true" target="_self" class="popup-button">
                Acessar Painel
            </a>
        </div>
        """

        popup_css = f"""
        <style>
        /* Oculta a interface principal do Streamlit */
        .main > div:first-child {{
            display: none;
        }}
        header, .stToolbar, .stDeployButton {{
            display: none !important;
        }}
        
        /* Animações */
        @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
        
        /* Overlay de fundo */
        .popup-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            {f"background-image: url('data:image/svg+xml;base64,{svg_base64}');" if svg_base64 else "background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);"}
            background-size: cover;
            background-position: center;
            z-index: 9998;
            animation: fadeIn 0.5s ease-out forwards;
        }}
        
        /* --- ABORDAGEM FINAL COM CONTÊINER FLEXÍVEL --- */

        /* 1. O contêiner que envolve o botão */
        .button-wrapper {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            z-index: 10001;
            
            /* Mágica do Flexbox para posicionamento */
            display: flex;
            justify-content: flex-end;  /* Alinha horizontalmente à direita */
            align-items: flex-end;    /* Alinha verticalmente na base */
            
            /* Espaçamento das bordas */
            padding: 5vh 5vw;
            box-sizing: border-box; /* Garante que o padding não estoure o tamanho */
        }}

        /* 2. O botão (agora é um link <a> estilizado) */
        .popup-button {{
            background: linear-gradient(45deg, #ff8c00, #ff6b00) !important;
            color: white !important;
            padding: 18px 36px !important;
            font-size: 1.2em !important;
            border-radius: 50px !important;
            cursor: pointer !important;
            transition: all 0.3s ease !important;
            box-shadow: 0 6px 20px rgba(255, 140, 0, 0.4) !important;
            font-weight: 600 !important;
            text-decoration: none !important;
            opacity: 0;
            animation: fadeIn 0.5s ease-out 0.3s forwards;
        }}
        
        .popup-button:hover {{
            transform: translateY(-3px) !important;
            box-shadow: 0 8px 25px rgba(255, 140, 0, 0.6) !important;
        }}

        /* 3. Media Query para Tablets e Celulares */
        @media (max-width: 768px) {{
            .button-wrapper {{
                justify-content: center; /* Centraliza horizontalmente */
                padding-bottom: 10vh;
            }}
        }}

        /* 4. Media Query para Celulares (ajuste fino) */
        @media (max-width: 480px) {{
            .button-wrapper {{
                padding: 0 20px 8vh 20px; /* Espaçamento lateral e inferior */
            }}
            .popup-button {{
                width: 100%;
                text-align: center;
                font-size: 1.1em !important;
            }}
        }}
        </style>
        """
        
        # Usamos query_params para detectar o "clique" no botão
        if 'close_popup' not in st.query_params:
            st.markdown(popup_css, unsafe_allow_html=True)
            st.markdown('<div class="popup-overlay"></div>', unsafe_allow_html=True)
            st.markdown(button_html, unsafe_allow_html=True)
            
            # Impede que o resto do script execute e mostre a página principal
            st.stop()
        else:
            # Se o parâmetro existe, significa que o botão foi clicado
            st.session_state.show_popup = False
            # Limpa o query param para poder mostrar o popup novamente no futuro
            st.query_params.clear()

# --- Lógica principal ---
def main():
    st.set_page_config(
        page_title="Dashboard - Módulo de Venda",
        page_icon="🏠",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    show_welcome_screen()

    # O conteúdo principal do seu dashboard
    st.title("🏠 Dashboard - Módulo de Venda")
    st.write("Bem-vindo ao sistema!")
    
    if st.button("Mostrar Popup Novamente"):
        st.session_state.show_popup = True
        st.rerun()

if __name__ == "__main__":
    main()
