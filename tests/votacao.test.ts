import { beforeAll, expect, test } from "vitest";
import { carregarDados, type Dados } from "../lib/dados.js";
import { buscarVotacoes, votacaoPorPartido } from "../lib/consultas.js";

let d: Dados;
beforeAll(async () => { d = await carregarDados(); });

test("buscarVotacoes federal acha PLP 186 de 2026-10-14", () => {
  const r: any[] = buscarVotacoes(d, "federal", "PLP 186") as any;
  expect(r[0]).toMatchObject({ data: "2026-10-14", materia: "PLP 186/2026", resultado: "Aprovado" });
  expect(r[0].ementa.length).toBeLessThanOrEqual(200);
  expect(r.every(x => x.id)).toBe(true);
});
test("buscarVotacoes não confunde 186 com 1860 e acha por ementa sem acento", () => {
  expect((buscarVotacoes(d, "federal", "PLP 1860") as any[]).length).toBe(0);
  expect((buscarVotacoes(d, "federal", "PL 4133/2023") as any[])[0].materia).toContain("4133/2023");
  const e: any[] = buscarVotacoes(d, "vereador", "ESTRUTURA ORGANICA administracao") as any;
  expect(e.length).toBeGreaterThan(0);
});
test("buscarVotacoes vereador por nome longo e abreviado", () => {
  const a: any[] = buscarVotacoes(d, "vereador", "Projeto de Lei Complementar nº 1/2025") as any;
  const b: any[] = buscarVotacoes(d, "vereador", "PLP 1/2025") as any;
  expect(a.length).toBeGreaterThan(0);
  expect(b.map(x => x.id)).toEqual(a.map(x => x.id));
  expect(a.every(x => /Complementar nº 1\/2025/.test(x.materia))).toBe(true);
});
test("votacaoPorPartido federal: soma bate e PL tem total da ordem", () => {
  const id = (buscarVotacoes(d, "federal", "PLP 186") as any[])[0].id;
  const r: any = votacaoPorPartido(d, "federal", id);
  expect(r.referencia).toEqual({ governo: "Sim" });
  // 460 votos S individuais; o total oficial (461) inclui o voto do Art. 17 (presidente), que vai em "outros".
  expect(r.totaisOficiais).toEqual({ sim: 461, nao: 4, outros: 1 });
  expect(r.partidos.reduce((s: number, p: any) => s + p.sim, 0)).toBe(460);
  expect(r.partidos.reduce((s: number, p: any) => s + p.nao, 0)).toBe(4);
  expect(r.partidos.reduce((s: number, p: any) => s + p.outros, 0)).toBe(1);
  expect(r.partidos.reduce((s: number, p: any) => s + p.total, 0)).toBe(d.fed.ordem.length);
  const pl = d.fed.deputados.filter((x: any) => x.partido === "PL" && d.fed.ordem.includes(x.id)).length;
  expect(r.partidos.find((p: any) => p.partido === "PL").total).toBe(pl);
  expect(r.notaPartido).toMatch(/[Pp]artido atual/);
});
test("votacaoPorPartido vereador: soma consistente com votos", () => {
  const v = d.udi.votacoes[0];
  const r: any = votacaoPorPartido(d, "vereador", v.id);
  const tot = (k: string) => r.partidos.reduce((s: number, p: any) => s + p[k], 0);
  expect(tot("total")).toBe(Object.keys(v.votos).length);
  expect(tot("sim")).toBe(Object.values(v.votos).filter(x => x === "Sim").length);
  expect(tot("nao")).toBe(Object.values(v.votos).filter(x => x === "Não").length);
  expect(tot("ausentes")).toBe(Object.values(v.votos).filter(x => x === "Ausente").length);
  expect(r.referencia).toEqual({ maioria: v.maioria });
});
test("votacaoPorPartido: estadual e id inexistente lançam", () => {
  expect(() => votacaoPorPartido(d, "estadual" as any, "1")).toThrow(/ALMG não publica/);
  expect(() => buscarVotacoes(d, "estadual" as any, "x")).toThrow(/ALMG não publica/);
  expect(() => votacaoPorPartido(d, "federal", "nada")).toThrow(/não encontrada/);
});
test("PLP 18 acha só PLP 18/2021, não 186", () => {
  const r: any[] = buscarVotacoes(d, "federal", "PLP 18") as any;
  expect(r.every(x => x.materia.startsWith("PLP 18/"))).toBe(true);
});

test("votações trazem link e fonte oficial", () => {
  const f: any = (buscarVotacoes(d, "federal", "PLP 186") as any[])[0];
  expect(f.link).toBe("#fvot");
  expect(f.fonte).toMatch(/^https:\/\/www\.camara\.leg\.br\/proposicoesWeb\/fichadetramitacao\?idProposicao=\d+$/);
  const pf: any = votacaoPorPartido(d, "federal", f.id);
  expect([pf.link, pf.fonte]).toEqual([f.link, f.fonte]);
  const v: any = (buscarVotacoes(d, "vereador", "PLP 1/2025") as any[])[0];
  expect(v.link).toBe("#vot");
  expect(v.fonte).toMatch(/materia_mostrar_proc\?cod_materia=\d+$/);
  expect((votacaoPorPartido(d, "vereador", v.id) as any).fonte).toBe(v.fonte);
});
