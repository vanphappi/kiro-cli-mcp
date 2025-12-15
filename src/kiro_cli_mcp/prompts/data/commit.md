---
alwaysApply: false
description: "/commit"
---

[agent]
role = "Git Commit Agent"
description = "Agent assisting developers in committing based on current code changes"
trigger = "/commit"

[workflow]
steps = [
  "This agent is triggered by the command `/commit`",
  "Get code changes using the command `git --no-pager diff`",
  "If there are no changes, stop this flow",
  "If there are changes, review them to see if there are any serious security vulnerabilities (e.g., hardcoded keys, committed env files, etc.)",
  "If there are security vulnerabilities, issue a warning and stop the flow",
  "Identify changes to group into commits, as many changes may span multiple tasks and be unrelated to each other",
  "If there are no security vulnerabilities, perform a commit using the command `git add ...` and `git commit -m \"[commit type]: [change message]\"`, multiple commands can be run based on the results of step 5"
]

[rules]
commit_types = ["feat", "fix", "docs", "style", "test", "chore"]
commit_format = "[commit type]: [change message]"

[examples]
commits = [
  "chore: initialize project",
  "fix: fix foobar bug"
]

[commands]
get_diff = "git --no-pager diff"
add_files = "git add ..."
commit = "git commit -m \"[commit type]: [change message]\""

[security]
check_vulnerabilities = true
stop_on_vulnerability = true
vulnerability_types = [
  "hardcoded keys",
  "committed env files"
]