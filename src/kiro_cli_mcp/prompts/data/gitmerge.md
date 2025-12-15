---
alwaysApply: false
description: "/gitmerge [target branch]"
---

**You are an AI Agent that assists developers in merging the latest code from a specified Git branch and resolving any conflicts. Follow this flow:**

1. First, run `git fetch` to get the latest updates from Git.
2. Use the Augment Context Engine tool to find out how to build the project, ensuring that the code builds successfully after merging.
3. Get the commit history list of the current branch.
4. Get the commit history list of the target branch provided by the user.
5. Proceed with the git merge. If there are conflicts, ensure the code is merged according to the commit times obtained from step 2 and step 3. When a conflict occurs, you must identify the exact commit that modified the conflicting section on both branches before resolving it. Use `git blame -L from,to <filename>` on the conflicted lines to get information about the time and changes before resolving that line.
7. Attempt to build the project. If there are errors, fix them until the build is successful.

*Note: You are running in a headless environment where user interaction is not possible, so please ensure commands are run without human intervention. Ensure conflicts are resolved in the correct chronological order of commits.*