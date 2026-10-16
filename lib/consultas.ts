import type { Casa, Dados } from "./dados.js";
import { normalizar } from "./texto.js";

export interface Pessoa {
  casa: Casa;
  id: string;
  nome: string;
  partido: string;
  uf?: string;
  /** Link do placar: #v/<id>, #e/<id> ou #d/<id>. */
  link: string;
  /** Link oficial da casa legislativa. */
  fonte: string;
}

const LIMITE = 10;

function todas(d: Dados, casa?: Casa): { p: Pessoa; nomes: string[] }[] {
  const out: { p: Pessoa; nomes: string[] }[] = [];
  if (!casa || casa === "vereador") {
    for (const v of d.udi?.vereadores ?? []) {
      const id = String(v.id);
      out.push({
        p: {
          casa: "vereador", id, nome: v.nome, partido: v.partido, link: `#v/${id}`,
          fonte: `https://www.camarauberlandia.mg.gov.br/vereadores/vereadores/${id}`,
        },
        nomes: [v.nome, v.nomeCompleto],
      });
    }
  }
  if (!casa || casa === "estadual") {
    for (const e of d.mg?.deputados ?? []) {
      const id = String(e.id);
      out.push({
        p: {
          casa: "estadual", id, nome: e.nome, partido: e.partido, link: `#e/${id}`,
          fonte: `https://www.almg.gov.br/a-assembleia/deputados/deputado/?id=${id}`,
        },
        nomes: [e.nome, e.nomeCompleto],
      });
    }
  }
  if (!casa || casa === "federal") {
    for (const f of d.fed?.deputados ?? []) {
      const id = String(f.id);
      out.push({
        p: {
          casa: "federal", id, nome: f.nome, partido: f.partido, uf: f.uf, link: `#d/${id}`,
          fonte: `https://www.camara.leg.br/deputados/${id}`,
        },
        nomes: [f.nome, f.nomeCivil],
      });
    }
  }
  return out;
}

/**
 * Busca por nome, nome completo/civil e partes do nome (sem acento, sem caixa).
 * Todos os termos da consulta precisam aparecer. Nome exato vem primeiro,
 * depois nome que começa com a consulta, depois os demais. Até 10 resultados.
 */
export function buscarParlamentar(d: Dados, consulta: string, casa?: Casa): Pessoa[] {
  const q = normalizar(consulta);
  if (!q) return [];
  const termos = q.split(" ");
  const achados: { p: Pessoa; rank: number }[] = [];
  for (const { p, nomes } of todas(d, casa)) {
    const ns = nomes.filter(Boolean).map(normalizar);
    const palavras = new Set(ns.flatMap(n => n.split(" ")));
    const contem = termos.every(t => ns.some(n => n.includes(t)));
    if (!contem) continue;
    const nome = ns[0] ?? "";
    let rank = 3;
    if (ns.includes(q)) rank = 0;
    else if (nome.startsWith(q)) rank = 1;
    else if (termos.every(t => palavras.has(t))) rank = 2;
    achados.push({ p, rank });
  }
  return achados
    .sort((a, b) => a.rank - b.rank) // sort estável: mantém a ordem dos dados
    .slice(0, LIMITE)
    .map(a => a.p);
}

// ---------------------------------------------------------------------------
// Perfil, votações, ranking, contas e governo
// ---------------------------------------------------------------------------

const AVISO_ESTADUAL = "A ALMG não publica presença nem voto individual de deputados estaduais em dados abertos.";
const VOTO_FEDERAL: Record<string, string> = {
  S: "Sim", N: "Não", A: "Abstenção", O: "Obstrução", P: "Art. 17", "-": "Não votou",
};
const NOME_CASA: Record<Casa, string> = { vereador: "vereador", estadual: "deputado estadual", federal: "deputado federal" };

const um = (n: number) => Math.round(n * 10) / 10;
const pctDe = (parte: number, total: number) => (total ? um((parte / total) * 100) : null);
const inteiro = (x: number | null) => (x == null ? "—" : `${Math.round(x)}%`);
const topo = (pares: [string, number][] | undefined, n = 5) =>
  (pares ?? []).slice(0, n).map(([categoria, valor]) => ({ categoria, valor }));

/** Registro bruto do JSON + a Pessoa já montada (mesmos links de buscarParlamentar). */
function achar(d: Dados, casa: Casa, id: string): { p: Pessoa; raw: any } {
  const alvo = String(id);
  const fonte: any[] =
    casa === "vereador" ? d.udi?.vereadores : casa === "estadual" ? d.mg?.deputados : d.fed?.deputados;
  const raw = (fonte ?? []).find(x => String(x.id) === alvo);
  const p = raw && todas(d, casa).find(t => t.p.id === alvo)?.p;
  if (!raw || !p) throw new Error(`${NOME_CASA[casa]} com id ${alvo} não encontrado.`);
  return { p, raw };
}

/** Presença no plenário do federal: presenças ÷ (presenças + justificadas + não justificadas), como o site. */
function presencaFederal(plen: number[]) {
  const total = plen[0] + plen[1] + plen[2];
  return {
    presentes: plen[0], ausenciasJustificadas: plen[1], ausenciasNaoJustificadas: plen[2],
    total, pct: pctDe(plen[0], total),
  };
}

const FONTE_MATERIA = "https://e-processos.camarauberlandia.mg.gov.br/consultas/materia/materia_mostrar_proc?cod_materia=";

/** Projetos de lei votados do vereador: contagens e até 5 itens mais recentes (sem a lista inteira). */
function resumoProjetos(pj: any, ressalva: string | undefined) {
  const { lista, ...contagens } = pj ?? { votados: 0, aprovados: 0, rejeitados: 0, emTramitacao: 0, vetados: 0, lista: [] };
  const recentes = [...((lista ?? []) as any[])]
    .sort((a, b) => b.data.localeCompare(a.data))
    .slice(0, 5)
    .map(x => ({
      materia: x.materia, status: x.status, data: x.data,
      ...(x.materiaId ? { fonte: `${FONTE_MATERIA}${encodeURIComponent(x.materiaId)}` } : {}),
    }));
  return { ...contagens, recentes, ressalva, link: "#vot" };
}

export function perfil(d: Dados, casa: Casa, id: string): object {
  const { p, raw: r } = achar(d, casa, id);
  if (casa === "vereador") {
    const t = r.tse ?? {};
    return {
      ...p,
      nomeCompleto: r.nomeCompleto, natureza: r.natureza, noMandatoDesde: r.inicio,
      presenca: {
        presentes: r.sessoesPres, total: r.sessoes, pct: pctDe(r.sessoesPres, r.sessoes),
        pctSite: r.sessoes ? inteiro((r.sessoesPres / r.sessoes) * 100) : "—",
      },
      votacoesNominais: {
        total: r.nVot, sim: r.sim, nao: r.nao, abstencoes: r.abst, ausencias: r.aus, contraMaioria: r.contraMaioria,
      },
      proposicoes: { total: r.propsTotal, porTipo: r.props, relatorias: r.relatorias },
      projetos: resumoProjetos(r.projetos, d.udi?.camaraProjetos?.ressalva),
      comissoes: (r.comissoes ?? []).map((c: any) => `${c.nome} (${c.cargo})`),
      eleicao2024: { votos: r.votosEleicao, situacao: t.situacao },
      patrimonio2024: t.patrimonio ?? null,
    };
  }
  if (casa === "estadual") {
    const t = r.tse ?? {};
    return {
      ...p,
      nomeCompleto: r.nomeCompleto, noMandatoDesde: r.inicio, mandatos: r.mandatos,
      aviso: AVISO_ESTADUAL,
      proposicoes: { total: r.props?.total, principais: r.props?.principal, viraramLei: r.props?.leis },
      verbaIndenizatoria: {
        total: r.verba, meses: r.verbaMeses,
        mediaMensal: r.verbaMeses ? Math.round(r.verba / r.verbaMeses) : null,
        principaisCategorias: topo(r.verbaCat),
      },
      eleicao2022: { votos: t.votos, votosEmUberlandia: t.votosLocal },
      patrimonio2022: t.patrimonio ?? null,
    };
  }
  const t = r.tse ?? {};
  return {
    ...p,
    nomeCivil: r.nomeCivil, noMandatoDesde: r.inicio, condicao: r.condicao,
    presenca: {
      plenario: presencaFederal(r.plen),
      comissoes: presencaFederal(r.com),
    },
    votacoesNominais: {
      total: r.votacoes, votou: r.votou,
      votouComOGoverno: { alinhados: r.govAl, comOrientacao: r.govN, pct: pctDe(r.govAl, r.govN) },
    },
    proposicoes: { total: r.props?.total, principais: r.props?.principal, viraramLei: r.props?.leis },
    cotaParlamentar: { total: r.ceap, principaisCategorias: topo(r.ceapCat) },
    eleicao2022: { votos: t.votos2022, votosEmUberlandia: t.votosLocal ?? null },
    patrimonio2022: t.patrimonio ?? null,
  };
}

const cortar = (s: string | undefined, n = 200) => {
  const t = (s ?? "").trim();
  return t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t;
};

/** Mais recentes primeiro; em empate de data, a que vem depois no arquivo vem antes. */
const recentesPrimeiro = <T extends { data: string }>(xs: T[]) =>
  [...xs].reverse().sort((a, b) => b.data.localeCompare(a.data));

export function votacoesDe(d: Dados, casa: Casa, id: string, limite = 10): object {
  if (casa === "estadual") throw new Error(AVISO_ESTADUAL);
  const { p } = achar(d, casa, id);
  const n = Math.max(1, Math.floor(limite));
  if (casa === "vereador") {
    const lista = recentesPrimeiro<any>(d.udi.votacoes).slice(0, n).map(v => ({
      data: v.data, materia: v.materia, ementa: cortar(v.ementa), resultado: v.resultado,
      voto: v.votos?.[p.id] ?? "Sem registro", referencia: { maioria: v.maioria },
    }));
    return { pessoa: p, votacoes: lista };
  }
  const i = (d.fed.ordem as string[]).indexOf(p.id);
  const lista = recentesPrimeiro<any>(d.fed.votacoes).slice(0, n).map(v => ({
    data: v.data, materia: v.prop, ementa: cortar(v.ementa), resultado: v.res,
    voto: VOTO_FEDERAL[v.v?.[i]] ?? "Não votou", referencia: { governo: v.gov || "Sem orientação" },
  }));
  return { pessoa: p, votacoes: lista };
}

export function ranking(
  d: Dados,
  casa: "vereador" | "federal",
  metrica: "presenca" | "faltas",
  opcoes: { uf?: string; limite?: number } = {},
): object {
  const limite = Math.max(1, Math.floor(opcoes.limite ?? 10));
  const uf = opcoes.uf?.toUpperCase();
  const base = (casa === "vereador" ? d.udi.vereadores : d.fed.deputados) as any[];
  const totalDe = (r: any): number => casa === "vereador" ? r.sessoes : r.plen[0] + r.plen[1] + r.plen[2];
  const maiorTotal = Math.max(0, ...base.map(totalDe));
  const todos = base
    .filter(r => casa === "vereador" || !uf || r.uf === uf)
    .map(r => {
      const presentes = casa === "vereador" ? r.sessoesPres : r.plen[0];
      const total = casa === "vereador" ? r.sessoes : r.plen[0] + r.plen[1] + r.plen[2];
      return { r, presentes, total };
    })
    .filter(x => x.total > 0)
    .map(({ r, presentes, total }) => {
      const { p } = achar(d, casa, r.id);
      const presencaPct = pctDe(presentes, total)!;
      return {
        nome: p.nome, partido: p.partido, ...(p.uf ? { uf: p.uf } : {}),
        presencaPct, faltasPct: um(100 - presencaPct), presentes, faltas: total - presentes, total,
        ...(casa === "federal" ? { faltasNaoJustificadas: r.plen[2] } : {}),
        link: p.link, fonte: p.fonte,
      };
    });
  // Amostra pequena (menos da metade do maior total da casa) não entra no ranking.
  const minimo = maiorTotal / 2;
  const itens = todos.filter(x => x.total >= minimo);
  const poucasTodas = todos.filter(x => x.total < minimo).sort((a, b) => b.total - a.total)
    .map(x => ({ nome: x.nome, total: x.total, link: x.link, fonte: x.fonte }));
  const poucasSessoes = poucasTodas.slice(0, 10);
  itens.sort((a, b) =>
    metrica === "presenca"
      ? b.presencaPct - a.presencaPct || b.total - a.total
      : b.faltasPct - a.faltasPct || b.faltas - a.faltas);
  return {
    casa, metrica, uf: uf ?? null, totalConsiderado: itens.length,
    criterio: casa === "vereador"
      ? "presença = reuniões com presença ÷ reuniões com votação"
      : "presença no plenário = presenças ÷ (presenças + ausências justificadas + não justificadas); faltas incluem as justificadas",
    itens: itens.slice(0, limite),
    poucasSessoes,
    ...(poucasTodas.length
      ? { totalPoucasSessoes: poucasTodas.length, notaPoucasSessoes: "Estas pessoas têm menos da metade do maior número de sessões da casa (ex.: suplentes); por isso ficam fora do ranking, pois a porcentagem delas não é comparável." }
      : {}),
  };
}

// ---------------------------------------------------------------------------
// Motor de rankings por métrica (pessoa ou partido)
// ---------------------------------------------------------------------------

type Unidade = "pct" | "reais" | "votos" | "qtd";
interface Metrica {
  tipo: "taxa" | "valor";
  descricao: string;
  unidade?: Unidade;
  /** Corte fixo: denominador menor que isto fica fora do ranking (em vez da metade da mediana). */
  denMinimo?: number;
}
type Extrator = (r: any) => number | { num: number; den: number } | null | undefined;

const nulo = (x: unknown): x is null | undefined => x == null || (typeof x === "number" && Number.isNaN(x));
const soma = (...xs: unknown[]) => (xs.some(nulo) ? null : (xs as number[]).reduce((a, b) => a + b, 0));
const taxa = (num: number | null | undefined, den: number | null | undefined) =>
  nulo(num) || nulo(den) ? null : { num, den };
const comp = (r: any) => (r.com?.length ? r.com : null) as number[] | null;
const plenFed = (r: any) => (r.plen as number[] | undefined) ?? null;
const propsValor = (r: any, k: string) => r.props?.[k];

const def = (
  tipo: "taxa" | "valor", unidade: Unidade, descricao: string, ext: Extrator, denMinimo?: number,
): [Metrica, Extrator] => [{ tipo, unidade, descricao, ...(denMinimo ? { denMinimo } : {}) }, ext];

const CATALOGO: Record<Casa, Record<string, [Metrica, Extrator]>> = {
  vereador: {
    presenca: def("taxa", "pct", "Presença: reuniões com presença ÷ reuniões com votação.", r => taxa(r.sessoesPres, r.sessoes)),
    faltas: def("taxa", "pct", "Faltas: (reuniões − presenças) ÷ reuniões com votação.",
      r => (nulo(r.sessoes) || nulo(r.sessoesPres) ? null : taxa(r.sessoes - r.sessoesPres, r.sessoes))),
    contra_maioria: def("taxa", "pct", "Votos contra a maioria da casa ÷ votações em que votou.", r => taxa(r.contraMaioria, r.votou)),
    proposicoes: def("valor", "qtd", "Total de proposições apresentadas.", r => r.propsTotal),
    projetos_de_lei: def("valor", "qtd",
      "Projetos de lei ordinária + projetos de lei complementar + propostas de emenda à Lei Orgânica.",
      r => soma(
        propsValor(r, "Projeto de Lei Ordinária") ?? 0,
        propsValor(r, "Projeto de Lei Complementar") ?? 0,
        propsValor(r, "Proposta de Emenda à Lei Orgânica") ?? 0,
      )),
    relatorias: def("valor", "qtd", "Relatorias (pareceres como relator).", r => r.relatorias),
    projetos_votados: def("valor", "qtd",
      "Projetos de lei de autoria do vereador que tiveram votação nominal em plenário (cada projeto conta uma vez). Só votações nominais.",
      r => r.projetos?.votados),
    projetos_aprovados: def("valor", "qtd",
      "Projetos de lei de autoria do vereador que terminaram aprovados (não inclui os vetados, que contam à parte). Só votações nominais.",
      r => r.projetos?.aprovados),
    taxa_aprovacao_projetos: def("taxa", "pct",
      "Taxa de aprovação: projetos aprovados ÷ projetos votados do vereador. Quem não teve projeto votado fica em semDado; quem teve menos de 3 projetos votados fica fora do ranking e vem em poucosProjetos (a taxa com 1 ou 2 projetos não é comparável). Os itens trazem num/den.",
      r => taxa(r.projetos?.aprovados, r.projetos?.votados), 3),
    votos_eleicao: def("valor", "votos", "Votos recebidos na eleição de 2024.", r => r.tse?.votos2024 ?? r.votosEleicao),
    patrimonio: def("valor", "reais", "Patrimônio declarado ao TSE (2024).", r => r.tse?.patrimonio),
    gasto_campanha: def("valor", "reais", "Gasto de campanha declarado ao TSE (2024).", r => r.tse?.campanha),
  },
  federal: {
    presenca: def("taxa", "pct", "Presença no plenário: presenças ÷ (presenças + ausências justificadas + não justificadas).",
      r => { const p = plenFed(r); return p && taxa(p[0], p[0] + p[1] + p[2]); }),
    faltas: def("taxa", "pct", "Faltas no plenário (incluem as justificadas) ÷ total de sessões.",
      r => { const p = plenFed(r); return p && taxa(p[1] + p[2], p[0] + p[1] + p[2]); }),
    presenca_comissoes: def("taxa", "pct", "Presença nas comissões: presenças ÷ (presenças + ausências justificadas + não justificadas).",
      r => { const c = comp(r); return c && taxa(c[0], c[0] + c[1] + c[2]); }),
    alinhamento_governo: def("taxa", "pct", "Votos alinhados à orientação do governo ÷ votações com orientação.", r => taxa(r.govAl, r.govN)),
    participacao_votacoes: def("taxa", "pct", "Votações nominais em que votou ÷ votações nominais da casa.", r => taxa(r.votou, r.votacoes)),
    proposicoes: def("valor", "qtd", "Total de proposições apresentadas.", r => r.props?.total),
    proposicoes_principais: def("valor", "qtd", "Proposições principais (de autoria).", r => r.props?.principal),
    leis_aprovadas: def("valor", "qtd", "Proposições que viraram lei.", r => r.props?.leis),
    cota_parlamentar: def("valor", "reais", "Gasto com a cota parlamentar (CEAP) no mandato.", r => r.ceap),
    votos_eleicao: def("valor", "votos", "Votos recebidos na eleição de 2022.", r => r.tse?.votos2022),
    votos_uberlandia: def("valor", "votos", "Votos recebidos em Uberlândia na eleição de 2022.", r => r.tse?.votosLocal),
    patrimonio: def("valor", "reais", "Patrimônio declarado ao TSE (2022).", r => r.tse?.patrimonio),
  },
  estadual: {
    proposicoes: def("valor", "qtd", "Total de proposições apresentadas.", r => r.props?.total),
    proposicoes_principais: def("valor", "qtd", "Proposições principais (de autoria).", r => r.props?.principal),
    leis_aprovadas: def("valor", "qtd", "Proposições que viraram lei.", r => r.props?.leis),
    verba_indenizatoria: def("valor", "reais", "Verba indenizatória total no mandato.", r => r.verba),
    mandatos: def("valor", "qtd", "Número de mandatos.", r => r.mandatos),
    votos_eleicao: def("valor", "votos", "Votos recebidos na eleição de 2022.", r => r.tse?.votos),
    votos_uberlandia: def("valor", "votos", "Votos recebidos em Uberlândia na eleição de 2022.", r => r.tse?.votosLocal),
    patrimonio: def("valor", "reais", "Patrimônio declarado ao TSE (2022).", r => r.tse?.patrimonio),
  },
};

export const METRICAS: Record<Casa, Record<string, Metrica>> = Object.fromEntries(
  Object.entries(CATALOGO).map(([casa, ms]) => [casa, Object.fromEntries(Object.entries(ms).map(([id, [m]]) => [id, m]))]),
) as Record<Casa, Record<string, Metrica>>;

export function metricasDisponiveis(casa?: Casa): object {
  const casas = casa ? [casa] : (Object.keys(METRICAS) as Casa[]);
  return Object.fromEntries(casas.map(c => [
    c, Object.entries(METRICAS[c]).map(([id, m]) => ({ id, tipo: m.tipo, unidade: m.unidade, descricao: m.descricao })),
  ]));
}

const duas = (n: number) => Math.round(n * 100) / 100;

export function rankingMetrica(
  d: Dados,
  casa: Casa,
  metrica: string,
  opcoes: { agrupar?: "pessoa" | "partido"; ordem?: "maior" | "menor"; ordenarPor?: "total" | "media"; uf?: string; limite?: number } = {},
): object {
  const entrada = CATALOGO[casa]?.[metrica];
  if (!entrada) {
    throw new Error(
      `Métrica "${metrica}" inválida para ${NOME_CASA[casa]}. Métricas válidas: ${Object.keys(CATALOGO[casa] ?? {}).join(", ")}.`,
    );
  }
  const [def_, ext] = entrada;
  const agrupar = opcoes.agrupar ?? "pessoa";
  const ordem = opcoes.ordem ?? "maior";
  const limite = Math.max(1, Math.floor(opcoes.limite ?? LIMITE));
  const uf = casa === "federal" ? opcoes.uf?.toUpperCase() : undefined;
  const base: any[] = (casa === "vereador" ? d.udi?.vereadores : casa === "estadual" ? d.mg?.deputados : d.fed?.deputados) ?? [];

  const extrair = (r: any) => {
    const v = ext(r);
    if (nulo(v)) return null;
    if (typeof v === "number") return { valor: v };
    return v.den > 0 ? { num: v.num, den: v.den, valor: um((v.num / v.den) * 100) } : null;
  };
  const ehTaxa = def_.tipo === "taxa";
  // Amostra pequena: menos da metade da mediana dos denominadores da casa (antes do filtro de UF).
  // Métrica com denMinimo (projetos) usa corte fixo; den = 0 já vira semDado em extrair().
  const dens = ehTaxa && !def_.denMinimo ? base.map(r => (extrair(r) as any)?.den ?? 0).filter(n => n > 0).sort((x, y) => x - y) : [];
  const mediana = dens.length ? (dens[(dens.length - 1) >> 1] + dens[dens.length >> 1]) / 2 : 0;
  const minimo = def_.denMinimo ?? mediana / 2;

  type Linha = { p: Pessoa; num?: number; den?: number; valor: number };
  const consideradas: Linha[] = [];
  const poucas: { nome: string; total: number; link: string; fonte: string }[] = [];
  let semDado = 0;
  for (const r of base) {
    if (uf && r.uf !== uf) continue;
    const x = extrair(r);
    if (!x) { semDado++; continue; }
    const { p } = achar(d, casa, r.id);
    if (ehTaxa && (x as any).den < minimo) {
      poucas.push({ nome: p.nome, total: (x as any).den, link: p.link, fonte: p.fonte });
      continue;
    }
    consideradas.push({ p, ...(x as any) });
  }
  const sinal = ordem === "maior" ? -1 : 1;
  poucas.sort((x, y) => y.total - x.total);
  const fixo = def_.denMinimo != null;
  const extras = {
    ...(poucas.length && fixo ? {
      poucosProjetos: poucas.slice(0, 10),
      totalPoucosProjetos: poucas.length,
      notaPoucosProjetos: `${poucas.length} ${poucas.length === 1 ? "vereador com" : "vereadores com"} menos de ${def_.denMinimo} projetos votados ficaram fora${agrupar === "partido" ? " do ranking e da soma dos partidos" : ""}: a taxa com 1 ou 2 projetos não é comparável.${poucas.length > 10 ? " Mostrando 10." : ""}`,
    } : {}),
    ...(poucas.length && !fixo ? {
      poucasSessoes: poucas.slice(0, 10),
      notaPoucasSessoes: `${poucas.length} ${poucas.length === 1 ? "parlamentar com" : "parlamentares com"} menos da metade da mediana de sessões/votações da casa (ex.: suplentes) ficaram fora do ranking${agrupar === "partido" ? " e da soma dos partidos" : ""}, pois a taxa deles não é comparável${poucas.length > 10 ? "; mostrando 10" : ""}.`,
      totalPoucasSessoes: poucas.length,
    } : {}),
    ...(semDado ? { semDado } : {}),
  };
  const cabecalho = { casa, metrica, descricao: def_.descricao, agrupar, ordem, ...(uf ? { uf } : {}) };

  if (agrupar === "pessoa") {
    const itens = consideradas
      .sort((a, b) => sinal * (a.valor - b.valor) || (b.den ?? 0) - (a.den ?? 0) || a.p.nome.localeCompare(b.p.nome))
      .slice(0, limite)
      .map(l => ({
        nome: l.p.nome, partido: l.p.partido, ...(l.p.uf ? { uf: l.p.uf } : {}),
        valor: l.valor, ...(ehTaxa ? { num: l.num, den: l.den } : {}), link: l.p.link, fonte: l.p.fonte,
      }));
    return { ...cabecalho, itens, ...extras };
  }

  const grupos = new Map<string, Linha[]>();
  for (const l of consideradas) grupos.set(l.p.partido, [...(grupos.get(l.p.partido) ?? []), l]);
  const itens = [...grupos.entries()].map(([partido, ls]) => {
    const n = ls.length;
    const aviso = n <= 2 ? { aviso: "poucos parlamentares" } : {};
    if (ehTaxa) {
      const num = ls.reduce((a, l) => a + l.num!, 0);
      const den = ls.reduce((a, l) => a + l.den!, 0);
      const valor = um((num / den) * 100);
      return { partido, parlamentares: n, valor, num, den, ...aviso };
    }
    const total = ls.reduce((a, l) => a + l.valor, 0);
    return { partido, parlamentares: n, valor: duas(total), media: duas(total / n), ...aviso };
  }).sort((a, b) =>
    sinal * ((ehTaxa || opcoes.ordenarPor !== "media" ? a.valor - b.valor : (a as any).media - (b as any).media)) || ((b as any).den ?? 0) - ((a as any).den ?? 0) || a.partido.localeCompare(b.partido));
  return { ...cabecalho, itens: itens.slice(0, limite), ...extras };
}

// ---------------------------------------------------------------------------
// Votações: busca e como cada partido votou
// ---------------------------------------------------------------------------

/** Nome de proposição em forma canônica: "Projeto de Lei Complementar nº 1/2025" e "PLP 1/2025" viram "plp 1/2025". */
function canonicaProposicao(s: string): string {
  return normalizar(s)
    .replace(/projeto de lei complementar/g, "plp")
    .replace(/projeto de lei ordinaria/g, "pl")
    .replace(/projeto de lei/g, "pl")
    .replace(/projeto de decreto legislativo/g, "pdl")
    .replace(/proposta de emenda a lei organica/g, "pelo")
    .replace(/proposta de emenda a constituicao/g, "pec")
    .replace(/\b(n|no|numero)[°º.]?\s+(?=\d)/g, "")
    .replace(/[°º]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
const escaparRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Mesmos destinos que o site usa: aba de votações e ficha oficial da matéria. */
function linkVotacao(casa: "vereador" | "federal", v: any): { link: string; fonte?: string } {
  if (casa === "vereador") {
    return {
      link: "#vot",
      ...(v.materiaId ? { fonte: `https://e-processos.camarauberlandia.mg.gov.br/consultas/materia/materia_mostrar_proc?cod_materia=${encodeURIComponent(v.materiaId)}` } : {}),
    };
  }
  return {
    link: "#fvot",
    ...(v.pid ? { fonte: `https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=${encodeURIComponent(v.pid)}` } : {}),
  };
}

export function buscarVotacoes(d: Dados, casa: "vereador" | "federal", consulta: string, limite = 5): object {
  if ((casa as Casa) === "estadual") throw new Error(AVISO_ESTADUAL);
  const lista: any[] = (casa === "vereador" ? d.udi?.votacoes : d.fed?.votacoes) ?? [];
  const nomeDe = (v: any): string => (casa === "vereador" ? v.materia : v.prop) ?? "";
  const q = canonicaProposicao(consulta);
  const porNome = q ? new RegExp(`(^| )${escaparRegex(q)}($|[ /(])`) : null;
  const palavras = normalizar(consulta).split(" ").filter(Boolean);
  let achadas = lista.filter(v => porNome?.test(canonicaProposicao(nomeDe(v))));
  if (!achadas.length && palavras.length && !/^[a-z]+ \d/.test(q)) { // nome de proposição não achado não vira busca por palavras
    achadas = lista.filter(v => {
      const texto = normalizar(`${nomeDe(v)} ${v.ementa ?? ""}`);
      return palavras.every(w => texto.includes(w));
    });
  }
  const n = Math.max(1, Math.floor(limite));
  return recentesPrimeiro(achadas).slice(0, n).map(v => ({
    id: String(v.id), data: v.data, materia: nomeDe(v), ementa: cortar(v.ementa),
    resultado: casa === "vereador" ? v.resultado : v.res,
    ...(casa === "vereador" && v.turno ? { turno: v.turno } : {}),
    ...linkVotacao(casa, v),
  }));
}

export function votacaoPorPartido(d: Dados, casa: "vereador" | "federal", id: string): object {
  if ((casa as Casa) === "estadual") throw new Error(AVISO_ESTADUAL);
  const alvo = String(id);
  const v = ((casa === "vereador" ? d.udi?.votacoes : d.fed?.votacoes) ?? []).find((x: any) => String(x.id) === alvo);
  if (!v) throw new Error(`Votação com id ${alvo} não encontrada.`);
  type Conta = { partido: string; sim: number; nao: number; outros: number; total: number; [k: string]: string | number };
  const ausente = casa === "vereador" ? "ausentes" : "semVotoRegistrado";
  const por = new Map<string, Conta>();
  const contar = (partido: string, tipo: "sim" | "nao" | "outros" | "ausente") => {
    const chave = tipo === "ausente" ? ausente : tipo;
    const c = por.get(partido) ?? { partido, sim: 0, nao: 0, outros: 0, [ausente]: 0, total: 0 };
    (c[chave] as number)++; c.total++;
    por.set(partido, c);
  };
  if (casa === "vereador") {
    const partidoDe = new Map<string, string>();
    for (const [k, n] of Object.entries<any>(d.udi.nomes ?? {})) partidoDe.set(k, n.partido);
    for (const r of d.udi.vereadores ?? []) partidoDe.set(String(r.id), r.partido);
    for (const [vid, voto] of Object.entries<string>(v.votos ?? {})) {
      contar(partidoDe.get(vid) ?? "Sem partido",
        voto === "Sim" ? "sim" : voto === "Não" ? "nao" : voto === "Ausente" ? "ausente" : "outros");
    }
  } else {
    const partidoDe = new Map<string, string>((d.fed.deputados as any[]).map(r => [String(r.id), r.partido]));
    (d.fed.ordem as string[]).forEach((did, i) => {
      const c = v.v?.[i];
      contar(partidoDe.get(String(did)) ?? "Sem partido",
        c === "S" ? "sim" : c === "N" ? "nao" : c === "-" ? "ausente" : "outros");
    });
  }
  const partidos = [...por.values()].sort((a, b) => b.total - a.total || a.partido.localeCompare(b.partido));
  const soma = (k: "sim" | "nao" | "outros") => partidos.reduce((t, p) => t + p[k], 0);
  const cabeca = {
    data: v.data, materia: casa === "vereador" ? v.materia : v.prop, ementa: cortar(v.ementa),
    resultado: casa === "vereador" ? v.resultado : v.res,
    ...linkVotacao(casa, v),
    referencia: casa === "vereador" ? { maioria: v.maioria } : { governo: v.gov || "Sem orientação" },
    notaPartido: casa === "federal"
      ? "Partido atual de cada deputado (federal.json), não necessariamente o da data da votação."
      : "Partido atual de cada vereador (o último registrado), não necessariamente o da data da votação.",
  };
  if (casa === "federal") {
    const oficiais = { sim: v.sim as number, nao: v.nao as number, outros: v.outros as number };
    if (soma("sim") + soma("nao") + soma("outros") === 0 && oficiais.sim + oficiais.nao + oficiais.outros > 0) {
      return { ...cabeca, totaisOficiais: oficiais, nota: "A Câmara não publicou o voto individual desta votação." };
    }
    return {
      ...cabeca,
      totaisOficiais: oficiais,
      votosNaoAtribuidos: { sim: oficiais.sim - soma("sim"), nao: oficiais.nao - soma("nao"), outros: oficiais.outros - soma("outros") },
      notaTotais: "Os partidos contam só os deputados atuais, pelo partido atual: votos de quem já saiu da Câmara não aparecem (ficam em votosNaoAtribuidos, a diferença para o total oficial). 'semVotoRegistrado' inclui ausentes e quem ainda não tinha mandato na data. Abstenção, obstrução e Art. 17 estão em outros.",
      resumo: { partidos: partidos.length, partidosComUmParlamentar: partidos.filter(p => p.total === 1).length },
      partidos,
    };
  }
  return {
    ...cabeca,
    resumo: { partidos: partidos.length, partidosComUmParlamentar: partidos.filter(p => p.total === 1).length },
    partidos,
  };
}

export function contas(d: Dados, ente: "prefeitura" | "estado", ano?: number): object {
  const fin: any[] = (ente === "prefeitura" ? d.udi.prefeitura?.fin : d.mg.governo?.fin) ?? [];
  const anos = fin.map(f => f.ano as number).sort((a, b) => a - b);
  const alvo = ano ?? anos[anos.length - 1];
  const f = fin.find(x => x.ano === alvo);
  if (!f) throw new Error(`Ano ${alvo} não encontrado nas contas de ${ente}. Anos disponíveis: ${anos.join(", ")}.`);
  const { ano: _a, receita, receitaBruta, despesa, funcoes, ...outras } = f;
  const pop = ente === "prefeitura" ? d.udi.prefeitura?.pop : d.mg.governo?.pop;
  return {
    ente, ano: f.ano, anosDisponiveis: anos,
    populacao: pop?.[String(f.ano)] ?? null,
    receitas: { total: receita, bruta: receitaBruta, detalhe: outras },
    despesas: {
      total: despesa,
      porFuncao: Object.entries((funcoes ?? {}) as Record<string, number>)
        .sort((a, b) => b[1] - a[1]).slice(0, 8).map(([funcao, valor]) => ({ funcao, valor })),
    },
    origem: ente === "prefeitura" ? "Tesouro Nacional (Siconfi)" : "Tesouro Nacional (Siconfi), Estado de Minas Gerais",
    link: ente === "prefeitura" ? "#pref" : "#gov",
    fonte: "https://siconfi.tesouro.gov.br",
  };
}

/** Resumo dos projetos de lei votados pela Câmara de Uberlândia, no total ou em um ano (ano da última votação do projeto). */
export function projetosCamara(d: Dados, ano?: number): object {
  const c = d.udi?.camaraProjetos;
  if (!c) throw new Error("O placar não tem dados de projetos votados.");
  const anos = Object.keys(c.porAno ?? {}).map(Number).sort((a, b) => a - b);
  const alvo = ano == null ? c.total : c.porAno?.[String(ano)];
  if (!alvo) {
    throw new Error(`Ano ${ano} sem dados de projetos votados. Anos disponíveis: ${anos.join(", ")}.`);
  }
  return {
    escopo: ano == null ? "total" : "ano",
    ...(ano == null ? {} : { ano }),
    anosDisponiveis: anos,
    ...alvo,
    nota: "Cada projeto conta uma vez, pelo resultado da última votação. aprovados não inclui vetados (vetados contam à parte); emTramitacao são projetos que seguem (aprovados só em 1ª discussão ou com parecer contrário rejeitado). Ano = ano da última votação do projeto. Autores: prefeitura, vereadores (inclui ex-vereadores) e comissoes.",
    ressalva: c.ressalva,
    link: "#vot",
    fonte: "https://www.camarauberlandia.mg.gov.br/vereadores",
  };
}

export function governoMG(d: Dados): object {
  const g = d.mg.governo;
  const { foto: _f, ...atual } = g.atual;
  const proj: any[] = g.projetos?.lista ?? [];
  return {
    link: "#gov",
    fonte: "https://dadosabertos.tse.jus.br",
    atual,
    eleito2022: { nome: g.eleito2022?.nome, partido: g.eleito2022?.partido },
    resultado2022: (g.eleicao ?? []).map((c: any) => ({
      nome: c.nome, partido: c.partido, votos: c.votos, votosEmUberlandia: c.votosLocal, situacao: c.situacao,
    })),
    projetosNaAssembleia: {
      total: g.projetos?.total, viraramLei: g.projetos?.leis,
      recentes: recentesPrimeiro(proj).slice(0, 10).map(x => ({
        projeto: x.p, ementa: cortar(x.e), data: x.data, viroLei: x.lei,
      })),
    },
  };
}
