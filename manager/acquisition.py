"""Build ``useq.MDAEvent`` lists for fabscope acquisitions and run them.

The legacy fabscope acquisition was a manual loop calling
``core.snap_image()`` per tile. Under pymmcore-plus we build a list of
``useq.MDAEvent`` objects (one per mask/tile), attach the SLM mask via
the ``slm_image`` field, and hand them to the core's ``run_mda``. The
default ``MDAEngine`` already calls ``setSLMImage`` + ``displaySLMImage``
for any event that carries an ``SLMImage``.
"""

import threading
import time
from typing import Callable, Iterable, Optional, Sequence

import numpy as np
from useq import MDAEvent, SLMImage


def qt_join(thread: threading.Thread, poll_s: float = 0.01) -> None:
    """Block until *thread* finishes while keeping the Qt event loop draining.

    ``pymmcore-plus``'s MDA signals (``frameReady`` etc.) are emitted from
    the MDA worker thread. When ``psygnal`` detects that Qt is loaded
    (which it is, transitively, the moment anything imports ``qtpy`` or
    ``napari``), cross-thread emissions get queued for delivery on the
    Qt main thread. A plain ``thread.join()`` blocks the main thread
    cold, so the queue never drains and listeners never fire.

    This helper polls the worker thread while calling
    ``QCoreApplication.processEvents()`` on each tick, so queued
    emissions get delivered as they arrive. If no Qt application
    instance exists yet (we're in a plain script that touched Qt only
    indirectly), one is created here so signals have somewhere to land.
    """
    try:
        from qtpy.QtCore import QCoreApplication
    except Exception:
        # Qt not available at all — psygnal will have emitted directly
        # on the worker thread; nothing to drain.
        thread.join()
        return

    import sys as _sys

    app = QCoreApplication.instance()
    if app is None:
        # Plain script case. Bootstrap a minimal QCoreApplication so the
        # main thread has an event dispatcher to drain emissions into.
        app = QCoreApplication(_sys.argv if _sys.argv else [""])
        # Anchor it on the module so it outlives this function frame —
        # without this, psygnal's QMDASignaler QObject can be GC'd
        # before the next call and any signal access fails with
        # "wrapped C/C++ object of type QMDASignaler has been deleted".
        globals()["_fabscope_qapp"] = app

    while thread.is_alive():
        app.processEvents()
        thread.join(timeout=poll_s)
    # Final drain for emissions that arrived just before the thread exited.
    app.processEvents()


def build_tile_events(
    mmc,
    tiles: Sequence[Sequence[np.ndarray]],
    channel_group: str,
    channel_config: str,
    camera_exposure: float,
    dmd_exposure: int,
    x_origin: float,
    y_origin: float,
    x_offset: float,
    y_offset: float,
    power_device: Optional[str] = None,
    power_property: Optional[str] = None,
    power: Optional[int] = None,
    exposure_times: Optional[Sequence[float]] = None,
    led_powers: Optional[Sequence[int]] = None,
) -> list[MDAEvent]:
    """Build one MDAEvent per tile in a row-major grid.

    Args:
        mmc: pymmcore_plus core instance (used only to look up the SLM device).
        tiles: 2D list of masks (DMD-shape uint8 arrays), indexed [row][col].
        channel_group / channel_config: MM config-group entry to set on each event.
        camera_exposure: default camera exposure (ms) for every tile.
        dmd_exposure: DMD display time (microseconds).
        x_origin / y_origin: stage XY for the top-left tile.
        x_offset / y_offset: tile-to-tile stage step.
        power_device / power_property / power: optional LED power baseline applied
            to every event via ``MDAEvent.properties``.
        exposure_times: optional per-row override of camera exposure (ms).
        led_powers: optional per-column override of LED power (requires
            ``power_device`` + ``power_property``).

    Returns:
        list of ``MDAEvent`` ready to feed to ``mmc.run_mda(events)``.
    """
    slm_dev = mmc.getSLMDevice()
    grid_height = len(tiles)
    grid_width = len(tiles[0]) if grid_height else 0
    channel = {"config": channel_config, "group": channel_group}

    events: list[MDAEvent] = []
    for col in range(grid_width):
        for row in range(grid_height):
            exp = exposure_times[row] if exposure_times is not None else camera_exposure
            x = x_origin + col * x_offset
            y = y_origin + row * y_offset

            if led_powers is not None and power_device and power_property:
                power_value = int(led_powers[col])
            else:
                power_value = power
            properties = None
            if power_value is not None and power_device and power_property:
                properties = [(power_device, power_property, power_value)]

            events.append(
                MDAEvent(
                    index={"p": col * grid_height + row},
                    channel=channel,
                    exposure=float(exp),
                    x_pos=x,
                    y_pos=y,
                    slm_image=SLMImage(
                        data=np.asarray(tiles[row][col]).astype(np.uint8),
                        device=slm_dev,
                        exposure=int(dmd_exposure),
                    ),
                    properties=properties,
                )
            )
    return events


def run_events(mmc, events: Iterable[MDAEvent], block: bool = True):
    """Run a sequence of events on the core's default MDA engine.

    Returns the thread handle from ``mmc.run_mda``; pass ``block=True``
    to wait until the acquisition finishes. Uses ``qt_join`` so that
    listener delivery works in both plain scripts and Qt-event-loop
    environments (Jupyter kernels, napari, etc.).
    """
    thread = mmc.run_mda(list(events))
    if block:
        qt_join(thread)
    return thread


def run_events_with_retry(
    mmc,
    events: Iterable[MDAEvent],
    on_frame: Optional[Callable[[np.ndarray, MDAEvent], None]] = None,
    max_retries: int = 5,
    retry_delay: float = 1.0,
) -> int:
    """Run events; on engine failure or partial completion, retry the tail.

    Counts frames as they arrive via ``frameReady``. If the MDA stops
    (RuntimeError or silent abort) before all events have produced an
    image, sleeps ``retry_delay`` seconds and re-runs the unfinished tail
    only — so a tile that already exposed isn't exposed a second time.

    ``max_retries`` caps consecutive attempts with zero progress; after
    that many failures in a row we raise.

    Args:
        mmc: CMMCorePlus instance.
        events: MDAEvents to run.
        on_frame: optional callback ``(image, event)`` invoked per acquired
            frame (use it for QC capture / progress bars).
        max_retries: consecutive retries with no new frames before giving up.
        retry_delay: seconds to wait between retries (lets hardware settle).

    Returns:
        Total number of events that produced a frame.
    """
    events = list(events)
    progress = {"count": 0}

    def _tick(image, event):
        progress["count"] += 1
        if on_frame is not None:
            on_frame(image, event)

    mmc.mda.events.frameReady.connect(_tick)
    try:
        attempt = 0
        while progress["count"] < len(events):
            before = progress["count"]
            pending = events[before:]
            try:
                qt_join(mmc.run_mda(pending))
            except RuntimeError as e:
                print(f"[run_events_with_retry] engine raised: {e}")
            if progress["count"] == before:
                attempt += 1
                if attempt >= max_retries:
                    raise RuntimeError(
                        f"No progress after {max_retries} retries at event "
                        f"{before}/{len(events)}; giving up."
                    )
                print(
                    f"  no progress; retrying remaining {len(pending)} events "
                    f"in {retry_delay}s (attempt {attempt}/{max_retries})"
                )
            else:
                attempt = 0
            time.sleep(retry_delay)
    finally:
        mmc.mda.events.frameReady.disconnect(_tick)
    return progress["count"]


def snap(mmc) -> np.ndarray:
    """Snap a single image with the current core settings.

    Bypasses the MDA engine entirely; if napari-micromanager's live view is
    running, the frame may end up consumed by its loop. Prefer ``snap_event``
    when running alongside the live viewer.
    """
    mmc.snap()
    return mmc.getImage()


def make_event(
    mmc,
    mask: np.ndarray,
    channel_group: str,
    channel_config: str,
    camera_exposure: float,
    dmd_exposure: int,
    *,
    power_device: Optional[str] = None,
    power_property: Optional[str] = None,
    power: Optional[int] = None,
    x_pos: Optional[float] = None,
    y_pos: Optional[float] = None,
) -> MDAEvent:
    """Build a single MDAEvent (channel + LED power + SLM mask + position)."""
    properties = None
    if power is not None and power_device and power_property:
        properties = [(power_device, power_property, int(power))]
    return MDAEvent(
        channel={"config": channel_config, "group": channel_group},
        exposure=float(camera_exposure),
        x_pos=x_pos,
        y_pos=y_pos,
        slm_image=SLMImage(
            data=np.ascontiguousarray(np.asarray(mask), dtype=np.uint8),
            device=mmc.getSLMDevice(),
            exposure=int(dmd_exposure),
        ),
        properties=properties,
    )


def snap_event(mmc, event: MDAEvent) -> np.ndarray:
    """Run a single MDAEvent through the engine and return the captured frame.

    Uses the threaded ``mmc.run_mda(...)`` path + ``qt_join`` so Qt-queued
    frame signals get drained on the main thread — napari-micromanager
    receives the frame in its viewer, and our temporary ``frameReady``
    listener captures it for the caller.

    Stops any continuous-sequence acquisition first (e.g. live view).
    """
    if mmc.isSequenceRunning():
        mmc.stopSequenceAcquisition()

    captured: list = []

    def _grab(image, _event, _meta=None):
        captured.append(np.asarray(image))

    mmc.mda.events.frameReady.connect(_grab)
    try:
        qt_join(mmc.run_mda([event]))
    finally:
        mmc.mda.events.frameReady.disconnect(_grab)

    if not captured:
        raise RuntimeError(
            "snap_event: MDA finished without producing a frame. If the Qt "
            "event loop isn't running on the main thread, frame signals can "
            "be dropped — see qt_join."
        )
    return captured[0]
