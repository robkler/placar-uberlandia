// Roda o mesmo agente do site no terminal: pnpm chat "pergunta"
import { carregarDados } from "../lib/dados.js";
import { criarAgente, escolherModelo } from "../lib/agente.js";

for (const arquivo of [".env", ".env.local"]) {
  try { process.loadEnvFile(arquivo); } catch { /* arquivo ausente: ignora */ }
}

const pergunta = process.argv.slice(2).join(" ").trim();
if (!pergunta) {
  console.error('Uso: pnpm chat "sua pergunta"');
  process.exit(1);
}

try {
  const { models, model } = escolherModelo();
  if (!(await models.getAuth(model))) {
    console.error(`Chave da API não encontrada para o provedor "${model.provider}". Defina a variável de ambiente da chave (por exemplo DEEPSEEK_API_KEY ou OPENCODE_API_KEY) em .env.local.`);
    process.exit(1);
  }
  const agente = criarAgente(await carregarDados(), []);
  let falhou = false;
  let novaMensagem = false;
  let escreveu = false;
  agente.subscribe(ev => {
    if (ev.type === "message_update" && ev.assistantMessageEvent.type === "text_delta") {
      if (novaMensagem && escreveu) process.stdout.write("\n\n");
      novaMensagem = false;
      escreveu = true;
      process.stdout.write(ev.assistantMessageEvent.delta);
    } else if (ev.type === "message_start" && ev.message.role === "assistant") {
      novaMensagem = true;
    } else if (ev.type === "message_end" && ev.message.role === "assistant" &&
      (ev.message.stopReason === "error" || ev.message.stopReason === "aborted")) {
      falhou = true;
      console.error(`\nErro do modelo: ${ev.message.errorMessage ?? ev.message.stopReason}`);
    }
  });
  await agente.prompt(pergunta);
  process.stdout.write("\n");
  if (falhou) process.exit(1);
} catch (e) {
  console.error(`Erro: ${e instanceof Error ? e.message : String(e)}`);
  process.exit(1);
}
