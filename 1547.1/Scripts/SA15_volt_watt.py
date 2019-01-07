"""
Copyright (c) 2018, Sandia National Labs, SunSpec Alliance and CanmetENERGY
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
from svpelab import hil
from svpelab import gridsim
from svpelab import pvsim
from svpelab import das
from svpelab import der
import numpy as np
import time
import script
import result as rslt

def p_target(v, v_nom, v_slope_start, v_slope_stop):
    """
    Calculate the target power from the VW curve parameters
    :param v: voltage point
    :param v_nom: nominal EUT voltage
    :param v_slope_start: VW V1
    :param v_slope_stop: VW V2
    :return: Expected VW power
    """
    v_pct = 100.*(v/v_nom)
    v_slope_start_pct = 100.*(v_slope_start/v_nom)
    v_slope_stop_pct = 100.*(v_slope_stop/v_nom)
    if v_pct < v_slope_start_pct:
        p_targ = 100.
    elif v_pct > v_slope_stop_pct:
        p_targ = 0.
    else:
        p_targ = 100. - 100.*((v_pct-v_slope_start_pct)/(v_pct-v_slope_stop_pct))
    return p_targ


def p_msa_range(v_value, v_msa, p_msa, v_nom, v_slope_start, v_slope_stop):
    """
    Determine  power target and the min/max p values for pass/fail acceptance based on manufacturer's specified
    accuracies (MSAs).  This assumes that Q1 = 100% and Q2 = 0% Prated

    :param v_value: measured voltage value
    :param v_msa: manufacturer's specified accuracy of voltage
    :param p_msa: manufacturer's specified accuracy of  power
    :param v_nom: EUT nominal voltage
    :param v_slope_start: VW V1
    :param v_slope_stop: VW V2
    :return: points for q_target, q_target_min, q_target_max
    """
    p_targ = p_target(v_value, v_nom, v_slope_start, v_slope_stop)    # target power for the voltage measurement
    p1 = p_target(v_value - v_msa, v_nom, v_slope_start, v_slope_stop)  # power target from the lower voltage limit
    p2 = p_target(v_value + v_msa, v_nom, v_slope_start, v_slope_stop)  # power target from the upper voltage limit
    if p1 >= p_target:
        # if the VW curve has a negative slope
        # add the power MSA to the high side (left point, p1)
        # subtract the power MSA from the low side (right point, p2)
        #
        #                          \ * (v_value - v_msa, p_upper)
        #                           \
        #                            . (v_value - v_msa, p1)
        #                             \
        #                              x (v_value, p_target)
        #                               \
        #                                . (v_value + v_msa, p2)
        #                                 \
        #     (v_value + v_msa, p_lower) * \

        p_upper = round(p1 + p_msa, 1)
        p_lower = round(p2 - p_msa, 1)
        return p_targ, p_lower, p_upper
    else:
        p_lower = round(p1 - p_msa, 1)
        p_upper = round(p2 + p_msa, 1)
        return p_targ, p_lower, p_upper


def power_total(data, phases):
    """
    Sum the EUT power from all phases
    :param data: dataset
    :param phases: number of phases in the EUT
    :return: total EUT power
    """
    if phases == 'Single phase':
        ts.log_debug('Powers are: %s' % (data.get('AC_P_1')))
        power = data.get('AC_P_1')

    elif phases == 'Split phase':
        ts.log_debug('Powers are: %s, %s' % (data.get('AC_P_1'),
                                             data.get('AC_P_2')))
        power = data.get('AC_P_1') + data.get('AC_P_2')

    elif phases == 'Three phase':
        ts.log_debug('Powers are: %s, %s, %s' % (data.get('AC_P_1'),
                                                 data.get('AC_P_2'),
                                                 data.get('AC_P_3')))
        power = data.get('AC_P_1') + data.get('AC_P_2') + data.get('AC_P_3')
    else:
        ts.log_error('Inverter phase parameter not set correctly.')
        raise

    return power


def test_run():

    result = script.RESULT_FAIL
    daq = None
    grid = None
    pv = None
    eut = None
    chil = None
    p_max = None
    v_nom_grid = None
    result_summary = None

    result_params = {
        'plot.title': 'title_name',
        'plot.x.title': 'Time (secs)',
        'plot.x.points': 'TIME',
        'plot.y.points': 'AC_VRMS_1, AC_P_1, P_target_pct',
        'plot.AC_VRMS_1.point': 'True',
        'plot.P_target_pct.point': 'True',
        'plot.P_target_pct.min_error': 'P_min_pct',
        'plot.P_target_pct.max_error': 'P_max_pct',
        'plot.P_MIN.point': 'True',
        'plot.P_MAX.point': 'True',
    }

    try:
        """
        Configuration
        """
        # Initiliaze VW EUT specified parameters variables
        vw_mode = ts.param_value('vw.vw_mode')
        phases = ts.param_value('vw.phases')
        v_nom = ts.param_value('vw.v_nom')
        v_min = ts.param_value('vw.v_min')
        v_max = ts.param_value('vw.v_max')
        MSA_V = ts.param_value('vw.MSA_V')
        MSA_P = ts.param_value('vw.MSA_P')
        t_settling = ts.param_value('vw.ts')
        v_start_max = ts.param_value('vw.vstart_max')
        v_start_min = ts.param_value('vw.vstart_min')

        # the k_power_slopes are the slope in %Prated/V
        k_p_slope_max = ts.param_value('vw.k_p_v_max')
        k_p_slope_min = ts.param_value('vw.k_p_v_min')

        hysteresis = ts.param_value('vw.hysteresis')
        MSA_t = ts.param_value('vw.MSA_t')
        v_stop_max = ts.param_value('vw.vstop_max')
        v_stop_min = ts.param_value('vw.vstop_min')

        # t_return is the delay before releasing the hysteresis power level and increasing power at k_power_rate
        t_return_max = ts.param_value('vw.treturn_max')
        t_return_min = ts.param_value('vw.treturn_min')

        # the k_power_rates are the hysteresis response in %P_rated/sec
        k_p_rate_max = ts.param_value('vw.k_p_rate_max')
        k_p_rate_min = ts.param_value('vw.k_p_rate_min')

        # Initiliaze VW test parameters variables
        curves = ts.param_value('test.curves')
        pwr_lvl = ts.param_value('test.power_lvl')
        n_iter = ts.param_value('test.n_iter')
        n_points = ts.param_value('test.n_points')

        # initialize hardware-in-the-loop environment (if applicable)
        ts.log('Configuring HIL system...')
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # initialize grid simulator
        grid = gridsim.gridsim_init(ts)

        # initialize pv simulator
        pv = pvsim.pvsim_init(ts)
        p_rated = ts.param_value('vw.p_rated')
        pv.power_set(p_rated)
        pv.power_on()  # power on at p_rated

        # Configure the EUT communications
        eut = der.der_init(ts)
        eut.config()
        # ts.log_debug(eut.measurements())
        ts.log_debug('If not done already, set L/HVRT and trip parameters to the widest range of adjustability.')

        # DAS soft channels
        das_points = {'sc': ('P_target_pct', 'P_min_pct', 'P_max_pct', 'volt_set', 'event')}

        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])
        daq.sc['P_target_pct'] = 100
        daq.sc['P_min_pct'] = 0
        daq.sc['P_max_pct'] = 100
        daq.sc['event'] = 'None'

        """
        Test Configuration
        """
        if curves == 'Both':
            vw_curves = [1, 2]
        elif curves == 'Characteristic Curve 1':
            vw_curves = [1]
        else:  # Characteristic Curve 2
            vw_curves = [2]

        if pwr_lvl == 'All':
            pwr_lvls = [1., 0.33]
        elif pwr_lvl == '100%':
            pwr_lvls = [1.]
        else:  # Power at 33%
            pwr_lvls = [0.33]

        if hysteresis == 'Enabled':
            hyst = [True]
        elif hysteresis == 'Disabled':
            hyst = [False]
        else:
            hyst = [True, False]

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write('Result, Test Name, Power Level, Iteration, Ramp, Volt, Power, P_min, P_max, '
                             'Dataset File\n')

        """
        Test start
        """
        ts.log_debug('Initial EUT VW settings are %s' % eut.volt_watt())
        for vw_curve in vw_curves:
            if vw_curve == 1:  # characteristic curve 1
                v_start = v_start_min
                k_power_volt = k_p_slope_max
                v_max_curve = v_start + 100./k_power_volt
                vw_curve_params = {'v': [v_start, v_max_curve], 'w': [100., 0], 'DeptRef': 'W_MAX_PCT'}
                vw_params = {'Ena': True, 'ActCrv': 1, 'curve': vw_curve_params}
                eut.volt_watt(params=vw_params)
            else:  # characteristic curve 2
                v_start = v_start_max
                k_power_volt = k_p_slope_max
                v_max_curve = v_start + 100./k_power_volt
                vw_curve_params = {'v': [v_start, v_max_curve], 'w': [100., 0], 'DeptRef': 'W_MAX_PCT'}
                vw_params = {'Ena': True, 'ActCrv': 1, 'curve': vw_curve_params}
                eut.volt_watt(params=vw_params)

            # Update hysteresis parameters
            for hys in hyst:
                v_stop = v_start  # when there is no hysteresis, this will define the test points
                if hys and vw_curve == 1:
                    k_power_rate = k_p_rate_max
                    v_stop = v_stop_min
                    t_return = t_return_max
                    # todo: hysteresis - der.py and der_sunspec.py and pysunspec must be updated
                    # vw_hyst_params = {'v_stop': v_stop, 'k_power_rate': k_power_rate, 't_return': t_return}
                    # eut.volt_watt(params=vw_hyst_params)
                if hys and vw_curve == 2:
                    k_power_rate = k_p_rate_max
                    v_stop = v_stop_min
                    t_return = t_return_max
                    # todo: hysteresis - der.py and der_sunspec.py and pysunspec must be updated
                    # vw_hyst_params = {'v_stop': v_stop, 'k_power_rate': k_power_rate, 't_return': t_return}
                    # eut.volt_watt(params=vw_hyst_params)

                # Verify EUT has parameters updated.
                ts.log_debug('EUT VW settings for this test are %s' % eut.volt_watt())

                for power in pwr_lvls:
                    pv.power_set(p_rated*power)
                    for n_iter in range(n_iter):
                        '''
                        There shall be a minimum number of 3 points tested above Vstart while increasing
                        voltage, and minimum number of 3 points tested above Vstop while decreasing voltage.
                        The voltage between points should be large enough to resolve the accuracy of Volt-
                        Watt function. The test points will be developed using these guidelines.
                        '''
                        # Include n_points on each of the 3 line segments for going up
                        if v_max_curve < v_max:
                            v_points_up = list(np.linspace(v_min+MSA_V, v_start, n_points)) + \
                                       list(np.linspace(v_start+MSA_V, v_max_curve-MSA_V, n_points)) + \
                                       list(np.linspace(v_max_curve+MSA_V, v_max-MSA_V, n_points))
                        else:  # slope extends past EUT trip point - skip final line segment
                            v_points_up = list(np.linspace(v_min+MSA_V, v_start, n_points)) + \
                                       list(np.linspace(v_start+MSA_V, v_max-MSA_V, n_points))

                        # Include n_points on each of the 2 line segments for going down
                        v_points_down = list(np.linspace(v_max-MSA_V, v_stop+MSA_V, n_points)) + \
                                       list(np.linspace(v_stop-1.5*MSA_V, v_min+MSA_V, n_points))

                        ts.log('Testing VW function at the following voltage up points %s' % v_points_up)
                        ts.log('Testing VW function at the following voltage down points %s' % v_points_down)

                        '''
                        The Volt-Watt test consists of a series of fast ramps from one voltage level to the
                        next. Figure SA15.3 shows a portion of a volt-watt test voltage profile including two
                        such ramps. Following each ramp the voltage is held at the desired test voltage for at
                        least twice the manufacturer's Volt-Watt settling time, ts. IEEE 1547.1a-2015, Annex
                        A.5, can be used for reference.
                        '''
                        for v_step in v_points_up:
                            daq.sc['volt_set'] = v_step
                            ts.log('        Recording power at voltage %0.3f V for 2*t_settling = %0.1f sec.' %
                                   (v_step, 2 * t_settling))

                            p_targ, p_min_to_pass, p_max_to_pass = p_msa_range(v_value=v_step, v_msa=MSA_V, p_msa=MSA_P,
                                                                               v_nom=v_nom, v_slope_start=v_start,
                                                                               v_slope_stop=v_max_curve)
                            daq.sc['P_target_pct'] = p_targ
                            daq.sc['P_min_pct'] = p_min_to_pass
                            daq.sc['P_max_pct'] = p_max_to_pass

                            test_str = 'VW_curve_%s_power=%0.2f_iter=%s' % (vw_curve, power, n_iter+1)
                            filename = test_str + '.csv'
                            daq.data_capture(True)
                            daq.sc['event'] = 'V_Step_Up'
                            grid.voltage(v_step)
                            ts.sleep(2 * t_settling)
                            daq.data_capture()
                            data = daq.data_capture_read()
                            AC_W = power_total(data, phases)
                            AC_W_pct = (AC_W / p_rated) * 100.

                            if p_min_to_pass <= AC_W_pct <= p_max_to_pass:
                                passfail = 'Pass'
                            else:
                                passfail = 'Fail'

                            result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                                 (passfail, ts.config_name(), power * 100., n_iter + 1,
                                                  'Up', v_step, AC_W_pct, daq.sc['P_min_pct'],
                                                  daq.sc['P_max_pct'], filename))

                        for v_step in v_points_down:
                            '''
                            For falling voltage, the EUT shall be considered in compliance if each of the following are
                            true

                            a) For all voltages V > Vstop + MSAV, and for each line cycle after the manufacturer's
                            stated settling time ts has passed following a voltage change, the measured active power
                            falls to alevel within a MSAP(V) of zero; and

                            b) At some voltage V, where Vstop - MSAV < V < Vstop + MSAV, the measured active power
                            begins rising after a delay of treturn, within MSAt. The rate of power increase must be
                            KPower_Rate, with allowances for MSAP(V) and MSAt as shown in Figure SA15.5. The power must
                            return to the nominal power level for the test within MSAP(V). KPower_Rate shall be
                            evaluated in accordance with the test criteria for RR in Section SA11.
                            '''

                            # The above seems to imply that t_return is active with and without hysteresis.
                            # Here we assume this is only enabled with hysteresis. Once reaching V_stop, the timer
                            # begins. After timing out, the EUT should ramp at K_power_rate back to rated power assuming
                            # V_stop < V_start

                            daq.sc['volt_set'] = v_step
                            ts.log('        Recording power at voltage %0.3f V for 2*t_settling = %0.1f sec.' %
                                   (v_step, 2 * t_settling))
                            daq.sc['event'] = 'V_Step_Down'
                            test_str = 'VW_curve_%s_power=%0.2f_iter=%s' % (vw_curve, power, n_iter+1)
                            filename = test_str + '.csv'
                            if v_step > v_stop-1.5*MSA_V and hys:
                                p_targ = 0.
                                p_min_to_pass = -MSA_P
                                p_max_to_pass = MSA_P
                                daq.sc['P_target_pct'] = p_targ
                                daq.sc['P_min_pct'] = p_min_to_pass
                                daq.sc['P_max_pct'] = p_max_to_pass
                                daq.data_capture(True)
                                grid.voltage(v_step)
                                # If the t_return functionality is initiated when Vstop - MSAV < V < Vstop + MSAV
                                # if v_step < v_stop-0.5*MSA_V:
                                #     t_return_start_time = time.time()
                                #     daq.sc['event'] = 't_return_Started'
                                ts.sleep(2 * t_settling)
                                daq.data_capture()
                                data = daq.data_capture_read()
                                AC_W_pct = (power_total(data, phases) / p_rated) * 100.
                                passfail = 'Pass' if p_min_to_pass <= AC_W_pct <= p_max_to_pass else 'Fail'

                            elif v_step == v_stop-1.5*MSA_V and hys:
                                p_targ = 100.  # it's ramping from 0 to 100
                                p_min_to_pass = -MSA_P
                                p_max_to_pass = MSA_P
                                daq.sc['P_target_pct'] = p_targ
                                daq.sc['P_min_pct'] = p_min_to_pass
                                daq.sc['P_max_pct'] = p_max_to_pass
                                daq.data_capture(True)
                                grid.voltage(v_step)
                                # Hysteresis Pass/Fail analysis
                                hys_start_time = time.time()
                                passfail = 'Pass'
                                while (time.time() - hys_start_time) < (2*t_settling + t_return + 100./k_power_rate):
                                    hys_clock = (time.time() - hys_start_time)
                                    daq.data_capture()
                                    data = daq.data_capture_read()
                                    AC_W_pct = (power_total(data, phases) / p_rated) * 100.
                                    remaining_time = 2*t_settling + t_return + 100./k_power_rate - hys_clock
                                    ts.log('Evaluating hysteresis return. Time=%0.3f, P=%0.2f. t_return=%s s, '
                                           'rate=%0.2f. Additional analysis time = %0.2f' %
                                           (hys_clock, AC_W_pct, t_return, k_power_rate, remaining_time))

                                    # check to see that t_return is used correctly: fail if power increasing early
                                    if hys_clock < t_return + MSA_t and AC_W_pct > MSA_P:
                                        passfail = 'Fail'

                                    # check to see that the k_power_rate ramp is followed with appropriate MSA values
                                    if (t_return + MSA_t) < hys_clock < (t_return + MSA_t + 100./k_power_rate):
                                        # Verify the EUT is not under-performing or over-performing
                                        if (k_power_rate*(hys_clock-MSA_t) - MSA_P) < AC_W_pct or \
                                                        AC_W_pct < (k_power_rate*(hys_clock+MSA_t) + MSA_P):
                                            passfail = 'Fail'

                                # Do final power check after settling time
                                daq.data_capture()
                                data = daq.data_capture_read()
                                AC_W_pct = (power_total(data, phases) / p_rated) * 100.
                                if AC_W_pct < p_min_to_pass or AC_W_pct > p_max_to_pass:
                                    passfail = 'Fail'

                            else:  # in all cases without hysteresis and when v_step < v_stop-1.5*MSA_V
                                p_targ, p_min_to_pass, p_max_to_pass = p_msa_range(v_value=v_step, v_msa=MSA_V,
                                                                                   p_msa=MSA_P,
                                                                                   v_nom=v_nom, v_slope_start=v_start,
                                                                                   v_slope_stop=v_max_curve)
                                daq.sc['P_target_pct'] = p_targ
                                daq.sc['P_min_pct'] = p_min_to_pass
                                daq.sc['P_max_pct'] = p_max_to_pass
                                daq.data_capture(True)
                                grid.voltage(v_step)
                                ts.sleep(2 * t_settling)
                                daq.data_capture()
                                data = daq.data_capture_read()
                                AC_W_pct = (power_total(data, phases) / p_rated) * 100.
                                passfail = 'Pass' if p_min_to_pass <= AC_W_pct <= p_max_to_pass else 'Fail'

                            result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                                 (passfail, ts.config_name(), power * 100., n_iter + 1,
                                                  'Up', v_step, AC_W_pct, daq.sc['P_min_pct'],
                                                  daq.sc['P_max_pct'], filename))

                            daq.data_capture(False)
                            ds = daq.data_capture_dataset()
                            ts.log('Saving file: %s' % filename)
                            ds.to_csv(ts.result_file_path(filename))
                            result_params['plot.title'] = test_str
                            ts.result_file(filename, params=result_params)

        result = script.RESULT_COMPLETE

    except script.ScriptFail, e:
        reason = str(e)
        if reason:
            ts.log_error(reason)
    finally:
        if daq is not None:
            daq.close()
        if pv is not None:
            if p_max is not None:
                pv.power_set(p_max)
            pv.close()
        if grid is not None:
            if v_nom_grid is not None:
                grid.voltage(v_nom_grid)
            grid.close()
        if chil is not None:
            chil.close()
        if eut is not None:
            eut.close()
        if result_summary is not None:
            result_summary.close()

        # create result workbook
        xlsxfile = ts.config_name() + '.xlsx'
        rslt.result_workbook(xlsxfile, ts.results_dir(), ts.result_dir())
        ts.result_file(xlsxfile)

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

# EUT VW parameters
info.param_group('vw', label='VW EUT specified parameters')
info.param('vw.phases', label='Phases', default='Single Phase', values=['Single phase', 'Split phase', 'Three phase'])
info.param('vw.p_rated', label='Output Power Rating (W)', default=10000.)
info.param('vw.v_min', label='Min AC voltage range with function enabled (V)', default=108.)
info.param('vw.v_max', label='Max AC voltage range with function enabled (V)', default=132.)
info.param('vw.v_nom', label='Nominal AC voltage (V)', default=120.)
info.param('vw.MSA_V', label='Manufacturer\'s stated AC voltage accuracy (V)', default=0.1)
info.param('vw.MSA_P', label='Manufacturer\'s stated power accuracy (W)', default=10.)
info.param('vw.ts', label='Settling time (s)', default=1.)
info.param('vw.vstart_max', label='Max start of power reduction, v_start (V)', default=135.6)
info.param('vw.vstart_min', label='Min start of power reduction, v_start (V)', default=123.6)
info.param('vw.k_p_v_max', label='Maximum slope of active power reduction (%Prated/V)', default=100.)
info.param('vw.k_p_v_min', label='Minimum slope of active power reduction (%Prated/V)', default=10.)
info.param('vw.hysteresis', label='Hysteresis in the Volt-Watt function', default='Disabled',
           values=['Enabled', 'Disabled'])  # Not including a 'Both' option because UL 1741 SA is either/or
info.param('vw.MSA_t', label='Manufacturer\'s stated time accuracy (s)', default=0.01, active='vw.hysteresis',
           active_value=['Enabled', 'Both'])
info.param('vw.vstop_max', label='Max stop of voltage curtailment (V)', default=135.6, active='vw.hysteresis',
           active_value=['Enabled', 'Both'])
info.param('vw.vstop_min', label='Min stop of voltage curtailment (V)', default=123.6, active='vw.hysteresis',
           active_value=['Enabled', 'Both'])
info.param('vw.treturn_max', label='Maximum adjustment of a delay before return to normal operation (s)', default=0.1,
           active='vw.hysteresis', active_value=['Enabled', 'Both'])
info.param('vw.treturn_min', label='Minimum adjustment of a delay before return to normal operation (s)', default=0.1,
           active='vw.hysteresis', active_value=['Enabled', 'Both'])
info.param('vw.k_p_rate_max', label='Max active power rate to return to normal operation (%Prated/Sec)', default=0.1,
           active='vw.hysteresis', active_value=['Enabled', 'Both'])
info.param('vw.k_p_rate_min', label='Min active power rate to return to normal operation (%Prated/Sec)', default=0.1,
           active='vw.hysteresis', active_value=['Enabled', 'Both'])
# VW test parameters
info.param_group('test', label='Test Parameters')
info.param('test.curves', label='Curves to Evaluate', default='Both', values=['Characteristic Curve 1',
                                                                              'Characteristic Curve 2', 'Both'])
info.param('test.power_lvl', label='Power Levels', default='All', values=['100%', '33%', 'All'])
info.param('test.n_iter', label='Number of iteration for each test', default=3)
info.param('test.n_points', label='Number of points tested above v_start', default=3)

# Other equipment parameters
der.params(info)
gridsim.params(info)
pvsim.params(info)
das.params(info)
hil.params(info)

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
