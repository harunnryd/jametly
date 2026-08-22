from __future__ import annotations

import asyncio
import io
import signal
import threading

import pytest

from jamly.bridge import (
    EXIT_CLEAN,
    EXIT_SIGNALLED,
    SHUTDOWN_SIGNALS,
    serve,
    shutdown_banner,
    startup_banner,
)


def test_shutdown_signals_cover_terminate_and_interrupt() -> None:
    assert signal.SIGTERM in SHUTDOWN_SIGNALS
    assert signal.SIGINT in SHUTDOWN_SIGNALS


def test_startup_banner_names_the_process_identity() -> None:
    banner = startup_banner(pid=4242)

    assert "4242" in banner
    assert "jamly" in banner


def test_shutdown_banner_names_the_reason_and_the_exit_code() -> None:
    banner = shutdown_banner("stdin closed", EXIT_CLEAN)

    assert "stdin closed" in banner
    assert str(EXIT_CLEAN) in banner


def test_exit_codes_distinguish_a_clean_close_from_a_signal() -> None:
    assert EXIT_CLEAN == 0
    assert EXIT_SIGNALLED != EXIT_CLEAN


async def test_serve_returns_the_clean_exit_code_on_stdin_eof() -> None:
    stdin = io.StringIO("")
    stdout = io.StringIO()

    code = await serve(stdin, stdout)

    assert code == EXIT_CLEAN


async def test_serve_drains_a_dispatched_request_before_returning() -> None:
    stdin = io.StringIO('{"id": "r1", "method": "debug.echo", "params": {"value": 1}}\n')
    stdout = io.StringIO()

    code = await serve(stdin, stdout)

    assert code == EXIT_CLEAN
    assert '"r1"' in stdout.getvalue()


class _BlockingStdin:
    def __init__(self) -> None:
        self.release = threading.Event()

    def readline(self) -> str:
        self.release.wait(timeout=30)
        return ""


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
async def test_each_shutdown_signal_stops_the_serve_loop(sig: signal.Signals) -> None:
    stdin = _BlockingStdin()
    stdout = io.StringIO()

    task = asyncio.ensure_future(serve(stdin, stdout))
    await asyncio.sleep(0.05)
    signal.raise_signal(sig)

    try:
        assert await asyncio.wait_for(task, timeout=5) == EXIT_SIGNALLED
    finally:
        stdin.release.set()
