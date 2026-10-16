import { beforeAll, expect, test } from "vitest";
import { carregarDados, type Dados } from "../lib/dados.js";
import { METRICAS, metricasDisponiveis, ranking, rankingMetrica } from "../lib/consultas.js";

let dados: Dados;
beforeAll(async () => {
  dados = await carregarDados();
});

test("partido/faltas/vereador: PODEMOS, PL, AVANTE com aviso", () => {
  const r: any = rankingMetrica(dados, "vereador", "faltas", { agrupar: "partido" });
  const [a, b, c] = r.itens;
  expect(a).toMatchObject({ partido: "PODEMOS", valor: 24.1, num: 79, den: 328, parlamentares: 2 });
  expect(b).toMatchObject({ partido: "PL", valor: 18.5, num: 91, den: 492, parlamentares: 3 });
  expect(c).toMatchObject({ partido: "AVANTE", valor: 17.7, num: 29, den: 164, parlamentares: 1, aviso: "poucos parlamentares" });
  expect(r.poucasSessoes.length).toBeGreaterThan(0);
});
test("pessoa/faltas/vereador tem paridade com ranking()", () => {
  const r: any = rankingMetrica(dados, "vereador", "faltas");
  const velho: any = ranking(dados, "vereador", "faltas");
  expect(r.itens[0].nome).toMatch(/Tannús/);
  expect(r.itens[0].valor).toBe(35.4);
  expect(r.itens.map((i: any) => i.nome)).toEqual(velho.itens.map((i: any) => i.nome));
});
test("federal/presenca MG: Gilmar Machado em poucasSessoes", () => {
  const r: any = rankingMetrica(dados, "federal", "presenca", { uf: "MG", limite: 100 });
  expect(r.poucasSessoes.map((x: any) => x.nome)).toContain("Gilmar Machado");
  expect(r.itens.map((x: any) => x.nome)).not.toContain("Gilmar Machado");
});
test("federal/alinhamento_governo por partido bate com conta independente", () => {
  const r: any = rankingMetrica(dados, "federal", "alinhamento_governo", { agrupar: "partido", limite: 100 });
  const item = r.itens.find((i: any) => i.partido === "PT") ?? r.itens[0];
  const dep = (dados.fed.deputados as any[]).filter(x => x.partido === item.partido);
  const ns = (dados.fed.deputados as any[]).map(x => x.govN).filter(n => n > 0).sort((a, b) => a - b);
  const mediana = (ns[(ns.length - 1) >> 1] + ns[ns.length >> 1]) / 2;
  const ok = dep.filter(x => x.govN > 0 && x.govN >= mediana / 2);
  expect(item.num).toBe(ok.reduce((s, x) => s + x.govAl, 0));
  expect(item.den).toBe(ok.reduce((s, x) => s + x.govN, 0));
  expect(item.parlamentares).toBe(ok.length);
});
test("estadual/verba_indenizatoria: maior e menor", () => {
  const verbas = (dados.mg.deputados as any[]).map(x => x.verba).filter((v: any) => v != null);
  const alto: any = rankingMetrica(dados, "estadual", "verba_indenizatoria");
  const baixo: any = rankingMetrica(dados, "estadual", "verba_indenizatoria", { ordem: "menor" });
  expect(alto.itens[0].valor).toBe(Math.max(...verbas));
  expect(baixo.itens[0].valor).toBe(Math.min(...verbas));
});
test("métrica inválida lista as válidas", () => {
  expect(() => rankingMetrica(dados, "estadual", "presenca")).toThrow(/verba_indenizatoria/);
});
test("semDado conta quem não tem votosLocal", () => {
  const r: any = rankingMetrica(dados, "federal", "votos_uberlandia", { limite: 1000 });
  const sem = (dados.fed.deputados as any[]).filter(x => x.tse?.votosLocal == null).length;
  expect(r.semDado ?? 0).toBe(sem);
  expect(r.itens.length + (r.semDado ?? 0)).toBe(dados.fed.deputados.length);
});
test("catálogo expõe métricas", () => {
  expect(Object.keys(METRICAS.vereador)).toContain("projetos_de_lei");
  expect(metricasDisponiveis("estadual")).toHaveProperty("estadual");
});
test("presenca_comissoes usa mediana: ranking cheio e poucas exclusões", () => {
  const r: any = rankingMetrica(dados, "federal", "presenca_comissoes", { limite: 10 });
  expect(r.itens).toHaveLength(10);
  expect(r.totalPoucasSessoes ?? 0).toBeLessThan(100);
});
test("poucasSessoes limitado a 10, com contagem total na nota", () => {
  const r: any = rankingMetrica(dados, "federal", "presenca");
  expect(r.poucasSessoes.length).toBeLessThanOrEqual(10);
  const n = r.totalPoucasSessoes;
  expect(r.notaPoucasSessoes).toContain(String(n));
  const t = r.poucasSessoes.map((x: any) => x.total);
  expect(t).toEqual([...t].sort((a: number, b: number) => b - a));
});
