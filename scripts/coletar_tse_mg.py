"""TSE · eleição de 2022 em Minas Gerais (rodar só depois de eleições ou troca de deputado).

Deputados estaduais em exercício: foto, votos em MG, votos em Uberlândia, patrimônio.
Governo: resultado para governador (MG e Uberlândia) e dados de quem governa hoje.
O deputado da ALMG é ligado ao candidato pelo número de urna da legislatura atual
(e, se não bater, pelo nome).

Requer:  pip install remotezip Pillow
Saída: dados/tse_mg.json e public/fotos/mg/*.jpg
"""
import csv
import io
import os
import sys
import unicodedata
import zipfile

from comum import DADOS, PUBLIC, TSE_MUNICIPIO, baixar, ler_json, log, salvar_json

try:
    from remotezip import RemoteZip
    from PIL import Image
except ImportError:
    sys.exit('Instale as dependências deste script:  pip install remotezip Pillow')

csv.field_size_limit(10**9)
ANO, UF, LEGISLATURA_ALMG = 2022, 'MG', 20
CDN = 'https://cdn.tse.jus.br/estatistica/sead'
CACHE = os.path.join(DADOS, 'tse_cache')
FOTOS = os.path.join(PUBLIC, 'fotos', 'mg')
CORRECOES = {}  # id ALMG -> SQ_CANDIDATO, se algum deputado não for encontrado


def norm(s):
    return unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().upper().strip()


def zip_local(nome):
    os.makedirs(CACHE, exist_ok=True)
    arq = os.path.join(CACHE, os.path.basename(nome))
    if not os.path.exists(arq):
        log(f'  baixando {os.path.basename(nome)}…')
        open(arq, 'wb').write(baixar(f'{CDN}/odsele/{nome}', json_=False, timeout=600))
    return zipfile.ZipFile(arq)


def ler(z, membro):
    return csv.DictReader(io.TextIOWrapper(z.open(membro), encoding='latin1'), delimiter=';')


def foto(dados, destino, w=300, h=400):
    im = Image.open(io.BytesIO(dados)).convert('RGB')
    W, H = im.size
    if W / H > w / h:
        nw = int(H * w / h); im = im.crop(((W - nw) // 2, 0, (W - nw) // 2 + nw, H))
    else:
        im = im.crop((0, 0, W, int(W * h / w)))
    im.resize((w, h), Image.LANCZOS).save(destino, 'JPEG', quality=78, optimize=True, progressive=True)


def main():
    log(f'TSE · Minas Gerais · eleição {ANO}')
    ids = [str(d['id']) for d in ler_json(os.path.join(DADOS, 'mg', 'deputados.json'), [])]
    if not ids:
        sys.exit('Rode antes:  python3 scripts/coletar_mg.py')
    almg = {i: ler_json(os.path.join(DADOS, 'mg', 'deputados', f'{i}.json'), {}) for i in ids}

    cand = list(ler(zip_local(f'consulta_cand/consulta_cand_{ANO}.zip'), f'consulta_cand_{ANO}_{UF}.csv'))
    est = [r for r in cand if r['DS_CARGO'] == 'DEPUTADO ESTADUAL' and r['NR_TURNO'] == '1']
    por_num = {r['NR_CANDIDATO']: r for r in est}
    alvo = {}
    for i, d in almg.items():
        if i in CORRECOES:
            alvo[i] = CORRECOES[i]; continue
        num = next((str(c['numeroCandidato']) for c in d.get('candidaturas', []) if c.get('legislatura') == LEGISLATURA_ALMG), None)
        r = por_num.get(num)
        if not r:
            m = [x for x in est if norm(x['NM_URNA_CANDIDATO']) == norm(d.get('nome')) or norm(x['NM_CANDIDATO']) == norm(d.get('nomeServidor'))]
            r = m[0] if len(m) == 1 else None
        if r:
            alvo[i] = r['SQ_CANDIDATO']
        else:
            log(f"  ATENÇÃO: não achei {d.get('nome')} no TSE. Adicione em CORRECOES.")
    gov = [r for r in cand if r['DS_CARGO'] in ('GOVERNADOR', 'VICE-GOVERNADOR')]
    for r in gov:
        alvo[f"gov-{r['SQ_CANDIDATO']}"] = r['SQ_CANDIDATO']
    S = set(alvo.values())
    por_sq = {r['SQ_CANDIDATO']: r for r in cand if r['SQ_CANDIDATO'] in S}

    pat = {}
    for r in ler(zip_local(f'bem_candidato/bem_candidato_{ANO}.zip'), f'bem_candidato_{ANO}_{UF}.csv'):
        if r['SQ_CANDIDATO'] in S:
            pat[r['SQ_CANDIDATO']] = pat.get(r['SQ_CANDIDATO'], 0) + float((r['VR_BEM_CANDIDATO'] or '0').replace(',', '.'))

    log('  lendo votação por município (arquivo grande, lido por partes)…')
    rz = RemoteZip(f'{CDN}/odsele/votacao_candidato_munzona/votacao_candidato_munzona_{ANO}.zip')
    tot, loc = {}, {}
    for r in ler(rz, f'votacao_candidato_munzona_{ANO}_{UF}.csv'):
        sq = r['SQ_CANDIDATO']
        if sq in S and r['NR_TURNO'] in ('1', '2'):
            k = (sq, r['NR_TURNO'])
            q = int(r['QT_VOTOS_NOMINAIS'] or 0)
            tot[k] = tot.get(k, 0) + q
            if r.get('CD_MUNICIPIO') == TSE_MUNICIPIO:
                loc[k] = loc.get(k, 0) + q

    log('  baixando fotos…')
    os.makedirs(FOTOS, exist_ok=True)
    fz = RemoteZip(f'{CDN}/eleicoes/eleicoes{ANO}/fotos/foto_cand{ANO}_{UF}_div.zip')
    nomes = set(fz.namelist())
    pessoas = {}
    for chave, sq in alvo.items():
        c = por_sq.get(sq, {})
        arq = None
        for ext in ('jpg', 'jpeg', 'png'):
            n = f'F{UF}{sq}_div.{ext}'
            if n in nomes:
                foto(fz.read(n), os.path.join(FOTOS, f'{chave}.jpg'))
                arq = f'fotos/mg/{chave}.jpg'
                break
        pessoas[chave] = dict(sq=sq, nomeUrna=c.get('NM_URNA_CANDIDATO'), cargo=c.get('DS_CARGO'),
                              partido2022=c.get('SG_PARTIDO'), numero=c.get('NR_CANDIDATO'),
                              ocupacao=(c.get('DS_OCUPACAO') or '').capitalize() or None,
                              situacao=c.get('DS_SIT_TOT_TURNO'),
                              votos=tot.get((sq, '1')), votosLocal=loc.get((sq, '1')),
                              votos2t=tot.get((sq, '2')), votosLocal2t=loc.get((sq, '2')),
                              patrimonio=round(pat.get(sq, 0), 2), foto=arq)
    eleicao = sorted(({'nome': p['nomeUrna'], 'partido': p['partido2022'], 'votos': p['votos'] or 0,
                       'votosLocal': p['votosLocal'] or 0, 'situacao': p['situacao']}
                      for k, p in pessoas.items() if k.startswith('gov-') and p['cargo'] == 'GOVERNADOR'),
                     key=lambda x: -x['votos'])
    salvar_json(os.path.join(DADOS, 'tse_mg.json'), dict(ano=ANO, pessoas=pessoas, eleicaoGovernador=eleicao))
    log(f"  ok: {sum(1 for k in pessoas if not k.startswith('gov-'))} deputados, {len(eleicao)} candidatos a governador")


if __name__ == '__main__':
    main()
