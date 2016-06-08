#!/usr/bin/env python
from __future__ import print_function
import argparse
import binascii
import time
import os
import sys
import struct
from bluepy import btle
import numpy as np
import datetime

# Calibration values: measurements
cal_x=np.array([8,21,34,88,99,168])
# Calibration values: matching gravity
cal_y=np.array([0.988,1,1.014,1.069,1.08,1.147])

A=np.vstack([cal_x, np.ones(len(cal_x))]).T
fit_m,fit_c = np.linalg.lstsq(A,cal_y)[0]

def convert_data_to_gravity(in_data):
    return fit_m*in_data+fit_c


if os.getenv('C','1') == '0':
    ANSI_RED = ''
    ANSI_GREEN = ''
    ANSI_YELLOW = ''
    ANSI_CYAN = ''
    ANSI_WHITE = ''
    ANSI_OFF = ''
else:
    ANSI_CSI = "\033["
    ANSI_RED = ANSI_CSI + '31m'
    ANSI_GREEN = ANSI_CSI + '32m'
    ANSI_YELLOW = ANSI_CSI + '33m'
    ANSI_CYAN = ANSI_CSI + '36m'
    ANSI_WHITE = ANSI_CSI + '37m'
    ANSI_OFF = ANSI_CSI + '0m'

def dump_services(dev):
    services = sorted(dev.getServices(), key=lambda s: s.hndStart)
    for s in services:
        print ("\t%04x: %s" % (s.hndStart, s))
        if s.hndStart == s.hndEnd:
            continue
        chars = s.getCharacteristics()
        for i, c in enumerate(chars):
            props = c.propertiesToString()
            h = c.getHandle()
            if 'READ' in props:
                val = c.read()
                if c.uuid == btle.AssignedNumbers.device_name:
                    string = ANSI_CYAN + '\'' + val.decode('utf-8') + '\'' + ANSI_OFF
                elif c.uuid == btle.AssignedNumbers.device_information:
                    string = repr(val)
                else:
                    string = '<s' + binascii.b2a_hex(val).decode('utf-8') + '>'
            else:
                string=''
            print ("\t%04x:    %-59s %-12s %s" % (h, c, props, string))

            while True:
                h += 1
                if h > s.hndEnd or (i < len(chars) -1 and h >= chars[i+1].getHandle() - 1):
                    break
                try:
                    val = dev.readCharacteristic(h)
                    print ("\t%04x:     <%s>" % (h, binascii.b2a_hex(val).decode('utf-8')))
                except btle.BTLEException:
                    break

class ScanPrint(btle.DefaultDelegate):
    def __init__(self, opts):
        btle.DefaultDelegate.__init__(self)
        self.opts = opts

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if dev.rssi < -128:
            return

        if dev.getValueText(9) != 'Brew':
            return

          
        print ('    Brew Device : %s (%s), %d dBm %s' % 
                  (
                   ANSI_CYAN + dev.addr + ANSI_OFF,
                   dev.addrType,
                   dev.rssi,
                   ('' if dev.connectable else '(not connectable)') )
              )
        print

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--scan', action='store_true',
                        help='Discover all available Brewometers. Must run as root!')
    parser.add_argument('-a', '--addr', action='store', type=str, 
                        default="",
                        help='Read specified device. Get ADDR by running: sudo brewster.py -s')
    arg = parser.parse_args(sys.argv[1:])
    if arg.scan == 0 and arg.addr == "":
        print ("Try this: brewster.py -h")
        return

    if arg.scan == 1:
        try:
            scanner = btle.Scanner().withDelegate(ScanPrint(arg))
            print (ANSI_RED + "Scanning for devices..." + ANSI_OFF)
            devices = scanner.scan(5)
        except:
            print ("Could not scan. Are you running as root (sudo)?")
            return

    if arg.addr != "":
        print ("Reading Brewometer:", ANSI_CYAN + arg.addr + ANSI_OFF)

        try:
            dev = btle.Peripheral(arg.addr)
            b_type = dev.readCharacteristic( 0x33 )
            b_temp = dev.readCharacteristic( 0x37 )
            b_angle = dev.readCharacteristic( 0x3b )
            b_batt = dev.readCharacteristic( 0x48 )
        except:
            print ("Problem reading device!")
            return

        print ("Time: ", datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
        print ("Type: ", ord(b_type[0]))
        print ("Temperature: ", ord(b_temp[0]))

        grav_meas = struct.unpack('B', b_angle[0])[0]
        if len(b_angle) > 1:
            grav_meas += (256 * struct.unpack('B', b_angle[1])[0])
        grav_calc = convert_data_to_gravity(grav_meas)
        print ("Measured: ", grav_meas)
        print ("Gravity: ", format(grav_calc,'0.3f'))
        print ("Battery: ", int(100*(ord(b_batt[0])/255.0)), "%")

        dev.disconnect()
        print


if __name__ == "__main__":
    main()

