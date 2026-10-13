"""Named stage-I variants for collaborative routing experiments."""

from dataclasses import replace

from experiments.collaborative_routing.config import DEFAULT_CONFIG, ExperimentConfig


def fixed_damping_config(config: ExperimentConfig = DEFAULT_CONFIG) -> ExperimentConfig:
    """The preserved baseline using a fixed fidelity relaxation of 0.2."""
    return replace(
        config,
        stage_one_iteration=replace(
            config.stage_one_iteration,
            fidelity_update_mode="fixed",
            fidelity_relaxation=0.2,
        ),
    )


def adaptive_damping_config(config: ExperimentConfig = DEFAULT_CONFIG) -> ExperimentConfig:
    """The optimized adaptive variant used by the proposed algorithm."""
    return replace(
        config,
        stage_one_iteration=replace(
            config.stage_one_iteration,
            fidelity_update_mode="adaptive",
            adaptive_fidelity_relaxations=(1.0, 0.5, 0.25, 0.125),
            adaptive_early_accept=True,
            active_links_only=True,
        ),
        link_configuration_search=replace(
            config.link_configuration_search,
            fine_step=0.001,
            use_precomputed_lookup=True,
        ),
    )
