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
from svpelab import p1547
from datetime import datetime, timedelta
import script
import math
import numpy as np
import collections
import cmath






def volt_watt_mode(vw_curves, vw_response_time, pwr_lvls):

    result = script.RESULT_FAIL
    daq = None
    data = None
    p_rated = None
    v_nom = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None
    dataset_filename = None


    try:

        p_rated = ts.param_value('eut.p_rated')
        s_rated = ts.param_value('eut.s_rated')

        # DC voltages
        v_in_nom = ts.param_value('eut.v_in_nom')
        v_min_in = ts.param_value('eut.v_in_min')
        v_max_in = ts.param_value('eut.v_in_max')

        # AC voltages
        v_nom = ts.param_value('eut.v_nom')
        v_min = ts.param_value('eut.v_low')
        v_max = ts.param_value('eut.v_high')
        p_min = ts.param_value('eut.p_min')
        phases = ts.param_value('eut.phases')

        # EUI Absorb capabilities
        absorb = {}
        absorb['ena'] = ts.param_value('eut_vw.sink_power')
        absorb['p_rated_prime'] = ts.param_value('eut_vw.p_rated_prime')
        absorb['p_min_prime'] = ts.param_value('eut_vw.p_min_prime')

        """
        A separate module has been create for the 1547.1 Standard
        """
        lib_1547 = p1547.module_1547(ts=ts, aif='VW', absorb=absorb)
        ts.log_debug("1547.1 Library configured for %s" % lib_1547.get_test_name())

        # result params
        result_params = lib_1547.get_rslt_param_plot()

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
        # TODO : add to library 1547
        das_points = {'sc': ('P_TARGET', 'P_TARGET_MIN', 'P_TARGET_MAX', 'P_MEAS', 'V_TARGET','V_MEAS','event')}

        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])
        if daq is not None:
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
                'L/HVRT and trip parameters set to the widest range : v_min: {0} V, v_max: {1} V'.format(v_min, v_max))
            try:
                eut.vrt_stay_connected_high(
                    params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000, 'V1': v_max, 'Tms2': 0.16, 'V2': v_max})
            except Exception, e:
                ts.log_error('Could not set VRT Stay Connected High curve. %s' % e)
            try:
                eut.vrt_stay_connected_low(
                    params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000, 'V1': v_min, 'Tms2': 0.16, 'V2': v_min})
            except Exception, e:
                ts.log_error('Could not set VRT Stay Connected Low curve. %s' % e)
        else:
            ts.log_debug('Set L/HVRT and trip parameters set to the widest range of adjustability possible.')

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
        result_summary.write(lib_1547.get_rslt_sum_col_name())



        '''
        v) Test may be repeated for EUT's that can also absorb power using the P' values in the characteristic
        definition.
        '''
        # TODO: add P' tests (Like CPF -> for absorb_power in absorb_powers:)

        '''
        u) Repeat steps d) through u) for characteristics 2 and 3.
        '''
        for vw_curve in vw_curves:
            ts.log('Starting test with characteristic curve %s' % (vw_curve))
            v_pairs = lib_1547.get_params(curve=vw_curve)
            a_v = lib_1547.MSA_V * 1.5
            '''
            t) Repeat steps d) through t) at EUT power set at 20% and 66% of rated power.
            '''
            for power in pwr_lvls:
                '''
                d) Adjust the EUT's available active power to Prated. For an EUT with an input voltage range, set the input
                voltage to Vin_nom. The EUT may limit active power throughout the test to meet reactive power requirements.
                For an EUT with an input voltage range.
                '''
                if pv is not None:
                    pv_power_setting = (p_rated * power)
                    pv.iv_curve_config(pmp=pv_power_setting, vmp=v_in_nom)
                    pv.irradiance_set(1000.)

                # Special considerations for CHIL ASGC/Typhoon startup #
                if chil is not None:
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
                e) Set EUT volt-watt parameters to the values specified by Characteristic 1. All other functions should
                   be turned off.
                '''
                if eut is not None:
                    # TODO : remove vw_curve unit
                    vw_curve_units = ts.param_value('vw.vw_curve_units')
                    vw_curve_params = {'v': [int(v_pairs['V1']*(100./v_nom)),
                                             int(v_pairs['V2']*(100./v_nom))],
                                       'w': [int(v_pairs['P1']*(100./p_rated)),
                                             int(v_pairs['P2']*(100./p_rated))],
                                       'DeptRef': 'W_MAX_PCT'}

                    vw_params = {'Ena': True, 'ActCrv': 1, 'curve': vw_curve_params}
                    ts.log_debug('Writing the following params to EUT: %s' % vw_params)
                    eut.volt_watt(params=vw_params)
                    eut.volt_var(params={'Ena': False})
                    eut.fixed_pf(params={'Ena': False})
                    '''
                    f) Verify volt-watt mode is reported as active and that the correct characteristic is reported.
                    '''
                    ts.log_debug('Initial EUT VW settings are %s' % eut.volt_watt())

                '''
                g) Begin the adjustment towards V_h. Step the AC test source voltage to a_v below V_1.

                STD_CHANGE: When V2 >= VH, some steps should be skipped.
                k) If V2 is less than VH, step the AC test source voltage to av above V2, else skip to step o).

                JAY NOTE: VRT requirements are such that VH should always be larger than V2 (1.1 pu). DER will operate
                within the 0.88 - 1.1 pu range continuously.
                '''
                v_steps_dict = collections.OrderedDict()
                v_steps_dict["Step G"] = v_pairs['V1'] - a_v
                v_steps_dict["Step H"] = v_pairs['V1'] + a_v
                v_steps_dict["Step I"] = (v_pairs['V2'] + v_pairs['V1']) / 2
                v_steps_dict["Step J"] = v_pairs['V2'] - a_v
                if v_pairs['V2'] < v_max:
                    v_steps_dict["Step K"] = v_pairs['V2'] + a_v
                    v_steps_dict["Step L"] = v_max - a_v
                    v_steps_dict["Step M"] = v_pairs['V2'] + a_v
                    v_steps_dict["Step N"] = v_pairs['V2'] - a_v
                v_steps_dict["Step O"] = (v_pairs['V1'] + v_pairs['V2']) / 2
                v_steps_dict["Step P"] = v_pairs['V1'] + a_v
                v_steps_dict["Step Q"] = v_pairs['V1'] - a_v
                # STD_CHANGE: Duplicated step R. Step R was changed for v_min + a_v
                # v_steps_dict["Step R"] = v_min + a_v
                # STD_CHANGE: Duplicated step R. Step S was changed for v_nom
                # JAY NOTE: Agreed. Delete step R. Don't return to V_nom because this will be done in the next loop.
                v_steps_dict["Step S"] = v_min + a_v

                # Ensure voltage step doesn't exceed the EUT boundaries and round V to 2 decimal places
                for step, voltage in v_steps_dict.iteritems():
                    v_steps_dict.update({step: np.around(voltage, 2)})
                    if voltage > v_max:
                        ts.log("{0} voltage step (value : {1}) changed to VH (v_max)".format(step, voltage))
                        v_steps_dict.update({step: v_max})
                    elif voltage < v_min:
                        ts.log("{0} voltage step (value : {1}) changed to VL (v_min)".format(step, voltage))
                        v_steps_dict.update({step: v_min})

                ts.log_debug('curve points:  %s' % v_pairs)

                # Configure the data acquisition system
                ts.log('Starting data capture for power = %s' % power)
                dataset_filename = ('VW_{0}_PWR_{1}'.format(vw_curve, power))
                ts.log('------------{}------------'.format(dataset_filename))
                daq.data_capture(True)

                for step_label, v_step in v_steps_dict.iteritems():
                    ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_step, step_label))
                    p_initial = lib_1547.get_initial(daq=daq, step=step_label)
                    if grid is not None:
                        grid.voltage(v_step)
                    v_p_analysis = lib_1547.criteria(daq=daq,
                                                     tr=vw_response_time[vw_curve],
                                                         step=step_label,
                                                         initial_value=p_initial,
                                                         target=v_step,
                                                         curve =vw_curve,
                                                         pwr_lvl=power)
                    result_summary.write(lib_1547.write_rslt_sum(analysis=v_p_analysis, step=step_label,
                                                                 filename=dataset_filename))
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
            eut.volt_watt(params={'Ena': False, 'ActCrv': 0})
            eut.close()
        if result_summary is not None:
            result_summary.close()


def volt_watt_mode_imbalanced_grid(imbalance_resp, vw_curves, vw_response_time):

    result = script.RESULT_FAIL
    daq = None
    p_rated = None
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
        imbalance_fix = ts.param_value('vw.imbalance_fix')


        # EUI Absorb capabilities
        absorb = {}
        absorb['ena'] = ts.param_value('eut_vw.sink_power')
        absorb['p_rated_prime'] = ts.param_value('eut_vw.p_rated_prime')
        absorb['p_min_prime'] = ts.param_value('eut_vw.p_min_prime')

        """
        A separate module has been create for the 1547.1 Standard
        """
        lib_1547 = p1547.module_1547(ts=ts, aif='VW', imbalance_angle_fix=imbalance_fix)
        ts.log_debug('1547.1 Library configured for %s' % lib_1547.get_test_name())

        # Get the rslt parameters for plot
        result_params = lib_1547.get_rslt_param_plot()



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
        # TODO : add to library 1547
        das_points = {'sc': ('P_TARGET', 'P_TARGET_MIN', 'P_TARGET_MAX', 'P_MEAS', 'V_TARGET', 'V_MEAS', 'event')}

        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])
        if daq is not None:
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
                'L/HVRT and trip parameters set to the widest range : v_min: {0} V, v_max: {1} V'.format(v_min, v_max))
            try:
                eut.vrt_stay_connected_high(
                    params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000, 'V1': v_max, 'Tms2': 0.16, 'V2': v_max})
            except Exception, e:
                ts.log_error('Could not set VRT Stay Connected High curve. %s' % e)
            try:
                eut.vrt_stay_connected_low(
                    params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000, 'V1': v_min, 'Tms2': 0.16, 'V2': v_min})
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

        '''
        c) Set all AC test source parameters to the nominal operating voltage and frequency.
        '''
        if grid is not None:
            grid.voltage(v_nom)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)

        result_summary.write('P_TR_ACC_REQ, TR_REQ, P_FINAL_ACC_REQ, V_MEAS, P_MEAS, P_TARGET, P_TARGET_MIN, '
                             'P_TARGET_MAX, STEP, FILENAME\n')

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
                e) Set EUT volt-watt parameters to the values specified by Characteristic 1. All other function be
                turned off.
                '''
                if eut is not None:
                    eut.volt_var(params={'Ena': False})
                    eut.fixed_pf(params={'Ena': False})
                v_pairs = lib_1547.get_params(curve=vw_curve)


                # it is assumed the EUT is on
                eut = der.der_init(ts)
                if eut is not None:
                    vw_curve_params = {'v': [int(v_pairs['V1'] * (100. / v_nom)),
                                             int(v_pairs['V2'] * (100. / v_nom))],
                                       'w': [int(v_pairs['P1'] * (100. / p_rated)),
                                             int(v_pairs['P2'] * (100. / p_rated))],
                                       'DeptRef': 'W_MAX_PCT'}
                    vw_params = {'Ena': True, 'ActCrv': 1, 'curve': vw_curve_params}
                    '''
                    f) Verify volt-watt mode is reported as active and that the correct characteristic is reported
                    '''
                    eut.volt_watt(params=vw_params)
                    # eut.volt_var(params={'Ena': True})
                    ts.log_debug('Initial EUT VW settings are %s' % eut.volt_watt())
                    ts.log_debug('curve points:  %s' % v_pairs)

                    # STD_CHANGE: Remove step g) or add more information about the volt-var configuration.
                    # Jay NOTE: Not sure if the committee is trying to test asymmetric VW/VV response here, but most
                    # likely a typo since this is tested in VV section

                    '''
                    g) Verify volt-var mode is reported as active and that the correct characteristic is reported.
                    '''
                    ts.log('volt-var settings: %s' % eut.volt_var())

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
                    p_initial = lib_1547.get_initial(daq=daq, step=step)
                    lib_1547.set_grid_asymmetric(grid=grid, case='case_a')
                    v_p_analysis = lib_1547.criteria(   daq=daq,
                                                        tr=vw_response_time[vw_curve],
                                                        step=step,
                                                        initial_value=p_initial,
                                                        curve=vw_curve)

                    result_summary.write(lib_1547.write_rslt_sum(analysis=v_p_analysis, step=step,
                                                                 filename=dataset_filename))

                '''
                Step j) For multiphase units, step the AC test source voltage to VN.
                '''
                if grid is not None:
                    step = 'Step J'
                    ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_nom, step))
                    p_initial = lib_1547.get_initial(daq=daq, step=step)
                    grid.voltage(v_nom)
                    v_p_analysis = lib_1547.criteria(   daq=daq,
                                                        tr=vw_response_time[vw_curve],
                                                        step=step,
                                                        initial_value=p_initial,
                                                        curve=vw_curve)
                    result_summary.write(lib_1547.write_rslt_sum(analysis=v_p_analysis, step=step,
                                                                 filename=dataset_filename))

                '''
                Step k) For multiphase units, step the AC test source voltage to Case B from Table 24
                '''
                if grid is not None:
                    step = 'Step K'
                    ts.log('Voltage step: setting Grid simulator to case B (IEEE 1547.1-Table 24)(%s)' % step)
                    p_initial = lib_1547.get_initial(daq=daq, step=step)
                    lib_1547.set_grid_asymmetric(grid=grid, case='case_b')
                    v_p_analysis = lib_1547.criteria(daq=daq,
                                                     tr=vw_response_time[vw_curve],
                                                     step=step,
                                                     initial_value=p_initial,
                                                     curve=vw_curve)

                    result_summary.write(lib_1547.write_rslt_sum(analysis=v_p_analysis, step=step,
                                                                 filename=dataset_filename))

                '''
                Step l) For multiphase units, step the AC test source voltage to VN.
                '''
                if grid is not None:
                    step = 'Step L'
                    ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_nom, step))
                    p_initial = lib_1547.get_initial(daq=daq, step=step)
                    grid.voltage(v_nom)
                    v_p_analysis = lib_1547.criteria(daq=daq,
                                                     tr=vw_response_time[vw_curve],
                                                     step=step,
                                                     initial_value=p_initial,
                                                     curve=vw_curve)
                    result_summary.write(lib_1547.write_rslt_sum(analysis=v_p_analysis, step=step,
                                                                 filename=dataset_filename))


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

        # Initialize VW EUT specified parameters variables
        mode = ts.param_value('vw.mode')
        """
        Test Configuration
        """
        # list of active tests
        vw_curves = []
        imbalance_resp = None
        vw_response_time = [0, 0, 0, 0]
        if mode == 'Imbalanced grid':
            if ts.param_value('eut.imbalance_resp') == 'EUT response to the individual phase voltages':
                imbalance_resp = ['INDIVIDUAL_PHASES_VOLTAGES']
            elif ts.param_value('eut.imbalance_resp') == 'EUT response to the average of the three-phase effective (RMS)':
                imbalance_resp = ['AVG_3PH_RMS']
            else:  # 'EUT response to the positive sequence of voltages'
                imbalance_resp = ['POSITIVE_SEQUENCE_VOLTAGES']

            vw_curves.append(1)
            vw_response_time[1] = float(ts.param_value('vw.test_1_tr'))

        else:
            if ts.param_value('vw.test_1') == 'Enabled':
                vw_curves.append(1)
                vw_response_time[1] = float(ts.param_value('vw.test_1_tr'))
            if ts.param_value('vw.test_2') == 'Enabled':
                vw_curves.append(2)
                vw_response_time[2] = float(ts.param_value('vw.test_2_tr'))
            if ts.param_value('vw.test_3') == 'Enabled':
                vw_curves.append(3)
                vw_response_time[3] = float(ts.param_value('vw.test_3_tr'))

        # List of power level for tests
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
            result = volt_watt_mode_imbalanced_grid(imbalance_resp=imbalance_resp, vw_curves=vw_curves,
                                                    vw_response_time=vw_response_time)
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

info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.2.0')

# VW test parameters
info.param_group('vw', label='Test Parameters')
info.param('vw.mode', label='Volt-Watt mode', default='Normal', values=['Normal', 'Imbalanced grid'])
info.param('vw.test_1', label='Characteristic 1 curve', default='Enabled', values=['Disabled', 'Enabled'],
           active='vw.mode', active_value=['Normal', 'Imbalanced grid'])
info.param('vw.test_1_tr', label='Response time (s) for curve 1', default=10.0,
           active='vw.test_1', active_value=['Enabled'])
info.param('vw.test_2', label='Characteristic 2 curve', default='Enabled', values=['Disabled', 'Enabled'],
           active='vw.mode', active_value=['Normal'])
info.param('vw.test_2_tr', label='Response time (s) for curve 2', default=90.0,
           active='vw.test_2', active_value=['Enabled'])
info.param('vw.test_3', label='Characteristic 3 curve', default='Enabled', values=['Disabled', 'Enabled'],
           active='vw.mode', active_value=['Normal'])
info.param('vw.test_3_tr', label='Response time (s) for curve 3', default=0.5,
           active='vw.test_3', active_value=['Enabled'])
info.param('vw.power_lvl', label='Power Levels', default='All', values=['100%', '66%', '20%', 'All'],
           active='vw.mode', active_value=['Normal'])
info.param('vw.imbalance_fix', label='Use minimum fix requirements from Table 24?',
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
info.param('eut.f_nom', label='Nominal AC frequency (Hz)', default=60.0)
info.param('eut.f_max', label='Maximum frequency in the continuous operating region (Hz)', default=66.)
info.param('eut.f_min', label='Minimum frequency in the continuous operating region (Hz)', default=56.)
info.param('eut.imbalance_resp', label='EUT response to phase imbalance is calculated by:',
           default='EUT response to the average of the three-phase effective (RMS)',
           values=['EUT response to the individual phase voltages',
                   'EUT response to the average of the three-phase effective (RMS)',
                   'EUT response to the positive sequence of voltages'])

# EUT VW parameters
info.param_group('eut_vw', label='VW - EUT Parameters', glob=True)
info.param('eut_vw.sink_power', label='Can DER absorb active power?', default='No',
           values=['No', 'Yes'])
info.param('eut_vw.p_rated_prime', label='P\'rated: Output power rating while absorbing power (W) (negative)',
           default=-3000.0, active='eut_vw.sink_power', active_value=['Yes'])
info.param('eut_vw.p_min_prime', label='P\'min: minimum active power while sinking power(W) (negative)',
           default=-0.2*3000.0, active='eut_vw.sink_power', active_value=['Yes'])

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
