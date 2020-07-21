import time
import visa
import pandas as pd
from datetime import datetime, timedelta
import re

EOS = "\n"
TIMEOUT = 10
START_TIMESTAMP = 0
SEARCHING = 2
FINISHED = 5
WIRING = {
    'Direct': '0',
    'Aron': '1',
    'Star': '2',
    'Delta': '3'
}

# map data points to query points

query_points = {
    'AC_VRMS': 'UTRMS',
    'AC_IRMS': 'ITRMS',
    'AC_P': 'P',
    'AC_S': 'S',
    'AC_Q': 'Q',
    'AC_PF': 'PF',
    'AC_FREQ': 'FCYC',
    'AC_INC': 'INCA',
    'AC_THDV': 'HUHD',
    'AC_THDI': 'HIHD',
    'DC_V': 'UDC',
    'DC_I': 'IDC',
    'DC_P': 'P'
}


class DeviceError(Exception):
    """
    Exception to wrap all das generated exceptions.
    """
    pass


class Device(object):
    def __init__(self, params):
        self.start_time = None
        self.params = params
        self.channels = params.get('channels')
        self.sample_interval = params.get('sample_interval')
        self.data_points = ['TIME']
        self.scale_i_inverse = params.get('scale_i_inverse')
        self.timestamp = params.get('timestamp')
        self._short_commands_enabled = False
        self.timeout = None
        self.groups = params.get('groups')
        # Resource Manager for pyvisa
        self.rm = None
        # Connection object
        self.conn = None
        # Open connection with lmg670
        self.open()
        # Change to short commands
        self.goto_short_commands()
        # Number of channel
        self.channels_number = len(self.channels) - 1
        ##        # Query the current channel jack list
        ##        self.current_list = len(self.query("IJLS?").split(','))
        ##        # Query the voltage channel jack list
        ##        self.voltage_list = len(self.query("UJLS?").split(','))
        # This create the query with all the wanted measurments
        self.query_chan_str = ""
        item = 0

        for i in range(1, 8):
            chan = self.channels[i]
            if chan is not None:
                chan_type = chan.get('type')
                points = chan.get('points')
                if points is not None:
                    chan_label = chan.get('label')
                    if chan_type is None:
                        raise DeviceError('No channel type specified')
                    if points is None:
                        raise DeviceError('No points specified')
                    for p in points:
                        item += 1
                        point_str = '%s_%s' % (chan_type, p)
                        chan_str = query_points.get(point_str)
                        self.query_chan_str += '%s%d?; ' % (chan_str, i)
                        if chan_label:
                            point_str = '%s_%s' % (point_str, chan_label)
                        self.data_points.append(point_str)
                        # Config the rms values
        self.rms_config()

    """
    Communication
    """

    def open(self):
        try:
            self.rm = visa.ResourceManager()
            if self.params['comm'] == 'Ethernet':
                try:
                    self._host = self.params['ip_address']
                    self._port = 5025
                    self.conn = self.rm.open_resource("TCPIP::{0}::{1}::SOCKET".format(self._host, self._port),
                                                      read_termination='\n')
                    # Timeouts are given per instrument in milliseconds.
                    self.conn.timeout = 5000
                except Exception as e:
                    raise DeviceError('LMG670 communication error: %s' % str(e))
            else:
                raise ValueError('Unknown communication type %s. Use TCPIP or Serial' % self.params['comm'])

        except Exception as e:
            raise DeviceError(str(e))

    def close(self):
        if self.params['comm'] == 'Ethernet':
            try:
                if self.conn is not None:
                    self.conn.close()
            except Exception as e:
                raise DeviceError('lmg670 communication error: %s' % str(e))
        else:
            raise ValueError('Unknown communication type %s. Use Serial or Ethernet' % self.params['comm'])

    def cmd(self, cmd_str):
        try:
            self.conn.write(cmd_str)
        except Exception as e:
            raise DeviceError('lmg670 communication error: %s' % str(e))

    def query(self, cmd_str):
        try:
            self.cmd(cmd_str)
            resp = self.conn.read()
        except Exception as e:
            raise DeviceError('lmg670 communication error: %s' % str(e))
        return resp

    def goto_short_commands(self):
        if not self._short_commands_enabled:
            self.cmd("*zlang short")
        self._short_commands_enabled = True

    def goto_scpi_commands(self):
        if self._short_commands_enabled:
            self.cmd("*zlang scpi")
        self._short_commands_enabled = False

    def send_short(self, msg):
        self.goto_short_commands()
        self.cmd(msg)

    def send_scpi(self, msg):
        self.goto_scpi_commands()
        self.cmd(msg)

    def query_short(self, msg):
        self.goto_short_commands()
        return self.query(msg)

    def query_scpi(self, msg):
        self.goto_scpi_commands()
        return self.query(msg)

    def query_short_bin(self, msg):
        self.goto_short_commands()
        return self.conn.query_binary_values(msg)

    """
    RMS Configuration
    """

    def rms_config(self):
        if self.params['comm'] == 'Ethernet':
            self.send_short('FRMT ASCii')
            # Device cycle mode set to fixed interval, specified by CYCL
            self.send_short("CYCLMOD 0")
            # Specifies the device cycle time to sample interval
            self.send_short("cycl {}".format(float(self.sample_interval) / 1000))
            # Turn off
            self.cont_off()
            # Signal filter automatic mode disabled for group 1 , 2, 3
            self.send_short("fauto 0;fauto2 0;fauto3 0")
            # Low-pass filter mode set to Narrowband converter
            self.send_short("LPFILT 2;LPFILT2 2")
            # Configure channel ranges
            self.set_ranges(0.03, 250)
            # Configure channel current ratio
            self.set_ratio()
            # Adjust the cycle length to the sampling rate
            self.send_short("cyclmod CYCL")
            # grouping the channel
            self.send_short("GROUP " + self.groups[0])
            # Wiring configuration of the daq
            for i in range(1, len(self.groups)):
                self.send_short(('WIRE%d ' % i) + WIRING[self.groups[i]['wiring']])
        else:
            raise ValueError('Unknown communication type %s. Use GPIB or VISA' % self.params['comm'])

    """
    RMS Functions
    """

    def data_capture(self, enable=True):
        self.capture(enable)

    def capture(self, enable=None):
        """
        Enable/disable capture.
        """
        ##        if enable is not None:
        ##            if enable is True:
        ##                self.cmd('CONT ON')
        ##            else:
        ##                self.cmd('CONT OFF')
        pass

    def data_read(self):
        data = self.query_short("INIM; TSNORM?; %s" % self.query_chan_str).split(";")
        if 'PF' in self.query_chan_str and self.params['pf_convention'] == 'Sunspec_EEI':
            data = self.pf_sunspec_EEI_convention(data)
        time_zimmer = data.pop(0)
        ts = time.clock()
        if self.timestamp == "Zimmer":
            m = re.search('(.*)\.[0-9]{6}', time_zimmer)
            # Remove the Nano Seconds since not use at the moment
            if self.start_time is None:
                self.start_time = datetime.strptime(m.group(0), '%Y:%m:%dD%H:%M:%S.%f')
            ts = (datetime.strptime(m.group(0), '%Y:%m:%dD%H:%M:%S.%f') - self.start_time).total_seconds()
        data = [float(x) for x in data]
        data.insert(0, ts)
        return data

    def pf_sunspec_EEI_convention(self, data):
        """
        Convert the power factor value from the DAQ sign convention value to Sunspec EEI sign convention
        value
        :param data: list
        This is the list of value return by the ZIMMER in unicode format

        :return: data: list
        data is the same as param data, but with the power factors that respect Sunspec sign
        convention
        """
        index_inc = 0
        index_q = 0
        i = 0
        q_position = 0
        for channel in range(1, self.channels_number + 1):
            if self.channels[channel]['type'] == 'Unused':
                continue
            else:
                index_inc = self.query_chan_str.find('INCA', index_inc + 1)
                index_q = self.query_chan_str.find('Q', index_q + 1)
                while index_q + 3 != i:
                    q_position += 1
                    i = self.query_chan_str.find(';', i + 1)
                inc_position = q_position
                while index_inc + 6 != i:
                    inc_position += 1
                    i = self.query_chan_str.find(';', i + 1)
                if '-1' in data[inc_position]:
                    a = data.pop(inc_position)
                    data.insert(inc_position, a.replace('-1', '1'))
                    a = data.pop(q_position)
                    data.insert(q_position, a.rjust(len(a) + 1, '-'))
                elif '1' in data[inc_position]:
                    a = data.pop(inc_position)
                    data.insert(inc_position, a.replace('1', '-1'))
                q_position = inc_position

        return data


    def set_ranges(self, current, voltage):
        for c in range(1, self.channels_number + 1):
            # Enables the manual settings (iauto 0) and set the range (p. 243)
            self.send_short("ijack{0} 1;iauto{0} 0; irng{0} {1};".format(c, current))
            # Enables the manual settings (uauto 0) and set the range (p. 281)
            self.send_short("uauto{0} 0; urng{0} {1}".format(c, voltage))

    def set_ratio(self):
        print((self.channels_number))
        for i in range(1, self.channels_number + 1):
            chan = self.channels[i]
            if chan is not None and chan['type'] != 'Unused':
                ratio = float(chan.get('ratio'))
                ratio = round((1.0 / ratio) * 1000.0, 2)
                if self.scale_i_inverse=='True':
                    ratio *= -1
                print(ratio)
                cmd = "ISCA{0} {1}".format(i, ratio)
                self.send_short(cmd)

    """
    Waveform Configuration
    """

    def waveform_config(self, params=None):
        # Transient sampling rate to 1.21 MS/s
        record_length = params['record_length']
        self.send_short('TRCSR {}'.format(params['sample_rate']))
        self.send_short('TRRECLEN {}'.format(record_length))
        self.send_short("TRCPTRT %f" % (params['pre_trigger']))
        self.send_short("SAMPLESTORAGEMODE 1")
        self.send_short('TRCOND DISabled')
        self.waveform_track()
        self.conn.timeout = record_length * 1000

        pass

    def waveform_track(self):
        track = 0
        # resets tracks
        for i in range(16):
            self.send_short("TRCTRAC {0}, ''".format(i))
        for channel in self.channels:
            if channel is not None and channel['type'] != 'Unused':
                chan_index = self.channels.index(channel)
                self.send_short("TRCTRAC {0}, 'U{1}'".format(track, chan_index))
                track += 1
                self.send_short("TRCTRAC {0}, 'I{1}'".format(track, chan_index))
                track += 1

    """
    Waveform Functions
    """

    def waveform_capture(self, enable=True, sleep=None):
        if enable == True:
            self.send_short('TRANSIENTRESTART')
            return 'Waveform - Waiting for trigger - code = %s' % self.waveform_wait_until(cond=SEARCHING)
        pass

    def waveform_status(self):
        stat = int(self.query_short('TRPSTAT?'))
        return stat

    def waveform_wait_until(self, cond=None):
        timeout = 0
        while timeout < 600:
            self.send_short('INIM NOW')
            stat = self.waveform_status()
            if stat == cond:
                break
            time.sleep(1)
            timeout += 1
        return stat

    def waveform_force_trigger(self):
        self.send_short('TRANSIENTNOW')
        return 'Waveform - Trigger Finished - code = %s' % self.waveform_wait_until(cond=FINISHED)

    def waveform_capture_dataset(self):
        # Variables
        waveforms = pd.DataFrame()
        samples = 30000
        track = 0
        samples_length = int(self.query_short('TRPTLEN?'))
        rec_length = float(self.query_short('TRRECLEN?'))
        start_time = self.query_short('TSTR?')
        sample_rate = self.query_short('TRCSR?')

        # Calculates the sample steps
        sample_steps = int(round(((rec_length / samples_length) * 10 ** 9), 1))
        m = re.search('(.*)\.[0-9]{6}', start_time)
        # Remove the Nano Seconds since not use at the moment
        zes_time_strp = datetime.strptime(m.group(0), '%Y:%m:%dD%H:%M:%S.%f')
        timestamp = pd.date_range(zes_time_strp, periods=samples_length, freq='{}N'.format(sample_steps))

        self.send_short('FRMT PACKed')
        for channel in self.channels:
            if channel is not None and channel['type'] != 'Unused':
                waveform_voltage = []
                waveform_current = []
                index_start = 0
                index_end = samples
                while index_start < samples_length - 1:
                    waveform_voltage.extend(
                        self.query_short_bin('TRPVAL? {0}, ({1}:{2});'.format(track, index_start, index_end))[2:])
                    waveform_current.extend(
                        self.query_short_bin('TRPVAL? {0}, ({1}:{2});'.format(track + 1, index_start, index_end))[2:])
                    index_start = index_end + 1
                    if (samples_length - index_start) < samples:
                        index_end = samples_length - 1
                    else:
                        index_end += samples
                waveforms = pd.concat([waveforms, pd.DataFrame({'CH{0}_U'.format(channel['label']): waveform_voltage})],
                                      axis=1)
                waveforms = pd.concat([waveforms, pd.DataFrame({'CH{0}_I'.format(channel['label']): waveform_current})],
                                      axis=1)
                track += 2
        # Assign the timestamp created from waveform parameters
        waveforms = waveforms.assign(timestamp=timestamp)
        waveforms.index = waveforms['timestamp']
        del waveforms['timestamp']
        waveforms.sort_index(inplace=True)
        # Add the parameter of the waveform to the dataset
        waveforms.loc[waveforms.index[0], 'START_TIME'] = start_time
        waveforms.loc[waveforms.index[0], 'SAMPLES_LENGTH'] = samples_length
        waveforms.loc[waveforms.index[0], 'RECORD_LENGTH'] = rec_length
        waveforms.loc[waveforms.index[0], 'SAMPLE_RATE'] = sample_rate
        waveforms.loc[waveforms.index[0], 'SAMPLES_STEPS'] = sample_steps
        self.send_short('FRMT ASCii')

        return waveforms

    def waveform_dataset_bin_to_float(self):
        pass

    """
    Other Functions
    """

    def info(self):
        return self.query_short('*IDN?')

    def status(self):
        result = self.query_short('*OPC?;*ESR?')
        return result

    def reset(self):
        self._short_commands_enabled = False
        self.send_short("*rst;*cls")

    def read_errors(self):
        return self.query_scpi("syst:err:all?")

    def cont_on(self):
        self.send_short("cont on")

    def cont_off(self):
        self.send_short("cont off")

    def disconnect(self):
        self.read_errors()


if __name__ == "__main__":
    params = {}
    params['comm'] = 'Ethernet'
    params['ip_address'] = '10.0.0.111'
    params['sample_interval'] = '50'
    params['scale_i_inverse'] = True
    params['channels'] = [None,
                          {'points': ('P'), 'type': 'AC', 'label': '1', 'ratio': '0.9923'},
                          {'points': ('P'), 'type': 'AC', 'label': '2', 'ratio': '1.0002'},
                          {'points': ('P'), 'type': 'AC', 'label': '3', 'ratio': '0.9971'},
                          None,
                          None,
                          None,
                          None, ]
    daq = Device(params=params)
    print((daq.info()))
    daq.send_short('ISCA{0} {1}'.format(1, 1))

    daq.close()

    pass
