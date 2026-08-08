# RNA — Indexing & Caching

## 1. Principle: on-demand, never eager

RNA never runs a mandatory "index the whole repo first" pass. The very first call a session ever makes — even on a repo RNA has never seen — should return an answer, computed for exactly the scope that call needs, nothing more. This is a deliberate rejection of the "build a full repo map before doing anything useful" pattern: it keeps RNA usable on huge monorepos where a full whole-program call graph could take minutes, and keeps cold-start latency proportional to the question asked, not to repo size.

The corollary: **the same underlying computation is shared across methods.** `get_symbol("Foo")` on module `a.py` builds and caches a Tier 1 symbol index for `a.py`; a later `get_callers("Foo.bar")` reuses that same per-file index rather than rebuilding it. Nothing is computed twice for the same `(file, tool, tool_version)` triple within a cache's lifetime.

---

## 2. Two cache layers

```text
Call --> L1 (in-memory LRU, per process)  --> hit: return immediately
              |
              miss
              v
          L2 (on-disk, .rna_cache/, persists across sessions) --> hit: promote to L1, return
              |
              miss
              v
          Compute (Tier 1/2/3, per 01_architecture.md request lifecycle)
              |
              v
          Write to L2, promote to L1, return
```

- **L1 (in-memory LRU):** fast path for repeated calls within one agent session (e.g. an agent calling `get_file` on the same file several times while iterating). Bounded by entry count, not size, to keep behavior predictable.
- **L2 (on-disk, `<repo_root>/.rna_cache/`):** survives process restarts. Two agent sessions against the same repo on the same machine, minutes or days apart, share this cache. Structured as a manifest (SQLite) mapping cache keys to either inline small values or references to blob files (for large results — e.g. a whole-program `LLDModel` for a big module).

Cache keys are always a tuple of:

```text
(repo_fingerprint, subject_hash, method_name, params_hash, tool_name, tool_version)
```

- `repo_fingerprint` — current git commit SHA if the tree is clean; a hash of `git status --porcelain` plus content hashes of dirty files if not. This means a call made against a dirty working tree caches correctly without needing a commit, and is invalidated the instant those specific files change again.
- `subject_hash` — content hash of the specific file(s)/scope the call concerns (not the whole repo) — most calls only care about a handful of files, so cache invalidation is per-file-granular, not per-commit-granular.
- `tool_version` — e.g. the installed `pyan3` version string. If a developer upgrades a Tier 3 tool, stale results are never served silently.

---

## 3. Invalidation

RNA never guesses staleness from a wall-clock TTL for anything derived from repository content (the one deliberate exception is `google_search`, whose answer concerns the outside world, not this repository — see §14 in `02_api_spec.md`, cached with a 24h TTL instead).

| Trigger | What gets invalidated |
|---|---|
| A tracked file changes (content hash differs from the cached `subject_hash`) | Every cache entry whose `subject_hash` derives from that file: its own symbol index, any import/call graph edge referencing it, any `LLDModel`/`HLDModel` that included it, any embedding chunk belonging to it |
| A file is deleted | Same as above, plus the file is dropped from `get_files_with_name` results and the import/call graph |
| A new file is added | No invalidation needed (nothing referenced it yet); it is indexed lazily the first time a call needs it |
| A Tier 2/3 tool is upgraded (version string changes) | Every cache entry keyed with the old `tool_version` for that tool becomes an automatic miss (no explicit purge needed — the key itself changed) |
| Explicit `rna.invalidate(path)` / `rna.invalidate_all()` | For host applications that already know a file changed outside RNA's view (e.g. an editor applied a patch) and want to force freshness immediately rather than wait for the next content-hash check |

Invalidation is computed incrementally against the previous `repo_fingerprint`, not recomputed from scratch: RNA runs a git diff (or, for dirty trees, a targeted `stat`+hash check limited to previously-seen files) between the last known fingerprint and the current one, and only touches cache entries for files that actually appear in that diff.

---

## 4. Performance budgets

| Method | Cold (uncached) target | Warm (cached) target | Notes |
|---|---|---|---|
| `get_file` | < 10 ms | < 1 ms | Bounded by OS I/O only |
| `get_files_with_name` | < 50 ms (mid-size repo) | < 5 ms | Tree walk is cached; invalidated incrementally on filesystem change |
| `get_symbol` (Tier 1) | < 100 ms | < 5 ms | Single-file parse |
| `get_symbol` (Tier 2) | < 300 ms (server already warm) | < 5 ms | First call in a session pays LSP server startup separately (a few seconds), amortized across the session |
| `search` | < 200 ms (repo-wide, ripgrep) | n/a (not cached) | Ripgrep is already fast enough that caching adds more complexity than value |
| `get_callers` (Tier 2) | < 500 ms | < 5 ms | |
| `get_import_graph` (repo-wide, Tier 1) | < 2 s (large repo) | < 10 ms | Dominant cost is parsing every file once; fully incremental after that |
| `get_tests` | < 1 s | < 10 ms | Git log scan is the dominant cost on first call |
| `get_workflow` | < 2 s (depth 4, moderate fan-out) | < 10 ms | Hard server-side depth cap (6) prevents runaway BFS regardless of requested `max_depth` |
| `get_hld` | < 10 s (large repo, first call) | < 20 ms | Acceptable because this is an intentionally rare, high-value call, not a per-step operation |
| `get_lld` (Tier 3, single module) | < 5 s | < 20 ms | Dominated by external tool subprocess startup + analysis |
| `semantic_search` | first-ever query on a fresh repo pays full index build (proportional to repo size, minutes on very large repos) | < 50 ms | See §5 for the warm-up escape hatch |
| `google_search` | < 1 s (network) | < 5 ms (24h TTL) | Bound by provider rate limits, not RNA |

Any Tier 2/3 subprocess call exceeding **2x** its budget is treated as a timeout and degrades one tier for that call (§6 in `01_architecture.md`) rather than blocking the caller indefinitely.

---

## 5. Optional warm-up

`semantic_search`'s first-ever index build is the one operation whose cold cost scales with the whole repo rather than with the scope of a single question — because a useful embedding index genuinely needs to see the whole corpus at least once. For this reason (and only this one), RNA offers an explicit, opt-in warm-up:

```bash
rna warm --repo . --only embeddings
```

This is a background job, not a requirement: an agent can call `semantic_search` immediately on a cold repo and get a correct (if slower, one-time) answer; `rna warm` exists purely to move that one-time cost out of the critical path of a live agent session (e.g. run it once when a repo is first onboarded, or nightly in CI). It never runs automatically and is never implied by any other `rna.*` call — consistent with the "on-demand, not eager" principle in §1.

---

## 6. Storage layout

```text
<repo_root>/.rna_cache/
  manifest.sqlite          # cache key -> {inline value | blob ref, tool_version, written_at}
  blobs/
    <sha256>.json            # large results (LLDModel/HLDModel for big scopes, whole-program graphs)
  embeddings/
    vectors.faiss             # (or the configured local vector store's native format)
    chunks.sqlite               # chunk_id -> {file, start_line, end_line, content_hash}
  web/
    responses.sqlite            # query_hash -> {results, fetched_at} with TTL enforcement
```

`.rna_cache/` is added to the host repo's ignore rules by default (RNA writes a `.gitignore` entry into the directory itself on first use, the same technique `.pytest_cache/` and `.ruff_cache/` already use in this project) — it is disposable, machine-local, and safe to delete at any time; RNA rebuilds anything missing from it lazily, on demand, per §1.
