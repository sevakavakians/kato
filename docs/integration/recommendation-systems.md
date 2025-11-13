# KATO Recommendation Systems Guide

## Table of Contents
1. [Overview](#overview)
2. [Collaborative Filtering](#collaborative-filtering)
3. [Content-Based Recommendations](#content-based-recommendations)
4. [Hybrid Approaches](#hybrid-approaches)
5. [Sequential Recommendations](#sequential-recommendations)
6. [Real-Time Personalization](#real-time-personalization)
7. [Real-World Examples](#real-world-examples)

## Overview

KATO's pattern recognition and prediction capabilities enable powerful recommendation systems that learn from user behavior sequences and predict future preferences.

### Key Capabilities

- **Sequential Patterns**: Learn item sequences (e.g., "buy A then B")
- **Contextual Predictions**: Consider temporal context
- **Real-Time Updates**: Immediate learning from user actions
- **Explainable**: Transparent pattern-based recommendations
- **Multi-Modal**: Combine items, categories, and embeddings

## Collaborative Filtering

### User-Based Collaborative Filtering

```python
import httpx
from typing import List, Dict, Optional

class UserBasedRecommender:
    """User-based collaborative filtering with KATO"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url, timeout=30.0)

    def track_interaction(
        self,
        user_id: str,
        item_id: str,
        interaction_type: str = "view",
        rating: Optional[float] = None
    ):
        """Track user-item interaction"""
        session_id = f"user:{user_id}"

        # Create session if not exists
        try:
            self.kato.get(f"/sessions/{session_id}")
        except:
            self.kato.post(
                "/sessions",
                json={"node_id": f"user:{user_id}"}
            )

        # Track interaction
        emotives = {}
        if rating is not None:
            emotives["rating"] = (rating - 3.0) / 2.0  # Normalize to [-1, 1]

        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [f"{interaction_type}:{item_id}"],
                "vectors": [],
                "emotives": emotives
            }
        )

    def get_recommendations(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[str]:
        """Get personalized recommendations"""
        session_id = f"user:{user_id}"

        # Get predictions
        predictions = self.kato.get(
            f"/sessions/{session_id}/predictions"
        ).json()

        # Extract recommended items
        recommendations = []
        for pred in predictions[:limit]:
            if pred.get("future"):
                for event in pred["future"][0]:
                    # Extract item_id from "view:item123" format
                    if ":" in event:
                        _, item_id = event.split(":", 1)
                        if item_id not in recommendations:
                            recommendations.append(item_id)

        return recommendations[:limit]

# Usage
recommender = UserBasedRecommender("http://localhost:8000")

# Track user behavior
recommender.track_interaction("user-123", "item-456", "view")
recommender.track_interaction("user-123", "item-789", "purchase", rating=5.0)

# Get recommendations
recommendations = recommender.get_recommendations("user-123", limit=5)
```

### Item-Based Collaborative Filtering

```python
class ItemBasedRecommender:
    """Item-based collaborative filtering with KATO"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def track_item_view_sequence(
        self,
        session_id: str,
        item_id: str,
        user_id: str
    ):
        """Track item view for building item-item patterns"""
        # Use item as node to learn "items viewed together"
        node_id = f"item:{item_id}"

        try:
            self.kato.get(f"/sessions/{session_id}")
        except:
            self.kato.post(
                "/sessions",
                json={"node_id": node_id}
            )

        # Track co-view
        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [f"viewed_by:{user_id}", f"item:{item_id}"],
                "vectors": [],
                "emotives": {}
            }
        )

    def get_similar_items(
        self,
        item_id: str,
        limit: int = 10
    ) -> List[str]:
        """Get items similar to given item"""
        node_id = f"item:{item_id}"

        # Get patterns for this item
        predictions = self.kato.get(
            f"/sessions/{node_id}/predictions"
        ).json()

        similar_items = []
        for pred in predictions[:limit]:
            if pred.get("future"):
                for event in pred["future"][0]:
                    if event.startswith("item:"):
                        similar = event.split(":")[1]
                        if similar != item_id:
                            similar_items.append(similar)

        return similar_items[:limit]
```

## Content-Based Recommendations

### Category-Based Recommendations

```python
class ContentBasedRecommender:
    """Content-based recommendations using item features"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def track_with_features(
        self,
        user_id: str,
        item_id: str,
        categories: List[str],
        tags: List[str],
        rating: Optional[float] = None
    ):
        """Track interaction with item features"""
        session_id = f"content:{user_id}"

        try:
            self.kato.get(f"/sessions/{session_id}")
        except:
            self.kato.post(
                "/sessions",
                json={"node_id": f"user:{user_id}"}
            )

        # Track with categories and tags
        strings = [f"item:{item_id}"]
        strings.extend([f"category:{cat}" for cat in categories])
        strings.extend([f"tag:{tag}" for tag in tags[:3]])  # Limit tags

        emotives = {}
        if rating:
            emotives["rating"] = (rating - 3.0) / 2.0

        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": strings,
                "vectors": [],
                "emotives": emotives
            }
        )

    def get_recommendations_by_preference(
        self,
        user_id: str,
        limit: int = 10
    ) -> Dict:
        """Get recommendations with preferred categories/tags"""
        session_id = f"content:{user_id}"

        predictions = self.kato.get(
            f"/sessions/{session_id}/predictions"
        ).json()

        # Extract preferred categories and tags
        preferred_categories = set()
        preferred_tags = set()
        recommended_items = []

        for pred in predictions[:limit]:
            if pred.get("future"):
                for event in pred["future"][0]:
                    if event.startswith("category:"):
                        preferred_categories.add(event.split(":")[1])
                    elif event.startswith("tag:"):
                        preferred_tags.add(event.split(":")[1])
                    elif event.startswith("item:"):
                        recommended_items.append(event.split(":")[1])

        return {
            "items": recommended_items[:limit],
            "preferred_categories": list(preferred_categories),
            "preferred_tags": list(preferred_tags)
        }
```

### Vector-Based Semantic Recommendations

```python
from typing import List

class SemanticRecommender:
    """Semantic recommendations using vector embeddings"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def track_with_embedding(
        self,
        user_id: str,
        item_id: str,
        embedding: List[float],
        interaction_type: str = "view"
    ):
        """Track interaction with item embedding"""
        session_id = f"semantic:{user_id}"

        try:
            self.kato.get(f"/sessions/{session_id}")
        except:
            self.kato.post(
                "/sessions",
                json={"node_id": f"user:{user_id}"}
            )

        # Send item with embedding
        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [f"{interaction_type}:{item_id}"],
                "vectors": [embedding],  # Item embedding
                "emotives": {}
            }
        )

    def get_semantic_recommendations(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict]:
        """Get semantically similar recommendations"""
        session_id = f"semantic:{user_id}"

        predictions = self.kato.get(
            f"/sessions/{session_id}/predictions"
        ).json()

        # KATO will find patterns in vector space
        recommendations = []
        for pred in predictions[:limit]:
            if pred.get("future"):
                for event in pred["future"][0]:
                    if ":" in event:
                        action, item_id = event.split(":", 1)
                        recommendations.append({
                            "item_id": item_id,
                            "predicted_action": action
                        })

        return recommendations[:limit]
```

## Hybrid Approaches

### Hybrid Recommendation System

```python
class HybridRecommender:
    """Combine collaborative, content-based, and sequential patterns"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)
        self.collaborative = UserBasedRecommender(kato_url)
        self.content = ContentBasedRecommender(kato_url)

    def track_rich_interaction(
        self,
        user_id: str,
        item_id: str,
        item_features: Dict,
        embedding: Optional[List[float]] = None,
        rating: Optional[float] = None
    ):
        """Track interaction with all available signals"""
        # Track for collaborative filtering
        self.collaborative.track_interaction(
            user_id, item_id, "view", rating
        )

        # Track for content-based
        if "categories" in item_features and "tags" in item_features:
            self.content.track_with_features(
                user_id,
                item_id,
                item_features["categories"],
                item_features["tags"],
                rating
            )

        # Track sequential pattern
        session_id = f"hybrid:{user_id}"
        try:
            self.kato.get(f"/sessions/{session_id}")
        except:
            self.kato.post(
                "/sessions",
                json={"node_id": f"user:{user_id}"}
            )

        strings = [f"item:{item_id}"]
        if "categories" in item_features:
            strings.append(f"cat:{item_features['categories'][0]}")

        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": strings,
                "vectors": [embedding] if embedding else [],
                "emotives": {"rating": (rating - 3) / 2} if rating else {}
            }
        )

    def get_hybrid_recommendations(
        self,
        user_id: str,
        limit: int = 10,
        weights: Dict[str, float] = None
    ) -> List[Dict]:
        """Get recommendations from multiple signals"""
        if weights is None:
            weights = {"collaborative": 0.4, "content": 0.3, "sequential": 0.3}

        # Get recommendations from each approach
        collab_recs = self.collaborative.get_recommendations(user_id, limit * 2)
        content_recs = self.content.get_recommendations_by_preference(user_id, limit * 2)

        # Get sequential predictions
        session_id = f"hybrid:{user_id}"
        predictions = self.kato.get(
            f"/sessions/{session_id}/predictions"
        ).json()

        # Combine and score
        item_scores = {}

        # Score collaborative
        for i, item in enumerate(collab_recs):
            score = (1.0 - i / len(collab_recs)) * weights["collaborative"]
            item_scores[item] = item_scores.get(item, 0) + score

        # Score content-based
        for i, item in enumerate(content_recs.get("items", [])):
            score = (1.0 - i / len(content_recs["items"])) * weights["content"]
            item_scores[item] = item_scores.get(item, 0) + score

        # Score sequential
        for i, pred in enumerate(predictions[:limit * 2]):
            if pred.get("future"):
                for event in pred["future"][0]:
                    if event.startswith("item:"):
                        item = event.split(":")[1]
                        score = (1.0 - i / len(predictions)) * weights["sequential"]
                        item_scores[item] = item_scores.get(item, 0) + score

        # Sort by combined score
        sorted_items = sorted(
            item_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return [
            {"item_id": item, "score": score}
            for item, score in sorted_items[:limit]
        ]
```

## Sequential Recommendations

### Session-Based Recommendations

```python
class SessionBasedRecommender:
    """Recommend next item in session sequence"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def track_session_event(
        self,
        anonymous_id: str,
        item_id: str,
        event_type: str = "view"
    ):
        """Track event in anonymous session"""
        session_id = f"session:{anonymous_id}"

        try:
            self.kato.get(f"/sessions/{session_id}")
        except:
            self.kato.post(
                "/sessions",
                json={
                    "node_id": "anonymous",
                    "config": {"session_ttl": 1800}  # 30 min
                }
            )

        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [f"{event_type}:{item_id}"],
                "vectors": [],
                "emotives": {}
            }
        )

    def get_next_item_predictions(
        self,
        anonymous_id: str,
        limit: int = 5
    ) -> List[str]:
        """Predict next item in session"""
        session_id = f"session:{anonymous_id}"

        predictions = self.kato.get(
            f"/sessions/{session_id}/predictions"
        ).json()

        next_items = []
        for pred in predictions[:limit]:
            if pred.get("future"):
                for event in pred["future"][0]:
                    if ":" in event:
                        _, item = event.split(":", 1)
                        next_items.append(item)

        return next_items[:limit]
```

## Real-Time Personalization

### Adaptive Recommendations

```python
class AdaptiveRecommender:
    """Real-time adaptive recommendations"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def update_and_recommend(
        self,
        user_id: str,
        current_item: str,
        interaction_type: str,
        limit: int = 5
    ) -> List[str]:
        """Update with current interaction and get immediate recommendations"""
        session_id = f"adaptive:{user_id}"

        try:
            self.kato.get(f"/sessions/{session_id}")
        except:
            self.kato.post(
                "/sessions",
                json={"node_id": f"user:{user_id}"}
            )

        # Track current interaction
        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [f"{interaction_type}:{current_item}"],
                "vectors": [],
                "emotives": {}
            }
        )

        # Get updated predictions
        predictions = self.kato.get(
            f"/sessions/{session_id}/predictions"
        ).json()

        # Extract recommendations
        recommendations = []
        for pred in predictions[:limit]:
            if pred.get("future"):
                for event in pred["future"][0]:
                    if ":" in event:
                        _, item = event.split(":", 1)
                        recommendations.append(item)

        return recommendations[:limit]
```

## Real-World Examples

### Example 1: E-Commerce Product Recommendations

```python
class EcommerceRecommender:
    """Complete e-commerce recommendation system"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def track_product_view(
        self,
        user_id: str,
        product_id: str,
        category: str,
        price_range: str
    ):
        """Track product view"""
        session_id = f"ecommerce:{user_id}"

        try:
            self.kato.get(f"/sessions/{session_id}")
        except:
            self.kato.post(
                "/sessions",
                json={"node_id": f"user:{user_id}"}
            )

        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [
                    f"view:{product_id}",
                    f"category:{category}",
                    f"price:{price_range}"
                ],
                "vectors": [],
                "emotives": {}
            }
        )

    def track_purchase(
        self,
        user_id: str,
        product_id: str,
        amount: float
    ):
        """Track purchase"""
        session_id = f"ecommerce:{user_id}"

        # Higher emotive value for purchase
        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [f"purchase:{product_id}"],
                "vectors": [],
                "emotives": {"purchase_value": min(amount / 1000, 1.0)}
            }
        )

    def get_recommendations_for_cart(
        self,
        user_id: str,
        cart_items: List[str]
    ) -> List[str]:
        """Recommend items for current cart"""
        session_id = f"ecommerce:{user_id}"

        # Track cart composition
        for item in cart_items:
            self.kato.post(
                f"/sessions/{session_id}/observe",
                json={
                    "strings": [f"in_cart:{item}"],
                    "vectors": [],
                    "emotives": {}
                }
            )

        # Get recommendations
        predictions = self.kato.get(
            f"/sessions/{session_id}/predictions"
        ).json()

        recommendations = []
        for pred in predictions[:10]:
            if pred.get("future"):
                for event in pred["future"][0]:
                    if event.startswith("purchase:"):
                        item = event.split(":")[1]
                        if item not in cart_items:
                            recommendations.append(item)

        return recommendations[:5]
```

### Example 2: Streaming Service Recommendations

```python
class StreamingRecommender:
    """Video/music streaming recommendations"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def track_play(
        self,
        user_id: str,
        content_id: str,
        genre: str,
        completion_rate: float,
        rating: Optional[float] = None
    ):
        """Track content playback"""
        session_id = f"streaming:{user_id}"

        try:
            self.kato.get(f"/sessions/{session_id}")
        except:
            self.kato.post(
                "/sessions",
                json={"node_id": f"user:{user_id}"}
            )

        # Track with engagement metrics
        emotives = {"engagement": completion_rate}
        if rating:
            emotives["rating"] = (rating - 3) / 2

        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [f"play:{content_id}", f"genre:{genre}"],
                "vectors": [],
                "emotives": emotives
            }
        )

    def get_watchlist_recommendations(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict]:
        """Get personalized watchlist"""
        session_id = f"streaming:{user_id}"

        predictions = self.kato.get(
            f"/sessions/{session_id}/predictions"
        ).json()

        recommendations = []
        for pred in predictions[:limit]:
            if pred.get("future"):
                content_items = []
                genres = []

                for event in pred["future"][0]:
                    if event.startswith("play:"):
                        content_items.append(event.split(":")[1])
                    elif event.startswith("genre:"):
                        genres.append(event.split(":")[1])

                if content_items:
                    recommendations.append({
                        "content_id": content_items[0],
                        "genres": genres
                    })

        return recommendations[:limit]
```

## Best Practices

1. **Track Diverse Signals**: Combine views, purchases, ratings
2. **Use Emotives**: Encode engagement strength (rating, dwell time)
3. **Category Hierarchies**: Include category/tag information
4. **Sequential Context**: Leverage KATO's temporal learning
5. **Hybrid Scoring**: Combine multiple recommendation strategies
6. **Cold Start**: Use content-based for new users/items
7. **Real-Time Updates**: Update immediately after interactions
8. **Explainability**: KATO patterns are interpretable

## Related Documentation

- [Pattern Matching](/docs/research/pattern-matching.md)
- [Vector Embeddings](/docs/research/vector-embeddings.md)
- [Emotives Processing](/docs/research/emotives-processing.md)
- [Session Management](session-management.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
