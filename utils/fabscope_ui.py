import numpy as np
import napari
from magicgui import magicgui
from napari.qt import thread_worker
import math
import time
from queue import Queue
from dataclasses import dataclass
from typing import List
from threading import Lock
from magicgui.widgets import Container


@dataclass
class StagePosition:
    x: float
    y: float
    pfs_offset: float


class FabscopeUI:
    def __init__(self, core, dmd, channels, sleep_time=0.1, clim=(0, 255)):
        self.core = core
        self.dmd = dmd
        self.channels = channels
        self.sleep_time = sleep_time
        self.clim = clim

        self.zmq_lock = Lock()
        self.acq_running = False
        self.img_queue = Queue()
        self.position_list: List[StagePosition] = []
        self.threshold = 100

        # Initialize viewer and data
        self.checker_board = np.kron([[1, 0] * 20, [0, 1] * 20] * 20, np.ones((20, 20)))
        self.startup_screen = self.checker_board * 100
        self.data = self.startup_screen
        self.viewer = None
        self.layers = None

    def acquire_data(self):
        """Acquire data from microscope"""
        self.zmq_lock.acquire()
        remaining_image_count = self.core.get_remaining_image_count()
        if remaining_image_count < 1:
            self.zmq_lock.release()
            print("Warning: No image in uManager queue.")
            time.sleep(0.5)
            return

        try:
            array = self.core.get_last_image()
        except Exception as e:
            self.zmq_lock.release()
            print("ERROR: No image in uManager queue.")
            time.sleep(0.5)
            return

        self.zmq_lock.release()
        img_width = int(math.sqrt(len(array)))
        img = np.reshape(array, (img_width, img_width))
        img = img[::]
        self.img_queue.put(img)

    def display_napari(self, image):
        """Update napari display with new image"""
        self.layers[0].data = image
        self.img_queue.task_done()

    @thread_worker
    def append_img(self):
        """Worker thread for acquiring images"""
        print("Worker started: append_img")
        while self.acq_running:
            self.acquire_data()
            time.sleep(self.sleep_time)

    @thread_worker
    def yield_img(self):
        """Worker thread for displaying images"""
        print("Worker started: yield_img")
        while self.acq_running:
            while self.img_queue.qsize() > 0:
                yield self.img_queue.get(block=False)
            time.sleep(self.sleep_time)

        while self.img_queue.qsize() > 0:
            yield self.img_queue.get(block=False)
        print("acquisition done")

    def start_acq(self):
        print("starting threads...")
        if not self.acq_running:
            self.acq_running = True
            with self.zmq_lock:
                self.core.start_continuous_sequence_acquisition(0)
            worker1 = self.append_img()
            worker2 = self.yield_img()

            # Connect them here to the actual instance methods
            worker2.yielded.connect(self.display_napari)

            # Now start them
            worker1.start()
            worker2.start()
        else:
            print("acquisition already running!")

    def stop_acq(self):
        """Stop acquisition"""
        print("stopping threads")
        self.zmq_lock.acquire()
        self.core.stop_sequence_acquisition()
        self.zmq_lock.release()
        self.acq_running = False

    def store_pos(self):
        """Store current stage position"""
        restart = False
        if self.acq_running:
            self.stop_acq()
            restart = True

        self.zmq_lock.acquire()
        point = self.core.get_xy_stage_position()
        pfs_offset = self.core.get_auto_focus_offset()
        x = point.get_x()
        y = point.get_y()
        self.zmq_lock.release()

        self.position_list.append(StagePosition(x, y, pfs_offset))

        if restart:
            self.start_acq()

    def set_dmd_checkerboard(self):
        """Set DMD to checkerboard pattern"""
        self.stop_acq()
        self.zmq_lock.acquire()
        self.dmd.checker_board()
        self.zmq_lock.release()
        self.start_acq()

    def create_channel_widget(self, channel):
        """Create widget for a single channel"""

        @magicgui(
            call_button="SELECT",
            auto_call=False,
            label={"widget_type": "Label", "name": "label", "label": channel.name},
            power={"widget_type": "SpinBox", "name": "power", "label": "%", "min": 0, "max": 100},
            exposure={"widget_type": "SpinBox", "name": "ms", "label": "ms", "min": 1, "max": 10000},
            layout="horizontal",
        )
        def channel_widget(label, power: int = channel.settings[-1][2], exposure=channel.camera_exposure_time):
            self.stop_acq()
            channel.camera_exposure_time = exposure
            channel.set_power(power)
            self.zmq_lock.acquire()
            channel.apply()
            self.dmd.all_on()
            self.zmq_lock.release()
            self.start_acq()

        return channel_widget

    def initialize_viewer(self):
        """Initialize the napari viewer with all widgets"""
        try:
            if self.viewer:
                self.viewer.close()
        except Exception as e:
            print("viewer already closed or never opened")

        self.viewer = napari.Viewer(ndisplay=2)

        # Add initial image layer
        self.layers = [
            self.viewer.add_image(
                self.data,
                name="zero",
                colormap="gray",
                interpolation="nearest",
                blending="additive",
                rendering="attenuated_mip",
                contrast_limits=self.clim,
            )
        ]

        # Add control widgets
        self.viewer.window.add_dock_widget(magicgui(self.start_acq, call_button="Start"), area="left")
        self.viewer.window.add_dock_widget(magicgui(self.stop_acq, call_button="Stop"), area="left")

        # Create channel widgets
        channels_widgets = [self.create_channel_widget(channel) for channel in self.channels]
        channels_container = Container(widgets=channels_widgets)
        self.viewer.window.add_dock_widget(channels_container, area="left")

        # Add other control widgets
        self.viewer.window.add_dock_widget(
            magicgui(self.set_dmd_checkerboard, call_button="DMD Checkerboard pattern"), area="left"
        )
        self.viewer.window.add_dock_widget(magicgui(self.store_pos, call_button="Store position"), area="left")

        self.viewer.text_overlay.visible = True
        return self.viewer
