# Placar de Uberlândia

**No ar em: https://placar-uberlandia.vercel.app**

Site estático com dois lados, escolhidos no seletor do topo:

- **Uberlândia**: os 27 vereadores (presença, como votaram em cada projeto, proposições,
  patrimônio e campanha) e as contas da Prefeitura. Dados em `public/data.json`.
- **Minas Gerais**: os 77 deputados estaduais da ALMG (projetos, leis, verba indenizatória,
  votos em Uberlândia em 2022) e o Governo do Estado (governador, eleição de 2022, projetos do
  governo na Assembleia, receitas e despesas). Dados em `public/mg.json`.
- **Câmara dos Deputados**: os 513 deputados federais, abrindo filtrado em Minas Gerais e
  ordenado por votos recebidos em Uberlândia em 2022 (presença oficial, principais votações,
  projetos, cota parlamentar). Dados em `public/federal.json`, carregado só quando a pessoa abre
  esse lado.

Os arquivos são gerados pelos scripts em `scripts/` a partir de fontes públicas e são
atualizados todo dia automaticamente (veja [Atualização automática](#atualização-automática)).

> **Aviso:** projeto independente, sem vínculo com a Câmara Municipal, a Prefeitura de
> Uberlândia, a ALMG, o Governo de Minas, a Câmara dos Deputados ou qualquer partido. Os dados são copiados de fontes
> oficiais e podem conter erros ou atrasos; na dúvida, confira na fonte. Achou algo errado?
> [Abra uma issue](https://github.com/robkler/placar-uberlandia/issues/new?template=dado-incorreto.yml).

## Atualizar os dados

Precisa só do `python3` (já vem no macOS). Se você usa o [mise](https://mise.jdx.dev),
`mise install` instala as versões do projeto (definidas em `mise.toml`). Na pasta do projeto:

```bash
./atualizar.sh              # baixa os dados novos e gera data.json, mg.json e federal.json (~5 a 10 min)
./atualizar.sh --publicar   # faz o mesmo e publica na Vercel
./ver.sh                    # abre o site no seu computador em http://localhost:8000
```

Outras opções:

```bash
./atualizar.sh --so-uberlandia   # só Uberlândia (~1 min)
./atualizar.sh --so-mg           # só Minas Gerais
./atualizar.sh --so-federal      # só a Câmara dos Deputados
./atualizar.sh --tse        # recoleta dados do TSE (só depois de eleições ou troca de parlamentar)
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

O `vercel.json` faz a Vercel servir só a pasta `public/` e publicar `api/chat.ts` como função
(com os três JSONs incluídos); o `.vercelignore` evita enviar scripts, dados brutos e testes nos
deploys pela CLI.

## Chat

O painel de chat do site responde perguntas sobre os dados do placar (presença, votações,
proposições, contas da Prefeitura e do Estado, governo de Minas). Roda numa Vercel Function
(`api/chat.ts`) com um agente Pi e o modelo DeepSeek, e consulta só `public/data.json`,
`mg.json` e `federal.json`.

- **O que faz**: busca políticos por nome, monta rankings (por exemplo, quem mais faltou), mostra
  como cada um votou e resume as contas. Toda resposta sobre uma pessoa traz o link do placar
  (`#v/<id>`, `#e/<id>`, `#d/<id>`) e o link oficial.
- **O que não faz**: não opina, não adjetiva político, não recomenda voto e não responde sobre
  assuntos fora dos dados. A ALMG não publica presença nem voto individual, então para
  deputado estadual ele diz isso em vez de dar um número.
- **Limites**: mensagem de até 500 caracteres, histórico de 10 mensagens e até 4.000 caracteres no total
  (o navegador descarta as mensagens mais antigas para caber), 50 s por pergunta (a função da Vercel
  tem teto de 60 s).
  `/api/chat` tem limite por IP no firewall da Vercel (10 requisições por 60 s; acima disso,
  responde 429).

Variáveis de ambiente (na Vercel, em *Settings → Environment Variables*):

| Variável | Padrão | Para quê |
|---|---|---|
| `DEEPSEEK_API_KEY` | (obrigatória com o provedor `deepseek`) | chave da API da DeepSeek |
| `CHAT_PROVEDOR` | `deepseek` | qualquer provedor embutido do Pi (`deepseek`, `opencode-go`, ...) |
| `CHAT_MODELO` | `deepseek-flash` | modelo do catálogo desse provedor |

Outros provedores usam a variável de chave própria (por exemplo `OPENCODE_API_KEY`). Exemplo com
o OpenCode Go: `CHAT_PROVEDOR=opencode-go`, `CHAT_MODELO=deepseek-v4.1-flash` e `OPENCODE_API_KEY=...`.
Provedor ou modelo que não existe dá erro claro.

Para rodar no seu computador:

```bash
mise install                   # Node e pnpm nas versões do projeto
pnpm install
pnpm test                      # testes (Vitest), não chamam o modelo
pnpm typecheck
echo 'DEEPSEEK_API_KEY=sua-chave' > .env.local   # .env* está no .gitignore
vercel dev                     # site e /api/chat em http://localhost:3000
```

Para perguntar ao mesmo agente pelo terminal, sem a Vercel (a resposta sai aos poucos no terminal):

```bash
pnpm chat "quais vereadores mais faltaram?"
```

O comando lê `.env` e `.env.local` (ambos fora do git). Exemplo com o OpenCode Go, em `.env.local`:

```
OPENCODE_API_KEY=sua-chave
CHAT_PROVEDOR=opencode-go
CHAT_MODELO=deepseek-v4.1-flash
```

Sem a chave do provedor, ele avisa em português e sai com erro. O código fica em `cli/`, que não vai
para a Vercel.

A lista de perguntas para conferir o chat antes de publicar está em
[`tests/perguntas.md`](tests/perguntas.md).

## Estrutura

```
public/                 o que vai para o ar
  index.html            a página
  data.json             Uberlândia, gerado por scripts/gerar_dados.py
  federal.json          Câmara dos Deputados, gerado por scripts/gerar_federal.py
  mg.json               Minas Gerais, gerado por scripts/gerar_mg.py
  fotos/                fotos oficiais do TSE (vereadores, prefeito, vice)
  fotos/dep/            fotos oficiais da Câmara dos Deputados
  fotos/mg/             fotos do TSE (deputados estaduais e governo de MG)
scripts/
  comum.py              configuração (município, legislatura) e funções comuns
  coletar_camara.py     vereadores e reuniões da Câmara (todo dia)
  coletar_tesouro.py    contas anuais da Prefeitura e população (todo dia, só baixa anos novos)
  coletar_tse.py        candidatos, bens, campanha e fotos (só após eleições)
  gerar_dados.py        junta tudo em public/data.json, com checagem de segurança
  coletar_federal.py    deputados, presença oficial, votações, projetos e cota (Câmara dos Deputados)
  coletar_tse_federal.py  votos em 2022 (total e em Uberlândia) e patrimônio dos deputados
  gerar_federal.py      gera public/federal.json, com checagem de segurança
  coletar_mg.py         ALMG (deputados, projetos, reuniões, verba) e contas do Estado
  coletar_tse_mg.py     fotos, votos (MG e Uberlândia) e patrimônio de deputados estaduais e governador
  gerar_mg.py           gera public/mg.json (inclui quem governa hoje, em GOVERNO_ATUAL)
api/
  chat.ts               Vercel Function do chat (POST /api/chat)
lib/                    agente, consultas e leitura dos JSONs (usados por api/chat.ts)
cli/                    `pnpm chat`: o agente no terminal (não vai para a Vercel)
tests/                  testes (Vitest) e perguntas.md, a lista de conferência do chat
dados/                  dados brutos e cache (não vão para o site)
atualizar.sh            comando principal
ver.sh                  servidor local para testar
vercel.json             configuração da Vercel (pasta public, cache, função do chat)
```

## Fontes e metodologia

| Dado | Fonte |
|---|---|
| Vereadores, reuniões, votações, proposições | API do site da Câmara Municipal (`camarauberlandia.mg.gov.br/++api++`) |
| Fotos, idade, patrimônio, campanha, votos | TSE, arquivos públicos em `cdn.tse.jus.br` |
| Receitas e despesas | Tesouro Nacional, SICONFI (Declaração de Contas Anuais) |
| População | IBGE, estimativas anuais |
| Deputados federais, votações, projetos, cota | Dados Abertos da Câmara dos Deputados (`dadosabertos.camara.leg.br`) |
| Presença oficial dos deputados | Página de cada deputado em `camara.leg.br` |
| Votos dos deputados em Uberlândia, patrimônio | TSE, eleição de 2022 (ligado ao deputado pelo CPF, que é consultado na hora e não fica salvo no repositório) |
| Deputados estaduais, projetos, reuniões, verba indenizatória | Dados Abertos da ALMG (`dadosabertos.almg.gov.br`) |
| Contas do Estado | Tesouro Nacional, SICONFI (DCA de Minas Gerais) |

- **Presença**: a lista de frequência oficial da Câmara não está sendo atualizada (vereadores que
  votaram aparecem com "falta"), por isso a presença é medida pelas votações nominais: o vereador
  conta como presente na reunião em que registrou pelo menos um voto ou presidiu a mesa.
  Reuniões sem votação nominal ficam fora da conta.
- **Votou contra a maioria**: votou sim quando a maioria votou não, ou o contrário.
- **Vetos e pareceres**: nessas votações "sim" e "não" se referem ao veto ou ao parecer, não ao projeto.
- **Presença dos deputados federais**: é a contagem oficial da Câmara (presenças, ausências
  justificadas e não justificadas). A % conta ausência justificada como ausência.
- **Principais votações federais**: votações do texto de PL, PLP, PEC, MP e PDL no plenário com
  mais de 300 votos, sem requerimentos e destaques.
- **Deputados estaduais**: a ALMG não publica presença nem voto individual em dados abertos, por
  isso essas métricas não existem para MG. Mostramos quantas reuniões de Plenário marcadas
  aconteceram, segundo a própria ALMG.
- **Governador atual**: não vem de API; está em `GOVERNO_ATUAL` no `scripts/gerar_mg.py`.
  Atualize quando mudar (por exemplo, em 1º de janeiro de 2027).
- **Campanha**: mostramos a origem do dinheiro (fundo eleitoral, pessoas físicas etc.), sem
  nomes de doadores.

## Quando algo mudar

- **Nova legislatura (2029)**: altere `LEGISLATURA_INICIO` em `scripts/comum.py` e rode
  `./atualizar.sh --tse` depois de ajustar `TSE_ANO_ELEICAO`.
- **Nova legislatura federal (2027)**: altere `LEGISLATURA` e `INICIO` em
  `scripts/coletar_federal.py` e `scripts/gerar_federal.py`, e `ANO` em `coletar_tse_federal.py`.
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
- **Dados** (`dados/`, `public/data.json`, `public/mg.json`, `public/federal.json`): dados
  públicos da Câmara Municipal de Uberlândia, da ALMG, da Câmara dos Deputados, do TSE, do
  Tesouro Nacional (SICONFI) e do IBGE. Pertencem a essas fontes e não estão sob a licença MIT; ao reutilizar, cite a fonte original.
- **Fotos** (`public/fotos/`): fotos oficiais do TSE e da Câmara dos Deputados; também não
  estão sob a licença MIT.
