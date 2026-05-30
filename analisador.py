import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)


def analisar_fii(ticker: str, texto_pdf: str, indicadores: dict, historico: list) -> str:
    historico_str = ""
    if historico:
        ultimas = historico[-3:]
        historico_str = f"""
## Histórico das últimas {len(ultimas)} análises:
{json.dumps(ultimas, ensure_ascii=False, indent=2)}
"""
    tipo = indicadores.get("tipo_fundo", "desconhecido")

    if tipo == "papel":
        foco_analise = """
Este é um FUNDO DE PAPEL (CRIs/LCIs). Foque em:
- Adimplência da carteira de crédito (crítico)
- Qualidade dos devedores e garantias
- Sensibilidade à taxa de juros (duration, marcação a mercado)
- Resultado vs. distribuição (sustentabilidade do dividendo)
- NÃO mencione vacância física — não se aplica
"""
    elif tipo == "tijolo":
        foco_analise = """
Este é um FUNDO DE TIJOLO (imóveis físicos). Foque em:
- Vacância física e financeira (crítico)
- Qualidade e diversificação dos inquilinos
- Vencimento dos contratos de locação
- Cap rate implícito e P/VP
"""
    elif tipo == "hibrido":
        foco_analise = """
Este é um FUNDO HÍBRIDO. Analise:
- Imóveis físicos: vacância, inquilinos, contratos
- Recebíveis: adimplência, qualidade de crédito
- Equilíbrio entre as duas carteiras
"""
    else:
        foco_analise = "Analise todos os indicadores disponíveis."
    prompt = f"""Você é um analista especializado em Fundos de Investimento Imobiliário (FIIs) brasileiro.

    ## Tipo do fundo: {tipo.upper()}
{foco_analise}

## REGRAS CRÍTICAS:
1. Use SOMENTE os dados fornecidos abaixo. NUNCA invente ou assuma números.
2. Se um indicador estiver como null, diga explicitamente que não foi encontrado no relatório.
3. Base toda recomendação nos números extraídos, com raciocínio explícito.

## Ticker analisado: {ticker}

## Indicadores extraídos automaticamente do PDF:
{json.dumps(indicadores, ensure_ascii=False, indent=2)}

## Texto completo do relatório (para contexto qualitativo):
{texto_pdf[:12000]}

{historico_str}

## Sua análise deve conter:

### 1. PONTOS FORTES
### 2. PONTOS FRACOS / RISCOS
### 3. ANÁLISE DOS INDICADORES
### 4. TENDÊNCIA (se houver histórico)
### 5. RECOMENDAÇÃO FINAL: CONTINUAR / REDUZIR / VENDER

Seja direto. Justifique tudo com os números fornecidos."""

    resposta = client.chat.completions.create(
        model="google/gemma-3-27b-it:freeze-v0.1",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
    )

    return resposta.choices[0].message.content