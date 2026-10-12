# Releasing

Steps for maintainers cutting a release.

1. Run everything CI runs, on every supported Python version:

   ```bash
   ruff check src/plinth tests/ scripts/ examples/
   mypy src/plinth tests/typing --follow-imports=silent
   lint-imports
   python scripts/validate_pipeline_configs.py
   python scripts/validate_public_surface.py
   python scripts/validate_ledger_write_sites.py
   python scripts/validate_expectation_matrix.py --check-scenarios
   pytest tests/ -q
   ```

2. If engine output changed on purpose, re-capture the golden snapshots and review the diff:

   ```bash
   python scripts/capture_golden_pipeline.py   # input dataset + GT1
   python scripts/capture_golden_tiers.py      # GT2–GT10
   ```

3. Bump `__version__` in `src/plinth/version.py`, and the `Version:` header of
   [stage_author_contract.md](stage_author_contract.md) if the author surface changed.
4. Move the **Unreleased** notes in [CHANGELOG.md](../CHANGELOG.md) under the new version.
5. Tag `vX.Y.Z` on the release commit and push the tag.
