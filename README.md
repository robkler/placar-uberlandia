# Placar de Uberlândia

**No ar em: https://placar-uberlandia.vercel.app**

Site estático que mostra os 27 vereadores de Uberlândia (presença, como votaram em cada
projeto, proposições, patrimônio e campanha) e as contas da Prefeitura.

A página (`public/index.html`) lê os dados de `public/data.json`. Esse arquivo é gerado
pelos scripts em `scripts/` a partir de fontes públicas e é atualizado todo dia
automaticamente (veja [Atualização automática](#atualização-automática)).

> **Aviso:** projeto independente, sem vínculo com a Câmara Municipal, a Prefeitura de
> Uberlândia ou qualquer partido. Os dados são copiados de fontes oficiais e podem conter
> erros ou atrasos; na dúvida, confira na fonte. Achou algo errado?
> [Abra uma issue](https://github.com/robkler/placar-uberlandia/issues/new?template=dado-incorreto.yml).

## Atualizar os dados

Precisa só do `python3` (já vem no macOS). Se você usa o [mise](https://mise.jdx.dev),
`mise install` instala as versões do projeto (definidas em `mise.toml`). Na pasta do projeto:

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

## Atualização automática

A GitHub Action `.github/workflows/atualizar-dados.yml` roda todo dia às 6h (horário de
Brasília): executa `./atualizar.sh` e, se algum dado mudou, faz commit em `dados/` e
`public/`. O histórico de commits desses arquivos serve de registro público de como os
dados mudaram. Para rodar na hora: aba *Actions* → *Atualizar dados* → *Run workflow*.

## Publicar na Vercel

O projeto `placar-uberlandia` na Vercel está ligado a este repositório: todo push na `main`
(inclusive os commits da atualização automática) publica o site.

Para publicar direto do seu computador, sem passar pelo GitHub: `./atualizar.sh --publicar`
(precisa da CLI, `npm i -g vercel`, e de `vercel link` uma vez).

O `vercel.json` faz a Vercel servir só a pasta `public/`; o `.vercelignore` evita enviar
scripts e dados brutos nos deploys pela CLI.

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

## Contribuir

- **Dado errado**: abra uma issue com o modelo
  [Dado incorreto](https://github.com/robkler/placar-uberlandia/issues/new?template=dado-incorreto.yml),
  com o link da fonte oficial.
- **Código**: pull requests são bem-vindos. Rode `./atualizar.sh` e `./ver.sh` para conferir
  a mudança antes de enviar.

## Licença

- **Código** (scripts, página, configuração): [MIT](LICENSE).
- **Dados** (`dados/`, `public/data.json`): dados públicos da Câmara Municipal de Uberlândia,
  do TSE, do Tesouro Nacional (SICONFI) e do IBGE. Pertencem a essas fontes e não estão
  sob a licença MIT; ao reutilizar, cite a fonte original.
- **Fotos** (`public/fotos/`): fotos oficiais de candidatura divulgadas pelo TSE; também não
  estão sob a licença MIT.
