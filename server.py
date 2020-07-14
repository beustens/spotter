#!/usr/bin/env python3

from picamera import PiCamera # to access the camera
from imgproc import FrameAnalysis, Mode # for camera frame processing
import logging # for more advanced prints
import socketserver # to make a server
from http import server # to handle http requests
import json # for parsing POST requests
import time # for waiting


logging.basicConfig(level=logging.INFO)
log = logging.getLogger(f'spotter_{__name__}')


class StreamingHandler(server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory='html', **kwargs)
    

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
                    if spotter.streamImage:
                        self.wfile.write(b'--FRAME\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', len(spotter.streamImage))
                        self.end_headers()
                        self.wfile.write(spotter.streamImage)
                        self.wfile.write(b'\n\n')
                        spotter.streamImage = bytes()
                    
                    time.sleep(0.01) # reduce idle load
            except BrokenPipeError:
                log.info(f'Removed streaming client {self.client_address}')
        elif '/settings' in self.path:
            # client requests settings
            data = {
                'contrast': camera.contrast, 
                'threshold': spotter.thresh, 
                'average': spotter.nSlotFrames, 
                'mode': 'Start' if spotter.mode == Mode.PREVIEW else 'Stop'
            }
            self.sendDict(data)
        elif '/infos' in self.path:
            # send event after processed frame from camera
            self.sendEventStreamHeader()
            try:
                while True:
                    if spotter.procTime:
                        # get debug infos
                        debug = {
                            'Processing time': f'{(spotter.procTime*1e3):.2f} ms', 
                            'Exposure time': f'{(camera.exposure_speed/1e3):.2f} ms', 
                            'Frames in slot': f'{spotter.slot.length}/{spotter.nSlotFrames}', 
                            'Last analysis': '--' if spotter.analysis is None else ('No valid change detected' if   not spotter.analysis.valid else f'Changes detected in {spotter.analysis.rect}')
                        }

                        # pack data
                        data = {'debug': debug}

                        # put in mirror picker size
                        if spotter.mode == Mode.PREVIEW:
                            picker = {
                                'width': 100*spotter.mirrorPickSize/camera.resolution[0], 
                                'height': 100*spotter.mirrorPickSize/camera.resolution[1]
                            }
                            data.update({'pickersize': picker})

                        # put in mirror coordinates in percent related to stream
                        if spotter.mode == Mode.DETECT and spotter.mirrorBounds and spotter.paperBounds:
                            mirror = {
                                'left': 100*spotter.mirrorBounds.left/spotter.paperBounds.width, 
                                'top': 100*spotter.mirrorBounds.top/spotter.paperBounds.height, 
                                'width': 100*spotter.mirrorBounds.width/spotter.paperBounds.width, 
                                'height': 100*spotter.mirrorBounds.height/spotter.paperBounds.height
                            }
                            data.update({'mirrorsize': mirror})

                        # send data
                        self.wfile.write(f'data: {json.dumps(data)}\n\n'.encode())
                        spotter.procTime = 0.
                    
                    time.sleep(0.01) # reduce idle load
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
                    'start': Mode.START, 
                    'preview': Mode.PREVIEW
                }
                spotter.mode = modes.get(value, Mode.PREVIEW)

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
