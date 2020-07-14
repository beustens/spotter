import sys # for simple command line parsing
import numpy as np # for image generation
from scipy import ndimage # for image processing
import threading # for non-blocking execution
import time # for waiting to generate next image

emulated = True if '-e' in sys.argv else False


class PiCamera:
    '''
    Fake picamera.PiCamera class to emulate camera

    Note: Does not support original features
    '''
    def __init__(self):
        self.resolution = (1280, 720)
        self.normContrast = 1. # 0...2
        self.fakeFPS = 15
        self.exposure_speed = 1e6/self.fakeFPS
        self.mirrorRatio = 0.1 # radius as ratio to image width
        self.thread = None
        self.stopper = threading.Event()
    

    def __enter__(self):
        # to support with statement
        return self
    

    def __exit__(self, *args):
        # make sure to stop the image generating thread
        self.stop_recording()
        if self.thread:
            self.thread.join()
    

    @property
    def contrast(self):
        return int(100*(self.normContrast-1.))
    

    @contrast.setter
    def contrast(self, val):
        self.normContrast = val/100.+1.
    

    @property
    def width(self):
        return self.resolution[0]
    

    @property
    def height(self):
        return self.resolution[1]


    def start_recording(self, analysis, *args, **kwargs):
        '''
        Starts a thread with fake image generation

        :param analysis: fake picamera.array.PiYUVAnalysis object
        '''
        self.stopper.clear()
        # start non-blocking image generation
        self.thread = threading.Thread(target=self._imageGeneration, args=(analysis,))
        self.thread.start()
    

    def stop_recording(self):
        '''
        Stops fake image generation
        '''
        self.stopper.set()
    

    def generateImage(self):
        '''
        :returns: fake image of paper and mirror
        '''
        # coordinates
        x = np.linspace(-1., 1., self.width)
        ratio = self.height/self.width
        y = np.linspace(-ratio, ratio, self.height)
        # grid
        x, y = np.meshgrid(x, y)
        d = np.sqrt(x**2+y**2)
        # masks
        size = 3*self.mirrorRatio
        paper = np.logical_and(np.abs(y) < size, np.abs(x) < size)
        mirror = d <= self.mirrorRatio

        # generate normalized grayscale frame
        img = 0.4-0.4*d**2 # background with vignette
        img[paper] = 0.8
        img[mirror] = 0.2
        # low pass filter a bit
        img = ndimage.gaussian_filter(img, 3)
        # add rough noise
        noise = np.random.normal(scale=0.03, size=(self.height, self.width))
        noise = ndimage.gaussian_filter(noise, 5)
        img += noise
        # add fine noise
        noise = np.random.normal(scale=0.02, size=(self.height, self.width))
        img += noise

        # apply contrast
        img *= self.normContrast

        # convert to image tensor
        img *= 255 # denormalize
        img = np.clip(img, 0, 255) # clip
        img = img.astype(np.uint8) # to ints
        img = np.repeat(img[..., None], 3, axis=2) # copy values to all channels

        return img


    def _imageGeneration(self, analysis):
        '''
        Fake image generation
        '''
        period = 1./self.fakeFPS
        tNext = time.time()
        while True:
            img = self.generateImage() # generate image
            analysis.analyse(img) # let external analysis process image

            # check if we should stop generating images
            if self.stopper.is_set():
                break

            # wait until next image generation
            tNext += period
            time.sleep(max(0., tNext-time.time()))


class PiYUVAnalysis:
    '''
    Fake picamera.array.PiYUVAnalysis class to emulate camera frames

    Note: Works only with a fake PiCamera object
    '''
    def __init__(self, camera):
        self.camera = camera
    

    def __enter__(self):
        # to support with statement
        return self
    

    def __exit__(self, *args):
        pass