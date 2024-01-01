import utime

from pico_simcom868 import PicoSimcom868, GpsCoordinatesNotAcquired, GpsData

sim868 = PicoSimcom868()


def initialize_module():
    if not sim868.module_power_state:
        sim868.change_module_power_state()

    if not sim868.gps_power_state:
        sim868.set_gps_on()

    sim868.initialize_http(apn="internet")


def get_gps_data():
    initialize_module()
    return sim868.get_gps_data()


def send_google_maps_link_by_sms(number: str):
    try:
        gps_data = get_gps_data()
    except GpsCoordinatesNotAcquired:
        print("Data not acquired")
        return
    sim868.send_text_message(number, gps_data.compose_google_maps_link())


def get_list_of_coordinates(samples_number: int, samples_collect_interval: int):
    """
    Get a list of GPS coordinates over a specified time period.

    :param samples_number: The number of GPS samples to collect
    :param samples_collect_interval: The time interval between gathering each GPS sample in seconds.
    """
    data = []
    for sample in range(samples_number):
        try:
            data.append(sim868.get_gps_data().__dict__)
            utime.sleep(samples_collect_interval)
        except GpsCoordinatesNotAcquired:
            print(f"Unable to gather Gps coordinates at loop: {sample}.")
    return data


def compose_gps_data_with_metadata(gps_data: GpsData, device_id: str = "Default device id"):
    """
    Compose ready to send json file with gathered data
    :param gps_data: The time interval between gathering each GPS sample in seconds.
    :param device_id: Custom device identification number
    :return:
    """
    """
      // var server_time = 0
      
      // one_packet data:
      // var device_id = 0
      // //GpsData fields
      // var latitude = 0
      // var longitude = 0
      // var datetime = 0
      // var altitude = 0
    """
    pass
    # return {"device_id": device_id, **gps_data}


# TODO: Can be overload of compose_single_json_packet
# def compose_multiple_gps_data_json(list_of_gps_data: list, device_id: str):
#     multiple_dictionary = {}
#     for gps_data in list_of_gps_data:
#         multiple_dictionary = {**multiple_dictionary, **compose_gps_data_with_metadata(gps_data, device_id)}
#     return multiple_dictionary


dummy_data = {
    "resource": [
        {
            "device_id": "PICO",
            "latitude": "15.202000",
            "longitude": "75.31100",
            "datetime": "2023-03-29 12:30:44",
            "altitude": "75.32000"
        },
        {
            "device_id": "POSTMAN2",
            "latitude": "15.200000",
            "longitude": "75.32000",
            "datetime": "2023-03-29 12:30:44",
            "altitude": "75.32000"
        }
    ]
}


def post_data():
    # sim868.http_post("https://webhook.site/831edb32-4630-4877-9d2e-b6a4d08a25fa", "data")
    sim868.http_post("https://script.google.com/macros/s/AKfycbwaGclwFytcXE6fX34CoT_e5-Y2r5P0-3yGlWNa17Ah3N7yf30lbUQouLw7ryXaY2TL/exec", str(dummy_data))
