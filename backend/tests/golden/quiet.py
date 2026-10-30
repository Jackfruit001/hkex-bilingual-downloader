"""A text-extraction worker that keeps pypdf's font warnings off the terminal.

Most real HKEXnews PDFs make pypdf log one warning per font. They are noise for the golden helper,
whose output a person reads. The worker runs in its own process, so silencing logging here
cannot affect anything else.
"""

import logging
import multiprocessing.connection as mpc

from app.pairing.content_check import _worker as default_worker


def quiet_worker(conn: mpc.Connection, pdf: bytes, pages: int) -> None:
    logging.disable(logging.WARNING)
    default_worker(conn, pdf, pages)
