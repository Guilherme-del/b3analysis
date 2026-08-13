#!/usr/bin/env python3
"""
scanner_dividendos.py — Scanner de dividendos B3 (metodologia Barsi/Bazin)

Universo: Bancos, Energia Eletrica, Saneamento, Seguros, Telecomunicacoes + FIIs opcionais.

Criterio de "barato":
  Preco-teto Bazin = dividendo_medio_anual_5anos / 0.06
  Margem de seguranca = (preco_teto / preco_atual - 1) * 100

Execucao:
  bash run.sh scanner_dividendos.py             # acoes + FIIs
  bash run.sh scanner_dividendos.py --so-acoes  # apenas acoes B.E.S.T.
  bash run.sh scanner_dividendos.py --so-fiis   # apenas FIIs
"""

import sys
import os
import time
import json
from datetime import datetime

# Garante UTF-8 no console Windows sem quebrar outros terminais
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Erro: instale as dependencias com: bash run.sh --install")
    print("Ou: pip install yfinance pandas")
    sys.exit(1)

# ── Universo de ativos ───────────────────────────────────────────────────────

ACOES = {
    "Bancos": [
        "BBAS3.SA",   # Banco do Brasil (ON)
        "ITUB3.SA",   # Itau Unibanco (ON)
        "ITUB4.SA",   # Itau Unibanco (PN) — alto DY historico
        "BBDC4.SA",   # Bradesco (PN) — predileto do Barsi
        "SANB11.SA",  # Santander Brasil (Unit)
        "BRSR6.SA",   # Banrisul (PN classe B) — estatal do RS
        "ITSA4.SA",   # Itausa (PN)
        "BNBR3.SA",   # Banco do Nordeste (ON)
    ],
    "Energia Eletrica": [
        "TAEE11.SA",  # Taesa (Unit)
        "EGIE3.SA",   # Engie Brasil (ON)
        "ISAE4.SA",   # ISA Energia Brasil — ex-TRPL4, migrado nov/2024 (PN)
        "CPLE3.SA",   # Copel (ON) — privatizada 2023, CPLE6 descontinuado no yfinance
        "ENGI11.SA",  # Energisa (Unit)
        "CPFE3.SA",   # CPFL Energia (ON)
        "AURE3.SA",   # Auren Energia (ON)
    ],
    "Saneamento": [
        "CSMG3.SA",   # COPASA (ON)
        "SAPR3.SA",   # Sanepar (ON)
        "SAPR11.SA",  # Sanepar (Unit)
        "SBSP3.SA",   # SABESP (ON)
    ],
    "Seguros": [
        "BBSE3.SA",   # BB Seguridade (ON)
        "PSSA3.SA",   # Porto Seguro (ON)
        "CXSE3.SA",   # Caixa Seguridade (ON)
    ],
    "Telecomunicacoes": [
        "VIVT3.SA",   # Telefonica Brasil / Vivo (ON)
        "TIMS3.SA",   # TIM Brasil (ON)
    ],
    # ── Fora do B.E.S.T. — universo B3 ampliado, apenas ON (final 3) ──────────
    # O criterio 2 do checklist e eliminatorio, entao nao ha razao para gastar
    # requisicao em PN/unit de setores que nao sao o foco da estrategia.
    "Varejo": [
        "LREN3.SA", "VULC3.SA", "PNVL3.SA", "VIVA3.SA", "GRND3.SA",
    ],
    "Saude": [
        "FLRY3.SA", "HAPV3.SA", "RDOR3.SA", "HYPE3.SA", "ODPV3.SA",
    ],
    "Tecnologia": [
        "TOTS3.SA", "INTB3.SA",
    ],
    "Industrial": [
        "WEGE3.SA", "ROMI3.SA", "FRAS3.SA", "LEVE3.SA",
    ],
    "Farmacias": [
        "RADL3.SA",
    ],
    "Petroleo": [
        "PETR3.SA", "PRIO3.SA", "RECV3.SA",
    ],
    "Mineracao e Siderurgia": [
        "VALE3.SA", "GOAU3.SA", "GGBR3.SA",
    ],
    "Agro": [
        "SLCE3.SA", "SMTO3.SA", "AGRO3.SA",
    ],
    "Logistica": [
        "RENT3.SA", "RAIL3.SA", "EMBR3.SA",
    ],
    "Construcao": [
        "DIRR3.SA", "CYRE3.SA",
    ],
    "Celulose": [
        "SUZB3.SA", "KLBN3.SA", "RANI3.SA",
    ],
    "Alimentos e Bebidas": [
        "ABEV3.SA", "JBSS3.SA", "MRFG3.SA", "MDIA3.SA",
    ],
    "Educacao": [
        "YDUQ3.SA",
    ],
    "Bolsa e Financeiro": [
        "B3SA3.SA", "CIEL3.SA",
    ],
}

FIIS = [
    # Logistica
    "HGLG11.SA",  # CSHG Logistica
    "BTLG11.SA",  # BTG Pactual Logistica
    "XPLG11.SA",  # XP Log
    "BRCO11.SA",  # Bresco Logistica
    "VILG11.SA",  # Vinci Logistica
    "TRXF11.SA",  # TRX Real Estate (logistica/renda urbana)
    # Hibrido / renda urbana
    "GARE11.SA",  # Guardian Real Estate (hibrido)
    # Shoppings
    "XPML11.SA",  # XP Malls
    "VISC11.SA",  # Vinci Shopping Centers
    "HSML11.SA",  # HSI Malls
    "HGBS11.SA",  # CSHG Brasil Shopping
    # Lajes corporativas
    "PVBI11.SA",  # VBI Prime Properties
    "RBRP11.SA",  # RBR Properties (lajes)
    # Papel / CRI
    "KNCR11.SA",  # Kinea Rendimentos Imobiliarios (CDI)
    "KNIP11.SA",  # Kinea Indice de Precos (IPCA+)
    "MXRF11.SA",  # Maxi Renda (CRI misto)
    "CPTS11.SA",  # Capitania Securities (CRI)
    "RECR11.SA",  # REC Recebiveis (CRI)
    # Fundo de fundos
    "BCFF11.SA",  # BC Fundo de Fundos
    # Renda urbana / hibrido
    "HGRU11.SA",  # CSHG Renda Urbana
    "RBRF11.SA",  # RBR Alpha (FoF)
]

BAZIN_MINIMA = 0.06   # Taxa minima de retorno para calculo do preco-teto (6% a.a.)
CDI_ATUAL    = 0.1389  # CDI atual (Selic meta 13,90% apos corte do Copom em 10/08/2026)

# Parametros do P/VP justificado — segundo eixo de desconto.
#   P/VP justo = (ROE - g) / (Ke - g)
# Uma empresa so merece negociar acima do valor patrimonial se o ROE supera o
# custo de capital. Sem esse ajuste, P/VP baixo e lido como promocao quando pode
# ser apenas o preco correto de um negocio que rende pouco: BBAS3 negocia a 0,58
# — parece o maior desconto da bolsa — mas com ROE de 9,2% o justo seria 0,35,
# ou seja, esta 66% CARO. O P/VP cru, sozinho, inverte o sinal nesses casos.
KE_EQUITY  = 0.17   # custo de capital proprio = CDI + ~3pp de premio de risco
G_PERPETUO = 0.05   # crescimento nominal de longo prazo (~IPCA + folga)

# Saida dos scans — relativa ao script, nao ao diretorio de onde foi invocado.
# Ignorada pelo git (ver .gitignore): sao snapshots de mercado, nao codigo.
SCANS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scans")


# ── Helpers de dividendo ─────────────────────────────────────────────────────

def _normalizar_index(series: pd.Series) -> pd.Series:
    """Remove timezone do index para uniformizar comparacoes."""
    if series.empty:
        return series
    if series.index.tz is not None:
        series = series.copy()
        series.index = series.index.tz_convert("UTC").tz_localize(None)
    return series


def _historico_dividendos(t: yf.Ticker) -> pd.Series:
    """Historico bruto de proventos, sem timezone. Vazio se indisponivel."""
    try:
        hist = t.dividends
        if hist is None or hist.empty:
            return pd.Series(dtype=float)
        return _normalizar_index(hist)
    except Exception:
        return pd.Series(dtype=float)


def _separar_extraordinarios(hist: pd.Series, fator: float = 3.0) -> tuple[pd.Series, float]:
    """
    Separa proventos extraordinarios dos ordinarios dentro da janela recebida.

    Um pagamento acima de `fator` x a mediana da janela e tratado como
    extraordinario. Sem esse filtro o metodo Bazin le liquidacao de balanco como
    dividendo recorrente — e o erro nao e teorico: GRND3 pagou R$1,0863/acao de
    uma vez em 29/12/2025 (R$979,9 mi), o que consumiu o caixa que gerava mais da
    metade do lucro da empresa. O scanner devolveu DY de 44,8% e margem de
    +353,9%, numeros aritmeticamente corretos e inuteis como sinal de
    recorrencia. Distribuicao extraordinaria e devolucao de capital, nao renda.

    Retorna (serie_so_ordinarios, fracao_do_total_que_era_extraordinaria).
    """
    if hist.empty:
        return hist, 0.0
    mediana = float(hist.median())
    if mediana <= 0:
        return hist, 0.0
    extraordinarios = hist > (fator * mediana)
    total = float(hist.sum())
    if total <= 0:
        return hist, 0.0
    fracao = float(hist[extraordinarios].sum()) / total
    return hist[~extraordinarios], fracao


def _dividendos_por_ano(hist: pd.Series) -> pd.Series:
    """Soma de proventos por ano-calendario."""
    if hist.empty:
        return pd.Series(dtype=float)
    return hist.groupby(hist.index.year).sum()


def _media_dividendo_5a(por_ano: pd.Series) -> float:
    """
    Media anual de dividendos dos ultimos 5 anos-calendario COMPLETOS.

    O ano corrente e excluido de proposito: incluir um ano parcial puxa a media
    para baixo e subestima o preco-teto (verificado: -30% em TAEE11, -22% em BBAS3).
    """
    if por_ano.empty:
        return 0.0
    ano_atual = pd.Timestamp.now().year
    # reindex preenche anos sem pagamento com zero. Sem isso, quem interrompeu
    # o dividendo tem a media calculada so sobre os anos bons — teto inflado
    # exatamente para o caso que o metodo mais quer excluir.
    completos = por_ano.reindex(range(ano_atual - 5, ano_atual), fill_value=0.0)
    return float(completos.mean())


def _anos_pagando(por_ano: pd.Series) -> int:
    """Anos-calendario completos com pagamento de dividendo nos ultimos 10 anos."""
    if por_ano.empty:
        return 0
    ano_atual = pd.Timestamp.now().year
    janela = por_ano[
        (por_ano.index >= ano_atual - 10) & (por_ano.index <= ano_atual - 1) & (por_ano > 0)
    ]
    return int(len(janela))


def _dy_ttm(hist: pd.Series, preco: float) -> float:
    """
    DY dos ultimos 12 meses, calculado do historico real de pagamentos.

    Nao usa info['dividendYield']: verificado que o campo e inconsistente entre
    tickers .SA (ITUB4 reportou 2.07 contra 8.16% real — erro de 4x).
    """
    if preco <= 0 or hist.empty:
        return 0.0
    ttm = float(hist[hist.index >= (pd.Timestamp.now() - pd.DateOffset(years=1))].sum())
    return (ttm / preco) * 100


def _pvp_justificado(roe: float | None) -> float | None:
    """
    P/VP justo pelo modelo de Gordon aplicado ao patrimonio: (ROE - g) / (Ke - g).

    Retorna None quando ROE <= g — nesse caso o negocio nao gera valor de
    perpetuidade e nenhum P/VP positivo se justifica, entao a razao nao tem
    significado. Nao aplicavel a FII (ROE nao tem sentido contabil ali; o FII e
    avaliado pelo P/VP direto contra o laudo dos imoveis).
    """
    if roe is None:
        return None
    justo = (roe - G_PERPETUO) / (KE_EQUITY - G_PERPETUO)
    return justo if justo > 0 else None


def _avaliar_qualidade(
    roe: float | None, payout: float | None, anos: int, pagou_ultimo_ano: bool = True,
    frac_extra: float = 0.0, em_queda: bool = False,
) -> list[str]:
    """
    Filtro de consistencia Barsi — aplicado ANTES do preco.
    Retorna lista de flags; lista vazia = passou.
    """
    flags = []
    if roe is not None and roe < 0:
        flags.append("ROE<0")
    if payout is not None and payout > 1.0:
        flags.append("PAYOUT>100%")
    if anos < 5:
        flags.append(f"SO {anos}a")
    # Pagamento interrompido e eliminatorio: quem tem historico mas nao pagou
    # no ultimo ano completo nao pode aparecer como oportunidade.
    if anos > 0 and not pagou_ultimo_ano:
        flags.append("SEM DIV ULT.ANO")
    # Distribuicao extraordinaria e devolucao de capital, nao renda. Acima de
    # 30% do total pago na janela, o DY deixa de descrever o que se repete —
    # GRND3 chegou a 70% e apareceu com DY de 44,8% e margem de +353,9%.
    if frac_extra > 0.30:
        flags.append(f"EXTRAORD {frac_extra*100:.0f}%")
    if em_queda:
        flags.append("DIV EM QUEDA")
    return flags


# ── Coleta ───────────────────────────────────────────────────────────────────

def fetch_ativo(ticker_symbol: str, setor: str, is_fii: bool = False) -> dict:
    """
    Coleta metricas Barsi/Bazin para um ativo.

    Acao e FII compartilham todo o pipeline de dividendos; a diferenca e que
    ROE/payout nao tem sentido contabil para FII (que e avaliado por P/VP),
    entao ficam fora do filtro de qualidade nesse caso.
    """
    base = {
        "ticker": ticker_symbol.replace(".SA", ""),
        "setor":  setor,
        "tipo":   "fii" if is_fii else "acao",
        "erro":   None,
    }
    try:
        t    = yf.Ticker(ticker_symbol)
        info = t.info or {}

        preco = (
            info.get("regularMarketPrice")
            or info.get("previousClose")
            or info.get("currentPrice")
            or 0.0
        )
        if not preco:
            base["erro"] = "sem preco de mercado"
            return base

        hist_bruto = _historico_dividendos(t)

        # Janela de 6 anos: cobre os 5 anos completos do Bazin mais o corrente,
        # que e onde a mediana de referencia precisa ser medida.
        janela = hist_bruto[hist_bruto.index >= (pd.Timestamp.now() - pd.DateOffset(years=6))]
        hist_ord, frac_extra = _separar_extraordinarios(janela)

        por_ano      = _dividendos_por_ano(hist_ord)
        div_medio_5a = _media_dividendo_5a(por_ano)
        dy_ttm_pct   = _dy_ttm(hist_ord, preco)
        # anos_div mede continuidade de pagamento, entao usa o historico bruto:
        # um ano em que so houve extraordinario ainda foi um ano com provento.
        anos_div     = _anos_pagando(_dividendos_por_ano(hist_bruto))

        corte_ttm = pd.Timestamp.now() - pd.DateOffset(years=1)
        div_ttm   = float(hist_ord[hist_ord.index >= corte_ttm].sum())

        # Cross-check de regime. A media de 5 anos olha para tras; se a empresa
        # mudou a politica de dividendos, o teto mira um passado que nao volta.
        # PETR3 pagou R$16,77/acao em 2022 e R$3,28 em 2025 — a media de 5 anos
        # produz teto de R$136 contra um teto real de ~R$50, erro de 17x na
        # margem. Usar o MENOR dos dois tetos e a leitura conservadora correta.
        em_queda = bool(div_medio_5a > 0 and div_ttm > 0 and div_medio_5a > 1.5 * div_ttm)
        div_base = min(div_medio_5a, div_ttm) if (div_medio_5a > 0 and div_ttm > 0) else div_medio_5a

        preco_teto = (div_base / BAZIN_MINIMA) if div_base > 0 else None
        teto_cdi   = (div_base / CDI_ATUAL)    if div_base > 0 else None
        margem_pct = ((preco_teto / preco - 1) * 100) if preco_teto else None
        margem_cdi = ((teto_cdi   / preco - 1) * 100) if teto_cdi   else None

        pvp    = info.get("priceToBook")
        roe    = None if is_fii else info.get("returnOnEquity")
        payout = None if is_fii else info.get("payoutRatio")

        # payout 0% com dividendo sendo pago e dado quebrado do yfinance, nao
        # payout real (visto em TAEE11: POUT 0% com DY 8%). Trata como ausente
        # para nao passar pelo filtro de qualidade disfarcado de dado valido.
        if payout == 0 and dy_ttm_pct > 0:
            payout = None

        ano_anterior   = pd.Timestamp.now().year - 1
        pagou_ult_ano  = bool(por_ano.get(ano_anterior, 0.0) > 0)

        pvp_justo = _pvp_justificado(roe)
        razao_pvp = (pvp / pvp_justo) if (pvp and pvp_justo) else None

        base.update({
            "nome":         (info.get("longName") or info.get("shortName") or "")[:42],
            "preco":        round(preco, 2),
            "div_medio_5a": round(div_medio_5a, 4),
            "dy_ttm_pct":   round(dy_ttm_pct, 2),
            "preco_teto":   round(preco_teto, 2) if preco_teto else None,
            "margem_pct":   round(margem_pct, 1) if margem_pct is not None else None,
            "teto_cdi":     round(teto_cdi, 2) if teto_cdi else None,
            "margem_cdi":   round(margem_cdi, 1) if margem_cdi is not None else None,
            "anos_div":     anos_div,
            "payout_pct":   round(payout * 100, 1) if payout is not None else None,
            "roe_pct":      round(roe * 100, 1) if roe is not None else None,
            "p_vp":         round(pvp, 2) if pvp else None,
            "pvp_justo":    round(pvp_justo, 2) if pvp_justo else None,
            "razao_pvp":    round(razao_pvp, 2) if razao_pvp else None,
            "is_on":        base["ticker"].endswith("3"),
            "frac_extra":   round(frac_extra, 3),
            "div_ttm":      round(div_ttm, 4),
            "div_em_queda": em_queda,
            "flags":        _avaliar_qualidade(roe, payout, anos_div, pagou_ult_ano,
                                               frac_extra, em_queda),
        })
    except Exception as e:
        base["erro"] = str(e)[:100]
    return base


# ── Formatacao do relatorio ──────────────────────────────────────────────────

def _status(margem: float | None, flags: list[str] | None) -> str:
    """
    Filtro de qualidade vem ANTES do preco (criterio Barsi): um ativo com ROE
    negativo, payout insustentavel ou historico curto e excluido independente
    de quao barato esteja — barato com fundamento ruim e armadilha de valor.
    """
    if flags:
        return "EXCLUIR"
    if margem is None:
        return "S/DADO"
    if margem >= 20:
        return "BARATO"
    if margem >= 0:
        return "OK"
    if margem >= -20:
        return "CARO"
    return "MUITO CARO"


# N/D so quando o dado nao existe. Zero e informacao (DY 0.0% = nao pagou nos
# ultimos 12m; 0a = nenhum ano completo com dividendo) e e exibido como numero.

def _linha_acao(r: dict) -> str:
    preco_s  = f"R${r['preco']:>8.2f}"
    teto_s   = f"R${r['preco_teto']:>8.2f}" if r.get("preco_teto") else "       N/D"
    margem_s = f"{r['margem_pct']:>+7.1f}%" if r.get("margem_pct") is not None else "     N/D"
    mcdi_s   = f"{r['margem_cdi']:>+7.1f}%" if r.get("margem_cdi") is not None else "     N/D"
    dy_s     = f"{r['dy_ttm_pct']:>5.1f}%" if r.get("dy_ttm_pct") is not None else "   N/D"
    anos_s   = f"{r['anos_div']:>2}a" if r.get("anos_div") is not None else "  -"
    roe_s    = f"{r['roe_pct']:>6.1f}%" if r.get("roe_pct") is not None else "    N/D"
    pout_s   = f"{r['payout_pct']:>5.0f}%" if r.get("payout_pct") is not None else "   N/D"
    # P/VP e o segundo eixo de desconto: teto Bazin mede barato por renda gerada,
    # P/VP mede barato por patrimonio. Os dois discordam com frequencia e a
    # discordancia e informativa — ver nota sobre setores na legenda.
    pvp_s    = f"{r['p_vp']:>6.2f}" if r.get("p_vp") else "   N/D"
    # Razao = P/VP de mercado / P/VP justificado pelo ROE. <=1 significa que o
    # mercado paga no maximo o que o retorno da empresa justifica.
    razao_s  = f"{r['razao_pvp']:>6.2f}" if r.get("razao_pvp") else "   N/D"
    st       = _status(r.get("margem_pct"), r.get("flags"))
    obs      = (" " + ",".join(r["flags"])) if r.get("flags") else ""
    return (
        f"  {r['ticker']:<9} {preco_s}  {dy_s}  {teto_s}  {margem_s}  {mcdi_s}  "
        f"{anos_s}  {roe_s}  {pout_s}  {pvp_s}  {razao_s}  {st:<11}{obs}"
    )


def _linha_fii(r: dict) -> str:
    preco_s  = f"R${r['preco']:>8.2f}"
    teto_s   = f"R${r['preco_teto']:>8.2f}" if r.get("preco_teto") else "       N/D"
    margem_s = f"{r['margem_pct']:>+7.1f}%" if r.get("margem_pct") is not None else "     N/D"
    mcdi_s   = f"{r['margem_cdi']:>+7.1f}%" if r.get("margem_cdi") is not None else "     N/D"
    dy_s     = f"{r['dy_ttm_pct']:>5.1f}%" if r.get("dy_ttm_pct") is not None else "   N/D"
    anos_s   = f"{r['anos_div']:>2}a" if r.get("anos_div") is not None else "  -"
    pvp_s    = f"{r['p_vp']:>6.2f}" if r.get("p_vp") else "   N/D"
    st       = _status(r.get("margem_pct"), r.get("flags"))
    obs      = (" " + ",".join(r["flags"])) if r.get("flags") else ""
    return (
        f"  {r['ticker']:<9} {preco_s}  {dy_s}  {teto_s}  {margem_s}  {mcdi_s}  "
        f"{anos_s}  {pvp_s}  {st:<11}{obs}"
    )


def _ordenar(registros: list[dict]) -> list[dict]:
    """Reprovados no filtro de qualidade vao para o fim, independente da margem."""
    return sorted(
        registros,
        key=lambda r: (bool(r.get("flags")), -(r.get("margem_pct") if r.get("margem_pct") is not None else -9999)),
    )


def formatar_relatorio(acoes: list[dict], fiis: list[dict]) -> str:
    ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    W  = 120
    linhas = []

    linhas.append("=" * W)
    linhas.append(f"  SCANNER DE DIVIDENDOS B3 — Barsi/Bazin  |  {ts}")
    linhas.append(f"  Setores: Bancos | Energia Eletrica | Saneamento | Seguros | Telecomunicacoes")
    linhas.append("=" * W)
    linhas.append("")
    linhas.append("  AVISO: Gerado por script automatizado para fins exclusivamente")
    linhas.append("  educacionais e de estudo pessoal. Nao constitui recomendacao")
    linhas.append("  de investimento ou consultoria financeira.")
    linhas.append("")
    linhas.append(
        f"  Parametros: Bazin = {BAZIN_MINIMA*100:.0f}% a.a. | "
        f"CDI benchmark = {CDI_ATUAL*100:.2f}% a.a. (Selic)"
    )
    linhas.append("")

    # ── Acoes por setor ──────────────────────────────────────────────────────
    if acoes:
        linhas.append("─" * W)
        linhas.append("  ACOES — B.E.S.T. (Barsi)  |  filtro de qualidade aplicado ANTES do preco")
        linhas.append("─" * W)

        por_setor: dict[str, list] = {}
        erros_acao: list[dict]     = []
        for r in acoes:
            if r.get("erro"):
                erros_acao.append(r)
            else:
                por_setor.setdefault(r["setor"], []).append(r)

        for setor, registros in por_setor.items():
            linhas.append(f"\n  [{setor}]")
            linhas.append(
                f"  {'TICKER':<9} {'PRECO':>10}  {'DY':>6}  {'TETO 6%':>10}  {'MARG 6%':>8}  "
                f"{'MARG CDI':>8}  {'DIV':>3}  {'ROE':>7}  {'POUT':>6}  {'P/VP':>6}  "
                f"{'RAZAO':>6}  STATUS"
            )
            linhas.append("  " + "-" * (W - 2))
            for r in _ordenar(registros):
                linhas.append(_linha_acao(r))

        if erros_acao:
            linhas.append("\n  Falhas na coleta:")
            for r in erros_acao:
                linhas.append(f"    {r['ticker']:<10} {r['erro']}")

        linhas.append("")

    # ── FIIs ─────────────────────────────────────────────────────────────────
    if fiis:
        linhas.append("─" * W)
        linhas.append("  FIIs — DY real (TTM) + P/VP + teto Bazin 6% vs teto CDI")
        linhas.append("─" * W)

        fiis_ok  = [r for r in fiis if not r.get("erro")]
        fiis_err = [r for r in fiis if r.get("erro")]

        linhas.append(
            f"\n  {'TICKER':<9} {'PRECO':>10}  {'DY':>6}  {'TETO 6%':>10}  {'MARG 6%':>8}  "
            f"{'MARG CDI':>8}  {'DIV':>3}  {'P/VP':>6}  STATUS"
        )
        linhas.append("  " + "-" * (W - 2))
        for r in _ordenar(fiis_ok):
            linhas.append(_linha_fii(r))

        if fiis_err:
            linhas.append("\n  Falhas na coleta:")
            for r in fiis_err:
                linhas.append(f"    {r['ticker']:<10} {r['erro']}")

        linhas.append("")

    # ── Aprovados ────────────────────────────────────────────────────────────
    # Secao final: o que sobra depois de TODOS os filtros. E o unico bloco que
    # responde "o que compensa comprar" — o resto do relatorio e o memorial de
    # calculo. Acao e FII usam testes patrimoniais diferentes de proposito:
    # acao passa pelo ROE (P/VP justificado), FII compara direto com o laudo.
    aprov_acoes = [
        r for r in acoes
        if not r.get("erro") and not r.get("flags") and r.get("is_on")
        and (r.get("margem_pct") or -99) > 0
        and r.get("razao_pvp") is not None and r["razao_pvp"] <= 1.10
    ]
    aprov_fiis = [
        r for r in fiis
        if not r.get("erro") and not r.get("flags")
        and (r.get("margem_pct") or -99) > 0
        and (r.get("p_vp") is None or r["p_vp"] <= 1.00)
    ]

    linhas.append("═" * W)
    linhas.append("  APROVADOS — sobreviveram a todos os filtros")
    linhas.append("═" * W)
    linhas.append("")
    linhas.append("  ACOES   filtro: ON (final 3) + margem 6% positiva + sem flag + P/VP <= justificado")
    if aprov_acoes:
        linhas.append(f"\n  {'TICKER':<9} {'SETOR':<22} {'PRECO':>9}  {'DY':>6}  {'MARG':>7}  "
                      f"{'ROE':>7}  {'P/VP':>6}  {'JUSTO':>6}  {'RAZAO':>6}")
        linhas.append("  " + "-" * (W - 2))
        for r in sorted(aprov_acoes, key=lambda x: x["razao_pvp"]):
            linhas.append(
                f"  {r['ticker']:<9} {r['setor']:<22} R${r['preco']:>7.2f}  "
                f"{r['dy_ttm_pct']:>5.1f}%  {r['margem_pct']:>+6.1f}%  {r['roe_pct']:>6.1f}%  "
                f"{r['p_vp']:>6.2f}  {r['pvp_justo']:>6.2f}  {r['razao_pvp']:>6.2f}"
            )
    else:
        linhas.append("\n    (nenhuma acao passou em todos os filtros)")

    linhas.append("")
    linhas.append("  FIIs    filtro: margem 6% positiva + sem flag + P/VP <= 1,00 (ou sem dado)")
    if aprov_fiis:
        linhas.append(f"\n  {'TICKER':<9} {'PRECO':>9}  {'DY':>6}  {'MARG':>7}  {'P/VP':>6}  "
                      f"{'DY s/VP':>8}")
        linhas.append("  " + "-" * (W - 2))
        for r in sorted(aprov_fiis, key=lambda x: -(x["margem_pct"] or 0)):
            pvp_s   = f"{r['p_vp']:>6.2f}" if r.get("p_vp") else "   N/D"
            dyvp_s  = f"{r['dy_ttm_pct'] * r['p_vp']:>7.2f}%" if r.get("p_vp") else "     N/D"
            linhas.append(
                f"  {r['ticker']:<9} R${r['preco']:>7.2f}  {r['dy_ttm_pct']:>5.1f}%  "
                f"{r['margem_pct']:>+6.1f}%  {pvp_s}  {dyvp_s}"
            )
    else:
        linhas.append("\n    (nenhum FII passou em todos os filtros)")

    linhas.append("")
    linhas.append("  Lembrete: margem CDI negativa em praticamente todo o universo significa que")
    linhas.append("  nenhum destes bate a renda fixa hoje pelo carrego isolado. Aprovado aqui quer")
    linhas.append("  dizer 'melhor dentro da renda variavel', nao 'melhor que a renda fixa'.")
    linhas.append("")

    # ── Legenda ──────────────────────────────────────────────────────────────
    linhas.append("─" * W)
    linhas.append("  Legenda:")
    linhas.append("  EXCLUIR    — reprovado no filtro de qualidade (ver flag ao lado) — nao comprar")
    linhas.append("  BARATO     — margem > +20% sobre o teto de 6% — zona de compra")
    linhas.append("  OK         — margem 0% a +20% — proximo do teto, aguardar queda")
    linhas.append("  CARO       — margem 0% a -20% — nao iniciar posicao")
    linhas.append("  MUITO CARO — margem < -20% — evitar")
    linhas.append("  S/DADO     — sem historico de dividendos disponivel no yfinance")
    linhas.append("")
    linhas.append("  Flags de qualidade (eliminatorias, aplicadas antes do preco):")
    linhas.append("    ROE<0        — prejuizo no patrimonio, nao sustenta dividendo")
    linhas.append("    PAYOUT>100%  — distribui mais do que lucra, insustentavel")
    linhas.append("    SO Na        — historico de dividendos menor que 5 anos completos")
    linhas.append("    SEM DIV ULT.ANO — nao pagou dividendo no ultimo ano-calendario completo")
    linhas.append("    EXTRAORD n%  — n% do que foi pago na janela veio de proventos extraordinarios")
    linhas.append("                   (pagamento > 3x a mediana). Extraordinario e devolucao de")
    linhas.append("                   capital, nao renda: GRND3 pagou R$979,9 mi de uma vez em")
    linhas.append("                   12/2025 consumindo o caixa que gerava metade do seu lucro,")
    linhas.append("                   e apareceu com DY de 44,8% e margem de +353,9%.")
    linhas.append("    DIV EM QUEDA — media de 5a > 1,5x o pago nos ultimos 12m. A empresa mudou")
    linhas.append("                   de politica e o teto olha para um passado que nao volta.")
    linhas.append("                   PETR3: R$16,77/acao em 2022 contra R$3,28 em 2025.")
    linhas.append("")
    linhas.append("  DY        = dividendos dos ultimos 12 meses / preco atual (calculado do")
    linhas.append("              historico real — o campo dividendYield do yfinance e inconsistente)")
    linhas.append("  TETO 6%   = dividendo-base / 0,06. O dividendo-base e o MENOR entre a media dos")
    linhas.append("              5 anos completos (Bazin classico, ja sem extraordinarios) e o pago")
    linhas.append("              nos ultimos 12 meses — a leitura conservadora quando os dois divergem.")
    linhas.append("  MARG 6%   = (teto 6% / preco - 1) x 100")
    linhas.append(f"  MARG CDI  = mesma conta usando {CDI_ATUAL*100:.2f}% (Selic) como taxa minima.")
    linhas.append("              Se MARG CDI for negativa, o ativo rende menos que a renda fixa hoje.")
    linhas.append("  DIV       = anos-calendario completos com dividendo (ultimos 10a)")
    linhas.append(f"  JUSTO     = P/VP justificado = (ROE - g) / (Ke - g), com Ke {KE_EQUITY*100:.0f}% e g {G_PERPETUO*100:.0f}%")
    linhas.append("  RAZAO     = P/VP de mercado / P/VP justificado. <=1,00 o mercado paga no maximo")
    linhas.append("              o que o ROE justifica; >1,50 esta caro mesmo com P/VP baixo. E este o")
    linhas.append("              numero que importa, nao o P/VP cru: BBAS3 negocia a P/VP 0,58 e parece")
    linhas.append("              o maior desconto da bolsa, mas com ROE de 9,2% o justo e 0,35 — razao")
    linhas.append("              1,66, ou seja, CARO. N/D quando ROE <= g (sem valor de perpetuidade).")
    linhas.append("  P/VP      = preco / valor patrimonial. Segundo eixo de desconto — o teto")
    linhas.append("              Bazin mede barato por RENDA gerada, o P/VP mede barato por")
    linhas.append("              PATRIMONIO. Quando os dois apontam desconto, o sinal e forte.")
    linhas.append("              Cuidado: P/VP so e comparavel dentro do mesmo setor. Bancos tem")
    linhas.append("              patrimonio contabil que reflete capital real (P/VP e confiavel);")
    linhas.append("              transmissoras e concessoes amortizam o ativo e naturalmente ficam")
    linhas.append("              com P/VP alto; holdings asset-light (BBSE3) tornam o P/VP inutil.")
    linhas.append("  POUT N/D  = payout ausente no yfinance, ou 0% com dividendo pago (dado quebrado)")
    linhas.append("")
    linhas.append("  Nota: o ano corrente e excluido da media (ano parcial subestima o teto)")
    linhas.append("        e anos sem pagamento dentro da janela contam como zero.")
    linhas.append("  Atencao FIIs: o historico de proventos do yfinance costuma comecar em ~2022;")
    linhas.append("        anos ausentes na fonte contam como zero, entao o teto de FII pode estar")
    linhas.append("        SUBESTIMADO. O P/VP nao depende desse historico e serve de contraprova.")
    linhas.append("─" * W)

    return "\n".join(linhas)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args         = sys.argv[1:]
    validos      = {"--so-acoes", "--so-fiis"}
    desconhecidos = [a for a in args if a not in validos]
    if desconhecidos:
        print(f"Argumento(s) desconhecido(s): {' '.join(desconhecidos)}")
        print("Uso: scanner_dividendos.py [--so-acoes | --so-fiis]")
        sys.exit(1)

    so_acoes = "--so-acoes" in args
    so_fiis  = "--so-fiis"  in args
    if so_acoes and so_fiis:
        print("Erro: --so-acoes e --so-fiis sao mutuamente exclusivos (juntos nao sobra nada para coletar).")
        sys.exit(1)

    ts_pasta  = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    pasta     = os.path.join(SCANS_DIR, f"scan_div_{ts_pasta}")
    os.makedirs(pasta, exist_ok=True)

    acoes_resultados: list[dict] = []
    fiis_resultados:  list[dict] = []

    # ── Coleta de acoes ──────────────────────────────────────────────────────
    if not so_fiis:
        total = sum(len(v) for v in ACOES.values())
        print(f"\nColetando {total} acoes ({', '.join(ACOES)})...")
        for setor, tickers in ACOES.items():
            for ticker in tickers:
                print(f"  {ticker:<12}", end=" ", flush=True)
                r = fetch_ativo(ticker, setor)
                acoes_resultados.append(r)
                if r.get("erro"):
                    print(f"ERRO: {r['erro']}")
                elif r.get("preco_teto"):
                    m     = r["margem_pct"]
                    m_str = f"{m:+.1f}%" if m is not None else "N/D"
                    flag  = f"  <<{','.join(r['flags'])}>>" if r.get("flags") else ""
                    print(
                        f"R${r['preco']:.2f} | DY {r['dy_ttm_pct']:.2f}% | "
                        f"teto R${r['preco_teto']:.2f} | margem {m_str}{flag}"
                    )
                else:
                    print(f"R${r['preco']:.2f} | sem historico de div para calcular teto")
                time.sleep(0.4)

    # ── Coleta de FIIs ───────────────────────────────────────────────────────
    if not so_acoes:
        print(f"\nColetando {len(FIIS)} FIIs...")
        for ticker in FIIS:
            print(f"  {ticker:<12}", end=" ", flush=True)
            r = fetch_ativo(ticker, "FII", is_fii=True)
            fiis_resultados.append(r)
            if r.get("erro"):
                print(f"ERRO: {r['erro']}")
            elif r.get("preco_teto"):
                m       = r["margem_pct"]
                m_str   = f"{m:+.1f}%" if m is not None else "N/D"
                pvp_str = f" | P/VP {r['p_vp']:.2f}" if r.get("p_vp") else ""
                flag    = f"  <<{','.join(r['flags'])}>>" if r.get("flags") else ""
                print(
                    f"R${r['preco']:.2f} | DY {r['dy_ttm_pct']:.2f}% | "
                    f"teto R${r['preco_teto']:.2f} | margem {m_str}{pvp_str}{flag}"
                )
            else:
                print(f"R${r['preco']:.2f} | sem historico de div para calcular teto")
            time.sleep(0.4)

    # ── Salvar JSON bruto ────────────────────────────────────────────────────
    json_path = os.path.join(pasta, "dados_brutos.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {"gerado_em": datetime.now().isoformat(), "acoes": acoes_resultados, "fiis": fiis_resultados},
            f, ensure_ascii=False, indent=2,
        )

    # ── Relatorio legivel ────────────────────────────────────────────────────
    relatorio = formatar_relatorio(acoes_resultados, fiis_resultados)
    print("\n" + relatorio)

    rel_path = os.path.join(pasta, "relatorio.txt")
    with open(rel_path, "w", encoding="utf-8") as f:
        f.write(relatorio + "\n")

    def _exibir(caminho: str) -> str:
        """Caminho relativo ao cwd quando possivel — absoluto polui a saida."""
        try:
            return os.path.relpath(caminho)
        except ValueError:  # drives diferentes no Windows
            return caminho

    print(f"\nResultados salvos em: {_exibir(pasta)}{os.sep}")
    print(f"  Relatorio:  {_exibir(rel_path)}")
    print(f"  JSON bruto: {_exibir(json_path)}")


if __name__ == "__main__":
    main()
