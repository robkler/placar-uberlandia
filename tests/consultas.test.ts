import { beforeAll, expect, test } from "vitest";
import { carregarDados, type Dados } from "../lib/dados.js";
import { contas, governoMG, perfil, ranking, votacoesDe } from "../lib/consultas.js";

let dados: Dados;
beforeAll(async () => {
  dados = await carregarDados();
});

test("presença do vereador bate com o site", () => {
  // Abatenio Marquez: 135 de 164 reuniões = 82,317% (index.html:363, v.sessoesPres / v.sessoes);
  // o card do site (index.html:396) mostra "82%".
  const r: any = perfil(dados, "vereador", "546914");
  expect(r.presenca).toMatchObject({ presentes: 135, total: 164, pct: 82.3, pctSite: "82%" });
  expect(r.link).toBe("#v/546914");
});
test("presença do federal usa presenças ÷ soma de plen", () => {
  // AJ Albuquerque: plen [338, 35, 22] → 338 / 395 = 85,57% (index.html:559)
  const r: any = perfil(dados, "federal", "204549");
  expect(r.presenca.plenario).toMatchObject({ presentes: 338, total: 395, pct: 85.6 });
});
test("votações do vereador trazem a maioria como referência", () => {
  const r: any = votacoesDe(dados, "vereador", "546914", 4);
  expect(r.votacoes).toHaveLength(4);
  expect(r.votacoes[0].referencia).toHaveProperty("maioria");
  expect(r.votacoes[0].data >= r.votacoes[3].data).toBe(true);
  expect(r.votacoes[0].ementa.length).toBeLessThanOrEqual(200);
});
test("votações do federal decodificam o voto", () => {
  const r: any = votacoesDe(dados, "federal", "204549", 3);
  expect(r.votacoes).toHaveLength(3);
  expect(["Sim", "Não", "Abstenção", "Obstrução", "Art. 17", "Não votou"]).toContain(r.votacoes[0].voto);
  expect(r.votacoes[0].referencia).toHaveProperty("governo");
});
test("voto do federal é o caractere da posição do deputado em ordem", () => {
  const f = dados.fed;
  const i = f.ordem.indexOf("204549");
  const mais = [...f.votacoes].sort((a: any, b: any) => b.data.localeCompare(a.data))[0];
  const esperado: Record<string, string> = { S: "Sim", N: "Não", A: "Abstenção", O: "Obstrução", P: "Art. 17", "-": "Não votou" };
  const r: any = votacoesDe(dados, "federal", "204549", 1);
  expect(r.votacoes[0].voto).toBe(esperado[mais.v[i]]);
});
test("estadual não tem votações e explica o motivo", () => {
  expect(() => votacoesDe(dados, "estadual", "12193")).toThrow(/ALMG não publica/);
  expect((perfil(dados, "estadual", "12193") as any).aviso).toMatch(/ALMG não publica/);
  expect((perfil(dados, "estadual", "12193") as any).presenca).toBeUndefined();
});
test("ranking de faltas dos federais de MG", () => {
  const r: any = ranking(dados, "federal", "faltas", { uf: "MG", limite: 5 });
  expect(r.itens).toHaveLength(5);
  expect(r.itens.every((p: any) => p.uf === "MG")).toBe(true);
  expect(r.itens[0].faltasPct).toBeGreaterThanOrEqual(r.itens[4].faltasPct);
});
test("ranking de presença dos vereadores, padrão 10 itens, do maior ao menor", () => {
  const r: any = ranking(dados, "vereador", "presenca");
  expect(r.itens).toHaveLength(10);
  expect(r.itens[0].presencaPct).toBeGreaterThanOrEqual(r.itens[9].presencaPct);
  expect(r.itens[0]).toHaveProperty("link");
});
test("id inexistente lança erro", () => {
  expect(() => perfil(dados, "federal", "1")).toThrow(/não encontrado/);
  expect(() => votacoesDe(dados, "vereador", "1")).toThrow(/não encontrado/);
});
test("contas do Estado em 2022", () => expect((contas(dados, "estado", 2022) as any).ano).toBe(2022));
test("contas da prefeitura sem ano usam o mais recente", () => {
  const r: any = contas(dados, "prefeitura");
  expect(r.ano).toBe(Math.max(...dados.udi.prefeitura.fin.map((f: any) => f.ano)));
  expect(r.despesas.total).toBeGreaterThan(0);
  expect(() => contas(dados, "prefeitura", 1999)).toThrow(/não encontrado/);
});
test("governador atual", () => {
  const r: any = governoMG(dados);
  expect(r.atual.nome).toBe("Mateus Simões");
  expect(r.projetosNaAssembleia.total).toBeGreaterThan(0);
  // a lista do JSON traz só os projetos mais recentes (hoje 8 de 104)
  expect(r.projetosNaAssembleia.recentes.length).toBe(Math.min(10, dados.mg.governo.projetos.lista.length));
  expect(r.eleito2022.nome).toBe("ZEMA");
});
