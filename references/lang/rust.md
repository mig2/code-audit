# Rust

## 1. Detection signals
`Cargo.toml`/`Cargo.lock`, `*.rs`; workspaces: `[workspace]` members (sub-projects).
Service signal: axum/actix/tonic/warp deps + binary targets. `unsafe` presence steers
review weight. `#![no_std]` flags embedded context (adjust expectations).

## 2. Tool matrix

| Purpose | Tool | Invocation | Notes |
|---|---|---|---|
| Lint | clippy | `cargo clippy --all-targets --message-format=json` | repo's lint config respected |
| Lint (audit tier) | clippy pedantic | `cargo clippy --all-targets --message-format=json -- -W clippy::pedantic -W clippy::nursery` | **report separately**; advisory census, not findings parity |
| Compiler | cargo check | `cargo check --all-targets --message-format=json` | warnings included |
| Dep vulns | cargo-audit | `cargo audit --json` | RustSec DB; needs network unless DB cached |
| Deps policy | cargo-deny | `cargo deny check --format json` (licenses, bans, advisories, sources) | reads/needs `deny.toml` — if absent, run with a default config from assets and note it |
| Licenses | cargo-deny | covered above | |
| Unsafe census | cargo-geiger | `cargo geiger --output-format Json` | optional; counts also derivable by grep |
| UB testing | miri | `cargo +nightly miri test` — **user approval; slow; nightly** | only when unsafe code + tests exist |
| Secrets | gitleaks | `gitleaks detect --report-format json` | JSON |
| Coverage | cargo-llvm-cov | `cargo llvm-cov --json` — user approval | |

Installs: `rustup component add clippy`, `cargo install cargo-audit cargo-deny` →
`~/.cargo/bin`. Pure no-root.

## 3. Strictness escalation
The pedantic/nursery clippy run above. Census: `unsafe` blocks (count + per-block
justification-comment presence — `// SAFETY:` discipline), `unwrap()`/`expect()` outside
tests (split: `expect` with message vs bare `unwrap`), `panic!`/`todo!`/`unimplemented!`
in library code, `#[allow(...)]` density, `clone()` density (advisory), `as` casts on
integers (want `try_into` near boundaries), `mem::transmute` (each one is a finding
until justified).

## 4. Risk checklist
**Unsafe (the Rust dimension):** every `unsafe` block — is the invariant stated
(`// SAFETY:`), is it actually upheld, could safe code + a dependency replace it?
FFI boundaries: pointer validity/lifetime across the boundary, panic-across-FFI
(UB — want `catch_unwind` shields), `CString` lifetime bugs (`as_ptr` on temporary);
`transmute` vs safe alternatives; `unsafe impl Send/Sync` — verify the claim against
the fields.

**Correctness:** panic policy — `unwrap` on values that can legitimately be
None/Err in production paths (CLI args vs request data differ — judge context);
arithmetic overflow (release-mode wraps silently — want
`checked_*`/`saturating_*` on untrusted math, or `overflow-checks = true`);
error-type design — `Box<dyn Error>`/anyhow in *libraries* (want thiserror-style typed
errors at public boundaries; anyhow fine in binaries); `Result` discarded via `let _ =`
on fallible writes; blocking calls in async (std `Mutex` held across `.await`,
`std::fs`/`reqwest::blocking` inside tokio — want `spawn_blocking`/async equivalents);
async cancellation safety (state corruption when a future drops mid-operation);
deadlocks via lock ordering or re-entrant locking.

**Security:** mostly inherited from deps — cargo-audit/deny carry it; plus: SQL string
building (sqlx macros vs format!), path traversal on user paths, `Command` with
sh `-c`, deserialization bombs (serde untagged enums on untrusted input — exponential
blowup; size limits on inputs), constant-time comparison for secrets (want `subtle`).

**Performance:** needless `clone()`/`to_owned()` on hot paths (borrow instead);
`String` building via `+` in loops; `Vec` without `with_capacity` in measured hot loops;
boxed trait objects where generics fit hot paths; `Rc<RefCell<...>>` webs as a design
smell (often a structure problem masquerading as a borrow-checker fight); async executor
churn (spawning per-item where batching fits).

**Deps:** duplicate crate versions in the tree (`cargo tree -d`); git deps on branches;
heavyweight deps for trivial needs; build.rs doing surprising things (network, codegen
from env) — supply-chain relevant.

## 5. Idiom rubric
Ownership expressed in signatures (`&str`/`&[T]` params, owned returns when transferring);
iterator chains over index loops where clear; pattern matching exhaustive — `match` over
if-let chains for multi-variant logic, no `_ =>` swallowing variants that deserve
handling; newtypes for domain values over bare primitives; `From`/`TryFrom` for
conversions; builder pattern for many-field construction; modules organized by domain
with `pub(crate)` discipline (minimal true `pub`); doc comments with examples on public
API (doctests as free tests); Clippy clean at default levels as table stakes.
