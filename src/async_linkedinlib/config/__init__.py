"""Config public exports."""

from .options import ClientOptions  # HTTP connection settings.
from .profile import ClientProfile  # Versioned app metadata.

__all__ = ["ClientOptions", "ClientProfile"]
