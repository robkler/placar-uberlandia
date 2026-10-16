"""Gera public/mg.json (Minas Gerais: ALMG e Governo do Estado) a partir de dados/mg/.

Mesma checagem de segurança dos outros geradores (use --forcar para ignorar).
"""
import datetime as dt
import glob
import html
import os
import re
import sys
import unicodedata

from comum import DADOS, PUBLIC, ler_json, log, salvar_json

DIR = os.path.join(DADOS, 'mg')
SAIDA = os.path.join(PUBLIC, 'mg.json')

# Quem governa hoje (não vem de nenhuma API; atualize quando mudar).
GOVERNO_ATUAL = dict(
    nome='Mateus Simões', partido='PSD', desde='2026-03-22', tseNome='MATEUS',
    nota='Eleito vice-governador em 2022 na chapa de Romeu Zema (Novo). Assumiu o governo em março de 2026, '
         'quando Zema renunciou para disputar a Presidência.')


def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9 ]', '', s).strip()


def nome_autor(linha):
    linha = re.sub(r'^\s*Deputad[oa]\s+', '', linha)
    return re.split(r'\s{2,}', linha.strip())[0]


def ts(v):
    return v.get('$') if isinstance(v, dict) else v


def financas():
    pasta = os.path.join(DIR, 'tesouro')
    out = []
    for arq in sorted(glob.glob(os.path.join(pasta, '*-receitas.json'))):
        ano = int(os.path.basename(arq)[:4])
        rc = {i['conta']: i['valor'] for i in ler_json(arq)['items'] if i['coluna'] == 'Receitas Brutas Realizadas'}
        itens = ler_json(arq)['items']
        deducoes = sum(i['valor'] for i in itens if i['conta'].startswith('RECEITAS (EXCETO') and i['coluna'] != 'Receitas Brutas Realizadas')
        if not any(i['coluna'].startswith('Deduções - Transferências') for i in itens):
            continue  # anos antigos sem os repasses aos municípios como dedução não são comparáveis
        de = {i['conta']: i['valor'] for i in (ler_json(os.path.join(pasta, f'{ano}-despesas_funcao.json'), {'items': []}))['items']
              if i['coluna'] == 'Despesas Liquidadas'}

        def g(dic, pre):
            return next((v for k, v in dic.items() if k.startswith(pre)), 0)
        out.append(dict(ano=ano, receitaBruta=g(rc, 'RECEITAS (EXCETO'), receita=g(rc, 'RECEITAS (EXCETO') - deducoes, icms=g(rc, '1.1.1.4.50'), ipva=g(rc, '1.1.1.2.51'),
                        tributos=g(rc, '1.1.0.0.00'), uniao=g(rc, '1.7.1.0.00'), fpe=g(rc, '1.7.1.1.50'),
                        despesa=g(de, 'Despesas Exceto'),
                        funcoes={re.sub(r'^\d+ - ', '', k): v for k, v in de.items() if re.match(r'^\d{2} - ', k)}))
    return [f for f in out if f['receita'] and f['despesa']]


def main():
    forcar = '--forcar' in sys.argv
    log('Gerando public/mg.json')
    lista = ler_json(os.path.join(DIR, 'deputados.json'))
    if not lista:
        sys.exit('Sem dados de MG. Rode:  python3 scripts/coletar_mg.py')
    tse_all = ler_json(os.path.join(DADOS, 'tse_mg.json'), {'pessoas': {}, 'eleicaoGovernador': []})
    tse = tse_all['pessoas']

    projetos = []
    for f in sorted(glob.glob(os.path.join(DIR, 'projetos', '*.json'))):
        projetos += ler_json(f)
    por_nome = {norm(d['nome']): str(d['id']) for d in lista}
    autoria = {}
    gov_props = []
    for p in projetos:
        lei = 'norma jurídica' in (p.get('sit') or '').lower()
        linhas = [l for l in (p.get('autor') or '').split('\n') if l.strip()]
        if any(l.strip().lower().startswith('governador') for l in linhas):
            gov_props.append(dict(p=p['p'], e=p['e'], lei=lei, data=p['data']))
        for ordem, l in enumerate(linhas):
            dep = por_nome.get(norm(nome_autor(l)))
            if not dep:
                continue
            a = autoria.setdefault(dep, dict(total=0, principal=0, leis=[]))
            a['total'] += 1
            a['principal'] += ordem == 0
            if lei:
                a['leis'].append(dict(p=p['p'], e=p['e'], data=p['data']))

    deps = []
    for d in sorted(lista, key=lambda d: d['nome']):
        i = str(d['id'])
        det = ler_json(os.path.join(DIR, 'deputados', f'{i}.json'), {})
        verba = ler_json(os.path.join(DIR, 'verbas', f'{i}.json'), {})
        cat = {}
        for mes in verba.values():
            for k, v in mes.items():
                cat[k] = cat.get(k, 0) + v
        a = autoria.get(i, dict(total=0, principal=0, leis=[]))
        leis = sorted(a['leis'], key=lambda l: l['data'] or '', reverse=True)
        legs = [l.get('numeroLegislatura') for l in det.get('legislaturas', [])]
        t = tse.get(i)
        bio = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', det.get('vidaProfissionalPolitica') or ''))).strip()
        deps.append(dict(
            id=i, nome=d['nome'], partido=d.get('partido'), foto=(t or {}).get('foto'),
            nomeCompleto=det.get('nomeServidor'), nasc=det.get('dataNascimento'), sexo=det.get('sexo'),
            naturalidade=', '.join(x for x in (det.get('naturalidadeMunicipio'), det.get('naturalidadeUf')) if x),
            profissao=det.get('atividadeProfissional'), inicio=ts(det.get('inicioSituacao')), tipoMandato=det.get('tipoMandato'),
            mandatos=len(legs), bio=bio[:700],
            props=dict(total=a['total'], principal=a['principal'], leis=len(leis), leisLista=leis[:6]),
            verba=round(sum(cat.values()), 2), verbaMeses=len(verba),
            verbaCat=[[k, round(v, 2)] for k, v in sorted(cat.items(), key=lambda x: -x[1])[:5]],
            tse={k: t[k] for k in ('votos', 'votosLocal', 'patrimonio', 'partido2022', 'numero', 'ocupacao')} if t else None))

    # governo
    atual = dict(GOVERNO_ATUAL)
    p = next((p for k, p in tse.items() if k.startswith('gov-') and atual['tseNome'] in (p.get('nomeUrna') or '')), None)
    if p:
        atual.update(foto=p.get('foto'), patrimonio2022=p.get('patrimonio'), cargo2022=p.get('cargo'))
    eleito = next((p for k, p in tse.items() if k.startswith('gov-') and p.get('cargo') == 'GOVERNADOR'
                   and (p.get('situacao') or '').startswith('ELEITO')), None)
    reun = ler_json(os.path.join(DIR, 'reunioes.json'), {})
    pop = ler_json(os.path.join(DIR, 'tesouro', 'populacao.json'), {})
    novo = dict(
        gerado=dt.datetime.now().isoformat(timespec='minutes'), coletado=ler_json(os.path.join(DIR, 'coletado_em.json')),
        deputados=deps, reunioes=reun,
        governo=dict(atual=atual, eleito2022=dict(nome=eleito.get('nomeUrna'), partido=eleito.get('partido2022'),
                                                  foto=eleito.get('foto'), patrimonio=eleito.get('patrimonio')) if eleito else None,
                     eleicao=tse_all.get('eleicaoGovernador', []), fin=financas(), pop=pop,
                     projetos=dict(total=len(gov_props), leis=sum(1 for g in gov_props if g['lei']),
                                   lista=sorted(gov_props, key=lambda g: g['data'] or '', reverse=True)[:8])))
    erros = []
    if len(deps) < 70:
        erros.append(f'só {len(deps)} deputados')
    if sum(1 for x in deps if x['props']['total']) < 50:
        erros.append('poucos deputados com projetos (o formato do autor pode ter mudado)')
    if not novo['governo']['fin']:
        erros.append('sem contas do Estado')
    if erros and not forcar:
        log('  NÃO gravei o mg.json: ' + '; '.join(erros))
        sys.exit(1)
    salvar_json(SAIDA, novo, compacto=True)
    log(f"  ok: {len(deps)} deputados estaduais, {len(projetos)} projetos, {os.path.getsize(SAIDA) // 1024} KB")


if __name__ == '__main__':
    main()
