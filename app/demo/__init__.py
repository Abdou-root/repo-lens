"""
Demo mode for RepoLens.

This module provides sample repositories and pre-populated data
for users to explore RepoLens without connecting their own GitHub repos.

Features:
- Sample Python & TypeScript projects
- Pre-parsed code with embeddings
- Realistic code examples (auth, API, frontend)
- Demo mode toggle
"""

from app.demo.config import (
    DemoConfig,
    get_demo_config,
    is_demo_mode_enabled,
    is_demo_repo,
)
from app.demo.repositories import (
    DEMO_REPOSITORIES,
    get_demo_repo,
    list_demo_repos,
)
from app.demo.data_loader import (
    DemoDataLoader,
    initialize_demo_data,
)

__all__ = [
    'DemoConfig',
    'get_demo_config',
    'is_demo_mode_enabled',
    'is_demo_repo',
    'DEMO_REPOSITORIES',
    'get_demo_repo',
    'list_demo_repos',
    'DemoDataLoader',
    'initialize_demo_data',
]
