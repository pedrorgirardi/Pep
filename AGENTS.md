# AGENTS.md

## Purpose
This repository is a Sublime Text plugin (`Pep`) that uses `clj-kondo` analysis data to power Clojure/ClojureScript navigation, documentation, usage search, highlighting, and lint annotations.

## Tech and Runtime
- Language: Python (Sublime Text plugin API)
- Host runtime: Sublime Text (plugin-loaded lifecycle)
- External dependency: `clj-kondo` executable available on `PATH` (or configured via `clj_kondo_path`)
- Main code: `pep.py`
- Progress UI helper: `plugin/progress.py`

## Core Architecture
- `pep.py` contains almost all logic: settings, indexing, analysis, UI commands, event listeners, and plugin lifecycle.
- Analysis is split into three scopes:
  - View analysis (`analyze_view`) from buffer text via stdin.
  - Project paths analysis (`analyze_paths`) from configured project paths.
  - Classpath analysis (`analyze_classpath`) from configured project classpath command.
- In-memory stores:
  - `_view_analysis_`: per-view analysis/indexes.
  - `_index_`: project path index by filename/semantic.
  - `_classpath_analysis_`: classpath-only index data.
- Index builders (`namespace_index`, `var_index`, `keyword_index`, `symbol_index`, `local_index`, `java_class_index`) normalize clj-kondo output into lookup-optimized maps.

## Important Files
- `pep.py`: plugin implementation.
- `Pep.sublime-settings`: default settings.
- `Default.sublime-commands`: command palette entries.
- `Main.sublime-menu`: menu integration.
- `tests/test_pep.py`: Sublime-hosted tests.
- `README.md`: user-facing docs and settings.
- `CHANGELOG.md`: release notes.

## Project Configuration Expectations
Pep expects project-level config in `*.sublime-project` under `"pep"`, especially:
- `"paths"`: list of source directories.
- `"classpath"`: command string/list that resolves to classpath (`clojure -Spath` commonly).

Example:
```json
{
  "pep": {
    "paths": ["src"],
    "classpath": "clojure -Spath"
  }
}
```

## Agent Workflow Guidance
When making changes, follow this order:
1. Read relevant functions in `pep.py` and keep behavior aligned with existing command names (`pg_pep_*`).
2. If command surface changes, update command/menu docs in:
   - `Default.sublime-commands`
   - `Main.sublime-menu`
   - `README.md` command table (if user-facing behavior changed)
3. If settings change, update:
   - `Pep.sublime-settings`
   - `README.md` settings section
4. Add/update `CHANGELOG.md` when behavior changes.

## Concurrency and UI Constraints
- Keep expensive work off UI callbacks. Use existing async wrappers (`*_async`) and timer-based throttling patterns.
- `PgPepViewListener` already debounces `on_modified_async` via `analysis_delay`; preserve this behavior.
- Do not introduce blocking subprocess calls directly in hot UI paths.

## clj-kondo Integration Rules
- Use `clj_kondo_path(window)` (which resolves via `shutil.which`) instead of hardcoding executable paths.
- Preserve subprocess `cwd` semantics. Cache/index correctness depends on project/file working directory.
- Paths/classpath analysis requires `.clj-kondo` cache directory creation; keep this logic intact.
- Handle JSON parse failures defensively (current code falls back to `{}`).

## Index/Data Integrity Rules
- Prefer extending existing index helper functions over ad-hoc index maps.
- Preserve row/column conventions expected by region conversion helpers (`thingy_to_region`, etc.).
- When changing analysis schemas, audit all consumers:
  - goto commands
  - highlight/select/replace flows
  - quick panel item builders
  - find usages/definitions

## Testing and Validation
- Automated tests in `tests/test_pep.py` are Sublime-hosted and rely on Sublime APIs (`sublime`, scratch views, windows).
- Run tests in a Sublime + UnitTesting environment, not plain `python`.
- Manual validation checklist after behavior changes:
  - Open a Clojure file and confirm automatic analysis runs.
  - Run `Pep: Analyze` and inspect output/errors.
  - Verify `Goto Definition`, `Find Usages`, `Show Documentation`, and `Highlight` on symbols/keywords.
  - Confirm project `paths` and `classpath` analysis flows still populate navigation across files/libs.

## Known Gaps / Caution
- `pep.py` is intentionally monolithic; minimize broad refactors unless requested.
- Tests may lag behind implementation details in active development branches; treat test updates as part of behavior changes.
- Some commands and settings are tightly coupled to syntax filters (`analysis_applicable_to`); verify applicability when adding features.

## Definition of Done for Agent Changes
- Code change implemented in `pep.py` (or companion file) with no obvious regressions in command behavior.
- Related settings/docs/menu/command metadata updated when applicable.
- Validation performed (automated in Sublime test harness and/or manual steps), with explicit note of what was run.
