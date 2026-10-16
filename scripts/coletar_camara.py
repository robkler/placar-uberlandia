"""Baixa da API da Câmara Municipal de Uberlândia: vereadores em exercício e reuniões
plenárias (com presença e votações nominais) da legislatura atual; e, do e-processos (SAGL),
os projetos de lei de autoria principal de cada vereador.

Guarda o bruto em dados/camara/. Reuniões antigas ficam em cache; as dos últimos
REBUSCAR_SESSOES_DIAS dias são baixadas de novo a cada execução. Projetos propostos ficam em
dados/camara/propostos/<id>-<ano>.json: anos passados não são baixados de novo; o ano atual sim.
Se o e-processos falhar, registra o aviso e mantém o que já estava em cache.
"""
import datetime as dt
import os
import re
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from comum import (CAMARA_API, DADOS, EPROCESSOS, LEGISLATURA_INICIO, REBUSCAR_SESSOES_DIAS, UA_EPROCESSOS,
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


# Tipos de matéria no e-processos: 1 PL (ordinária), 5 PLC (complementar), 4 PELO (emenda à Lei Orgânica).
TIPOS_PROJETO = (1, 5, 4)
CAMPOS_MATERIA = ('cod_materia', 'tipo_item', 'sgl_tipo_materia', 'des_tipo_materia', 'num_ident_basica',
                  'ano_ident_basica', 'identificacao', 'txt_ementa', 'dat_apresentacao', 'autores', 'detail_url',
                  'ind_tramitacao', 'ult_tramitacao', 'norma_derivada', 'anexadoras')


def baixar_propostos(vid, ano):
    """Projetos (PL, PLC, PELO) de autoria principal do vereador apresentados no ano, todas as páginas."""
    itens, pagina = [], 1
    while True:
        q = urllib.parse.urlencode([('cod_autor', vid), *[('tip_id_basica', t) for t in TIPOS_PROJETO],
                                    ('ano_ident_basica', ano), ('chk_primeiro_autor', 1),
                                    ('itens_por_pagina', 100), ('pagina', pagina)])
        r = baixar(f'{EPROCESSOS}/consultas/materia/materias_legislativas_json?{q}', ua=UA_EPROCESSOS)
        itens += [{k: m.get(k) for k in CAMPOS_MATERIA} for m in r.get('data') or []]
        if not r.get('has_next') or pagina >= 50:
            break
        pagina += 1
    if len(itens) != r.get('total', len(itens)):
        raise RuntimeError(f'esperava {r.get("total")} projetos e vieram {len(itens)}')
    return dict(codAutor=vid, ano=ano, total=len(itens), coletadoEm=dt.datetime.now().isoformat(timespec='minutes'),
                itens=itens)


def sem_acento(t):
    t = unicodedata.normalize('NFD', t or '')
    return re.sub(r'\s+', ' ', ''.join(c for c in t if not unicodedata.combining(c)).casefold()).strip()


def autores_eprocessos(ids):
    """id do vereador no site da Câmara -> cod_autor no e-processos. Os códigos NÃO são sempre os mesmos
    (ex.: Ângela do Postinho é 556176 no site e 556181 no e-processos, onde 556176 é a Mesa Diretora),
    então o casamento é pelo nome (apelido ou nome completo), sem acento."""
    arq = os.path.join(DIR, 'autores_eprocessos.json')
    try:
        autores = baixar(f'{EPROCESSOS}/consultas/materia/autores_json', ua=UA_EPROCESSOS)
        salvar_json(arq, autores)
    except Exception as e:
        log(f'  aviso: lista de autores do e-processos indisponível ({e}); usando a anterior')
        autores = ler_json(arq, [])
    por_nome = {}
    for a in autores:
        por_nome.setdefault(sem_acento(a['text']), []).append(a['id'])
    mapa, sem = {}, []
    for i in ids:
        d = ler_json(os.path.join(DIR, 'vereadores', f'{i}.json'), {})
        cods = por_nome.get(sem_acento(d.get('title'))) or por_nome.get(sem_acento(d.get('fullname'))) or []
        if len(cods) == 1:
            mapa[i] = str(cods[0])
        else:
            sem.append(d.get('title') or i)
    if sem:
        log(f'  aviso: sem autor (ou mais de um) no e-processos para {", ".join(sem)}')
    return mapa


def propostos(ids):
    """Baixa os projetos de autoria principal por vereador e ano. Nunca derruba a coleta."""
    hoje = dt.date.today()
    pasta = os.path.join(DIR, 'propostos')
    mapa = autores_eprocessos(ids)

    def precisa(i, ano):
        cache = ler_json(os.path.join(pasta, f'{i}-{ano}.json'))
        return ano == hoje.year or not cache or str(cache.get('codAutor')) != mapa[i]

    tarefas = [(i, ano) for i in ids if i in mapa for ano in range(LEGISLATURA_INICIO, hoje.year + 1) if precisa(i, ano)]

    def um(t):
        vid, ano = t
        try:
            salvar_json(os.path.join(pasta, f'{vid}-{ano}.json'), dict(id=vid, **baixar_propostos(mapa[vid], ano)))
            return None
        except Exception as e:
            return f'{vid}/{ano}: {e}'

    with ThreadPoolExecutor(2) as ex:
        falhas = [f for f in ex.map(um, tarefas) if f]
    log(f'  projetos propostos: {len(tarefas) - len(falhas)} de {len(tarefas)} vereador-ano baixados do e-processos')
    if falhas:
        log(f'  aviso: e-processos falhou em {len(falhas)} (mantido o cache anterior): {"; ".join(falhas[:5])}')


def main():
    log('Câmara Municipal de Uberlândia')
    ids = vereadores()
    sessoes()
    try:
        propostos(ids)
    except Exception as e:  # o e-processos fora do ar não pode parar a atualização diária
        log(f'  aviso: projetos propostos não atualizados ({e}); mantido o cache anterior')
    salvar_json(os.path.join(DIR, 'coletado_em.json'), dt.datetime.now().isoformat(timespec='minutes'))


if __name__ == '__main__':
    main()
