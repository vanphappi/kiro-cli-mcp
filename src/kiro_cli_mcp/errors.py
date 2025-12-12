"""Error definitions for Kiro CLI MCP Server."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Error codes for MCP operations."""
    
    # Validation errors
    INVALID_MESSAGE = "INVALID_MESSAGE"
    INVALID_COMMAND = "INVALID_COMMAND"
    INVALID_CONFIG = "INVALID_CONFIG"
    
    # Session errors
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_ALREADY_EXISTS = "SESSION_ALREADY_EXISTS"
    SESSION_LIMIT_REACHED = "SESSION_LIMIT_REACHED"
    SESSION_INACTIVE = "SESSION_INACTIVE"
    
    # Execution errors
    COMMAND_TIMEOUT = "COMMAND_TIMEOUT"
    COMMAND_FAILED = "COMMAND_FAILED"
    KIRO_CLI_NOT_FOUND = "KIRO_CLI_NOT_FOUND"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    
    # Agent errors
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    
    # Concurrency errors
    SESSION_BUSY = "SESSION_BUSY"
    SERVER_OVERLOADED = "SERVER_OVERLOADED"
    
    # Streaming errors
    STREAM_INTERRUPTED = "STREAM_INTERRUPTED"


ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.INVALID_MESSAGE: "Message cannot be empty or contain only whitespace",
    ErrorCode.INVALID_COMMAND: "Invalid or unsupported command format",
    ErrorCode.INVALID_CONFIG: "Invalid configuration value",
    ErrorCode.SESSION_NOT_FOUND: "Session with specified ID does not exist",
    ErrorCode.SESSION_ALREADY_EXISTS: "Session with specified ID already exists",
    ErrorCode.SESSION_LIMIT_REACHED: "Maximum number of sessions reached",
    ErrorCode.SESSION_INACTIVE: "Session is no longer active",
    ErrorCode.COMMAND_TIMEOUT: "Command execution timed out",
    ErrorCode.COMMAND_FAILED: "Command execution failed",
    ErrorCode.KIRO_CLI_NOT_FOUND: "kiro-cli executable not found at specified path",
    ErrorCode.EXECUTION_ERROR: "An error occurred during execution",
    ErrorCode.AGENT_NOT_FOUND: "Specified agent does not exist",
    ErrorCode.SESSION_BUSY: "Session is currently processing another request",
    ErrorCode.SERVER_OVERLOADED: "Server has reached maximum capacity",
    ErrorCode.STREAM_INTERRUPTED: "Streaming response was interrupted",
}


@dataclass
class MCPError(Exception):
    """Base exception for MCP Server errors."""
    
    code: ErrorCode
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        if self.message is None:
            self.message = ERROR_MESSAGES.get(self.code, "Unknown error")
        super().__init__(self.message)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for JSON serialization."""
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }
    
    @classmethod
    def from_code(cls, code: ErrorCode, **details: Any) -> "MCPError":
        """Create an MCPError from an error code with optional details."""
        return cls(code=code, details=details)


class ValidationError(MCPError):
    """Error raised for input validation failures."""
    pass


class SessionError(MCPError):
    """Error raised for session-related failures."""
    pass


class ExecutionError(MCPError):
    """Error raised for command execution failures."""
    pass


class TimeoutError(MCPError):
    """Error raised when operations timeout."""
    pass


class ConfigurationError(MCPError):
    """Error raised for configuration issues."""
    pass


class ConcurrencyError(MCPError):
    """Error raised for concurrent access conflicts."""
    pass
