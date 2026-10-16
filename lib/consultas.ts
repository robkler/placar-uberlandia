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
