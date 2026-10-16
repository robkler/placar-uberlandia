// Deixa o Node 24 (que remove os tipos sozinho) resolver os imports "./x.js" de lib/ para "./x.ts".
import { register } from "node:module";
register("./resolver.mjs", import.meta.url);
