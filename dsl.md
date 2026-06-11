# HSM DSL — Domain-Specific Language Reference

Complete reference for the Domain-Specific Language (DSL) of the hierarchical state machine library.

All DSL functions are **namespace/module-level functions** (not methods on objects), enabling model construction and validation at compile time.

> **Notation:** `hsm.FunctionName(...)` represents a function in the `hsm` namespace/module. These are free functions, not instance methods.

> **Naming convention:** All canonical exported DSL and runtime API functions use **PascalCase**. This choice is intentional, even though it conflicts with some language-specific style guides. PascalCase is the *only* casing convention that is consistently supported across **all major languages** for **both namespace-level functions and object methods**, without ambiguity or special rules. This ensures the DSL can be mapped 1:1 into C, C++, Rust, Go, C#, Java, Python, JavaScript, and scripting bindings while preserving identical API names and documentation. Implementations may also expose language-native aliases, such as TypeScript's camelCase aliases or Python's snake_case aliases (`Define` -> `define`, `OnSet` -> `on_set`, `TakeSnapshot` -> `take_snapshot`, `MakeGroup` -> `make_group`, `DefaultClock` -> `default_clock`, `StateKind` -> `state_kind`, `CompletionEvent` -> `completion_event`, `Config(ID=..., Clock=..., Queue=...)` -> `Config(id=..., clock=..., queue=...)`), but those aliases must map directly to the canonical PascalCase API and must not introduce separate behavior.

---

## Table of Contents

1. [Model Definition](#model-definition)
2. [State Declaration](#state-declaration)
3. [Submachine Composition](#submachine-composition)
4. [Pseudostates](#pseudostates)
5. [Transitions](#transitions)
6. [Event Triggers](#event-triggers)
7. [Timing Events](#timing-events)
8. [Transition Targets & Routing](#transition-targets--routing)
9. [State Behaviors](#state-behaviors)
10. [Guards & Deferral](#guards--deferral)
11. [Model Metadata](#model-metadata)
12. [Group Operations](#group-operations)
13. [Type Utilities](#type-utilities)
14. [Runtime Attribute Access](#runtime-attribute-access)
15. [Runtime Configuration](#runtime-configuration)
16. [Snapshotting](#snapshotting)
17. [Runtime Constants](#runtime-constants)

---

## Model Definition

### `hsm.Define(name, partials...)`

Declares a hierarchical state machine model with a name and zero or more child elements.

**Parameters:**

* `name` Model name. Cannot contain the character `/`.
* `partials...` Zero or more state/initial/transition/operation/attribute/group declarations.

**Constraints:**

* Model names must not contain `/`.
* Compile-time function.

**Description:**
The top-level DSL entry point for constructing a state machine. Accepts a name and any combination of states, initial transitions, attributes, and operations to build the model structure.

---

## State Declaration

> **Design note (parallel regions):** UML-style parallel/orthogonal regions are intentionally **not supported**. Parallel behavior must be modeled explicitly using **submachines** (independent child state machines) composed within a parent state machine. This avoids implicit concurrency semantics, simplifies execution guarantees, and keeps scheduling, ordering, and resource usage explicit and deterministic.

### `hsm.State(name, partials...)`

Declares a composite or basic state within the state machine hierarchy.

**Parameters:**

* `name` State name. Cannot contain `/`.
* `partials...` Entry/exit/activity actions, transitions, nested states.

**Constraints:**

* State names must not contain `/`.
* Compile-time function.

**Description:**
Defines a named state in the hierarchy. Can contain nested substates, transitions, and behavioral actions.

### `hsm.Final(name)`

Declares a UML final state: an absorbing state with no outgoing transitions.

**Parameters:**

* `name` Final state name. Cannot contain `/`.

**Constraints:**

* Final state names must not contain `/`.
* Compile-time function.

**Description:**
Represents a terminal state indicating the completion of a region or the entire state machine.

---

## Submachine Composition

### `hsm.SubmachineState(name, machine, partials...)`

Declares a state whose active behavior is provided by a referenced state machine model.

**Parameters:**

* `name` Submachine state name. Cannot contain `/`.
* `machine` A statically defined `hsm.Define(...)` model reference.
* `partials...` Entry/exit/activity actions, transitions, deferral, and other state-level declarations for the containing state boundary.

**Constraints:**

* Submachine state names must not contain `/`.
* `machine` must refer to a complete, valid state machine model.
* A submachine state must not directly contain nested `hsm.State(...)`, `hsm.Initial(...)`, `hsm.Final(...)`, or pseudostate declarations.
* Parent transitions must not target arbitrary internal states of the child machine; they must enter through the child machine's default initial transition or a declared `hsm.EntryPoint(...)`.
* Compile-time function.

**Description:**
Represents a reusable state machine as a state in another state machine. Entering the submachine state activates the referenced child machine. Exiting the submachine state exits the active child configuration before executing the submachine state's exit behavior.

While a `SubmachineState` is active, incoming events are evaluated using the same bottom-up transition selection used for ordinary hierarchical states. Selection begins at the deepest active state of the child machine. If no enabled transition is found in the child machine, selection continues at the containing `SubmachineState` and then outward through the parent hierarchy. A selected child transition does not exit the containing `SubmachineState` unless the child reaches a `Final` state or an `hsm.ExitPoint(...)`.

If a transition targets a `SubmachineState` directly, the child machine enters through its normal `hsm.Initial(...)` transition. If a transition targets one of the child machine's `hsm.EntryPoint(...)` declarations, the child machine enters through that named entry point.

### `hsm.EntryPoint(name, partials...)`

Declares a named public entry point for a state machine model.

**Parameters:**

* `name` Entry point name. Cannot contain `/`.
* `partials...` Target path and optional effect action.

**Constraints:**

* Entry point names must not contain `/`.
* Must include a target.
* Target must resolve to a state or supported pseudostate inside the declaring machine.
* Entry points are valid transition targets only from outside the declaring machine through a containing `hsm.SubmachineState(...)`.
* Compile-time function.

**Description:**
Defines a public boundary through which a parent machine may enter a child machine without targeting the child machine's internal states directly. Entry points preserve submachine encapsulation while allowing a reusable child machine to expose multiple well-defined entry routes.

When used as a transition partial with no target partials, `hsm.EntryPoint(name)` selects the named child entry point for a transition whose target is a `hsm.SubmachineState(...)`. In that context, the entry point name must resolve in the target submachine's referenced model.

### `hsm.ExitPoint(name, partials...)`

Declares a named public exit point for a state machine model.

**Parameters:**

* `name` Exit point name. Cannot contain `/`.
* `partials...` Optional effect action.

**Constraints:**

* Exit point names must not contain `/`.
* Exit points may be targeted only by transitions inside the declaring machine.
* Reaching an exit point exits the child machine through that named boundary and returns transition selection to the containing `hsm.SubmachineState(...)`.
* Compile-time function.

**Description:**
Defines a public boundary through which a child machine may complete with a named outcome. When an active child machine reaches an exit point, the containing submachine state handles the exit-point outcome as part of normal run-to-completion processing. Parent transitions may use the named exit point to decide the next parent state without the child machine directly targeting parent states.

When used as a transition partial with no target partials inside a `hsm.SubmachineState(...)`, `hsm.ExitPoint(name)` matches the named exit-point outcome from the active child machine. In that context, the exit point name must resolve in the submachine state's referenced model.

---

## Pseudostates

### `hsm.ShallowHistory(name, partials...)`

Declares a named shallow history pseudostate that remembers the most recent direct child of its parent composite state.

**Parameters:**

* `name` History pseudostate name. Cannot contain `/`.
* `partials...` Target, guard, and/or effect for the default transition (required).

**Constraints:**

* History names must not contain `/`.
* Must have at least one partial (typically a target).
* Compile-time function.

**Description:**
Upon entry to a history pseudostate, the machine transitions to the most recently active direct child of the parent state, or to a default target if no history exists.

### `hsm.DeepHistory(name, partials...)`

Declares a named deep history pseudostate that recursively remembers the deepest active leaf state.

**Parameters:**

* `name` History pseudostate name. Cannot contain `/`.
* `partials...` Target, guard, and/or effect for the default transition (required).

**Constraints:**

* History names must not contain `/`.
* Must have at least one partial.
* Compile-time function.

**Description:**
Upon entry to a deep history pseudostate, the machine transitions to the deepest (most nested) leaf state that was previously active within the parent's subtree, or to a default target if no history exists.

### `hsm.Choice(name, partials...)`

Declares a choice pseudostate that evaluates a series of guarded transitions and takes the first one whose guard condition is satisfied.

**Parameters:**

* `name` Choice pseudostate name. Cannot contain `/`.
* `partials...` Two or more transitions; typically the last is a guardless fallback.

**Constraints:**

* Choice names must not contain `/`.
* Must have at least one transition.
* Last transition should typically be guardless (fallback).
* Compile-time function.

**Description:**
Implements conditional routing based on guard conditions. Each transition is evaluated in order, and the first with a successful guard is taken.

---

## Transitions

### `hsm.Transition(partials...)`

Declares a transition between states or pseudostates.

**Parameters:**

* `partials...` Any combination of event trigger, target path, guard condition, effect action, source state, entry-point selector, and/or exit-point outcome.

**Constraints:**

* Compile-time function.

**Description:**
Defines the structural elements of a state change: what event triggers it, where it goes, any conditions that must be met, actions to execute, and optionally the originating state.

### `hsm.Initial(partials...)`

Declares the initial transition when entering a composite state or the machine root.

**Parameters:**

* `partials...` Target path and optional effect action.

**Constraints:**

* Must include a target.
* Compile-time function.

**Description:**
Specifies the default entry point when a composite state (or the root machine) is entered.

---

## Event Triggers

### `hsm.On(event_type)`

Declares a typed event trigger for a specific event type.

**Parameters:**

* `event_type` Event type identifier (strongly-typed).

**Constraints:**

* Compile-time function.

**Description:**
Specifies that a transition is triggered by a particular event type. The event system is statically type-checked at compile time.

### `hsm.On(event_name)`

Declares a string-based event trigger using a string literal name.

**Parameters:**

* `event_name` Event name (string literal). No character restrictions for the name itself.

**Constraints:**

* Compile-time function.

**Description:**
Enables simple event triggering by string name, useful for events without structured data payloads.

### Event Ownership

Dispatch implementations should treat the event envelope (`Name`, `QualifiedName`, `Source`, `Target`, `ID`, and `Kind`) as immutable routing state. Behavior metadata writes must not change those envelope fields; mutable payload data and schema metadata remain application-owned values.

Event payload data is application-owned. Implementations may pass payload data by reference unless a language binding explicitly documents stronger copy semantics. Callers that need isolated mutable payloads should provide immutable data or copy it at the application boundary.

### `hsm.OnCall(operation_name)`

Declares a transition trigger linked to a named operation. Fires when that operation is invoked via a language-specific call mechanism.

**Parameters:**

* `operation_name` Operation name. Cannot contain `/`.

**Constraints:**

* Operation names must not contain `/`.
* Compile-time function.

**Description:**
Routes transitions based on explicit operation invocation, allowing the state machine to respond to named procedure calls.

### `hsm.When(attribute_name)` / `hsm.OnSet(attribute_name)`

Declares an attribute-change trigger that fires when a named attribute is modified via either compile-time or runtime attribute setters.

**Parameters:**

* `attribute_name` Attribute name. Cannot contain `/`.

**Constraints:**

* Attribute names must not contain `/`.
* Compile-time function.

**Description:**
Triggers a transition whenever a specific attribute value changes. Provides reactive attribute-based state management.

---

## Timing Events

### `hsm.After(duration_source)`

Declares a timeout trigger that fires after a specified duration.

**Parameters:**

* `duration_source` Either a callable returning a duration, or an attribute name (string literal) containing a duration value.

**Constraints:**

* Compile-time function.

**Description:**
Defines a time-based trigger. The duration can be statically specified via a callable, or dynamically specified via an attribute value. The timeout is relative (elapsed time) rather than absolute. See the distinct-timer and `hsm.Choice` note under `hsm.Every(...)`.

### `hsm.Every(interval_source)`

Declares a periodic interval trigger that fires repeatedly at fixed intervals.

**Parameters:**

* `interval_source` Either a callable returning a duration, or an attribute name (string literal) containing a duration value.

**Constraints:**

* Compile-time function.

**Description:**
Defines a repeating timer. The transition (typically a self-transition) fires on each interval expiration.

Each `hsm.After(...)`, `hsm.Every(...)`, or `hsm.At(...)` on a transition creates a **distinct** time event and timer activity. Multiple transitions that use the same duration expression are **not** merged: each fires on its own run-to-completion step. To branch on one timer firing, route into `hsm.Choice(...)` with guarded transitions instead of duplicating the same trigger on sibling transitions.

### `hsm.At(timepoint_source)`

Declares a time-point trigger that fires at a specific absolute time.

**Parameters:**

* `timepoint_source` Either a callable returning a time-point, or an attribute name (string literal) containing a time-point value.

**Constraints:**

* Compile-time function.

**Description:**
Defines an absolute deadline trigger. Unlike `hsm.After()` (which is relative), this fires at a specific moment in time.

---

## Transition Targets & Routing

### `hsm.Target(path)`

Declares the target state of a transition using a hierarchical path.

**Parameters:**

* `path` State path (string literal). Absolute paths start with `/`, for example `/RootName/ParentName/ChildName`. Relative paths are resolved from the containing state, for example `child`, `../sibling`, or `.` for the current source state.

**Constraints:**

* Path must resolve to a state, supported pseudostate, or entry point in the model.
* Paths that cross into a child machine may resolve only to a declared `hsm.EntryPoint(...)`; arbitrary child internal states are not valid cross-boundary targets.
* Compile-time function.

**Description:**
Specifies the destination state for a transition using hierarchical path notation. Implementations must support absolute model paths and relative paths from the state that contains the transition.

### `hsm.Source(path)`

Specifies the source state of a transition for parent-level routing.

**Parameters:**

* `path` Source state path (string literal). Absolute paths start with `/`. Relative paths are resolved from the containing state.

**Constraints:**

* Path must resolve to a state in the model.
* Compile-time function.

**Description:**
Explicitly names the originating state of a transition. Enables transitions to be defined at a parent level while routing based on which child state the event originated from.

---

## State Behaviors

### `hsm.Entry(action...)`

Declares entry action(s) executed upon entering a state.

**Parameters:**

* `action...` One or more action callables.

**Constraints:**

* Compile-time function.

**Description:**
Specifies behaviors that occur when the state is entered. Multiple entry actions execute in order.

### `hsm.Entry(operation_name...)`

Declares entry actions as references to named model operations.

**Parameters:**

* `operation_name...` One or more operation names (string literals). Cannot contain `/`.

**Constraints:**

* Operation names must not contain `/`.
* Compile-time function.

**Description:**
References model-level operations to execute on state entry.

### `hsm.Exit(action...)`

Declares exit action(s) executed upon leaving a state.

**Parameters:**

* `action...` One or more action callables.

**Constraints:**

* Compile-time function.

**Description:**
Specifies behaviors that occur when the state is exited. Multiple exit actions execute in order.

### `hsm.Exit(operation_name...)`

Declares exit actions as references to named model operations.

**Parameters:**

* `operation_name...` One or more operation names (string literals). Cannot contain `/`.

**Constraints:**

* Operation names must not contain `/`.
* Compile-time function.

**Description:**
References model-level operations to execute on state exit.

### `hsm.Activity(action...)`

Declares state activity/ies: ongoing behaviors executed while in a state.

**Parameters:**

* `action...` One or more activity callables.

**Constraints:**

* Compile-time function.

**Description:**
Specifies behaviors that run while the state is active.

**Non-blocking rule:** activities must not block or poll. Use `hsm.After(...)` or `hsm.Every(...)` triggers for scheduled work.

### `hsm.Activity(operation_name...)`

Declares state activities as references to named model operations.

**Parameters:**

* `operation_name...` One or more operation names (string literals). Cannot contain `/`.

**Constraints:**

* Operation names must not contain `/`.
* Compile-time function.

**Description:**
References model-level operations to execute as state activities.

### `hsm.Effect(action...)`

Declares transition effect(s): action(s) executed when traversing a transition.

**Parameters:**

* `action...` One or more effect callables.

**Constraints:**

* Compile-time function.

**Description:**
Specifies behaviors executed during a transition, between the exit of the source state and the entry of the target state. Multiple effect actions execute in order.

### `hsm.Effect(operation_name...)`

Declares transition effects as references to named model operations.

**Parameters:**

* `operation_name...` One or more operation names (string literals). Cannot contain `/`.

**Constraints:**

* Operation names must not contain `/`.
* Compile-time function.

**Description:**
References model-level operations to execute as transition effects.

---

## Guards & Deferral

### `hsm.Guard(condition)`

Declares a transition guard: a boolean condition that must be satisfied for the transition to execute.

**Parameters:**

* `condition` A callable returning a boolean value.

**Constraints:**

* Compile-time function.

**Description:**
Specifies a condition that gates a transition. If the guard returns false, the transition does not occur.

### `hsm.Guard(operation_name)`

Declares a guard as a reference to a named model operation.

**Parameters:**

* `operation_name` Operation name (string literal). Cannot contain `/`.

**Constraints:**

* Operation names must not contain `/`.
* Compile-time function.

**Description:**
References a model-level operation that implements the guard logic and returns a boolean.

### `hsm.Defer(event_type...)`

Declares that certain event types should be deferred (queued) while in a state, to be re-queued and processed upon exiting the state.

**Parameters:**

* `event_type...` One or more event types to defer.

**Constraints:**

* Compile-time function.

**Description:**
Specifies event types that should not be processed in the current state but instead queued for later processing when the state is exited.

Deferred events are scoped to the runtime region that deferred them. If an active child machine defers an event and the containing `hsm.SubmachineState(...)` is later exited by a parent transition before the child can replay that event, the child-owned deferred event is discarded as part of child runtime teardown. It must not be replayed into the parent machine after the submachine boundary has been exited.

---

## Model Metadata

### `hsm.Attribute(name, type)`

Declares a model-level attribute of a specified type without a default value.

**Parameters:**

* `name` Attribute name (string literal). Cannot contain `/`.
* `type` Attribute type.

**Constraints:**

* Attribute names must not contain `/`.
* Compile-time function.

**Description:**
Defines a named data member of the state machine with explicit type specification.

### `hsm.Attribute(name, type, default_value)`

Declares a model-level attribute with a default value.

**Parameters:**

* `name` Attribute name (string literal). Cannot contain `/`.
* `type` Attribute type (explicit).
* `default_value` Initial value.

**Constraints:**

* Attribute names must not contain `/`.
* Compile-time function.

### `hsm.Attribute(name, default_value)`

Declares a model-level attribute with type deduced from the default value.

**Parameters:**

* `name` Attribute name (string literal). Cannot contain `/`.
* `default_value` Initial value (type is deduced).

**Constraints:**

* Attribute names must not contain `/`.
* Compile-time function.

### `hsm.Operation(name, implementation)`

Declares a named operation that can be invoked via explicit operation calls and that drives internal operation events.

**Parameters:**

* `name` Operation identifier (string literal). Cannot contain `/`.
* `implementation` Reference to the operation implementation (a stable callable reference, not an inline anonymous function).

**Constraints:**

* Operation names must not contain `/`.
* Implementation must be a callable reference (not an inline lambda/anonymous callable).
* Compile-time function.

**Description:**
Registers a named operation in the model. Operations can be invoked via a language-specific call mechanism and trigger corresponding transitions via `hsm.OnCall(...)`.

---

## Group Operations

### `hsm.MakeGroup(machines...)`

Factory function to create a group of multiple state machine instances.

**Parameters:**

* `machines...` Two or more state machine instances.

**Constraints:**

* Requires at least one machine.
* Compile-time function.

**Description:**
Combines multiple machines into a logical group for coordinated dispatch and management.

### `hsm.MakeGroup(group_id, machines...)`

Factory function to create a group with an identifier.

**Parameters:**

* `group_id` Group identifier (string).
* `machines...` Two or more state machine instances.

**Constraints:**

* Compile-time function.

**Description:**
Creates an identified group of machines for tracking and coordinated operation.

**Python alias:** `hsm.make_group(...)` maps directly to `hsm.MakeGroup(...)`. Python also keeps `hsm.NewGroup(...)` / `hsm.new_group(...)` as compatibility aliases for existing callers.

---

## Type Utilities

### `hsm.MakeKind(base_kinds...)`

Constructs kind identifiers with optional inheritance.

**Parameters:**

* `base_kinds...` Optional parent kinds for polymorphic inheritance.

**Constraints:**

* Compile-time function.

**Description:**
Creates kind values with automatically assigned IDs and optional inheritance hierarchy. Implementations should expose the canonical PascalCase API and any language-native spelling, such as Python's `make_kind`.

### `hsm.IsKind(kind, base_kind...)`

Checks if a kind matches or inherits from one or more base kinds.

**Parameters:**

* `kind` Kind value to check.
* `base_kind...` One or more base kinds to match against.

**Constraints:**

* Compile-time function.

**Returns:** boolean.

---

## Runtime Dispatch

### `instance.Dispatch(event)`

Submits an event to a running state machine instance.

**Parameters:**

* `event` Event value or event name accepted by the implementation's event-construction rules.

**Returns:** completion handle.

The completion handle is a host-language-native waitable that carries no value:

* Go: a receive-only completion channel such as `<-chan struct{}`.
* Python: an awaitable / future that resolves to `None`.
* JavaScript / TypeScript: a `Promise<void>`.
* C# / Rust / Dart / Zig / C++: the nearest native no-value completion primitive, or `void` for strictly synchronous implementations.

**Description:**
Dispatch submits the event and optionally lets callers wait until the resulting run-to-completion work reaches the implementation's synchronization point. The normal dispatch API does not report whether a submitted event was immediately consumed, deferred for later replay, or ignored by transition selection. Deferred-event handling is runtime-internal behavior unless exposed through explicit observation APIs.

**Constraints:**

* Waiting on the returned completion handle is the supported production synchronization path after dispatch.
* Completion handles must not carry `Processed`, `Deferred`, `QueueFull`, or equivalent dispatch-result values.
* Queue failures are runtime errors, not normal dispatch results. If processing can continue, implementations should surface queue failures through the runtime error-event mechanism.
* Dispatch implementations should treat the event envelope (`Name`, `QualifiedName`, `Source`, `Target`, `ID`, and `Kind`) as immutable routing state. Behavior metadata writes must not change those envelope fields; mutable payload data and schema metadata remain application-owned values.

### Runtime Context

Runtime contexts are immutable request values modeled after Go `context.Context`: adding HSM runtime values returns an extended context and must not mutate the parent context.

Implementations should expose canonical context keys and lookup helpers:

* `hsm.Keys.HSM` identifies the current state machine or group in an extended runtime context.
* `hsm.Keys.Owner` identifies the previous enclosing state machine or group when a machine extends an existing machine context.
* `hsm.Keys.Instances` identifies the shared started-machine registry for a runtime context tree.
* `hsm.FromContext(ctx)` returns the current state machine or group and whether one was present.
* `hsm.InstancesFromContext(ctx)` returns the started machines visible through `ctx` and whether a registry was present.

Machine start extends the supplied context with `Keys.HSM`, `Keys.Owner`, and the shared `Keys.Instances` registry. Behavior callbacks receive an extended context whose current `Keys.HSM` is the executing machine. Cross-machine dispatch uses this context to populate missing per-recipient event envelope fields: `Source` from the current machine ID and `Target` from the recipient machine ID. Explicit caller-provided `Source` or `Target` metadata remains payload metadata and must not be overwritten.

### `hsm.DispatchAll(ctx, event)`

Submits an event to every started machine in a runtime context.

**Returns:** completion handle.

The handle completes after all selected machines have reached their dispatch synchronization point. It carries no value.

### `hsm.DispatchTo(ctx, event, ids...)`

Submits an event to started machines matching one or more runtime instance identifiers.

**Returns:** completion handle.

The handle completes after all selected machines have reached their dispatch synchronization point. It carries no value.

---

## Runtime Attribute Access

Runtime string-based attribute accessors that complement compile-time, name-specialized access (for languages that support it). These APIs use **type erasure** via a **dynamic value container** (for example: `Any`, `Variant`, or equivalent in the host language) to support scripting bindings, serialization, and tooling.

### `instance.Get(name)`

Runtime attribute read.

**Parameters:**

* `name` Attribute name (string or string-like value).

**Returns:**

* A **dynamic value** containing a copy of the attribute value, or
* An **empty dynamic value** if no attribute with the given name exists.

**Description:**
Looks up an attribute by name at runtime and returns its value wrapped in a dynamic container.

**Limitations:**

* Returns a copy (inherent to type erasure).
* Caller must know the expected type (or inspect the dynamic value) to extract safely.

### `instance.Set(name, value)`

Runtime attribute write.

**Parameters:**

* `name` Attribute name (string or string-like value).
* `value` Dynamic value containing the new attribute value.

**Returns:** completion handle.

The completion handle is the same host-language-native no-value waitable used by `instance.Dispatch(event)`.

**Description:**
Looks up an attribute by name at runtime, validates the dynamic value matches the attribute type, applies change detection, updates storage, and emits any associated `hsm.When(...)` / `hsm.OnSet(...)` change events. Waiting on the returned completion handle is the supported synchronization path for both the attribute update and the resulting runtime reaction.

**Limitations:**

* Requires exact type match (no implicit conversions).
* Unknown-name and type-mismatch failures are runtime errors, not normal result values. Host-language bindings may surface them through exceptions, failed completion handles, or the runtime error-event mechanism according to that language's conventions.

---

## Runtime Configuration

### `hsm.Config(...)`

Configures a runtime state machine instance without changing the model.

**Fields:**

* `ID` Optional stable instance identifier used by `hsm.ID(...)`, `hsm.DispatchTo(...)`, and snapshots.
* `Name` Optional runtime qualified machine name used by `hsm.Name(...)`, `hsm.QualifiedName(...)`, and snapshots. The model's qualified name remains unchanged.
* `Data` Optional payload supplied to the initial event when the machine starts.
* `Clock` Optional runtime clock used by timer-based transitions such as `hsm.After(...)`, `hsm.Every(...)`, and `hsm.At(...)` where implemented.
* `Queue` Optional runtime event queue used to receive, buffer, and select regular events for processing.

**Constraints:**

* Runtime configuration is applied when constructing or starting an instance.
* Runtime configuration must not mutate the model.
* Multiple instances of the same model may use different runtime configuration.

**Description:**
Provides instance-specific identity, initial data, and scheduling behavior. Configuration values affect runtime observability and execution only; they do not alter the DSL model structure.

### `hsm.Queue(fifo...)`

Defines runtime event queue behavior for regular event ingress and selection.

**Parameters:**

* `fifo` Optional regular-event FIFO backend with synchronous `push(event)`, `pop()`, and `len()` methods. Defaults to an internal `Fifo` deque. May also be another `Queue` instance whose `push`/`pop`/`len` handle regular events only.

**Constraints:**

* Runtime facility.
* Queue configuration is instance-specific and must not mutate the model.
* Implementations must provide a default queue when no `Config.Queue` is supplied.
* A custom `fifo` backend must implement all three operations: `push`, `pop`, and `len`.
* Queue operations are synchronous runtime hooks. `Push`, `Pop`, and `Len` must not return promises, futures, tasks, coroutines, channels, or other awaitable/asynchronous results.
* A supplied queue receives regular events only. Runtime completion events remain in the runtime-owned priority queue, are selected before regular events, and must not be routed through custom queue hooks.
* Queue operation errors must be propagated through the runtime as `ErrorEvent` when processing can continue. Since `ErrorEvent` derives from `CompletionEvent`, those propagated errors must enter the runtime-owned priority queue and must not be routed back through the supplied queue.
* Queue implementations must preserve run-to-completion compatibility: `Push` must not process transitions directly, and `Pop` must return events to the runtime for normal transition selection.

**Description:**
Allows production runtimes and tests to control regular event buffering, priority, backpressure, persistence, or integration with host event loops. Dispatch APIs describe *which* event enters a machine; `Queue` controls *how* received regular events are buffered and selected for processing while completion events preserve runtime-defined priority behavior.

### `hsm.Clock(...)`

Defines runtime scheduling hooks for timer-based behavior.

**Fields:**

* `Sleep(duration)` / `After(duration)` Host-language-specific wait function for relative durations.
* `NewTimer(duration)` Optional host-language-specific timer factory where supported.

**Constraints:**

* Runtime facility.
* Implementations must provide `hsm.DefaultClock`.
* A partial clock inherits unspecified behavior from `hsm.DefaultClock`.
* Timer waits must be cancelable by state exit or machine stop where the host language supports cancellation.

**Description:**
Allows production runtimes and tests to control time deterministically. Timer DSL declarations (`hsm.After`, `hsm.Every`, and `hsm.At`) describe *when* a transition should fire; `Clock` controls *how* the runtime waits for that time.

### `hsm.DefaultClock`

The process- or module-level fallback clock used when no `Config.Clock` is supplied.

**Constraints:**

* Runtime facility.
* Must be safe for ordinary production use by default.

---

## Snapshotting

### `hsm.TakeSnapshot(ctx, machine)`

Captures a point-in-time snapshot of a state machine instance for debugging, observability, testing, and tooling.

**Parameters:**

* `ctx` Execution or runtime context used for snapshot capture (opaque, implementation-defined).
* `machine` State machine instance to snapshot.

**Returns:** `Snapshot`

**Constraints:**

* Runtime function.
* Must not mutate machine state.

**Description:**
Collects a consistent, read-only view of the machine at the time of invocation. Snapshotting is intended for diagnostics, visualization, time-travel debugging, audit logs, and deterministic testing. The snapshot reflects the *current stable state* of the machine and does not advance execution.

---

### Snapshot Data Model

The following structures describe the **logical snapshot schema**. Field names are normative; concrete language bindings may map them to equivalent native representations.

#### `TransitionSnapshot`

Describes a transition that is visible from the current active state at the time the snapshot is captured.

* `Name` Fully-qualified transition name.
* `Kind` Transition kind identifier.
* `Source` Absolute source vertex path.
* `Target` Absolute target vertex path, if resolved.
* `Events` Ordered list of trigger event names for the transition.
* `Guard` Boolean indicating whether the transition has a guard.

#### `Snapshot`

Represents the complete observable state of a machine at a point in time.

* `ID` Unique snapshot identifier.
* `QualifiedName` Fully-qualified machine name.
* `State` Current active state path.
* `Attributes` Map of fully-qualified attribute names to their current values (dynamic values).
* `QueueLen` Number of events currently queued.
* `Transitions` Ordered list of `TransitionSnapshot` entries describing transitions visible from the current active state.

**Notes:**

* Attribute values are represented using a dynamic value container (`Any` / `Variant` / equivalent).
* Snapshot contents are immutable once produced.
* Implementations may cap the number of transitions recorded for bounded memory usage.

---

**This document is normative.**
Any behavior not described here is undefined.
