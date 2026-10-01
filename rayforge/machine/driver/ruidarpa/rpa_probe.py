"""Build a Rayforge device profile from Ruida controller settings."""

from __future__ import annotations

import logging
from gettext import gettext as _
from typing import TYPE_CHECKING

from protocols.ruida.ruida_protocol import CARD_IDS

if TYPE_CHECKING:
    from rayforge.machine.device.profile import DeviceProfile

logger = logging.getLogger(__name__)

# Controller memory read during a probe. Lengths are in µm, velocities
# in µm/s and accelerations in µm/s² (verified on an RDC8445S).
PROBE_SETTINGS = [
    "MEM_CARD_ID",
    "MEM_BED_SIZE_X",
    "MEM_BED_SIZE_Y",
    "MEM_AXIS_MAX_VELOCITY_1",
    "MEM_AXIS_MAX_VELOCITY_2",
    "MEM_AXIS_MAX_ACC_1",
    "MEM_AXIS_MAX_ACC_2",
    "MEM_FOCUS_CONFIG",
]

# How Home Z references the Z axis: a Z home switch (HOME_Z) or the
# controller's auto-focus probe (FOCUS_Z). On an RDC8445S, HOME_Z stops
# with the work against the probe, while FOCUS_Z leaves it at focus height.
Z_HOMING_SWITCH = "switch"
Z_HOMING_FOCUS = "focus"

# MEM_FOCUS_CONFIG bit set when the controller has auto-focus enabled.
_FOCUS_ENABLED_BIT = 0x0001

_UM_PER_MM = 1000.0


def _pair_mm(
    values: dict[str, int], key_x: str, key_y: str
) -> tuple[float, float] | None:
    """Return a positive (x, y) pair in mm, or None if unusable."""
    raw_x = values.get(key_x)
    raw_y = values.get(key_y)
    if raw_x is None or raw_y is None or raw_x <= 0 or raw_y <= 0:
        return None
    return raw_x / _UM_PER_MM, raw_y / _UM_PER_MM


def controller_name(values: dict[str, int]) -> str:
    """Name the controller from its card ID."""
    card_id = values.get("MEM_CARD_ID")
    if card_id is None:
        return "Ruida"
    model = CARD_IDS.get(card_id)
    if model is None:
        return f"Ruida (card ID 0x{card_id:08X})"
    return f"Ruida {model}"


def z_homing_from_settings(values: dict[str, int]) -> str | None:
    """Pick the Z homing mode from the controller's focus setting.

    Returns "focus" when auto-focus is enabled, "switch" when it is
    disabled, or None if the setting could not be read.
    """
    focus_config = values.get("MEM_FOCUS_CONFIG")
    if focus_config is None:
        return None
    if focus_config & _FOCUS_ENABLED_BIT:
        return Z_HOMING_FOCUS
    return Z_HOMING_SWITCH


def build_ruida_profile(
    values: dict[str, int],
) -> tuple[DeviceProfile, list[str]]:
    """
    Build a ``DeviceProfile`` from raw Ruida controller settings.

    *values* maps the ``PROBE_SETTINGS`` mnemonics to the raw values
    read from the controller; missing settings are skipped. This is a
    pure data-transformation function with no I/O.

    Returns a ``(DeviceProfile, warnings)`` tuple. All failures become
    warnings; this function never raises.
    """
    from rayforge.machine.device.profile import (
        DeviceMeta,
        DeviceProfile,
        MachineConfig,
    )

    warnings: list[str] = []
    name = controller_name(values)
    if "MEM_CARD_ID" in values and values["MEM_CARD_ID"] not in CARD_IDS:
        warnings.append(
            _("Unrecognised Ruida controller model; settings may differ.")
        )

    extents = _pair_mm(values, "MEM_BED_SIZE_X", "MEM_BED_SIZE_Y")
    if extents is None:
        warnings.append(_("Could not read the Ruida bed size."))

    velocity = _pair_mm(
        values, "MEM_AXIS_MAX_VELOCITY_1", "MEM_AXIS_MAX_VELOCITY_2"
    )
    max_speed: int | None = None
    if velocity is not None:
        # Controller velocities are per second; the machine uses mm/min.
        max_speed = int(min(velocity) * 60)
    else:
        warnings.append(_("Could not read the Ruida maximum speeds."))

    acceleration_mm = _pair_mm(
        values, "MEM_AXIS_MAX_ACC_1", "MEM_AXIS_MAX_ACC_2"
    )
    acceleration: int | None = None
    if acceleration_mm is not None:
        acceleration = int(min(acceleration_mm))
    else:
        warnings.append(_("Could not read the Ruida acceleration."))

    return (
        DeviceProfile(
            meta=DeviceMeta(
                name=name,
                vendor="Ruida",
                description=_("Auto-configured via probe wizard"),
            ),
            machine_config=MachineConfig(
                axis_extents=extents,
                max_travel_speed=max_speed,
                max_cut_speed=max_speed,
                acceleration=acceleration,
                single_axis_homing_enabled=True,
            ),
            dialect_config={},
        ),
        warnings,
    )
