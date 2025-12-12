"""Tool definitions for Kiro CLI MCP Server."""

from typing import Any

# Tool definitions following MCP specification
TOOLS: list[dict[str, Any]] = [
    {
        "name": "kiro_chat",
        "description": "Send a chat message to kiro-cli and get AI response",
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
        "name": "kiro_session_switch",
        "description": "Switch to a specific session",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID to switch to"
                }
            },
            "required": ["session_id"]
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
        "description": "Execute a kiro-cli command (e.g., /mcp, /help)",
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
        "name": "kiro_agents_list",
        "description": "List available custom agents",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "kiro_history",
        "description": "Get conversation history for a session",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to return",
                    "default": 50
                }
            }
        }
    },
    {
        "name": "kiro_history_clear",
        "description": "Clear conversation history for a session",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID"
                }
            }
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
    },
    {
        "name": "kiro_task_cancel",
        "description": "Cancel a running async task",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID to cancel"
                }
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "kiro_task_list",
        "description": "List active async tasks",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional filter by session ID"
                },
                "include_done": {
                    "type": "boolean",
                    "description": "Include completed/failed tasks",
                    "default": False
                }
            }
        }
    },
    {
        "name": "kiro_pool_stats",
        "description": "Get process pool statistics for performance monitoring",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "kiro_session_clear",
        "description": "Clear kiro-cli session history in working directory (deletes .kiro/session.json)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional MCP session ID"
                }
            }
        }
    },
    {
        "name": "kiro_session_save",
        "description": "Save current kiro-cli session to a file using /save command",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional MCP session ID"
                },
                "path": {
                    "type": "string",
                    "description": "Path to save session (relative to working directory)"
                }
            },
            "required": ["path"]
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
