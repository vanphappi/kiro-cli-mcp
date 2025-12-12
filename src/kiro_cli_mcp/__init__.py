"""Kiro CLI MCP Server - Orchestrate kiro-cli from Kiro IDE via MCP."""

__version__ = "0.1.0"

from .server import KiroCliMCPServer, create_mcp_server
from .config import ServerConfig, ConfigManager
from .session import Session, SessionManager
from .executor import CommandExecutor
from .models import ChatResponse, CommandResult, SessionInfo, AgentInfo
from .errors import MCPError, ErrorCode
from .process_pool import ProcessPool, PooledProcess
from .streaming import (
    StreamingTaskManager,
    AsyncTask,
    TaskStatus,
    StreamChunk,
    create_chat_task_executor,
)

__all__ = [
    # Server
    "KiroCliMCPServer",
    "create_mcp_server",
    # Config
    "ServerConfig",
    "ConfigManager",
    # Session
    "Session",
    "SessionManager",
    # Executor
    "CommandExecutor",
    # Models
    "ChatResponse",
    "CommandResult",
    "SessionInfo",
    "AgentInfo",
    # Errors
    "MCPError",
    "ErrorCode",
    # Process Pool (Performance)
    "ProcessPool",
    "PooledProcess",
    # Streaming (Async Tasks)
    "StreamingTaskManager",
    "AsyncTask",
    "TaskStatus",
    "StreamChunk",
    "create_chat_task_executor",
]
