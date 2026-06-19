# MCP (Model Context Protocol) integration for MindOS
#
# MCP servers expose tools that LLMs can discover and call.
# MCP clients connect to servers and route tool calls from the LLM.
#
# Safety: Every MCP server validates calls independently.
# The LLM is never trusted — all side-effect operations require confirmation.
