import unittest
from unittest.mock import AsyncMock, patch

from agent.pumpfun.control_store import MonitorControl, control_tick


class ControlStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_state_fails_closed_and_writes_heartbeat(self):
        state = MonitorControl(enabled=True)
        with patch("agent.pumpfun.control_store._command", new=AsyncMock(side_effect=[None, "OK"])) as command:
            await control_tick(state)
        self.assertFalse(state.running)
        self.assertEqual(state.last_error, "control_state_missing_or_invalid")
        self.assertEqual(command.await_count, 2)

    async def test_running_state_requires_successful_heartbeat(self):
        state = MonitorControl(enabled=True)
        with patch("agent.pumpfun.control_store._command", new=AsyncMock(side_effect=["running", "OK"])):
            await control_tick(state)
        self.assertTrue(state.running)
        self.assertIsNone(state.last_error)

    async def test_store_failure_fails_closed(self):
        state = MonitorControl(enabled=True, running=True)
        with patch("agent.pumpfun.control_store._command", new=AsyncMock(side_effect=RuntimeError("secret URL must not leak"))):
            await control_tick(state)
        self.assertFalse(state.running)
        self.assertEqual(state.last_error, "control_store_unavailable")

    async def test_heartbeat_failure_fails_closed_even_if_state_running(self):
        state = MonitorControl(enabled=True)
        with patch("agent.pumpfun.control_store._command", new=AsyncMock(side_effect=["running", "ERROR"])):
            await control_tick(state)
        self.assertFalse(state.running)
        self.assertEqual(state.last_error, "heartbeat_write_failed")

    async def test_control_disabled_preserves_local_monitor_behavior(self):
        state = MonitorControl(enabled=False)
        with patch("agent.pumpfun.control_store._command", new=AsyncMock()) as command:
            await control_tick(state)
        self.assertTrue(state.running)
        command.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
