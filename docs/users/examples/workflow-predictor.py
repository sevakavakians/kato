#!/usr/bin/env python3
"""
Workflow Predictor Example

Demonstrates sequential workflow tracking and next-step prediction.

Use Case:
  Track multi-step workflows (e.g., onboarding, checkout) and predict next steps.

Features:
  - Temporal sequence learning
  - Next-step prediction
  - Progress tracking
  - Deviation detection

Usage:
  python workflow-predictor.py
"""

import requests
from typing import List, Optional, Dict


class WorkflowPredictor:
    """Predict next steps in multi-step workflows."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session_id: Optional[str] = None

    def create_session(self, workflow_name: str = "workflow_tracker"):
        """Create KATO session."""
        response = requests.post(
            f"{self.base_url}/sessions",
            json={
                "node_id": workflow_name,
                "config": {
                    "recall_threshold": 0.5,  # Strict matching
                    "max_predictions": 5,
                    "sort_symbols": False  # Preserve order
                }
            }
        )
        response.raise_for_status()
        data = response.json()
        self.session_id = data['session_id']
        print(f"✓ Session created for workflow: {workflow_name}")
        return self.session_id

    def record_step(self, step: str, metadata: Dict = None):
        """Record workflow step."""
        observation = {
            "strings": [step],
            "vectors": [],
            "emotives": {},
            "metadata": metadata or {}
        }

        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/observe",
            json=observation
        )
        response.raise_for_status()
        print(f"  ✓ Recorded step: {step}")

    def learn_workflow(self) -> Dict:
        """Learn workflow pattern."""
        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/learn"
        )
        response.raise_for_status()
        return response.json()

    def predict_next_steps(self) -> List[str]:
        """Get predicted next steps."""
        response = requests.get(
            f"{self.base_url}/sessions/{self.session_id}/predictions"
        )
        response.raise_for_status()
        predictions = response.json()

        if not predictions['predictions']:
            return []

        # Extract future steps
        top = predictions['predictions'][0]
        future = top.get('future', [])

        # Flatten to list of steps
        next_steps = [step[0] for step in future if step]
        return next_steps

    def get_current_progress(self) -> Dict:
        """Get current workflow progress."""
        response = requests.get(
            f"{self.base_url}/sessions/{self.session_id}/predictions"
        )
        response.raise_for_status()
        predictions = response.json()

        if not predictions['predictions']:
            return {
                'completed': [],
                'current': [],
                'remaining': [],
                'progress': 0
            }

        top = predictions['predictions'][0]
        past = top.get('past', [])
        present = top.get('present', [])
        future = top.get('future', [])

        total_steps = len(past) + len(present) + len(future)
        completed_steps = len(past)

        return {
            'completed': [s[0] for s in past],
            'current': [s[0] for s in present],
            'remaining': [s[0] for s in future],
            'progress': (completed_steps / total_steps * 100) if total_steps > 0 else 0
        }

    def clear_progress(self):
        """Clear current workflow progress."""
        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/clear-stm"
        )
        response.raise_for_status()


def demo_onboarding_workflow():
    """Demo: User onboarding workflow."""
    print("\n" + "=" * 60)
    print("Demo: User Onboarding Workflow")
    print("=" * 60 + "\n")

    predictor = WorkflowPredictor()
    predictor.create_session("onboarding_workflow")

    # Define onboarding steps
    print("\n📋 Training workflow...")
    onboarding_steps = [
        "step1_signup",
        "step2_verify_email",
        "step3_profile_setup",
        "step4_preferences",
        "step5_tutorial",
        "step6_first_action",
        "step7_completion"
    ]

    # Record training workflow
    for step in onboarding_steps:
        predictor.record_step(step)

    # Learn pattern
    result = predictor.learn_workflow()
    print(f"\n✓ Workflow learned: {result['length']} steps")
    print(f"  Pattern: {result.get('pattern_name', 'N/A')}")

    # Simulate user going through workflow
    print("\n" + "-" * 60)
    print("Simulating user onboarding...")
    print("-" * 60 + "\n")

    predictor.clear_progress()

    # User completes steps 1-3
    for step in onboarding_steps[:3]:
        predictor.record_step(step)

        # Show progress
        progress = predictor.get_current_progress()
        print(f"\n📍 After {step}:")
        print(f"  Completed: {progress['completed']}")
        print(f"  Current: {progress['current']}")
        print(f"  Progress: {progress['progress']:.0f}%")

        # Predict next steps
        next_steps = predictor.predict_next_steps()
        if next_steps:
            print(f"  Next steps: {next_steps[:3]}")  # Show next 3


def demo_checkout_workflow():
    """Demo: E-commerce checkout workflow."""
    print("\n" + "=" * 60)
    print("Demo: E-commerce Checkout")
    print("=" * 60 + "\n")

    predictor = WorkflowPredictor()
    predictor.create_session("checkout_workflow")

    # Training data
    print("📋 Training checkout workflow...")
    checkout_steps = [
        "cart_review",
        "shipping_address",
        "shipping_method",
        "payment_method",
        "order_review",
        "place_order",
        "confirmation"
    ]

    for step in checkout_steps:
        predictor.record_step(step)

    result = predictor.learn_workflow()
    print(f"✓ Checkout workflow learned: {result['length']} steps\n")

    # Simulate checkout
    print("-" * 60)
    print("Simulating customer checkout...")
    print("-" * 60 + "\n")

    predictor.clear_progress()

    # Customer at cart review
    predictor.record_step("cart_review")

    progress = predictor.get_current_progress()
    print(f"📍 Customer at: cart_review")
    print(f"  Remaining steps: {len(progress['remaining'])}")
    print(f"  Next step: {progress['remaining'][0] if progress['remaining'] else 'None'}")


def demo_deviation_detection():
    """Demo: Detect workflow deviations."""
    print("\n" + "=" * 60)
    print("Demo: Deviation Detection")
    print("=" * 60 + "\n")

    predictor = WorkflowPredictor()
    predictor.create_session("standard_workflow")

    # Learn standard workflow
    print("📋 Learning standard workflow...")
    standard_steps = ["start", "step_a", "step_b", "complete"]

    for step in standard_steps:
        predictor.record_step(step)

    predictor.learn_workflow()
    print("✓ Standard workflow learned\n")

    # Simulate deviation
    print("-" * 60)
    print("Simulating workflow with deviation...")
    print("-" * 60 + "\n")

    predictor.clear_progress()

    # User follows start → step_a → [skips step_b] → complete
    predictor.record_step("start")
    predictor.record_step("step_a")
    predictor.record_step("complete")  # Skipped step_b!

    # Check predictions
    response = requests.get(
        f"{predictor.base_url}/sessions/{predictor.session_id}/predictions"
    )
    predictions = response.json()

    if predictions['predictions']:
        top = predictions['predictions'][0]
        missing = top.get('missing', [])

        print("⚠️  Deviation detected!")
        print(f"  Missing steps: {missing}")
        print(f"  User skipped: step_b")


def main():
    """Run workflow predictor examples."""
    print("=" * 60)
    print("Workflow Predictor Examples - KATO")
    print("=" * 60)

    try:
        # Run demos
        demo_onboarding_workflow()
        demo_checkout_workflow()
        demo_deviation_detection()

        print("\n" + "=" * 60)
        print("✓ All demos completed successfully")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
