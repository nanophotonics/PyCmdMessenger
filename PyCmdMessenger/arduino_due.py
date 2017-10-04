"""
This class inherets from the ArduinoBoard class and sets the right number of
bytes to store an integer, longs, float and double on Arduino Due and SAMD
based boards. Here integers and doubles are stored as 32-bit (4-byte and) and
8-byte (64-bit) values, respectively, compared to the Arduino Uno and other
ATMega based boards.
"""

from arduino import ArduinoBoard

class ArduinoDueBoard(ArduinoBoard):

    def __init__(self, port, baud_rate=9600, timeout=1.0, settle_time=2.0,
                 enable_dtr=False, int_bytes=4, long_bytes=4, float_bytes=4,
                 double_bytes=8):
        super(ArduinoDueBoard, self).__init__(port, baud_rate, timeout,
                                             settle_time, enable_dtr,
                                             int_bytes, long_bytes, float_bytes,
                                             double_bytes)