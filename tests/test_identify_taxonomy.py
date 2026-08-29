from __future__ import annotations

from aegis.identify import ImplementationStatus, SimulationReadiness, build_fraud_taxonomy


def test_broad_taxonomy_keeps_exactly_the_existing_three_deep() -> None:
    taxonomy = build_fraud_taxonomy()
    deep = [
        scenario
        for scenario in taxonomy.scenarios
        if scenario.implementation_status is ImplementationStatus.DEEP_SIMULATED
    ]
    assert {scenario.id for scenario in deep} == {
        "synthetic-identity-bustout",
        "mule-network-structuring",
        "adaptive-detector-evasion",
    }
    assert taxonomy.summary.deeply_simulated == 3
    assert all(scenario.simulation_readiness is SimulationReadiness.READY for scenario in deep)


def test_identified_only_entries_are_evidenced_and_not_ready() -> None:
    taxonomy = build_fraud_taxonomy()
    identified_only = [
        scenario
        for scenario in taxonomy.scenarios
        if scenario.implementation_status is ImplementationStatus.IDENTIFIED_ONLY
    ]
    assert identified_only
    assert all(scenario.evidence_sources for scenario in identified_only)
    assert all(
        source.url.startswith(("https://", "docs/"))
        for scenario in taxonomy.scenarios
        for source in scenario.evidence_sources
    )
    assert all(
        scenario.simulation_readiness is not SimulationReadiness.READY
        for scenario in identified_only
    )


def test_summary_is_derived_from_scenarios() -> None:
    taxonomy = build_fraud_taxonomy()
    assert taxonomy.summary.total_attacks_identified == len(taxonomy.scenarios)
    assert taxonomy.summary.categories_represented == sorted(
        {scenario.category for scenario in taxonomy.scenarios}
    )
    assert taxonomy.summary.channels_represented == sorted(
        {channel for scenario in taxonomy.scenarios for channel in scenario.channels}
    )
