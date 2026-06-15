# 💬 Chat System Behavior & Employee Experience Guide

**Date**: June 10, 2026
**Status**: ✅ Fixed & Documented
**Component**: IT Support Chat UI/UX

---

## 📋 Overview

The **IT Support Chat** is the primary interface for employees to get AI-powered help with IT issues. It uses a multi-agent LangGraph workflow to triage, resolve, or escalate issues.

---

## ✅ Expected Chat Behavior (Now Fixed)

### 1. **Initial Greeting**

When an employee opens the chat:

```
🤖 Hi Alice! I'm your AI IT assistant. How can I help you today?
   I can help with email issues, VPN problems, hardware troubleshooting, and more.
```

**Status**: ✅ Working correctly

---

### 2. **User Sends Message**

Employee types and sends a message like: `"unable to login to Naukari account"`

**Frontend State**:
- Input is cleared immediately
- Message appears in chat as user bubble
- Loading indicator (typing dots) appears
- Input field is disabled

**Status**: ✅ Working correctly

---

### 3. **AI Response**

**Backend Processing**:
1. Message is sent to LangGraph workflow
2. Orchestrator routes to Triage Agent
3. Issue is classified (category, severity, urgency)
4. Knowledge Base is searched
5. Response is formatted

**Response Fields**:
```json
{
  "session_id": "uuid",
  "message_id": "uuid",
  "content": "Let me help you with that...",          // ← Main response
  "issue_category": "access/permissions",          // ← Issue classification
  "confidence_score": 0.75,                        // ← AI confidence
  "follow_up_question": "Can you...",              // ← Clarification
  "resolution_steps": [                            // ← Troubleshooting steps
    {"step_number": 1, "instruction": "..."}
  ],
  "requires_escalation": false                     // ← Escalation needed?
}
```

**Frontend Display** (Now Fixed):
- ✅ Displays `content` field (NOT "I received your message")
- ✅ Shows resolution steps if available
- ✅ Shows follow-up questions for clarification
- ✅ Shows escalation banner if `requires_escalation: true`

**Status**: ✅ FIXED (was showing placeholder text before)

---

### 4. **Response Types**

#### Type A: AI Can Resolve Directly
```
🤖 To reset your password, follow these steps:
   1. Go to www.company.com/login
   2. Click "Forgot Password"
   3. Enter your email...

   [Request Live Agent] (only if confidence low)
```

**Conditions**:
- `confidence_score >= 0.8`
- Relevant knowledge base articles found
- Clear resolution steps available

---

#### Type B: AI Needs Clarification
```
🤖 I understand you're having login issues. Can you tell me:
   - Which application or service?
   - What error message do you see?
   - On which device (laptop, phone, etc.)?
```

**Conditions**:
- `follow_up_question` is set
- Issue category too broad
- Need more context

**Employee Action**: Reply with more details

---

#### Type C: AI Recommends Escalation
```
🤖 This looks like it needs IT Agent assistance.

⚠️ This may require human assistance

[Request Live Agent]
```

**Conditions**:
- `confidence_score < 0.5`
- `requires_escalation: true`
- Complex issue / hardware failure / custom software

---

### 5. **Employee Requests Live Agent**

When employee clicks **"Request Live Agent"**:

1. **Currently**: Button is displayed (functionality pending)
2. **Future**:
   - Creates remote support session
   - Sends consent request to employee
   - Routes to available IT agent queue
   - Chat transitions to remote support

**Button Scenarios**:
- Always shown if `requires_escalation: true`
- Always shown if AI confidence is low and no steps generated
- Appears after each response (for user choice)

---

### 6. **Conversation Flow Examples**

#### Example 1: Simple Issue (Resolved)

```
👤 Employee: "I can't access my email"

🤖 AI: "Let me help you with that.
   Step 1: Go to Outlook web (outlook.office.com)
   Step 2: Check if web version works

   If web works but desktop doesn't:
   - Close Outlook
   - Delete cache files
   - Restart Outlook"

   Confidence: 85% ✅

👤 Employee: "Thanks, it works now!"

🤖 AI: "Great! Glad I could help. Feel free to reach out anytime."
```

**Status**: ✅ Working

---

#### Example 2: Needs Clarification

```
👤 Employee: "My device won't connect"

🤖 AI: "I see you're having connectivity issues.

   Can you provide more details? For example:
   - Which type of connection? (WiFi, Ethernet, VPN)
   - What error do you see?
   - Which device?

   [Request Live Agent]"

👤 Employee: "WiFi only works when I restart the router"

🤖 AI: "Try these steps:
   1. Check if WiFi driver is updated
   2. Reset network settings..."
```

**Status**: ✅ Working

---

#### Example 3: Escalation Needed

```
👤 Employee: "I need to install custom software for my project"

🤖 AI: "This requires IT Admin approval and custom deployment.

   ⚠️ This may require human assistance

   [Request Live Agent]

   An IT agent will help you with:
   - Approval process
   - Software licensing
   - Installation & setup"

👤 Employee: [Clicks "Request Live Agent"]

→ Session transferred to IT Agent queue
```

**Status**: ✅ Working (except final transfer - pending)

---

## 🐛 Issue That Was Fixed

### The Problem
The chat was showing **"I received your message"** for every response because:

```javascript
// BEFORE (Wrong):
content: data.response || data.message || 'I received your message.'
//        ↑ Wrong field        ↑ Wrong field        ↑ Fallback triggered

// AFTER (Fixed):
content: data.content || data.response || data.message || 'I received your message.'
//        ↑ Correct field
```

The backend returns `data.content`, but the frontend was only checking for `data.response` or `data.message`.

### The Fix
Updated the field priority to check `data.content` first ✅

---

## 📊 Current Chat Features

| Feature | Status | Notes |
|---------|--------|-------|
| Welcome greeting | ✅ Working | Personalizes with user's first name |
| Send messages | ✅ Working | Sends to backend, handles loading |
| AI responses | ✅ FIXED | Now displays proper content |
| Resolution steps | ✅ Working | Shows step-by-step instructions |
| Follow-up questions | ✅ Working | Asks for clarification |
| Escalation detection | ✅ Working | Flags complex issues |
| Live agent request | ⏳ Pending | Button shows, routing not implemented |
| Session persistence | ⏳ Pending | Each chat starts fresh |
| Session history | ⏳ Pending | Not in database yet |
| Typing indicator | ✅ Working | Animated dots during AI response |
| Error handling | ✅ Working | Shows "Sorry, I encountered an error" |

---

## 🎯 Is This Correct Behavior?

**Question**: "Why does the chat show 'I received your message' sometimes?"

**Answer** (Before Fix):
- Frontend bug: Incorrect field mapping
- Should have been fixed immediately

**Answer** (After Fix):
- ✅ Now displays proper AI response content
- ✅ Shows resolution steps when available
- ✅ Shows follow-up questions for clarification
- ✅ Shows escalation options when needed

---

## 🔄 Chat Flow Diagram

```
┌─────────────────────────────────┐
│  Employee Opens Chat            │
│  ↓                              │
│  Sees Welcome Greeting          │
└──────────┬──────────────────────┘
           │
           ↓
    ┌──────────────────┐
    │ Employee Types   │
    │ & Sends Message  │
    └────────┬─────────┘
             │
             ↓
   ┌────────────────────────────┐
   │ Backend: LangGraph Workflow│
   │                            │
   │ 1. Triage (classify issue) │
   │ 2. Retrieve (search KB)    │
   │ 3. Resolve (generate steps)│
   │ 4. Escalate? (if needed)   │
   └────────┬───────────────────┘
            │
            ↓
  ┌─────────────────────────────────────┐
  │ Response Display (FIXED)            │
  │                                     │
  │ ✓ AI response text (data.content)   │
  │ ✓ Resolution steps (if available)   │
  │ ✓ Follow-up questions (if needed)   │
  │ ✓ Escalation option (if flagged)    │
  │                                     │
  │ [Request Live Agent] button         │
  └────────────┬────────────────────────┘
               │
       ┌───────┴─────────┐
       │                 │
       ↓                 ↓
  Employee Tries    Employee Escalates
  AI Solution       to Live Agent
       │                 │
       └─────────────────┴─→ (Future: Remote Support)
```

---

## 📝 Testing Scenarios

### Test 1: Simple Resolution
```
Input: "My email isn't syncing"
Expected: Step-by-step instructions
Status: ✅ PASS (now shows content correctly)
```

### Test 2: Needs Clarification
```
Input: "My computer is broken"
Expected: Follow-up questions
Status: ✅ PASS (shows follow_up_question field)
```

### Test 3: Escalation Needed
```
Input: "I need to install Photoshop"
Expected: Escalation banner + "Request Live Agent"
Status: ✅ PASS (shows requires_escalation: true)
```

### Test 4: Error Handling
```
Input: (with invalid token)
Expected: "Sorry, I encountered an error"
Status: ✅ PASS (catches and displays error message)
```

---

## 🎓 Employee Instructions

### How to Use Chat Effectively

1. **Describe your issue clearly**
   - ❌ "It doesn't work"
   - ✅ "Outlook not syncing emails on my Mac"

2. **Provide context when asked**
   - ❌ Just repeat the issue
   - ✅ Answer follow-up questions (device, OS, error message)

3. **Follow the troubleshooting steps**
   - Read each step completely
   - Try exactly as described
   - Report if it works or what happens

4. **Request live agent if:**
   - AI can't solve it after multiple tries
   - You see the "⚠️ This may require human assistance" banner
   - You need custom software or hardware changes

5. **Common response types:**
   - **3-5 steps**: Simple fix, try them
   - **Follow-up question**: Provide more info
   - **"Request Live Agent" button**: Complex issue, request escalation

---

## 💡 Design Decisions

### Why Show Resolution Steps in Chat?
- Keeps guidance visible while user troubleshoots
- User can reference steps immediately
- No need to open separate documentation
- Builds confidence in AI system

### Why Not Auto-Escalate?
- Employee has agency to decide
- Some prefer to try AI first (faster)
- IT agent queue is limited resource
- Proper escalation reduces help desk load

### Why Confidence Scores?
- Transparency: "I'm 85% sure this will work"
- Informs escalation decisions
- Helps IT agents prioritize
- Improves over time with feedback

---

## ✅ Summary

**Before Fix**: Chat showed "I received your message" (wrong field mapping)
**After Fix**: Chat properly displays AI responses, steps, questions, and escalation options
**Status**: ✅ **CORRECT BEHAVIOR NOW WORKING**

The chat system is now functioning as designed:
- ✅ Proper AI responses
- ✅ Troubleshooting steps
- ✅ Escalation detection
- ✅ Error handling

---

*For more info, see AGENTS.md (multi-agent system), DEPLOYMENT_SUCCESS_REPORT.md (system status), or .github/copilot-instructions.md (coding guidelines).*
