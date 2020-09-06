import io # for temporary buffer to simulate file for image conversion
import emulation
if emulation.emulated:
    from emulation import PiYUVAnalysis
else:
    from picamera.array import PiYUVAnalysis # to stream frames to numpy arrays
import numpy as np # for array math
from scipy import ndimage # for image processing
from PIL import Image # to convert array to image
import time # for performance measurement
from enum import Enum # for states
from collections import deque # for fast ring buffer
import logging # for more advanced prints


log = logging.getLogger(f'spotter_{__name__}')


class State(Enum):
    PREVIEW = 0
    START = 1
    COLLECT = 2
    DETECT = 3


class FrameAnalysis(PiYUVAnalysis):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # general
        self.frameCnt = 0
        self.streamDims = self.camera.resolution # width, height in pixels of current background
        self.streamImage = bytes()
        self.lowPreviewRes = True # cutting preview stream image resolution to save time
        self.procTime = 0.
        self.showDiff = False # show amplified diff instead of the camera frames
        self.state = State.PREVIEW # do not average and detect changes yet

        # mirror detection related
        self.mirrorTolerance = 10 # tolerance to find mirror pixels from center luminance
        self.mirrorPickSize = 20 # center size (width and height) in pixels to pick luminance
        self.paperScale = 3. # overall paper is that much larger than mirror
        self.mirrorScale = (1., 1.) # scale corrections of mirror bounds
        self.mirrorTranslate = (0, 0) # position corrections of mirror bounds
        self.pickBounds = None
        self.cropBounds = None
        self.mirrorBounds = None
        self.keepMirror = False

        # slot related
        self.maxSlots = 3 # number of slots
        self.nSlotFrames = 10 # number of frames to average

        # hole detection related
        self.thresh = 5 # hole detection sensitivity
        self.maxHoleSize = 20 # maximum expected hole size in width or height pixels

        self.reset()
    

    def reset(self):
        '''
        Resets analysis results
        '''
        log.debug('Resetting analysis results and marks')
        self.slot = Slot()
        self.slots = deque(maxlen=self.maxSlots)
        self.analysis = None # last analysis
        self.detected = []
        self.marks = []
    

    def analyse(self, img):
        '''
        Event fired for each new image coming from camera recording
        '''
        startTime = time.perf_counter()
        self.frameCnt += 1

        # convert camera image to grayscale frame matrix
        frame = img[:, :, 0] # get luminance channel of YUV

        # make square
        halfH, halfW = frame.shape[0]//2, frame.shape[1]//2
        frame = frame[:, halfW-halfH:halfW+halfH]

        if self.state == State.PREVIEW:
            # in preview state, output uncropped frame
            self.streamDims = frame.shape[::-1]
            prev = frame[::2, ::2] if self.lowPreviewRes else frame
            self.makeStreamImage(prev)
        elif self.state == State.START:
            self.reset() # reset analysis results and marks
            
            # reset if wanted
            if not self.keepMirror or self.cropBounds is None:
                # detect mirror
                log.info('Detecting mirror')
                self.pickBounds = self.findMirror(frame)
                log.debug(f'Mirror bounds in camera frame: {self.pickBounds}')

                # check if picked size is realistic
                if self.pickBounds.width < 0.05*frame.shape[1] or self.pickBounds.height < 0.05*frame.shape[0] or self.pickBounds.width > 0.8*frame.shape[1] or self.pickBounds.height > 0.8*frame.shape[0]:
                    log.error(f'Could not detect mirror correctly')
                    self.pickBounds = self.squareBounds(frame, 0.25) # made up
                
                log.debug('Resetting mirror transformation')
                self.mirrorScale = (1., 1.)
                self.mirrorTranslate = (0, 0)
                self.cropBounds = self.pickBounds.scaled(self.paperScale).clamped(frame)
                self.mirrorBounds = self.pickBounds.relativeTo(self.cropBounds)

            # proceed with next state
            log.info('Collecting frames')
            self.state = State.COLLECT
        else:
            # COLLECT or DETECT state
            # crop frame
            frame = self.cropBounds.crop(frame)
            frame = frame.astype(np.int16, copy=False)
            
            # add frame to current slot
            log.debug(f'Adding frame {self.slot.length+1}/{self.nSlotFrames} to slot')
            self.slot.add(frame)
            if self.slot.length >= self.nSlotFrames:
                # add current slot to slots
                log.debug('Cycling slot')
                if self.cycleSlots(self.slot):
                    # all slots filles and ready for analysis
                    self.streamDims = frame.shape[::-1]
                    self.state = State.DETECT
                    
                    # analyse for differences between newest and oldest slot
                    log.debug('Comparing newest to oldest slot')
                    self.analysis = Analysis(self.slots[0], self.slots[-1], self.thresh, self.maxHoleSize)
                    display = np.copy(np.abs(self.analysis.diff*30) if self.showDiff else self.slots[0].mean)
                    if self.analysis.valid:
                        log.info(f'Valid change detected at {self.analysis.rect.center}')
                        # add detection to mark consideration
                        self.detected.append(self.analysis.rect.center)
                    else:
                        # add mark of detection
                        if self.detected:
                            log.debug('Adding change detection mark')
                            self.marks.append(self.detected[0])
                        self.detected = []
                    
                    # debug display
                    display[self.analysis.mask] = 255
                    self.makeStreamImage(display)
        
        self.procTime = time.perf_counter()-startTime
    
    
    def findMirror(self, frame):
        '''
        Tries to find the borders of the black center circle

        :param frame: (h, w) array (int16 grayscale matrix)
        :returns: Rect object of mirror bounds in frame
        '''
        # pick center luminance
        iRow = int(frame.shape[0]/2) # y
        iCol = int(frame.shape[1]/2) # x
        pad = self.mirrorPickSize//2 # half with/height
        pickArea = frame[iRow-pad:iRow+pad, iCol-pad:iCol+pad]

        # mask luminance in frame for picked value
        matchMask = np.logical_and(
            frame > pickArea.min()-self.mirrorTolerance, 
            frame < pickArea.max()+self.mirrorTolerance)

        # prepare flooding
        toFlood = np.full(frame.shape, False)
        toFlood[iRow, iCol] = True
        # get center isle
        mirrorMask = ndimage.binary_propagation(toFlood, mask=matchMask)

        # get dimensions of isle
        iMask = np.argwhere(mirrorMask)
        xMin, xMax = np.min(iMask[:, 1]), np.max(iMask[:, 1])
        yMin, yMax = np.min(iMask[:, 0]), np.max(iMask[:, 0])
        
        return Rect(xMin, xMax, yMin, yMax)
    

    def squareBounds(self, frame, heightRatio):
        '''
        Makes a square bound in center based on relative height of a frame
        '''
        frameRect = Rect(0, frame.shape[1], 0, frame.shape[0])
        radius = int(heightRatio*frameRect.height/2)
        mid = frameRect.center
        return Rect(mid[0]-radius, mid[0]+radius, mid[1]-radius, mid[1]+radius)
    

    @property
    def corrMirrorBounds(self):
        '''
        Corrected mirror bounds in cropped frame
        '''
        if self.mirrorBounds:
            return self.mirrorBounds.scaled(self.mirrorScale).moved(*self.mirrorTranslate)
        else:
            return None
    

    def cycleSlots(self, slot):
        '''
        Pushes new slot into buffer

        :param slot: Slot object
        :returns: True if all slots filled, False otherwise
        '''
        self.slots.appendleft(slot) # insert current slot
        self.slot = Slot() # reset current slot
        # check if full
        if len(self.slots) == self.slots.maxlen:
            return True
        else:
            return False
    

    def imgArrayToImgBytes(self, img, filetype='jpeg'):
        '''
        Converts an image array to image bytes

        :param img: (h, w, 3) or (h, w) array (uint8 grayscale or RGB image)
        :param filetype: image format string, e.g. "png", "gif", ... default "jpeg"
        :returns: image file bytes
        '''
        im = Image.fromarray(img) # create image object
        buffer = io.BytesIO() # make buffer to simulate file
        im.save(buffer, filetype) # write image to buffer
        return buffer.getvalue() # get buffer bytes
    

    def makeStreamImage(self, frame):
        '''
        Converts a grayscale frame to bytes of its image

        :param frame: (h, w) array (int16 grayscale matrix)
        '''
        img = frame.astype(np.uint8)
        try:
            self.streamImage = self.imgArrayToImgBytes(img)
        except SystemError:
            log.warning('Could not create stream image')
            log.info(f'Image cropping: {self.cropBounds}')


class Slot:
    '''
    Stores multiple frames in an array for averaging
    '''
    def __init__(self):
        self.frames = []
        self._mean = None
    

    def add(self, frame):
        '''
        Adds a frame to the slot

        :param frame: (h, w) array (int16 grayscale matrix)
        '''
        self.frames.append(frame)
    

    @property
    def length(self):
        '''
        :returns: current number of stored frames
        '''
        return len(self.frames)
    

    @property
    def mean(self):
        '''
        :returns: average value of each pixel over all frames
        '''
        if self._mean is None:
            self._mean = np.mean(self.frames, axis=0, dtype=np.int16)
        
        return self._mean


class Rect:
    '''
    Stores indices of matrix indices rect
    '''
    def __init__(self, xMin, xMax, yMin, yMax):
        self.left = xMin
        self.right = xMax
        self.top = yMin
        self.bottom = yMax
    

    def __str__(self):
        return f'Rect(left: {self.left}, right: {self.right}, top: {self.top}, bottom: {self.bottom})'
    

    def __hash__(self):
        return hash((self.left, self.right, self.top, self.bottom))
    

    def __eq__(self, other):
        return hash(self) == hash(other)
    

    @property
    def width(self):
        '''
        :returns: width between left and right indices
        '''
        return self.right-self.left
    
    
    @property
    def height(self):
        '''
        :returns: height between top and bottom indices
        '''
        return self.bottom-self.top
    

    @property
    def center(self):
        '''
        :returns: center position indices (x, y)
        '''
        return (int((self.left+self.right)/2), int((self.top+self.bottom)/2))
    

    def scaled(self, fac):
        '''
        Scales the rect from center pivot point

        :param fac: float factor to scale or 
            tuple for two scale factors
        :returns: new scaled rect
        '''
        midX, midY = self.center
        # check if scalar or dimensions
        if isinstance(fac, tuple):
            facX, facY = fac[0], fac[1]
        else:
            facX = facY = fac
        # scale
        left = int(facX*self.left-facX*midX)+midX
        right = int(facX*self.right-facX*midX)+midX
        top = int(facY*self.top-facY*midY)+midY
        bottom = int(facY*self.bottom-facY*midY)+midY
        return Rect(left, right, top, bottom)
    

    def moved(self, x, y):
        '''
        Translates rect by x and y

        :param x, y: integer numbers to move the rect by
        :returns: new moved Rect object
        '''
        left = self.left+x
        right = self.right+x
        top = self.top+y
        bottom = self.bottom+y
        return Rect(left, right, top, bottom)
    

    def clamped(self, frame):
        '''
        Limits rect to frame dimensions

        :param frame: (h, w) array (int16 grayscale matrix)
        :returns: new clamped Rect oject
        '''
        left = max(self.left, 0)
        right = min(self.right, frame.shape[1])
        top = max(self.top, 0)
        bottom = min(self.bottom, frame.shape[0])
        return Rect(left, right, top, bottom)
    

    def relativeTo(self, ref):
        '''
        Relative to other rect

        :param ref: other Rect object
        :returns: new relative Rect object
        '''
        return self.moved(-ref.left, -ref.top)
    

    def crop(self, frame):
        '''
        Crops a frame

        :param frame: (h, w) array (int16 grayscale matrix)
        :returns: cropped frame section
        '''
        return frame[self.top:self.bottom, self.left:self.right]


class Analysis:
    '''
    Analysis between slots
    '''
    def __init__(self, newSlot, oldSlot, thresh, maxSize=100):
        '''
        :param newSlot/oldSlot: Slots objects
        :param thresh: threshold (0...255) to detect changes between averaged slot frames
        :param maxSize: maximum width/height of difference detection area in pixel
        '''
        self.thresh = thresh
        self.maxSize = maxSize

        newFrame = newSlot.mean
        oldFrame = oldSlot.mean

        diff = newFrame-oldFrame
        self.analyzeDiff(diff)

        # check for too much movement and try to solve by tracking
        if self.result == 'too much change':
            # describe feature matrix bounds
            dims = oldSlot.mean.shape
            size = 30 # feature width and height
            pos = (dims[1]//2, dims[0]//2-size) # feature center position
            featureBounds = Rect(pos[0]-size//2, pos[0]+size//2, pos[1]-size//2, pos[1]+size//2)
            
            # track (camera pitch vibrations in the first place)
            searchV = 15 # +/- search range in vertical direction
            searchH = 5 # +/- search range in horizontal direction
            log.debug('Tracking movement')
            matchBounds = self.track(newFrame, oldFrame, featureBounds, (searchH, searchV)) # track
            shift = (matchBounds.center[0]-featureBounds.center[0], matchBounds.center[1]-featureBounds.center[1])
            log.info(f'Movement between slots: {shift}')

            # correct by moving old in direction of tracking
            log.debug('Correcting and analyzing again')
            oldRolled = np.roll(oldFrame, shift[::-1], (0, 1))
            diff = np.abs(newFrame-oldRolled) # compare old with new
            xBorder, yBorder = abs(shift[0]), abs(shift[1])
            # zero write rolled areas
            diff[:yBorder, :] = 0 # top border
            diff[:, :xBorder] = 0 # left border
            diff[diff.shape[0]-yBorder:, :] = 0 # bottom border
            diff[:, diff.shape[1]-xBorder:] = 0 # right border

            self.analyzeDiff(diff)
    

    def analyzeDiff(self, diff):
        '''
        Analyzes the difference between 2 frames
        '''
        self.valid = False
        self.result = ''

        self.diff = ndimage.gaussian_filter(diff, 2) # to eliminate outliers
        self.mask = self.diff < -self.thresh
        iMask = np.argwhere(self.mask )
        nChange = len(iMask)
        if nChange > 0:
            log.debug(f'{nChange} pixels changed')
            # getting change bounds
            x = iMask[:, 1]
            xMin, xMax = np.min(x), np.max(x)
            y = iMask[:, 0]
            yMin, yMax = np.min(y), np.max(y)
            self.rect = Rect(xMin, xMax, yMin, yMax)
            log.debug(f'Change width: {self.rect.width}, height: {self.rect.height}')
            # check valid size
            if self.rect.width < self.maxSize and self.rect.height < self.maxSize:
                self.valid = True
                self.result = 'valid change'
            else:
                log.warning('Too many pixels changed')
                self.result = 'too much change'
        else:
            self.result = 'no change'
    

    def track(self, searchFrame, baseFrame, featureBounds, searchRadius=(10, 10)):
        '''
        Tries to find movement between frames

        :param searchFrame/baseFrame: (h, w) array (int16 grayscale matrix)
        :param featureBounds: Rect object describing the bounds in baseFrame 
            of the feature matrix to search in searchFrame
        :param searchRadius: +/- x and y ranges to search
        :returns: rect object of the estimated match of featureBounds in searchFrame
        '''
        # get crop from old frame
        base = featureBounds.crop(baseFrame)

        # search
        bestBounds = featureBounds
        bestMatch = 1e6
        xRange = range(-searchRadius[0], searchRadius[0])
        yRange = range(-searchRadius[1], searchRadius[1])
        for yMove in yRange:
            for xMove in xRange:
                # get crop of frame to search in
                movedBounds = featureBounds.moved(xMove, yMove)
                lookup = movedBounds.crop(searchFrame)
                # metric for match
                match = np.sum(np.abs(lookup-base))
                if match < bestMatch:
                    bestMatch = match
                    bestBounds = movedBounds
        
        return bestBounds
    

    def __repr__(self):
        return f'<Analysis({self.result})>'
    

    def __str__(self):
        return self.result
