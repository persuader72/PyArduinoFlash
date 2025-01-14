#!/usr/bin/python

"""Arduino flash memory utility.
   It is used to write / verify and read the flash memory of an Arduino board.
   The input / output file format is Intel Hexadecimal."""

VERSION = '0.3.0'

import argparse
import sys

from intelhex import IntelHex
from intelhex import AddressOverlapError, HexRecordError
from arduinobootloader import ArduinoBootloader
import progressbar

parser = argparse.ArgumentParser(description="arduino flash utility")
group = parser.add_mutually_exclusive_group()
parser.add_argument("filename", help="filename in hexadecimal Intel format")
parser.add_argument("--version", action="store_true", help="script version")
parser.add_argument("-e", "--eeprom", action="store_true", help="program eeprom")
parser.add_argument("-d", "--device", help="specify the device. Use net: for TCP connection")
parser.add_argument("-b", "--baudrate", type=int, required=True, help="old bootolader (57600) Optiboot (115200)")
parser.add_argument("-p", "--programmer", required=True, help="programmer version - Nano (Stk500v1) Mega (Stk500v2)")
group.add_argument("-r", "--read", action="store_true", help="read the cpu flash memory")
group.add_argument("-u", "--update", action="store_true", help="update cpu flash memory")
args = parser.parse_args()

if args.version:
    print("version {}".format(VERSION))

if args.update:
    print("update Arduino firmware with filename: {}".format(args.filename))
elif args.read:
    print("read the Arduino firmware and save in filename: {}".format(args.filename))
else:
    parser.print_help()
    sys.exit()

ih = IntelHex()
ab = ArduinoBootloader()

prg = ab.select_programmer(args.programmer)
if prg is None:
    print("programmer version unsupported: {}".format(args.programmer))
    sys.exit()


def exit_by_error(msg):
    print("\nerror, {}".format(msg))
    prg.leave_bootloader()
    prg.close()
    sys.exit(0)


if prg.open(port=args.device, speed=args.baudrate):
    print("AVR device initialized and ready to accept instructions")
    address = 0
    if not prg.board_request():
        exit_by_error(msg="board request")

    print("bootloader: {} version: {} hardware version: {}".format(ab.programmer_name,\
                                                                   ab.sw_version, ab.hw_version))

    if not prg.cpu_signature():
        exit_by_error(msg="cpu signature")

    print("cpu name: {}".format(ab.cpu_name))

    page_size = ab.cpu_page_size if not args.eeprom else ab.eeprom_page_size
    if args.update:
        print("reading input file: {}".format(args.filename))

        try:
            ih.fromfile(args.filename, format='hex')
        except FileNotFoundError:
            exit_by_error(msg="file not found")
        except (AddressOverlapError, HexRecordError):
            exit_by_error(msg="error, file format")

        print("writing {}: {} bytes".format("flash" if not args.eeprom else "eeprom", ih.maxaddr()))
        bar = progressbar.ProgressBar(maxval=ih.maxaddr())
        bar.start()
        for address in range(0, ih.maxaddr(), page_size):
            buffer = ih.tobinarray(start=address, size=page_size)
            if not prg.write_memory(buffer, address, flash=not args.eeprom):
                exit_by_error(msg="writing {} memory".format("flash" if not args.eeprom else "eeprom"))

            bar.update(address)

        bar.finish()

    dict_hex = dict()

    if args.update:
        max_address = ih.maxaddr()
        print("reading and verifying {} memory".format("flash" if not args.eeprom else "eeprom"))

    elif args.read:
        if not args.eeprom:
            max_address = int(ab.cpu_page_size * ab.cpu_pages)
        else:
            max_address = int(ab.eeprom_page_size * ab.eeprom_pages)
        print("reading {} memory".format("flash" if not args.eeprom else "eeprom"))
    else:
        max_address = 0
        page_size = 0

    bar = progressbar.ProgressBar(maxval=max_address)
    bar.start()

    for address in range(0, max_address, page_size):
        read_buffer = prg.read_memory(address, page_size, flash=not args.eeprom)
        if read_buffer is None:
            exit_by_error(msg="reading {} memory".format("flash" if not args.eeprom else "eeprom"))

        if args.update:
            if read_buffer != ih.tobinarray(start=address, size=page_size):
                exit_by_error(msg="file not match")
        elif args.read:
            for i in range(0, page_size):
                dict_hex[address + i] = read_buffer[i]

        bar.update(address)

    bar.finish()

    if args.read:
        dict_hex["start_addr"] = 0
        ih.fromdict(dict_hex)
        try:
            ih.tofile(args.filename, 'hex')
        except FileNotFoundError:
            exit_by_error(msg="the file cannot be created")

    print("\nprogram done, thank you")

    prg.leave_bootloader()
    prg.close()
else:
    print("error, could not connect with arduino board - baudrate: {}".format(args.baudrate))
