# KATO Chatbot Integration Guide

## Table of Contents
1. [Overview](#overview)
2. [Conversation Context Management](#conversation-context-management)
3. [Dialogue State Tracking](#dialogue-state-tracking)
4. [Intent Pattern Learning](#intent-pattern-learning)
5. [Multi-Turn Conversations](#multi-turn-conversations)
6. [Integration with LLMs](#integration-with-llms)
7. [Real-World Examples](#real-world-examples)

## Overview

KATO provides conversational memory and pattern recognition for chatbots, enabling context-aware responses and learning user preferences over time.

### Key Capabilities

- **Conversation History**: Track dialogue across sessions
- **Intent Patterns**: Learn user intent sequences
- **Context Prediction**: Anticipate next user actions
- **Sentiment Tracking**: Monitor emotional tone
- **Personalization**: Remember user preferences

## Conversation Context Management

### Basic Chat Context

```python
import httpx
from typing import Optional, List, Dict

class ChatContextManager:
    """Manage conversation context with KATO"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url, timeout=30.0)
        self.user_sessions = {}

    def get_or_create_session(self, user_id: str, conversation_id: str) -> str:
        """Get or create session for conversation"""
        key = f"{user_id}:{conversation_id}"

        if key not in self.user_sessions:
            response = self.kato.post(
                "/sessions",
                json={
                    "node_id": f"chat:{user_id}",
                    "config": {
                        "recall_threshold": 0.2,
                        "max_predictions": 10,
                        "session_ttl": 3600
                    }
                }
            )
            self.user_sessions[key] = response.json()["session_id"]

        return self.user_sessions[key]

    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        intent: str,
        sentiment: float = 0.0
    ):
        """Add message to conversation context"""
        session_id = self.get_or_create_session(user_id, conversation_id)

        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [intent, f"msg:{message[:50]}"],  # Intent + snippet
                "vectors": [],
                "emotives": {"sentiment": sentiment}
            }
        )

    def get_context_predictions(
        self,
        user_id: str,
        conversation_id: str
    ) -> List[Dict]:
        """Get predictions for next turn"""
        session_id = self.get_or_create_session(user_id, conversation_id)

        response = self.kato.get(f"/sessions/{session_id}/predictions")
        return response.json()

# Usage
chat = ChatContextManager("http://localhost:8000")
chat.add_message("user-123", "conv-1", "I want to book a flight", "book_flight", 0.3)
predictions = chat.get_context_predictions("user-123", "conv-1")
```

## Dialogue State Tracking

### State-Based Conversation Management

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class DialogueState(Enum):
    """Conversation states"""
    GREETING = "greeting"
    INTENT_DETECTION = "intent_detection"
    SLOT_FILLING = "slot_filling"
    CONFIRMATION = "confirmation"
    COMPLETION = "completion"

@dataclass
class ConversationContext:
    """Conversation context data"""
    user_id: str
    conversation_id: str
    current_state: DialogueState
    intent: Optional[str] = None
    slots: dict = None

    def __post_init__(self):
        if self.slots is None:
            self.slots = {}

class DialogueManager:
    """Manage dialogue flow with KATO"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)
        self.contexts = {}

    def process_message(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        detected_intent: str,
        extracted_slots: dict
    ) -> dict:
        """Process message and update dialogue state"""
        # Get or create context
        ctx_key = f"{user_id}:{conversation_id}"
        if ctx_key not in self.contexts:
            self.contexts[ctx_key] = ConversationContext(
                user_id=user_id,
                conversation_id=conversation_id,
                current_state=DialogueState.GREETING
            )

        context = self.contexts[ctx_key]

        # Update intent and slots
        if detected_intent:
            context.intent = detected_intent
        context.slots.update(extracted_slots)

        # Send to KATO
        session_id = f"chat:{user_id}:{conversation_id}"
        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [
                    f"state:{context.current_state.value}",
                    f"intent:{detected_intent}"
                ],
                "vectors": [],
                "emotives": {},
                "metadata": {"slots": extracted_slots}
            }
        )

        # Get predictions for next state
        predictions = self.kato.get(
            f"/sessions/{session_id}/predictions"
        ).json()

        return {
            "current_state": context.current_state.value,
            "intent": context.intent,
            "slots": context.slots,
            "predictions": predictions
        }
```

## Intent Pattern Learning

### Intent Sequence Recognition

```python
class IntentPatternLearner:
    """Learn and predict intent sequences"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def track_intent(
        self,
        user_id: str,
        intent: str,
        confidence: float,
        context: Optional[dict] = None
    ):
        """Track intent occurrence"""
        session_id = f"intents:{user_id}"

        # Create or use existing session
        try:
            self.kato.get(f"/sessions/{session_id}")
        except:
            self.kato.post(
                "/sessions",
                json={"node_id": f"user:{user_id}"}
            )

        # Track intent
        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [intent],
                "vectors": [],
                "emotives": {"confidence": confidence},
                "metadata": context or {}
            }
        )

    def predict_next_intent(self, user_id: str) -> List[str]:
        """Predict likely next intent"""
        session_id = f"intents:{user_id}"

        predictions = self.kato.get(
            f"/sessions/{session_id}/predictions"
        ).json()

        # Extract predicted intents
        predicted_intents = []
        for pred in predictions[:3]:  # Top 3
            if pred.get("future"):
                for event in pred["future"][0]:
                    predicted_intents.append(event)

        return predicted_intents

# Usage
learner = IntentPatternLearner("http://localhost:8000")
learner.track_intent("user-123", "book_flight", 0.95)
learner.track_intent("user-123", "add_baggage", 0.87)
next_intents = learner.predict_next_intent("user-123")
# Might predict: ["confirm_booking", "payment_info"]
```

## Multi-Turn Conversations

### Turn-Level Context Tracking

```python
from datetime import datetime
from typing import List, Dict

class MultiTurnConversation:
    """Track multi-turn conversations with KATO"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def add_turn(
        self,
        user_id: str,
        conversation_id: str,
        speaker: str,  # "user" or "bot"
        message: str,
        intent: Optional[str] = None,
        entities: Optional[Dict] = None
    ):
        """Add conversation turn"""
        session_id = f"conv:{user_id}:{conversation_id}"

        # Ensure session exists
        try:
            self.kato.get(f"/sessions/{session_id}")
        except:
            self.kato.post(
                "/sessions",
                json={
                    "node_id": f"user:{user_id}",
                    "config": {"session_ttl": 1800}  # 30 min
                }
            )

        # Track turn
        turn_data = {
            "strings": [
                f"speaker:{speaker}",
                f"intent:{intent}" if intent else "message"
            ],
            "vectors": [],
            "emotives": {},
            "metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "entities": entities or {}
            }
        }

        self.kato.post(
            f"/sessions/{session_id}/observe",
            json=turn_data
        )

    def get_conversation_summary(
        self,
        user_id: str,
        conversation_id: str
    ) -> Dict:
        """Get conversation context summary"""
        session_id = f"conv:{user_id}:{conversation_id}"

        # Get STM (recent turns)
        stm = self.kato.get(f"/sessions/{session_id}/stm").json()

        # Get predictions
        predictions = self.kato.get(
            f"/sessions/{session_id}/predictions"
        ).json()

        return {
            "recent_turns": stm,
            "predicted_next": predictions
        }

# Usage
conversation = MultiTurnConversation("http://localhost:8000")

conversation.add_turn(
    "user-123", "conv-1",
    speaker="user",
    message="I want to book a flight to NYC",
    intent="book_flight",
    entities={"destination": "NYC"}
)

conversation.add_turn(
    "user-123", "conv-1",
    speaker="bot",
    message="When would you like to travel?",
    intent="request_date"
)

summary = conversation.get_conversation_summary("user-123", "conv-1")
```

## Integration with LLMs

### KATO + LLM Hybrid Architecture

```python
import openai  # or any LLM client

class HybridChatbot:
    """Chatbot combining KATO memory with LLM generation"""

    def __init__(self, kato_url: str, openai_key: str):
        self.kato = httpx.Client(base_url=kato_url)
        openai.api_key = openai_key

    def generate_response(
        self,
        user_id: str,
        message: str,
        conversation_id: str
    ) -> str:
        """Generate response using KATO context + LLM"""
        session_id = f"hybrid:{user_id}:{conversation_id}"

        # Get KATO predictions for context
        try:
            predictions = self.kato.get(
                f"/sessions/{session_id}/predictions"
            ).json()
        except:
            # Create session if not exists
            self.kato.post(
                "/sessions",
                json={"node_id": f"user:{user_id}"}
            )
            predictions = []

        # Build context from predictions
        context = self._build_context(predictions)

        # Generate response with LLM
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": f"You are a helpful assistant. "
                               f"Context from user history: {context}"
                },
                {"role": "user", "content": message}
            ]
        )

        bot_message = response.choices[0].message.content

        # Store interaction in KATO
        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [f"user:{message[:50]}", f"bot:{bot_message[:50]}"],
                "vectors": [],
                "emotives": {}
            }
        )

        return bot_message

    def _build_context(self, predictions: List[Dict]) -> str:
        """Build context string from predictions"""
        if not predictions:
            return "No prior context"

        context_items = []
        for pred in predictions[:3]:
            if pred.get("past"):
                context_items.extend(pred["past"][0][:3])

        return ", ".join(context_items) if context_items else "Limited context"
```

## Real-World Examples

### Example 1: Customer Support Bot

```python
class CustomerSupportBot:
    """Customer support chatbot with KATO memory"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def handle_support_query(
        self,
        customer_id: str,
        query: str,
        category: str
    ) -> Dict:
        """Handle support query with historical context"""
        session_id = f"support:{customer_id}"

        # Get customer's historical issues
        try:
            predictions = self.kato.get(
                f"/sessions/{session_id}/predictions"
            ).json()
            has_history = len(predictions) > 0
        except:
            # New customer
            self.kato.post(
                "/sessions",
                json={"node_id": f"customer:{customer_id}"}
            )
            has_history = False

        # Track current query
        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [f"category:{category}", f"query:{query[:50]}"],
                "vectors": [],
                "emotives": {}
            }
        )

        # Generate response based on history
        if has_history:
            response = f"I see you've contacted us before about {category}. "
            response += "Let me help you with your current issue."
        else:
            response = "Welcome! How can I help you today?"

        return {
            "response": response,
            "has_history": has_history,
            "predictions": predictions if has_history else []
        }
```

### Example 2: Educational Tutor Bot

```python
class TutorBot:
    """Educational chatbot tracking learning progress"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def track_learning(
        self,
        student_id: str,
        topic: str,
        difficulty: str,
        success: bool
    ):
        """Track student learning progress"""
        session_id = f"student:{student_id}"

        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [
                    f"topic:{topic}",
                    f"difficulty:{difficulty}",
                    f"result:{'success' if success else 'struggle'}"
                ],
                "vectors": [],
                "emotives": {"confidence": 1.0 if success else 0.3}
            }
        )

    def get_next_topic(self, student_id: str) -> str:
        """Suggest next topic based on progress"""
        session_id = f"student:{student_id}"

        predictions = self.kato.get(
            f"/sessions/{session_id}/predictions"
        ).json()

        # Extract predicted next topic
        if predictions and predictions[0].get("future"):
            for event in predictions[0]["future"][0]:
                if event.startswith("topic:"):
                    return event.split(":")[1]

        return "review_basics"  # Default
```

## Best Practices

1. **Session Per Conversation**: Create separate sessions for each conversation
2. **Intent Tracking**: Always track intents for pattern learning
3. **Sentiment Analysis**: Include sentiment in emotives field
4. **Context Window**: Keep STM size manageable with appropriate TTL
5. **Prediction Integration**: Use predictions to guide conversation flow
6. **Fallback Handling**: Have defaults when KATO has no predictions
7. **Privacy**: Use anonymized node_ids for sensitive conversations
8. **Testing**: Test multi-turn flows thoroughly

## Related Documentation

- [Hybrid Agents Guide](hybrid-agents.md)
- [Session Management](session-management.md)
- [Architecture Patterns](architecture-patterns.md)
- [Emotives Processing](/docs/research/emotives-processing.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
