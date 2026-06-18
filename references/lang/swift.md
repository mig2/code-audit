# Swift

## 1. Detection signals
`Package.swift` (SwiftPM), `*.xcodeproj`/`*.xcworkspace`, `Podfile`, `Cartfile`,
`*.swift`. App vs. library: app targets in project, `@main`/`AppDelegate`. Platform
flags in manifest. Service signal: Vapor/Hummingbird deps.

## 2. Tool matrix — **platform-dependent**

| Purpose | Tool | Invocation | Platform |
|---|---|---|---|
| Lint | SwiftLint | `swiftlint lint --reporter json` | macOS; Linux if installed |
| Format conformance | swift-format | `swift-format lint -r SRC` | both (if toolchain) |
| Compiler diagnostics | swift build | `swift build -Xswiftc -warnings-as-errors 2>&1` (SwiftPM only) | both w/ toolchain |
| Static analysis | xcodebuild | `xcodebuild analyze -scheme S -quiet` | **macOS only** |
| Dep vulns | osv-scanner | `osv-scanner scan --format json -r .` (reads Package.resolved) | both |
| Secrets | gitleaks | `gitleaks detect --report-format json` | both |
| Coverage | swift test | `swift test --enable-code-coverage` + `llvm-cov export` — **user approval** | toolchain |

**Linux degradation:** no xcodebuild analyze, no Xcode-project builds. Record both as
coverage gaps. SwiftLint runs on Linux (prebuilt binary or `mint`). Xcode-project-only
repos on Linux ⇒ automated layer is SwiftLint + gitleaks + osv-scanner; your manual
review carries this audit — say so in the completeness table and weight Phase 3 up.

Install (macOS): `brew install swiftlint swift-format` (user-writable brew) or `mint
install`. Linux: SwiftLint release binary into `~/.local/bin`.

## 3. Strictness escalation
SwiftPM: build with `-Xswiftc -strict-concurrency=complete` (pre-Swift-6 repos) and
report the Sendable/isolation diagnostic count as the concurrency-readiness gap. Census:
`!` force unwraps (excluding `as!`-free test code), `try!`, `as!`, implicitly-unwrapped
optional declarations (`: Type!`), `@unchecked Sendable` — density per kLOC.
SwiftLint with `--strict` and analyzer rules (`unused_declaration`, `unused_import`)
when a compilation log is available.

## 4. Risk checklist
**Memory/lifecycle:** retain cycles — closures capturing `self` strongly in stored
handlers (`[weak self]` discipline), delegate properties not `weak`, timer/observer
invalidation; `unowned` where lifetime isn't actually guaranteed.

**Concurrency:** actor/`Sendable` correctness; `@MainActor` discipline for UI-touching
code; `Task {}` fire-and-forget without cancellation/error handling; shared mutable
state crossing isolation via `@unchecked Sendable`; blocking calls inside async contexts
(sync I/O, semaphores bridging callback APIs); data races in pre-concurrency code
(DispatchQueue discipline, `sync` deadlock shapes).

**Correctness:** force-unwrap on data that can legitimately be nil (JSON, userInfo,
first/last); `try?` swallowing errors silently on important paths; floating-point money;
`Codable` decoding without strategy for missing/extra fields where the API evolves;
notification/KVO observer leaks.

**Security:** Keychain vs. UserDefaults for secrets; ATS exceptions
(`NSAllowsArbitraryLoads`); `NSCoding` without `NSSecureCoding`; WKWebView JS bridges
exposing native calls to remote content; hardcoded API keys (gitleaks + manual);
URL scheme handlers validating inputs; jailbreak-detectable assumptions ≠ security.

**Performance:** main-thread I/O or decoding; O(n) `Array.contains` in loops (want Set);
image decoding off-cache on scroll paths; excessive Combine chain allocations on hot
paths; struct copies of large value types in tight loops (CoW awareness).

## 5. Idiom rubric
Optionals as honest API (no `!` in signatures); `guard let` early-exit shape; value
types by default, classes for identity/lifecycle; protocol-oriented composition over
deep class hierarchies (but no protocol-for-one-conformer ritual); `Result`/typed
`throws` at boundaries; extensions to organize conformances; trailing-closure and
argument labels reading as sentences; avoid stringly-typed selectors/keys (use
`#keyPath`, enums for userInfo keys).
