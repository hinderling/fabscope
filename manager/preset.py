import time

class preset:
    def __init__(self,core,settings = []):
        '''Allows to store and apply multiple device properties at once.
        A dmd calibration affine transformation matrix can be created and stored.
        '''
        #list of commands in the form of
        #[['device_name', 'property_name', 'property_value'],
        #     ['device_name_2', 'property_name_2', 'property_value_2']]
        self.settings = settings
        self.affine = None #as dmd calibrations are done per channel, it makes sense to store them with a preset
        self.core = core
        self.camera_exposure_time = None
        self.dmd_exposure_time = None
        self.name = None
        
    def set_power(self, power):
        '''change the power of the laser/led. put property to change in last line of prests'''
        self.settings[-1][2] = power
        
    def apply_no_retry(self, verbous = False):
        '''Apply the settings by setting the respective device properties in micro manager. 
        Waits until all the devices are not busy anymore.
        Args: 
            verbous: print out all changes applied
        '''
        for setting in self.settings:
            #will result in such a command:
            #core.set_property('Core', 'AutoShutter', 0)
            if verbous:
                print(str(setting[0])+": Set " + str(setting[1]) + " to " + str(setting[2]))
            self.core.set_property(setting[0], setting[1], setting[2])
        for setting in self.settings:
            #wait until none of the devices changed are busy anymore
            self.core.wait_for_device(setting[0])


    def apply(self, verbous = False, max_retries = 10, i = 0):
        '''See apply_no_retry, but retries max_retries-times if an error is caught (e.g. Wheel-C cannot turn)
        '''
        if i > max_retries:
            #Tried to many times. Break and throw error.
            print('Cannot apply setting. Break.')
            raise RuntimeError
        try:
            for setting in self.settings:
                #will result in such a command:
                #core.set_property('Core', 'AutoShutter', 0)
                if verbous:
                    print(str(setting[0])+": Set " + str(setting[1]) + " to " + str(setting[2]))
                self.core.set_property(setting[0], setting[1], setting[2])
            for setting in self.settings:
                #wait until none of the devices changed are busy anymore
                self.core.wait_for_device(setting[0])
             
            if self.camera_exposure_time != None:
                self.core.set_exposure(self.camera_exposure_time)
            
            
        except KeyboardInterrupt:
            print('Caught keyboard interrupt. Quitting')
            raise KeyboardInterrupt
        except:
            #Caught an error. Try again.
            print(f'Error when applying setting. Retry nb. {i}.')
            time.sleep(1)
            self.apply(verbous = verbous, max_retries = max_retries, i = i+1)

    def test_apply(self):
        '''Debug mode, doesn't upload any settings to micro manager.
        '''
        for setting in self.settings:
            print(str(setting[0])+": Set \"" + str(setting[1]) + "\" to " + str(setting[2]))

    def calibrate_dmd(self, dmd, dmd_exposure_time, camera_exposure_time):
        '''Apply the preset, then run the calibration routine. Stores the resulting affine in self.affine.
        '''
        self.apply() 
        affine = dmd.calibrate()
        self.affine = affine

