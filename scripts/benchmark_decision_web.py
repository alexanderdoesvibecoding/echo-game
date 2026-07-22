#!/usr/bin/env python3
"""Benchmark deterministic startup decision-web generation."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from echo_adventure.config import GameConfig  # noqa: E402
from echo_adventure.decision_web import DecisionWeb, generate_decision_web  # noqa: E402
from echo_adventure.scenario_generator import generate_scenario  # noqa: E402

"""First ten possible seeds in the app's range of possible randomly-selected seeds (100,000 - 999,999,999)"""
DEFAULT_SEEDS = tuple(range(100001, 100011))
MIB = 1024 * 1024
LOG_DIRECTORY = PROJECT_ROOT / "log"


class _Tee:
    def __init__(self, *streams: TextIO) -> None:
        self._streams = streams

    def write(self, value: str) -> int:
        for stream in self._streams:
            stream.write(value)
        return len(value)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def _nonnegative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("value must be a finite nonnegative number")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark decision-web generation in isolated child processes. "
            "Timings exclude Python imports and report scenario generation separately."
        )
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=list(DEFAULT_SEEDS),
        metavar="SEED",
        help="scenario seeds to benchmark (default: 1 through 10)",
    )
    parser.add_argument(
        "--runs",
        type=_positive_int,
        default=1,
        help="number of isolated runs per seed (default: 1)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit one machine-readable JSON document",
    )
    parser.add_argument(
        "--no-console-output",
        "--no-console",
        "--quiet",
        action="store_true",
        help="write benchmark output only to the timestamped log file",
    )
    parser.add_argument(
        "--max-median-web-seconds",
        type=_nonnegative_float,
        help="fail if median web-generation time exceeds this threshold",
    )
    parser.add_argument(
        "--max-peak-rss-mib",
        type=_nonnegative_float,
        help="fail if any run's peak resident memory exceeds this threshold",
    )
    parser.add_argument("--_worker-seed", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--_worker-run", type=int, help=argparse.SUPPRESS)
    return parser


def _peak_rss_bytes() -> int | None:
    try:
        import resource
    except ImportError:
        return None

    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform != "darwin":
        peak *= 1024
    return peak


def _optimal_route_metrics(web: DecisionWeb) -> dict[str, int | bool]:
    ordinary_targets: set[str] = set()
    all_targets: set[str] = set()
    enters_overtime = False
    node_id: str | None = web.root_node_id
    while node_id is not None:
        node = web.node(node_id)
        all_targets.add(node.card.primary_job_id)
        if node.card.event_scope != "follow-up":
            ordinary_targets.add(node.card.primary_job_id)
        transition = node.transitions[node.optimal_choice_id]
        enters_overtime = enters_overtime or transition.enters_overtime
        node_id = transition.next_node_id
    return {
        "ordinary_target_count": len(ordinary_targets),
        "all_target_count": len(all_targets),
        "optimal_route_enters_overtime": enters_overtime,
    }


def _worker_result(seed: int, run: int) -> dict[str, Any]:
    config = GameConfig(seed=seed)

    scenario_started = time.perf_counter()
    scenario = generate_scenario(config)
    scenario_seconds = time.perf_counter() - scenario_started

    web_started = time.perf_counter()
    web = generate_decision_web(scenario, config)
    web_seconds = time.perf_counter() - web_started

    nodes = len(web.nodes)
    edges = sum(len(node.transitions) for node in web.nodes.values())
    result = {
        "seed": seed,
        "run": run,
        "scenario_seconds": scenario_seconds,
        "web_seconds": web_seconds,
        "nodes": nodes,
        "edges": edges,
        "generation_attempt": web.generation_attempt,
        "optimal_completion_day": web.optimal_completion_day,
        "optimal_unfinished_job_days": web.optimal_unfinished_job_days,
        "nodes_per_second": nodes / web_seconds if web_seconds else None,
        "peak_rss_bytes": _peak_rss_bytes(),
    }
    result.update(_optimal_route_metrics(web))
    return result


def _run_isolated(seed: int, run: int) -> tuple[dict[str, Any] | None, str | None]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--_worker-seed",
        str(seed),
        "--_worker-run",
        str(run),
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        return None, detail or f"worker exited with status {completed.returncode}"
    try:
        return json.loads(completed.stdout), None
    except json.JSONDecodeError as error:
        return None, f"worker returned invalid JSON: {error}"


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _describe(values: Sequence[float]) -> dict[str, float]:
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "p95": _percentile(values, 0.95),
        "max": max(values),
    }


def _summary(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {}

    web_seconds = [float(result["web_seconds"]) for result in results]
    scenario_seconds = [float(result["scenario_seconds"]) for result in results]
    nodes = [float(result["nodes"]) for result in results]
    edges = [float(result["edges"]) for result in results]
    memory = [
        float(result["peak_rss_bytes"])
        for result in results
        if result["peak_rss_bytes"] is not None
    ]
    return {
        "successful_runs": len(results),
        "scenario_seconds": _describe(scenario_seconds),
        "web_seconds": _describe(web_seconds),
        "nodes": _describe(nodes),
        "edges": _describe(edges),
        "peak_rss_bytes": _describe(memory) if memory else None,
        "aggregate_nodes_per_second": sum(nodes) / sum(web_seconds),
    }


def _environment() -> dict[str, str]:
    return {
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def _new_log_path() -> Path:
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S_%f%z")
    return LOG_DIRECTORY / f"{timestamp}.log"


def _format_memory(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value / MIB:.1f} MiB"


def _print_header(environment: dict[str, str], seeds: Sequence[int], runs: int) -> None:
    print("Decision-web startup benchmark")
    print(
        f"Python {environment['python_version']} ({environment['machine']}); "
        f"{len(seeds)} seed(s), {runs} run(s) per seed"
    )
    print("Timings exclude imports; peak RSS includes the Python process and retained web.")
    print()
    print(
        f"{'Seed':>10} {'Run':>4} {'Scenario':>10} {'Web':>10} "
        f"{'Nodes':>9} {'Edges':>9} {'Try':>3} {'Day':>4} {'UJD':>7} "
        f"{'Ord':>3} {'All':>3} {'OT':>2} {'Nodes/s':>10} {'Peak RSS':>11}"
    )


def _print_result(result: dict[str, Any]) -> None:
    throughput = result["nodes_per_second"]
    throughput_text = f"{throughput:,.0f}" if throughput is not None else "n/a"
    overtime_text = "Y" if result["optimal_route_enters_overtime"] else "N"
    print(
        f"{result['seed']:>10} {result['run']:>4} "
        f"{result['scenario_seconds']:>9.4f}s {result['web_seconds']:>9.3f}s "
        f"{result['nodes']:>9,} {result['edges']:>9,} "
        f"{result['generation_attempt']:>3} {result['optimal_completion_day']:>4} "
        f"{result['optimal_unfinished_job_days']:>7,} "
        f"{result['ordinary_target_count']:>3} {result['all_target_count']:>3} "
        f"{overtime_text:>2} {throughput_text:>10} "
        f"{_format_memory(result['peak_rss_bytes']):>11}",
        flush=True,
    )


def _print_summary(summary: dict[str, Any], failures: Sequence[dict[str, Any]]) -> None:
    print()
    if summary:
        web = summary["web_seconds"]
        nodes = summary["nodes"]
        print(
            "Web time: "
            f"median {web['median']:.3f}s, mean {web['mean']:.3f}s, "
            f"p95 {web['p95']:.3f}s, range {web['min']:.3f}-{web['max']:.3f}s"
        )
        print(
            "Web size: "
            f"median {nodes['median']:,.0f} nodes, range "
            f"{nodes['min']:,.0f}-{nodes['max']:,.0f}; "
            f"aggregate {summary['aggregate_nodes_per_second']:,.0f} nodes/s"
        )
        peak_memory = summary["peak_rss_bytes"]
        if peak_memory:
            print(
                "Peak RSS: "
                f"median {_format_memory(peak_memory['median'])}, "
                f"maximum {_format_memory(peak_memory['max'])}"
            )
    if failures:
        print(f"Generation failures: {len(failures)}")


def _threshold_failures(
    args: argparse.Namespace,
    summary: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    if not summary:
        return failures
    median_limit = args.max_median_web_seconds
    median_web = summary["web_seconds"]["median"]
    if median_limit is not None and median_web > median_limit:
        failures.append(
            f"median web time {median_web:.3f}s exceeded {median_limit:.3f}s"
        )
    memory_limit = args.max_peak_rss_mib
    memory_summary = summary["peak_rss_bytes"]
    if memory_limit is not None and memory_summary:
        peak_mib = memory_summary["max"] / MIB
        if peak_mib > memory_limit:
            failures.append(
                f"peak RSS {peak_mib:.1f} MiB exceeded {memory_limit:.1f} MiB"
            )
    return failures


def _run_benchmark(args: argparse.Namespace) -> int:
    environment = _environment()
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if not args.json:
        _print_header(environment, args.seeds, args.runs)

    for seed in args.seeds:
        for run in range(1, args.runs + 1):
            result, error = _run_isolated(seed, run)
            if result is not None:
                results.append(result)
                if not args.json:
                    _print_result(result)
            else:
                failure = {"seed": seed, "run": run, "error": error}
                failures.append(failure)
                if not args.json:
                    print(f"{seed:>10} {run:>4} FAILED: {error}", flush=True)

    summary = _summary(results)
    threshold_failures = _threshold_failures(args, summary)
    payload = {
        "environment": environment,
        "configuration": {
            "seeds": args.seeds,
            "runs_per_seed": args.runs,
            "max_median_web_seconds": args.max_median_web_seconds,
            "max_peak_rss_mib": args.max_peak_rss_mib,
        },
        "results": results,
        "summary": summary,
        "failures": failures,
        "threshold_failures": threshold_failures,
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_summary(summary, failures)
        for failure in threshold_failures:
            print(f"Threshold failure: {failure}")

    if failures:
        return 1
    if threshold_failures:
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args._worker_seed is not None:
        run = args._worker_run if args._worker_run is not None else 1
        print(json.dumps(_worker_result(args._worker_seed, run)))
        return 0

    log_path = _new_log_path()
    with log_path.open("x", encoding="utf-8", buffering=1) as log_file:
        output = (
            log_file
            if args.no_console_output
            else _Tee(log_file, sys.stdout)
        )
        with redirect_stdout(output):
            return _run_benchmark(args)


if __name__ == "__main__":
    raise SystemExit(main())
