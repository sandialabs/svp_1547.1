"""
Copyright (c) 2018, Sandia National Labs, SunSpec Alliance and CanmetENERGY(Natural Resources Canada)
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

Redistributions of source code must retain the above copyright notice, this
list of conditions and the following disclaimer.

Redistributions in binary form must reproduce the above copyright notice, this
list of conditions and the following disclaimer in the documentation and/or
other materials provided with the distribution.

Neither the names of the Sandia National Labs, SunSpec Alliance and CanmetENERGY(Natural Resources Canada)
nor the names of its contributors may be used to endorse or promote products derived from
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
from svpelab import p1547
import script
from svpelab import result as rslt
from datetime import datetime, timedelta

import numpy as np
import collections
import cmath
import math

VV = 'VV'
V = 'V'
F = 'F'
P = 'P'
Q = 'Q'

def volt_vars_mode(vv_curves, vv_response_time, pwr_lvls, v_ref_value):

    result = script.RESULT_FAIL
    daq = None
    v_nom = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None
    dataset_filename = None

    try:
        cat = ts.param_value('eut.cat')
        cat2 = ts.param_value('eut.cat2')
        sink_power = ts.param_value('eut.sink_power')
        p_rated = ts.param_value('eut.p_rated')
        p_rated_prime = ts.param_value('eut.p_rated_prime')
        var_rated = ts.param_value('eut.var_rated')
        s_rated = ts.param_value('eut.s_rated')

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

        """
        Version validation
        """
        p1547.VersionValidation(script_version=ts.info.version)

        """
        A separate module has been create for the 1547.1 Standard
        """
        ActiveFunction = p1547.ActiveFunction(ts=ts,
                                              functions=[VV],
                                              script_name='Volt-Var',
                                              criteria_mode=[True, True, True])
        ts.log_debug("1547.1 Library configured for %s" % ActiveFunction.get_script_name())

        # result params
        result_params = ActiveFunction.get_rslt_param_plot()
        ts.log_debug(result_params)

        '''
        a) Connect the EUT according to the instructions and specifications provided by the manufacturer.
        '''
        ts.log_debug(15*"*"+"HIL initialization"+15*"*")

        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()
        ts.log_debug(15*"*"+"PVSIM initialization"+15*"*")
        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts, support_interfaces={'hil': chil}) 
        if pv is not None:
            pv.power_set(p_rated)
            pv.power_on()  # Turn on DC so the EUT can be initialized
            #daq.set_dc_measurement(pv)  # send pv obj to daq to get dc measurements
            ts.sleep(0.5)

        # DAS soft channels
        ts.log_debug(15*"*"+"DAS initialization"+15*"*")

        #das_points = {'sc': ('Q_TARGET', 'Q_TARGET_MIN', 'Q_TARGET_MAX', 'Q_MEAS', 'V_TARGET', 'V_MEAS', 'event')}
        das_points = ActiveFunction.get_sc_points()
        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'], support_interfaces={'hil': chil}) 

        daq.sc['V_TARGET'] = v_nom
        daq.sc['Q_TARGET'] = 100
        daq.sc['Q_TARGET_MIN'] = 100
        daq.sc['Q_TARGET_MAX'] = 100
        daq.sc['event'] = 'None'

        ts.log('DAS device: %s' % daq.info())

        '''
        b) Set all voltage trip parameters to the widest range of adjustability.  Disable all reactive/active power
        control functions.
        '''
        ts.log_debug(15*"*"+"EUT initialization"+15*"*")

        eut = der.der_init(ts, support_interfaces={'hil': chil}) 
        if eut is not None:
            eut.config()
            ts.log_debug(eut.measurements())

            #Deactivating all functions on EUT
            #eut.deactivate_all_fct()

            ts.log_debug('Voltage trip parameters set to the widest range: v_min: {0} V, '
                         'v_max: {1} V'.format(v_low, v_high))
            try:
                eut.vrt_stay_connected_high(params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000,
                                                    'V1': v_high, 'Tms2': 0.16, 'V2': v_high})
            except Exception as e:
                ts.log_error('Could not set VRT Stay Connected High curve. %s' % e)
            try:
                eut.vrt_stay_connected_low(params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000,
                                                   'V1': v_low, 'Tms2': 0.16, 'V2': v_low})
            except Exception as e:
                ts.log_error('Could not set VRT Stay Connected Low curve. %s' % e)
        else:
            ts.log_debug('Set L/HVRT and trip parameters set to the widest range of adjustability possible.')

        # # Special considerations for CHIL ASGC/Typhoon startup
        if chil is not None:
            if eut is not None:
                if eut.measurements() is not None:
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
        ts.log_debug(15*"*"+"GRIDSIM initialization"+15*"*")

        grid = gridsim.gridsim_init(ts,support_interfaces={'hil': chil})  # Turn on AC so the EUT can be initialized
        if grid is not None:
            grid.voltage(v_nom)
            if chil is not None:  # If using HIL, give the grid simulator the hil object
                grid.config()

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write(ActiveFunction.get_rslt_sum_col_name())

        '''
        d) Adjust the EUT's available active power to Prated. For an EUT with an input voltage range, set the input
        voltage to Vin_nom. The EUT may limit active power throughout the test to meet reactive power requirements.
        For an EUT with an input voltage range.
        '''

        if pv is not None:
            pv.iv_curve_config(pmp=p_rated, vmp=v_in_nom)
            pv.irradiance_set(1000.)

        '''
        gg) Repeat steps g) through dd) for characteristics 2 and 3.
        '''
        for vv_curve in vv_curves:
            ts.log('Starting test with characteristic curve %s' % (vv_curve))
            ActiveFunction.reset_curve(vv_curve)
            ActiveFunction.reset_time_settings(tr=vv_response_time[vv_curve], number_tr=2)
            v_pairs = ActiveFunction.get_params(function=VV, curve=vv_curve)
            #ts.log_debug('v_pairs:%s' % v_pairs)

            '''
            ff) Repeat test steps d) through ee) at EUT power set at 20% and 66% of rated power.
            '''
            for power in pwr_lvls:
                ActiveFunction.reset_pwr(power)

                if pv is not None:
                    pv_power_setting = (p_rated * power)
                    pv.iv_curve_config(pmp=pv_power_setting, vmp=v_in_nom)
                    pv.irradiance_set(1000.)

                # Special considerations for CHIL ASGC/Typhoon startup #
                # Why does it need to appear twice, shouldn't this be at the driver level
                if chil is not None:
                    if eut is not None:
                        if  eut.measurements() is not None:
                            inv_power = eut.measurements().get('W')
                            timeout = 120.
                            if inv_power <= pv_power_setting * 0.85:
                                pv.irradiance_set(995)  # Perturb the pv slightly to start the inverter
                                ts.sleep(3)
                                eut.connect(params={'Conn': True})
                            while inv_power <= pv_power_setting * 0.85 and timeout >= 0:
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
                    



                '''
                ee) Repeat test steps e) through dd) with Vref set to 1.05*VN and 0.95*VN, respectively.
                '''
                for v_ref in v_ref_value:
                    ts.log('Setting v_ref at %s %% of v_nom' % (int(v_ref * 100)))

                    #Setting grid to vnom before test
                    if grid is not None:
                        grid.voltage(v_nom)

                    if eut is not None:
                        '''
                        e) Set EUT volt-var parameters to the values specified by Characteristic 1.
                        All other function should be turned off. Turn off the autonomously adjusting reference voltage.
                        '''
                        # Activate volt-var function with following parameters
                        # SunSpec convention is to use percentages for V and Q points.
                        vv_curve_params = {
                            'v': [(v_pairs['V1'] / v_nom) , (v_pairs['V2'] / v_nom) ,
                                  (v_pairs['V3'] / v_nom), (v_pairs['V4'] / v_nom) ],
                            'var': [(v_pairs['Q1'] / s_rated), (v_pairs['Q2'] / s_rated) ,
                                    (v_pairs['Q3'] / s_rated) , (v_pairs['Q4'] / s_rated)],
                            'vref': v_ref,
                            'RmpPtTms': vv_response_time[vv_curve]
                        }
                        ts.log_debug('Sending VV points: %s' % vv_curve_params)
                        eut.volt_var(params={'Ena': True, 'ACTCRV': vv_curve, 'curve': vv_curve_params})
                        # TODO autonomous vref adjustment to be included
                        # eut.autonomous_vref_adjustment(params={'Ena': False})
                        '''
                        f) Verify volt-var mode is reported as active and that the correct characteristic is reported.
                        '''
                        ts.log_debug('Initial EUT VV settings are %s' % eut.volt_var())
                    if chil is not None:                        
                        ts.log('Start simulation of CHIL')  
                        chil.start_simulation()
                    v_steps_dict = ActiveFunction.create_vv_dict_steps(v_ref=v_ref)

                    dataset_filename = 'VV_%s_PWR_%d_vref_%d' % (vv_curve, power * 100, v_ref*100)
                    ActiveFunction.reset_filename(filename=dataset_filename)
                    #ts.log('------------{}------------'.format(dataset_filename))
                    # Start the data acquisition systems
                    daq.data_capture(True)

                    for step_label, v_step in v_steps_dict.items():

                        ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_step, step_label))

                        ActiveFunction.start(daq=daq, step_label=step_label)
                        step_dict = {'V': v_step}

                        if grid is not None:
                            grid.voltage(step_dict['V'])

                        ActiveFunction.record_timeresponse(daq=daq)
                        ActiveFunction.evaluate_criterias(daq=daq, step_dict=step_dict)
                        result_summary.write(ActiveFunction.write_rslt_sum())

                    ts.log('Sampling complete')
                    dataset_filename = dataset_filename + ".csv"
                    daq.data_capture(False)
                    ds = daq.data_capture_dataset()
                    ts.log('Saving file: %s' % dataset_filename)
                    ds.to_csv(ts.result_file_path(dataset_filename))
                    result_params['plot.title'] = dataset_filename.split('.csv')[0]
                    ts.result_file(dataset_filename, params=result_params)
                    result = script.RESULT_COMPLETE



    except script.ScriptFail as e:
        reason = str(e)
        if reason:
            ts.log_error(reason)

    except Exception as e:
        if dataset_filename is not None:
            dataset_filename = dataset_filename + ".csv"
            daq.data_capture(False)
            ds = daq.data_capture_dataset()
            ts.log('Saving file: %s' % dataset_filename)
            ds.to_csv(ts.result_file_path(dataset_filename))
            result_params['plot.title'] = dataset_filename.split('.csv')[0]
            ts.result_file(dataset_filename, params=result_params)
        ts.log_error('Test script exception: %s' % traceback.format_exc())

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
            #eut.volt_var(params={'Ena': False})
            eut.close()
        if result_summary is not None:
            result_summary.close()


    return result


def volt_vars_mode_vref_test():
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
    dataset_filename = None

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
        pf_response_time = ts.param_value('vv.test_1_t_r')

        imbalance_fix = ts.param_value('vv.imbalance_fix')

        """
        A separate module has been create for the 1547.1 Standard
        """
        ActiveFunction = p1547.ActiveFunction(ts=ts,
                                              script_name='Volt-Var',
                                              functions=[VV],
                                              criteria_mode=[True, True, True])
        ActiveFunction.set_imbalance_config(imbalance_angle_fix=imbalance_fix)
        ts.log_debug('1547.1 Library configured for %s' % ActiveFunction.get_script_name())

        # Get the rslt parameters for plot
        result_params = ActiveFunction.get_rslt_param_plot()

        '''
        a) Connect the EUT according to the instructions and specifications provided by the manufacturer.
        '''
        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # grid simulator is initialized with test parameters and enabled
        grid = gridsim.gridsim_init(ts, support_interfaces={'hil': chil})  # Turn on AC so the EUT can be initialized
        if grid is not None:
            grid.voltage(v_nom)

        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts, support_interfaces={'hil': chil}) 
        if pv is not None:
            pv.power_set(p_rated)
            pv.power_on()  # Turn on DC so the EUT can be initialized

        # DAS soft channels
        das_points = ActiveFunction.get_sc_points()

        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'], support_interfaces={'hil': chil}) 
        if daq is not None:
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
        # it is assumed the EUT is on
        eut = der.der_init(ts, support_interfaces={'hil': chil}) 
        if eut is not None:
            eut.config()
            ts.log_debug('If not done already, set L/HVRT and trip parameters to the widest range of adjustability.')

        '''
        c) Set all AC test source parameters to the nominal operating voltage and frequency.
        '''
        if grid is not None:
            grid.voltage(v_nom)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)

        result_summary.write(ActiveFunction.get_rslt_sum_col_name())

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
        ts.log_debug(f'imbalance_resp={imbalance_resp}')
        for imbalance_response in imbalance_resp:

            #Default 2 time responses cycles
            #ActiveFunction.reset_time_settings(tr=pf_response_time)

            for vv_curve in vv_curves:

                '''
                 e) Set EUT volt-watt parameters to the values specified by Characteristic 1. All other function be turned off.
                 '''
                ts.log('Starting test with characteristic curve %s' % (vv_curve))
                ActiveFunction.reset_curve(vv_curve)
                ActiveFunction.reset_time_settings(tr=vv_response_time[vv_curve], number_tr=2)
                v_pairs = ActiveFunction.get_params(function=VV, curve=vv_curve)
                ts.log_debug('v_pairs:%s' % v_pairs)
                #Setting up step label
                ActiveFunction.set_step_label(starting_label='G')


                # it is assumed the EUT is on
                if eut is not None:
                    vv_curve_params = {
                            'v': [(v_pairs['V1'] / v_nom) , (v_pairs['V2'] / v_nom) ,
                                  (v_pairs['V3'] / v_nom), (v_pairs['V4'] / v_nom) ],
                            'var': [(v_pairs['Q1'] / s_rated), (v_pairs['Q2'] / s_rated) ,
                                    (v_pairs['Q3'] / s_rated) , (v_pairs['Q4'] / s_rated)],
                            'vref': 1.0,
                            'RmpPtTms': vv_response_time[vv_curve]}
                    ts.log_debug('Sending VV points: %s' % vv_curve_params)
                    eut.volt_var(params={'Ena': True, 'curve': vv_curve_params})

                '''
                f) Verify volt-var mode is reported as active and that the correct characteristic is reported.
                '''
                if eut is not None:
                    ts.log_debug('Initial EUT VV settings are %s' % eut.volt_var())
                ts.log_debug('curve points:  %s' % v_pairs)
                if chil is not None:                        
                    ts.log('Start simulation of CHIL')  
                    chil.start_simulation()
                '''
                g) Wait for steady state to be reached.
    
                Every time a parameter is stepped or ramped, measure and record the time domain current and voltage
                response for at least 4 times the maximum expected response time after the stimulus, and measure or
                derive, active power, apparent power, reactive power, and power factor.
                '''

                step = ActiveFunction.get_step_label()

                daq.sc['event'] = step
                daq.data_sample()
                ts.log('Wait for steady state to be reached')
                ts.sleep(2 * vv_response_time[vv_curve])
                ts.log(imbalance_resp)

                ts.log('Starting imbalance test with VV mode at %s' % (imbalance_response))

                ActiveFunction.set_imbalance_config(imbalance_angle_fix=imbalance_fix)
                #ts.log_debug(f'{imbalance_response}')
                dataset_filename = f'VV_IMB_{imbalance_fix}_{imbalance_response}'

                ActiveFunction.reset_filename(filename=dataset_filename)
                ts.log('------------{}------------'.format(dataset_filename))
                # Start the data acquisition systems
                daq.data_capture(True)

                '''
                h) For multiphase units, step the AC test source voltage to Case A from Table 24.
                '''
                if grid is not None:
                    step_label = ActiveFunction.get_step_label()
                    ts.log('Voltage step: setting Grid simulator to case A (IEEE 1547.1-Table 24)(%s)' % step)
                    ActiveFunction.start(daq=daq, step_label=step_label)
                    v_target = ActiveFunction.set_grid_asymmetric(grid=grid, case='case_a', imbalance_resp=imbalance_response)
                    ts.log_debug(f'v_target={v_target}')
                    step_dict = {'V': v_target}
                    ActiveFunction.record_timeresponse(daq=daq)
                    ActiveFunction.evaluate_criterias(daq=daq, step_dict=step_dict)
                    result_summary.write(ActiveFunction.write_rslt_sum())

                '''
                i) For multiphase units, step the AC test source voltage to VN.
                '''
                if grid is not None:
                    step_label = ActiveFunction.get_step_label()
                    v_target = v_nom
                    ActiveFunction.start(daq=daq, step_label=step_label)
                    ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_nom, step))
                    grid.voltage(v_target)
                    step_dict = {'V': v_target}
                    ActiveFunction.record_timeresponse(daq=daq)
                    ActiveFunction.evaluate_criterias(daq=daq, step_dict=step_dict)
                    result_summary.write(ActiveFunction.write_rslt_sum())

                """
                j) For multiphase units, step the AC test source voltage to Case B from Table 24.
                """
                if grid is not None:
                    step_label = ActiveFunction.get_step_label()
                    ActiveFunction.start(daq=daq, step_label=step_label)
                    ts.log('Voltage step: setting Grid simulator to case B (IEEE 1547.1-Table 24)(%s)' % step)
                    v_target = ActiveFunction.set_grid_asymmetric(grid=grid, case='case_b', imbalance_resp=imbalance_response)
                    step_dict = {'V': v_target}
                    ActiveFunction.record_timeresponse(daq=daq)
                    ActiveFunction.evaluate_criterias(daq=daq, step_dict=step_dict)
                    result_summary.write(ActiveFunction.write_rslt_sum())

                """
                k) For multiphase units, step the AC test source voltage to VN
                """
                if grid is not None:
                    step_label = ActiveFunction.get_step_label()
                    v_target = v_nom
                    ActiveFunction.start(daq=daq, step_label=step_label)
                    ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_nom, step))
                    grid.voltage(v_nom)
                    step_dict = {'V': v_target}
                    ActiveFunction.record_timeresponse(daq=daq)
                    ActiveFunction.evaluate_criterias(daq=daq, step_dict=step_dict)
                    result_summary.write(ActiveFunction.write_rslt_sum())

                ts.log('Sampling complete')
                dataset_filename = dataset_filename + ".csv"
                daq.data_capture(False)
                ds = daq.data_capture_dataset()
                ts.log('Saving file: %s' % dataset_filename)
                ds.to_csv(ts.result_file_path(dataset_filename))
                result_params['plot.title'] = dataset_filename.split('.csv')[0]
                ts.result_file(dataset_filename, params=result_params)
                result = script.RESULT_COMPLETE

    except script.ScriptFail as e:
        reason = str(e)
        if reason:
            ts.log_error(reason)


    except Exception as e:

        if dataset_filename is not None:
            dataset_filename = dataset_filename + ".csv"
            daq.data_capture(False)
            ds = daq.data_capture_dataset()
            ts.log('Saving file: %s' % dataset_filename)
            ds.to_csv(ts.result_file_path(dataset_filename))
            result_params['plot.title'] = dataset_filename.split('.csv')[0]
            ts.result_file(dataset_filename, params=result_params)

        raise

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
            #eut.volt_var(params={'Ena': False})
            #eut.volt_watt(params={'Ena': False})
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
        imbalance_resp=[]
        if mode == 'Vref-test':
            vv_curves['characteristic 1'] = 1
            vv_response_time[1] = ts.param_value('vv.test_1_t_r')
            irr = '100%'
            vref = '100%'
            result = volt_vars_mode_vref_test(vv_curves=vv_curves, vv_response_time=vv_response_time, pwr_lvls=pwr_lvls)

        # Section 5.14.6
        if mode == 'Imbalanced grid':
            if ts.param_value('eut.imbalance_resp') == 'EUT response to the individual phase voltages':
                imbalance_resp.append('INDIVIDUAL_PHASES_VOLTAGES')
            elif ts.param_value('eut.imbalance_resp') == 'EUT response to the average of the three-phase effective (RMS)':
                imbalance_resp.append('AVG_3PH_RMS')
            else:  # 'EUT response to the positive sequence of voltages'
                imbalance_resp.append('POSITIVE_SEQUENCE_VOLTAGES')

            vv_curves.append(1)
            vv_response_time[1] = ts.param_value('vv.test_1_t_r')

            result = volt_var_mode_imbalanced_grid(imbalance_resp=imbalance_resp,
                                                   vv_curves=vv_curves,
                                                   vv_response_time=vv_response_time )

        # Normal volt-var test (Section 5.14.4)
        else:
            irr = ts.param_value('vv.irr')
            vref = ts.param_value('vv.vref')
            v_nom = ts.param_value('eut.v_nom')
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
                v_ref_value = [1.0]
            else:
                v_ref_value = [1.0, 0.95, 1.05]

            result = volt_vars_mode(vv_curves=vv_curves, vv_response_time=vv_response_time,
                                    pwr_lvls=pwr_lvls, v_ref_value=v_ref_value)

    except script.ScriptFail as e:
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
        ts.result(result)
        if result == script.RESULT_FAIL:
            rc = 1

    except Exception as e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)


info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.4.3')

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
           default='not_fix', values=['not_fix', 'fix_ang', 'fix_mag', 'std'], active='vv.mode', active_value=['Imbalanced grid'])

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
info.param('eut.f_nom', label='Nominal AC frequency (Hz)', default=60.0)
info.param('eut.f_max', label='Maximum frequency in the continuous operating region (Hz)', default=66.)
info.param('eut.f_min', label='Minimum frequency in the continuous operating region (Hz)', default=56.)
info.param('eut.imbalance_resp', label='EUT response to phase imbalance is calculated by:',
           default='EUT response to the average of the three-phase effective (RMS)',
           values=['EUT response to the individual phase voltages',
                   'EUT response to the average of the three-phase effective (RMS)',
                   'EUT response to the positive sequence of voltages'])



# Other equipment parameters
der.params(info)
gridsim.params(info)
pvsim.params(info)
das.params(info)
hil.params(info)

# Add the SIRFN logo
info.logo('sirfn.png')

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