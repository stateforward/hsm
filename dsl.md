# HSM DSL — Domain-Specific Language Reference

Complete reference for the Domain-Specific Language (DSL) of the hierarchical state machine library.

All DSL functions are **namespace/module-level functions** (not methods on objects), enabling model construction and validation at compile time.

> **Notation:** `hsm.FunctionName(...)` represents a function in the `hsm` namespace/module. These are free functions, not instance methods.

> **Naming convention:** All exported DSL and runtime API functions use **PascalCase**. This choice is intentional, even though it conflicts with some language-specific style guides. PascalCase is the *only* casing convention that is consistently supported across **all major languages** for **both namespace-level functions and object methods**, without ambiguity or special rules. This ensures the DSL can be mapped 1:1 into C, C++, Rust, Go, C#, Java, Python, JavaScript, and scripting bindings while preserving identical API names and documentation.

---

## Table of Contents

1. [Model Definition](#model-definition)
2. [State Declaration](#state-declaration)
3. [Pseudostates](#pseudostates)
4. [Transitions](#transitions)
5. [Event Triggers](#event-triggers)
6. [Timing Events](#timing-events)
7. [Transition Targets & Routing](#transition-targets--routing)
8. [State Behaviors](#state-behaviors)
9. [Guards & Deferral](#guards--deferral)
10. [Model Metadata](#model-metadata)
11. [Group Operations](#group-operations)
12. [Type Utilities](#type-utilities)
13. [Runtime Attribute Access](#runtime-attribute-access)
14. [Runtime Constants](#runtime-constants)

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

* `partials...` Any combination of event trigger, target path, guard condition, effect action, and/or source state.

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
Defines a time-based trigger. The duration can be statically specified via a callable, or dynamically specified via an attribute value. The timeout is relative (elapsed time) rather than absolute.

### `hsm.Every(interval_source)`

Declares a periodic interval trigger that fires repeatedly at fixed intervals.

**Parameters:**

* `interval_source` Either a callable returning a duration, or an attribute name (string literal) containing a duration value.

**Constraints:**

* Compile-time function.

**Description:**
Defines a repeating timer. The transition (typically a self-transition) fires on each interval expiration.

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

Declares the target state of a transition using an absolute path.

**Parameters:**

* `path` Absolute state path (string literal). Must start with `/`. Format: `/RootName/ParentName/ChildName`.

**Constraints:**

* Path must be absolute (start with `/`).
* Compile-time function.

**Description:**
Specifies the destination state for a transition using a hierarchical path notation. Paths are absolute from the root of the state machine.

### `hsm.Source(path)`

Specifies the source state of a transition for parent-level routing.

**Parameters:**

* `path` Source state path (string literal).

**Constraints:**

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

---

## Type Utilities

### `hsm.MakeKind(id)` / `hsm.MakeKind(name)`

Constructs event kind identifiers with optional inheritance.

**Parameters:**

* `id` Numeric event ID, or
* `name` Event name (string), and
* `base_kinds...` Optional parent kinds for polymorphic inheritance.

**Constraints:**

* Compile-time function.

**Description:**
Creates kind values that define the event type and optional inheritance hierarchy.

### `hsm.IsKind(kind, base_kind...)`

Checks if a kind matches or inherits from one or more base kinds.

**Parameters:**

* `kind` Kind value to check.
* `base_kind...` One or more base kinds to match against.

**Constraints:**

* Compile-time function.

**Returns:** boolean.

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

**Returns:** `result_t`

* `Processed` Attribute updated (or value unchanged).
* `QueueFull` Update failed (unknown attribute name or type mismatch).

**Description:**
Looks up an attribute by name at runtime, validates the dynamic value matches the attribute type, applies change detection, updates storage, and emits any associated `hsm.When(...)` / `hsm.OnSet(...)` change events.

**Limitations:**

* Requires exact type match (no implicit conversions).
* Unknown-name and type-mismatch failures share the same result.

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

#### `EventDetail`

Describes an event that was recently processed or is pending in the queue.

* `Event` String identifier of the event.
* `Target` Absolute target state path, if resolved.
* `Guard` Boolean indicating whether the guard condition evaluated to true.
* `Schema` Optional event payload or schema information (dynamic value).

#### `Snapshot`

Represents the complete observable state of a machine at a point in time.

* `ID` Unique snapshot identifier.
* `QualifiedName` Fully-qualified machine name.
* `State` Current active state path.
* `Attributes` Map of attribute names to their current values (dynamic values).
* `QueueLen` Number of events currently queued.
* `Events` Ordered list of `EventDetail` entries describing recent or queued events.

**Notes:**

* Attribute and schema values are represented using a dynamic value container (`Any` / `Variant` / equivalent).
* Snapshot contents are immutable once produced.
* Implementations may cap the number of events recorded for bounded memory usage.

---

## Runtime Constants

### Event Dispatch Results

* `QueueFull` Event could not be enqueued due to queue capacity.
* `Processed` Event was successfully enqueued and will be processed.
* `Deferred` Event was deferred for later processing per `hsm.Defer(...)`.

**Description:**
Return values from `instance.Dispatch(event)` indicating the outcome of an attempt to queue an event.

---

**This document is normative.**
Any behavior not described here is undefined.
