"""Gera public/federal.json (Câmara dos Deputados) a partir de dados/federal/.

Mesma checagem de segurança do gerar_dados.py: se algo parecer quebrado, mantém o
arquivo anterior e sai com erro (use --forcar para gravar mesmo assim).
"""
import datetime as dt
import glob
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from comum import DADOS, PUBLIC, baixar, ler_json, log, salvar_json

DIR = os.path.join(DADOS, 'federal')
SAIDA = os.path.join(PUBLIC, 'federal.json')
API = 'https://dadosabertos.camara.leg.br/api/v2'
LEGISLATURA = 57
INICIO = '2023-02-01'
TIPOS = {'Proposta de Emenda à Constituição': 'PEC', 'Projeto de Lei Complementar': 'PLP',
         'Projeto de Decreto Legislativo': 'PDL', 'Projeto de Lei': 'PL', 'Medida Provisória': 'MPV'}
RX_PROP = re.compile(r'(Proposta de Emenda à Constituição|Projeto de Lei Complementar|Projeto de Decreto Legislativo|'
                     r'Projeto de Lei|Medida Provisória) n[º°] ?([\d\.]+),? de (\d{4})')
CODIGO = {'Sim': 'S', 'Não': 'N', 'Abstenção': 'A', 'Obstrução': 'O', 'Artigo 17': 'P'}


def intervalos(hist):
    h = sorted((x for x in hist if x.get('idLegislatura') == LEGISLATURA and x.get('situacao')
                and (x.get('dataHora') or '') >= INICIO), key=lambda x: x['dataHora'])
    iv, ini = [], None
    for x in h:
        if x['situacao'] == 'Exercício':
            ini = ini or x['dataHora']
        elif ini:
            iv.append((ini, x['dataHora'])); ini = None
    if ini:
        iv.append((ini, '9999'))
    return iv


def dentro(t, iv):
    return any(a <= t <= b for a, b in iv)


def principais(votacoes):
    """Votações do texto principal de projetos (não requerimentos nem destaques) com 300+ votos."""
    out = []
    for v in votacoes:
        d = v['desc'] or ''
        if v['sim'] + v['nao'] <= 300 or not re.match(r'(Aprovad|Rejeitad)', d):
            continue
        if not re.search('Projeto de Lei|Proposta de Emenda|Medida Provisória|Projeto de Decreto', d):
            continue
        if re.search('Requerimento|Destaque|Emenda n|Emendas|Recurso', d):
            continue
        m = RX_PROP.search(d)
        if not m:
            continue
        sig, num, ano = TIPOS[m.group(1)], m.group(2).replace('.', ''), m.group(3)
        turno = ' (1º turno)' if 'primeiro turno' in d else ' (2º turno)' if 'segundo turno' in d else ''
        out.append(dict(v, chave=f'{sig}/{num}/{ano}', prop_nome=f'{sig} {num}/{ano}{turno}'))
    return out


def ementas(chaves):
    arq = os.path.join(DIR, 'ementas.json')
    cache = ler_json(arq, {})
    faltam = [c for c in chaves if c not in cache]

    def uma(c):
        sig, num, ano = c.split('/')
        try:
            r = baixar(f'{API}/proposicoes?siglaTipo={sig}&numero={num}&ano={ano}')['dados']
            return c, (dict(ementa=r[0]['ementa'], id=r[0]['id']) if r else dict(ementa='', id=None))
        except RuntimeError:
            return c, None
    with ThreadPoolExecutor(6) as ex:
        for c, r in ex.map(uma, faltam):
            if r:
                cache[c] = r
    salvar_json(arq, cache)
    return cache


def main():
    forcar = '--forcar' in sys.argv
    log('Gerando public/federal.json')
    lista = ler_json(os.path.join(DIR, 'deputados.json'))
    if not lista:
        sys.exit('Sem dados federais. Rode:  python3 scripts/coletar_federal.py')
    pres = ler_json(os.path.join(DIR, 'presenca.json'), {})
    tse = (ler_json(os.path.join(DADOS, 'tse_federal.json'), {}) or {}).get('pessoas', {})

    votacoes = []
    for f in sorted(glob.glob(os.path.join(DIR, 'anos', '*-votacoes.json'))):
        votacoes += [v for v in ler_json(f) if v['t'] >= INICIO]
    votacoes.sort(key=lambda v: v['t'])
    props = []
    for f in sorted(glob.glob(os.path.join(DIR, 'anos', '*-proposicoes.json'))):
        props += ler_json(f)
    ceap = {}
    for f in sorted(glob.glob(os.path.join(DIR, 'anos', '*-ceap.json'))):
        for dep, cats in ler_json(f).items():
            d = ceap.setdefault(dep, {})
            for k, v in cats.items():
                d[k] = d.get(k, 0) + v

    # autoria
    autoria = {}
    for p in props:
        lei = 'Transformad' in (p['sit'] or '')
        for dep, ordem in p['autores']:
            a = autoria.setdefault(dep, dict(total=set(), principal=set(), leis=[]))
            a['total'].add(p['id'])
            if ordem == '1':
                a['principal'].add(p['id'])
            if lei and not any(l['id'] == p['id'] for l in a['leis']):
                a['leis'].append(dict(id=p['id'], p=p['p'], e=p['e'], data=p['data']))

    princ = principais(votacoes)
    em = ementas(sorted({v['chave'] for v in princ}))
    ordem = [str(d['id']) for d in sorted(lista, key=lambda d: d['nome'])]
    idx = {i: n for n, i in enumerate(ordem)}

    deps = []
    for d in sorted(lista, key=lambda d: d['nome']):
        i = str(d['id'])
        det = ler_json(os.path.join(DIR, 'det', f'{i}.json'), {})
        hist = ler_json(os.path.join(DIR, 'hist', f'{i}.json'), [])
        iv = intervalos(hist)
        primeiro = next((x for x in sorted(hist, key=lambda x: x.get('dataHora') or '')
                         if x.get('idLegislatura') == LEGISLATURA and x.get('situacao') == 'Exercício'
                         and (x.get('dataHora') or '') >= INICIO), {})
        anos = {a: r['p'] for a, r in sorted(pres.get(i, {}).items()) if r.get('p')}
        plen = [sum(v[k] for v in anos.values()) for k in range(3)]
        com = [sum((r.get('c') or [0, 0, 0])[k] for r in pres.get(i, {}).values()) for k in range(3)]
        nv = [v for v in votacoes if dentro(v['t'], iv)]
        votou = sum(1 for v in nv if i in v['votos'])
        gov = [v for v in nv if v.get('gov') in ('Sim', 'Não') and v['votos'].get(i) in ('Sim', 'Não')]
        a = autoria.get(i, dict(total=set(), principal=set(), leis=[]))
        leis = sorted(a['leis'], key=lambda l: l['data'], reverse=True)
        c = ceap.get(i, {})
        t = tse.get(i)
        deps.append(dict(
            id=i, nome=d['nome'], partido=d['siglaPartido'], uf=d['siglaUf'],
            foto=f'fotos/dep/{i}.jpg' if os.path.exists(os.path.join(PUBLIC, 'fotos', 'dep', f'{i}.jpg')) else None,
            nomeCivil=det.get('nomeCivil'), nasc=det.get('dataNascimento'), escolaridade=det.get('escolaridade'),
            inicio=(primeiro.get('dataHora') or '')[:10] or None, condicao=primeiro.get('condicaoEleitoral'),
            anos=anos, plen=plen, com=com,
            votacoes=len(nv), votou=votou, govAl=sum(1 for v in gov if v['votos'][i] == v['gov']), govN=len(gov),
            props=dict(total=len(a['total']), principal=len(a['principal']), leis=len(leis), leisLista=leis[:6]),
            ceap=round(sum(c.values()), 2), ceapCat=[[k, round(v, 2)] for k, v in sorted(c.items(), key=lambda x: -x[1])[:5]],
            tse=t))

    pv = []
    for v in princ:
        e = em.get(v['chave'], {})
        cod = ''.join(CODIGO.get(v['votos'].get(i), '-') for i in ordem)
        d = v['desc']
        pv.append(dict(id=v['id'], data=v['data'], prop=v['prop_nome'], ementa=e.get('ementa', ''), pid=e.get('id'),
                       res='Aprovado' if d.startswith('Aprov') else 'Rejeitado', sim=v['sim'], nao=v['nao'],
                       outros=v['outros'], gov=v.get('gov'), desc=d[:400], v=cod))
    pv.sort(key=lambda v: v['data'], reverse=True)

    novo = dict(gerado=dt.datetime.now().isoformat(timespec='minutes'),
                coletado=ler_json(os.path.join(DIR, 'coletado_em.json')),
                totalVotacoes=len(votacoes), ordem=ordem, deputados=deps, votacoes=pv,
                tseMunicipio='Uberlândia' if tse else None)
    ant = ler_json(SAIDA)
    erros = []
    if len(deps) < 500:
        erros.append(f'só {len(deps)} deputados')
    if ant and len(pv) < len(ant.get('votacoes', [])):
        erros.append(f"votações principais caíram de {len(ant['votacoes'])} para {len(pv)}")
    if sum(1 for x in deps if sum(x['plen'])) < 400:
        erros.append('presença faltando para muitos deputados')
    if erros and not forcar:
        log('  NÃO gravei o federal.json: ' + '; '.join(erros))
        sys.exit(1)
    salvar_json(SAIDA, novo, compacto=True)
    log(f'  ok: {len(deps)} deputados, {len(pv)} votações principais de {len(votacoes)} nominais, '
        f'{os.path.getsize(SAIDA) // 1024} KB')


if __name__ == '__main__':
    main()
