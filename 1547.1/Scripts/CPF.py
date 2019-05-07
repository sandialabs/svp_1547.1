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
from svpelab import loadsim
from svpelab import pvsim
from svpelab import das
from svpelab import der
from svpelab import hil
import script
from svpelab import result as rslt
from datetime import datetime, timedelta

import numpy as np
import collections
import cmath
import math


def q_p_criteria(pf, MSA_P, MSA_Q, daq, tr, step, q_initial):
    """
    Determine Q(MSAs)
    :param pf:          power factor target
    :param MSA_P:       manufacturer's specified accuracy of active power (W)
    :param MSA_Q:       manufacturer's specified accuracy of reactive power (VAr)
    :param daq:         data acquisition object in order to manipulated
    :param tr:          response time (s)
    :param step:        test procedure step letter or number (e.g "Step G")
    :param q_initial:   dictionnary with timestamp and reactive value before step change
    :return:    dictionnary q_p_analysis that contains passfail of response time requirements ( q_p_analysis['Q_TR_PF'])
    and test result accuracy requirements ( q_p_analysis['Q_FINAL_PF'] )
    """
    tr_analysis = 'start'
    result_analysis = 'start'
    q_p_analysis = {}

    """
    Every time a parameter is stepped or ramped, 
    measure and record the time domain current and 
    voltage response for at least 4 times the maximum 
    expected response time after the stimulus, and measure or derive, 
    active power, apparent power, reactive power, and power factor.
    
    This is only for the response time requirements (5.14.3.3 Criteria)
    """
    first_tr = q_initial['timestamp']+timedelta(seconds = tr)
    four_times_tr = q_initial['timestamp']+timedelta(seconds = 4*tr)

    try:
        while tr_analysis == 'start':
            time_to_sleep = first_tr - datetime.now()
            ts.sleep(time_to_sleep.total_seconds())
            now = datetime.now()
            if first_tr <= now:
                daq.data_sample()
                data = daq.data_capture_read()
                daq.sc['V_MEAS'] = measurement_total(data=data, type_meas='V',log=False)
                daq.sc['Q_MEAS'] = measurement_total(data=data, type_meas='Q',log=False)
                daq.sc['P_MEAS'] = measurement_total(data=data, type_meas='P',log=False)
                # The variable q_tr is the value use to verify the time response requirement.
                q_tr = daq.sc['Q_MEAS']
                daq.sc['event'] = "{}_tr_1".format(step)
                daq.data_sample()
                # This is to get out of the while loop. It provides the timestamp of tr_1
                tr_analysis = now

        while result_analysis == 'start':
            time_to_sleep = four_times_tr - datetime.now()
            ts.sleep(time_to_sleep.total_seconds())
            now = datetime.now()
            if four_times_tr <= now:
                daq.data_sample()
                data = daq.data_capture_read()
                daq.sc['V_MEAS'] = measurement_total(data=data, type_meas='V',log=True)
                daq.sc['Q_MEAS'] = measurement_total(data=data, type_meas='Q',log=True)
                daq.sc['P_MEAS'] = measurement_total(data=data, type_meas='P',log=True)
                daq.sc['event'] = "{}_tr_4".format(step)
                # To calculate the min/max, you need the measured value
                p_min = daq.sc['P_MEAS']+1.5*MSA_P
                p_max = daq.sc['P_MEAS']-1.5*MSA_P
                daq.sc['Q_TARGET_MIN'] = math.sqrt(pow(p_min, 2)*((1/pow(pf,2))-1))-1.5*MSA_Q  # reactive power target from the lower voltage limit
                daq.sc['Q_TARGET_MAX'] = math.sqrt(pow(p_max, 2)*((1/pow(pf,2))-1))+1.5*MSA_Q  # reactive power target from the upper voltage limit
                daq.data_sample()
                ts.log('        Q actual, min, max: %s, %s, %s' % (daq.sc['Q_MEAS'], daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX']))

                """
                The variable q_tr is the value use to verify the time response requirement.
                |----------|----------|----------|----------|
                           1st tr     2nd tr     3rd tr     4th tr            
                |          |                                |
                q_initial  q_tr                             q_final    
                
                (1547.1)After each voltage, the open loop response time, Tr , is evaluated. 
                The expected reactive power output, Q(T r ) ,
                at one times the open loop response time , 
                is calculated as 90% x (Qfinal - Q initial ) + Q initial
                """

                q_p_analysis['Q_INITIAL'] = q_initial['value']
                q_p_analysis['Q_FINAL'] = daq.sc['Q_MEAS']
                q_tr_diff = q_p_analysis['Q_FINAL'] - q_p_analysis['Q_INITIAL']
                q_tr_target = ((0.9 * q_tr_diff) +  q_p_analysis['Q_INITIAL'])
                # This q_tr_diff < 0 has been added to tackle when Q_final - Q_initial is negative.
                if q_tr_diff < 0 :
                    if q_tr <= q_tr_target :
                        q_p_analysis['Q_TR_PF'] = 'Pass'
                    else:
                        q_p_analysis['Q_TR_PF'] = 'Fail'
                elif q_tr_diff >= 0:
                    if q_tr >= q_tr_target :
                        q_p_analysis['Q_TR_PF'] = 'Pass'
                    else:
                        q_p_analysis['Q_TR_PF'] = 'Fail'

                if daq.sc['Q_TARGET_MIN'] <= daq.sc['Q_MEAS'] <= daq.sc['Q_TARGET_MAX']:
                    q_p_analysis['Q_FINAL_PF'] = 'Pass'
                else:
                    q_p_analysis['Q_FINAL_PF'] = 'Fail'
                ts.log('        Q_TR Passfail: %s' % (q_p_analysis['Q_TR_PF']))
                ts.log('        Q_FINAL Passfail: %s' % (q_p_analysis['Q_FINAL_PF']))

                # This is to get out of the while loop. It provides the timestamp of tr_4
                result_analysis = now

    except:
        daq.sc['V_MEAS'] = 'No Data'
        daq.sc['P_MEAS'] = 'No Data'
        daq.sc['Q_MEAS'] = 'No Data'
        passfail = 'Fail'
        daq.sc['Q_TARGET_MIN'] = 'No Data'
        daq.sc['Q_TARGET_MAX'] = 'No Data'

    return q_p_analysis

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
    daq.sc['Q_MEAS'] = measurement_total(data=data, type_meas='Q', log=True)
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

def test_run():

    result = script.RESULT_FAIL
    grid = None
    pv = p_rated = None
    daq = None
    eut = None
    rs = None
    chil = None
    result_summary = None
    step = None
    q_initial = None

    #sc_points = ['PF_TARGET', 'PF_MAX', 'PF_MIN']



    try:

        cat = ts.param_value('eut.cat')
        cat2 = ts.param_value('eut.cat2')
        sink_power = ts.param_value('eut.sink_power')
        p_rated = ts.param_value('eut.p_rated')
        p_rated_prime = ts.param_value('eut.p_rated_prime')
        s_rated = ts.param_value('eut.s_rated')

        # DC voltages
        v_nom_in_enabled = ts.param_value('cpf.v_in_nom')
        v_min_in_enabled = ts.param_value('cpf.v_in_min')
        v_max_in_enabled = ts.param_value('cpf.v_in_max')

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
        pf_response_time = ts.param_value('eut.pf_response_time')
        #imbalance_resp = ts.param_value('eut.imbalance_resp')

        # Pass/fail accuracies
        pf_msa = ts.param_value('eut.pf_msa')

        #According to Table 3-Minimum requirements for manufacturers stated measured and calculated accuracy
        MSA_Q = 0.05 * s_rated
        MSA_P = 0.05 * s_rated
        MSA_V = 0.01 * v_nom
        a_v = MSA_V * 1.5

        # get target power factors
        pf_targets = {}
        if ts.param_value('cpf.pf_min_inj') == 'Enabled':
            pf_targets['cpf_min_ind'] = float(ts.param_value('cpf.pf_min_inj_value'))
        if ts.param_value('cpf.pf_mid_inj') == 'Enabled':
            pf_targets['cpf_mid_ind'] = float(ts.param_value('cpf.pf_mid_inj_value'))
        if ts.param_value('cpf.pf_min_ab') == 'Enabled':
            pf_targets['cpf_min_cap'] = float(ts.param_value('cpf.pf_min_ab_value'))
        if ts.param_value('cpf.pf_mid_ab') == 'Enabled':
            pf_targets['cpf_mid_cap'] = float(ts.param_value('cpf.pf_mid_ab_value'))

        v_in_targets = {}

        if v_nom_in_enabled == 'Enabled' :
            v_in_targets['v_nom_in'] = v_nom_in
        if v_min_in != v_nom_in and v_min_in_enabled == 'Enabled':
            v_in_targets['v_min_in'] = v_min_in
        if v_max_in != v_nom_in and v_max_in_enabled == 'Enabled':
            v_in_targets['v_max_in'] = v_max_in
        if not v_in_targets:
            ts.log_error('No V_in target specify. Please select a V_IN test')
            raise


        """
        a) Connect the EUT according to the instructions and specifications provided by the manufacturer.
        """
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
        das_points = {'sc': ('V_MEAS', 'P_MEAS', 'Q_MEAS', 'Q_TARGET_MIN', 'Q_TARGET_MAX', 'PF_TARGET', 'event')}

        # initialize data acquisition
        daq = das.das_init(ts, sc_points=das_points['sc'])

        if daq:
            daq.sc['V_MEAS'] = 100
            daq.sc['P_MEAS'] = 100
            daq.sc['Q_MEAS'] = 100
            daq.sc['Q_TARGET_MIN'] = 100
            daq.sc['Q_TARGET_MAX'] = 100
            daq.sc['PF_TARGET'] = 1
            daq.sc['event'] = 'None'

        ts.log('DAS device: %s' % daq.info())

        """
        b) Set all voltage trip parameters to the widest range of adjustability. Disable all reactive/active power
        control functions.
        """
        # it is assumed the EUT is on
        eut = der.der_init(ts)
        if eut is not None:
            eut.config()
            # disable volt/var curve
            eut.volt_var(params={'Ena': False})
            ts.log_debug('If not done already, set L/HVRT and trip parameters to the widest range of adjustability.')

        """
        c) Set all AC test source parameters to the nominal operating voltage and frequency.
        """
        if grid is not None:
            grid.voltage(v_nom)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)

        result_summary.write('RESULT_ACCURACY_REQUIREMENTS,RESPONSE_TIME_REQUIREMENTS,PF_TARGET,VRMS_ACT,P_ACT,Q_FINAL,Q_TARGET_MIN,Q_TARGET_MAX,STEP,FILENAME\n')

        """
        d) Adjust the EUT's available active power to Prated. For an EUT with an input voltage range, set the input
        voltage to Vin_nom. The EUT may limit active power throughout the test to meet reactive power requirements.

        s) For an EUT with an input voltage range, repeat steps d) through o) for Vin_min and Vin_max.
        """
        # TODO: Include step t)
        """
        t) Steps d) through q) may be repeated to test additional communication protocols - Run with another test.
        """

        # For PV systems, this requires that Vmpp = Vin_nom and Pmpp = Prated.
        for v_in_label, v_in in v_in_targets.iteritems():
            ts.log('Starting test %s at v_in = %s' % (v_in_label, v_in))
            if pv is not None:
                pv.iv_curve_config(pmp=p_rated, vmp=v_in)
                pv.irradiance_set(1000.)

            """
            e) Enable constant power factor mode and set the EUT power factor to PFmin,inj.
            r) Repeat steps d) through o) for additional power factor settings: PFmin,ab, PFmid,inj, PFmid,ab.

            Only the user-selected PF setting will be tested.
            """
            for pf_test_name, pf_target in pf_targets.iteritems():
                # Start acquisition
                daq.data_capture(True)
                # Configure the data acquisition system
                ts.log('Starting data capture for pf = %s' % pf_target)
                dataset_filename = ('{0}_{1}'.format(v_in_label.upper(), pf_test_name.upper()))
                ts.log('------------{}------------'.format(dataset_filename))
                daq.sc['PF_TARGET'] = pf_target


                if eut is not None:
                    parameters = {'Ena': True, 'PF': pf_target}
                    ts.log('PF set: %s' % parameters)
                    eut.fixed_pf(params=parameters)
                    pf_setting = eut.fixed_pf()
                    ts.log('PF setting read: %s' % pf_setting)

                """
                f) Wait for steady state to be reached.

                Every time a parameter is stepped or ramped, measure and record the time domain current and voltage
                response for at least 4 times the maximum expected response time after the stimulus, and measure or
                derive, active power, apparent power, reactive power, and power factor.
                """
                step = 'Step F'
                daq.sc['event'] = step
                daq.data_sample()
                ts.log('Wait for steady state to be reached')
                ts.sleep(4*pf_response_time)

                """
                g) Step the EUT's active power to Pmin.
                """
                if pv is not None:
                    ts.log('Power step: setting PV simulator power to %s' % p_min)
                    step = 'Step G'
                    q_initial = get_q_initial(daq=daq,step=step)
                    pv.power_set(p_min)
                    q_p_analysis = q_p_criteria(pf=pf_target, MSA_P=MSA_P, MSA_Q=MSA_Q, daq=daq, tr=pf_response_time, step=step, q_initial=q_initial)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (q_p_analysis['Q_FINAL_PF'], q_p_analysis['Q_TR_PF'], pf_target,
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], q_p_analysis['Q_FINAL'],
                                          daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX'], step, dataset_filename))
                """
                h) Step the EUT's available active power to Prated.
                """
                if pv is not None:
                    ts.log('Power step: setting PV simulator power to %s' % p_rated)
                    step = 'Step H'
                    q_initial = get_q_initial(daq=daq,step=step)
                    pv.power_set(p_rated)
                    q_p_analysis = q_p_criteria(pf=pf_target, MSA_P=MSA_P, MSA_Q=MSA_Q, daq=daq, tr=pf_response_time,
                                                step=step, q_initial=q_initial)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (q_p_analysis['Q_FINAL_PF'], q_p_analysis['Q_TR_PF'], pf_target,
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], q_p_analysis['Q_FINAL'],
                                          daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX'], step, dataset_filename))

                if grid is not None:

                    #   i) Step the AC test source voltage to (VL + av)
                    ts.log('Voltage step: setting Grid simulator voltage to %s' % (v_min + a_v))
                    step = 'Step I'
                    q_initial = get_q_initial(daq=daq,step=step)
                    grid.voltage(v_min + a_v)
                    q_p_analysis = q_p_criteria(pf=pf_target, MSA_P=MSA_P, MSA_Q=MSA_Q, daq=daq, tr=pf_response_time,
                                                step=step, q_initial=q_initial)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (q_p_analysis['Q_FINAL_PF'], q_p_analysis['Q_TR_PF'], pf_target,
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], q_p_analysis['Q_FINAL'],
                                          daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX'], step, dataset_filename))

                    #   j) Step the AC test source voltage to (VH - av)
                    ts.log('Voltage step: setting Grid simulator voltage to %s' % (v_max - a_v))
                    step = 'Step J'
                    q_initial = get_q_initial(daq=daq, step=step)
                    grid.voltage(v_max - a_v)
                    q_p_analysis = q_p_criteria(pf=pf_target, MSA_P=MSA_P, MSA_Q=MSA_Q, daq=daq, tr=pf_response_time,
                                                step=step, q_initial=q_initial)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (q_p_analysis['Q_FINAL_PF'], q_p_analysis['Q_TR_PF'], pf_target,
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], q_p_analysis['Q_FINAL'],
                                          daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX'], step, dataset_filename))

                    #   k) Step the AC test source voltage to (VL + av)
                    #   STD_CHANGE : We think at CanmetENERGY that this should be v_nom and not (v_min + a_v) before doing imbalance testing
                    ts.log('Voltage step: setting Grid simulator voltage to %s' % (v_nom))
                    step = 'Step K'
                    q_initial = get_q_initial(daq=daq, step=step)
                    grid.voltage(v_nom)
                    q_p_analysis = q_p_criteria(pf=pf_target, MSA_P=MSA_P, MSA_Q=MSA_Q, daq=daq, tr=pf_response_time,
                                                step=step, q_initial=q_initial)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (q_p_analysis['Q_FINAL_PF'], q_p_analysis['Q_TR_PF'], pf_target,
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], q_p_analysis['Q_FINAL'],
                                          daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX'], step, dataset_filename))

                """
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
                """
                if grid is not None:
                    ts.log('Voltage step: setting Grid simulator to case A (IEEE 1547.1-Table 23)')
                    step = 'Step L'
                    q_initial = get_q_initial(daq=daq, step=step)
                    grid.config_asymmetric_phase_angles(mag=[1.07*v_nom, 0.967*v_nom, 0.967*v_nom],
                                                        angle=[0., 123.6, -123.6])
                    q_p_analysis = q_p_criteria(pf=pf_target, MSA_P=MSA_P, MSA_Q=MSA_Q, daq=daq, tr=pf_response_time,
                                                step=step, q_initial=q_initial)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (q_p_analysis['Q_FINAL_PF'], q_p_analysis['Q_TR_PF'], pf_target,
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], q_p_analysis['Q_FINAL'],
                                          daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX'], step, dataset_filename))



                """
                m) For multiphase units, step the AC test source voltage to VN.
                """

                if grid is not None:
                    ts.log('Voltage step: setting Grid simulator voltage to %s' % v_nom)
                    step = 'Step M'
                    q_initial = get_q_initial(daq=daq,step=step)
                    grid.voltage(v_nom)
                    q_p_analysis = q_p_criteria(pf=pf_target, MSA_P=MSA_P, MSA_Q=MSA_Q, daq=daq, tr=pf_response_time,
                                                step=step, q_initial=q_initial)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (q_p_analysis['Q_FINAL_PF'], q_p_analysis['Q_TR_PF'], pf_target,
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], q_p_analysis['Q_FINAL'],
                                          daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX'], step, dataset_filename))

                """
                n) For multiphase units, step the AC test source voltage to Case B from Table 23.
                """
                if grid is not None:
                    ts.log('Voltage step: setting Grid simulator to case B (IEEE 1547.1-Table 23)')
                    step = 'Step N'
                    q_initial = get_q_initial(daq=daq,step=step)
                    grid.config_asymmetric_phase_angles(mag=[0.91*v_nom, 1.048*v_nom, 1.048*v_nom],
                                                        angle=[0., 115.7, -115.7])
                    q_p_analysis = q_p_criteria(pf=pf_target, MSA_P=MSA_P, MSA_Q=MSA_Q, daq=daq, tr=pf_response_time,
                                                step=step, q_initial=q_initial)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (q_p_analysis['Q_FINAL_PF'], q_p_analysis['Q_TR_PF'], pf_target,
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], q_p_analysis['Q_FINAL'],
                                          daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX'], step, dataset_filename))

                """
                o) For multiphase units, step the AC test source voltage to VN
                """
                if grid is not None:
                    ts.log('Voltage step: setting Grid simulator voltage to %s' % v_nom)
                    step = 'Step O'
                    q_initial = get_q_initial(daq=daq, step=step)
                    grid.voltage(v_nom)
                    q_p_analysis = q_p_criteria(pf=pf_target, MSA_P=MSA_P, MSA_Q=MSA_Q, daq=daq, tr=pf_response_time,
                                                step=step, q_initial=q_initial)
                    result_summary.write('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' %
                                         (q_p_analysis['Q_FINAL_PF'], q_p_analysis['Q_TR_PF'], pf_target,
                                          daq.sc['V_MEAS'], daq.sc['P_MEAS'], q_p_analysis['Q_FINAL'],
                                          daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX'], step, dataset_filename))
                """
                p) Disable constant power factor mode. Power factor should return to unity.
                """
                if eut is not None:
                    parameters = {'Ena': False, 'PF': 1.0}
                    ts.log('PF set: %s' % parameters)
                    eut.fixed_pf(params=parameters)
                    pf_setting = eut.fixed_pf()
                    ts.log('PF setting read: %s' % pf_setting)
                    daq.sc['event'] = 'Step P'
                    daq.data_sample()
                    ts.sleep(4*pf_response_time)
                    daq.sc['event'] = 'T_settling_done'
                    daq.data_sample()


                """
                q) Verify all reactive/active power control functions are disabled.
                """
                if eut is not None:
                    ts.log('Reactive/active power control functions are disabled.')
                    # TODO Implement ts.prompt functionality?
                    #meas = eut.measurements()
                    #ts.log('EUT PF is now: %s' % (data.get('AC_PF_1')))
                    #ts.log('EUT Power: %s, EUT Reactive Power: %s' % (meas['W'], meas['VAr']))

                # result params
                result_params = {
                    'plot.title': ts.name,
                    'plot.x.title': 'Time (sec)',
                    'plot.x.points': 'TIME',
                    'plot.y.points': '{}, PF_TARGET'.format(','.join(str(x) for x in get_measurement_label('PF'))),
                    'plot.y.title': 'Power Factor',
                    'plot.y2.points': '{}'.format(','.join(str(x) for x in get_measurement_label('I'))),
                    'plot.y2.title': 'Current (A)'
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

        if grid is not None:
            grid.close()
        if pv is not None:
            if p_rated is not None:
                pv.power_set(p_rated)
            pv.close()
        if daq is not None:
            daq.close()
        if eut is not None:
            eut.fixed_pf(params={'Ena': False, 'PF': 1.0})
            eut.close()
        if rs is not None:
            rs.close()
        if chil is not None:
            chil.close()

        if result_summary is not None:
            result_summary.close()

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

info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.1.2')

# Power factor parameters
# PF - the commanded power factor
# PFmin,inj - minimum injected power factor, 0.90 for both Category A and B equipment
# PFmin,ab - minimum absorbed power factor, 0.97 for Catergory A, 0.90 for Catergory B
# PFmid,inj - a power factor setting chosen to be less than 1 and greater than PFmin,inj
# PFmid,ab - a power factor setting chosen to be less than 1 and greater than PFmin,ab

info.param_group('cpf', label='Test Parameters')
info.param('cpf.pf_min_inj', label='PFmin,inj activation', default='Enabled', values=['Disabled', 'Enabled'])
info.param('cpf.pf_min_inj_value', label='PFmin,inj (Overexcited) (negative value, for SunSpec sign convention)',
           default=-0.90, active='cpf.pf_min_inj', active_value=['Enabled'])

info.param('cpf.pf_mid_inj', label='PFmid,inj activation', default='Enabled', values=['Disabled', 'Enabled'])
info.param('cpf.pf_mid_inj_value', label='PFmid,inj value (-1.00 < PFmid,inj < PFmin,inj):', default=-0.95,
           active='cpf.pf_mid_inj', active_value=['Enabled'])

info.param('cpf.pf_min_ab', label='PFmin,ab activation', default='Enabled', values=['Disabled', 'Enabled'])
info.param('cpf.pf_min_ab_value', label='PFmin,ab (Underexcited)', default=0.90,
           active='cpf.pf_min_ab', active_value=['Enabled'])

info.param('cpf.pf_mid_ab', label='PFmid,ab', default='Enabled', values=['Disabled', 'Enabled'])
info.param('cpf.pf_mid_ab_value', label='PFmid,ab value (PFmin,ab < PFmid,ab < 1.00):', default=0.95,
           active='cpf.pf_mid_ab', active_value=['Enabled'])
info.param('cpf.v_in_nom', label='Test V_in_nom', default='Enabled', values=['Disabled', 'Enabled'])
info.param('cpf.v_in_min', label='Test V_in_min', default='Enabled', values=['Disabled', 'Enabled'])
info.param('cpf.v_in_max', label='Test V_in_max', default='Enabled', values=['Disabled', 'Enabled'])

# EUT parameters
# Prated - output power rating (W)
# P'rated - for EUT's that can sink power, output power rating while sinking power (W)
# Srated - apparent power rating (VA)
# Vin_nom - for an EUT with an electrical input, nominal input voltage (V)
# Vin_min - for an EUT with an electrical input, minimum input voltage (V)
# Vin_max - for an EUT with an electrical input, maximum input voltage (V)
# VN - nominal output voltage (V)
# VL - minimum output voltage in the continous operating region (V)
# VH - maximum output voltage in the continous operating region (V)
# Pmin - minimum active power (W)
# P'min - for EUT's that can sink power, minimum active power while sinking power(W)
# Qmax,inj - maximum absorbed reactive power (VAr)
# Qmax,inj - minimum absorbed reactive power (VAr)

info.param_group('eut', label='CPF - EUT Parameters', glob=True)
info.param('eut.cat', label='DER Category (Distribution System Stability)', default='Category III (inverter-based)',
           values=['Category I (synchronous generator)', 'Category II (fuel cell)', 'Category III (inverter-based)'])

info.param('eut.cat2', label='DER Category (Bulk System Stability)', default='Category B',
           values=['Category A', 'Category B'],
           active='eut.cat', active_value=['Category II (fuel cell)'])

info.param('eut.sink_power', label='Can the EUT sink power, e.g., is it a battery system', default='No',
           values=['No', 'Yes'])

info.param('eut.p_rated', label='Prated: Output power rating (W)', default=3000.0)
info.param('eut.p_rated_prime', label='P\'rated: Output power rating while sinking power (W) (negative)',
           default=-3000.0, active='eut.sink_power', active_value=['Yes'])

info.param('eut.s_rated', label='Srated: apparent power rating (VA)', default=3000.0)

info.param('eut.v_in_nom', label='V_in_nom: Nominal input voltage (Vdc)', default=400)
info.param('eut.v_in_min', label='V_in_min: Nominal input voltage (Vdc)', default=200)
info.param('eut.v_in_max', label='V_in_max: Nominal input voltage (Vdc)', default=600)
info.param('eut.v_nom', label='V_nom: Nominal voltage output (V)', default=240.0)
info.param('eut.v_low', label='Minimum output voltage in the continous operating region (V)', default=0.88*240)
info.param('eut.v_high', label='Maximum output voltage in the continous operating region (V)', default=1.1*240)

info.param('eut.p_min', label='Pmin: Minimum active power (W)', default=0.2*3000.0)
info.param('eut.p_min_prime', label='P\'min: minimum active power while sinking power(W) (negative)',
           default=-0.2*3000.0, active='eut.sink_power', active_value=['Yes'])
#info.param('eut.imbalance_resp', label='Imbalance response. EUT responds to:', default='individual phase voltages',
#           values=['individual phase voltages', 'average of the three-phase effective (RMS)',
#                   'the positive sequence of voltages'])

info.param('eut.phases', label='Phases', values=['Single phase', 'Split phase', 'Three phase'], default='Three phase')

info.param('eut.pf_response_time', label='PF Response Time (secs)', default=1.0)

der.params(info)
das.params(info)
gridsim.params(info)
loadsim.params(info)
pvsim.params(info)
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


