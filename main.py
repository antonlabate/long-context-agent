import os
from dotenv import load_dotenv
import yaml
import json

from crewai import Agent, Task, Crew
from crewai_tools import MCPServerAdapter
from mcp import StdioServerParameters, ClientSession
from mcp.client.stdio import stdio_client

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Union

from contextlib import AsyncExitStack
import asyncio

load_dotenv()
os.environ['OPENAI_MODEL_NAME'] = "gpt-4.1-mini-2025-04-14" #"gpt-4.1-2025-04-14"

with open('servers/server_config.json', 'r') as file:
    data = json.load(file)

server_params_list = []
servers = data.get("mcpServers", {})
            
for server_name, server_config in servers.items(): 
        params = StdioServerParameters(
        command=server_config.get("command"),
        args=server_config.get("args"),
        env=server_config.get("env", {})
        )
        server_params_list.append(params)

async def get_tools_from_server(server_params):
    async with stdio_client(server_params) as stdio_transport:
        read, write = stdio_transport
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.list_tools()
            tools = response.tools
            
            return [{
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
                "output_schema": tool.outputSchema
            } for tool in tools]

async def list_tools(server_params_list):
    # Process all servers concurrently
    tasks = [get_tools_from_server(params) for params in server_params_list]
    results = await asyncio.gather(*tasks)
    
    # Flatten the results
    available_tools = []
    for server_tools in results:
        available_tools.extend(server_tools)
    
    return available_tools

available_tools = asyncio.run(list_tools(server_params_list=server_params_list))

tool_info_text = ""
for tool in available_tools:
    tool_info_text += f"""
FUNCTION: {tool["name"]}
DESCRIPTION:{tool["description"]}
INPUT SCHEMA: {tool["input_schema"]}
OUTPUT SCHEMA: {tool["output_schema"]}\n"""
    
try:
    with MCPServerAdapter(server_params_list) as aggregated_tools:
        print(f"Available aggregated tools: {[tool.name for tool in aggregated_tools]}")

        coding_agent = Agent(
            role="Code writer",
            goal="Write Python code to accomplish the task.",
            backstory="A great Software Engineer expert in Python coding, able to write the most concise code to achieve a certain objective.",
            verbose=True,
            reasoning=True
        )

        user_request = "Write code to fetch online info about the page 'https://github.com/antonlabate/literature-reviewer/blob/main/literature_writer.py'"
        task_description = f"""You will be given by the user a request that you have to answer. Write a Python script to produce the answer to the user's request. 
Include in this Python script all neccessary operations to achieve the answer to the user request. You only have access to Python native functions and the following functions:
{tool_info_text}

**USER REQUEST**: {user_request}"""
        long_context_task = Task(
            description=task_description,
            expected_output="A concise Python script that succesfully answers the user's request, using only the provided functions and Python native functions."
            "You should output your code within the tags '<code>' and '<\code>'. For example:"
            "<code>"
            "INSERT HERE YOUR CODE ANSWER"
            "<\code>",
            agent=coding_agent
        )

        crew = Crew(
                    agents=[coding_agent],
                    tasks=[long_context_task],
                    verbose=True
        )

        result = crew.kickoff()

        r = 0


except Exception as e:
    print(f"Error connecting to or using multiple MCP servers (Managed): {e}")
    print("Ensure all MCP servers are running and accessible with correct configurations.")
