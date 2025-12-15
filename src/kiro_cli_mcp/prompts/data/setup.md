---
alwaysApply: false
description: "/setup [language typescript|python]"
---

# You are an agent capable of editing the AGENTS.md file to add necessary rules when initializing a project based on the programming language provided by the user.

Your task is to add the following rule to the ./AGENTS.md file in the root project with the following content of https://raw.githubusercontent.com/nullmastermind/prompts/refs/heads/master/common.augment-guidelines (fetch this url to get the content). Follow this flow:

1. fetch https://raw.githubusercontent.com/nullmastermind/prompts/refs/heads/master/common.augment-guidelines to get rule's content.

2. Check if ./AGENTS.md exists; if not, create the ./AGENTS.md file with step 1 content. If it exists, read ./AGENTS.md and append the content from step 1 to the current file.

3. Depending on the programming language provided, follow the subflow below:
   - Typescript:
     - Check if bun is installed by running `bun -v`. If not, close the flow and ask the user to install bun.
     - Check biome exists, if not install by `bun add -D -E @biomejs/biome` at root directory, then create the biome.json file in the root directory based on the content from URL: https://gist.githubusercontent.com/nullmastermind/f725561ef77f736bdbcde1a391580937/raw/20a9333e37974aadbd879bfa9f15c1359c9fc7e9/biome.json
     - Add lint script to package.json: `bunx biome check --write`
     - Add lint script to AGENTS.md: `ALWAYS run \`bun run lint\` at root directory after writing code to ensure code quality.` and `Linter: biome. NEVER run --unsafe, manually fix all errors.`.
   - Python:
     - Check if uv is installed by running `uv -V`. If not, close the flow and ask the user to install uv.
     - Add lint script to AGENTS.md: `ALWAYS run \`uv run ruff check\` at root directory after writing code to ensure code quality.` and run `uv run ruff format` after completing the coding task.
