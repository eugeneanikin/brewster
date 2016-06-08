# brewster
Really inofficial brewometer scanner software. 

It is based on bluepy (bluez) package by IanHarvey. There might be some other dependencies which I'll enumerate later. I've tested it on Raspberry PI 3 running Ubuntu Mate 1.12.1.


Sample usage:

To get syntax of the command:

[smartuser]$ ./brewster.py -h

usage: brewster.py [-h] [-s] [-a ADDR]

optional arguments:

  -h, --help            show this help message and exit
  
  -s, --scan            Discover all available Brewometers. Must run as root!
  
  -a ADDR, --addr ADDR  Read specified device. Get ADDR by running: sudo brewster.py -s


To find out address of your brewometer(s):

[smartuser]$ sudo ./brewster.py -s
[sudo] password for smartuser: 
Scanning for devices...
    Brew Device : d0:39:72:d3:4e:dd (public), -72 dBm (not connectable)


 [smartuser]$ ./brewster.py -a d0:39:72:d3:4e:dd
    Reading Brewometer: d0:39:72:d3:4e:dd
    Time:  2016-06-07 21:34
    Type:  10
    Temperature:  72
    Measured:  122
    Gravity:  1.102
    Battery:  26 %

That's about all. Have fun and brew some ales!

Any questions, contact me at (eugene AT anikin DONT com)
