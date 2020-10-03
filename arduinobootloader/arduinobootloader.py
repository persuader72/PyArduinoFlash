'''
Is a Python Class for updating the firmware of Arduino boards that use
Atmel AVR CPUs.
For example Arduino Nano, Uno, Mega.

The module implements the essential parts that Avrdude uses for the
arduino and wiring protocols. In turn, they are a subset of the
STK500 V1 and V2 protocols respectively.
'''

import serial
import serial.tools.list_ports
import time

"""Constants for the Stk500v1 protocol"""
RESP_STK_OK = 0x10
RESP_STK_IN_SYNC = 0x14

""" The dictionary key is made up of SIG1, SIG2 and SIG3
    The value is a list with the name of the CPU the page size in byte 
    and the flash pages.
"""
AVR_ATMEL_CPUS = {0x1E9608: ["ATmega640", (128*2), 1024],
                  0x1E9802: ["ATmega2561", (128*2), 1024],
                  0x1E9801: ["ATmega2560", (128*2), 1024],
                  0x1E9703: ["ATmega1280", (128*2), 512],
                  0x1E9705: ["ATmega1284P", (128*2), 512],
                  0x1E9704: ["ATmega1281", (128*2), 512],
                  0x1E9782: ["AT90USB1287", (128 * 2), 512],
                  0x1E9702: ["ATmega128", (128*2), 512],
                  0x1E9602: ["ATmega64", (128*2), 256],
                  0x1E9502: ["ATmega32", (64*2), 256],
                  0x1E9403: ["ATmega16", (64*2), 128],
                  0x1E9307: ["ATmega8", (32 * 2), 128],
                  0x1E930A: ["ATmega88", (32*2), 128],
                  0x1E9406: ["ATmega168", (64*2), 256],
                  0x1E950F: ["ATmega328P", (64*2), 256],
                  0x1E9514: ["ATmega328", (64*2), 256],
                  0x1E9404: ["ATmega162", (64*2), 128],
                  0x1E9402: ["ATmega163", (64*2), 128],
                  0x1E9405: ["ATmega169", (64*2), 128],
                  0x1E9306: ["ATmega8515", (32*2), 128],
                  0x1E9308: ["ATmega8535", (32*2), 128]}


"""STK message constants for Stk500v2"""
MESSAGE_START = 0x1B        # = ESC = 27 decimal
TOKEN = 0x0E
STATUS_CMD_OK = 0x00

"""Supported Commands for the Stk500v2 Protocol"""
CMD_SIGN_ON = 0x01
CMD_GET_PARAMETER = 0x03
CMD_SPI_MULTI = 0x1D
CMD_LOAD_ADDRESS = 0x06
CMD_PROGRAM_FLASH_ISP = 0x13
CMD_READ_FLASH_ISP = 0x14
CMD_LEAVE_PROGMODE_ISP = 0x11

"""Options for get parameter"""
OPT_HW_VERSION = b'\x90'
OPT_SW_MAJOR = b'\x91'
OPT_SW_MINOR = b'\x92'

"""Index for CPU signatures"""
CPU_SIG1 = 0
CPU_SIG2 = 1
CPU_SIG3 = 2

class ArduinoBootloader(object):
    """Contains the two inner classes that support the Stk500 V1 and V2 protocols
    for comunicate with arduino bootloaders.

    Usage: ab = ArduinoBooloader()

           # For Nano or Uno
           ab.select_protocol("Stk500v1")
           # For Mega 2560
           ab.select_protocol("Stk500v2")

           prg.open(speed=115200)
           prg.board_request()
           prg.cpu_signature()
           prg.write_memory(data, ab._cpu_page_size)
           prg.leave_bootloader()
           prg.close
    """
    def __init__(self, *args, **kwargs):
        self.device = None
        self.port = None
        self._hw_version = 0
        self._sw_major = 0
        self._sw_minor = 0
        self._cpu_name = ""
        self._cpu_page_size = 0
        self._cpu_pages = 0
        self._programmer_name = ""
        self._programmer = None

    @property
    def hw_version(self):
        return str(self._hw_version)

    @property
    def sw_version(self):
        return "{}.{}".format(self._sw_major, self._sw_minor)

    @property
    def cpu_name(self):
        return self._cpu_name

    @property
    def cpu_page_size(self):
        return self._cpu_page_size

    @property
    def cpu_pages(self):
        return self._cpu_pages

    @property
    def programmer_name(self):
        return self._programmer_name

    def select_programmer(self, type):
        """Select the communication protocol to connect with the Arduino bootloader."""
        if type == "Stk500v1":
            self._programmer = self.Stk500v1(self)
        elif type == "Stk500v2":
            self._programmer = self.Stk500v2(self)
        else:
            self._programmer = None

        return self._programmer

    def _is_cpu_signature(self, signature):
        """See if the signature corresponds to any of the Atmel CPUs that use the Arduino boards."""
        try:
            list_cpu = AVR_ATMEL_CPUS[signature]
            self._cpu_name = list_cpu[0]
            self._cpu_page_size = list_cpu[1]
            self._cpu_pages = list_cpu[2]
            return True
        except KeyError:
            self._cpu_name = "signature: {:06x}".format(signature)
            self._cpu_page_size = 0
            self._cpu_pages = 0
            return False

    def _find_device_port(self):
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if ("VID:PID=1A86:7523" in port.hwid) or ("VID:PID=2341:0043" in port.hwid):
                return port.device
        return ""

    def open(self, port=None, speed=115200):
        """ Find and open the communication port where the Arduino is connected.
        Generate the reset sequence with the DTR / RTS pins.
        Send the sync command to verify that there is a valid bootloader.
        """
        if not port:
            port = self._find_device_port()

        if not port:
            return False
        else:
            self.device = serial.Serial(port, speed, 8, 'N', 1, timeout=1)

        self.port = port

        ''' Clear DTR and RTS to unload the RESET capacitor of the Arduino boards'''
        self.device.dtr = True
        self.device.rts = True
        time.sleep(1 / 20)
        ''' Set DTR and RTS back to high '''
        self.device.dtr = False
        self.device.rts = False
        time.sleep(1 / 20)

        """Discards bytes generated by the initialization sequence."""
        self.device.reset_input_buffer()
        return True

    def close(self):
        """Close the serial communication port."""
        if self.device.is_open:
            self.device.close()
            self.device = None

    class Stk500v1(object):
        """It encapsulates the communication protocol that Arduino uses for the first
           versions of bootoloader, which can write up to 128 K bytes of flash memory.
           For example: Nano, Uno, etc
           The older version (ATmegaBOOT_168.c) works at 57600 baudios,
           the new version (OptiBoot) at 115200"""
        def __init__(self, ab):
            self._ab = ab
            self._answer = None

        def open(self, port=None, speed=57600):
            """Find and open the communication port where the Arduino is connected.
               Generate the reset sequence with the DTR / RTS pins.
               Send the sync command to verify that there is a valid bootloader."""
            if self._ab.open(port, speed):
                return self.get_sync()

            return False

        def close(self):
            """Close the communication port."""
            self._ab.close()

        def get_sync(self):
            """Send the sync command whose function is to discard the reception buffers of both serial units.
              The first time you send the sync command to get rid of the line noise with a 500mS timeout.
            """
            self._ab.device.timeout = 1 / 2
            for i in range(1, 5):
                if self._cmd_request(b"0 ", answer_len=2):
                    self._ab.device.timeout = 1
                    return True
            return False

        def board_request(self):
            """Get the firmware and hardware version of the bootloader."""
            if not self._cmd_request(b"A\x80 ", answer_len=3):
                return False

            self._ab._hw_version = self._answer[1]

            if not self._cmd_request(b"A\x81 ", answer_len=3):
                return False

            self._ab._hw_version = self._answer[1]

            if not self._cmd_request(b"A\x82 ", answer_len=3):
                return False

            self._ab._sw_minor = self._answer[1]

            """As the Optiboot does not implement the STK_GET_SIGN_ON command and it always 
            returns 0x14 0x10, the function send command without checking the length of the 
            response is used."""
            if not self._cmd_request_no_len(b"1 ", answer_len=7):
                return False

            """The name of the programmer is between the beginning and end of the frame."""
            name = bytearray(self._answer)
            del name[-1]
            del name[0]
            self._ab._programmer_name = name.decode("utf-8")

            return True

        def cpu_signature(self):
            """Get CPU information: name, size and count of the flash memory pages"""
            if self._cmd_request(b"u ", answer_len=5):
                return self._ab._is_cpu_signature((self._answer[1] << 16) | (self._answer[2] << 8) | self._answer[3])
            return False

        def write_memory(self, buffer, address, flash=True):
            """Write the buffer to the requested address of the flash memory or eeprom."""

            if self._set_address(address, flash):
                buff_len = len(buffer)

                cmd = bytearray(4)
                cmd[0] = ord('d')
                cmd[1] = ((buff_len >> 8) & 0xFF)
                cmd[2] = (buff_len & 0xFF)
                cmd[3] = ord('F') if flash else ord('E')

                cmd.extend(buffer)
                cmd.append(ord(' '))

                return self._cmd_request(cmd, answer_len=2)
            return False

        def read_memory(self, address, count, flash=True):
            """Read flash or eeprom memory from requested address."""

            if self._set_address(address, flash):
                cmd = bytearray(5)
                cmd[0] = ord('t')
                cmd[1] = ((count >> 8) & 0xFF)
                cmd[2] = (count & 0xFF)
                cmd[3] = ord('F') if flash else ord('E')
                cmd[4] = ord(' ')

                if self._cmd_request(cmd, answer_len=count+2):
                    # The answer start with RESP_STK_IN_SYNC and finish with RESP_STK_OK
                    buffer = bytearray(self._answer[1:count+1])

                    return buffer
            return None

        def _set_address(self, address, flash):
            """The address flash are in words, and the eeprom in bytes."""
            if flash:
                address = int(address / 2)

            """The address is in little endian format"""
            cmd = bytearray(4)
            cmd[0] = ord('U')
            cmd[1] = (address & 0xFF)
            cmd[2] = ((address >> 8) & 0xFF)
            cmd[3] = ord(' ')

            return self._cmd_request(cmd, answer_len=2)

        def leave_bootloader(self):
            """Tells the bootloader to leave programming mode and start executing the stored firmware"""
            return self._cmd_request(b"Q ", answer_len=2)

        def _cmd_request_no_len(self, msg, answer_len):
            """Send and receive a command in stk500v1 format", but don't check the answer len"""
            if self._ab.device:
                self._ab.device.write(msg)
                self._answer = self._ab.device.read(answer_len)

                """If the answer has at least two characters, check that the first and last 
                corresponds to the start and end sentinel."""
                if len(self._answer) >= 2 and \
                        self._answer[0] == RESP_STK_IN_SYNC and self._answer[-1] == RESP_STK_OK:
                    return True
            return False

        def _cmd_request(self, msg, answer_len):
            """Send and receive a command in stk500v1 format
            verifies that the response size matches what is expected."""
            if self._cmd_request_no_len(msg, answer_len):
                return len(self._answer) == answer_len

            return False

    class Stk500v2(object):
        """It encapsulates the communication protocol that Arduino uses in bootloaders
        with more than 128K bytes of flash memory. For example: Mega 2560 etc"""
        def __init__(self, ab):
            self._ab = ab
            self._answer = None
            self._sequence_number = 0

        def open(self, port=None, speed=115200):
            """Find and open the communication port where the Arduino is connected.
               Generate the reset sequence with the DTR / RTS pins.
               Send the sync command to verify that there is a valid bootloader."""
            if self._ab.open(port, speed):
                return self.get_sync()

            return False

        def close(self):
            """Close the communication port."""
            self._ab.close()

        def get_sync(self):
            """Send the sync command"""
            if self._send_command(CMD_SIGN_ON):
                if self._recv_answer(CMD_SIGN_ON):
                    prog_name_len = self._answer[0]
                    del self._answer[0]

                    self._ab._programmer_name = self._answer.decode("utf-8")
                    return True
            return False

        def board_request(self):
            """Get the firmware and hardware version of the bootloader."""

            if not self._get_params(OPT_HW_VERSION):
                return False

            self._ab._hw_version = self._answer[0]

            if not self._get_params(OPT_SW_MAJOR):
                return False

            self._ab._hw_version = self._answer[0]

            if not self._get_params(OPT_SW_MINOR):
                return False

            self._ab._sw_minor = self._answer[0]

            return True

        def cpu_signature(self):
            """Get CPU information: name, size and count of the flash memory pages"""
            signature = 0
            if not self._get_signature(CPU_SIG1):
                return False
            signature = (self._answer[3] << 16)

            if not self._get_signature(CPU_SIG2):
                return False
            signature |= (self._answer[3] << 8)

            if not self._get_signature(CPU_SIG3):
                return False
            signature |= self._answer[3]

            return self._ab._is_cpu_signature(signature)

        def write_memory(self, buffer, address, flash=True):
            """Write the buffer to the requested address of the flash memory or eeprom."""

            if self._load_address(address, flash):
                buff_len = len(buffer)

                msg = bytearray(9)
                msg[0] = ((buff_len >> 8) & 0xFF)
                msg[1] = (buff_len & 0xFF)
                msg.extend(buffer)
                """The seven bytes preceding the data are not used."""
                if self._send_command(CMD_PROGRAM_FLASH_ISP, msg):
                    return self._recv_answer(CMD_PROGRAM_FLASH_ISP)
            return False

        def read_memory(self, address, count, flash=True):
            """Read flash or eeprom memory from requested address."""

            if self._load_address(address, flash):
                msg = bytearray(3)
                msg[0] = ((count >> 8) & 0xFF)
                msg[1] = (count & 0xFF)
                """The third byte is not used"""
                if self._send_command(CMD_READ_FLASH_ISP, msg):
                    if self._recv_answer(CMD_READ_FLASH_ISP):
                        """The end of data is marked with STATUS_OK"""
                        if self._answer[-1] == STATUS_CMD_OK:
                            del self._answer[-1]
                            return self._answer
            return None

        def leave_bootloader(self):
            """Tells the bootloader to leave programming mode and start executing the stored firmware"""
            msg = bytearray(3)
            if self._send_command(CMD_LEAVE_PROGMODE_ISP, msg):
                return self._recv_answer(CMD_LEAVE_PROGMODE_ISP)

            return False

        def _load_address(self, address, flash):
            """The address flash are in words, and the eeprom in bytes."""
            if flash:
                address = int(address / 2)

            msg = bytearray(4)
            msg[0] = (((address >> 24) & 0xFF) | 0x80)
            msg[1] = ((address >> 16) & 0xFF)
            msg[2] = ((address >> 8) & 0xFF)
            msg[3] = (address & 0xFF)

            if self._send_command(CMD_LOAD_ADDRESS, msg):
                return self._recv_answer(CMD_LOAD_ADDRESS)
            return False

        def _get_signature(self, index):
            """Implement a subcommand of CMD_SPI_MULTI to get the processor signature."""
            msg = bytearray(6)
            msg[3] = ord('0') # Get signature
            msg[5] = index

            if self._send_command(CMD_SPI_MULTI, msg):
                return self._recv_answer(CMD_SPI_MULTI)
            return False

        def _get_params(self, option):
            """Bootloader information"""
            if self._send_command(CMD_GET_PARAMETER, option):
                return self._recv_answer(CMD_GET_PARAMETER)
            return False

        def _inc_sequence_numb(self):
            """Controls the overflow of the sequence number (8 bits)"""
            self._sequence_number += 1
            if self._sequence_number > 0xFF:
                self._sequence_number = 0

        def _send_command(self, cmd, data=None):
            """The command have two parts: a fixed header of 5 bytes, and the data with the checksum."""
            if self._ab.device:
                self._inc_sequence_numb()

                buff = bytearray(5)
                checksum = 0
                data_len = 1 if data is None else len(data) + 1

                buff[0] = MESSAGE_START
                buff[1] = self._sequence_number
                buff[2] = ((data_len >> 8) & 0xFF)
                buff[3] = (data_len & 0xFF)
                buff[4] = TOKEN
                buff.append(cmd)
                if not data is None:
                    buff.extend(data)

                for val in buff:
                    checksum ^= val

                buff.append(checksum)

                self._ab.device.write(buff)
                return True
            return False

        def _recv_answer(self, cmd):
            """The response have a fixed size header that inform the data len, and the
            first two bytes of the data contain the command and the operation status."""
            head = self._read_headear()
            if not head is None:
                """Add one because the length does not include the checksum byte"""
                len_data = ((head[1] << 8) | head[2]) + 1
                """The minimum response contains the command and the status of the operation."""
                if len_data >= 3:
                    self._answer = bytearray(self._ab.device.read(len_data))
                    if len(self._answer) == len_data and\
                        self._answer[0] == cmd and self._answer[1] == STATUS_CMD_OK:
                        answ_chk = self._answer[-1]
                        del self._answer[-1]

                        head.extend(self._answer)

                        """The head don't include the START_MESSAGE byte"""
                        checksum = MESSAGE_START
                        for val in head:
                            checksum ^= val
                        """Discards the command and status from the response"""
                        del self._answer[0]
                        del self._answer[0]

                        """The answer is valid when the checksums match"""
                        return checksum == answ_chk
            return False

        def _read_headear(self):
            """Wait for the reception of the beginning of frame byte"""
            for i in range(1, 10):
                """The header is valid, when the trailing byte sequence number and token match."""
                start = self._ab.device.read(1)
                if len(start) >= 1 and start[0] == MESSAGE_START:
                    head = bytearray(self._ab.device.read(4))
                    if len(head) == 4 and head[3] == TOKEN and self._sequence_number == head[0]:
                        return head
            return None