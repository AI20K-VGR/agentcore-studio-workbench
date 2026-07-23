"""Recipe Builder compatibility bridge module for Workbench (SWE owner — Thiệu Quang Minh).

Re-exports builder functions for Day 3 and Day 4.
"""

from studio_workbench.builder_d3 import (
    build_agent_config,
    create_recipe_d3,
    create_sample_recipe_d3,
)
from studio_workbench.builder_d4 import create_recipe_d4

__all__ = [
    "build_agent_config",
    "create_recipe_d3",
    "create_recipe_d4",
    "create_sample_recipe_d3",
]
