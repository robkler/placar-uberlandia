"""Minas Gerais: Assembleia Legislativa (ALMG) e Governo do Estado.

ALMG (dadosabertos.almg.gov.br): deputados estaduais em exercício, projetos apresentados
(PL, PLC, PEC) desde 2023, reuniões de Plenário marcadas e realizadas, e verba indenizatória.
Governo: contas anuais do Estado no Tesouro (SICONFI) e população do IBGE.

Observação: a ALMG não publica em dados abertos a presença nem o voto de cada deputado.
Os meses de verba já baixados ficam em cache; só os 2 últimos meses são baixados de novo.
"""
import datetime as dt
import os
from concurrent.futures import ThreadPoolExecutor

from comum import DADOS, baixar, ler_json, log, salvar_json

API = 'https://dadosabertos.almg.gov.br/api/v2'
DIR = os.path.join(DADOS, 'mg')
INICIO = dt.date(2023, 2, 1)
HOJE = dt.date.today()
TIPOS = ('PL', 'PLC', 'PEC')
IBGE_UF = '31'


def j(path):
    sep = '&' if '?' in path else '?'
    return baixar(f'{API}/{path}{sep}formato=json', timeout=120)


def deputados():
    lista = j('deputados/em_exercicio')['list']
    if len(lista) < 70:
        raise RuntimeError(f'A ALMG retornou só {len(lista)} deputados.')

    def um(d):
        salvar_json(os.path.join(DIR, 'deputados', f"{d['id']}.json"), j(f"deputados/{d['id']}")['deputado'])
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(um, lista))
    salvar_json(os.path.join(DIR, 'deputados.json'), lista)
    log(f'  {len(lista)} deputados estaduais')
    return lista


def projetos():
    for ano in range(INICIO.year, HOJE.year + 1):
        arq = os.path.join(DIR, 'projetos', f'{ano}.json')
        dias = (dt.datetime.now().timestamp() - os.path.getmtime(arq)) / 86400 if os.path.exists(arq) else 999
        if ano < HOJE.year and dias < 7:
            continue
        itens = []
        for tipo in TIPOS:
            p = 1
            while True:
                r = j(f'proposicoes/pesquisa/direcionada?tipo={tipo}&ano={ano}&tp=100&p={p}&ord=0')
                r = r[list(r)[0]]
                lote = r.get('listaItem') or []
                for x in lote:
                    itens.append(dict(p=f"{x['siglaTipoProjeto']} {x['numero']}/{x['ano']}", tipo=x['siglaTipoProjeto'],
                                      e=(x.get('ementa') or '')[:300], autor=x.get('autor') or '',
                                      sit=x.get('situacao'), sitGeral=x.get('situacaoGeral'), data=x.get('dataPublicacao')))
                if len(lote) < 100 or p * 100 >= int(r.get('noOcorrencias') or 0):
                    break
                p += 1
        salvar_json(os.path.join(DIR, 'projetos', f'{ano}.json'), itens, compacto=True)
        log(f'  {ano}: {len(itens)} projetos (PL, PLC, PEC)')


def reunioes():
    out = {}
    for ano in range(INICIO.year, HOJE.year + 1):
        fim = min(dt.date(ano, 12, 31), HOJE)
        p, lista = 1, []
        while True:
            r = j(f'plenario/reunioes/pesquisa?ini={ano}0101&fim={fim:%Y%m%d}&tp=100&p={p}')['resultadoPesquisaReunioesPlenario']
            lote = r.get('listaReuniaoPlenario') or []
            lista += lote
            if len(lote) < 100:
                break
            p += 1
        c = {}
        for x in lista:
            t = x['tipoReuniao']['nome']
            if t not in ('ORDINÁRIA', 'EXTRAORDINÁRIA') or x['dia'] > HOJE.isoformat():
                continue
            k = c.setdefault(t, dict(marcadas=0, realizadas=0))
            k['marcadas'] += 1
            k['realizadas'] += x.get('reuniaoOcorrida') == 'S'
        out[str(ano)] = c
    salvar_json(os.path.join(DIR, 'reunioes.json'), out)
    log(f'  reuniões de Plenário: {out}')


def verbas(lista):
    pasta = os.path.join(DIR, 'verbas')
    os.makedirs(pasta, exist_ok=True)
    recentes = {(HOJE.year, HOJE.month), ((HOJE.replace(day=1) - dt.timedelta(days=1)).year,
                                          (HOJE.replace(day=1) - dt.timedelta(days=1)).month)}

    def um(d):
        i = d['id']
        arq = os.path.join(pasta, f'{i}.json')
        cache = ler_json(arq, {})
        try:
            datas = j(f'prestacao_contas/verbas_indenizatorias/deputados/{i}/datas')['listaFechamentoVerba']
        except RuntimeError:
            return 0
        n = 0
        for x in datas:
            a, m = int(x['dataReferencia'][:4]), int(x['dataReferencia'][5:7])
            if dt.date(a, m, 1) < INICIO.replace(day=1):
                continue
            chave = f'{a}-{m:02d}'
            if chave in cache and (a, m) not in recentes:
                continue
            try:
                itens = j(f'prestacao_contas/verbas_indenizatorias/deputados/{i}/{a}/{m}')['list']
            except RuntimeError:
                continue
            cache[chave] = {it['descTipoDespesa']: round(it['valor'], 2) for it in itens}
            n += 1
        salvar_json(arq, cache, compacto=True)
        return n
    with ThreadPoolExecutor(6) as ex:
        n = sum(ex.map(um, lista))
    log(f'  verba indenizatória: {n} meses baixados')


def estado():
    pasta = os.path.join(DIR, 'tesouro')
    os.makedirs(pasta, exist_ok=True)
    for ano in range(2021, HOJE.year):
        for nome, anexo in (('receitas', 'DCA-Anexo%20I-C'), ('despesas_funcao', 'DCA-Anexo%20I-E')):
            arq = os.path.join(pasta, f'{ano}-{nome}.json')
            if (ler_json(arq, {}) or {}).get('items'):
                continue
            try:
                d = baixar(f'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca?an_exercicio={ano}&no_anexo={anexo}&id_ente={IBGE_UF}')
            except RuntimeError as e:
                log(f'  aviso: {e}'); continue
            if d.get('items'):
                salvar_json(arq, d)
    anos = '%7C'.join(str(a) for a in range(HOJE.year - 2, HOJE.year + 1))
    try:
        r = baixar(f'https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/{anos}/variaveis/9324?localidades=N3%5B{IBGE_UF}%5D')
        pop = ler_json(os.path.join(pasta, 'populacao.json'), {})
        pop.update({k: int(v) for k, v in r[0]['resultados'][0]['series'][0]['serie'].items() if v and v.isdigit()})
        salvar_json(os.path.join(pasta, 'populacao.json'), pop)
    except Exception as e:
        log(f'  aviso: população de MG não atualizada ({e})')
    log('  contas do Estado e população ok')


def main():
    log('Minas Gerais (ALMG e Governo do Estado)')
    lista = deputados()
    projetos()
    reunioes()
    verbas(lista)
    estado()
    salvar_json(os.path.join(DIR, 'coletado_em.json'), dt.datetime.now().isoformat(timespec='minutes'))


if __name__ == '__main__':
    main()
