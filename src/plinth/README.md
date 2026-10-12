# Plinth package documentation

Author and maintainer documentation lives in the project `docs/` directory at the repository root.

## Key documents

| Document | Purpose |
|----------|---------|
| [docs/README.md](../../docs/README.md) | Documentation index and reading order |
| [docs/quickstart.md](../../docs/quickstart.md) | First hermetic stage test in ≤30 minutes |
| [docs/stage_author_contract.md](../../docs/stage_author_contract.md) | Authoritative stage API (`StageIntent`, `StageOutcome`) |
| [docs/testing_recipe.md](../../docs/testing_recipe.md) | Hermetic stage tests without filesystem |
| [docs/stage_kinds.md](../../docs/stage_kinds.md) | Typical vs exceptional |
| [docs/internals.md](../../docs/internals.md) | How the engine is put together |
| [docs/expectation_matrix.md](../../docs/expectation_matrix.md) | User-expectation ↔ test coverage matrix |

## Quick start for stage authors

Application stages live in your application package — not in `plinth`. To create a typical stage:

1. Subclass `BaseStage`
2. Implement `get_intent() -> StageIntent`
3. Implement `process_file() -> StageOutcome`
4. Register with `@StageRegistry.register("stage_name", mode="typical")`

See [docs/stage_author_contract.md](../../docs/stage_author_contract.md) for the full contract.
