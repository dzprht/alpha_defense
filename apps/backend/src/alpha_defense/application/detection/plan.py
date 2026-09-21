"""Versioned analyzer applicability plan for communication observations."""

from alpha_defense.application.detection.dto import ObservationAnalysisInput
from alpha_defense.domain.communications import ObservationKind
from alpha_defense.domain.detection import (
    AnalysisApplicability,
    AnalysisPlan,
    AnalysisRequirement,
    AnalyzerKind,
)

ANALYSIS_PLAN_VERSION = "observation-analysis-v1"


def build_observation_analysis_plan(value: ObservationAnalysisInput) -> AnalysisPlan:
    text_applicable = value.kind in {
        ObservationKind.SMS,
        ObservationKind.MESSENGER,
        ObservationKind.CALL_TRANSCRIPT,
    }
    url_applicable = (
        value.kind is ObservationKind.WEB_RESOURCE and value.raw_resource_url is not None
    )
    lookup_applicable = value.has_lookup_indicators
    visual_applicable = bool(value.media_refs)
    return AnalysisPlan(
        version=ANALYSIS_PLAN_VERSION,
        requirements=(
            _requirement(AnalyzerKind.TEXT, text_applicable, "content_has_no_text"),
            _requirement(AnalyzerKind.RESOURCE_URL, url_applicable, "content_has_no_url"),
            _requirement(
                AnalyzerKind.THREAT_LOOKUP,
                lookup_applicable,
                "content_has_no_lookup_indicators",
            ),
            _requirement(
                AnalyzerKind.RESOURCE_VISUAL,
                visual_applicable,
                "content_has_no_visual_media",
            ),
        ),
    )


def _requirement(
    analyzer: AnalyzerKind,
    applicable: bool,
    not_applicable_reason: str,
) -> AnalysisRequirement:
    return AnalysisRequirement(
        analyzer=analyzer,
        applicability=(
            AnalysisApplicability.APPLICABLE if applicable else AnalysisApplicability.NOT_APPLICABLE
        ),
        required=applicable,
        reason_code="analysis_required" if applicable else not_applicable_reason,
    )
