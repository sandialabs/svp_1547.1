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
"""

"""


def sequence012_to_abc(params=None):
    """
    TODO: Convert desired sequence 012 into phase a,b,c magnitudes and angles

    :param params={'zero':None, 'positive'=None, 'negative'=None}
    :return: magnitude dictionary containing phase and angles into degrees
    :        angles dictionary containing phase and angles into degrees
    """
    a = cmath.exp(2 * cmath.pi * 1j / 3)
    a2 = cmath.exp(4 * cmath.pi * 1j / 3)
    magnitudes = {}
    angles = {}
    vector = {}
    # Fortescue equation to convert into ABC
    # Current driver takes channel 1,2,3 instead of a,b,c
    """
    vector['a']=(params['0']+params['+']+params['-'])
    vector['b']=(params['0']+a2*params['+']+a*params['-'])
    vector['c']=(params['0']+a*params['+']+a2*params['-'])
    """
    vector['1'] = (params['0'] + params['+'] + params['-'])
    vector['2'] = (params['0'] + a2 * params['+'] + a * params['-'])
    vector['3'] = (params['0'] + a * params['+'] + a2 * params['-'])
    for phase, value in vector.iteritems():
        magnitudes[phase], angles[phase] = cmath.polar(value)
        # Rounding up values
        magnitudes[phase] = round(magnitudes[phase] * ts.param_value('eut.v_nom'), 2)
        # convert into degrees
        angles[phase] = str(round(angles[phase] * 180 / math.pi, 3)) + 'DEGree'
    return magnitudes, angles


def imbalanced_grid_test(curve_vq, grid, daq, result_summary):
    """
    TODO: Function that execute test in mode imbalanced grid

    :param curve_number: VV characteristic curve desired
    :param v_nom: VV nominal voltage output
    :param s_rated: VV apparent power output
    :return: curve tests vector
    """

    seq012 = ([0, 1.0, 0.10, 60], \
              [0, 1.0, 0.05, 300], \
              [0, 1.0, 0.03, 300], \
              [0, 1.0, 0, 30], \
              [0, 1.0, -0.12, 60], \
              [0, 1.0, -0.05, 300], \
              [0, 1.0, -0.03, 300], \
              [0, 1.0, 0, 30])

    v_nom = ts.param_value('eut.v_nom')
    phases = ts.param_value('eut.phases')
    mode = ts.param_value('vv.mode')

    dataset_filename = 'VV_IG_Vnom_%d.csv' % (v_nom)

    daq.data_capture(True)
    daq.data_sample()
    data = daq.data_capture_read()

    for steps in seq012:
        daq.sc['event'] = 'zero_{}_pos_{}_neg_{}'.format(steps[0], steps[1], steps[2])
        mag, angle = sequence012_to_abc(params={'0': steps[0], '+': steps[1], '-': steps[2]})
        ts.log_debug('For sequence zero:%0.2f postive:%0.2f negative:%0.2f' % (steps[0], steps[1], steps[2]))
        ts.log('Setting magnitudes phA:%s phB:%s phC:%s' % (mag['1'], mag['2'], mag['3']))
        ts.log('Setting angles phA:%s phB:%s phC:%s' % (angle['1'], angle['2'], angle['3']))

        if grid is not None:
            grid.voltage(mag)
            grid.phases_angles(params=angle)

        ts.sleep(steps[3])
        # ts.sleep(1)
        daq.data_sample()
        data = daq.data_capture_read()

        # Test result accuracy requirements per IEEE1547-4.2 for Q(V)
        q_v_passfail_result = q_v_passfail(data=data,
                                           phases=phases,
                                           curve_vq=curve_vq,
                                           daq=daq)

        # Test result accuracy requirements per IEEE1547-4.2 for Q(tr)
        # Still needs to be implemented

        daq.sc['event'] = 'T_settling_done_{}'.format(steps[3])
        daq.data_sample()

        result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                             (q_v_passfail_result,
                              ts.config_name(),
                              mode,
                              daq.sc['V_MEAS'],
                              daq.sc['Q_MEAS'],
                              daq.sc['Q_TARGET'],
                              daq.sc['Q_TARGET_MIN'],
                              daq.sc['Q_TARGET_MAX'],
                              dataset_filename))

    result_params = {
        'plot.title': 'title_name',
        'plot.x.title': 'Time (sec)',
        'plot.x.points': 'TIME',
        'plot.y.points': 'Q_TARGET,V_MEAS',
        'plot.y.title': 'Reactive power (Vars)',
        'plot.Q_TARGET.point': 'True',
        'plot.y2.points': 'Q_TARGET,Q_MEAS',
        'plot.Q_TARGET.point': 'True',
        'plot.Q_TARGET.min_error': 'Q_TARGET_MIN',
        'plot.Q_TARGET.max_error': 'Q_TARGET_MAX',
    }

    daq.data_capture(False)
    ds = daq.data_capture_dataset()
    ts.log('Saving file: %s' % dataset_filename)
    ds.to_csv(ts.result_file_path(dataset_filename))
    result_params['plot.title'] = os.path.splitext(dataset_filename)[0]
    ts.result_file(dataset_filename, params=result_params)
    result = script.RESULT_COMPLETE

    return result


def normal_curve_test(vv_curve, mode, vq_curve, v_ref, power, t_settling, daq, grid, result_summary):

    v_nom=ts.param_value('eut.v_nom')
    phases=ts.param_value('eut.phases')

    if mode == 'Vref-test':
        dataset_filename = 'VV_%s_tr_%d.csv' % (mode, t_r[vv_curve - 1])
        ts.log('Set EUT to autonomous adjusting Vref mode ON')

    else:
        dataset_filename = 'VV_%s_pwr_%d_Vref_%d.csv' % (vv_curve, int(power * 100), (100 * round(v_ref / v_nom, 2)))


    v_steps_dic = voltage_steps(v=vq_curve,
                                v_ref=v_ref,
                                mode=mode)

    daq.data_capture(True)

    for test, v_steps in v_steps_dic.iteritems():
        ts.log('With v_steps_dict at - %s' % (v_steps))

        for v_step in v_steps:
            ts.log('        Recording Q(vars) at voltage %0.2f V for 4*t_settling = %0.1f sec. %s' %
                   (v_step, 4 * t_settling, test))

            q_targ = interpolation_v_q(value=v_step,
                                       vq_curve=vq_curve)  # target reactive power for the voltage measurement
            ts.log('        Q target: %s' %q_targ)

            daq.sc['event'] = 'v_Step_{}'.format(test)

            daq.sc['V_TARGET'] = v_step
            daq.sc['Q_TARGET'] = q_targ

            if grid is not None:
                grid.voltage(v_step)

            for i in range(4):
                daq.sc['event'] = 'v_step_{}'.format(test)
                ts.sleep(1 * t_settling)
                daq.sc['event'] = 'TR_{}_done'.format(i + 1)
                daq.data_sample()
                data = daq.data_capture_read()

            # Test result accuracy requirements per IEEE1547-4.2 for Q(t)
            # Still needs to be implemented

            # Test result accuracy requirements per IEEE1547-4.2 for Q(V)
            qv_passfail = q_v_passfail(data=data,
                                       phases=phases,
                                       vq_curve=vq_curve,
                                       daq=daq)

            daq.sc['event'] = 'T_settling_done_{}'.format(test)
            daq.data_sample()

            result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                 (qv_passfail,
                                  ts.config_name(),
                                  power * 100.,
                                  v_ref,
                                  '%s-%s' % (mode, test),
                                  daq.sc['V_TARGET'],
                                  daq.sc['V_MEAS'],
                                  daq.sc['Q_MEAS'],
                                  daq.sc['Q_TARGET'],
                                  daq.sc['Q_TARGET_MIN'],
                                  daq.sc['Q_TARGET_MAX'],
                                  dataset_filename))
    result_params = {
        'plot.title': 'title_name',
        'plot.x.title': 'Time (sec)',
        'plot.x.points': 'TIME',
        'plot.y.points': 'Q_TARGET,V_MEAS',
        'plot.y.title': 'Reactive power (Vars)',
        'plot.Q_TARGET.point': 'True',
        'plot.y2.points': 'Q_TARGET,Q_MEAS',
        'plot.Q_TARGET.point': 'True',
        'plot.Q_TARGET.min_error': 'Q_TARGET_MIN',
        'plot.Q_TARGET.max_error': 'Q_TARGET_MAX',
    }

    daq.data_capture(False)
    ds = daq.data_capture_dataset()
    ts.log('Saving file: %s' % dataset_filename)
    ds.to_csv(ts.result_file_path(dataset_filename))
    result_params['plot.title'] = os.path.splitext(dataset_filename)[0]
    ts.result_file(dataset_filename, params=result_params)
    result = script.RESULT_COMPLETE

    return result


def voltage_steps(v, v_ref, mode):
    """
    TODO: make v steps vector for desired test (Normal or Vref test)

    :param curve_number: VV characteristic curve desired
    :param v_nom: VV nominal voltage output
    :param s_rated: VV apparent power output
    :return: curve tests vector
    """
    v_steps_dict = collections.OrderedDict()
    v_low = ts.param_value('eut.v_low')
    v_high = ts.param_value('eut.v_high')
    v_nom=ts.param_value('eut.v_nom')
    a_v = round(1.5 * 0.01 * v_nom, 2)

    # Establishing V step depending on mode Normal or Vref
    if mode == 'Vref-test':
        v_steps_vref = [v_nom,
                        (v['V3'] + v['V4']) / 2,
                        (v['V1'] + v['V2']) / 2,
                        v_nom]
        v_steps_dict['Vref-test'] = np.around(v_steps_vref, decimals=2)
        ts.log('Testing VV function at the following voltage(vref test) points %s' % v_steps_dict['Vref-test'])

    else:
        # Per standard 1547.1 december 2018 version
        v_steps_cap = [(v['V3'] - a_v),  # step f
                       (v['V3'] + a_v),  # step g
                       (v['V3'] + v['V4']) / 2,  # step h
                       v['V4'] - a_v,  # step i only if V4<V_h
                       v['V4'] + a_v,  # step j only if V4<V_h
                       v_high - a_v,  # step k only if V4<V_h
                       v['V4'] + a_v,  # step l only if V4<V_h
                       (v['V3'] + v['V4']) / 2,  # step m only if V4<V_h
                       v['V3'] + a_v,  # step n
                       v['V3'] - a_v,  # step o
                       v_ref]  # step p

        if v['V4'] >= v_high:  # if V4 > V_h, remove step i,j,k,l,m
            del v_steps_cap[8]
            del v_steps_cap[7]
            del v_steps_cap[6]
            del v_steps_cap[5]
            del v_steps_cap[4]

        v_steps_dict['capacitive'] = np.around(v_steps_cap, decimals=2)

        """
        This section will need to be reviewed. As it is, it seems there are a few typos with this draft
        """
        v_steps_ind = [(v['V2'] + a_v),  # step q
                       (v['V2'] - a_v),  # step r
                       (v['V1'] + v['V2']) / 2,  # step s
                       v['V1'] + a_v,  # step t only if V1>V_low
                       v['V1'] - a_v,  # step u only if V1>V_low
                       v_low + a_v,  # step v only if V1>V_low
                       v['V1'] + a_v,  # step w only if V1>V_low
                       (v['V1'] + v['V2']) / 2,  # step x only if V1>V_low
                       v['V2'] - a_v,  # step y
                       v['V2'] + a_v,  # step z
                       v_ref]  # step aa

        if v['V1'] <= v_low:  # if V1 < V_low, remove step t,u,v,w,x
            del v_steps_ind[8]
            del v_steps_ind[7]
            del v_steps_ind[6]
            del v_steps_ind[5]
            del v_steps_ind[4]
        v_steps_dict['inductive'] = np.around(v_steps_ind, decimals=2)

        ts.log('Testing VV function at the following voltage(capacitive) points %s' % v_steps_dict['capacitive'])
        ts.log('Testing VV function at the following voltage(inductive) points %s' % v_steps_dict['inductive'])

    return v_steps_dict


def curve_v_q(curve_number):
    """
    :param curve_number: VV characteristic curve desired
    :return: curve tests vector
    """
    v_nom = ts.param_value('eut.v_nom')
    var_rated = ts.param_value('eut.var_rated')

    v_pairs={}

    v_pairs[1] = {'V1': round(0.92 * v_nom,2),
                  'V2': round(0.98 * v_nom,2),
                  'V3': round(1.02 * v_nom, 2),
                  'V4': round(1.08 * v_nom, 2),
                  'Q1': round(var_rated*1.0,2),
                  'Q2': round(var_rated*0.0, 2),
                  'Q3': round(var_rated*0.0, 2),
                  'Q4': round(var_rated*-1.0,2)}

    v_pairs[2] = {'V1': round(0.88 * v_nom,2),
                  'V2': round(1.04 * v_nom,2),
                  'V3': round(1.07 * v_nom, 2),
                  'V4': round(1.10 * v_nom, 2),
                  'Q1': round(var_rated*1.0,2),
                  'Q2': round(var_rated*0.5, 2),
                  'Q3': round(var_rated*0.5, 2),
                  'Q4': round(var_rated*-1.0,2)}

    v_pairs[3] = {'V1': round(0.90 * v_nom,2),
                  'V2': round(0.93 * v_nom,2),
                  'V3': round(0.96 * v_nom, 2),
                  'V4': round(1.10 * v_nom, 2),
                  'Q1': round(var_rated*1.0,2),
                  'Q2': round(var_rated*-0.5, 2),
                  'Q3': round(var_rated*-0.5, 2),
                  'Q4': round(var_rated*-1.0,2)}

    ts.log_debug('curve points:  %s' % v_pairs[curve_number])

    return v_pairs[curve_number]


def interpolation_v_q(value, vq_curve):
    """
    Interpolation function to find the target reactive power based on a 4 point VV curve

    TODO: make generic for n-point curves

    :param value: voltage point for the interpolation
    :param v: VV voltage points
    :param q: VV reactive power points
    :return: target reactive power
    """
    if value <= vq_curve['V1']:
        q_value = vq_curve['Q1']
    elif value < vq_curve['V2']:
        q_value = vq_curve['Q1'] + ((vq_curve['Q2'] - vq_curve['Q1']) / (vq_curve['V2'] - vq_curve['V1']) * (value - vq_curve['V1']))
    elif value == vq_curve['V2']:
        q_value = vq_curve['Q2']
    elif value <= vq_curve['V3']:
        q_value = vq_curve['Q3']
    elif value < vq_curve['V4']:
        q_value = vq_curve['Q3'] + ((vq_curve['Q4'] - vq_curve['Q3']) / (vq_curve['V4'] - vq_curve['V3']) * (value - vq_curve['V3']))
    else:
        q_value = vq_curve['Q4']
    return round(q_value, 1)


def q_v_passfail(data, phases, vq_curve, daq=None):
    """
    Determine reactive power target and the min/max q values for pass/fail acceptance based on manufacturer's specified
    accuracies (MSAs)

    :param v_value: measured voltage value
    :param v_msa: manufacturer's specified accuracy of voltage
    :param q_mra: manufacturer's specified accuracy of reactive power
    :param v: VV voltage points
    :param q: VV reactive power points
    :return: points for q_target, q_target_min, q_target_max
    """
    a_v = round(1.5 * 0.01 * ts.param_value('eut.v_nom'), 2)
    q_mra = round(0.05 * ts.param_value('eut.s_rated'), 1)

    daq.sc['V_MEAS'] = measurement_total(data=data, phases=phases, type_meas='V')
    daq.sc['Q_MEAS'] = measurement_total(data=data, phases=phases, type_meas='Q')

    # To calculate the min/max, you need the measured value
    if daq.sc['V_MEAS'] != 'No Data':
        daq.sc['Q_TARGET_MIN'] = interpolation_v_q(daq.sc['V_MEAS'] + a_v, vq_curve=vq_curve) - q_mra  # reactive power target from the lower voltage limit
        daq.sc['Q_TARGET_MAX'] = interpolation_v_q(daq.sc['V_MEAS'] - a_v, vq_curve=vq_curve) + q_mra  # reactive power target from the upper voltage limit

        ts.log('        Q actual, min, max: %s, %s, %s' % (
        daq.sc['Q_MEAS'], daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX']))

        if daq.sc['Q_TARGET_MIN'] <= daq.sc['Q_MEAS'] <= daq.sc['Q_TARGET_MAX']:
            passfail = 'Pass'
        else:
            passfail = 'Fail'
    else:
        daq.sc['Q_TARGET_MIN'] = 'No Data'
        daq.sc['Q_TARGET_MAX'] = 'No Data'
        passfail = 'Fail'
    ts.log('        Q(V) Passfail: %s' % (passfail))

    return passfail

def measurement_total(data, phases, type_meas):
    """
    Sum the EUT reactive power from all phases
    :param data: dataset
    :param phases: number of phases in the EUT
    :param choice: Either V,P or Q 
    :return: either total EUT reactive power, total EUT active power or average V
    """
    if type_meas == 'V':
        meas = 'VRMS'
        log_meas = 'Voltages'
    elif type_meas == 'P':
        meas = 'P'
        log_meas = 'Active powers'
    else:
        meas = 'Q'
        log_meas = 'Reactive powers'

    # ts.log_debug('%s' % type_meas)
    # ts.log_debug('%s' % log_meas)

    if phases == 'Single phase':
        try:
            ts.log_debug('        %s are: %s' % (log_meas, data.get('AC_{}_1'.format(meas))))
            value = data.get('AC_{}_1')
        except:
            value = 'No Data'
            return value
        phase = 1

    elif phases == 'Split phase':
        try:
            ts.log_debug('        %s are: %s, %s' % (log_meas, data.get('AC_{}_1'.format(meas)),
                                                     data.get('AC_{}_2'.format(meas))))
            value = data.get('AC_{}_1'.format(meas)) + data.get('AC_{}_2'.format(meas))
        except:
            value = 'No Data'
            return value
        phase = 2
    elif phases == 'Three phase':
        try:
            ts.log_debug('        %s are: %s, %s, %s' % (log_meas,
                                                         data.get('AC_{}_1'.format(meas)),
                                                         data.get('AC_{}_2'.format(meas)),
                                                         data.get('AC_{}_3'.format(meas))))
            value = data.get('AC_{}_1'.format(meas)) + data.get('AC_{}_2'.format(meas)) + data.get('AC_{}_3'.format(meas))
        except:
            value = 'No Data'
            return value
        phase = 3
    else:
        ts.log_error('Inverter phase parameter not set correctly.')
        raise

    if type_meas == 'V':
        # average value of V
        if value is not None:
            value = value / phase
        else:
            value = 'No Data'
            return value

    elif type_meas == 'P':
        return abs(value)

    return value


def test_run():
    result = script.RESULT_PASS
    daq = None
    pv = None
    grid = None
    chil = None
    result_summary = None
    p_max = None
    eut = None


    try:
        # Initiliaze VV EUT specified parameters variables
        tests_param = ts.param_value('eut.tests')
        p_rated = ts.param_value('eut.p_rated')
        v_nom = ts.param_value('eut.v_nom')


        mode = ts.param_value('vv.mode')
        phases = ts.param_value('eut.phases')

        # default power range
        p_min = p_rated * .2
        p_max = p_rated

        # initialize hardware-in-the-loop environment (if applicable)
        ts.log('Configuring HIL system...')
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # initialize grid simulator
        grid = gridsim.gridsim_init(ts)

        if grid is not None:
            grid.voltage(v_nom)
        """
        b) Set all voltage trip parameters to the widest range of adjustability. 
        Disable all reactive/active power control functions.
        """
        # Configure the EUT communications

        eut = der.der_init(ts)
        if eut is not None:
            eut.config()
            # ts.log_debug(eut.measurements())
            ts.log_debug('If not done already, set L/HVRT and trip parameters to the widest range of adjustability.')

        else:
            ts.log_debug('Set L/HFRT and trip parameters to the widest range of adjustability possible.')

        """
        c) Set all EPS source parameters to the nominal operating voltage and frequency. 
        """
        """
        d) Adjust the EUT active power to Prated. Where applicable, set the input voltage to Vin_nom.
        """
        # initialize pv simulator
        if pv is not None:
            pv = pvsim.pvsim_init(ts)
            pv.power_set(p_rated)
            pv.power_on()  # power on at p_rated

        # DAS soft channels
        das_points = {'sc': ('V_MEAS', 'V_TARGET', 'Q_MEAS', 'Q_TARGET', 'Q_TARGET_MIN', 'Q_TARGET_MAX', 'event')}

        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])
        if daq:
            daq.sc['V_MEAS'] = 100
            daq.sc['Q_MEAS'] = 100
            daq.sc['Q_TARGET'] = 100
            daq.sc['Q_TARGET_MIN'] = 100
            daq.sc['Q_TARGET_MAX'] = 100
            daq.sc['event'] = 'None'

        """
        e) Set EUT volt-var parameters to the values specified by Characteristic 1. 
        All other function should 1 be turned off. Turn off the autonomously adjusting reference voltage.
        """

        """
        Test Configuration
        """
        # list of active tests
        vv_curves = []
        t_r = [0, 0, 0, 0]
        if mode == 'Vref-test':
            vv_curves.append(1)
            t_r[0] = ts.param_value('vv.vref_t_r_1')
            irr = '100%'
            vref = '100%'
        elif mode == 'Imbalanced grid':
            irr = '100%'
            vref = '100%'
            vv_curves.append(1)
        else:
            irr = ts.param_value('vv.irr')
            vref = ts.param_value('vv.vref')
            if ts.param_value('vv.test_1') == 'Enabled':
                vv_curves.append(1)
                t_r[0] = ts.param_value('vv.test_1_t_r')
            if ts.param_value('vv.test_2') == 'Enabled':
                vv_curves.append(2)
                t_r[1] = ts.param_value('vv.test_2_t_r')
            if ts.param_value('vv.test_3') == 'Enabled':
                vv_curves.append(3)
                t_r[2] = ts.param_value('vv.test_3_t_r')

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

        v_ref_value[:] = [v_nom * i for i in v_ref_value]
        ts.log_debug('v_reference_dictionary:%s' % (v_ref_value))

        ts.log_debug('power_lvl_dictionary:%s' % (pwr_lvls))
        ts.log_debug('%s' % (vv_curves))

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write('Result, Curve Characteristic, Power Level, Vref, Test, '
                             'Vstep, V_measured, Q_measured, Q_target, Q_min, Q_max, Dataset File\n')

        """
            Test start
            """
        if eut is not None:
            ts.log_debug('Initial EUT VV settings are %s' % eut.volt_var())

        ts.log('Starting test - %s' % (mode))

        for vv_curve in vv_curves:
            ts.log('With - %s' % (test_labels[vv_curve]))
            vq_curve = curve_v_q(vv_curve)

            for pwr_lvl in pwr_lvls:
                ts.log('With power at - %s%%' % (pwr_lvl * 100))
                if pv is not None:
                    pv.power_set(p_rated * pwr_lvl)
                for v_ref in v_ref_value:
                    # create voltage settings along all segments of the curve
                    if not (mode == 'Imbalanced grid'):
                        result = normal_curve_test(vv_curve=vv_curve,
                                                   mode=mode,
                                                   vq_curve=vq_curve,
                                                   v_ref=v_ref,
                                                   power=pwr_lvl,
                                                   t_settling=t_r[vv_curve-1],
                                                   daq=daq,
                                                   grid=grid,
                                                   result_summary=result_summary)
                    else:
                        result = imbalanced_grid_test(curve_vq=curve_vq,
                                                      grid=grid,
                                                      daq=daq,
                                                      result_summary=result_summary)


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
            if v_nom is not None:
                grid.voltage(v_nom)
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


info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.0.0')

info.param_group('vv', label='Test Parameters')
info.param('vv.mode', label='Volt-Var mode', default='Normal', values=['Normal', 'Vref-test', 'Imbalanced grid'])
info.param('vv.vref_t_r_1', label='T ref value (t)', default=300, values=['Single phase', 'Split phase', 'Three phase'], \
           active='vv.mode', active_value=['Vref-test'])

info.param('vv.test_1', label='Characteristic 1 curve', default='Enabled', values=['Disabled', 'Enabled'], \
           active='vv.mode', active_value=['Normal'])
info.param('vv.test_1_t_r', label='Settling time (t) for curve 1', default=5.0, \
           active='vv.test_1', active_value=['Enabled'])

info.param('vv.test_2', label='Characteristic 2 curve', default='Enabled', values=['Disabled', 'Enabled'], \
           active='vv.mode', active_value=['Normal'])
info.param('vv.test_2_t_r', label='Settling time min (t) for curve 2', default=1.0, \
           active='vv.test_2', active_value=['Enabled'])

info.param('vv.test_3', label='Characteristic 3 curve', default='Enabled', values=['Disabled', 'Enabled'], \
           active='vv.mode', active_value=['Normal'])
info.param('vv.test_3_t_r', label='Settling time max (t) for curve 3', default=90.0, \
           active='vv.test_3', active_value=['Enabled'])

info.param('vv.irr', label='Power Levels iteration', default='All', values=['100%', '66%', '20%', 'All'],
           active='vv.mode', active_value=['Normal'])
info.param('vv.vref', label='Voltage reference iteration', default='All', values=['100%', '95%', '105%', 'All'],
           active='vv.mode', active_value=['Normal'])

info.param_group('eut', label='EUT VV Parameters', glob=True)
info.param('eut.s_rated', label='Apparent power rating (VA)', default=0.0)
info.param('eut.p_rated', label='Output power rating (W)', default=0.0)
info.param('eut.var_rated', label='Output var rating (vars)', default=0.0)
info.param('eut.v_nom', label='Nominal AC voltage (V)', default=120.0, desc='Nominal voltage for the AC simulator.')
info.param('eut.v_low', label='Minimum AC voltage (V)', default=0.0)
info.param('eut.v_high', label='Maximum AC voltage (V)', default=0.0)
info.param('eut.q_max_over', label='Maximum reactive power production (over-excited) (VAr)', default=0.0)
info.param('eut.q_max_under', label='Maximum reactive power absorbtion (under-excited) (VAr)(-)', default=0.0)
info.param('eut.phases', label='Phases', default='Three phase',
           values=['Single phase', 'Split phase', 'Three phase'])

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
