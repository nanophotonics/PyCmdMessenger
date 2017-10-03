"""
This class inherets from the ArduinoBoard class and sets the right number of
bytes to store an integer, longs, float and double on Arduino Due and SAMD 
based boards. Here integers and doubles are stored as 32-bit (4-byte and) and
8-byte (64-bit) values, respectively, compared to the Arduino Uno and other 
ATMega based boards.
"""

from arduino import ArduinoBoard

class ArduinoDueBoard(ArduinoBoard):

    def __init__(self, port):
        super(ArduinoDueBoard, self).__init__(port, int_bytes=4, double_bytes=8)