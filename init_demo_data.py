"""
Initialize demo data for RepoLens.

This script loads demo repositories into the system:
- Parses sample Python and TypeScript code
- Generates embeddings for semantic search
- Populates Neo4j database (if configured)
- Enables users to explore RepoLens without GitHub connection

Usage:
    python init_demo_data.py              # Load demo data
    python init_demo_data.py --force      # Force reload (clear and reload)
    python init_demo_data.py --clear      # Clear demo data only
    python init_demo_data.py --status     # Check demo data status
"""

import sys
import os
import argparse
import logging
from typing import Optional

# Add project to path
sys.path.insert(0, os.path.dirname(__file__))

from app.demo import DemoDataLoader, initialize_demo_data, get_demo_config
from app.services.embeddings import CodeEmbedder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def get_neo4j_driver():
    """
    Get Neo4j driver if configured.

    Returns:
        Neo4j driver or None
    """
    try:
        from neo4j import GraphDatabase
        from dotenv import load_dotenv

        load_dotenv()

        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD")

        if not neo4j_password:
            logger.warning("NEO4J_PASSWORD not set - demo data will only be in-memory")
            return None

        driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )

        # Test connection
        with driver.session() as session:
            session.run("RETURN 1")

        logger.info(f"Connected to Neo4j at {neo4j_uri}")
        return driver

    except ImportError:
        logger.warning("neo4j package not installed - demo data will only be in-memory")
        return None
    except Exception as e:
        logger.warning(f"Failed to connect to Neo4j: {e}")
        logger.warning("Demo data will only be in-memory")
        return None


def load_demo_data(force_reload: bool = False):
    """
    Load demo data into the system.

    Args:
        force_reload: Whether to clear and reload existing data
    """
    print("=" * 70)
    print("LOADING DEMO DATA FOR REPOLENS")
    print("=" * 70)
    print()

    # Check demo mode configuration
    config = get_demo_config()

    if not config.enabled:
        print("❌ Demo mode is disabled in configuration")
        print("   Enable it in .env or app/demo/config.py")
        return

    print(f"✓ Demo mode enabled")
    print(f"  Max demo repos: {config.max_demo_repos}")
    print(f"  Auto-load on startup: {config.auto_load_on_startup}")
    print()

    # Initialize services
    print("Initializing services...")
    print("  [1/3] Loading embedding model...")
    embedder = CodeEmbedder(model_name="all-MiniLM-L6-v2")
    print(f"        ✓ Model loaded (dimension: {embedder.get_embedding_dimension()})")

    print("  [2/3] Connecting to Neo4j...")
    neo4j_driver = get_neo4j_driver()
    if neo4j_driver:
        print("        ✓ Neo4j connected")
    else:
        print("        ⚠ Neo4j not available - using in-memory only")

    print("  [3/3] Initializing data loader...")
    loader = DemoDataLoader(
        embedder=embedder,
        neo4j_driver=neo4j_driver,
    )
    print("        ✓ Data loader ready")
    print()

    # Check if already loaded
    if loader.is_demo_data_loaded() and not force_reload:
        print("ℹ️  Demo data is already loaded")
        print("   Use --force to reload")
        print()
        _print_stats(loader)
        return

    # Clear if force reload
    if force_reload and loader.is_demo_data_loaded():
        print("🗑️  Clearing existing demo data...")
        clear_stats = loader.clear_demo_data()
        print(f"   ✓ Cleared {clear_stats.get('nodes_deleted', 0)} nodes")
        print()

    # Load demo repositories
    print("Loading demo repositories...")
    print()

    stats = loader.load_all_demo_repositories()

    # Display results
    print()
    print("=" * 70)

    if stats.get("status") == "disabled":
        print("❌ DEMO LOADING FAILED - Demo mode disabled")
    elif stats.get("errors"):
        print("⚠️  DEMO LOADING COMPLETED WITH ERRORS")
        print()
        print(f"✓ Repositories loaded: {stats['repos_loaded']}")
        print(f"✓ Files parsed: {stats['files_parsed']}")
        print(f"✓ Functions indexed: {stats['functions_indexed']}")
        print(f"✓ Classes indexed: {stats['classes_indexed']}")
        print(f"✓ Embeddings generated: {stats['embeddings_generated']}")
        print()
        print(f"❌ Errors: {len(stats['errors'])}")
        for error in stats['errors']:
            print(f"   - {error}")
    else:
        print("✅ DEMO DATA LOADED SUCCESSFULLY")
        print()
        print(f"✓ Repositories loaded: {stats['repos_loaded']}")
        print(f"✓ Files parsed: {stats['files_parsed']}")
        print(f"✓ Functions indexed: {stats['functions_indexed']}")
        print(f"✓ Classes indexed: {stats['classes_indexed']}")
        print(f"✓ Embeddings generated: {stats['embeddings_generated']}")

    print("=" * 70)
    print()

    # Print additional stats
    _print_stats(loader)

    # Cleanup
    if neo4j_driver:
        neo4j_driver.close()


def clear_demo_data():
    """Clear all demo data from the system"""
    print("=" * 70)
    print("CLEARING DEMO DATA")
    print("=" * 70)
    print()

    # Initialize services
    embedder = CodeEmbedder(model_name="all-MiniLM-L6-v2")
    neo4j_driver = get_neo4j_driver()

    loader = DemoDataLoader(
        embedder=embedder,
        neo4j_driver=neo4j_driver,
    )

    # Check if loaded
    if not loader.is_demo_data_loaded():
        print("ℹ️  No demo data to clear")
        print()
        return

    # Clear
    print("Clearing demo data...")
    stats = loader.clear_demo_data()

    print()
    print("✅ DEMO DATA CLEARED")
    print(f"   Nodes deleted: {stats.get('nodes_deleted', 0)}")
    print()

    # Cleanup
    if neo4j_driver:
        neo4j_driver.close()


def check_status():
    """Check demo data status"""
    print("=" * 70)
    print("DEMO DATA STATUS")
    print("=" * 70)
    print()

    # Check configuration
    config = get_demo_config()
    print("Configuration:")
    print(f"  Demo mode enabled: {config.enabled}")
    print(f"  Max demo repos: {config.max_demo_repos}")
    print(f"  Auto-load on startup: {config.auto_load_on_startup}")
    print()

    # Initialize services
    embedder = CodeEmbedder(model_name="all-MiniLM-L6-v2")
    neo4j_driver = get_neo4j_driver()

    loader = DemoDataLoader(
        embedder=embedder,
        neo4j_driver=neo4j_driver,
    )

    # Check if loaded
    is_loaded = loader.is_demo_data_loaded()

    print("Status:")
    print(f"  Demo data loaded: {'✅ Yes' if is_loaded else '❌ No'}")
    print()

    if is_loaded:
        _print_stats(loader)

    # Cleanup
    if neo4j_driver:
        neo4j_driver.close()


def _print_stats(loader: DemoDataLoader):
    """Print detailed statistics"""
    stats = loader.get_stats()

    search_stats = stats.get("search_stats", {})
    embedder_stats = stats.get("embedder_stats", {})

    print("Search Index:")
    print(f"  Total indexed: {search_stats.get('total_indexed', 0)}")

    by_type = search_stats.get("by_type", {})
    if by_type:
        print("  By type:")
        for code_type, count in by_type.items():
            print(f"    - {code_type}: {count}")

    by_lang = search_stats.get("by_language", {})
    if by_lang:
        print("  By language:")
        for lang, count in by_lang.items():
            print(f"    - {lang}: {count}")

    print()
    print("Embedder:")
    print(f"  Model: {embedder_stats.get('model_name', 'unknown')}")
    print(f"  Dimension: {embedder_stats.get('embedding_dimension', 0)}")
    print(f"  Embeddings generated: {embedder_stats.get('embeddings_generated', 0)}")
    print(f"  Cache size: {embedder_stats.get('cache_size', 0)}")
    print(f"  Cache hits: {embedder_stats.get('cache_hits', 0)}")
    print()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Initialize demo data for RepoLens",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python init_demo_data.py              # Load demo data
  python init_demo_data.py --force      # Force reload
  python init_demo_data.py --clear      # Clear demo data
  python init_demo_data.py --status     # Check status
        """,
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reload (clear and reload demo data)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear demo data without reloading",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check demo data status",
    )

    args = parser.parse_args()

    try:
        if args.status:
            check_status()
        elif args.clear:
            clear_demo_data()
        else:
            load_demo_data(force_reload=args.force)

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
