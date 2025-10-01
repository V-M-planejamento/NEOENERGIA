import streamlit as st
import streamlit.components.v1 as components
import base64
import io
import matplotlib.pyplot as plt
from typing import Optional

def create_fullscreen_image_viewer(figure: plt.Figure,
                                         empreendimento: Optional[str] = None) -> None:
    """
    Renderiza um gráfico Matplotlib diretamente no HTML com um botão de tela cheia
    posicionado corretamente no canto superior direito.
    
    CORREÇÃO: Altura fixa para evitar alteração de espaçamento.

    Args:
        figure (plt.Figure): A figura Matplotlib a ser exibida.
        empreendimento (Optional[str]): Um identificador único para o componente.
    """
    
    # --- Etapa 1: Converter a figura para imagem Base64 ---
    img_buffer_display = io.BytesIO()
    figure.savefig(img_buffer_display, format='png', dpi=150, bbox_inches='tight')
    img_base64_display = base64.b64encode(img_buffer_display.getvalue()).decode('utf-8')

    img_buffer_viewer = io.BytesIO()
    figure.savefig(img_buffer_viewer, format='png', dpi=300, bbox_inches='tight', facecolor='white')
    img_base64_viewer = base64.b64encode(img_buffer_viewer.getvalue()).decode('utf-8')
    
    unique_id = f"viewer-btn-{empreendimento if empreendimento else hash(img_base64_display)}"

    # --- Etapa 2: Criar o HTML com altura FIXA ---
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            /* Container principal com altura FIXA */
            .gantt-container {{
                position: relative;
                width: 100%;
                height: 500px; /* ALTURA FIXA */
                margin: 0 auto;
                background-color: white;
                border-radius: 8px;
                overflow: hidden;
            }}
            
            /* Container da imagem */
            .image-wrapper {{
                width: 100%;
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                background-color: white;
            }}
            
            /* Imagem responsiva */
            .gantt-image {{
                max-width: 100%;
                max-height: 100%;
                width: auto;
                height: auto;
                object-fit: contain;
            }}

            /* Botão de tela cheia */
            .fullscreen-btn {{
                position: absolute;
                top: 10px;
                right: 10px;
                background-color: #FFFFFF;
                color: #31333F;
                border: 1px solid #E6EAF1;
                width: 32px;
                height: 32px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 18px;
                font-weight: bold;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s ease;
                z-index: 10;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            
            .fullscreen-btn:hover {{
                border-color: #FF4B4B;
                color: #FF4B4B;
                transform: scale(1.05);
            }}
        </style>
    </head>
    <body>
        <div class="gantt-container">
            <div class="image-wrapper">
                <img src="data:image/png;base64,{img_base64_display}" class="gantt-image" alt="Gráfico Gantt">
                <button id="{unique_id}" class="fullscreen-btn" title="Visualizar em tela cheia">⛶</button>
            </div>
        </div>

        <script>
            (function() {{
                const parentDoc = window.parent.document;
                const button = document.getElementById('{unique_id}');
                const viewerImgSrc = 'data:image/png;base64,{img_base64_viewer}';

                const styleId = 'viewer-hide-streamlit-elements';
                if (!parentDoc.getElementById(styleId)) {{
                    const style = parentDoc.createElement('style');
                    style.id = styleId;
                    style.innerHTML = `
                        body.viewer-active header[data-testid="stHeader"] {{
                            display: none;
                        }}
                        
                        body.viewer-active section[data-testid="stSidebar"] {{
                            transform: translateX(-100%);
                            transition: transform 0.3s ease-in-out;
                        }}
                        
                        body.viewer-active .main .block-container {{
                            max-width: 100% !important;
                            padding-left: 1rem !important;
                            padding-right: 1rem !important;
                            transition: all 0.3s ease-in-out;
                        }}
                    `;
                    parentDoc.head.appendChild(style);
                }}

                function loadScript(src, callback) {{
                    let script = parentDoc.querySelector(`script[src="${{src}}"]`);
                    if (script) {{ if (callback) callback(); return; }}
                    script = parentDoc.createElement('script');
                    script.src = src;
                    script.onload = callback;
                    parentDoc.head.appendChild(script);
                }}

                function loadCss(href) {{
                    if (!parentDoc.querySelector(`link[href="${{href}}"]`)) {{
                        const link = parentDoc.createElement('link');
                        link.rel = 'stylesheet'; 
                        link.href = href;
                        parentDoc.head.appendChild(link);
                    }}
                }}

                loadCss('https://cdnjs.cloudflare.com/ajax/libs/viewerjs/1.11.6/viewer.min.css' );

                button.addEventListener('click', function() {{
                    loadScript('https://cdnjs.cloudflare.com/ajax/libs/viewerjs/1.11.6/viewer.min.js', function( ) {{
                        const tempImage = parentDoc.createElement('img');
                        tempImage.src = viewerImgSrc;
                        tempImage.style.display = 'none';
                        parentDoc.body.appendChild(tempImage);

                        const viewer = new parent.Viewer(tempImage, {{
                            inline: false, 
                            navbar: false, 
                            button: true, 
                            title: false,
                            toolbar: true, 
                            fullscreen: true, 
                            keyboard: true, 
                            zIndex: 99999,
                            shown: () => {{
                                parentDoc.body.classList.add('viewer-active');
                            }},
                            hidden: () => {{
                                parentDoc.body.classList.remove('viewer-active');
                                viewer.destroy();
                                if (parentDoc.body.contains(tempImage)) {{
                                    parentDoc.body.removeChild(tempImage);
                                }}
                            }},
                        }});
                        viewer.show();
                    }});
                }});
            }})();
        </script>
    </body>
    </html>
    """
    
    # Altura FIXA para todos os gráficos - isso resolve o problema de espaçamento
    FIXED_HEIGHT = 505
    
    # Renderizar com altura FIXA
    components.html(html_content, height=FIXED_HEIGHT, scrolling=False)

# --- Exemplo de uso ---
if __name__ == '__main__':
    st.set_page_config(layout="wide")
    
    st.sidebar.image("https://viannaemoura.com.br/wp-content/uploads/2023/09/logo-Vianna-Moura.png", use_column_width=True )
    st.sidebar.header("Barra Lateral")
    st.sidebar.selectbox("Filtro de exemplo", ["Opção 1", "Opção 2", "Opção 3"])

    st.title("🎯 Visualizador com Gráficos Maiores")
    st.success("✨ CORREÇÃO: Gráficos mais largos para melhor visualização!")
    
    st.markdown("""
    ### Solução implementada:
    1. **`figsize` ajustado** para criar imagens mais largas (ex: `(20, 6)`).
    2. **Imagem se expande horizontalmente** dentro do contêiner de altura fixa.
    3. **Resultado:** Gráficos maiores e mais fáceis de ler na tela.
    """)

    # Criar múltiplos gráficos para demonstrar o espaçamento consistente
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Gráfico 1")
        # ALTERADO: figsize de (12, 6) para (20, 6) para deixar mais largo
        fig1, ax1 = plt.subplots(figsize=(20, 6))
        ax1.barh(['Tarefa A', 'Tarefa B', 'Tarefa C'], [10, 20, 15], left=[5, 0, 12])
        ax1.set_title("Gráfico de Gantt 1")
        ax1.grid(True, linestyle='--', alpha=0.5)
        plt.tight_layout()
        create_fullscreen_image_viewer(fig1, empreendimento="gantt_1")

    with col2:
        st.subheader("Gráfico 2")
        # ALTERADO: figsize de (12, 6) para (20, 6) para deixar mais largo
        fig2, ax2 = plt.subplots(figsize=(20, 6))
        ax2.barh(['Tarefa X', 'Tarefa Y', 'Tarefa Z'], [8, 15, 12], left=[2, 8, 5])
        ax2.set_title("Gráfico de Gantt 2")
        ax2.grid(True, linestyle='--', alpha=0.5)
        plt.tight_layout()
        create_fullscreen_image_viewer(fig2, empreendimento="gantt_2")

    # Gráfico único abaixo
    st.subheader("Gráfico Detalhado")
    # ALTERADO: figsize de (16, 8) para (25, 7) para um formato bem panorâmico
    fig3, ax3 = plt.subplots(figsize=(25, 7))
    ax3.barh(['Fase 1', 'Fase 2', 'Fase 3', 'Fase 4'], [20, 30, 25, 15], left=[0, 20, 50, 75])
    ax3.set_title("Cronograma Detalhado do Projeto")
    ax3.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    create_fullscreen_image_viewer(fig3, empreendimento="gantt_3")
    
    st.markdown("---")
    st.write("✅ **Funcionando:** Gráficos maiores e com espaçamento consistente!")
    st.info("💡 **Dica:** Ajuste o `figsize` para encontrar a proporção ideal para seus dados.")

