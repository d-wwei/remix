from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


DEFAULT_WEIGHTS = {
    "task_fit": 1.2,
    "structural_clarity": 1.0,
    "maintainability": 1.0,
    "extensibility": 0.9,
    "testability": 0.9,
    "compatibility_risk": 1.0,
    "operator_experience": 0.7,
    "maintenance_cost": 0.7,
    "provenance_safety": 1.1,
}


PROFILE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "skill": {
        "profile_id": "skill",
        "artifact_type": "skill",
        "display_name": "Skill Profile",
        "default_packaging_profile": "skill-package",
        "required_outputs": ["skill/SKILL.md", "skill/manifest.json", "provenance.json"],
        "verification_focus": [
            "protocol compatibility",
            "manifest validity",
            "scenario tests",
            "governor readiness",
        ],
        "governance_posture": "compatible_with_governor",
        "default_weights": {
            **DEFAULT_WEIGHTS,
            "skill_se_kit_compatibility": 1.2,
            "governor_readiness": 1.1,
        },
    },
    "protocol": {
        "profile_id": "protocol",
        "artifact_type": "protocol",
        "display_name": "Protocol Profile",
        "default_packaging_profile": "protocol-bundle",
        "required_outputs": ["protocol/schemas/remixed.schema.json", "provenance.json"],
        "verification_focus": [
            "schema validation",
            "compatibility analysis",
            "ambiguity reduction",
        ],
        "governance_posture": "advisory",
        "default_weights": {
            **DEFAULT_WEIGHTS,
            "protocol_compatibility": 1.3,
            "ambiguity_reduction": 1.1,
        },
    },
    "module": {
        "profile_id": "module",
        "artifact_type": "module",
        "display_name": "Module Profile",
        "default_packaging_profile": "python-package",
        "required_outputs": ["module/README.md", "provenance.json"],
        "verification_focus": [
            "packaging sanity",
            "unit or contract tests",
            "dependency safety",
        ],
        "governance_posture": "native_repository",
        "default_weights": {
            **DEFAULT_WEIGHTS,
            "api_coherence": 1.2,
            "dependency_safety": 1.0,
        },
    },
    "feature": {
        "profile_id": "feature",
        "artifact_type": "feature",
        "display_name": "Feature Profile",
        "default_packaging_profile": "feature-bundle",
        "required_outputs": ["feature/spec.md", "feature/rollout_plan.md", "provenance.json"],
        "verification_focus": [
            "acceptance coverage",
            "rollout safety",
            "observability readiness",
        ],
        "governance_posture": "product_delivery",
        "default_weights": {
            **DEFAULT_WEIGHTS,
            "rollout_safety": 1.2,
            "integration_fit": 1.1,
        },
    },
    "product": {
        "profile_id": "product",
        "artifact_type": "product",
        "display_name": "Product Profile",
        "default_packaging_profile": "product-bundle",
        "required_outputs": ["product/PRD.md", "product/roadmap.md", "provenance.json"],
        "verification_focus": [
            "objective coverage",
            "internal consistency",
            "dependency realism",
        ],
        "governance_posture": "advisory",
        "default_weights": {
            **DEFAULT_WEIGHTS,
            "objective_coverage": 1.3,
            "dependency_realism": 1.1,
        },
    },
    "compound": {
        "profile_id": "compound",
        "artifact_type": "compound",
        "display_name": "Compound Profile",
        "default_packaging_profile": "compound-bundle",
        "required_outputs": ["artifact_manifest.json", "provenance.json"],
        "verification_focus": [
            "bundle completeness",
            "cross-artifact consistency",
            "handoff clarity",
        ],
        "governance_posture": "mixed",
        "default_weights": dict(DEFAULT_WEIGHTS),
    },
}


class TargetProfileRegistry:
    def __init__(self) -> None:
        self._profiles = deepcopy(PROFILE_DEFINITIONS)

    def list_profiles(self) -> List[Dict[str, Any]]:
        return [deepcopy(profile) for profile in self._profiles.values()]

    def get(self, profile_id: str) -> Dict[str, Any]:
        if profile_id not in self._profiles:
            raise ValueError(f"Unsupported target profile: {profile_id}")
        return deepcopy(self._profiles[profile_id])

    def resolve(self, brief: Dict[str, Any]) -> Dict[str, Any]:
        profile_id = (
            brief.get("target_profile")
            or brief.get("target_artifact_type")
            or brief.get("artifact_type")
            or "skill"
        )
        profile = self.get(profile_id)
        profile["packaging_profile"] = brief.get("packaging_profile", profile["default_packaging_profile"])
        if profile_id == "compound":
            child_profiles = brief.get("compound_profiles") or ["skill", "module"]
            profile["child_profiles"] = [self.get(child_id) for child_id in child_profiles]
        return profile
