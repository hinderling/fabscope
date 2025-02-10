#from cv2 import cv2 #fixes a pylint error
import cv2
import numpy as np
import matplotlib.pyplot as plt
import time
import scipy
from .acquisition import acq

def coordinates_to_lightmap(xy, mask):
    '''Takes a list of coordinates [(y,x),(y,x),...] and draws an ellipse on a mask for every point. '''

    #Elipse properties
    axesLength = (3, 3) 
    angle = 0
    startAngle = 0
    endAngle = 360
    color = (1) 
    thickness = -1
    light_mask = np.zeros_like(mask)        
    center_coordinates = (int(xy[1]),int(xy[0]))
    light_mask = cv2.ellipse(light_mask, center_coordinates, axesLength, angle, startAngle, endAngle, color, thickness) 

    return light_mask


class dmd():
    '''all methods that relate to the control of the DMD
        img is in camera space (2048px*2048px / 1024px*1024px / ... )
        mask is in dmd space (600px*800px)

    '''
    def __init__(self, core):
        '''Args:
            core: MMCore object from bridge.get_core()
        '''
        #Load all dmd properties from micro-manager
        self.core = core
        self.name = self.core.get_slm_device()
        self.height = self.core.get_slm_height(self.name)
        self.width = self.core.get_slm_width(self.name)
        self.bppx = self.core.get_slm_bytes_per_pixel(self.name)
        self.exposure_time = self.core.get_slm_exposure(self.name)

    def transform_img(self, img,affine):
        '''Applies transformation matrix on image in camera space. Returns mask in dmd space.
        Args:
            img: image in camera space
            affine: affine transformation matrix
        '''
        img_transformed = cv2.warpAffine(img, affine, (self.width, self.height))
        return img_transformed


    def all_on(self):
        '''turn on projector all pixels for a long time
        '''
        self.core.set_slm_exposure(self.name, 200000)
        self.core.set_property(self.name, 'OverlapMode', 'On')
        self.core.set_slm_pixels_to(self.name, 1)
        self.core.display_slm_image(self.name)   

    def all_off(self):
        '''turn off pixels
        '''
        self.core.set_slm_exposure(self.name, 1)
        self.core.set_property(self.name, 'OverlapMode', 'Off')
        self.core.set_slm_pixels_to(self.name, 0)
        self.core.display_slm_image(self.name) 

    def upload_mask(self, mask):
        '''Converts np.array in shape of dmd into string, and uploades it to the dmd.
        Args:
            mask: binary array in shape of dmd
        '''
        flatarray = mask.ravel().tolist()
        self.core.set_slm_image(self.name, np.array(flatarray).astype(np.uint8))

    def checker_board(self, pixels = 20):
        '''display a checkerboard pattern for a long time
        '''
        #build checkerboard
        checker_board = np.kron([[1, 0] * 20, [0, 1] * 20] * 15, np.ones((20, 20))) #https://stackoverflow.com/a/37440123
        self.core.set_slm_exposure(self.name, 200000)
        self.core.set_property(self.name, 'OverlapMode', 'On')
        self.upload_mask(checker_board)
        self.core.display_slm_image(self.name)   
    
    def display_mask(self,mask):
        '''Display the mask loaded on the dmd. Displays it for the set exposure.
        '''
        self.upload_mask(mask)
        self.core.set_slm_exposure(self.name, 200000)
        self.core.set_property(self.name, 'OverlapMode', 'On')
        self.core.display_slm_image(self.name)

    def set_exposure(self, exposure_time):
        '''Set the time a mask is displayed on the dmd.
        '''
        #todo: check for max allowed exposure time
        self.exposure_time = exposure_time
        self.core.set_slm_exposure(self.name,exposure_time)

    def capture_and_stim_mask(self, mask, dmd_exposure_time,camera_exposure_time,delay=0):
        '''Stimulate using dmd and take an image.
        '''    
        #stimulate using dmd and take an image of the stim
        self.core.set_slm_exposure(self.name, dmd_exposure_time)#set exposure dmd
        self.core.set_exposure(camera_exposure_time)#set exposure camera
        self.upload_mask(mask) #upload mask to dmd        
        self.display_mask()#display on dmd
        time.sleep(delay)#time between stimulation begin and capture begin
        self.core.snap_image()#take picture
        tagged_img = self.core.get_tagged_image()
        img_height = tagged_img.tags['Height']
        img_width = tagged_img.tags['Width']
        img = tagged_img.pix.reshape(img_height, img_width)
        return img

    def capture_and_stim_full_on(self, dmd_exposure_time,camera_exposure_time,delay=0):
        '''Stimulate using dmd (all pixels on) and take an image.
        '''    
        #stimulate using dmd and take an image of the stim
        self.core.set_slm_exposure(self.name, dmd_exposure_time)#set exposure dmd
        self.core.set_exposure(camera_exposure_time)#set exposure camera
        self.core.set_slm_pixels_to(self.name, 1)
        self.core.display_slm_image(self.name)
        time.sleep(delay)#time between stimulation begin and capture begin
        self.core.snap_image()#take picture
        tagged_img = self.core.get_tagged_image()
        img_height = tagged_img.tags['Height']
        img_width = tagged_img.tags['Width']
        img = tagged_img.pix.reshape(img_height, img_width)
        return img


    def capture_and_stim_img(self, img, affine, dmd_exposure_time,camera_exposure_time,delay=0):
        '''Transform img using affine matrix, then stimulate using dmd and take an image.
        ''' 
        #mask = scipy.ndimage.affine_transform(img, affine, output_shape=(self.width, self.height))
        mask = cv2.warpAffine(img, affine, (self.width, self.height))
        img_captured = self.capture_and_stim_mask(mask, dmd_exposure_time,camera_exposure_time, delay)
        return img_captured


    def transform_and_disp(self, img, affine):
        '''Transform img using affine matrix, then uplaod and display it.
        ''' 
        mask = cv2.warpAffine(img, affine, (self.width, self.height))
        #self.core.set_slm_exposure(self.name, 20000)#set exposure dmd    
        self.display_mask(mask)#display on dmd

    def calibrate(self, verbous=False, blur = 10, circle_size = 10, marker_style = 'x'):
        '''Calibrate the dmd and camera coordinate systems. 
        '''

        calibration_points_DMD = [(180,180),(700,130),(180,550)] #width x height 800x600 X/Y ordering
        calibration_points_camera = []


        mask = np.zeros((self.height, self.width))
        #background = self.capture_and_stim_mask(mask, dmd_exposure_time, camera_exposure_time)
        #background = cv2.blur(background,(blur,blur), cv2.BORDER_REFLECT) #TODO change border padding
        stim_imgs = []

        for xy in calibration_points_DMD:
            #create mask
            mask = np.zeros((self.height, self.width))
            #mask[xy[1],xy[0]] = 1

            #mask = coordinates_to_lightmap(xy, mask)
            mask = cv2.circle(mask, (xy[0],xy[1]), circle_size, 1, -1)

            #display mask
            self.display_mask(mask)#, dmd_exposure_time, camera_exposure_time)
            #self.core.snap_image()#take picture
            img = acq(self.core)
            img = cv2.blur(img,(blur,blur))  

            #extract pixel location
            max_pixel = np.unravel_index(np.argmax(img, axis=None), img.shape)
            
            # yx -> xy from numpy
            max_pixel =[max_pixel[1],max_pixel[0]]
            calibration_points_camera.append(max_pixel)#store point

            if verbous:
                stim_imgs.append(img)
        
        camera_width = img.shape[0]
        camera_height = img.shape[1]

        calibration_points_camera = np.array(calibration_points_camera)
        calibration_points_DMD = np.array(calibration_points_DMD)

        calibration_points_camera = np.float32(calibration_points_camera[:, np.newaxis, :])
        calibration_points_DMD = np.float32(calibration_points_DMD[:, np.newaxis, :])

        #from the two list of points calculate affine translation matrix
        warp_mat = cv2.getAffineTransform(calibration_points_camera,calibration_points_DMD) #source, destination
        #warp_mat = cv2.invertAffineTransform(warp_mat)
        
        # if verbous, print five images:
        #[background, point1, point2, point3, calibration_test]
        if verbous:
            fig, axs = plt.subplots(figsize=(20, 5), ncols=4, dpi = 250) 
        #axs[0].yaxis.tick_left()
           # axs[0].xaxis.tick_top()  
           # axs[0].yaxis.set_ticks(np.arange(0, camera_height, 256))
           # axs[0].xaxis.set_ticks(np.arange(0, camera_width, 256))
           # axs[0].imshow(background, cmap='gray') #show the background image

            #show the images with single pixel on
            for (i,point_detected) in enumerate(calibration_points_camera):
                #axs[i+1].set_ylim(axs[i+1].get_ylim()[::-1])
                axs[i].xaxis.tick_top()    # and move the X-Axis     
                axs[i].xaxis.set_ticks(np.arange(0, camera_width, 256)) # set y-ticks
                axs[i].yaxis.set_ticks(np.arange(0, camera_height, 256)) # set y-ticks
                axs[i].yaxis.tick_left() 
                axs[i].imshow(stim_imgs[i],cmap='gray')
                axs[i].scatter(point_detected[0][0],point_detected[0][1],marker = marker_style, facecolors='none', edgecolors='red')
            
            #test the calibration on three new points
            max_res = 2048
            calibration_points_camera = [[200,500],[200,1400],[1400,300],[1500,500],[1800,1000],[1750,1650]]
            #scale to binning
            for i, xy in enumerate(calibration_points_camera): 
                calibration_points_camera[i]=[int(xy[0]/max_res*camera_width),int(xy[1]/max_res*camera_height)]

            #create image in camera space[]
            mask = np.zeros((camera_height, camera_width)) #TODO; grab from core
            for xy in calibration_points_camera: 
                mask = cv2.circle(mask, (xy[0],xy[1]), circle_size, 1, -1)
            
            #transform to dmd space
            mask_warped = self.transform_img(mask, warp_mat)
            #display in dmd space and capture dmd in cameraspace
            self.display_mask(mask_warped)#, dmd_exposure_time, camera_exposure_time)
            img = acq(self.core)
            
            #compare expected and result
            plt.axis([0, camera_height, 0, camera_width])   
            ax=plt.gca()                            # get the axis
            axs[3].set_ylim(ax.get_ylim()[::-1])        # invert the axis
            axs[3].xaxis.tick_top()                     # and move the X-Axis      
            axs[3].yaxis.set_ticks(np.arange(0, camera_height, 256)) # set y-ticks
            axs[3].yaxis.tick_left()   
            axs[3].imshow(img, cmap='gray',origin='upper')
            for xy in calibration_points_camera:
                axs[3].scatter(xy[0],xy[1],marker = marker_style, facecolors='none', edgecolors='green')
           #plt.show()
        return warp_mat





