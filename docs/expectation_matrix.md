# Plinth expectation matrix

Master checklist: every user-visible pipeline expectation must have a positive proof (does the right thing) and a negative proof (rejects the wrong thing). Enforced by `scripts/validate_expectation_matrix.py`.

| ID | Expectation | Contract | Positive test | Negative test |
|----|-------------|----------|---------------|---------------|
| E01 | Stages return typed `StageOutcome` only | stage_author_contract §StageOutcome | tests/invariants/test_stage_outcome_surface.py | tests/invariants/test_dict_return_rejection.py |
| E02 | Only stages registered as exceptional may replace `execute()` | stage_author_contract §Typical stage shape | tests/invariants/test_recipe_demo.py | tests/invariants/test_undeclared_execute_override.py |
| E03 | Required manifest columns enforced before run | stage_author_contract §StageIntent | tests/invariants/test_intent_conformance.py | tests/invariants/test_wrong_stage_intent.py |
| E04 | Row failure default is fail-fast | stage_author_contract §Row failure policy | tests/invariants/test_row_failure_policy.py | tests/invariants/test_partial_dataset_guard.py |
| E05 | Opt-in partial success with max_dropped_rows cap | stage_author_contract §StageIntent | tests/invariants/test_row_failure_policy.py | tests/invariants/test_row_failure_policy.py |
| E06 | Column-update stages merge manifest in place | internals §Manifest replace truth table | tests/invariants/test_live_manifest_propagation.py | tests/invariants/test_manifest_policy.py |
| E07 | Filter/expand/aggregate replace manifest | internals §Manifest replace truth table | tests/invariants/test_live_manifest_propagation.py | tests/invariants/test_manifest_policy.py |
| E08 | `modifies_files=False` propagates files by reference | stage_author_contract §Propagation | tests/invariants/test_live_manifest_propagation.py | tests/invariants/test_stage_shapes_in_memory.py |
| E09 | `modifies_files=True` copies files into stage tree | stage_author_contract §Propagation | tests/invariants/test_live_manifest_propagation.py | tests/invariants/test_stage_shapes_in_memory.py |
| E10 | Parallel branches are independent with deterministic serial execution | stage_author_contract §Parallel blocks | tests/invariants/test_parallel_fail_fast.py | tests/invariants/test_parallel_continue_policy.py |
| E11 | Parallel fail-fast aborts block on first branch failure | internals §Failure policies | tests/invariants/test_parallel_fail_fast.py | tests/invariants/test_parallel_continue_policy.py |
| E12 | Parallel write-column conflicts rejected at config time | stage_author_contract §Parallel blocks | tests/invariants/test_config_validation.py | tests/invariants/test_config_validation.py |
| E13 | Parallel unique-key mutation rejected at runtime | block_executors | tests/invariants/test_adversarial_corpus.py | tests/invariants/test_adversarial_corpus.py |
| E14 | Exceptional stages satisfy runtime obligations | stage_author_contract §Exceptional | tests/invariants/test_exceptional_runtime_obligations.py | tests/invariants/test_exceptional_runtime_obligations.py |
| E15 | Ledger writes only via `LedgerWriter` | internals §Data ownership | tests/invariants/test_data_ownership.py | tests/invariants/test_data_ownership.py |
| E16 | Hash chain contiguity validated post-run | internals §Provenance hashes | tests/invariants/test_hash_chain_validator.py | tests/invariants/test_hash_chain_validator.py |
| E17 | Address resolver is sole path authority | internals §Address authority | tests/invariants/test_address_consumer_agreement.py | tests/invariants/test_address_resolver.py |
| E18 | Skip/resume JSONPath matches resolver output | stage_author_contract §JSONPath | tests/invariants/test_address_consumer_agreement.py | tests/invariants/test_cleanup_end_at.py |
| E19 | Resume from stage preserves upstream manifests | resume_policy | tests/invariants/test_resume_idempotency.py | tests/invariants/test_resume_idempotency.py |
| E20 | Full run ≡ resume-from-k for golden tiers | metamorphic | tests/metamorphic/test_run_equivalences.py | tests/metamorphic/test_run_equivalences.py |
| E21 | `end_at_stage` stops before downstream nodes | pipeline.run | tests/invariants/test_cleanup_end_at.py | tests/invariants/test_cleanup_end_at.py |
| E22 | Cleanup refuse-delete for unparseable dirs | internals §Propagation and resume | tests/invariants/test_cleanup_refuse_delete.py | tests/invariants/test_cleanup_refuse_delete.py |
| E23 | Golden pipeline equivalence (GT1–GT10) | golden README §Equivalence rules | tests/golden/test_pipeline_equivalence.py | tests/golden/test_pipeline_equivalence.py |
| E24 | Hermetic stage recipe (filter/expand/aggregate/group) | testing_recipe | tests/invariants/test_stage_shapes_in_memory.py | tests/invariants/test_stage_shapes_in_memory.py |
| E25 | Library import boundary (no domain stages) | public_api | tests/adoption/test_import_smoke.py | tests/invariants/test_import_boundary.py |
| E26 | Export copies stage tree to experiment export/ | stage_author_contract §Export | tests/invariants/test_export_typical.py | tests/invariants/test_export_typical.py |
| E27 | Empty manifest handoff fails clearly | adversarial | tests/invariants/test_adversarial_corpus.py | tests/invariants/test_adversarial_corpus.py |
| E28 | Duplicate unique keys after expand rejected | adversarial | tests/invariants/test_adversarial_corpus.py | tests/invariants/test_adversarial_corpus.py |
| E29 | Corrupt ledger fails hash-chain validation | adversarial | tests/invariants/test_adversarial_corpus.py | tests/invariants/test_adversarial_corpus.py |
| E30 | Parallel join schema mismatch fails | adversarial | tests/invariants/test_adversarial_corpus.py | tests/invariants/test_adversarial_corpus.py |
| E31 | Attributed errors cite contract section | stage_author_contract (section named in each error) | tests/invariants/test_attributed_errors.py | tests/invariants/test_attributed_errors.py |
| E32 | Deep nested DAG addressing | golden GT6 | tests/golden/test_pipeline_equivalence.py | tests/invariants/test_address_consumer_agreement.py |
| E33 | Expand→aggregate structural chain | golden GT7 | tests/golden/test_pipeline_equivalence.py | tests/invariants/test_stage_shapes_in_memory.py |
| E34 | Resume mid-DAG golden snapshot | golden GT8 | tests/golden/test_pipeline_equivalence.py | tests/invariants/test_resume_idempotency.py |
| E35 | Address resolver property: execute ≡ cleanup | property | tests/invariants/test_address_resolver_properties.py | tests/property/test_address_resolver_hypothesis.py |
| E36 | Launcher run matches Pipeline output | metamorphic launcher | tests/metamorphic/test_launcher_pipeline_parity.py | tests/metamorphic/test_run_equivalences.py |
| E37 | Filesystem modifies_files copies files | internals §Propagation and resume | tests/invariants/test_filesystem_propagation.py | tests/invariants/test_live_manifest_propagation.py |
| E38 | Multi-input parallel join merge | internals §Propagation and resume | tests/invariants/test_filesystem_propagation.py | tests/invariants/test_adversarial_corpus.py |
| E39 | Nested parallel resume snapshots | resume_policy | tests/invariants/test_resume_policy_snapshots.py | tests/invariants/test_resume_idempotency.py |
| E40 | always_propagate copies when no file write | propagation | tests/invariants/test_always_propagate.py | tests/invariants/test_always_propagate.py |
| E41 | aggregate_outputs false keeps branch dirs | block_settings | tests/invariants/test_aggregate_outputs_policy.py | tests/invariants/test_aggregate_outputs_policy.py |
| E42 | end_at_paths config matches API cut | pipeline.run | tests/invariants/test_config_end_at_paths.py | tests/invariants/test_config_end_at_paths.py |
| E43 | continue policy breaks downstream lineage | stage_author_contract §Parallel blocks | tests/invariants/test_parallel_continue_lineage.py | tests/invariants/test_parallel_continue_policy.py |
| E44 | On-disk truncated ledger fails | adversarial disk | tests/invariants/test_filesystem_adversarial.py | tests/invariants/test_adversarial_corpus.py |
| E45 | Intent/outcome fuzz fail-fast invariants | property fuzz | tests/property/test_intent_outcome_fuzz.py | tests/invariants/test_partial_dataset_guard.py |
| E46 | Invalid JSONPath index fails at resolution | stage_author_contract §JSONPath skip and resume | tests/invariants/test_config_end_at_paths.py | tests/invariants/test_cleanup_end_at.py |
| E47 | Resume rejects upstream param drift | resume_policy | tests/invariants/test_resume_idempotency.py | tests/invariants/test_resume_recovery.py |
| E48 | Failed run resume and re-run idempotency | resume_policy | tests/invariants/test_resume_recovery.py | tests/invariants/test_resume_recovery.py |
| E49 | Export artifacts land in export/ tree | export_engine | tests/invariants/test_export_typical.py | tests/invariants/test_export_typical.py |
| E50 | `CoreManifestRow` documents core keys; no runtime row validation | stage_author_contract §Manifest row protocol | tests/typing/test_row_types.py | tests/typing/test_row_types.py |
| E51 | `plinth.testing` import surface matches the public API | public_api | tests/adoption/test_import_smoke.py | tests/invariants/test_import_boundary.py |
| E53 | `ManifestIdentity` normalizes declared aliases to `entity_id` | stage_author_contract §Manifest row protocol | tests/invariants/test_entity_identity.py | tests/invariants/test_entity_identity.py |
| E54 | Flow arming skips disarmed parallel branches; resume rejects arming drift | internals §Flow control | tests/invariants/test_flow_arming.py | tests/invariants/test_flow_arming.py |
| E55 | `dataset_schema.yaml` is written with every field explicit and `schema_format: 1`; files without `schema_format`, or with another format, are rejected | stage_author_contract §Dataset schema | tests/invariants/test_schema_format.py | tests/invariants/test_schema_format.py |
| E56 | Default identity is flat (no injected hierarchy columns); hierarchies and key rules apply only when declared | stage_author_contract §Dataset schema | tests/invariants/test_entity_identity.py | tests/invariants/test_entity_identity.py |
