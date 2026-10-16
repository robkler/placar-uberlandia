"""Dados eleitorais do TSE (rodar só depois de uma eleição ou se mudar a composição da Câmara).

Para cada vereador em exercício, o prefeito e o vice: foto oficial, idade, ocupação,
escolaridade, votos, patrimônio declarado e origem do dinheiro da campanha.
Também guarda o resultado da eleição para prefeito.

Requer:  pip install remotezip Pillow
Usa os arquivos públicos de cdn.tse.jus.br. Os arquivos grandes (fotos e prestação de
contas, mais de 1 GB) são lidos por partes, sem baixar o arquivo inteiro.
Saída: dados/tse.json e public/fotos/*.jpg
"""
import csv
import datetime as dt
import io
import os
import sys
import unicodedata
import zipfile

from comum import (DADOS, PUBLIC, TSE_ANO_ELEICAO, TSE_MUNICIPIO, baixar, ler_json, log,
                   salvar_json)

try:
    from remotezip import RemoteZip
    from PIL import Image
except ImportError:
    sys.exit('Instale as dependências deste script:  pip install remotezip Pillow')

csv.field_size_limit(10**9)
ANO = TSE_ANO_ELEICAO
CDN = 'https://cdn.tse.jus.br/estatistica/sead'
CACHE = os.path.join(DADOS, 'tse_cache')

# Quando o nome cadastrado na Câmara não bate com o do TSE, informe aqui:
# id do vereador na Câmara -> SQ_CANDIDATO no TSE
CORRECOES = {
    '399041': '130002278033',  # Antônio Carrijo
}


def norm(s):
    return unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().upper().strip()


def zip_local(nome):
    os.makedirs(CACHE, exist_ok=True)
    arq = os.path.join(CACHE, os.path.basename(nome))
    if not os.path.exists(arq):
        log(f'  baixando {os.path.basename(nome)}…')
        open(arq, 'wb').write(baixar(f'{CDN}/odsele/{nome}', json_=False, timeout=600))
    return zipfile.ZipFile(arq)


def linhas(zf, membro, filtro):
    with zf.open(membro) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin1'), delimiter=';'):
            if filtro(r):
                yield r


def valor(s):
    try:
        return float((s or '0').replace(',', '.'))
    except ValueError:
        return 0.0


def fonte(r):
    f = (r.get('DS_FONTE_RECEITA') or '').upper()
    if 'FUNDO ESPECIAL' in f or 'FEFC' in f:
        return 'Fundo Eleitoral (público)'
    if 'PARTID' in f and 'FUNDO' in f:
        return 'Fundo Partidário (público)'
    return {'Recursos de pessoas físicas': 'Doações de pessoas físicas',
            'Recursos próprios': 'Recursos do próprio candidato',
            'Recursos de outros candidatos': 'Outros candidatos',
            'Recursos de partido político': 'Partido (outros recursos)',
            'Recursos de Financiamento Coletivo': 'Vaquinha online'}.get(r.get('DS_ORIGEM_RECEITA'), 'Outros')


def foto_jpg(dados, destino, w=300, h=400):
    im = Image.open(io.BytesIO(dados)).convert('RGB')
    W, H = im.size
    if W / H > w / h:
        nw = int(H * w / h); im = im.crop(((W - nw) // 2, 0, (W - nw) // 2 + nw, H))
    else:
        nh = int(W * h / w); im = im.crop((0, 0, W, nh))
    im.resize((w, h), Image.LANCZOS).save(destino, 'JPEG', quality=78, optimize=True, progressive=True)


def main():
    log(f'TSE · eleição {ANO} · município {TSE_MUNICIPIO}')
    ver_ids = ler_json(os.path.join(DADOS, 'camara', 'vereadores.json'))
    if not ver_ids:
        sys.exit('Rode antes:  python3 scripts/coletar_camara.py')
    ver = {i: ler_json(os.path.join(DADOS, 'camara', 'vereadores', f'{i}.json')) for i in ver_ids}

    # Candidaturas (1º turno)
    zc = zip_local(f'consulta_cand/consulta_cand_{ANO}.zip')
    cand = list(linhas(zc, f'consulta_cand_{ANO}_MG.csv',
                       lambda r: r['SG_UE'] == TSE_MUNICIPIO and r['NR_TURNO'] == '1'))
    por_sq = {r['SQ_CANDIDATO']: r for r in cand}
    vereadores_tse = [r for r in cand if r['DS_CARGO'] == 'VEREADOR']

    alvo = {}  # chave -> SQ_CANDIDATO
    for i, v in ver.items():
        if i in CORRECOES:
            alvo[i] = CORRECOES[i]; continue
        m = [r for r in vereadores_tse if norm(r['NM_CANDIDATO']) == norm(v.get('fullname'))]
        if len(m) != 1:
            m = [r for r in vereadores_tse if norm(r['NM_URNA_CANDIDATO']) == norm(v.get('title'))]
        if len(m) == 1:
            alvo[i] = m[0]['SQ_CANDIDATO']
        else:
            log(f'  ATENÇÃO: não achei {v.get("title")} ({v.get("fullname")}) no TSE. Adicione em CORRECOES.')
    eleito = [r for r in cand if r['DS_CARGO'] == 'PREFEITO' and r['DS_SIT_TOT_TURNO'].startswith('ELEITO')]
    if eleito:
        alvo['prefeito'] = eleito[0]['SQ_CANDIDATO']
        vice = [r for r in cand if r['DS_CARGO'] == 'VICE-PREFEITO' and r['NR_CANDIDATO'] == eleito[0]['NR_CANDIDATO']]
        if vice:
            alvo['vice'] = vice[0]['SQ_CANDIDATO']
    S = set(alvo.values())

    # Bens
    zb = zip_local(f'bem_candidato/bem_candidato_{ANO}.zip')
    bens = {}
    for r in linhas(zb, f'bem_candidato_{ANO}_MG.csv', lambda r: r['SQ_CANDIDATO'] in S):
        bens.setdefault(r['SQ_CANDIDATO'], []).append((r['DS_TIPO_BEM_CANDIDATO'], valor(r['VR_BEM_CANDIDATO'])))

    # Votos (todos os candidatos a prefeito, e os nossos)
    zv = zip_local(f'votacao_candidato_munzona/votacao_candidato_munzona_{ANO}.zip')
    votos, prefeitos = {}, {}
    for r in linhas(zv, f'votacao_candidato_munzona_{ANO}_MG.csv',
                    lambda r: r['SG_UE'] == TSE_MUNICIPIO and r['NR_TURNO'] == '1'):
        q = int(r['QT_VOTOS_NOMINAIS'] or 0)
        votos[r['SQ_CANDIDATO']] = votos.get(r['SQ_CANDIDATO'], 0) + q
        if r['DS_CARGO'].upper() == 'PREFEITO':
            k = (r['NM_URNA_CANDIDATO'], r['SG_PARTIDO'])
            prefeitos[k] = prefeitos.get(k, 0) + q

    # Receitas de campanha (arquivo remoto grande, lido por partes)
    log('  lendo prestação de contas (pode levar alguns minutos)…')
    rz = RemoteZip(f'{CDN}/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ANO}.zip')
    rec = {}
    with rz.open(f'receitas_candidatos_{ANO}_MG.csv') as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin1'), delimiter=';'):
            if r['SQ_CANDIDATO'] in S:
                d = rec.setdefault(r['SQ_CANDIDATO'], {})
                d[fonte(r)] = d.get(fonte(r), 0) + valor(r['VR_RECEITA'])

    # Fotos
    log('  baixando fotos…')
    pasta_fotos = os.path.join(PUBLIC, 'fotos')
    os.makedirs(pasta_fotos, exist_ok=True)
    fz = RemoteZip(f'{CDN}/eleicoes/eleicoes{ANO}/fotos/foto_cand{ANO}_MG_div.zip')
    nomes = set(fz.namelist())
    fotos = {}
    for chave, sq in alvo.items():
        for ext in ('jpg', 'jpeg', 'png'):
            n = f'FMG{sq}_div.{ext}'
            if n in nomes:
                foto_jpg(fz.read(n), os.path.join(pasta_fotos, f'{chave}.jpg'))
                fotos[chave] = f'fotos/{chave}.jpg'
                break
        else:
            log(f'  sem foto no TSE: {chave}')

    hoje = dt.date.today()
    pessoas = {}
    for chave, sq in alvo.items():
        c = por_sq.get(sq, {})
        idade = None
        try:
            n = dt.datetime.strptime(c.get('DT_NASCIMENTO', ''), '%d/%m/%Y').date()
            idade = hoje.year - n.year - ((hoje.month, hoje.day) < (n.month, n.day))
        except ValueError:
            pass
        b = bens.get(sq, [])
        tipos = {}
        for t, v in b:
            tipos[t] = tipos.get(t, 0) + v
        rf = rec.get(sq, {})
        pessoas[chave] = dict(
            sq=sq, nomeUrna=c.get('NM_URNA_CANDIDATO'), partido=c.get('SG_PARTIDO'),
            ocupacao=(c.get('DS_OCUPACAO') or '').capitalize() or None,
            escolaridade=(c.get('DS_GRAU_INSTRUCAO') or '').capitalize() or None,
            nascimento=c.get('DT_NASCIMENTO'), idade=idade, genero=c.get('DS_GENERO'),
            numero=c.get('NR_CANDIDATO'), situacao=c.get('DS_SIT_TOT_TURNO'), votos2024=votos.get(sq),
            patrimonio=round(sum(v for _, v in b), 2), bensN=len(b),
            bensTipo=[[k, round(v, 2)] for k, v in sorted(tipos.items(), key=lambda x: -x[1])[:5]],
            campanha=round(sum(rf.values()), 2),
            campanhaFonte=[[k, round(v, 2)] for k, v in sorted(rf.items(), key=lambda x: -x[1])],
            foto=fotos.get(chave))
    eleicao = [dict(nome=n, partido=p, votos=q) for (n, p), q in sorted(prefeitos.items(), key=lambda x: -x[1])]
    salvar_json(os.path.join(DADOS, 'tse.json'), dict(ano=ANO, gerado=hoje.isoformat(), pessoas=pessoas,
                                                      eleicaoPrefeito=eleicao))
    log(f'  {len(pessoas)} pessoas, {len(fotos)} fotos → dados/tse.json')


if __name__ == '__main__':
    main()
