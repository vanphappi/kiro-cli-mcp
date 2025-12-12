"""Entry point for Kiro CLI MCP Server."""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from mcp.server.stdio import stdio_server

from .config import ConfigManager, ServerConfig
from .server import create_mcp_server
from .session import _cleanup_all_processes

logger = logging.getLogger(__name__)


def _signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, cleaning up...")
    _cleanup_all_processes()
    sys.exit(0)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Kiro CLI MCP Server - Orchestrate kiro-cli from Kiro IDE"
    )

    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="Path to configuration file (JSON)",
    )

    parser.add_argument(
        "--log-level",
        "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,  # None means use config/env value
        help="Logging level (overrides config/env)",
    )

    return parser.parse_args()


async def run_stdio_server(config: ServerConfig) -> None:
    """Run server with stdio transport using MCP SDK."""
    logger.info("Starting Kiro CLI MCP Server with stdio transport")
    logger.debug(f"Config: {config.to_dict()}")

    # Create MCP server instance
    mcp_server = create_mcp_server(config)

    # Run with stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options()
        )


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Load configuration from env/file FIRST
    config = ConfigManager.load(args.config)

    # Override log level from CLI args if explicitly provided
    if args.log_level is not None:
        log_level = args.log_level
    else:
        # Use log level from config (env or file)
        log_level = config.log_level

    # Setup logging with the final log level
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,  # Log to stderr to keep stdout for MCP
        force=True,  # Force reconfigure if already set
    )
    
    # Set level for all relevant loggers
    logging.getLogger().setLevel(getattr(logging, log_level))
    logging.getLogger("mcp").setLevel(getattr(logging, log_level))
    logging.getLogger("kiro_cli_mcp").setLevel(getattr(logging, log_level))

    # Update config with final log level if it was overridden
    if args.log_level is not None:
        config = ServerConfig(
            kiro_cli_path=config.kiro_cli_path,
            command_timeout=config.command_timeout,
            max_sessions=config.max_sessions,
            session_timeout=config.session_timeout,
            cleanup_interval=config.cleanup_interval,
            working_directory=config.working_directory,
            log_level=log_level,
            default_model=config.default_model,
            default_agent=config.default_agent,
            log_response=config.log_response,
            pool_enabled=config.pool_enabled,
            pool_size=config.pool_size,
            pool_idle_time=config.pool_idle_time,
            pool_max_uses=config.pool_max_uses,
            max_async_tasks=config.max_async_tasks,
            task_ttl=config.task_ttl,
        )

    logger.info(f"Log level: {log_level}")
    logger.debug(f"Configuration loaded: {config.to_dict()}")

    # Register signal handlers for cleanup
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    
    # Run server with stdio transport
    try:
        asyncio.run(run_stdio_server(config))
    except KeyboardInterrupt:
        logger.info("Server shutdown by user")
        _cleanup_all_processes()
    except Exception as e:
        logger.exception(f"Server error: {e}")
        _cleanup_all_processes()
        sys.exit(1)


if __name__ == "__main__":
    main()
