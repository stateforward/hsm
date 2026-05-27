# HSM Conformance Suite

This directory contains the shared behavioral conformance suite for all HSM language implementations.

The suite is data, not compiler output. Each language owns a runner that reads the same case JSON, builds a native model, executes the script, records a normalized trace, and compares that trace to the expected result embedded in the case.

```text
case JSON -> language runner -> native runtime -> actual trace == expected trace
```

`hsmc` may use this data as input in the future, but the conformance contract does not depend on `hsmc`.

## Case Format

A conformance case has these top-level sections:

- `model`: runtime-oriented HSM model IR.
- `behaviors`: portable behavior programs keyed by behavior ID.
- `instances`: optional named runtime instances for group/broadcast cases.
- `groups`: optional named groups of instances.
- `script`: ordered input steps.
- `expect`: expected final state, trace, attributes, or errors.
- `features`: optional labels a runner can use to skip unsupported feature groups.
- `mode`: `runtime` for executable cases or `validation` for invalid-model cases.

The schema lives at [schema/case.schema.json](schema/case.schema.json).

## Model IR

The model IR is runtime-oriented, not source-oriented. It intentionally omits source ranges, imports, host-language code, and compiler adapter metadata.

Names are slashless symbolic names. Paths in `initial`, `source`, and `target` are normalized by runners:

- `/Model/state` is an absolute state path.
- `state` is model-relative and resolves to `/Model/state` for ordinary transition targets.
- `parent/child` is model-relative and resolves to `/Model/parent/child`.
- `./child`, `../sibling`, and deeper parent paths are resolved relative to the containing state.
- Composite `initial` targets are resolved relative to the composite state they belong to.

Supported model fields:

- `name`: model name.
- `initial`: initial target path, or `{ "target": "...", "effects": [...] }` for compound initial effects.
- `attributes`: optional map of attribute names to `{ "type": "...", "default": ... }`.
- `operations`: optional map of operation names to behavior references.
- `states`: nested state declarations.
- `transitions`: root-owned transitions.

Supported state fields:

- `name`
- `kind`: `state`, `final`, `choice`, `shallow_history`, or `deep_history`; defaults to `state`.
- `initial`
- `entry`, `exit`, `activity`: ordered behavior references.
- `defer`: event names deferred while the state is active.
- `states`: nested states or pseudostates.
- `transitions`: ordered transitions.

Supported transition fields:

- `id`: optional transition identifier.
- `kind`: `external`, `internal`, `local`, or `self`; defaults to `external`.
- `source`: optional source path for parent-owned routing.
- `target`: optional target path.
- `on`: shorthand for `{ "trigger": { "kind": "on", "event": "..." } }`.
- `trigger`: explicit trigger object.
- `guard`: behavior reference that returns a boolean.
- `effects`: ordered behavior references.

Supported trigger kinds are `on`, `on_set`, `on_call`, `after`, `every`, `at`, `when`, and `completion`.

Timers use `duration_ms`, `time_ms`, `attribute`, or `behavior` depending on the case. Time values are runner-local deterministic logical milliseconds unless the case explicitly uses a real `sleep` step.

Event references can be plain event names or event objects with `name`, `data`, `id`, `source`, `target`, and `metadata`. Event metadata fields exist to test ownership/copy behavior; payload `data` remains application-owned unless a language documents stronger copy semantics.

Runners may skip cases whose `features` require runtime facilities they have not implemented yet, but they must fail clearly rather than silently changing semantics.

## Feature Coverage

The v1 IR can express every currently identified conformance area:

| Area | IR surface |
| --- | --- |
| Nested states and compound initial transitions | nested `states`, object-form `initial.effects` |
| Relative vs absolute path resolution | `initial`, `source`, `target` path normalization |
| Source-qualified parent transitions | transition `source` |
| Self/local/internal/external transitions | transition `kind` |
| Multiple transitions and selection order | ordered `transitions`, ordered `guard` behavior trace |
| Choice pseudostates | state `kind: "choice"` with ordered transitions |
| Shallow/deep history | state `kind: "shallow_history"` / `deep_history` |
| Final states and completion | state `kind: "final"`, trigger `kind: "completion"`, expect `done` |
| Deferral and replay | state `defer`, trace `defer` / `undefer`, expect `queue` |
| Activities and cancellation | `activity`, trace `activity_start` / `activity_cancel` / `activity_done` |
| `on_set`, `on_call`, `when` | trigger kinds plus script `set` / `call` |
| Timers `after`, `every`, `at` | trigger kinds plus `duration_ms`, `time_ms`, script `tick` |
| Event payload/data matching | event object `data`, behavior op `event_data_equals` |
| Event ownership/copy semantics | event object metadata, behavior ops `event_metadata_set` / `event_metadata_get` |
| Operation references | model `operations`, script/behavior op `call`, trigger `on_call` |
| Snapshots | script op `snapshot`, behavior op `snapshot`, expect `snapshots` |
| Groups/broadcast | top-level `instances`, `groups`, script `dispatch_all`, `dispatch_to`, `group_dispatch` |
| Error handling | expect `error`, trace `error` |
| Validation/invalid model cases | `mode: "validation"`, expect `validation` |
| Async behavior ordering | behavior ops `sleep` and `yield`, activity trace |
| Queue ordering/reentrancy | behavior op `dispatch`, trace/expect `queue` |
| Restart/stop/lifecycle edge cases | script ops `start`, `stop`, `restart`, trace lifecycle events |

## Runner Contract

A language runner must:

1. Read a case JSON file.
2. Validate at least the fields it uses.
3. Build the native model from `model`.
4. Bind each behavior ID to native callbacks that execute the portable behavior ops.
5. Execute `script` in order.
6. Record trace events in the same order and shape as `expect.trace`.
7. Compare the final state and trace locally.
8. Exit non-zero on mismatch.

Runners should not depend on source-language syntax, compiler source ranges, imports, or adapter metadata.

## Portable Behavior Ops

The portable behavior vocabulary is intentionally imperative and small enough for every language runner to implement without a general-purpose interpreter:

- `trace`: append `{ "type": "trace", "value": <value> }`.
- `set_attr`: set a model/instance attribute.
- `get_attr`: read an attribute for side-effect-free evaluation.
- `return_attr`: return an attribute value from a guard or trigger expression.
- `return_value`: return a literal value.
- `return_equals`: return whether an attribute equals a literal value.
- `event_name_equals`: return whether the current event name equals `value`.
- `event_data_equals`: return whether the current event data, or data at `path`, equals `value`.
- `event_data_get`: return current event data, or data at `path`.
- `event_metadata_set`: mutate current event metadata for event ownership tests.
- `event_metadata_get`: read current event metadata.
- `raise`: raise/send an internal event if the runtime supports it.
- `dispatch`: dispatch an event from inside behavior for queue/reentrancy tests.
- `call`: invoke a named operation.
- `snapshot`: append or return a normalized snapshot.
- `sleep`: await logical or real milliseconds.
- `yield`: yield once to the scheduler.

New ops should be added only when at least one shared case needs them.

## Trace Events

Trace events are normalized JSON objects. The initial core event types are:

- `trace`
- `start`
- `stop`
- `restart`
- `dispatch`
- `select`
- `guard`
- `exit`
- `effect`
- `enter`
- `activity_start`
- `activity_cancel`
- `activity_done`
- `defer`
- `undefer`
- `raise`
- `call`
- `set`
- `timer_scheduled`
- `timer_cancelled`
- `timer_fired`
- `snapshot`
- `stable`
- `done`
- `error`

Cases can use behavior `trace` ops to make entry, exit, effect, guard, and activity ordering observable without requiring runtimes to expose private internals.

## Cases

<!-- conformance case files in conformance/cases -->

- [activity_cancel.json](cases/activity_cancel.json): activity start and cancellation on exit.
- [async_ordering.json](cases/async_ordering.json): yielded async behavior preserves deterministic ordering.
- [basic_transition.json](cases/basic_transition.json): initial entry, dispatch, exit, effect, entry, and final stable state.
- [broadcast_dispatch.json](cases/broadcast_dispatch.json): context-wide dispatch to all instances.
- [choice_no_fallback_validation.json](cases/choice_no_fallback_validation.json): validation-mode choice without fallback.
- [choice_order.json](cases/choice_order.json): choice guard order and fallback routing.
- [completion_nested.json](cases/completion_nested.json): nested final triggers parent completion.
- [defer_order_multiple.json](cases/defer_order_multiple.json): multiple deferred events replay FIFO.
- [defer_replay.json](cases/defer_replay.json): deferred event replay after exit.
- [error_behavior.json](cases/error_behavior.json): behavior error produces normalized error expectation.
- [event_ownership.json](cases/event_ownership.json): event metadata mutation isolation across recipients.
- [event_payload_guard.json](cases/event_payload_guard.json): guard reads structured event data.
- [final_completion.json](cases/final_completion.json): final state and completion transition.
- [group_dispatch.json](cases/group_dispatch.json): group dispatch reaches all members.
- [group_snapshot.json](cases/group_snapshot.json): group snapshot reports member states.
- [guard_attribute.json](cases/guard_attribute.json): attribute default, script `set`, guard false/true ordering, and guarded transition.
- [history_deep.json](cases/history_deep.json): deep history restores nested leaf.
- [history_default.json](cases/history_default.json): history default target with no recorded state.
- [history_shallow.json](cases/history_shallow.json): shallow history restores last direct child.
- [invalid_final.json](cases/invalid_final.json): validation-mode final state with outgoing transition.
- [invalid_model_names.json](cases/invalid_model_names.json): validation-mode invalid slashful names.
- [invalid_targets.json](cases/invalid_targets.json): validation-mode missing targets.
- [nested_initial.json](cases/nested_initial.json): nested composite initial entry order.
- [on_call.json](cases/on_call.json): operation call trigger.
- [on_set.json](cases/on_set.json): attribute set trigger.
- [operation_reference.json](cases/operation_reference.json): operation references from entry, guard, and effect.
- [path_resolution.json](cases/path_resolution.json): absolute, model-relative, and nested targets.
- [queue_reentrancy.json](cases/queue_reentrancy.json): nested dispatch queue ordering.
- [restart_lifecycle.json](cases/restart_lifecycle.json): start, stop, restart lifecycle ordering.
- [snapshot.json](cases/snapshot.json): snapshot state, attributes, and queue length.
- [source_qualified_parent_transition.json](cases/source_qualified_parent_transition.json): parent-owned transition with child source.
- [timer_after.json](cases/timer_after.json): one-shot timeout.
- [timer_at.json](cases/timer_at.json): absolute timepoint trigger.
- [timer_cancel_on_exit.json](cases/timer_cancel_on_exit.json): timer cancellation when source state exits.
- [timer_every.json](cases/timer_every.json): repeated interval trigger.
- [transition_kinds.json](cases/transition_kinds.json): external, internal, local, and self transition semantics.
- [transition_selection_order.json](cases/transition_selection_order.json): multiple same-event transitions select first passing guard.
- [when.json](cases/when.json): predicate/condition trigger.

## Python Runner

The first runner is [runners/python/run_case.py](runners/python/run_case.py). From the repo root:

```sh
PYTHONPATH=hsm.py python3 conformance/runners/python/run_case.py conformance/cases/basic_transition.json
```

The Python runner exits `77` when all failures are explicit unsupported-feature skips. It currently executes all checked-in conformance cases against `hsm.py`; a zero exit means every case matched its expected trace and final state.
