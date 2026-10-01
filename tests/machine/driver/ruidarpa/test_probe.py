"""
Unit tests for Ruida probing: building a device profile from raw
controller settings and the adapter's probe() connection flow.

Raw values mirror an RDC8445S as read over TCP.
"""

from unittest.mock import Mock

import pytest

from rayforge.machine.driver.driver import DriverPrecheckError
from rayforge.machine.driver.ruidarpa import rpa_adapter
from rayforge.machine.driver.ruidarpa.rpa_adapter import RuidaRPAAdapter
from rayforge.machine.driver.ruidarpa.rpa_direct_driver import (
    RpaDirectDriver,
)
from rayforge.machine.driver.ruidarpa.rpa_probe import (
    PROBE_SETTINGS,
    build_ruida_profile,
    controller_name,
    z_homing_from_settings,
)

RDC8445S_VALUES = {
    "MEM_CARD_ID": 0x90109010,
    "MEM_BED_SIZE_X": 1300000,
    "MEM_BED_SIZE_Y": 900000,
    "MEM_AXIS_MAX_VELOCITY_1": 500000,
    "MEM_AXIS_MAX_VELOCITY_2": 500000,
    "MEM_AXIS_MAX_ACC_1": 5000000,
    "MEM_AXIS_MAX_ACC_2": 3000000,
}


class TestBuildRuidaProfile:
    """Raw controller settings map onto the machine config."""

    def test_rdc8445s_settings(self):
        profile, warnings = build_ruida_profile(RDC8445S_VALUES)
        config = profile.machine_config

        assert profile.meta.name == "Ruida RDC8445S"
        assert config.axis_extents == (1300.0, 900.0)
        assert config.max_travel_speed == 30000
        assert config.max_cut_speed == 30000
        assert config.acceleration == 3000
        assert config.origin is None
        assert warnings == []

    def test_slowest_axis_limits_speed_and_acceleration(self):
        values = dict(
            RDC8445S_VALUES,
            MEM_AXIS_MAX_VELOCITY_1=400000,
            MEM_AXIS_MAX_ACC_2=8000000,
        )
        config = build_ruida_profile(values)[0].machine_config

        assert config.max_travel_speed == 24000
        assert config.acceleration == 5000

    def test_missing_values_become_warnings(self):
        profile, warnings = build_ruida_profile({"MEM_CARD_ID": 0x90109010})
        config = profile.machine_config

        assert config.axis_extents is None
        assert config.max_travel_speed is None
        assert config.acceleration is None
        assert len(warnings) == 3

    def test_non_positive_bed_size_is_ignored(self):
        values = dict(RDC8445S_VALUES, MEM_BED_SIZE_X=0)
        profile, warnings = build_ruida_profile(values)

        assert profile.machine_config.axis_extents is None
        assert len(warnings) == 1

    def test_unknown_card_is_named_and_warned(self):
        values = dict(RDC8445S_VALUES, MEM_CARD_ID=0x12345678)
        profile, warnings = build_ruida_profile(values)

        assert profile.meta.name == "Ruida (card ID 0x12345678)"
        assert len(warnings) == 1

    def test_controller_name_without_card_id(self):
        assert controller_name({}) == "Ruida"


class TestZHomingFromSettings:
    """The focus-enabled flag selects the Z homing mode."""

    def test_focus_enabled_selects_focus_probe(self):
        # RDC8445S reads 0x8201: focus enabled, air assist by layer.
        assert z_homing_from_settings({"MEM_FOCUS_CONFIG": 0x8201}) == (
            "focus"
        )

    def test_focus_disabled_selects_home_switch(self):
        assert z_homing_from_settings({"MEM_FOCUS_CONFIG": 0x8200}) == (
            "switch"
        )

    def test_unread_setting_leaves_mode_unset(self):
        assert z_homing_from_settings({}) is None


def _probe_backend(monkeypatch, *, started=True, values=None) -> Mock:
    """Patch the adapter to build a mock direct driver for probing."""
    backend = Mock(spec=RpaDirectDriver)
    backend.start.return_value = started
    backend.is_connected = True
    backend.read_settings.return_value = (
        RDC8445S_VALUES if values is None else values
    )
    monkeypatch.setattr(rpa_adapter, "RpaDirectDriver", lambda: backend)
    return backend


class TestProbe:
    """probe() connects directly, reads settings, then disconnects."""

    @pytest.mark.asyncio
    async def test_probe_reads_settings_over_tcp(self, monkeypatch):
        backend = _probe_backend(monkeypatch)
        args = {"udp_host": "192.168.1.208", "network_protocol": "TCP"}

        profile, warnings = await RuidaRPAAdapter.probe(Mock(), **args)

        backend.start.assert_called_once_with(
            "192.168.1.208", None, None, protocol="tcp"
        )
        backend.read_settings.assert_called_once_with(
            PROBE_SETTINGS, RuidaRPAAdapter.PROBE_READ_TIMEOUT
        )
        backend.stop.assert_called_once()
        assert profile.machine_config.driver == "RuidaRPAAdapter"
        assert profile.machine_config.driver_args == args
        assert profile.machine_config.axis_extents == (1300.0, 900.0)
        assert warnings == []

    @pytest.mark.asyncio
    async def test_probe_sets_focus_z_homing(self, monkeypatch):
        values = dict(RDC8445S_VALUES, MEM_FOCUS_CONFIG=0x8201)
        _probe_backend(monkeypatch, values=values)

        profile, _warnings = await RuidaRPAAdapter.probe(
            Mock(), udp_host="192.168.1.208"
        )

        assert profile.machine_config.driver_args == {
            "udp_host": "192.168.1.208",
            "z_homing": "focus",
        }

    @pytest.mark.asyncio
    async def test_probe_failed_start_raises_and_stops(self, monkeypatch):
        backend = _probe_backend(monkeypatch, started=False)

        with pytest.raises(ConnectionError):
            await RuidaRPAAdapter.probe(Mock(), udp_host="192.168.1.208")

        backend.read_settings.assert_not_called()
        backend.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_probe_silent_controller_times_out(self, monkeypatch):
        backend = _probe_backend(monkeypatch)
        backend.is_connected = False
        monkeypatch.setattr(RuidaRPAAdapter, "PROBE_CONNECT_TIMEOUT", 0.05)
        monkeypatch.setattr(RuidaRPAAdapter, "CONNECTION_POLL_INTERVAL", 0.01)

        with pytest.raises(TimeoutError):
            await RuidaRPAAdapter.probe(Mock(), udp_host="192.168.1.208")

        backend.read_settings.assert_not_called()
        backend.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_probe_requires_an_endpoint(self, monkeypatch):
        backend = _probe_backend(monkeypatch)

        with pytest.raises(DriverPrecheckError):
            await RuidaRPAAdapter.probe(Mock())

        backend.start.assert_not_called()

    def test_adapter_supports_probing(self):
        assert RuidaRPAAdapter.supports_probing is True
