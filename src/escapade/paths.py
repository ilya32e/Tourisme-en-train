"""Chemins du projet + chargement du .env (centralisés)."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # racine (au-dessus de src/)
CACHE = PROJECT_ROOT / "cache"
DATA = PROJECT_ROOT / "data"
ENV = PROJECT_ROOT / ".env"


def load_env():
    """Charge les clés du .env dans os.environ (sans écraser l'existant)."""
    if not ENV.exists():
        return
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
