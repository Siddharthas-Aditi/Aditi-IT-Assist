# QA Agent Prompt

Ensure quality for Aditi IT Assist:

## Testing Strategy
- Unit tests for all service methods and workflow nodes
- Integration tests for API endpoints
- Mock external services (LLM, email)
- Minimum 80% coverage on service layer
- Use pytest-asyncio for async tests

## Quality Checks
- `make lint` passes (Ruff + ESLint)
- `make typecheck` passes (mypy + tsc)
- No hardcoded values
- Error handling on all paths
- Input validation via Pydantic
