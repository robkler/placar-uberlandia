import { beforeAll, expect, test } from "vitest";
import { carregarDados, type Dados } from "../lib/dados.js";
import { METRICAS, perfil, projetosCamara, rankingMetrica } from "../lib/consultas.js";

let d: Dados;
beforeAll(async () => { d = await carregarDados(); });

const RESSALVA = "Só entram projetos com votação nominal; aprovações em votação simbólica não aparecem.";

test("catálogo: três métricas de projetos para vereador", () => {
  expect(METRICAS.vereador.projetos_votados).toMatchObject({ tipo: "valor", unidade: "qtd" });
  expect(METRICAS.vereador.projetos_aprovados).toMatchObject({ tipo: "valor", unidade: "qtd" });
  expect(METRICAS.vereador.taxa_aprovacao_projetos).toMatchObject({ tipo: "taxa", unidade: "pct" });
});

test("perfil do vereador traz projetos com contagens e no máximo 5 recentes", () => {
  const liza: any = perfil(d, "vereador", "399022");
  expect(liza.projetos).toMatchObject({ votados: 20, aprovados: 1, rejeitados: 13, emTramitacao: 1, vetados: 5, ressalva: RESSALVA });
  expect(liza.projetos.recentes).toHaveLength(5);
  expect(liza.projetos.recentes[0]).toMatchObject({ materia: "Projeto de Lei Ordinária nº 1323/2026", status: "vetado", data: "2026-10-14" });
  expect(liza.projetos.recentes[0].fonte).toContain("cod_materia=268336");
  expect(liza.projetos.lista).toBeUndefined();
  const carrijo: any = perfil(d, "vereador", "399041");
  expect(carrijo.projetos).toMatchObject({ votados: 5, aprovados: 4, rejeitados: 0, emTramitacao: 1, vetados: 0 });
});

test("vereador sem projeto votado: zeros e lista vazia", () => {
  const p: any = perfil(d, "vereador", "537428");
  expect(p.projetos).toMatchObject({ votados: 0, aprovados: 0, recentes: [] });
});

test("projetosCamara: total, com ressalva e link", () => {
  const r: any = projetosCamara(d);
  expect(r).toMatchObject({ escopo: "total", votados: 300, aprovados: 243, rejeitados: 25, emTramitacao: 14, vetados: 18, ressalva: RESSALVA, link: "#vot" });
  expect(r.porAutor.prefeitura).toMatchObject({ votados: 238 });
  expect(r.porAutor.vereadores).toMatchObject({ votados: 56 });
  expect(r.porAutor.comissoes).toMatchObject({ votados: 6 });
  expect(r.fonte).toBeUndefined(); // a página de pesquisa da matéria não é acessível; sem link oficial
  expect(r.nota).toContain("veto mantido, total ou parcial");
  expect(r.anosDisponiveis).toEqual([2025, 2026]);
});

test("projetosCamara por ano", () => {
  expect(projetosCamara(d, 2025)).toMatchObject({ escopo: "ano", ano: 2025, votados: 181, aprovados: 141, porAutor: { prefeitura: { votados: 140 } } });
  expect(projetosCamara(d, 2026)).toMatchObject({ ano: 2026, votados: 119 });
});

test("projetosCamara: ano sem dado lista os anos disponíveis", () => {
  expect(() => projetosCamara(d, 2019)).toThrow(/2019.*Anos disponíveis: 2025, 2026/);
});

test("ranking por partido de projetos_aprovados: PP lidera com 6", () => {
  const r: any = rankingMetrica(d, "vereador", "projetos_aprovados", { agrupar: "partido" });
  expect(r.itens[0]).toMatchObject({ partido: "PP", valor: 6, parlamentares: 6 });
  expect(r.itens[1]).toMatchObject({ partido: "PODEMOS", valor: 2, parlamentares: 2, aviso: "poucos parlamentares" });
});

test("ranking por pessoa de projetos_aprovados: Antônio Carrijo (4) primeiro", () => {
  const r: any = rankingMetrica(d, "vereador", "projetos_aprovados");
  expect(r.itens[0]).toMatchObject({ nome: expect.stringMatching(/Carrijo/), valor: 4 });
});

test("taxa_aprovacao_projetos: menos de 3 votados fora do ranking, em poucosProjetos; num/den nos itens", () => {
  const r: any = rankingMetrica(d, "vereador", "taxa_aprovacao_projetos", { limite: 30 });
  expect(r.semDado).toBe(13);
  expect(r.poucasSessoes).toBeUndefined();
  expect(r.itens[0]).toMatchObject({ valor: 80, num: 4, den: 5 });
  expect(r.itens[0].nome).toMatch(/Carrijo/);
  expect(r.itens.every((i: any) => i.den >= 3)).toBe(true);
  expect(r.totalPoucosProjetos).toBe(r.poucosProjetos.length);
  expect(r.poucosProjetos.map((x: any) => x.nome)).toContain("Zezinho Mendonça");
  expect(r.poucosProjetos.every((x: any) => x.total < 3)).toBe(true);
  expect(r.notaPoucosProjetos).toContain("menos de 3 projetos votados ficaram fora: a taxa com 1 ou 2 projetos não é comparável.");
});

test("taxa_aprovacao_projetos por partido: só quem tem 3+ votados entra na soma", () => {
  const r: any = rankingMetrica(d, "vereador", "taxa_aprovacao_projetos", { agrupar: "partido" });
  expect(r.itens[0]).toMatchObject({ partido: "PP", num: 4, den: 5, valor: 80, parlamentares: 1, aviso: "poucos parlamentares" });
  expect(r.itens).toHaveLength(5);
  expect(r.notaPoucosProjetos).toContain("do ranking e da soma dos partidos");
});
