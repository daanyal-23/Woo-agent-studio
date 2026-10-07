"""MCP stdio client wrapper for the agent demo.

Manages connection to the WooCommerce MCP server subprocess over stdio,
discovers tools, and converts MCP schemas into the format expected by Groq.
"""

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import Tool


def build_mcp_subprocess_env() -> dict[str, str]:
    """Construct a clean, minimal environment dictionary for the MCP subprocess.

    Passes only necessary execution paths and explicitly required WooCommerce variables.
    Does NOT load or print .env.
    """
    env: dict[str, str] = {
        # Core OS execution variables needed to boot Python on Windows/Linux
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
    }

    # Pass only required WooCommerce settings
    if "WOO_BASE_URL" in os.environ:
        env["WOO_BASE_URL"] = os.environ["WOO_BASE_URL"]
    if "WOO_CONSUMER_KEY" in os.environ:
        env["WOO_CONSUMER_KEY"] = os.environ["WOO_CONSUMER_KEY"]
    if "WOO_CONSUMER_SECRET" in os.environ:
        env["WOO_CONSUMER_SECRET"] = os.environ["WOO_CONSUMER_SECRET"]
    if "WOO_ALLOW_INSECURE_HTTP" in os.environ:
        env["WOO_ALLOW_INSECURE_HTTP"] = os.environ["WOO_ALLOW_INSECURE_HTTP"]
    if "WOO_TIMEOUT_SECONDS" in os.environ:
        env["WOO_TIMEOUT_SECONDS"] = os.environ["WOO_TIMEOUT_SECONDS"]

    return env


def mcp_tool_to_groq_spec(tool: Tool) -> dict[str, Any]:
    """Convert an MCP Tool definition to the OpenAI/Groq function tool schema format."""
    schema = getattr(tool, "inputSchema", getattr(tool, "input_schema", {}))
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": schema,
        },
    }


class MCPConnectorClient:
    """High-level client wrapper around an active MCP ClientSession."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._tools: list[Tool] = []
        self._tool_map: dict[str, Tool] = {}

    async def initialize(self) -> None:
        """Initialize the MCP session and discover available tools."""
        await self._session.initialize()
        tools_result = await self._session.list_tools()
        self._tools = list(tools_result.tools)
        self._tool_map = {t.name: t for t in self._tools}

    @property
    def tools(self) -> list[Tool]:
        """Raw list of discovered MCP tools."""
        return self._tools

    @property
    def tool_names(self) -> set[str]:
        """Set of available tool names."""
        return set(self._tool_map.keys())

    def get_groq_tools(self) -> list[dict[str, Any]]:
        """Return all discovered tools formatted as Groq function tool specs."""
        return [mcp_tool_to_groq_spec(t) for t in self._tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Invoke a tool by name with arguments through the MCP session.

        Returns string content for consumption by the LLM.
        """
        if name not in self._tool_map:
            available = list(self.tool_names)
            return f"Error: Tool '{name}' is not recognized. Available tools: {available}"

        res = await self._session.call_tool(name, arguments)
        parts = [item.text for item in res.content if hasattr(item, "text")]
        result_text = "\n".join(parts) if parts else ""

        if res.is_error:
            return f"Tool Execution Error: {result_text}"
        return result_text


@asynccontextmanager
async def connect_mcp_client(
    python_executable: str | None = None,
    server_module: str = "woo_connector.mcp_server",
) -> AsyncIterator[MCPConnectorClient]:
    """Spawn the WooCommerce MCP server subprocess over stdio and yield a ready client."""
    cmd = python_executable or sys.executable
    server_env = build_mcp_subprocess_env()

    server_params = StdioServerParameters(
        command=cmd,
        args=["-m", server_module],
        env=server_env,
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            client = MCPConnectorClient(session)
            await client.initialize()
            yield client
