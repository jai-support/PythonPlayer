from flask import Flask, render_template, Response
import eBUS as eb
from datetime import datetime
import camera

# from eBUS import PvResult
import PvSampleUtils as psu
import cv2

running = False
capture = False

outputFrame = cv2.imread("jai.PNG")

cam = None
device_param = None
filename = ""
app = Flask(__name__)


## FLASK FUNCTIONS
def generate_frames():
    """Generate frames from the video."""
    global capture
    while True:
        if running:
            try:
                frame = cam.GetImage()
                if capture:
                    cv2.imwrite(filename, frame)
                    capture = False
            except RuntimeError as e:
                print("Acquisition error: ", e)
                disconnect()

        else:
            frame = outputFrame
        ret, buffer = cv2.imencode(".jpg", frame)
        frame = buffer.tobytes()
        yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


## FLASK HTML FUNCTIONS
@app.route("/")
def index():
    """Display the video streaming HTML page."""
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    """Route for streaming the video."""
    return Response(
        generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/iExposureTime")
def iExposureTime():

    print("hello")
    result, value = cam.GetParameter("ExposureTime", device_param)
    if result is None:
        return "failed to get Exposure Time"
    exp_max = value[2]
    exp_current = value[1]
    if (exp_current + 1000) > exp_max:
        return "can't set Exposure Time higher than " + str(exp_max)
    if cam.SetParameter("ExposureTime", exp_current + 1000, device_param):
        return "ExposureTime = " + str(exp_current + 1000)
    return "failed to set Exposure Time"


@app.route("/dExposureTime")
def dExposureTime():
    result, value = cam.GetParameter("ExposureTime", device_param)
    if result is None:
        return "failed to get Exposure Time"
    exp_min = value[0]
    exp_current = value[1]
    if (exp_current - 1000) < exp_min:
        return "can't set Exposure Time less than " + str(exp_min)
    if cam.SetParameter("ExposureTime", exp_current - 1000, device_param):
        return "ExposureTime = " + str(exp_current - 1000)
    return "failed to set Exposure Time"


@app.route("/start_stop")
def start_stop():
    global running
    global capture
    capture = False
    if running:
        cam.StopAcquisition()
        running = False
        return "Stop"
    cam.StartAcquisition()
    running = True
    return "Start"


@app.route("/disconnect")
def disconnect():
    cam.StopAcquisition()
    cam.Close()
    exit()
    return "Closing Camera"


@app.route("/capture")
def capture():
    global capture
    global running
    global filename
    if running:
        capture = True
        now = datetime.now()
        filename = f"{now.strftime('%d-%m-%y_%H.%M.%S')}.PNG"
        return "Saving image as " + filename
    return "not running"


if __name__ == "__main__":
    connection_ID = psu.PvSelectDevice()
    if connection_ID is None:
        exit()
    result, device = eb.PvDevice.CreateAndConnect(connection_ID)
    if device is None:
        print(
            f"Unable to connect to device: {result.GetCodeString()} ({result.GetDescription()})"
        )
    cam = camera.Camera(device, connection_ID, True)
    if cam.Open():
        device_param = device.GetParameters()
        app.run(debug=False)
