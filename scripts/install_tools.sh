#!/usr/bin/env bash
# install_tools.sh — best-effort USER-LEVEL installs only. Never sudo.
# Usage: install_tools.sh --tools ruff,gosec,gitleaks[,...]   [--dry-run]
set -u
DRY=0; TOOLS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tools) TOOLS="$2"; shift 2;;
    --dry-run) DRY=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[[ -z "$TOOLS" ]] && { echo "usage: install_tools.sh --tools a,b,c [--dry-run]"; exit 2; }

LOCALBIN="$HOME/.local/bin"; mkdir -p "$LOCALBIN"
run() { echo "+ $*"; [[ $DRY -eq 1 ]] || "$@"; }
have() { command -v "$1" >/dev/null 2>&1; }

py_install() {  # prefer pipx > uv > pip --user
  local pkg="$1"
  if have pipx; then run pipx install "$pkg"
  elif have uv; then run uv tool install "$pkg"
  elif have pip3; then run pip3 install --user --break-system-packages "$pkg" 2>/dev/null || run pip3 install --user "$pkg"
  else echo "SKIP $pkg: no pipx/uv/pip3"; return 1; fi
}

gh_release_binary() {  # $1 name, $2 repo, $3 asset-grep
  local name="$1" repo="$2" pat="$3" os arch url tmp
  os=$(uname -s | tr '[:upper:]' '[:lower:]'); arch=$(uname -m)
  [[ "$arch" == "x86_64" ]] && arch_alt="amd64" || arch_alt="$arch"
  url=$(curl -fsSL "https://api.github.com/repos/$repo/releases/latest" \
        | grep -o '"browser_download_url": *"[^"]*"' | cut -d'"' -f4 \
        | grep -i "$os" | grep -iE "($arch|$arch_alt)" | grep -iE "$pat" | head -1)
  [[ -z "$url" ]] && { echo "SKIP $name: no matching release asset"; return 1; }
  tmp=$(mktemp -d)
  echo "+ download $url"
  if [[ $DRY -eq 0 ]]; then
    curl -fsSL "$url" -o "$tmp/pkg" || return 1
    case "$url" in
      *.tar.gz|*.tgz) tar -xzf "$tmp/pkg" -C "$tmp";;
      *.zip) unzip -q "$tmp/pkg" -d "$tmp";;
      *) cp "$tmp/pkg" "$tmp/$name"; chmod +x "$tmp/$name";;
    esac
    found=$(find "$tmp" -type f -name "$name" | head -1)
    [[ -z "$found" ]] && found=$(find "$tmp" -type f -perm -u+x ! -name pkg | head -1)
    [[ -z "$found" ]] && { echo "SKIP $name: binary not found in archive"; return 1; }
    install -m 0755 "$found" "$LOCALBIN/$name"
  fi
  echo "installed $name -> $LOCALBIN/$name"
}

for t in ${TOOLS//,/ }; do
  echo "── $t"
  case "$t" in
    ruff|mypy|bandit|pip-audit|radon|vulture|semgrep|pip-licenses) py_install "$t";;
    staticcheck) have go && run go install honnef.co/go/tools/cmd/staticcheck@latest || echo "SKIP: need go";;
    gosec)       have go && run go install github.com/securego/gosec/v2/cmd/gosec@latest || echo "SKIP: need go";;
    govulncheck) have go && run go install golang.org/x/vuln/cmd/govulncheck@latest || echo "SKIP: need go";;
    go-licenses) have go && run go install github.com/google/go-licenses@latest || echo "SKIP: need go";;
    golangci-lint) gh_release_binary golangci-lint golangci/golangci-lint 'tar.gz';;
    cargo-audit) have cargo && run cargo install cargo-audit --locked || echo "SKIP: need cargo";;
    cargo-deny)  have cargo && run cargo install cargo-deny --locked || echo "SKIP: need cargo";;
    cargo-clippy) have rustup && run rustup component add clippy || echo "SKIP: need rustup";;
    gitleaks)    gh_release_binary gitleaks gitleaks/gitleaks 'tar.gz';;
    osv-scanner) gh_release_binary osv-scanner google/osv-scanner '.*';;
    scc)         gh_release_binary scc boyter/scc 'tar.gz|zip';;
    gh)          gh_release_binary gh cli/cli 'tar.gz';;
    glab)        gh_release_binary glab gitlab-org/cli 'tar.gz';;
    swiftlint)
      if have brew; then run brew install swiftlint
      else gh_release_binary swiftlint realm/SwiftLint 'zip|tar'; fi;;
    eslint|tsc|madge|knip|jscpd|license-checker)
      echo "via npx at run time; no install needed (node present: $(have node && echo yes || echo NO))";;
    pmd)
      echo "manual: download release zip from pmd.github.io to ~/.local/share/code-audit/tools";;
    spotbugs|checkstyle|cppcheck|clang-tidy)
      echo "manual/system install needed for $t; recording as coverage gap is acceptable";;
    *) echo "unknown tool: $t";;
  esac
done
echo
echo "Ensure on PATH: $LOCALBIN, ~/go/bin, ~/.cargo/bin"
