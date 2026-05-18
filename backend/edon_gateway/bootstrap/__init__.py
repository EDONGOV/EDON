"""EDON Bootstrap Engine — Cold-start intake for new prospects.

Converts static artifacts (OpenAPI specs, agent configs, log samples) into
a live execution graph + first findings report. No live traffic required.

Entry points:
    from .engine import run_bootstrap, get_bootstrap_engine
    from .job_store import get_job, create_job
"""

from .engine import run_bootstrap, BootstrapEngine, get_bootstrap_engine
from .job_store import create_job, get_job, update_job

__all__ = [
    "run_bootstrap", "BootstrapEngine", "get_bootstrap_engine",
    "create_job", "get_job", "update_job",
]
