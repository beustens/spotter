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
import logging # for more advanced prints


log = logging.getLogger(f'spotter_{__name__}')


class State(Enum):
    PREVIEW = 0
    START = 1
    COLLECT = 2
    DETECT = 3


class FrameAnalysis(PiYUVAnalysis):

    MAX_SLOTS = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # general
        self.frameCnt = 0
        self.streamImage = bytes()
        self.procTime = 0.
        self.showDiff = False # show amplified diff instead of the camera frames
        self.state = State.PREVIEW # do not average and detect changes yet

        # mirror detection related
        self.mirrorTolerance = 15 # tolerance to find mirror pixels from center luminance
        self.mirrorPickSize = 10 # center size (width and height) in pixels to pick luminance

        # paper crop related
        self.paperScale = 3. # overall paper is that much larger than mirror

        # slot related
        self.nSlotFrames = 5 # number of frames to average

        # hole detection related
        self.thresh = 5 # hole detection sensitivity
        self.maxHoleSize = 20 # maximum expected hole size in width or height pixels
        
        # marks related
        self.maxMarks = 100 # maximum number marks to keep in history

        self.reset()
    

    def reset(self):
        '''
        Resets analysis results
        '''
        self.mirrorBounds = None
        self.paperBounds = None
        self.slot = Slot()
        self.slots = []
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
        frame = frame.astype(np.int16)

        if self.state == State.PREVIEW:
            # in preview state, reset analysis results and output uncropped frame
            self.reset()
            self.streamImage = self.frameToImage(frame)
        elif self.state == State.START:
            # auto-crop and detect mirror
            log.info('Switching to START sate')
            # find mirror (black circle on paper)
            self.mirrorBounds = self.findMirror(frame)
            log.debug(f'Mirror bounds in image: {self.mirrorBounds}')
            # get paper crop and re-calculate mirror bounds within cropped area
            self.paperBounds = self.mirrorBounds.scaled(self.paperScale)
            self.mirrorBounds = self.mirrorBounds.relativeTo(self.paperBounds)
            log.info('Switching to COLLECT sate')
            self.state = State.COLLECT
        else:
            # filling slots with frames
            frame = self.crop(frame, self.paperBounds) # crop
            # add frame to current slot
            log.debug(f'Adding frame {self.slot.length+1}/{self.nSlotFrames} to slot')
            self.slot.add(frame)
            if self.slot.length >= self.nSlotFrames:
                # add current slot to slots
                log.debug('Cycling slot')
                if self.cycleSlots(self.slot):
                    # all slots filles and ready for analysis
                    self.state = State.DETECT
                    # analyse for differences between newest and oldest slot
                    log.debug('Comparing newest to oldest slot')
                    self.analysis = Analysis(self.slots[0], self.slots[-1], self.thresh, self.maxHoleSize)
                    display = np.copy(np.abs(self.analysis.diff*30) if self.showDiff else self.slots[0].mean)
                    if self.analysis.valid:
                        log.info(f'Valid change detected at {self.analysis.rect.center}')
                        # add detection to mark consideration
                        self.detected.append(self.analysis.rect.center)
                        # debug display
                        display[self.analysis.mask] = 255
                    else:
                        # add mark of detection
                        if self.detected:
                            log.debug('Adding change detection mark')
                            self.cycleMarks(self.detected[0])
                        self.detected = []
                    
                    # TODO: parallel to above processing, convert frame to image
                    self.streamImage = self.frameToImage(display)
        
        self.procTime = time.perf_counter()-startTime
    

    def crop(self, frame, rect):
        '''
        Crops a frame by rect

        :param frame: (h, w) array
        :param rect: Rect object
        :returns: cropped frame
        '''
        # ensure rect is in bounds of frame
        top = max(0, rect.top)
        bottom = min(frame.shape[0], rect.bottom)
        left = max(0, rect.left)
        right = min(frame.shape[1], rect.right)
        # crop
        return frame[top:bottom, left:right]
    
    
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
        pickLum = np.mean(frame[iRow-pad:iRow+pad, iCol-pad:iCol+pad], dtype=np.int16)

        # mask luminance in frame for picked value
        matchMask = abs(frame-pickLum) < self.mirrorTolerance

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
    

    def cycleSlots(self, slot):
        '''
        Pushes new slot into buffer

        :param slot: Slot object
        :returns: True if all slots filled, False otherwise
        '''
        self.slots.insert(0, slot) # store current slot
        self.slot = Slot() # reset current slot
        if len(self.slots) > self.MAX_SLOTS:
            self.slots.pop(-1) # delete oldest slot
            return True
        else:
            return False
    

    def cycleMarks(self, pos):
        '''
        Pushes new mark middle position into buffer

        :param pos: tuple of (left, top) pixel matrix indices
        '''
        self.marks.insert(0, pos)
        if len(self.marks) > self.maxMarks:
            self.marks.pop(-1)
    

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
    

    def frameToImage(self, frame):
        '''
        Converts a grayscale frame to bytes of its image

        :param frame: (h, w) array (int16 grayscale matrix)
        :returns: image file bytes
        '''
        img = frame.astype(np.uint8)
        return self.imgArrayToImgBytes(img)


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
    

    def __repr__(self):
        return f'Rect(left: {self.left}, right: {self.right}, top: {self.top}, bottom: {self.bottom})'
    

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
        return ((self.left+self.right)//2, (self.top+self.bottom)//2)
    

    def scaled(self, fac):
        '''
        Scales the rect from center pivot point

        :param fac: float factor to scale
        :returns: new scaled rect
        '''
        xMid, yMid = self.center
        left = int(fac*self.left-fac*xMid)+xMid
        right = int(fac*self.right-fac*xMid)+xMid
        top = int(fac*self.top-fac*yMid)+yMid
        bottom = int(fac*self.bottom-fac*yMid)+yMid
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
    

    def relativeTo(self, ref):
        '''
        Relative to other rect

        :param ref: other Rect object
        :returns: new relative Rect object
        '''
        return self.moved(-ref.left, -ref.top)


class Analysis:
    '''
    Analysis between slots
    '''
    def __init__(self, newSlot, oldSlot, thresh, maxSize=100):
        '''
        :param newSlot/oldSlot: slots
        :param thresh: threshold (0...255) to detect changes between averaged slot frames
        :param maxSize: maximum width/height of difference detection area in pixel
        '''
        self.valid = False
        
        # mask
        diff = newSlot.mean-oldSlot.mean
        log.debug(f'diff min: {diff.min()}, max: {diff.max()}, threshold: {-thresh}')
        self.diff = ndimage.gaussian_filter(diff, 2) # to eliminate outliers
        self.mask = self.diff < -thresh
        #mask = ndimage.binary_erosion(mask).astype(mask.dtype) # erode mask to eliminate outliers
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
            if self.rect.width < maxSize and self.rect.height < maxSize:
                self.valid = True
            else:
                log.info('Too many pixels changed')
    

    def __repr__(self):
        s = f'Analysis({"valid" if self.valid else "invalid"} change'
        if self.valid:
            s += f', {self.rect.width}w x {self.rect.height}h'
        s += ')'
        return s
