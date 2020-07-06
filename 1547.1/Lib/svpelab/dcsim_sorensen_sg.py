"""
By canmetENERGY
"""

import os
import time
import visa
from . import dcsim
#import serial
from visa import constants

sorensen_info = {
    'name': os.path.splitext(os.path.basename(__file__))[0],
    'mode': 'Sorensen SG series'
}

def dcsim_info():
    return sorensen_info

def params(info, group_name=None):

    gname = lambda name: group_name + '.' + name
    pname = lambda name: group_name + '.' + GROUP_NAME + '.' + name
    mode = sorensen_info['mode']
    info.param_add_value(gname('mode'), mode)
    info.param_group(gname(GROUP_NAME), label='%s Parameters' % mode, active=gname('mode'),  active_value=mode, glob=True)
    info.param(pname('modes'), label='DC power supply mode', default='Serial', values=['Serial', 'GPIB'])
    # Constant current/voltage modes
    info.param(pname('v_max'), label='Max Voltage', default=300.0)
    info.param(pname('v'), label='Voltage', default=50.0)
    info.param(pname('i_max'), label='Max Current', default=1.0)
    info.param(pname('i'), label='Power Supply Current', default=0.5)

    # Comms
    info.param(pname('comm'), label='Communications Interface', default='Serial',values=['Serial', 'Visa', 'TCP'])
    # Serial
    info.param(pname('serial_port'), label='serial Port', active=pname('comm'),active_value=['Serial'], default='com21')
    info.param(pname('baudrate'), label='Baud Rate', active=pname('comm'),active_value=['Serial'], default='19200',values =['9600','19200'])
    info.param(pname('parity'), label='Parity', active=pname('comm'), active_value=['Serial'], default='no_parity',values=['odd_parity', 'even_parity', 'no_parity'])
    info.param(pname('data_bits'), label='Data Bits', active=pname('comm'),active_value=['Serial'], default=8)
    info.param(pname('stop_bits'), label='Stop Bits', active=pname('comm'),active_value=['Serial'], default=1)
    # TCP
    info.param(pname('ip_address'), label='TCP address', active=pname('comm'), active_value=['TCP'], default='10.0.0.121',values= ['10.0.0.121','10.0.0.122'])
    info.param(pname('ip_port'), label='TCP port', active=pname('comm'), active_value=['TCP'], default='502')


GROUP_NAME = 'sorensen_sg'

class DCSim(dcsim.DCSim):

    """
    Implementation for Sorensen Programmable DC power supply .

    Valid parameters:
      mode - 'Sorensen SG series'
      v_nom
      v_max
      i_max
      freq
      profile_name
      serial_port
      baudrate
      timeout
      write_timeout
      ip_addr
      ip_port
    """
    def __init__(self, ts, group_name):
        self.buffer_size = 1024
        self.rm = None
        self.conn = None

        dcsim.DCSim.__init__(self, ts, group_name)

        # power supply parameters
        self.v_max_param = self._param_value('v_max')
        self.v_param = self._param_value('v')
        self.i_max_param = self._param_value('i_max')
        self.i_param = self._param_value('i')
        self.comm = self._param_value('comm')
        self.serial_port = self._param_value('serial_port')
        self.baudrate = self._param_value('baudrate')
        self.byte_size = self._param_value('data_bits')
        self.stop_bits = self._param_value('stop_bits')
        self.timeout = 6000
        self.write_timeout = 6000
        self.cmd_str = ''
        self._cmd = None
        self._query = None

        # Open selected configuration
        # Establish communications with the DC power supply
        if self.comm == 'Serial':
            self.open()  # open communications
            self._cmd = self.cmd_serial
            self._query = self.query_serial
        elif self.comm == 'TCP/IP':
            self._cmd = self.cmd_tcp
            self._query = self.query_tcp

    # Serial commands for power supply
    def cmd_serial(self, cmd_str):
        self.cmd_str = cmd_str
        try:
            if self.conn is None:
                raise dcsim.DCSimError('Communications port to power supply not open')

            self.conn.flushInput()
            self.conn.write(cmd_str)
        except Exception as e:
             raise dcsim.DCSimError(str(e))

    # Serial queries for power supply
    def query_serial(self, cmd_str):
        resp = ''
        more_data = True

        self.cmd_serial(cmd_str)

        while more_data:
            try:
                count = self.conn.inWaiting()
                if count < 1:
                    count = 1
                data = self.conn.read(count)
                if len(data) > 0:
                    for d in data:
                        resp += d
                        if d == '\n':
                            more_data = False
                            break
                else:
                    raise dcsim.DCSimError('Timeout waiting for response')
            except dcsim.DCSimError:
                raise
            except Exception as e:
                raise dcsim.DCSimError('Timeout waiting for response - More data problem')

        return resp

    def _param_value(self, name):
        return self.ts.param_value(self.group_name + '.' + GROUP_NAME + '.' + name)

    """
    Communication
    """

    def open(self):
        """
        Open the communications resources associated with the grid simulator.
        """

        self.rm = visa.ResourceManager()
        serialport = self._param_value('serial_port')
        self.ts.log_debug(serialport)
        try:
            if self.comm == 'Serial':
                # Serial parameters
                self.conn = self.rm.open_resource(serialport,
                                                  baud_rate = int(self._param_value('baudrate')),
                                                  data_bits = self._param_value('data_bits'),
                                                  write_termination= '\r',
                                                  read_termination = '\r')
                constants.VI_ASRL_PAR_NONE
                constants.VI_ASRL_STOP_ONE
                self.ts.log_debug(type(self.conn))
                self.ts.log_debug(self.conn.baud_rate)
                self.ts.log_debug(self.conn.data_bits)
                self.conn.timeout = float(self.timeout)
                self.conn.write_timeout = float(self.timeout)

            if self.comm == 'TCP':
                # TCP paramaters
                self.ipaddr = self._param_value('ip_addr')
                self.ipport = self._param_value('ip_port')
                self.conn = self.rm.open_resource("TCPIP::{0}::{1}::SOCKET".format(self.ipaddr, self.ipport ),read_termination='\n')

            time.sleep(2)
        except Exception as e:
            raise dcsim.DCSimError(str(e))

    def close(self):
        try:
            if self.conn is not None:
                self.conn.close()
        except Exception as e:
            raise dcsim.DCSimError(str(e))

    def cmd(self, cmd_str):
        self.cmd_str = cmd_str
        try:
            if self.conn is None:
                raise dcsim.DCSimError('Communications port to power supply not open')

            #self.conn.flushInput()
            self.conn.write(cmd_str)
        except Exception as e:
             raise dcsim.DCSimError(str(e))

    def query(self, cmd_str):
        if self._param_value('comm') == 'VISA' or self._param_value('comm') == 'Network':
            self.cmd(cmd_str)
            resp = self.conn.read()
        elif self._param_value('comm') == 'Serial':
            self.ts.log_debug(cmd_str)
            resp = self.conn.query(cmd_str)
        return resp

    """
    Configuration
    """

    def config(self):
        """
        Perform any configuration for the simulation based on the previously
        provided parameters.
        """

        # set voltage limits
        v_max_set = self.voltage_max()
        if v_max_set != self.v_max_param:
            v_max_set = self.voltage_max(voltage=self.v_max_param)
        #v_min_set = self.voltage_min()
        #if v_min_set != 0:
        #    v_min_set = self.voltage_min(voltage=20.)
        #self.ts.log('Battery power supply voltage range: [%s, %s] volts' % (v_min_set, v_max_set))

        v_set = self.voltage()
        if v_set != self.v_param:
            self.ts.log_debug('Power supply voltage is %s, should be %s' % (self.v_param, v_set))
            v_set = self.voltage(voltage=self.v_param)
        self.ts.log('Battery power supply voltage: %s volts' % v_set)

        i_max_set = self.current_max()
        if i_max_set != self.i_max_param:
            i_max_set = self.current_max(self.i_max_param)
        self.ts.log('Battery power supply max current: %s Amps' % i_max_set)

        # set current
        #self.current_min(current=0.)  # get the current limit out of the way.

        i = self.i_param
        i_set = self.current()
        self.ts.log_debug('Power supply current is %s, should be %s' % (i_set, i))
        if i != i_set:
            i_set = self.current(current=i)
            self.ts.log_debug('Power supply current is %0.3f, should be %0.3f' % (i, i_set))
            if i_set == 0.0:
                self.ts.log_warning('Make sure the DC switch is closed!')
        self.ts.log('Battery power supply current settings: i = %s' % i_set)

        ''' Not implemented
        output_mode_set = self.output_mode()
        self.ts.log('Battery power supply mode is %s' % output_mode_set)
        if output_mode_set == 'CVCC':
            self.output_mode(mode='CVCC')
        '''

        # set power supply output
        self.output(start=True)
        outputting = self.output()
        if outputting == '1':
            self.ts.log_warning('Battery power supply output is started!')

    """
    SCPI functions
    """
    def info(self):
        try:
            '''
            self.conn.write('*IDN?')
            self.ts.log_debug("apres write query")
            resp = self.conn.read_raw()
            '''
            resp = self.conn.query("*IDN?")
            self.ts.log_debug(resp)
        except Exception as e:
            raise dcsim.DCSimError(str(e))
        return resp

    def status(self):
        #result = self.query_short('*OPC?;*ESR?')

        return result

    def reset(self):
        self.cmd("*RST")
        self.cmd("*CLS")

    def read_errors(self):
        return self.query_scpi("syst:err:all?")

    def output(self, start=None):
        """
        Start/stop power supply output

        start: if False stop output, if True start output
        """
        if start is not None:
            if start is True:
                self.cmd('OUTP ON\n')
            else:
                self.cmd('OUTP OFF\n')
        #output = self.query('CONF:OUTP?\n')
        output = self.query('OUTP?\n')
        return output

    """
    Non-SCPI functions
    """
    def output_mode(self, mode=None):
        """
        Start/stop power supply output
        mode: 'CVCC' constant voltage constant current
        """
        if mode is not None:
            self.cmd('OUTPut:MODE %s' % mode)
        mode = self.query('OUTPut:MODE?\n')
        return mode

    def current(self, current=None):
        """
        Set the value for current if provided. If none provided, obtains the value for current.
        """
        self.ts.log_debug(current)
        if current is not None:
            self.cmd('SOUR:CURR %0.1f\n' % current)
        i = self.query('SOUR:CURR?\n')
        self.ts.log_debug(i)
        return float(i)

    def current_max(self, current=None):
        """
        Set the value for max current if provided. If none provided, obtains the value for max current.
        """
        if current is not None:
            self.cmd('SOUR:CURR:LIM %0.1f\n' % current)
            #self.cmd('SOUR:CURR:PROT %0.1f\n' % current)
        i1 = self.query('SOUR:CURR:LIM?\n')
        #i1 = self.query('CURR:LIMIT:HIGH?\n')
        #i2 = self.query('SOUR:CURR:PROT?\n')
        #eturn float(min(i1, i2))
        return float(i1)
    '''
    def current_min(self, current=None):
        """
        Set the value for min current if provided. If none provided, obtains
        the value for min current.
        """
        if current is not None:
            self.cmd('SOUR:CURR:LIMIT:LOW %0.1f\n' % current)
        i = self.query('SOUR:CURR:LIMIT:LOW?\n')
        return float(i)
    '''
    def voltage(self, voltage=None):
        """
        Set the value for voltage. If none provided, obtains the value for voltage.
        """
        if voltage is not None:
            self.cmd('SOUR:VOLT %0.1f\n' % voltage)
        v = self.query('SOUR:VOLT?')
        return float(v)

    def voltage_max(self, voltage=None):
        """
        Set the value for max voltage if provided. If none provided, obtains
        the value for max voltage.
        """
        if voltage is not None:
            #self.cmd('SOUR:VOLT:LIMIT:HIGH %0.1f\n' % voltage)
            self.cmd('SOUR:VOLT:LIM %0.1f' % voltage)
            self.cmd('SOUR:VOLT:PROT %0.1f' % voltage)
        #v1 = self.query('SOUR:VOLT:LIMIT:HIGH?\n')
        v1 = self.query('SOUR:VOLT:LIM?')
        v2 = self.query('SOUR:VOLT:PROT?\n')
        return min(float(v1), float(v2))

    '''
    def voltage_min(self, voltage=None):
        """
        Set the value for max voltage if provided. If none provided, obtains
        the value for max voltage.
        """
        if voltage is not None:
            self.cmd('SOUR:VOLT:LIMIT:LOW %0.1f\n' % voltage)
        v = self.query('SOUR:VOLT:LIMIT:LOW?\n')
        return float(v)
    '''
