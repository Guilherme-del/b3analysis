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


# ── Helpers de dividendo ─────────────────────────────────────────────────────

def _normalizar_index(series: pd.Series) -> pd.Series:
    """Remove timezone do index para uniformizar comparacoes."""
    if series.empty:
        return series
    if series.index.tz is not None:
        series = series.copy()
        series.index = series.index.tz_convert("UTC").tz_localize(None)
    return series


def _media_dividendo_5a(t: yf.Ticker) -> float:
    """
    Retorna a media anual de dividendos pagos nos ultimos 5 anos (em R$ por cota/acao).
    Usa o historico real de pagamentos — mais preciso que DY x preco do info dict.
    """
    try:
        hist = t.dividends
        if hist is None or hist.empty:
            return 0.0
        hist = _normalizar_index(hist)
        cutoff = pd.Timestamp.now() - pd.DateOffset(years=5)
        recent = hist[hist.index >= cutoff]
        if recent.empty:
            return 0.0
        annual = recent.groupby(recent.index.year).sum()
        return float(annual.mean())
    except Exception:
        return 0.0


def _anos_pagando(t: yf.Ticker) -> int:
    """Quantos anos distintos a empresa pagou dividendo nos ultimos 10 anos."""
    try:
        hist = t.dividends
        if hist is None or hist.empty:
            return 0
        hist = _normalizar_index(hist)
        cutoff = pd.Timestamp.now() - pd.DateOffset(years=10)
        recent = hist[hist.index >= cutoff]
        return int(recent.index.year.nunique()) if not recent.empty else 0
    except Exception:
        return 0


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

        div_medio_5a = _media_dividendo_5a(t)
        dy_atual_pct = (info.get("dividendYield") or 0.0) * 100
        anos_div     = _anos_pagando(t)

        preco_teto = (div_medio_5a / BAZIN_MINIMA) if div_medio_5a > 0 else None
        margem_pct = ((preco_teto / preco - 1) * 100) if (preco_teto and preco > 0) else None

        payout = info.get("payoutRatio")
        roe    = info.get("returnOnEquity")
        pvp    = info.get("priceToBook")

        base.update({
            "nome":          (info.get("longName") or info.get("shortName") or "")[:42],
            "preco":         round(preco, 2),
            "div_medio_5a":  round(div_medio_5a, 4),
            "dy_atual_pct":  round(dy_atual_pct, 2),
            "preco_teto":    round(preco_teto, 2) if preco_teto else None,
            "margem_pct":    round(margem_pct, 1) if margem_pct is not None else None,
            "anos_div":      anos_div,
            "payout_pct":    round(payout * 100, 1) if payout else None,
            "roe_pct":       round(roe * 100, 1) if roe else None,
            "p_vp":          round(pvp, 2) if pvp else None,
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

        div_medio_5a = _media_dividendo_5a(t)
        dy_atual_pct = (info.get("dividendYield") or 0.0) * 100
        anos_div     = _anos_pagando(t)
        pvp          = info.get("priceToBook")

        preco_teto = (div_medio_5a / BAZIN_MINIMA) if div_medio_5a > 0 else None
        margem_pct = ((preco_teto / preco - 1) * 100) if (preco_teto and preco > 0) else None

        base.update({
            "nome":         (info.get("longName") or info.get("shortName") or "")[:42],
            "preco":        round(preco, 2),
            "div_medio_5a": round(div_medio_5a, 4),
            "dy_atual_pct": round(dy_atual_pct, 2),
            "preco_teto":   round(preco_teto, 2) if preco_teto else None,
            "margem_pct":   round(margem_pct, 1) if margem_pct is not None else None,
            "anos_div":     anos_div,
            "p_vp":         round(pvp, 2) if pvp else None,
        })
    except Exception as e:
        base["erro"] = str(e)[:100]
    return base


# ── Formatacao do relatorio ──────────────────────────────────────────────────

def _status(margem: float | None) -> str:
    if margem is None:
        return "S/DADO"
    if margem >= 20:
        return "BARATO"
    if margem >= 0:
        return "OK    "
    if margem >= -20:
        return "CARO  "
    return "MUITO CARO"


def _linha_acao(r: dict) -> str:
    preco_s  = f"R${r['preco']:>8.2f}"
    teto_s   = f"R${r['preco_teto']:>8.2f}" if r.get("preco_teto") else "       N/D"
    margem_s = f"{r['margem_pct']:>+7.1f}%" if r.get("margem_pct") is not None else "     N/D"
    dy_s     = f"{r['dy_atual_pct']:>5.1f}%" if r.get("dy_atual_pct") else "  N/D"
    anos_s   = f"{r['anos_div']:>2}a" if r.get("anos_div") else " -"
    roe_s    = f"{r['roe_pct']:>5.1f}%" if r.get("roe_pct") is not None else "   N/D"
    pout_s   = f"{r['payout_pct']:>5.0f}%" if r.get("payout_pct") is not None else "   N/D"
    st       = _status(r.get("margem_pct"))
    return (
        f"  {r['ticker']:<9} {preco_s}  {teto_s}  {margem_s}  "
        f"{dy_s}  {anos_s}  {roe_s}  {pout_s}  [{st}]"
    )


def _linha_fii(r: dict) -> str:
    preco_s  = f"R${r['preco']:>8.2f}"
    teto_s   = f"R${r['preco_teto']:>8.2f}" if r.get("preco_teto") else "       N/D"
    margem_s = f"{r['margem_pct']:>+7.1f}%" if r.get("margem_pct") is not None else "     N/D"
    dy_s     = f"{r['dy_atual_pct']:>5.1f}%" if r.get("dy_atual_pct") else "  N/D"
    anos_s   = f"{r['anos_div']:>2}a" if r.get("anos_div") else " -"
    pvp_s    = f"{r['p_vp']:>5.2f}" if r.get("p_vp") else "   N/D"
    st       = _status(r.get("margem_pct"))
    return (
        f"  {r['ticker']:<10} {preco_s}  {teto_s}  {margem_s}  "
        f"{dy_s}  {anos_s}  {pvp_s}  [{st}]"
    )


def formatar_relatorio(acoes: list[dict], fiis: list[dict]) -> str:
    ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    W  = 82
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
        linhas.append("  ACOES — B.E.S.T. (Barsi)  |  Preco-teto = div.medio_5a / 6%")
        linhas.append("─" * W)

        por_setor: dict[str, list] = {}
        erros_acao: list[dict]     = []
        for r in acoes:
            if r.get("erro"):
                erros_acao.append(r)
            else:
                por_setor.setdefault(r["setor"], []).append(r)

        for setor, registros in por_setor.items():
            registros.sort(key=lambda r: r.get("margem_pct") or -9999, reverse=True)
            linhas.append(f"\n  [{setor}]")
            linhas.append(
                f"  {'TICKER':<9} {'PRECO':>10}  {'PRECO-TETO':>10}  {'MARGEM':>8}  "
                f"{'DY%':>5}  {'DIV':>3}  {'ROE%':>6}  {'POUT%':>6}  STATUS"
            )
            linhas.append("  " + "-" * (W - 2))
            for r in registros:
                linhas.append(_linha_acao(r))

        if erros_acao:
            linhas.append("\n  Falhas na coleta:")
            for r in erros_acao:
                linhas.append(f"    {r['ticker']:<10} {r['erro']}")

        linhas.append("")

    # ── FIIs ─────────────────────────────────────────────────────────────────
    if fiis:
        linhas.append("─" * W)
        linhas.append("  FIIs — DY + P/VP + Preco-teto Bazin (div.medio_5a / 6%)")
        linhas.append("─" * W)

        fiis_ok  = [r for r in fiis if not r.get("erro")]
        fiis_err = [r for r in fiis if r.get("erro")]
        fiis_ok.sort(key=lambda r: r.get("margem_pct") or -9999, reverse=True)

        linhas.append(
            f"\n  {'TICKER':<10} {'PRECO':>10}  {'PRECO-TETO':>10}  {'MARGEM':>8}  "
            f"{'DY%':>5}  {'DIV':>3}  {'P/VP':>6}  STATUS"
        )
        linhas.append("  " + "-" * (W - 2))
        for r in fiis_ok:
            linhas.append(_linha_fii(r))

        if fiis_err:
            linhas.append("\n  Falhas na coleta:")
            for r in fiis_err:
                linhas.append(f"    {r['ticker']:<10} {r['erro']}")

        linhas.append("")

    # ── Legenda ──────────────────────────────────────────────────────────────
    linhas.append("─" * W)
    linhas.append("  Legenda:")
    linhas.append("  BARATO     — preco < preco-teto (margem > 20%) — zona de compra")
    linhas.append("  OK         — proximo ao teto   (0% a +20%)     — aguardar queda")
    linhas.append("  CARO       — acima do teto     (0% a -20%)     — nao iniciar posicao")
    linhas.append("  MUITO CARO — muito acima        (< -20%)        — evitar")
    linhas.append("  S/DADO     — sem historico de dividendos disponivel no yfinance")
    linhas.append("")
    linhas.append("  Preco-teto Bazin  = dividendo_medio_anual_5a / 0,06")
    linhas.append("  Margem            = (preco_teto / preco_atual - 1) x 100")
    linhas.append("  DIV               = anos distintos pagando dividendo (ultimos 10a)")
    linhas.append("  P/VP              = preco / valor patrimonial por cota")
    linhas.append("─" * W)

    return "\n".join(linhas)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    so_acoes = "--so-acoes" in sys.argv
    so_fiis  = "--so-fiis"  in sys.argv

    ts_pasta  = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    pasta     = f"scan_div_{ts_pasta}"
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
                    m = r["margem_pct"]
                    m_str = f"{m:+.1f}%" if m is not None else "N/D"
                    print(
                        f"R${r['preco']:.2f} | teto R${r['preco_teto']:.2f} | "
                        f"margem {m_str} | DY {r['dy_atual_pct']:.1f}%"
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
                m = r["margem_pct"]
                m_str = f"{m:+.1f}%" if m is not None else "N/D"
                pvp_str = f"P/VP {r['p_vp']:.2f}" if r.get("p_vp") else ""
                print(
                    f"R${r['preco']:.2f} | teto R${r['preco_teto']:.2f} | "
                    f"margem {m_str} | DY {r['dy_atual_pct']:.1f}% {pvp_str}"
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

    print(f"\nResultados salvos em: {pasta}/")
    print(f"  Relatorio: {rel_path}")
    print(f"  JSON bruto: {json_path}")


if __name__ == "__main__":
    main()
