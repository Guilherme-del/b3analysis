#!/usr/bin/env python3
"""
scanner_dividendos.py — Scanner de dividendos B3 (metodologia Barsi/Bazin)

Universo: Bancos, Energia Eletrica, Saneamento, Seguros + FIIs opcionais.

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
        "BRSR6.SA",   # Banrisul (Unit)
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
}

FIIS = [
    "HGLG11.SA",  # CSHG Logistica
    "KNCR11.SA",  # Kinea Rendimentos Imobiliarios
    "XPML11.SA",  # XP Malls
    "BTLG11.SA",  # BTG Pactual Logistica
    "TRXF11.SA",  # TRX Real Estate
    "KNIP11.SA",  # Kinea Indice de Precos
    "HGBS11.SA",  # CSHG Brasil Shopping
]

BAZIN_MINIMA = 0.06   # Taxa minima de retorno para calculo do preco-teto (6% a.a.)
CDI_ATUAL    = 0.1475  # Selic/CDI atual — benchmark de retorno minimo para renda variavel

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


def _dividendos_por_ano(t: yf.Ticker) -> pd.Series:
    """
    Soma de dividendos por ano-calendario. Series vazia se nao houver historico.
    Cacheado no proprio Ticker para evitar refetch entre as metricas.
    """
    try:
        hist = t.dividends
        if hist is None or hist.empty:
            return pd.Series(dtype=float)
        hist = _normalizar_index(hist)
        return hist.groupby(hist.index.year).sum()
    except Exception:
        return pd.Series(dtype=float)


def _media_dividendo_5a(por_ano: pd.Series) -> float:
    """
    Media anual de dividendos dos ultimos 5 anos-calendario COMPLETOS.

    O ano corrente e excluido de proposito: incluir um ano parcial puxa a media
    para baixo e subestima o preco-teto (verificado: -30% em TAEE11, -22% em BBAS3).
    """
    if por_ano.empty:
        return 0.0
    ano_atual = pd.Timestamp.now().year
    completos = por_ano[(por_ano.index >= ano_atual - 5) & (por_ano.index <= ano_atual - 1)]
    return float(completos.mean()) if not completos.empty else 0.0


def _anos_pagando(por_ano: pd.Series) -> int:
    """Anos-calendario completos com pagamento de dividendo nos ultimos 10 anos."""
    if por_ano.empty:
        return 0
    ano_atual = pd.Timestamp.now().year
    janela = por_ano[
        (por_ano.index >= ano_atual - 10) & (por_ano.index <= ano_atual - 1) & (por_ano > 0)
    ]
    return int(len(janela))


def _dy_ttm(t: yf.Ticker, preco: float) -> float:
    """
    DY dos ultimos 12 meses, calculado do historico real de pagamentos.

    Nao usa info['dividendYield']: verificado que o campo e inconsistente entre
    tickers .SA (ITUB4 reportou 2.07 contra 8.16% real — erro de 4x).
    """
    if preco <= 0:
        return 0.0
    try:
        hist = t.dividends
        if hist is None or hist.empty:
            return 0.0
        hist = _normalizar_index(hist)
        ttm = float(hist[hist.index >= (pd.Timestamp.now() - pd.DateOffset(years=1))].sum())
        return (ttm / preco) * 100
    except Exception:
        return 0.0


def _avaliar_qualidade(roe: float | None, payout: float | None, anos: int) -> list[str]:
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
    return flags


# ── Coleta por tipo de ativo ─────────────────────────────────────────────────

def fetch_acao(ticker_symbol: str, setor: str) -> dict:
    """Coleta metricas Barsi/Bazin para uma acao."""
    base = {
        "ticker": ticker_symbol.replace(".SA", ""),
        "setor":  setor,
        "tipo":   "acao",
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

        por_ano      = _dividendos_por_ano(t)
        div_medio_5a = _media_dividendo_5a(por_ano)
        dy_ttm_pct   = _dy_ttm(t, preco)
        anos_div     = _anos_pagando(por_ano)

        preco_teto  = (div_medio_5a / BAZIN_MINIMA) if div_medio_5a > 0 else None
        teto_cdi    = (div_medio_5a / CDI_ATUAL)    if div_medio_5a > 0 else None
        margem_pct  = ((preco_teto / preco - 1) * 100) if preco_teto else None
        margem_cdi  = ((teto_cdi   / preco - 1) * 100) if teto_cdi   else None

        payout = info.get("payoutRatio")
        roe    = info.get("returnOnEquity")
        pvp    = info.get("priceToBook")

        base.update({
            "nome":          (info.get("longName") or info.get("shortName") or "")[:42],
            "preco":         round(preco, 2),
            "div_medio_5a":  round(div_medio_5a, 4),
            "dy_ttm_pct":    round(dy_ttm_pct, 2),
            "preco_teto":    round(preco_teto, 2) if preco_teto else None,
            "margem_pct":    round(margem_pct, 1) if margem_pct is not None else None,
            "teto_cdi":      round(teto_cdi, 2) if teto_cdi else None,
            "margem_cdi":    round(margem_cdi, 1) if margem_cdi is not None else None,
            "anos_div":      anos_div,
            "payout_pct":    round(payout * 100, 1) if payout is not None else None,
            "roe_pct":       round(roe * 100, 1) if roe is not None else None,
            "p_vp":          round(pvp, 2) if pvp else None,
            "flags":         _avaliar_qualidade(roe, payout, anos_div),
        })
    except Exception as e:
        base["erro"] = str(e)[:100]
    return base


def fetch_fii(ticker_symbol: str) -> dict:
    """Coleta metricas de dividendo + P/VP para um FII."""
    base = {
        "ticker": ticker_symbol.replace(".SA", ""),
        "setor":  "FII",
        "tipo":   "fii",
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

        por_ano      = _dividendos_por_ano(t)
        div_medio_5a = _media_dividendo_5a(por_ano)
        dy_ttm_pct   = _dy_ttm(t, preco)
        anos_div     = _anos_pagando(por_ano)
        pvp          = info.get("priceToBook")

        preco_teto = (div_medio_5a / BAZIN_MINIMA) if div_medio_5a > 0 else None
        teto_cdi   = (div_medio_5a / CDI_ATUAL)    if div_medio_5a > 0 else None
        margem_pct = ((preco_teto / preco - 1) * 100) if preco_teto else None
        margem_cdi = ((teto_cdi   / preco - 1) * 100) if teto_cdi   else None

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
            "p_vp":         round(pvp, 2) if pvp else None,
            "flags":        _avaliar_qualidade(None, None, anos_div),
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


def _linha_acao(r: dict) -> str:
    preco_s  = f"R${r['preco']:>8.2f}"
    teto_s   = f"R${r['preco_teto']:>8.2f}" if r.get("preco_teto") else "       N/D"
    margem_s = f"{r['margem_pct']:>+7.1f}%" if r.get("margem_pct") is not None else "     N/D"
    mcdi_s   = f"{r['margem_cdi']:>+7.1f}%" if r.get("margem_cdi") is not None else "     N/D"
    dy_s     = f"{r['dy_ttm_pct']:>5.1f}%" if r.get("dy_ttm_pct") else "   N/D"
    anos_s   = f"{r['anos_div']:>2}a" if r.get("anos_div") else " -"
    roe_s    = f"{r['roe_pct']:>6.1f}%" if r.get("roe_pct") is not None else "    N/D"
    pout_s   = f"{r['payout_pct']:>5.0f}%" if r.get("payout_pct") is not None else "  N/D"
    st       = _status(r.get("margem_pct"), r.get("flags"))
    obs      = (" " + ",".join(r["flags"])) if r.get("flags") else ""
    return (
        f"  {r['ticker']:<9} {preco_s}  {dy_s}  {teto_s}  {margem_s}  {mcdi_s}  "
        f"{anos_s}  {roe_s}  {pout_s}  {st:<11}{obs}"
    )


def _linha_fii(r: dict) -> str:
    preco_s  = f"R${r['preco']:>8.2f}"
    teto_s   = f"R${r['preco_teto']:>8.2f}" if r.get("preco_teto") else "       N/D"
    margem_s = f"{r['margem_pct']:>+7.1f}%" if r.get("margem_pct") is not None else "     N/D"
    mcdi_s   = f"{r['margem_cdi']:>+7.1f}%" if r.get("margem_cdi") is not None else "     N/D"
    dy_s     = f"{r['dy_ttm_pct']:>5.1f}%" if r.get("dy_ttm_pct") else "   N/D"
    anos_s   = f"{r['anos_div']:>2}a" if r.get("anos_div") else " -"
    pvp_s    = f"{r['p_vp']:>5.2f}" if r.get("p_vp") else "  N/D"
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
    W  = 108
    linhas = []

    linhas.append("=" * W)
    linhas.append(f"  SCANNER DE DIVIDENDOS B3 — Barsi/Bazin  |  {ts}")
    linhas.append(f"  Setores: Bancos | Energia Eletrica | Saneamento | Seguros")
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
                f"{'MARG CDI':>8}  {'DIV':>3}  {'ROE':>7}  {'POUT':>6}  STATUS"
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
    linhas.append("")
    linhas.append("  DY        = dividendos dos ultimos 12 meses / preco atual (calculado do")
    linhas.append("              historico real — o campo dividendYield do yfinance e inconsistente)")
    linhas.append("  TETO 6%   = dividendo medio dos ultimos 5 anos COMPLETOS / 0,06  (Bazin classico)")
    linhas.append("  MARG 6%   = (teto 6% / preco - 1) x 100")
    linhas.append(f"  MARG CDI  = mesma conta usando {CDI_ATUAL*100:.2f}% (Selic) como taxa minima.")
    linhas.append("              Se MARG CDI for negativa, o ativo rende menos que a renda fixa hoje.")
    linhas.append("  DIV       = anos-calendario completos com dividendo (ultimos 10a)")
    linhas.append("  P/VP      = preco / valor patrimonial por cota")
    linhas.append("")
    linhas.append("  Nota: o ano corrente e excluido da media — ano parcial subestima o teto.")
    linhas.append("─" * W)

    return "\n".join(linhas)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    so_acoes = "--so-acoes" in sys.argv
    so_fiis  = "--so-fiis"  in sys.argv

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
                r = fetch_acao(ticker, setor)
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
            r = fetch_fii(ticker)
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
