import pdfplumber
import re
import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# ─────────────────────────────────────────────
# CAMPOS e seus limites físicos realistas
# Se a IA retornar fora desses limites = alucinação → vira null
# ─────────────────────────────────────────────
LIMITES = {
    "dy_mensal":           (0.01,  30.0),   # % ao mês
    "dy_anual":            (0.1,   60.0),   # % ao ano
    "cota_mercado":        (0.01, 500.0),   # R$
    "cota_patrimonial":    (0.01, 500.0),   # R$
    "pvp":                 (0.1,    5.0),   # ratio
    "ultimo_rendimento":   (0.001, 50.0),   # R$/cota
    "resultado_mensal":    (0.001, 50.0),   # R$/cota
    "num_cotas":           (1_000, 1e10),   # unidades
    "valor_mercado_bi":    (0.001, 500.0),  # R$ bilhões
    "valor_patrimonial_bi":(0.001, 500.0),  # R$ bilhões
    "taxa_liquida_ipca":   (0.1,   30.0),   # % a.a.
    "adimplencia":         (0.0,  100.0),   # %
    "vacancia":            (0.0,  100.0),   # %
    "area_total":          (100, 1e8),      # m²
}

CAMPOS_ESPERADOS = list(LIMITES.keys())


def extrair_texto_completo(pdf_path: str) -> dict:
    resultado = {
        "texto_por_pagina": [],
        "tabelas": [],
        "texto_completo": ""
    }

    with pdfplumber.open(pdf_path) as pdf:
        for i, pagina in enumerate(pdf.pages):
            texto = pagina.extract_text() or ""
            resultado["texto_por_pagina"].append({
                "pagina": i + 1,
                "texto": texto
            })
            resultado["texto_completo"] += f"\n--- PÁGINA {i+1} ---\n{texto}"

            tabelas = pagina.extract_tables()
            for tabela in tabelas:
                if tabela:
                    resultado["tabelas"].append({
                        "pagina": i + 1,
                        "dados": tabela
                    })

    return resultado


def _num(texto: str) -> float | None:
    """Converte string numérica brasileira para float."""
    if not texto:
        return None
    try:
        limpo = texto.strip().replace(".", "").replace(",", ".")
        return float(limpo)
    except Exception:
        return None


def _validar(campo: str, valor) -> float | None:
    """
    Valida se o valor está dentro dos limites físicos realistas.
    Retorna None se for alucinação provável.
    """
    if valor is None:
        return None
    try:
        v = float(valor)
    except Exception:
        return None

    if campo in LIMITES:
        minimo, maximo = LIMITES[campo]
        if not (minimo <= v <= maximo):
            return None  # fora do range físico = descartado

    return round(v, 4)

def detectar_tipo_fundo(texto: str) -> str:
    texto_lower = texto.lower()

    # Palavras EXCLUSIVAS de papel (quase nunca aparecem em tijolo)
    exclusivas_papel = {
        'certificado de recebível imobiliário': 10,
        'cri': 3,
        'duration': 5,
        'marcação a mercado': 5,
        'adimplência': 4,
        'devedor': 3,
        'spread de crédito': 5,
        'taxa de juros': 2,
        'lci': 3,
        'inadimplência': 4,
    }

    # Palavras EXCLUSIVAS de tijolo (quase nunca aparecem em papel)
    exclusivas_tijolo = {
        'área bruta locável': 10,
        'abl': 5,
        'vacância': 6,
        'inquilino': 6,
        'locatário': 6,
        'contrato de locação': 8,
        'revisional': 5,
        'cap rate': 7,
        'taxa de ocupação': 6,
        'galpão': 5,
        'laje corporativa': 8,
        'shopping': 4,
    }

    pontos_papel = sum(
        peso * texto_lower.count(palavra)
        for palavra, peso in exclusivas_papel.items()
    )
    pontos_tijolo = sum(
        peso * texto_lower.count(palavra)
        for palavra, peso in exclusivas_tijolo.items()
    )

    total = pontos_papel + pontos_tijolo
    if total == 0:
        return 'desconhecido'

    ratio_papel = pontos_papel / total

    if ratio_papel >= 0.75:
        return 'papel'
    elif ratio_papel <= 0.25:
        return 'tijolo'
    else:
        return 'hibrido'


# ─────────────────────────────────────────────
# CAMADA 1: Regex — certeza absoluta
# ─────────────────────────────────────────────
def _extrair_via_regex(texto: str) -> dict:
    ind = {campo: None for campo in CAMPOS_ESPERADOS}

    padroes = {
        # DY mensal — várias formas comuns
        "dy_mensal": [
            r'[Dd]ividend\s+[Yy]ield\s*[\(\[]?[Mm]ensal[\)\]]?\s*[:\-]?\s*(\d{1,2}[.,]\d{1,4})\s*%',
            r'DY\s*[Mm]ensal\s*[:\-]?\s*(\d{1,2}[.,]\d{1,4})\s*%',
            r'[Dd]ividend\s+[Yy]ield\s*[:\-]?\s*(\d{1,2}[.,]\d{1,4})\s*%',
        ],
        # DY 12 meses
        "dy_anual": [
            r'(\d{1,2}[.,]\d{1,2})\s*%\s*[úu]ltimos?\s*12\s*meses',
            r'DY\s*12\s*[Mm]eses?\s*[:\-]?\s*(\d{1,2}[.,]\d{1,4})\s*%',
            r'[úu]ltimos?\s*12\s*meses\s*[:\-]?\s*(\d{1,2}[.,]\d{1,4})\s*%',
        ],
        # Cota de mercado
        "cota_mercado": [
            r'[Cc]ota\s+[Mm]ercado\s*[:\-]?\s*R?\$?\s*(\d+[.,]\d+)',
            r'[Cc]ota\s+de\s+[Mm]ercado\s*[:\-]?\s*R?\$?\s*(\d+[.,]\d+)',
            r'pre[çc]o\s+de\s+mercado\s*[:\-]?\s*R?\$?\s*(\d+[.,]\d+)',
        ],
        # Cota patrimonial
        "cota_patrimonial": [
            r'[Cc]ota\s+[Pp]atrimonial\s*[:\-]?\s*R?\$?\s*(\d+[.,]\d+)',
            r'[Vv]alor\s+[Pp]atrimonial\s+por\s+[Cc]ota\s*[:\-]?\s*R?\$?\s*(\d+[.,]\d+)',
            r'VP\s+por\s+[Cc]ota\s*[:\-]?\s*R?\$?\s*(\d+[.,]\d+)',
        ],
        # P/VP explícito
        "pvp": [
            r'P\s*/\s*VP\s*[:\-]?\s*(\d+[.,]\d+)',
            r'P\.VP\s*[:\-]?\s*(\d+[.,]\d+)',
        ],
        # Dividendo/rendimento mensal
        "ultimo_rendimento": [
            r'[Dd]ividendo\s+[Mm]ensal\s*[:\-]?\s*R?\$?\s*(\d+[.,]\d+)',
            r'[Rr]endimento\s+[Dd]istribu[íi]do\s*[:\-]?\s*R?\$?\s*(\d+[.,]\d+)',
            r'[Dd]istribui[çc][ãa]o\s*[:\-]?\s*R?\$?\s*(\d+[.,]\d+)\s*por\s*cota',
        ],
        # Resultado mensal
        "resultado_mensal": [
            r'[Rr]esultado\s+[Mm]ensal\s*[:\-]?\s*R?\$?\s*(\d+[.,]\d+)',
            r'[Rr]esultado\s+por\s+[Cc]ota\s*[:\-]?\s*R?\$?\s*(\d+[.,]\d+)',
        ],
        # Número de cotas
        "num_cotas": [
            r'[Nn][úu]mero\s+de\s+[Cc]otas?\s*[:\-]?\s*([\d.,]+)',
            r'[Cc]otas?\s+[Ee]mitidas?\s*[:\-]?\s*([\d.,]+)',
            r'COTAS?\s*[:\-]\s*([\d.]+)',
        ],
        # Valor de mercado total
        "valor_mercado_bi": [
            r'[Vv]alor\s+de\s+[Mm]ercado\s*[\(\[]?R?\$?\s*bilh[ãa]o[\)\]]?\s*[:\-]?\s*(\d+[.,]\d+)',
            r'[Mm]ercado\s*[\(\[]R\$\s*bilh[ãa]o[\)\]]\s*(\d+[.,]\d+)',
        ],
        # Valor patrimonial total
        "valor_patrimonial_bi": [
            r'[Vv]alor\s+[Pp]atrimonial\s*[\(\[]?R?\$?\s*bilh[ãa]o[\)\]]?\s*[:\-]?\s*(\d+[.,]\d+)',
            r'[Pp]atrimonial\s*[\(\[]R\$\s*bilh[ãa]o[\)\]]\s*(\d+[.,]\d+)',
        ],
        # Taxa líquida IPCA
        "taxa_liquida_ipca": [
            r'[Tt]axa\s+[Ll][íi]quida\s*[:\-]?\s*IPCA\s*\+\s*(\d+[.,]\d+)',
            r'IPCA\s*\+\s*(\d+[.,]\d+)\s*%?\s*a\.a',
        ],
        # Adimplência
        "adimplencia": [
            r'[Aa]dimpl[eê]ncia\s*[:\-]?\s*(\d+[.,]\d*)\s*%',
            r'[Cc]arteira\s+(\d+[.,]\d*)\s*%\s+adimplente',
        ],
        # Vacância
        "vacancia": [
            r'[Vv]ac[aâ]ncia\s+[Ff][íi]sica\s*[:\-]?\s*(\d+[.,]\d+)\s*%',
            r'[Vv]ac[aâ]ncia\s*[:\-]?\s*(\d+[.,]\d+)\s*%',
            r'[Tt]axa\s+de\s+[Vv]ac[aâ]ncia\s*[:\-]?\s*(\d+[.,]\d+)\s*%',
        ],
        # Área total
        "area_total": [
            r'[Áá]rea\s+[Tt]otal\s*[:\-]?\s*([\d.,]+)\s*m[²2]',
            r'[Áá]rea\s+[Bb]ruta\s+[Ll]oc[aá]vel\s*[:\-]?\s*([\d.,]+)',
            r'ABL\s*[:\-]?\s*([\d.,]+)\s*m[²2]',
        ],
    }

    for campo, lista_padroes in padroes.items():
        for padrao in lista_padroes:
            m = re.search(padrao, texto, re.IGNORECASE)
            if m:
                valor = _validar(campo, _num(m.group(1)))
                if valor is not None:
                    ind[campo] = valor
                    break

    # P/VP calculado se não encontrado explicitamente
    if ind["pvp"] is None and ind["cota_mercado"] and ind["cota_patrimonial"]:
        try:
            pvp_calc = ind["cota_mercado"] / ind["cota_patrimonial"]
            ind["pvp"] = _validar("pvp", pvp_calc)
        except Exception:
            pass

    # ── PADRÕES CONTEXTUAIS (layout tabular sem rótulo inline) ──

    # "R$ 7,93 por cota R$ 8,85 por cota"
    m = re.search(
        r'R\$\s*(\d+[.,]\d+)\s*por\s*cota\s+R\$\s*(\d+[.,]\d+)\s*por\s*cota',
        texto, re.IGNORECASE
    )
    if m:
        if ind["cota_mercado"] is None:
            ind["cota_mercado"] = _validar("cota_mercado", _num(m.group(1)))
        if ind["cota_patrimonial"] is None:
            ind["cota_patrimonial"] = _validar("cota_patrimonial", _num(m.group(2)))

    # "Valor de Mercado Valor Patrimonial ... 2,88 3,22 10,64%"
    m = re.search(
        r'[Vv]alor\s+de\s+[Mm]ercado\s+[Vv]alor\s+[Pp]atrimonial'
        r'.{0,60}?(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)\s*%',
        texto, re.DOTALL
    )
    if m:
        if ind["valor_mercado_bi"] is None:
            ind["valor_mercado_bi"] = _validar("valor_mercado_bi", _num(m.group(1)))
        if ind["valor_patrimonial_bi"] is None:
            ind["valor_patrimonial_bi"] = _validar("valor_patrimonial_bi", _num(m.group(2)))
        if ind["taxa_liquida_ipca"] is None:
            ind["taxa_liquida_ipca"] = _validar("taxa_liquida_ipca", _num(m.group(3)))

    # "Resultado Mensal Dividendo Mensal Dividend Yield ... 0,074 0,090 14,50%"
    m = re.search(
        r'[Rr]esultado\s+[Mm]ensal\s+[Dd]ividendo\s+[Mm]ensal\s+[Dd]ividend'
        r'.{0,60}?(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(\d{1,2}[.,]\d+)\s*%',
        texto, re.DOTALL
    )
    if m:
        if ind["resultado_mensal"] is None:
            ind["resultado_mensal"] = _validar("resultado_mensal", _num(m.group(1)))
        if ind["ultimo_rendimento"] is None:
            ind["ultimo_rendimento"] = _validar("ultimo_rendimento", _num(m.group(2)))
        if ind["dy_mensal"] is None:
            ind["dy_mensal"] = _validar("dy_mensal", _num(m.group(3)))

    # "352.639.199" — número de cotas no formato xxx.xxx.xxx
    m = re.search(
        r'[Nn][úu]mero\s+de\s+[Cc]otas?.{0,50}?([\d]{3}\.[\d]{3}\.[\d]{3})',
        texto, re.DOTALL
    )
    if m and ind["num_cotas"] is None:
        ind["num_cotas"] = _validar("num_cotas", _num(m.group(1)))

    # Recalcula P/VP com os novos valores se ainda for None
    if ind["pvp"] is None and ind["cota_mercado"] and ind["cota_patrimonial"]:
        try:
            ind["pvp"] = round(ind["cota_mercado"] / ind["cota_patrimonial"], 3)
        except Exception:
            pass

    # ── PADRÕES GENÉRICOS CONTEXTUAIS ──────────────────────────

    # "R$ X por cota" — primeiro = mercado, segundo = patrimonial
    if ind["cota_mercado"] is None or ind["cota_patrimonial"] is None:
        matches = re.findall(r'R\$\s*(\d+[.,]\d+)\s*por\s*cota', texto, re.IGNORECASE)
        if len(matches) >= 2:
            if ind["cota_mercado"] is None:
                ind["cota_mercado"] = _validar("cota_mercado", _num(matches[0]))
            if ind["cota_patrimonial"] is None:
                ind["cota_patrimonial"] = _validar("cota_patrimonial", _num(matches[1]))
        elif len(matches) == 1 and ind["cota_mercado"] is None:
            ind["cota_mercado"] = _validar("cota_mercado", _num(matches[0]))

    # "R$ X/cota" ou "R$X/cota" — dividendo
    if ind["ultimo_rendimento"] is None:
        m = re.search(r'R\$\s*(\d+[.,]\d+)\s*/\s*cota', texto, re.IGNORECASE)
        if m:
            ind["ultimo_rendimento"] = _validar("ultimo_rendimento", _num(m.group(1)))

    # "distribuição ... R$ X por cota" — dividendo explícito
    if ind["ultimo_rendimento"] is None:
        m = re.search(
            r'distribui[çc][ãa]o.{0,80}?R\$\s*(\d+[.,]\d+)\s*por\s*cota',
            texto, re.IGNORECASE | re.DOTALL
        )
        if m:
            ind["ultimo_rendimento"] = _validar("ultimo_rendimento", _num(m.group(1)))

    # "dividendo ... R$ X por cota"
    if ind["ultimo_rendimento"] is None:
        m = re.search(
            r'dividendo.{0,80}?R\$\s*(\d+[.,]\d+)\s*por\s*cota',
            texto, re.IGNORECASE | re.DOTALL
        )
        if m:
            ind["ultimo_rendimento"] = _validar("ultimo_rendimento", _num(m.group(1)))

    # DY mensal — "equivalente a um DY a.a. de X%" — pega o mais recente
    if ind["dy_mensal"] is None:
        matches = re.findall(
            r'DY\s+a\.?a\.?\s+de\s+(\d{1,2}[.,]\d{1,2})\s*%',
            texto, re.IGNORECASE
        )
        if matches:
            # usa o primeiro (mais recente no relatório)
            ind["dy_mensal"] = _validar("dy_mensal", _num(matches[0]))

    # Número de cotas — qualquer formato xxx.xxx.xxx próximo de palavras-chave
    if ind["num_cotas"] is None:
        m = re.search(
            r'(?:cotas?|emitidas?|circula[çc][ãa]o).{0,50}?(\d{1,3}(?:\.\d{3}){2,})',
            texto, re.IGNORECASE | re.DOTALL
        )
        if not m:
            # fallback: número grande isolado (> 100.000 cotas)
            m = re.search(r'\b(\d{3}\.\d{3}\.\d{3})\b', texto)
        if m:
            ind["num_cotas"] = _validar("num_cotas", _num(m.group(1)))

    return ind


# ─────────────────────────────────────────────
# CAMADA 2: IA — só para campos ainda nulos
# Com validação rígida pós-extração
# ─────────────────────────────────────────────
def _extrair_via_ia(texto: str, ja_encontrados: dict) -> dict:
    campos_nulos = [c for c, v in ja_encontrados.items() if v is None]

    if not campos_nulos:
        return ja_encontrados  # tudo já encontrado, não chama a IA

    descricoes = {
        "dy_mensal":            "Dividend Yield mensal em % (ex: 1.2)",
        "dy_anual":             "Dividend Yield dos últimos 12 meses em % (ex: 14.5)",
        "cota_mercado":         "Valor da cota no mercado em R$ (ex: 7.93)",
        "cota_patrimonial":     "Valor patrimonial da cota em R$ (ex: 8.85)",
        "pvp":                  "Preço sobre Valor Patrimonial, ratio (ex: 0.894)",
        "ultimo_rendimento":    "Valor do dividendo/rendimento distribuído por cota em R$ (ex: 0.09)",
        "resultado_mensal":     "Resultado por cota no mês em R$ (ex: 0.074)",
        "num_cotas":            "Número total de cotas emitidas, sem pontos (ex: 352639199)",
        "valor_mercado_bi":     "Valor de mercado total do fundo em R$ bilhões (ex: 2.88)",
        "valor_patrimonial_bi": "Valor patrimonial total do fundo em R$ bilhões (ex: 3.22)",
        "taxa_liquida_ipca":    "Taxa líquida expressa como IPCA + X% ao ano (retorne só o X, ex: 10.64)",
        "adimplencia":          "Taxa de adimplência da carteira em % (ex: 100.0)",
        "vacancia":             "Taxa de vacância física em % (ex: 5.2)",
        "area_total":           "Área total ou ABL em m² (ex: 48000.0)",
    }

    campos_desc = "\n".join(
        f'  "{c}": {descricoes[c]}'
        for c in campos_nulos
    )

    nulos_json = json.dumps({c: None for c in campos_nulos}, ensure_ascii=False)

    prompt = f"""Você é um extrator de dados financeiros. Sua única tarefa é encontrar
valores numéricos LITERALMENTE presentes no texto abaixo.

REGRAS ABSOLUTAS:
1. Retorne SOMENTE um objeto JSON válido, sem texto antes ou depois.
2. Para cada campo, retorne o número como float se encontrar no texto, ou null se não encontrar.
3. NUNCA invente, estime, calcule ou suponha valores. Só retorne o que está escrito.
4. Não inclua unidades, apenas o número.
5. Use ponto como separador decimal (ex: 14.5, não 14,5).

CAMPOS A ENCONTRAR:
{campos_desc}

TEMPLATE DE RESPOSTA (preencha os nulls com o valor encontrado ou mantenha null):
{nulos_json}

TEXTO DO RELATÓRIO:
{texto[:10000]}"""

    try:
        resposta = client.chat.completions.create(
            model="meta-llama/llama-3.3-70b-instruct:free",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0,  # zero criatividade = menos alucinação
        )

        raw = resposta.choices[0].message.content or ""
        # remove markdown caso o modelo coloque ```json ... ```
        raw = re.sub(r"```json|```", "", raw).strip()

        # extrai só o JSON, ignorando texto antes/depois
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            return ja_encontrados

        dados_ia = json.loads(match.group())

        # valida cada campo retornado pela IA
        for campo in campos_nulos:
            valor_bruto = dados_ia.get(campo)
            if valor_bruto is None:
                continue

            valor_validado = _validar(campo, valor_bruto)

            # segurança extra: confirma que o número aparece no texto original
            if valor_validado is not None:
                # procura o número (ou variação com vírgula) no texto
                num_str = str(valor_validado).replace(".", "[.,]")
                if re.search(num_str[:6], texto):  # primeiros 6 dígitos
                    ja_encontrados[campo] = valor_validado
                # se não encontrar no texto, descarta silenciosamente

    except Exception:
        pass  # falha na IA não quebra o programa

    return ja_encontrados


# ─────────────────────────────────────────────
# FUNÇÃO PRINCIPAL
# ─────────────────────────────────────────────
def extrair_indicadores_chave(texto: str) -> dict:
    indicadores = _extrair_via_regex(texto)
    indicadores = _extrair_via_ia(texto, indicadores)
    indicadores["tipo_fundo"] = detectar_tipo_fundo(texto)
    return indicadores