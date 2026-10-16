"""Junta o que foi coletado (dados/) e gera public/data.json para a página.

Antes de gravar, confere se os dados fazem sentido; se algo parecer quebrado
(API fora do ar, formato mudou), mantém o data.json anterior e sai com erro.
Use --forcar para gravar mesmo assim.
"""
import collections
import datetime as dt
import glob
import html
import math
import os
import re
import sys
import unicodedata

from comum import DADOS, PUBLIC, LEGISLATURA_INICIO, ler_json, log, salvar_json

CAMARA = os.path.join(DADOS, 'camara')
SAIDA = os.path.join(PUBLIC, 'data.json')
# Lista de projetos de autoria principal por vereador (grande demais para o data.json; ver README).
SAIDA_PROJETOS = os.path.join(PUBLIC, 'projetos.json')


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


PREFIXOS_PROJETO = ('Projeto de Lei Ordinária', 'Projeto de Lei Complementar', 'Proposta de Emenda à Lei Orgânica')
RESSALVA_PROJETOS = 'Só entram projetos com votação nominal; aprovações em votação simbólica não aparecem.'
STATUS_PROJETO = ('aprovado', 'rejeitado', 'em_tramitacao', 'vetado')


def sem_acento(t):
    t = unicodedata.normalize('NFD', t or '')
    return re.sub(r'\s+', ' ', ''.join(c for c in t if not unicodedata.combining(c)).casefold()).strip()


def status_projeto(vots):
    """Status de um projeto a partir das suas votações nominais (já ordenadas por data e id).

    Vale a última votação que não é de veto: "Aprovado em 2ª Discussão", "Aprovado" ou discussão
    única aprovada = aprovado; "Aprovado em 1ª Discussão" ou "Rejeitado Parecer Contrário" (o
    projeto segue) = em_tramitacao; "Rejeitado" ou "Mantido Parecer Contrário" (arquivado) =
    rejeitado. Veto Mantido = vetado; Veto Rejeitado (veto derrubado) mantém aprovado.
    Qualquer outro resultado (ex.: "Aprovado Parecer da Comissão") é só parecer: não muda o
    status; sem votação decisiva o projeto fica em_tramitacao."""
    vetos = [v for v in vots if v['turno'] == 'Apreciar veto' or v['resultado'].startswith('Veto')]
    if vetos:
        return 'vetado' if vetos[-1]['resultado'].startswith('Veto Mantido') else 'aprovado'
    for v in reversed(vots):
        r = v['resultado']
        if r.startswith(('Aprovado em 2ª', 'Aprovado em Discussão Única')) or r == 'Aprovado':
            return 'aprovado'
        if r.startswith(('Aprovado em 1ª', 'Rejeitado Parecer Contrário')):
            return 'em_tramitacao'
        if r == 'Rejeitado' or r.startswith('Mantido Parecer Contrário'):
            return 'rejeitado'
    return 'em_tramitacao'


def resumo_vazio():
    return dict(votados=0, aprovados=0, rejeitados=0, emTramitacao=0, vetados=0)


def somar_resumo(r, status):
    r['votados'] += 1
    r[{'aprovado': 'aprovados', 'rejeitado': 'rejeitados', 'em_tramitacao': 'emTramitacao', 'vetado': 'vetados'}[status]] += 1


def projetos_votados(votacoes, vereadores, nomes):
    """Projetos de lei com votação nominal, por vereador (autoria) e no total da Câmara."""
    por_nome = {}
    for v in vereadores:
        por_nome[sem_acento(v['nome'])] = v['id']
    for i, n in nomes.items():
        por_nome.setdefault(sem_acento(n['nome']), i)
    ids_perfil = {v['id'] for v in vereadores}
    grupos = collections.defaultdict(list)
    for v in sorted(votacoes, key=lambda v: (v['data'], v['id'])):
        if v['materia'].startswith(PREFIXOS_PROJETO):
            grupos[v['materiaId']].append(v)
    por_ver = {v['id']: dict(**resumo_vazio(), lista=[]) for v in vereadores}
    novo_resumo = lambda: dict(**resumo_vazio(), porAutor={k: resumo_vazio() for k in ('prefeitura', 'vereadores', 'comissoes')})
    total, por_ano = novo_resumo(), collections.defaultdict(novo_resumo)
    sem_match = set()
    for mid, vots in grupos.items():
        ult = vots[-1]
        status = status_projeto(vots)
        if ult['autorTipo'] == 'Prefeitura':
            tipo, dono = 'prefeitura', None
        elif ult['autorTipo'] == 'Vereador':
            aut = ult['autor']
            if sem_acento(aut).startswith(('comissao', 'mesa diretora')):
                tipo, dono = 'comissoes', None
            else:
                tipo, dono = 'vereadores', por_nome.get(sem_acento(aut))
                if dono is None:
                    sem_match.add(aut)
                elif dono not in ids_perfil:
                    sem_match.add(f'{aut} (sem perfil, só no total)')
        else:
            tipo, dono = 'vereadores', None
            sem_match.add(f'{ult["materia"]} (sem autor)')
        for r in (total, por_ano[ult['data'][:4]]):
            somar_resumo(r, status)
            somar_resumo(r['porAutor'][tipo], status)
        if dono in por_ver:
            r = por_ver[dono]
            somar_resumo(r, status)
            r['lista'].append(dict(materia=ult['materia'], materiaId=mid, status=status, data=ult['data']))
    for r in por_ver.values():
        r['lista'].sort(key=lambda x: x['data'], reverse=True)
    if sem_match:
        log(f'  aviso: autores sem vereador com perfil: {"; ".join(sorted(sem_match))}')
    return por_ver, dict(ressalva=RESSALVA_PROJETOS, porAno=dict(sorted(por_ano.items())), total=total)


# Situação da última tramitação no e-processos que indica projeto aprovado (pela Câmara,
# com ou sem votação nominal), sancionado ou promulgado. Também conta como aprovado o projeto com norma
# jurídica derivada (lei), mesmo que a última tramitação seja só "Arquivado" (o que é o mais comum).
# Lista completa em .../consultas/materia/status_tramitacao_json; ver README.
SITUACOES_APROVADO = (
    'Aprovado', 'Aprovado - Art. 102-A, RI', 'Aprovado em 2ª Discussão', 'Aprovado em Discussão Única',
    'Aguardando Sanção/Veto Executivo', 'Redação Final', 'Promulgação', 'Juntada - Norma Promulgada',
    'Veto Rejeitado',
)
FONTE_PROPOSTOS = 'e-processos da Câmara (autoria principal: PL, PLC e PELO)'
# Sem votação nominal, a tramitação também pode mostrar rejeição ou veto mantido.
SITUACOES_REJEITADO = ('Rejeitado', 'Parecer Contrário Mantido')
SITUACOES_VETO_MANTIDO = ('Veto Mantido',)


def data_iso(br):
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})', br or '')
    return f'{m.group(3)}-{m.group(2)}-{m.group(1)}' if m else ''


def carregar_propostos(vid, hoje):
    """Projetos de autoria principal do vereador na legislatura (cache do e-processos), ou None se faltar algum ano."""
    itens = []
    for ano in range(LEGISLATURA_INICIO, hoje.year + 1):
        c = ler_json(os.path.join(CAMARA, 'propostos', f'{vid}-{ano}.json'))
        if c is None:
            return None
        itens += c['itens']
    return itens


def aprovado_por_tramitacao(m):
    return bool(m.get('norma_derivada')) or (m.get('ult_tramitacao') or {}).get('des_status') in SITUACOES_APROVADO


def status_proposto(m, vots):
    """Status de um projeto de autoria principal. Com votação nominal, vale status_projeto (em_tramitacao
    vira aprovado se a tramitação já mostra a aprovação). Sem votação nominal, vale a tramitação:
    aprovado, rejeitado, vetado (veto mantido) ou nao_votado (não chegou ao plenário)."""
    apr = aprovado_por_tramitacao(m)
    if vots:
        st = status_projeto(vots)
        return 'aprovado' if st == 'em_tramitacao' and apr else st
    sit = (m.get('ult_tramitacao') or {}).get('des_status')
    if apr:
        return 'aprovado'
    if sit in SITUACOES_REJEITADO:
        return 'rejeitado'
    if sit in SITUACOES_VETO_MANTIDO:
        return 'vetado'
    return 'nao_votado'


def resumo_propostos(lista):
    """Contagens dos projetos de autoria principal. propostos = aprovados + rejeitados + vetoMantido +
    emTramitacaoPlenario + naoChegaramAoPlenario."""
    c = collections.Counter(x['status'] for x in lista)
    aprovados = [x for x in lista if x['status'] == 'aprovado']
    n = len(lista)
    return dict(
        propostos=n, aprovados=len(aprovados),
        aprovadosNominal=sum(1 for x in aprovados if x['votado']),
        aprovadosSemVotoNominal=sum(1 for x in aprovados if not x['votado']),
        rejeitados=c['rejeitado'], vetoMantido=c['vetado'],
        emTramitacaoPlenario=c['em_tramitacao'], naoChegaramAoPlenario=c['nao_votado'],
        propostosVotacaoNominal=sum(1 for x in lista if x['votado']),
        pctAprovados=math.floor(len(aprovados) / n * 100 * 10 + 0.5) / 10 if n else None)  # como pctDe no chat


def propostos_do_vereador(itens, grupos):
    """Lista (mais recentes primeiro) e resumo dos projetos de autoria principal do vereador."""
    lista = []
    for m in itens:
        vots = grupos.get(str(m['cod_materia']))
        n = m.get('norma_derivada') or {}
        lista.append(dict(
            identificacao=(m.get('identificacao') or '').replace('n°', 'nº'), ementa=cortar(m.get('txt_ementa')),
            data=data_iso(m.get('dat_apresentacao')), situacao=(m.get('ult_tramitacao') or {}).get('des_status') or '',
            votado=bool(vots), status=status_proposto(m, vots), aprovadoPorTramitacao=aprovado_por_tramitacao(m),
            **({'norma': f"{n.get('sgl_norma')} {n.get('num_norma')}/{n.get('ano_norma')}"} if n else {}),
            fonte=m.get('detail_url') or ''))
    lista.sort(key=lambda x: (x['data'], x['identificacao']), reverse=True)
    return resumo_propostos(lista), lista


def primeiro_autor(m):
    return sem_acento((m.get('autores') or '').split(',')[0].rsplit(' - ', 1)[0])


def cortar(t, n=200):
    t = re.sub(r'\s+', ' ', t or '').strip()
    return t if len(t) <= n else t[:n - 1].rstrip() + '…'


def grupos_votacoes(votacoes):
    """Votações nominais de projetos de lei por matéria (id), em ordem de data."""
    grupos = collections.defaultdict(list)
    for v in sorted(votacoes, key=lambda v: (v['data'], v['id'])):
        if v['materia'].startswith(PREFIXOS_PROJETO) and v.get('materiaId'):
            grupos[str(v['materiaId'])].append(v)
    return grupos


def com_propostos(vereadores, votacoes, hoje, anterior, anterior_proj):
    """Põe em cada vereador.projetos.propostos o resumo dos projetos de autoria principal e devolve
    {id: lista} para projetos.json. Sem o cache do e-processos de algum ano, ou se o 1º autor da lista não
    for o vereador, mantém o resumo e a lista anteriores; sem anteriores, o vereador fica sem `propostos`
    (nada de "0 projetos" falso)."""
    grupos = grupos_votacoes(votacoes)
    ant = {str(v['id']): (v.get('projetos') or {}).get('propostos') for v in (anterior or {}).get('vereadores', [])}
    ant_lista = (anterior_proj or {}).get('vereadores', {})
    listas, faltando = {}, []
    for v in vereadores:
        itens = carregar_propostos(v['id'], hoje)
        nomes = {sem_acento(v.get('nome')), sem_acento(v.get('nomeCompleto'))}
        if itens is not None:
            outros = sorted({m.get('autores') for m in itens if primeiro_autor(m) not in nomes})
            if outros:
                log(f"  aviso: lista do e-processos de {v['nome']} tem outro 1º autor ({'; '.join(outros[:3])}); descartada")
                itens = None
        if itens is None:
            faltando.append(v['nome'])
            if isinstance(ant.get(v['id']), dict) and v['id'] in ant_lista:
                v['projetos']['propostos'] = ant[v['id']]
                listas[v['id']] = ant_lista[v['id']]
            continue
        v['projetos']['propostos'], listas[v['id']] = propostos_do_vereador(itens, grupos)
    if faltando:
        log(f'  aviso: sem projetos do e-processos para {", ".join(faltando)}; mantidos os anteriores (se houver)')
    return listas


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
    por_ver, camara_proj = projetos_votados(votacoes, vereadores, nomes)
    for v in vereadores:
        v['projetos'] = por_ver[v['id']]
    anterior = ler_json(SAIDA)
    listas = com_propostos(vereadores, votacoes, hoje, anterior, ler_json(SAIDA_PROJETOS))
    pv = [v for v in votacoes if v['autorTipo'] == 'Prefeitura']
    pessoas = []
    for k, cargo in (('prefeito', 'Prefeito'), ('vice', 'Vice-prefeito')):
        if k in tse:
            pessoas.append(dict(tse[k], cargo=cargo))
    pop = {int(k): v for k, v in (ler_json(os.path.join(DADOS, 'tesouro', 'populacao.json'), {}) or {}).items()}
    novo = dict(
        gerado=dt.datetime.now().isoformat(timespec='minutes'),
        coletadoCamara=ler_json(os.path.join(CAMARA, 'coletado_em.json')),
        vereadores=vereadores, votacoes=votacoes, nomes=nomes, camaraProjetos=camara_proj,
        prefeitura=dict(pessoas=pessoas, eleicao=tse_all.get('eleicaoPrefeito', []), fin=financas(), pop=pop,
                        votacoesPrefeitura=len(pv), aprovadasPrefeitura=sum(1 for v in pv if v['resultado'].startswith('Aprovado'))))
    erros = validar(novo, anterior)
    if erros and not forcar:
        log('  NÃO gravei o data.json: ' + '; '.join(erros))
        log('  O site continua com a versão anterior. Use --forcar se tiver certeza.')
        sys.exit(1)
    salvar_json(SAIDA, novo, compacto=True)
    salvar_json(SAIDA_PROJETOS, dict(gerado=novo['gerado'], fonte=FONTE_PROPOSTOS, vereadores=listas), compacto=True)
    log(f'  ok: {len(vereadores)} vereadores, {len(votacoes)} votações, {os.path.getsize(SAIDA) // 1024} KB '
        f'(+ projetos.json {os.path.getsize(SAIDA_PROJETOS) // 1024} KB)')


if __name__ == '__main__':
    main()
