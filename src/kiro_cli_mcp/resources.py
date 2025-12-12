"""Resource definitions for Kiro CLI MCP Server."""

from typing import Any

# Resource definitions following MCP specification
RESOURCES: list[dict[str, Any]] = [
    {
        "uri": "kiro://sessions",
        "name": "Active Sessions",
        "description": "List of all active kiro-cli sessions",
        "mimeType": "application/json"
    },
    {
        "uri": "kiro://agents",
        "name": "Available Agents",
        "description": "List of configured custom agents",
        "mimeType": "application/json"
    },
    {
        "uri": "kiro://config",
        "name": "Server Configuration",
        "description": "Current server configuration (read-only)",
        "mimeType": "application/json"
    }
]


def get_resource_by_uri(uri: str) -> dict[str, Any] | None:
    """Get resource definition by URI."""
    for resource in RESOURCES:
        if resource["uri"] == uri:
            return resource
    return None


def get_all_resources() -> list[dict[str, Any]]:
    """Get all resource definitions."""
    return RESOURCES.copy()
