from __future__ import annotations

from typing import Any, Dict


class NullValidator:
    """Skips all validation. Used when no protocol plugin is installed."""

    def validate_manifest(self, manifest: Dict[str, Any]) -> None:
        pass

    def validate_proposal(self, proposal: Dict[str, Any]) -> None:
        pass


class NullEvolutionBackend:
    """No-op evolution backend. Used when skill-se-kit is not installed."""

    def detect_governor(self) -> bool:
        return False

    def record_experience(self, **kwargs: Any) -> None:
        pass
