import time

import numpy as np


class dmd:
    """Minimal DMD/SLM wrapper for fabscope.

    Masks are authored at native DMD resolution (e.g. 600x800) and uploaded
    directly. No camera<->DMD coordinate transform is applied — fabscope
    cuts large patterns into DMD-sized tiles via ``utils.mask_handler.tile_array``
    and exposes each tile in place.
    """

    def __init__(self, mmc):
        """Args:
            mmc: a ``pymmcore_plus.CMMCorePlus`` instance.
        """
        self.mmc = mmc
        self.name = mmc.getSLMDevice()
        self.height = mmc.getSLMHeight(self.name)
        self.width = mmc.getSLMWidth(self.name)
        self.bppx = mmc.getSLMBytesPerPixel(self.name)
        self.exposure_time = mmc.getSLMExposure(self.name)

    def all_on(self):
        """Turn on every DMD pixel for a long time."""
        self.mmc.setSLMExposure(self.name, 200000)
        self.mmc.setProperty(self.name, "OverlapMode", "On")
        self.mmc.setSLMPixelsTo(self.name, 1)
        self.mmc.displaySLMImage(self.name)

    def all_off(self):
        """Turn off every DMD pixel."""
        self.mmc.setSLMExposure(self.name, 1)
        self.mmc.setProperty(self.name, "OverlapMode", "Off")
        self.mmc.setSLMPixelsTo(self.name, 0)
        self.mmc.displaySLMImage(self.name)

    def upload_mask(self, mask):
        """Upload a binary array of DMD shape (height, width) to the device."""
        arr = np.ascontiguousarray(np.asarray(mask), dtype=np.uint8)
        if arr.shape != (self.height, self.width):
            raise ValueError(
                f"mask shape {arr.shape} doesn't match DMD shape "
                f"({self.height}, {self.width})"
            )
        self.mmc.setSLMImage(self.name, arr)

    def checker_board(self):
        """Display a checkerboard pattern for a long time (useful for alignment)."""
        checker_board = np.kron([[1, 0] * 20, [0, 1] * 20] * 15, np.ones((20, 20)))
        self.mmc.setSLMExposure(self.name, 200000)
        self.mmc.setProperty(self.name, "OverlapMode", "On")
        self.upload_mask(checker_board)
        self.mmc.displaySLMImage(self.name)

    def display_mask(self, mask):
        """Upload and display a mask on the DMD for the currently set exposure."""
        self.upload_mask(mask)
        self.mmc.setSLMExposure(self.name, 200000)
        self.mmc.setProperty(self.name, "OverlapMode", "On")
        self.mmc.displaySLMImage(self.name)

    def set_exposure(self, exposure_time):
        """Set how long a mask is displayed on the DMD (microseconds)."""
        self.exposure_time = exposure_time
        self.mmc.setSLMExposure(self.name, exposure_time)

    def snap(self):
        """Snap a single image with the current core exposure."""
        self.mmc.snap()
        return self.mmc.getImage()

    def capture_and_stim_mask(self, mask, dmd_exposure_time, camera_exposure_time, delay=0):
        """Display a mask on the DMD and capture an image of the stimulation."""
        self.mmc.setSLMExposure(self.name, dmd_exposure_time)
        self.mmc.setExposure(camera_exposure_time)
        self.upload_mask(mask)
        self.mmc.setProperty(self.name, "OverlapMode", "On")
        self.mmc.displaySLMImage(self.name)
        time.sleep(delay)
        return self.snap()
