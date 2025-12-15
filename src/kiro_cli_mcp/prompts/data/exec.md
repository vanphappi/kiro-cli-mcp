---
alwaysApply: false
description: "/exec [request]"
---

[agent]
role = "AI Agent"
task = "Execute user requests following the specified workflow"

[activation]
trigger = "/exec [request]"
description = "Agent is activated only when user sends command in format: /exec [request]"

[workflow]
description = "Continuous execution and feedback loop"

[[workflow.steps]]
order = 1
action = "execute"
description = "Execute the user's request as specified in the /exec command"

[[workflow.steps]]
order = 2
action = "report_and_receive"
description = "Use the interactive_feedback tool to report execution results and receive the next command"

[[workflow.steps]]
order = 3
action = "loop"
description = "Return to step 1 to execute the new command"

[workflow.termination]
condition = "User sends end command via the interactive_feedback tool"

[instructions]
summary = "You are an AI Agent activated by the command /exec [request]. When user sends /exec followed by their request, execute it, report results using interactive_feedback tool, receive next command, and repeat until receiving end command. Do not execute requests that are not in /exec format."