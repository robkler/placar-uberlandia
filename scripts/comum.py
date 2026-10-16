"""Configuração e funções compartilhadas pelos scripts do Placar de Uberlândia."""
import gzip
import json
import os
import sys
import time
import urllib.request
import urllib.error

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(RAIZ, 'dados')
PUBLIC = os.path.join(RAIZ, 'public')

# --- Configuração -----------------------------------------------------------
CAMARA_API = 'https://www.camarauberlandia.mg.gov.br/++api++'
LEGISLATURA_INICIO = 2025          # 1º ano da legislatura atual da Câmara
IBGE_MUNICIPIO = '3170206'         # Uberlândia no IBGE / Tesouro
TSE_MUNICIPIO = '54038'            # Uberlândia no TSE
TSE_ANO_ELEICAO = 2024
REBUSCAR_SESSOES_DIAS = 45         # reuniões recentes são baixadas de novo (votos podem ser lançados depois)

UA = 'Mozilla/5.0 (PlacarUberlandia; dados publicos) Python-urllib'


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def baixar(url, tentativas=4, timeout=60, json_=True):
    """GET com retentativas. Retorna JSON (dict) ou bytes."""
    erro = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json' if json_ else '*/*'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                corpo = r.read()
            if corpo[:2] == b'\x1f\x8b':  # alguns servidores respondem em gzip
                corpo = gzip.decompress(corpo)
            return json.loads(corpo) if json_ else corpo
        except urllib.error.HTTPError as e:
            erro = e
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:  # rede instável
            erro = e
        time.sleep(2 * (i + 1))
    raise RuntimeError(f'Falha ao baixar {url}: {erro}')


def ler_json(caminho, padrao=None):
    try:
        with open(caminho, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return padrao


def salvar_json(caminho, dados, compacto=False):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        if compacto:
            json.dump(dados, f, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        else:
            json.dump(dados, f, ensure_ascii=False, indent=1, allow_nan=False)
    os.replace(tmp, caminho)
