"""
Demo mode configuration.

Controls whether demo mode is enabled and configures demo settings.
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class DemoConfig:
    """Demo mode configuration"""
    enabled: bool = True  # Enable demo mode by default
    allow_real_repos: bool = True  # Allow real repos alongside demo repos
    max_demo_repos: int = 3  # Maximum number of demo repos
    demo_user_id: str = "demo_user"  # Demo user ID
    auto_load_on_startup: bool = True  # Auto-load demo data on startup


_demo_config: Optional[DemoConfig] = None


def get_demo_config() -> DemoConfig:
    """Get demo configuration (singleton)"""
    global _demo_config

    if _demo_config is None:
        # Load from environment or use defaults
        enabled = os.getenv("DEMO_MODE_ENABLED", "true").lower() == "true"
        allow_real = os.getenv("DEMO_ALLOW_REAL_REPOS", "true").lower() == "true"
        auto_load = os.getenv("DEMO_AUTO_LOAD", "true").lower() == "true"

        _demo_config = DemoConfig(
            enabled=enabled,
            allow_real_repos=allow_real,
            auto_load_on_startup=auto_load,
        )

    return _demo_config


def is_demo_mode_enabled() -> bool:
    """Check if demo mode is enabled"""
    return get_demo_config().enabled


def is_demo_repo(repo_id: str) -> bool:
    """Check if a repository ID is a demo repo"""
    return repo_id.startswith("demo_")
