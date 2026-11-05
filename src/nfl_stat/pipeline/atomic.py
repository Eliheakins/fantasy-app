from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


@contextmanager
def atomic_path(target: Path) -> Iterator[Path]:
    """
    Yield a unique temp path next to `target`; replace `target` with it when the block succeeds.

    A reader (the API, a manifest scan) never sees a half-written file, concurrent writers never
    share a temp name, and a failure leaves the old file in place and removes the temp file.
    """
    fd, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    os.close(fd)
    tmp = Path(name)
    try:
        yield tmp
        os.chmod(tmp, 0o666 & ~_umask())  # mkstemp makes 0600; keep the mode a plain write gets
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
