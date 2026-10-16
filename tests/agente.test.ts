import { beforeAll, expect, test } from "vitest";
import { carregarDados, type Dados } from "../lib/dados.js";
import { PROMPT_SISTEMA, criarAgente, criarFerramentas, escolherModelo, validarPedido } from "../lib/agente.js";

let d: Dados;
beforeAll(async () => { d = await carregarDados(); });

const ferramenta = (nome: string) => criarFerramentas(d).find(t => t.name === nome)!;

test("criarFerramentas devolve os onze nomes", () => {
  expect(criarFerramentas(d).map(t => t.name).sort()).toEqual(
    ["buscar_parlamentar", "buscar_votacao", "contas", "governo_mg", "metricas", "perfil", "projetos_camara", "projetos_do_vereador", "ranking", "votacao_por_partido", "votacoes"]);
});

test("buscar_parlamentar devolve texto JSON com o link do placar", async () => {
  const r = await ferramenta("buscar_parlamentar").execute("1", { consulta: "liza prado" });
  expect(r.content[0]).toMatchObject({ type: "text" });
  expect((r.content[0] as { text: string }).text).toContain("#v/399022");
});

test("votacoes de estadual rejeita", async () => {
  const p = ferramenta("votacoes").execute("1", { casa: "estadual", id: "1" });
  await expect(p).rejects.toThrow(/ALMG não publica/);
});

test("prompt proíbe recomendar voto", () => {
  expect(PROMPT_SISTEMA).toContain("não recomende em quem votar");
});

test("criarAgente converte o histórico em mensagens do pi", () => {
  const a = criarAgente(d, [
    { papel: "usuario", texto: "oi" }, { papel: "assistente", texto: "olá" },
  ]);
  const m = a.state.messages;
  expect(m.map(x => x.role).filter(r => r !== "system")).toEqual(["user", "assistant"]);
  expect(a.state.thinkingLevel).toBe("off");
});

test("prompt: links só das ferramentas, português sempre, link por pessoa", () => {
  expect(PROMPT_SISTEMA).toContain("Use apenas links que as ferramentas devolveram; nunca escreva outro endereço.");
  expect(PROMPT_SISTEMA).toContain("Responda sempre em português do Brasil, mesmo em frases curtas.");
  expect(PROMPT_SISTEMA).toContain("na linha de cada pessoa");
});

test("governo_mg e contas devolvem link do placar e fonte oficial", async () => {
  const g = JSON.parse((await ferramenta("governo_mg").execute("1", {})).content[0]!.type === "text"
    ? ((await ferramenta("governo_mg").execute("1", {})).content[0] as { text: string }).text : "{}");
  expect(g).toMatchObject({ link: "#gov", fonte: "https://dadosabertos.tse.jus.br" });
  const c = JSON.parse(((await ferramenta("contas").execute("1", { ente: "prefeitura" })).content[0] as { text: string }).text);
  expect(c).toMatchObject({ link: "#pref", fonte: "https://siconfi.tesouro.gov.br" });
});

test("prompt: sem tabelas e sem anunciar consultas", () => {
  expect(PROMPT_SISTEMA).toContain("Não use tabelas nem títulos; use listas com '- '.");
  expect(PROMPT_SISTEMA).toContain("Não anuncie as consultas que vai fazer; responda direto.");
});

test("escolherModelo resolve opencode-go/deepseek-v4.1-flash e o padrão deepseek", () => {
  expect(escolherModelo("opencode-go", "deepseek-v4.1-flash").model.id).toBe("deepseek-v4.1-flash");
  expect(escolherModelo("deepseek", "deepseek-flash").model.provider).toBe("deepseek");
});

test("escolherModelo: provedor ou modelo desconhecido dá erro claro", () => {
  expect(() => escolherModelo("nao-existe", "x")).toThrow(/Provedor de chat não encontrado: nao-existe/);
  expect(() => escolherModelo("deepseek", "nao-existe")).toThrow(/Modelo de chat não encontrado: deepseek\/nao-existe/);
});

test("validarPedido limita o total do histórico a 4000 caracteres", () => {
  const msg = (papel: "usuario" | "assistente", n: number) => ({ papel, texto: "a".repeat(n) });
  const ok = [msg("assistente", 2000), msg("usuario", 500), msg("assistente", 1500)];
  ok.push(msg("usuario", 1));
  expect(() => validarPedido({ mensagens: ok })).toThrow(/4000 caracteres no total/);
  expect(validarPedido({ mensagens: [msg("assistente", 2000), msg("assistente", 1500), msg("usuario", 500)] }).mensagens).toHaveLength(3);
});

test("ranking aceita métrica do catálogo, por partido, nas três casas e mantém a chamada antiga", async () => {
  const txt = async (n: string, p: any) => JSON.parse(((await ferramenta(n).execute("1", p)).content[0] as any).text);
  const r: any = await txt("ranking", { casa: "vereador", metrica: "faltas", agrupar: "partido" });
  expect(r.itens[0].partido).toBe("PODEMOS");
  const e: any = JSON.parse(((await ferramenta("ranking").execute("1", { casa: "estadual", metrica: "verba_indenizatoria" })).content[0] as any).text);
  expect(e.itens.length).toBeGreaterThan(0);
  const velho: any = JSON.parse(((await ferramenta("ranking").execute("1", { casa: "federal", metrica: "faltas", uf: "MG" })).content[0] as any).text);
  expect(velho.itens[0].nome).toMatch(/Hercílio/);
});

test("metricas, buscar_votacao e votacao_por_partido respondem JSON", async () => {
  const txt = async (n: string, p: any) => JSON.parse(((await ferramenta(n).execute("1", p)).content[0] as any).text);
  expect((await txt("metricas", { casa: "estadual" })).estadual.map((m: any) => m.id)).toContain("verba_indenizatoria");
  const v = await txt("buscar_votacao", { casa: "federal", consulta: "PLP 186" });
  const pp = await txt("votacao_por_partido", { casa: "federal", id: v[0].id });
  expect(pp.partidos.length).toBeGreaterThan(5);
  await expect(ferramenta("votacao_por_partido").execute("1", { casa: "estadual", id: "1" })).rejects.toThrow(/ALMG não publica/);
});

test("prompt: avisa quando nada serve e pede contagem em rankings por partido", () => {
  expect(PROMPT_SISTEMA).toContain("Quando nenhuma ferramenta trouxer o que foi pedido, diga que o placar ainda não calcula isso.");
  expect(PROMPT_SISTEMA).toContain("Em rankings por partido, diga quantos parlamentares cada partido tem e avise quando forem poucos.");
});

test("prompt: sem link devolvido, sem link escrito", () => {
  expect(PROMPT_SISTEMA).toContain("Se a ferramenta não devolver link, não escreva link nenhum.");
});

test("prompt: o agente não faz contas", () => {
  expect(PROMPT_SISTEMA).toContain("Não faça contas: não some, não tire média, não conte itens nem calcule diferenças com os números das ferramentas; use só os totais que elas devolverem. Se o número pronto não vier, diga que o placar ainda não calcula isso.");
});

test("projetos_camara devolve o total e o ano da Câmara", async () => {
  const t = JSON.parse(((await ferramenta("projetos_camara").execute("1", {})).content[0] as { text: string }).text);
  expect(t).toMatchObject({ votados: 300, aprovados: 243, link: "#vot" });
  const a = JSON.parse(((await ferramenta("projetos_camara").execute("1", { ano: 2025 })).content[0] as { text: string }).text);
  expect(a).toMatchObject({ ano: 2025, votados: 181 });
  await expect(ferramenta("projetos_camara").execute("1", { ano: 2019 })).rejects.toThrow(/Anos disponíveis/);
});

test("prompt: deputados só têm leis aprovadas, não projetos votados", () => {
  expect(PROMPT_SISTEMA).toContain("Para deputados federais e estaduais, o placar só sabe quantos projetos viraram lei, não quantos foram votados.");
});

test("prompt: taxa de aprovação sempre em 'X de Y projetos'", () => {
  expect(PROMPT_SISTEMA).toContain("Em taxa de aprovação de projetos, sempre diga 'X de Y projetos'.");
});

test("projetos_do_vereador: por id ou nome, com filtro, ano e limite", async () => {
  const txt = async (p: any) => JSON.parse(((await ferramenta("projetos_do_vereador").execute("1", p)).content[0] as { text: string }).text);
  const r = await txt({ id: "399041", filtro: "aprovados", ano: 2025, limite: 3 });
  expect(r).toMatchObject({ filtro: "aprovados", ano: 2025, mostrando: 3 });
  expect(r.totalNoFiltro).toBe(r.totais.aprovados);
  expect(r.itens[0].fonte).toContain("cod_materia=");
  const n = await txt({ consulta: "queijinho" });
  expect(n.pessoa.id).toBe("537380");
  const t = ferramenta("projetos_do_vereador");
  expect(t.description).toContain("autoria principal");
  expect(t.description).toContain("link oficial");
  expect(t.description).not.toContain("votação simbólica");
  expect((t.parameters as any).properties.limite.maximum).toBe(25);
});

test("prompt: lista de projetos com o link oficial de cada um", () => {
  expect(PROMPT_SISTEMA).toContain("Ao listar projetos, ponha na linha de cada projeto o link oficial que a ferramenta devolveu, no formato [Fonte oficial](fonte).");
});

test("perfil: descrição sem coautoria, com aprovados ÷ propostos e aponta projetos_do_vereador", () => {
  const desc = ferramenta("perfil").description;
  expect(desc).not.toContain("coautoria");
  expect(desc).toContain("projetos_do_vereador");
  expect(desc).toContain("aprovados ÷ propostos");
  expect(desc).toContain("votações nominais (inclui projetos de antes de 2025)");
  expect(ferramenta("ranking").description).toContain("taxa_aprovacao_propostos");
  expect(ferramenta("ranking").description).not.toContain("taxa_chegou_votacao");
});
