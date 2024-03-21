import eBUS as eb
import PvSampleUtils as psu
import cv2
import re
from threading import Thread, Lock

if __name__ == "__main__":
    import time


class ParameterNotAvailableError(Exception):
    """Exception raised when Parameters aren't available.

    Attributes:
        command -- input command which caused the error
        message -- explanation of the error
    """

    def __init__(self, command, message="This command is not available"):
        self.command = command
        self.message = message
        super().__init__(self.message)


class ParameterNotReadableError(Exception):
    """Exception raised when Parameters aren't readable.

    Attributes:
        command -- input command which caused the error
        message -- explanation of the error
    """

    def __init__(self, command, message="This command is not readable"):
        self.command = command
        self.message = message
        super().__init__(self.message)


class ParameterSetFailureError(Exception):
    """Exception raised when Parameters fails to set.

    Attributes:
        command -- input command which caused the error
        message -- explanation of the error
    """

    def __init__(self, command, message="This command is not readable"):
        self.command = command
        self.message = message
        super().__init__(self.message)


class Camera:
    """Class to work with the image sensors (sources) on the camera
    Returns:
        Object: use it to manage a source
    """

    device_name = None
    _device = None
    _connection_id = None
    _stream = None

    _output_available = False
    _output_frame = None
    _output_format = None
    _format_image = None

    _BUFFER_COUNT = 16
    _buffers = []

    _thread = None
    _lock = Lock()

    _running = False
    _stop_thread = False

    def __init__(self, device, connection_id, format_image):
        self._format_image = format_image
        self._device = device
        self._connection_id = connection_id

    ## PRIVATE

    def _ConfigureStream(self):
        # If this is a GigE Vision device, configure GigE Vision specific streaming parameters
        if isinstance(self._device, eb.PvDeviceGEV):
            # Negotiate packet size
            self._device.NegotiatePacketSize()
            # Configure device streaming destination
            self._device.SetStreamDestination(
                self._stream.GetLocalIPAddress(), self._stream.GetLocalPort()
            )
            stream_param = self._stream.GetParameters()

            self.SetParameter("MaximumResendGroupSize", 5000, stream_param)
            self.SetParameter("MaximumResendRequestRetryByPacket", 5, stream_param)

    def _ConfigureStreamBuffers(self):
        # Reading payload size from device
        size = self._device.GetPayloadSize()

        # Use BUFFER_COUNT or the maximum number of buffers, whichever is smaller
        buffer_count = self._stream.GetQueuedBufferMaximum()
        if buffer_count > self._BUFFER_COUNT:
            buffer_count = self._BUFFER_COUNT

        # Allocate buffers
        for i in range(buffer_count):
            # Create new pv_buffer object
            pv_buffer = eb.PvBuffer()
            # Have the new pv_buffer object allocate payload memory
            pv_buffer.Alloc(size)
            # Add to external list - used to eventually release the buffers
            self._buffers.append(pv_buffer)

        # Queue all buffers in the stream
        for pv_buffer in self._buffers:
            self._stream.QueueBuffer(pv_buffer)

    def _ConfigurePixelFormat(self):
        if self._format_image:
            dp = self._device.GetParameters()
            # Set Pixel format to 8 bits
            gen_type, pixel_format = self.GetParameter("PixelFormat", dp)
            if pixel_format is None:
                return print(gen_type)

            self._output_format = re.search(r"\D+", pixel_format).group()
            channel_size = int(
                pixel_format[len(self._output_format) : len(pixel_format)]
            )

            if channel_size > 8:
                self.SetParameter("PixelFormat", self._output_format + "8", dp)
            self._output_format = self._output_format + "8"

    def _ImageFormatting(self, buffer):

        image = buffer.GetImage()
        image_data = image.GetDataPointer()
        match image.GetPixelType():
            case eb.PvPixelMono8:
                pass
            case eb.PvPixelBayerBG8:
                image_data = cv2.cvtColor(image_data, cv2.COLOR_BayerBG2RGB)
            case eb.PvPixelBayerGB8:
                image_data = cv2.cvtColor(image_data, cv2.COLOR_BayerGB2RGB)
            case eb.PvPixelBayerGR8:
                image_data = cv2.cvtColor(image_data, cv2.COLOR_BayerGR2RGB)
            case eb.PvPixelBayerRG8:
                image_data = cv2.cvtColor(image_data, cv2.COLOR_BayerRG2RGB)
            case eb.PvPixelRGB8:
                image_data = cv2.cvtColor(image_data, cv2.COLOR_RGB2BGR)
            case _:
                return None
        return image_data

    def _BufferProcessing(self, buffer):
        lPayloadType = buffer.GetPayloadType()
        match lPayloadType:
            case eb.PvPayloadTypeImage:
                if self._format_image:
                    image_data = self._ImageFormatting(buffer)
                else:
                    image = buffer.GetImage()
                    image_data = image.GetDataPointer()

                if image_data.size != 0:
                    with self._lock:
                        self._output_frame = image_data.copy()
                        self._output_available = True
            case eb.PvPayloadTypeChunkData:
                print(
                    f" Chunk Data payload type with {buffer.GetChunkCount()} chunks",
                    end="",
                )
            case eb.PvPayloadTypeRawData:
                print(
                    f" Raw Data with {buffer.GetRawData().GetPayloadLength()} bytes",
                    end="",
                )
            case eb.PvPayloadTypeMultiPart:
                print(
                    f" Multi Part with {buffer.GetMultiPartContainer().GetPartCount()} parts",
                    end="",
                )
            case _:
                print(" Payload type not supported by this sample", end="")

    def _Acquisition(self):
        """
        thread function
        """
        error_count = 0
        error_buffer = []
        while True:
            if self._stop_thread:
                # close thread
                break

            if self._running is False:
                # Wait for Acquisition
                continue

            result, buffer, operational_result = self._stream.RetrieveBuffer(1000)
            if result.IsOK():
                if operational_result.IsOK():
                    error_count = 0
                    error_buffer.clear()
                    # buffer is good, process it
                    self._BufferProcessing(buffer)
                    self._stream.QueueBuffer(buffer)
                else:
                    error_buffer.append(
                        "Operation Result: " + str(operational_result.GetCode())
                    )
                    error_count += 1
            else:
                error_buffer.append("result: " + str(result.GetCode()))
                error_count += 1

            if error_count >= 10:
                print("Got to many consecutive errors, aborting")
                for e in error_buffer:
                    print(e)
                break
            continue

        # Abort all buffers from the stream and dequeue
        self._stream.AbortQueuedBuffers()
        while self._stream.GetQueuedBufferCount() > 0:
            print("hello")
            result, buffer, lOperationalResult = self._stream.RetrieveBuffer()

    # Public

    def SetParameter(self, command, value, param):
        gen_parameter = param.Get(command)
        try:
            result, lAvailable = gen_parameter.IsAvailable()
            if not lAvailable:
                raise ParameterNotAvailableError(command)
        except AttributeError as e:
            print("IsAvailable not found: ", e)

        # Parameter readable?
        try:
            result, lReadable = gen_parameter.IsReadable()
            if not lReadable:
                raise ParameterNotReadableError(command)
        except AttributeError as e:
            print("IsAvailable not found: ", e)

        # / Get the parameter type
        result, gen_type = gen_parameter.GetType()
        result = gen_parameter.SetValue(value)
        if result.IsFailure():
            raise ParameterSetFailureError(command, result.GetDescription())
        return True

    def GetParameter(self, command, param):
        gen_parameter = param.Get(command)
        if gen_parameter is None:
            return None, None
        result, gen_type = gen_parameter.GetType()
        match gen_type:
            case eb.PvGenTypeEnum:
                # return gen_parameter.GetValueInt()
                result, value = gen_parameter.GetValueString()
            case eb.PvGenTypeBoolean | eb.PvGenTypeString:
                result, value = gen_parameter.GetValue()
            case eb.PvGenTypeInteger | eb.PvGenTypeFloat:
                result, value = gen_parameter.GetValue()
                value = [
                    gen_parameter.GetMin()[1],
                    gen_parameter.GetValue()[1],
                    gen_parameter.GetMax()[1],
                ]
            case _:
                return None, None

        if result.IsFailure():
            return result.GetDescription(), None
        return gen_type, value

    def Open(self):
        """close the stream to a source"""
        print("Opening stream from ", self._connection_id, ".", sep="")
        # Open stream to the GigE Vision or USB3 Vision device
        result, stream = eb.PvStream.CreateAndOpen(self._connection_id)
        if stream is None:
            print(
                f"Unable to stream from device. {result.GetCodeString()} ({result.GetDescription()})"
            )
            return None

        self.device_name = self.GetParameter(
            "DeviceModelName", self._device.GetParameters()
        )[1]
        self._stream = stream

        self._ConfigureStream()
        self._ConfigurePixelFormat()

        self._ConfigureStreamBuffers()

        self._thread = Thread(target=self._Acquisition, args=[])
        self._thread.start()

        return True

    def Close(self):
        """close the stream to a source"""
        print("Closing source from ", self.device_name, ".", sep="")

        # stopping thread
        self._stop_thread = True
        self._thread.join()

        self._buffers.clear()

        # Closing stream
        self._stream.Close()
        eb.PvStream.Free(self._stream)

    def StartAcquisition(self):
        """Starts acquisition of a source"""
        # print("Start acquisition ", self._connection_id.GetDisplayID(), ".", sep="")
        self._running = True

        # Sending AcquisitionStart command to device
        self._device.GetParameters().Get("AcquisitionStart").Execute()

        self._device.StreamEnable()

    def StopAcquisition(self):
        """Stops acquisition of a source"""
        # print("Stop acquisition ", self._connection_id.GetDisplayID(), ".", sep="")
        self._running = False

        # Sending AcquisitionStop command to device
        self._device.GetParameters().Get("AcquisitionStop").Execute()

        self._device.StreamDisable()

    def GetImage(self):
        while self._thread.is_alive():
            if self._output_available:
                break
        if self._thread.is_alive():
            with self._lock:
                self._output_available = False
                return self._output_frame

        raise RuntimeError("Thread was killed due to Acquisition errors")


if __name__ == "__main__":

    kb = psu.PvKb()
    connection_ID = psu.PvSelectDevice()
    if connection_ID is None:
        exit()
    result, device = eb.PvDevice.CreateAndConnect(connection_ID)
    if device is None:
        print(
            f"Unable to connect to device: {result.GetCodeString()} ({result.GetDescription()})"
        )
    cam = Camera(device, connection_ID, True)
    if cam.Open():
        cam.StartAcquisition()

        kb.start()
        while not kb.is_stopping():
            try:
                frame = cam.GetImage()
                if frame is None:
                    continue
                image_data = cv2.resize(
                    frame,
                    (800, 600),
                    interpolation=cv2.INTER_LINEAR,
                )
                cv2.imshow("stream", image_data)
                cv2.waitKey(1)
            except RuntimeError as e:
                print("Acquisition error: ", e)
                break
            if kb.kbhit():
                kb.getch()
                break

        cam.StopAcquisition()
        cam.Close()
