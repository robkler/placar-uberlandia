import json, glob, re, html, io, base64, collections, datetime as dt
import pandas as pd
from PIL import Image

R = '/home/claude/udi/raw/'; T = '/home/claude/udi/tse/'
TODAY = '2026-10-16'
sq = json.load(open(T + 'sq.json'))
S = set(sq.values())

def foto(key, w=150, h=200):
    try:
        im = Image.open(f'{T}fotos/{key}.jpg').convert('RGB')
    except Exception:
        return None
    # crop to 3:4 then resize
    W, H = im.size; tr = 3/4
    if W/H > tr:
        nw = int(H*tr); im = im.crop(((W-nw)//2, 0, (W-nw)//2+nw, H))
    else:
        nh = int(W/tr); im = im.crop((0, 0, W, nh))
    im = im.resize((w, h), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, 'JPEG', quality=74, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()

def strip(h):
    t = re.sub(r'<[^>]+>', ' ', h or ''); return re.sub(r'\s+', ' ', html.unescape(t)).strip()

# ---------- TSE ----------
cand = pd.read_csv(T+'consulta_cand_2024_MG.csv', sep=';', encoding='latin1', dtype=str)
cand = cand[cand.SQ_CANDIDATO.isin(S) & (cand.NR_TURNO == '1')].set_index('SQ_CANDIDATO')
bens = pd.read_csv(T+'bem_candidato_2024_MG.csv', sep=';', encoding='latin1', dtype=str)
bens = bens[bens.SQ_CANDIDATO.isin(S)].copy(); bens['v'] = bens.VR_BEM_CANDIDATO.str.replace(',', '.').astype(float)
rec = pd.read_csv(T+'receitas_candidatos_2024_MG.csv', sep=';', encoding='latin1', dtype=str)
rec = rec[rec.SQ_CANDIDATO.isin(S)].copy(); rec['v'] = rec.VR_RECEITA.str.replace(',', '.').astype(float)
def fonte(r):
    f = (r.DS_FONTE_RECEITA or '').upper()
    if 'FUNDO ESPECIAL' in f or 'FEFC' in f: return 'Fundo Eleitoral (público)'
    if 'PARTID' in f and 'FUNDO' in f: return 'Fundo Partidário (público)'
    o = r.DS_ORIGEM_RECEITA or ''
    return {'Recursos de pessoas físicas': 'Doações de pessoas físicas', 'Recursos próprios': 'Recursos do próprio candidato',
            'Recursos de outros candidatos': 'Outros candidatos', 'Recursos de partido político': 'Partido (outros recursos)',
            'Recursos de Financiamento Coletivo': 'Vaquinha online'}.get(o, 'Outros')
rec['f'] = rec.apply(fonte, axis=1)
vtse = pd.read_csv(T+'votacao_candidato_munzona_2024_MG.csv', sep=';', encoding='latin1', dtype=str)
vtse = vtse[vtse.SQ_CANDIDATO.isin(S) & (vtse.NR_TURNO == '1')].copy(); vtse['q'] = vtse.QT_VOTOS_NOMINAIS.astype(int)
votos_tse = vtse.groupby('SQ_CANDIDATO').q.sum().to_dict()

def tse_info(s):
    if s not in cand.index: return None
    c = cand.loc[s]
    b = bens[bens.SQ_CANDIDATO == s].sort_values('v', ascending=False)
    bt = b.groupby('DS_TIPO_BEM_CANDIDATO').v.sum().sort_values(ascending=False)
    r = rec[rec.SQ_CANDIDATO == s]
    rf = r.groupby('f').v.sum().sort_values(ascending=False)
    nasc = c.DT_NASCIMENTO
    idade = None
    try:
        d = dt.datetime.strptime(nasc, '%d/%m/%Y'); t = dt.datetime(2026, 10, 16)
        idade = t.year - d.year - ((t.month, t.day) < (d.month, d.day))
    except Exception: pass
    return dict(nomeUrna=c.NM_URNA_CANDIDATO, ocupacao=c.DS_OCUPACAO.capitalize() if isinstance(c.DS_OCUPACAO, str) else None,
                escolaridade=c.DS_GRAU_INSTRUCAO.capitalize() if isinstance(c.DS_GRAU_INSTRUCAO, str) else None,
                idade=idade, genero=c.DS_GENERO, numero=c.NR_CANDIDATO, situacao=c.DS_SIT_TOT_TURNO,
                votos2024=votos_tse.get(s),
                patrimonio=round(float(b.v.sum()), 2), bensN=int(len(b)),
                bensTipo=[[k, round(v, 2)] for k, v in bt.head(5).items()],
                campanha=round(float(r.v.sum()), 2), campanhaFonte=[[k, round(v, 2)] for k, v in rf.items()])

# ---------- Vereadores ----------
V = {}
for f in glob.glob(R+'ver/*.json'):
    d = json.load(open(f)); V[d['id']] = d

# ---------- Sessions & votes ----------
sessions = []
for f in glob.glob(R+'ses/*.json'):
    sessions.append(json.load(open(f)))
sessions.sort(key=lambda s: (s['date'], s.get('startTime') or ''))
names = {}
votacoes = []
TURN_MAP = {}
for s in sessions:
    for it in (s.get('votacao') or {}).get('items', []):
        if it.get('tipo_votacao') != 'Nominal' or 'title' not in it: continue
        votes = {}; vid = None
        for g in it.get('votos', []):
            for cat, lst in g.items():
                for x in lst:
                    votes[x['id']] = x['voto']; vid = vid or x.get('votacao_id')
                    names.setdefault(x['id'], dict(nome=x['title'], partido=(x.get('partido') or [{}])[0].get('token')))
        if not votes: continue
        res = (it.get('apuracao') or [{}])
        res = res[0].get('resultado') if res else None
        aut = it.get('autoria') or []
        mid = it.get('id')
        votacoes.append(dict(id=vid or f"{s['id']}-{mid}", sessao=s['id'], data=s['date'], sessaoNome=s['title'],
            materia=it['title'], materiaId=mid, ementa=(it.get('description') or '').strip(),
            autor=', '.join(a.get('title', '') for a in aut if a.get('primeiro_autor')) or ', '.join(a.get('title', '') for a in aut[:2]),
            autorTipo='Prefeitura' if any('Prefeito' in (a.get('title') or '') for a in aut) else ('Vereador' if aut else ''),
            turno=it.get('turno'), quorum=it.get('quorum'), resultado=res or 'Sem resultado registrado',
            sim=it.get('favoravel', 0), nao=it.get('contrario', 0), abst=it.get('abstencao', 0), aus=it.get('ausente', 0),
            votos=votes))
# dedupe identical ids
seen = set(); vv = []
for v in votacoes:
    if v['id'] in seen: continue
    seen.add(v['id']); vv.append(v)
votacoes = vv
print('votacoes', len(votacoes))

# majority side per vote (Sim vs Não among those who voted)
for v in votacoes:
    c = collections.Counter(v['votos'].values())
    v['maioria'] = 'Sim' if c['Sim'] >= c['Não'] else 'Não'
    v['disputada'] = min(c['Sim'], c['Não']) >= 3

# per vereador metrics
ver_out = []
for vid_, d in V.items():
    listed = [v for v in votacoes if vid_ in v['votos']]
    c = collections.Counter(v['votos'][vid_] for v in listed)
    sess_listed = collections.defaultdict(set)
    for v in listed: sess_listed[v['sessao']].add(v['votos'][vid_])
    sess_pres = sum(1 for s, vs in sess_listed.items() if vs - {'Ausente'})
    contra = sum(1 for v in listed if v['votos'][vid_] in ('Sim', 'Não') and v['votos'][vid_] != v['maioria'])
    votou = c['Sim'] + c['Não'] + c['Abstenção']
    # proposições 2025-2026 by tipo
    xy = d['proposicoes']['facets'].get('xy', [])
    labels = {t['value']: t['label'] for t in d['proposicoes']['facets'].get('tipo', [])}
    pt = collections.Counter()
    for r in xy:
        if r['ano'] in ('2025', '2026'): pt[labels.get(r['tipo'], r['tipo'])] += r['count']
    rel = sum(r['count'] for r in d['relatorias']['facets'].get('ano', []) if r['value'] in ('2025', '2026'))
    mand = d.get('mandatos') or []
    cur = next((m for m in mand if m.get('legislatura_ano_inicio') == 2025), mand[0] if mand else {})
    prev = [m for m in mand if m is not cur]
    com = [dict(nome=c_['comissao'], cargo=c_['title']) for c_ in d.get('comissoes', []) if (c_.get('end') or '9999') >= TODAY]
    mesa = [dict(nome=m.get('title') or m.get('description'), cargo=m.get('cargo') or m.get('title')) for m in d.get('mesas', [])] if d.get('mesas') else []
    s = sq.get(vid_)
    ver_out.append(dict(id=vid_, nome=d['title'], nomeCompleto=d['fullname'], partido=(d.get('partido_atual') or {}).get('sgl') or d.get('description'),
        foto=foto(vid_), bio=strip(d.get('biografia'))[:700], email=d.get('email'), tel=d.get('telefone_gabinete'),
        natureza=cur.get('natureza'), inicio=cur.get('start'), votosEleicao=cur.get('votos'),
        mandatosAnteriores=[dict(ini=m.get('legislatura_ano_inicio'), fim=m.get('legislatura_ano_fim'), natureza=m.get('natureza'), votos=m.get('votos')) for m in prev],
        filiacoes=[dict(p=f_.get('token'), ini=f_.get('data_filiacao'), fim=f_.get('data_desfiliacao')) for f_ in d.get('filiacoes', [])],
        sessoes=len(sess_listed), sessoesPres=sess_pres,
        nVot=len(listed), sim=c['Sim'], nao=c['Não'], abst=c['Abstenção'], aus=c['Ausente'], pres=c['Na Presidência'],
        votou=votou, contraMaioria=contra,
        props=dict(sorted(pt.items(), key=lambda x: -x[1])), propsTotal=sum(pt.values()), relatorias=rel,
        comissoes=com, tse=tse_info(s) if s else None))
ver_out.sort(key=lambda x: x['nome'])

# ---------- Prefeitura ----------
def dca(y, a):
    try: return json.load(open(f'/home/claude/udi/sic/{y}-{a}.json'))['items']
    except Exception: return []
fin = []
for y in range(2021, 2026):
    rc = {i['conta']: i['valor'] for i in dca(y, 'I-C') if i['coluna'] == 'Receitas Brutas Realizadas'}
    de = {i['conta']: i['valor'] for i in dca(y, 'I-E') if i['coluna'] == 'Despesas Liquidadas'}
    def g(dct, pre):
        for k, v in dct.items():
            if k.startswith(pre): return v
        return 0
    funcs = {re.sub(r'^\d+ - ', '', k): v for k, v in de.items() if re.match(r'^\d{2} - ', k)}
    fin.append(dict(ano=y, receita=g(rc, 'RECEITAS (EXCETO'), tributos=g(rc, '1.1.0.0.00'),
        iptu=g(rc, '1.1.1.2.50'), iss=g(rc, '1.1.1.4.51.1'), itbi=g(rc, '1.1.1.2.53'),
        uniao=g(rc, '1.7.1.0.00'), estado=g(rc, '1.7.2.0.00'), icms=g(rc, '1.7.2.1.50'), fpm=g(rc, '1.7.1.1.51.0'),
        despesa=g(de, 'Despesas Exceto'), funcoes=funcs))
pop = {2024: 754954, 2025: 761835}

pref = []
for k, cargo in (('prefeito', 'Prefeito'), ('vice', 'Vice-prefeito')):
    t = tse_info(sq[k]); t['cargo'] = cargo; t['foto'] = foto(k); t['partido'] = cand.loc[sq[k]].SG_PARTIDO
    pref.append(t)
# mayor results 2024
vtp = pd.read_csv(T+'votacao_candidato_munzona_2024_MG.csv', sep=';', encoding='latin1', dtype=str)
vtp = vtp[(vtp.SG_UE == '54038') & (vtp.DS_CARGO == 'Prefeito') & (vtp.NR_TURNO == '1')]
vtp['q'] = vtp.QT_VOTOS_NOMINAIS.astype(int)
eleicao = [dict(nome=n, partido=p, votos=int(q)) for (n, p), q in vtp.groupby(['NM_URNA_CANDIDATO', 'SG_PARTIDO']).q.sum().sort_values(ascending=False).items()]

pv = [v for v in votacoes if v['autorTipo'] == 'Prefeitura']
apr = sum(1 for v in pv if v['resultado'] and v['resultado'].startswith('Aprovado'))

out = dict(gerado=TODAY, vereadores=ver_out, votacoes=votacoes, nomes=names, prefeitura=dict(pessoas=pref, eleicao=eleicao, fin=fin, pop=pop,
          votacoesPrefeitura=len(pv), aprovadasPrefeitura=apr))
s = json.dumps(out, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
open('/home/claude/udi/data.json', 'w').write(s)
print(len(s)/1e6, 'MB')
for v in ver_out:
    print(v['nome'], v['partido'], v['natureza'], v['inicio'], v['sessoesPres'], '/', v['sessoes'], v['votou'], v['nVot'], v['aus'], v['pres'], v['contraMaioria'], v['propsTotal'], v['tse'] and v['tse']['patrimonio'], bool(v['foto']))
