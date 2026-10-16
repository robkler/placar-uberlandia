"""Baixa do Tesouro Nacional (SICONFI) as contas anuais da Prefeitura (DCA) e do IBGE a
população estimada. Os anos já baixados ficam em cache; só busca anos novos."""
import datetime as dt
import os

from comum import DADOS, IBGE_MUNICIPIO, baixar, ler_json, log, salvar_json

DIR = os.path.join(DADOS, 'tesouro')
ANO_INICIAL = 2021
ANEXOS = {'receitas': 'DCA-Anexo I-C', 'despesas_funcao': 'DCA-Anexo I-E'}


def main():
    log('Tesouro Nacional (SICONFI) e IBGE')
    os.makedirs(DIR, exist_ok=True)
    ultimo = dt.date.today().year - 1  # a DCA de um ano sai no início do ano seguinte
    for ano in range(ANO_INICIAL, ultimo + 1):
        for nome, anexo in ANEXOS.items():
            arq = os.path.join(DIR, f'{ano}-{nome}.json')
            if ler_json(arq, {}).get('items'):
                continue
            url = ('https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca?an_exercicio='
                   f'{ano}&no_anexo={anexo.replace(" ", "%20")}&id_ente={IBGE_MUNICIPIO}')
            try:
                d = baixar(url)
            except RuntimeError as e:
                log(f'  aviso: {e}')
                continue
            if d.get('items'):
                salvar_json(arq, d)
                log(f'  {ano} {nome}: {len(d["items"])} linhas')
            else:
                log(f'  {ano} {nome}: ainda não publicado')
    anos = '%7C'.join(str(a) for a in range(ultimo - 1, ultimo + 2))
    try:
        r = baixar(f'https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/{anos}/variaveis/9324'
                   f'?localidades=N6%5B{IBGE_MUNICIPIO}%5D')
        serie = r[0]['resultados'][0]['series'][0]['serie']
        pop = ler_json(os.path.join(DIR, 'populacao.json'), {})
        pop.update({k: int(v) for k, v in serie.items() if v and v.isdigit()})
        salvar_json(os.path.join(DIR, 'populacao.json'), pop)
        log(f'  população: {pop}')
    except Exception as e:
        log(f'  aviso: população não atualizada ({e})')


if __name__ == '__main__':
    main()
