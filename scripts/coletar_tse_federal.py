"""TSE · eleição de 2022 para deputado federal (rodar só depois de eleições).

Para cada deputado em exercício: votos totais em 2022, votos em Uberlândia (só para quem
concorreu por MG) e patrimônio declarado. O deputado é ligado ao candidato pelo CPF.

Requer:  pip install remotezip
Saída: dados/tse_federal.json
"""
import csv
import io
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor

from comum import DADOS, TSE_MUNICIPIO, baixar, ler_json, log, salvar_json

try:
    from remotezip import RemoteZip
except ImportError:
    sys.exit('Instale a dependência deste script:  pip install remotezip')

csv.field_size_limit(10**9)
ANO = 2022
UF_LOCAL = 'MG'
CDN = 'https://cdn.tse.jus.br/estatistica/sead/odsele'
API_CAMARA = 'https://dadosabertos.camara.leg.br/api/v2'
CACHE = os.path.join(DADOS, 'tse_cache')


def zip_local(nome):
    os.makedirs(CACHE, exist_ok=True)
    arq = os.path.join(CACHE, os.path.basename(nome))
    if not os.path.exists(arq):
        log(f'  baixando {os.path.basename(nome)}…')
        open(arq, 'wb').write(baixar(f'{CDN}/{nome}', json_=False, timeout=600))
    return zipfile.ZipFile(arq)


def ler(zf_or_rz, membro):
    f = zf_or_rz.open(membro)
    return csv.DictReader(io.TextIOWrapper(f, encoding='latin1'), delimiter=';')


def main():
    log(f'TSE · deputados federais · eleição {ANO}')
    deps = ler_json(os.path.join(DADOS, 'federal', 'deputados.json'))
    if not deps:
        sys.exit('Rode antes:  python3 scripts/coletar_federal.py')

    # O CPF não fica salvo em dados/ (o repositório é público): busca na API só para este cruzamento.
    def cpf(d):
        return baixar(f"{API_CAMARA}/deputados/{d['id']}")['dados'].get('cpf'), str(d['id'])

    with ThreadPoolExecutor(8) as ex:
        cpf_dep = {c.zfill(11): i for c, i in ex.map(cpf, deps) if c}

    zc = zip_local(f'consulta_cand/consulta_cand_{ANO}.zip')
    sq_dep, uf_dep = {}, {}
    for n in zc.namelist():
        if not n.endswith('.csv') or n.endswith(('_BR.csv', '_BRASIL.csv')):
            continue
        for r in ler(zc, n):
            if r['DS_CARGO'] != 'DEPUTADO FEDERAL':
                continue
            dep = cpf_dep.get((r['NR_CPF_CANDIDATO'] or '').zfill(11))
            if dep:
                sq_dep[r['SQ_CANDIDATO']] = dep
                uf_dep[dep] = r['SG_UF']
    log(f'  {len(set(sq_dep.values()))} de {len(deps)} deputados encontrados no TSE pelo CPF')

    zb = zip_local(f'bem_candidato/bem_candidato_{ANO}.zip')
    pat = {}
    for n in zb.namelist():
        if n.endswith('.csv') and not n.endswith(('_BR.csv', '_BRASIL.csv')):
            for r in ler(zb, n):
                dep = sq_dep.get(r['SQ_CANDIDATO'])
                if dep:
                    pat[dep] = pat.get(dep, 0) + float((r['VR_BEM_CANDIDATO'] or '0').replace(',', '.'))

    log('  lendo votação por município (arquivo grande, lido por partes)…')
    rz = RemoteZip(f'{CDN}/votacao_candidato_munzona/votacao_candidato_munzona_{ANO}.zip')
    total, local = {}, {}
    for uf in sorted(set(uf_dep.values())):
        membro = f'votacao_candidato_munzona_{ANO}_{uf}.csv'
        for r in ler(rz, membro):
            if r['DS_CARGO'].upper() != 'DEPUTADO FEDERAL':
                continue
            dep = sq_dep.get(r['SQ_CANDIDATO'])
            if not dep:
                continue
            q = int(r['QT_VOTOS_NOMINAIS'] or 0)
            total[dep] = total.get(dep, 0) + q
            if uf == UF_LOCAL and r.get('CD_MUNICIPIO') == TSE_MUNICIPIO:
                local[dep] = local.get(dep, 0) + q
    pessoas = {dep: dict(uf2022=uf_dep.get(dep), votos2022=total.get(dep), votosLocal=local.get(dep),
                         patrimonio=round(pat.get(dep, 0), 2)) for dep in set(sq_dep.values())}
    salvar_json(os.path.join(DADOS, 'tse_federal.json'), dict(ano=ANO, municipio='Uberlândia', pessoas=pessoas))
    log(f'  ok: {len(pessoas)} deputados → dados/tse_federal.json')


if __name__ == '__main__':
    main()
