import utime
import re
import machine


def to_bytes(given):
    return bytes(given, "utf-8")


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

    def __bool__(self):
        """
        Check if GPS data is not empty.
        :return:
        """
        return all([self.latitude, self.longitude])

    def get_coordinates(self) -> tuple:
        """
        Method for obtaining tuple of latitude and longitude in tuple form.
        :return: Tuple of latitude(0) and longitude(1)
        """
        return self.latitude, self.longitude

    def compose_google_maps_link(self):
        """
        Return a link to google maps to query a place with latitude and longitude of a place. (devided by space)
        :return: Google Maps Link
        """
        return f"https://www.google.com/maps/search/?api=1&query={self.latitude}%20{self.longitude}"


class GpsCoordinatesNotAcquired(Exception):
    pass


class IncorrectCommandOutput(Exception):
    pass


class PicoSimcom868:
    """
    A class representing the Simcom SIM868 module, connected to a Raspberry Pi Pico.
    This class provides a Python interface to interact with the Simcom SIM868 module for GSM and GPS communication.
    Implementation is based on usage of Micropython.

    Code based on implementation of @EvilPeanut: https://github.com/EvilPeanut/GSM-Modem

    """

    def __init__(self, port=0, uart_baudrate=115200, module_power_gpio_pin=14):
        self.port = port
        self.uart_baudrate = uart_baudrate
        self.power_pin = machine.Pin(module_power_gpio_pin, mode=machine.Pin.OUT)
        self.uart = machine.UART(self.port, self.uart_baudrate)

        self.module_power_state = False
        self.ensure_module_power_state()

        self.gps_power_state = False
        self.last_command = None
        self.last_number = None

    def change_module_power_state(self, force_state=None):
        """
        Change power level of the modem module.
        Power level value would be stored in variable self.module_power_state.
        Assume that module power is turned off by default.
        :param force_state: Force module power state argument value
        :return:
        """

        def pulse_module_power():
            self.power_pin.value(1)
            utime.sleep(1)
            self.power_pin.value(0)

        print(f"Toggle module power state. Changed from {self.module_power_state} to {not self.module_power_state}")
        pulse_module_power()

        if isinstance(force_state, bool):
            print(f"Forced power state, state value will be: {force_state}")
            self.module_power_state = force_state
        else:
            self.module_power_state = not self.module_power_state
        utime.sleep(3)

    @staticmethod
    def parse_serial_raw_data(data) -> str:
        # TODO: Find better way to handle None
        if data is None: return data

        decoded_data = data.decode()
        if decoded_data.count('\n') == 2:
            decoded_data = decoded_data.split('\n')[1]
        return decoded_data.replace("\r", "").replace("\n", "")

    def read_uart_response(self):
        if self.uart.txdone():
            serial_read_raw_data = self.uart.read()
        else:
            raise Exception("UART tx not done, could not read anything from serial.")
        if serial_read_raw_data:
            return self.parse_serial_raw_data(serial_read_raw_data)

    # TODO: Add to_byte conversion and command with response check. Inspirations:
    #  https://github.com/Ircama/raspberry-pi-sim800l-gsm-module/blob/master/sim800l/sim800l.py
    #  https://github.com/inductivekickback/at/blob/master/at/at.py
    def send_command(self, command, time_to_wait=1, add_execute_command_string=True, print_response=True):
        """
        Send a command through the UART interface to the module and read the response.

        This method flushes the serial buffer, then sends a command through the UART interface,
        After that waits for the specified time, and reads the response.
        The response is then optionally printed to the console.

        :param command: The command to be sent as a byte sequence.
        :param time_to_wait: Time to wait to response read after sending command
        :param add_execute_command_string: Determine if \r should be added at the end of the command to execute it
        :param print_response:  Whether to print the command and response to the console (default is True)
        :return: The response received from the module serial.
        """

        if add_execute_command_string: command += '\r'
        self.last_command = command
        command = to_bytes(command)
        self.uart.flush()
        self.uart.write(command)
        utime.sleep(time_to_wait)
        response = self.read_uart_response()
        if print_response: print(f"Command:\n{command}\nResponse:\n{response}")
        return response

    def send_command_and_check_response(self, command: str, expected_response: str,
                                        add_execute_command_string: bool = True, time_to_wait: int = 1,
                                        raise_exception=False):
        command_response = self.send_command(command=command, time_to_wait=time_to_wait,
                                             add_execute_command_string=add_execute_command_string,
                                             print_response=False)
        if expected_response in command_response:
            print(f"Correct response from command {command} with answer {command_response}")
            return True
        else:
            fail_message = f"Expected response string not found in command output!\n Command {command} with answer {command_response}"
            if raise_exception:
                raise IncorrectCommandOutput(fail_message)
            else:
                print(fail_message)
                return True

    def get_echo(self):
        """
        Send echo command to the module.

        :return: State if sending command was successful
        """
        return self.send_command_and_check_response('AT', 'OK')

    def ensure_module_power_state(self):
        """
        Send echo command to determine if module is really powered down.
        Module power state is kept in self.module_power_state variable.
        Turn off module power if detected that it is powered on.
        """
        if self.get_echo():
            self.change_module_power_state(force_state=False)

    def get_gsm_signal_quality(self):
        """
        Return signal quality
        0 -115 dBm or less
        1 -111 dBm
        2...30 -110... -54 dBm
        31 -52 dBm or greater
        99 not known or not detectable
        """
        # TODO: Add enum for signal quality
        response = self.send_command('AT+CSQ')
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
                    response = self.send_command(f'AT+CMGR={msg_count}')
                    print(response)
                if len(response) == 3:
                    # print(response)
                    self.last_number = re.search(r'\+CMGR:\s"\w+\s\w+","(\+\d+)"', response[1]).group(1)
                    response = response[2]
                    return response
            utime.sleep(1)

    def send_text_message(self, number: str, message: str):
        """
        Send text message to given number in E.164 format.
        """

        # Set the format of messages to Text mode
        self.send_command('AT+CMGF=1')

        # Select the GSM 7 bit default alphabet
        self.send_command('AT+CSCS="GSM"')

        # Start sending
        self.send_command(f'AT+CMGS="{number}"')

        # Send message
        response = self.send_command(message + '\r\x1a', add_execute_command_string=False)

        return response

    def set_gps_on(self):
        """
        Turn module GPS on
        """
        print("Setting GPS on")
        response = self.send_command('AT+CGNSPWR=1', 5)
        if self.gps_power_state:
            print("GPS already set on")
        else:
            print("Wait 30 seconds for GPS fix")
            utime.sleep(30)
        self.gps_power_state = True
        return response

    def set_gps_off(self):
        print("Setting GPS off")
        response = self.send_command('AT+CGNSPWR=0', 5)
        if not self.gps_power_state:
            print("GPS already set off")
        self.gps_power_state = False
        return response

    def get_gps_data(self, attempts_number=5, attempt_wait_time=5) -> GpsData:
        """
        Retrieves the current location using the GNSS module.
        Set GPS module power on if it's not turned on.

        :param attempts_number: Set a number of attempts which for accruing GPS coordinates
        :param attempt_wait_time: Set a wait time between coordinates attempt  will occur
        :return: A string representing the geographic coordinates (latitude and longitude) of the current location.

        Method will throw GpsCoordinatesNotAcquired exception if was unable to gather GPS Data

        """

        def gps_coordinates_acquired(command_response: str) -> bool:
            """
            Example of correct AT+CGNSING output:
                "+CGNSINF: 1,1,20231122111000.000,50.887232,19.231535,120.429,0.00,0.0,1,,1.0,1.4,0.9,,14,7,5,,31,,"
            Example of not correct AT+CGNSING output:
                +CGNSINF: 0,,,,,,,,,,,,,,,,,,,,
            GPS coordinates are marked as acquired if AT+CGNSING command returned output without series of blank fields.

            :param command_response:
            :return: state if there are in acquired command response
            """
            return ',,,,' not in command_response and command_response is not None

        def send_modem_gps_info_command():
            return self.send_command('AT+CGNSINF', 10)

        for _ in range(attempts_number):
            gps_command_response = send_modem_gps_info_command()
            if gps_coordinates_acquired(gps_command_response):
                split_gps_command_response = gps_command_response.split(",")
                response = GpsData(latitude=split_gps_command_response[3], longitude=split_gps_command_response[4],
                                   datetime=split_gps_command_response[2], altitude=split_gps_command_response[5])
                print(f"Acquired coordinates: {gps_command_response}")
                return response
            else:
                print("Invalid GPS data, trying again in 10 seconds")
                utime.sleep(attempt_wait_time)
                pass

        raise GpsCoordinatesNotAcquired("Reached maximum gather attempts number. "
                                        "Unable to acquire GPS coordinates data.")

    def initialize_http(self, apn: str, apn_address: str = None, apn_user: str = None,
                        apn_password: str = None):
        """
        Initializes GPRS for HTTP communication.

        :param apn_address: Access point address (if not dns)
        :param apn_user: Access point username (if required)
        :param apn_password: Access point username (if required)
        :param apn: Access Point Name for GPRS (default is "internet").

        Note:
            This method sets up GPRS configuration for HTTP communication using AT commands.
            It configures the GPRS connection with the specified Access Point Name (APN),
        """

        self.send_command('AT+SAPBR=3,1,"CONTYPE","GPRS"')
        self.send_command(f'AT+SAPBR=3,1,"APN","{apn}"')
        if apn_address:
            self.send_command(f'AT+SAPBR=3,1,"APN","{apn_address}"')
        if apn_user:
            self.send_command(f'AT+SAPBR=3,1,"USER","{apn_user}"')
        if apn_password:
            self.send_command(f'AT+SAPBR=3,1,"PWD","{apn_password}"')
        self.send_command('AT+SAPBR=2,1')
        self.send_command('AT+SAPBR=1,1')
        self.send_command('AT+HTTPINIT')
        # Enable SSL software feature
        self.send_command('AT+HTTPSSL=1')
        self.send_command('AT+HTTPPARA="CID",1')

    def http_post(self, url: str, data: str):
        """
        HTTP Post
        """

        # TODO: Method refactor
        self.send_command(f'AT+HTTPPARA="URL","{url}"')
        # Get= 0 / Post= 1
        self.send_command('AT+HTTPACTION=1', 3)
        # self.write_command_and_return_response(to_bytes(to_bytes(f'AT+HTTPDATA={len(data.encode()) + 5},10000\r')))
        self.send_command(f'AT+HTTPDATA=15,10000')
        # self.write_command_and_return_response(to_bytes(str(data)+"\r"))
        # self.write_command_and_return_response(to_bytes(str(data)+"\r"))
        # self.write_command_and_return_response(to_bytes(str(data)))
        # self.write_command_and_return_response(to_bytes(str(data) + '\r\x1a'))
        self.send_command(str(data) + '>', add_execute_command_string=False)
        self.send_command('\r\x1a', add_execute_command_string=False)
        # "AT+HTTPPARA=\"CONTENT\",\"text/plain\"\r"

        utime.sleep(11)
        #
        self.send_command('AT+HTTPREAD')
        self.send_command('AT+HTTPACTION=1')
        utime.sleep(10)
        self.send_command('AT+HTTPTERM')

        # return str(response)
