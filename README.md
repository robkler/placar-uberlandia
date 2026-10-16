# Placar de Uberlândia

Site estático que mostra os 27 vereadores de Uberlândia (presença, como votaram em cada
projeto, proposições, patrimônio e campanha) e as contas da Prefeitura.

A página (`public/index.html`) lê os dados de `public/data.json`. Esse arquivo é gerado
pelos scripts em `scripts/` a partir de fontes públicas e é atualizado quando você roda
o comando abaixo.

## Atualizar os dados

Precisa só do `python3` (já vem no macOS). Na pasta do projeto:

```bash
./atualizar.sh              # baixa os dados novos e gera public/data.json (~1 a 3 min)
./atualizar.sh --publicar   # faz o mesmo e publica na Vercel
./ver.sh                    # abre o site no seu computador em http://localhost:8000
```

Outras opções:

```bash
./atualizar.sh --tse        # recoleta dados do TSE (só depois de eleições ou troca de vereador)
./atualizar.sh --forcar     # grava o data.json mesmo se a checagem de segurança reclamar
```

O `--tse` precisa de duas bibliotecas extras, que você instala uma vez:
`pip3 install remotezip Pillow`

### Checagem de segurança

Antes de gravar, `gerar_dados.py` confere se os dados fazem sentido (27 vereadores, número de
votações não diminuiu, finanças presentes). Se a API da Câmara estiver fora do ar ou mudar de
formato, ele **não** sobrescreve o `data.json`, o site continua com a última versão boa e o
comando termina com erro explicando o motivo.

## Publicar na Vercel

**Primeira vez** (uma vez só):

1. Instale a CLI: `npm i -g vercel` (ou use `npx vercel`, o script já faz isso se precisar).
2. Na pasta do projeto, rode `vercel` e responda:
   - *Set up and deploy?* → Yes
   - *Link to existing project?* → No
   - *Project name* → placar-uberlandia
   - *In which directory is your code located?* → `./`
   - Não altere as configurações sugeridas (o `vercel.json` já define a pasta `public`).
3. Isso cria um link de teste. Para o endereço oficial: `vercel deploy --prod`.

**Depois disso**, para atualizar o site: `./atualizar.sh --publicar`.

O `.vercelignore` faz com que só a pasta `public/` seja enviada; scripts e dados brutos
ficam só no seu computador.

## Estrutura

```
public/                 o que vai para o ar
  index.html            a página
  data.json             gerado por scripts/gerar_dados.py
  fotos/                fotos oficiais do TSE (geradas por coletar_tse.py)
scripts/
  comum.py              configuração (município, legislatura) e funções comuns
  coletar_camara.py     vereadores e reuniões da Câmara (todo dia)
  coletar_tesouro.py    contas anuais da Prefeitura e população (todo dia, só baixa anos novos)
  coletar_tse.py        candidatos, bens, campanha e fotos (só após eleições)
  gerar_dados.py        junta tudo em public/data.json, com checagem de segurança
dados/                  dados brutos e cache (não vão para o site)
atualizar.sh            comando principal
ver.sh                  servidor local para testar
vercel.json             configuração da Vercel (pasta public, cache)
```

## Fontes e metodologia

| Dado | Fonte |
|---|---|
| Vereadores, reuniões, votações, proposições | API do site da Câmara Municipal (`camarauberlandia.mg.gov.br/++api++`) |
| Fotos, idade, patrimônio, campanha, votos | TSE, arquivos públicos em `cdn.tse.jus.br` |
| Receitas e despesas | Tesouro Nacional, SICONFI (Declaração de Contas Anuais) |
| População | IBGE, estimativas anuais |

- **Presença**: a lista de frequência oficial da Câmara não está sendo atualizada (vereadores que
  votaram aparecem com "falta"), por isso a presença é medida pelas votações nominais: o vereador
  conta como presente na reunião em que registrou pelo menos um voto ou presidiu a mesa.
  Reuniões sem votação nominal ficam fora da conta.
- **Votou contra a maioria**: votou sim quando a maioria votou não, ou o contrário.
- **Vetos e pareceres**: nessas votações "sim" e "não" se referem ao veto ou ao parecer, não ao projeto.
- **Campanha**: mostramos a origem do dinheiro (fundo eleitoral, pessoas físicas etc.), sem
  nomes de doadores.

## Quando algo mudar

- **Nova legislatura (2029)**: altere `LEGISLATURA_INICIO` em `scripts/comum.py` e rode
  `./atualizar.sh --tse` depois de ajustar `TSE_ANO_ELEICAO`.
- **Vereador novo (suplente assumiu)**: rode `./atualizar.sh --tse` para buscar foto e dados do TSE.
  Se o script avisar que não encontrou alguém, adicione o par em `CORRECOES` no
  `scripts/coletar_tse.py` (id da Câmara → número `SQ_CANDIDATO` do TSE).
- **Outra cidade**: mude os códigos em `scripts/comum.py`. Só funciona sem ajustes se a Câmara
  usar o mesmo sistema (Portal Modelo do Interlegis).

## Problemas comuns

- **`CERTIFICATE_VERIFY_FAILED`** ao rodar no Mac: o Python baixado do python.org precisa instalar
  os certificados uma vez. Rode `/Applications/Python\ 3*/Install\ Certificates.command`.
- **`NÃO gravei o data.json`**: a checagem de segurança encontrou algo estranho. Leia o motivo na
  mensagem; geralmente é a API da Câmara instável. Tente de novo mais tarde.
