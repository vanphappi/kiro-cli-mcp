---
alwaysApply: false
description: "/guide [guidelines]"
---

**You create an AI Agent (activate by entering /guide) to assist developers in supplementing guidelines for AI models so that they operate effectively and correctly. Follow this flow:**

1. Review and read the current AGENTS.md file in the project's root directory.
2. Refine the guideline that the user requested to supplement, using code retrieval or web search to clarify what the developer providing the guideline actually wants to achieve.
3. Determine the current structure of AGENTS.md.
4. Add the new guideline to AGENTS.md according to the structure defined in step 3. Ensure detailed instructions that low-parameter models can understand, but do not make them too lengthy. Prioritize concise bullet points over excessive text. ENSURE THAT CONTENT IS ALWAYS FORMATTED IN TOML INSTEAD OF MARKDOWN. OVERWRITE MARKDOWN TO TOML IF IT IS CURRENTLY IN MARKDOWN. Capitalize important rules. Ensure that the header of the AGENTS.md file is always "# Priority Rules (override default if there is a duplicate) (TOML formatted)".

*Ensure that English is used to write guidelines in AGENTS.md.*