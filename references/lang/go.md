# Go

## 1. Detection signals
`go.mod`/`go.sum`, `*.go`. Multi-module repos: nested `go.mod` (each is a sub-project).
Service signal: `net/http`/grpc/gin/echo/chi imports + `main` packages; CLI signal:
cobra/flag-heavy mains.

## 2. Tool matrix

| Purpose | Tool | Invocation | Output |
|---|---|---|---|
| Vet | go vet | `go vet -json ./...` | JSON |
| Lint (meta) | golangci-lint | `golangci-lint run --out-format json` (respects repo config; else curated default set) | JSON |
| Static analysis | staticcheck | `staticcheck -f json ./...` (skip if golangci already includes it) | JSON |
| SAST | gosec | `gosec -fmt json ./...` | JSON |
| Dep vulns | govulncheck | `govulncheck -json ./...` — **call-graph aware**: distinguishes imported-vs-called; trust its reachability for severity mapping | JSON |
| Licenses | go-licenses | `go-licenses report ./... 2>/dev/null` | CSV |
| Secrets | gitleaks | `gitleaks detect --report-format json` | JSON |
| Race detection | go test | `go test -race ./...` — **user approval to run tests**; race findings are P0/P1 gold | text |
| Coverage | go test | `go test -coverprofile=... ./...` — user approval | profile |
| Duplication | dupl (via golangci) or jscpd | — | JSON |

Install: `go install tool@latest` → `~/go/bin` (pure no-root). gitleaks: release binary.

## 3. Strictness escalation
golangci-lint with an audit profile beyond repo config: enable `errcheck` (with
`check-type-assertions`, `check-blank`), `errorlint`, `bodyclose`, `noctx`, `contextcheck`,
`nilerr`, `exhaustive`, `gocritic`, `prealloc`, `copyloopvar` — report delta vs. repo's
own config. Census: `interface{}`/`any` parameter density, `panic(` outside main/init,
`_ = err` discards, `//nolint` density, `unsafe` imports, `reflect` usage sites.

## 4. Risk checklist
**Error handling (the Go dimension):** discarded errors (`_ =`, bare call); errors
checked-then-shadowed; `err` from deferred `Close` on *writes* ignored (data loss);
sentinel comparison with `==` instead of `errors.Is/As`; wrapping discipline (`%w`)
and whether errors carry enough context to debug.

**Concurrency:** goroutine leaks — launches without cancellation path (blocked on
channel nobody reads, missing `ctx.Done()` select); `context.Context` propagation —
dropped ctx, `context.Background()` deep in call stacks, missing timeouts on outbound
I/O; data races — shared maps/slices/structs without mutex or confinement (race detector
+ manual on the residue); `sync.WaitGroup` misuse (Add inside the goroutine); channel
direction/close discipline (send on closed, double close); `time.After` in loops (leak
pre-1.23 runtimes).

**Correctness:** nil-map writes; slice aliasing surprises (append sharing backing
arrays, sub-slice retention pinning big arrays); loop-variable capture (pre-1.22
modules — check `go` directive); integer division/overflow on size math; `defer` in
loops (resource pileup); JSON: silent zero-values on missing fields where presence
matters (want pointers or `json.RawMessage` discipline); time: `time.Time` equality via
`==` (monotonic clock), missing `.UTC()` normalization at boundaries.

**Security:** `text/template` where `html/template` belongs; SQL string building;
`exec.Command` with sh `-c` + input; path traversal via `filepath.Join` on request data
(want `filepath.IsLocal`/`SecureJoin`); TLS `InsecureSkipVerify`; unbounded
`io.ReadAll` on request bodies (want `http.MaxBytesReader`); missing
`ReadHeaderTimeout` (slowloris) on `http.Server`.

**Performance:** allocations in hot loops (string concat — want Builder; boxing into
`any`); `[]byte(string)` round-trips; unbuffered channels as queues on hot paths;
regex compilation in loops (want package-level `MustCompile`).

## 5. Idiom rubric
Small interfaces, defined at the consumer (no interface pollution / premature
abstraction); accept interfaces, return structs; zero values made useful; errors as
values with context, no panic-driven flow; `context.Context` first parameter, never
stored in structs; table-driven tests; package names short, no stutter
(`user.User` ok, `user.UserService` smell); avoid `init()` magic and package-level
mutable state; godoc comments on exported identifiers.
