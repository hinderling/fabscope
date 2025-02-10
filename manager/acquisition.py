import numpy as np


def multi_channel_aqc(presets,dmd):
    ''' Apply all the settings to aqcuire a channel. Returns a stack of all aqcuired images. 
            Args:
                presets: A list of presets describing a channel, including exposure times for camera and dmd.
    '''
    stack = []
    for preset in presets:
        dmd_exposure_time = preset.dmd_exposure_time
        camera_exposure_time = preset.camera_exposure_time
        preset.apply()
        img_captured = dmd.capture_and_stim_full_on(dmd_exposure_time,camera_exposure_time,delay=0)
        presets[0].core.set_property("Spectra RIGHT","White_Level",0) #turn off the light source to avoid light leaks
        stack.append(img_captured)
    stack = np.array(stack,ndmin=3) #CYX format
    return stack #CYX format



def acq(core):
    core.snap_image()#take picture
    tagged_img = core.get_tagged_image()
    img_height = tagged_img.tags['Height']
    img_width = tagged_img.tags['Width']
    img = tagged_img.pix.reshape(img_height, img_width)
    return img


def acq_multi(presets,dmd):
    ''' Apply all the settings to aqcuire a channel. Returns a stack of all aqcuired images. 
            Args:
                presets: A list of presets describing a channel, including exposure times for camera and dmd.
    '''
    stack = []
    for preset in presets:
        camera_exposure_time = preset.camera_exposure_time
        preset.apply()
        dmd.all_on()
        img = acq(dmd.core)
        dmd.all_off()
        stack.append(img)
    stack = np.array(stack,ndmin=3) #CYX format
    return stack #CYX format


def acq_multi_dark(presets,dmd):
    ''' Take dark exposure with DMD all off for background subtractions.
        Apply all the settings to aqcuire a channel. Returns a stack of all aqcuired images. 
            Args:
                presets: A list of presets describing a channel, including exposure times for camera and dmd.
    '''
    stack = []
    for preset in presets:
        camera_exposure_time = preset.camera_exposure_time
        preset.apply()
        dmd.all_off()
        dmd.core.set_exposure(camera_exposure_time) #should be done in preset apply
        img = acq(dmd.core)
        dmd.all_off()
        stack.append(img)
    stack = np.array(stack,ndmin=3) #CYX format
    return stack #CYX format   


def acq_stim(img, preset, affine, dmd):
    ''' Apply all the settings to aqcuire a channel. Upload image on DMD. Capture and returns image.
    '''
    preset.apply()
    dmd.core.set_exposure(preset.camera_exposure_time) #should be done in preset apply
    dmd.transform_and_disp(img,affine)
    img = acq(dmd.core)
    dmd.all_off()
    return img


def acq_mask(mask, preset, dmd):
    ''' Apply all the settings to aqcuire a channel. Upload image on DMD. Capture and returns image.
    '''
    preset.apply()
    dmd.core.set_exposure(preset.camera_exposure_time) #should be done in preset apply
    dmd.display_mask(mask)
    img = acq(dmd.core)
    dmd.all_off()
    return img   