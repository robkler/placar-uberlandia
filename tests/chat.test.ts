import { expect, test, vi } from "vitest";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { StreamFn } from "@earendil-works/pi-agent-core";
import { validarPedido } from "../lib/agente.js";
import { responder } from "../lib/chat.js";
import { POST } from "../api/chat.js";

test.each([
  ["corpo vazio", undefined],
  ["sem mensagens", {}],
  ["mensagem longa", { mensagens: [{ papel: "usuario", texto: "a".repeat(501) }] }],
  ["histórico grande", { mensagens: Array.from({ length: 11 }, () => ({ papel: "usuario", texto: "oi" })) }],
  ["última não é do usuário", { mensagens: [{ papel: "assistente", texto: "oi" }] }],
])("rejeita %s", (_, corpo) => expect(() => validarPedido(corpo)).toThrow());

test("aceita pedido válido", () => {
  expect(validarPedido({ mensagens: [{ papel: "usuario", texto: "oi" }] }).mensagens).toHaveLength(1);
});

test("POST com JSON inválido responde 400", async () => {
  const r = await POST(new Request("http://x/api/chat", { method: "POST", body: "{" }));
  expect(r.status).toBe(400);
  expect(await r.json()).toEqual({ erro: expect.any(String) });
});

test("POST com pedido fora do limite responde 400 sem chamar o modelo", async () => {
  const corpo = JSON.stringify({ mensagens: [{ papel: "usuario", texto: "a".repeat(501) }] });
  const r = await POST(new Request("http://x/api/chat", { method: "POST", body: corpo }));
  expect(r.status).toBe(400);
});

function msg(over: Partial<AssistantMessage>): AssistantMessage {
  return {
    role: "assistant", content: [], api: "openai-completions", provider: "deepseek", model: "deepseek-flash",
    usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
    stopReason: "stop", timestamp: Date.now(), ...over,
  } as AssistantMessage;
}

function fake(deltas: string[], falha = false): { fn: StreamFn; opcoes: unknown[] } {
  const opcoes: unknown[] = [];
  const fn: StreamFn = (_m, _c, o) => {
    opcoes.push(o);
    const s = createAssistantMessageEventStream();
    queueMicrotask(() => {
      let texto = "";
      s.push({ type: "start", partial: msg({}) });
      s.push({ type: "text_start", contentIndex: 0, partial: msg({}) });
      for (const delta of deltas) {
        texto += delta;
        s.push({ type: "text_delta", contentIndex: 0, delta, partial: msg({ content: [{ type: "text", text: texto }] }) });
      }
      if (falha) {
        s.push({ type: "error", reason: "error", error: msg({ content: [{ type: "text", text: texto }], stopReason: "error", errorMessage: "boom" }) });
      } else {
        s.push({ type: "text_end", contentIndex: 0, content: texto, partial: msg({ content: [{ type: "text", text: texto }] }) });
        s.push({ type: "done", reason: "stop", message: msg({ content: [{ type: "text", text: texto }] }) });
      }
    });
    return s;
  };
  return { fn, opcoes };
}

const pedido = () => new Request("http://x/api/chat", {
  method: "POST", body: JSON.stringify({ mensagens: [{ papel: "usuario", texto: "oi" }] }),
});

test("responde 200 text/plain com os deltas concatenados e maxTokens 800", async () => {
  const { fn, opcoes } = fake(["Olá", ", ", "mundo"]);
  const r = await responder(pedido(), { streamFn: fn });
  expect(r.status).toBe(200);
  expect(r.headers.get("content-type")).toBe("text/plain; charset=utf-8");
  expect(await r.text()).toBe("Olá, mundo");
  expect((opcoes[0] as { maxTokens: number }).maxTokens).toBe(800);
});

test("acrescenta a linha de falha quando o modelo erra no meio", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  const { fn } = fake(["Par", "cial"], true);
  const r = await responder(pedido(), { streamFn: fn });
  expect(await r.text()).toBe("Parcial\n\n[Não consegui terminar a resposta. Tente de novo.]");
  expect(log).toHaveBeenCalledWith("[chat]", "error", "boom");
  log.mockRestore();
});

test("para após 6 chamadas ao modelo quando só pede ferramenta e avisa o cliente", async () => {
  let chamadas = 0;
  const fn: StreamFn = () => {
    chamadas++;
    const s = createAssistantMessageEventStream();
    queueMicrotask(() => {
      const tc = { type: "toolCall" as const, id: `t${chamadas}`, name: "buscar_parlamentar", arguments: { consulta: "liza" } };
      const m = msg({ content: [tc], stopReason: "toolUse" });
      s.push({ type: "start", partial: msg({}) });
      s.push({ type: "toolcall_end", contentIndex: 0, toolCall: tc, partial: m });
      s.push({ type: "done", reason: "toolUse", message: m });
    });
    return s;
  };
  const r = await responder(pedido(), { streamFn: fn });
  const texto = await r.text();
  expect(chamadas).toBe(6);
  expect(texto).toBe("\n\n[A pergunta precisou de muitas consultas. Tente perguntar de forma mais específica.]");
});
