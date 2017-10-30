### COMMAND FORMATS

__description__ = \
"""
subclass of PyCmdMessenger class that enables continuouse reading from and
writing to Arduino board.
"""
__author__ = "Michael J. Harms, chrisgrosse"
__date__ = "2017-09-25"


import warnings, time
import numpy as np
import struct
from PyCmdMessenger import CmdMessenger
from PyCRC.CRCCCITT import CRCCCITT as CRC
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
#        super(CmdMessengerThreaded, self).__init__(board_instance, commands,
#                                                 field_separator, command_separator,
#                                                 escape_separator, warnings)
        CmdMessenger.__init__(self, board_instance, commands, field_separator,
                              command_separator, escape_separator, warnings)
        threading.Thread.__init__(self)
        
        self.serial = board_instance.comm
        self.daemon = True
        self.alive = True
        self._lock = threading.Lock()
        self._made_connection = threading.Event()
        self._buffer = []
        self._num_bytes_check_value = 2
        self._num_bytes = {"c":1,
                           "b":1,
                           "i":self.board.int_bytes,
                           "I":self.board.int_bytes,
                           "l":self.board.long_bytes,
                           "L":self.board.long_bytes,
                           "f":self.board.float_bytes,
                           "d":self.board.double_bytes,
                           "s":-1,
                           "?":1}
        
        
        # start serial reading thread
        self._byte_field_sep=bytearray(self._byte_field_sep)
        self.corrupted_cmds=0.00 # percentage of received commands that are corrupted
        self.start()


    def stop(self):
        self.alive = False
        if hasattr(self.serial, 'cancel_read'):
            self.serial.cancel_read()
        self.join(2)

    def close(self):
        with self._lock:
            self.stop()
            self.serial.close()

    def connect(self):
        if self.alive:
            self._made_connection.wait()
            if not self.alive:
                raise RuntimeError("lost_connection already called")
            return (self)
        else:
            raise RuntimeError("already stopped")

    def __enter__(self):
        self.start()
        self._made_connection.wait()
        if not self.alive:
            raise RuntimeError("lost_connection already called")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def made_connection(self, transport):
        print "connection made by PyCmdMessenger"


    def lost_connection(self, exc):
#        raise IOError("Lost connection to Arduino!")
        raise exc


    def run(self, arg_formats=None):
        num_cmd_rec=0
        num_corr_cmd=0
        _buffer = bytearray()
        prev_command = []
        if not hasattr(self.serial, 'cancel_read'):
            self.serial.timeout = 1
        try:
            self.made_connection(self)
        except Exception as e:
            self.alive = False
            self.lost_connection(e)
            self._made_connection.set()
            return
        
        error = None
        msg = [[]]
        raw_msg = []
        escaped = False  
        command_sep_found = False 
        
        while self.alive and self.serial.is_open:
            while self.serial.in_waiting > 0:

                tmp = self.serial.read(1)
                if tmp != "":    
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
                        elif tmp == self._byte_command_sep:
                            command_sep_found = True
                        # okay, must be something
                        else:
                            msg[-1].append(tmp)                    
                
                if command_sep_found:                        
                    command_sep_found = False 
                    raw_command = msg
                    
                    # Turn message into fields (excluding crc value at the end)
                    rec_crc_value = b''.join(msg[-1])
                    fields = [b''.join(m) for m in msg[:-1]]
                    msg=[[]]
                            
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
                            arg_format_list = ["g" for i in range(len(fields[1:-2]))]
                            
                    # Deal with "*" format  
                    arg_format_list = self._treat_star_format(arg_format_list,fields[1:-2])
                    
    #                print "fields:", fields
    #                print "command name:", cmd_name
                    
                    # check correct length of command
                    if len(fields[1:]) > 0:
                        if len(arg_format_list) != len(fields[1:]): 
                            print "fields:", fields
                            print "previous command:", prev_command
                            err = "Number of argument formats must match the number of received arguments."
                            raise ValueError(err)              
                    
                    # get a byte value from 1-3 ASCII characters encoding the
                    # command number to calculate the correct check value
                    try:
                        fields[0] = bytearray([np.uint8(str(fields[0]))])
                    except:
                        print "problem transforming command number to byte value. command:", fields[0]
                                              
                    # calculate CRC check value
                    crc = CRC(version='XModem').calculate(self._byte_field_sep.join(fields))
                    calc_crc_2bytes = struct.pack("<H", crc)
                    
    #                print "calculated crc value: _{}_".format(calc_crc_2bytes)
    #                print "calculated crc value string: _{}_".format(str(calc_crc_2bytes))
                            
                   # compare received and calculated CRC value
                    if calc_crc_2bytes != rec_crc_value:
                        num_corr_cmd+=1
                        print "received corrupted commands", num_corr_cmd
                        print "raw command:", raw_command                   
                        print "calculated crc as 2 bytes: _{}_".format(calc_crc_2bytes)
                        print "calculated crc hex:", hex(crc)
                        print "percentage of corrupted commands:",self.corrupted_cmds
                    else: 
                        received = []
                        for i, f in enumerate(fields[1:]):
                            received.append(self._recv_methods[arg_format_list[i]](f)) 
                        # Record the time the message arrived
                        message_time = time.time()
                        prev_command = fields
                        self.response_to_command(cmd_name, received, message_time)
                        
                                                   
    #                         check that comand has the correct length for the
    #                         received command number and one byte of a binary
    #                         argument was not accidently identified as command_sep
    #                        arguments = []
    #                        if len(command) != 0:
    #                            try:
    #                                cmd_ASCII, arguments = command.split(self._byte_field_sep, 1)
    #                            except:
    #                                print "command cannot be split into command number and arguments"
    #                                print "raw command:", command
    #                                print "buffer:", _buffer
    #                                print "previous command:", prev_command
    #                            
    #                            try:
    #                                # Get the command name  
    #                                cmd = str(cmd_ASCII).strip().decode()
    #                                cmd_name = self._int_to_cmd_name[int(cmd)]
    #                            except (ValueError,IndexError):
    #                                if self.give_warnings:
    #                                    print "command number not recognized"
    #                                    print "raw command:", command
    #                                    print "previous command:", prev_command
    #                                    cmd_name = "unknown"
    #                                    w = "Unrecognized command or bit error!"
    #                                    warnings.warn(w,Warning)    
    #                                 
    #                            # Figure out format and length of received command.
    #                            arg_format_list = []
    #                            if arg_formats != None:
    #                                # The user specified formats
    #                                arg_format_list = list(arg_formats)
    #                            else:
    #                                try:
    #                                    # See if class was initialized with a format 
    #                                    # for arguments to this command
    #                                    arg_format_list = self._cmd_name_to_format[cmd_name]
    #                                except KeyError:
    #                                    print "problem with argument format for command", cmd_name
    #                                    print "raw command:", command
    #                                    print "previous command:", prev_command
                                        
                                
    #                            expected_bytes = self._num_bytes_check_value
    #                            expected_bytes += len(arg_format_list)-1  # one additional byte for each field separator
    #                            for c in arg_format_list:
    #                                expected_bytes += self._num_bytes[c]
                                    
    #                            # check that received command has the correct length, otherwise add bytes from buffer
    #                            while len(arguments) < expected_bytes:
    #    #                            print "received command is too short!"
    #    #                            print "raw command:", command
    #    #                            print "previous command:", prev_command
    #                                # check if there is another command separator in _buffer
    #                                sep_pos = _buffer.find(self._byte_command_sep)
    #                                if sep_pos == -1:  # no command separator
    #    #                                print "no command separator found in buffer, so update buffer"
    #                                    # wait until remaining parts of commands have arrived
    #                                    while self.command_separator not in _buffer:
    #                                        _buffer.extend(bytearray(self.serial.read(self.serial.in_waiting or 1)))
    #                                    sep_pos = _buffer.find(self._byte_command_sep)
    #    #                                print "new buffer:", _buffer
    #                                
    #                                arguments.extend(self.command_separator) # byte missinterpreted as command separator                                                            
    #                                if sep_pos == 0:
    #                                    del _buffer[0]
    #                                
    #                                elif sep_pos <= (expected_bytes-len(arguments)): # check that new bytes are the missing ones
    #                                    remaining_cmd, _buffer = _buffer.split(self._byte_command_sep, 1)
    #                                    arguments.extend(remaining_cmd)
    ##                                    print "new arguments:", arguments
    #                                
    #                                elif sep_pos > (expected_bytes-len(arguments)):
    #                                    print "expected_bytes", expected_bytes
    #                                    print "len(arguments)", len(arguments)
    #                                    
    #                                    print "raw command:", command
    #                                    print "previous command:", prev_command
    #                                    print "following arugments too long!"
    #                                    print _buffer[:sep_pos] 
                                
    #                           
    #                                received = []
    #                                if len(fields[1:]) > 0:
    #                                    # check that number of arguments in received command is same as
    #                                    # number of arguments expected for command number
    #                                    if len(arg_format_list) < len(fields[1:]): 
    #                                        # one byte in binary argument misinterpreted as field separator, 
    #                                        # because total number of bytes in command was verified before
    #                                        # so go through argument format list ..
    #                                        for i,c in enumerate(arg_format_list):
    #                                            if len(fields[i+1])<self._num_bytes[c]:
    #                                                fields[i+1]=self._byte_field_sep.join(fields[i+1:i+2])
    #    #                                            print "binaray argument misinterpreted as field separator"
    #    
    #                                    elif len(arg_format_list) > len(fields[1:]):  
    #                                        err = "Number of argument formats must match the number of received arguments."
    #                                        err += " Function causing problem: "+cmd_name
    #                                        print err
    #                                        print " message causing probelm: "
    #                                        print fields
    #                                        print "preceeding command:", prev_command
    #                                        raise ValueError(err)
    #                                    else:
    #                        #                print "fields as string:",fields
    #                                        # convert argument list of bytearray to list of hex string
    #                                        for i, f in enumerate(fields[1:]):
    #                                            received.append(self._recv_methods[arg_format_list[i]](str(f)))
    #                                     
    #                                        # Record the time the message arrived
    #                                        message_time = time.time()
    #                                        prev_command = command
    #                                        self.response_to_command(cmd_name, received, message_time)
    #                            
                           
        self.alive = False
        self.lost_connection(error)
        
        
    def received_command(self, fields, arg_formats=None):
        """
        Basically original receive() method. However, different commands are
        separated by run() method already
        param fields: list of bytearrays containing the command number and arguments
        """
        
        # Get the command name.
        fields[0]=str(ord(str(fields[0])))        
        try:
            cmd = str(fields[0]).strip().decode()
            cmd_name = self._int_to_cmd_name[int(cmd)]
        except (ValueError,IndexError):
            if self.give_warnings:
                cmd_name = "unknown"
                w = "Recieved unrecognized command ({}).".format(cmd)
                w += " Recieved fields: ({})".format(fields)
                warnings.warn(w,Warning)
#        print "fields:", fields
        
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

        received = []
        if len(fields[1:]) > 0:
            # check that number of arguments in received command is same as
            # number of arguments expected for command number
#            if len(arg_format_list) != len(fields[1:]):
            if len(arg_format_list) < len(fields[1:]): # most likely one byte in binary argument misinterpreted as field separator
                # go through argument format list ..
                for i,c in enumerate(arg_format_list):
                    if len(fields[i+1])<self._num_bytes[c]:
                        fields[i+1]=self._byte_field_sep.join(fields[i+1:i+2])
#                        print "binaray argument misinterpreted as field separator"
            elif len(arg_format_list) > len(fields[1:]):  
                err = "Number of argument formats must match the number of received arguments."
                err += " Function causing problem: "+cmd_name
                print err
                print " message causing probelm: "
                print fields
                raise ValueError(err)
            else:
#                print "fields as string:",fields
                # convert argument list of bytearray to list of hex string
                for i, f in enumerate(fields[1:]):
                    received.append(self._recv_methods[arg_format_list[i]](str(f)))
             
                # Record the time the message arrived
                message_time = time.time()
                self.response_to_command(cmd_name, received, message_time)


    def response_to_command(self, cmd_name, msg, message_time):
        raise NotImplementedError("response_to_command needs to be overwritten by subclass!")


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


    





