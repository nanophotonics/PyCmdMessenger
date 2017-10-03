### COMMAND FORMATS

__description__ = \
"""
subclass of PyCmdMessenger class that enables continuouse reading from and
writing to Arduino board.
"""
__author__ = "Michael J. Harms, chrisgrosse"
__date__ = "2017-09-25"


import warnings, time
from PyCmdMessenger import CmdMessenger
#from serial.threaded import Packetizer
import threading

class CmdMessengerThreaded(CmdMessenger, threading.Thread):
    """
    Basic interface for interfacing over a serial connection to an arduino 
    using the CmdMessenger library.
    """
    
    def __init__(self,
                 board_instance,
                 commands,
                 field_separator=",",
                 command_separator=";",
                 escape_separator="/",
                 warnings=True):
        """
        Input:
            board_instance:
                instance of ArduinoBoard initialized with correct serial 
                connection (points to correct serial with correct baud rate) and
                correct board parameters (float bytes, etc.)

            commands:
                a list or tuple of commands specified in the arduino .ino file
                *in the same order* they are listed there.  commands should be
                a list of lists, where the first element in the list specifies
                the command name and the second the formats for the arguments.
                (e.g. commands = [["who_are_you",""],["my_name_is","s"]])

            field_separator:
                character that separates fields within a message
                Default: ","

            command_separator:
                character that separates messages (commands) from each other
                Default: ";" 
       
            escape_separator:
                escape character to allow separators within messages.
                Default: "/"

            warnings:
                warnings for user
                Default: True
 
            The separators and escape_separator should match what's
            in the arduino code that initializes the CmdMessenger.  The default
            separator values match the default values as of CmdMessenger 4.0. 
        """
        super(CmdMessengerThreaded, self).__init__(board_instance, commands, field_separator,
                              command_separator, escape_separator, warnings)
        self.serial = board_instance
        self.daemon = True
        self.alive = True
        self._lock = threading.lock()
        self.buffer = bytearray()
        # start serial reading thread
        self.run()
        
        
    def run(self):
        error = None
        while self.alive and self.serial.is_open:
            try:
                data = self.serial.read(self.serial.in_waiting or 1)
            except serial.SerialException as e:
                error = e
                break
            else:
                if data:
                    try:
                        self.received_data(data)
                    except Exception as e:
                        error = e
                        break
        self.alive = False
        self.lost_connection(error)
        
    def stop(self):
        self.alive = False
        if hasattr(self.serial, 'cancel_read'):
            self.serial.cancel_read()
        self.join(2)
        
    def close(self):
        with self._lock:
            self.stop()
            self.serial.close()
            
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()        
    
    def lost_connection(self, exc):
        raise IOError("Lost connection to Arduino!")
        raise exc
    
    def write(self, data):
        with self._lock:
            self.serial.write(data)            
    
    
    def send(self,cmd,*args,**kwargs):
        """
        Send a command (which may or may not have associated arguments) to an 
        arduino using the CmdMessage protocol.  The command and any parameters
        should be passed as direct arguments to send.  

        arg_formats can be passed as a keyword argument. arg_formats is an
        optional string that specifies the formats to use for each argument
        when passed to the arduino. If specified here, arg_formats supercedes
        formats specified on initialization.  
        """

        # Turn the command into an integer.
        try:
            command_as_int = self._cmd_name_to_int[cmd]
        except KeyError:
            err = "Command '{}' not recognized.\n".format(cmd)
            raise ValueError(err)

        # Grab arg_formats from kwargs
        arg_formats = kwargs.pop('arg_formats', None)
        if kwargs:
            raise TypeError("'send()' got unexpected keyword arguments: {}".format(', '.join(kwargs.keys())))

        # Figure out what formats to use for each argument.  
        arg_format_list = []
        if arg_formats != None:

            # The user specified formats
            arg_format_list = list(arg_formats)

        else:
            try:
                # See if class was initialized with a format for arguments to this
                # command
                arg_format_list = self._cmd_name_to_format[cmd]
            except KeyError:
                # if not, guess for all arguments
                arg_format_list = ["g" for i in range(len(args))]
  
        # Deal with "*" format  
        arg_format_list = self._treat_star_format(arg_format_list,args)

        if len(args) > 0:
            if len(arg_format_list) != len(args):
                err = "Number of argument formats must match the number of arguments."
                raise ValueError(err)

        # Go through each argument and create a bytes representation in the
        # proper format to send.  Escape appropriate characters. 
        fields = ["{}".format(command_as_int).encode("ascii")]
        for i, a in enumerate(args):
            fields.append(self._send_methods[arg_format_list[i]](a))
            fields[-1] = self._escape_re.sub(self._byte_escape_sep + r"\1".encode("ascii"),fields[-1])

        # Make something that looks like cmd,field1,field2,field3;
        compiled_bytes = self._byte_field_sep.join(fields) + self._byte_command_sep

        # Send the message. 
        # Only part in this function that has changed to use new thread safe write() function
        self.write(compiled_bytes)    
    
    
    def received_data(self, data):
        """Buffer received data, find self.command_separator, call received_command"""
        self.buffer.extend(data)
        while self.command_separator in self.buffer:
            command, self.buffer = self.buffer.split(self.command_separator, 1)
            self.received_command(command)
        
    def received_command(self, command): 
        """
        Basically original receive() method. However, different commands are
        separated by received_data() method already
        """
        msg = [[]]
        raw_msg = []
        escaped = False
#        command_sep_found = False
        for tmp in command:
#        while True:
#            tmp = self.board.read()
            raw_msg.append(tmp)

            if escaped:

                # Either drop the escape character or, if this wasn't really
                # an escape, keep previous escape character and new character
                if tmp in self._escaped_characters:
                    msg[-1].append(tmp)
                    escaped = False
                else:
                    msg[-1].append(self._byte_escape_sep)
                    msg[-1].append(tmp)
                    escaped = False
            else:

                # look for escape character
                if tmp == self._byte_escape_sep:
                    escaped = True

                # or field separator
                elif tmp == self._byte_field_sep:
                    msg.append([])

                # or command separator
#                elif tmp == self._byte_command_sep:
#                    command_sep_found = True
#                    break

                # or any empty characater 
                elif tmp == b'':
                    break

                # okay, must be something
                else:
                    msg[-1].append(tmp)
  
        # No message received given timeouts
        if len(msg) == 1 and len(msg[0]) == 0:
            return None

        # Make sure the message terminated properly
#        if not command_sep_found:
#          
#            # empty message (likely from line endings being included) 
#            joined_raw = b''.join(raw_msg) 
#            if joined_raw.strip() == b'':
#                return  None
#           
#            err = "Incomplete message ({})".format(joined_raw.decode())
#            raise EOFError(err)

        # Turn message into fields
        fields = [b''.join(m) for m in msg]

        # Get the command name.
        cmd = fields[0].strip().decode()
        try:
            cmd_name = self._int_to_cmd_name[int(cmd)]
        except (ValueError,IndexError):

            if self.give_warnings:
                cmd_name = "unknown"
                w = "Recieved unrecognized command ({}).".format(cmd)
                warnings.warn(w,Warning)
        
        # Figure out what formats to use for each argument.  
        arg_format_list = []
        if arg_formats != None:

            # The user specified formats
            arg_format_list = list(arg_formats)

        else:
            try:
                # See if class was initialized with a format for arguments to this
                # command
                arg_format_list = self._cmd_name_to_format[cmd_name]
            except KeyError:
                # if not, guess for all arguments
                arg_format_list = ["g" for i in range(len(fields[1:]))]

        # Deal with "*" format  
        arg_format_list = self._treat_star_format(arg_format_list,fields[1:])

        if len(fields[1:]) > 0:
            if len(arg_format_list) != len(fields[1:]):
                err = "Number of argument formats must match the number of received arguments."
                raise ValueError(err)

        received = []
        for i, f in enumerate(fields[1:]):
            received.append(self._recv_methods[arg_format_list[i]](f))
        
        # Record the time the message arrived
        message_time = time.time()
        self.analyze_command(cmd_name, received, message_time)
    
    
    def analyze_command(self, cmd_name, msg, message_time):
        raise NotImplementedError("analyze_command needs to be overwritten by subclass!")  
        
    
    


