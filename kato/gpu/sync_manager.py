"""
Sync manager for CPU → GPU pattern promotion.

Handles automatic and manual synchronization triggers:
1. Automatic threshold (every N patterns)
2. Time-based background sync (every N seconds)
3. Manual API trigger
4. Training completion hook
"""

import logging
import threading
import time
from typing import Optional

from kato.gpu.matcher import HybridGPUMatcher
from kato.config.gpu_settings import GPUConfig

logger = logging.getLogger(__name__)


class SyncManager:
    """
    Manages CPU → GPU synchronization triggers and background tasks.

    Sync Triggers:
    1. Automatic: Every sync_threshold patterns added to CPU tier
    2. Background: Every sync_interval_seconds (if patterns pending)
    3. Manual: Explicit sync() call
    4. Training: After batch training completion (hook)

    Note:
        Background sync runs in daemon thread and stops gracefully on shutdown.
    """

    def __init__(
        self,
        matcher: HybridGPUMatcher,
        config: GPUConfig
    ):
        """
        Initialize sync manager.

        Args:
            matcher: HybridGPUMatcher instance to manage
            config: GPU configuration
        """
        self.matcher = matcher
        self.config = config

        # Background sync thread
        self.background_thread: Optional[threading.Thread] = None
        self.stop_background = threading.Event()

        # Sync statistics
        self.total_syncs = 0
        self.total_patterns_synced = 0
        self.last_sync_duration_ms = 0.0

        # Training mode flag (pauses automatic sync during training)
        self.training_mode = False

        logger.info("Sync manager initialized")

    def start_background_sync(self) -> None:
        """
        Start background sync thread.

        Background thread wakes every sync_interval_seconds to check if
        sync is needed. Runs as daemon thread.
        """
        if not self.config.enable_background_sync:
            logger.info("Background sync disabled in config")
            return

        if self.background_thread is not None and self.background_thread.is_alive():
            logger.warning("Background sync already running")
            return

        self.stop_background.clear()

        self.background_thread = threading.Thread(
            target=self._background_sync_loop,
            name="GPU-Sync-Background",
            daemon=True
        )
        self.background_thread.start()

        logger.info(
            f"Background sync started (interval: {self.config.sync_interval_seconds}s)"
        )

    def stop_background_sync(self) -> None:
        """
        Stop background sync thread gracefully.

        Waits up to 5 seconds for thread to stop.
        """
        if self.background_thread is None or not self.background_thread.is_alive():
            return

        logger.info("Stopping background sync...")

        self.stop_background.set()
        self.background_thread.join(timeout=5.0)

        if self.background_thread.is_alive():
            logger.warning("Background sync thread did not stop cleanly")
        else:
            logger.info("Background sync stopped")

        self.background_thread = None

    def _background_sync_loop(self) -> None:
        """
        Background sync loop (runs in separate thread).

        Wakes periodically to check if sync is needed.
        Stops when stop_background event is set.
        """
        logger.debug("Background sync loop started")

        while not self.stop_background.is_set():
            try:
                # Sleep with timeout (allows quick stop)
                self.stop_background.wait(timeout=self.config.sync_interval_seconds)

                if self.stop_background.is_set():
                    break

                # Check if sync needed
                if self.check_sync_needed(trigger_source="background"):
                    self.trigger_sync(source="background")

            except Exception as e:
                logger.error(f"Error in background sync loop: {e}", exc_info=True)
                # Continue loop (don't crash on errors)

        logger.debug("Background sync loop stopped")

    def check_sync_needed(self, trigger_source: str = "manual") -> bool:
        """
        Check if sync should be triggered.

        Args:
            trigger_source: Source of check ("manual", "background", "automatic")

        Returns:
            True if sync should be triggered

        Note:
            Respects training mode (pauses automatic/background sync).
        """
        # Never sync during training (manual override allowed)
        if self.training_mode and trigger_source != "manual":
            return False

        # Delegate to matcher's check
        return self.matcher.check_sync_needed()

    def trigger_sync(self, source: str = "manual") -> int:
        """
        Trigger CPU → GPU synchronization.

        Args:
            source: Source of trigger ("manual", "background", "automatic", "training")

        Returns:
            Number of patterns synchronized

        Note:
            Synchronization is blocking but typically fast (~100ms for 1K patterns).
        """
        if not self.matcher.use_gpu:
            logger.warning("GPU not available, cannot sync")
            return 0

        logger.info(f"Triggering sync from source: {source}")

        sync_start = time.time()

        # Perform sync
        patterns_synced = self.matcher.sync_cpu_to_gpu()

        sync_duration_ms = (time.time() - sync_start) * 1000

        # Update statistics
        self.total_syncs += 1
        self.total_patterns_synced += patterns_synced
        self.last_sync_duration_ms = sync_duration_ms

        logger.info(
            f"Sync complete: {patterns_synced:,} patterns in {sync_duration_ms:.1f}ms "
            f"(source: {source}, total syncs: {self.total_syncs})"
        )

        return patterns_synced

    def enter_training_mode(self) -> None:
        """
        Enter training mode (pauses automatic/background sync).

        During training mode:
        - Automatic threshold sync is disabled
        - Background time-based sync is disabled
        - Manual sync still works
        - Sync will trigger automatically after exit_training_mode()

        Use this when doing batch training to avoid sync overhead.
        """
        if self.training_mode:
            logger.warning("Already in training mode")
            return

        self.training_mode = True
        logger.info("Entered training mode (sync paused)")

    def exit_training_mode(self, trigger_sync: bool = True) -> None:
        """
        Exit training mode and optionally trigger sync.

        Args:
            trigger_sync: If True, sync immediately after exiting training mode

        Note:
            If trigger_sync=True and patterns are pending, sync will be triggered.
        """
        if not self.training_mode:
            logger.warning("Not in training mode")
            return

        self.training_mode = False
        logger.info("Exited training mode")

        # Trigger sync if requested and patterns pending
        if trigger_sync and len(self.matcher.cpu_tier) > 0:
            self.trigger_sync(source="training")

    def get_stats(self) -> dict:
        """
        Get sync manager statistics.

        Returns:
            Dictionary with sync metrics
        """
        return {
            'total_syncs': self.total_syncs,
            'total_patterns_synced': self.total_patterns_synced,
            'last_sync_duration_ms': self.last_sync_duration_ms,
            'background_sync_enabled': self.config.enable_background_sync,
            'background_sync_running': (
                self.background_thread is not None and
                self.background_thread.is_alive()
            ),
            'training_mode': self.training_mode,
            'cpu_tier_patterns': len(self.matcher.cpu_tier),
            'patterns_since_last_sync': self.matcher.patterns_since_sync,
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"SyncManager("
            f"syncs={self.total_syncs}, "
            f"patterns={self.total_patterns_synced:,}, "
            f"training={self.training_mode})"
        )

    def __del__(self):
        """Cleanup: Stop background thread on deletion."""
        try:
            self.stop_background_sync()
        except Exception:
            pass  # Ignore errors during cleanup
