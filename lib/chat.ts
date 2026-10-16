import type { StreamFn } from "@earendil-works/pi-agent-core";
import { carregarDados } from "./dados.js";
import { criarAgente, validarPedido } from "./agente.js";

export const LINHA_FALHA = "\n\n[Não consegui terminar a resposta. Tente de novo.]";
const TEMPO_MAXIMO_MS = 60_000;

const erro400 = (erro: string) =>
  Response.json({ erro }, { status: 400 });

/** Lógica do endpoint; `streamFn` é injetado só nos testes. */
export async function responder(req: Request, opcoes: { streamFn?: StreamFn } = {}): Promise<Response> {
  let corpo: unknown;
  try {
    corpo = await req.json();
  } catch {
    return erro400("O corpo da requisição precisa ser um JSON válido.");
  }
  let mensagens;
  try {
    ({ mensagens } = validarPedido(corpo));
  } catch (e) {
    return erro400(e instanceof Error ? e.message : "Pedido inválido.");
  }

  const ultima = mensagens[mensagens.length - 1]!;
  const agente = criarAgente(await carregarDados(), mensagens.slice(0, -1), opcoes);
  const enc = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      let falhou = false;
      const timer = setTimeout(() => { falhou = true; agente.abort(); }, TEMPO_MAXIMO_MS);
      req.signal.addEventListener("abort", () => agente.abort());
      agente.subscribe(ev => {
        if (ev.type === "message_update" && ev.assistantMessageEvent.type === "text_delta") {
          controller.enqueue(enc.encode(ev.assistantMessageEvent.delta));
        } else if (ev.type === "message_end" && ev.message.role === "assistant") {
          if (ev.message.stopReason === "error" || ev.message.stopReason === "aborted") falhou = true;
        }
      });
      try {
        await agente.prompt(ultima.texto);
      } catch {
        falhou = true;
      } finally {
        clearTimeout(timer);
      }
      if (falhou) controller.enqueue(enc.encode(LINHA_FALHA));
      controller.close();
    },
    cancel() { agente.abort(); },
  });

  return new Response(stream, { headers: { "content-type": "text/plain; charset=utf-8" } });
}
