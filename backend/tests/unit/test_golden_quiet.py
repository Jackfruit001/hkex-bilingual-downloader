import logging
from typing import Any

from tests.golden.quiet import quiet_worker
from tests.support import make_pdf


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list[Any] = []
        self.closed = False

    def send(self, message: Any) -> None:
        self.sent.append(message)

    def close(self) -> None:
        self.closed = True


def test_the_quiet_worker_returns_the_same_text_as_the_ordinary_one() -> None:
    conn = FakeConnection()
    try:
        quiet_worker(conn, make_pdf([["Hello 2026"]]), 3)  # type: ignore[arg-type]
        assert logging.root.manager.disable == logging.WARNING
    finally:
        logging.disable(logging.NOTSET)
    assert conn.sent == [("ok", "Hello 2026\n")] and conn.closed


def test_the_quiet_worker_reports_a_broken_file_instead_of_raising() -> None:
    conn = FakeConnection()
    try:
        quiet_worker(conn, b"not a pdf", 3)  # type: ignore[arg-type]
    finally:
        logging.disable(logging.NOTSET)
    assert conn.sent[0][0] == "error" and conn.closed
