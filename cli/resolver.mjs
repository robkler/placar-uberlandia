import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

export async function resolve(especificador, contexto, proximo) {
  if (especificador.startsWith(".") && especificador.endsWith(".js") && contexto.parentURL) {
    const alvo = new URL(especificador.replace(/\.js$/, ".ts"), contexto.parentURL);
    if (existsSync(fileURLToPath(alvo))) return proximo(alvo.href, contexto);
  }
  return proximo(especificador, contexto);
}
