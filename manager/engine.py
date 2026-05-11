"""Custom MDA engine for fabscope.

The default ``pymmcore_plus.mda.MDAEngine.setup_event`` ends in
``mmcore.waitForSystem()``, which polls every loaded device's ``Busy()``
flag. On this Moench microscope the Mosaic 3 (DMD) and TIXYDrive (XY
stage) both report ``Busy=True`` long after they're physically settled,
so ``waitForSystem`` reliably times out and crashes the MDA on every
event.

This engine mirrors the pattern in ``faro/microscope/pertzlab/moench.py``:
skip the problem devices from per-device waits entirely, and instead
confirm the XY stage settled by polling its reported position against
the event's target XY.
"""

import time
from typing import Iterable

from pymmcore_plus.mda import MDAEngine
from useq import MDAEvent

try:  # pragma: no cover - only used for isinstance check
    from useq import SequencedEvent  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    SequencedEvent = ()  # type: ignore[assignment]


class FabscopeMDAEngine(MDAEngine):
    """MDAEngine that bypasses ``waitForSystem`` for devices with stuck Busy flags.

    ``skip_devices`` is a per-device skip list for the per-device wait loop.
    The XY stage is *always* skipped from that loop and instead confirmed
    via position polling against the event target, so it does not need to
    appear here — by default we only skip ``Mosaic3`` (matching faro).
    """

    def __init__(
        self,
        mmcore=None,
        *,
        skip_devices: Iterable[str] = ("Mosaic3",),
        xy_tolerance_um: float = 1.0,
        xy_max_wait_s: float = 5.0,
        xy_poll_interval_s: float = 0.5,
    ) -> None:
        super().__init__(mmcore)
        self._skip_devices = tuple(skip_devices)
        self._xy_tolerance_um = xy_tolerance_um
        self._xy_max_wait_s = xy_max_wait_s
        self._xy_poll_interval_s = xy_poll_interval_s

    def setup_event(self, event: MDAEvent) -> None:
        """Apply event settings, then run a relaxed system wait."""
        if SequencedEvent and isinstance(event, SequencedEvent):
            self.setup_sequenced_event(event)
        else:
            self.setup_single_event(event)
        # Deliberately skip super().setup_event's final mmcore.waitForSystem():
        # Mosaic3 and TIXYDrive have stuck Busy() flags and time it out.
        self._wait_for_system_relaxed(event)

    def _wait_for_system_relaxed(self, event: MDAEvent) -> None:
        """Wait for every loaded device except the XY stage and skip list.

        Then verify XY position settled by polling against the event target.
        """
        core = self.mmcore
        xy_stage = core.getXYStageDevice() or None

        skip = {"Core"}
        skip.update(self._skip_devices)
        if xy_stage:
            skip.add(xy_stage)

        for dev in core.getLoadedDevices():
            if dev in skip:
                continue
            try:
                core.waitForDevice(dev)
            except RuntimeError as e:
                if "timed out" in str(e).lower():
                    print(f"[FabscopeMDAEngine] waitForDevice({dev}) timed out: {e}")
                else:
                    raise

        target_xy = (event.x_pos, event.y_pos)
        if xy_stage and target_xy != (None, None):
            elapsed = 0.0
            while elapsed < self._xy_max_wait_s:
                try:
                    actual = core.getXYPosition()
                    dx = abs(actual[0] - target_xy[0])
                    dy = abs(actual[1] - target_xy[1])
                    if dx < self._xy_tolerance_um and dy < self._xy_tolerance_um:
                        break
                except Exception:
                    pass
                time.sleep(self._xy_poll_interval_s)
                elapsed += self._xy_poll_interval_s
            else:
                try:
                    actual = core.getXYPosition()
                except Exception:
                    actual = "unknown"
                print(
                    f"[FabscopeMDAEngine] {xy_stage} not at target after "
                    f"{self._xy_max_wait_s}s. target={target_xy}, actual={actual}"
                )


def install(mmc, **kwargs) -> FabscopeMDAEngine:
    """Register a ``FabscopeMDAEngine`` on the given core and return it."""
    engine = FabscopeMDAEngine(mmc, **kwargs)
    mmc.mda.set_engine(engine)
    return engine
