"""
Copyright (c) 2017, Sandia National Labs and SunSpec Alliance
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

Redistributions of source code must retain the above copyright notice, this
list of conditions and the following disclaimer.

Redistributions in binary form must reproduce the above copyright notice, this
list of conditions and the following disclaimer in the documentation and/or
other materials provided with the distribution.

Neither the names of the Sandia National Labs and SunSpec Alliance nor the names of its
contributors may be used to endorse or promote products derived from
this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

Questions can be directed to support@sunspec.org
"""

import os

import script
try:
    import RtlabApi
except ImportError as e:
    print(e)
from . import wavegen

opalrt_info = {
    'name': os.path.splitext(os.path.basename(__file__))[0],
    'mode': 'OPAL-RT Function Generator'
}

def wavegen_info():
    return opalrt_info

def params(info, group_name):
    gname = lambda name: group_name + '.' + name
    pname = lambda name: group_name + '.' + GROUP_NAME + '.' + name
    mode = opalrt_info['mode']
    info.param_add_value(gname('mode'), mode)
    info.param_group(gname(GROUP_NAME), label='%s Parameters' % mode,active=gname('mode'),  active_value=mode, glob=True)
    info.param(pname('project_name'), label='"Active" RT-Lab Project Name', default='Open loop')

GROUP_NAME = 'opalrt'

class WavegenError(Exception):
    """
    Exception to wrap all wavegen generated exceptions.
    """
    pass

class Wavegen(wavegen.Wavegen):
    """
    Template for waveform generator (wavegen) implementations. This class can be used as a base class or
    independent data acquisition classes can be created containing the methods contained in this class.
    """

    def __init__(self, ts, group_name, points=None):
        wavegen.Wavegen.__init__(self, ts, group_name)
        self.project_name = self._param_value('project_name')

    def _param_value(self, name):
        return self.ts.param_value(self.group_name + '.' + GROUP_NAME + '.' + name)

    def info(self):
        """
        Return information string for the wavegen controller device.
        """
        '''
        sytem_info = RtlabApi.GetTargetNodeSystemInfo(self.target_name)
        opal_rt_info = "OPAL-RT - Platform version {0} (IP address : {1})".format(sytem_info[1],sytem_info[6])
        '''
        opal_rt_info = "Need a better OPAL info for wavegen"
        return opal_rt_info

    def open(self):
        """
        Open communications resources associated with the wavegen device.
        """
        RtlabApi.OpenProject(self.project_name)


    def close(self):
        """
        Close any open communications resources associated with the wavegen device.
        """
        RtlabApi.CloseProject()

    def load_config(self,sequence):
        """
        Load configuration
        """
        self.device.load_config(sequence=sequence)

    def start(self):
        """
        Start sequence execution
        :return:
        """
        self.device.start()

    def stop(self):
        """
        Start sequence execution
        :return:
        """
        self.device.stop()

    def chan_state(self, chans):
        """
        Enable channels
        :param chans: list of channels to enable
        :return:
        """
        i = 1
        for chan in chans:
            chan_config = "PF818072_test_model/sm_computation/FunctionGenerator/AnalogOutputs/Channel_Enable/Value({})".format(i)
            self._get_model_control()
            if chan:
                RtlabApi.SetParametersByName((chan_config),(1))
            else:
                RtlabApi.SetParametersByName((chan_config),(0))
            i = i + 1
        pass



    def voltage(self, voltage, channel):
        """
        Change the voltage value of individual channel
        :param voltage: The amplitude of the waveform
        :param channel: Channel to configure
        """
        voltage_config = {}
        if type(channel) is not list and type(voltage) is not list:
            voltage_config["name"] = "PF818072_test_model/sm_computation/Magnitude/Value({})".format(channel)
            voltage_config["value"] = voltage/40.0
            self._get_model_control()
            RtlabApi.SetParametersByName((voltage_config["name"]), (voltage_config["value"]))

    def frequency(self, frequency):
        """
        Change the voltage value of individual channel
        :param frequency: The frequency of the waveform on all channels
        """
        frequency_config = "PF818072_test_model/sm_computation/Freq/Value"
        self._get_model_control()
        RtlabApi.SetParametersByName((frequency_config), (frequency))

    def phase(self, phase, channel):
        """
        Change the voltage value of individual channel
        :param phase: This command sets the phase on selected channel
        :param channel: Channel to configure
        """
        if type(channel) is not list and type(phase) is not list:
            phase_config = "PF818072_test_model/sm_computation/Phases/Value({})".format(channel)
            self._get_model_control()
            RtlabApi.SetParametersByName((phase_config),(phase))

    def config_asymmetric_phase_angles(self, mag=None, angle=None):
        """
        :param mag: list of voltages for the imbalanced test, e.g., [277.2, 277.2, 277.2]
        :param angle: list of phase angles for the imbalanced test, e.g., [0, 120, -120]
        :returns: voltage list and phase list
        """
        mag = [x / 40 for x in mag]
        if type(mag) is list and type(angle) is list:
            mags = {}
            angs = {}
            for chan in range(1,4):
                mags[chan] = "PF818072_test_model/sm_computation/Magnitude/Value({})".format(chan)
                angs[chan] = "PF818072_test_model/sm_computation/Phases/Value({})".format(chan)
            self._get_model_control()
            RtlabApi.SetParametersByName((mags[1], mags[2], mags[3], angs[1], angs[2], angs[3]),
                                         (mag[0], mag[1], mag[2], angle[0], angle[1], angle[2]))

        return None, None


    def _is_model_running(self, phase, channel):
        pass

    def _get_model_control(self):
        parameterControl = 1
        RtlabApi.GetParameterControl(parameterControl)



if __name__ == "__main__":

    pass


