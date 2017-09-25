### COMMAND FORMATS

__description__ = \
"""
subclass of PyCmdMessenger class that enables continuouse reading from and
writing to Arduino board.
"""
__author__ = "Michael J. Harms, chrisgrosse"
__date__ = "2017-09-25"


import re, warnings, time, struct
from PyCmdMessenger import CmdMessenger
from serial.threaded import Packetizer

class CmdMessengerThreaded(CmdMessenger, Packetizer):
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
        CmdMessenger.__init__(self.board_instance, commands, field_separator,
                              command_separator, escape_separator, warnings)
        Packetizer.__init()
        TERMINATOR = self.command_separator
        
        
    def connection_made(self, transport):
        super(CmdMessengerThreaded, self).connection_made(transport)
        
    def connection_lost(self, exc):
        super(CmdMessengerThreaded, self).connection_lost(exc)
        raise IOError("Lost connection to Arduino!")
        
    def handle_packet(self, data_packet): # basically original receive method
        """
        Basically original receive method. However, different commands are
        separated by Packetizer.data_received() method already
        """
        msg = [[]]
        raw_msg = []
        escaped = False
#        command_sep_found = False
        for tmp in data_packet:
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
        analyze_command(cmd_name, received, message_time)
    
    
    def analyze_command(self, cmd_name, msg, message_time):
        raise NotImplementedError("analyze_command needs to be overwritten by subclass!")  
        
    
    


