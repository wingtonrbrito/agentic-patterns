# {Skill Name}

description: Brief description of what this skill does
triggers: ["keyword1", "keyword2", "phrase"]
mcp_servers: ["server-name"]
priority: 0

---

## Instructions

Step-by-step instructions for the agent when this skill is activated.

1. First, do this
2. Then, do that
3. Finally, validate the output

## Examples

```example
User: Example query
Agent: Example response with tool usage
```

## Constraints

- **Constraint**: Always scope queries by tenant_id
- **Constraint**: Never return more than 10 results without pagination
- **Constraint**: Always cite sources in responses
