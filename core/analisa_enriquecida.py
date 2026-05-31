"""
Análise enriquecida: métricas derivadas e validações tipo-específicas
para melhorar robustez das análises de IA por tipo de FII.
"""
import json
from datetime import datetime


def calcular_metricas_derivadas(indicadores: dict, tipo: str = None) -> dict:
    """Calcula métricas derivadas a partir dos indicadores extraídos."""
    metricas = {}

    # Cobertura de dividendo: resultado_mensal / ultimo_rendimento
    if indicadores.get("resultado_mensal") and indicadores.get("ultimo_rendimento"):
        cobertura = indicadores["resultado_mensal"] / indicadores["ultimo_rendimento"]
        metricas["cobertura_dividendo"] = round(cobertura, 3)

    # Cap rate implícito para TIJOLO: (resultado_mensal * 12) / cota_patrimonial / (1 - vacancia/100)
    if tipo == "tijolo" and indicadores.get("resultado_mensal") and indicadores.get("cota_patrimonial"):
        resultado_anual = indicadores["resultado_mensal"] * 12
        vacancia_pct = indicadores.get("vacancia", 0) or 0
        ocupacao_taxa = max(0, (1 - vacancia_pct / 100))

        if ocupacao_taxa > 0:
            cap_rate_bruto = (resultado_anual / indicadores["cota_patrimonial"]) * 100
            metricas["cap_rate_bruto"] = round(cap_rate_bruto, 2)

            # Cap rate implícito (sem vacancia)
            if vacancia_pct > 0:
                cap_rate_sem_vacancia = (resultado_anual / indicadores["cota_patrimonial"] / ocupacao_taxa) * 100
                metricas["cap_rate_sem_vacancia"] = round(cap_rate_sem_vacancia, 2)

    # DY implícito vs. atual (análise de consistência)
    if indicadores.get("ultimo_rendimento") and indicadores.get("cota_mercado"):
        dy_por_rendimento = (indicadores["ultimo_rendimento"] / indicadores["cota_mercado"]) * 100
        metricas["dy_por_rendimento"] = round(dy_por_rendimento, 3)

        # Compara com DY mensal relatado
        if indicadores.get("dy_mensal"):
            diferenca_dy = abs(indicadores["dy_mensal"] - dy_por_rendimento)
            metricas["consistencia_dy"] = "✅ Consistente" if diferenca_dy < 0.2 else "⚠️ Inconsistente"

    # Sustentabilidade: rendimento vs. resultado
    if indicadores.get("resultado_mensal") and indicadores.get("ultimo_rendimento"):
        sustentabilidade = (indicadores["resultado_mensal"] / indicadores["ultimo_rendimento"]) * 100
        metricas["sustentabilidade_pct"] = round(sustentabilidade, 1)

    # P/VP classificação
    if indicadores.get("pvp"):
        pvp = indicadores["pvp"]
        if pvp < 0.95:
            metricas["pvp_status"] = f"Em Desconto ({pvp:.2f}x) - Oportunidade"
        elif pvp <= 1.05:
            metricas["pvp_status"] = f"Ao Par ({pvp:.2f}x) - Justo"
        else:
            metricas["pvp_status"] = f"Em Prêmio ({pvp:.2f}x) - Premium"

    # Tamanho do fundo
    if indicadores.get("valor_patrimonial_bi"):
        vp_bi = indicadores["valor_patrimonial_bi"]
        if vp_bi > 10:
            metricas["tamanho_status"] = f"Mega ({vp_bi:.1f}bi) - Altamente Líquido"
        elif vp_bi > 5:
            metricas["tamanho_status"] = f"Grande ({vp_bi:.1f}bi) - Líquido"
        elif vp_bi > 1:
            metricas["tamanho_status"] = f"Médio ({vp_bi:.1f}bi) - Aceitável"
        else:
            metricas["tamanho_status"] = f"Pequeno ({vp_bi:.1f}bi) - Baixa Liquidez"

    # Ocupação real (para TIJOLO)
    if tipo == "tijolo" and indicadores.get("vacancia"):
        ocupacao = 100 - indicadores["vacancia"]
        metricas["ocupacao_real"] = round(ocupacao, 1)

    # Taxa IPCA+ (parsing se existir no texto do relatório - aqui é placeholder)
    # Seria extraído em extrator.py, mas incluímos para completude
    if indicadores.get("taxa_liquida_ipca"):
        taxa = indicadores["taxa_liquida_ipca"]
        metricas["taxa_ipca_status"] = f"IPCA + {taxa:.2f}% a.a."

    return metricas


def validacoes_tipo_especifico(tipo: str, indicadores: dict, metricas: dict) -> list:
    """Retorna lista de avisos/validações críticas por tipo de FII."""
    avisos = []

    # PAPEL (CRIs/Crédito)
    if tipo == "papel":
        if indicadores.get("vacancia") and indicadores["vacancia"] > 0:
            avisos.append({
                "nivel": "aviso",
                "mensagem": f"⚠️ PAPEL não deveria ter vacância (encontrado {indicadores['vacancia']:.1f}%)"
            })

        if indicadores.get("adimplencia"):
            adimpl = indicadores["adimplencia"]
            if adimpl < 95:
                avisos.append({
                    "nivel": "crítico",
                    "mensagem": f"🔴 ADIMPLÊNCIA BAIXA ({adimpl:.1f}%) - Risco de crédito elevado"
                })
            elif adimpl < 98:
                avisos.append({
                    "nivel": "aviso",
                    "mensagem": f"⚠️ Adimplência abaixo do ideal ({adimpl:.1f}%) - Monitorar"
                })

        if metricas.get("cobertura_dividendo"):
            cob = metricas["cobertura_dividendo"]
            if cob < 0.95:
                avisos.append({
                    "nivel": "crítico",
                    "mensagem": f"🔴 COBERTURA CRÍTICA ({cob:.2f}x) - Dividendo pode não ser sustentável"
                })
            elif cob < 1.05:
                avisos.append({
                    "nivel": "aviso",
                    "mensagem": f"⚠️ Cobertura no limite ({cob:.2f}x) - Pouca margem de segurança"
                })

    # TIJOLO (Imóveis)
    elif tipo == "tijolo":
        if indicadores.get("vacancia"):
            vac = indicadores["vacancia"]
            if vac > 20:
                avisos.append({
                    "nivel": "crítico",
                    "mensagem": f"🔴 VACÂNCIA CRÍTICA ({vac:.1f}%) - Muito acima do saudável"
                })
            elif vac > 10:
                avisos.append({
                    "nivel": "aviso",
                    "mensagem": f"⚠️ Vacância elevada ({vac:.1f}%) - Acima do ideal (≤7%)"
                })

        if metricas.get("cobertura_dividendo"):
            cob = metricas["cobertura_dividendo"]
            vac = indicadores.get("vacancia", 0) or 0
            if cob < 1.0 and vac > 10:
                avisos.append({
                    "nivel": "crítico",
                    "mensagem": f"🔴 DUPLO RISCO - Cobertura baixa ({cob:.2f}x) + Vacância alta ({vac:.1f}%)"
                })
            elif cob < 1.0:
                avisos.append({
                    "nivel": "aviso",
                    "mensagem": f"⚠️ Cobertura abaixo de 1x ({cob:.2f}x) - Monitorar rentabilidade"
                })

        if indicadores.get("pvp") and indicadores["pvp"] > 1.15:
            avisos.append({
                "nivel": "aviso",
                "mensagem": f"⚠️ P/VP em prêmio ({indicadores['pvp']:.2f}x) - Caro para TIJOLO"
            })

    # HÍBRIDO
    elif tipo == "hibrido":
        vac = indicadores.get("vacancia", 0)
        taxa_ipca = indicadores.get("taxa_liquida_ipca")

        ambos_ruins = False
        if vac and vac > 15:
            avisos.append({
                "nivel": "aviso",
                "mensagem": f"⚠️ Vacância elevada para componente imobiliário ({vac:.1f}%)"
            })
            ambos_ruins = True

        if taxa_ipca and taxa_ipca < 5:
            avisos.append({
                "nivel": "aviso",
                "mensagem": f"⚠️ Taxa IPCA+ baixa para componente de crédito ({taxa_ipca:.2f}%)"
            })
            ambos_ruins = True

        if ambos_ruins:
            avisos.append({
                "nivel": "crítico",
                "mensagem": "🔴 AMBOS OS COMPONENTES COM RISCO - Revisar estratégia de mix"
            })

    # FOF (Fundo de Fundos)
    elif tipo == "fof":
        if indicadores.get("pvp"):
            pvp = indicadores["pvp"]
            if pvp > 1.15:
                avisos.append({
                    "nivel": "aviso",
                    "mensagem": f"⚠️ P/VP em prêmio significativo ({pvp:.2f}x) - Questionar qualidade dos FIIs subjacentes"
                })
            elif pvp > 1.10:
                avisos.append({
                    "nivel": "aviso",
                    "mensagem": f"⚠️ P/VP acima do par ({pvp:.2f}x) - Verificar se value está justificado"
                })

        if metricas.get("cobertura_dividendo"):
            cob = metricas["cobertura_dividendo"]
            if cob < 0.95:
                avisos.append({
                    "nivel": "crítico",
                    "mensagem": f"🔴 COBERTURA BAIXA ({cob:.2f}x) - Distribuição pode sofrer cuts"
                })

    # Validações gerais
    if metricas.get("consistencia_dy") == "⚠️ Inconsistente":
        avisos.append({
            "nivel": "aviso",
            "mensagem": f"⚠️ DY inconsistente - Valor reportado vs. calculado diferem significativamente"
        })

    return avisos


def gerar_contexto_analise(tipo: str, indicadores: dict, metricas: dict, historico: list = None) -> str:
    """Gera string com contexto enriquecido para o prompt da IA."""
    contexto = f"\n## ANÁLISE ENRIQUECIDA - {tipo.upper()}\n"

    # Seção 1: Métricas Calculadas
    contexto += "\n### Métricas Derivadas Calculadas:\n"
    for chave, valor in metricas.items():
        if isinstance(valor, str):
            contexto += f"  • {chave}: {valor}\n"
        elif isinstance(valor, (int, float)):
            contexto += f"  • {chave}: {valor}\n"

    # Seção 2: Validações e Avisos
    validacoes = validacoes_tipo_especifico(tipo, indicadores, metricas)
    if validacoes:
        contexto += "\n### Avisos Detectados:\n"
        for aviso in validacoes:
            contexto += f"  {aviso['mensagem']}\n"

    # Seção 3: Comparação com Histórico
    if historico and len(historico) > 0:
        contexto += "\n### Análise de Tendência:\n"
        ultima = historico[-1]
        ultima_data = datetime.fromisoformat(ultima["data"])
        ultimos_ind = ultima.get("indicadores", {})

        tendencias = []
        for chave in ["dy_mensal", "vacancia", "pvp", "adimplencia"]:
            atual = indicadores.get(chave)
            anterior = ultimos_ind.get(chave)

            if atual is not None and anterior is not None:
                if isinstance(atual, (int, float)) and isinstance(anterior, (int, float)):
                    diff = atual - anterior
                    pct_change = (diff / anterior * 100) if anterior != 0 else 0

                    seta = "📈" if diff > 0 else "📉" if diff < 0 else "➡️"
                    tendencias.append(f"  {seta} {chave}: {anterior} → {atual} ({pct_change:+.1f}%)")

        if tendencias:
            contexto += "\n".join(tendencias) + "\n"
        else:
            contexto += "  (Sem dados anteriores para comparação)\n"

    # Seção 4: Resumo de Foco por Tipo
    contexto += "\n### Instruções Específicas para Análise:\n"
    if tipo == "papel":
        contexto += """
  • CRÍTICO: Foco em ADIMPLÊNCIA da carteira de crédito
  • Avaliar sustentabilidade do dividendo vs. resultado operacional
  • Considerar sensibilidade a juros (IPCA+)
  • Não espera-se vacância (é fundo de crédito, não imóvel)
"""
    elif tipo == "tijolo":
        contexto += """
  • CRÍTICO: Foco em VACÂNCIA física/financeira
  • Avaliar qualidade dos inquilinos e vencimento de contratos
  • Cap rate implícito vs. TIR esperada
  • Ocupação real deve estar acima de 85% para saúde financeira
"""
    elif tipo == "hibrido":
        contexto += """
  • IMPORTANTE: Ambos os componentes (imóvel + crédito) precisam estar saudáveis
  • Vacância do componente imobiliário deve ser baixa (≤7%)
  • Taxa IPCA+ do componente de crédito deve ser competitiva (≥6%)
  • Análise de correlação/balanceamento entre as duas pernas
"""
    elif tipo == "fof":
        contexto += """
  • CRÍTICO: Qualidade da carteira de FIIs subjacentes (embora não tenhamos detalhes)
  • P/VP acima do par (1.0x) é aceitável APENAS se os FIIs subjacentes forem de qualidade
  • Fee drag: estimar impacto de taxas de gestão na distribuição final
  • Diversificação entre tipos de FIIs (papel vs. tijolo)
"""

    return contexto


def exibir_metricas_console(indicadores: dict, metricas: dict, tipo: str) -> str:
    """Retorna string formatada com métricas para exibição no console (Rich table)."""
    from rich.table import Table

    table = Table(
        title="📊 Métricas Derivadas e Análise Enriquecida",
        show_header=True,
        header_style="bold cyan",
        show_lines=True,
    )

    table.add_column("Métrica", style="bold white", min_width=25)
    table.add_column("Valor", justify="right", min_width=20)
    table.add_column("Status", justify="center", min_width=15)

    # Cobertura
    if metricas.get("cobertura_dividendo"):
        cob = metricas["cobertura_dividendo"]
        status = "🟢 Saudável" if cob >= 1.05 else "🟡 Atento" if cob >= 0.95 else "🔴 Crítica"
        table.add_row("Cobertura Dividendo", f"{cob:.2f}x", status)

    # Cap rate (TIJOLO)
    if tipo == "tijolo":
        if metricas.get("cap_rate_sem_vacancia"):
            cap = metricas["cap_rate_sem_vacancia"]
            status = "🟢 Bom" if cap > 7 else "🟡 Justo" if cap > 5 else "🔴 Baixo"
            table.add_row("Cap Rate (sem vacância)", f"{cap:.2f}% a.a.", status)

    # DY Consistência
    if metricas.get("consistencia_dy"):
        table.add_row("Consistência DY", metricas["consistencia_dy"], "")

    # Sustentabilidade
    if metricas.get("sustentabilidade_pct"):
        sust = metricas["sustentabilidade_pct"]
        status = "🟢 Sustentável" if sust >= 100 else "🟡 Atenção" if sust >= 85 else "🔴 Em Risco"
        table.add_row("Sustentabilidade", f"{sust:.1f}%", status)

    # P/VP Status
    if metricas.get("pvp_status"):
        table.add_row("Valuation (P/VP)", metricas["pvp_status"], "")

    # Tamanho
    if metricas.get("tamanho_status"):
        table.add_row("Tamanho/Liquidez", metricas["tamanho_status"], "")

    # Ocupação (TIJOLO)
    if tipo == "tijolo" and metricas.get("ocupacao_real"):
        oc = metricas["ocupacao_real"]
        status = "🟢 Excelente" if oc >= 93 else "🟡 Bom" if oc >= 85 else "🔴 Baixa"
        table.add_row("Ocupação Real", f"{oc:.1f}%", status)

    # Taxa IPCA
    if metricas.get("taxa_ipca_status"):
        table.add_row("Taxa de Retorno", metricas["taxa_ipca_status"], "")

    return table
