import { beforeAll, expect, test } from "vitest";
import { carregarDados, type Dados } from "../lib/dados.js";
import { METRICAS, perfil, projetosCamara, projetosDoVereador, rankingMetrica } from "../lib/consultas.js";

let d: Dados;
beforeAll(async () => { d = await carregarDados(); });

const RESSALVA = "Só entram projetos com votação nominal; aprovações em votação simbólica não aparecem.";

test("catálogo: três métricas de projetos para vereador", () => {
  expect(METRICAS.vereador.projetos_votados).toMatchObject({ tipo: "valor", unidade: "qtd" });
  expect(METRICAS.vereador.projetos_aprovados).toMatchObject({ tipo: "valor", unidade: "qtd" });
  expect(METRICAS.vereador.taxa_aprovacao_projetos).toMatchObject({ tipo: "taxa", unidade: "pct" });
});

test("perfil do vereador: bloco de votações nominais rotulado, com contagens e no máximo 5 recentes", () => {
  const liza: any = perfil(d, "vereador", "399022");
  const vn = liza.projetos.votacoesNominais;
  expect(vn).toMatchObject({ descricao: "votações nominais (inclui projetos de antes de 2025)", votados: 20, aprovados: 1, rejeitados: 13, emTramitacao: 1, vetados: 5, ressalva: RESSALVA });
  expect(vn.recentes).toHaveLength(5);
  expect(vn.recentes[0]).toMatchObject({ materia: "Projeto de Lei Ordinária nº 1323/2026", status: "vetado", data: "2026-10-14" });
  expect(vn.recentes[0].fonte).toContain("cod_materia=268336");
  expect(vn.lista).toBeUndefined();
  const carrijo: any = perfil(d, "vereador", "399041");
  expect(carrijo.projetos.votacoesNominais).toMatchObject({ votados: 5, aprovados: 4, rejeitados: 0, emTramitacao: 1, vetados: 0 });
});

test("vereador sem projeto votado: zeros e lista vazia no bloco nominal", () => {
  const p: any = perfil(d, "vereador", "537428");
  expect(p.projetos.votacoesNominais).toMatchObject({ votados: 0, aprovados: 0, recentes: [] });
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

test("catálogo: propostos, aprovados (total) e taxa de aprovação dos propostos; sem taxa_chegou_votacao", () => {
  expect(METRICAS.vereador.projetos_propostos).toMatchObject({ tipo: "valor", unidade: "qtd" });
  expect(METRICAS.vereador.projetos_aprovados_total).toMatchObject({ tipo: "valor", unidade: "qtd" });
  expect(METRICAS.vereador.taxa_aprovacao_propostos).toMatchObject({ tipo: "taxa", unidade: "pct", denMinimo: 3, denRotulo: "projetos propostos" });
  expect(METRICAS.vereador.taxa_chegou_votacao).toBeUndefined();
  for (const id of ["projetos_propostos", "projetos_aprovados_total", "taxa_aprovacao_propostos"]) {
    expect(METRICAS.vereador[id]!.descricao).toContain("autoria principal");
    expect(METRICAS.vereador[id]!.descricao).not.toContain("coautoria");
  }
});

const somaConfere = (r: any) =>
  r.aprovados + r.rejeitados + r.vetoMantido + r.emTramitacaoPlenario + r.naoChegaramAoPlenario === r.propostos
  && r.aprovadosNominal + r.aprovadosSemVotoNominal === r.aprovados
  && r.aprovadosNominal <= r.propostosVotacaoNominal
  && r.chegaramAoPlenario === r.propostos - r.naoChegaramAoPlenario
  && r.chegaramAoPlenario === r.aprovados + r.rejeitados + r.vetoMantido + r.emTramitacaoPlenario
  && r.pctChegaramAoPlenario === (r.propostos ? Math.round((1000 * r.chegaramAoPlenario) / r.propostos) / 10 : null);

test("perfil: propostos aninhados, com explicação, somas consistentes e % = aprovados ÷ propostos", () => {
  for (const v of d.udi.vereadores) {
    const pr: any = (perfil(d, "vereador", v.id) as any).projetos.propostos;
    if (!pr) continue;
    expect(somaConfere(pr)).toBe(true);
    expect(pr.pctAprovados).toBe(pr.propostos ? Math.round((1000 * pr.aprovados) / pr.propostos) / 10 : null);
    expect(pr.explicacao).toContain("autoria principal");
    expect(pr.explicacao).toContain("aprovados sem votação nominal também chegaram ao plenário");
    expect(pr.ressalva).toBeUndefined();
    expect(JSON.stringify(pr)).not.toContain("votação simbólica");
  }
  const c: any = perfil(d, "vereador", "399041");
  expect(c.projetos.propostos.propostos).toBeGreaterThanOrEqual(26); // 26 apresentados em 2025 (fixo)
  expect(c.projetos.notaAutoria).toBeUndefined();
  expect(c.projetos.ressalva).toBeUndefined();
  expect(Object.keys(c.projetos).sort()).toEqual(["propostos", "votacoesNominais"]);
  expect(JSON.stringify(c.projetos.propostos)).not.toContain(RESSALVA);
  expect(c.projetos.votacoesNominais.ressalva).toBe(RESSALVA);
  // Carrijo: 49 propostos, 20 não chegaram -> 29 chegaram ao plenário (cache de 16/10/2026; invariante acima vale sempre)
  expect(c.projetos.propostos.chegaramAoPlenario).toBe(c.projetos.propostos.propostos - c.projetos.propostos.naoChegaramAoPlenario);
});

test("perfil e lista concordam: resumo do data.json = contagem do projetos.json", () => {
  for (const v of d.udi.vereadores) {
    const pr = v.projetos.propostos;
    const lista: any[] | undefined = d.proj.vereadores[v.id];
    if (!pr) { expect(lista).toBeUndefined(); continue; }
    expect(lista!.length).toBe(pr.propostos);
    expect(lista!.filter(x => x.status === "aprovado").length).toBe(pr.aprovados);
    expect(lista!.filter(x => !x.votado && x.status === "aprovado").length).toBe(pr.aprovadosSemVotoNominal);
    expect(lista!.filter(x => x.status === "nao_votado").length).toBe(pr.naoChegaramAoPlenario);
    expect(lista!.filter(x => x.votado).length).toBe(pr.propostosVotacaoNominal);
    expect(lista!.filter(x => x.status !== "nao_votado").length).toBe(pr.chegaramAoPlenario);
  }
});

test("catálogo: taxa_chegou_plenario = chegaram ao plenário ÷ propostos, mínimo 3; num/den = perfil", () => {
  expect(METRICAS.vereador.taxa_chegou_plenario).toMatchObject({ tipo: "taxa", unidade: "pct", denMinimo: 3, denRotulo: "projetos propostos" });
  expect(METRICAS.vereador.taxa_chegou_plenario!.descricao).toContain("sem votação nominal");
  const r: any = rankingMetrica(d, "vereador", "taxa_chegou_plenario", { limite: 30 });
  for (const i of r.itens) {
    const v = d.udi.vereadores.find((x: any) => x.nome === i.nome);
    expect([i.num, i.den]).toEqual([v.projetos.propostos.chegaramAoPlenario, v.projetos.propostos.propostos]);
    expect(i.den).toBeGreaterThanOrEqual(3);
  }
});

test("ranking projetos_propostos e projetos_aprovados_total: ordem decrescente, valor = perfil", () => {
  for (const m of ["projetos_propostos", "projetos_aprovados_total"]) {
    const r: any = rankingMetrica(d, "vereador", m, { limite: 30 });
    const vals = r.itens.map((i: any) => i.valor);
    expect(vals).toEqual([...vals].sort((a: number, b: number) => b - a));
    const campo = m === "projetos_propostos" ? "propostos" : "aprovados";
    const primeiro: any = perfil(d, "vereador", r.itens[0].id ?? d.udi.vereadores.find((v: any) => v.nome === r.itens[0].nome).id);
    expect(primeiro.projetos.propostos[campo]).toBe(r.itens[0].valor);
  }
});

test("taxa_aprovacao_propostos: num/den = aprovados/propostos, den ≥ 3, sem lista em semDado", () => {
  const r: any = rankingMetrica(d, "vereador", "taxa_aprovacao_propostos", { limite: 30 });
  expect(r.itens.every((i: any) => i.den >= 3)).toBe(true);
  for (const i of r.itens) {
    const v = d.udi.vereadores.find((x: any) => x.nome === i.nome);
    expect([i.num, i.den]).toEqual([v.projetos.propostos.aprovados, v.projetos.propostos.propostos]);
  }
  const vals = r.itens.map((i: any) => i.valor);
  expect(vals).toEqual([...vals].sort((a: number, b: number) => b - a));
  expect(r.semDado).toBeGreaterThanOrEqual(1); // Dr. Maciel Amorim: nenhum projeto de autoria principal
});

test("projetosDoVereador: Carrijo tem 21 PL de autoria principal apresentados em 2025 (26 com PLC e PELO)", () => {
  const r: any = projetosDoVereador(d, { id: "399041", ano: 2025, limite: 25 });
  expect(r.totais.propostos).toBe(26);
  expect(r.totalNoFiltro).toBe(26);
  expect(r.itens).toHaveLength(25); // limite máximo 25
  const todos: any[] = d.proj.vereadores["399041"].filter((x: any) => x.identificacao.endsWith("/2025"));
  expect(todos.filter(x => x.identificacao.startsWith("Projeto de Lei Ordinária")).length).toBe(21);
  expect(somaConfere(r.totais)).toBe(true);
});

test("projetosDoVereador: todos, mais recentes primeiro, link oficial, totais iguais ao perfil", () => {
  const r: any = projetosDoVereador(d, { id: "399041" });
  expect(r.pessoa).toMatchObject({ id: "399041", nome: "Antônio Carrijo", link: "#v/399041" });
  expect(r).toMatchObject({ filtro: "todos", mostrando: 10 });
  const { explicacao: _e, ...resumo } = (perfil(d, "vereador", "399041") as any).projetos.propostos;
  expect(r.totais).toEqual(resumo);
  expect(r.totalNoFiltro).toBe(r.totais.propostos);
  expect(r.itens).toHaveLength(10);
  for (let i = 1; i < r.itens.length; i++) expect(r.itens[i - 1].data >= r.itens[i].data).toBe(true);
  for (const x of r.itens) {
    expect(x.fonte).toMatch(/^https:\/\/e-processos\.camarauberlandia\.mg\.gov\.br\/consultas\/materia\/materia_mostrar_proc\?cod_materia=\d+$/);
    expect(x.ementa.length).toBeLessThanOrEqual(200);
  }
  expect(r.explicacao).toBeTruthy();
});

test("projetosDoVereador: filtros são subconjuntos coerentes com os totais", () => {
  const t: any = projetosDoVereador(d, { id: "399041", limite: 25 });
  const v: any = projetosDoVereador(d, { id: "399041", filtro: "votados", limite: 25 });
  expect(v.totalNoFiltro).toBe(t.totais.chegaramAoPlenario);
  expect(v.itens.every((x: any) => x.chegouAoPlenario && x.status !== "nao_votado")).toBe(true);
  const vn: any = projetosDoVereador(d, { id: "399041", filtro: "votacao_nominal", limite: 25 });
  expect(vn.totalNoFiltro).toBe(t.totais.propostosVotacaoNominal);
  expect(vn.itens.every((x: any) => x.votacaoNominal && x.chegouAoPlenario)).toBe(true);
  expect(vn.itens.map((x: any) => x.identificacao)).toContain("Proposta de Emenda à Lei Orgânica nº 7/2025");
  expect(vn.itens[0].votado).toBeUndefined();
  const a: any = projetosDoVereador(d, { id: "399041", filtro: "aprovados", limite: 25 });
  expect(a.totalNoFiltro).toBe(t.totais.aprovados);
  expect(a.itens.every((x: any) => x.status === "aprovado")).toBe(true);
  const n: any = projetosDoVereador(d, { id: "399022", filtro: "nao_chegaram", ano: 2026, limite: 25 });
  expect(n.totalNoFiltro).toBe(n.totais.naoChegaramAoPlenario);
  expect(n.totalNoFiltro).toBe(n.totais.propostos - n.totais.chegaramAoPlenario);
  expect(n.itens.every((x: any) => x.status === "nao_votado" && !x.chegouAoPlenario && x.identificacao.endsWith("/2026"))).toBe(true);
  // aprovados sem votação nominal não entram em "não chegaram"
  expect(n.itens.some((x: any) => x.status === "aprovado")).toBe(false);
  expect(t.totais.naoChegaramAoPlenario + t.totais.chegaramAoPlenario).toBe(t.totais.propostos);
});

test("projetosDoVereador: limite acima de 25 vira 25", () => {
  const r: any = projetosDoVereador(d, { id: "399022", limite: 100 });
  expect(r.mostrando).toBe(25);
});

test("projetosDoVereador: busca pelo nome; ambíguo devolve opções; sem vereador dá erro", () => {
  const r: any = projetosDoVereador(d, { consulta: "carrijo", filtro: "votados" });
  expect(r.pessoa.id).toBe("399041");
  const amb: any = projetosDoVereador(d, { consulta: "antonio" });
  expect(amb.ambiguo).toBe(true);
  expect(amb.opcoes.map((p: any) => p.id).sort()).toEqual(["399041", "537380"]);
  expect(() => projetosDoVereador(d, { consulta: "xyzxyz" })).toThrow(/Nenhum vereador/);
  expect(() => projetosDoVereador(d, { id: "1" })).toThrow(/não encontrado/);
});

test("projetosDoVereador: vereador sem projeto de autoria principal tem lista vazia (não é falta de dado)", () => {
  const r: any = projetosDoVereador(d, { id: "556185" });
  expect(r).toMatchObject({ totalNoFiltro: 0, itens: [] });
  expect(r.totais.propostos).toBe(0);
});

test("sem lista do vereador (não casou no e-processos): ferramenta avisa, perfil sem propostos, nada de 0 falso", () => {
  const semLista: Dados = {
    ...d,
    udi: { ...d.udi, vereadores: d.udi.vereadores.map((v: any) => v.id === "537433"
      ? { ...v, projetos: (({ propostos: _p, ...resto }) => resto)(v.projetos) } : v) },
    proj: { ...d.proj, vereadores: Object.fromEntries(Object.entries(d.proj.vereadores).filter(([k]) => k !== "537433")) },
  };
  expect(() => projetosDoVereador(semLista, { id: "537433" })).toThrow("O placar ainda não tem a lista de projetos deste vereador.");
  const p: any = perfil(semLista, "vereador", "537433");
  expect(p.projetos.propostos).toBeUndefined();
  expect(p.projetos.votacoesNominais).toBeDefined();
  const r: any = rankingMetrica(semLista, "vereador", "projetos_propostos", { limite: 30 });
  expect(r.itens.some((i: any) => i.nome === "Ivan Nunes")).toBe(false);
  const semArquivo: Dados = { ...d, proj: null };
  expect(() => projetosDoVereador(semArquivo, { id: "399041" })).toThrow("O placar ainda não tem a lista de projetos deste vereador.");
});

test("projetosCamara: nota diz que é só votação nominal e aponta os dados por vereador", () => {
  const r: any = projetosCamara(d);
  expect(r.nota).toContain("Só votações nominais");
  expect(r.nota).toContain("projetos_do_vereador");
});
