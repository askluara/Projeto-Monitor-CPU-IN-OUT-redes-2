"""Intervalos rápidos de consulta do histórico."""
from datetime import datetime, timedelta


HISTORY_PERIODS = {
    "Últimos 15 minutos": timedelta(minutes=15),
    "Últimos 30 minutos": timedelta(minutes=30),
    "Última 1 hora": timedelta(hours=1),
    "Últimas 3 horas": timedelta(hours=3),
    "Últimas 6 horas": timedelta(hours=6),
    "Últimas 12 horas": timedelta(hours=12),
    "Últimas 24 horas": timedelta(hours=24),
}


def period_bounds(label, now=None):
    """Retorna timestamps locais [início, fim] do período selecionado."""
    if label not in HISTORY_PERIODS:
        raise ValueError(f"Período não reconhecido: {label}")
    end = now or datetime.now().astimezone()
    return (end - HISTORY_PERIODS[label]).timestamp(), end.timestamp()
