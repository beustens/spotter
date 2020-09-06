from picamera import PiCamera # to access the camera
from datetime import datetime # for timestamp

fps = 15
camera = PiCamera(resolution=(1920, 1080), framerate=fps)
camera.meter_mode = 'spot'
camera.exposure_mode = 'verylong'

dt = datetime.now().strftime('%Y.%m.%d-%H.%M')
camera.start_recording(f'/home/pi/video_{fps}fps_{dt}.h264')
try:
    while True:
        camera.wait_recording(5)
except KeyboardInterrupt:
    pass
camera.stop_recording()