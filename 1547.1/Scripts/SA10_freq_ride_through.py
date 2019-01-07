"""
Copyright (c) 2018, Sandia National Labs and SunSpec Alliance
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

import sys
import os
import traceback
from svpelab import gridsim
from svpelab import loadsim
from svpelab import pvsim
from svpelab import das
from svpelab import der
from svpelab import hil
import script
import result as rslt
import time

def freq_rt_profile(v_nom=100.0, freq_nom=100.0, freq_t=100.0, t_fall=0, t_hold=1, t_rise=0, t_dwell=5, n=5):
    """
    :param: v_nom - starting voltage value
    :param: freq_nom - starting frequency value
    :param: freq_t - test frequency value
    :param: t_fall - fall time
    :param: t_hold is hold time (s)
    :param: t_rise - rise time
    :param: t_dwell - dwell time
    :param: n - number of iterations

    :returns: profile - grid sim profile, in format of grid_profiles
    """
    profile = []
    t = 0
    profile.append((t, v_nom, v_nom, v_nom, freq_nom))       # (time offset, starting voltage (%), freq (100%))
    for i in range(1, n+1):
        t += t_dwell                                         # hold for dwell time
        profile.append((t, v_nom, v_nom, v_nom, freq_nom))   # (time offset, starting voltage (%), freq (100%))
        t += t_fall                                          # ramp over fall time
        profile.append((t, v_nom, v_nom, v_nom, freq_t))     # (time offset, test voltage (%), freq (100%))
        t += t_hold                                          # hold for hold time
        profile.append((t, v_nom, v_nom, v_nom, freq_t))     # (time offset, test voltage (%), freq (100%))
        t += t_rise                                          # ramp over rise time
        profile.append((t, v_nom, v_nom, v_nom, freq_nom))   # (time offset, starting voltage (%), freq (100%))
    t += t_dwell                                             # hold for dwell time
    profile.append((t, v_nom, v_nom, v_nom, freq_nom))       # (time offset, starting voltage (%), freq (100%))

    return profile

def test_run():

    result = script.RESULT_FAIL
    eut = grid = load = pv = daq_rms = daq_wf = chil = None

    sc_points = ['AC_IRMS_MIN']

    # result params
    result_params = {
        'plot.title': ts.name,
        'plot.x.title': 'Time (secs)',
        'plot.x.points': 'TIME',
        'plot.y.points': 'AC_FREQ_1',
        'plot.y.title': 'Frequency (Hz)',
        'plot.y2.points': 'AC_IRMS_1, AC_IRMS_MIN',
        'plot.y2.title': 'Current (A)'
    }

    try:
        test_label = ts.param_value('frt.test_label')
        # get test parameters
        freq_msa = ts.param_value('eut.freq_msa')
        p_rated = ts.param_value('eut.p_rated')
        v_nom = ts.param_value('eut.v_nom')
        t_msa = ts.param_value('eut.t_msa')
        t_dwell = ts.param_value('eut.frt_t_dwell')
        freq_nom = ts.param_value('eut.freq_nom')
        freq_grid_min = ts.param_value('frt.freq_grid_min')
        freq_grid_max = ts.param_value('frt.freq_grid_max')
        freq_test = ts.param_value('frt.freq_test')
        t_hold = ts.param_value('frt.t_hold')
        n_r = ts.param_value('frt.n_r')

        # calculate voltage adjustment based on msa
        freq_msa_adj = freq_msa * 1.5
        if freq_test > freq_nom:
            # apply HFRT msa adjustments
            freq_n = freq_grid_min + freq_msa_adj
            freq_t = freq_test - freq_msa_adj
        else:
            # apply LFRT msa adjustments
            freq_n = freq_grid_max - freq_msa_adj
            freq_t = freq_test + freq_msa_adj

        # set power levels that are enabled
        power_levels = []
        if ts.param_value('frt.p_100') == 'Enabled':
            power_levels.append((100, '100'))
        if ts.param_value('frt.p_20') == 'Enabled':
            power_levels.append((20, '20'))

        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # grid simulator is initialized with test parameters and enabled
        grid = gridsim.gridsim_init(ts)
        profile_supported = False

        # In cases where the grid simulator has voltage rise/loss on the line to the EUT or operates through a
        # transformer, the nominal voltage of the grid simulator won't be the same as the EUT and a correction
        # factor is applied.
        try:
            v_nom_grid = grid.v_nom_param
        except Exception, e:
            v_nom_grid = v_nom


        grid.voltage((v_nom_grid, v_nom_grid, v_nom_grid))

        # load simulator initialization
        load = loadsim.loadsim_init(ts)
        if load is not None:
            ts.log('Load device: %s' % load.info())

        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts)
        pv.power_set(p_rated)
        pv.power_on()

        # initialize rms data acquisition
        daq_rms = das.das_init(ts, 'das_rms', sc_points=sc_points)
        if daq_rms is not None:
            ts.log('DAS RMS device: %s' % (daq_rms.info()))
            daq_rms.sc['SC_TRIG'] = 0
            daq_rms.sc['AC_IRMS_MIN'] = ''


        # initialize waveform data acquisition
        daq_wf = das.das_init(ts, 'das_wf')
        if daq_wf is not None:
            ts.log('DAS Waveform device: %s' % (daq_wf.info()))

        # it is assumed the EUT is on
        eut = der.der_init(ts)
        if eut is not None:
            eut.config()

        # perform all power levels
        for power_level in power_levels:
            # set test power level
            power = float(power_level[0])/100 * p_rated
            pv.power_set(power)
            ts.log('Setting power level to %s%% of rated' % (power_level[0]))

            if daq_rms is not None:
                daq_rms.sc['AC_IRMS_MIN'] = ''
                ts.log('Starting RMS data capture')
                daq_rms.data_capture(True)
                ts.log('Waiting 5 seconds to start test')
                ts.sleep(5)

            if profile_supported:
                # create and execute test profile
                profile = freq_rt_profile(v_nom=v_nom, freq_nom=freq_n/freq_nom, freq_t=freq_t/freq_nom, t_hold=t_hold,
                                          t_dwell=t_dwell, n=n_r)
                grid.profile_load(profile=profile)
                grid.profile_start()
                # create countdown timer
                start_time = time.time()
                profile_time = profile[-1][0]
                ts.log('Profile duration is %s seconds' % profile_time)
                while (time.time() - start_time) < profile_time:
                    remaining_time = profile_time - (time.time()-start_time)
                    ts.log('Sleeping for another %0.1f seconds' % remaining_time)
                    sleep_time = min(remaining_time, 10)
                    ts.sleep(sleep_time)
                grid.profile_stop()
            else:
                # execute test sequence
                ts.log('Test duration is %s seconds' % ((float(t_dwell) + float(t_hold)) * float(n_r) +
                                                            float(t_dwell)))

                # get initial current level to determine threshold
                if daq_rms is not None:
                    daq_rms.data_sample()
                    data = daq_rms.data_capture_read()
                    irms = data.get('AC_IRMS_1')
                    if irms is not None:
                        daq_rms.sc['AC_IRMS_MIN'] = round(irms * .8, 2)

                for i in range(n_r):
                    grid.freq(freq=freq_n)
                    ts.log('Setting frequency: freq = %s for %s seconds' % (freq_n, t_dwell))
                    ts.sleep(t_dwell)
                    grid.freq(freq=freq_t)
                    ts.log('Setting frequency: freq = %s for %s seconds' % (freq_t, t_hold))
                    ts.sleep(t_hold)
                grid.freq(freq=freq_n)
                ts.log('Setting frequency: freq = %s for %s seconds' % (freq_n, t_dwell))
                ts.sleep(t_dwell)
            if daq_rms is not None:
                daq_rms.data_capture(False)
                ds = daq_rms.data_capture_dataset()
                test_name = '%s_rms_%s' % (test_label, power_level[1])
                filename = '%s.csv' % (test_name)
                ds.to_csv(ts.result_file_path(filename))
                result_params['plot.title'] = test_name
                ts.result_file(filename, params=result_params)
                ts.log('Saving data capture %s' % (filename))

        result = script.RESULT_COMPLETE

    except script.ScriptFail, e:
        reason = str(e)
        if reason:
            ts.log_error(reason)
    finally:

        # reset to nominal frequency and full power
        grid.freq(freq=freq_nom)
        pv.power_set(p_rated)

        if eut is not None:
            eut.close()
        if grid is not None:
            grid.close()
        if load is not None:
            load.close()
        if pv is not None:
            pv.close()
        if daq_rms is not None:
            daq_rms.close()
        if daq_wf is not None:
            daq_wf.close()
        if chil is not None:
            chil.close()

        # create result workbook
        file = ts.config_name() + '.xlsx'
        rslt.result_workbook(file, ts.results_dir(), ts.result_dir())
        ts.result_file(file)

    return result

def run(test_script):

    try:
        global ts
        ts = test_script
        rc = 0
        result = script.RESULT_COMPLETE

        ts.log_debug('')
        ts.log_debug('**************  Starting %s  **************' % (ts.config_name()))
        ts.log_debug('Script: %s %s' % (ts.name, ts.info.version))
        ts.log_active_params()

        result = test_run()

        ts.result(result)
        if result == script.RESULT_FAIL:
            rc = 1

    except Exception, e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)

info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.0.0')

'''
    eut
        p_rated
        v_nom
        freq_nom
        freq_msa (%)
        t_msa
        frt_t_dwell
    frt
        freq_test
        t_hold
        freq_grid_min
        freq_grid_max
        Power Level
            100%
            20%
'''

info.param_group('frt', label='Test Parameters')
info.param('frt.test_label', label='Test Label', default='frt')
info.param('frt.freq_test', label='Ride-Through Frequency (Hz)', default=60.0)
info.param('frt.t_hold', label='Ride-Through Duration (secs)', default=10.0)
info.param('frt.freq_grid_min', label='Minimum grid frequency (Hz)', default=60.0)
info.param('frt.freq_grid_max', label='Maximum grid frequency (Hz)', default=60.0)
info.param('frt.p_100', label='Power Level 100% Tests', default='Enabled', values=['Disabled', 'Enabled'])
info.param('frt.p_20', label='Power Level 20% Tests', default='Enabled', values=['Disabled', 'Enabled'])
info.param('frt.n_r', label='Number of test repetitions', default=5)

info.param_group('eut', label='EUT Parameters', glob=True)
info.param('eut.p_rated', label='P_rated', default=3000)
info.param('eut.v_nom', label='V_nom', default=240)
info.param('eut.freq_nom', label='Freq_nom', default=60.0)
info.param('eut.freq_msa', label='Freq_msa', default=2.0)
info.param('eut.t_msa', label='T_msa', default=1.0)
info.param('eut.frt_t_dwell', label='FRT T_dwell', default=5)

der.params(info)
das.params(info, 'das_rms', 'Data Acquisition (RMS)')
das.params(info, 'das_wf', 'Data Acquisition (Waveform)')
gridsim.params(info)
loadsim.params(info)
pvsim.params(info)

def script_info():
    
    return info


if __name__ == "__main__":

    # stand alone invocation
    config_file = None
    if len(sys.argv) > 1:
        config_file = sys.argv[1]

    params = None

    test_script = script.Script(info=script_info(), config_file=config_file, params=params)
    test_script.log('log it')

    run(test_script)


