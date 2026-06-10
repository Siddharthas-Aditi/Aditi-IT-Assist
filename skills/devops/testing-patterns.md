# Skill: Testing Patterns

> Testing standards for Aditi IT Assist (backend + frontend).

---

## Backend Testing (pytest)

### Unit Tests — Service Layer

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.chat_service import ChatService

@pytest.mark.asyncio
async def test_process_message_returns_response():
    """ChatService processes a message and returns response."""
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = "Try restarting Outlook."
    mock_repo = AsyncMock()

    service = ChatService(llm=mock_llm, repo=mock_repo)
    result = await service.process_message(ChatMessageCreate(message="Outlook broken"))

    assert result.message is not None
    assert result.confidence > 0
    mock_llm.generate.assert_called_once()
```

### Workflow Node Tests

```python
@pytest.mark.asyncio
async def test_triage_classifies_email():
    state = {
        "messages": [HumanMessage(content="Not receiving emails")],
        "session_id": "test",
        "turn_count": 0,
    }
    result = await triage_node(state)
    assert result["issue_category"] == "email/outlook"
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

---

## Frontend Testing (Vitest + RTL)

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatInput } from './ChatInput';

test('calls onSend when submit button clicked', () => {
  const onSend = vi.fn();
  render(<ChatInput onSend={onSend} />);

  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Hello' } });
  fireEvent.click(screen.getByRole('button', { name: /send/i }));

  expect(onSend).toHaveBeenCalledWith('Hello');
});
```

---

## What to Test

| Layer | Coverage Target | Focus |
|-------|----------------|-------|
| Workflow nodes | 100% happy path | State transitions |
| Service methods | 80%+ | Business logic |
| Repositories | Integration only | Query correctness |
| API routes | Happy + error paths | HTTP contract |
| Components | User interactions | Behavior, not impl |

---

## Running Tests

```bash
make test-backend     # pytest backend/tests/
make test-frontend    # vitest frontend/
make test             # Both
make coverage         # With coverage report
```
