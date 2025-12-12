"""Data models for Kiro CLI MCP Server."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ChatResponse:
    """Response from a chat interaction with kiro-cli."""
    
    content: str
    session_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    is_complete: bool = True
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "content": self.content,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "is_complete": self.is_complete,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatResponse":
        """Create from dictionary."""
        return cls(
            content=data["content"],
            session_id=data["session_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            is_complete=data.get("is_complete", True),
        )


@dataclass
class CommandResult:
    """Result from executing a kiro-cli command."""
    
    success: bool
    output: str
    error: str | None = None
    exit_code: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommandResult":
        """Create from dictionary."""
        return cls(
            success=data["success"],
            output=data["output"],
            error=data.get("error"),
            exit_code=data.get("exit_code", 0),
        )


@dataclass
class SessionInfo:
    """Information about a kiro-cli session."""
    
    id: str
    agent: str | None
    working_directory: str
    created_at: str
    last_active: str
    is_active: bool
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "agent": self.agent,
            "working_directory": self.working_directory,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "is_active": self.is_active,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionInfo":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            agent=data.get("agent"),
            working_directory=data["working_directory"],
            created_at=data["created_at"],
            last_active=data["last_active"],
            is_active=data.get("is_active", True),
        )


@dataclass
class AgentInfo:
    """Information about a custom agent."""
    
    name: str
    description: str | None = None
    config_path: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "config_path": self.config_path,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentInfo":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            description=data.get("description"),
            config_path=data.get("config_path"),
        )


@dataclass
class HistoryMessage:
    """A message in conversation history."""
    
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HistoryMessage":
        """Create from dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )
