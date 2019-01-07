'''
Copyright (c) 2016, Sandia National Labs and SunSpec Alliance
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

Written by Sandia National Laboratories, Loggerware, and SunSpec Alliance
Questions can be directed to Jay Johnson (jjohns2@sandia.gov)
'''

# #!C:\Python27\python.exe

import sys
import os
import traceback
from svpelab import gridsim
from svpelab import pvsim
from svpelab import das
from svpelab import der
from svpelab import hil
from svpelab import loadsim
from svpelab import switch
from svpelab import waveform, waveform_analysis

import math
import operator
import sunspec.core.client as client

import script
import openpyxl
import matplotlib.pyplot as plt

def run_anti_islanding(grid=None, load=None, daq=None, test_iteration=None, q=None):
    ds = None
    filename = 'AI_%s_%s' % (test_iteration, q)

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

    # get data from daq waveform capture
    done = False
    countdown = 3
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
        ds.to_csv(ts.result_file_path(filename + '.csv'))
        ts.result_file(filename + '.csv')

        wf = waveform.Waveform(ts)
        wf.from_csv(ts.result_file_path(filename + '.csv'))

        wf.compute_rms_data(phase=1)
        time_data = wf.rms_data['1'][0]  # Time
        voltage_data_1 = wf.rms_data['1'][1]  # Voltage
        current_data_1 = wf.rms_data['1'][2]  # Current

        fig, ax1 = plt.subplots()
        ax1.plot(time_data, voltage_data_1, 'b-')
        ax1.set_xlabel('time (s)')
        ax1.set_ylabel('Voltage (V)', color='b')
        ax1.tick_params('y', colors='b')

        ax2 = ax1.twinx()
        ax2.plot(time_data, current_data_1, 'r.')
        ax2.set_ylabel('Current (A)', color='r')
        ax2.tick_params('y', colors='r')
        plt.show()
        fig.savefig(filename + '.png')

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

    daq.data_capture(False)
    ds = daq.data_capture_dataset()
    ds.to_csv(ts.result_file_path(filename))
    ts.result_file(filename)
    ts.log('Saving data capture %s' % (filename))

    return trip_time

def test_run():

    result = script.RESULT_FAIL
    daq = None
    pv = None
    grid = None
    chil = None
    eut = None
    load = None
    sw_load = sw_utility = sw_eut = None

    try:

        # get EUT parameters
        phases = ts.param_value('ratings.phases')
        p_rated = ts.param_value('ratings.p_rated')
        p_min = ts.param_value('ratings.p_min')
        f_nom = ts.param_value('ratings.f_nom')
        v_nom = ts.param_value('ratings.v_nom')

        # get voltage ride-through parameters
        h_n_points = ts.param_value('vrt.h_n_points')
        h_curve_num = ts.param_value('vrt.h_curve_num')
        h_time = ts.param_value('vrt.h_curve.h_time')
        h_volt = ts.param_value('vrt.h_curve.h_volt')

        l_n_points = ts.param_value('vrt.l_n_points')
        l_curve_num = ts.param_value('vrt.l_curve_num')
        l_time = ts.param_value('vrt.l_curve.l_time')
        l_volt = ts.param_value('vrt.l_curve.l_volt')

        vrt_ride_through = ts.param_value('vrt.ride_through')

        hc_n_points = ts.param_value('vrt.hc_n_points')
        hc_curve_num = ts.param_value('vrt.hc_curve_num')
        hc_time = ts.param_value('vrt.hc_curve.hc_time')
        hc_volt = ts.param_value('vrt.hc_curve.hc_volt')

        lc_n_points = ts.param_value('vrt.lc_n_points')
        lc_curve_num = ts.param_value('vrt.lc_curve_num')
        lc_time = ts.param_value('vrt.lc_curve.lc_time')
        lc_volt = ts.param_value('vrt.lc_curve.lc_volt')

        # get frequency ride-through parameters
        f_h_n_points = ts.param_value('frt.h_n_points')
        f_h_curve_num = ts.param_value('frt.h_curve_num')
        f_h_time = ts.param_value('frt.h_curve.h_time')
        f_h_freq = ts.param_value('frt.h_curve.h_freq')

        f_l_n_points = ts.param_value('frt.l_n_points')
        f_l_curve_num = ts.param_value('frt.l_curve_num')
        f_l_time = ts.param_value('frt.l_curve.l_time')
        f_l_freq = ts.param_value('frt.l_curve.l_freq')

        frt_ride_through = ts.param_value('frt.ride_through')

        f_hc_n_points = ts.param_value('frt.hc_n_points')
        f_hc_curve_num = ts.param_value('frt.hc_curve_num')
        f_hc_time = ts.param_value('frt.hc_curve.hc_time')
        f_hc_freq = ts.param_value('frt.hc_curve.hc_freq')

        f_lc_n_points = ts.param_value('frt.lc_n_points')
        f_lc_curve_num = ts.param_value('frt.lc_curve_num')
        f_lc_time = ts.param_value('frt.lc_curve.lc_time')
        f_lc_freq = ts.param_value('frt.lc_curve.lc_freq')

        # volt-var parameters
        vv_mode = ts.param_value('vv.vv_mode')
        if vv_mode == 'VV11 (watt priority)':
            deptRef = 1
        else:  # vv_mode == 'VV12 (var priority)'
            deptRef = 2
        vv_curve_num = ts.param_value('vv.curve_num')
        vv_volt = ts.param_value('vv.curve.volt')
        vv_var = ts.param_value('vv.curve.var')
        vv_n_points = ts.param_value('vv.n_points')

        # SPF parameters
        pf = ts.param_value('spf.pf')

        # RR parameters
        worst_rr = ts.param_value('rr.normal_rr')

        # FW parameters
        fw_mode = ts.param_value('fw.fw_mode')
        #fw_mode == 'FW21 (FW parameters)':
        WGra = ts.param_value('fw.WGra')
        HzStr = ts.param_value('fw.HzStr')
        HzStop = ts.param_value('fw.HzStop')
        HysEna = ts.param_value('fw.HysEna')
        HzStopWGra = ts.param_value('fw.HzStopWGra')

        #'FW22 (pointwise FW)'
        fw_curve_num = ts.param_value('fw.curve_num')
        fw_n_points = ts.param_value('fw.n_points')
        fw_freq = ts.param_value('fw.curve.freq')
        fw_w = ts.param_value('fw.curve.W')

        # VW
        volt_ref = ts.param_value('vw.volt_ref')
        vw_points = ts.param_value('vw.vw_points')
        vw_v = ts.param_value('vw.curve.volt')
        vw_w = ts.param_value('vw..curve.W')
        vw_deptref = ts.param_value('vw.curve.vw_deptref')

        n_sets = ts.param_value('functions.n_sets')
        sets = ts.param_value('functions.sets.set')

        ''' IEEE 1547.1-2005 5.7.1.2 Procedure
        a) Configure test circuit.
        b) Connect the EUT according to the instructions and specifications provided by the manufacturer.
        c) Set all EUT input source parameters to the nominal operating conditions for the EUT.
        '''

        ts.log('Configuring hardware-in-the-loop environment (if applicable).')
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # initialize data acquisition
        sc_points = ['V_TARGET', 'Q_TARGET']
        daq = das.das_init(ts, sc_points=sc_points)

        # grid simulator is initialized with test parameters and enabled
        grid = gridsim.gridsim_init(ts)

        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts)

        eut = der.der_init(ts)
        eut.config()

        # load initialization
        ts.log('Configuring RLC Loads')
        load = loadsim.loadsim_init(ts)
        load.config()
        ts.log('Loadsim: %s' % load.info())

        # configure switches
        sw_load = switch.switch_init(ts, id='switch_load')
        sw_utility = switch.switch_init(ts, id='switch_utility')
        sw_eut = switch.switch_init(ts, id='switch_eut')

        # trip times and averages will be stored in a list of dictionaries with the following characteristics:
        # t_trips = [{'power_level_pct': 100,
        #             'average_time': 0.36, 'q load longest time': 98, 'longest_time': 0.52, * index = fnc set number
        #             'set': 1, 'tests': [{'number': 1, 'q_value': 100, 'times': [0.2]}      * index = test number
        #                                {'number': 2, 'q_value': 101, 'times': [0.25]}
        #                                {'number': 3, 'q_value': 102, 'times': [0.25]}
        #                                {'number': 4, 'q_value': 103, 'times': [0.25]}
        #                                {'number': 5, 'q_value': 104, 'times': [0.25]}
        #                                {'number': 6, 'q_value': 105, 'times': [0.25]}
        #                                {'number': 7, 'q_value': 100, 'times': [0.25]}
        #                                {'number': 8, 'q_value': 99, 'times': [0.25]}
        #                                {'number': 9, 'q_value': 98, 'times': [0.52, 0.55, 0.56]} *from SA8.2.2(a)(1)
        #                                {'number': 10, 'q_value': 97, 'times': [0.25]}
        #                                {'number': 11, 'q_value': 98, 'times': [0.25]}
        #                                {'number': 12, 'q_value': 95, 'times': [0.25]}]
        #            {'power_level_pct': 100, 'average_time': 0.37, 'q load longest time': 100, 'longest_time': 0.79,
        #             'set': 2, 'tests': [{'number': 1, 'q_value': 100, 'times': [0.25]
        #                                {'number': 2, 'q_value': 101, 'times': [0.25]}
        #                                {'number': 3, 'q_value': 102, 'times': [0.25]}
        #                                {'number': 4, 'q_value': 103, 'times': [0.25]}
        #                                {'number': 5, 'q_value': 104, 'times': [0.25]}
        #                                {'number': 6, 'q_value': 105, 'times': [0.25]}
        #                                {'number': 7, 'q_value': 100, 'times': [0.79, 0.86, 0.87]} *from SA8.2.2(a)(1)
        #                                {'number': 8, 'q_value': 99, 'times': [0.25]}
        #                                {'number': 9, 'q_value': 98, 'times': [0.25]}
        #                                {'number': 10, 'q_value': 97, 'times': [0.25]}
        #                                {'number': 11, 'q_value': 98, 'times': [0.25]}
        #                                {'number': 12, 'q_value': 95, 'times': [0.25]}]
        #            {'power_level_pct': 100, 'average_time': 0.56, 'q load longest time': 102, 'longest_time': 0.80,
        #             'set': 3, 'tests': [{'number': 1, 'q_value': 100, 'times': [0.80, 0.86, 8.7]} *from SA8.2.2(c)(3)
        #                                {'number': 2, 'q_value': 101, 'times': [0.76, 0.83, 8.7]} *from SA8.2.2(c)(3)
        #                                {'number': 3, 'q_value': 102, 'times': [0.83, 0.87, 8.7]} *from SA8.2.2(a)(1)
        #                                {'number': 4, 'q_value': 103, 'times': [0.25]}
        #                                {'number': 5, 'q_value': 104, 'times': [0.25]}
        #                                {'number': 6, 'q_value': 105, 'times': [0.29]}
        #                                {'number': 13, 'q_value': 106, 'times': [0.25]} * from IEEE 1547.1 5.7.1.2(l)
        #                                {'number': 7, 'q_value': 100, 'times': [0.25]}
        #                                {'number': 8, 'q_value': 99, 'times': [0.25]}
        #                                {'number': 9, 'q_value': 98, 'times': [0.25]}
        #                                {'number': 10, 'q_value': 97, 'times': [0.25]}
        #                                {'number': 11, 'q_value': 98, 'times': [0.25]}
        #                                {'number': 12, 'q_value': 95, 'times': [0.25]}],
        #            [{'power_level_pct': 66, 'average_time': 0.36, 'q load longest time': 100, 'longest_time': 0.79,
        #             'set': 3, ...],
        #            [{'power_level_pct': 33, 'average_time': 0.42, 'q load longest time': 100, 'longest_time': 0.82,
        #             'set': 3, ...]

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        if phases == 'Single Phase':
            # single phase to be cleaned up
            result_summary.write('Result, Test Name, t_trip, t_trip_meas, Dataset File\n')
        else:
            result_summary.write('Result, Test Name, t_trip, t_trip_meas, Dataset File\n')

        worst_set = None
        t_trips = []  # collects the average trip time for each function set
        average_times = []
        for max_power in [100, 66, max(33, p_min)]:
            try:
                eut.limit_max_power(params={'ModEna': True, 'WMaxPct': max_power,
                                            'WinTms': 0, 'RmpTms': 0, 'RvrtTms': 0})
            except Exception, e:
                ts.log_warning('Could not set the power reduction in the inverter. Error: %s. '
                               'Using PV simulator instead.' % e)
                pv.power_set(max_power)

            if max_power == 100:
                functions_to_test = range(1, n_sets+1)
            else:
                functions_to_test = worst_set

            for test_set in list(functions_to_test):
                '''
                d) Set and verify the EUT trip parameters are at maximum adjustable voltage and frequency ranges,
                maximum adjustable response durations as previously determined in the voltage and frequency
                ride-through sections, and grid support functions are set as described below.

                    i) For each of the functions to be verified as compatible with unintentional islanding
                    compliance, the manufacturer shall identify parameters that adversely affect islanding detection
                    and state the worst-case condition for the EUT to be anti-islanding compliant. The worst-case
                    conditions shall be identified and documented by the manufacturer and test laboratory for
                    evaluation under this test program.

                    ii) Given the function configuration to be validated, unintentional islanding tests shall be
                    performed to validate each unique combination of functions grouped together that can be
                    simultaneously enabled as stated by the manufacturer. Functions, which may be grouped within
                    unique function combination groupings, are not required to be retested.

                    iii) For example, to test the EUT for hypothetical functions A, B, and C that can be enabled
                    simultaneously, those functions shall be enabled and tested as a group. See Table SA8.1. If the
                    EUT passes the test for this grouping then no additional tests or combinations of A, B, and C
                    are required. However, to certify another function, D, which is mutually exclusive with C, then
                    the grouping A, B, D must be tested as well.
                '''

                functions = sets[test_set]
                ts.log('The following functions will be enabled for this test: %s' % functions)
                if 'VRT' in functions:
                    ts.log('    Setting VRT settings.')
                    if vrt_ride_through == 'Yes':
                        eut.vrt_stay_connected_high(params={'Ena': True, 'ActCrv': hc_curve_num, 'NPt': hc_n_points,
                                                            'curve': {'Tms': hc_time, 'V': hc_volt}})
                        eut.vrt_stay_connected_low(params={'Ena': True, 'ActCrv': lc_curve_num, 'NPt': lc_n_points,
                                                           'curve': {'Tms': lc_time, 'V': lc_volt}})
                    eut.vrt_trip_high(params={'Ena': True, 'ActCrv': h_curve_num, 'NPt': h_n_points,
                                              'curve': {'Tms': h_time, 'V': h_volt}})
                    eut.vrt_trip_low(params={'Ena': True, 'ActCrv': l_curve_num, 'NPt': l_n_points,
                                             'curve': {'Tms': l_time, 'Hz': l_volt}})
                if 'FRT' in functions:
                    ts.log('    Setting FRT settings.')
                    if frt_ride_through == 'Yes':
                        eut.frt_stay_connected_high(params={'Ena': True, 'ActCrv': f_hc_curve_num, 'NPt': f_hc_n_points,
                                                            'curve': {'Tms': f_hc_time, 'Hz': f_hc_freq}})
                        eut.frt_stay_connected_low(params={'Ena': True, 'ActCrv': f_lc_curve_num, 'NPt': f_lc_n_points,
                                                           'curve': {'Tms': f_lc_time, 'Hz': f_lc_freq}})
                    eut.frt_trip_high(params={'Ena': True, 'ActCrv': f_h_curve_num, 'NPt': f_h_n_points,
                                              'curve': {'Tms': f_h_time, 'Hz': f_h_freq}})
                    eut.frt_trip_low(params={'Ena': True, 'ActCrv': f_l_curve_num, 'NPt': f_l_n_points,
                                             'curve': {'Tms': f_l_time, 'Hz': f_l_freq}})
                if 'SPF' in functions:
                    ts.log('    Setting SPF settings.')
                    eut.fixed_pf(params={'ModEna': True, 'PF': pf, 'WinTms': 0, 'RmpTms': 0, 'RvrtTms': 0})
                if 'VV' in functions:
                    ts.log('    Setting VV settings.')
                    eut.volt_var(params={'ModEna': True, 'ActCrv': vv_curve_num, 'NPt': vv_n_points, 'RmpTms': 0,
                                         'RvrtTms': 0, 'curve': {'DeptRef': deptRef, 'v': vv_volt, 'var': vv_var}})
                if 'RR' in functions:
                    ts.log('    Setting RR settings.')
                    eut.settings(params={'WGra': worst_rr})
                if 'FW' in functions:
                    ts.log('    Setting FW settings.')
                    if fw_mode == 'FW21 (FW parameters)':
                        eut.freq_watt_param(params={'ModEna': True, 'HysEna': HysEna, 'WGra': WGra, 'HzStr': HzStr,
                                                    'HzStop': HzStop, 'HzStopWGra': HzStopWGra})
                    else:
                        eut.freq_watt(params={'ModEna': True, 'ActCrv': fw_curve_num, 'NPt': fw_n_points, 'WinTms': 0,
                                              'RmpTms': 0, 'RvrtTms': 0, 'curve': {'hz': fw_freq, 'w': fw_w}})
                if 'VW' in functions:
                    ts.log('    Setting VW settings.')
                    eut.volt_watt(params={'ModEna': True, 'ActCrv': 1, 'NCrv': 1, 'NPt': vw_points, 'WinTms': 0,
                                          'RvrtTms': 0, 'RmpTms': 0, 'curve': {'ActPt': 3, 'v': vw_v, 'w': vw_w,
                                                                               'DeptRef': vw_deptref, 'RmpPt1Tms': 0,
                                                                               'RmpDecTmm': 0, 'RmpIncTmm': 0}})

                '''
                e) Set the EUT (including the input source as necessary) to provide 100% of its rated output power.
                '''
                pv.power_set(p_rated*1.1)
                pv.power_on()

                '''
                f) Record all applicable settings.
                '''
                ## ts.log('Starting data capture for test = %d' % test_set)

                '''
                g) Set the Simulated EPS to the EUT nominal voltage +/- 2% and nominal frequency +/- 0.1 Hz.
                '''
                grid.voltage(v_nom)
                grid.freq(f_nom)

                '''
                h) Adjust the islanding load circuit in Figure 2 to provide a quality factor Qf of 1.0 +/- 0.05
                (when Qf is equal to 1.0, the following applies: PqL = PqC = 1.0*P). The value of Qf is to be
                determined by using the following equations as appropriate:

                Qf_targ = 1.00    # target quality factor of the parallel (RLC) resonant load
                P = das.ac_watts  # the real output power per phase of the unit (W)
                f = das.ac_freq   # ac frequency
                V = das.ac_voltage
                PqL_targ = 1.0*P  # target reactive power per phase consumed by the inductive load component (var)
                PqC_targ = 1.0*P  # target reactive power per phase consumed by the capacitive load component (var)

                L_targ = (V**2)/(2.*math.pi*f*P*Qf_targ)
                C_targ = (P*Qf_targ)/(2.*math.pi*f*(V**2))
                '''

                daq.data_sample()  # Sample before the grid voltage change
                data = daq.data_capture_read()
                if phases == 'Single Phase':
                    p_now = data.get('AC_P_1')
                    q_now = data.get('AC_Q_1')
                    ts.log('The active power of the EUT is %0.2f W and the reactive power is %0.2f var.' % (p_now, q_now))
                else:
                    p_now, p_now_2, p_now_3 = data.get('AC_P_1'), data.get('AC_P_2'), data.get('AC_P_3')
                    q_now, q_now_2, q_now_3 = data.get('AC_Q_1'), data.get('AC_Q_2'), data.get('AC_Q_3')
                    ts.log('The active power of the EUT is p1=%0.2f, p2=%0.2f, p3=%0.2f W '
                           'and the reactive power is q1=%0.2f, q2=%0.2f, q3=%0.2f var.' %
                           (p_now, p_now_2, p_now_3, q_now, q_now_2, q_now_3))

                # Calculate the RLC values for the test
                Qf = 1.0
                l_value = (v_nom**2)/(2.*math.pi*f_nom*p_now*Qf)
                c_value = (p_now*Qf)/(2.*math.pi*f_nom*(v_nom**2))
                r_value = Qf/(math.sqrt(c_value/l_value))

                ts.log('Setting RLC loads: R = %0.3f Ohms, L = %0.6f H, C = %0.6f F.' % (r_value, l_value, c_value))
                load.resistance(r_value)
                load.inductance(l_value)
                load.capacitance(c_value)

                # # tune the capacitance starting place
                # ts.log('The capacitive load on each phase should create reactive power equal to the active power of the'
                #        ' EUT (%0.2f VAr) to get a Qf of 1.0; however, we must account for the VArs of the EUT, so the  '
                #        'capacitive reactive power is set to EUT active power - EUT reactive power, or %0.2f VAr' %
                #        (p_now, (p_now-q_now)))
                # if 'VV' in functions or 'SPF' in functions:
                #     ts.log('Note: When tuning for the current balance in this step with a nonunity output PF, '
                #            'there will be an imbalance between the L and C load components to account for the EUT '
                #            'reactive current. The EUT reactive output current shall be measured and algebraically '
                #            'added to the appropriate reactive load component when calculating Qf.')

                # tune the inductance starting place
                # ts.log('The inductive load should absorb the reactive power equal to the reactive power of the '
                #        'capacitive load + EUT reactive power (%0.2f VAr) to get a Qf of 1.0' % p_now)
                # Note: only measure the fundamental reactive power of the load
                # PqL = p_now
                # load.inductor_q(PqL)  # reactive power per phase consumed by the inductive load component (VArs)
                # PqC = p_now-q_now
                # load.capacitor_q(PqC)  # reactive power per phase consumed by the capacitive load (VArs)

                # tune the resistor starting place
                # ts.log('The resistive load should consume the active power of the EUT, %0.2f W' % p_now)
                # load.resistance_p(p_now)  # reactive power per phase consumed by the inductive load component (VArs)

                # run check on the RLC
                # daq.data_sample()  # Sample before the grid voltage change
                # data = daq.data_capture_read()
                # p_now = data.get('AC_P_1')
                # Qf = float(math.sqrt(PqL*PqC)/p_now)   # the quality factor of the parallel (RLC) resonant load
                # ts.log('Quality factor (Qf) of the parallel resonant load is %0.3f. 1.000 is the target. ' % Qf)

                '''
                i) Close switch S1, switch S2, and switch S3, and wait until the EUT produces the desired power level.
                '''
                if sw_load is not None:
                    sw_load.switch_close()
                if sw_utility is not None:
                    sw_utility.switch_close()
                if sw_eut is not None:
                    sw_eut.switch_close()

                '''
                j) Adjust R, L, and C until the fundamental frequency current through switch S3 is less than 2% of the
                rated current of the EUT on a steady-state basis in each phase.
                '''
                i1, i2, i3 = grid.meas_current()
                eut_a_rtg = eut.nameplate().get('ARtg')  # EUT current rating
                ts.log('Need to have utility currents below 2%% of the EUT rated current.')
                ts.log('Utility currents are %s, %s, %s A and 2%% of the EUT current is %0.2f A.' %
                       (i1, i2, i3, 0.02*eut_a_rtg))
                if i1 + i2 + i3 > eut_a_rtg:
                    load.tune_current(i=0.02*eut_a_rtg)

                '''
                k) Open switch S3 and record the time between the opening of switch S3 and when the EUT ceases to
                energize the RLC load.
                '''
                trips = {}
                q = 100
                trip_time_sum = 0
                total_tests = 0

                # run data capture
                f_sample = 5000
                t_trip = 2.0
                t_pretrig = 0.5
                wfm_config_params = {
                    'sample_rate': f_sample,
                    'pre_trigger': t_pretrig,
                    'post_trigger': t_trip+0.5,
                    'timeout': 30
                    }
                if phases == 'Single Phase':
                    wfm_config_params['channels'] = ['AC_V_1', 'AC_I_1', 'EXT']
                else:
                    wfm_config_params['channels'] = ['AC_V_1', 'AC_V_2', 'AC_V_3', 'AC_I_1', 'AC_I_2', 'AC_I_3', 'EXT']

                wfm_config_params['trigger_cond'] = 'Rising Edge'
                wfm_config_params['trigger_channel'] = 'EXT'
                wfm_config_params['trigger_level'] = 1  # 0-5 V signal
                daq.waveform_config(params=wfm_config_params)

                ts.log('Starting anti-islanding data capture for reactive power output of the EUT, q = 100%%')
                forced = False
                if forced:
                    daq.waveform_force_trigger()
                    ts.sleep(0.5)
                else:
                    # Start Waveform Capture
                    daq.waveform_capture(True)  # turn on daq waveform capture
                    t_sleep = 2  # need time to prepare acquisition
                    ts.log('Sleeping for %s seconds, to wait for the capture to prime.' % t_sleep)
                    ts.sleep(t_sleep)

                # get data from daq waveform capture
                ds = None
                filename = 'AI_%s_%s' % (1, 100)
                done = False
                countdown = 3
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
                    ds.to_csv(ts.result_file_path(filename + '.csv'))
                    ts.result_file(filename + '.csv')

                    wf = waveform.Waveform(ts)
                    wf.from_csv(ts.result_file_path(filename + '.csv'))

                    wf.compute_rms_data(phase=1)
                    time_data = wf.rms_data['1'][0]  # Time
                    voltage_data_1 = wf.rms_data['1'][1]  # Voltage
                    current_data_1 = wf.rms_data['1'][2]  # Current

                    fig, ax1 = plt.subplots()
                    ax1.plot(time_data, voltage_data_1, 'b-')
                    ax1.set_xlabel('time (s)')
                    ax1.set_ylabel('Voltage (V)', color='b')
                    ax1.tick_params('y', colors='b')

                    ax2 = ax1.twinx()
                    ax2.plot(time_data, current_data_1, 'r.')
                    ax2.set_ylabel('Current (A)', color='r')
                    ax2.tick_params('y', colors='r')
                    plt.show()
                    fig.savefig(filename + '.png')

                    if phases == 'Single Phase':
                        channel_data = [wf.channel_data[1], wf.channel_data[2]]
                    else:
                        channel_data = [wf.channel_data[1], wf.channel_data[4]]

                    # Collect RMS current and voltage data
                    _, current_data_1 = waveform_analysis.calculateRmsOfSignal(data=channel_data[0],
                                                                               windowSize=20,  # ms
                                                                               samplingFrequency=f_sample)

                    time_data, voltage_data_1 = waveform_analysis.calculateRmsOfSignal(data=channel_data[1],
                                                                                       windowSize=20,  # ms
                                                                                       samplingFrequency=f_sample)
                    # calculate trip time
                    trip_time = 0
                    # find current trip index from rms data.
                    ac_current_idx = [idx for idx, i in enumerate(current_data_1) if i <= 0.1*p_rated]
                    if len(ac_current_idx) != 0:
                        trip_time = time_data[min(ac_current_idx)]

                    t_trip_meas = trip_time - t_pretrig
                    ts.log('EUT trip at %s.  Total trip time: %s sec.' %
                           (trip_time, t_trip_meas))
                else:
                    ts.log_warning('Did not capture waveform data!')
                    t_trip_meas = -1

                trip_time_sum += t_trip_meas
                total_tests += 1
                t_trips.append({'power_level_pct': max_power, 'average_time': trip_time, 'q load longest time': q,
                                'tests': [{'number': 1, 'q_value': q, 'times': [trip_time]}]})

                # result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s\n' %
                #                      (passfail, ts.config_name(), power, v1, v2, v3, i1_pre, i2_pre, i3_pre,
                #                       i1_post, i2_post, i3_post,  filename))

                '''
                l) The test is to be repeated with the reactive load (either capacitive or inductive) adjusted in 1%
                increments or alternatively with the reactive power output of the EUT adjusted in 1% increments from
                95% to 105% of the initial balanced load component value.
                '''
                for q in [101, 102, 103, 104, 105, 100, 99, 98, 97, 96, 95]:
                    trip_time = run_anti_islanding(grid=grid, load=load, daq=daq, test_iteration=1, q=q)
                    trip_time_sum += trip_time
                    total_tests += 1
                    t_trips[len(t_trips)].get('tests').append({'number': 1, 'q_value': q, 'times': [trip_time]})
                    if t_trips[len(t_trips)].get['tests'].get['times'] < trip_time:
                        t_trips[len(t_trips)].get['longest_time'] = trip_time
                        t_trips[len(t_trips)].get['q load longest time'] = q

                '''
                If unit shutdown times are still increasing at the 95% or 105% points, additional 1% increments
                shall be taken until trip times begin decreasing.
                '''
                lowest_test_q = 95
                while trips.get('t_trip_%s' % lowest_test_q) > trips.get('t_trip_%s' % (lowest_test_q+1)):
                    q = lowest_test_q - 1
                    trip_time = run_anti_islanding(grid=grid, load=load, daq=daq, test_iteration=1, q=q)
                    trip_time_sum += trip_time
                    total_tests += 1
                    t_trips[len(t_trips)].get('tests').append({'number': 1, 'q_value': q, 'times': [trip_time]})
                    if t_trips[len(t_trips)].get['tests'] < trip_time:
                        t_trips[len(t_trips)].get['longest_time'] = trip_time
                        t_trips[len(t_trips)].get['q load longest time'] = q
                        lowest_test_q = q

                highest_test_q = 105
                while trips.get('t_trip_%s' % highest_test_q) > trips.get('t_trip_%s' % (highest_test_q-1)):
                    q = highest_test_q + 1
                    trip_time = run_anti_islanding(grid=grid, load=load, daq=daq, test_iteration=1, q=q)
                    trip_time_sum += trip_time
                    total_tests += 1
                    t_trips[len(t_trips)].get('tests').append({'number': 1, 'q_value': q, 'times': [trip_time]})
                    if t_trips[len(t_trips)].get['tests'].get['times'] < trip_time:
                        t_trips[len(t_trips)].get['longest_time'] = trip_time
                        t_trips[len(t_trips)].get['q load longest time'] = q
                        highest_test_q = q

                ''' SA8.2.2.
                a) Review the test results of IEEE 1547.1-2005 section 5.7.1.2 step (l) for the 1% load
                increment settings. Identify the load setting that yielded the longest run on time before tripping.
                    1) Run two additional test iterations for those identified load settings.
                    2) The average trip time is to be taken of the three test iterations to determine the worst
                    case trip time for the set of functions under test. Note that SA8.3.4 applies to the results
                    of all iterations.
                '''

                q = t_trips[len(t_trips)].get['q load longest time']  # repeat tests with the q with long run-on times
                for i in [2, 3]:
                    trip_time = run_anti_islanding(grid=grid, load=load, daq=daq, test_iteration=i, q=q)
                    trip_time_sum += trip_time
                    total_tests += 1
                    t_trips[len(t_trips)].get('tests').get['times'].append(trip_time)
                    if t_trips[len(t_trips)].get['tests'].get['times'] < trip_time:
                        t_trips[len(t_trips)].get['longest_time'] = trip_time
                        t_trips[len(t_trips)].get['q load longest time'] = q

                # determine the average trip time for the function set
                t_trips[len(t_trips)].get['average_time'] = float(trip_time_sum/total_tests)
                average_times.append(float(trip_time_sum/total_tests))

                '''
                b) Repeat IEEE 1547.1-2005 section 5.7.1.2 steps (d) through (l) and sub-step SA8.2.2(a)(1),
                with the next appropriate EUT function set activated in accordance with Table SA8.1.
                '''
                # End function sets

            '''
            c) After collecting the 1% load setting increments that yielded the longest average trip time for
            each function set detailed in Table SA8.1, determine which function set produced the longest
            average trip time.
                1) For that function set, review the trip time results and the 1% load setting increments
                that yielded the three longest trip times. The two settings that were not already
                subjected to three test iterations from sub-step (a)(1), shall be subjected to two
                additional test iterations.
                2) If the three longest trip times (including the trip time already subjected to 3 test
                iterations from sub-step (a)(1)) occur at nonconsecutive 1% load setting increments, the
                additional two iterations shall be run for all load settings in between.
            '''
            worst_set, max_average_time = max(average_times)
            ts.log('The worst set was %s with an average trip time of %0.2f' % (sets[worst_set], max_average_time))

            # sort through all the tests and find the q tests that had the worst times. Pick the 2nd and 3rd worst
            q0 = 96  # worst run on time
            q1 = 97  # 2nd worst run on time
            q2 = 98  # 3rd worst run on time
            new_q = [q1, q2]
            ts.log('Testing all the q values between the 3 worst cases. q = %s' % range(min(new_q), max(new_q)))

            for q in range(min(new_q), max(new_q)):
                if q != q0:  # don't retest the worst case of run on time
                    for i in [2, 3]:
                        trip_time = run_anti_islanding(grid=grid, load=load, daq=daq, test_iteration=i, q=q)
                        t_trips[len(t_trips)].get('tests').get['times'].append(trip_time)
                        if t_trips[len(t_trips)].get['tests'].get['times'] < trip_time:
                            t_trips[len(t_trips)].get['longest_time'] = trip_time
                            t_trips[len(t_trips)].get['q load longest time'] = q

            # End tests for that power level

        '''
        d) For that function set identified in (c), repeat IEEE 1547.1-2005 section 5.7.1.2 step (n).

        IEEE 1547.1-2005 section 5.7.1.2 step (n)
        Repeat steps d) through m) with the test input source adjusted to limit the EUT output power to 66%.
        This value is allowed to be between 50% and 95% of rated output power and is intended to evaluate
        the EUT at less than full power and under the condition where the available output is determined or
        limited by the input source. If the EUT does not provide this mode of operation, then set the EUT to
        control the output power to the specified level.
        '''

        '''
        e) For that function set identified in (c), repeat IEEE 1547.1-2005 section 5.7.1.2 step (o).

        IEEE 1547.1-2005 section 5.7.1.2 step (o)
        Repeat steps d) through m) with the EUT output power set via software or hardware to 33% of its
        nominal rating with the test input source capable of supplying at least 150% of the maximum input
        power rating of the EUT over the entire range of EUT input voltages. For units that are incapable of
        setting or commanding an output power level, the EUT output power shall be limited via the input
        power source. For units that are incapable of operating at 33%, the EUT shall be tested at the lowest
        output power the EUT will support. This step is intended to evaluate the EUT at low power and
        under the condition where the available output is determined or limited by the EUT control setting.
        If the EUT does not provide this mode of operation, then set the input source to meet the specified
        output power level.
        '''
        # End tests at the 3 power levels.

        result = script.RESULT_COMPLETE

    except script.ScriptFail, e:
        reason = str(e)
        if reason:
            ts.log_error(reason)
    finally:
        if daq is not None:
            daq.close()
        if pv is not None:
            pv.close()
        if grid is not None:
            grid.close()
        if eut is not None:
            eut.close()
        if chil is not None:
            chil.close()
        if load is not None:
            load.close()
        if sw_load is not None:
            sw_load.close()
        if sw_utility is not None:
            sw_utility.close()
        if sw_eut is not None:
            sw_eut.close()

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

info.param_group('ratings', label='DER Ratings')
info.param('ratings.phases', label='Phases', default='Single Phase',
           values=['Single Phase', '3-Phase 3-Wire', '3-Phase 4-Wire'])
info.param('ratings.p_rated', label='Prated', default=3000)
info.param('ratings.p_min', label='Pmin', default=3000*0.2, desc='Lowest output power the EUT will support')
info.param('ratings.f_nom', label='Nominal EUT Frequency (Hz)', default=60.)
info.param('ratings.v_nom', label='Nominal EUT Voltage (V)', default=240.)

info.param_group('functions', label='Functions to include in the Anti-Islanding Tests.')

# VRT parameters
info.param('functions.vrt', label='Include VRT?', default='Yes', values=['Yes', 'No'])
info.param_group('vrt', label='VRT Settings', active='functions.vrt', active_value=['Yes'])
info.param('vrt.ramp_time', label='Ramp Time (seconds)', default=0,
           desc='Ramp time in seconds.'
                'A value of 0 indicates function should not ramp, but step.')
info.param('vrt.time_window', label='Time Window (seconds)', default=0,
           desc='Time window for VRT change. Randomized time window for operation.'
                'A value of 0 indicates VRT executes immediately.')
info.param('vrt.timeout_period', label='Timeout Period (seconds)', default=0,
           desc='Time period before function reverts to default state. '
                'A value of 0 indicates function should not revert.')

# Define points for HVRT must trip curves
info.param('vrt.h_curve_num', label='HVRT Curve number', default=1, values=[1,2,3,4])
info.param('vrt.h_n_points', label='Number of (t, V) pairs (2-10)', default=4, values=[2,3,4,5,6,7,8,9,10])
info.param_group('vrt.h_curve', label='HVRT Curve Trip Points', index_count='vrt.h_n_points', index_start=1,
                 desc='Curve is assumed to be vertical from 1st point and horizontal from last point.')
info.param('vrt.h_curve.h_time', label='Time (sec)', default=0., desc='Time curve point')
info.param('vrt.h_curve.h_volt', label='Volt (%Vref)', default=100., desc='Volt curve point')

# Define points for LVRT must trip curves
info.param('vrt.l_curve_num', label='LVRT Curve number', default=1, values=[1,2,3,4])
info.param('vrt.l_n_points', label='Number of (t, V) pairs (2-10)', default=4, values=[2,3,4,5,6,7,8,9,10])
info.param_group('vrt.l_curve', label='LVRT Curve Trip Points', index_count='vrt.l_n_points', index_start=1,
                 desc='Curve is assumed to be vertical from 1st point and horizontal from last point.')
info.param('vrt.l_curve.l_time', label='Time (sec)', default=0., desc='Time curve point')
info.param('vrt.l_curve.l_volt', label='Volt (%Vref)', default=100., desc='Volt curve point')

# Define points for HVRT must remain connected curves
info.param('vrt.ride_through', label='Does the test have ride-through curves?', default='Yes',
           values=['Yes', 'No'])
info.param('vrt.hc_curve_num', label='HVRT must remain connected curve number',
           active='vrt.ride_through', active_value=['Yes'], default=1, values=[1,2,3,4])
info.param('vrt.hc_n_points', label='Number of (t, V) pairs (2-10)',
           active='vrt.ride_through', active_value=['Yes'], default=4, values=[2,3,4,5,6,7,8,9,10])
info.param_group('vrt.hc_curve', label='HVRT Curve Must Remain Connected Points',
                 active='vrt.ride_through', active_value=['Yes'],
                 index_count='vrt.hc_n_points', index_start=1,
                 desc='Curve is assumed to be vertical from 1st point and horizontal from last point.')
info.param('vrt.hc_curve.hc_time', label='Time (sec)',
           active='vrt.ride_through', active_value=['Yes'], default=0., desc='Time curve point')
info.param('vrt.hc_curve.hc_volt', label='Volt (%Vref)',
           active='vrt.ride_through', active_value=['Yes'], default=100., desc='Volt curve point')

# Define points for LVRT must remain connected curves
info.param('vrt.lc_curve_num', label='LVRT must remain connected curve number)',
           active='vrt.ride_through', active_value=['Yes'], default=1, values=[1,2,3,4])
info.param('vrt.lc_n_points', label='Number of (t, V) pairs (2-10)',
           active='vrt.ride_through', active_value=['Yes'], default=4, values=[2,3,4,5,6,7,8,9,10])
info.param_group('vrt.lc_curve', label='LVRT Curve Must Remain Connected Points',
                 active='vrt.ride_through', active_value=['Yes'],
                 index_count='vrt.lc_n_points', index_start=1,
                 desc='Curve is assumed to be vertical from 1st point and horizontal from last point.')
info.param('vrt.lc_curve.lc_time', label='Time (sec)',
           active='vrt.ride_through', active_value=['Yes'], default=0., desc='Time curve point')
info.param('vrt.lc_curve.lc_volt', label='Volt (%Vref)',
           active='vrt.ride_through', active_value=['Yes'], default=100., desc='Volt curve point')

# ## FRT parameters
info.param('functions.frt', label='Include FRT?', default='Yes', values=['Yes', 'No'])
info.param_group('frt', label='FRT Settings', active='functions.frt', active_value=['Yes'])

# Define points for HFRT must trip curves
info.param('frt.h_curve_num', label='HFRT Curve number', default=1, values=[1,2,3,4])
info.param('frt.h_n_points', label='Number of (t, F) pairs (2-10)', default=4, values=[2,3,4,5,6,7,8,9,10])
info.param_group('frt.h_curve', label='HFRT Curve Trip Points', index_count='frt.h_n_points', index_start=1,
                 desc='Curve is assumed to be vertical from 1st point and horizontal from last point.')
info.param('frt.h_curve.h_time', label='Time (sec)', default=0., desc='Time curve point')
info.param('frt.h_curve.h_freq', label='Freq (%Fnom)', default=100., desc='Freq curve point')

# Define points for LFRT must trip curves
info.param('frt.l_curve_num', label='LFRT Curve number', default=1, values=[1,2,3,4])
info.param('frt.l_n_points', label='Number of (t, F) pairs (2-10)', default=4, values=[2,3,4,5,6,7,8,9,10])
info.param_group('frt.l_curve', label='LFRT Curve Trip Points', index_count='frt.l_n_points', index_start=1,
                 desc='Curve is assumed to be vertical from 1st point and horizontal from last point.')
info.param('frt.l_curve.l_time', label='Time (sec)', default=0., desc='Time curve point')
info.param('frt.l_curve.l_freq', label='Freq (%Fnom)', default=100., desc='Freq curve point')

# Define points for HFRT must remain connected curves
info.param('frt.ride_through', label='Does the test have ride-through curves?', default='Yes',
           values=['Yes', 'No'])
info.param('frt.hc_curve_num', label='HFRT must remain connected curve number',
           active='frt.ride_through', active_value=['Yes'], default=1, values=[1,2,3,4])
info.param('frt.hc_n_points', label='Number of (t, F) pairs (2-10)',
           active='frt.ride_through', active_value=['Yes'], default=4, values=[2,3,4,5,6,7,8,9,10])
info.param_group('frt.hc_curve', label='HFRT Curve Must Remain Connected Points',
                 active='frt.ride_through', active_value=['Yes'],
                 index_count='frt.hc_n_points', index_start=1,
                 desc='Curve is assumed to be vertical from 1st point and horizontal from last point.')
info.param('frt.hc_curve.hc_time', label='Time (sec)',
           active='frt.ride_through', active_value=['Yes'], default=0., desc='Time curve point')
info.param('frt.hc_curve.hc_freq', label='Freq (%Fnom)',
           active='frt.ride_through', active_value=['Yes'], default=100., desc='Freq curve point')

# Define points for LFRT must remain connected curves
info.param('frt.lc_curve_num', label='LFRT must remain connected curve number)',
           active='frt.ride_through', active_value=['Yes'], default=1, values=[1,2,3,4])
info.param('frt.lc_n_points', label='Number of (t, F) pairs (2-10)',
           active='frt.ride_through', active_value=['Yes'], default=4, values=[2,3,4,5,6,7,8,9,10])
info.param_group('frt.lc_curve', label='LFRT Curve Must Remain Connected Points',
                 active='frt.ride_through', active_value=['Yes'],
                 index_count='frt.lc_n_points', index_start=1,
                 desc='Curve is assumed to be vertical from 1st point and horizontal from last point.')
info.param('frt.lc_curve.lc_time', label='Time (sec)',
           active='frt.ride_through', active_value=['Yes'], default=0., desc='Time curve point')
info.param('frt.lc_curve.lc_freq', label='Freq (%Fnom)',
           active='frt.ride_through', active_value=['Yes'], default=100., desc='Freq curve point')

# SPF parameters
info.param('functions.spf', label='Include specified power factor?', default='Yes', values=['Yes', 'No'])
info.param_group('spf', label='PF Settings', active='functions.spf', active_value=['Yes'])
info.param('spf.pf', label='Power Factor', default=.850)

# Volt-var parameters
info.param('functions.vv', label='Include volt-var?', default='Yes', values=['Yes', 'No'])
info.param_group('vv', label='VV Settings', active='functions.vv', active_value=['Yes'])
info.param('vv.vv_mode', label='Volt-Var Mode', default='VV12 (var priority)',
           values=['VV11 (watt priority)', 'VV12 (var priority)'])
           #values=['VV11 (watt priority)', 'VV12 (var priority)', 'VV13 (fixed var)', 'VV14 (no volt-var)'])
info.param('vv.var_ramp_rate', label='Maximum Ramp Rate (VAr/s)', default=1600,
           desc='Maximum Ramp Rate (VAr/s)')
info.param('vv.MSA_VAr', label='Reactive Power Accuracy (VAr)', default=20,
           desc='Reactive Power Accuracy (VAr)')
info.param('vv.v_low', label='Min dc voltage range with function enabled (V)', default=200,
           desc='Min dc voltage range with function enabled (V)')
info.param('vv.v_high', label='Max dc voltage range with function enabled (V)', default=600,
           desc='Max dc voltage range with function enabled (V)')
info.param('vv.k_varmax', label='Maximum Volt-Var curve slope (VAr/V)', default=800,
           desc='Maximum Volt-Var curve slope (VAr/V)')
info.param('vv.v_deadband_min', label='Min deadband range (V)', default=2,
           desc='Min deadband voltage (V)')
info.param('vv.v_deadband_max', label='Max deadband range (V)', default=10,
           desc='Max deadband voltage (V)')

# Define points for VV11 and VV12
info.param('vv.curve_num', label='Curve number (1-4)', default=1, values=[1,2,3,4])
info.param('vv.n_points', label='Number of (Volt, VAr) pairs (2-10)', default=4, values=[2,3,4,5,6,7,8,9,10],
           active='vv.vv_mode',  active_value=['VV11 (watt priority)', 'VV12 (var priority)'])
info.param('vv.manualcurve', label='Enter the Volt-Var Curves Manually?', default='Manual',
           values=['Manual', 'Enter Test Number'])
info.param('vv.test_num', label='Enter the UL 1741 test number', default=1, values=[1,2,3,4,5],
           active='vv.manualcurve', active_value=['Enter Test Number'],
           desc='Automatically calculates the volt-var curve points based on the UL 1741 SA procedure.')

info.param_group('vv.curve', label='VV Curve Points', index_count='vv.n_points', index_start=1,
                 active='vv.manualcurve', active_value=['Manual'])
info.param('vv.curve.volt', label='Volt', default=100.,
           desc='Volt curve point')
info.param('vv.curve.var', label='VAr', default=0.,
           desc='VAr curve point')

# Ramp Rate Parameters
info.param('functions.rr', label='Include ramp rate?', default='Yes', values=['Yes', 'No'])
info.param_group('rr', label='RR Settings', active='functions.rr', active_value=['Yes'])
info.param('rr.normal_rr', label='Ramp Rate (%i_rated/sec)', default=5,
           desc='Worst case ramp rate for unintentional islanding (%i_rated/sec)')

# Freq-watt parameters
info.param('functions.fw', label='Include freq-watt?', default='Yes', values=['Yes', 'No'])
info.param_group('fw', label='FW Configuration', active='functions.fw', active_value=['Yes'])
info.param('fw.fw_mode', label='Freq-Watt Mode', default='FW21 (FW parameters)',
           values=['FW21 (FW parameters)', 'FW22 (pointwise FW)'],
           desc='Parameterized FW curve or pointwise linear FW curve?')
info.param('fw.freq_ref', label='Nominal Grid Frequency (Hz)', default=60.)

# Define points for FW21
info.param('fw.WGra', label='Ramp Rate (%nameplate power/Hz)', default=65.,
           active='fw.fw_mode',  active_value='FW21 (FW parameters)',
           desc='slope of the reduction in the maximum allowed watts output as a function '
                'of frequency (units of % max power/ Hz)')
info.param('fw.HzStr', label='FW Start Freq Above Nominal (delta Hz)', default=0.2,
           active='fw.fw_mode',  active_value='FW21 (FW parameters)',
           desc='Frequency deviation from fnom at which power reduction occurs.')
info.param('fw.HysEna', label='Hysteresis Enabled', default='Yes', values=['Yes', 'No'],
           active='fw.fw_mode',  active_value='FW21 (FW parameters)')
info.param('fw.HzStop', label='FW Stop Freq Above Nominal (delta Hz)', default=0.1,
           active='fw.HysEna',  active_value='Yes',
           desc='frequency deviation from nominal frequency (ECPNomHz) at which curtailed power output '
                'returns to normal and the cap on the power level value is removed.')
info.param('fw.HzStopWGra', label='Recovery Ramp Rate (%nameplate power/min)', default=10000.,
           active='fw.fw_mode',  active_value='FW21 (FW parameters)',
           desc='Maximum time-based rate of change at which power output returns to normal '
                'after having been capped by an over frequency event)')

# Define points for FW22
info.param('fw.curve_num', label='Curve number (1-4)', default=1, values=[1,2,3,4],
           active='fw.fw_mode',  active_value='FW22 (pointwise FW)')
info.param('fw.n_points', label='Number of (Freq, Power) pairs (2-10)', default=3, values=[2,3,4,5,6,7,8,9,10],
           active='fw.fw_mode',  active_value='FW22 (pointwise FW)')
info.param_group('fw.curve', label='FW Curve Points', index_count='fw.n_points', index_start=1,
                 active='fw.fw_mode',  active_value='FW22 (pointwise FW)')
info.param('fw.curve.freq', label='%Hz', default=100., desc='Freq curve point')
info.param('fw.curve.W', label='%Wmax', default=100., desc='Power curve point')

# Volt-watt parameters
info.param('functions.vw', label='Include volt-watt?', default='No', values=['Yes', 'No'])
info.param_group('vw', label='VW Configuration', active='functions.vw', active_value=['Yes'])
info.param('vw.volt_ref', label='Nominal Grid Voltage (V)', default=240.)
info.param('vw.vw_points', label='Number of (Volt, Power) pairs (2-10)', default=3, values=[2,3,4,5,6,7,8,9,10])
info.param_group('vw.curve', label='VW Curve Points', index_count='vw.n_points', index_start=1)
info.param('vw.curve.volt', label='%V', default=100., desc='Volt curve point')
info.param('vw.curve.W', label='%Wmax', default=100., desc='Power curve point')
info.param('vw.curve.vw_deptref', label='DeptRef', default=1, desc='1 = W_MAX_PCT, 2 = W_AVAL_PCT')

# Define the matrix of functions to be tested
info.param('functions.n_sets', label='Number of tests in the test matrix.', default=3)
info.param_group('functions.sets', label='Function Sets', index_count='functions.n_sets', index_start=1)
info.param('functions.sets.set', label='Functions in Test', default='VRT, FRT, SPF, VV, RR, FW, VW',
           desc='Choose from {VRT, FRT, SPF, VV, RR, FW, VW}')

der.params(info)
gridsim.params(info)
pvsim.params(info)
das.params(info)
hil.params(info)
loadsim.params(info)
switch.params(info, id='switch_load', label='Load Switch')
switch.params(info, id='switch_utility', label='Utility Switch')
switch.params(info, id='switch_eut', label='EUT Switch')

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


