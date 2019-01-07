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

import sys
import os
import traceback
from svpelab import gridsim
from svpelab import pvsim
from svpelab import das
from svpelab import der
from svpelab import hil
from svpelab import waveform, waveform_analysis

import script
import openpyxl
import time
import numpy as np
import matplotlib.pyplot as plt

def voltage_rt_profile(v_nom=100., t_t=2., P_b=100., P_U=111.):
    """
    :param: P_N - nominal voltage
    :param: P_T - trip voltage
    :param: P_U - final voltage after step function
    :param: P_b - starting voltage
    :param: t_hold - hold time
    :param: t_r - rise time
    :param: t_t - trip time
    :param: A - scaling factor
    :param: Pb - starting pt of the step function. Pb shall be within 10% of, but not exceed, the trip point mag.

    p - magnitude of the voltage
    t_i - start time of the step function
    t0 - start time used for calculating the trip time

    :returns: profile - grid sim profile in format of grid_profiles
    """
    profile = []
    t = 0
    # profile.append((t, P_b, P_b, P_b, 100))      # (time offset, starting voltage (%), freq (100%))
    profile.append((t, P_U, P_U, P_U, 100))        # (time offset, starting voltage (%), freq (100%))
    t += t_t + 1                                   # hold for trip time plus 1 sec
    profile.append((t, P_U, P_U, P_U, 100))        # (time offset, starting voltage (%), freq (100%))
    profile.append((t, v_nom, v_nom, v_nom, 100))  # (time offset, starting voltage (%), freq (100%))

    return profile

def test_run():

    result = script.RESULT_FAIL
    eut = grid = load = pv = daq = chil = None

    try:

        '''
        This procedure uses the step function defined in Annex A.
        a) Connect the EUT according to the instructions and specifications provided by the manufacturer.
        b) Set all source parameters to the nominal operating conditions for the EUT.
        c) Set (or verify) all EUT parameters to the nominal operating settings. If the overvoltage trip time setting
        is adjustable, set it to the minimum.
        d) Record applicable settings.
        e) Set the source voltage to a value within 10% of, but not exceeding, the overvoltage trip point setting.
        The source shall be held at this voltage for period t_hold. At the end of this period, step the source voltage
        to a value that causes the unit to trip. Hold this value until the unit trips. For multiphase units,
        this test may be performed on one phase only.
        f) Record the trip time.
        g) Repeat steps d) through f) four times for a total of five tests.
        h) If the overvoltage time setting is adjustable, repeat steps d) through g) at the midpoint and maximum
        overvoltage time settings.
        '''

        phases = ts.param_value('eut.phases')
        p_rated = ts.param_value('eut.p_rated')
        v_nom = ts.param_value('eut.v_nom')  # volts
        v_msa = ts.param_value('eut.v_msa')
        t_msa = ts.param_value('eut.t_msa')
        t_trip = ts.param_value('eut.t_trip')
        P_T = ts.param_value('vrt.v_test')  # percentage
        t_hold = ts.param_value('vrt.t_hold')
        n_r = ts.param_value('vrt.n_r')

        # P_T = trip voltage
        # P_b = starting voltage
        # P_U = test voltage

        # Parameter A shall be chosen so that P_U is at least 110% (90% for under value tests) of P_T
        P_T_volts = (P_T/100)*v_nom
        if P_T_volts > v_nom:
            A = 0.1 * P_T_volts  # volts
        else:
            A = -0.1 * P_T_volts  # volts
        P_U = P_T_volts + A
        if P_U < 0:
            P_U = 0
        # P_b = v_nom + (v_nom - v_msa)*0.9  # if the grid sim has a long slew rate
        P_b = v_nom  # starting voltage of the test, in volts

        '''
        Set all AC source parameters to the normal operating conditions for the EUT.
        '''
        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # grid simulator is initialized with test parameters and enabled
        grid = gridsim.gridsim_init(ts)

        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts)
        pv.power_set(p_rated)
        pv.power_on()

        # initialize data acquisition
        daq = das.das_init(ts)
        ts.log('DAS device: %s' % daq.info())

        '''
        Turn on the EUT. It is permitted to set all L/HVRT limits and abnormal voltage trip parameters to the
        widest range of adjustability possible with the SPF enabled in order not to cross the must trip
        magnitude threshold during the test.
        '''
        # it is assumed the EUT is on
        eut = der.der_init(ts)
        eut.config()

        # run data capture
        ts.log('Running capture 1')
        f_sample = 5000
        wfm_config_params = {
            'sample_rate': f_sample,
            'pre_trigger': 0.5,
            'post_trigger': t_trip+1.5,
            'timeout': 30
            }
        if phases == 'Single Phase':
            wfm_config_params['channels'] = ['AC_V_1', 'AC_I_1', 'EXT']
        else:
            wfm_config_params['channels'] = ['AC_V_1', 'AC_V_2', 'AC_V_3', 'AC_I_1', 'AC_I_2', 'AC_I_3', 'EXT']
        if chil is not None:
            wfm_config_params['channels'] = ['AC_V_1', 'AC_V_2', 'AC_V_3', 'AC_I_1', 'AC_I_2', 'AC_I_3']
            if P_T > v_nom:
                wfm_config_params['trigger_cond'] = 'Rising Edge'
                wfm_config_params['trigger_channel'] = 'AC_V_1'
                wfm_config_params['trigger_level'] = ((P_U+P_b)/2.)*np.sqrt(2)
            else:
                wfm_config_params['trigger_cond'] = 'Rising Edge'
                wfm_config_params['trigger_channel'] = 'AC_I_1'  # catch the current increase on v sag
                wfm_config_params['trigger_level'] = ((p_rated/v_nom)/3)*1.05*np.sqrt(2)  # trigger when current 5% above rated
        else:
            wfm_config_params['trigger_cond'] = 'Rising Edge'
            wfm_config_params['trigger_channel'] = 'EXT'
            wfm_config_params['trigger_level'] = 1  # 0-5 V signal

        daq.waveform_config(params=wfm_config_params)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        if phases == 'Single Phase':
            # single phase to be cleaned up
            result_summary.write('Result, Test Name, t_trip, t_trip_meas, Dataset File\n')
        else:
            result_summary.write('Result, Test Name, t_trip, t_trip_meas, Dataset File\n')

        # set phase tests that are enabled
        phase_tests = []
        # set single phase test voltages and test labels
        if phases == 'Single Phase':
            phase_tests.append(((P_U, v_nom, v_nom), 'Phase 1 Fault Test', 'p1', (P_b, v_nom, v_nom)))
        if phases == '3-Phase 3-Wire' or phases == '3-Phase 4-Wire':
            if ts.param_value('vrt.phase_1') == 'Enabled':
                phase_tests.append(((P_U, v_nom, v_nom), 'Phase 1 Fault Test', 'p1', (P_b, v_nom, v_nom)))
            if ts.param_value('vrt.phase_2') == 'Enabled':
                phase_tests.append(((v_nom, P_U, v_nom), 'Phase 2 Fault Test', 'p2', (v_nom, P_b, v_nom)))
            if ts.param_value('vrt.phase_3') == 'Enabled':
                phase_tests.append(((v_nom, v_nom, P_U), 'Phase 3 Fault Test', 'p3', (v_nom, v_nom, P_b)))
        ts.log_debug('Phase Tests: %s' % phase_tests)

        for phase_test in phase_tests:
            if daq is not None:
                ts.log('Starting RMS data capture')
                daq.data_capture(True)
            v_1, v_2, v_3 = phase_test[0]
            v_1_init, v_2_init, v_3_init = phase_test[3]

            # generate step change profile
            profile = voltage_rt_profile(v_nom=100, t_t=t_trip, P_b=P_b, P_U=P_U)

            for i in range(n_r):
                filename = '%s_%s_%s.csv' % ('voltage_trip', phase_test[2], i+1)
                # start trip time test
                profile_supported = False
                if profile_supported:
                    # UNTESTED!
                    daq.waveform_capture(True)  # turn on daq waveform capture
                    t_sleep = 2  # need time to prepare acquisition
                    ts.log('Sleeping for %s seconds, to wait for the capture to prime.' % t_sleep)
                    ts.sleep(t_sleep)

                    grid.profile_load(profile=profile)
                    # grid.profile_load(profile_name='VV Profile')
                    ts.log_debug(profile)
                    ts.log('Starting profile now!')
                    grid.profile_start()
                    # Provide GUI with countdown timer
                    start_time = time.time()
                    profile_time = profile[-1][0]
                    ts.log('Profile duration is %s seconds' % profile_time)
                    while (time.time()-start_time) < profile_time:
                        remaining_time = profile_time - (time.time()-start_time)
                        ts.log('Sleeping for another %0.1f seconds' % remaining_time)
                        ts.sleep(5)
                    grid.profile_stop()

                else:
                    grid.voltage((v_nom, v_nom, v_nom))
                    ts.log('Setting voltage: v_1 = %s  v_2 = %s  v_3 = %s for %s seconds' %
                           (v_nom, v_nom, v_nom, t_hold))

                    # Check that the EUT is functioning
                    daq.data_sample()  # Sample before the grid voltage change
                    data = daq.data_capture_read()
                    p1 = data.get('AC_P_1')
                    p2 = data.get('AC_P_2')
                    p3 = data.get('AC_P_3')
                    ts.log('    EUT powers before dwell: p_1 = %s  p_2 = %s  p_3 = %s' % (p1, p2, p3))
                    grid.voltage((v_nom, v_nom, v_nom))
                    countdown = 30
                    while (p1 < (0.1*p_rated)/3 or p2 < (0.1*p_rated)/3 or p3 < (0.1*p_rated)/3) and countdown > 0:
                        countdown -= 1
                        ts.log('    Waiting for EUT to turn back on for another %s seconds. (p1=%s, p2=%s, p3=%s)'
                               % (countdown, p1, p2, p3))
                        ts.sleep(1)
                        data = daq.data_capture_read()
                        p1 = data.get('AC_P_1')
                        p2 = data.get('AC_P_2')
                        p3 = data.get('AC_P_3')
                    ts.sleep(3)  # return to ~rated power

                    forced = True
                    if forced:
                        daq.waveform_force_trigger()
                        ts.sleep(0.5)
                    else:
                        # Start Waveform Capture
                        daq.waveform_capture(True)  # turn on daq waveform capture
                        t_sleep = 2  # need time to prepare acquisition
                        ts.log('Sleeping for %s seconds, to wait for the capture to prime.' % t_sleep)
                        ts.sleep(t_sleep)

                    if v_1_init != v_nom or v_2_init != v_nom or v_3_init != v_nom:
                        # Run Profile
                        ts.log('    Setting voltage: v_1 = %s  v_2 = %s  v_3 = %s for %s seconds' %
                               (v_1_init, v_2_init, v_3_init, t_hold))
                        # v_1_init = v_1_init*(grid.v_nom/v_nom)
                        # v_2_init = v_2_init*(grid.v_nom/v_nom)
                        # v_3_init = v_3_init*(grid.v_nom/v_nom)
                        grid.voltage(voltage=(v_1_init, v_2_init, v_3_init))
                        ts.sleep(t_hold)

                    ts.log('    Setting voltage: v_1 = %s  v_2 = %s  v_3 = %s for %s seconds' %
                           (v_1, v_2, v_3, t_trip+1))
                    # v_1 = v_1*(grid.v_nom/v_nom)
                    # v_2 = v_2*(grid.v_nom/v_nom)
                    # v_3 = v_3*(grid.v_nom/v_nom)
                    grid.voltage((v_1, v_2, v_3))
                    ts.sleep(t_trip+1)

                # get data from daq waveform capture
                done = False
                countdown = int(t_trip) + 10
                while not done and countdown > 0:
                    status = daq.waveform_status()
                    if status == 'COMPLETE':
                        ds = daq.waveform_capture_dataset()
                        done = True
                    elif status == 'INACTIVE':
                        ts.log('Waveform capture inactive')
                        raise script.ScriptFail('Waveform capture inactive')
                    elif status == 'ACTIVE':
                        ts.log('Waveform capture active, sleeping')
                        ts.sleep(1)
                        countdown -= 1

                # save captured data set to capture file in SVP result directory
                if ds is not None:
                    ds.to_csv(ts.result_file_path(filename))
                    ts.result_file(filename)

                    wf = waveform.Waveform(ts)
                    wf.from_csv(ts.result_file_path(filename))

                    # wf.compute_rms_data(phase=1)
                    # time_data = wf.rms_data['1'][0]  # Time
                    # voltage_data_1 = wf.rms_data['1'][1]  # Voltage
                    # current_data_1 = wf.rms_data['1'][2]  # Current
                    # plt.figure(1)
                    # plt.plot(time_data, voltage_data_1)
                    # plt.figure(2)
                    # plt.plot(time_data, current_data_1)
                    # plt.show()

                    if phase_test[2] == 'p1':
                        channel_data = [wf.channel_data[1], wf.channel_data[4]]
                    elif phase_test[2] == 'p2':
                        channel_data = [wf.channel_data[2], wf.channel_data[5]]
                    else:
                        channel_data = [wf.channel_data[3], wf.channel_data[6]]

                    _, current_data_1 = waveform_analysis.calculateRmsOfSignal(data=channel_data[0],
                                                                               windowSize=20,  # ms
                                                                               samplingFrequency=f_sample)

                    time_data, voltage_data_1 = waveform_analysis.calculateRmsOfSignal(data=channel_data[1],
                                                                                       windowSize=20,  # ms
                                                                                       samplingFrequency=f_sample)
                    # plt.figure(1)
                    # plt.plot(time_data, voltage_data_1, 'r',  time_data, current_data_1, 'b')
                    # plt.show()

                    v_window = 10  # v_window is the window around the nominal RMS voltage where the VRT test is started
                    volt_idx = [idx for idx, i in enumerate(voltage_data_1) if
                                (i <= (v_nom - v_window) or i >= (v_nom + v_window))]
                    if len(volt_idx) != 0:
                        t_start = time_data[min(volt_idx)]
                    else:
                        t_start = 0
                        ts.log_warning('Voltage deviation started before the waveform capture.')

                    ac_current_idx = [idx for idx, i in enumerate(current_data_1) if i <= 0.1*p_rated]
                    if len(ac_current_idx) != 0:
                        trip_time = time_data[min(ac_current_idx)]

                    t_trip_meas = trip_time - t_start
                    ts.log('Voltage change started at %s, EUT trip at %s.  Total trip time: %s sec.' %
                           (t_start, trip_time, t_trip_meas))

                    # Determine pass/fail
                    if t_trip_meas <= t_trip:
                        passfail = 'Pass'
                    else:
                        passfail = 'Fail'
                else:
                    ts.log_warning('No waveform data collected')
                    raise

                result_summary.write('%s, %s, %s, %s, %s \n' %
                                     (passfail, ts.config_name(), t_trip, t_trip_meas, filename))

        result = script.RESULT_COMPLETE

    except script.ScriptFail, e:
        reason = str(e)
        if reason:
            ts.log_error(reason)
    finally:
        if eut is not None:
            eut.close()
        if grid is not None:
            grid.close()
        if load is not None:
            load.close()
        if pv is not None:
            pv.close()
        if daq is not None:
            daq.close()
        if chil is not None:
            chil.close()
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

info.param_group('eut', label='EUT Parameters', glob=True)
info.param('eut.p_rated', label='P_rated', default=3000)
info.param('eut.v_nom', label='V_nom', default=240.0)
info.param('eut.phases', label='Phases', default='Single Phase',
           values=['Single Phase', '3-Phase 3-Wire', '3-Phase 4-Wire'])
info.param('eut.v_msa', label='V_msa', default=2.0)
info.param('eut.t_msa', label='T_msa', default=1.0)
info.param('eut.t_trip', label='Trip Time', default=5)

info.param_group('vrt', label='Test Parameters')
info.param('vrt.v_test', label='Voltage (% of nomimal)', default=100.0)
info.param('vrt.t_hold', label='Hold Duration (secs)', default=2.0)
info.param('vrt.n_r', label='Number of test repetitions', default=5)
info.param('vrt.phase_1', label='Phase 1 Fault Tests', default='Enabled', values=['Disabled', 'Enabled'],
           active='eut.phases', active_value=['3-Phase 3-Wire', '3-Phase 4-Wire'])
info.param('vrt.phase_2', label='Phase 2 Fault Tests', default='Enabled', values=['Disabled', 'Enabled'],
           active='eut.phases', active_value=['3-Phase 3-Wire', '3-Phase 4-Wire'])
info.param('vrt.phase_3', label='Phase 3 Fault Tests', default='Enabled', values=['Disabled', 'Enabled'],
           active='eut.phases', active_value=['3-Phase 3-Wire', '3-Phase 4-Wire'])

gridsim.params(info)
pvsim.params(info)
der.params(info)
das.params(info)
hil.params(info)

# info.logo('sunspec.gif')

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


