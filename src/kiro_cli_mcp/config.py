"""Configuration management for Kiro CLI MCP Server."""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ConfigurationError, ErrorCode

logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    """Server configuration settings."""
    
    kiro_cli_path: str = "kiro-cli"
    command_timeout: float = 30.0  # 30 seconds (IDE-friendly)
    max_sessions: int = 10
    session_timeout: float = 300.0  # 5 minutes - auto-cleanup inactive sessions
    cleanup_interval: float = 30.0  # Check for inactive sessions every 30 seconds
    working_directory: str | None = None
    log_level: str = "INFO"
    default_model: str = "claude-opus-4.5"  # Default to Claude Opus 4.5
    default_agent: str | None = "kiro_default"  # Default agent to use (None = no agent)
    log_response: bool = True  # Log full CLI response for debugging
    
    # Process pool settings for performance
    pool_enabled: bool = True  # Enable process pool for better performance
    pool_size: int = 5  # Maximum number of pooled processes
    pool_idle_time: float = 300.0  # Max idle time before process is recycled (5 min)
    pool_max_uses: int = 100  # Max uses per process before recycling
    
    # Streaming/async task settings
    max_async_tasks: int = 100  # Maximum concurrent async tasks
    task_ttl: float = 3600.0  # Task result TTL in seconds (1 hour)
    
    def __post_init__(self) -> None:
        """Validate configuration values after initialization."""
        self._validate()
    
    def _validate(self) -> None:
        """Validate configuration values."""
        errors: list[str] = []
        
        # 0 means unlimited, negative is invalid
        if self.command_timeout < 0:
            errors.append("command_timeout must be non-negative (0 = unlimited)")
        
        # 0 means unlimited, negative is invalid
        if self.max_sessions < 0:
            errors.append("max_sessions must be non-negative (0 = unlimited)")
        
        if self.session_timeout <= 0:
            errors.append("session_timeout must be positive")
        
        if self.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            errors.append(f"Invalid log_level: {self.log_level}")
        
        if self.working_directory is not None:
            path = Path(self.working_directory)
            if not path.exists():
                logger.warning(f"Working directory does not exist: {self.working_directory}")
        
        if errors:
            raise ConfigurationError(
                code=ErrorCode.INVALID_CONFIG,
                message="; ".join(errors),
                details={"errors": errors},
            )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "kiro_cli_path": self.kiro_cli_path,
            "command_timeout": self.command_timeout,
            "max_sessions": self.max_sessions,
            "session_timeout": self.session_timeout,
            "cleanup_interval": self.cleanup_interval,
            "working_directory": self.working_directory,
            "log_level": self.log_level,
            "default_model": self.default_model,
            "default_agent": self.default_agent,
            "log_response": self.log_response,
            "pool_enabled": self.pool_enabled,
            "pool_size": self.pool_size,
            "pool_idle_time": self.pool_idle_time,
            "pool_max_uses": self.pool_max_uses,
            "max_async_tasks": self.max_async_tasks,
            "task_ttl": self.task_ttl,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServerConfig":
        """Create configuration from dictionary."""
        
        def parse_bool(value: Any, default: bool = True) -> bool:
            """Parse boolean from string or bool."""
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        
        return cls(
            kiro_cli_path=data.get("kiro_cli_path", "kiro-cli"),
            command_timeout=float(data.get("command_timeout", 30.0)),
            max_sessions=int(data.get("max_sessions", 10)),
            session_timeout=float(data.get("session_timeout", 300.0)),
            cleanup_interval=float(data.get("cleanup_interval", 30.0)),
            working_directory=data.get("working_directory"),
            log_level=data.get("log_level", "INFO"),
            default_model=data.get("default_model", "claude-opus-4.5"),
            default_agent=data.get("default_agent", "kiro_default"),
            log_response=parse_bool(data.get("log_response"), True),
            pool_enabled=parse_bool(data.get("pool_enabled"), True),
            pool_size=int(data.get("pool_size", 5)),
            pool_idle_time=float(data.get("pool_idle_time", 300.0)),
            pool_max_uses=int(data.get("pool_max_uses", 100)),
            max_async_tasks=int(data.get("max_async_tasks", 100)),
            task_ttl=float(data.get("task_ttl", 3600.0)),
        )


class ConfigManager:
    """Manages server configuration loading and validation."""
    
    ENV_PREFIX = "KIRO_MCP_"
    
    @classmethod
    def get_default(cls) -> ServerConfig:
        """Get default configuration."""
        return ServerConfig()
    
    @classmethod
    def load_from_env(cls) -> ServerConfig:
        """Load configuration from environment variables.
        
        Environment variables:
        - KIRO_MCP_CLI_PATH: Path to kiro-cli executable
        - KIRO_MCP_COMMAND_TIMEOUT: Command timeout in seconds
        - KIRO_MCP_MAX_SESSIONS: Maximum number of sessions
        - KIRO_MCP_SESSION_TIMEOUT: Session timeout in seconds
        - KIRO_MCP_WORKING_DIRECTORY: Default working directory
        - KIRO_MCP_LOG_LEVEL: Logging level
        """
        config_dict: dict[str, Any] = {}
        
        env_mappings = {
            "CLI_PATH": "kiro_cli_path",
            "COMMAND_TIMEOUT": "command_timeout",
            "MAX_SESSIONS": "max_sessions",
            "SESSION_TIMEOUT": "session_timeout",
            "CLEANUP_INTERVAL": "cleanup_interval",
            "WORKING_DIRECTORY": "working_directory",
            "LOG_LEVEL": "log_level",
            "DEFAULT_MODEL": "default_model",
            "DEFAULT_AGENT": "default_agent",
            "LOG_RESPONSE": "log_response",
            "POOL_ENABLED": "pool_enabled",
            "POOL_SIZE": "pool_size",
            "POOL_IDLE_TIME": "pool_idle_time",
            "POOL_MAX_USES": "pool_max_uses",
            "MAX_ASYNC_TASKS": "max_async_tasks",
            "TASK_TTL": "task_ttl",
        }
        
        for env_suffix, config_key in env_mappings.items():
            env_var = f"{cls.ENV_PREFIX}{env_suffix}"
            value = os.environ.get(env_var)
            if value is not None:
                config_dict[config_key] = value
        
        try:
            return ServerConfig.from_dict(config_dict)
        except ConfigurationError:
            logger.warning("Invalid environment configuration, using defaults")
            return cls.get_default()
    
    @classmethod
    def load_from_file(cls, path: str | Path) -> ServerConfig:
        """Load configuration from a JSON file.
        
        Args:
            path: Path to the configuration file
            
        Returns:
            ServerConfig instance
            
        Raises:
            ConfigurationError: If file cannot be read or parsed
        """
        path = Path(path)
        
        if not path.exists():
            logger.warning(f"Config file not found: {path}, using defaults")
            return cls.get_default()
        
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return ServerConfig.from_dict(data)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return cls.get_default()
        except ConfigurationError:
            logger.warning("Invalid configuration in file, using defaults")
            return cls.get_default()
        except Exception as e:
            logger.error(f"Error reading config file: {e}")
            return cls.get_default()
    
    @classmethod
    def load(cls, config_path: str | Path | None = None) -> ServerConfig:
        """Load configuration with priority: file > env > defaults.
        
        Args:
            config_path: Optional path to configuration file
            
        Returns:
            ServerConfig instance
        """
        # Start with defaults
        config = cls.get_default()
        
        # Override with environment variables
        env_config = cls.load_from_env()
        config_dict = config.to_dict()
        env_dict = env_config.to_dict()
        
        # Merge env values that differ from defaults
        default_dict = cls.get_default().to_dict()
        for key, value in env_dict.items():
            if value != default_dict.get(key):
                config_dict[key] = value
        
        # Override with file if provided
        if config_path:
            file_config = cls.load_from_file(config_path)
            file_dict = file_config.to_dict()
            for key, value in file_dict.items():
                if value != default_dict.get(key):
                    config_dict[key] = value
        
        try:
            return ServerConfig.from_dict(config_dict)
        except ConfigurationError:
            logger.warning("Merged configuration invalid, using defaults")
            return cls.get_default()
