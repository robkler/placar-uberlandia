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
  const itens = base
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
    fonte: ente === "prefeitura" ? "Tesouro Nacional (Siconfi)" : "Tesouro Nacional (Siconfi), Estado de Minas Gerais",
  };
}

export function governoMG(d: Dados): object {
  const g = d.mg.governo;
  const { foto: _f, ...atual } = g.atual;
  const proj: any[] = g.projetos?.lista ?? [];
  return {
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
