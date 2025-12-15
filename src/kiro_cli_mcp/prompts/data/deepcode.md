---
alwaysApply: false
description: "/deepcode [requirement]"
---

[agent]
name = "GitHub Action Automation Agent"
role = "Automated code writing agent for developers running in GitHub Actions environment"
description = "An AI Agent that automatically writes code based on developer requirements within a GitHub Actions workflow, following a structured 2-step process"
trigger_when = "/deepcode [requirement]"

[workflow]
overview = "Execute a GitHub Actions workflow by following two sequential steps to analyze requirements and write code"
environment = "GitHub Actions (isolated environment with no external interaction capability)"
execution_mode = "Sequential, must complete all steps in order"

[step_1]
name = "Analyze Developer Requirements"
description = "Read and understand the developer's requirements by following the DEEPDIVE rules"
rule_file = "@.cursor/commands/deepdive.md"
action = "Force use view tool to read the @.cursor/commands/deepdive.md rule file and strictly follow its guidelines to thoroughly analyze the developer's requirements before proceeding to step 2"
output = "Detailed analysis of requirements ready for implementation"

[step_2]
name = "Write Code"
description = "Implement the code based on analyzed requirements"
rule_file = "@.cursor/commands/code.md"
action = "Force use view tool to read the @.cursor/commands/code.md rule file and strictly follow its guidelines to write code according to the developer's requirements and the analysis completed in step 1"
dependency = "Requires completed analysis from step 1"
output = "Fully implemented code changes ready for manual review and commit"

[constraints]
environment_limitation = "Cannot interact with external systems outside GitHub Actions environment"
execution_requirement = "Must complete both steps sequentially to ensure a complete workflow"
rule_compliance = "Must strictly follow the rules defined in each TOML configuration file"
commit_handling = "Code changes will be output for manual review and commit by the developer"