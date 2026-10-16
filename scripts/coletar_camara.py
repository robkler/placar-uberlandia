"""Baixa da API da Câmara Municipal de Uberlândia: vereadores em exercício e reuniões
plenárias (com presença e votações nominais) da legislatura atual.

Guarda o bruto em dados/camara/. Reuniões antigas ficam em cache; as dos últimos
REBUSCAR_SESSOES_DIAS dias são baixadas de novo a cada execução.
"""
import datetime as dt
import os
from concurrent.futures import ThreadPoolExecutor

from comum import (CAMARA_API, DADOS, LEGISLATURA_INICIO, REBUSCAR_SESSOES_DIAS,
                   baixar, ler_json, log, salvar_json)

DIR = os.path.join(DADOS, 'camara')
TIPOS_SESSAO = (1, 2, 3, 4)  # ordinária, extraordinária, solene, especial


def vereadores():
    lista = baixar(f'{CAMARA_API}/vereadores/vereadores')
    ids = [i['@id'].rstrip('/').rsplit('/', 1)[1] for i in lista.get('items', [])]
    if not ids:
        raise RuntimeError('A Câmara não retornou nenhum vereador.')

    def um(i):
        return baixar(f'{CAMARA_API}/vereadores/vereadores/{i}')

    with ThreadPoolExecutor(4) as ex:
        dados = list(ex.map(um, ids))
    for d in dados:
        salvar_json(os.path.join(DIR, 'vereadores', f"{d['id']}.json"), d)
    salvar_json(os.path.join(DIR, 'vereadores.json'), ids)
    log(f'  {len(ids)} vereadores')
    return ids


def sessoes():
    hoje = dt.date.today()
    limite = (hoje - dt.timedelta(days=REBUSCAR_SESSOES_DIAS)).isoformat()
    todas = {}
    for ano in range(LEGISLATURA_INICIO, hoje.year + 1):
        for tipo in TIPOS_SESSAO:
            r = baixar(f'{CAMARA_API}/atividade-legislativa/sessoes?ano={ano}&tipo={tipo}')
            for it in r.get('items', []):
                todas[it['id']] = it.get('date') or ''
    pasta = os.path.join(DIR, 'sessoes')
    os.makedirs(pasta, exist_ok=True)
    baixar_ids = [i for i, data in todas.items()
                  if data >= limite or not os.path.exists(os.path.join(pasta, f'{i}.json'))]

    def uma(i):
        d = baixar(f'{CAMARA_API}/atividade-legislativa/sessoes/{i}', timeout=120)
        salvar_json(os.path.join(pasta, f'{i}.json'), d)

    with ThreadPoolExecutor(4) as ex:
        list(ex.map(uma, baixar_ids))
    salvar_json(os.path.join(DIR, 'sessoes.json'), sorted(todas))
    log(f'  {len(todas)} reuniões na legislatura ({len(baixar_ids)} baixadas agora)')


def main():
    log('Câmara Municipal de Uberlândia')
    vereadores()
    sessoes()
    salvar_json(os.path.join(DIR, 'coletado_em.json'), dt.datetime.now().isoformat(timespec='minutes'))


if __name__ == '__main__':
    main()
