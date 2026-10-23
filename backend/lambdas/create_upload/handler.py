"""POST /uploads: issue a server-owned, bounded upload reservation.

The implementation lives in shared.uploads so capability and signing policy can
be tested without duplicating endpoint code. Caller-selected IDs are rejected.
"""

from backend.shared.uploads import handler

__all__ = ["handler"]
