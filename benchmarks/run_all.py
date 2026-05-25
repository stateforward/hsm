import json
import subprocess
import sys
import os
import time

DEFAULT_WARMUP_MS = max(1, int(os.environ.get("HSM_BENCH_WARMUP_MS", "250")))
DEFAULT_DURATION_MS = max(1, int(os.environ.get("HSM_BENCH_DURATION_MS", "2000")))
DEFAULT_VALIDATE = os.environ.get("HSM_BENCH_VALIDATE", "0")

# Define the list of benchmarks to run.
# Each entry requires a 'name', 'build_cmd' (optional), and 'run_cmd'.
# Traffic-light benchmark contract:
# - each counted operation submits one external event;
# - the benchmark waits until that event has fully run to completion before
#   submitting the next event;
# - validation mode runs a deterministic CarArrival/TimerEvent/TimerEvent/
#   TimerEvent sequence and fails if state/effects do not match.
BENCHMARKS = [
    {
        "name": "C++",
        "dir": "hsm.cpp",
        "build_cmd": ["clang++", "-std=c++20", "-I./include", "-O3", "bench/traffic_light_bench.cpp", "-o", "bench_traffic_light"],
        "run_cmd": ["./bench_traffic_light"]
    },
    {
        "name": "JavaScript (Node)",
        "dir": "hsm.js",
        "build_cmd": [],
        "run_cmd": ["node", "benchmark/traffic_light_bench.js"]
    },
    {
        "name": "TypeScript",
        "dir": "hsm.ts",
        "build_cmd": [],
        "run_cmd": ["npx", "tsx", "benchmark/traffic_light_bench.ts"]
    },
    {
        "name": "Python",
        "dir": "hsm.py",
        "build_cmd": [],
        "run_cmd": ["python3", "bench/traffic_light_bench.py"],
        "env": {"PYTHONPATH": "."}
    },
    {
        "name": "Java",
        "dir": "hsm.java",
        "build_cmd": [
            "javac", "-d", "build/classes",
            "src/main/java/com/stateforward/hsm/Hsm.java",
            "benchmark/TrafficLightBench.java"
        ],
        "run_cmd": ["java", "-cp", "build/classes", "com.stateforward.hsm.TrafficLightBench"]
    },
    {
        "name": "Go",
        "dir": "hsm.go",
        "build_cmd": ["go", "build", "-o", "bench_traffic_light", "cmd/bench_traffic_light/main.go"],
        "run_cmd": ["./bench_traffic_light"]
    },
    {
        "name": "Zig",
        "dir": "hsm.zig",
        "build_cmd": ["zig", "build", "traffic_light_bench", "-Doptimize=ReleaseFast"],
        "run_cmd": ["zig-out/bin/traffic_light_bench"]
    },
    {
        "name": "Rust",
        "dir": "hsm.rs",
        "build_cmd": ["cargo", "build", "--release", "--bin", "traffic_light_bench"],
        "run_cmd": ["target/release/traffic_light_bench"]
    },
    {
        "name": "C#",
        "dir": "hsm.cs/TrafficLightBench",
        "build_cmd": ["dotnet", "build", "-c", "Release", "--nologo"],
        "run_cmd": ["dotnet", "bin/Release/net10.0/TrafficLightBench.dll"]
    },
    {
        "name": "Dart",
        "dir": "hsm.dart",
        "build_cmd": [],
        "run_cmd": ["dart", "run", "benchmark/traffic_light_bench.dart"]
    }
]

def run_benchmark(bench, root_dir):
    name = bench["name"]
    bench_dir = os.path.join(root_dir, bench.get("dir", ""))
    
    print(f"--- Running {name} ---")
    
    env = os.environ.copy()
    env.update({
        "HSM_BENCH_WARMUP_MS": str(DEFAULT_WARMUP_MS),
        "HSM_BENCH_DURATION_MS": str(DEFAULT_DURATION_MS),
        "HSM_BENCH_VALIDATE": DEFAULT_VALIDATE,
    })
    if bench.get("env"):
        env.update(bench["env"])

    # Run build command if specified
    if bench.get("build_cmd"):
        print(f"Building {name}...")
        try:
            subprocess.run(bench["build_cmd"], cwd=bench_dir, check=True, capture_output=True, text=True, env=env)
        except subprocess.CalledProcessError as e:
            print(f"Error building {name}:\n{e.stderr}")
            return None
            
    # Run benchmark command
    print(f"Executing {name}...")
    try:
        # We expect the benchmark to print a single JSON object to stdout or stderr
        result = subprocess.run(bench["run_cmd"], cwd=bench_dir, check=True, capture_output=True, text=True, env=env)
        
        # Try to parse the last line (or the whole output) as JSON
        output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        
        # Extract json part if there's other output
        json_str = None
        for line in reversed(output.split('\n')):
            if line.startswith('{') and line.endswith('}'):
                json_str = line
                break
                
        if not json_str:
            print(f"Could not find JSON output for {name}. Output was:\n{output}")
            return None
            
        data = json.loads(json_str)
        print(f"Success! Throughput: {data.get('throughput_ops_per_sec', 0):,} ops/sec")
        return data
        
    except subprocess.CalledProcessError as e:
        print(f"Error running {name}:\n{e.stderr}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from {name}: {e}\nOutput was:\n{output}")
        return None
    except Exception as e:
        print(f"Unexpected error running {name}: {e}")
        return None

def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results = []
    failures = []
    
    print("Starting cross-language benchmarks...\n")
    print(
        f"Shared benchmark settings: warmup={DEFAULT_WARMUP_MS}ms, "
        f"measurement={DEFAULT_DURATION_MS}ms, "
        f"validate={DEFAULT_VALIDATE}\n"
    )
    
    for bench in BENCHMARKS:
        data = run_benchmark(bench, root_dir)
        if data:
            results.append(data)
        else:
            failures.append(bench["name"])
        print()
        
    # Write results to benchmarks/results.js so it can be loaded without a server
    results_file = os.path.join(root_dir, "benchmarks", "results.js")
    with open(results_file, 'w') as f:
        f.write("const benchmarkResults = ")
        json.dump(results, f, indent=2)
        f.write(";\n")
        
    print(f"Finished running benchmarks. Results saved to {results_file}")
    if failures:
        print(f"Failed benchmarks: {', '.join(failures)}", file=sys.stderr)
        sys.exit(1)
    
if __name__ == "__main__":
    main()
