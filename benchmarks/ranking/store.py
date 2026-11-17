"""How a query set's records are kept on disk.

A set has two forms:

    <run>/sets/<set>.jsonl       the working file: a run appends one line per query to it
    <run>/sets/<set>.jsonl.gz    the stored file: the same lines, compressed

A run works on the working file, because a line can be appended to it and a
line cut short by an interruption can be found and dropped. When a node is
complete its sets are packed: the stored file is written and the working file
removed. The stored files are what is kept in git; a full run of the guide
suite is about 6 MB as lines and about 1 MB stored.

Reading takes the working file when there is one (a run in progress, or one
that was interrupted), else the stored file.
"""

from __future__ import annotations

import gzip
import zlib
from pathlib import Path

_UNREADABLE = (OSError, EOFError, zlib.error)


def working(sets_dir: Path, set_key: str) -> Path:
    return Path(sets_dir) / f"{set_key}.jsonl"


def stored(sets_dir: Path, set_key: str) -> Path:
    return Path(sets_dir) / f"{set_key}.jsonl.gz"


def _unpacked(path: Path) -> bytes:
    """The content of a stored file, or None when it cannot be read as one."""
    try:
        return gzip.decompress(path.read_bytes())
    except _UNREADABLE:
        return None


def restore(sets_dir: Path, set_key: str) -> Path:
    """Make the working file a run appends to, from the stored file if there is no working file yet.

    A working file that is there is left as it is: it is the newer of the two,
    left by a run that stopped before its node was complete. Returns its path.
    """
    path, packed = working(sets_dir, set_key), stored(sets_dir, set_key)
    if not path.exists() and packed.exists():
        content = _unpacked(packed)
        if content is None:
            raise ValueError(f"{packed} cannot be read. Delete it to ask its queries again.")
        path.write_bytes(content)
    return path


def pack(sets_dir: Path, set_key: str) -> None:
    """Store a set compressed and remove its working file.

    The stored bytes carry no file name and no time, and a stored file that
    already holds the same lines is left untouched, so a file changes in git
    only when its results changed. The stored file is written whole under
    another name and then renamed, so it is never left half written.
    """
    path, packed = working(sets_dir, set_key), stored(sets_dir, set_key)
    if not path.exists():
        return
    content = path.read_bytes()
    if not (packed.exists() and _unpacked(packed) == content):
        partial = packed.with_name(packed.name + ".part")
        with partial.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw,
                                                      compresslevel=9, mtime=0) as out:
            out.write(content)
        partial.replace(packed)
    path.unlink()


def read_lines(sets_dir: Path, set_key: str) -> list:
    """A set's lines: from the working file when there is one, else from the stored file. [] when neither."""
    path, packed = working(sets_dir, set_key), stored(sets_dir, set_key)
    if path.exists():
        content = path.read_bytes()
    elif packed.exists():
        content = _unpacked(packed)
        if content is None:
            raise ValueError(f"{packed} cannot be read.")
    else:
        return []
    return [line for line in content.decode("utf-8").splitlines() if line.strip()]


def discard(sets_dir: Path) -> None:
    """Remove every set of a run, in both forms."""
    sets_dir = Path(sets_dir)
    for pattern in ("*.jsonl", "*.jsonl.gz", "*.jsonl.gz.part"):
        for path in sorted(sets_dir.glob(pattern)):
            path.unlink()
