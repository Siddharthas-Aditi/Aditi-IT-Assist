# P1 Implementation Guide: Top 3 Gaps
## Context Summarization, Urgency Detection, Web Search Fallback

**Timeline**: 3 weeks (5 days each + 2 days integration)  
**Effort**: 1–2 engineers  
**Start**: Monday

---

## Gap 1: Context Summarization (Days 1–2)

### Problem
After 15+ turns, diagnostic context is 60+ fields of accumulated history. LLM prompt balloons, becomes expensive and slower.

### Solution
Auto-compress context every 10 turns into a 2–3 sentence summary.

### Files to Create/Modify

#### 1. Create `backend/app/services/agents/context_summarizer.py`

```python
"""Compress diagnostic context into concise summary."""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class ContextSummary:
    """Compressed view of conversation so far."""
    issue_one_liner: str  # "Outlook mailbox full, user cleared cache but still failing"
    entity: str  # "Outlook"
    attempted_solutions: list[str]  # ["Cleared cache", "Restarted"]
    current_status: str  # "Issue persists after 2 attempts"
    key_facts: dict  # {"uses_2fa": true, "device": "windows"}
    turn_count: int

class ContextSummarizerService:
    """Summarize DiagnosticContext to reduce LLM prompt size."""
    
    def __init__(self, llm_service: LLMService):
        self.llm = llm_service
    
    async def summarize(
        self, 
        diagnostic_context: DiagnosticContext
    ) -> ContextSummary:
        """
        Compress diagnostic context into 2–3 sentence summary.
        
        Input: 60+ fields of accumulated history
        Output: Concise summary for LLM prompt injection
        """
        filled_slots = diagnostic_context.get_filled_slots()
        
        # Build summary prompt
        summary_prompt = f"""
Summarize this IT support conversation in 2-3 sentences:

**Issue**: {diagnostic_context.issue_subtype or 'Unknown'}
**Entity**: {diagnostic_context.normalized_system}
**Symptom**: {diagnostic_context.exact_problem_statement}
**Attempts**: {', '.join(diagnostic_context.attempted_steps or [])}
**Results**: {', '.join(f'{step}→{outcome}' for step, outcome in zip(
    diagnostic_context.attempted_steps,
    diagnostic_context.failed_steps
) if outcome)}

Output format:
"User has [issue]. Tried [attempts] but [current status]. [key fact]."
        """
        
        summary_text = await self.llm.complete(
            system="You are a support ticket analyst. Summarize conversations concisely.",
            user_prompt=summary_prompt,
            temperature=0.3,  # Deterministic
        )
        
        return ContextSummary(
            issue_one_liner=summary_text.strip(),
            entity=diagnostic_context.normalized_system,
            attempted_solutions=diagnostic_context.attempted_steps or [],
            current_status=diagnostic_context.exact_problem_statement,
            key_facts=filled_slots,
            turn_count=len(diagnostic_context.suggested_steps) + len(diagnostic_context.failed_steps),
        )
    
    def should_summarize(self, turn_count: int) -> bool:
        """Summarize every 10 turns."""
        return turn_count > 0 and turn_count % 10 == 0
```

#### 2. Modify `backend/app/services/agents/chat_service.py`

```python
class ChatService:
    def __init__(
        self,
        repo: ChatRepository,
        workflow,
        context_summarizer: ContextSummarizerService,  # ADD
    ):
        self.repo = repo
        self.workflow = workflow
        self.context_summarizer = context_summarizer  # ADD
    
    async def process_message(self, data: ChatMessageCreate) -> ChatResponse:
        # ... existing code ...
        
        # AFTER running workflow, before returning:
        
        # Step 1: Check if we need to summarize
        turn_count = len(messages)
        if self.context_summarizer.should_summarize(turn_count):
            # Summarize accumulated context
            summary = await self.context_summarizer.summarize(
                workflow_output.diagnostic_context
            )
            workflow_output.diagnostic_context.conversation_summary = summary.issue_one_liner
            logger.info(f"Context summarized at turn {turn_count}: {summary.issue_one_liner}")
        
        # Step 2: Return response
        return ChatResponse(
            session_id=data.chat_id,
            message_id=uuid4(),
            content=workflow_output.messages[-1].content,
            # ... rest of response ...
        )
```

#### 3. Modify `backend/app/workflows/nodes/resolution.py`

When building LLM prompt, use summary instead of full history:

```python
async def resolution_node(state: AgentState) -> dict:
    """
    Resolution node: suggest troubleshooting steps.
    ENHANCE: Use context summary in LLM prompt to reduce size.
    """
    context = state.diagnostic_context
    
    # Build LLM prompt with context
    if context.conversation_summary:
        # Turn 11+: use summary + last 3 messages
        context_for_llm = f"""
## Conversation Summary (so far)
{context.conversation_summary}

## Latest Updates
{format_last_3_messages(state.messages[-3:])}
        """
    else:
        # Turn 1-10: use full context
        context_for_llm = format_full_context(context)
    
    system_prompt = f"""
You are an IT support analyst guiding {context.normalized_system} troubleshooting.

{context_for_llm}

Suggest next troubleshooting step (max 3 steps per turn).
    """
    
    # Call LLM
    response = await llm_service.complete(
        system=system_prompt,
        user_prompt=state.messages[-1].content,
    )
    
    # ... rest of node ...
```

### Tests to Add

**File**: `backend/tests/services/agents/test_context_summarizer.py`

```python
import pytest
from backend.app.services.agents.context_summarizer import ContextSummarizerService

@pytest.mark.asyncio
async def test_summarize_creates_concise_summary(mock_llm_service):
    """Summarize long context into 2-3 sentences."""
    summarizer = ContextSummarizerService(mock_llm_service)
    
    context = DiagnosticContext(
        issue_subtype="mailbox-full",
        normalized_system="Outlook",
        exact_problem_statement="Mailbox full, can't send emails",
        attempted_steps=["Cleared cache", "Restarted Outlook"],
        failed_steps=["Cache clear didn't help", "Restart didn't help"],
    )
    
    summary = await summarizer.summarize(context)
    
    # Verify summary is concise
    sentences = summary.issue_one_liner.count('.') + 1
    assert sentences <= 3, f"Summary too long: {summary.issue_one_liner}"
    
    # Verify key elements present
    assert "Outlook" in summary.issue_one_liner or "mailbox" in summary.issue_one_liner.lower()
    assert "Cleared cache" in summary.attempted_solutions or "cache" in summary.issue_one_liner.lower()

@pytest.mark.asyncio
async def test_should_summarize_every_10_turns(summarizer):
    """Trigger summary at turn 10, 20, 30, etc."""
    assert summarizer.should_summarize(0) == False
    assert summarizer.should_summarize(9) == False
    assert summarizer.should_summarize(10) == True  # ✅
    assert summarizer.should_summarize(11) == False
    assert summarizer.should_summarize(20) == True  # ✅

@pytest.mark.asyncio
async def test_summary_not_used_in_first_10_turns():
    """Context summary should be None until turn 10."""
    # Mock conversation: turns 1-9
    context = DiagnosticContext()
    assert context.conversation_summary is None
    
    # After turn 10 summary created
    context.conversation_summary = "Issue summary"
    assert context.conversation_summary == "Issue summary"
```

### Manual Testing

```
Turn 1: "I can't access my Outlook"
Turn 2-10: Regular troubleshooting (10 attempts)
Turn 11: 
  - Verify: summary created
  - Verify: LLM prompt uses summary, not full 60+ fields
  - Verify: response quality unchanged
  - Verify: latency reduced (fewer tokens to LLM)
```

---

## Gap 2: Urgency & Sentiment Detection (Days 3–4)

### Problem
Agent treats "I can't access email" same as "EMAIL IS DOWN!!!" — no tone adjustment.

### Solution
Detect urgency/frustration, adjust response tone and escalation threshold.

### Files to Create/Modify

#### 1. Create `backend/app/services/agents/sentiment_analyzer.py`

```python
"""Detect user tone: urgency, frustration, confusion."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

class Urgency(str, Enum):
    LOW = "low"            # "When you get a chance..."
    MEDIUM = "medium"      # "I need this soon"
    HIGH = "high"          # "ASAP", "Critical"
    CRITICAL = "critical"  # "System DOWN", "Can't work"

class Frustration(str, Enum):
    CALM = "calm"          # Matter-of-fact tone
    MILD = "mild"          # Some frustration ("This is annoying")
    HIGH = "high"          # Very frustrated ("I can't BELIEVE this!")

class Confusion(str, Enum):
    CLEAR = "clear"        # Knows exactly what's wrong
    CONFUSED = "confused"  # "Not sure what's happening"

@dataclass
class SentimentAnalysis:
    urgency: Urgency
    frustration: Frustration
    confusion: Confusion
    confidence: float  # 0.0-1.0
    raw_analysis: dict  # For debugging

class SentimentAnalyzerService:
    """Detect tone from user messages."""
    
    def __init__(self, llm_service: LLMService):
        self.llm = llm_service
    
    async def analyze(self, message: str) -> SentimentAnalysis:
        """
        Detect user sentiment: urgency, frustration, confusion.
        
        Args:
            message: User's chat message
            
        Returns:
            SentimentAnalysis with tone indicators
        """
        # First: pattern-based detection (fast)
        pattern_result = self._analyze_patterns(message)
        
        # If pattern confidence high (>0.8), use it
        if pattern_result.confidence >= 0.8:
            return pattern_result
        
        # Otherwise: LLM-based detection (more nuanced)
        llm_result = await self._analyze_with_llm(message)
        
        return llm_result
    
    def _analyze_patterns(self, message: str) -> SentimentAnalysis:
        """Fast pattern-based sentiment detection."""
        msg_lower = message.lower()
        
        # Urgency signals
        urgency_keywords = {
            "critical": Urgency.CRITICAL,
            "down": Urgency.CRITICAL,
            "can't work": Urgency.CRITICAL,
            "urgent": Urgency.HIGH,
            "asap": Urgency.HIGH,
            "now": Urgency.MEDIUM,
            "soon": Urgency.MEDIUM,
        }
        
        # Frustration signals
        frustration_patterns = {
            # Caps lock + exclamation = high frustration
            r"[A-Z]{5,}!": 0.9,  # "EMAIL!!!" → 0.9 frustration
            # Multiple exclamation marks = high frustration
            r"!{2,}": 0.8,
            # "Can't", "won't", "doesn't work" = some frustration
            r"(can't|won't|doesn't work)": 0.5,
            # Swearing = high frustration
            r"(damn|frustrated|angry)": 0.8,
        }
        
        # Detect urgency
        detected_urgency = Urgency.LOW
        for keyword, level in urgency_keywords.items():
            if keyword in msg_lower:
                detected_urgency = level
                break
        
        # Detect frustration
        frustration_score = 0.0
        for pattern, score in frustration_patterns.items():
            if re.search(pattern, message):
                frustration_score = max(frustration_score, score)
        
        frustration = (
            Frustration.HIGH if frustration_score > 0.7
            else Frustration.MILD if frustration_score > 0.3
            else Frustration.CALM
        )
        
        # Detect confusion
        confusion_keywords = ["?", "not sure", "confused", "how do i", "what's"]
        has_confusion = any(kw in msg_lower for kw in confusion_keywords)
        confusion = Confusion.CONFUSED if has_confusion else Confusion.CLEAR
        
        # Confidence based on signal strength
        confidence = 0.7 if any([
            detected_urgency != Urgency.LOW,
            frustration != Frustration.CALM,
            has_confusion
        ]) else 0.5  # Weak signals = lower confidence
        
        return SentimentAnalysis(
            urgency=detected_urgency,
            frustration=frustration,
            confusion=confusion,
            confidence=confidence,
            raw_analysis={
                "urgency_keyword": next((k for k in urgency_keywords if k in msg_lower), None),
                "frustration_score": frustration_score,
                "has_confusion_keywords": has_confusion,
            }
        )
    
    async def _analyze_with_llm(self, message: str) -> SentimentAnalysis:
        """LLM-based sentiment detection for nuanced cases."""
        analysis_prompt = f"""
Analyze this IT support message for tone.

Message: "{message}"

Detect:
1. Urgency: low (casual) / medium (soon) / high (ASAP) / critical (system down)
2. Frustration: calm (neutral) / mild (some frustration) / high (very frustrated)
3. Confusion: clear (knows issue) / confused (lost)

Return JSON:
{{
  "urgency": "low|medium|high|critical",
  "frustration": "calm|mild|high",
  "confusion": "clear|confused",
  "reasoning": "brief explanation"
}}
        """
        
        result = await self.llm.complete_json(
            system="You are analyzing customer support message tone.",
            user_prompt=analysis_prompt,
            temperature=0.3,  # Deterministic
        )
        
        return SentimentAnalysis(
            urgency=Urgency(result["urgency"]),
            frustration=Frustration(result["frustration"]),
            confusion=Confusion(result["confusion"]),
            confidence=0.85,  # LLM analysis = high confidence
            raw_analysis=result,
        )
```

#### 2. Modify `backend/app/workflows/nodes/triage.py`

```python
from backend.app.services.agents.sentiment_analyzer import SentimentAnalyzerService

async def triage_node(state: AgentState) -> dict:
    """
    Triage node: classify issue + detect sentiment.
    ENHANCE: Sentiment detection guides response tone.
    """
    user_message = state.messages[-1].content
    
    # Existing: entity normalization, intent classification
    # ... existing code ...
    
    # NEW: Detect sentiment
    sentiment_analyzer = SentimentAnalyzerService(llm_service)
    sentiment = await sentiment_analyzer.analyze(user_message)
    
    # Store in context
    state.diagnostic_context.urgency = sentiment.urgency.value
    state.diagnostic_context.business_impact = (
        "critical" if sentiment.urgency == Urgency.CRITICAL else
        "high" if sentiment.urgency == Urgency.HIGH else
        "medium"
    )
    
    # Detect if frustrated → soften response
    is_frustrated = sentiment.frustration == Frustration.HIGH
    if is_frustrated:
        state.messages.append(AssistantMessage(
            content="I understand this is frustrating. Let me help you resolve it."
        ))
    
    # Continue with existing triage logic
    return {"next": "retrieve"}
```

#### 3. Modify `backend/app/workflows/nodes/resolution.py`

Inject sentiment into LLM prompt:

```python
async def resolution_node(state: AgentState) -> dict:
    context = state.diagnostic_context
    
    # Build system prompt with sentiment guidance
    urgency_guidance = {
        "critical": "This is urgent. Prioritize fastest solution, skip optional steps.",
        "high": "User is in a hurry. Be concise, prioritize speed over comprehensiveness.",
        "medium": "Normal priority. Balance speed and thoroughness.",
        "low": "User is patient. Can be thorough.",
    }
    
    frustration_guidance = {
        "high": "User is frustrated. Lead with empathy: acknowledge issue, then solve.",
        "mild": "Some frustration. Be professional and reassuring.",
        "calm": "User is calm. Direct and factual tone is fine.",
    }
    
    system_prompt = f"""
You are an IT support analyst helping resolve {context.normalized_system} issues.

**User Context**:
- Urgency: {context.urgency} - {urgency_guidance.get(context.urgency, '')}
- Frustration: {context.business_impact} - {frustration_guidance.get(context.business_impact, '')}

**Tone Guidance**:
{f"- Be empathetic first, then technical. Validate their frustration." if context.business_impact == 'high' else ''}
{f"- Be concise and action-focused. Skip explanations." if context.urgency == 'critical' else ''}

Suggest next troubleshooting step (max 3 steps per turn).
    """
    
    # Call LLM with sentiment-aware prompt
    response = await llm_service.complete(
        system=system_prompt,
        user_prompt=state.messages[-1].content,
    )
    
    # ... rest of node ...
```

#### 4. Modify `backend/app/workflows/nodes/escalation.py`

Urgent issues escalate earlier:

```python
def should_escalate(state: AgentState) -> bool:
    """
    Decide if we should escalate.
    ENHANCE: Urgent issues escalate sooner.
    """
    context = state.diagnostic_context
    confidence = state.confidence
    
    # Critical urgency → lower threshold
    escalation_threshold = {
        "critical": 0.4,   # Lower threshold for critical issues
        "high": 0.5,       # Default
        "medium": 0.6,     # Can be more exploratory
        "low": 0.7,        # Can be very exploratory
    }.get(context.urgency, 0.5)
    
    if confidence < escalation_threshold:
        return True
    
    # Also escalate if user frustrated AND low confidence
    if context.business_impact == "high" and confidence < 0.6:
        return True
    
    return False
```

### Tests to Add

**File**: `backend/tests/services/agents/test_sentiment_analyzer.py`

```python
@pytest.mark.asyncio
async def test_detect_urgent_message():
    """CRITICAL urgency detected."""
    analyzer = SentimentAnalyzerService(mock_llm)
    
    sentiment = await analyzer.analyze("EMAIL IS DOWN!!! I CAN'T WORK!!!")
    
    assert sentiment.urgency == Urgency.CRITICAL
    assert sentiment.frustration == Frustration.HIGH

@pytest.mark.asyncio
async def test_detect_calm_message():
    """Calm tone detected."""
    sentiment = await analyzer.analyze("Hi, when you get a chance, can you help?")
    
    assert sentiment.urgency == Urgency.LOW
    assert sentiment.frustration == Frustration.CALM

@pytest.mark.asyncio
async def test_detect_confused_message():
    """Confusion detected."""
    sentiment = await analyzer.analyze("I'm not sure what's wrong. How do I fix this?")
    
    assert sentiment.confusion == Confusion.CONFUSED

@pytest.mark.asyncio
async def test_urgent_escalates_sooner():
    """Critical urgency → escalate at confidence 0.4 instead of 0.5"""
    # Verify escalation threshold logic
    pass
```

### Manual Testing

```
Test 1: Calm user
Input: "Hi, my Outlook isn't syncing"
Expected: Calm tone, thorough guidance, take time

Test 2: Frustrated user
Input: "I CAN'T ACCESS OUTLOOK!!! THIS IS CRITICAL!!!"
Expected: Empathetic intro, quick escalation (lower threshold)

Test 3: Confused user
Input: "My email is slow? I'm not sure if it's my device or server?"
Expected: Simple language, clarify questions
```

---

## Gap 3: Web Search Fallback (Days 5–7)

### Problem
KB empty = immediate escalation. Novel issues get no guidance.

### Solution
Search web when KB returns 0 articles, offer results as fallback.

### Files to Create/Modify

#### 1. Create `backend/app/services/web_search_service.py`

```python
"""Search web when KB has no guidance."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import os

class DomainTrust(str, Enum):
    OFFICIAL = "official"      # microsoft.com, apple.com, etc.
    VENDOR = "vendor"          # Dell, Lenovo, etc.
    TRUSTED_COMMUNITY = "trusted_community"  # stackoverflow, reddit
    GENERAL_BLOG = "general_blog"  # Medium, personal blogs

@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str
    domain: str
    trust_level: DomainTrust

class WebSearchService:
    """Search web for guidance when KB is empty."""
    
    def __init__(self, api_key: Optional[str] = None):
        # Using Tavily API (free tier: 1000 calls/month)
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            self.enabled = False
            logger.warning("TAVILY_API_KEY not set. Web search disabled.")
        else:
            self.enabled = True
    
    async def search(
        self,
        query: str,
        category: str,  # e.g., "outlook", "access"
        system: str,    # e.g., "Windows", "Mac"
    ) -> list[WebSearchResult]:
        """
        Search web for guidance.
        
        Args:
            query: User's problem (e.g., "mailbox full can't send")
            category: Issue category (e.g., "outlook")
            system: Affected system (e.g., "Windows 10")
            
        Returns:
            Top 3-5 results ranked by trust
        """
        if not self.enabled:
            return []
        
        # Build focused search query
        search_query = f"{category} {system} {query} help solution"
        
        try:
            # Call Tavily API
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.api_key,
                        "query": search_query,
                        "max_results": 10,  # Get more, rank them
                        "topic": "IT Help",
                    },
                    timeout=5.0,
                )
            
            data = response.json()
            raw_results = data.get("results", [])
            
            # Convert to WebSearchResult
            results = [
                WebSearchResult(
                    title=r["title"],
                    url=r["url"],
                    snippet=r["content"],
                    domain=self._extract_domain(r["url"]),
                    trust_level=self._assess_trust(r["url"]),
                )
                for r in raw_results
            ]
            
            # Rank by trust
            results.sort(
                key=lambda x: self._trust_score(x.trust_level),
                reverse=True,
            )
            
            # Return top 3
            return results[:3]
            
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return []
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc
    
    def _assess_trust(self, url: str) -> DomainTrust:
        """Assess trustworthiness of domain."""
        domain = self._extract_domain(url).lower()
        
        # Official vendor sites
        if any(vendor in domain for vendor in [
            "microsoft", "apple", "google", "dell", "hp", "lenovo",
            "amazon", "aws", "azure", "office.com", "support.microsoft"
        ]):
            return DomainTrust.OFFICIAL
        
        # Trusted communities
        if any(community in domain for community in [
            "stackoverflow.com", "reddit.com", "superuser.com", "serverfault.com"
        ]):
            return DomainTrust.TRUSTED_COMMUNITY
        
        # General blogs
        return DomainTrust.GENERAL_BLOG
    
    def _trust_score(self, trust_level: DomainTrust) -> int:
        """Map trust level to score for sorting."""
        scores = {
            DomainTrust.OFFICIAL: 100,
            DomainTrust.VENDOR: 80,
            DomainTrust.TRUSTED_COMMUNITY: 60,
            DomainTrust.GENERAL_BLOG: 30,
        }
        return scores.get(trust_level, 0)
```

#### 2. Modify `backend/app/workflows/nodes/resolution.py`

```python
async def resolution_node(state: AgentState) -> dict:
    context = state.diagnostic_context
    
    # Check: do we have KB articles?
    if not knowledge_results or len(knowledge_results) == 0:
        # KB is empty, try web search
        web_results = await web_search_service.search(
            query=context.exact_problem_statement,
            category=context.issue_subtype,
            system=context.normalized_system,
        )
        
        if web_results:
            # Format web results for user
            web_response = await _format_web_results(web_results)
            
            state.messages.append(AssistantMessage(
                content=f"""
I couldn't find guidance in our internal knowledge base for this issue.
However, I found some external resources that might help:

{web_response}

Would you like to try one of these solutions, or would you prefer to talk to an IT agent?
                """
            ))
            
            # Add quick replies
            state.quick_replies = [
                {"label": "Try external solution", "value": "yes_web"},
                {"label": "Talk to IT agent", "value": "escalate"},
            ]
            
            return {"next": "end"}  # Wait for user choice
        else:
            # No KB, no web → escalate
            return {"next": "escalation", "reason": "No guidance available"}
    
    # ... existing resolution logic ...

async def _format_web_results(results: list[WebSearchResult]) -> str:
    """Format web search results for user display."""
    formatted = []
    for i, result in enumerate(results, 1):
        trust_badge = {
            "official": "✓ Official",
            "vendor": "✓ Vendor",
            "trusted_community": "Community",
            "general_blog": "Blog",
        }.get(result.trust_level.value, "External")
        
        formatted.append(f"""
**{i}. {result.title}** [{trust_badge}]
{result.snippet}
[View article]({result.url})
        """)
    
    return "\n".join(formatted)
```

#### 3. Create `backend/app/workflows/nodes/web_resolution.py`

Handle user's choice on web solution:

```python
async def web_resolution_node(state: AgentState) -> dict:
    """
    User chose to try web solution or escalate.
    """
    last_message = state.messages[-1].content
    
    if "web" in last_message.lower() or "yes" in last_message.lower():
        # User will try web solution
        response = """
Great! Try following the steps in the article.
Let me know if it resolves your issue, or if you run into problems.
        """
        state.messages.append(AssistantMessage(content=response))
        state.quick_replies = [
            {"label": "Issue resolved!", "value": "resolved"},
            {"label": "Still not working", "value": "still_broken"},
        ]
        return {"next": "confirm"}
    else:
        # User wants to escalate
        return {"next": "escalation"}
```

#### 4. Add to `backend/app/workflows/graph.py`

Add web_resolution node to graph:

```python
graph.add_node("web_resolution", web_resolution_node)
graph.add_edge("resolution", "web_resolution")  # From resolution → web_resolution if web used
graph.add_edge("web_resolution", "confirm")
```

### Environment Setup

Add to `.env.example`:

```bash
# Web search fallback (optional)
# Get free API key at https://tavily.com
TAVILY_API_KEY=your_api_key_here
```

### Tests to Add

**File**: `backend/tests/services/test_web_search_service.py`

```python
@pytest.mark.asyncio
async def test_web_search_returns_results():
    """Search web returns top 3 results."""
    service = WebSearchService(api_key="test_key")
    
    results = await service.search(
        query="mailbox full can't send",
        category="outlook",
        system="Windows",
    )
    
    assert len(results) <= 3
    assert all(isinstance(r, WebSearchResult) for r in results)

@pytest.mark.asyncio
async def test_results_ranked_by_trust():
    """Results sorted: official > community > blog."""
    service = WebSearchService(api_key="test_key")
    results = await service.search(...)
    
    # Verify order
    trust_scores = [service._trust_score(r.trust_level) for r in results]
    assert trust_scores == sorted(trust_scores, reverse=True)

@pytest.mark.asyncio
async def test_web_search_fallback_when_kb_empty():
    """When KB returns 0 articles, use web search."""
    # Mock retrieval: 0 articles
    # Verify: web_search called
    # Verify: results presented to user
    pass
```

### Manual Testing

```
Test Case: Novel issue (not in KB)
Input: "How do I configure VPN on Ubuntu 22.04?"
Expected:
1. KB search returns 0 articles
2. Web search triggered
3. User sees: Microsoft VPN docs, Community posts, Blogs
4. User can try solution or escalate
5. If resolved: issue logged for KB addition
```

---

## Integration Checklist

After implementing all 3 gaps:

- [ ] Context summarization working (every 10 turns)
- [ ] Sentiment detection feeding into responses
- [ ] Web search providing fallback guidance
- [ ] All 3 manual test cases pass
- [ ] No regressions in existing conversations
- [ ] Debug traces show new fields (summary, urgency, web_used)
- [ ] Performance acceptable (LLM calls still <2sec)

---

## Rollout Plan

### Friday (Code Review)
- PR with all 3 gaps
- Code review + feedback
- Fixes applied

### Monday (Staging Deploy)
- Deploy to staging
- IT team tests 5 conversations
- Gather feedback

### Wednesday (Production)
- Deploy to production with feature flag
- Monitor: escalation rate, resolution rate, web search usage
- Rollback if issues (feature flag)

---

## Success Metrics (After 1 Week)

| Metric | Target | How to Measure |
|--------|--------|---|
| Context summarization | Every 10 turns | Check debug trace shows summary |
| Urgency detected correctly | 90% accuracy | Manual review 10 conversations |
| Web search fallback used | 1–5% of conversations | Analytics query |
| Resolution rate | +5–10% | Compare pre/post |
| Escalation rate | -10–15% | Compare pre/post |
| MTTR | Reduced | Ticket creation timestamp vs resolution |

---

**Ready to start? Begin with Context Summarization on Monday!**
