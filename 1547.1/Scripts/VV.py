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
from svpelab import gridsim
from svpelab import pvsim
from svpelab import das
from svpelab import der
from svpelab import hil
from svpelab import result as rslt
from datetime import datetime, timedelta
import script
import math
import numpy as np
import collections
#import cmath

test_labels = {
    1: 'Characteristic Curve 1',
    2: 'Characteristic Curve 2',
    3: 'Characteristic Curve 3',
    4: 'Vref test',
    5: 'Imbalanced grid',
    'Characteristic Curve 1': [1],
    'Characteristic Curve 2': [2],
    'Characteristic Curve 3': [3],
    'Vref test': [4],
    'Imbalanced grid': [5]
}


def interpolation_v_q(value, v_pairs, pwr_lvl):
    """
    Interpolation function to find the target reactive power based on a 4 point VV curve

    TODO: make generic for n-point curves

    :param value: voltage point for the interpolation
    :param v: VV voltage points
    :param q: VV reactive power points
    :return: target reactive power
    """
    if value <= v_pairs['V1']:
        q_value = v_pairs['Q1']
    elif value < v_pairs['V2']:
        q_value = v_pairs['Q1'] + ((v_pairs['Q2'] - v_pairs['Q1']) / (v_pairs['V2'] - v_pairs['V1']) * (value - v_pairs['V1']))
    elif value == v_pairs['V2']:
        q_value = v_pairs['Q2']
    elif value <= v_pairs['V3']:
        q_value = v_pairs['Q3']
    elif value < v_pairs['V4']:
        q_value = v_pairs['Q3'] + ((v_pairs['Q4'] - v_pairs['Q3']) / (v_pairs['V4'] - v_pairs['V3']) * (value - v_pairs['V3']))
    else:
        q_value = v_pairs['Q4']
    q_value *= pwr_lvl
    return round(q_value, 1)

def q_v_criteria(v_pairs, v_target, MSA_V, MSA_Q, daq, tr,  step, q_initial, pwr_lvl=1.0):
    """
    Determine Q(MSAs)
    :param v_pairs:     Voltage point for the interpolation
    :param v_target:     Voltage point for the interpolation
    :param pf:          power factor target
    :param MSA_P:       manufacturer's specified accuracy of active power (W)
    :param MSA_Q:       manufacturer's specified accuracy of reactive power (VAr)
    :param daq:         data acquisition object in order to manipulated
    :param tr:          response time (s)
    :param step:        test procedure step letter or number (e.g "Step G")
    :param q_initial:   dictionnary with timestamp and reactive value before step change
    :param pwr_lvl:     The test power level (0.2 , 0.66 or 1 )
    :return:    dictionnary q_v_analysis that contains passfail of response time requirements ( q_v_analysis['Q_TR_PF'])
    and test result accuracy requirements ( q_v_analysis['Q_FINAL_PF'] )
    """
    tr_analysis = 'start'
    result_analysis = 'start'
    q_v_analysis = {}

    """
    Every time a parameter is stepped or ramped, 
    measure and record the time domain current and 
    voltage response for at least 4 times the maximum 
    expected response time after the stimulus, and measure or derive, 
    active power, apparent power, reactive power, and power factor.

    This is only for the response time requirements (5.14.3.3 Criteria)
    """
    first_tr = q_initial['timestamp'] + timedelta(seconds=tr)
    four_times_tr = q_initial['timestamp'] + timedelta(seconds=4 * tr)
    daq.sc['V_TARGET'] = v_target

    try:
        while tr_analysis == 'start':
            time_to_sleep = first_tr - datetime.now()
            ts.sleep(time_to_sleep.total_seconds())
            now = datetime.now()
            if first_tr <= now:
                daq.data_sample()
                data = daq.data_capture_read()
                daq.sc['V_MEAS'] = measurement_total(data=data, type_meas='V', log=False)
                daq.sc['Q_MEAS'] = measurement_total(data=data, type_meas='Q', log=False)
                #daq.sc['P_MEAS'] = measurement_total(data=data, type_meas='P', log=False)
                # The variable q_tr is the value use to verify the time response requirement.
                v_tr = daq.sc['V_MEAS']
                q_tr = daq.sc['Q_MEAS']
                daq.sc['Q_TARGET'] = interpolation_v_q(daq.sc['V_MEAS'], v_pairs=v_pairs, pwr_lvl=pwr_lvl)
                daq.sc['Q_TARGET_MIN'] = interpolation_v_q(daq.sc['V_MEAS']+1.5*MSA_V, v_pairs=v_pairs, pwr_lvl=pwr_lvl) - 1.5*MSA_Q
                daq.sc['Q_TARGET_MAX'] = interpolation_v_q(daq.sc['V_MEAS']-1.5*MSA_V, v_pairs=v_pairs, pwr_lvl=pwr_lvl) + 1.5*MSA_Q
                daq.data_sample()
                daq.sc['event'] = "{}_tr_1".format(step)
                daq.data_sample()

                if daq.sc['Q_TARGET_MIN'] <= daq.sc['Q_MEAS'] <= daq.sc['Q_TARGET_MAX']:
                    q_v_analysis['Q_TR_PF'] = 'Pass'
                    ts.log('        Q(Tr) evaluation: %0.1f <= %0.1f <= %0.1f  [PASS]' %
                           (daq.sc['Q_TARGET_MIN'], daq.sc['Q_MEAS'], daq.sc['Q_TARGET_MAX']))
                else:
                    q_v_analysis['Q_TR_PF'] = 'Fail'
                    ts.log_error('        Q(Tr) evaluation: %0.1f <= %0.1f <= %0.1f  [FAIL]' %
                                 (daq.sc['Q_TARGET_MIN'], daq.sc['Q_MEAS'], daq.sc['Q_TARGET_MAX']))
                # This is to get out of the while loop. It provides the timestamp of tr_1
                tr_analysis = now
                q_v_analysis['tr_analysis'] = tr_analysis

        while result_analysis == 'start':
            time_to_sleep = four_times_tr - datetime.now()
            ts.sleep(time_to_sleep.total_seconds())
            now = datetime.now()
            if four_times_tr <= now:
                daq.data_sample()
                data = daq.data_capture_read()
                daq.sc['V_MEAS'] = measurement_total(data=data, type_meas='V', log=False)
                daq.sc['Q_MEAS'] = measurement_total(data=data, type_meas='Q', log=False)
                daq.sc['event'] = "{}_tr_4".format(step)
                # To calculate the min/max, you need the measured value
                # reactive power target from the lower voltage limit
                daq.sc['Q_TARGET_MIN'] = interpolation_v_q(daq.sc['V_MEAS']+1.5*MSA_V, v_pairs=v_pairs, pwr_lvl=pwr_lvl) - 1.5*MSA_Q
                # reactive power target from the upper voltage limit
                daq.sc['Q_TARGET_MAX'] = interpolation_v_q(daq.sc['V_MEAS']-1.5*MSA_V, v_pairs=v_pairs, pwr_lvl=pwr_lvl) + 1.5*MSA_Q
                daq.data_sample()

                """
                The variable q_tr is the value use to verify the time response requirement.
                |----------|----------|----------|----------|
                           1st tr     2nd tr     3rd tr     4th tr            
                |          |                                |
                q_initial  q_tr                             q_final    

                (1547.1)After each voltage, the open loop response time, Tr , is evaluated. 
                The expected reactive power output, Q(T r ), at one times the open loop response time,
                is calculated as 90% x (Qfinal - Q initial ) + Q initial
                """

                q_v_analysis['Q_INITIAL'] = q_initial['value']
                q_v_analysis['Q_FINAL'] = daq.sc['Q_MEAS']
                q_tr_diff = q_v_analysis['Q_FINAL'] - q_v_analysis['Q_INITIAL']
                q_tr_target = ((0.9 * q_tr_diff) + q_v_analysis['Q_INITIAL'])
                # This q_tr_diff < 0 has been added to tackle when Q_final - Q_initial is negative.
                if q_tr_diff < 0:
                    if q_tr <= q_tr_target:
                        q_v_analysis['TR_PF'] = 'Pass'
                    else:
                        q_v_analysis['TR_PF'] = 'Fail'
                elif q_tr_diff >= 0:
                    if q_tr >= q_tr_target:
                        q_v_analysis['TR_PF'] = 'Pass'
                    else:
                        q_v_analysis['TR_PF'] = 'Fail'

                if daq.sc['Q_TARGET_MIN'] <= daq.sc['Q_MEAS'] <= daq.sc['Q_TARGET_MAX']:
                    q_v_analysis['Q_FINAL_PF'] = 'Pass'
                else:
                    q_v_analysis['Q_FINAL_PF'] = 'Fail'
                ts.log('        Q_TR [%s], TR [%s], Q_FINAL [%s]' %
                       (q_v_analysis['Q_TR_PF'], q_v_analysis['TR_PF'], q_v_analysis['Q_FINAL_PF']))

                # This is to get out of the while loop. It provides the timestamp of tr_4
                result_analysis = now
                q_v_analysis['result_analysis'] = result_analysis

    except:
        daq.sc['V_MEAS'] = 'No Data'
        daq.sc['P_MEAS'] = 'No Data'
        daq.sc['Q_MEAS'] = 'No Data'
        #passfail = 'Fail'
        daq.sc['Q_TARGET_MIN'] = 'No Data'
        daq.sc['Q_TARGET_MAX'] = 'No Data'

    return q_v_analysis

def get_q_initial(daq, step):
    """
    Sum the EUT reactive power from all phases
    :param daq:         data acquisition object in order to manipulated
    :param step:        test procedure step letter or number (e.g "Step G")
    :return: returns a dictionnary with the timestamp, event and total EUT reactive power
    """
    # TODO : In a more sophisticated approach, q_initial['timestamp'] will come from a reliable secure thread or data acquisition timestamp
    q_initial={}
    q_initial['timestamp'] = datetime.now()
    daq.data_sample()
    data = daq.data_capture_read()
    daq.sc['event'] = step
    daq.sc['Q_MEAS'] = measurement_total(data=data, type_meas='Q', log=False)
    daq.data_sample()
    q_initial['value'] = daq.sc['Q_MEAS']
    return q_initial

def get_measurement_label(type_meas):
    """
    Sum the EUT reactive power from all phases
    :param type_meas:   Either V,P or Q
    :return:            List of labeled measurements
    """

    phases = ts.param_value('eut.phases')
    if type_meas == 'V':
        meas_root = 'AC_VRMS'
    elif type_meas == 'P':
        meas_root = 'AC_P'
    elif type_meas == 'PF':
        meas_root = 'AC_PF'
    elif type_meas == 'I':
        meas_root = 'AC_IRMS'
    else:
        meas_root = 'AC_Q'
    if phases == 'Single phase':
        meas_label = [meas_root+'_1']
    elif phases == 'Split phase':
        meas_label = [meas_root+'_1',meas_root+'_2']
    elif phases == 'Three phase':
        meas_label = [meas_root+'_1',meas_root+'_2',meas_root+'_3']

    return meas_label

def measurement_total(data, type_meas,log):
    """
    Sum the EUT reactive power from all phases
    :param data:        dataset from data acquistion object
    :param type_meas:   Either V,P or Q
    :param log:         Boolean variable to disable or enable logging
    :return: either total EUT reactive power, total EUT active power or average V
    """
    phases = ts.param_value('eut.phases')

    if phases == 'Single phase':
        value = data.get(get_measurement_label(type_meas)[0])
        if log:
            ts.log_debug('        %s are: %s' % (get_measurement_label(type_meas),value))
        nb_phases = 1

    elif phases == 'Split phase':
        value1 = data.get(get_measurement_label(type_meas)[0])
        value2 = data.get(get_measurement_label(type_meas)[1])
        if log:
            ts.log_debug('        %s are: %s, %s' % (get_measurement_label(type_meas),value1,value2))
        value = value1 + value2
        nb_phases = 2

    elif phases == 'Three phase':
        value1 = data.get(get_measurement_label(type_meas)[0])
        value2 = data.get(get_measurement_label(type_meas)[1])
        value3 = data.get(get_measurement_label(type_meas)[2])
        if log:
            ts.log_debug('        %s are: %s, %s, %s' % (get_measurement_label(type_meas),value1,value2,value3))
        value = value1 + value2 + value3
        nb_phases = 3

    else:
        ts.log_error('Inverter phase parameter not set correctly.')
        ts.log_error('phases=%s' % phases)
        raise

    if type_meas == 'V':
        # average value of V
        value = value/nb_phases

    elif type_meas == 'P':
        return abs(value)

    return value


def volt_vars_mode(vv_curves, vv_response_time, pwr_lvls, v_ref_value):

    result = script.RESULT_FAIL
    daq = None
    v_nom = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None

    try:
        cat = ts.param_value('eut.cat')
        cat2 = ts.param_value('eut.cat2')
        sink_power = ts.param_value('eut.sink_power')
        p_rated = ts.param_value('eut.p_rated')
        p_rated_prime = ts.param_value('eut.p_rated_prime')
        var_rated = ts.param_value('eut.var_rated')
        s_rated = ts.param_value('eut.s_rated')

        #TODO Implement eut efficiency?

        #absorb_enable = ts.param_value('eut.abs_enabled')
        # DC voltages
        v_in_nom = ts.param_value('eut.v_in_nom')
        #v_min_in = ts.param_value('eut.v_in_min')
        #v_max_in = ts.param_value('eut.v_in_max')

        # AC voltages
        v_nom = ts.param_value('eut.v_nom')
        v_low = ts.param_value('eut.v_low')
        v_high = ts.param_value('eut.v_high')
        p_min = ts.param_value('eut.p_min')
        p_min_prime = ts.param_value('eut.p_min_prime')
        phases = ts.param_value('eut.phases')
        #imbalance_resp = ts.param_value('eut.imbalance_resp')

        # Pass/fail accuracies
        # According to Table 3-Minimum requirements for manufacturers stated measured and calculated accuracy
        MSA_Q = 0.05 * s_rated
        MSA_P = 0.05 * s_rated
        MSA_V = 0.01 * v_nom
        '''
        a) Connect the EUT according to the instructions and specifications provided by the manufacturer.
        '''

        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts)
        if pv is not None:
            pv.power_set(p_rated)
            pv.power_on()  # Turn on DC so the EUT can be initialized

        # DAS soft channels
        das_points = {'sc': ('Q_TARGET', 'Q_TARGET_MIN', 'Q_TARGET_MAX', 'Q_MEAS', 'V_TARGET', 'V_MEAS', 'event')}

        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])

        daq.sc['V_TARGET'] = v_nom
        daq.sc['Q_TARGET'] = 100
        daq.sc['Q_TARGET_MIN'] = 100
        daq.sc['Q_TARGET_MAX'] = 100
        daq.sc['event'] = 'None'

        ts.log('DAS device: %s' % daq.info())

        ts.log_debug('power_lvl_dictionary: %s' % (pwr_lvls))
        ts.log_debug('%s' % (vv_curves))

        '''
        b) Set all voltage trip parameters to the widest range of adjustability.  Disable all reactive/active power
        control functions.
        '''

        eut = der.der_init(ts)
        if eut is not None:
            eut.config()
            ts.log_debug(eut.measurements())

            eut.volt_var(params={'Ena': False})
            eut.volt_watt(params={'Ena': False})
            eut.fixed_pf(params={'Ena': False})
            ts.log_debug('Voltage trip parameters set to the widest range: v_min: {0} V, '
                         'v_max: {1} V'.format(v_low, v_high))
            try:
                eut.vrt_stay_connected_high(params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000,
                                                    'V1': v_high, 'Tms2': 0.16, 'V2': v_high})
            except Exception, e:
                ts.log_error('Could not set VRT Stay Connected High curve. %s' % e)
            try:
                eut.vrt_stay_connected_low(params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000,
                                                   'V1': v_low, 'Tms2': 0.16, 'V2': v_low})
            except Exception, e:
                ts.log_error('Could not set VRT Stay Connected Low curve. %s' % e)
        else:
            ts.log_debug('Set L/HVRT and trip parameters set to the widest range of adjustability possible.')

        # Special considerations for CHIL ASGC/Typhoon startup
        if chil is not None:
            inv_power = eut.measurements().get('W')
            timeout = 120.
            if inv_power <= p_rated * 0.85:
                pv.irradiance_set(995)  # Perturb the pv slightly to start the inverter
                ts.sleep(3)
                eut.connect(params={'Conn': True})
            while inv_power <= p_rated * 0.85 and timeout >= 0:
                ts.log('Inverter power is at %0.1f. Waiting up to %s more seconds or until EUT starts...' %
                       (inv_power, timeout))
                ts.sleep(1)
                timeout -= 1
                inv_power = eut.measurements().get('W')
                if timeout == 0:
                    result = script.RESULT_FAIL
                    raise der.DERError('Inverter did not start.')
            ts.log('Waiting for EUT to ramp up')
            ts.sleep(8)
            ts.log_debug('DAS data_read(): %s' % daq.data_read())

        '''
        c) Set all AC test source parameters to the nominal operating voltage and frequency.
        '''
        grid = gridsim.gridsim_init(ts)  # Turn on AC so the EUT can be initialized
        if grid is not None:
            grid.voltage(v_nom)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write('Q_TR_ACC_REQ, TR_REQ, Q_FINAL_ACC_REQ, V_MEAS, Q_MEAS,Q_TARGET, Q_TARGET_MIN, '
                             'Q_TARGET_MAX, STEP,FILENAME\n')

        # STD_CHANGE Typo with step U. - Out of order
        '''
        d) Adjust the EUT's available active power to Prated. For an EUT with an input voltage range, set the input
        voltage to Vin_nom. The EUT may limit active power throughout the test to meet reactive power requirements.
        For an EUT with an input voltage range.
        '''
        ts.log('%s %s' % (p_rated, v_in_nom))
        ts.log('%s %s' % (type(p_rated), type(v_in_nom)))

        if pv is not None:
            pv.iv_curve_config(pmp=p_rated, vmp=v_in_nom)
            pv.irradiance_set(1000.)

        v_pairs = collections.OrderedDict()

        v_pairs[1] = {'V1': round(0.92 * v_nom, 2),
                'V2': round(0.98 * v_nom, 2),
                'V3': round(1.02 * v_nom, 2),
                'V4': round(1.08 * v_nom, 2),
                'Q1': round(var_rated * 1.0, 2),
                'Q2': round(var_rated * 0.0, 2),
                'Q3': round(var_rated * 0.0, 2),
                'Q4': round(var_rated * -1.0, 2)}

        v_pairs[2] = {'V1': round(0.88 * v_nom, 2),
                'V2': round(1.04 * v_nom, 2),
                'V3': round(1.07 * v_nom, 2),
                'V4': round(1.10 * v_nom, 2),
                'Q1': round(var_rated * 1.0, 2),
                'Q2': round(var_rated * 0.5, 2),
                'Q3': round(var_rated * 0.5, 2),
                'Q4': round(var_rated * -1.0, 2)}

        v_pairs[3] = {'V1': round(0.90 * v_nom, 2),
                    'V2': round(0.93 * v_nom, 2),
                    'V3': round(0.96 * v_nom, 2),
                    'V4': round(1.10 * v_nom, 2),
                    'Q1': round(var_rated * 1.0, 2),
                    'Q2': round(var_rated * -0.5, 2),
                    'Q3': round(var_rated * -0.5, 2),
                    'Q4': round(var_rated * -1.0, 2)}

        '''
        dd) Repeat steps e) through dd) for characteristics 2 and 3.
        '''
        for vv_curve in vv_curves:
            ts.log('Starting test with characteristic curve %s' % (vv_curve))

            '''
            d2) Set EUT volt-var parameters to the values specified by Characteristic 1.
            All other function should be turned off. Turn off the autonomously adjusting reference voltage.
            '''
            if eut is not None:
                # Activate volt-var function with following parameters
                # SunSpec convention is to use percentages for V and Q points.
                vv_curve_params = {'v': [v_pairs[vv_curve]['V1']*(100./v_nom), v_pairs[vv_curve]['V2']*(100./v_nom),
                                         v_pairs[vv_curve]['V3']*(100./v_nom), v_pairs[vv_curve]['V4']*(100./v_nom)],
                                   'var': [v_pairs[vv_curve]['Q1']*(100./var_rated),
                                           v_pairs[vv_curve]['Q2']*(100./var_rated),
                                           v_pairs[vv_curve]['Q3']*(100./var_rated),
                                           v_pairs[vv_curve]['Q4']*(100./var_rated)]}

                eut.volt_var(params={'Ena': True, 'curve': vv_curve_params})
                eut.volt_watt(params={'Ena': False})
                # TODO autonomous vref adjustment to be included
                # eut.autonomous_vref_adjustment(params={'Ena': False})

                '''
                e) Verify volt-var mode is reported as active and that the correct characteristic is reported.
                '''
                ts.log_debug('Initial EUT VV settings are %s' % eut.volt_var())

            '''
            cc) Repeat test steps d) through cc) at EUT power set at 20% and 66% of rated power.
            '''
            for power in pwr_lvls:

                '''
                bb) Repeat test steps e) through bb) with Vref set to 1.05*VN and 0.95*VN, respectively.
                '''
                for v_ref in v_ref_value:
                    ts.log('Setting v_ref at %s %% of v_nom' % (int(v_ref*100)))
                    v_steps_dict = collections.OrderedDict()

                    # Capacitive test
                    v_steps_dict['Step F'] = v_pairs[vv_curve]['V3'] - 1.5*MSA_V
                    v_steps_dict['Step G'] = v_pairs[vv_curve]['V3'] + 1.5*MSA_V
                    v_steps_dict['Step H'] = (v_pairs[vv_curve]['V3'] + v_pairs[vv_curve]['V4']) / 2

                    '''
                    i) If V4 is less than VH, step the AC test source voltage to av below V4, else skip to step l).
                    l) Begin the return to VRef. If V4 is less than VH, step the AC test source voltage to av above V4,
                       else skip to step n).
                    '''
                    if v_pairs[vv_curve]['V4'] < v_high:
                        v_steps_dict['Step I'] = v_pairs[vv_curve]['V4'] - 1.5*MSA_V
                        v_steps_dict['Step J'] = v_pairs[vv_curve]['V4'] + 1.5*MSA_V
                        v_steps_dict['Step K'] = v_high - 1.5*MSA_V
                        v_steps_dict['Step L'] = v_pairs[vv_curve]['V4'] + 1.5*MSA_V
                        v_steps_dict['Step M'] = (v_pairs[vv_curve]['V3'] + v_pairs[vv_curve]['V4']) / 2
                    v_steps_dict['Step N'] = v_pairs[vv_curve]['V3'] + 1.5*MSA_V
                    v_steps_dict['Step O'] = v_pairs[vv_curve]['V3'] - 1.5*MSA_V
                    v_steps_dict['Step P'] = v_ref*v_nom

                    # Inductive test
                    v_steps_dict['Step Q'] = v_pairs[vv_curve]['V2'] + 1.5*MSA_V
                    v_steps_dict['Step R'] = v_pairs[vv_curve]['V2'] - 1.5*MSA_V
                    v_steps_dict['Step S'] = (v_pairs[vv_curve]['V1'] + v_pairs[vv_curve]['V2']) / 2

                    '''
                    t) If V1 is greater than VL, step the AC test source voltage to av above V1, else skip to step x).
                    '''
                    if v_pairs[vv_curve]['V1'] > v_low:
                        v_steps_dict['Step T'] = v_pairs[vv_curve]['V1'] + 1.5*MSA_V
                        v_steps_dict['Step U'] = v_pairs[vv_curve]['V1'] - 1.5*MSA_V
                        v_steps_dict['Step V'] = v_low + 1.5*MSA_V
                        v_steps_dict['Step W'] = v_pairs[vv_curve]['V1'] + 1.5*MSA_V
                        v_steps_dict['Step X'] = (v_pairs[vv_curve]['V1'] + v_pairs[vv_curve]['V2']) / 2
                    v_steps_dict['Step Y'] = v_pairs[vv_curve]['V2'] - 1.5*MSA_V
                    v_steps_dict['Step Z'] = v_pairs[vv_curve]['V2'] + 1.5*MSA_V
                    v_steps_dict['Step aa'] = v_ref*v_nom

                    for step, voltage in v_steps_dict.iteritems():
                        v_steps_dict.update({step: round(voltage, 2)})
                        if voltage > v_high:
                            v_steps_dict.update({step: v_high})
                        elif voltage < v_low:
                            v_steps_dict.update({step: v_low})

                    dataset_filename = 'VV_%s_PWR_%d_vref_%d' % (vv_curve, power * 100, v_ref*100)
                    ts.log('------------{}------------'.format(dataset_filename))
                    # Start the data acquisition systems
                    daq.data_capture(True)

                    for step_label, v_step in v_steps_dict.iteritems():
                        ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_step, step_label))
                        q_initial = get_q_initial(daq=daq, step=step_label)
                        if grid is not None:
                            grid.voltage(v_step)
                        q_v_analysis = q_v_criteria(v_pairs=v_pairs[vv_curve],
                                                    v_target=v_step,
                                                    MSA_V=MSA_V,
                                                    MSA_Q=MSA_Q,
                                                    daq=daq,
                                                    tr=vv_response_time[vv_curve],
                                                    step=step_label,
                                                    q_initial=q_initial,
                                                    pwr_lvl=power)

                        result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                             (q_v_analysis['Q_TR_PF'],
                                              q_v_analysis['TR_PF'],
                                              q_v_analysis['Q_FINAL_PF'],
                                              daq.sc['V_MEAS'],
                                              daq.sc['Q_MEAS'],
                                              daq.sc['Q_TARGET'],
                                              daq.sc['Q_TARGET_MIN'],
                                              daq.sc['Q_TARGET_MAX'],
                                              step_label,
                                              dataset_filename))

                    # result params
                    result_params = {
                        'plot.title': 'title_name',
                        'plot.x.title': 'Time (sec)',
                        'plot.x.points': 'TIME',
                        'plot.y.points': 'Q_TARGET,Q_MEAS',
                        'plot.y.title': 'Reactive Power (Var)',
                        'plot.y2.points': 'V_TARGET,V_MEAS',
                        'plot.y2.title': 'Voltage (V)',
                        'plot.Q_TARGET.min_error': 'Q_TARGET_MIN',
                        'plot.Q_TARGET.max_error': 'Q_TARGET_MAX',
                    }

                    ts.log('Sampling complete')
                    dataset_filename = dataset_filename + ".csv"
                    daq.data_capture(False)
                    ds = daq.data_capture_dataset()
                    ts.log('Saving file: %s' % dataset_filename)
                    ds.to_csv(ts.result_file_path(dataset_filename))
                    result_params['plot.title'] = dataset_filename.split('.csv')[0]
                    ts.result_file(dataset_filename, params=result_params)
                    result = script.RESULT_COMPLETE

        return result

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
            if v_nom is not None:
                grid.voltage(v_nom)
            grid.close()
        if chil is not None:
            chil.close()
        if eut is not None:
            eut.volt_var(params={'Ena': False})
            eut.close()
        if result_summary is not None:
            result_summary.close()


def volt_var_mode_vref_test():

    return 1

def volt_var_mode_imbalanced_grid(imbalance_resp, vv_curves, vv_response_time):

    result = script.RESULT_FAIL
    daq = None
    v_nom = None
    p_rated = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None

    try:
        #cat = ts.param_value('eut.cat')
        #cat2 = ts.param_value('eut.cat2')
        #sink_power = ts.param_value('eut.sink_power')
        p_rated = ts.param_value('eut.p_rated')
        #p_rated_prime = ts.param_value('eut.p_rated_prime')
        var_rated = ts.param_value('eut.var_rated')
        s_rated = ts.param_value('eut.s_rated')

        #absorb_enable = ts.param_value('eut.abs_enabled')

        # DC voltages
        v_in_nom = ts.param_value('eut.v_in_nom')
        #v_min_in = ts.param_value('eut.v_in_min')
        #v_max_in = ts.param_value('eut.v_in_max')

        # AC voltages
        v_nom = ts.param_value('eut.v_nom')
        v_min = ts.param_value('eut.v_low')
        v_max = ts.param_value('eut.v_high')
        p_min = ts.param_value('eut.p_min')
        p_min_prime = ts.param_value('eut.p_min_prime')
        phases = ts.param_value('eut.phases')
        pf_response_time = ts.param_value('vv.test_imbalanced_t_r')

        # Pass/fail accuracies
        pf_msa = ts.param_value('eut.pf_msa')
        # According to Table 3-Minimum requirements for manufacturers stated measured and calculated accuracy
        MSA_Q = 0.05 * s_rated
        MSA_P = 0.05 * s_rated
        MSA_V = 0.01 * v_nom

        # Imbalance configuration
        '''
                                            Table 24 - Imbalanced Voltage Test Cases
                +-----------------------------------------------------+-----------------------------------------------+
                | Phase A (p.u.)  | Phase B (p.u.)  | Phase C (p.u.)  | In order to keep V0 magnitude                 |
                |                 |                 |                 | and angle at 0. These parameter can be used.  |
                +-----------------+-----------------+-----------------+-----------------------------------------------+
                |       Mag       |       Mag       |       Mag       | Mag   | Ang  | Mag   | Ang   | Mag   | Ang    |
        +-------+-----------------+-----------------+-----------------+-------+------+-------+-------+-------+--------+
        |Case A |     >= 1.07     |     <= 0.91     |     <= 0.91     | 1.08  | 0.0  | 0.91  |-126.59| 0.91  | 126.59 |
        +-------+-----------------+-----------------+-----------------+-------+------+-------+-------+-------+--------+
        |Case B |     <= 0.91     |     >= 1.07     |     >= 1.07     | 0.9   | 0.0  | 1.08  |-114.5 | 1.08  | 114.5  |
        +-------+-----------------+-----------------+-----------------+-------+------+-------+-------+-------+--------+

        For tests with imbalanced, three-phase voltages, the manufacturer shall state whether the EUT responds
        to individual phase voltages, or the average of the three-phase effective (RMS) values or the positive
        sequence of voltages. For EUTs that respond to individual phase voltages, the response of each
        individual phase shall be evaluated. For EUTs that response to the average of the three-phase effective
        (RMS) values mor the positive sequence of voltages, the total three-phase reactive and active power
        shall be evaluated.
        '''
        imbalance_fix = ts.param_value('vv.imbalance_fix')
        mag = {}
        ang = {}

        if imbalance_fix == "Yes":
            # Case A
            mag['case_a'] = [1.07 * v_nom, 0.91 * v_nom, 0.91 * v_nom]
            ang['case_a'] = [0., 120, -120]
            # Case B
            mag['case_b'] = [0.91 * v_nom, 1.07 * v_nom, 1.07 * v_nom]
            ang['case_b'] = [0., 120.0, -120.0]
        else:
            # Case A
            mag['case_a'] = [1.08 * v_nom, 0.91 * v_nom, 0.91 * v_nom]
            ang['case_a'] = [0., 126.59, -126.59]
            # Case B
            mag['case_b'] = [0.9 * v_nom, 1.08 * v_nom, 1.08 * v_nom]
            ang['case_b'] = [0., 114.5, -114.5]

        '''
        a) Connect the EUT according to the instructions and specifications provided by the manufacturer.
        '''
        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # grid simulator is initialized with test parameters and enabled
        grid = gridsim.gridsim_init(ts)  # Turn on AC so the EUT can be initialized
        if grid is not None:
            grid.voltage(v_nom)

        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts)
        pv.power_set(p_rated)
        pv.power_on()  # Turn on DC so the EUT can be initialized

        # DAS soft channels
        das_points = {'sc': ('Q_TARGET', 'Q_TARGET_MIN', 'Q_TARGET_MAX', 'Q_MEAS', 'V_TARGET', 'V_MEAS', 'event')}

        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])
        daq.sc['Q_TARGET'] = 100
        daq.sc['Q_TARGET_MIN'] = 100
        daq.sc['Q_TARGET_MAX'] = 100
        daq.sc['V_TARGET'] = v_nom
        daq.sc['event'] = 'None'

        ts.log('DAS device: %s' % daq.info())

        '''
        b) Set all voltage trip parameters to the widest range of adjustability. Disable all reactive/active power
        control functions.
        '''

        '''
        c) Set all AC test source parameters to the nominal operating voltage and frequency.
        '''
        if grid is not None:
            grid.voltage(v_nom)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)

        result_summary.write('Q_TR_ACC_REQ, TR_REQ, Q_FINAL_ACC_REQ, V_MEAS, Q_MEAS, Q_TARGET, Q_TARGET_MIN, '
                             'Q_TARGET_MAX, STEP,FILENAME\n')

        '''
         d) Adjust the EUT's available active power to Prated. For an EUT with an input voltage range, set the input
        voltage to Vin_nom.
        '''

        if pv is not None:
            pv.iv_curve_config(pmp=p_rated, vmp=v_in_nom)
            pv.irradiance_set(1000.)

        '''
        h) Once steady state is reached, begin the adjustment of phase voltages.
        '''

        """
        Test start
        """

        for imbalance_response in imbalance_resp:
            for vv_curve in vv_curves:

                '''
                 e) Set EUT volt-watt parameters to the values specified by Characteristic 1. All other function be turned off.
                 '''

                v_pairs = collections.OrderedDict()  # {}

                v_pairs[1] = {'V1': round(0.92 * v_nom, 2),
                              'V2': round(0.98 * v_nom, 2),
                              'V3': round(1.02 * v_nom, 2),
                              'V4': round(1.08 * v_nom, 2),
                              'Q1': round(var_rated * 1.0, 2),
                              'Q2': round(var_rated * 0.0, 2),
                              'Q3': round(var_rated * 0.0, 2),
                              'Q4': round(var_rated * -1.0, 2)}

                # it is assumed the EUT is on
                eut = der.der_init(ts)
                if eut is not None:
                    vv_curve_params = {'v': [v_pairs[vv_curve]['V1']/v_nom, v_pairs[vv_curve]['V2']/v_nom,
                                             v_pairs[vv_curve]['V3']/v_nom, v_pairs[vv_curve]['V4']/v_nom],
                                       'q': [v_pairs[vv_curve]['Q1']/var_rated, v_pairs[vv_curve]['Q2']/var_rated,
                                             v_pairs[vv_curve]['Q3']/var_rated, v_pairs[vv_curve]['Q4']/var_rated],
                                       'DeptRef': 'Q_MAX_PCT'}
                    vv_params = {'Ena': True, 'ActCrv': 1, 'curve': vv_curve_params}
                    eut.volt_var(params=vv_params)

                '''
                f) Verify volt-var mode is reported as active and that the correct characteristic is reported.
                '''
                ts.log_debug('Initial EUT VV settings are %s' % eut.volt_var())
                ts.log_debug('curve points:  %s' % v_pairs[vv_curve])

                """
                g) Wait for steady state to be reached.
    
                Every time a parameter is stepped or ramped, measure and record the time domain current and voltage
                response for at least 4 times the maximum expected response time after the stimulus, and measure or
                derive, active power, apparent power, reactive power, and power factor.
                """
                step = 'Step G'
                daq.sc['event'] = step
                daq.data_sample()
                ts.log('Wait for steady state to be reached')
                ts.sleep(4 * vv_response_time[vv_curve])
                ts.log(imbalance_resp)

                ts.log('Starting imbalance test with VW mode at %s' % (imbalance_response))

                if imbalance_fix == "Yes":
                    dataset_filename = 'VW_IMB_%s_FIX' % (imbalance_response)
                else:
                    dataset_filename = 'VW_IMB_%s' % (imbalance_response)
                ts.log('------------{}------------'.format(dataset_filename))
                # Start the data acquisition systems
                daq.data_capture(True)

                '''
                h) For multiphase units, step the AC test source voltage to Case A from Table 24.
                '''
                if grid is not None:
                    ts.log('Voltage step: setting Grid simulator to case A (IEEE 1547.1-Table 24)')
                    step = 'Step H'
                    q_initial = get_q_initial(daq=daq, step=step)
                    grid.config_asymmetric_phase_angles(mag=mag['case_a'],
                                                        angle=ang['case_a'])
                    q_v_analysis = q_v_criteria(v_pairs=v_pairs[1],
                                                v_target=np.mean(np.array(mag['case_a'])),
                                                MSA_V=MSA_V,
                                                MSA_Q=MSA_Q,
                                                daq=daq,
                                                tr=vv_response_time[vv_curve],
                                                step=step,
                                                q_initial=q_initial)

                    result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                         (q_v_analysis['Q_TR_PF'],
                                          q_v_analysis['TR_PF'],
                                          q_v_analysis['Q_FINAL_PF'],
                                          daq.sc['V_MEAS'],
                                          daq.sc['Q_MEAS'],
                                          daq.sc['Q_TARGET'],
                                          daq.sc['Q_TARGET_MIN'],
                                          daq.sc['Q_TARGET_MAX'],
                                          step,
                                          dataset_filename))

                '''
                w) For multiphase units, step the AC test source voltage to VN.
                '''
                if grid is not None:
                    ts.log('Voltage step: setting Grid simulator voltage to %s' % v_nom)
                    step = 'Step W'
                    q_initial = get_q_initial(daq=daq, step=step)
                    grid.voltage(v_nom)
                    q_v_analysis = q_v_criteria(v_pairs=v_pairs[1],
                                                v_target=v_nom,
                                                MSA_V=MSA_V,
                                                MSA_Q=MSA_Q,
                                                daq=daq,
                                                tr=vv_response_time[vv_curve],
                                                step=step,
                                                q_initial=q_initial)
                    result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                         (q_v_analysis['Q_TR_PF'],
                                          q_v_analysis['TR_PF'],
                                          q_v_analysis['Q_FINAL_PF'],
                                          daq.sc['V_MEAS'],
                                          daq.sc['Q_MEAS'],
                                          daq.sc['Q_TARGET'],
                                          daq.sc['Q_TARGET_MIN'],
                                          daq.sc['Q_TARGET_MAX'],
                                          step,
                                          dataset_filename))

                """
                i) For multiphase units, step the AC test source voltage to Case B from Table 24.
                """
                if grid is not None:
                    ts.log('Voltage step: setting Grid simulator to case B (IEEE 1547.1-Table 24)')
                    step = 'Step I'
                    q_initial = get_q_initial(daq=daq, step=step)
                    grid.config_asymmetric_phase_angles(mag=mag['case_b'],
                                                        angle=ang['case_b'])
                    q_v_analysis = q_v_criteria(v_pairs=v_pairs[1],
                                                v_target=np.mean(np.array(mag['case_b'])),
                                                MSA_V=MSA_V,
                                                MSA_Q=MSA_Q,
                                                daq=daq,
                                                tr=vv_response_time[vv_curve],
                                                step=step,
                                                q_initial=q_initial)
                    result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                         (q_v_analysis['Q_TR_PF'],
                                          q_v_analysis['TR_PF'],
                                          q_v_analysis['Q_FINAL_PF'],
                                          daq.sc['V_MEAS'],
                                          daq.sc['Q_MEAS'],
                                          daq.sc['Q_TARGET'],
                                          daq.sc['Q_TARGET_MIN'],
                                          daq.sc['Q_TARGET_MAX'],
                                          step,
                                          dataset_filename))

                """
                j) For multiphase units, step the AC test source voltage to VN
                """
                if grid is not None:
                    ts.log('Voltage step: setting Grid simulator voltage to %s' % v_nom)
                    step = 'Step J'
                    q_initial = get_q_initial(daq=daq, step=step)
                    grid.voltage(v_nom)
                    q_v_analysis = q_v_criteria(v_pairs=v_pairs[1],
                                                v_target=v_nom,
                                                MSA_V=MSA_V,
                                                MSA_Q=MSA_Q,
                                                daq=daq,
                                                tr=vv_response_time[vv_curve],
                                                step=step,
                                                q_initial=q_initial)
                    result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                         (q_v_analysis['Q_TR_PF'],
                                          q_v_analysis['TR_PF'],
                                          q_v_analysis['Q_FINAL_PF'],
                                          daq.sc['V_MEAS'],
                                          daq.sc['Q_MEAS'],
                                          daq.sc['Q_TARGET'],
                                          daq.sc['Q_TARGET_MIN'],
                                          daq.sc['Q_TARGET_MAX'],
                                          step,
                                          dataset_filename))

                # result params
                result_params = {
                    'plot.title': 'title_name',
                    'plot.x.title': 'Time (sec)',
                    'plot.x.points': 'TIME',
                    'plot.y.points': 'Q_TARGET,Q_MEAS',
                    'plot.y.title': 'Reactive Power (Var)',
                    'plot.y2.points': 'V_TARGET,V_MEAS',
                    'plot.y2.title': 'Voltage (V)',
                    'plot.Q_TARGET.min_error': 'Q_TARGET_MIN',
                    'plot.Q_TARGET.max_error': 'Q_TARGET_MAX',
                }

                ts.log('Sampling complete')
                dataset_filename = dataset_filename + ".csv"
                daq.data_capture(False)
                ds = daq.data_capture_dataset()
                ts.log('Saving file: %s' % dataset_filename)
                ds.to_csv(ts.result_file_path(dataset_filename))
                result_params['plot.title'] = dataset_filename.split('.csv')[0]
                ts.result_file(dataset_filename, params=result_params)
                result = script.RESULT_COMPLETE

    except script.ScriptFail, e:
        reason = str(e)
        if reason:
            ts.log_error(reason)
    finally:
        if daq is not None:
            daq.close()
        if pv is not None:
            if p_rated is not None:
                pv.power_set(p_rated)
            pv.close()
        if grid is not None:
            if v_nom is not None:
                grid.voltage(v_nom)
            grid.close()
        if chil is not None:
            chil.close()
        if eut is not None:
            eut.volt_var(params={'Ena': False})
            eut.volt_watt(params={'Ena': False})
            eut.close()
        if result_summary is not None:
            result_summary.close()

    return result

def test_run():

    result = script.RESULT_FAIL

    try:
        """
        Configuration
        """

        mode = ts.param_value('vv.mode')

        """
        Test Configuration
        """
        # list of active tests
        vv_curves = []
        vv_response_time = [0, 0, 0, 0]

        if mode == 'Vref-test':
            vv_curves['characteristic 1'] = 1
            vv_response_time[1] = ts.param_value('vv.test_1_t_r')
            irr = '100%'
            vref = '100%'
            result = volt_vars_mode_vref_test(vv_curves=vv_curves, vv_response_time=vv_response_time, pwr_lvls=pwr_lvls)

        # Section 5.14.6
        if mode == 'Imbalanced grid':
            if ts.param_value('eut.imbalance_resp') == 'EUT response to the individual phase voltages':
                imbalance_resp = ['INDIVIDUAL_PHASES_VOLTAGES']
            elif ts.param_value('eut.imbalance_resp') == 'EUT response to the average of the three-phase effective (RMS)':
                imbalance_resp = ['AVG_3PH_RMS']
            else:  # 'EUT response to the positive sequence of voltages'
                imbalance_resp = ['POSITIVE_SEQUENCE_VOLTAGES']

            vv_curves.append(1)
            vv_response_time[1] = ts.param_value('vv.test_1_t_r')

            result = volt_var_mode_imbalanced_grid(imbalance_resp=imbalance_resp,
                                                   vv_curves=vv_curves,
                                                   vv_response_time=vv_response_time )

        # Normal volt-var test (Section 5.14.4)
        else:
            irr = ts.param_value('vv.irr')
            vref = ts.param_value('vv.vref')
            if ts.param_value('vv.test_1') == 'Enabled':
                vv_curves.append(1)
                vv_response_time[1] = ts.param_value('vv.test_1_t_r')
            if ts.param_value('vv.test_2') == 'Enabled':
                vv_curves.append(2)
                vv_response_time[2] = ts.param_value('vv.test_2_t_r')
            if ts.param_value('vv.test_3') == 'Enabled':
                vv_curves.append(3)
                vv_response_time[3] = ts.param_value('vv.test_3_t_r')

            # List of power level for tests
            if irr == '20%':
                pwr_lvls = [0.20]
            elif irr == '66%':
                pwr_lvls = [0.66]
            elif irr == '100%':
                pwr_lvls = [1.]
            else:
                pwr_lvls = [1., 0.66, 0.20]

            if vref == '95%':
                v_ref_value = [0.95]
            elif vref == '105%':
                v_ref_value = [1.05]
            elif vref == '100%':
                v_ref_value = [1.]
            else:
                v_ref_value = [1, 0.95, 1.05]

            result = volt_vars_mode(vv_curves=vv_curves, vv_response_time=vv_response_time,
                                    pwr_lvls=pwr_lvls, v_ref_value=v_ref_value)

    except script.ScriptFail, e:
        reason = str(e)
        if reason:
            ts.log_error(reason)

    finally:
        # create result workbook
        excelfile = ts.config_name() + '.xlsx'
        rslt.result_workbook(excelfile, ts.results_dir(), ts.result_dir())
        ts.result_file(excelfile)

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

        # ts.svp_version(required='1.5.3')
        ts.svp_version(required='1.5.8')

        result = test_run()
        ts.log_debug('after test_run')
        ts.result(result)
        if result == script.RESULT_FAIL:
            rc = 1

    except Exception, e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)


info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.1.1')

# VV test parameters
info.param_group('vv', label='Test Parameters')
info.param('vv.mode', label='Volt-Var mode', default='Normal', values=['Normal', 'Vref-test', 'Imbalanced grid'])
info.param('vv.test_1', label='Characteristic 1 curve', default='Enabled', values=['Disabled', 'Enabled'],
           active='vv.mode', active_value=['Normal', 'Imbalanced grid'])
info.param('vv.test_1_t_r', label='Response time (s) for curve 1', default=10.0,
           active='vv.test_1', active_value=['Enabled'])
info.param('vv.test_2', label='Characteristic 2 curve', default='Enabled', values=['Disabled', 'Enabled'],
           active='vv.mode', active_value=['Normal'])
info.param('vv.test_2_t_r', label='Settling time min (t) for curve 2', default=1.0,
           active='vv.test_2', active_value=['Enabled'])
info.param('vv.test_3', label='Characteristic 3 curve', default='Enabled', values=['Disabled', 'Enabled'],
           active='vv.mode', active_value=['Normal'])
info.param('vv.test_3_t_r', label='Settling time max (t) for curve 3', default=90.0,
           active='vv.test_3', active_value=['Enabled'])
info.param('vv.irr', label='Power Levels iteration', default='All', values=['100%', '66%', '20%', 'All'],
           active='vv.mode', active_value=['Normal'])
info.param('vv.vref', label='Voltage reference iteration', default='All', values=['100%', '95%', '105%', 'All'],
           active='vv.mode', active_value=['Normal'])
info.param('vv.imbalance_fix', label='Use minimum fix requirements from table 24 ?',
           default='No', values=['Yes', 'No'], active='vv.mode', active_value=['Imbalanced grid'])

# EUT general parameters
info.param_group('eut', label='EUT Parameters', glob=True)
info.param('eut.phases', label='Phases', default='Single Phase', values=['Single phase', 'Split phase', 'Three phase'])
info.param('eut.s_rated', label='Apparent power rating (VA)', default=10000.0)
info.param('eut.p_rated', label='Output power rating (W)', default=8000.0)
info.param('eut.p_min', label='Minimum Power Rating(W)', default=1000.)
info.param('eut.var_rated', label='Output var rating (vars)', default=2000.0)
info.param('eut.v_nom', label='Nominal AC voltage (V)', default=120.0, desc='Nominal voltage for the AC simulator.')
info.param('eut.v_low', label='Minimum AC voltage (V)', default=116.0)
info.param('eut.v_high', label='Maximum AC voltage (V)', default=132.0)
info.param('eut.v_in_nom', label='V_in_nom: Nominal input voltage (Vdc)', default=400)

info.param('eut.imbalance_resp', label='EUT response to phase imbalance is calculated by:',
           default='EUT response to the average of the three-phase effective (RMS)',
           values=['EUT response to the individual phase voltages',
                   'EUT response to the average of the three-phase effective (RMS)',
                   'EUT response to the positive sequence of voltages'])

# Add the SIRFN logo
info.logo('sirfn.png')
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
