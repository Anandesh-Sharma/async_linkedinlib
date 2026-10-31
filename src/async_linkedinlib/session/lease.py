"""POSIX ownership of one session file, following the local Instagram client's pattern."""

import os
from pathlib import Path

from ..exceptions import SessionInUse


class SessionLease:
    """Hold a stable sidecar lock until the owning client closes."""

    def __init__(self, path: Path) -> None:
        import fcntl

        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(self._fd, 0o600)
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.close()
            raise SessionInUse("This session file is already open in another client.") from None
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1
