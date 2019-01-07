
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
import script
import math
import result as rslt
import numpy as np

test_labels = {
    1: 'Test 1 - Most Aggressive',
    2: 'Test 2 - Average',
    3: 'Test 3 - Least Aggressive',
    4: 'Test 4 - Specified Curve',
    'Test 1 - Most Aggressive': [1],
    'Test 2 - Average': [2],
    'Test 3 - Least Aggressive': [3],
    'Test 4 - Specified Curve': [4],
}

def segment_points(start, end, count):
    ts.log('points - %s %s' % (str(start), str(end)))
    interval = (end - start)/(count + 1)
    points = [start]
    last = start
    for i in range(count):
        last = last + interval
        points.append(last)
    points.append(end)
    return points

def sample_points(p, segment_count=3):
    points = segment_points(p[0], p[1], segment_count)[1:]
    points.extend(segment_points(p[1], p[2], segment_count)[1:])
    points.extend(segment_points(p[2], p[3], segment_count)[1:])
    points.extend(segment_points(p[3], p[4], segment_count)[1:])
    points.extend(segment_points(p[4], p[5], segment_count)[1:-1])
    return points

def v_q(value, v, q):
    """
    Interpolation function to find the target reactive power based on a 4 point VV curve

    TODO: make generic for n-point curves

    :param value: voltage point for the interpolation
    :param v: VV voltage points
    :param q: VV reactive power points
    :return: target reactive power
    """
    if value <= v[1]:
        q_value = q[1]
    elif value < v[2]:
        q_value = q[1] - ((q[1] - q[2])/(v[2] - v[1]) * (value - v[1]))
    elif value == v[2]:
        q_value = q[2]
    elif value < v[3]:
        q_value = q[2] - ((q[2] - q[3])/(v[3] - v[2]) * (value - v[2]))
    elif value == v[3]:
        q_value = q[3]
    elif value < v[4]:
        q_value = q[3] - ((q[3] - q[4])/(v[4] - v[3]) * (value - v[3]))
    else:
        q_value = q[4]
    return round(q_value, 1)


def q_msa_range(v_value, v_msa, q_msa, v, q):
    """
    Determine reactive power target and the min/max q values for pass/fail acceptance based on manufacturer's specified
    accuracies (MSAs)

    :param v_value: measured voltage value
    :param v_msa: manufacturer's specified accuracy of voltage
    :param q_msa: manufacturer's specified accuracy of reactive power
    :param v: VV voltage points
    :param q: VV reactive power points
    :return: points for q_target, q_target_min, q_target_max
    """

    q_target = v_q(v_value, v, q)    # target reactive power for the voltage measurement
    q1 = v_q(v_value - v_msa, v, q)  # reactive power target from the lower voltage limit
    q2 = v_q(v_value + v_msa, v, q)  # reactive power target from the upper voltage limit
    if q1 >= q_target:
        # if the VV curve has a negative slope (as is generally the case)
        # add the reactive power MSA to the high side (left point, q1)
        # subtract the reactive power MSA from the low side (right point, q2)
        #
        #                          \ * (v_value - v_msa, q_upper)
        #                           \
        #                            . (v_value - v_msa, q1)
        #                             \
        #                              x (v_value, q_target)
        #                               \
        #                                . (v_value + v_msa, q2)
        #                                 \
        #     (v_value + v_msa, q_lower) * \

        q_upper = round(q1 + q_msa, 1)
        q_lower = round(q2 - q_msa, 1)
        return q_target, q_lower, q_upper
    else:
        q_lower = round(q1 - q_msa, 1)
        q_upper = round(q2 + q_msa, 1)
        return q_target, q_lower, q_upper


def test_pass_fail(var_act, var_min, var_max, var_aval=None, q_msa=None, priority='Reactive'):
    """
    Apply pass/fail criterion for each phase

    :param var_act: reactive power being produced by EUT based on VV function
    :param var_min: VV reactive power lower limit
    :param var_max: VV reactive power upper limit
    :param var_aval: VV reactive power available to the EUT
    :param priority: 'Reactive' or 'Active' power priority for the VV function
    :return: 'Pass' or 'Fail' based on the results
    """

    passfail = 'Fail'

    if priority == 'Reactive':
        if var_min <= var_act <= var_max:
            passfail = 'Pass'
    else:  # priority is 'Active Power'
        if var_aval <= var_max:
            # if the available vars does not apply
            if var_min <= var_act <= var_max:
                passfail = 'Pass'
        else:
            # if the available vars does apply
            if (var_aval - q_msa) <= var_act <= (var_aval + q_msa):
                passfail = 'Pass'

    return passfail


def test_run():

    result = script.RESULT_PASS
    daq = None
    pv = None
    grid = None
    chil = None
    result_summary = None
    p_max = None
    v_nom_grid = None

    result_params = {
        'plot.title': 'title_name',
        'plot.x.title': 'Time (secs)',
        'plot.x.points': 'TIME',
        'plot.y.points': 'AC_P_1, AC_Q_1, Q_ACT, Q_TARGET',
        'plot.Q_ACT.point': 'True',
        'plot.Q_TARGET.point': 'True',
        'plot.Q_TARGET.min_error': 'Q_MIN_ERROR',
        'plot.Q_TARGET.max_error': 'Q_MAX_ERROR',
        'plot.Q_MIN.point': 'True',
        'plot.Q_MAX.point': 'True',
        'plot.V_ACT.point': 'True',
        'plot.V_TARGET.point': 'True',
        'plot.y.title': 'Reactive Power (var)',
        'plot.y2.points': 'AC_VRMS_1, V_ACT, V_TARGET',
        'plot.y2.title': 'Voltage (V)'
    }

    try:
        # read test parameters
        tests_param = ts.param_value('eut_vv.tests')

        s_rated = ts.param_value('eut_vv.s_rated')
        p_rated = ts.param_value('eut_vv.p_rated')
        var_rated = ts.param_value('eut_vv.var_rated')
        # v_dc_min = ts.param_value('eut_vv.v_dc_min')  ##
        # v_dc_max = ts.param_value('eut_vv.v_dc_max')  ##
        v_nom = ts.param_value('eut_vv.v_nom')
        v_min = ts.param_value('eut_vv.v_min')
        v_max = ts.param_value('eut_vv.v_max')
        v_msa = ts.param_value('eut_vv.v_msa')
        var_msa = ts.param_value('eut_vv.var_msa')
        var_ramp_max = ts.param_value('eut_vv.var_ramp_max')
        q_max_over = ts.param_value('eut_vv.q_max_over')
        q_max_under = ts.param_value('eut_vv.q_max_under')
        k_var_max = ts.param_value('eut_vv.k_var_max')
        deadband_min = ts.param_value('eut_vv.vv_deadband_min')
        deadband_max = ts.param_value('eut_vv.vv_deadband_max')
        t_settling = ts.param_value('eut_vv.vv_t_settling')
        phases = ts.param_value('eut_vv.phases')

        if phases == 'Single Phase':
            sc_points = ['V_ACT_1', 'Q_ACT_1',  # 'V_ACT_PU_1', 'Q_ACT_PU_1',
                         'V_TARGET_1', 'Q_TARGET_1', 'Q_MIN_1', 'Q_MAX_1', 'Q_MIN_ERROR_1', 'Q_MAX_ERROR_1']
        else:
            sc_points = ['V_ACT_1', 'Q_ACT_1',  # 'V_ACT_PU_1', 'Q_ACT_PU_1',
                         'V_TARGET_1', 'Q_TARGET_1', 'Q_MIN_1', 'Q_MAX_1', 'Q_MIN_ERROR_1', 'Q_MAX_ERROR_1',
                         'V_ACT_2', 'Q_ACT_2',  # 'V_ACT_PU_2', 'Q_ACT_PU_2',
                         'V_TARGET_2', 'Q_TARGET_2', 'Q_MIN_2', 'Q_MAX_2', 'Q_MIN_ERROR_2', 'Q_MAX_ERROR_2',
                         'V_ACT_3', 'Q_ACT_3',  # 'V_ACT_PU_3', 'Q_ACT_PU_3',
                         'V_TARGET_3', 'Q_TARGET_3', 'Q_MIN_3', 'Q_MAX_3', 'Q_MIN_ERROR_3', 'Q_MAX_ERROR_3']

        p_min_pct = ts.param_value('srd.vv_p_min_pct')
        p_max_pct = ts.param_value('srd.vv_p_max_pct')
        k_var_min_srd = ts.param_value('srd.vv_k_var_min')
        try:
            k_var_min = float(k_var_min_srd)
        except ValueError:
            k_var_min = None
        segment_point_count = ts.param_value('srd.vv_segment_point_count')

        # set power priorities to be tested
        power_priorities = []
        if ts.param_value('vv.pp_active') == 'Enabled':
            power_priorities.append('Active')
        if ts.param_value('vv.pp_reactive') == 'Enabled':
            power_priorities.append('Reactive')

        # default power range
        p_min = p_rated * .2
        p_max = p_rated

        # use values from SRD, if supplied
        if p_min_pct is not None:
            p_min = p_rated * (p_min_pct/100.)
        if p_max is not None:
            p_max = p_rated * (p_max_pct/100.)
        p_avg = (p_min + p_max)/2

        # q_max_under should be negative
        if q_max_under > 0:
            q_max_under *= -1
        q_min_over = q_max_over/4
        q_min_under = q_max_under/4
        v_dev = min(v_nom - v_min, v_max - v_nom)
        # calculate k_var_min if not supplied in the SRD
        if k_var_min is None:
            k_var_min = (q_max_over/4)/(v_dev - deadband_max/2)
        k_var_avg = (k_var_min + k_var_max)/2
        deadband_avg = (deadband_min + deadband_max)/2

        # list of active tests
        test_1_enabled = test_2_enabled = test_3_enabled = False
        active_tests = []
        if ts.param_value('vv.test_1') == 'Enabled':
            test_1_enabled = True
            active_tests.append(1)
        if ts.param_value('vv.test_2') == 'Enabled':
            test_2_enabled = True
            active_tests.append(2)
        if ts.param_value('vv.test_3') == 'Enabled':
            test_3_enabled = True
            active_tests.append(3)

        # check for specified test curve
        spec_curve = False
        spec_curve_v = []
        spec_curve_q = []
        spec_curve_config = False
        if ts.param_value('vv.spec_curve') == 'Enabled':
            spec_curve = True
            spec_curve_v_str = ts.param_value('vv.spec_curve_v').split(',')
            if len(spec_curve_v_str) != 4:
                ts.fail('Invalid specified curve V point count (must be 4): %s' % len(spec_curve_v))
            spec_curve_v = [float(i) for i in spec_curve_v_str]
            spec_curve_q_str = ts.param_value('vv.spec_curve_q').split(',')
            if len(spec_curve_q_str) != 4:
                ts.fail('Invalid specified curve Q point count (must be 4): %s' % len(spec_curve_q))
            spec_curve_q = [float(i) for i in spec_curve_q_str]
            if ts.param_value('vv.spec_curve_config') == 'Enabled':
                spec_curve_config = True

        # create test curves based on input parameters
        tests = [0] * 5

        '''
        The script only sets points 1-4 in the EUT, however they use v[0] and v[5] for testing purposes to define
        n points on the line segment to verify the reactive power
        '''
        # Test 1 - Characteristic 1 "Most Aggressive" Curve
        if test_1_enabled:
            q = [0] * 6
            q[0] = q_max_over    # Q1
            q[1] = q_max_over
            q[2] = 0
            q[3] = 0
            q[4] = q_max_under
            q[5] = q_max_under
            v = [0] * 6
            v[2] = v_nom - deadband_min/2
            v[1] = v[2] - abs(q[1])/k_var_max
            v[0] = v_min
            v[3] = v_nom + deadband_min/2
            v[4] = v[3] + abs(q[4])/k_var_max
            v[5] = v_max

            tests[1] = [list(v), list(q), True]

        # Test 2 - Characteristic 2 "Average" Curve
        if test_2_enabled:
            q = [0] * 6
            q[0] = q_max_over * .5
            q[1] = q_max_over * .5
            q[2] = 0
            q[3] = 0
            q[4] = q_max_under * .5
            q[5] = q_max_under * .5
            v = [0] * 6
            v[2] = v_nom - deadband_avg/2
            v[1] = v[2] - abs(q[1])/k_var_avg
            v[0] = v_min
            v[3] = v_nom + deadband_avg/2
            v[4] = v[3] + abs(q[4])/k_var_avg
            v[5] = v_max
            tests[2] = [list(v), list(q), True]

        # Test 3 - Characteristic 3 "Least Aggressive" Curve
        if test_3_enabled:
            q = [0] * 6
            q[0] = q_min_over
            q[1] = q_min_over
            q[2] = 0
            q[3] = 0
            q[4] = q_min_under
            q[5] = q_min_under
            v = [0] * 6
            v[0] = v_min
            v[2] = v_nom - deadband_max/2
            v[3] = v_nom + deadband_max/2
            if k_var_min == 0:
                v[1] = 0.99*v[2]
                v[4] = 1.01*v[3]
            else:
                v[1] = v[2] - abs(q[1])/k_var_min
                v[4] = v[3] + abs(q[4])/k_var_min
            v[5] = v_max
            tests[3] = [list(v), list(q), True]

        # Specified curve
        if spec_curve:
            q = [0] * 6
            q[0] = spec_curve_q[0]/100 * q_max_over
            q[1] = q[0]
            q[2] = spec_curve_q[1]/100 * q_max_over
            q[3] = spec_curve_q[2]/100 * q_max_over
            q[4] = spec_curve_q[3]/100 * q_max_over
            q[5] = q[4]
            v = [0] * 6
            v[0] = v_min
            v[1] = spec_curve_v[0]/100 * v_nom
            v[2] = spec_curve_v[1]/100 * v_nom
            v[3] = spec_curve_v[2]/100 * v_nom
            v[4] = spec_curve_v[3]/100 * v_nom
            v[5] = v_max
            tests[4] = [list(v), list(q), spec_curve_config]
            active_tests.append(4)

        ts.log('tests = %s' % (tests))

        # list of tuples each containing (power level as % of max, # of test at power level)
        power_levels = []
        count = ts.param_value('vv.n_r_100')
        if count > 0:
            power_levels.append((1, count))
        count = ts.param_value('vv.n_r_66')
        if count > 0:
            power_levels.append((.66, count))
        count = ts.param_value('vv.n_r_min')
        if count > 0:
            power_levels.append(((p_min/p_max), count))

        '''
        1) Connect the EUT and measurement equipment according to the requirements in Sections 4 and 5 of
        IEEE Std 1547.1-2005 and specifications provided by the manufacturer.
        '''
        '''
        2) Set all AC source parameters to the nominal operating conditions for the EUT. Frequency is set at nominal
        and held at nominal throughout this test. Set the EUT power to Pmax.
        '''
        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # grid simulator is initialized with test parameters and enabled
        grid = gridsim.gridsim_init(ts)

        # In cases where the grid simulator has voltage rise/loss on the line to the EUT or operates through a
        # transformer, the nominal voltage of the grid simulator won't be the same as the EUT and a correction
        # factor is applied.
        try:
            v_nom_grid = grid.v_nom_param
        except Exception, e:
            v_nom_grid = v_nom

        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts)
        pv.power_set(p_max)
        pv.power_on()

        # initialize data acquisition
        daq = das.das_init(ts, sc_points=sc_points)

        if phases == 'Single Phase':
            n_phase = 1
        else:
            n_phase = 3

        for ph in range(n_phase):
            ph_val = ph + 1  # phase names start at 1 (not zero)
            daq.sc['V_ACT_%i' % ph_val] = ''
            daq.sc['Q_ACT_%i' % ph_val] = ''
            # daq.sc['V_ACT_PU_%i' % ph_val] = ''
            # daq.sc['Q_ACT_PU_%i' % ph_val] = ''
            daq.sc['V_TARGET_%i' % ph_val] = ''
            daq.sc['Q_TARGET_%i' % ph_val] = ''
            daq.sc['Q_MIN_%i' % ph_val] = ''
            daq.sc['Q_MAX_%i' % ph_val] = ''
            daq.sc['Q_MIN_ERROR_%i' % ph_val] = ''
            daq.sc['Q_MAX_ERROR_%i' % ph_val] = ''

        '''
        3) Turn on the EUT. Set all L/HVRT parameters to the widest range of adjustability possible with the
        VV Q(V) enabled. The EUT's range of disconnect settings may depend on which function(s) are enabled.
        '''
        # it is assumed the EUT is on
        eut = der.der_init(ts)
        if eut is not None:
            eut.config()
            eut.fixed_pf(params={'Ena': False})

        settling_time = t_settling

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        if n_phase == 1:
            result_summary.write('Result, Test Name, Power Priority, Power Level, Iteration, Var MSA, Dataset File,'
                                 'Point Result, Var Actual, Var Target, Var Min Allowed, Var Max Allowed,'
                                 'Voltage (pu), Total Reactive Power (pu)\n')
        else:
            result_summary.write('Result, Test Name, Power Priority, Power Level, Iteration, Var MSA, Dataset File,'
                                 'Point Result 1, Var Actual 1, Var Target 1, Var Min Allowed 1, Var Max Allowed 1,'
                                 'Point Result 2, Var Actual 2, Var Target 2, Var Min Allowed 2, Var Max Allowed 2,'
                                 'Point Result 3, Var Actual 3, Var Target 3, Var Min Allowed 3, Var Max Allowed 3,'
                                 'Average Voltage (pu), Total Reactive Power (pu)\n')

        for priority in power_priorities:
            '''
            4) If the EUT has the ability to set 'Active Power Priority' or 'Reactive Power Priority', select Priority
            being evaluated.
            '''
            '''
            5) Set the EUT to provide reactive power according to the Q(V) characteristic defined in Test 1 in
            Table SA13.1.
            '''
            for test in active_tests:
                ts.log('Starting test - %s' % (test_labels[test]))

                # create voltage settings along all segments of the curve
                v = tests[test][0]
                q = tests[test][1]
                v_points = sample_points(v, segment_point_count)
                ### q_points = sample_points(q, segment_point_count)
                q_points = []
                q_min_points = []
                q_max_points = []
                for p in v_points:
                    q_target, q_min, q_max = q_msa_range(p, v_msa, var_msa, tests[test][0], tests[test][1])
                    q_points.append(q_target)
                    q_min_points.append(q_min)
                    q_max_points.append(q_max)

                ts.log('Voltage test points = %s' % (v_points))
                ts.log('Var test points = %s' % (q_points))
                ts.log('Var min pass/fail limits = %s' % (q_min_points))
                ts.log('Var max pass/fail limits = %s' % (q_max_points))

                '''
                q_msa_range(v_value, v_msa, q_msa, v, q)

                x = []
                for p in v_points:
                    x.append(v_q(p, tests[4][0], tests[4][1]))
                    x.append(q_msa_range(p, v_msa, var_msa, tests[4][0], tests[4][1]))
                ts.log('v_q = %s' % (x))
                '''

                # set dependent reference type
                if priority == 'Active':
                    dept_ref = 'VAR_AVAL_PCT'
                elif priority == 'Reactive':
                    dept_ref = 'VAR_MAX_PCT'
                else:
                    raise script.ScriptFail('Unknown power priority setting: %s')

                # ts.log_debug({'v': [v[1]/v_nom*100.0, v[2]/v_nom*100.0, v[3]/v_nom*100.0, v[4]/v_nom*100.0],
                #     'var': [q[1]/q_max_over*100.0, q[2]/q_max_over*100.0, q[3]/q_max_over*100.0,
                #             q[4]/q_max_over*100.0]})

                # configure EUT if configure enabled
                if tests[test][2]:
                    # set volt/var curve
                    if eut is not None:
                        eut.volt_var_curve(1, params={
                            # convert curve points to percentages and set DER parameters
                            'v': [round(v[1]/v_nom*100.0), round(v[2]/v_nom*100.0), round(v[3]/v_nom*100.0),
                                  round(v[4]/v_nom*100.0)],
                            'var': [round(q[1]/q_max_over*100.0), round(q[2]/q_max_over*100.0),
                                    round(q[3]/q_max_over*100.0), round(q[4]/q_max_over*100.0)],
                            'Dept_Ref': dept_ref,
                        })

                        # enable volt/var curve and verify
                        eut.volt_var(params={'ActCrv': 1, 'Ena': True})
                        parameters = eut.volt_var()
                        ts.log_debug('EUT VV settings (readback): %s' % parameters)
                        if parameters['Ena'] == False:
                            ts.log_debug('Could not enable the VV function. Trying again in 3 seconds.')
                            ts.sleep(3)
                            eut.volt_var(params={'Ena': True})
                            parameters = eut.volt_var()
                            ts.log_debug('EUT VV settings (readback): %s' % parameters)
                            if parameters['Ena'] == False:
                                ts.log_error('VV function is not enabled!')
                            else:
                                ts.log('VV function enabled. Proceeding with the test...')

                for level in power_levels:
                    power = level[0]
                    # set input power level
                    ts.log('    Setting the input power of the PV simulator to %0.2f' % (p_max * power))
                    pv.power_set(p_max * power)

                    count = level[1]
                    for i in xrange(1, count + 1):
                        '''
                        6) Set the EPS voltage to a value greater than V4 for a duration of not less than the settling
                        time.
                        '''
                        '''
                        7) Begin recording the time domain response of the EUT AC voltage and current, and DC voltage
                        and current. Step down the simulated EPS voltage (the rise/fall time of simulated EPS voltage
                        shall be < 1 cyc or < 1% of settling time) until at least three points are recorded in each
                        line segment of the characteristic curve or the EUT trips from the LVRT must trip requirements.
                        Continue recording the time domain response for at least twice the settling time after each
                        voltage step.
                        '''
                        '''
                        8) Set all AC source parameters to the nominal operating conditions for the EUT. Frequency is
                        set at nominal and held at nominal throughout this test. Set the EUT power to Pmax then repeat
                        Repeat Step (7), except raising, instead of dropping, the simulated EPS voltage (the rise/fall
                        time of simulated EPS voltage shall be < 1 cyc or < 1% of settling time) until at least three
                        points are recorded in each line segment of the characteristic curve or the EUT trips from HVRT
                        must trip requirements.
                        '''

                        order_test = [('down', list(reversed(v_points)), list(reversed(q_points))),
                                      ('up', v_points, q_points)]
                        for order in order_test:
                            order_str = order[0]
                            v_test_points = order[1]
                            q_test_points = order[2]
                            # start capture
                            test_str = 'VV_%s_%s_%s_%s' % (str(test), str(int(power*100.)), order_str, str(i))
                            ts.log('Starting data capture for test %s, testing voltage from %s , with %s, '
                                   'Power = %s%%, and sweep = %s' % (order_str, test_str, test_labels[test],
                                                                     power*100., i))
                            filename = '%s.csv' % (test_str)
                            test_passfail = 'Pass'
                            daq.data_capture(True)

                            for p in range(len(v_test_points)):
                                v_target = v_test_points[p]
                                q_target = q_test_points[p]
                                ts.log('        Setting the grid voltage to %0.2f and waiting %0.1f seconds. '
                                       'Q_targ = %s' % (v_target, settling_time, q_target))
                                grid.voltage(v_target/v_nom * v_nom_grid)
                                # capture a data sample with trigger enabled
                                ts.sleep(settling_time)
                                # get last voltage reading
                                daq.data_sample()
                                data = daq.data_capture_read()

                                # Collect data from the end of the settling time
                                v_act = [data.get('AC_VRMS_1')]
                                q_act = [data.get('AC_Q_1')]
                                p_act = [data.get('AC_P_1')]
                                if phases != 'Single Phase':
                                    v_act.append(data.get('AC_VRMS_2'))
                                    v_act.append(data.get('AC_VRMS_3'))
                                    q_act.append(data.get('AC_Q_2'))
                                    q_act.append(data.get('AC_Q_3'))
                                    p_act.append(data.get('AC_P_2'))
                                    p_act.append(data.get('AC_P_3'))
                                if v_act is None or q_act is None:
                                    ts.fail('Could not get data to record target information')

                                # prepare pass/fail data
                                passfail = [None, None, None]
                                q_target = [0., 0., 0.]
                                q_min = [0., 0., 0.]
                                q_max = [0., 0., 0.]
                                # v_act_pu = [0., 0., 0.]
                                # q_act_pu = [0., 0., 0.]
                                var_aval = [var_rated/3., var_rated/3., var_rated/3.]

                                if priority == 'Active':
                                    # In the case of watt priority, calculate the available reactive power per phase
                                    if phases == 'Single Phase':
                                        var_aval = [math.sqrt(max([((s_rated/3.)**2)-(p_act[0]**2), 0.]))]
                                    else:
                                        var_aval = [math.sqrt(max([((s_rated/3.)**2)-(p_act[0]**2), 0.])),
                                                    math.sqrt(max([((s_rated/3.)**2)-(p_act[1]**2), 0.])),
                                                    math.sqrt(max([((s_rated/3.)**2)-(p_act[2]**2), 0.]))]
                                # Calculate the target reactive power for each phase and save them to the soft channels
                                for ph in range(len(v_act)):  # for each phase
                                    ph_val = ph + 1  # phase names start at 1 (not zero)
                                    q_target[ph], q_min[ph], q_max[ph] = q_msa_range(v_act[ph], v_msa, var_msa,
                                                                                     tests[test][0], tests[test][1])

                                    # For 3-phase inverters, the reactive power is spread across all 3 phases
                                    if phases != 'Single Phase':
                                        q_target[ph] = q_target[ph]/3.
                                        q_min[ph] = q_min[ph]/3.
                                        q_max[ph] = q_max[ph]/3.

                                    daq.sc['V_ACT_%i' % ph_val] = v_act[ph]
                                    daq.sc['Q_ACT_%i' % ph_val] = q_act[ph]
                                    # daq.sc['V_ACT_PU_%i' % ph_val] = v_act_pu[ph]
                                    # daq.sc['Q_ACT_PU_%i' % ph_val] = q_act_pu
                                    daq.sc['V_TARGET_%i' % ph_val] = v_target
                                    daq.sc['Q_TARGET_%i' % ph_val] = q_target[ph]
                                    daq.sc['Q_MIN_%i' % ph_val] = q_min[ph]
                                    daq.sc['Q_MAX_%i' % ph_val] = q_max[ph]
                                    daq.sc['Q_MIN_ERROR_%i' % ph_val] = abs(q_target[ph] - q_min[ph])
                                    daq.sc['Q_MAX_ERROR_%i' % ph_val] = abs(q_max[ph] - q_target[ph])

                                    # perform pass/fall on current voltage target and phase
                                    if priority == 'Reactive':
                                        passfail[ph] = test_pass_fail(var_act=q_act[ph], var_min=q_min[ph],
                                                                      var_max=q_max[ph])
                                    else:
                                        passfail[ph] = test_pass_fail(var_act=q_act[ph], var_min=q_min[ph],
                                                                      var_max=q_max[ph], var_aval=var_aval[ph],
                                                                      q_msa=var_msa, priority=priority)
                                    if passfail[ph] == 'Fail':
                                        test_passfail = 'Fail'
                                        result = script.RESULT_FAIL

                                    ts.sleep(0.05)  # insert small sleep so the test/suite can be stopped.

                                # Ensure that 1 data entry includes the soft channel data.
                                daq.data_sample()

                                # Clear soft channel data. Hopefully only 1 data entry will include the soft
                                # channel data, but it's not guaranteed
                                for ph in range(len(v_act)):  # for each phase
                                    ph_val = ph + 1  # phase names start at 1 (not zero)
                                    daq.sc['V_ACT_%i' % ph_val] = ''
                                    daq.sc['Q_ACT_%i' % ph_val] = ''
                                    # daq.sc['V_ACT_PU_%i' % ph_val] = ''
                                    # daq.sc['Q_ACT_PU_%i' % ph_val] = ''
                                    daq.sc['V_TARGET_%i' % ph_val] = ''
                                    daq.sc['Q_TARGET_%i' % ph_val] = ''
                                    daq.sc['Q_MIN_%i' % ph_val] = ''
                                    daq.sc['Q_MAX_%i' % ph_val] = ''
                                    daq.sc['Q_MIN_ERROR_%i' % ph_val] = ''
                                    daq.sc['Q_MAX_ERROR_%i' % ph_val] = ''

                                # For plotting purposes, collect the (V, Q) point for this test point
                                v_act_pu = np.mean(v_act)/v_nom
                                q_act_pu = sum(q_act)/q_max_over

                                # create result summary entry of the final measurements and pass/fail results
                                if result_summary is not None:
                                    if phases == 'Single Phase':
                                        result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s\n'
                                                             % ('', '', '', '', '', '', '',
                                                                passfail[0], q_act[0], q_target[0], q_min[0], q_max[0],
                                                                v_act_pu, q_act_pu))
                                    else:
                                        result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,'
                                                             '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n'
                                                             % ('', '', '', '', '', '', '',
                                                                passfail[0], q_act[0], q_target[0], q_min[0], q_max[0],
                                                                passfail[1], q_act[1], q_target[1], q_min[1], q_max[1],
                                                                passfail[2], q_act[2], q_target[2], q_min[2], q_max[2],
                                                                v_act_pu, q_act_pu))

                            # stop capture and save
                            daq.data_capture(False)
                            ds = daq.data_capture_dataset()
                            ds.to_csv(ts.result_file_path(filename))
                            result_params['plot.title'] = test_str
                            ts.result_file(filename, params=result_params)
                            ts.log('Saving data capture')

                            if result_summary is not None:
                                if phases == 'Single Phase':
                                    result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s\n' %
                                                         (test_passfail, test_str, priority, power*100., count,
                                                          var_msa, filename, '', '', '', '', ''))
                                else:
                                    result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
                                                         '%s, %s, %s, %s, %s, %s, %s, %s, %s\n' %
                                                         (test_passfail, test_str, priority, power*100., count,
                                                          var_msa, filename, '', '', '', '', '', '', '', '', '',
                                                          '', '', '', '', '', ''))

                        '''
                        9) Repeat test Steps (6) - (8) at power levels of 20 and 66%; as described by the following:
                           a) For the 20% test, the EUT output power set to 20% of its Prated nominal rating
                           b) For the 66% test the test input source is to be adjusted to limit the EUT output power to
                           a value between 50% and 95% of rated output power.
                           c) The 66% power level, as defined in (b), shall be repeated for a total of five sweeps of
                           the Q(V) curve to validate consistency.
                        '''
                '''
                10) Repeat steps (6) - (9) for the remaining tests in Table SA13.1. Other than stated in (9) (c), the
                required number of sweeps for each of these repetitions is three. In the case of EUT without adjustable
                (V, Q) points, this step may be eliminated.
                '''
            '''
            11) If the EUT has the ability to set 'Active Power Priority' and 'Reactive Power Priority', select the
            other Priority, return the simulated EPS voltage to nominal, and repeat steps (5) - (10).
            '''

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

        ts.svp_version(required='1.5.3')

        result = test_run()

        ts.result(result)
        if result == script.RESULT_FAIL:
            rc = 1

    except Exception, e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)

info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.0.0')

info.param_group('vv', label='Test Parameters')
info.param('vv.test_1', label='Test 1 - Most Agressive Curve', default='Enabled', values=['Disabled', 'Enabled'])
info.param('vv.test_2', label='Test 2 - Average Curve', default='Enabled', values=['Disabled', 'Enabled'])
info.param('vv.test_3', label='Test 3 - Least Agressive Curve', default='Enabled', values=['Disabled', 'Enabled'])
info.param('vv.spec_curve', label='Specified curve', default='Disabled', values=['Disabled', 'Enabled'])
info.param('vv.spec_curve_v', label='Specified curve V points (v1,v2,...)', default='',
           active='vv.spec_curve', active_value=['Enabled'])
info.param('vv.spec_curve_q', label='Specified curve Q points (q1,q2,...)', default='',
           active='vv.spec_curve', active_value=['Enabled'])
info.param('vv.spec_curve_config', label='Specified curve configure',default='Disabled',values=['Disabled', 'Enabled'],
           active='vv.spec_curve', active_value=['Enabled'])
info.param('vv.n_r_100', label='Power level 100% - number of test repetitions', default=3)
info.param('vv.n_r_66', label='Power level 66% - number of test repetitions', default=5)
info.param('vv.n_r_min', label='Power level minimum - number of test repetitions', default=3)
info.param('vv.pp_active', label='Active power priority tests', default='Enabled', values=['Disabled', 'Enabled'])
info.param('vv.pp_reactive', label='Reactive power priority tests', default='Enabled', values=['Disabled', 'Enabled'])

info.param_group('srd', label='Source Requirements Document', glob=True)
# source requirements document
info.param('srd.vv_p_min_pct', label='Minimum tested output power (% of nameplate power rating)', default=20.)
info.param('srd.vv_p_max_pct', label='Maximum tested output power (% of nameplate power rating)', default=100.)
info.param('srd.vv_k_var_min', label='Minimum slope (Var/V)', default=0.0)
info.param('srd.vv_segment_point_count', label='Measurement points per curve segment', default=3)

info.param_group('eut_vv', label='EUT VV Parameters', glob=True)
info.param('eut_vv.s_rated', label='Apparent power rating (VA)', default=0.0)
info.param('eut_vv.p_rated', label='Output power rating (W)', default=0.0)
info.param('eut_vv.var_rated', label='Output var rating (vars)', default=0.0)
info.param('eut_vv.v_nom', label='Nominal AC voltage (V)', default=0.0, desc='Nominal voltage for the AC simulator.')
info.param('eut_vv.v_min', label='Minimum AC voltage (V)', default=0.0)
info.param('eut_vv.v_max', label='Maximum AC voltage (V)', default=0.0)
info.param('eut_vv.v_msa', label='AC voltage manufacturers stated accuracy (V)', default=0.0)
info.param('eut_vv.var_msa', label='Reactive power manufacturers stated accuracy (Var)', default=0.0)

info.param('eut_vv.var_ramp_max', label='Maximum ramp rate (VAr/s)', default=0.0)
info.param('eut_vv.q_max_over', label='Maximum reactive power production (over-excited) (VAr)', default=0.0)
info.param('eut_vv.q_max_under', label='Maximum reactive power absorbtion (under-excited) (VAr)(-)', default=0.0)
info.param('eut_vv.k_var_max', label='Maximum slope (VAr/V)', default=0.0)
info.param('eut_vv.vv_deadband_min', label='Deadband minimum range (V)', default=0.0)
info.param('eut_vv.vv_deadband_max', label='Deadband maximum range (V)', default=0.0)
info.param('eut_vv.vv_t_settling', label='Settling time (t)', default=0.0)

info.param('eut_vv.phases', label='Phases', default='Single Phase', values=['Single Phase', '3-Phase 3-Wire',
                                                                         '3-Phase 4-Wire'])
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



