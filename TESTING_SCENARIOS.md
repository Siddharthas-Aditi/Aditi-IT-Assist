# Manual Testing Scenarios: P1 Gaps

**Test Date**: [YOUR DATE]  
**Tester**: [YOUR NAME]  
**Status**: Ready to Test

---

## Setup

### Prerequisites
1. Docker containers running and healthy
2. .env file configured with LLM_API_KEY
3. Test users seeded (run `docker compose exec backend uv run python -m scripts.seed_enterprise`)
4. Browser tab open: http://localhost:5173

### Test User Credentials
- Email: `employee@aditi.com`
- Password: `employee123`

---

## Test Scenario 1: Context Summarization (15+ Turn Conversation)

**Goal**: Verify context is compressed every 10 turns

### Steps

1. **Login** as employee
2. **Start conversation** about a fictional issue:
   ```
   User: "Hi, I can't access my Outlook email"
   ```
3. **Continue back-and-forth** for 15+ turns:
   - Turn 3: "It says connection error"
   - Turn 5: "I restarted, didn't help"
   - Turn 7: "Still getting the error"
   - Turn 9: "Error code: 0x800c0008"
   - Turn 11: "Tried in Chrome too, same issue"
   - Turn 13: "Nothing has worked so far"
   - Turn 15: "What should I try next?"

### Verification Checklist

- [ ] **Turn 10**: Check backend logs for summarization event
  ```bash
  docker compose logs backend | grep "context_summarized"
  ```
  Expected: `context_summarized turn_count=10 summary_preview="User has Outlook access issue..."`

- [ ] **Turn 15**: Agent still references earlier context correctly
  - Agent should NOT repeat steps already mentioned
  - Agent should say "We've tried X, so let's try Y"

- [ ] **Performance**: Response time after turn 10 is ~same or better (context compressed)

### Expected Behavior

- Context summary appears in logs at turn 10, 20, 30, etc.
- Agent's responses remain consistent and don't repeat
- No degradation in response quality

### Result
- [ ] PASS
- [ ] FAIL (describe issue)

---

## Test Scenario 2: Urgent Issue Detection

**Goal**: Verify agent detects urgency and responds appropriately

### Steps

1. **Login** as employee
2. **Send urgent message**:
   ```
   "EMAIL IS DOWN!!! I CAN'T ACCESS ANYTHING!!! 
    THIS IS CRITICAL - MEETINGS IN 10 MINUTES!!!"
   ```

### Verification Checklist

- [ ] **Agent response** includes urgency acknowledgment:
  - Should say something like: "I understand this is urgent—let's get this fixed fast."
  - Should NOT be generic or slow-paced

- [ ] **Backend logs** show sentiment detection:
  ```bash
  docker compose logs backend | grep "sentiment_detected"
  ```
  Expected: `sentiment_detected urgency=critical frustration=high`

- [ ] **Escalation threshold** lowered (if confidence < 0.5, escalate sooner):
  - Escalation message should come sooner than normal
  - Agent should prioritize speed over comprehensiveness

### Expected Behavior

- Agent detects CRITICAL urgency
- Response is fast and action-oriented
- Escalation happens quickly if KB can't help

### Result
- [ ] PASS
- [ ] FAIL (describe issue)

---

## Test Scenario 3: Frustrated User Detection

**Goal**: Verify agent detects frustration and responds with empathy

### Steps

1. **Login** as employee
2. **Send frustrated message**:
   ```
   "I've been trying to fix this for HOURS! 
    This is SO FRUSTRATING! Nothing works!! 
    I'm done with this system!"
   ```

### Verification Checklist

- [ ] **Agent response** includes empathy:
  - Should say something like: "I completely understand your frustration..."
  - Should validate feelings BEFORE jumping to solutions

- [ ] **Backend logs** show frustration detection:
  ```bash
  docker compose logs backend | grep "sentiment_detected"
  ```
  Expected: `sentiment_detected frustration=high`

- [ ] **Tone of response** is warm and understanding, not robotic

### Expected Behavior

- Agent leads with empathy
- Solution is presented as team effort ("Let's solve this together")
- No dismissive language

### Result
- [ ] PASS
- [ ] FAIL (describe issue)

---

## Test Scenario 4: Confused User Detection

**Goal**: Verify agent detects confusion and simplifies language

### Steps

1. **Login** as employee
2. **Send confused message**:
   ```
   "I'm not sure what's happening. 
    My email won't open? I don't know if it's my device or...
    How do I even check if it's working? I'm lost."
   ```

### Verification Checklist

- [ ] **Agent response** uses simplified language:
  - No jargon (no "IMAP", "SSL", "API")
  - Clear, step-by-step guidance
  - Asks clarifying questions if needed

- [ ] **Backend logs** show confusion detection:
  ```bash
  docker compose logs backend | grep "sentiment_detected"
  ```
  Expected: `sentiment_detected confusion=confused`

- [ ] **First step is clarity**:
  - Agent starts with understanding the situation
  - Then provides simple steps

### Expected Behavior

- Agent detects confusion flag
- Response is beginner-friendly
- Steps are broken down into tiny, manageable pieces

### Result
- [ ] PASS
- [ ] FAIL (describe issue)

---

## Test Scenario 5: Web Search Fallback (Niche Issue)

**Goal**: Verify agent searches web when KB has no guidance

### Prerequisites
- TAVILY_API_KEY set in .env (or leave blank to skip this test)

### Steps

1. **Login** as employee
2. **Ask about a niche/novel issue** NOT in KB:
   ```
   "How do I configure Outlook on Ubuntu 22.04?"
   OR
   "Set up VPN on a Mac with Apple Silicon"
   OR
   "Why is Zoom so slow on Linux Mint?"
   ```

### Verification Checklist

- [ ] **Agent response** says KB is empty AND offers web results:
  - "I couldn't find this in our internal knowledge base, but I found some external resources..."
  - Shows 2-3 results with titles, trust level badges, snippets

- [ ] **Results are ranked by trust**:
  - Official docs (Microsoft, Apple) appear first
  - Community posts (StackOverflow, Reddit) appear next
  - Blogs appear last

- [ ] **Backend logs** show web search:
  ```bash
  docker compose logs backend | grep "web_search"
  ```
  Expected: `web_search_fallback_used results_count=3 top_trust=official`

- [ ] **User can click** the result links (if they appear as markdown)

### If TAVILY_API_KEY is not set:
- [ ] Agent says KB is empty (no web results offered)
- [ ] Agent offers to escalate instead

### Expected Behavior

- Novel issues get external guidance
- Results clearly marked as "external sources"
- Disclaimer: "You're welcome to try these, or escalate if you'd prefer"
- No hallucinated guidance

### Result
- [ ] PASS
- [ ] FAIL (describe issue)

---

## Test Scenario 6: Web Search Doesn't Replace KB

**Goal**: Verify web search is FALLBACK, not primary

### Steps

1. **Login** as employee
2. **Ask about something IN KB**:
   ```
   "My Outlook mailbox is full"
   ```

### Verification Checklist

- [ ] **Agent uses KB**, NOT web search
  - Response should reference internal knowledge
  - Should say "Based on our knowledge base..."
  - Should NOT mention external sources

- [ ] **Backend logs** show NO web search:
  ```bash
  docker compose logs backend | grep "web_search"
  ```
  Should NOT appear for this message

### Expected Behavior

- KB articles used when available
- Web search only when KB returns 0 results
- No redundant external suggestions

### Result
- [ ] PASS
- [ ] FAIL (describe issue)

---

## Test Scenario 7: Multi-Intent Clarification Still Works

**Goal**: Verify existing clarification flow not broken

### Steps

1. **Login** as employee
2. **Send multi-intent message**:
   ```
   "I can't access my Outlook AND my VPN isn't working"
   ```

### Verification Checklist

- [ ] **Agent clarifies** which issue to address first:
  - "I see two issues: Outlook access and VPN connectivity. Which should we address first?"
  - Shows quick-reply buttons: "Outlook first" vs "VPN first"

- [ ] **Agent doesn't mix** solutions
  - After user picks Outlook, agent focuses ONLY on Outlook
  - Doesn't suddenly suggest VPN fixes

### Expected Behavior

- Clarification flow works as before
- No regressions in existing functionality
- New features enhance, don't break

### Result
- [ ] PASS
- [ ] FAIL (describe issue)

---

## Regression Testing

**Goal**: Verify existing functionality still works

### Scenarios to Test

1. **Basic troubleshooting**:
   ```
   User: "My Outlook is slow"
   Expected: Agent provides steps from KB
   ```
   - [ ] PASS / [ ] FAIL

2. **Confirmation flow**:
   ```
   Agent: "I understand you have mailbox full issue. Is that right?"
   User: "Yes"
   Expected: Agent proceeds to resolution
   ```
   - [ ] PASS / [ ] FAIL

3. **Resolution feedback**:
   ```
   User: "That didn't work"
   Expected: Agent marks step as failed, suggests next step
   ```
   - [ ] PASS / [ ] FAIL

4. **Escalation**:
   ```
   User: "Can I talk to someone?"
   Expected: Agent escalates, creates ticket
   ```
   - [ ] PASS / [ ] FAIL

---

## Performance Testing

### Metrics to Track

- **Response time per turn**: 
  - Expected: < 3 seconds (including LLM calls)
  - Record: ___ seconds (average)

- **Memory usage**:
  - Expected: < 500MB
  - Check: `docker stats`

- **Error rate**:
  - Expected: 0 errors in logs
  - Record: ___ errors found

### Commands

```bash
# Monitor memory + CPU
docker stats

# Check for errors
docker compose logs backend | grep -i error | wc -l

# Get response latency from logs
docker compose logs backend | grep "process_message" | tail -1
```

---

## Summary

### All Gaps Tested
- [ ] Gap 1: Context Summarization ✓
- [ ] Gap 2: Sentiment Detection (Urgency) ✓
- [ ] Gap 3: Sentiment Detection (Frustration) ✓
- [ ] Gap 4: Sentiment Detection (Confusion) ✓
- [ ] Gap 5: Web Search Fallback ✓
- [ ] Gap 6: KB Priority Over Web ✓

### Regressions Checked
- [ ] Basic troubleshooting
- [ ] Confirmation flow
- [ ] Resolution feedback
- [ ] Escalation

### Performance Acceptable
- [ ] Response time < 3 sec
- [ ] No memory leaks
- [ ] No error spam

### Overall Result
- [ ] ALL PASS — Ready for production
- [ ] SOME FAIL — Document issues below
- [ ] MAJOR ISSUES — Rollback and fix

---

## Issues Found

### Issue 1
**Description**: _________________________________________  
**Steps to Reproduce**: ___________________________________  
**Expected**: __________________________________________  
**Actual**: ___________________________________________  
**Severity**: [ ] Critical [ ] High [ ] Medium [ ] Low  
**Fix**: ___________________________________________  

### Issue 2
**Description**: _________________________________________  
...

---

## Sign-Off

**Tester Name**: _________________________  
**Date**: _________________________  
**Overall Result**: [ ] PASS [ ] FAIL [ ] NEEDS WORK  
**Notes**: _________________________________________  

---

**End of Testing Scenarios**
