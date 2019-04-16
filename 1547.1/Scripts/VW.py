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
import script
import math
import numpy as np
import collections
import cmath

def interpolation_v_p(value, v_pairs):
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

    return round(float(p_value),2)

def p_v_criteria(v_pairs, a_v, p_mra, daq, imbalance_resp):
    """
    Determine reactive power target and the min/max q values for pass/fail acceptance based on manufacturer's specified
    accuracies (MSAs)

    :param phases: number of phases of systems
    :param v_value: measured voltage value
    :param a_v: manufacturer's mininum requirement accuracy of voltage
    :param p_mra: manufacturer's minimum requirement accuracy of reactive power
    :param v: VW voltage points (volts)
    :param p: VW reactive power points (W)
    :return: passfail for p(v)
    """

    if imbalance_resp == 'individual phase voltages':
        pass
    elif imbalance_resp == 'average of the three-phase effective (RMS)':
        pass
    else:  # 'the positive sequence of voltages'
        pass

    try:
        daq.sc['V_MEAS'] = measurement_total(data=data, type_meas='V')
        #daq.sc['Q_MEAS'] = measurement_total(data=data, type_meas='Q')
        daq.sc['P_MEAS'] = measurement_total(data=data, type_meas='P')

        #To calculate the min/max, you need the measured value
        daq.sc['P_TARGET_MIN']= interpolation_v_p(daq.sc['V_MEAS'] + a_v, v_pairs)-p_mra  # reactive power target from the lower voltage limit
        daq.sc['P_TARGET_MAX']= interpolation_v_p(daq.sc['V_MEAS'] - a_v, v_pairs)+p_mra  # reactive power target from the upper voltage limit

        ts.log('        P actual, min, max: %s, %s, %s' % (daq.sc['P_MEAS'], daq.sc['P_TARGET_MIN'], daq.sc['P_TARGET_MAX']))

        if daq.sc['P_TARGET_MIN'] <= daq.sc['P_MEAS'] <= daq.sc['P_TARGET_MAX']:
            passfail = 'Pass'
        else:
            passfail = 'Fail'

        ts.log('        P(V) Passfail: %s' % (passfail))

    except:
        daq.sc['V_MEAS'] = 'No Data'
        daq.sc['P_MEAS'] = 'No Data'
        #daq.sc['Q_MEAS'] = 'No Data'
        passfail = 'Fail'
        daq.sc['P_TARGET_MIN'] = 'No Data'
        daq.sc['P_TARGET_MAX'] = 'No Data'

    return passfail

def measurement_total(data, type_meas):
    """
    Sum the EUT reactive power from all phases
    :param data: dataset
    :param phases: number of phases in the EUT
    :param choice: Either V,P or Q
    :return: either total EUT reactive power, total EUT active power or average V
    """
    phases = ts.param_value('eut.phases')
    if type_meas == 'V':
        meas = 'VRMS'
        log_meas = 'Voltages'
    elif type_meas == 'P':
        meas = 'P'
        log_meas = 'Active powers'
    else:
        meas = 'Q'
        log_meas='Reactive powers'

    ts.log_debug('%s' % type_meas)
    ts.log_debug('%s' % log_meas)

    if phases == 'Single phase':
        ts.log_debug('        %s are: %s' % (log_meas, data.get('AC_{}_1'.format(meas))))
        value = data.get('AC_{}_1')
        nb_phases = 1

    elif phases == 'Split phase':
        ts.log_debug('        %s are: %s, %s' % (log_meas, data.get('AC_{}_1'.format(meas)),
                                                    data.get('AC_{}_2'.format(meas))))
        value = data.get('AC_{}_1'.format(meas)) + data.get('AC_{}_2'.format(meas))
        nb_phases = 2

    elif phases == 'Three phase':
        ts.log_debug('        %s are: %s, %s, %s' % (log_meas,
                                                        data.get('AC_{}_1'.format(meas)),
                                                        data.get('AC_{}_2'.format(meas)),
                                                        data.get('AC_{}_3'.format(meas))))
        value = data.get('AC_{}_1'.format(meas)) + data.get('AC_{}_2'.format(meas)) + data.get('AC_{}_3'.format(meas))
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

def volt_watt_mode(vw_curves, t_settling, pwr_lvls):

    result = script.RESULT_FAIL
    daq = None
    data = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None

    try:
        # result params
        result_params = {
            'plot.title': 'title_name',
            'plot.x.title': 'Time (sec)',
            'plot.x.points': 'TIME',
            'plot.y.points': 'V_TARGET,V_MEAS',
            'plot.y.title': 'Voltage (V)',
            'plot.V_TARGET.point': 'True',
            'plot.y2.points': 'P_TARGET,P_MEAS',
            'plot.P_TARGET.point': 'True',
            'plot.P_TARGET.min_error': 'P_TARGET_MIN',
            'plot.P_TARGET.max_error': 'P_TARGET_MAX',
        }

        cat = ts.param_value('eut.cat')
        cat2 = ts.param_value('eut.cat2')
        sink_power = ts.param_value('eut.sink_power')
        p_rated = ts.param_value('eut.p_rated')
        p_rated_prime = ts.param_value('eut.p_rated_prime')
        s_rated = ts.param_value('eut.s_rated')
        eff = {
            1.00: ts.param_value('eut.efficiency_100') / 100,
            0.66: ts.param_value('eut.efficiency_66') / 100,
            0.20: ts.param_value('eut.efficiency_20') / 100
        }
        absorb_enable = ts.param_value('eut.abs_enabled')

        # DC voltages
        v_nom_in = ts.param_value('eut.v_in_nom')
        v_min_in = ts.param_value('eut.v_in_min')
        v_max_in = ts.param_value('eut.v_in_max')

        # AC voltages
        v_nom = ts.param_value('eut.v_nom')
        v_min = ts.param_value('eut.v_low')
        v_max = ts.param_value('eut.v_high')
        p_min = ts.param_value('eut.p_min')
        p_min_prime = ts.param_value('eut.p_min_prime')
        phases = ts.param_value('eut.phases')
        pf_settling_time = ts.param_value('eut.pf_settling_time')
        imbalance_resp = ts.param_value('eut.imbalance_resp')

        # Pass/fail accuracies
        pf_msa = ts.param_value('eut.pf_msa')
        # According to Table 3-Minimum requirements for manufacturers stated measured and calculated accuracy
        MSA_Q = 0.05 * s_rated
        MSA_P = 0.05 * s_rated
        MSA_V = 0.01 * v_nom
        a_v = 1.5 * MSA_V

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
        # it is assumed the EUT is on
        eut = der.der_init(ts)
        if eut is not None:
            vw_curve_params = {'v': [v_start, v_stop], 'w': [100., 0], 'DeptRef': 'W_MAX_PCT'}
            vw_params = {'Ena': True, 'ActCrv': 1, 'curve': vw_curve_params}
            eut.volt_watt(params=vw_params)
            ts.log_debug('Initial EUT VW settings are %s' % eut.volt_watt())
        '''
        c) Set all AC test source parameters to the nominal operating voltage and frequency.
        '''

        if grid is not None:
            grid.voltage(v_nom)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)

        result_summary.write('Result,Test Name,Power Level,Iteration,direction,V_target,V_actual,Power_target,Power_actual,P_min,P_max,Dataset File\n')


        '''
        d) Adjust the EUT's available active power to Prated. For an EUT with an input voltage range, set the input
        voltage to Vin_nom. The EUT may limit active power throughout the test to meet reactive power requirements.
        For an EUT with an input voltage range, repeat steps d) through o) for Vin_min and Vin_max.
        '''

        #if pv is not None:
            # TODO implement IV_curve_config
            #pv.iv_curve_config(pmp=p_rated, vpm=v_nom)
            #pv.iv_curve_config(pmp=p_rated, vpm=v_in)
            #pv.irradiance_set(1000.)
        '''
        e) Set EUT volt-watt parameters to the values specified by Characteristic 1. All other function be turned off.
        '''

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
        f) Verify volt-watt mode is reported as active and that the correct characteristic is reported.
        g) Begin the adjustment towards V_h. Step the AC test source voltage to a_v below V_1.
        t) Repeat steps d) through t) at EUT power set at 20% and 66% of rated power.
        u) Repeat steps d) through u) for characteristics 2 and 3.
        v) Test may be repeated for EUT's that can also absorb power using the P' values in the characteristic definition.
        '''

        """
        Test start
        """
        for test, vw_curve in vw_curves.iteritems():

            ts.log('Starting test with VW mode at %s' % (test))

            v_steps_dict = collections.OrderedDict()

            # 1547.1 :
            v_steps_up = [(v_pairs[vw_curve]['V1'] - a_v),  # step g
                          (v_pairs[vw_curve]['V1'] + a_v),  # step h
                          (v_pairs[vw_curve]['V2'] + v_pairs[vw_curve]['V1']) / 2,  # step i
                          v_pairs[vw_curve]['V2'] - a_v,  # step j
                          v_pairs[vw_curve]['V2'] + a_v,  # step k
                          v_max - a_v]  # step l

            v_steps_down = [v_pairs[vw_curve]['V2'] + a_v,  # step m
                            v_pairs[vw_curve]['V2'] - a_v,  # step n
                            (v_pairs[vw_curve]['V1'] + v_pairs[vw_curve]['V2']) / 2,  # step o
                            v_pairs[vw_curve]['V1'] + a_v,  # step p
                            v_pairs[vw_curve]['V1'] - a_v,  # step q
                            v_min + a_v]  # step s

            for i in range(len(v_steps_up)):
                if v_steps_up[i] > v_max:
                    v_steps_up[i] = v_max
                elif v_steps_up[i] < v_min:
                    v_steps_up[i] = v_min
            for i in range(len(v_steps_down)):
                if v_steps_down[i] > v_max:
                    v_steps_down[i] = v_max
                elif v_steps_down[i] < v_min:
                    v_steps_down[i] = v_min

            v_steps_dict['up'] = np.around(v_steps_up, decimals=2)
            v_steps_dict['down'] = np.around(v_steps_down, decimals=2)
            ts.log('Testing VW function at the following voltage(up) points %s' % v_steps_dict['up'])
            ts.log('Testing VW function at the following voltage(down) points %s' % v_steps_dict['down'])

            for power in pwr_lvls:
                if pv is not None:
                    # TODO implement IV_curve_config
                    pv.power_set(power)
                    #pv_power_setting = (p_rated * power) / eff[power]
                    #pv.iv_curve_config(pmp=pv_power_setting, vpm=v_in)
                    #pv.irradiance_set(1000.)
                    #ts.log('Set PV simulator power to {} with efficiency at {} %'.format(p_rated * power, eff[power] * 100.))



                ts.log_debug('curve points:  %s' % v_pairs[vw_curve])

                # Configure the data acquisition system
                ts.log('Starting data capture for power = %s' % power)
                dataset_filename = 'VW_curve_%s_pwr_%0.2f.csv' % (vw_curve, power)
                daq.data_capture(True)

                for direction, v_steps in v_steps_dict.iteritems():
                    for v_step in v_steps:

                        ts.log('        Recording power at voltage %0.2f V for 4*t_settling = %0.1f sec.' %
                               (v_step, 4 * t_settling[vw_curve]))
                        daq.sc['V_TARGET'] = v_step
                        daq.sc['event'] = 'v_step_{}'.format(direction)

                        p_targ = interpolation_v_p(value=v_step,
                                                   v_pairs=v_pairs[vw_curve])

                        grid.voltage(v_step)
                        for i in range(4):
                            daq.sc['event'] = 'v_step_{}'.format(direction)
                            ts.sleep(1 * t_settling[vw_curve])
                            daq.sc['event'] = 'TR_{}_done'.format(i + 1)
                            daq.data_sample()
                            data = daq.data_capture_read()

                        daq.sc['P_TARGET'] = p_targ

                        # Test result accuracy requirements per IEEE1547-4.2 for Q(V)
                        P_V_passfail = p_v_criteria(v_pairs=v_pairs[vw_curve], a_v=a_v, p_mra=MSA_P, daq=daq,
                                                    imbalance_resp=imbalance_resp)
                                                   #data=data)

                        # Test result accuracy requirements per IEEE1547-4.2 for Q(tr)
                        # TODO p_tr_criteria still needs to be implemented

                        ts.log('        Powers targ, min, max: %s, %s, %s' % (
                        daq.sc['P_TARGET'], daq.sc['P_TARGET_MIN'], daq.sc['P_TARGET_MAX']))

                        daq.sc['event'] = 'T_settling_done_{}'.format(direction)
                        daq.data_sample()



            result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                 (P_V_passfail,
                                  ts.config_name(),
                                  power * 100.,
                                  direction,
                                  daq.sc['V_TARGET'],
                                  daq.sc['V_MEAS'],
                                  daq.sc['P_TARGET'],
                                  daq.sc['P_MEAS'],
                                  daq.sc['P_TARGET_MIN'],
                                  daq.sc['P_TARGET_MAX'],
                                  dataset_filename))

        # create result workbook

        ts.log('Sampling complete')
        daq.data_capture(False)
        ds = daq.data_capture_dataset()
        ts.log('Saving file: %s' % dataset_filename)
        ds.to_csv(ts.result_file_path(dataset_filename))
        result_params['plot.title'] = os.path.splitext(dataset_filename)[0]
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
            eut.close()
        if result_summary is not None:
            result_summary.close()



def volt_watt_mode_imbalanced_grid(imbalance_resp, vw_curves = 1):

    result = script.RESULT_FAIL
    daq = None
    data = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None

    try:
        # result params
        result_params = {
            'plot.title': 'title_name',
            'plot.x.title': 'Time (sec)',
            'plot.x.points': 'TIME',
            'plot.y.points': 'V_TARGET,V_MEAS',
            'plot.y.title': 'Voltage (V)',
            'plot.V_TARGET.point': 'True',
            'plot.y2.points': 'P_TARGET,P_MEAS',
            'plot.P_TARGET.point': 'True',
            'plot.P_TARGET.min_error': 'P_TARGET_MIN',
            'plot.P_TARGET.max_error': 'P_TARGET_MAX',
        }

        cat = ts.param_value('eut.cat')
        cat2 = ts.param_value('eut.cat2')
        sink_power = ts.param_value('eut.sink_power')
        p_rated = ts.param_value('eut.p_rated')
        p_rated_prime = ts.param_value('eut.p_rated_prime')
        s_rated = ts.param_value('eut.s_rated')
        eff = {
            1.00: ts.param_value('eut.efficiency_100') / 100,
            0.66: ts.param_value('eut.efficiency_66') / 100,
            0.20: ts.param_value('eut.efficiency_20') / 100
        }
        absorb_enable = ts.param_value('eut.abs_enabled')

        # DC voltages
        v_nom_in = ts.param_value('eut.v_in_nom')
        v_min_in = ts.param_value('eut.v_in_min')
        v_max_in = ts.param_value('eut.v_in_max')

        # AC voltages
        v_nom = ts.param_value('eut.v_nom')
        v_min = ts.param_value('eut.v_low')
        v_max = ts.param_value('eut.v_high')
        p_min = ts.param_value('eut.p_min')
        p_min_prime = ts.param_value('eut.p_min_prime')
        phases = ts.param_value('eut.phases')
        pf_settling_time = ts.param_value('eut.pf_settling_time')
        imbalance_resp = ts.param_value('eut.imbalance_resp')

        # Pass/fail accuracies
        pf_msa = ts.param_value('eut.pf_msa')
        # According to Table 3-Minimum requirements for manufacturers stated measured and calculated accuracy
        MSA_Q = 0.05 * s_rated
        MSA_P = 0.05 * s_rated
        MSA_V = 0.01 * v_nom
        a_v = 1.5 * MSA_V

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
        # it is assumed the EUT is on
        eut = der.der_init(ts)
        if eut is not None:
            vw_curve_params = {'v': [v_start, v_stop], 'w': [100., 0], 'DeptRef': 'W_MAX_PCT'}
            vw_params = {'Ena': True, 'ActCrv': 1, 'curve': vw_curve_params}
            eut.volt_watt(params=vw_params)
            ts.log_debug('Initial EUT VW settings are %s' % eut.volt_watt())
        '''
        c) Set all AC test source parameters to the nominal operating voltage and frequency.
        '''

        if grid is not None:
            grid.voltage(v_nom)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)

        result_summary.write(
            'Result,Test Name,Power Level,Iteration,direction,V_target,V_actual,Power_target,Power_actual,P_min,P_max,Dataset File\n')

        '''
        d) Adjust the EUT's available active power to Prated. For an EUT with an input voltage range, set the input
        voltage to Vin_nom. The EUT may limit active power throughout the test to meet reactive power requirements.
        For an EUT with an input voltage range, repeat steps d) through o) for Vin_min and Vin_max.
        '''

        # if pv is not None:
        # TODO implement IV_curve_config
        # pv.iv_curve_config(pmp=p_rated, vpm=v_nom)
        # pv.iv_curve_config(pmp=p_rated, vpm=v_in)
        # pv.irradiance_set(1000.)
        '''
        e) Set EUT volt-watt parameters to the values specified by Characteristic 1. All other function be turned off.
        '''

        v_pairs = collections.OrderedDict()  # {}

        v_pairs[1] = {'V1': round(1.06 * v_nom, 2),
                      'V2': round(1.10 * v_nom, 2),
                      'P1': round(p_rated, 2)}

        if absorb_enable == 'Yes':
            v_pairs[1].add('P2', 0)

        else:
            if p_min > (0.2 * p_rated):
                v_pairs[1]['P2'] = int(0.2 * p_rated)
            else:
                v_pairs[1]['P2'] = int(p_min)

        '''
        f) Verify volt-var mode is reported as active and that the correct characteristic is reported.
        g) Once steady state is reached, begin the adjustment of phase voltages.
        t) Repeat steps d) through t) at EUT power set at 20% and 66% of rated power.
        u) Repeat steps d) through u) for characteristics 2 and 3.
        v) Test may be repeated for EUT's that can also absorb power using the P' values in the characteristic definition.
        '''

        """
        Test start
        """
        for imbalance_response in imbalance_resp:

            ts.log('Starting imbalance test with VW mode at %s' % (imbalance_response))

            if pv is not None:
                # TODO implement IV_curve_config
                pv.power_set(power)
                # pv_power_setting = (p_rated * power) / eff[power]
                # pv.iv_curve_config(pmp=pv_power_setting, vpm=v_in)
                # pv.irradiance_set(1000.)
                # ts.log('Set PV simulator power to {} with efficiency at {} %'.format(p_rated * power, eff[power] * 100.))

            # Configure the data acquisition system
            ts.log('Starting data capture for power = %s' % power)
            dataset_filename = 'VW_curve_%s_pwr_%0.2f.csv' % (vw_curve, power)
            daq.data_capture(True)

            ts.log_debug('curve points:  %s' % v_pairs[vw_curve])

            '''
            l) For multiphase units, step the AC test source voltage to Case A from Table 23.

                                        Table 23 - Imbalanced Voltage Test Cases 12
                    +----------------------------------------------+-----------------------------------------------+
                    | Symmetrical Components                       | Phasor Components                             |
                    +----------------------------------------------+-----------------------------------------------+
                    | Zero Sequence | Positive Seq | Negative Seq  | Phase A      | Phase B       | Phase C        |
                    | Mag | Angle   | Mag | Angle  | Mag   | Angle | Mag   | Angle| Mag   | Angle | Mag   | Angle  |
            +-------+-----+---------+-----+--------+-------+-------+-------+------+-------+-------+-------+--------+
            |Case A | 0.0 | 0.0     | 1.0 | 0.0    | 0.07  | 0     | 1.070 | 0.0  | 0.967 | 123.6 | 0.967 | -123.6 |
            +-------+-----+---------+-----+--------+-------+-------+-------+------+-------+-------+-------+--------+
            |Case B | 0.0 | 0.0     | 1.0 | 0.0    | 0.09  | 180   | 0.910 | 0.0  | 1.048 | 115.7 | 1.048 | -115.7 |
            +-------+-----+---------+-----+--------+-------+-------+-------+------+-------+-------+-------+--------+
            |Case C | 0.0 | 0.0     | 1.0 | 0.0    | 0.05  | 0     | 1.050 | 0.0  | 0.976 | 122.5 | 0.976 | -122.5 |
            +-------+-----+---------+-----+--------+-------+-------+-------+------+-------+-------+-------+--------+
            |Case D | 0.0 | 0.0     | 1.0 | 0.0    | 0.05  | 180   | 0.950 | 0.0  | 1.026 | 117.6 | 1.026 | -117.6 |
            +-------+-----+---------+-----+--------+-------+-------+-------+------+-------+-------+-------+--------+

            For tests with imbalanced, three-phase voltages, the manufacturer shall state whether the EUT responds
            to individual phase voltages, or the average of the three-phase effective (RMS) values or the positive
            sequence of voltages. For EUTs that respond to individual phase voltages, the response of each
            individual phase shall be evaluated. For EUTs that response to the average of the three-phase effective
            (RMS) values mor the positive sequence of voltages, the total three-phase reactive and active power
            shall be evaluated.
            '''

            '''
            Step i) For multiphase units, step the AC test source voltage to Case A from Table 23
            '''

            if grid is not None:
                grid.config_asymmetric_phase_angles(mag=[1.07 * v_nom, 0.967 * v_nom, 0.967 * v_nom],
                                                    angle=[0., 123.6, -123.6])
                daq.sc['event'] = 'Case A'
                ts.sleep(4 * pf_settling_time)
                daq.sc['event'] = 'T_settling_done'

                # Test result accuracy for CPF
                daq.data_sample()
                data = daq.data_capture_read()

                # Test result accuracy requirements per IEEE1547-4.2 for Q(V)
                P_V_passfail = p_v_criteria(v_pairs=v_pairs[vw_curve], a_v=a_v, p_mra=MSA_P, daq=daq,
                                            imbalance_resp=imbalance_response)

                # Test result accuracy requirements per IEEE1547-4.2 for Q(tr)
                # TODO p_tr_criteria still needs to be implemented

                ts.log('        Powers targ, min, max: %s, %s, %s' % (
                    daq.sc['P_TARGET'], daq.sc['P_TARGET_MIN'], daq.sc['P_TARGET_MAX']))

                result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                     (P_V_passfail, ts.config_name(), power * 100., direction, daq.sc['V_TARGET'],
                                      daq.sc['V_MEAS'], daq.sc['P_TARGET'], daq.sc['P_MEAS'], daq.sc['P_TARGET_MIN'],
                                      daq.sc['P_TARGET_MAX'], dataset_filename))

            '''
            Step j) For multiphase units, step the AC test source voltage to VN.
            '''
            if grid is not None:
                grid.voltage(v_nom)
                daq.sc['event'] = 'Step J'
                ts.sleep(4 * pf_settling_time)
                daq.sc['event'] = 'T_settling_done'

                # Test result accuracy for CPF
                daq.data_sample()
                data = daq.data_capture_read()

                # Test result accuracy requirements per IEEE1547-4.2 for Q(V)
                P_V_passfail = p_v_criteria(v_pairs=v_pairs[vw_curve], a_v=a_v, p_mra=MSA_P, daq=daq,
                                            imbalance_resp=imbalance_response)

                # Test result accuracy requirements per IEEE1547-4.2 for Q(tr)
                # TODO p_tr_criteria still needs to be implemented

                ts.log('        Powers targ, min, max: %s, %s, %s' % (
                    daq.sc['P_TARGET'], daq.sc['P_TARGET_MIN'], daq.sc['P_TARGET_MAX']))

                result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                     (P_V_passfail, ts.config_name(), power * 100., direction, daq.sc['V_TARGET'],
                                      daq.sc['V_MEAS'], daq.sc['P_TARGET'], daq.sc['P_MEAS'],
                                      daq.sc['P_TARGET_MIN'],
                                      daq.sc['P_TARGET_MAX'], dataset_filename))

            '''
            Step k) For multiphase units, step the AC test source voltage to Case B from Table 23
            '''

            if grid is not None:
                grid.config_asymmetric_phase_angles(mag=[0.910 * v_nom, 1.048 * v_nom, 1.048 * v_nom],
                                                    angle=[0., 115.7, -115.7])
                daq.sc['event'] = 'Case B'
                ts.sleep(4 * pf_settling_time)
                daq.sc['event'] = 'T_settling_done'

                # Test result accuracy for CPF
                daq.data_sample()
                data = daq.data_capture_read()

                # Test result accuracy requirements per IEEE1547-4.2 for Q(V)
                P_V_passfail = p_v_criteria(v_pairs=v_pairs[vw_curve], a_v=a_v, p_mra=MSA_P, daq=daq,
                                            imbalance_resp=imbalance_response)

                # Test result accuracy requirements per IEEE1547-4.2 for Q(tr)
                # TODO p_tr_criteria still needs to be implemented

                ts.log('        Powers targ, min, max: %s, %s, %s' % (
                    daq.sc['P_TARGET'], daq.sc['P_TARGET_MIN'], daq.sc['P_TARGET_MAX']))

                result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                     (P_V_passfail, ts.config_name(), power * 100., direction, daq.sc['V_TARGET'],
                                      daq.sc['V_MEAS'], daq.sc['P_TARGET'], daq.sc['P_MEAS'], daq.sc['P_TARGET_MIN'],
                                      daq.sc['P_TARGET_MAX'], dataset_filename))

            '''
            Step l) For multiphase units, step the AC test source voltage to VN.
            '''
            if grid is not None:
                grid.voltage(v_nom)
                daq.sc['event'] = 'Step J'
                ts.sleep(4 * pf_settling_time)
                daq.sc['event'] = 'T_settling_done'

                # Test result accuracy for CPF
                daq.data_sample()
                data = daq.data_capture_read()

                # Test result accuracy requirements per IEEE1547-4.2 for Q(V)
                P_V_passfail = p_v_criteria(v_pairs=v_pairs[vw_curve], a_v=a_v, p_mra=MSA_P, daq=daq,
                                            imbalance_resp=imbalance_response)

                # Test result accuracy requirements per IEEE1547-4.2 for Q(tr)
                # TODO p_tr_criteria still needs to be implemented

                ts.log('        Powers targ, min, max: %s, %s, %s' % (
                    daq.sc['P_TARGET'], daq.sc['P_TARGET_MIN'], daq.sc['P_TARGET_MAX']))

                result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                     (P_V_passfail, ts.config_name(), power * 100., direction, daq.sc['V_TARGET'],
                                      daq.sc['V_MEAS'], daq.sc['P_TARGET'], daq.sc['P_MEAS'],
                                      daq.sc['P_TARGET_MIN'],
                                      daq.sc['P_TARGET_MAX'], dataset_filename))

        # create result workbook

        ts.log('Sampling complete')
        daq.data_capture(False)
        ds = daq.data_capture_dataset()
        ts.log('Saving file: %s' % dataset_filename)
        ds.to_csv(ts.result_file_path(dataset_filename))
        result_params['plot.title'] = os.path.splitext(dataset_filename)[0]
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
            eut.close()
        if result_summary is not None:
            result_summary.close()

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
        Equipment Configuration
        """

        # initialize pv simulator
        pv = pvsim.pvsim_init(ts)
        p_rated = ts.param_value('eut.p_rated')
        pv.power_set(p_rated)
        pv.power_on()  # power on at p_rated

        """
        Test Configuration
        """
        # list of active tests
        vw_curves = collections.OrderedDict()
        t_settling = [0,0,0,0]

        if mode == 'Imbalanced grid':
            if ts.param_value('vw.imbalance_resp_1') == 'Enable':
                imbalance_resp.append('individual phase voltages')
            if ts.param_value('vw.imbalance_resp_2') == 'Enable':
                imbalance_resp.append('average of the three-phase effective (RMS)')
            if ts.param_value('vw.imbalance_resp_3') == 'Enable':
                imbalance_resp.append('the positive sequence of voltages')
        else:
            irr = ts.param_value('vw.irr')
            if ts.param_value('vw.test_1') == 'Enabled':
                vw_curves['characteristic 1'] = 1
                t_settling[1]=ts.param_value('vw.test_1_t_r')
            if ts.param_value('vw.test_2') == 'Enabled':
                vw_curves['characteristic 2'] = 2
                t_settling[2]=ts.param_value('vw.test_2_t_r')
            if ts.param_value('vw.test_3') == 'Enabled':
                vw_curves['characteristic 3'] = 3
                t_settling[3]=ts.param_value('vw.test_3_t_r')

        #List of power level for tests
        if irr == '20%':
            pwr_lvls = [0.20]
        elif irr == '66%':
            pwr_lvls = [0.66]
        elif irr == '100%':
            pwr_lvls = [1.00]
        else:
            pwr_lvls = [1.00, 0.66, 0.20]

        # ts.log_debug('power_lvl_dictionary:%s' % (pwr_lvls))
        # ts.log_debug('%s' % (vw_curves))
        if mode == 'Imbalanced grid':
            result = volt_watt_mode_imbalanced_grid(imbalance_resp=imbalance_resp)
        else:
            result = volt_watt_mode(vw_curves=vw_curves, t_settling=t_settling, pwr_lvls=pwr_lvls)

        return result

    except script.ScriptFail, e:
        reason = str(e)
        if reason:
            ts.log_error(reason)

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
info.param_group('eut', label='VW EUT specified parameters',glob=True)
info.param('eut.phases', label='Phases', default='Single Phase', values=['Single phase', 'Split phase', 'Three phase'])
info.param('eut.s_rated', label='Output Apparent power Rating (W)', default=10000.)
info.param('eut.p_rated', label='Output Power Rating (W)', default=10000.)
info.param('eut.p_min', label='Minimum Power Rating(W)', default=1000.)
info.param('eut.abs_enable', label='Can DER absorb active power?', default='No',values=['No', 'Yes'])
info.param('eut.v_low', label='Min AC voltage range with function enabled (V)', default=108.)
info.param('eut.v_high', label='Max AC voltage range with function enabled (V)', default=132.)
info.param('eut.v_nom', label='Nominal AC voltage (V)', default=120.)
info.param('eut.efficiency_20', label='CEC Efficiency list for power level = 20% at nominal VDC', default=97.0)
info.param('eut.efficiency_66', label='CEC Efficiency list for power level = 66% at nominal VDC', default=97.0)
info.param('eut.efficiency_100', label='CEC Efficiency list for power level = 100% at nominal VDC', default=96.9)

# VW test parameters
info.param_group('vw', label='Test Parameters')
info.param('vw.mode', label='Volt-Watt mode', default='Normal', values=['Normal', 'Imbalanced grid'])

info.param('vw.test_1', label='Characteristic 1 curve', default='Enabled', values=['Disabled', 'Enabled'],\
           active='vw.mode', active_value=['Normal'])
info.param('vw.test_1_t_r', label='Settling time (t) for curve 1', default=10.0,\
           active='vw.test_1', active_value=['Enabled'])

info.param('vw.test_2', label='Characteristic 2 curve', default='Enabled', values=['Disabled', 'Enabled'],\
           active='vw.mode', active_value=['Normal'])
info.param('vw.test_2_t_r', label='Settling time min (t) for curve 2', default=90.0,\
           active='vw.test_2', active_value=['Enabled'])

info.param('vw.test_3', label='Characteristic 3 curve', default='Enabled', values=['Disabled', 'Enabled'],\
           active='vw.mode', active_value=['Normal'])
info.param('vw.test_3_t_r', label='Settling time max (t) for curve 3', default=0.5,\
           active='vw.test_3', active_value=['Enabled'])

info.param('vw.power_lvl', label='Power Levels', default='All', values=['100%', '66%', '20%', 'All'],\
           active='vw.mode', active_value=['Normal'])

info.param('vw.imbalance_resp_1', label='EUT responds to: Individual phase voltages', \
           default='Enabled', values=['Disabled', 'Enabled'], active='vw.mode', active_value=['Imbalanced grid'])
info.param('vw.imbalance_resp_2', label='EUT responds to: Average of the three-phase effective (RMS)', \
           default='Enabled', values=['Disabled', 'Enabled'], active='vw.mode', active_value=['Imbalanced grid'])
info.param('vw.imbalance_resp_3', label='EUT responds to: Positive sequence of voltages', \
           default='Enabled', values=['Disabled', 'Enabled'], active='vw.mode', active_value=['Imbalanced grid'])
#info.param('vw.n_iter', label='Number of iteration for each test', default=1)


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
