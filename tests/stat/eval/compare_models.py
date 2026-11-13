"""
Runs the intent eval against several MLX models, one model server at a time, and prints accuracy,
speed, cold start and memory for each, for choosing the model size (issue #9):
    uv run --group llm python tests/stat/eval/compare_models.py \\
        mlx-community/Qwen3-4B-Instruct-2507-4bit mlx-community/Qwen2.5-7B-Instruct-4bit

Each model is downloaded first, so download time is not counted as cold start. Thinking is turned
off, as the app needs it off (the answer has a 300-token budget); templates without it ignore it.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).parent
RESULTS_FILE = EVAL_DIR / "results.jsonl"
PORT = 8090
READY_TIMEOUT_S = 300
TEMPLATE_ARGS = '{"enable_thinking": false}'
_UNITS_MB = {"KB": 1 / 1024, "MB": 1.0, "GB": 1024.0}


def parse_footprint(text: str) -> float:
    """The process total from macOS `footprint`, in MB. It counts GPU (Metal) memory, unlike RSS."""
    match = re.search(r"Footprint:\s+([\d.]+)\s+(KB|MB|GB)", text)
    if not match:
        raise ValueError(f"unexpected footprint output: {text[:200]!r}")
    return float(match.group(1)) * _UNITS_MB[match.group(2)]


def _post_chat(model: str) -> None:
    body = json.dumps(
        {"model": model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1}
    ).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=READY_TIMEOUT_S) as response:
        response.read()


def _wait_until_listening(server: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"model server exited with {server.returncode}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v1/models", timeout=2):
                if server.poll() is None:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    raise TimeoutError("model server did not start")


def _recorded_runs() -> list[str]:
    return RESULTS_FILE.read_text().splitlines() if RESULTS_FILE.exists() else []


def measure(model: str) -> dict[str, Any]:
    from huggingface_hub import snapshot_download

    snapshot_download(model)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            raise RuntimeError(f"port {PORT} is taken; another server would answer for {model}")
    command = [sys.executable, "-m", "mlx_lm.server", "--model", model, "--port", str(PORT)]
    server = subprocess.Popen(
        [*command, "--chat-template-args", TEMPLATE_ARGS],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        started = time.perf_counter()
        _wait_until_listening(server)
        _post_chat(model)  # the first request includes loading the weights
        cold_s = time.perf_counter() - started
        env = {**os.environ, "LLM_BASE_URL": f"http://127.0.0.1:{PORT}/v1", "LLM_MODEL": model}
        eval_test = str(EVAL_DIR / "test_intent_eval.py")
        before = len(_recorded_runs())
        # The eval's own thresholds may fail; the numbers are what this run is for.
        subprocess.run(
            [sys.executable, "-m", "pytest", "-m", "eval", "-q", eval_test], env=env, check=False
        )
        runs = _recorded_runs()
        if len(runs) != before + 1 or json.loads(runs[-1])["model"] != model:
            raise RuntimeError(f"the eval did not record exactly one run for {model}")
        run = json.loads(runs[-1])
        footprint = subprocess.run(
            ["footprint", "-p", str(server.pid)], capture_output=True, text=True, check=True
        )
        memory_mb = parse_footprint(footprint.stdout)
        return {**run, "cold_start_s": round(cold_s, 1), "memory_mb": memory_mb}
    finally:
        server.terminate()
        server.wait(timeout=30)


def main(models: list[str]) -> int:
    if not models:
        print(__doc__, file=sys.stderr)
        return 2
    print("| Model | Cases | Held-out | Corrections | Mean / p95 s | Cold start s | Memory GB |")
    print("|---|---|---|---|---|---|---|")
    for model in models:
        r = measure(model)
        s, lat = r["by_set"], r["latency"]
        print(
            f"| {model.split('/')[-1]} | {s['cases']} | {s['heldout']} | {s['corrections']} "
            f"| {lat['mean_s']} / {lat['p95_s']} | {r['cold_start_s']} "
            f"| {r['memory_mb'] / 1024:.1f} |",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
