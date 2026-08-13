import os
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent

DEFAULT_CONFIG = {
    "data_cache_dir": str(_BASE_DIR / "data_cache"),
    # _get_stock_stats_bulk le data_vendors.technical_indicators para escolher
    # entre buscar online e ler um CSV local. Sem essa chave o acesso levantava
    # KeyError, que era engolido pelo except do chamador e caia no caminho
    # por-data — uma release completa de 15 anos por dia consultado, com o erro
    # so aparecendo em stdout. Falha silenciosa, nao falha ruidosa.
    "data_vendors": {
        "technical_indicators": "online",
    },
}

_config = DEFAULT_CONFIG.copy()


def get_config():
    return _config.copy()
