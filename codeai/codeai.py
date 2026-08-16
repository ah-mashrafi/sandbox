#!/usr/bin/env python3

import os
import subprocess
from pathlib import Path

from openai import OpenAI


MODEL = "gpt-5.6"

SYSTEM_PROMPT = """
You are CodeAI, a terminal-based coding assistant.

You are helping the user work on a software project.

Rules:
- Be concise and practical.
- When the user asks about code, explain the actual problem.
- Use available tools when you need information from the project.
- Never assume the contents of a file you haven't read.
- Never claim you executed a command unless you actually did.
- Before making destructive changes, ask the user for confirmation.
- Prefer small, safe changes.
- When showing code changes, clearly identify the file and relevant code.
"""


client = OpenAI()


def read_file(path):
    try:
        file_path = Path(path).resolve()

        if not file_path.is_file():
            return f"Error: {path} is not a file."

        if file_path.stat().st_size > 1_000_000:
            return "Error: file is larger than 1 MB."

        return file_path.read_text(errors="replace")

    except Exception as e:
        return f"Error reading {path}: {e}"


def list_files(path="."):
    try:
        root = Path(path).resolve()

        if not root.is_dir():
            return f"Error: {path} is not a directory."

        files = []

        for item in root.rglob("*"):
            if ".git" in item.parts:
                continue
            if ".venv" in item.parts:
                continue

            if item.is_file():
                files.append(str(item.relative_to(root)))

            if len(files) >= 200:
                break

        if not files:
            return "No files found."

        return "\n".join(files)

    except Exception as e:
        return f"Error listing files: {e}"


def search_files(query, path="."):
    try:
        root = Path(path).resolve()
        results = []

        for file in root.rglob("*"):
            if not file.is_file():
                continue

            if ".git" in file.parts or ".venv" in file.parts:
                continue

            try:
                text = file.read_text(errors="ignore")
            except Exception:
                continue

            for line_number, line in enumerate(text.splitlines(), 1):
                if query.lower() in line.lower():
                    results.append(
                        f"{file.relative_to(root)}:{line_number}: {line.strip()}"
                    )

                    if len(results) >= 100:
                        return "\n".join(results)

        return "\n".join(results) if results else "No matches found."

    except Exception as e:
        return f"Error searching project: {e}"


def run_command(command):
    print()
    print(f"AI wants to run:")
    print(f"  $ {command}")
    print()

    answer = input("Allow? [y/N]: ").strip().lower()

    if answer != "y":
        return "Command rejected by user."

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = ""

        if result.stdout:
            output += result.stdout

        if result.stderr:
            output += "\n[stderr]\n" + result.stderr

        if not output:
            output = "(no output)"

        return (
            f"Exit code: {result.returncode}\n"
            f"{output[:20_000]}"
        )

    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."

    except Exception as e:
        return f"Error running command: {e}"


TOOLS = [
    {
        "type": "function",
        "name": "read_file",
        "description": "Read a text file from the current project.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file."
                }
            },
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "list_files",
        "description": "List files in the current project.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to inspect."
                }
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "search_files",
        "description": "Search project files for a text string.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for."
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search."
                }
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "run_command",
        "description": "Run a shell command after getting user confirmation.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute."
                }
            },
            "required": ["command"],
        },
    },
]


def call_tool(name, arguments):
    if name == "read_file":
        return read_file(arguments["path"])

    if name == "list_files":
        return list_files(arguments.get("path", "."))

    if name == "search_files":
        return search_files(
            arguments["query"],
            arguments.get("path", "."),
        )

    if name == "run_command":
        return run_command(arguments["command"])

    return f"Unknown tool: {name}"


def ask_ai(history):

    response = client.responses.create(
        model=MODEL,
        instructions=SYSTEM_PROMPT,
        input=history,
        tools=TOOLS,
    )

    while True:

        tool_calls = [
            item
            for item in response.output
            if item.type == "function_call"
        ]

        if not tool_calls:
            return response.output_text

        history.extend(response.output)

        for call in tool_calls:

            import json

            arguments = json.loads(call.arguments)

            result = call_tool(
                call.name,
                arguments,
            )

            history.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": result,
                }
            )

        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM_PROMPT,
            input=history,
            tools=TOOLS,
        )


def main():

    print()
    print("╭──────────────────────────────────────────╮")
    print("│                 CODEAI                   │")
    print("│       Terminal Coding Assistant          │")
    print("╰──────────────────────────────────────────╯")
    print()

    print(f"Project: {Path.cwd()}")
    print("Type 'exit' to quit.")
    print()

    history = []

    while True:

        try:
            user_input = input("You > ").strip()

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        history.append(
            {
                "role": "user",
                "content": user_input,
            }
        )

        try:
            answer = ask_ai(history)

            print()
            print("AI >")
            print(answer)
            print()

            history.append(
                {
                    "role": "assistant",
                    "content": answer,
                }
            )

        except Exception as e:
            print()
            print(f"Error: {e}")
            print()


if __name__ == "__main__":
    main()
