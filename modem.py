from collections import namedtuple

import utime
import re
import machine


def get_coordinates_tuple_obj():
    # TODO: Use this sketch
    GpsData = namedtuple("GpsData", ("datetime", "latitude", "longitude", "altitude"))
    return GpsData


class GpsData:
    """
    Data class for storing obtained datetime and geographic location data.
    """
    datetime: str
    latitude: str
    longitude: str
    altitude: str

    def __init__(self, latitude, longitude, datetime=None, altitude=None):
        self.latitude = latitude
        self.longitude = longitude
        self.datetime = datetime
        self.altitude = altitude

    def get_coordinates(self) -> tuple:
        """
        Method for obtaining tuple of latitude and longitude in tuple form.
        :return: Tuple of latitude(0) and longitude(1)
        """
        return self.latitude, self.longitude


class PicoSimcom868:
    """
    A class representing the Simcom SIM868 module, connected to a Raspberry Pi Pico.
    Implementation is based on usage of Micropython.

    Code based on implementation of @EvilPeanut: https://github.com/EvilPeanut/GSM-Modem

    """

    def __init__(self, port=0, uart_baudrate=115200, module_power_gpio_pin=14):
        self.port = port
        self.uart_baudrate = uart_baudrate
        self.module_power_gpio_pin = module_power_gpio_pin
        # TODO: Change write method and test it
        self.uart = machine.UART(self.port, self.uart_baudrate)

        self.module_power_state = False
        self.gps_power_state = False
        self.last_command = None
        self.last_number = None

    def change_module_power_state(self):
        """
        Change power level of the modem module.
        Power level value would be stored in variable self.module_power_state.
        Assume that module power is turned off by default.
        :return:
        """
        print(f"Toggle module power state. Changed from {self.module_power_state} to {not self.module_power_state}")
        power_pin = machine.Pin(self.module_power_gpio_pin, machine.Pin.OUT)
        power_pin.value(1)
        utime.sleep(1)
        power_pin.value(0)
        self.module_power_state = not self.module_power_state

    @staticmethod
    def parse_serial_raw_data(data) -> str:
        # TODO: Find better way to handle None
        if data is None: return data

        decoded_data = data.decode()
        if decoded_data.count('\n') == 2:
            decoded_data = decoded_data.split('\n')[1]
        return decoded_data.replace("\r", "").replace("\n", "")

    def write_command_and_return_response(self, command, time_to_wait=1, print_response=True):
        if not self.module_power_state: self.change_module_power_state()
        self.last_command = command
        self.uart.flush()
        self.uart.write(command)
        utime.sleep(time_to_wait)
        response = self.read_uart_response()
        if print_response: print(f"Response:\n{response}")
        return response

    def read_uart_response(self):
        if not self.module_power_state: self.change_module_power_state()
        # Add sleep to make sure that respond was transmitted
        utime.sleep(0.1)
        if self.uart.txdone():
            serial_read_raw_data = self.uart.read()
        else:
            raise Exception("UART tx not done, could not read anything from serial.")
        if serial_read_raw_data:
            return self.parse_serial_raw_data(serial_read_raw_data)

    def get_echo(self):
        """
        Return echo
        """
        response = self.write_command_and_return_response(b'AT\r', 1)

        return response

    def get_gsm_signal_quality(self):
        """
        Return signal quality
        0 -115 dBm or less
        1 -111 dBm
        2...30 -110... -54 dBm
        31 -52 dBm or greater
        99 not known or not detectable
        """
        response = self.write_command_and_return_response(b'AT+CSQ\r', 1)
        response = re.search(r"\+CSQ: (\d*),\d*", response).group(1)

        return response

    def get_text_messages(self):
        """
        Get text message
        """
        while True:
            response = self.read_uart_response()
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
            utime.sleep(1)

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

        return response

    """
	Turn GPS on
	"""

    def set_gps_on(self):
        print("Setting GPS on")
        response = self.write_command_and_return_response(b'AT+CGNSPWR=1\r', 5)
        if self.gps_power_state:
            print("GPS already set on")
        else:
            print("Wait 30 seconds for GPS fix")
            utime.sleep(30)
        self.gps_power_state = True
        return response

    def set_gps_off(self):
        print("Setting GPS off")
        response = self.write_command_and_return_response(b'AT+CGNSPWR=0\r', 5)
        if not self.gps_power_state:
            print("GPS already set off")
        self.gps_power_state = False
        return response

    def get_gps_data(self):
        """
        Retrieves the current location using the GNSS module.
        Set GPS module power on if it's not turned on.



        :return: A string representing the geographic coordinates (latitude and longitude) of the current location.
        """

        def gps_coordinates_acquired(command_response: str) -> bool:
            """
            GPS coordinates are marked as acquired if AT+CGNSING command returned output without series of blank fields.

            Example of uncorrect AT+CGNSING output:
                +CGNSINF: 0,,,,,,,,,,,,,,,,,,,,
            :param command_response:
            :return: state if
            """
            return ',,,,' not in command_response

        if not self.gps_power_state: self.set_gps_on()
        gps_command_response = self.write_command_and_return_response(b'AT+CGNSINF\r\n', 10)
        if gps_coordinates_acquired(gps_command_response):
            response = {}
            regex_search_result = re.search(
                r"\+CGNSINF: (\d+),(\d+),(\d+?\.\d+),(-?\d+?\.\d+),(-?\d+?\.\d+),(-?\d+?\.\d+)", gps_command_response)
            dt = regex_search_result.group(3)
            response['datetime'] = dt[:4] + '-' + dt[4:6] + '-' + dt[6:8] + ' ' + dt[8:10] + ':' + dt[10:12] + ':' + dt[
                                                                                                                     12:14]
            response['latitude'] = regex_search_result.group(4)
            response['longitude'] = regex_search_result.group(5)
            response['altitude'] = regex_search_result.group(6)
        else:
            print("Invalid GPS data, trying again in 10 seconds")
            utime.sleep(10)
            return self.get_gps_data()
        print(f"Acquired coordinates: {response}")
        return response

    """
	HTTP Post
	"""

    # TODO: Method refactor
    def httpPost(self, url):
        self.write_command_and_return_response(b'AT+HTTPINIT\r')

        utime.sleep(1)

        self.write_command_and_return_response(b'AT+HTTPPARA="URL","' + url + '"\r')

        utime.sleep(1)

        response = self.write_command_and_return_response(b'AT+HTTPACTION=0\r')

        utime.sleep(1)

        self.write_command_and_return_response(b'AT+HTTPTERM\r')

        return str(response)

    """
	GPRS Init
	"""

    # TODO: Method refactor
    def httpInit(self):
        self.write_command_and_return_response(b'AT+HTTPPARA="CID",1\r')

        utime.sleep(1)

        # Vodaphone settings
        self.write_command_and_return_response(b'AT+SAPBR=3,1,"CONTYPE","GPRS"\r')

        utime.sleep(1)

        self.write_command_and_return_response(b'AT+SAPBR=3,1,"APN","pp.vodafone.co.uk"\r')

        utime.sleep(1)

        self.write_command_and_return_response(b'AT+SAPBR=3,1,"USER","wap"\r')

        utime.sleep(1)

        self.write_command_and_return_response(b'AT+SAPBR=3,1,"PWD","wap"\r')

        utime.sleep(1)

        self.write_command_and_return_response(b'AT+SAPBR=2,1\r')

        utime.sleep(1)

        self.write_command_and_return_response(b'AT+SAPBR=1,1\r')
