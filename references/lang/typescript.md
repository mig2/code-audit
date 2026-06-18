# TypeScript / JavaScript / Node

Covers TS and JS; TS-only items marked **[TS]**. Browser-vs-Node differences noted.

## 1. Detection signals
`package.json` (always), `tsconfig.json` **[TS]**, lockfiles (`package-lock.json`,
`yarn.lock`, `pnpm-lock.yaml`, `bun.lockb`), `*.ts|tsx|js|jsx|mjs|cjs`. Frameworks:
react/next (`next.config.*`), express/fastify/nest (deps), electron. Monorepo:
`workspaces` field, `pnpm-workspace.yaml`, `turbo.json`, `nx.json`. Service signal:
server framework deps + Dockerfile/start script.

## 2. Tool matrix

| Purpose | Tool | Invocation | Output |
|---|---|---|---|
| Lint | eslint | `npx eslint . -f json` (uses repo config; if none, flag as finding and run with `--no-eslintrc --config` a minimal recommended config) | JSON |
| Types **[TS]** | tsc | `npx tsc --noEmit --pretty false` | text (parseable `file(l,c): error TS####`) |
| SAST | semgrep | `semgrep scan --config p/typescript --config p/javascript --config p/security-audit --json` | JSON |
| Dep vulns | npm/pnpm/yarn audit | `npm audit --json` (match the repo's package manager) | JSON |
| Dep vulns (alt) | osv-scanner | `osv-scanner scan --format json -r .` | JSON |
| Licenses | license-checker | `npx license-checker --json` | JSON |
| Dead code/exports | knip | `npx knip --reporter json` | JSON |
| Import cycles | madge | `npx madge --circular --json SRC` | JSON |
| Duplication | jscpd | `npx jscpd --reporters json SRC` | JSON |
| Secrets | gitleaks | `gitleaks detect --report-format json` | JSON |
| Coverage | repo's runner | `npx jest --coverage --coverageReporters=json-summary` / vitest equivalent — **user approval to run tests** | JSON |

`npx` makes most of these zero-install; prefer the repo's own pinned versions when in
`devDependencies`.

## 3. Strictness escalation **[TS]**
Run tsc with `--strict --noUncheckedIndexedAccess --exactOptionalPropertyTypes
--noImplicitOverride` against the repo and report the delta vs. its own tsconfig as the
type-honesty gap. Census: `any` (explicit + `as any`), `@ts-ignore`/`@ts-expect-error`,
non-null assertions `!.`, `unknown`-laundering casts — density per kLOC. JS-only repos:
note absence of types as a maintainability finding scaled to repo size, and whether
`// @ts-check` + JSDoc is in use.

## 4. Risk checklist
**Security/data flow:** injection sinks — `child_process.exec` with concatenated input
(want `execFile`), string-built SQL, `eval`/`new Function`, dynamic `require`; XSS —
`dangerouslySetInnerHTML`, `innerHTML`/`insertAdjacentHTML`, unescaped template
rendering; prototype pollution — deep-merge of user input, `Object.assign` chains,
`__proto__` handling; path traversal in `fs` ops on request data; SSRF via fetch/axios
on user URLs; ReDoS — user input into complex regex; JWT: `alg:none` acceptance, secrets
in code; cookies without `httpOnly`/`secure`/`sameSite`; CORS `*` with credentials;
Express: missing helmet-ish headers, body-size limits, rate limiting on auth.

**Correctness:** floating promises (un-awaited, no `.catch`) — top Node bug class;
`async` array callbacks in `forEach`/`map` without `Promise.all`; missing `await` in
try/catch (error escapes the catch); `==` vs `===` on untyped boundaries; NaN/`parseInt`
without radix on input; mutation of shared module-level state across requests;
unhandled `error` events on streams/EventEmitters (process crash); timezone/locale math
with bare `Date`.

**Performance:** sync fs/crypto/zlib on request paths (`*Sync` in handlers — event-loop
stalls); unbounded concurrency (`Promise.all` over thousands of I/O calls — want
batching); JSON.parse/stringify of huge payloads on hot paths; bundle weight for
frontends (census only at triage).

**Deps:** the supply-chain heavyweight — flag: install scripts (`postinstall`) in deps,
git/branch deps, duplicate majors of the same lib, lockfile absent/drifted, abandoned
criticals. ESM/CJS seams: dual-mode packages, `default` interop bugs, `type: module`
mismatches.

## 5. Idiom rubric
**[TS]** types at boundaries, inference inside; discriminated unions over enums-of-flags
and over boolean parameter pairs; `unknown` + narrowing over `any`; `readonly` where
intent is immutability; zod/valibot-style runtime validation at I/O edges matching the
static types. General: async/await over then-chains; early returns; optional
chaining/nullish coalescing over `&&` ladders; named exports over default (refactor
safety); small modules over barrel-file megahubs (note: barrels also hurt tree-shaking).
