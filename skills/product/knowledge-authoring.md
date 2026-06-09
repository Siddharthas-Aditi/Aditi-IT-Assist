# Knowledge Authoring

## Knowledge Article Format (YAML)
```yaml
category: "category/subcategory"
description: "What this playbook covers"

articles:
  - id: "unique-id"
    title: "Human-readable title"
    category: "primary-category"
    subcategory: "specific-issue"
    tags: ["searchable", "keywords"]
    content: |
      Detailed description of the issue and context.
    steps:
      - step_number: 1
        instruction: "What to do"
        details: "How to do it specifically"
    escalation_trigger: "When to give up and escalate"
    resolution_rate: 0.75
```

## Guidelines
- Each step must be actionable and specific
- Include expected outcomes
- Keep language clear and non-technical where possible
- Always include an escalation_trigger
- Tag articles generously for search
