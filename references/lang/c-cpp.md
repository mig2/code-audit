# C / C++

One file, divergences marked **[C]** / **[C++]**. The audit's center of gravity here is
memory safety and UB; weight Phase 3 accordingly.

## 1. Detection signals
`*.c|h` **[C]**, `*.cpp|cc|cxx|hpp|hh` **[C++]**; build systems: `CMakeLists.txt`,
`Makefile`, `meson.build`, `BUILD.bazel`, `configure.ac`. Standard from build flags
(`-std=`). `compile_commands.json` presence determines clang-tidy viability — if absent
and CMake exists, generate via `cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -B build-audit`
(user approval; out-of-tree dir).

## 2. Tool matrix

| Purpose | Tool | Invocation | Notes |
|---|---|---|---|
| Static analysis | cppcheck | `cppcheck --enable=all --inconclusive --xml SRC 2> raw/cppcheck.xml` | no compile DB needed |
| Static analysis | clang-tidy | `clang-tidy -p build-audit --checks=<set> $(files)` via `run-clang-tidy` | needs compile_commands.json |
| Compiler warnings | gcc/clang | rebuild w/ `-Wall -Wextra -Wpedantic -Wconversion -Wshadow` (out-of-tree; user approval) | text |
| Sanitizers | ASan/UBSan/TSan | test-suite run with `-fsanitize=address,undefined` (separate build; TSan separately) — **user approval, big runtime cost** | text |
| SAST | semgrep | `semgrep scan --config p/c --config p/cpp --json` | JSON |
| Dep vulns | osv-scanner | conan/vcpkg manifests if present; vendored deps need manual inventory | JSON |
| Secrets | gitleaks | `gitleaks detect --report-format json` | JSON |
| Include hygiene | include-what-you-use | optional, needs compile DB | text |

clang-tidy check set: `bugprone-*, cert-*, concurrency-*, misc-*, performance-*` plus
**[C++]** `modernize-*, cppcoreguidelines-*` (narrate, don't dump — these are noisy;
aggregate by check into single findings with counts). No-root installs are the weak
point here: use distro-provided binaries if present; else record the gap.

## 3. Strictness escalation
The warning rebuild above *is* the escalation. Census: `malloc/free` count vs.
smart-pointer count **[C++]**, raw `new`/`delete` **[C++]**, `(cast)` C-style casts in
C++ files, `strcpy/strcat/sprintf/gets` family **[C]**, `goto` usage, `#define` function
macros, global mutable state, `const` discipline on pointer parameters.

## 4. Risk checklist
**Memory/lifetime (both):** every allocation's owner identifiable? double-free /
use-after-free shapes (free in one branch, use after); returning pointers/references to
locals; buffer arithmetic — every index/length computation near external input;
off-by-one at boundaries (`<=` with sizes, null-terminator space); unchecked
malloc/realloc returns (and the `p = realloc(p,...)` leak shape); `memcpy` size
mismatches; **[C++]** RAII conformance — naked resources that should be
unique_ptr/lock_guard/fstream; rule-of-three/five on resource-owning classes; iterator
invalidation (erase-in-loop, reference into reallocating vector); object slicing;
dangling `string_view`/spans.

**UB inventory (both):** signed overflow in size/index math; shifts ≥ width; strict
aliasing violations (type-punning via casts — want memcpy); uninitialized reads;
sequence-point/unsequenced modification; misaligned access from packed structs;
**[C]** VLAs from untrusted sizes.

**Concurrency:** data races on shared globals/statics; lock-ordering hazards;
condition-variable wait without predicate loop; signal-handler async-safety **[C]**;
`volatile`-as-synchronization (it isn't); **[C++]** `std::atomic` memory-order
adventurism (non-default orders need justification); detached threads touching freed
state.

**Security:** all of the above near input, plus: format-string bugs (`printf(buf)`);
integer promotion surprises validating sizes (`int` vs `size_t` comparisons); TOCTOU on
file ops; `system()`/`popen` with built strings; world-writable temp files (`mkstemp`
discipline); `rand()` for anything security-relevant.

**Performance:** **[C++]** pass-by-value of heavy types; missing moves/reserve;
accidental copies in range-for (`auto` vs `const auto&`); virtual calls in inner loops;
**[both]** cache-hostile data layouts on measured hot paths only — demand profiles
before micro-findings.

**Build:** warnings suppressed wholesale; no sanitizer CI job; vendored deps unversioned
(dependency dimension); hardening flags absent for shipped binaries
(`-D_FORTIFY_SOURCE=2`, `-fstack-protector-strong`, RELRO/PIE).

## 5. Idiom rubric
**[C++]** RAII everywhere; smart pointers expressing ownership (unique by default,
shared with reason); `std::optional`/`expected` over out-params and sentinels; algorithms
over hand loops where clearer; `enum class`; `constexpr`/`const` discipline; no naked
`new`. **[C]** consistent ownership conventions documented at headers; goto-cleanup
pattern acceptable and audited for completeness; opaque structs for encapsulation;
sized-string discipline (`snprintf`, explicit lengths). **[both]** headers
self-contained; include guards/pragma once; minimal macro magic.
