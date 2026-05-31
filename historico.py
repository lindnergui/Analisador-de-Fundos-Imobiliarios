import json
import os
from datetime import datetime

HISTORICO_DIR = "historico"

def salvar_analise(ticker: str, dados_extraidos: dict, analise_ia: str):
    os.makedirs(HISTORICO_DIR, exist_ok=True)
    caminho = os.path.join(HISTORICO_DIR, f"{ticker}.json")

    historico = []
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            historico = json.load(f)

    entrada = {
        "data": datetime.now().isoformat(),
        "indicadores": dados_extraidos,
        "analise": analise_ia
    }
    historico.append(entrada)

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)

    print(f"Histórico de {ticker} salvo com {len(historico)} entrada(s).")


def carregar_historico(ticker: str) -> list:
    caminho = os.path.join(HISTORICO_DIR, f"{ticker}.json")
    if not os.path.exists(caminho):
        return []
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def ticker_existe(ticker: str) -> bool:
    """Verifica se há histórico salvo para este ticker."""
    caminho = os.path.join(HISTORICO_DIR, f"{ticker}.json")
    return os.path.exists(caminho)


def tem_analise_este_mes(ticker: str) -> bool:
    """Verifica se há análise do mês/ano atual para este ticker."""
    historico = carregar_historico(ticker)
    if not historico:
        return False

    ultima_analise = historico[-1]
    ultima_data = datetime.fromisoformat(ultima_analise["data"])
    hoje = datetime.now()

    return (ultima_data.year == hoje.year and
            ultima_data.month == hoje.month)