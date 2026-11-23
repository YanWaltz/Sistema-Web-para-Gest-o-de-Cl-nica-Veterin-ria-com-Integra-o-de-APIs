"""Configuracao local e conexoes independentes para os dois servicos."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('SDM_DATA_DIR', ROOT.parent / 'data'))
GOV_URL = os.environ.get('SDM_GOV_URL', 'http://127.0.0.1:8001').rstrip('/')
GOV_KEY = os.environ.get('SDM_GOV_KEY', 'somente-demonstracao-local')

@contextmanager
def db(nome='clinica'):
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DATA / f'{nome}.db', timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        with c:
            yield c
    finally:
        c.close()
