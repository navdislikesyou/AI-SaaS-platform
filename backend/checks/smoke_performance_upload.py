r"""Live end-to-end smoke test for Performance dataset upload.

Starts a real uvicorn server as a subprocess and drives it over real HTTP, so
this exercises the multipart parser, the upload service, the manifest, the job
store, the worker thread, the real pandas loader, the analyzers, and artifact
serving. Nothing is stubbed and no ASGI test transport is used.

Two deliberate test-setup choices, neither of which weakens what is being
verified:

* The subprocess is started with all three ``*_AGENT_ENABLED`` flags off. The
  smoke test touches only the Performance dataset and job routes, which never
  call an agent. Building the registry would otherwise construct the Knowledge
  adapter and load its embedding model, which takes minutes and is not what this
  script is testing. No production code path is changed.
* Uploads are redirected to a temporary directory, so a smoke run writes nothing
  into the repository.

If the server does not become ready within ``STARTUP_TIMEOUT_SECONDS`` the script
reports the reason, dumps the tail of the server log, and exits non-zero. It never
reports success for a run that did not reach the endpoints.

Run: .venv\Scripts\python.exe checks\smoke_performance_upload.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

HOST = "127.0.0.1"
PORT = int(os.environ.get("SMOKE_PORT", "8123"))
BASE = f"http://{HOST}:{PORT}/api/v1"

#: Bounded budget for the lifespan to finish. Generous enough for a cold import
#: of pandas and matplotlib, far short of "wait and hope". Exceeding it is a
#: failure with a reason, not a longer wait.
STARTUP_TIMEOUT_SECONDS = float(os.environ.get("SMOKE_STARTUP_TIMEOUT", "90"))

#: Per-job budget. The visualize operation renders charts, so this is the
#: slowest single step.
JOB_TIMEOUT_SECONDS = 240.0

#: Three rows across every dimension column the analyzers group by.
CSV = (
    b"\n".join(
        [
            b"date,sales,profit,units_sold,sales_target,profit_target,employee_id,"
            b"employee_name,department,product,region,customer_segment,sales_channel",
            b"2026-01-01,1000,200,4,1100,220,E-1,Aarti Rao,Sales,Widget,North,SMB,Direct",
            b"2026-02-01,1500,300,6,1400,280,E-2,Omkar Shenwai,Sales,Gadget,South,"
            b"Enterprise,Partner",
            b"2026-03-01,2200,440,9,2100,420,E-1,Aarti Rao,Sales,Gadget,North,SMB,Direct",
        ]
    )
    + b"\n"
)

failures: list[str] = []
checks_run = 0
endpoint_reached = False


def check(label: str, condition: bool, detail: str = "") -> None:
    """Record a pass or fail for one assertion.

    Args:
        label: What was checked.
        condition: Whether it held.
        detail: Extra context printed on failure.
    """
    global checks_run

    checks_run += 1

    if condition:
        print(f"  PASS  {label}", flush=True)
    else:
        print(f"  FAIL  {label}  {detail}", flush=True)
        failures.append(label)


def section(title: str) -> None:
    """Print a section header.

    Args:
        title: Section name.
    """
    print(f"\n{title}", flush=True)


def log_tail(path: Path, lines: int = 40) -> str:
    """Return the last lines of the server log.

    Args:
        path: The log file.
        lines: How many lines to return.

    Returns:
        The tail, or a note that the log is empty.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "<server log could not be read>"

    if not content:
        return "<server log is empty>"

    return "\n".join(content[-lines:])


def stop_server(process: subprocess.Popen[bytes]) -> None:
    """Terminate the server and everything it spawned.

    Uses the process tree on Windows, because uvicorn with reload or a spawned
    worker can outlive a plain terminate. Safe to call more than once.

    Args:
        process: The server process handle.
    """
    if process.poll() is not None:
        return

    print("  ..    stopping server", flush=True)

    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )
        else:
            process.terminate()
    except OSError as exc:
        print(f"  WARN  terminate failed: {exc}", flush=True)

    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print("  WARN  server would not die", flush=True)

    print(
        f"  ..    server stopped (exit code {process.returncode}; "
        "a non-zero code is expected after a forced kill)",
        flush=True,
    )


def wait_for_server(client: httpx.Client, log_path: Path) -> bool:
    """Poll the health endpoint until the server answers or the budget runs out.

    Reports each attempt, the elapsed time, and the last error, so a startup
    failure is diagnosable from the output alone rather than inferred from a
    timeout.

    Args:
        client: HTTP client bound to the server.
        log_path: The server log, dumped if the budget is exceeded.

    Returns:
        True once the server responded.
    """
    started = time.monotonic()
    deadline = started + STARTUP_TIMEOUT_SECONDS
    last_problem = "no attempt made"
    attempt = 0

    while time.monotonic() < deadline:
        attempt += 1
        elapsed = time.monotonic() - started

        if process_exited_early():
            print(
                f"  FAIL  server process exited during startup after " f"{elapsed:.1f}s",
                flush=True,
            )
            print("\n--- server log ---\n" + log_tail(log_path), flush=True)

            return False

        try:
            response = client.get(f"{BASE}/health")

            if response.status_code == 200:
                print(
                    f"  ..    server ready after {elapsed:.1f}s " f"({attempt} attempt(s))",
                    flush=True,
                )

                return True

            last_problem = f"HTTP {response.status_code}"

        except httpx.HTTPError as exc:
            last_problem = f"{exc.__class__.__name__}: {exc}"

        print(
            f"  ..    attempt {attempt} at {elapsed:5.1f}s: {last_problem}",
            flush=True,
        )

        time.sleep(1.0)

    elapsed = time.monotonic() - started

    print(
        f"  FAIL  server was not ready within {STARTUP_TIMEOUT_SECONDS:.0f}s "
        f"(last problem: {last_problem})",
        flush=True,
    )
    print("\n--- server log ---\n" + log_tail(log_path), flush=True)

    return False


_process: subprocess.Popen[bytes] | None = None


def process_exited_early() -> bool:
    """Report whether the server process died before becoming ready.

    Returns:
        True when the process has exited.
    """
    if _process is None:
        return False

    return _process.poll() is not None


def poll_job(client: httpx.Client, job_id: str) -> dict:
    """Poll a job to a terminal state.

    Args:
        client: HTTP client bound to the server.
        job_id: The job to poll.

    Returns:
        The final status payload, or an empty dict on timeout.
    """
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    final: dict = {}

    while time.monotonic() < deadline:
        final = client.get(f"{BASE}/performance/jobs/{job_id}").json()["data"]

        if final["status"] in ("completed", "failed"):
            return final

        time.sleep(0.4)

    print(f"  FAIL  job {job_id} did not finish in {JOB_TIMEOUT_SECONDS:.0f}s", flush=True)

    return final


def main() -> int:
    """Run the smoke test and report.

    Returns:
        Process exit code: 0 when every check passed.
    """
    global _process

    tmp = Path(tempfile.mkdtemp(prefix="perf-smoke-"))
    csv_path = tmp / "Quarterly Sales.csv"
    csv_path.write_bytes(CSV)
    xls_path = tmp / "legacy.xls"
    xls_path.write_bytes(b"legacy")
    empty_path = tmp / "empty.csv"
    empty_path.write_bytes(b"")
    fake_xlsx = tmp / "disguised.xlsx"
    fake_xlsx.write_bytes(CSV)

    upload_dir = tmp / "uploads"
    manifest_path = upload_dir / "datasets.json"
    log_path = tmp / "server.log"

    # Agent construction is off and storage is redirected. See the module
    # docstring: this is test setup, and it is what keeps the run fast and keeps
    # the repository clean.
    child_env = dict(os.environ)
    child_env.update(
        {
            "KNOWLEDGE_AGENT_ENABLED": "false",
            "AUTOMATION_AGENT_ENABLED": "false",
            "PERFORMANCE_AGENT_ENABLED": "false",
            "PERFORMANCE_UPLOAD_DIR": str(upload_dir),
            "PERFORMANCE_UPLOAD_MANIFEST_PATH": str(manifest_path),
            "LOG_LEVEL": "WARNING",
        }
    )

    print(f"workdir  : {Path.cwd()}")
    print(f"tmpdir   : {tmp}")
    print(f"endpoint : {BASE}")
    print(f"startup  : {STARTUP_TIMEOUT_SECONDS:.0f}s budget")

    log_handle = log_path.open("w", encoding="utf-8", errors="replace")

    _process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        cwd=str(Path.cwd()),
        env=child_env,
    )

    started = time.monotonic()

    try:
        with httpx.Client(base_url=f"http://{HOST}:{PORT}", timeout=30.0) as client:
            section("[0] Server startup")

            if not wait_for_server(client, log_path):
                return 1

            global endpoint_reached
            endpoint_reached = True

            section("[1] Upload a CSV")

            upload = client.post(
                f"{BASE}/performance/datasets",
                files={"file": (csv_path.name, CSV, "text/csv")},
            )
            check("returns 201", upload.status_code == 201, upload.text[:200])

            if upload.status_code != 201:
                return 1

            dataset = upload.json()["data"]["dataset"]
            dataset_id = dataset["dataset_id"]

            check(
                "reports the display filename",
                dataset["filename"] == "Quarterly Sales.csv",
                dataset["filename"],
            )
            check(
                "reports normalized columns",
                dataset["column_names"][:3] == ["date", "sales", "profit"],
                str(dataset["column_names"][:3]),
            )
            check("marks it ready", dataset["status"] == "ready")

            section("[2] Rejections")

            for label, path in [
                ("legacy .xls", xls_path),
                ("empty file", empty_path),
                ("CSV renamed .xlsx", fake_xlsx),
            ]:
                response = client.post(
                    f"{BASE}/performance/datasets",
                    files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
                )
                body = response.json()

                check(
                    f"{label} refused with 422 VALIDATION_ERROR",
                    response.status_code == 422 and body["error"]["code"] == "VALIDATION_ERROR",
                    str(response.status_code),
                )

            section("[3] List includes the sample and the upload")

            listing = client.get(f"{BASE}/performance/datasets").json()["data"]
            ids = [entry["dataset_id"] for entry in listing["datasets"]]

            check("sample is listed first", ids[0] == "sample", str(ids))
            check("uploaded dataset is listed", dataset_id in ids, str(ids))
            check(
                "reports the 25 MiB limit",
                listing["max_upload_bytes"] == 26214400,
                str(listing["max_upload_bytes"]),
            )

            section("[4] Run every operation against the uploaded dataset")

            for operation in [
                "load_dataset",
                "compute_kpis",
                "compare_periods",
                "analyze",
                "visualize",
            ]:
                created = client.post(
                    f"{BASE}/performance/jobs",
                    json={"operation": operation, "dataset_id": dataset_id},
                )
                check(
                    f"{operation} accepted with 202", created.status_code == 202, created.text[:160]
                )

                if created.status_code != 202:
                    continue

                final = poll_job(client, created.json()["data"]["job_id"])

                check(
                    f"{operation} completed",
                    final.get("status") == "completed",
                    str(final.get("error"))[:300],
                )

                if operation == "compute_kpis" and final.get("status") == "completed":
                    total = final["result"]["overall"]["total_sales"]
                    check("KPIs from the uploaded rows (4700)", total == 4700, str(total))

                if operation == "load_dataset" and final.get("status") == "completed":
                    reported = final["result"]["file_path"]
                    check(
                        "load_dataset reports a bare filename",
                        "/" not in reported and "\\" not in reported,
                        reported,
                    )

                if operation == "visualize" and final.get("status") == "completed":
                    chart = final["result"]["visualizations"][0]
                    served = client.get(
                        f"{BASE}/performance/jobs/{final['job_id']}"
                        f"/artifacts/{chart['filename']}"
                    )
                    check(
                        "generated chart is downloadable",
                        served.status_code == 200 and served.headers["content-type"] == "image/png",
                        str(served.status_code),
                    )
                    check("chart is not empty", chart["size_bytes"] > 0, str(chart["size_bytes"]))

            section("[5] Unknown and tampered dataset ids")

            for bad_id in [
                "does-not-exist",
                "../../performance_agent/data/Financials_standardized.csv",
            ]:
                response = client.post(
                    f"{BASE}/performance/jobs",
                    json={"operation": "compute_kpis", "dataset_id": bad_id},
                )
                check(
                    f"{bad_id[:28]} refused with 404 DATASET_NOT_FOUND",
                    response.status_code == 404
                    and response.json()["error"]["code"] == "DATASET_NOT_FOUND",
                    str(response.status_code),
                )

            section("[6] The sample dataset still works")

            created = client.post(
                f"{BASE}/performance/jobs",
                json={"operation": "load_dataset", "dataset_id": "sample"},
            )
            check("sample job accepted", created.status_code == 202)

            if created.status_code == 202:
                final = poll_job(client, created.json()["data"]["job_id"])
                check(
                    "sample dataset completes",
                    final.get("status") == "completed",
                    str(final.get("error"))[:200],
                )

            section("[7] The server-side file_path workflow still works")

            created = client.post(
                f"{BASE}/performance/jobs",
                json={
                    "operation": "load_dataset",
                    "file_path": "performance_agent/data/Financials_standardized.csv",
                },
            )
            check("file_path job accepted", created.status_code == 202)

            if created.status_code == 202:
                final = poll_job(client, created.json()["data"]["job_id"])
                check(
                    "file_path job completes",
                    final.get("status") == "completed",
                    str(final.get("error"))[:200],
                )

            section("[8] Both references at once is rejected")

            response = client.post(
                f"{BASE}/performance/jobs",
                json={
                    "operation": "compute_kpis",
                    "dataset_id": dataset_id,
                    "file_path": "performance_agent/data/Financials_standardized.csv",
                },
            )
            check("rejected with 422", response.status_code == 422, str(response.status_code))

            section("[9] No server paths in dataset responses")

            responses = [
                (
                    "upload",
                    client.post(
                        f"{BASE}/performance/datasets",
                        files={"file": (csv_path.name, CSV, "text/csv")},
                    ),
                ),
                ("list", client.get(f"{BASE}/performance/datasets")),
            ]

            for label, response in responses:
                text = response.text
                check(
                    f"{label} leaks no path or stored name",
                    "uploads" not in text
                    and "performance_agent" not in text
                    and ":\\" not in text
                    and tmp.name not in text,
                    text[:300],
                )
            section("[10] On disk: generated, contained, collision-free")

            stored = sorted(upload_dir.glob("*.csv")) + sorted(upload_dir.glob("*.xlsx"))

            check(
                "at least two datasets stored",
                len(stored) >= 2,
                str([p.name for p in stored]),
            )
            check(
                "no rejected file was stored",
                not any(
                    token in p.name for p in stored for token in ("legacy", "empty", "disguised")
                ),
                str([p.name for p in stored]),
            )
            # A stored name is `<uuid>_<safe-stem><ext>`. The readable stem is
            # deliberate and mirrors the Knowledge and Automation uploads, so the
            # property that matters is the generated prefix plus containment --
            # not the absence of the client's words.
            check(
                "every stored name is prefixed with a generated id",
                all(re.fullmatch(r"[0-9a-f]{32}_[A-Za-z0-9._-]+", p.name) for p in stored),
                str([p.name for p in stored]),
            )
            check(
                "no stored name contains a separator or traversal",
                all(
                    "/" not in p.name and "\\" not in p.name and ".." not in p.name for p in stored
                ),
                str([p.name for p in stored]),
            )
            check(
                "two uploads of one filename did not collide",
                len({p.name for p in stored}) == len(stored),
                str([p.name for p in stored]),
            )
            check(
                "everything stayed inside the upload directory",
                all(p.parent.resolve() == upload_dir.resolve() for p in stored),
                str([p.parent for p in stored]),
            )
            check(
                "sample dataset untouched",
                Path("performance_agent/data/Financials_standardized.csv").is_file(),
                "packaged sample missing",
            )
    except KeyboardInterrupt:
        print("\n  FAIL  interrupted before the run finished", flush=True)
        failures.append("interrupted")

        return 1

    finally:
        stop_server(_process)
        log_handle.close()

        elapsed = time.monotonic() - started
        print(f"\nelapsed  : {elapsed:.1f}s")
        print(f"checks   : {checks_run}")

    print("=" * 60)

    if not endpoint_reached:
        print("RESULT   : FAILED - the server never became ready, " "so no endpoint was exercised")

        return 1

    if failures:
        print(f"RESULT   : FAILED - {len(failures)} of {checks_run} check(s)")

        for item in failures:
            print(f"  - {item}")

        return 1

    print(f"RESULT   : PASSED - all {checks_run} checks")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
