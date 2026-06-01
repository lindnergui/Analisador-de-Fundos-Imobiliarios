import streamlit as st
import tempfile
import os
from pathlib import Path

from main import processar_fii
from rich.console import Console

console = Console()

st.set_page_config(
    page_title="FII Analyzer",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main {
        padding-top: 0;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("📋 FII Analyzer")
    st.markdown("---")
    st.markdown(
        """
        **Análise Inteligente de Fundos Imobiliários**

        Upload um relatório PDF de um FII e descubra:
        - 📊 Indicadores-chave extraídos
        - 🎯 Pontuação conservadora
        - 📈 Métricas derivadas
        - 🤖 Análise com IA
        - 💡 Recomendação final
        """
    )
    st.markdown("---")
    st.info("💡 **Dica**: Use relatórios informativos oficiais do fundo (PDF)")


st.title("🏢 Analisador de Fundos Imobiliários")
st.markdown("Carregue um PDF de relatório e descubra as melhores oportunidades em FIIs")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📄 Relatório")
    pdf_file = st.file_uploader(
        "Escolha um arquivo PDF",
        type="pdf",
        help="Selecione o relatório PDF do fundo"
    )

with col2:
    st.subheader("🏷️  Ticker do Fundo")
    ticker = st.text_input(
        "Informe o ticker (ex: HGLG11, MXRF11)",
        placeholder="HGLG11",
        help="O código de negociação do fundo na B3"
    ).upper().strip()

st.markdown("---")

if st.button("🚀 Analisar", use_container_width=True, type="primary"):
    if not pdf_file:
        st.error("❌ Por favor, selecione um arquivo PDF")
    elif not ticker:
        st.error("❌ Por favor, informe o ticker do fundo")
    elif len(ticker) < 4:
        st.error("❌ Ticker deve ter pelo menos 4 caracteres")
    else:
        try:
            with st.spinner("⏳ Processando PDF... aguarde..."):
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_file.read())
                    tmp_path = tmp.name

                try:
                    resultado = processar_fii(tmp_path, ticker)
                finally:
                    os.unlink(tmp_path)

            indicadores = resultado["indicadores"]
            pontuacao = resultado["pontuacao"]
            metricas = resultado["metricas_derivadas"]
            tipo_fundo = resultado["tipo_fundo"]
            analise = resultado["analise"]
            recomendacao = resultado["recomendacao"]

            st.success(f"✅ Análise concluída para {ticker}!")
            st.balloons()

            col_metric1, col_metric2, col_metric3, col_metric4 = st.columns(4)

            with col_metric1:
                dy = indicadores.get("dy_mensal")
                st.metric("📊 DY Mensal", f"{dy}%" if dy else "—",
                         delta="Alta" if dy and dy > 0.5 else None)

            with col_metric2:
                pvp = indicadores.get("pvp")
                st.metric("💰 P/VP", f"{pvp}" if pvp else "—",
                         delta="Bom" if pvp and pvp < 1 else None)

            with col_metric3:
                vac = indicadores.get("vacancia")
                st.metric("🏢 Vacância", f"{vac}%" if vac else "—",
                         delta="Baixa" if vac and vac < 10 else "Média" if vac and vac < 20 else "Alta")

            with col_metric4:
                score = pontuacao["percentual"]
                st.metric("🎯 Score", f"{score:.1f}%",
                         delta=pontuacao["conceito"])

            st.markdown("---")

            tabs = st.tabs([
                "📊 Indicadores",
                "🎯 Pontuação",
                "📈 Métricas Derivadas",
                "🤖 Análise IA",
                "📋 Resumo Final"
            ])

            with tabs[0]:
                st.subheader("📊 Indicadores Extraídos")

                tipos_cores = {
                    "papel": "🔵",
                    "tijolo": "🟡",
                    "hibrido": "🟣",
                    "fof": "🔷",
                }

                tipo = indicadores.get("tipo_fundo", "desconhecido")
                confianca = indicadores.get("tipo_confianca")
                tipo_display = f"{tipos_cores.get(tipo, '•')} {tipo.upper()}"
                if confianca:
                    tipo_display += f" ({confianca:.0%})"

                col_tipo1, col_tipo2 = st.columns(2)
                with col_tipo1:
                    st.info(f"**Tipo do Fundo**: {tipo_display}")
                with col_tipo2:
                    evidencias = indicadores.get("tipo_evidencias")
                    if evidencias:
                        st.info(f"**Evidência**: {evidencias[0]}")

                indicadores_display = {
                    "DY Mensal (%)": indicadores.get("dy_mensal"),
                    "DY Anual (%)": indicadores.get("dy_anual"),
                    "P/VP": indicadores.get("pvp"),
                    "Cota Patrimonial (R$)": indicadores.get("cota_patrimonial"),
                    "Último Rendimento (R$)": indicadores.get("ultimo_rendimento"),
                    "Vacância (%)": indicadores.get("vacancia"),
                    "Área Total (m²)": indicadores.get("area_total"),
                    "Nº de Cotas": indicadores.get("num_cotas"),
                }

                data_for_table = []
                for nome, valor in indicadores_display.items():
                    if valor is not None:
                        data_for_table.append({"Indicador": nome, "Valor": valor, "Status": "✅"})
                    else:
                        data_for_table.append({"Indicador": nome, "Valor": "—", "Status": "❌"})

                if data_for_table:
                    st.dataframe(data_for_table, use_container_width=True, hide_index=True)

            with tabs[1]:
                st.subheader("🎯 Pontuação Conservadora")

                col_score1, col_score2 = st.columns(2)
                with col_score1:
                    st.metric(
                        "Score Final",
                        f"{pontuacao['percentual']:.1f}%",
                        f"{pontuacao['total']}/{pontuacao['max']} pts"
                    )
                with col_score2:
                    st.metric("Conceito", pontuacao["conceito"])

                st.progress(pontuacao["percentual"] / 100, text=pontuacao["conceito"])

                st.markdown("**Fatores Avaliados**:")
                fatores_data = []
                for item in pontuacao.get("itens", []):
                    fatores_data.append({
                        "Fator": item["fator"],
                        "Pontos": f"{item['pontos']}/{item['max']}",
                        "Detalhe": item["detalhe"]
                    })

                st.dataframe(fatores_data, use_container_width=True, hide_index=True)

            with tabs[2]:
                st.subheader("📈 Métricas Derivadas")

                if metricas:
                    col1, col2 = st.columns(2)

                    with col1:
                        for chave, valor in list(metricas.items())[:len(metricas)//2 + 1]:
                            if valor is not None:
                                st.metric(chave.replace("_", " ").title(), f"{valor}")

                    with col2:
                        for chave, valor in list(metricas.items())[len(metricas)//2 + 1:]:
                            if valor is not None:
                                st.metric(chave.replace("_", " ").title(), f"{valor}")
                else:
                    st.info("Nenhuma métrica derivada calculada")

            with tabs[3]:
                st.subheader("🤖 Análise IA")

                secoes = [
                    "PONTOS FORTES",
                    "PONTOS FRACOS",
                    "RISCOS",
                    "ANÁLISE DOS INDICADORES",
                    "TENDÊNCIA",
                    "RECOMENDAÇÃO FINAL"
                ]

                linhas = analise.split("\n")
                buffer = []
                secao_atual = None

                for linha in linhas:
                    linha_upper = linha.upper().strip().lstrip("#").strip()
                    encontrou = False

                    for secao in secoes:
                        if secao in linha_upper:
                            if buffer and secao_atual:
                                conteudo = "\n".join(buffer).strip().replace("`", "")
                                if conteudo:
                                    with st.expander(f"**{secao_atual}**", expanded=secao_atual == "RECOMENDAÇÃO FINAL"):
                                        st.write(conteudo)
                            buffer = []
                            secao_atual = secao
                            encontrou = True
                            break

                    if not encontrou and secao_atual:
                        linha_limpa = linha.replace("**", "").replace("*", "•").replace("`", "").strip()
                        if linha_limpa:
                            buffer.append(linha_limpa)

                if buffer and secao_atual:
                    conteudo = "\n".join(buffer).strip().replace("`", "")
                    if conteudo:
                        with st.expander(f"**{secao_atual}**", expanded=secao_atual == "RECOMENDAÇÃO FINAL"):
                            st.write(conteudo)

            with tabs[4]:
                st.subheader("📋 Resumo Final")

                col1, col2 = st.columns(2)

                with col1:
                    st.metric("Ticker", ticker, label_visibility="collapsed")
                    st.metric("Tipo de Fundo", tipo.upper())

                with col2:
                    st.metric("Score", f"{pontuacao['percentual']:.1f}%")
                    st.metric("Recomendação", recomendacao.replace("✅ ", "").replace("⚠️  ", "").replace("🔴 ", ""))

                st.info(f"**Recomendação**: {recomendacao}")

                dy = indicadores.get("dy_mensal")
                vac = indicadores.get("vacancia")
                pvp = indicadores.get("pvp")

                st.markdown("**KPIs Principais**:")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("DY Mensal", f"{dy}%" if dy else "—")
                with col2:
                    st.metric("Vacância", f"{vac}%" if vac else "—")
                with col3:
                    st.metric("P/VP", pvp if pvp else "—")

            st.markdown("---")

            col_download, col_info = st.columns([3, 1])

            with col_download:
                st.download_button(
                    label="📥 Baixar Relatório Completo",
                    data=analise,
                    file_name=f"{ticker}_analise.txt",
                    mime="text/plain",
                    use_container_width=True
                )

            with col_info:
                st.info("✅ Análise salva automaticamente no histórico")

        except ValueError as e:
            st.warning(f"⚠️  {str(e)}")
        except Exception as e:
            st.error(f"❌ Erro ao processar: {str(e)}")
            st.error("Verifique se o arquivo PDF é válido")
