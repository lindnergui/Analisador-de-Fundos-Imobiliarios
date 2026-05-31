def _pct(valor, casas=1):
    if valor is None:
        return "n/d"
    return f"{valor:.{casas}f}%"


def _rs(valor):
    if valor is None:
        return "n/d"
    return f"R$ {valor:.2f}"


def _item(fator, pontos, maximo, detalhe):
    return {
        "fator": fator,
        "pontos": pontos,
        "max": maximo,
        "detalhe": detalhe,
    }


def _score_pvp(pvp, peso=15):
    if pvp is None:
        return _item("Preço vs valor patrimonial", 0, peso, "P/VP não encontrado")
    if pvp <= 0.90:
        pontos, detalhe = peso, f"P/VP {pvp:.2f}: desconto relevante"
    elif pvp <= 1.00:
        pontos, detalhe = round(peso * 0.8), f"P/VP {pvp:.2f}: preço abaixo/ao redor do VP"
    elif pvp <= 1.10:
        pontos, detalhe = round(peso * 0.45), f"P/VP {pvp:.2f}: leve prêmio"
    elif pvp <= 1.20:
        pontos, detalhe = round(peso * 0.2), f"P/VP {pvp:.2f}: prêmio exige cautela"
    else:
        pontos, detalhe = 0, f"P/VP {pvp:.2f}: prêmio elevado"
    return _item("Preço vs valor patrimonial", pontos, peso, detalhe)


def _score_dy(dy_mensal, peso=12):
    if dy_mensal is None:
        return _item("Rendimento mensal", 0, peso, "DY mensal não encontrado")
    if 0.65 <= dy_mensal <= 1.20:
        pontos, detalhe = peso, f"DY mensal {_pct(dy_mensal)} em faixa saudável"
    elif 0.45 <= dy_mensal < 0.65:
        pontos, detalhe = round(peso * 0.65), f"DY mensal {_pct(dy_mensal)} moderado"
    elif 1.20 < dy_mensal <= 1.60:
        pontos, detalhe = round(peso * 0.55), f"DY mensal {_pct(dy_mensal)} alto; verificar recorrência"
    elif 1.60 < dy_mensal <= 2.00:
        pontos, detalhe = round(peso * 0.25), f"DY mensal {_pct(dy_mensal)} muito alto; possível risco"
    else:
        pontos, detalhe = 0, f"DY mensal {_pct(dy_mensal)} fora da faixa conservadora"
    return _item("Rendimento mensal", pontos, peso, detalhe)


def _score_cobertura(resultado, rendimento, peso=16):
    if resultado is None or rendimento is None:
        return _item("Cobertura do rendimento", 0, peso, "Resultado ou rendimento não encontrado")
    if rendimento <= 0:
        return _item("Cobertura do rendimento", 0, peso, "Rendimento inválido")

    cobertura = resultado / rendimento
    if cobertura >= 1.05:
        pontos, detalhe = peso, f"Resultado cobre {cobertura:.2f}x o rendimento"
    elif cobertura >= 0.95:
        pontos, detalhe = round(peso * 0.8), f"Cobertura próxima do ideal: {cobertura:.2f}x"
    elif cobertura >= 0.85:
        pontos, detalhe = round(peso * 0.45), f"Cobertura apertada: {cobertura:.2f}x"
    else:
        pontos, detalhe = 0, f"Cobertura fraca: {cobertura:.2f}x"
    return _item("Cobertura do rendimento", pontos, peso, detalhe)


def _score_liquidez_tamanho(valor_bi, peso=8):
    if valor_bi is None:
        return _item("Tamanho/liquidez do fundo", 0, peso, "Valor patrimonial/mercado não encontrado")
    if valor_bi >= 2:
        pontos, detalhe = peso, f"Fundo grande: R$ {valor_bi:.2f} bi"
    elif valor_bi >= 1:
        pontos, detalhe = round(peso * 0.75), f"Fundo de bom porte: R$ {valor_bi:.2f} bi"
    elif valor_bi >= 0.5:
        pontos, detalhe = round(peso * 0.45), f"Porte médio: R$ {valor_bi:.2f} bi"
    else:
        pontos, detalhe = round(peso * 0.15), f"Porte menor: R$ {valor_bi:.2f} bi"
    return _item("Tamanho/liquidez do fundo", pontos, peso, detalhe)


def _score_vacancia(vacancia, peso=22):
    if vacancia is None:
        return _item("Vacância", 0, peso, "Vacância não encontrada")
    if vacancia <= 3:
        pontos, detalhe = peso, f"Vacância baixa: {_pct(vacancia)}"
    elif vacancia <= 7:
        pontos, detalhe = round(peso * 0.8), f"Vacância controlada: {_pct(vacancia)}"
    elif vacancia <= 12:
        pontos, detalhe = round(peso * 0.45), f"Vacância relevante: {_pct(vacancia)}"
    elif vacancia <= 20:
        pontos, detalhe = round(peso * 0.2), f"Vacância alta: {_pct(vacancia)}"
    else:
        pontos, detalhe = 0, f"Vacância crítica: {_pct(vacancia)}"
    return _item("Vacância", pontos, peso, detalhe)


def _score_area(area, peso=7):
    if area is None:
        return _item("Escala imobiliária", 0, peso, "ABL/área não encontrada")
    if area >= 500_000:
        pontos, detalhe = peso, f"Portfólio amplo: {area:,.0f} m²".replace(",", ".")
    elif area >= 150_000:
        pontos, detalhe = round(peso * 0.75), f"Boa escala: {area:,.0f} m²".replace(",", ".")
    elif area >= 50_000:
        pontos, detalhe = round(peso * 0.45), f"Escala moderada: {area:,.0f} m²".replace(",", ".")
    else:
        pontos, detalhe = round(peso * 0.2), f"Escala menor: {area:,.0f} m²".replace(",", ".")
    return _item("Escala imobiliária", pontos, peso, detalhe)


def _score_taxa_ipca(taxa, peso=22):
    if taxa is None:
        return _item("Taxa média da carteira", 0, peso, "Taxa IPCA+ não encontrada")
    if 6 <= taxa <= 10:
        pontos, detalhe = peso, f"IPCA+ {_pct(taxa)} em faixa conservadora"
    elif 10 < taxa <= 12:
        pontos, detalhe = round(peso * 0.7), f"IPCA+ {_pct(taxa)} atrativa, com risco maior"
    elif 4 <= taxa < 6:
        pontos, detalhe = round(peso * 0.55), f"IPCA+ {_pct(taxa)} defensiva, menor prêmio"
    elif 12 < taxa <= 14:
        pontos, detalhe = round(peso * 0.35), f"IPCA+ {_pct(taxa)} alta; exige atenção ao crédito"
    else:
        pontos, detalhe = 0, f"IPCA+ {_pct(taxa)} fora da faixa conservadora"
    return _item("Taxa média da carteira", pontos, peso, detalhe)


def _score_adimplencia(adimplencia, peso=18):
    if adimplencia is None:
        return _item("Adimplência", 0, peso, "Adimplência não encontrada")
    if adimplencia >= 99:
        pontos, detalhe = peso, f"Carteira quase totalmente adimplente: {_pct(adimplencia)}"
    elif adimplencia >= 97:
        pontos, detalhe = round(peso * 0.75), f"Boa adimplência: {_pct(adimplencia)}"
    elif adimplencia >= 94:
        pontos, detalhe = round(peso * 0.4), f"Adimplência requer atenção: {_pct(adimplencia)}"
    else:
        pontos, detalhe = 0, f"Adimplência fraca: {_pct(adimplencia)}"
    return _item("Adimplência", pontos, peso, detalhe)


def _score_desconto_fof(pvp, peso=26):
    if pvp is None:
        return _item("Desconto patrimonial", 0, peso, "P/VP não encontrado")
    if pvp <= 0.85:
        pontos, detalhe = peso, f"P/VP {pvp:.2f}: desconto amplo"
    elif pvp <= 0.95:
        pontos, detalhe = round(peso * 0.8), f"P/VP {pvp:.2f}: bom desconto"
    elif pvp <= 1.00:
        pontos, detalhe = round(peso * 0.55), f"P/VP {pvp:.2f}: próximo do VP"
    elif pvp <= 1.08:
        pontos, detalhe = round(peso * 0.2), f"P/VP {pvp:.2f}: prêmio moderado"
    else:
        pontos, detalhe = 0, f"P/VP {pvp:.2f}: prêmio elevado"
    return _item("Desconto patrimonial", pontos, peso, detalhe)


def _score_confianca_tipo(confianca, peso=5):
    if confianca is None:
        return _item("Tipo identificado", 0, peso, "Tipo sem confiança estimada")
    if confianca >= 0.9:
        pontos, detalhe = peso, f"Tipo identificado com {confianca:.0%} de confiança"
    elif confianca >= 0.75:
        pontos, detalhe = round(peso * 0.6), f"Tipo identificado com {confianca:.0%} de confiança"
    else:
        pontos, detalhe = round(peso * 0.2), f"Tipo pouco confiável: {confianca:.0%}"
    return _item("Tipo identificado", pontos, peso, detalhe)


def avaliar_pontuacao(indicadores: dict) -> dict:
    tipo = indicadores.get("tipo_fundo", "desconhecido")
    valor_base = indicadores.get("valor_patrimonial_bi") or indicadores.get("valor_mercado_bi")

    itens = [_score_confianca_tipo(indicadores.get("tipo_confianca"))]

    if tipo == "papel":
        itens.extend([
            _score_taxa_ipca(indicadores.get("taxa_liquida_ipca")),
            _score_adimplencia(indicadores.get("adimplencia")),
            _score_cobertura(indicadores.get("resultado_mensal"), indicadores.get("ultimo_rendimento")),
            _score_dy(indicadores.get("dy_mensal")),
            _score_pvp(indicadores.get("pvp"), peso=10),
            _score_liquidez_tamanho(valor_base, peso=7),
        ])
    elif tipo == "tijolo":
        itens.extend([
            _score_vacancia(indicadores.get("vacancia")),
            _score_pvp(indicadores.get("pvp")),
            _score_cobertura(indicadores.get("resultado_mensal"), indicadores.get("ultimo_rendimento")),
            _score_dy(indicadores.get("dy_mensal")),
            _score_area(indicadores.get("area_total")),
            _score_liquidez_tamanho(valor_base, peso=8),
        ])
    elif tipo == "fof":
        itens.extend([
            _score_desconto_fof(indicadores.get("pvp")),
            _score_dy(indicadores.get("dy_mensal"), peso=14),
            _score_cobertura(indicadores.get("resultado_mensal"), indicadores.get("ultimo_rendimento"), peso=12),
            _score_liquidez_tamanho(valor_base, peso=12),
        ])
    elif tipo == "hibrido":
        itens.extend([
            _score_pvp(indicadores.get("pvp")),
            _score_dy(indicadores.get("dy_mensal")),
            _score_cobertura(indicadores.get("resultado_mensal"), indicadores.get("ultimo_rendimento")),
            _score_vacancia(indicadores.get("vacancia"), peso=12),
            _score_taxa_ipca(indicadores.get("taxa_liquida_ipca"), peso=12),
            _score_liquidez_tamanho(valor_base, peso=8),
        ])
    else:
        itens.extend([
            _score_pvp(indicadores.get("pvp")),
            _score_dy(indicadores.get("dy_mensal")),
            _score_cobertura(indicadores.get("resultado_mensal"), indicadores.get("ultimo_rendimento")),
            _score_liquidez_tamanho(valor_base),
        ])

    total = sum(item["pontos"] for item in itens)
    maximo = sum(item["max"] for item in itens)
    percentual = (total / maximo * 100) if maximo else 0

    if percentual >= 80:
        conceito = "Forte"
        cor = "green"
    elif percentual >= 65:
        conceito = "Bom"
        cor = "cyan"
    elif percentual >= 50:
        conceito = "Neutro"
        cor = "yellow"
    else:
        conceito = "Fraco"
        cor = "red"

    return {
        "tipo": tipo,
        "total": total,
        "max": maximo,
        "percentual": round(percentual, 1),
        "conceito": conceito,
        "cor": cor,
        "itens": itens,
    }
