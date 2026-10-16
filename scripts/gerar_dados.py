"""Junta o que foi coletado (dados/) e gera public/data.json para a página.

Antes de gravar, confere se os dados fazem sentido; se algo parecer quebrado
(API fora do ar, formato mudou), mantém o data.json anterior e sai com erro.
Use --forcar para gravar mesmo assim.
"""
import collections
import datetime as dt
import glob
import html
import os
import re
import sys

from comum import DADOS, PUBLIC, LEGISLATURA_INICIO, ler_json, log, salvar_json

CAMARA = os.path.join(DADOS, 'camara')
SAIDA = os.path.join(PUBLIC, 'data.json')


def limpar(h):
    t = re.sub(r'<[^>]+>', ' ', h or '')
    return re.sub(r'\s+', ' ', html.unescape(t)).strip()


def carregar_votacoes():
    sessoes = []
    for f in glob.glob(os.path.join(CAMARA, 'sessoes', '*.json')):
        s = ler_json(f)
        if s and (s.get('date') or '') >= f'{LEGISLATURA_INICIO}-01-01':
            sessoes.append(s)
    sessoes.sort(key=lambda s: (s['date'], s.get('startTime') or ''))
    nomes, votacoes, vistos = {}, [], set()
    for s in sessoes:
        for it in (s.get('votacao') or {}).get('items', []):
            if it.get('tipo_votacao') != 'Nominal' or 'title' not in it:
                continue
            votos, vid = {}, None
            for g in it.get('votos', []):
                for lista in g.values():
                    for x in lista:
                        votos[x['id']] = x['voto']
                        vid = vid or x.get('votacao_id')
                        nomes.setdefault(x['id'], dict(nome=x['title'], partido=(x.get('partido') or [{}])[0].get('token')))
            if not votos:
                continue
            vid = vid or f"{s['id']}-{it.get('id')}"
            if vid in vistos:
                continue
            vistos.add(vid)
            apur = it.get('apuracao') or []
            aut = it.get('autoria') or []
            principais = [a.get('title', '') for a in aut if a.get('primeiro_autor')] or [a.get('title', '') for a in aut[:2]]
            c = collections.Counter(votos.values())
            votacoes.append(dict(
                id=vid, sessao=s['id'], data=s['date'], sessaoNome=s['title'],
                materia=it['title'], materiaId=it.get('id'), ementa=(it.get('description') or '').strip(),
                autor=', '.join(principais),
                autorTipo='Prefeitura' if any('Prefeito' in (a.get('title') or '') for a in aut) else ('Vereador' if aut else ''),
                turno=it.get('turno'), quorum=it.get('quorum'),
                resultado=(apur[0].get('resultado') if apur else None) or 'Sem resultado registrado',
                sim=c['Sim'], nao=c['Não'], abst=c['Abstenção'], aus=c['Ausente'],
                votos=votos, maioria='Sim' if c['Sim'] >= c['Não'] else 'Não',
                disputada=min(c['Sim'], c['Não']) >= 3))
    return sessoes, votacoes, nomes


def montar_vereador(d, votacoes, tse, hoje):
    vid = d['id']
    listadas = [v for v in votacoes if vid in v['votos']]
    c = collections.Counter(v['votos'][vid] for v in listadas)
    por_sessao = collections.defaultdict(set)
    for v in listadas:
        por_sessao[v['sessao']].add(v['votos'][vid])
    presente = sum(1 for vs in por_sessao.values() if vs - {'Ausente'})
    contra = sum(1 for v in listadas if v['votos'][vid] in ('Sim', 'Não') and v['votos'][vid] != v['maioria'])
    anos = {str(a) for a in range(LEGISLATURA_INICIO, hoje.year + 1)}
    fac = (d.get('proposicoes') or {}).get('facets', {})
    rot = {t['value']: t['label'] for t in fac.get('tipo', [])}
    props = collections.Counter()
    for r in fac.get('xy', []):
        if r.get('ano') in anos:
            props[rot.get(r['tipo'], r['tipo'])] += r['count']
    relat = sum(r['count'] for r in (d.get('relatorias') or {}).get('facets', {}).get('ano', []) if r['value'] in anos)
    mand = d.get('mandatos') or []
    atual = next((m for m in mand if m.get('legislatura_ano_inicio') == LEGISLATURA_INICIO), mand[0] if mand else {})
    t = tse.get(vid)
    return dict(
        id=vid, nome=d['title'], nomeCompleto=d.get('fullname'),
        partido=(d.get('partido_atual') or {}).get('sgl') or d.get('description'),
        foto=(t or {}).get('foto'), bio=limpar(d.get('biografia'))[:700],
        email=d.get('email'), tel=d.get('telefone_gabinete'),
        natureza=atual.get('natureza'), inicio=atual.get('start'), votosEleicao=atual.get('votos'),
        mandatosAnteriores=[dict(ini=m.get('legislatura_ano_inicio'), fim=m.get('legislatura_ano_fim'),
                                 natureza=m.get('natureza'), votos=m.get('votos')) for m in mand if m is not atual],
        filiacoes=[dict(p=f.get('token'), ini=f.get('data_filiacao'), fim=f.get('data_desfiliacao')) for f in d.get('filiacoes', [])],
        sessoes=len(por_sessao), sessoesPres=presente,
        nVot=len(listadas), sim=c['Sim'], nao=c['Não'], abst=c['Abstenção'], aus=c['Ausente'], pres=c['Na Presidência'],
        votou=c['Sim'] + c['Não'] + c['Abstenção'], contraMaioria=contra,
        props=dict(props.most_common()), propsTotal=sum(props.values()), relatorias=relat,
        comissoes=[dict(nome=x['comissao'], cargo=x['title']) for x in d.get('comissoes', [])
                   if (x.get('end') or '9999') >= hoje.isoformat()],
        tse={k: v for k, v in t.items() if k not in ('foto', 'sq')} if t else None)


def financas():
    pasta = os.path.join(DADOS, 'tesouro')
    out = []
    for arq in sorted(glob.glob(os.path.join(pasta, '*-receitas.json'))):
        ano = int(os.path.basename(arq)[:4])
        rc = {i['conta']: i['valor'] for i in ler_json(arq)['items'] if i['coluna'] == 'Receitas Brutas Realizadas'}
        itens = ler_json(arq)['items']
        deducoes = sum(i['valor'] for i in itens if i['conta'].startswith('RECEITAS (EXCETO') and i['coluna'] != 'Receitas Brutas Realizadas')
        de_arq = ler_json(os.path.join(pasta, f'{ano}-despesas_funcao.json'), {'items': []})
        de = {i['conta']: i['valor'] for i in de_arq['items'] if i['coluna'] == 'Despesas Liquidadas'}

        def g(dic, pre):
            return next((v for k, v in dic.items() if k.startswith(pre)), 0)
        out.append(dict(
            ano=ano, receitaBruta=g(rc, 'RECEITAS (EXCETO'), receita=g(rc, 'RECEITAS (EXCETO') - deducoes, tributos=g(rc, '1.1.0.0.00'),
            iptu=g(rc, '1.1.1.2.50'), iss=g(rc, '1.1.1.4.51.1'), itbi=g(rc, '1.1.1.2.53'),
            uniao=g(rc, '1.7.1.0.00'), estado=g(rc, '1.7.2.0.00'), icms=g(rc, '1.7.2.1.50'), fpm=g(rc, '1.7.1.1.51.0'),
            despesa=g(de, 'Despesas Exceto'),
            funcoes={re.sub(r'^\d+ - ', '', k): v for k, v in de.items() if re.match(r'^\d{2} - ', k)}))
    return [f for f in out if f['receita'] and f['despesa']]


def validar(novo, anterior):
    erros = []
    if len(novo['vereadores']) < 20:
        erros.append(f"só {len(novo['vereadores'])} vereadores (esperado 27)")
    if anterior:
        a, n = len(anterior.get('votacoes', [])), len(novo['votacoes'])
        if n < a:
            erros.append(f'votações caíram de {a} para {n}')
    if not novo['prefeitura']['fin']:
        erros.append('sem dados financeiros da Prefeitura')
    sem_tse = [v['nome'] for v in novo['vereadores'] if not v['tse']]
    if sem_tse:
        log(f'  aviso: sem dados do TSE para {", ".join(sem_tse)} (rode coletar_tse.py se a composição mudou)')
    return erros


def main():
    forcar = '--forcar' in sys.argv
    hoje = dt.date.today()
    log('Gerando public/data.json')
    ids = ler_json(os.path.join(CAMARA, 'vereadores.json'))
    if not ids:
        sys.exit('Sem dados da Câmara. Rode:  python3 scripts/coletar_camara.py')
    tse_all = ler_json(os.path.join(DADOS, 'tse.json'), {'pessoas': {}, 'eleicaoPrefeito': []})
    tse = tse_all['pessoas']
    sessoes, votacoes, nomes = carregar_votacoes()
    vereadores = sorted((montar_vereador(ler_json(os.path.join(CAMARA, 'vereadores', f'{i}.json')), votacoes, tse, hoje)
                         for i in ids), key=lambda v: v['nome'])
    pv = [v for v in votacoes if v['autorTipo'] == 'Prefeitura']
    pessoas = []
    for k, cargo in (('prefeito', 'Prefeito'), ('vice', 'Vice-prefeito')):
        if k in tse:
            pessoas.append(dict(tse[k], cargo=cargo))
    pop = {int(k): v for k, v in (ler_json(os.path.join(DADOS, 'tesouro', 'populacao.json'), {}) or {}).items()}
    novo = dict(
        gerado=dt.datetime.now().isoformat(timespec='minutes'),
        coletadoCamara=ler_json(os.path.join(CAMARA, 'coletado_em.json')),
        vereadores=vereadores, votacoes=votacoes, nomes=nomes,
        prefeitura=dict(pessoas=pessoas, eleicao=tse_all.get('eleicaoPrefeito', []), fin=financas(), pop=pop,
                        votacoesPrefeitura=len(pv), aprovadasPrefeitura=sum(1 for v in pv if v['resultado'].startswith('Aprovado'))))
    erros = validar(novo, ler_json(SAIDA))
    if erros and not forcar:
        log('  NÃO gravei o data.json: ' + '; '.join(erros))
        log('  O site continua com a versão anterior. Use --forcar se tiver certeza.')
        sys.exit(1)
    salvar_json(SAIDA, novo, compacto=True)
    log(f'  ok: {len(vereadores)} vereadores, {len(votacoes)} votações, {os.path.getsize(SAIDA) // 1024} KB')


if __name__ == '__main__':
    main()
