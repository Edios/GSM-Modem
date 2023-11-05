# import serial
# TODO: Consider changing time.wait to utime
import time
import utime
import re
from machine import UART


class GSMModem:
    def __init__(self, port=0, uart_baudrate=115200):
        self.port = port
        self.uart_baudrate = uart_baudrate
        # TODO: Change write method and test it
        self.uart = UART(self.port, baudrate=self.uart_baudrate)

        self.last_command = None
        self.last_number = None

    @staticmethod
    def parse_serial_raw_data(data) -> str:
        # Decode bytes to string
        # if last command and 2x \n in output
        #    Clear command (all before \n)
        # Replace all \n \r with ""

        decoded_data = data.decode()
        if decoded_data.count('\n') == 2:
            decoded_data = decoded_data.split('\n')[1]
        return decoded_data.replace("\r", "").replace("\n", "")

    def write_command_and_return_response(self, command, timeout_ms=2000, printresponse=False):
        self.last_command = command

        # self.uart.timeout = timeout

        # self.uart.read(self.uart.inWaiting())
        # Pico uart :
        # self.uart.txdone()

        # self.uart.flushInput()
        # self.uart.flushOutput()
        # Pico uart :
        self.uart.flush()

        self.uart.write(command)

        response = self.read()

        return response

    def read(self):
        # Add sleep to make sure that respond was transmitted
        utime.sleep(0.1)
        if self.uart.txdone():
            serial_read_raw_data = self.uart.read()
        else:
            raise Exception("UART tx not done, could not read anything from serial.")
        return self.parse_serial_raw_data(serial_read_raw_data)

    """
	Return echo
	"""

    def getEcho(self):
        response = self.write_command_and_return_response(b'AT\r', 1)

        if response == 'ERROR':
            # Handle error
            response = response
        else:
            response = response[1]

        return response

    """
	Return signal quality
	0 -115 dBm or less
	1 -111 dBm
	2...30 -110... -54 dBm
	31 -52 dBm or greater
	99 not known or not detectable
	"""

    def getCSQ(self):
        response = self.write_command_and_return_response(b'AT+CSQ\r', 1)

        if response == 'ERROR':
            # Handle error
            response = response
        else:
            response = response[1]
            response = re.search(r"\+CSQ: (\d*),\d*", response).group(1)

        return response

    """
	Get text message
	"""

    def getText(self):
        while True:
            response = self.read()
            if len(response) > 0:
                if response[0].startswith('+CMTI'):
                    print(response)
                    regex = re.search(r'\+CMTI: "(\w+)",(\d+)', response[0])
                    msg_count = regex.group(2)
                    response = self.write_command_and_return_response(b'AT+CMGR=' + msg_count + '\r')
                    print(response)
                if len(response) == 3:
                    # print(response)
                    self.last_number = re.search(r'\+CMGR:\s"\w+\s\w+","(\+\d+)"', response[1]).group(1)
                    response = response[2]
                    return response
            time.sleep(1)

    """
	Send text
	"""

    def sendText(self, number, message):
        # Set the format of messages to Text mode
        self.write_command_and_return_response(b'AT+CMGF=1\r', 1)

        # Select the GSM 7 bit default alphabet
        self.write_command_and_return_response(b'AT+CSCS="GSM"\r', 1)

        # Start sending
        self.write_command_and_return_response(b'AT+CMGS="' + number + '"\r', 1)

        # Send message
        response = self.write_command_and_return_response(message + '\r\x1a', 1)

        if response == 'ERROR':
            # Handle error
            response = response
        else:
            response = response[1]

        return response

    """
	Turn GPS on
	"""

    def setGPSOn(self):
        response = self.write_command_and_return_response(b'AT+CGNSPWR=1\r', 5)
        time.sleep(30)
        return response

    """
	Get GPS data
	"""

    def getGPSData(self):
        raw = self.write_command_and_return_response(b'AT+CGNSINF\r', 10)

        raw = raw[1]
        if (re.match(r"\+CGNSINF: (\d+),(\d+),(\d+?\.\d+),(-?\d+?\.\d+),(-?\d+?\.\d+),(-?\d+?\.\d+)", raw)):
            raw = re.search(r"\+CGNSINF: (\d+),(\d+),(\d+?\.\d+),(-?\d+?\.\d+),(-?\d+?\.\d+),(-?\d+?\.\d+)", raw)

            response = {}

            dt = raw.group(3)
            response['datetime'] = dt[:4] + '-' + dt[4:6] + '-' + dt[6:8] + ' ' + dt[8:10] + ':' + dt[10:12] + ':' + dt[
                                                                                                                     12:14]
            response['latitude'] = raw.group(4)
            response['longitude'] = raw.group(5)
            response['altitude'] = raw.group(6)
        else:
            print("Invalid GPS data, trying again in 10 seconds")
            time.sleep(10)
            return self.getGPSData()

        return response

    """
	HTTP Post
	"""

    def httpPost(self, url):
        self.write_command_and_return_response(b'AT+HTTPINIT\r')

        time.sleep(1)

        self.write_command_and_return_response(b'AT+HTTPPARA="URL","' + url + '"\r')

        time.sleep(1)

        response = self.write_command_and_return_response(b'AT+HTTPACTION=0\r')

        time.sleep(1)

        self.write_command_and_return_response(b'AT+HTTPTERM\r')

        return str(response)

    """
	GPRS Init
	"""

    def httpInit(self):
        self.write_command_and_return_response(b'AT+HTTPPARA="CID",1\r')

        time.sleep(1)

        # Vodaphone settings
        self.write_command_and_return_response(b'AT+SAPBR=3,1,"CONTYPE","GPRS"\r')

        time.sleep(1)

        self.write_command_and_return_response(b'AT+SAPBR=3,1,"APN","pp.vodafone.co.uk"\r')

        time.sleep(1)

        self.write_command_and_return_response(b'AT+SAPBR=3,1,"USER","wap"\r')

        time.sleep(1)

        self.write_command_and_return_response(b'AT+SAPBR=3,1,"PWD","wap"\r')

        time.sleep(1)

        self.write_command_and_return_response(b'AT+SAPBR=2,1\r')

        time.sleep(1)

        self.write_command_and_return_response(b'AT+SAPBR=1,1\r')
