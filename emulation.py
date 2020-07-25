import sys # for simple command line parsing
import numpy as np # for image generation
from scipy import ndimage # for image processing
import threading # for non-blocking execution
import time # for waiting to generate next image
import cv2 # for grabbing images from video
import argparse # for getting arguments when calling script


# setup arguments for command line
parser = argparse.ArgumentParser()
parser.add_argument('-e', '--emulate', help='Generates artificial frames instead of using the pi camera', action='store_true')
parser.add_argument('-v', '--video', help='Optional path to a video file to use its frames instead of the pi camera', default='')
# evaluate arguments
args = parser.parse_args()

emulated = args.emulate


class Emulator:
    '''
    Base fake picamera.PiCamera class to emulate camera

    Note: Does not support original features
    '''
    def __init__(self):
        self.resolution = (1280, 720)
        self.normContrast = 1. # 0...2
        self.fakeFPS = 15
        self.exposure_speed = 1e6/self.fakeFPS
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
        raise NotImplementedError('Generation of new fake image must be implemented here')


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


class ArtificialPiCamera(Emulator):
    '''
    Generates fake images based on algorithm
    '''
    def __init__(self):
        super().__init__()
        self.mirrorRatio = 0.1 # radius as ratio to image width
        self.paperSize = 3*self.mirrorRatio
        self.holeRatio = 0.005 # radius as ratio to image with
        self.holePeriod = 3. # generate every x seconds a new hole
        self.holeTime = time.time()+10. # start hole generation in y seconds
        self.makeCoords()
        self.baseImage = self.generateBaseImage()
        np.random.seed(0)
    

    def makeCoords(self):
        '''
        Generates relative image coordinates over width 
        with origin in center and square pixel ratio
        '''
        # coordinates
        x = np.linspace(-1., 1., self.width)
        ratio = self.height/self.width
        y = np.linspace(-ratio, ratio, self.height)
        # grid
        self.relX, self.relY = np.meshgrid(x, y)
    

    def generateBaseImage(self):
        '''
        :returns: normed grayscale image matrix for the static content
        '''
        dist = np.sqrt(self.relX**2+self.relY**2)
        # masks
        paperMask = np.logical_and(np.abs(self.relY) < self.paperSize, np.abs(self.relX) < self.paperSize)
        mirrorMask = dist <= self.mirrorRatio
        # generate normalized grayscale frame
        img = 0.4-0.4*dist**2 # background with vignette
        img[paperMask] = 0.8
        img[mirrorMask] = 0.2
        return img
    

    def makeHole(self, img):
        '''
        Makes a random hole on the image

        :param img: normed grayscale image matrix
        '''
        # generate random coordinates for hole on paper
        rndX, rndY = np.random.normal(0., self.paperSize/2.5, (2,))
        dist = np.sqrt((self.relX+rndX)**2+(self.relY+rndY)**2)
        # mask
        holeMask = dist <= self.holeRatio
        # draw hole on image
        img[holeMask] = 0.1
    

    def generateImage(self):
        '''
        :returns: fake image of paper and mirror
        '''
        img = self.baseImage
        # make hole
        now = time.time()
        if now >= self.holeTime:
            self.holeTime = now+self.holePeriod
            self.makeHole(img)
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
        img = (img-0.5)*self.normContrast+0.5

        # convert to image tensor
        img *= 255 # denormalize
        img = np.clip(img, 0, 255) # clip
        img = img.astype(np.uint8) # to ints
        img = np.repeat(img[..., None], 3, axis=2) # copy values to all channels

        return img


class VideoPiCamera(Emulator):
    '''
    Streams fake images from video
    '''
    def __init__(self):
        super().__init__()
        self.video = cv2.VideoCapture(args.video)
    

    def generateImage(self):
        '''
        :returns: video frame image
        '''
        success, img = self.video.read()
        if not success:
            self.video.set(1, 0) # set playback to start
            success, img = self.video.read()
            if not success:
                raise Exception('Cannot read frame from video')
        # convert to yuv
        img = cv2.cvtColor(img, cv2.COLOR_BGR2YUV)
        return img


class PiCamera(VideoPiCamera if args.video else ArtificialPiCamera):
    pass


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