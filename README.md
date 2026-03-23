# hsm — Hierarchical State Machine

A unified, cross-language hierarchical state machine library built on a single [DSL specification](dsl.md).

Every implementation shares the same compile-time DSL, the same semantics, and the same API surface — only the host language changes.

## Language Implementations

| Language | Module | Status |
|----------|--------|--------|
| C++ | [hsm.cpp](hsm.cpp/) | Active |
| Dart | [hsm.dart](hsm.dart/) | Active |
| Go | [hsm.go](hsm.go/) | Active |
| JavaScript/TypeScript | [hsm.js](hsm.js/) | Active |
| Python | [hsm.py](hsm.py/) | Active |
| Rust | [hsm.rs](hsm.rs/) | Active |
| Zig | [hsm.zig](hsm.zig/) | Active |

## DSL

All implementations conform to the [HSM DSL Reference](dsl.md) — a language-agnostic specification that defines:

- **Model definition** — `hsm.Define`, `hsm.State`, `hsm.Final`
- **Pseudostates** — `hsm.Choice`, `hsm.ShallowHistory`, `hsm.DeepHistory`
- **Transitions** — `hsm.Transition`, `hsm.Initial`, `hsm.Target`, `hsm.Source`
- **Events** — `hsm.On`, `hsm.OnCall`, `hsm.When` / `hsm.OnSet`
- **Timing** — `hsm.After`, `hsm.Every`, `hsm.At`
- **Behaviors** — `hsm.Entry`, `hsm.Exit`, `hsm.Activity`, `hsm.Effect`
- **Guards & deferral** — `hsm.Guard`, `hsm.Defer`
- **Metadata** — `hsm.Attribute`, `hsm.Operation`
- **Composition** — `hsm.MakeGroup`
- **Snapshotting** — `hsm.TakeSnapshot`

All DSL functions use **PascalCase** across every language for a 1:1 API mapping.

### Quick Example

```
TrafficLight = hsm.Define("TrafficLight",
    hsm.Initial(hsm.Target("/TrafficLight/Red")),
    hsm.State("Red",
        hsm.Transition(hsm.After(30s), hsm.Target("/TrafficLight/Green")),
    ),
    hsm.State("Green",
        hsm.Transition(hsm.After(25s), hsm.Target("/TrafficLight/Yellow")),
    ),
    hsm.State("Yellow",
        hsm.Transition(hsm.After(5s), hsm.Target("/TrafficLight/Red")),
    ),
)
```

### Design Principles

- **No parallel regions** — concurrent behavior is modeled with submachines, not orthogonal states.
- **Run-to-completion** — each event is fully processed before the next is dequeued.
- **Pure guards, effects, and actions** — no side effects in transition logic.
- **Compile-time construction** — models are validated at build time, not runtime.
- **Events as the only interface** — interact via `Dispatch`; observe via callbacks, channels, or futures.

See the full specification: **[dsl.md](dsl.md)**

## Repository Structure

This is a monorepo using git submodules. Each `hsm.<lang>` directory is an independent repository.

```
hsm/
├── README.md        # this file
├── dsl.md           # language-agnostic DSL specification
├── hsm.cpp/         # C++ implementation
├── hsm.dart/        # Dart implementation
├── hsm.go/          # Go implementation
├── hsm.js/          # JavaScript/TypeScript implementation
├── hsm.py/          # Python implementation
├── hsm.rs/          # Rust implementation
└── hsm.zig/         # Zig implementation
```

## Getting Started

Clone with submodules:

```sh
git clone --recurse-submodules https://github.com/stateforward/hsm.git
```

Or initialize submodules after cloning:

```sh
git clone https://github.com/stateforward/hsm.git
cd hsm
git submodule update --init --recursive
```

Then navigate to the language implementation of your choice — each has its own README with language-specific setup instructions.

## License

Each language implementation maintains its own license. See the individual submodule directories for details.
