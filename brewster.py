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
# Database location
dbpath='/var/lib/brew'
dbname='brew.db'

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
        self.devices = []

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
        self.devices.append(dev.addr)

class BrewDB():
    def __init__(self, path, dbname):
        global sqlite3
        import sqlite3
        self.dbpath = path
        self.dbn = path + '/' + dbname
        self.db = {}
        self.cur = {}

    def open_db(self):
        try:
            self.db = sqlite3.connect(self.dbn)
            self.cur = self.db.cursor()
        except:
            e = sys.exc_info()[0]
            print ("Exception: %s"% e)
            print ("Could not connect to the database: %s!" % self.dbn)
            sys.exit(2)
        
    def create_db(self):
        try:
            if os.path.exists(self.dbpath) == False:
                os.mkdir(self.dbpath, 0777)
                os.chmod(self.dbpath, 0777)
            mydb = sqlite3.connect(self.dbn)
            dbcur = mydb.cursor()
            dbcur.execute('create table brewometers(d_id INTEGER PRIMARY KEY, adr TEXT, color TEXT, name TEXT, brew_id INTEGER )')
            mydb.commit()
            dbcur.execute('create table brews(brew_id INTEGER PRIMARY KEY, d_id INTEGER, name TEXT, started_time INTEGER, started_time_txt TEXT, stopped_time INTEGER, stopped_time_txt TEXT, last_update TEXT )')
            mydb.commit()
            dbcur.execute('create table measurements(d_id INTEGER, brew_id INTEGER, timestamp INTEGER, timestamp_txt TEXT, temp REAL, grav_meas INTEGER, grav_calc REAL, battery REAL )')
            mydb.commit()
            mydb.close()
            os.chmod(self.dbn,0666)
        except:
            e = sys.exc_info()[0]
            print ("Exception: %s"% e)
            print ("Could not create database. Plese run: sudo brewster.py -s -db")
            sys.exit(1)

    def has_device(self, address):
        self.cur.execute("SELECT d_id FROM brewometers WHERE adr = ?", (address,))
        item = self.cur.fetchone()
        data = 0
        if item:
            data = item[0]
        return data

    def get_device_info(self, dev_num):
        data = self.db.execute("SELECT name,color,brew_id FROM brewometers WHERE d_id = ?",(dev_num,))
        rv = []
        for d in data:
            rv.append(d[0])
            rv.append(d[1])
            rv.append(d[2])
        return rv

    def get_active_devices(self):
        data = self.db.execute("SELECT adr FROM brewometers WHERE brew_id > 0")
        rv = []
        for d in data:
            rv.append(d[0])
        return rv

    def add_device(self, address, color, name):
        self.cur.execute("SELECT MAX(d_id) AS d_id FROM brewometers")
        max_id = self.cur.fetchone()[0]
        if max_id:
            max_id = 1 + max_id
        else:
            max_id = 1
        self.cur.execute("INSERT INTO brewometers values(?,?,?,?,?)", (max_id, address, color, name, 0))
        self.db.commit()
        return max_id

    def start_new_brew(self, d_id, b_name):
        time = datetime.datetime.now()
        s_time = time.strftime('%Y-%m-%d %H:%M')
        u_time = int(time.strftime("%s"))

        self.cur.execute("SELECT MAX(brew_id) AS brew_id FROM brews")
        max_id = self.cur.fetchone()[0]
        if max_id:
            max_id = 1 + max_id
        else:
            max_id = 1
        self.cur.execute("INSERT INTO brews values(?,?,?,?,?,0,'','')", (max_id, d_id, b_name, u_time, s_time))
        self.db.commit()
        self.cur.execute('UPDATE brewometers SET brew_id = ? WHERE d_id = ?', (max_id, d_id))
        self.db.commit()

    def brew_id_on_dev(self, d_id):
        self.cur.execute("SELECT brew_id FROM brewometers WHERE d_id = ?", (d_id,))
        brew_id = self.cur.fetchone()[0]
        return brew_id 

    def stop_brew(self, d_id):
        time = datetime.datetime.now()
        s_time = time.strftime('%Y-%m-%d %H:%M')
        u_time = int(time.strftime("%s"))

        brew_id = self.brew_id_on_dev(d_id)

        self.cur.execute('UPDATE brewometers SET brew_id = 0 WHERE d_id = ?', (d_id,))
        self.db.commit()

        if brew_id and brew_id > 0:
            self.cur.execute('UPDATE brews SET stopped_time = ?, stopped_time_txt = ? WHERE brew_id = ?', (u_time, s_time, brew_id))
            self.db.commit()

    def timestamp_brew(self, brew_id):
        time = datetime.datetime.now()
        s_time = time.strftime('%Y-%m-%d %H:%M')

        if brew_id and brew_id > 0:
            self.cur.execute('UPDATE brews SET last_update = ? WHERE brew_id = ?', (s_time, brew_id))
            self.db.commit()

    def update_measurement(self, adr, info):
        (u_time, s_time, d_type, d_temp, grav_meas, grav_calc, batt) = info
        batt_volt = Battery_Value(batt)
        d_id = self.has_device(adr)
        brew_id = self.brew_id_on_dev(d_id)
        self.timestamp_brew(brew_id)
        self.cur.execute("INSERT INTO measurements values(?,?,?,?,?,?,?,?)", (d_id, brew_id, u_time, s_time, d_temp, grav_meas, grav_calc, batt_volt))
        self.db.commit()
        return
        
    def print_device_info(self, doall):
        if (doall):
            self.cur.execute('SELECT d_id, adr, color, name, brew_id FROM brewometers')
        else:
            self.cur.execute('SELECT d_id, adr, color, name, brew_id FROM brewometers WHERE brew_id > 0')
        for binfo in self.cur.fetchall():
            (d_id, adr, color, name, brew_id) = binfo
            string = 'Brewometer #' + str(d_id) + ' "' + ANSI_RED + name + ANSI_OFF + '" (' + adr.decode('utf-8') + ')' 
            if brew_id > 0:
                string += ' Running brew number ' + str(brew_id)
            print (string)
        return

    def print_brew_info(self, doall):
        if (doall):
            self.cur.execute('SELECT brew_id, name, started_time_txt, last_update FROM brews')
        else:
            self.cur.execute('SELECT brews.brew_id, brews.name, started_time_txt, last_update FROM brews INNER JOIN brewometers ON brews.brew_id = brewometers.brew_id')
        for binfo in self.cur.fetchall():
            (brew_id, name, started_time_txt, last_update) = binfo
            if last_update == '':  last_update = 'N/A' 
            string = 'Brew #' + str(brew_id) + ' "' + ANSI_RED + name + ANSI_OFF + '" started: ' + started_time_txt + ', last updated: ' + last_update
            print (string)
        return
        
# end class BrewDB

def Read_Device(address):
    try:
        dev = btle.Peripheral(address)
        b_type = dev.readCharacteristic( 0x33 )
        b_temp = dev.readCharacteristic( 0x37 )
        b_angle = dev.readCharacteristic( 0x3b )
        b_batt = dev.readCharacteristic( 0x48 )
    except:
        #print ("Problem reading device!")
        return

    time = datetime.datetime.now()
    s_time = time.strftime('%Y-%m-%d %H:%M')
    u_time = int(time.strftime("%s"))

    grav_meas = struct.unpack('B', b_angle[0])[0]
    if len(b_angle) > 1:
        grav_meas += (256 * struct.unpack('B', b_angle[1])[0])
    grav_calc = convert_data_to_gravity(grav_meas)

    dev.disconnect()
    return (u_time, s_time, ord(b_type[0]), ord(b_temp[0]), grav_meas, grav_calc, ord(b_batt[0]))

def Battery_Value(batt):
    return 1.95 + (3.53 - 1.95) * batt/100.0

def PrintDevice(info_list):
    (u_time, s_time, b_type, temp, angle, grav, batt) = info_list

    print ("Utime: ", u_time)
    print ("Time: ", s_time)
    print ("Type: ", b_type)
    print ("Temperature: ", temp)
    print ("Measured: ", angle)
    print ("Gravity: ", format(grav,'0.3f'))
    print ("Battery: ", Battery_Value(batt), "V")
    print

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--scan', action='store_true',
                        help='Discover all available Brewometers. Must run as root!')
    parser.add_argument('-a', '--addr', action='store', type=str, 
                        default="",
                        help='Read specified device. Get ADDR by running: sudo brewster.py -s')
    parser.add_argument('-i', '--info', action='store', type=str,
                        help='Query database. Use: [-i devs | -i alldevs] for devices, [-i brews | -i allbrews ] for brews.')
    parser.add_argument('-db', '--dbase', action='store_true', 
                        help='Store scanned data in sqlite database file.')
    parser.add_argument('-bon', '--brew-on', type=int, default=0,
                        help='Start a new brew scan on the specified device.')
    parser.add_argument('-boff', '--brew-off', type=int, default=0,
                        help='Stop a brew scan on the specified device.')
    arg = parser.parse_args(sys.argv[1:])

    # BON and BOFF infer -db
    if arg.brew_on != 0 or arg.brew_off != 0 or arg.info != "":
        arg.dbase = 1

    # Some option must be turned on
    if arg.scan == 0 and arg.addr == "" and arg.dbase == 0:
        print ("Try this: brewster.py -h")
        return

    # Initialize or create the database, if -db was specified
    if arg.dbase != 0:
        BDB = BrewDB(dbpath,dbname)
        if os.path.exists(BDB.dbn) == False:
            BDB.create_db()
        BDB.open_db()

    # New device scan was requested. List all available devices, and optionally add them to the database
    if arg.scan == 1:
        try:
            myscan = ScanPrint(arg)
            scanner = btle.Scanner().withDelegate(myscan)
            print (ANSI_RED + "Scanning for devices..." + ANSI_OFF)
            devices = scanner.scan(5)
        except:
            print ("Could not scan. Are you running as root (sudo)?")
            return
        if arg.dbase != 0:
            for dev in myscan.devices:
                d_id = BDB.has_device(dev)
                if d_id:
                    (name, color, brew_id) = BDB.get_device_info(d_id)
                    print ("I already know about '", name, "':", dev, ", it is brewometer number", d_id)
                else:
                    print ("Found a new device ", dev)
                    d_color = raw_input('Tell me its color:')
                    d_name = raw_input('Give it a name:')
                    d_num = BDB.add_device(dev, d_color, d_name)
                    print ("It will be device number %d" % d_num)
        return

    # Direct read mode. Look for a specified device and print out its info
    if arg.addr != "":
        print ("Reading Brewometer:", ANSI_CYAN + arg.addr + ANSI_OFF)
        r_vals = Read_Device(arg.addr)
        if r_vals:
            PrintDevice(r_vals)
        else:
            print ("Could not read device")
        return

    # Start brew scan
    if arg.brew_on != 0:
        d_id = arg.brew_on
        dv = BDB.get_device_info(d_id)
        if dv:
            (name, color, brew_id) = dv
            print ("Starting a new brew on [", name, "], device", d_id)
            b_name = raw_input('Give it a good descriptive name:')
            BDB.start_new_brew(d_id, b_name)
        else:
            print ("Could not find device", d_id, "in database, try scanning for new devices.")
        return

    # Stop brew scan
    if arg.brew_off != 0:    
        d_id = arg.brew_off
        dv = BDB.get_device_info(d_id)
        if dv:
            (name, color, brew_id) = dv
            print ("Stopping a brew on [", name, "], device", d_id)
            BDB.stop_brew(d_id)
        else:
            print ("Could not find device", d_id, "in database, try scanning for new devices.")
        return

    # Database query mode.
    if arg.info:
        if arg.info == "devs" or arg.info == "alldevs":
            doall = False
            if arg.info == "alldevs":
                doall = True 
                print ("Known devices:")
            else:
                print ("Enabled devices:")
            BDB.print_device_info(doall)
        elif arg.info == "brews" or arg.info == "allbrews":
            doall = False
            if arg.info == "allbrews":
                doall = True 
                print ("All brews:")
            else:
                print ("Known brews:")
            BDB.print_brew_info(doall)
        else:
            print ("Strange argument:", arg.info)
        return

    # Database update mode. Look for all registered devices, try to connect to them and save measured data
    if arg.dbase != 0:
        for dd in BDB.get_active_devices():
            #print ("Reading dd", dd)
            r_vals = Read_Device(dd)
            if r_vals:
                #PrintDevice(r_vals)
                BDB.update_measurement(dd, r_vals)
            else:
                print ("Could not read device")
        return

if __name__ == "__main__":
    main()

