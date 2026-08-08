# Optional tools that unlock RNA tiers

RNA always works with **Tier 1 (tree-sitter)** alone. Install any of the tools below to upgrade precision.

| Language | Tier 2 (LSP) | Tier 3 (whole-program) | Unlocks |
|---|---|---|---|
| Python | `pylsp` or `pyright-langserver` | `pyan3`, `pyreverse` (`pylint`), optional `pycg` | precise `get_symbol`/`get_callers`, rich `get_lld` |
| JavaScript / TypeScript | `typescript-language-server` | `madge`, `dependency-cruiser`, `ts-morph` | import graphs, LLD |
| Go | `gopls` | `callgraph` / `go-callgraph` | precise callers, LLD |
| C / C++ | `clangd` (+ `compile_commands.json`) | `cscope`, `universal-ctags` | callers / symbols |
| Rust | `rust-analyzer` | — | precise symbol/callers |
| Java | `jdtls` | — | precise symbol/callers |

Lexical search prefers `rg` (ripgrep) on `PATH`; otherwise falls back to Python `re`.

Python extras:

```bash
pip install 'neutrino-cli[rna-python-lld]'
pip install 'neutrino-cli[rna-embeddings]'
pip install 'neutrino-cli[rna-web]'
```
