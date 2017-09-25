__description__ = \
"""
subclass of ArduinoBoard class that enables continuouse reading from and
writing to Arduino board.
"""
__author__ = "chrisgrosse"
__date__ = "2017-09-25"

import time, serial
from serial.threaded import ReaderThread
from PyCmdMessenger import ArduinoBoard

class ArduinoBoardThreaded(ArduinoBoard):
    """
    Class for connecting to an Arduino board over USB using PyCmdMessenger.  
    The board holds the serial handle (which, in turn, holds the device name,
    baud rate, and timeout) and the board parameters (size of data types in 
    bytes, etc.).  The default parameters are for an ArduinoUno board.
    """
    
    def __init__(self, device):
        super(ArduinoBoardThreaded, self).__init__(device)
        # start reading thread ..
        self.protocol = Protocol()
        self.reading_thread = ReaderThread(self.comm, self.protocol)
        self.reading_thread.run()
    
    def read(self):
        """
        Wrap threaded serial read method.
        """
        err  = "read command not supported anymore! Serial signals are detect automatically."
        raise NotImplementedError(err)   
 
    def readline(self):
        """
        Wrap serial readline method.
        """
        raise NotImplementedError("readline command not implemented yet!")    
    

    def write(self,msg):
        """
        Wrap threaded serial write method.
        """        
        self.reading_thread.write(msg)

    def close(self):
        """
        Close serial connection.
        """
        if self._is_connected:
            self.serial_thread.close()
        self._is_connected = False
        