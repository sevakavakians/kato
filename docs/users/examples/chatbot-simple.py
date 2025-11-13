#!/usr/bin/env python3
"""
Simple Chatbot Example

Demonstrates basic conversational pattern learning with KATO.

Use Case:
  Train a chatbot to learn conversation patterns and predict responses.

Features:
  - Basic observation and learning
  - Simple prediction retrieval
  - Pattern-based response generation

Usage:
  python chatbot-simple.py
"""

import requests
import sys
from typing import List, Optional


class SimpleChatbot:
    """Simple chatbot using KATO for pattern learning."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session_id: Optional[str] = None

    def create_session(self, bot_name: str = "simple_chatbot"):
        """Create KATO session for chatbot."""
        response = requests.post(
            f"{self.base_url}/sessions",
            json={
                "node_id": bot_name,
                "config": {
                    "recall_threshold": 0.1,  # Permissive matching
                    "max_predictions": 10
                }
            }
        )
        response.raise_for_status()
        data = response.json()
        self.session_id = data['session_id']
        print(f"✓ Created session: {self.session_id[:16]}...")
        return self.session_id

    def observe(self, user_input: str, bot_response: str):
        """Record conversation turn."""
        # Event 1: User input
        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/observe",
            json={
                "strings": [f"user:{user_input}"],
                "vectors": [],
                "emotives": {}
            }
        )
        response.raise_for_status()

        # Event 2: Bot response
        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/observe",
            json={
                "strings": [f"bot:{bot_response}"],
                "vectors": [],
                "emotives": {}
            }
        )
        response.raise_for_status()

    def learn(self):
        """Learn conversation pattern."""
        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/learn"
        )
        response.raise_for_status()
        return response.json()

    def get_response(self, user_input: str) -> Optional[str]:
        """Get predicted bot response for user input."""
        # Clear STM and observe user input
        requests.post(f"{self.base_url}/sessions/{self.session_id}/clear-stm")

        requests.post(
            f"{self.base_url}/sessions/{self.session_id}/observe",
            json={"strings": [f"user:{user_input}"], "vectors": [], "emotives": {}}
        )

        # Get predictions
        response = requests.get(
            f"{self.base_url}/sessions/{self.session_id}/predictions"
        )
        response.raise_for_status()
        predictions = response.json()

        # Extract bot response from future
        if predictions['predictions']:
            top = predictions['predictions'][0]
            if top['future']:
                bot_reply = top['future'][0][0]  # First event, first string
                # Remove "bot:" prefix
                return bot_reply.replace("bot:", "")

        return None

    def clear_stm(self):
        """Clear short-term memory."""
        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/clear-stm"
        )
        response.raise_for_status()


def train_chatbot(bot: SimpleChatbot):
    """Train chatbot with sample conversations."""
    print("\n📚 Training chatbot...")

    conversations = [
        ("hello", "Hi! How can I help you today?"),
        ("what is your name", "I'm a KATO-powered chatbot!"),
        ("how are you", "I'm doing great, thank you for asking!"),
        ("goodbye", "Goodbye! Have a great day!"),
        ("help", "I can answer questions and have conversations. Try saying hello!"),
        ("thank you", "You're welcome!"),
    ]

    for user_input, bot_response in conversations:
        bot.observe(user_input, bot_response)
        print(f"  Learned: '{user_input}' → '{bot_response}'")

    # Learn all patterns
    result = bot.learn()
    print(f"✓ Training complete! Pattern: {result.get('pattern_name', 'N/A')}")


def test_chatbot(bot: SimpleChatbot):
    """Test chatbot with queries."""
    print("\n🤖 Testing chatbot...")

    test_inputs = [
        "hello",
        "what is your name",
        "goodbye",
        "help",
        "unknown query"  # Should return None
    ]

    for user_input in test_inputs:
        response = bot.get_response(user_input)
        if response:
            print(f"  User: {user_input}")
            print(f"  Bot:  {response}")
        else:
            print(f"  User: {user_input}")
            print(f"  Bot:  [No response - pattern not learned]")
        print()


def interactive_mode(bot: SimpleChatbot):
    """Interactive chatbot mode."""
    print("\n💬 Interactive mode (type 'quit' to exit):\n")

    while True:
        try:
            user_input = input("You: ").strip()
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break

            if not user_input:
                continue

            response = bot.get_response(user_input)
            if response:
                print(f"Bot: {response}\n")
            else:
                print("Bot: I don't understand. Try: hello, help, goodbye\n")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


def main():
    """Run chatbot example."""
    print("=" * 60)
    print("Simple Chatbot Example - KATO")
    print("=" * 60)

    # Create chatbot
    bot = SimpleChatbot()
    bot.create_session("chatbot_example")

    # Train
    train_chatbot(bot)

    # Test
    test_chatbot(bot)

    # Interactive mode
    try:
        interactive_mode(bot)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
