import json
from pathlib import Path


def load_config(path="config.json") -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"{path} nao encontrado. Copie config.example.json para config.json e ajuste."
        )
    cfg = json.loads(p.read_text(encoding="utf-8"))
    if float(cfg.get("collect_interval_s", 0)) <= 0:
        raise ValueError("collect_interval_s deve ser maior que zero")
    return cfg
