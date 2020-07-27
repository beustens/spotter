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


class StreamingHandler(server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.target = Target()
        self.oldStreamImage = None
        self.oldState = None
        self.oldFrameCnt = None
        self.oldMarks = None
        super().__init__(*args, directory='html', **kwargs)
    

    def pointPercent(self, point):
        '''
        Percent of point pixel coordinates on background stream

        :param point: (left, top) pixel coordinates
        :returns: dictionary with keys "left", "top"
            and values in percentage
        '''
        x, y = point
        return {'left': 100*x/spotter.streamDims.width, 'top': 100*y/spotter.streamDims.height}
    

    def rectPercent(self, rect):
        '''
        Percent of rect pixel coordinates on background stream

        :param rect: Rect object in pixel coordinates
        :returns: dictionary with keys "left", "top", "width", "height"
            and values in percentage
        '''
        w, h = spotter.streamDims.width, spotter.streamDims.height
        percent = {
            'left': 100*rect.left/w, 
            'top': 100*rect.top/h, 
            'width': 100*rect.width/w, 
            'height': 100*rect.height/h
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
    

    def sendDict(self, data):
        '''
        Sends a dictionary as JSON

        :param data: dictionary
        '''
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    
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
                    
                    time.sleep(0.01) # reduce idle load
            except BrokenPipeError:
                log.info(f'Removed streaming client {self.client_address}')
        elif '/settings' in self.path:
            # push settings into clients input fields
            self.sendEventStreamHeader()
            try:
                while True:
                    ip = self.client_address[0]
                    # init update state for each client
                    if ip not in updateSettings:
                        updateSettings[ip] = True
                    # pack settings
                    if updateSettings[ip]:
                        data = {
                            'contrast': camera.contrast, 
                            'threshold': spotter.thresh, 
                            'average': spotter.nSlotFrames, 
                            'showdiff': spotter.showDiff, 
                            'mode': 'Start' if spotter.state == State.PREVIEW else 'Stop'
                        }
                        # send data
                        self.wfile.write(f'data: {json.dumps(data)}\n\n'.encode())
                        updateSettings[ip] = False

                    time.sleep(0.1) # reduce idle load
            except BrokenPipeError:
                log.info(f'Removed streaming client {self.client_address}')
        elif '/infos' in self.path:
            # send event after processed frame from camera
            self.sendEventStreamHeader()
            try:
                while True:
                    if self.oldFrameCnt != spotter.frameCnt:
                        # get debug infos
                        data = {
                            'Processing time': f'{(spotter.procTime*1e3):.2f} ms', 
                            'Exposure time': f'{(camera.exposure_speed/1e3):.2f} ms', 
                            'Frames in slot': f'{spotter.slot.length}/{spotter.nSlotFrames}', 
                            'Last analysis': '--' if spotter.analysis is None else str(spotter.analysis)
                        }
                        # send data
                        self.wfile.write(f'data: {json.dumps(data)}\n\n'.encode())
                        self.oldFrameCnt = spotter.frameCnt
                    
                    time.sleep(0.01) # reduce idle load
            except BrokenPipeError:
                log.info(f'Removed streaming client {self.client_address}')
        elif '/state' in self.path:
            # state change
            self.sendEventStreamHeader()
            try:
                while True:
                    if self.oldState != spotter.state:
                        data = {'state': str(spotter.state).split('.')[1]}
                        
                        # put in mirror picker size
                        if spotter.state == State.PREVIEW:
                            picker = {
                                'width': 100*spotter.mirrorPickSize/camera.resolution[0], 
                                'height': 100*spotter.mirrorPickSize/camera.resolution[1]
                            }
                            data.update({'pickersize': picker})

                        # put in mirror coordinates in percent to stream
                        if spotter.state == State.DETECT and spotter.mirrorBounds:
                            rings = [self.rectPercent(ring) for ring in self.target.getRingBounds(spotter.mirrorBounds)]
                            data.update({'ringsizes': rings})

                        # send data
                        self.wfile.write(f'data: {json.dumps(data)}\n\n'.encode())
                        self.oldState = spotter.state
                    
                    time.sleep(0.1) # reduce idle load
            except BrokenPipeError:
                log.info(f'Removed streaming client {self.client_address}')
        elif '/marks' in self.path:
            # marks change
            self.sendEventStreamHeader()
            try:
                while True:
                    marksHash = hash(tuple(spotter.marks)) # to detect changed mark list
                    if self.oldMarks != marksHash:
                        data = [self.pointPercent(mark) for mark in spotter.marks]
                        # send data
                        self.wfile.write(f'data: {json.dumps(data)}\n\n'.encode())
                        self.oldMarks = marksHash
                    
                    time.sleep(0.1) # reduce idle load
            except BrokenPipeError:
                log.info(f'Removed streaming client {self.client_address}')
        else:
            super().do_GET()
    

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
            
            # update settings for all clients
            for k in updateSettings:
                updateSettings[k] = True

        # respond
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    with PiCamera() as camera:
        log.debug('Adjusting camera settings')
        camera.resolution = (1280, 720)#(1920, 1080)
        camera.meter_mode = 'spot'
        camera.contrast = 0
        camera.framerate_range = (0.1, 30)
        camera.exposure_mode = 'verylong'
        time.sleep(2)
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
