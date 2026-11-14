// Check: competition search by country name/code (app/src/SearchScreen.tsx norm/tier/best + src/countries.ts), against api/v1/index.json.
// Run from app/: node scripts/check_country_search.mjs [path-to-index.json]
import fs from "node:fs";
import ts from "typescript";

const tsx = fs.readFileSync(new URL("../src/SearchScreen.tsx", import.meta.url), "utf8").split("\r\n").join("\n");
// source of a top-level function (from "function name(" to the closing "}" at column 0)
const grab = (name) => {
  const i = tsx.indexOf(`function ${name}(`);
  const j = tsx.indexOf("\n}\n", i);
  if (i < 0 || j < 0) throw new Error("function not found: " + name);
  return tsx.slice(tsx.lastIndexOf("\n", i) + 1, j + 3).replace(/^export /, "");
};
const bestLine = tsx.match(/const best = [^\n]+\n/)[0];
const ctry = fs.readFileSync(new URL("../src/countries.ts", import.meta.url), "utf8");
const js = ts.transpileModule(ctry.split("export ").join("") + "\n" + grab("norm") + grab("tier") + bestLine +
  "\nglobalThis.__m = { norm, best, countryKeys };", { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
eval(js);
const { norm, best, countryKeys } = globalThis.__m;

const idx = JSON.parse(fs.readFileSync(process.argv[2] || new URL("../../api/v1/index.json", import.meta.url), "utf8"));
const comps = [...idx.leagues, ...idx.cups].map((c) => ({
  code: c.code,
  keys: [norm(c.name.ar), norm(c.name.en), norm(c.code), ...countryKeys(c.code).map(norm)],
}));
const search = (q) => comps.filter((c) => best(norm(q), ...c.keys) < 9).map((c) => c.code);

// query -> country: every competition of that country must be found, and nothing from another country
const expect = { "السعودية": "SAU", KSA: "SAU", Saudi: "SAU", "مصر": "EGY", Egypt: "EGY", "الأردن": "JOR", Jordan: "JOR",
  JOR: "JOR", "الإمارات": "UAE", Morocco: "MAR" };
let fail = 0;
for (const [q, c] of Object.entries(expect)) {
  const got = search(q);
  const want = comps.map((x) => x.code).filter((x) => x.split("-")[0] === c);
  const ok = want.every((w) => got.includes(w)) && got.every((g) => g.split("-")[0] === c);
  if (!ok) fail++;
  console.log(`${ok ? "PASS" : "FAIL"} ${q} -> ${got.join(", ")}${ok ? "" : "  (want " + want.join(", ") + ")"}`);
}
console.log(fail ? `${fail} failed` : "all passed");
process.exit(fail ? 1 : 0);
