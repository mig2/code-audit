# Java

## 1. Detection signals
`pom.xml` (Maven), `build.gradle[.kts]` (Gradle), `*.java`; multi-module: `<modules>` /
`settings.gradle` includes (sub-projects). Frameworks: Spring (`@SpringBootApplication`,
starters), Jakarta EE, Android (`AndroidManifest.xml` — note: Android adds lint via
`gradlew lint`). Service signal: Spring Boot/embedded-server deps + Dockerfile.

## 2. Tool matrix

| Purpose | Tool | Invocation | Notes |
|---|---|---|---|
| Bug patterns | SpotBugs + FindSecBugs | `spotbugs -textui -xml:withMessages -include ... target/classes` | needs compiled classes — `mvn -q compile` / `gradlew classes` first (user approval) |
| Lint | PMD | `pmd check -d SRC -R rulesets/java/quickstart.xml -f json` | source-level, no build |
| Style | Checkstyle | `checkstyle -c <repo's or google_checks.xml> -f xml SRC` | source-level |
| SAST | semgrep | `semgrep scan --config p/java --config p/security-audit --json` | JSON |
| Dep vulns | osv-scanner | `osv-scanner scan --format json -r .` (reads pom/gradle lockfiles) | JSON |
| Dep vulns (alt) | OWASP dependency-check | `dependency-check --scan . --format JSON` | slow; NVD download — skip in `--offline` |
| Licenses | license-maven-plugin / gradle-license-report | if configured; else osv-scanner inventory + manual | varies |
| Secrets | gitleaks | `gitleaks detect --report-format json` | JSON |
| Coverage | JaCoCo | `mvn test jacoco:report` — **user approval** | XML |

No-root installs: SpotBugs/PMD/Checkstyle ship as zips → `~/.local/share/code-audit/tools/`.
ErrorProne: only if already wired into the build (adding it is a recommendation, not an
audit step).

## 3. Strictness escalation
`javac -Xlint:all -Werror` delta (advisory compile); census: raw types, unchecked
warnings suppressed (`@SuppressWarnings("unchecked")` density), `Optional.get()` without
presence check, `null` returns on collection-typed methods, reflection usage,
`synchronized` vs `java.util.concurrent` ratio, checked-exception laundering
(`throws Exception`, `catch (Exception e)` breadth).

## 4. Risk checklist
**Correctness:** `equals`/`hashCode` contract — overridden pairs, mutable fields in
hash keys, comparison via `==` on boxed types/Strings; `BigDecimal` for money (and
`new BigDecimal(double)` trap); resource leaks — every Closeable in try-with-resources
(streams from `Files.lines`, JDBC triple: Connection/Statement/ResultSet);
`SimpleDateFormat` shared across threads (not thread-safe — want
`DateTimeFormatter`); legacy `Date`/`Calendar` math vs `java.time`; serialVersionUID
and Serializable on evolving classes; equals-ignore-case locale traps
(`toUpperCase()` Turkish-i — want `Locale.ROOT` at protocol boundaries).

**Concurrency:** check-then-act on shared maps (want `computeIfAbsent`/concurrent
collections); double-checked locking without `volatile`; `synchronized` on `this`/class
exposed publicly; thread pools — unbounded queues (OOM) or `Executors.newCachedThreadPool`
on bursty load; `CompletableFuture` chains swallowing exceptions (no
`exceptionally`/`whenComplete`); `ThreadLocal` leaks in pooled environments.

**Security:** deserialization of untrusted data (`ObjectInputStream` — top Java RCE
class; also XStream/Jackson polymorphic typing `enableDefaultTyping`); XXE — every
`DocumentBuilderFactory`/`SAXParser`/`XMLInputFactory` without secure-processing
features; SQL via string concat (want PreparedStatement; check MyBatis `${}` vs `#{}`);
JNDI lookups on tainted input; `Runtime.exec` with built strings; path traversal on
`new File(base, userInput)`; weak crypto (`DES`, `ECB` mode, `MD5`/`SHA1` for
passwords — want bcrypt/argon2); `TrustManager`/`HostnameVerifier` overrides accepting
everything; Spring: CSRF disabled without reason, actuator endpoints exposed,
`@CrossOrigin("*")` with credentials, SpEL on user input.

**Performance:** string concat in loops (compiler handles simple cases — flag loop
accumulation; want StringBuilder); autoboxing in hot loops/collections of primitives;
N+1 in JPA (lazy relations iterated — want fetch joins/EntityGraph; also
`hibernate.show_sql` evidence); regex compilation per call; reading entire files where
streaming fits.

## 5. Idiom rubric
Immutability by default (final fields, records for data carriers); Optional as return
type only (not fields/params); streams where they clarify, loops where they don't (no
stream gymnastics); interfaces for seams actually needed; constructor injection over
field injection (Spring); exceptions: specific catches, no log-and-rethrow duplication,
no exceptions for control flow; package-by-feature over package-by-layer for larger
apps; Javadoc on public API with `@throws` honesty.
