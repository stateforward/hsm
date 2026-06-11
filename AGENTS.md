# Monorepo Agent Instructions

- ALWAYS keep it stupid simple.
- ALWAYS check for existing code before writing new code.
- NEVER add new dependencies without asking.
- NEVER add unnecssary functions for one-off tasks.
- NEVER add fields to classes without permission.

This repository contains multiple language implementations of the same HSM DSL/runtime.

## Scope rules

- When working anywhere in this repository, check for a nearer `AGENTS.md` in the target package or subdirectory.
- The nearest `AGENTS.md` is authoritative for that subtree and may add stricter rules than this file.
- If both the repo root and a submodule/package `AGENTS.md` apply, follow both. On conflict, follow the more specific file.

## Submodule/package guidance

- `hsm.ts` has package-specific implementation rules in [hsm.ts/AGENTS.md](/Users/gabrielwillen/VSCode/stateforward/hsm/hsm/hsm.ts/AGENTS.md).
- Language implementations may use other submodules as behavioral references, but not as architecture excuses. Do not assume one implementation’s shortcuts are acceptable in another.

## General expectations

- Preserve cross-language parity intentionally. If a package deviates from `dsl.md` or sibling implementations, make that deviation explicit.
- Prefer native implementation quality in each language over façade-only compatibility work.
- Do not hide runtime design debt behind declaration files, generated wrappers, or package-entry indirection.
