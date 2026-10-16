"""Câmara dos Deputados (API e arquivos de Dados Abertos) para a legislatura atual.

Baixa os 513 deputados em exercício, a presença oficial (páginas de cada deputado em
camara.leg.br), votações nominais do plenário, projetos apresentados e a cota parlamentar.
Anos passados ficam em cache em dados/federal/; o ano corrente é baixado de novo a cada
execução. Proposições dos anos passados são atualizadas uma vez por semana (um projeto
antigo pode virar lei depois).
"""
import csv
import datetime as dt
import html
import io
import os
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

from comum import DADOS, PUBLIC, baixar, ler_json, log, salvar_json

csv.field_size_limit(10**9)
API = 'https://dadosabertos.camara.leg.br/api/v2'
ARQ = 'https://dadosabertos.camara.leg.br/arquivos'
LEGISLATURA = 57
INICIO = dt.date(2023, 2, 1)
DIR = os.path.join(DADOS, 'federal')
FOTOS = os.path.join(PUBLIC, 'fotos', 'dep')
HOJE = dt.date.today()
ANOS = list(range(INICIO.year, HOJE.year + 1))
TIPOS_PROJ = {'PL', 'PLP', 'PEC', 'PDL'}


def velho(caminho, dias):
    try:
        return time.time() - os.path.getmtime(caminho) > dias * 86400
    except OSError:
        return True


def csv_remoto(url):
    corpo = baixar(url, json_=False, timeout=600)
    return csv.DictReader(io.StringIO(corpo.decode('utf-8-sig')), delimiter=';')


# --- deputados -----------------------------------------------------------------
def deputados():
    lista = baixar(f'{API}/deputados?itens=1000')['dados']
    if len(lista) < 500:
        raise RuntimeError(f'A API retornou só {len(lista)} deputados.')
    salvar_json(os.path.join(DIR, 'deputados.json'), lista)
    os.makedirs(FOTOS, exist_ok=True)

    def um(d):
        i = d['id']
        for tipo, url in (('det', f'{API}/deputados/{i}'), ('hist', f'{API}/deputados/{i}/historico')):
            arq = os.path.join(DIR, tipo, f'{i}.json')
            if velho(arq, 7):
                dados = baixar(url)['dados']
                if tipo == 'det':
                    dados.pop('cpf', None)  # o repositório é público; coletar_tse_federal.py busca na hora
                salvar_json(arq, dados)
        foto = os.path.join(FOTOS, f'{i}.jpg')
        if not os.path.exists(foto):
            try:
                open(foto, 'wb').write(baixar(d['urlFoto'], json_=False))
            except RuntimeError as e:
                log(f'  sem foto {d["nome"]}: {e}')

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(um, lista))
    log(f'  {len(lista)} deputados')
    return lista


# --- presença oficial (página de cada deputado) ---------------------------------
RX_PLEN = re.compile(r'Presença em Plenário.*?Presenças na Câmara (\d+) dias? Ausências justificadas (\d+) dias? '
                     r'Ausências não justificadas (\d+) dias?')
RX_COM = re.compile(r'Presença em comissões \? Presenças na Câmara (\d+) reuni\w+ Ausências justificadas (\d+) reuni\w+ '
                    r'Ausências não justificadas (\d+) reuni\w+')


def presenca(lista):
    arq = os.path.join(DIR, 'presenca.json')
    pres = ler_json(arq, {})
    tarefas = [(d['id'], a) for d in lista for a in ANOS
               if a == HOJE.year or str(a) not in pres.get(str(d['id']), {})]

    def uma(t):
        i, a = t
        try:
            s = baixar(f'https://www.camara.leg.br/deputados/{i}?ano={a}', json_=False).decode('utf-8', 'ignore')
        except RuntimeError:
            return t, None
        j = s.find('presencas__content')
        txt = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s[j:j + 15000])))
        p, c = RX_PLEN.search(txt), RX_COM.search(txt)
        return t, dict(p=[int(x) for x in p.groups()] if p else None, c=[int(x) for x in c.groups()] if c else None)

    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(uma, tarefas))
    falhas = 0
    for (i, a), r in res:
        if r and r['p'] is not None:
            pres.setdefault(str(i), {})[str(a)] = r
        else:
            falhas += 1
    salvar_json(arq, pres, compacto=True)
    log(f'  presença: {len(tarefas)} páginas lidas, {falhas} falhas')


# --- votações do plenário ------------------------------------------------------
def votacoes_ano(a):
    arq = os.path.join(DIR, 'anos', f'{a}-votacoes.json')
    if a < HOJE.year and os.path.exists(arq):
        return
    vt = {}
    for r in csv_remoto(f'{ARQ}/votacoes/csv/votacoes-{a}.csv'):
        n = sum(int(r[k] or 0) for k in ('votosSim', 'votosNao', 'votosOutros'))
        if r['siglaOrgao'] == 'PLEN' and n > 0:
            vt[r['id']] = dict(id=r['id'], t=r['dataHoraRegistro'], data=r['data'], desc=r['descricao'],
                              sim=int(r['votosSim'] or 0), nao=int(r['votosNao'] or 0), outros=int(r['votosOutros'] or 0),
                              prop=r.get('ultimaApresentacaoProposicao_idProposicao') or None, votos={})
    for r in csv_remoto(f'{ARQ}/votacoesVotos/csv/votacoesVotos-{a}.csv'):
        v = vt.get(r['idVotacao'])
        if v is not None:
            v['votos'][r['deputado_id']] = r['voto']
    for r in csv_remoto(f'{ARQ}/votacoesOrientacoes/csv/votacoesOrientacoes-{a}.csv'):
        v = vt.get(r['idVotacao'])
        if v is not None and r['siglaBancada'] == 'Governo':
            v['gov'] = r['orientacao']
    salvar_json(arq, list(vt.values()), compacto=True)
    log(f'  {a}: {len(vt)} votações nominais no plenário')


# --- proposições de autoria ----------------------------------------------------
def proposicoes_ano(a):
    arq = os.path.join(DIR, 'anos', f'{a}-proposicoes.json')
    if a < HOJE.year and not velho(arq, 7):
        return
    props = {}
    for r in csv_remoto(f'{ARQ}/proposicoes/csv/proposicoes-{a}.csv'):
        if r['siglaTipo'] in TIPOS_PROJ and (r['dataApresentacao'] or '') >= INICIO.isoformat():
            props[r['id']] = dict(id=r['id'], p=f"{r['siglaTipo']} {r['numero']}/{r['ano']}", e=(r['ementa'] or '')[:300],
                                  sit=r['ultimoStatus_descricaoSituacao'], data=r['dataApresentacao'][:10], autores=[])
    for r in csv_remoto(f'{ARQ}/proposicoesAutores/csv/proposicoesAutores-{a}.csv'):
        p = props.get(r['idProposicao'])
        if p is not None and r['proponente'] == '1' and r['idDeputadoAutor']:
            p['autores'].append([r['idDeputadoAutor'], r['ordemAssinatura']])
    salvar_json(arq, list(props.values()), compacto=True)
    log(f'  {a}: {len(props)} projetos (PL, PLP, PEC, PDL)')


# --- cota parlamentar (CEAP) ---------------------------------------------------
def ceap_ano(a):
    arq = os.path.join(DIR, 'anos', f'{a}-ceap.json')
    if a < HOJE.year and not velho(arq, 30):
        return
    z = zipfile.ZipFile(io.BytesIO(baixar(f'https://www.camara.leg.br/cotas/Ano-{a}.csv.zip', json_=False, timeout=600)))
    tot = {}
    with z.open(z.namelist()[0]) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig'), delimiter=';'):
            if r['codLegislatura'] != str(LEGISLATURA) or not r['ideCadastro']:
                continue
            v = float((r['vlrLiquido'] or '0').replace(',', '.'))
            d = tot.setdefault(r['ideCadastro'], {})
            d[r['txtDescricao']] = d.get(r['txtDescricao'], 0) + v
    salvar_json(arq, tot, compacto=True)
    log(f'  {a}: cota de {len(tot)} deputados')


def main():
    log('Câmara dos Deputados')
    lista = deputados()
    presenca(lista)
    for a in ANOS:
        votacoes_ano(a)
        proposicoes_ano(a)
        ceap_ano(a)
    salvar_json(os.path.join(DIR, 'coletado_em.json'), dt.datetime.now().isoformat(timespec='minutes'))


if __name__ == '__main__':
    main()
