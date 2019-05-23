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
import cmath

def interpolation_v_p(value, v_pairs, pwr_lvl):
    """
    Interpolation function to find the target reactive power based on a 2 point VW curve

    :param value: voltage point for the interpolation
    :param v: VW voltage points
    :param p: VW active power points
    :return: target reactive power
    """
    #ts.log("%s, %s" %(value, v_pairs))
    if value <= v_pairs['V1']:
        p_value = v_pairs['P1']
    elif value < v_pairs['V2']:
        p_value = v_pairs['P1'] + ((v_pairs['P2'] - v_pairs['P1'])/(v_pairs['V2'] - v_pairs['V1']) * (value-v_pairs['V1']))
    else:
        p_value = v_pairs['P2']

    p_value *= pwr_lvl

    return round(float(p_value),2)


def v_p_criteria(v_pairs, v_target, a_v, p_mra, daq, tr, step, p_initial, pwr_lvl=1.0):
    """
    Determine Q(MSAs)
    :param v_pairs:     Voltage point for the interpolation
    :param v_target:     Voltage point for the interpolation
    :param a_v:         Manufacturer's mininum requirement accuracy of voltage
    :param p_mra:       Manufacturer's minimum requirement accuracy of active power
    :param daq:         data acquisition object in order to manipulated
    :param tr:          response time (s)
    :param step:        test procedure step letter or number (e.g "Step G")
    :param p_initial:   dictionnary with timestamp and active power value before step change
    :param pwr_lvl:     The test power level (0.2 , 0.66 or 1 )
    :return:            dictionnary v_p_analysis that contains :
                        passfail of response time requirements ( v_p_analysis['TR_PF'])
                        passfail of P(TR) test result accuracy requirements ( v_p_analysis['P_TR_PF'])
                        passfail of test result accuracy requirements (v_p_analysis['P_FINAL_PF'] )
    """
    tr_analysis = 'start'
    result_analysis = 'start'
    v_p_analysis = {}

    """
    Every time a parameter is stepped or ramped, 
    measure and record the time domain current and 
    voltage response for at least 4 times the maximum 
    expected response time after the stimulus, and measure or derive, 
    active power, apparent power, reactive power, and power factor.

    This is only for the response time requirements (5.14.3.3 Criteria)
    """
    first_tr = p_initial['timestamp'] + timedelta(seconds=tr)
    four_times_tr = p_initial['timestamp'] + timedelta(seconds=4 * tr)
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
                daq.sc['P_MEAS'] = measurement_total(data=data, type_meas='P', log=False)
                # The variable q_tr is the value use to verify the time response requirement.
                v_tr = daq.sc['V_MEAS']
                p_tr = daq.sc['P_MEAS']
                daq.sc['P_TARGET'] = interpolation_v_p(daq.sc['V_MEAS'], v_pairs, pwr_lvl)
                daq.sc['P_TARGET_MIN'] = interpolation_v_p(daq.sc['V_MEAS'] + a_v, v_pairs, pwr_lvl) - p_mra
                daq.sc['P_TARGET_MAX'] = interpolation_v_p(daq.sc['V_MEAS'] - a_v, v_pairs, pwr_lvl) + p_mra
                daq.data_sample()
                ts.log('        P(Tr) actual, min, max: %s, %s, %s' % (daq.sc['P_MEAS'], daq.sc['P_TARGET_MIN'], daq.sc['P_TARGET_MAX']))
                daq.sc['event'] = "{}_tr_1".format(step)
                daq.data_sample()
                if daq.sc['P_TARGET_MIN'] <= daq.sc['P_MEAS'] <= daq.sc['P_TARGET_MAX']:
                    v_p_analysis['P_TR_PF'] = 'Pass'
                else:
                    v_p_analysis['P_TR_PF'] = 'Fail'
                # This is to get out of the while loop. It provides the timestamp of tr_1
                tr_analysis = now
                v_p_analysis['tr_analysis'] = tr_analysis

        while result_analysis == 'start':
            time_to_sleep = four_times_tr - datetime.now()
            ts.sleep(time_to_sleep.total_seconds())
            now = datetime.now()
            if four_times_tr <= now:
                daq.data_sample()
                data = daq.data_capture_read()
                daq.sc['V_MEAS'] = measurement_total(data=data, type_meas='V', log=True)
                daq.sc['P_MEAS'] = measurement_total(data=data, type_meas='P', log=True)
                daq.sc['event'] = "{}_tr_4".format(step)
                # To calculate the min/max, you need the measured value
                # reactive power target from the lower voltage limit
                daq.sc['P_TARGET_MIN'] = interpolation_v_p(daq.sc['V_MEAS'] + a_v, v_pairs, pwr_lvl)- p_mra
                daq.sc['P_TARGET_MAX'] = interpolation_v_p(daq.sc['V_MEAS'] - a_v, v_pairs, pwr_lvl) + p_mra
                daq.data_sample()
                ts.log('        P actual, min, max: %s, %s, %s' % (daq.sc['P_MEAS'], daq.sc['P_TARGET_MIN'], daq.sc['P_TARGET_MAX']))
                """
                The variable p_tr is the value use to verify the time response requirement.
                |----------|----------|----------|----------|
                           1st tr     2nd tr     3rd tr     4th tr            
                |          |                                |
                p_initial  p_tr                             p_final    

                (1547.1)After each voltage, the open loop response time, Tr , is evaluated. 
                The expected active power output, P(Tr) ,
                at one times the open loop response time , 
                is calculated as 90% x (P_final - P_initial ) + P_initial
                """

                v_p_analysis['P_INITIAL'] = p_initial['value']
                v_p_analysis['P_FINAL'] = daq.sc['P_MEAS']
                p_tr_diff = v_p_analysis['P_FINAL'] - v_p_analysis['P_INITIAL']
                p_tr_target = ((0.9 * p_tr_diff) + v_p_analysis['P_INITIAL'])
                # This q_tr_diff < 0 has been added to tackle when Q_final - Q_initial is negative.
                if p_tr_diff < 0:
                    if p_tr <= p_tr_target:
                        v_p_analysis['TR_PF'] = 'Pass'
                    else:
                        v_p_analysis['TR_PF'] = 'Fail'
                elif p_tr_diff >= 0:
                    if p_tr >= p_tr_target:
                        v_p_analysis['TR_PF'] = 'Pass'
                    else:
                        v_p_analysis['TR_PF'] = 'Fail'

                if daq.sc['P_TARGET_MIN'] <= daq.sc['P_MEAS'] <= daq.sc['P_TARGET_MAX']:
                    v_p_analysis['P_FINAL_PF'] = 'Pass'
                else:
                    v_p_analysis['P_FINAL_PF'] = 'Fail'
                ts.log('        P_TR Passfail: %s' % (v_p_analysis['P_TR_PF']))
                ts.log('        TR Passfail: %s' % (v_p_analysis['TR_PF']))
                ts.log('        P_FINAL Passfail: %s' % (v_p_analysis['P_FINAL_PF']))

                # This is to get out of the while loop. It provides the timestamp of tr_4
                result_analysis = now
                v_p_analysis['result_analysis'] = result_analysis


    except:
        daq.sc['V_MEAS'] = 'No Data'
        daq.sc['P_MEAS'] = 'No Data'
        daq.sc['Q_MEAS'] = 'No Data'
        passfail = 'Fail'
        daq.sc['P_TARGET_MIN'] = 'No Data'
        daq.sc['P_TARGET_MAX'] = 'No Data'

    return v_p_analysis


def get_p_initial(daq, step):
    """
    Sum the EUT reactive power from all phases
    :param daq:         data acquisition object in order to manipulated
    :param step:        test procedure step letter or number (e.g "Step G")
    :return: returns a dictionnary with the timestamp, event and total EUT active power
    """
    # TODO : In a more sophisticated approach, p_initial['timestamp'] will come from a reliable secure thread or data acquisition timestamp
    q_initial = {}
    q_initial['timestamp'] = datetime.now()
    daq.data_sample()
    data = daq.data_capture_read()
    daq.sc['event'] = step
    daq.sc['P_MEAS'] = measurement_total(data=data, type_meas='P', log=True)
    daq.data_sample()
    q_initial['value'] = daq.sc['P_MEAS']
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
        meas_label = [meas_root + '_1']
    elif phases == 'Split phase':
        meas_label = [meas_root + '_1', meas_root + '_2']
    elif phases == 'Three phase':
        meas_label = [meas_root + '_1', meas_root + '_2', meas_root + '_3']

    return meas_label


def measurement_total(data, type_meas, log):
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
            ts.log_debug('        %s are: %s' % (get_measurement_label(type_meas), value))
        nb_phases = 1

    elif phases == 'Split phase':
        value1 = data.get(get_measurement_label(type_meas)[0])
        value2 = data.get(get_measurement_label(type_meas)[1])
        if log:
            ts.log_debug('        %s are: %s, %s' % (get_measurement_label(type_meas), value1, value2))
        value = value1 + value2
        nb_phases = 2

    elif phases == 'Three phase':
        value1 = data.get(get_measurement_label(type_meas)[0])
        value2 = data.get(get_measurement_label(type_meas)[1])
        value3 = data.get(get_measurement_label(type_meas)[2])
        if log:
            ts.log_debug('        %s are: %s, %s, %s' % (get_measurement_label(type_meas), value1, value2, value3))
        value = value1 + value2 + value3
        nb_phases = 3

    else:
        ts.log_error('Inverter phase parameter not set correctly.')
        ts.log_error('phases=%s' % phases)
        raise

    if type_meas == 'V':
        # average value of V
        value = value / nb_phases

    elif type_meas == 'P':
        return abs(value)

    return value

def volt_watt_mode(vw_curves, vw_response_time, pwr_lvls):

    result = script.RESULT_FAIL
    daq = None
    data = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None

    try:

        p_rated = ts.param_value('eut.p_rated')
        s_rated = ts.param_value('eut.s_rated')

        # DC voltages
        v_nom_in = ts.param_value('eut.v_in_nom')
        v_min_in = ts.param_value('eut.v_in_min')
        v_max_in = ts.param_value('eut.v_in_max')

        # AC voltages
        v_nom = ts.param_value('eut.v_nom')
        v_min = ts.param_value('eut.v_low')
        v_max = ts.param_value('eut.v_high')
        p_min = ts.param_value('eut.p_min')
        phases = ts.param_value('eut.phases')

        # EUI Absorb capabilities
        absorb_enable = ts.param_value('eut_vw.sink_power')
        p_rated_prime = ts.param_value('eut_vw.p_rated_prime')
        p_min_prime = ts.param_value('eut_vw.p_min_prime')

        # Pass/fail accuracies
        pf_msa = ts.param_value('eut.pf_msa')
        # According to Table 3-Minimum requirements for manufacturers stated measured and calculated accuracy
        MSA_Q = 0.05 * s_rated
        MSA_P = 0.05 * s_rated
        MSA_V = 0.01 * v_nom
        a_v = 1.5 * MSA_V
        p_mra = 1.5 * MSA_P

        '''
        a) Connect the EUT according to the instructions and specifications provided by the manufacturer.
        '''
        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()


        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts)
        pv.power_set(p_rated)
        pv.power_on()  # Turn on DC so the EUT can be initialized

        # DAS soft channels
        das_points = {'sc': ('P_TARGET', 'P_TARGET_MIN', 'P_TARGET_MAX', 'P_MEAS', 'V_TARGET','V_MEAS','event')}

        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])
        daq.sc['P_TARGET'] = 100
        daq.sc['P_TARGET_MIN'] = 100
        daq.sc['P_TARGET_MAX'] = 100
        daq.sc['V_TARGET'] = v_nom
        daq.sc['event'] = 'None'

        ts.log('DAS device: %s' % daq.info())

        '''
        b) Set all voltage trip parameters to the widest range of adjustability. Disable all reactive/active power
        control functions.
        '''
        eut = der.der_init(ts)
        if eut is not None:
            eut.config()
            ts.log_debug(eut.measurements())
            ts.log_debug(
                'L/HVRT and trip parameters set to the widest range : v_min:{0} V, v_max:{1} V'.format(v_min, v_max))
            eut.vrt_stay_connected_high(
                params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000, 'V1': v_max, 'Tms2': 0.16, 'V2': v_max})
            eut.vrt_stay_connected_low(
                params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000, 'V1': v_min, 'Tms2': 0.16, 'V2': v_min})
        else:
            ts.log_debug('Set L/HVRT and trip parameters to the widest range of adjustability possible.')

        '''
        c) Set all AC test source parameters to the nominal operating voltage and frequency.
        '''
        # grid simulator is initialized with test parameters and enabled
        grid = gridsim.gridsim_init(ts)  # Turn on AC so the EUT can be initialized
        if grid is not None:
            grid.voltage(v_nom)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)

        result_summary.write('P_TR_ACC_REQ,TR_REQ,P_FINAL_ACC_REQ,V_MEAS,P_MEAS,P_TARGET,P_TARGET_MIN,P_TARGET_MAX,STEP,FILENAME\n')


        '''
        d) Adjust the EUT's available active power to Prated. For an EUT with an input voltage range, set the input
        voltage to Vin_nom. The EUT may limit active power throughout the test to meet reactive power requirements.
        For an EUT with an input voltage range.
        '''

        if pv is not None:
            pv.iv_curve_config(pmp=p_rated, vmp=v_nom_in)
            pv.irradiance_set(1000.)

        v_pairs = collections.OrderedDict()#{}

        v_pairs[1] = {'V1': round(1.06 * v_nom, 2),
                      'V2': round(1.10 * v_nom, 2),
                      'P1': round(p_rated, 2)}

        v_pairs[2] = {'V1': round(1.05 * v_nom, 2),
                      'V2': round(1.10 * v_nom, 2),
                      'P1': round(p_rated, 2)}

        v_pairs[3] = {'V1': round(1.09 * v_nom, 2),
                      'V2': round(1.10 * v_nom, 2),
                      'P1': round(p_rated, 2)}

        if absorb_enable == 'Yes':

            v_pairs[1].add('P2', 0)
            v_pairs[2].add('P2', p_rated_prime)
            v_pairs[3].add('P2', p_rated_prime)

        else:

            if p_min > (0.2 * p_rated):
                v_pairs[1]['P2'] = int(0.2 * p_rated)
                v_pairs[2]['P2'] = int(0.2 * p_rated)
                v_pairs[3]['P2'] = int(0.2 * p_rated)
            else:
                v_pairs[1]['P2'] = int(p_min)
                v_pairs[2]['P2'] = int(p_min)
                v_pairs[3]['P2'] = int(p_min)


        '''
        g) Begin the adjustment towards V_h. Step the AC test source voltage to a_v below V_1.
        t) Repeat steps d) through t) at EUT power set at 20% and 66% of rated power.
        u) Repeat steps d) through u) for characteristics 2 and 3.
        v) Test may be repeated for EUT's that can also absorb power using the P' values in the characteristic definition.
        '''

        """
        Test start
        """
        for vw_curve in vw_curves:

            ts.log('Starting test with VW mode - Characteristic %s' % (vw_curve))

            '''
            e) Set EUT volt-watt parameters to the values specified by Characteristic 1. All other function be turned off.
            f) Verify volt-watt mode is reported as active and that the correct characteristic is reported.
            '''
            if eut is not None:
                vw_curve_params = {'v': [v_pairs[vw_curve]['V1'], v_pairs[vw_curve]['V2']],
                                   'w': [v_pairs[vw_curve]['P1'], v_pairs[vw_curve]['P2']],
                                   'DeptRef': 'W_MAX_PCT'}
                vw_params = {'Ena': True, 'ActCrv': 1, 'curve': vw_curve_params}
                eut.volt_watt(params=vw_params)
                ts.log_debug('Initial EUT VW settings are %s' % eut.volt_watt())

            v_steps_dict = collections.OrderedDict()

            # 1547.1 steps :
            # STD_CHANGE: When V2 >= VH, some steps should be skipped. k) If V2 is less than VH, step the
            #  AC test source voltage to av above V2 , else skip to step o).
            v_steps_dict["Step G"] = v_pairs[vw_curve]['V1'] - a_v
            v_steps_dict["Step H"] = v_pairs[vw_curve]['V1'] + a_v
            v_steps_dict["Step I"] = (v_pairs[vw_curve]['V2'] + v_pairs[vw_curve]['V1']) / 2
            v_steps_dict["Step J"] = v_pairs[vw_curve]['V2'] - a_v
            if v_pairs[vw_curve]['V2'] < v_max:
                v_steps_dict["Step K"] = v_pairs[vw_curve]['V2'] + a_v
                v_steps_dict["Step L"] = v_max - a_v
                v_steps_dict["Step M"] = v_pairs[vw_curve]['V2'] + a_v
                v_steps_dict["Step N"] = v_pairs[vw_curve]['V2'] - a_v
            v_steps_dict["Step O"] = (v_pairs[vw_curve]['V1'] + v_pairs[vw_curve]['V2']) / 2
            v_steps_dict["Step P"] = v_pairs[vw_curve]['V1'] + a_v
            v_steps_dict["Step Q"] = v_pairs[vw_curve]['V1'] - a_v
            # STD_CHANGE: Duplicated step R. Step R was changed for v_min + a_v
            v_steps_dict["Step R"] = v_min + a_v
            # STD_CHANGE: Duplicated step R. Step S was changed for v_nom
            v_steps_dict["Step S"] = v_nom
            
            # This is to make sure the volatge step don't exceed the
            # EUT boundaries and to round the number to 2 decimals
            for step, voltage in v_steps_dict.iteritems():
                v_steps_dict.update({step : np.around(voltage,2)})
                if voltage > v_max:
                    ts.log("{0} voltage step (value : {1}) changed to VH (v_max)".format(step, voltage))
                    v_steps_dict.update({step : v_max})
                elif voltage < v_min:
                    ts.log("{0} voltage step (value : {1}) changed to VL (v_min)".format(step, voltage))
                    v_steps_dict.update({step: v_min})

            for power in pwr_lvls:
                if pv is not None:
                    pv_power_setting = (p_rated * power)
                    pv.iv_curve_config(pmp=pv_power_setting, vmp=v_nom_in)
                    pv.irradiance_set(1000.)                
                
                ts.log_debug('curve points:  %s' % v_pairs[vw_curve])

                # Configure the data acquisition system
                ts.log('Starting data capture for power = %s' % power)
                dataset_filename = ('VW_{0}_PWR_{1}'.format(vw_curve, power))
                ts.log('------------{}------------'.format(dataset_filename))
                daq.data_capture(True)

                for step_label, v_step in v_steps_dict.iteritems():
                    ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_step,step_label))
                    p_initial = get_p_initial(daq=daq, step=step_label)
                    grid.voltage(v_step)
                    v_p_analysis = v_p_criteria(v_pairs=v_pairs[vw_curve],
                                                v_target=v_step,
                                                a_v=a_v,
                                                p_mra=p_mra,
                                                daq=daq,
                                                tr=vw_response_time[vw_curve],
                                                step=step_label,
                                                p_initial=p_initial,
                                                pwr_lvl=power)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (v_p_analysis['P_TR_PF'], v_p_analysis['TR_PF'],v_p_analysis['P_FINAL_PF'],
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'],daq.sc['P_TARGET'],daq.sc['P_TARGET_MIN'],
                                          daq.sc['P_TARGET_MAX'],step_label,dataset_filename))



                # result params
                result_params = {
                    'plot.title': 'title_name',
                    'plot.x.title': 'Time (sec)',
                    'plot.x.points': 'TIME',
                    'plot.y.points': 'P_TARGET,P_MEAS',
                    'plot.y.title': 'Active Power (W)',
                    'plot.y2.points': 'V_TARGET,V_MEAS',
                    'plot.y2.title': 'Voltage (V)',
                    'plot.P_TARGET.min_error': 'P_TARGET_MIN',
                    'plot.P_TARGET.max_error': 'P_TARGET_MAX',
                }
                # create result workbook

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
            eut.volt_watt(params={'Ena': False, 'ActCrv': 0})
            eut.close()
        if result_summary is not None:
            result_summary.close()


def volt_watt_mode_imbalanced_grid(imbalance_resp, vw_curves, vw_response_time):

    result = script.RESULT_FAIL
    daq = None
    data = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None

    try:


        cat = ts.param_value('eut.cat')
        cat2 = ts.param_value('eut.cat2')
        p_rated = ts.param_value('eut.p_rated')
        s_rated = ts.param_value('eut.s_rated')

        # DC voltages
        v_in_nom = ts.param_value('eut.v_in_nom')

        # AC voltages
        v_nom = ts.param_value('eut.v_nom')
        v_min = ts.param_value('eut.v_low')
        v_max = ts.param_value('eut.v_high')
        p_min = ts.param_value('eut.p_min')
        phases = ts.param_value('eut.phases')

        # EUI Absorb capabilities
        absorb_enable = ts.param_value('eut_vw.sink_power')
        p_rated_prime = ts.param_value('eut_vw.p_rated_prime')
        p_min_prime = ts.param_value('eut_vw.p_min_prime')


        # Pass/fail accuracies
        # According to Table 3-Minimum requirements for manufacturers stated measured and calculated accuracy
        MSA_Q = 0.05 * s_rated
        MSA_P = 0.05 * s_rated
        MSA_V = 0.01 * v_nom
        a_v = 1.5 * MSA_V
        p_mra = 1.5 * MSA_P

        # Imbalance configuration
        '''
                                            Table 24 - Imbalanced Voltage Test Cases

                +-----------------------------------------------------+-----------------------------------------------+
                | Phase A (p.u.)  | Phase B (p.u.)  | Phase C (p.u.)  | In order to keep V0 magnitude                 |
                |                 |                 |                 | and angle at 0. These parameter can be use.   |
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
        imbalance_fix = ts.param_value('vw.imbalance_fix')
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
        if pv is not None:
            pv.power_set(p_rated)
            pv.power_on()  # Turn on DC so the EUT can be initialized

        # DAS soft channels
        das_points = {'sc': ('P_TARGET', 'P_TARGET_MIN', 'P_TARGET_MAX', 'P_MEAS', 'V_TARGET', 'V_MEAS', 'event')}

        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])
        daq.sc['P_TARGET'] = 100
        daq.sc['P_TARGET_MIN'] = 100
        daq.sc['P_TARGET_MAX'] = 100
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

        result_summary.write('P_TR_ACC_REQ,TR_REQ,P_FINAL_ACC_REQ,V_MEAS,P_MEAS,P_TARGET,P_TARGET_MIN,P_TARGET_MAX,STEP,FILENAME\n')


        '''
         d) Adjust the EUT's available active power to Prated. For an EUT with an input voltage range, set the input
        voltage to Vin_nom.
        '''

        if pv is not None:
            pv.iv_curve_config(pmp=p_rated, vmp=v_in_nom)
            pv.irradiance_set(1000.)

        for imbalance_response in imbalance_resp:
            for vw_curve in vw_curves:
                '''
                e) Set EUT volt-watt parameters to the values specified by Characteristic 1. All other function be turned off.
                '''

                v_pairs = collections.OrderedDict()  # {}

                v_pairs[vw_curve] = {'V1': round(1.06 * v_nom, 2),
                                     'V2': round(1.10 * v_nom, 2),
                                     'P1': round(p_rated, 2)}

                if absorb_enable == 'Yes':
                    v_pairs[vw_curve]['P2'] = 0

                else:
                    if p_min > (0.2 * p_rated):
                        v_pairs[vw_curve]['P2'] = int(0.2 * p_rated)
                    else:
                        v_pairs[vw_curve]['P2'] = int(p_min)

                # it is assumed the EUT is on
                eut = der.der_init(ts)
                if eut is not None:
                    vw_curve_params = {'v': [v_pairs[vw_curve]['V1'], v_pairs[vw_curve]['V2']],
                                       'w': [v_pairs[vw_curve]['P1'], v_pairs[vw_curve]['P2']],
                                       'DeptRef': 'W_MAX_PCT'}
                    vw_params = {'Ena': True, 'ActCrv': 1, 'curve': vw_curve_params}
                    '''
                    f) Verify volt-watt mode is reported as active and that the correct characteristic is reported
                    '''
                    eut.volt_watt(params=vw_params)
                    # eut.volt_var(params={'Ena': True})
                    ts.log_debug('Initial EUT VW settings are %s' % eut.volt_watt())
                    ts.log_debug('curve points:  %s' % v_pairs[vw_curve])

                    # STD_CHANGE: Remove step g) or add more information about the volt-var configuration.
                    '''
                    g) Verify volt-var mode is reported as active and that the correct characteristic is reported.
                    '''
                    #eut.volt_var(params=vw_params)


                '''
                h) Once steady state is reached, begin the adjustment of phase voltages.
                '''

                """
                Test start
                """
                step = 'Step H'
                daq.sc['event'] = step
                daq.data_sample()
                ts.log('Wait for steady state to be reached')
                ts.sleep(4 * vw_response_time[vw_curve])
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
                Step i) For multiphase units, step the AC test source voltage to Case A from Table 24
                '''

                if grid is not None:
                    step = 'Step I'
                    ts.log('Voltage step: setting Grid simulator to case A (IEEE 1547.1-Table 24)(%s)' % step)
                    p_initial = get_p_initial(daq=daq, step=step)
                    grid.config_asymmetric_phase_angles(mag=mag['case_a'],
                                                        angle=ang['case_a'])
                    v_p_analysis = v_p_criteria(v_pairs=v_pairs[1],
                                                v_target=np.mean(np.array(mag['case_a'])),
                                                a_v=a_v,
                                                p_mra=p_mra,
                                                daq=daq,
                                                tr=vw_response_time[vw_curve],
                                                step=step,
                                                p_initial=p_initial)

                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (v_p_analysis['P_TR_PF'], v_p_analysis['TR_PF'], v_p_analysis['P_FINAL_PF'],
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], daq.sc['P_TARGET'], daq.sc['P_TARGET_MIN'],
                                          daq.sc['P_TARGET_MAX'], step, dataset_filename))


                '''
                Step j) For multiphase units, step the AC test source voltage to VN.
                '''
                if grid is not None:
                    step = 'Step J'
                    ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_nom, step))
                    p_initial = get_p_initial(daq=daq, step=step)
                    grid.voltage(v_nom)
                    v_p_analysis = v_p_criteria(v_pairs=v_pairs[1],
                                                v_target=v_nom,
                                                a_v=a_v,
                                                p_mra=p_mra,
                                                daq=daq,
                                                tr=vw_response_time[vw_curve],
                                                step=step,
                                                p_initial=p_initial)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (v_p_analysis['P_TR_PF'], v_p_analysis['TR_PF'], v_p_analysis['P_FINAL_PF'],
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], daq.sc['P_TARGET'], daq.sc['P_TARGET_MIN'],
                                          daq.sc['P_TARGET_MAX'], step, dataset_filename))

                '''
                Step k) For multiphase units, step the AC test source voltage to Case B from Table 24
                '''

                if grid is not None:
                    step = 'Step K'
                    ts.log('Voltage step: setting Grid simulator to case B (IEEE 1547.1-Table 24)(%s)' % step)
                    p_initial = get_p_initial(daq=daq, step=step)
                    grid.config_asymmetric_phase_angles(mag=mag['case_b'],
                                                        angle=ang['case_b'])
                    v_p_analysis = v_p_criteria(v_pairs=v_pairs[1],
                                                v_target=np.mean(np.array(mag['case_b'])),
                                                a_v=a_v,
                                                p_mra=p_mra,
                                                daq=daq,
                                                tr=vw_response_time[vw_curve],
                                                step=step,
                                                p_initial=p_initial)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (v_p_analysis['P_TR_PF'], v_p_analysis['TR_PF'], v_p_analysis['P_FINAL_PF'],
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], daq.sc['P_TARGET'], daq.sc['P_TARGET_MIN'],
                                          daq.sc['P_TARGET_MAX'], step, dataset_filename))

                '''
                Step l) For multiphase units, step the AC test source voltage to VN.
                '''
                if grid is not None:
                    step = 'Step L'
                    ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_nom, step))
                    p_initial = get_p_initial(daq=daq, step=step)
                    grid.voltage(v_nom)
                    v_p_analysis = v_p_criteria(v_pairs=v_pairs[1],
                                                v_target=v_nom,
                                                a_v=a_v,
                                                p_mra=p_mra,
                                                daq=daq,
                                                tr=vw_response_time[vw_curve],
                                                step=step,
                                                p_initial=p_initial)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (v_p_analysis['P_TR_PF'], v_p_analysis['TR_PF'], v_p_analysis['P_FINAL_PF'],
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], daq.sc['P_TARGET'], daq.sc['P_TARGET_MIN'],
                                          daq.sc['P_TARGET_MAX'], step, dataset_filename))

                # result params
                result_params = {
                    'plot.title': 'title_name',
                    'plot.x.title': 'Time (sec)',
                    'plot.x.points': 'TIME',
                    'plot.y.points': 'P_TARGET,P_MEAS',
                    'plot.y.title': 'Active Power (W)',
                    'plot.y2.points': 'V_TARGET,V_MEAS',
                    'plot.y2.title': 'Voltage (V)',
                    'plot.P_TARGET.min_error': 'P_TARGET_MIN',
                    'plot.P_TARGET.max_error': 'P_TARGET_MAX',
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

        # Initiliaze VW EUT specified parameters variables
        mode = ts.param_value('vw.mode')
        irr = ts.param_value('vw.irr')

        """
        Test Configuration
        """
        # list of active tests
        vw_curves = []
        imbalance_resp = []
        vw_response_time = [0,0,0,0]
        if mode == 'Imbalanced grid':
            if ts.param_value('eut.imbalance_resp_1') == 'Enabled':
                imbalance_resp.append('INDIVIDUAL_PHASES_VOLTAGES')
            if ts.param_value('eut.imbalance_resp_2') == 'Enabled':
                imbalance_resp.append('AVG_3PH_RMS')
            if ts.param_value('eut.imbalance_resp_3') == 'Enabled':
                imbalance_resp.append('POSITIVE_SEQUENCE_VOLTAGES')
            vw_curves.append(1)
            vw_response_time[1] = float(ts.param_value('vw.test_1_tr'))

        else:
            irr = ts.param_value('vw.irr')
            if ts.param_value('vw.test_1') == 'Enabled':
                vw_curves.append(1)
                vw_response_time[1] = float(ts.param_value('vw.test_1_tr'))
            if ts.param_value('vw.test_2') == 'Enabled':
                vw_curves.append(2)
                vw_response_time[2]=float(ts.param_value('vw.test_2_tr'))
            if ts.param_value('vw.test_3') == 'Enabled':
                vw_curves.append(3)
                vw_response_time[3]=float(ts.param_value('vw.test_3_tr'))
        #List of power level for tests
        irr = ts.param_value('vw.power_lvl')
        if irr == '20%':
            pwr_lvls = [0.20]
        elif irr == '66%':
            pwr_lvls = [0.66]
        elif irr == '100%':
            pwr_lvls = [1.00]
        else:
            pwr_lvls = [1.00, 0.66, 0.20]

        if mode == 'Imbalanced grid':
            result = volt_watt_mode_imbalanced_grid(imbalance_resp=imbalance_resp,vw_curves=vw_curves, vw_response_time=vw_response_time)
        else:
            result = volt_watt_mode(vw_curves=vw_curves, vw_response_time=vw_response_time, pwr_lvls=pwr_lvls)

        return result

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

        result = test_run()

        ts.result(result)
        if result == script.RESULT_FAIL:
            rc = 1

    except Exception, e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)

info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.1.3')

# VW test parameters
info.param_group('vw', label='Test Parameters')
info.param('vw.mode', label='Volt-Watt mode', default='Normal', values=['Normal', 'Imbalanced grid'])
info.param('vw.test_1', label='Characteristic 1 curve', default='Enabled', values=['Disabled', 'Enabled'],\
           active='vw.mode', active_value=['Normal', 'Imbalanced grid'])
info.param('vw.test_1_tr', label='Response time (s) for curve 1', default=10.0,\
           active='vw.test_1', active_value=['Enabled'])
info.param('vw.test_2', label='Characteristic 2 curve', default='Enabled', values=['Disabled', 'Enabled'],\
           active='vw.mode', active_value=['Normal'])
info.param('vw.test_2_tr', label='Response time (s) for curve 2', default=90.0,\
           active='vw.test_2', active_value=['Enabled'])
info.param('vw.test_3', label='Characteristic 3 curve', default='Enabled', values=['Disabled', 'Enabled'],\
           active='vw.mode', active_value=['Normal'])
info.param('vw.test_3_tr', label='Response time (s) for curve 3', default=0.5,\
           active='vw.test_3', active_value=['Enabled'])
info.param('vw.power_lvl', label='Power Levels', default='All', values=['100%', '66%', '20%', 'All'],\
           active='vw.mode', active_value=['Normal'])
info.param('vw.imbalance_fix', label='Use minimum fix requirements from table 24 ?', \
           default='No', values=['Yes', 'No'], active='vw.mode', active_value=['Imbalanced grid'])

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
info.param('eut.imbalance_resp_1', label='EUT response to the individual phase voltages', default='Disabled',
           values=['Disabled', 'Enabled'])
info.param('eut.imbalance_resp_2', label='EUT response to the average of the three-phase effective (RMS)', default='Enabled',
           values=['Disabled', 'Enabled'])
info.param('eut.imbalance_resp_3', label='EUT response to the positive sequence of voltages', default='Disabled',
           values=['Disabled', 'Enabled'])

# EUT VW parameters
info.param_group('eut_vw', label='VW - EUT Parameters', glob=True)
info.param('eut_vw.sink_power', label='Can DER absorb active power?', default='No',
           values=['No', 'Yes'])
info.param('eut_vw.p_rated_prime', label='P\'rated: Output power rating while absorbing power (W) (negative)',
           default=-3000.0, active='eut_vw.sink_power', active_value=['Yes'])
info.param('eut_vw.p_min_prime', label='P\'min: minimum active power while sinking power(W) (negative)',
           default=-0.2*3000.0, active='eut_vw.sink_power', active_value=['Yes'])



# Add the SIRFN logo
info.logo('sirfn.png')

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
