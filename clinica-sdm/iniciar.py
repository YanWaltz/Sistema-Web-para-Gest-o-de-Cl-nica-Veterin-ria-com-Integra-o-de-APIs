"""Inicia os dois serviços na própria máquina e abre a interface."""
import argparse
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8000'
SERVICOS = [('governo',8001), ('clinica',8000)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sem-navegador', action='store_true')
    args = p.parse_args()
    processos = []
    try:
        for modulo, porta in SERVICOS:
            proc = subprocess.Popen([sys.executable,'-m','uvicorn',f'sdm.{modulo}:app','--host','127.0.0.1','--port',str(porta)],cwd=ROOT)
            processos.append(proc)
            fim = time.monotonic()+15
            while True:
                if proc.poll() is not None:
                    raise RuntimeError(f'Não foi possível iniciar {modulo} na porta {porta}. Veja a mensagem acima.')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{porta}/saude',timeout=.5) as r:
                        r.read()
                    break
                except (OSError, TimeoutError):
                    if time.monotonic()>fim:
                        raise RuntimeError(f'{modulo} não respondeu na porta {porta}.')
                    time.sleep(.15)
        print(f'Abra {URL} no navegador. Para parar, pressione Ctrl+C.',flush=True)
        if not args.sem_navegador:
            webbrowser.open(URL)
        while all(p.poll() is None for p in processos):
            time.sleep(.4)
        raise RuntimeError('Um serviço encerrou antes da hora.')
    except KeyboardInterrupt:
        return 0
    except RuntimeError as e:
        print(e,file=sys.stderr); return 1
    finally:
        for proc in processos:
            if proc.poll() is None:
                proc.terminate()
        for proc in processos:
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()

if __name__ == '__main__':
    raise SystemExit(main())
