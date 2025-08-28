#!/usr/bin/env python3
"""
Load generator for KATO stress tests.
Generates realistic load patterns with various distributions and traffic patterns.
"""

import time
import random
import string
import threading
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass
import math

# Simple math utilities for load patterns
def sin_wave(x):
    """Calculate sine wave value."""
    return math.sin(x)

def poisson_sample(mean):
    """Simple Poisson approximation using random."""
    import random as rand
    # Use a simple approximation for Poisson distribution
    # For large mean, Poisson approximates normal distribution
    if mean > 20:
        return max(0, int(rand.gauss(mean, math.sqrt(mean))))
    else:
        # For small mean, use simple simulation
        L = math.exp(-mean)
        k = 0
        p = 1.0
        while p > L:
            k += 1
            p *= rand.random()
        return k - 1
from enum import Enum


class LoadPattern(Enum):
    """Load pattern types."""
    CONSTANT = "constant"
    RAMP_UP = "ramp_up"
    RAMP_DOWN = "ramp_down"
    SPIKE = "spike"
    WAVE = "wave"
    RANDOM = "random"
    POISSON = "poisson"
    BURST = "burst"


@dataclass
class LoadProfile:
    """Configuration for load generation."""
    pattern: LoadPattern
    duration_seconds: float
    initial_users: int
    peak_users: int
    requests_per_user_per_second: float
    think_time_ms: float = 1000
    ramp_time_seconds: float = 30
    spike_interval_seconds: float = 60
    spike_duration_seconds: float = 10
    wave_period_seconds: float = 120


class DataGenerator:
    """Generates realistic test data for KATO operations."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize test data generator.
        
        Args:
            config: Test data configuration from stress_config.yaml
        """
        self.config = config
        
        # Pre-generate vocabulary for consistent data
        self.vocabulary = self._generate_vocabulary()
        
        # Emotive types
        self.emotive_types = [
            "joy", "sadness", "anger", "fear", "surprise",
            "disgust", "trust", "anticipation", "interest",
            "confusion", "excitement", "calm", "stress"
        ]
        
    def _generate_vocabulary(self) -> List[str]:
        """Generate a vocabulary of test strings."""
        vocab = []
        vocab_size = self.config.get('string_vocabulary_size', 1000)
        
        # Add common words
        common_words = [
            "the", "and", "a", "to", "of", "in", "is", "that", "it", "was",
            "for", "on", "with", "as", "at", "by", "from", "be", "have", "had",
            "data", "test", "kato", "observe", "learn", "predict", "model",
            "sequence", "pattern", "memory", "processor", "system", "analyze"
        ]
        vocab.extend(common_words)
        
        # Add random words
        while len(vocab) < vocab_size:
            word_length = random.randint(3, 12)
            word = ''.join(random.choices(string.ascii_lowercase, k=word_length))
            vocab.append(word)
            
        return vocab[:vocab_size]
        
    def generate_observation_data(self) -> Dict[str, Any]:
        """Generate random observation data."""
        data = {
            "strings": [],
            "vectors": [],
            "emotives": {}
        }
        
        # Generate strings
        num_strings = random.randint(
            self.config.get('min_strings_per_observation', 1),
            self.config.get('max_strings_per_observation', 10)
        )
        
        for _ in range(num_strings):
            # Mix vocabulary words and random strings
            if random.random() < 0.7:  # 70% from vocabulary
                data["strings"].append(random.choice(self.vocabulary))
            else:  # 30% random
                length = random.randint(
                    self.config.get('min_string_length', 1),
                    self.config.get('max_string_length', 50)
                )
                data["strings"].append(''.join(
                    random.choices(string.ascii_letters + string.digits, k=length)
                ))
                
        # Generate vectors (optional)
        if random.random() < self.config.get('vector_probability', 0.3):
            vector_size = random.randint(
                self.config.get('min_vector_size', 10),
                self.config.get('max_vector_size', 100)
            )
            
            vector_range = self.config.get('vector_dimension_range', [0.0, 1.0])
            data["vectors"] = [
                random.uniform(vector_range[0], vector_range[1])
                for _ in range(vector_size)
            ]
            
        # Generate emotives (optional)
        if random.random() < self.config.get('emotive_probability', 0.2):
            num_emotives = random.randint(
                self.config.get('min_emotives', 1),
                self.config.get('max_emotives', 5)
            )
            
            emotive_range = self.config.get('emotive_value_range', [0.0, 1.0])
            selected_emotives = random.sample(
                self.emotive_types,
                min(num_emotives, len(self.emotive_types))
            )
            
            for emotive in selected_emotives:
                data["emotives"][emotive] = random.uniform(
                    emotive_range[0], emotive_range[1]
                )
                
        return data
        
    def generate_sequence(self, length: int) -> List[Dict[str, Any]]:
        """Generate a sequence of observations."""
        sequence = []
        
        # Generate with some pattern for more realistic sequences
        base_strings = random.sample(self.vocabulary, min(10, len(self.vocabulary)))
        
        for i in range(length):
            data = {
                "strings": [],
                "vectors": [],
                "emotives": {}
            }
            
            # Create evolving pattern
            if i == 0:
                # Start of sequence
                data["strings"] = random.sample(base_strings, random.randint(1, 3))
            elif i == length - 1:
                # End of sequence
                data["strings"] = ["end"] + random.sample(base_strings, random.randint(0, 2))
            else:
                # Middle of sequence - evolve from previous
                prev_strings = sequence[-1]["strings"] if sequence else base_strings
                # Keep some, add some new
                keep_count = random.randint(0, min(2, len(prev_strings)))
                keep_strings = random.sample(prev_strings, keep_count) if prev_strings else []
                new_strings = random.sample(base_strings, random.randint(1, 3))
                data["strings"] = keep_strings + new_strings
                
            # Occasionally add vectors/emotives
            if random.random() < 0.2:
                data["vectors"] = [random.random() for _ in range(random.randint(5, 20))]
                
            if random.random() < 0.1:
                data["emotives"] = {
                    random.choice(self.emotive_types): random.random()
                }
                
            sequence.append(data)
            
        return sequence


class VirtualUser:
    """Represents a virtual user generating load."""
    
    def __init__(self, user_id: int, request_func: Callable,
                 data_generator: DataGenerator,
                 operations_mix: Dict[str, float],
                 requests_per_second: float = 1.0,
                 think_time_ms: float = 1000):
        """
        Initialize virtual user.
        
        Args:
            user_id: Unique user identifier
            request_func: Function to make requests
            data_generator: Test data generator
            operations_mix: Probability distribution of operations
            requests_per_second: Target requests per second for this user
            think_time_ms: Think time between requests in milliseconds
        """
        self.user_id = user_id
        self.request_func = request_func
        self.data_generator = data_generator
        self.operations_mix = operations_mix
        self.requests_per_second = requests_per_second
        self.think_time_ms = think_time_ms
        
        self.active = False
        self.thread = None
        self.request_count = 0
        self.error_count = 0
        
        # User state for realistic behavior
        self.working_memory_size = 0
        self.has_learned_model = False
        
    def start(self):
        """Start generating load."""
        self.active = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop generating load."""
        self.active = False
        if self.thread:
            self.thread.join(timeout=5)
            
    def _run(self):
        """Main loop for virtual user."""
        while self.active:
            try:
                # Select operation based on mix
                operation = self._select_operation()
                
                # Execute operation
                self._execute_operation(operation)
                
                # Apply think time
                time.sleep(self.think_time_ms / 1000.0)
                
                # Rate limiting
                expected_interval = 1.0 / self.requests_per_second
                time.sleep(max(0, expected_interval - (self.think_time_ms / 1000.0)))
                
            except Exception as e:
                self.error_count += 1
                print(f"User {self.user_id} error: {e}")
                
    def _select_operation(self) -> str:
        """Select operation based on probability distribution."""
        rand = random.random()
        cumulative = 0.0
        
        for operation, probability in self.operations_mix.items():
            cumulative += probability
            if rand < cumulative:
                return operation
                
        return "observe"  # Default
        
    def _execute_operation(self, operation: str):
        """Execute the selected operation."""
        self.request_count += 1
        
        if operation == "observe":
            data = self.data_generator.generate_observation_data()
            self.request_func("observe", data)
            self.working_memory_size += 1
            
        elif operation == "learn":
            # Only learn if we have observations
            if self.working_memory_size > 0:
                self.request_func("learn", {})
                self.has_learned_model = True
                self.working_memory_size = 0
                
        elif operation == "predictions":
            # Get predictions if we have models
            if self.has_learned_model:
                self.request_func("predictions", {})
                
        elif operation == "working_memory":
            self.request_func("working_memory", {})
            
        elif operation == "clear_memory":
            self.request_func("clear_working_memory", {})
            self.working_memory_size = 0


class LoadGenerator:
    """Generates load according to specified patterns."""
    
    def __init__(self, profile: LoadProfile,
                 request_func: Callable,
                 data_config: Dict[str, Any],
                 operations_mix: Dict[str, float]):
        """
        Initialize load generator.
        
        Args:
            profile: Load profile configuration
            request_func: Function to make requests
            data_config: Test data configuration
            operations_mix: Operation probability distribution
        """
        self.profile = profile
        self.request_func = request_func
        self.data_generator = DataGenerator(data_config)
        self.operations_mix = operations_mix
        
        self.users: List[VirtualUser] = []
        self.active = False
        self.start_time = None
        self.control_thread = None
        
    def start(self):
        """Start load generation."""
        self.active = True
        self.start_time = time.time()
        self.control_thread = threading.Thread(target=self._control_loop, daemon=True)
        self.control_thread.start()
        
    def stop(self):
        """Stop load generation."""
        self.active = False
        
        # Stop all users
        for user in self.users:
            user.stop()
            
        if self.control_thread:
            self.control_thread.join(timeout=5)
            
        self.users.clear()
        
    def _control_loop(self):
        """Control loop for managing virtual users based on load pattern."""
        while self.active:
            elapsed = time.time() - self.start_time
            
            # Determine target user count based on pattern
            target_users = self._calculate_target_users(elapsed)
            
            # Adjust user count
            self._adjust_users(target_users)
            
            # Check if test duration exceeded
            if elapsed > self.profile.duration_seconds:
                self.active = False
                break
                
            time.sleep(1)  # Control loop interval
            
    def _calculate_target_users(self, elapsed: float) -> int:
        """Calculate target number of users based on load pattern."""
        if self.profile.pattern == LoadPattern.CONSTANT:
            return self.profile.peak_users
            
        elif self.profile.pattern == LoadPattern.RAMP_UP:
            if elapsed < self.profile.ramp_time_seconds:
                progress = elapsed / self.profile.ramp_time_seconds
                return int(self.profile.initial_users + 
                          (self.profile.peak_users - self.profile.initial_users) * progress)
            return self.profile.peak_users
            
        elif self.profile.pattern == LoadPattern.RAMP_DOWN:
            if elapsed < self.profile.ramp_time_seconds:
                progress = elapsed / self.profile.ramp_time_seconds
                return int(self.profile.peak_users - 
                          (self.profile.peak_users - self.profile.initial_users) * progress)
            return self.profile.initial_users
            
        elif self.profile.pattern == LoadPattern.SPIKE:
            # Periodic spikes
            cycle_time = elapsed % self.profile.spike_interval_seconds
            if cycle_time < self.profile.spike_duration_seconds:
                return self.profile.peak_users
            return self.profile.initial_users
            
        elif self.profile.pattern == LoadPattern.WAVE:
            # Sine wave pattern
            phase = (elapsed / self.profile.wave_period_seconds) * 2 * math.pi
            amplitude = (self.profile.peak_users - self.profile.initial_users) / 2
            midpoint = (self.profile.peak_users + self.profile.initial_users) / 2
            return int(midpoint + amplitude * sin_wave(phase))
            
        elif self.profile.pattern == LoadPattern.RANDOM:
            # Random fluctuation
            return random.randint(self.profile.initial_users, self.profile.peak_users)
            
        elif self.profile.pattern == LoadPattern.POISSON:
            # Poisson distribution for realistic traffic
            mean_users = (self.profile.peak_users + self.profile.initial_users) / 2
            return min(self.profile.peak_users, 
                      max(self.profile.initial_users, 
                          poisson_sample(mean_users)))
                          
        elif self.profile.pattern == LoadPattern.BURST:
            # Sudden burst pattern
            if elapsed < self.profile.ramp_time_seconds:
                # Sudden jump to peak
                return self.profile.peak_users
            else:
                # Then gradual decline
                remaining = self.profile.duration_seconds - elapsed
                if remaining > 0:
                    decline_rate = (self.profile.peak_users - self.profile.initial_users) / (
                        self.profile.duration_seconds - self.profile.ramp_time_seconds)
                    return max(self.profile.initial_users,
                              int(self.profile.peak_users - decline_rate * 
                                  (elapsed - self.profile.ramp_time_seconds)))
                return self.profile.initial_users
                
        return self.profile.initial_users
        
    def _adjust_users(self, target_users: int):
        """Adjust the number of virtual users."""
        current_users = len(self.users)
        
        if target_users > current_users:
            # Add users
            for i in range(target_users - current_users):
                user = VirtualUser(
                    user_id=len(self.users),
                    request_func=self.request_func,
                    data_generator=self.data_generator,
                    operations_mix=self.operations_mix,
                    requests_per_second=self.profile.requests_per_user_per_second,
                    think_time_ms=self.profile.think_time_ms
                )
                user.start()
                self.users.append(user)
                
        elif target_users < current_users:
            # Remove users
            while len(self.users) > target_users:
                user = self.users.pop()
                user.stop()
                
    def get_statistics(self) -> Dict[str, Any]:
        """Get current load generation statistics."""
        total_requests = sum(user.request_count for user in self.users)
        total_errors = sum(user.error_count for user in self.users)
        
        return {
            'active_users': len(self.users),
            'total_requests': total_requests,
            'total_errors': total_errors,
            'error_rate': total_errors / total_requests if total_requests > 0 else 0,
            'elapsed_seconds': time.time() - self.start_time if self.start_time else 0
        }


class BurstLoadGenerator:
    """Specialized generator for burst traffic patterns."""
    
    def __init__(self, request_func: Callable,
                 data_generator: DataGenerator,
                 burst_size: int = 1000,
                 burst_duration_ms: int = 100):
        """
        Initialize burst load generator.
        
        Args:
            request_func: Function to make requests
            data_generator: Test data generator
            burst_size: Number of requests per burst
            burst_duration_ms: Duration of burst in milliseconds
        """
        self.request_func = request_func
        self.data_generator = data_generator
        self.burst_size = burst_size
        self.burst_duration_ms = burst_duration_ms
        
    def generate_burst(self):
        """Generate a burst of requests."""
        threads = []
        
        def make_request():
            data = self.data_generator.generate_observation_data()
            self.request_func("observe", data)
            
        # Create threads for concurrent requests
        for _ in range(self.burst_size):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            
        # Start all threads with minimal delay
        start_time = time.time()
        for thread in threads:
            thread.start()
            
            # Spread requests over burst duration
            elapsed = (time.time() - start_time) * 1000
            if elapsed < self.burst_duration_ms:
                time.sleep((self.burst_duration_ms - elapsed) / 1000 / len(threads))
                
        # Wait for completion
        for thread in threads:
            thread.join(timeout=10)