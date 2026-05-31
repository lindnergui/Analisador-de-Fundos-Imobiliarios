# FII Analyzer 🏢

**Análise Inteligente de Fundos Imobiliários Brasileiros**

Um analisador robusto que extrai indicadores financeiros de relatórios PDF de FIIs, avalia pontuação conservadora e gera análises IA contextualizadas.

## ⚡ Começo Rápido

### Instalação

```bash
pip install -r requirements.txt
```

### 🌐 Interface Web (Recomendado)

Para usuários não-técnicos, use a interface Streamlit:

```bash
streamlit run app.py
```

Acesse `http://localhost:8501` no navegador e:
1. Faça upload do PDF
2. Informe o ticker
3. Clique "Analisar"

### 💻 Interface CLI (Terminal)

Para usuários avançados:

```bash
python main.py <caminho_pdf> <TICKER>
```

Exemplo:
```bash
python main.py relatorios/hglg11.pdf HGLG11
```

## 📊 Funcionalidades

### Extração de Indicadores
- DY Mensal e Anual
- P/VP (Preço/Valor Patrimonial)
- Cota Patrimonial
- Vacância (para FIIs de tijolo)
- Área Total
- Número de Cotas

### Análise IA
- Detecção automática de tipo de fundo (papel, tijolo, híbrido, FoF)
- Análise contextualizada por tipo
- Pontos fortes e fracos
- Identificação de riscos
- Tendência baseada em histórico
- Recomendação final (Continuar/Reduzir/Vender)

### Pontuação Conservadora
Sistema de scoring com até 100 pontos, avaliando:
- P/VP (relação preço/valor)
- DY (rentabilidade)
- Cobertura de dividendos
- Vacância
- Tamanho do fundo

### Histórico
- Rastreamento de análises por ticker
- Detecção de duplicatas (mesma análise no mês)
- Análise de tendências ao longo do tempo

## 📁 Estrutura

```
├── main.py                    # Orquestrador CLI + funções core
├── app.py                     # Interface Streamlit
├── extrator.py               # Extração de texto e indicadores
├── analisador.py             # Análise com IA (OpenRouter)
├── analisa_enriquecida.py    # Cálculo de métricas derivadas
├── score.py                  # Sistema de pontuação
├── historico.py              # Persistência e histórico
├── relatorios/               # Relatórios gerados (TXT)
├── historico/                # Histórico de análises (JSON)
└── requirements.txt          # Dependências
```

## 🔧 Configuração

### Variáveis de Ambiente

Crie um arquivo `.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-seu-token-aqui
USAR_IA_EXTRACAO=0  # 1 para usar IA na extração complementar
```

**Obtenha sua chave em**: https://openrouter.ai

## 🎯 Fluxo de Processamento

```
PDF → Extração (texto + tabelas)
  ↓
Indicadores (regex + IA opcional)
  ↓
Tipo do Fundo (papel/tijolo/híbrido/fof)
  ↓
Métricas Derivadas (cap rate, cobertura, etc)
  ↓
Pontuação Conservadora (0-100)
  ↓
Análise IA (OpenRouter Gemma 27B)
  ↓
Recomendação + Histórico
```

## 📝 Exemplos de Uso

### Interface Web
```bash
streamlit run app.py
# Abra http://localhost:8501
# Upload do PDF e clique "Analisar"
```

### Interface CLI
```bash
python main.py relatorios/hglg11.pdf HGLG11
# Saída formatada no terminal
# Relatório salvo em relatorios/HGLG11_analise.txt
```

## 🔍 Tipos de FIIs Suportados

| Tipo | Características | Análise Focada |
|------|-----------------|---|
| **Papel** | CRIs, LCIs, créditos | Adimplência, spread, duration |
| **Tijolo** | Imóveis físicos | Vacância, contratos, cap rate |
| **Híbrido** | Mix papel + tijolo | Análise combinada |
| **FoF** | Fundo de fundos | Diversificação, desconto/prêmio |

## 📈 Saída

### Relatório Web (Streamlit)
- Visualização interativa com abas
- Métricas em cards
- Gráficos de pontuação
- Download do relatório completo

### Relatório CLI (Terminal)
- Tabelas formatadas com Rich
- Análise em painéis coloridos
- Código de cores por criticidade

### Arquivo de Texto
Salvo em `relatorios/TICKER_analise.txt` com análise completa

## ⚙️ Requisitos

- Python 3.10+
- Dependências: `pdfplumber`, `openai`, `python-dotenv`, `rich`, `streamlit`
- Chave de API: OpenRouter
- Acesso à internet (para chamadas à IA)

## 🚨 Limitações

- Análise requer conexão com OpenRouter API
- Duplicatas no mesmo mês são descartadas automaticamente
- PDFs muito grandes podem demorar (timeout configurável)
- Extração depende da estrutura do relatório PDF

## 📜 Licença

Uso pessoal e educacional

---

**Última atualização**: 2026-05-31
