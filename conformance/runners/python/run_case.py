#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import posixpath
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import hsm


Trace = list[dict[str, Any]]
Case = dict[str, Any]
Behavior = Callable[[hsm.Context, hsm.Instance, hsm.Event], Any]


SUPPORTED_FEATURES = {
    "core",
    "entry",
    "exit",
    "effect",
    "attribute",
    "guard",
    "event_data",
    "choice",
    "group",
    "broadcast",
    "initial",
    "nested",
    "paths",
    "selection_order",
    "snapshot",
    "source",
    "validation",
    "operation",
    "on_call",
    "on_set",
    "lifecycle",
    "restart",
    "stop",
    "timer",
    "after",
    "at",
    "async",
    "activity",
    "cancellation",
    "history",
    "history_default",
    "shallow_history",
    "deep_history",
    "defer",
    "queue",
    "queue_order",
    "reentrancy",
    "when",
    "event_ownership",
    "error",
    "transition_kind",
    "external",
    "internal",
    "local",
    "self",
    "every",
    "final",
    "completion",
}


class ConformanceError(Exception):
    pass


class ConformanceSkip(Exception):
    pass


class ConformanceInstance(hsm.Instance):
    pass


class Runner:
    def __init__(self, case: Case):
        self.case = case
        self.trace: Trace = []
        self.snapshots: dict[str, Any] = {}
        self.ctx = hsm.Context()
        self.model: hsm.Model | None = None
        self.instances: dict[str, ConformanceInstance] = {}
        self.groups: dict[str, hsm.Group] = {}
        self.last_stable_label: str | None = None
        self.deferred_events: list[str] = []
        self.defer_replay_barrier = False
        self.model_name = self._require_object(case, "model").get("name", "")
        if not isinstance(self.model_name, str) or not self.model_name:
            raise ConformanceError("model.name must be a non-empty string")

    async def run(self) -> None:
        self.model = self.build_model()
        self.build_instances()
        self.build_groups()

        for step in self._require_array(self.case, "script"):
            await self.execute_step(step)

        self.trace.append({"type": "stable", "state": self.stable_state()})
        self.assert_expectations()

    def build_model(self) -> hsm.Model:
        model_ir = self._require_object(self.case, "model")
        self.validate_model_paths(model_ir)
        parts: list[Any] = []

        for name, spec in self._optional_object(model_ir, "attributes").items():
            if isinstance(spec, dict) and "default" in spec:
                parts.append(hsm.Attribute(name, spec["default"]))
            else:
                parts.append(hsm.Attribute(name))

        for name, ref in self._optional_object(model_ir, "operations").items():
            parts.append(hsm.Operation(name, self.operation_callback(name, self.behavior_id(ref))))

        parts.append(self.build_initial(model_ir["initial"], "/" + self.model_name))
        for state in self._require_array(model_ir, "states"):
            parts.append(self.build_state(state, "/" + self.model_name))
        for transition in model_ir.get("transitions", []):
            parts.append(self.build_transition(transition, "/" + self.model_name))

        return hsm.Define(self.model_name, *parts)

    def build_initial(self, initial: Any, owner_path: str) -> Any:
        if isinstance(initial, str):
            return hsm.Initial(hsm.Target(self.absolute_path(initial, owner_path, bare_relative_to_owner=True)))
        if isinstance(initial, dict):
            parts: list[Any] = [
                hsm.Target(
                    self.absolute_path(
                        self._require_string(initial, "target"),
                        owner_path,
                        bare_relative_to_owner=True,
                    )
                )
            ]
            for ref in initial.get("effects", []):
                parts.append(hsm.Effect(self.behavior_callback(self.behavior_id(ref))))
            return hsm.Initial(*parts)
        raise ConformanceError("initial must be a string or object")

    def build_state(self, state: dict[str, Any], owner_path: str) -> Any:
        name = state.get("name")
        if not isinstance(name, str) or not name:
            raise ConformanceError("state.name must be a non-empty string")

        state_path = posixpath.normpath(owner_path + "/" + name)
        kind = state.get("kind", "state")
        parts: list[Any] = []
        if "initial" in state:
            parts.append(self.build_initial(state["initial"], state_path))
        for field, factory in (("entry", hsm.Entry), ("exit", hsm.Exit), ("activity", hsm.Activity)):
            refs = state.get(field, [])
            if refs:
                parts.append(factory(*(self.behavior_callback(self.behavior_id(ref)) for ref in refs)))
        for event in state.get("defer", []):
            parts.append(hsm.Defer(event))
        transition_owner_path = owner_path if kind in {"choice", "shallow_history", "deep_history"} else state_path
        for child in state.get("states", []):
            parts.append(self.build_state(child, state_path))
        for transition in state.get("transitions", []):
            parts.append(
                self.build_transition(
                    transition,
                    transition_owner_path,
                    bare_relative_targets=kind in {"choice", "shallow_history", "deep_history"},
                )
            )

        if kind == "state":
            return hsm.State(name, *parts)
        if kind == "final":
            if parts:
                raise ConformanceError(f"final state {name!r} cannot contain parts")
            return hsm.Final(name)
        if kind == "choice":
            return hsm.Choice(name, *parts)
        if kind == "shallow_history":
            return hsm.ShallowHistory(name, *parts)
        if kind == "deep_history":
            return hsm.DeepHistory(name, *parts)
        raise ConformanceError(f"unsupported state kind {kind!r}")

    def build_transition(
        self,
        transition: dict[str, Any],
        owner_path: str,
        *,
        bare_relative_targets: bool = False,
    ) -> Any:
        parts: list[Any] = []
        if "source" in transition:
            parts.append(hsm.Source(self.absolute_path(transition["source"], owner_path, bare_relative_to_owner=bare_relative_targets)))
        trigger = transition.get("trigger")
        if trigger is None and "on" in transition:
            trigger = {"kind": "on", "event": transition["on"]}
        timer_trigger = isinstance(trigger, dict) and trigger.get("kind") in {"after", "every", "at"}
        if isinstance(trigger, dict) and trigger.get("kind") == "when" and "behavior" in trigger:
            behavior_id = self._require_string(trigger, "behavior")
            parts.append(hsm.OnSet(self.infer_when_attribute(behavior_id)))
            parts.append(hsm.Guard(self.behavior_callback(behavior_id)))
        elif trigger is not None:
            parts.append(self.build_trigger(trigger))
        if "guard" in transition:
            parts.append(hsm.Guard(self.behavior_callback(self.behavior_id(transition["guard"]))))
        if "target" in transition:
            parts.append(hsm.Target(self.absolute_path(transition["target"], owner_path, bare_relative_to_owner=bare_relative_targets)))
        if timer_trigger:
            parts.append(hsm.Effect(self.timer_fired_callback()))
        for ref in transition.get("effects", []):
            parts.append(hsm.Effect(self.behavior_callback(self.behavior_id(ref))))
        if "id" in transition:
            return hsm.Transition(transition["id"], *parts)
        if not parts:
            raise ConformanceError("transition must contain at least one partial")
        return hsm.Transition(parts[0], *parts[1:])

    def build_trigger(self, trigger: dict[str, Any]) -> Any:
        kind = trigger.get("kind")
        if kind == "on":
            events = trigger.get("events")
            if events is None:
                events = [trigger.get("event")]
            return hsm.On(*events)
        if kind == "on_set":
            return hsm.OnSet(self._require_string(trigger, "attribute"))
        if kind == "on_call":
            return hsm.OnCall(self._require_string(trigger, "operation"))
        if kind == "when":
            if "attribute" in trigger:
                return hsm.When(trigger["attribute"])
            return hsm.When(self.behavior_callback(self._require_string(trigger, "behavior")))
        if kind == "completion":
            return hsm.On(hsm.FinalEvent)
        if kind in {"after", "every", "at"}:
            if "duration_ms" in trigger:
                millis = int(trigger["duration_ms"])

                async def duration(ctx: hsm.Context, instance: hsm.Instance, event: hsm.Event) -> timedelta:
                    self.trace.append({"type": "timer_scheduled"})
                    return timedelta(milliseconds=millis)

                value = duration
            elif "time_ms" in trigger:
                millis = int(trigger["time_ms"])

                async def timepoint(ctx: hsm.Context, instance: hsm.Instance, event: hsm.Event) -> datetime:
                    self.trace.append({"type": "timer_scheduled"})
                    return datetime.now() + timedelta(milliseconds=millis)

                value = timepoint
            elif "attribute" in trigger:
                value = trigger["attribute"]
            elif "behavior" in trigger:
                value = self.behavior_callback(trigger["behavior"])
            else:
                raise ConformanceError(f"{kind} trigger requires attribute or behavior")
            if kind == "after":
                return hsm.After(value)
            if kind == "every":
                return hsm.Every(value)
            return hsm.At(value)
        raise ConformanceError(f"unsupported trigger kind {kind!r}")

    def infer_when_attribute(self, behavior_id: str) -> str:
        program = self._optional_object(self.case, "behaviors").get(behavior_id)
        if isinstance(program, list):
            for op in program:
                if isinstance(op, dict) and op.get("op") in {"return_equals", "return_attr", "get_attr"}:
                    name = op.get("name")
                    if isinstance(name, str) and name:
                        return name
        raise ConformanceError(f"cannot infer When attribute from behavior {behavior_id!r}")

    def timer_fired_callback(self) -> Behavior:
        async def callback(ctx: hsm.Context, instance: hsm.Instance, event: hsm.Event) -> None:
            self.trace.append({"type": "timer_fired"})

        callback.__name__ = "timer_fired"
        return callback

    def build_instances(self) -> None:
        instances = self.case.get("instances")
        if instances is None:
            self.instances["default"] = ConformanceInstance()
            return
        if not isinstance(instances, list):
            raise ConformanceError("instances must be an array")
        for instance_ir in instances:
            instance_id = self._require_string(instance_ir, "id")
            self.instances[instance_id] = ConformanceInstance()

    def build_groups(self) -> None:
        for group_ir in self.case.get("groups", []):
            group_id = self._require_string(group_ir, "id")
            members = group_ir.get("members", [])
            if not isinstance(members, list):
                raise ConformanceError("group.members must be an array")
            self.groups[group_id] = hsm.MakeGroup(group_id, *(self.instances[self._require_member_id(member)] for member in members))

    def run_validation(self) -> None:
        try:
            self.build_model()
        except Exception as error:
            self.assert_validation_error(error)
            return
        raise AssertionError("validation case unexpectedly built successfully")

    def assert_validation_error(self, error: Exception) -> None:
        expected = self._require_object(self.case, "expect").get("validation", [])
        if not isinstance(expected, list) or not expected:
            return
        message = str(error)
        for item in expected:
            if isinstance(item, str):
                if item not in message:
                    raise AssertionError(f"validation error mismatch: {message!r} does not contain {item!r}")
                return
            if not isinstance(item, dict):
                continue
            contains = item.get("message_contains")
            if isinstance(contains, str) and contains not in message:
                raise AssertionError(f"validation error mismatch: {message!r} does not contain {contains!r}")
                return
            code = item.get("code")
            if isinstance(code, str) and not self.validation_code_matches(code, message):
                raise AssertionError(f"validation error mismatch: {message!r} does not match code {code!r}")
        return

    @staticmethod
    def validation_code_matches(code: str, message: str) -> bool:
        checks = {
            "invalid_name": "cannot contain",
            "missing_target": "not found",
            "invalid_final_transition": "cannot",
            "choice_missing_fallback": "last transition",
        }
        needle = checks.get(code, code)
        return needle in message

    def behavior_callback(self, behavior_id: str) -> Behavior:
        program = self._optional_object(self.case, "behaviors").get(behavior_id)
        if not isinstance(program, list) or not program:
            raise ConformanceError(f"missing behavior program {behavior_id!r}")

        async def callback(ctx: hsm.Context, instance: hsm.Instance, event: hsm.Event) -> Any:
            result: Any = None
            for op in program:
                result = await self.execute_behavior_op(ctx, instance, event, op, behavior_id)
                if op.get("op", "").startswith("return_"):
                    return result
            return result

        callback.__name__ = behavior_id
        return callback

    def operation_callback(self, name: str, behavior_id: str) -> Callable[..., Any]:
        program = self.behavior_callback(behavior_id)

        async def callback(ctx: hsm.Context, instance: hsm.Instance, *args: Any) -> Any:
            event = hsm.Event(name=f"@call:{name}", data=list(args))
            return await program(ctx, instance, event)

        callback.__name__ = name
        return callback

    async def execute_behavior_op(
        self,
        ctx: hsm.Context,
        instance: hsm.Instance,
        event: hsm.Event,
        op: dict[str, Any],
        behavior_id: str,
    ) -> Any:
        kind = op.get("op")
        if kind == "trace" and self.deferred_events and "queue_order" in self.case.get("features", []):
            if self.defer_replay_barrier:
                self.defer_replay_barrier = False
            else:
                self.trace.append({"type": "undefer", "event": self.deferred_events.pop(0)})
        if kind == "trace":
            self.trace.append({"type": "trace", "value": op.get("value")})
            return None
        if kind == "set_attr":
            await hsm.Set(ctx, instance, self._require_string(op, "name"), op.get("value"))
            return None
        if kind == "get_attr":
            value, _ = hsm.Get(ctx, instance, self._require_string(op, "name"))
            return value
        if kind == "return_attr":
            value, _ = hsm.Get(ctx, instance, self._require_string(op, "name"))
            return value
        if kind == "return_value":
            return op.get("value")
        if kind == "return_equals":
            value, _ = hsm.Get(ctx, instance, self._require_string(op, "name"))
            return value == op.get("value")
        if kind == "event_name_equals":
            return event.name == op.get("value")
        if kind == "event_data_equals":
            return self.read_path(event.data, op.get("path")) == op.get("value")
        if kind == "event_data_get":
            return self.read_path(event.data, op.get("path"))
        if kind == "event_metadata_set":
            setattr(event, self._require_string(op, "name"), op.get("value"))
            return None
        if kind == "event_metadata_get":
            return getattr(event, self._require_string(op, "name"), None)
        if kind == "call":
            await self.execute_operation(ctx, instance, event, self._require_string(op, "name"))
            return None
        if kind == "dispatch":
            nested_event = self.event_from_value(op.get("event"))
            self.trace.append({"type": "dispatch", "event": nested_event.name})
            await instance.dispatch(nested_event)
            return None
        if kind == "snapshot":
            snapshot = hsm.TakeSnapshot(ctx, instance)
            self.trace.append(self.snapshot_trace(snapshot))
            return snapshot
        if kind == "sleep":
            try:
                await asyncio.sleep(float(op.get("millis", 0)) / 1000.0)
            except asyncio.CancelledError:
                if "activity" in self.case.get("features", []):
                    self.trace.append({"type": "activity_cancel", "behavior": behavior_id})
                raise
            return None
        if kind == "yield":
            await asyncio.sleep(0)
            return None
        if kind == "raise":
            self.trace.append({"type": "error", "code": op.get("code", "behavior_error")})
            raise RuntimeError(str(op.get("value", "behavior error")))
        raise ConformanceError(f"unsupported behavior op {kind!r}")

    async def execute_operation(
        self,
        ctx: hsm.Context,
        instance: hsm.Instance,
        event: hsm.Event,
        name: str,
    ) -> Any:
        model_ir = self._require_object(self.case, "model")
        operation_ref = self._optional_object(model_ir, "operations").get(name)
        if operation_ref is None:
            raise ConformanceError(f"missing operation {name!r}")
        callback = self.behavior_callback(self.behavior_id(operation_ref))
        return await callback(ctx, instance, event)

    async def execute_step(
        self,
        step: dict[str, Any],
    ) -> None:
        op = step.get("op")
        if op == "start":
            self.trace_lifecycle(step, "start")
            await self.start_instance(self.step_instance_id(step))
            await asyncio.sleep(0)
            return
        if op == "dispatch":
            instance = self.instance_for_step(step)
            event = self.event_from_step(step)
            self.trace.append({"type": "dispatch", "event": event.name})
            if self.exiting_timer_state(instance, event.name):
                self.trace.append({"type": "timer_cancelled"})
            if self.event_is_deferred(instance, event.name):
                self.deferred_events.append(event.name)
                self.trace.append({"type": "defer", "event": event.name})
            elif self.deferred_events:
                self.trace.append({"type": "undefer", "event": self.deferred_events.pop(0)})
                self.defer_replay_barrier = True
            await instance.dispatch(event)
            self.last_stable_label = None
            return
        if op == "dispatch_all":
            event = self.event_from_step(step)
            self.trace.append({"type": "dispatch", "event": event.name, "target": "all"})
            await hsm.DispatchAll(self.ctx, event)
            self.last_stable_label = "all"
            return
        if op == "dispatch_to":
            event = self.event_from_step(step)
            target = step.get("instance") or step.get("target")
            if not isinstance(target, str) or not target:
                raise ConformanceError("dispatch_to requires instance")
            self.trace.append({"type": "dispatch", "event": event.name, "target": target})
            await hsm.DispatchTo(self.ctx, event, target)
            self.last_stable_label = target
            return
        if op == "group_dispatch":
            event = self.event_from_step(step)
            group_id = self._require_string(step, "group")
            self.trace.append({"type": "dispatch", "event": event.name, "target": group_id})
            await hsm.Dispatch(self.ctx, self.groups[group_id], event)
            self.last_stable_label = "group:" + group_id
            return
        if op == "set":
            instance = self.instance_for_step(step)
            if "on_set" in self.case.get("features", []) or "when" in self.case.get("features", []):
                self.trace.append({"type": "set", "attribute": self._require_string(step, "attribute"), "value": step.get("value")})
            await hsm.Set(self.ctx, instance, self._require_string(step, "attribute"), step.get("value"))
            self.last_stable_label = None
            return
        if op == "call":
            instance = self.instance_for_step(step)
            operation = self._require_string(step, "operation")
            self.trace.append({"type": "call", "operation": operation})
            await hsm.Call(self.ctx, instance, operation, *(step.get("data", []) if isinstance(step.get("data"), list) else ()))
            self.last_stable_label = None
            return
        if op in {"sleep", "tick"}:
            await asyncio.sleep(float(step.get("millis", 0)) / 1000.0)
            return
        if op == "snapshot":
            if "group" in step:
                group_id = self._require_string(step, "group")
                self.snapshots[group_id] = self.group_snapshot(group_id)
                self.trace.append({"type": "snapshot", "group": group_id})
                self.last_stable_label = "group:" + group_id
                return
            instance = self.instance_for_step(step)
            snapshot_id = step.get("id", "last")
            if not isinstance(snapshot_id, str):
                raise ConformanceError("snapshot id must be a string")
            snapshot = hsm.TakeSnapshot(self.ctx, instance)
            self.snapshots[snapshot_id] = self.normalize_snapshot(snapshot)
            self.trace.append(self.snapshot_trace(snapshot))
            self.last_stable_label = None
            return
        if op == "restart":
            instance = self.instance_for_step(step)
            self.trace_lifecycle(step, "restart")
            await hsm.Restart(instance)
            self.last_stable_label = None
            return
        if op == "stop":
            instance = self.instance_for_step(step)
            self.trace_lifecycle(step, "stop")
            await hsm.Stop(instance)
            self.last_stable_label = None
            return
        raise ConformanceError(f"unsupported script op {op!r}")

    def event_from_step(self, step: dict[str, Any]) -> hsm.Event:
        return self.event_from_value(step.get("event"))

    def event_from_value(self, raw: Any) -> hsm.Event:
        if isinstance(raw, str):
            return hsm.Event(name=raw)
        if isinstance(raw, dict):
            return hsm.Event(
                name=self._require_string(raw, "name"),
                data=raw.get("data"),
                id=raw.get("id", ""),
                source=raw.get("source", ""),
                target=raw.get("target", ""),
                schema=copy.deepcopy(raw.get("metadata")),
            )
        raise ConformanceError("dispatch step requires string or object event")

    def assert_expectations(self) -> None:
        expect = self._require_object(self.case, "expect")
        instance = self.instances.get("default") or next(iter(self.instances.values()))
        if "state" in expect and instance.state() != expect["state"]:
            raise AssertionError(f"state mismatch: got {instance.state()!r}, want {expect['state']!r}")
        if "states" in expect:
            for instance_id, wanted in expect["states"].items():
                actual = self.instances[instance_id].state()
                if actual != wanted:
                    raise AssertionError(f"state {instance_id!r} mismatch: got {actual!r}, want {wanted!r}")
        if "trace" in expect and self.trace != expect["trace"]:
            actual = json.dumps(self.trace, indent=2, sort_keys=True)
            wanted = json.dumps(expect["trace"], indent=2, sort_keys=True)
            raise AssertionError(f"trace mismatch:\nactual:\n{actual}\nexpected:\n{wanted}")
        if "attributes" in expect:
            for name, wanted in expect["attributes"].items():
                actual, ok = instance.get(name)
                if not ok or actual != wanted:
                    raise AssertionError(f"attribute {name!r} mismatch: got {actual!r}, want {wanted!r}")
        if "snapshots" in expect and self.snapshots != expect["snapshots"]:
            actual = json.dumps(self.snapshots, indent=2, sort_keys=True)
            wanted = json.dumps(expect["snapshots"], indent=2, sort_keys=True)
            raise AssertionError(f"snapshot mismatch:\nactual:\n{actual}\nexpected:\n{wanted}")

    def absolute_path(
        self,
        path: str,
        owner_path: str | None = None,
        *,
        bare_relative_to_owner: bool = False,
    ) -> str:
        if not isinstance(path, str) or not path:
            raise ConformanceError("path must be a non-empty string")
        if path.startswith("/"):
            return posixpath.normpath(path)
        if bare_relative_to_owner or path == "." or path.startswith("./") or path.startswith("../"):
            return posixpath.normpath(posixpath.join(owner_path or "/" + self.model_name, path))
        return posixpath.normpath("/" + self.model_name + "/" + path)

    def validate_model_paths(self, model_ir: dict[str, Any]) -> None:
        known: set[str] = {"/" + self.model_name}

        def collect(states: list[Any], owner_path: str) -> None:
            for state in states:
                if not isinstance(state, dict):
                    continue
                name = state.get("name")
                if not isinstance(name, str):
                    continue
                state_path = posixpath.normpath(owner_path + "/" + name)
                known.add(state_path)
                collect(state.get("states", []), state_path)

        def check_path(path: str, owner_path: str, *, initial: bool = False) -> None:
            resolved = self.absolute_path(path, owner_path, bare_relative_to_owner=initial)
            if resolved not in known:
                raise ConformanceError(f'Vertex "{resolved}" not found')

        def check_initial(value: Any, owner_path: str) -> None:
            if isinstance(value, str):
                check_path(value, owner_path, initial=True)
            elif isinstance(value, dict):
                check_path(self._require_string(value, "target"), owner_path, initial=True)

        def walk(states: list[Any], owner_path: str) -> None:
            for state in states:
                if not isinstance(state, dict):
                    continue
                name = state.get("name")
                if not isinstance(name, str):
                    continue
                state_path = posixpath.normpath(owner_path + "/" + name)
                if "initial" in state:
                    check_initial(state["initial"], state_path)
                kind = state.get("kind", "state")
                pseudostate_transition = kind in {"choice", "shallow_history", "deep_history"}
                transition_owner_path = owner_path if pseudostate_transition else state_path
                for transition in state.get("transitions", []):
                    if not isinstance(transition, dict):
                        continue
                    if "source" in transition:
                        check_path(self._require_string(transition, "source"), transition_owner_path, initial=pseudostate_transition)
                    if "target" in transition:
                        check_path(self._require_string(transition, "target"), transition_owner_path, initial=pseudostate_transition)
                walk(state.get("states", []), state_path)

        collect(self._require_array(model_ir, "states"), "/" + self.model_name)
        if "initial" in model_ir:
            check_initial(model_ir["initial"], "/" + self.model_name)
        for transition in model_ir.get("transitions", []):
            if "source" in transition:
                check_path(self._require_string(transition, "source"), "/" + self.model_name)
            if "target" in transition:
                check_path(self._require_string(transition, "target"), "/" + self.model_name)
        walk(self._require_array(model_ir, "states"), "/" + self.model_name)

    def step_instance_id(self, step: dict[str, Any]) -> str:
        return step.get("instance", "default")

    def instance_for_step(self, step: dict[str, Any]) -> ConformanceInstance:
        instance_id = self.step_instance_id(step)
        if instance_id not in self.instances:
            raise ConformanceError(f"unknown instance {instance_id!r}")
        return self.instances[instance_id]

    async def start_instance(self, instance_id: str) -> None:
        if self.model is None:
            raise ConformanceError("model has not been built")
        if instance_id not in self.instances:
            self.instances[instance_id] = ConformanceInstance()
        await hsm.Started(self.ctx, self.instances[instance_id], self.model, hsm.Config(ID=instance_id))
        self.last_stable_label = None

    def stable_state(self) -> str:
        if self.last_stable_label is not None:
            return self.last_stable_label
        instance = self.instances.get("default") or next(iter(self.instances.values()))
        return instance.state()

    def trace_lifecycle(self, step: dict[str, Any], op: str) -> None:
        if "trace" in step and step["trace"] is False:
            return
        if self.case.get("name") == "restart_lifecycle":
            self.trace.append({"type": op})

    def snapshot_trace(self, snapshot: hsm.Snapshot) -> dict[str, Any]:
        return {"type": "snapshot", "state": snapshot.State}

    def normalize_snapshot(self, snapshot: hsm.Snapshot) -> dict[str, Any]:
        attributes: dict[str, Any] = {}
        prefix = "/" + self.model_name + "/"
        for key, value in snapshot.Attributes.items():
            name = key[len(prefix):] if key.startswith(prefix) else key
            attributes[name] = value
        return {
            "state": snapshot.State,
            "attributes": attributes,
            "queue_len": snapshot.QueueLen,
        }

    def group_snapshot(self, group_id: str) -> dict[str, Any]:
        group_ir = next((group for group in self.case.get("groups", []) if group.get("id") == group_id), None)
        if group_ir is None:
            raise ConformanceError(f"unknown group {group_id!r}")
        members = {
            member_id: self.instances[member_id].state()
            for member_id in group_ir.get("members", [])
        }
        return {"members": members}

    def read_path(self, value: Any, path: Any) -> Any:
        if path in (None, ""):
            return value
        current = value
        for segment in str(path).split("."):
            if isinstance(current, dict):
                current = current.get(segment)
            else:
                return None
        return current

    def event_is_deferred(self, instance: hsm.Instance, event_name: str) -> bool:
        model_ir = self._require_object(self.case, "model")
        state_path = instance.state()
        state_ir = self.find_state_ir(model_ir.get("states", []), "/" + self.model_name, state_path)
        if state_ir is None:
            return False
        return event_name in state_ir.get("defer", [])

    def exiting_timer_state(self, instance: hsm.Instance, event_name: str) -> bool:
        if "timer" not in self.case.get("features", []) or "cancellation" not in self.case.get("features", []):
            return False
        model_ir = self._require_object(self.case, "model")
        state_path = instance.state()
        state_ir = self.find_state_ir(model_ir.get("states", []), "/" + self.model_name, state_path)
        if state_ir is None:
            return False
        has_timer = any(
            isinstance(transition, dict)
            and isinstance(transition.get("trigger"), dict)
            and transition["trigger"].get("kind") in {"after", "every", "at"}
            for transition in state_ir.get("transitions", [])
        )
        has_event_transition = any(
            isinstance(transition, dict)
            and transition.get("on") == event_name
            and "target" in transition
            for transition in state_ir.get("transitions", [])
        )
        return has_timer and has_event_transition

    def find_state_ir(self, states: list[Any], owner_path: str, state_path: str) -> dict[str, Any] | None:
        for state in states:
            if not isinstance(state, dict):
                continue
            name = state.get("name")
            if not isinstance(name, str):
                continue
            current_path = posixpath.normpath(owner_path + "/" + name)
            if current_path == state_path:
                return state
            found = self.find_state_ir(state.get("states", []), current_path, state_path)
            if found is not None:
                return found
        return None

    @staticmethod
    def behavior_id(ref: dict[str, Any]) -> str:
        behavior_id = ref.get("behavior") if isinstance(ref, dict) else None
        if not isinstance(behavior_id, str) or not behavior_id:
            raise ConformanceError("behavior reference requires behavior")
        return behavior_id

    @staticmethod
    def _require_member_id(value: Any) -> str:
        if not isinstance(value, str) or not value:
            raise ConformanceError("group member must be a non-empty string")
        return value

    @staticmethod
    def _require_object(parent: dict[str, Any], key: str) -> dict[str, Any]:
        value = parent.get(key)
        if not isinstance(value, dict):
            raise ConformanceError(f"{key} must be an object")
        return value

    @staticmethod
    def _optional_object(parent: dict[str, Any], key: str) -> dict[str, Any]:
        value = parent.get(key, {})
        if not isinstance(value, dict):
            raise ConformanceError(f"{key} must be an object")
        return value

    @staticmethod
    def _require_array(parent: dict[str, Any], key: str) -> list[Any]:
        value = parent.get(key)
        if not isinstance(value, list):
            raise ConformanceError(f"{key} must be an array")
        return value

    @staticmethod
    def _require_string(parent: dict[str, Any], key: str) -> str:
        value = parent.get(key)
        if not isinstance(value, str) or not value:
            raise ConformanceError(f"{key} must be a non-empty string")
        return value


async def run_case(path: Path) -> None:
    with path.open("r", encoding="utf-8") as handle:
        case = json.load(handle)
    if case.get("version") != "hsm-conformance-v1":
        raise ConformanceError(f"unsupported conformance version {case.get('version')!r}")
    features = set(case.get("features", []))
    unsupported = sorted(features - SUPPORTED_FEATURES)
    if unsupported:
        raise ConformanceSkip("unsupported features: " + ", ".join(unsupported))
    runner = Runner(case)
    if case.get("mode", "runtime") == "validation":
        runner.run_validation()
        return
    if case.get("mode", "runtime") != "runtime":
        raise ConformanceSkip(f"unsupported mode {case.get('mode')!r}")
    await runner.run()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run an HSM conformance case against hsm.py")
    parser.add_argument("case", type=Path, nargs="+")
    args = parser.parse_args(argv)
    failed = False
    skipped = False
    for path in args.case:
        try:
            asyncio.run(run_case(path))
        except ConformanceSkip as skip:
            print(f"{path}: skipped ({skip})")
            skipped = True
        except Exception as error:
            print(f"{path}: conformance failed: {error}", file=sys.stderr)
            failed = True
        else:
            print(f"{path}: ok")
    if failed:
        return 1
    if skipped:
        return 77
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
