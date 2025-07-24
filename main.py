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

server_params_info = {}
servers = data.get("mcpServers", {})
            
for server_name, server_config in servers.items(): 
        params = StdioServerParameters(
        command=server_config.get("command"),
        args=server_config.get("args"),
        env=server_config.get("env", {})
        )
        server_params_info[server_name] = params

async def get_tools_from_server(name, server_params):
    
    async with stdio_client(server_params) as stdio_transport:
        read, write = stdio_transport
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.list_tools()
            tools = response.tools
            """ 
            return [{
                "name": name+"-"+tool.name, # define unique names for tools, consisting of session-tool
                "description": tool.description,
                "input_schema": tool.inputSchema,
                "output_schema": tool.outputSchema,
                "session": name
            } for tool in tools]
            """

            return {
                f"{name}-{tool.name}":{
                "name": name+"-"+tool.name, # define unique names for tools, consisting of session-tool
                "description": tool.description,
                "input_schema": tool.inputSchema,
                "output_schema": tool.outputSchema,
                "session": name
                }
            for tool in tools
            }
           


async def list_tools(server_params_info):
    # Process all servers concurrently
    tasks = [get_tools_from_server(name, params) for name, params in server_params_info.items()]
    results = await asyncio.gather(*tasks)
    
    """ 
    # Flatten the results
    available_tools = []
    for server_tools in results:
        available_tools.extend(server_tools)
    """
    available_tools = {k: v for d in results for (k, v) in d.items()}

    
    #fetch_tool = await available_tools[0]["session"].call_tool("fetch", {"url":"https://en.wikipedia.org/wiki/Vicia_faba"})
    
    return available_tools

async def run_tool(tool, server_params_info, function_args):

    server_params = server_params_info[tool["session"]]

    async with stdio_client(server_params) as stdio_transport:
        read, write = stdio_transport
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool["name"], arguments=function_args)
            r = 0

    return result

available_tools = asyncio.run(list_tools(server_params_info=server_params_info))

tool_info_text = ""
for tool in available_tools.values():
    tool_info_text += f"""
FUNCTION: {tool["name"]}
DESCRIPTION:{tool["description"]}
INPUT SCHEMA: {tool["input_schema"]}
OUTPUT SCHEMA: {tool["output_schema"]}\n"""
    
async def _run(tool_name, function_args):

    server_params = server_params_info[available_tools[tool_name]["session"]]

    async with stdio_client(server_params) as stdio_transport:
        read, write = stdio_transport
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool["name"], arguments=function_args)
            r = 0

    return result

result = asyncio.run(_run("fetch-fetch", function_args={"url":"https://en.wikipedia.org/wiki/Vicia_faba"}))
    
server_params_list = list(server_params_info.values())
    
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
Include in this Python script all neccessary operations to achieve the answer to the user request. You only have access to Python native functions and the following MCP tools:
{tool_info_text}

If you wish to run any of the provided MCP functions, you can call them using the auxiliary function '_run', defined at the start of the code.
To use it for running a MCP function, you just need to call it with the arguments: (tool_name=<INSERT HERE THE NAME OF THE TOOL YOU WISH TO USE>>, function_args=<<INSERT HERE THE DICT OF THE TOOL ARGS>>). 
Note that the tool arguments need to be passed as a dict to the auxiliar function '_run'. The execution of '_run' will return the result of the tool that you chose with your arguments.
An example usage is:
```
result = asyncio.run(_run(tool_name="github-list_branches", function_args={{"owner":"john_doe", "repo":"my-awesome-app"}}))
```

It is provided to you the start of the code, which contains the initialization of the MCP servers and an auxiliary function to run the MCP tools.
DO NOT ALTER IT, COPY IT IN YOUR ANSWER AND CONTINUE YOUR ANSWER AFTER IT. An example of execution is provided below:

```
USER REQUEST: List all of the branches made by the user 'john_doe' in the repository 'my-awesome-app'.
<code_prefix>
async def _run(tool_name, function_args):

    server_params = server_params_info[available_tools[tool_name]["session"]]

    async with stdio_client(server_params) as stdio_transport:
        read, write = stdio_transport
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool["name"], arguments=function_args)
            r = 0

    return result
<\code_prefix>
<code>
result = asyncio.run(_run(tool_name="github-list_branches", function_args={{"owner":"john_doe", "repo":"my-awesome-app"}}))
return result
```

**GUIDELINES**:
    - Generate ONLY the python code as final answer - DO NOT PROVIDE EXPLANATIONS;
    - Write a CONCISE code, only writing what is neccesary for achieving the intended request;
    - DO NOT TRY TO CALL YOURSELF THE FUNCTIONS, only write them in the script.
    
NOW IT'S YOUR TURN:
**USER REQUEST**: {user_request}

START:
<code_prefix>
async def _run(tool_name, function_args):

    server_params = server_params_info[available_tools[tool_name]["session"]]

    async with stdio_client(server_params) as stdio_transport:
        read, write = stdio_transport
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool["name"], arguments=function_args)
            r = 0

    return result
<\code_prefix>
<code>


# WRITE YOUR CODE BELOW HERE

"""
        long_context_task = Task(
            description=task_description,
            expected_output="A concise Python script that succesfully answers the user's request, using only the provided functions and Python native functions."
            "You should output your code within the tags '<code>' and '<\code>'. For example:"
            "<code>"
            "INSERT HERE YOUR CODE ANSWER"
            "<\code>.",
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
