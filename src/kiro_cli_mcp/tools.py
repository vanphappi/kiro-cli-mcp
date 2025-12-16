"""Tool definitions for Kiro CLI MCP Server."""

from typing import Any

# Tool definitions following MCP specification
# Streamlined to 7 essential tools
TOOLS: list[dict[str, Any]] = [
    {
        "name": "kiro_chat",
        "description": "Send a chat message to kiro-cli and get AI response. Supports AI-powered prompt selection based on message content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to send to kiro-cli"
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID. Uses active session if not provided"
                },
                "stream": {
                    "type": "boolean",
                    "description": "Whether to stream the response",
                    "default": False
                },
                "skip_prompt_matching": {
                    "type": "boolean",
                    "description": "Skip AI-powered prompt selection and send message as-is",
                    "default": False
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "kiro_session_create",
        "description": "Create a new kiro-cli session. If working_directory is not provided or does not exist, the current directory will be used.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "Optional agent name to use for this session"
                },
                "working_directory": {
                    "type": "string",
                    "description": "Working directory for the session. Must be an existing directory path. If not provided or invalid, defaults to current directory."
                }
            }
        }
    },
    {
        "name": "kiro_session_list",
        "description": "List all active kiro-cli sessions",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "kiro_session_end",
        "description": "End a kiro-cli session",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID to end"
                }
            },
            "required": ["session_id"]
        }
    },
    {
        "name": "kiro_command",
        "description": "Execute a kiro-cli command (e.g., /mcp, /help, /clear, /save, /agents)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to execute"
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "kiro_chat_async",
        "description": "Start an async chat task for streaming-like experience. Use kiro_task_status to poll for results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to send to kiro-cli"
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID. Uses active session if not provided"
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "kiro_task_status",
        "description": "Get status and partial results of an async task. Use for polling streaming results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID returned by kiro_chat_async"
                },
                "from_chunk_index": {
                    "type": "integer",
                    "description": "Get chunks starting from this index (for incremental updates)",
                    "default": 0
                }
            },
            "required": ["task_id"]
        }
    }
]


def get_tool_by_name(name: str) -> dict[str, Any] | None:
    """Get tool definition by name."""
    for tool in TOOLS:
        if tool["name"] == name:
            return tool
    return None


def get_all_tools() -> list[dict[str, Any]]:
    """Get all tool definitions."""
    return TOOLS.copy()
