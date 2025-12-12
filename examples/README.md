# Kiro CLI MCP Server - Configuration Examples

## mcp.json

Example MCP configuration for use with Kiro IDE or other MCP clients.

### Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| **Logging** |||
| `KIRO_MCP_LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `KIRO_MCP_LOG_RESPONSE` | `true` | Log full CLI response for debugging |
| **Timeouts** |||
| `KIRO_MCP_COMMAND_TIMEOUT` | `30` | Seconds to wait for kiro-cli response (0 = unlimited) |
| **Session Management** |||
| `KIRO_MCP_MAX_SESSIONS` | `10` | Max concurrent sessions (0 = unlimited) |
| `KIRO_MCP_SESSION_TIMEOUT` | `300` | Seconds before inactive session is cleaned up |
| `KIRO_MCP_CLEANUP_INTERVAL` | `30` | Seconds between cleanup checks |
| `KIRO_MCP_WORKING_DIRECTORY` | *current* | Default working directory for sessions |
| **Kiro-CLI Defaults** |||
| `KIRO_MCP_CLI_PATH` | `kiro-cli` | Path to kiro-cli executable |
| `KIRO_MCP_DEFAULT_MODEL` | `claude-opus-4.5` | Default model: `claude-opus-4.5`, `claude-sonnet-4.5`, `auto` |
| `KIRO_MCP_DEFAULT_AGENT` | `kiro_default` | Default agent name (empty for none) |
| **Process Pool (Performance)** |||
| `KIRO_MCP_POOL_ENABLED` | `true` | Enable process reuse for faster responses |
| `KIRO_MCP_POOL_SIZE` | `5` | Maximum pooled processes |
| `KIRO_MCP_POOL_IDLE_TIME` | `300` | Seconds before idle process is recycled |
| `KIRO_MCP_POOL_MAX_USES` | `100` | Max uses per process before recycling |
| **Async Tasks (Streaming)** |||
| `KIRO_MCP_MAX_ASYNC_TASKS` | `100` | Max concurrent async chat tasks |
| `KIRO_MCP_TASK_TTL` | `3600` | Seconds to keep completed task results |

### Minimal Configuration

```json
{
  "mcpServers": {
    "kiro-cli-mcp": {
      "command": "python",
      "args": ["-m", "kiro_cli_mcp"]
    }
  }
}
```

### Production Configuration

```json
{
  "mcpServers": {
    "kiro-cli-mcp": {
      "command": "python",
      "args": ["-m", "kiro_cli_mcp"],
      "env": {
        "KIRO_MCP_LOG_LEVEL": "WARNING",
        "KIRO_MCP_COMMAND_TIMEOUT": "120",
        "KIRO_MCP_LOG_RESPONSE": "false",
        "KIRO_MCP_POOL_ENABLED": "true",
        "KIRO_MCP_POOL_SIZE": "10"
      }
    }
  }
}
```

### Available Tools

| Tool | Description | Auto-Approve Safe? |
|------|-------------|-------------------|
| `kiro_chat` | Send chat message to kiro-cli | ❌ |
| `kiro_chat_async` | Start async chat (for streaming) | ❌ |
| `kiro_session_create` | Create new session | ❌ |
| `kiro_session_list` | List all sessions | ✅ |
| `kiro_session_switch` | Switch active session | ❌ |
| `kiro_session_end` | End a session | ❌ |
| `kiro_session_clear` | Clear kiro-cli session file | ❌ |
| `kiro_session_save` | Save session to file | ❌ |
| `kiro_command` | Execute kiro-cli command | ❌ |
| `kiro_agents_list` | List available agents | ✅ |
| `kiro_history` | Get conversation history | ✅ |
| `kiro_history_clear` | Clear history | ❌ |
| `kiro_task_status` | Get async task status | ✅ |
| `kiro_task_cancel` | Cancel async task | ❌ |
| `kiro_task_list` | List async tasks | ✅ |
| `kiro_pool_stats` | Get process pool stats | ✅ |
