import { readFile } from "node:fs/promises";
import path from "node:path";

export type Casa = "vereador" | "estadual" | "federal";

/** Formato dos JSONs de public/ como estão hoje. */
export interface Dados {
  udi: any; // data.json
  mg: any; // mg.json
  fed: any; // federal.json
}

const TTL_MS = 10 * 60 * 1000;
const cache = new Map<string, { em: number; dados: Promise<Dados> }>();

async function ler(pasta: string, arquivo: string) {
  return JSON.parse(await readFile(path.join(pasta, arquivo), "utf8"));
}

/** Lê public/*.json e guarda em memória por 10 minutos. */
export function carregarDados(pasta: string = path.join(process.cwd(), "public")): Promise<Dados> {
  const agora = Date.now();
  const hit = cache.get(pasta);
  if (hit && agora - hit.em < TTL_MS) return hit.dados;
  const dados = Promise.all([
    ler(pasta, "data.json"),
    ler(pasta, "mg.json"),
    ler(pasta, "federal.json"),
  ]).then(([udi, mg, fed]) => ({ udi, mg, fed }));
  cache.set(pasta, { em: agora, dados });
  dados.catch(() => cache.delete(pasta));
  return dados;
}
