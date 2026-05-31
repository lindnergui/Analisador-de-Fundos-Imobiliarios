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
    "num_cotas":           (100_000, 1e10), # unidades
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
        limpo = re.sub(r"\s+", "", texto.strip())
        limpo = limpo.replace(".", "").replace(",", ".")
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


NUM_BR = r'(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?)'


def _buscar_numero_contextual(texto: str, padrao: str, grupo: int = 1) -> float | None:
    m = re.search(padrao, texto, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return _num(m.group(grupo))


def _em_bilhoes(valor) -> float | None:
    v = _num(valor) if isinstance(valor, str) else valor
    if v is None:
        return None
    return v / 1_000_000_000 if v > 500 else v


def detectar_tipo_fundo_detalhado(texto: str) -> dict:
    texto_lower = texto.lower()
    evidencias = []

    # A classificação/tipo ANBIMA costuma ser a melhor fonte quando existe.
    # Se vier "Papel Híbrido Gestão Ativa", "Papel" é o tipo econômico e
    # "Híbrido/Gestão Ativa" descreve estratégia ou mandato.
    match_anbima = re.search(
        r'(?:classifica[çc][ãa]o\s+anbima|tipo\s+anbima)[:\s]*(.{0,180})',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if match_anbima:
        trecho = " ".join(match_anbima.group(1).split())
        trecho_lower = trecho.lower()
        if "papel" in trecho_lower:
            return {
                "tipo_fundo": "papel",
                "confianca": 0.98,
                "evidencias": ["Classificação ANBIMA contém Papel"],
            }
        if "tijolo" in trecho_lower:
            return {
                "tipo_fundo": "tijolo",
                "confianca": 0.98,
                "evidencias": ["Classificação ANBIMA contém Tijolo"],
            }
        if "tvm" in trecho_lower or "títulos e valores mobiliários" in trecho_lower:
            return {
                "tipo_fundo": "fof",
                "confianca": 0.95,
                "evidencias": ["Tipo ANBIMA indica TVM/Fundo de Fundos"],
            }

    if re.search(r'fundo\s+de\s+fundos|cotas\s+de\s+outros\s+fii', texto_lower):
        return {
            "tipo_fundo": "fof",
            "confianca": 0.9,
            "evidencias": ["Relatório indica investimento em cotas de outros FIIs"],
        }

    padroes_papel = {
        r'\bcarteira\s+de\s+cris?\b': 18,
        r'\btir\s+carteira\s+de\s+cris?\b': 16,
        r'\b%[\s\w]*cris?\b': 10,
        r'\bcris?\b': 2,
        r'certificados?\s+de\s+receb[ií]veis?\s+imobili[aá]rios?': 18,
        r'receb[ií]veis?\s+imobili[aá]rios?': 14,
        r'\bdevedores?\b': 6,
        r'\badimpl[eê]ncia\b|\badimplentes?\b': 8,
        r'\binadimpl[eê]ncia\b|\binadimplentes?\b': 8,
        r'marca[çc][ãa]o\s+a\s+mercado|\bmtm\b': 8,
        r'\bduration\b': 7,
        r'spread\s+de\s+cr[eé]dito': 7,
        r'taxa\s+l[ií]quida.*ipca|ipca\s*\+': 5,
        r'\bsecurities\b': 8,
    }
    padroes_tijolo = {
        r'\bvac[âa]ncia\s+f[ií]sica\b': 12,
        r'\bvac[âa]ncia\s+financeira\b': 12,
        r'\b[aá]rea\s+bruta\s+loc[aá]vel\b': 12,
        r'\babl\b': 4,
        r'\binquilinos?\b': 8,
        r'\blocat[áa]rios?\b': 8,
        r'contratos?\s+de\s+loca[çc][ãa]o': 10,
        r'receita\s+de\s+loca[çc][ãa]o': 10,
        r'\bcap\s+rate\b': 8,
        r'taxa\s+de\s+ocupa[çc][ãa]o': 8,
        r'\bgalp(?:[ãa]o|ões|oes)\b': 6,
        r'lajes?\s+corporativas?': 8,
        r'\bshopping(?:s)?\b': 5,
    }

    pontos_papel = 0
    pontos_tijolo = 0

    for padrao, peso in padroes_papel.items():
        ocorrencias = len(re.findall(padrao, texto_lower, re.IGNORECASE))
        if ocorrencias:
            pontos_papel += peso * ocorrencias
            evidencias.append(f"papel: {padrao} ({ocorrencias}x)")

    for padrao, peso in padroes_tijolo.items():
        ocorrencias = len(re.findall(padrao, texto_lower, re.IGNORECASE))
        if ocorrencias:
            pontos_tijolo += peso * ocorrencias
            evidencias.append(f"tijolo: {padrao} ({ocorrencias}x)")

    total = pontos_papel + pontos_tijolo
    if total == 0:
        return {
            "tipo_fundo": "desconhecido",
            "confianca": 0.0,
            "evidencias": [],
        }

    ratio_papel = pontos_papel / total
    confianca = max(ratio_papel, 1 - ratio_papel)

    if ratio_papel >= 0.65:
        tipo = 'papel'
    elif ratio_papel <= 0.35:
        tipo = 'tijolo'
    else:
        tipo = 'hibrido'
        confianca = 1 - abs(0.5 - ratio_papel) * 2

    return {
        "tipo_fundo": tipo,
        "confianca": round(confianca, 2),
        "evidencias": evidencias[:6],
    }


def detectar_tipo_fundo(texto: str) -> str:
    return detectar_tipo_fundo_detalhado(texto)["tipo_fundo"]


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
        ],
        # DY 12 meses
        "dy_anual": [
            r'(\d{1,2}[.,]\d{1,2})\s*%\s*[úu]ltimos?\s*12\s*meses',
            r'DY\s*12\s*[Mm]eses?\s*[:\-]?\s*(\d{1,2}[.,]\d{1,4})\s*%',
            r'[úu]ltimos?\s*12\s*meses\s*[:\-]?\s*(\d{1,2}[.,]\d{1,4})\s*%',
            r'[Dd]ividend\s+[Yy]ield\s+anualizado\s+de\s+(\d{1,2}[.,]\d{1,4})\s*%',
            r'anualizado\s+de\s+(\d{1,2}[.,]\d{1,4})\s*%',
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

    # ── PADRÕES DE CARDS/TABELAS EM DUAS COLUNAS ─────────────────
    # Relatórios costumam mostrar "Rótulo A Rótulo B" e, abaixo,
    # "Valor A Valor B". Isso cobre cards financeiros/imobiliários
    # sem depender de um layout específico de uma gestora.
    m = re.search(
        rf'PATRIM[ÔO]NIO\s+L[ÍI]QUIDO.{{0,140}}?R\$\s*{NUM_BR}\s*(bilh(?:[oõ]es|[aã]o))?',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m and ind["valor_patrimonial_bi"] is None:
        valor = _num(m.group(1))
        if m.group(2) or (valor is not None and valor > 500):
            ind["valor_patrimonial_bi"] = _validar("valor_patrimonial_bi", _em_bilhoes(valor))

    m = re.search(
        rf'COTA\s+PATRIMONIAL(?:\s+EM\s+\d{{2}}/\d{{2}}/\d{{2,4}})?'
        rf'.{{0,120}}?R\$\s*{NUM_BR}',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["cota_patrimonial"] = _validar("cota_patrimonial", _num(m.group(1)))

    m = re.search(
        rf'COTA\s+(?:DE\s+)?MERCADO(?:\s+EM\s+\d{{2}}/\d{{2}}/\d{{2,4}})?'
        rf'.{{0,120}}?R\$\s*{NUM_BR}',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["cota_mercado"] = _validar("cota_mercado", _num(m.group(1)))

    m = re.search(
        rf'VALOR\s+PATRIMONIAL.{{0,80}}?R\$\s*{NUM_BR}\s*(bi|bilh(?:[oõ]es|[aã]o))?',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        valor = _num(m.group(1))
        if m.group(2) or (valor is not None and valor > 500):
            ind["valor_patrimonial_bi"] = _validar("valor_patrimonial_bi", _em_bilhoes(valor))

    m = re.search(
        rf'VALOR\s+DE\s+MERCADO.{{0,80}}?R\$\s*{NUM_BR}\s*(bi|bilh(?:[oõ]es|[aã]o))?',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m and "VALOR PATRIMONIAL" not in m.group(0).upper():
        valor = _num(m.group(1))
        if m.group(2) or (valor is not None and valor > 500):
            ind["valor_mercado_bi"] = _validar("valor_mercado_bi", _em_bilhoes(valor))

    m = re.search(
        r'QUANTIDADE\s+DE\s+C\s*OT\s*AS[^\d]{0,120}([\d][\d.\s]*(?:,\d+)?)',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["num_cotas"] = _validar("num_cotas", _num(m.group(1)))

    m = re.search(
        r'DIVIDENDOS\s+A\s+PAGAR.{0,120}?R\$\s*([\d\s.,]+?)\s*/?\s*cota',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["ultimo_rendimento"] = _validar("ultimo_rendimento", _num(m.group(1)))

    m = re.search(
        rf'representam\s+uma\s+rentabilidade.{{0,120}}?de\s+{NUM_BR}\s*%',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m and ind["dy_mensal"] is None:
        ind["dy_mensal"] = _validar("dy_mensal", _num(m.group(1)))

    m = re.search(
        rf'Valor\s+de\s+mercado.*?Distribui[çc][ãa]o\s+de\s+dividendos'
        rf'.{{0,120}}?R\$\s*{NUM_BR}\s*\(R\$\s*{NUM_BR}\s*/\s*cota\)\s*R\$\s*{NUM_BR}\s*/\s*cota'
        rf'.{{0,160}}?Valor\s+patrimonial.*?R\$\s*{NUM_BR}\s*\(R\$\s*{NUM_BR}\s*/\s*cota\)',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["valor_mercado_bi"] = _validar("valor_mercado_bi", _em_bilhoes(m.group(1)))
        ind["cota_mercado"] = _validar("cota_mercado", _num(m.group(2)))
        ind["ultimo_rendimento"] = _validar("ultimo_rendimento", _num(m.group(3)))
        ind["valor_patrimonial_bi"] = _validar("valor_patrimonial_bi", _em_bilhoes(m.group(4)))
        ind["cota_patrimonial"] = _validar("cota_patrimonial", _num(m.group(5)))

    m = re.search(
        rf'DY:\s*{NUM_BR}\s*%\s*a\.?m\.',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["dy_mensal"] = _validar("dy_mensal", _num(m.group(1)))

    m = re.search(
        rf'ABL\s+Total\s*\(m[²2]\)\s+{NUM_BR}',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m and ind["area_total"] is None:
        ind["area_total"] = _validar("area_total", _num(m.group(1)))

    m = re.search(
        rf'Vac[âa]ncia\s*\(%\s*ABL\).*?{NUM_BR}\s*%',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m and ind["vacancia"] is None:
        ind["vacancia"] = _validar("vacancia", _num(m.group(1)))

    m = re.search(
        rf'Valor\s+de\s+mercado\s+{NUM_BR}.{{0,100}}?Quantidade\s+de\s+cotas\s+{NUM_BR}',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["valor_mercado_bi"] = _validar("valor_mercado_bi", _em_bilhoes(m.group(1)))
        ind["num_cotas"] = _validar("num_cotas", _num(m.group(2)))

    m = re.search(
        rf'[Aa]\s*cota\s*encerrou\s*o\s*m[eê]s.*?R\$\s*{NUM_BR}',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["cota_mercado"] = _validar("cota_mercado", _num(m.group(1)))

    m = re.search(
        rf'RENDIMENTO\s+MENSAL.{{0,80}}?R\$\s*{NUM_BR}',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["ultimo_rendimento"] = _validar("ultimo_rendimento", _num(m.group(1)))

    m = re.search(
        rf'aprox\.?\s*{NUM_BR}\s*mil\s+metros\s+de\s+ABL',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["area_total"] = _validar("area_total", _num(m.group(1)) * 1000)

    m = re.search(
        rf'Cota\s+de\s+Mercado:?\s+Valor\s+de\s+Mercado:?\s+Cota\s+Patrimonial:?'
        rf'.{{0,120}}?R\$\s*{NUM_BR}\s+R\$\s*{NUM_BR}\s+R\$\s*{NUM_BR}',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["cota_mercado"] = _validar("cota_mercado", _num(m.group(1)))
        ind["valor_mercado_bi"] = _validar("valor_mercado_bi", _em_bilhoes(m.group(2)))
        ind["cota_patrimonial"] = _validar("cota_patrimonial", _num(m.group(3)))

    m = re.search(
        rf'Valor\s+Patrimonial:?\s+Rendimento\s+no\s+M[eê]s:?\s+Dividend\s+Yield\s+Mensal\s+e'
        rf'.{{0,160}}?R\$\s*{NUM_BR}\s+R\$\s*{NUM_BR}.{{0,80}}?'
        rf'{NUM_BR}\s*%\s*/\s*{NUM_BR}\s*%',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["valor_patrimonial_bi"] = _validar("valor_patrimonial_bi", _em_bilhoes(m.group(1)))
        ind["ultimo_rendimento"] = _validar("ultimo_rendimento", _num(m.group(2)))
        ind["dy_mensal"] = _validar("dy_mensal", _num(m.group(3)))
        ind["dy_anual"] = _validar("dy_anual", _num(m.group(4)))

    m = re.search(
        rf'dividend\s+yield\s+mensal\s+de\s+{NUM_BR}\s*%.*?'
        rf'anualizado\s+de\s+{NUM_BR}\s*%.*?cota\s+de\s+mercado\s+de\s+R\$\s*{NUM_BR}',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["dy_mensal"] = _validar("dy_mensal", _num(m.group(1)))
        ind["dy_anual"] = _validar("dy_anual", _num(m.group(2)))
        if ind["cota_mercado"] is None or ind["cota_mercado"] < 5:
            ind["cota_mercado"] = _validar("cota_mercado", _num(m.group(3)))

    m = re.search(
        rf'[Áá]rea\s+de\s+Terreno.*?[Áá]rea\s+Bruta\s+Loc[aá]vel.*?'
        rf'{NUM_BR}\s*m[²2]\s+{NUM_BR}\s*m[²2]',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m and ind["area_total"] is None:
        ind["area_total"] = _validar("area_total", _num(m.group(2)))

    m = re.search(
        rf'Vac[âa]ncia:?.{{0,80}}?F[ií]sica:?\s*{NUM_BR}\s*%.{{0,140}}?Financeira:?\s*{NUM_BR}\s*%',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["vacancia"] = _validar("vacancia", _num(m.group(1)))

    m = re.search(
        rf'Resultado\s+Operacional\s+por\s+Cota\s+{NUM_BR}\s+{NUM_BR}\s+{NUM_BR}\s+{NUM_BR}',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["resultado_mensal"] = _validar("resultado_mensal", _num(m.group(4)))

    m = re.search(
        rf'Patrim[oô]nio\s+L[ií]quido\*?\s+Cota\s+Patrimonial\*?'
        rf'.{{0,120}}?R\$\s*{NUM_BR}\s*bilh(?:[oõ]es|[aã]o)?\s+R\$\s*{NUM_BR}',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["valor_patrimonial_bi"] = _validar("valor_patrimonial_bi", _num(m.group(1)))
        ind["cota_patrimonial"] = _validar("cota_patrimonial", _num(m.group(2)))

    m = re.search(
        rf'Valor\s+de\s+Mercado\*?\s+Cota\s+de\s+Mercado\*?'
        rf'.{{0,360}}?R\$\s*{NUM_BR}\s*bilh(?:[oõ]es|[aã]o)?\s+R\$\s*{NUM_BR}',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        ind["valor_mercado_bi"] = _validar("valor_mercado_bi", _num(m.group(1)))
        ind["cota_mercado"] = _validar("cota_mercado", _num(m.group(2)))

    m = re.search(
        rf'P\s*/\s*VP\*?\s+ADTV\*?.{{0,360}}?{NUM_BR}\s*x',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m and ind["pvp"] is None:
        ind["pvp"] = _validar("pvp", _num(m.group(1)))

    m = re.search(
        rf'Dividend\s+Yield.{{0,300}}?'
        rf'{NUM_BR}\s*%\s*a\.?a\.?.{{0,40}}?{NUM_BR}\s*%\s*a\.?a\.?',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m and ind["dy_anual"] is None:
        ind["dy_anual"] = _validar("dy_anual", _num(m.group(1)))

    m = re.search(
        rf'ABL\s*\(m[²2]\)\*?.{{0,260}}?{NUM_BR}\s+{NUM_BR}\s*anos?',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m and ind["area_total"] is None:
        ind["area_total"] = _validar("area_total", _num(m.group(1)))

    m = re.search(
        rf'Vac[âa]ncia\s+F[ií]sica\*?\s+Vac[âa]ncia\s+Financeira\*?'
        rf'.{{0,260}}?{NUM_BR}\s*%\s+{NUM_BR}\s*%',
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    if m and ind["vacancia"] is None:
        ind["vacancia"] = _validar("vacancia", _num(m.group(1)))

    valor = _buscar_numero_contextual(
        texto,
        rf'Cotas\s+Emitidas?.{{0,220}}?{NUM_BR}(?:\s*[¹²³])?',
    )
    if valor is not None and ind["num_cotas"] is None:
        ind["num_cotas"] = _validar("num_cotas", valor)

    valor = _buscar_numero_contextual(
        texto,
        rf'distribui[çc][ãa]o\s+de\s+rendimentos?.{{0,120}}?R\$\s*{NUM_BR}\s*/\s*cota',
    )
    if valor is not None:
        ind["ultimo_rendimento"] = _validar("ultimo_rendimento", valor)

    valor = _buscar_numero_contextual(
        texto,
        rf'resultado\s+de\s+R\$.{{0,160}}?{NUM_BR}\s*/\s*cota',
    )
    if valor is not None and ind["resultado_mensal"] is None:
        ind["resultado_mensal"] = _validar("resultado_mensal", valor)

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
        if ind["dy_anual"] is None:
            ind["dy_anual"] = _validar("dy_anual", _num(m.group(3)))

    # "352.639.199" — número de cotas no formato xxx.xxx.xxx
    m = re.search(
        r'[Nn][úu]mero\s+de\s+[Cc]otas?.{0,160}?([\d]{1,3}\.[\d]{3}\.[\d]{3})',
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

    # "R$ X por cota" — se houver pares, geralmente são mercado/patrimonial.
    # Um único valor por cota costuma ser distribuição, então não deve virar
    # cota de mercado.
    if ind["cota_mercado"] is None or ind["cota_patrimonial"] is None:
        matches = re.findall(r'R\$\s*(\d+[.,]\d+)\s*por\s*cota', texto, re.IGNORECASE)
        if len(matches) >= 2:
            if ind["cota_mercado"] is None:
                ind["cota_mercado"] = _validar("cota_mercado", _num(matches[0]))
            if ind["cota_patrimonial"] is None:
                ind["cota_patrimonial"] = _validar("cota_patrimonial", _num(matches[1]))

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

    # DY a.a. explícito. O DY mensal, quando possível, é calculado por
    # rendimento/cota de mercado ao fim da extração.
    if ind["dy_anual"] is None:
        matches = re.findall(
            r'DY\s+a\.?a\.?\s+de\s+(\d{1,2}[.,]\d{1,2})\s*%',
            texto, re.IGNORECASE
        )
        if matches:
            # usa o primeiro (mais recente no relatório)
            ind["dy_anual"] = _validar("dy_anual", _num(matches[0]))

    # Número de cotas — qualquer formato xxx.xxx.xxx próximo de palavras-chave
    if ind["num_cotas"] is None:
        m = re.search(
            r'(?:n[úu]mero\s+de\s+cotas?|cotas?\s+emitidas?|quantidade\s+de\s+cotas?).{0,160}?(\d{1,3}(?:\.\d{3}){2,})',
            texto, re.IGNORECASE | re.DOTALL
        )
        if m:
            ind["num_cotas"] = _validar("num_cotas", _num(m.group(1)))

    if ind["cota_patrimonial"] is None and ind["valor_patrimonial_bi"] and ind["num_cotas"]:
        cota = ind["valor_patrimonial_bi"] * 1_000_000_000 / ind["num_cotas"]
        ind["cota_patrimonial"] = _validar("cota_patrimonial", cota)

    if ind["cota_mercado"] is None and ind["valor_mercado_bi"] and ind["num_cotas"]:
        cota = ind["valor_mercado_bi"] * 1_000_000_000 / ind["num_cotas"]
        ind["cota_mercado"] = _validar("cota_mercado", cota)

    if ind["num_cotas"] is None and ind["valor_mercado_bi"] and ind["cota_mercado"]:
        cotas = ind["valor_mercado_bi"] * 1_000_000_000 / ind["cota_mercado"]
        ind["num_cotas"] = _validar("num_cotas", cotas)

    if ind["num_cotas"] is None and ind["valor_patrimonial_bi"] and ind["cota_patrimonial"]:
        cotas = ind["valor_patrimonial_bi"] * 1_000_000_000 / ind["cota_patrimonial"]
        ind["num_cotas"] = _validar("num_cotas", cotas)

    if ind["valor_patrimonial_bi"] is None and ind["num_cotas"] and ind["cota_patrimonial"]:
        valor = ind["num_cotas"] * ind["cota_patrimonial"] / 1_000_000_000
        ind["valor_patrimonial_bi"] = _validar("valor_patrimonial_bi", valor)

    if ind["ultimo_rendimento"] and ind["cota_mercado"]:
        if ind["ultimo_rendimento"] > ind["cota_mercado"] * 0.5:
            ind["ultimo_rendimento"] = None

    if ind["pvp"] is None and ind["cota_mercado"] and ind["cota_patrimonial"]:
        ind["pvp"] = _validar("pvp", ind["cota_mercado"] / ind["cota_patrimonial"])

    if ind["dy_mensal"] is None and ind["ultimo_rendimento"] and ind["cota_mercado"]:
        dy_calc = (ind["ultimo_rendimento"] / ind["cota_mercado"]) * 100
        ind["dy_mensal"] = _validar("dy_mensal", dy_calc)

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
6. PROIBIDO procurar informações na internet. Use APENAS o texto fornecido.

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
    if os.getenv("USAR_IA_EXTRACAO", "0") == "1":
        indicadores = _extrair_via_ia(texto, indicadores)
    tipo = detectar_tipo_fundo_detalhado(texto)
    indicadores["tipo_fundo"] = tipo["tipo_fundo"]
    indicadores["tipo_confianca"] = tipo["confianca"]
    indicadores["tipo_evidencias"] = tipo["evidencias"]
    return indicadores
