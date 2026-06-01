import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich import box
from rich.rule import Rule
from rich.bar import Bar

from core.extrator import extrair_texto_completo, extrair_indicadores_chave
from core.analisador import analisar_fii
from historico.historico import salvar_analise, carregar_historico, ticker_existe, tem_analise_este_mes
from core.analisa_enriquecida import calcular_metricas_derivadas, exibir_metricas_console
from core.score import avaliar_pontuacao

console = Console()


def exibir_banner():
    banner = Text()
    banner.append("FII", style="bold green")
    banner.append(" Analyzer", style="bold white")
    banner.append(" — Análise Inteligente de Fundos Imobiliários", style="dim")
    console.print(Panel(banner, border_style="green", padding=(1, 4)))


def exibir_indicadores(indicadores: dict, ticker: str):
    table = Table(
        title=f"📊 Indicadores Extraídos — {ticker}",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold cyan",
        show_lines=True,
    )

    table.add_column("Indicador", style="bold white", min_width=22)
    table.add_column("Valor", justify="right", min_width=16)
    table.add_column("Status", justify="center", min_width=10)

    labels = {
        "dy_mensal":          "DY Mensal (%)",
        "dy_anual":           "DY Anual (%)",
        "pvp":                "P/VP",
        "cota_patrimonial":   "Cota Patrimonial (R$)",
        "ultimo_rendimento":  "Último Rendimento (R$)",
        "vacancia":           "Vacância (%)",
        "area_total":         "Área Total (m²)",
        "num_cotas":          "Nº de Cotas",
    }

    alertas = {
        "dy_mensal": lambda v: ("green" if v and v > 0.5 else "yellow"),
        "vacancia":  lambda v: ("red" if v and v > 20 else "green"),
        "pvp":       lambda v: ("green" if v and v < 1 else "yellow"),
    }

    # trata tipo_fundo separadamente com cor
    tipo = indicadores.get("tipo_fundo", "desconhecido")
    cores_tipo = {
        "papel":       "cyan",
        "tijolo":      "yellow",
        "hibrido":     "magenta",
        "fof":         "blue",
        "desconhecido":"dim"
    }
    cor_tipo = cores_tipo.get(tipo, "white")
    confianca = indicadores.get("tipo_confianca")
    if confianca is not None:
        valor_tipo = f"[{cor_tipo}]{tipo.upper()}[/{cor_tipo}] [dim]({confianca:.0%})[/dim]"
    else:
        valor_tipo = f"[{cor_tipo}]{tipo.upper()}[/{cor_tipo}]"
    table.add_row("Tipo do Fundo", valor_tipo, "🏷️")

    evidencias = indicadores.get("tipo_evidencias") or []
    if evidencias:
        table.add_row("Evidência do Tipo", f"[dim]{evidencias[0]}[/dim]", "🔎")

    for chave, label in labels.items():
        valor = indicadores.get(chave)
        if valor is not None:
            cor = alertas.get(chave, lambda v: "white")(valor)
            table.add_row(label, f"[{cor}]{valor}[/{cor}]", "✅")
        else:
            table.add_row(label, "[dim]—[/dim]", "[red]❌[/red]")

    console.print()
    console.print(table)
    console.print()


def exibir_pontuacao(pontuacao: dict, ticker: str):
    cor = pontuacao["cor"]
    percentual = pontuacao["percentual"]

    resumo = Text()
    resumo.append(f"{pontuacao['conceito']} ", style=f"bold {cor}")
    resumo.append(f"({pontuacao['total']}/{pontuacao['max']} pts · {percentual:.1f}%)", style="white")

    console.print(Panel(
        Bar(size=100, begin=0, end=percentual, width=40, color=cor),
        title=f"[bold {cor}]Pontuação Conservadora — {ticker}[/bold {cor}]",
        subtitle=resumo,
        border_style=cor,
        padding=(1, 2),
    ))

    table = Table(
        title="Fatores Pontuados",
        box=box.ROUNDED,
        border_style=cor,
        header_style=f"bold {cor}",
        show_lines=True,
    )
    table.add_column("Fator", style="bold white", min_width=24)
    table.add_column("Pontos", justify="right", min_width=10)
    table.add_column("Detalhe", style="white")

    for item in pontuacao["itens"]:
        pontos = item["pontos"]
        maximo = item["max"]
        item_cor = "green" if pontos >= maximo * 0.75 else "yellow" if pontos > 0 else "red"
        table.add_row(
            item["fator"],
            f"[{item_cor}]{pontos}/{maximo}[/{item_cor}]",
            item["detalhe"],
        )

    console.print(table)
    console.print()


def exibir_analise(analise: str, ticker: str):
    console.print(Rule(f"[bold green] Análise IA — {ticker} [/bold green]", style="green"))
    console.print()

    secoes = {
        "PONTOS FORTES": ("green", "💪"),
        "PONTOS FRACOS": ("red", "⚠️"),
        "RISCOS": ("red", "⚠️"),
        "ANÁLISE DOS INDICADORES": ("cyan", "📈"),
        "TENDÊNCIA": ("yellow", "📉"),
        "RECOMENDAÇÃO FINAL": ("bold magenta", "🎯"),
    }

    linhas = analise.split("\n")
    secao_atual = None
    buffer = []

    def flush_buffer(secao, buf):
        if not buf:
            return
        cor, emoji = secoes.get(secao, ("white", "•"))
        conteudo = "\n".join(buf).strip()
        if conteudo:
            console.print(Panel(
                conteudo,
                title=f"{emoji} {secao}",
                border_style=cor,
                padding=(0, 2),
            ))
            console.print()

    for linha in linhas:
        linha_upper = linha.upper().strip().lstrip("#").strip()
        encontrou = False
        for chave in secoes:
            if chave in linha_upper:
                flush_buffer(secao_atual, buffer)
                secao_atual = chave
                buffer = []
                encontrou = True
                break
        if not encontrou and secao_atual:
            # limpa markdown básico
            linha_limpa = linha.replace("**", "").replace("*", "•").strip()
            if linha_limpa:
                buffer.append(linha_limpa)

    flush_buffer(secao_atual, buffer)


def extrair_recomendacao(analise: str):
    recomendacao = "—"
    for linha in analise.split("\n"):
        l = linha.upper()
        if "CONTINUAR" in l:
            recomendacao = "✅ CONTINUAR"
            break
        elif "REDUZIR" in l:
            recomendacao = "⚠️  REDUZIR"
            break
        elif "VENDER" in l:
            recomendacao = "🔴 VENDER"
            break
    return recomendacao


def exibir_resumo_final(ticker: str, indicadores: dict, analise: str, pontuacao: dict):
    recomendacao = "—"
    cor_rec = "white"
    for linha in analise.split("\n"):
        l = linha.upper()
        if "CONTINUAR" in l:
            recomendacao = "✅ CONTINUAR"
            cor_rec = "bold green"
            break
        elif "REDUZIR" in l:
            recomendacao = "⚠️  REDUZIR"
            cor_rec = "bold yellow"
            break
        elif "VENDER" in l:
            recomendacao = "🔴 VENDER"
            cor_rec = "bold red"
            break

    dy = indicadores.get("dy_mensal")
    vac = indicadores.get("vacancia")
    pvp = indicadores.get("pvp")

    resumo = Table(box=box.SIMPLE_HEAVY, border_style="magenta", show_header=False)
    resumo.add_column("Campo", style="dim", min_width=20)
    resumo.add_column("Valor", style="bold white")

    resumo.add_row("Ticker", f"[bold cyan]{ticker}[/bold cyan]")
    resumo.add_row("DY Mensal", f"[green]{dy}%[/green]" if dy else "[dim]n/d[/dim]")
    resumo.add_row("Vacância", f"[red]{vac}%[/red]" if vac else "[dim]n/d[/dim]")
    resumo.add_row("P/VP", str(pvp) if pvp else "[dim]n/d[/dim]")
    resumo.add_row("Score", f"[{pontuacao['cor']}]{pontuacao['percentual']:.1f}% · {pontuacao['conceito']}[/{pontuacao['cor']}]")
    resumo.add_row("Recomendação", f"[{cor_rec}]{recomendacao}[/{cor_rec}]")

    console.print(Panel(resumo, title="[bold magenta]📋 Resumo Final[/bold magenta]",
                        border_style="magenta", padding=(1, 2)))


def processar_fii(pdf_path: str, ticker: str) -> dict:
    dados = extrair_texto_completo(pdf_path)
    indicadores = extrair_indicadores_chave(dados["texto_completo"])
    pontuacao = avaliar_pontuacao(indicadores)

    tipo_fundo = indicadores.get("tipo_fundo", "desconhecido")
    metricas_derivadas = calcular_metricas_derivadas(indicadores, tipo_fundo)

    historico = carregar_historico(ticker)
    novo_ticker = not ticker_existe(ticker)

    incluir_tendencia = not novo_ticker
    indicadores["pontuacao"] = pontuacao
    analise = analisar_fii(ticker, dados["texto_completo"], indicadores, historico, incluir_tendencia=incluir_tendencia)

    salvar_analise(ticker, indicadores, analise)

    import os
    os.makedirs("relatorios", exist_ok=True)
    with open(f"relatorios/{ticker}_analise.txt", "w", encoding="utf-8") as f:
        f.write(analise)

    recomendacao = extrair_recomendacao(analise)

    return {
        "ticker": ticker,
        "indicadores": indicadores,
        "pontuacao": pontuacao,
        "metricas_derivadas": metricas_derivadas,
        "tipo_fundo": tipo_fundo,
        "analise": analise,
        "recomendacao": recomendacao,
        "novo_ticker": novo_ticker,
        "relatorio_path": f"relatorios/{ticker}_analise.txt"
    }


def main(pdf_path: str, ticker: str):
    exibir_banner()

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        t1 = progress.add_task("Extraindo e analisando PDF...", total=None)
        resultado = processar_fii(pdf_path, ticker)
        progress.remove_task(t1)

    indicadores = resultado["indicadores"]
    pontuacao = resultado["pontuacao"]
    metricas_derivadas = resultado["metricas_derivadas"]
    tipo_fundo = resultado["tipo_fundo"]
    analise = resultado["analise"]

    exibir_indicadores(indicadores, ticker)
    exibir_pontuacao(pontuacao, ticker)

    tabela_metricas = exibir_metricas_console(indicadores, metricas_derivadas, tipo_fundo)
    console.print(tabela_metricas)

    exibir_analise(analise, ticker)
    exibir_resumo_final(ticker, indicadores, analise, pontuacao)

    console.print(Rule(style="dim"))
    console.print(f"[dim]✅ Histórico salvo · Relatório em [cyan]{resultado['relatorio_path']}[/cyan][/dim]")
    console.print()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        console.print(Panel(
            "[bold]Uso:[/bold] python main.py [cyan]<caminho_pdf>[/cyan] [green]<TICKER>[/green]\n"
            "[dim]Ex:  python main.py relatorios/hglg11.pdf HGLG11[/dim]",
            title="❓ Como usar",
            border_style="yellow"
        ))
    else:
        main(sys.argv[1], sys.argv[2])
