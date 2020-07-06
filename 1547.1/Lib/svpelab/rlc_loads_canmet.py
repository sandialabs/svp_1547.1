"""
Created by Estefan Apablaza-Arancibia
Modified by Michel Bui - March 19th 2019
CanmetENERGY-2018
"""

import os

from builtins import range

from . import rlc_loads
from pymodbus.client.sync import ModbusTcpClient
from pymodbus.client.sync import ModbusSerialClient

canmet_info = {
    'name': os.path.splitext(os.path.basename(__file__))[0],
    'mode': 'Canmet'
}
load_bank_nodes = {
    'R1': 1,
    'R2': 2,
    'R3': 3,
    'I1': 4,
    'I2': 5,
    'I3': 6,
    'C1': 7,
    'C2': 8,
    'C3': 9
    }

load_bank_pwr = {
    '0': 5000,
    '1': 10000,
    '2': 40000
}
def rlc_loads_info():
    return canmet_info

def params(info, group_name):
    gname = lambda name: group_name + '.' + name
    pname = lambda name: group_name + '.' + GROUP_NAME + '.' + name
    mode = canmet_info['mode']
    info.param_add_value(gname('mode'), mode)
    info.param_group(gname(GROUP_NAME), label='%s Communication Parameters' % mode, active=gname('mode'),
                     active_value=mode, glob=True)

    info.param(pname('ifc_type'), label='Interface type', default='TCP', values=['RTU', 'TCP'])
    # Modbus RTU parameters
    info.param(pname('ifc_name'), label='Interface Name', default='COM3',
               active=pname('ifc_type'),active_value=['RTU'])
    info.param(pname('baudrate'), label='Baud Rate', default=9600, values=[9600, 19200],
               active=pname('ifc_type'), active_value=['RTU'])
    info.param(pname('data_bits'), label='Data bits', default='8',
               active=pname('ifc_type'), active_value=['RTU'])
    info.param(pname('stop_bits'), label='Stop bits', default='1',
               active=pname('ifc_type'), active_value=['RTU'])
    info.param(pname('parity'), label='Parity', default='None', values=['N', 'E', 'O'],
               active=pname('ifc_type'), active_value=['RTU'])
    # Modbus TCP parameters
    # default='192.168.0.170'
    info.param(pname('ipaddr'), label='IP Address', default='10.0.0.116', active=pname('ifc_type'),
               active_value=['TCP'])
    info.param(pname('ipport'), label='IP Port', default=502, active=pname('ifc_type'),
               active_value=['TCP'])

GROUP_NAME = 'Canmet'


class RLC(rlc_loads.RLC):
    """
    Template for RLC load implementations. This class can be used as a base class or
    independent RLC load classes can be created containing the methods contained in this class.
    """

    def __init__(self, ts, group_name=None):
        rlc_loads.RLC.__init__(self, ts, group_name)
        self.rlc = None
        self.open()
        self.config()



    '''
    Communication functions
    '''

    def open(self):
        if self._param_value('ifc_type') == 'TCP':
            ipaddr = self._param_value('ipaddr')
            ipport = self._param_value('ipport')
            self.client = ModbusTcpClient(ipaddr, ipport)
        elif self._param_value['ifc_type'] == 'RTU':
            port = self._param_value('ifc_name')
            baudrate = self._param_value('baudrate')
            data_bits = self._param_value('data_bits')
            stop_bits = self._param_value('stop_bits')
            self.client = ModbusSerialClient(method="rtu", port=port, stopbits=stop_bits, bytesize=data_bits, parity=parity , baudrate=baudrate)
        return self.client.connect()
        

    def close(self):
        if self.client is not None:
            self.client.close()
            self.ts.log_debug("Closing connection")

    def status(self, unit=None):
        status = {}
        if unit is not None:
            for key, value in list(load_bank_nodes.items()):
                if unit.isalnum():
                    if unit.upper() in key:
                        rr_holding = self.client.read_holding_registers(0, 4, unit=value)
                        rr_discrete = self.client.read_discrete_inputs(0, 4, unit=value)
                        status[key] = '''Status = {}, Output = {}, Input power = {}, Idle = {}, {}'''.format(
                            rr_discrete.bits[1], rr_discrete.bits[2], rr_discrete.bits[3], rr_discrete.bits[4],
                            rr_holding.registers)
        else:
            for key, value in list(load_bank_nodes.items()):
                rr_holding = self.client.read_holding_registers(0, 4, unit=value)
                rr_discrete = self.client.read_discrete_inputs(0, 4, unit=value)
                status[key] = '''Status = {}, Output = {}, Input power = {}, Idle = {}, {}'''.format(rr_discrete.bits[1],rr_discrete.bits[2],rr_discrete.bits[3],rr_discrete.bits[4],rr_holding.registers)
        return status

    '''
    RLC Functions
    '''
    def config(self):
        # Control Switch
        for key, value in list(load_bank_nodes.items()):
            rq = self.client.write_coil(0, True, unit=value)
            rr = self.client.read_coils(0, 1, unit=value)
            assert (rq.function_code < 0x80)
            assert (rr.bits[0] == True)
            rq = self.client.write_coil(1, True, unit=load_bank_nodes[key])
            rr = self.client.read_coils(1, 1, unit=load_bank_nodes[key])
            assert (rq.function_code < 0x80)
            assert (rr.bits[0] == True)


    def resistance(self,r=None,err=None):
        if r is not None:
            if type(r) is not list and type(r) is not tuple and isinstance(r, (int, long)):
                self.ts.log_debug('resistance 1e')
                for key, value in list(load_bank_nodes.items()):
                    if 'R' in key:
                        self.set_value(value=r, unit=key, err=err)

            elif type(r) is tuple:
                n=1
                self.ts.log_debug('resistance 2e')
                for values in r:
                    if isinstance(values, (int, long)):
                        self.set_value(value=values, unit=n, err=err)
                        n += 1

    def inductance(self, i=None):
        # TODO Inductance functionality to be added
        if i is not None:
            if type(i) is not list and type(i) is not tuple and i.isdigit():
                for key, value in list(load_bank_nodes.items()):
                    if 'I' in key:
                        self.set_value(value=i, unit=key)

            elif type(i) is list:
                n = 4
                for values in i:
                    if values.isdigit():
                        self.set_value(value=i, unit=n)
                        n += 1
    def capacitance(self, c=None):
        # TODO capacitance functionality to be added
        if c is not None:
            if type(c) is not list and type(c) is not tuple and c.isdigit():
                for key, value in list(load_bank_nodes.items()):
                    if 'C' in key:
                        self.set_value(value=c, unit=key)

            elif type(c) is list:
                n = 7
                for values in i:
                    if values.isdigit():
                        self.set_value(value=c, unit=n)
                        n += 1

    def set_value(self,value=None, err=None, unit=0x1):

        self.ts.log_debug('value={}W and unit={}'.format(value, unit))

        # Activate unit
        rq = self.client.write_coil(1, True, unit=unit)
        rr = self.client.read_coils(1, 1, unit=unit)

        # Check the range is fine
        rr = self.client.read_holding_registers(0, 4, unit=int(unit))
        actual_range = rr.registers[1]
        self.ts.log_debug('Actual Range={}'.format(actual_range))
        auto_range = self.range_validator(int(value))

        if actual_range != int(auto_range):
            self.ts.log_debug('For Unit={}'.format(unit))

            rq = self.client.write_register(1, int(auto_range), unit=unit)

            rr = self.client.read_holding_registers(0, 4, unit=int(unit))
            self.ts.log_debug('Range has been set at {}'.format(rr.registers[1]))
            assert (rq.function_code < 0x80)
            assert (rr.registers[1] == int(auto_range))

        r_percent = (float(value) / load_bank_pwr.get(auto_range)) + (err/100)
        if r_percent > 1.0:
            r_percent = 1.0
        self.ts.log_debug('r_percent={} with error of {}% added'.format(r_percent, err))
        r_bits = int(r_percent * 0xFFFF)
        self.ts.log_debug('r_bits={}'.format(r_bits))
        rr = self.client.read_holding_registers(0, 4, unit=unit)
        self.ts.log_debug('bit_value register before modification={}'.format(rr.registers[2]))

        rq = self.client.write_register(2, r_bits, unit=unit)
        assert (rq.function_code < 0x80)

        rr = self.client.read_holding_registers(0, 4, unit=unit)
        self.ts.log_debug('bit_value after modification={}'.format(rr.registers[2]))
        assert (rr.registers[2] == r_bits)

    def range_validator(self, value):

        if load_bank_pwr.get('1') < value <= load_bank_pwr.get('2'):
            range_selected = '2'

        elif load_bank_pwr.get('0') < value <= load_bank_pwr.get('1'):
            range_selected = '1'

        elif value <= load_bank_pwr.get('0'):
            range_selected = '0'

        else:
            raise rlc_loads.RLCError('Out of range')

        self.ts.log_debug('Range to be set at {}'.format(range_selected))
        return range_selected
        #pass

    def _param_value(self, name):
        return self.ts.param_value(self.group_name + '.' + GROUP_NAME + '.' + name)



    



