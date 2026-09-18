"""Opt-out does not initialize Redis or change the default event mirror."""
import asyncio
import importlib.util
import sys
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parents[3] / "kato/storage/redis_streams.py"
    spec = importlib.util.spec_from_file_location("stm_opt_out_test_module", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_disabled_does_not_connect_or_allocate_manager(monkeypatch):
    module = load_module()
    monkeypatch.setenv("KATO_DISTRIBUTED_STM_ENABLED", "false")
    async def forbidden(_):
        raise AssertionError("disabled mirror tried to connect")
    monkeypatch.setattr(module.DistributedSTMManager, "initialize", forbidden)
    assert asyncio.run(module.get_distributed_stm_manager("test")) is None
    assert module._distributed_stm_manager is None


def test_existing_default_still_initializes_and_reuses_manager(monkeypatch):
    module = load_module()
    monkeypatch.delenv("KATO_DISTRIBUTED_STM_ENABLED", raising=False)
    calls = []
    async def initialize(manager):
        calls.append(manager.processor_id)
        return True
    monkeypatch.setattr(module.DistributedSTMManager, "initialize", initialize)
    first = asyncio.run(module.get_distributed_stm_manager("test"))
    assert asyncio.run(module.get_distributed_stm_manager("test")) is first
    assert calls == ["test"]
