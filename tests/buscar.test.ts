import { expect, test } from "vitest";
import { carregarDados } from "../lib/dados.js";
import { buscarParlamentar } from "../lib/consultas.js";

test("acha vereadora ignorando acento e caixa", async () => {
  const r = buscarParlamentar(await carregarDados(), "liza prado");
  expect(r[0]).toMatchObject({ casa: "vereador", id: "399022", link: "#v/399022" });
  expect(r[0].fonte).toBe("https://www.camarauberlandia.mg.gov.br/vereadores/vereadores/399022");
});
test("acha deputado federal pelo nome parlamentar", async () => {
  const r = buscarParlamentar(await carregarDados(), "AJ Albuquerque", "federal");
  expect(r[0]).toMatchObject({ casa: "federal", id: "204549", uf: "CE", link: "#d/204549" });
});
test("acha deputado estadual com link da ALMG", async () => {
  const r = buscarParlamentar(await carregarDados(), "adalclever");
  expect(r[0]).toMatchObject({ casa: "estadual", id: "12193", link: "#e/12193" });
  expect(r[0].fonte).toBe("https://www.almg.gov.br/a-assembleia/deputados/deputado/?id=12193");
});
test("sobrenome comum devolve várias pessoas e casas", async () => {
  const r = buscarParlamentar(await carregarDados(), "silva");
  expect(r.length).toBeGreaterThan(1);
  expect(new Set(r.map(p => p.casa)).size).toBeGreaterThan(1);
});
test("nada encontrado devolve lista vazia", async () => {
  expect(buscarParlamentar(await carregarDados(), "xyzxyz")).toEqual([]);
});
