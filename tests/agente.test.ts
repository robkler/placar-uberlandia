import { beforeAll, expect, test } from "vitest";
import { carregarDados, type Dados } from "../lib/dados.js";
import { PROMPT_SISTEMA, criarAgente, criarFerramentas } from "../lib/agente.js";

let d: Dados;
beforeAll(async () => { d = await carregarDados(); });

const ferramenta = (nome: string) => criarFerramentas(d).find(t => t.name === nome)!;

test("criarFerramentas devolve os seis nomes", () => {
  expect(criarFerramentas(d).map(t => t.name).sort()).toEqual(
    ["buscar_parlamentar", "contas", "governo_mg", "perfil", "ranking", "votacoes"]);
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
