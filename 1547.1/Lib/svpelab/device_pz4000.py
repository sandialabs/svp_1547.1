
import time
import visa
# map data points to query points
query_points = {
    'AC_VRMS': 'URMS',
    'AC_IRMS': 'IRMS',
    'AC_P': 'P',
    'AC_S': 'S',
    'AC_Q': 'Q',
    'AC_PF': 'LAMBDA',
    'AC_FREQ': 'FU',
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
        self.params = params
        self.channels = params.get('channels')
        self.data_points = ['TIME']
        # Resource Manager for VISA
        self.rm = None
        # Connection to instrument for VISA-GPIB
        self.conn = None

        # create query string for configured channels
        query_chan_str = ''
        item = 0
        for i in range(1,5):
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
                        query_chan_str += ':NUMERIC:NORMAL:ITEM%d %s,%d;' % (item, chan_str, i)
                        if chan_label:
                            point_str = '%s_%s' % (point_str, chan_label)
                        self.data_points.append(point_str)
        query_chan_str += '\n:NUMERIC:NORMAL:VALUE?'

        self.query_str = ':NUMERIC:FORMAT ASCII\nNUMERIC:NORMAL:NUMBER %d\n' % (item) + query_chan_str
        self.open()
        print((self.query(self.query_str)))
        self.cmd('*CLS')
        # Set display format to show only numeric
        self.cmd(":DISPlay:FORMat NUMeric")
        # Set the quantity of element to display
        self.cmd(":DISPLAY:NUMERIC:NORMAL:IAMOUNT ALL")
        # Disable filter on all elements
        self.cmd(":FILTER:LINE OFF")
        # Observation time
        self.cmd(":TIMebase:OBServe 40ms")
        # Turn off the trigger
        self.cmd(":TRIGGER:MODE OFF")
        # Voltage range set to 300Vpk
        self.cmd(":VOLTAGE:RANGE 300")
        # Current terminal are all sensor (Shunts)
        self.cmd(":INPUT:POWER:CURRENT:TERMINAL:ALL SENSor")
        # Current range set to 100mVpk
        self.cmd(":INPUT:POWER:CURRENT:RANGE:ALL AUTO")
        # Set the PZ4000 in normal mode operation
        self.cmd(":SETUP:MODE NORMAL")
        # Divide the memory in two
        self.cmd(":ACQUIRE:DIVISION ON")
        # Turn OFF computation 
        self.cmd(":MEASure:MODE 1")
        #Set the transition filter used to detect the completition of the numerical data updating
        self.cmd('STATUS:FILTER2 RISE')
        #Clear the extended event register (Read and trash the response)
        print((self.query('STATUS:EESR?')))


        

    def open(self):
        try:
            if self.params['comm'] == 'GPIB':
                raise NotImplementedError('The driver for plain GPIB is not implemented yet. ' +
                                          'Please use VISA which supports also GPIB devices')
            elif self.params['comm'] == 'VISA':
                try:
                    # sys.path.append(os.path.normpath(self.visa_path))
                    self.rm = visa.ResourceManager()
                    self.conn = self.rm.open_resource(self.params['visa_address'])
                except Exception as e:
                    raise DeviceError('PZ4000 communication error: %s' % str(e))
            elif self.params['comm'] == 'Serial':
                try:
                    # sys.path.append(os.path.normpath(self.visa_path))
                    self.rm = visa.ResourceManager()
                    self.conn = self.rm.open_resource(self.params['com_port'])
                    self.conn.baud_rate = 19200
                    self.data_bits = 8
                    self.stop_bits = 1
                    self.parity = 'no_parity'


                except Exception as e:
                    raise DeviceError('PZ4000 communication error: %s' % str(e))
            else:
                raise ValueError('Unknown communication type %s. Use GPIB or VISA' % self.params['comm'])

        except Exception as e:
            raise DeviceError(str(e))


    def close(self):

        if self.params['comm'] == 'GPIB':
            raise NotImplementedError('The driver for plain GPIB is not implemented yet.')
        elif self.params['comm'] == 'VISA':
            try:
                if self.conn is not None:
                    self.conn.close()
            except Exception as e:
                raise DeviceError('PZ4000 communication error: %s' % str(e))
        else:
            raise ValueError('Unknown communication type %s. Use Serial, GPIB or VISA' % self.params['comm'])


    def cmd(self, cmd_str):
        try:
            self.conn.write(cmd_str)

        except Exception as e:
            raise DeviceError('PZ4000 communication error: %s' % str(e))

    def query(self, cmd_str):
        try:
            resp = self.conn.ask(cmd_str)
        except Exception as e:
            raise DeviceError('PZ4000 communication error: %s' % str(e))
        return resp

    def info(self):
        return self.query('*IDN?')

    def data_capture(self, enable=True):
        self.capture(enable)

    def capture(self, enable=None):
        """
        Enable/disable capture.
        """
        if enable is not None:
            if enable is True:
                self.cmd('STAR')
            else:
                self.cmd('STOP')
        


    COND_RUN = 0x1000
    COND_TRG = 0x0004
    COND_CAP = 0x0001

    def status(self):
        """
        Returns dict with following entries:
            'trigger_wait' - waiting for trigger - True/False
            'capturing' - waveform capture is active - True/False
        """
        cond = int(self.query('STAT:COND?'))
        result = {'trigger_wait': (cond & COND_TRG),
                  'capturing': (cond & COND_CAP),
                  'cond': cond}
        return result

    def waveform(self):
        import numpy
        #Get sampling rate
        sampling_rate = float(self.conn.ask(':TIM:SRAT?').split(' ', 1)[-1])

        # Get wave length
        wave_length = float(self.query(':WAV:LENG?').split(' ', 1)[-1])

        # Get zoom value
        zoom_value = float(self.query(':ZOOM:MAG?').split(' ', 1)[-1])

        # Get zoom position
        zoom_position = float(self.query(':ZOOM:POS?').split(' ', 1)[-1])

        # Calculate capture window  nSRate = lround(m_fSRate)
        m_nStart = int(round((sampling_rate*zoom_position)-(wave_length/(2.0*zoom_value)), 1))
        if m_nStart < 0 :
            m_nStart = 0
        m_nStop = int(round((sampling_rate * zoom_position) + (wave_length / (2.0 * zoom_value)), 1))
        if m_nStop > wave_length:
            m_nStop = int(wave_length)

        self.conn.write(':WAV:STAR {};:WAV:END {};'.format(m_nStart,m_nStop))
        print(('Start : {}\r\nStop :{}'.format(m_nStart, m_nStop)))
        import time

        collection = [2,4,6]
        wave = numpy.array([])

        for i in collection :
            self.conn.write(':WAV:FORM ASCii;:WAV:TRAC {}'.format(i))
            if i != 2:
                wave = numpy.vstack((wave, numpy.array(self.conn.query_ascii_values(':WAV:SEND?'))))
            else:
                wave = numpy.array(self.conn.query_ascii_values(':WAV:SEND?'))

        wave = numpy.transpose(wave)

        timestr = time.strftime("%Y%m%d-%H%M%S")
        numpy.savetxt("Waveform_{}.csv".format(timestr), wave, delimiter=",")

        return wave


    def trigger_config(self, params):
        """
        slope - (rise, fall, both)
        level - (V, I, P)
        chan - (chan num)
        action - (memory save)
        position - (trigger % in capture)
        """

        """
        samples/sec
        secs pre/post

        rise/fall
        level (V, A)
        """

        pass

    def data_read(self):
        # Wait for the completion of the numerical data updating
        self.cmd("COMMUNICATE:WAIT 2")
        # Clear the extended event register (Read and trash the response)
        print((self.query("STATUS:EESR?")))
        data = [float(i) for i in self.query("NUMERIC:NORMAL:VALUE?").split(',')]
        data.insert(0, time.clock())
        return data

if __name__ == "__main__":
    
    params = {}
    params['comm'] = 'VISA'
    params['visa_address'] = 'GPIB0::7::INSTR'
    params['channels'] = [{'points': ('VRMS', 'IRMS', 'P', 'S', 'Q', 'PF', 'FREQ'), 'type': 'AC', 'label': '1'}, {'points': ('VRMS', 'IRMS', 'P', 'S', 'Q', 'PF', 'FREQ'), 'type': 'AC', 'label': '2'}, {'points': ('VRMS', 'IRMS', 'P', 'S', 'Q', 'PF', 'FREQ'), 'type': 'AC', 'label': '3'}, None, None]


    d = Device(params=params)
    print((d.info()))
    d.capture(True)
    #d.cmd(":START")
    # Read and display the numerical data ( Repeated 10 times)
    for i in range(1,11):                
        print((d.data_read()))
    #d.cmd(":STOP")








    pass
