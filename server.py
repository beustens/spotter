#!/usr/bin/env python3
import emulation
if emulation.emulated:
    from emulation import PiCamera
else:
    from picamera import PiCamera # to access the camera
from imgproc import FrameAnalysis, State # for camera frame processing
from target import Target # to display rings and value marks
import logging # for more advanced prints
import socketserver # to make a server
from http import server # to handle http requests
import json # for parsing POST requests
import time # for waiting


logging.basicConfig(level=logging.INFO)
log = logging.getLogger(f'spotter_{__name__}')

updateSettings = {}
target = Target(name='100 m Gewehr, 25 m Pistole', holeDia=5.5)


class StreamingHandler(server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.oldStreamImage = None
        self.oldState = None
        self.oldFrameCnt = None
        self.oldMirror = None
        self.oldMarks = None
        self.oldMarkDia = None
        self.oldTargetName = None
        super().__init__(*args, directory='html', **kwargs)
    

    def pixToPercent(self, pix):
        '''
        Converts pixel size to size in percent 
        to the current stream image

        :param pix: (x, y) pixel values
        '''
        if spotter.state == State.PREVIEW:
            # workaround
            height = camera.resolution[0]
            dims = (height, height)
        else:
            dims = spotter.streamDims
        
        return (100*pix[0]/dims[0], 100*pix[1]/dims[1])
    

    def pointPercent(self, point):
        '''
        Percent of point pixel coordinates on background stream

        :param point: (left, top) pixel coordinates
        :returns: dictionary with keys "left", "top"
            and values in percentage
        '''
        percent = self.pixToPercent(point)
        return {'left': percent[0], 'top': percent[1]}
    

    def rectPercent(self, rect):
        '''
        Percent of rect pixel coordinates on background stream

        :param rect: Rect object in pixel coordinates
        :returns: dictionary with keys "left", "top", "width", "height"
            and values in percentage
        '''
        posPercent = self.pixToPercent((rect.left, rect.top))
        sizePercent = self.pixToPercent((rect.width, rect.height))
        percent = {
            'left': posPercent[0], 
            'top': posPercent[1], 
            'width': sizePercent[0], 
            'height': sizePercent[1]
        }
        return percent
    

    def sendEventStreamHeader(self):
        '''
        Sends response and header for text/event-stream
        '''
        self.send_response(200)
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Content-type', 'text/event-stream')
        self.end_headers()
    
    
    def do_GET(self):
        '''
        Got GET request
        '''
        if 'stream.jpg' in self.path:
            # got request for the stream
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    # update stream image
                    if self.oldStreamImage != spotter.streamImage:
                        self.wfile.write(b'--FRAME\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', len(spotter.streamImage))
                        self.end_headers()
                        self.wfile.write(spotter.streamImage)
                        self.wfile.write(b'\n\n')
                        self.oldStreamImage = spotter.streamImage
                    
                    time.sleep(0.05) # reduce idle load
            except BrokenPipeError:
                log.info(f'Removed streaming client {self.client_address}')
        elif '/change' in self.path:
            self.sendEventStreamHeader()
            try:
                while True:
                    data = {}
                    self.settingsEvent(data)
                    self.updateEvent(data)
                    self.stateEvent(data)
                    self.ringsEvent(data)
                    self.marksEvent(data)
                    # send data to client
                    self.wfile.write(f'data: {json.dumps(data)}\n\n'.encode())
                    time.sleep(0.25) # reduce idle load
            except BrokenPipeError:
                log.info(f'Removed streaming client {self.client_address}')
        else:
            super().do_GET()
    

    def settingsEvent(self, eventData):
        ip = self.client_address[0]
        # init update state for each client
        if ip not in updateSettings:
            updateSettings[ip] = True
        # pack settings
        if updateSettings[ip]:
            data = {
                'contrast': camera.contrast, 
                'brightness': camera.brightness, 
                'threshold': spotter.thresh, 
                'average': spotter.nSlotFrames, 
                'showdiff': spotter.showDiff, 
                'target': target.name, 
                'markdia': target.holeDia, 
                'ringswidth': spotter.mirrorScale[0]*100-100, 
                'ringsheight': spotter.mirrorScale[1]*100-100, 
                'ringsleft': spotter.mirrorTranslate[0], 
                'ringstop': spotter.mirrorTranslate[1], 
                'saverings': spotter.keepMirror, 
                'mode': 'Start' if spotter.state == State.PREVIEW else 'Stop'
            }
            eventData.update({'settings': data})
            updateSettings[ip] = False
    

    def updateEvent(self, eventData):
        if self.oldFrameCnt != spotter.frameCnt:
            data = {}
            # get debug infos
            infos = {
                'Processing time': f'{(spotter.procTime*1e3):.2f} ms', 
                'Exposure time': f'{(camera.exposure_speed/1e3):.2f} ms', 
                'Last analysis': '--' if spotter.analysis is None else str(spotter.analysis)
            }
            data.update({'infos': infos})
            
            # get progress
            if spotter.state == State.DETECT:
                # average progress
                progress = spotter.slot.length/spotter.nSlotFrames
                data.update({'progress': 100*progress})
            elif spotter.state == State.COLLECT:
                # filling slots progress
                curCollect = spotter.slot.length+sum(slot.length for slot in spotter.slots)
                maxCollect = spotter.maxSlots*spotter.nSlotFrames
                progress = curCollect/maxCollect
                data.update({'progress': 100*progress})
            
            eventData.update({'update': data})
            self.oldFrameCnt = spotter.frameCnt
    

    def stateEvent(self, eventData):
        if self.oldState != spotter.state:
            data = {'state': str(spotter.state).split('.')[1]}
            
            # put in mirror picker size
            if spotter.state == State.PREVIEW:
                w, h = self.pixToPercent((spotter.mirrorPickSize, spotter.mirrorPickSize))
                picker = {'width': w, 'height': h}
                data.update({'pickersize': picker})
            
            eventData.update({'state': data})
            self.oldState = spotter.state
    

    def ringsEvent(self, eventData):
        if spotter.state == State.DETECT:
            newMirror = spotter.corrMirrorBounds
        elif spotter.state == State.COLLECT:
            newMirror = spotter.pickBounds
        else:
            newMirror = None
        
        if self.oldMirror != newMirror:
            # corrected mirror coordinates in percent to stream
            if newMirror:
                target.mirrorBounds = newMirror # update mirror bounds
                rings = [self.rectPercent(ring) for ring in target.ringBounds]
            else:
                rings = []
            eventData.update({'rings': rings})
            
            self.oldMirror = newMirror
    

    def marksEvent(self, eventData):
        # changed mark list
        marksHash = hash(tuple(spotter.marks) if spotter.state == State.DETECT else None)
        if self.oldMarks != marksHash:
            data = []
            # in collect state, get marks
            mirror = spotter.corrMirrorBounds
            if mirror and spotter.state == State.DETECT:
                for pos in spotter.marks:
                    # look up ring for each mark
                    ring = target.pointInRing(pos)
                    mark = {
                        'pixpos': {'left': pos[0], 'top': pos[1]}, 
                        'relpos': self.pointPercent(pos), 
                        'ring': ring
                    }
                    data.append(mark)
                
                # get mark size
                p = target.holeSize
                markSize = self.pixToPercent((p, p))
                eventData.update({'marksize': {
                    'width': markSize[0], 
                    'height': markSize[1]
                }})
            
            eventData.update({'marks': data})
            self.oldMarks = marksHash
    

    def do_POST(self):
        '''
        Got POST request
        '''
        self.data_string = self.rfile.read(int(self.headers['Content-Length']))
        data = json.loads(self.data_string.decode())
        log.debug(f'Got POST data: {data}')

        # parse data
        if self.path == '/setting':
            # client wants to change a parameter
            param = data['param']
            value = data['value']
            log.info(f'Client wants to set {param} to {value}')
            if param == 'contrast':
                # set camera contrast
                camera.contrast = int(value)
            elif param == 'brightness':
                # set camera brightness
                camera.brightness = int(value)
            elif param == 'threshold':
                # set difference detection threshold
                spotter.thresh = int(value)
            elif param == 'average':
                # set number of frames per slot to average
                spotter.nSlotFrames = int(value)
            elif param == 'mode':
                # change mode
                modes = {
                    'start': State.START, 
                    'preview': State.PREVIEW
                }
                spotter.state = modes.get(value, State.PREVIEW)
            elif param == 'showdiff':
                # show normal or diff image
                spotter.showDiff = value
            elif param == 'target':
                # set target type
                target.fromDatabase(value)
            elif param == 'markdia':
                # set mark size
                target.holeDia = float(value)
            elif param == 'ringswidth':
                # scale mirror in x
                spotter.mirrorScale = ((float(value)+100)/100, spotter.mirrorScale[1])
            elif param == 'ringsheight':
                # scale mirror in y
                spotter.mirrorScale = (spotter.mirrorScale[0], (float(value)+100)/100)
            elif param == 'ringsleft':
                # move mirror in x
                spotter.mirrorTranslate = (int(value), spotter.mirrorTranslate[1])
            elif param == 'ringstop':
                # move mirror in y
                spotter.mirrorTranslate = (spotter.mirrorTranslate[0], int(value))
            elif param == 'saverings':
                # check if mirror rings and related settings should reset at start
                spotter.keepMirror = value
            
            # update settings for all clients
            for k in updateSettings:
                updateSettings[k] = True
        elif self.path == '/mark':
            # client wants to change a mark
            action = data['action']
            iMark = data['index']
            log.info(f'Client wants to {action} mark {iMark}')
            if action == 'delete':
                # delete mark
                del spotter.marks[iMark]
            elif action == 'copy':
                # copy mark
                spotter.marks.append(spotter.marks[iMark])
            elif action == 'correct':
                # change position of mark
                pos = data['pos']
                pos = (int(pos['left']), int(pos['top']))
                spotter.marks[iMark] = pos

        # respond
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    with PiCamera(resolution=(1920, 1080), framerate_range=(3, 30)) as camera:
        camera.meter_mode = 'spot'
        camera.exposure_mode = 'verylong'
        with FrameAnalysis(camera) as spotter:
            log.debug('Starting frame analysis')
            camera.start_recording(spotter, format='yuv')
            # start server
            try:
                log.debug('Starting HTTP server')
                server = StreamingServer(('', 8000), StreamingHandler)
                log.info(f'Started user interface on http://{server.server_name}:{server.server_port}')
                log.info('Press ctrl-C to stop')
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                camera.stop_recording()
                log.debug('Stopped camera recording')
