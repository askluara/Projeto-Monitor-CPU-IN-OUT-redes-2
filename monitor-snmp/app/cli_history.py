"""Consulta o banco para conferir a persistencia.

Uso:
  python cli_history.py                              -> ultimas 15 amostras
  python cli_history.py "2026-10-21 14:00" "2026-10-21 15:00"   -> periodo (hora local)
"""
import sys
from datetime import datetime

from app.config import load_config
from app.storage import Storage

FMT = "%Y-%m-%d %H:%M"


def fmt(v, suf=""):
    return "   -   " if v is None else f"{v:10.1f}{suf}"


def main():
    cfg = load_config()
    db = Storage(cfg.get("db_path", "monitor.db"))
    if len(sys.argv) == 3:
        start = datetime.strptime(sys.argv[1], FMT).timestamp()
        end = datetime.strptime(sys.argv[2], FMT).timestamp()
        rows = db.query_samples(start, end)
        print(f"Periodo: {sys.argv[1]} ate {sys.argv[2]}")
        if not rows:
            print("Sem dados no periodo selecionado.")
    else:
        rows = db.query_samples()[-15:]
        print(f"Total no banco: {db.count_samples()} amostras (mostrando as ultimas 15)")
    for row in rows:
        ts, i, o, c = row[:4]
        when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{when} | IN {fmt(i)} bps | OUT {fmt(o)} bps | CPU {fmt(c, '%')}")
    errs = db.query_errors(5)
    if errs:
        print("\nUltimos erros:")
        for ts, kind, msg in errs:
            print(datetime.fromtimestamp(ts).strftime("%H:%M:%S"), kind, msg)
    db.close()


if __name__ == "__main__":
    main()
