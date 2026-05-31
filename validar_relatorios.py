import sys

from extrator import extrair_indicadores_chave, extrair_texto_completo
from score import avaliar_pontuacao


CAMPOS = [
    "tipo_fundo",
    "tipo_confianca",
    "dy_mensal",
    "dy_anual",
    "cota_mercado",
    "cota_patrimonial",
    "pvp",
    "ultimo_rendimento",
    "resultado_mensal",
    "num_cotas",
    "valor_mercado_bi",
    "valor_patrimonial_bi",
    "taxa_liquida_ipca",
    "adimplencia",
    "vacancia",
    "area_total",
]


def main(paths: list[str]) -> None:
    if not paths:
        print("Uso: python validar_relatorios.py <relatorio1.pdf> [relatorio2.pdf ...]")
        return

    for path in paths:
        dados = extrair_texto_completo(path)
        indicadores = extrair_indicadores_chave(dados["texto_completo"])
        pontuacao = avaliar_pontuacao(indicadores)

        print(f"\n=== {path} ===")
        print(
            f"paginas={len(dados['texto_por_pagina'])} "
            f"tabelas={len(dados['tabelas'])} "
            f"chars={len(dados['texto_completo'])}"
        )
        print(
            f"score: {pontuacao['percentual']:.1f}% "
            f"({pontuacao['total']}/{pontuacao['max']}) - {pontuacao['conceito']}"
        )
        for campo in CAMPOS:
            print(f"{campo}: {indicadores.get(campo)}")


if __name__ == "__main__":
    main(sys.argv[1:])
