import queue
from trackpy.linking import Linker

class FOV:
    ''' Class that provides FOV abstraction. Every FOV has properties like:
        Args:
            core: the MMCore object that allows the FOV to intreact with the microscope hardware
            stage_position: the position of the X/Y microscope stage
            treatment: the experimental treatment associated with that FOV
            index: an index between [0,total number FOVs]
    '''
    def __init__(self, core, stage_position, treatment, index, search_range, memory,percentage):
        self.core = core
        self.pos = stage_position
        self.treatment = treatment
        self.index = index
        self.pipeline_thread = None
        self.tracks_queue = queue.Queue(maxsize=1) #queue where processed tracks are passed between threads
        self.light_mask_queue = queue.Queue(maxsize=1) #queue where light masks are passed between threads
        self.tracks = None
        self.light_mask = None
        self.last_frame_time = None
        self.percentage = percentage
        self.linker = Linker(search_range = search_range, memory= memory, adaptive_stop=3, adaptive_step=1)
        self.cells_to_stim = []
        self.cells_apo = []
        self.stim_quantile = []
        self.stim_time = []
        self.stim_size = []

    def get_tracks_from_thread(self):
        self.tracks = self.tracks_queue.get() #take the latest tracks and store locally

    def get_light_mask_from_thread(self):           
        self.light_mask = self.light_mask_queue.get() #take the latest tracks and store locally

    def move_stage_to_fov(self):
        xy_stage = self.core.get_xy_stage_device()
        focus_device = self.core.get_focus_device()
        self.core.set_xy_position(xy_stage,self.pos.x,self.pos.y)
        #self.core.set_position(self.pos.z) #TODO disable to keep PFS
        self.core.wait_for_device(xy_stage)
        self.core.wait_for_device(focus_device)
