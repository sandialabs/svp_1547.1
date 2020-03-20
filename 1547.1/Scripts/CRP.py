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
from svpelab import p1547
import script
from svpelab import result as rslt
from datetime import datetime, timedelta

import numpy as np
import collections
import cmath
import math


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
    dataset_filename = None

    try:

        cat = ts.param_value('eut.cat')
        cat2 = ts.param_value('eut.cat2')
        sink_power = ts.param_value('eut.sink_power')
        p_rated = ts.param_value('eut.p_rated')
        p_rated_prime = ts.param_value('eut.p_rated_prime')
        s_rated = ts.param_value('eut.s_rated')
        var_rated = ts.param_value('eut.var_rated')

        # DC voltages
        v_nom_in_enabled = ts.param_value('crp.v_in_nom')
        v_min_in_enabled = ts.param_value('crp.v_in_min')
        v_max_in_enabled = ts.param_value('crp.v_in_max')

        v_nom_in = ts.param_value('eut.v_in_nom')
        v_min_in = ts.param_value('eut_crp.v_in_min')
        v_max_in = ts.param_value('eut_crp.v_in_max')

        # AC voltages
        v_nom = ts.param_value('eut.v_nom')
        v_min = ts.param_value('eut.v_low')
        v_max = ts.param_value('eut.v_high')
        p_min = ts.param_value('eut.p_min')
        p_min_prime = ts.param_value('eut.p_min_prime')
        phases = ts.param_value('eut.phases')
        pf_response_time = ts.param_value('crp.pf_response_time')

        # Pass/fail accuracies
        pf_msa = ts.param_value('eut.pf_msa')

        # Imbalance configuration
        imbalance_fix = ts.param_value('crp.imbalance_fix')

        # EUI Absorb capabilities
        absorb = {}
        absorb['ena'] = ts.param_value('eut_crp.sink_power')
        absorb['p_rated_prime'] = ts.param_value('eut_crp.p_rated_prime')
        absorb['p_min_prime'] = ts.param_value('eut_crp.p_min_prime')

        """
        A separate module has been create for the 1547.1 Standard
        """
        lib_1547 = p1547.module_1547(ts=ts, aif='CRP', absorb=absorb)
        ts.log_debug("1547.1 Library configured for %s" % lib_1547.get_test_name())

        # result params
        result_params = lib_1547.get_rslt_param_plot()


        #get target q relative value
        q_targets = {}

        if ts.param_value('crp.q_max_abs_enable') == 'Enabled':
            q_targets['crp_q_max_abs'] = float(ts.param_value('crp.q_max_abs_value'))
        if ts.param_value('crp.q_max_inj_enable') == 'Enabled':
            q_targets['crp_q_max_inj'] = float(ts.param_value('crp.q_max_inj_value'))
        if ts.param_value('crp.half_q_max_abs_enable') == 'Enabled':
            q_targets['crp_half_q_max_abs'] = 0.5*float(ts.param_value('crp.q_max_abs_value'))
        if ts.param_value('crp.half_q_max_inj_enable') == 'Enabled':
            q_targets['crp_half_q_max_inj'] = 0.5*float(ts.param_value('crp.q_max_inj_value'))

        #get q max value
        #q_max_value = ts.param_value('crp.q_max_value')

        v_in_targets = {}

        if v_nom_in_enabled == 'Enabled':
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
        #das_points = {'sc': ('V_MEAS', 'P_MEAS', 'Q_MEAS', 'Q_TARGET_MIN', 'Q_TARGET_MAX', 'PF_TARGET', 'event')}
        das_points = lib_1547.get_sc_points()

        # initialize data acquisition
        daq = das.das_init(ts, sc_points=das_points['sc'])

        if daq is not None:
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
            #eut.volt_var(params={'Ena': False})
            ts.log_debug('If not done already, set L/HVRT and trip parameters to the widest range of adjustability.')

        # Special considerations for CHIL ASGC/Typhoon startup #
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

        """
        c) Set all AC test source parameters to the nominal operating voltage and frequency.
        """
        if grid is not None:
            grid.voltage(v_nom)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write(lib_1547.get_rslt_sum_col_name())

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
        for v_in_label, v_in in v_in_targets.items():
            ts.log('Starting test %s at v_in = %s' % (v_in_label, v_in))
            a_v = lib_1547.MSA_V * 1.5
            if pv is not None:
                pv.iv_curve_config(pmp=p_rated, vmp=v_in)
                pv.irradiance_set(1000.)

            """
            e) Enable constant power factor mode and set the EUT power factor to PFmin,inj.
            r) Repeat steps d) through o) for additional power factor settings: PFmin,ab, PFmid,inj, PFmid,ab.

            Only the user-selected PF setting will be tested.
            """
            for q_test_name, q_target in q_targets.items():

                # Setting up step label
                lib_1547.set_step_label(starting_label='F')

                q_target *= var_rated

                ts.log('Starting data capture for fixed Q relative = %s' % q_target)

                if imbalance_fix == "Yes":
                    dataset_filename = ('{0}_{1}_FIX'.format(v_in_label.upper(), q_test_name.upper()))
                else:
                    dataset_filename = ('{0}_{1}'.format(v_in_label.upper(), q_test_name.upper()))

                ts.log('------------{}------------'.format(dataset_filename))
                # Start the data acquisition systems
                daq.data_capture(True)

                daq.sc['Q_TARGET'] = q_target

                if eut is not None:
                    parameters = {'Ena': True, 'Q': q_target, 'Wmax': p_rated}
                    ts.log('Parameters set: %s' % parameters)
                    eut.reactive_power(params=parameters)
                    vars_setting = eut.reactive_power(params=parameters)
                    ts.log('fixed vars setting read: %s' % vars_setting)

                """
                f) Verify Constant Var mode is reported as active and that the power factor setting is reported 
                as Qmax,inj.

                """
                step = lib_1547.get_step_label()
                daq.sc['event'] = step
                daq.data_sample()
                ts.log('Wait for steady state to be reached')
                ts.sleep(2 * pf_response_time)

                """
                g) Step the EUT's active power to 20% of Prated or Pmin, whichever is less.
                """
                if pv is not None:
                    step = lib_1547.get_step_label()
                    ts.log('Power step: setting PV simulator power to %s (%s)' % (p_min, step))
                    initial_values = lib_1547.get_initial_value(daq=daq, step=step)
                    if p_rated * 0.2 > p_min:
                        p_target = p_min
                    else:
                        p_target = p_rated * 0.2
                    step_dict = {'V': v_nom, 'P': round(p_target,2), 'Q': q_target}
                    pv.power_set(step_dict['P'])
                    lib_1547.process_data(
                        daq=daq,
                        tr=pf_response_time,
                        step=step,
                        pwr_lvl=1.0,
                        y_target=step_dict,
                        initial_value=initial_values,
                        result_summary=result_summary,
                        filename=dataset_filename
                    )

                """
                h) Step the EUT's active power to 5% of Prated or Pmin, whichever is less.
                """
                if pv is not None:
                    step = lib_1547.get_step_label()
                    ts.log('Power step: setting PV simulator power to %s (%s)' % (p_min, step))
                    initial_values = lib_1547.get_initial_value(daq=daq, step=step)
                    if p_rated * 0.05 > p_min:
                        p_target = p_min
                    else:
                        p_target = p_rated * 0.05
                    step_dict = {'V': v_nom, 'P': round(p_target,2), 'Q': q_target}
                    pv.power_set(step_dict['P'])
                    lib_1547.process_data(
                        daq=daq,
                        tr=pf_response_time,
                        step=step,
                        pwr_lvl=1.0,
                        y_target=step_dict,
                        initial_value=initial_values,
                        result_summary=result_summary,
                        filename=dataset_filename
                    )

                """
                i) Step the EUT's available active power to Prated.
                """
                if pv is not None:
                    step = lib_1547.get_step_label()
                    ts.log('Power step: setting PV simulator power to %s (%s)' % (p_rated, step))
                    initial_values = lib_1547.get_initial_value(daq=daq, step=step)
                    step_dict = {'V': v_nom, 'P': p_rated, 'Q': q_target}
                    pv.power_set(step_dict['P'])
                    lib_1547.process_data(
                        daq=daq,
                        tr=pf_response_time,
                        step=step,
                        pwr_lvl=1.0,
                        y_target=q_target,
                        initial_value=initial_values,
                        result_summary=result_summary,
                        filename=dataset_filename
                    )

                if grid is not None:
                    #   J) Step the AC test source voltage to (VL + av)
                    step = lib_1547.get_step_label()
                    ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % ((v_min + a_v), step))
                    initial_values = lib_1547.get_initial_value(daq=daq, step=step)
                    step_dict = {'V': v_min + a_v, 'P': p_rated, 'Q': q_target}
                    grid.voltage(step_dict['V'])
                    lib_1547.process_data(
                        daq=daq,
                        tr=pf_response_time,
                        step=step,
                        pwr_lvl=1.0,
                        y_target=q_target,
                        initial_value=initial_values,
                        result_summary=result_summary,
                        filename=dataset_filename
                    )


                    #   k) Step the AC test source voltage to (VH - av)
                    step = lib_1547.get_step_label()
                    ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % ((v_max - a_v), step))
                    initial_values = lib_1547.get_initial_value(daq=daq, step=step)
                    step_dict = {'V': v_max - a_v, 'P': p_rated, 'Q': q_target}
                    grid.voltage(step_dict['V'])
                    lib_1547.process_data(
                        daq=daq,
                        tr=pf_response_time,
                        step=step,
                        pwr_lvl=1.0,
                        y_target=step_dict,
                        initial_value=initial_values,
                        result_summary=result_summary,
                        filename=dataset_filename
                    )

                    #   l) Step the AC test source voltage to (VL + av)
                    step = lib_1547.get_step_label()
                    ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % ((v_min + a_v), step))
                    initial_values = lib_1547.get_initial_value(daq=daq, step=step)
                    step_dict = {'V': v_min + a_v, 'P': p_rated, 'Q': q_target}
                    grid.voltage(step_dict['V'])
                    lib_1547.process_data(
                        daq=daq,
                        tr=pf_response_time,
                        step=step,
                        pwr_lvl=1.0,
                        y_target=step_dict,
                        initial_value=initial_values,
                        result_summary=result_summary,
                        filename=dataset_filename
                    )

                    if phases == 'Three phase':
                        #   m) For multiphase units, step the AC test source voltage to VN
                        step = lib_1547.get_step_label()
                        ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_nom, step))
                        initial_values = lib_1547.get_initial_value(daq=daq, step=step)
                        step_dict = {'V': v_nom, 'P': p_rated, 'Q': q_target}
                        grid.voltage(step_dict['V'])
                        lib_1547.process_data(
                            daq=daq,
                            tr=pf_response_time,
                            step=step,
                            pwr_lvl=1.0,
                            y_target=step_dict,
                            initial_value=initial_values,
                            result_summary=result_summary,
                            filename=dataset_filename
                        )

                    '''
                    n) For multiphase units, step the AC test source voltage to Case A from Table 24.
                    '''

                    if grid is not None and phases == 'Three phase':
                        step = lib_1547.get_step_label()
                        ts.log('Voltage step: setting Grid simulator to case A (IEEE 1547.1-Table 24)(%s)' % step)
                        initial_values = lib_1547.get_initial_value(daq=daq, step=step)
                        step_dict = {'V': v_nom*(1.07+0.91+0.91)/3, 'P': p_rated, 'Q': q_target}
                        lib_1547.set_grid_asymmetric(grid=grid, case='case_a')
                        lib_1547.process_data(
                            daq=daq,
                            tr=pf_response_time,
                            step=step,
                            pwr_lvl=1.0,
                            y_target=step_dict,
                            initial_value=initial_values,
                            result_summary=result_summary,
                            filename=dataset_filename
                        )

                    """
                    o) For multiphase units, step the AC test source voltage to VN.
                    """

                    if grid is not None and phases == 'Three phase':
                        step = lib_1547.get_step_label()
                        ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_nom, step))
                        initial_values = lib_1547.get_initial_value(daq=daq, step=step)
                        step_dict = {'V': v_nom, 'P': p_rated, 'Q': q_target}
                        grid.voltage(step_dict['V'])
                        lib_1547.process_data(
                            daq=daq,
                            tr=pf_response_time,
                            step=step,
                            pwr_lvl=1.0,
                            y_target=step_dict,
                            initial_value=initial_values,
                            result_summary=result_summary,
                            filename=dataset_filename
                        )

                    """
                    p) For multiphase units, step the AC test source voltage to Case B from Table 24.
                    """
                    if grid is not None and phases == 'Three phase':
                        step = lib_1547.get_step_label()
                        ts.log('Voltage step: setting Grid simulator to case B (IEEE 1547.1-Table 24)(%s)' % step)
                        initial_values = lib_1547.get_initial_value(daq=daq, step=step)
                        step_dict = {'V': v_nom*(0.91+1.07+1.07)/3, 'P': p_rated, 'Q': q_target}
                        lib_1547.set_grid_asymmetric(grid=grid, case='case_b')
                        lib_1547.process_data(
                            daq=daq,
                            tr=pf_response_time,
                            step=step,
                            pwr_lvl=1.0,
                            y_target=step_dict,
                            initial_value=initial_values,
                            result_summary=result_summary,
                            filename=dataset_filename
                        )

                    """
                    q) For multiphase units, step the AC test source voltage to VN
                    """
                    if grid is not None and phases == 'Three phase':
                        step = lib_1547.get_step_label()
                        ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_nom, step))
                        initial_values = lib_1547.get_initial_value(daq=daq, step=step)
                        step_dict = {'V': v_nom, 'P': p_rated, 'Q': q_target}
                        grid.voltage(step_dict['V'])
                        lib_1547.process_data(
                            daq=daq,
                            tr=pf_response_time,
                            step=step,
                            pwr_lvl=1.0,
                            y_target=step_dict,
                            initial_value=initial_values,
                            result_summary=result_summary,
                            filename=dataset_filename
                        )

                """
                r) Disable constant power factor mode. Power factor should return to unity.
                """
                if eut is not None:
                    parameters = {'Ena': False}
                    #ts.log('PF set: %s' % parameters)
                    eut.fixed_var(params=parameters)
                    var_setting = eut.fixed_var()
                    ts.log('Reactive Power setting read: %s' % vars_setting)
                    daq.sc['event'] = lib_1547.get_step_label()
                    daq.data_sample()
                    ts.sleep(4 * pf_response_time)
                    daq.sc['event'] = 'T_settling_done'
                    daq.data_sample()

                """
                q) Verify all reactive/active power control functions are disabled.
                """
                if eut is not None:
                    ts.log('Reactive/active power control functions are disabled.')
                    # TODO Implement ts.prompt functionality?
                    # meas = eut.measurements()
                    # ts.log('EUT PF is now: %s' % (data.get('AC_PF_1')))
                    # ts.log('EUT Power: %s, EUT Reactive Power: %s' % (meas['W'], meas['VAr']))

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

        if grid is not None:
            grid.close()
        if pv is not None:
            if p_rated is not None:
                pv.power_set(p_rated)
            pv.close()
        if daq is not None:
            daq.close()
        if eut is not None:
            #eut.reactive_power(params={'Ena': False})
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

    except Exception as e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)


info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.3.0')

# CPF test parameters
info.param_group('crp', label='Test Parameters')
info.param('crp.q_max_abs_value', label='Qmax,inj value (pu)', default=-1)
info.param('crp.q_max_inj_value', label='Qmax,abs value (pu)', default=1)
#info.param('crp.q_max_value', label='Qmax value (vars)', default=4400)
info.param('crp.q_max_abs_enable', label='Qmax,abs activation', default='Enabled', values=['Disabled', 'Enabled'])
info.param('crp.q_max_inj_enable', label='Qmax,inj activation', default='Enabled', values=['Disabled', 'Enabled'])
info.param('crp.half_q_max_abs_enable', label='0.5*Qmax,abs activation', default='Enabled', values=['Disabled', 'Enabled'])
info.param('crp.half_q_max_inj_enable', label='0.5*Qmax,inj activation', default='Enabled', values=['Disabled', 'Enabled'])

info.param('crp.pf_response_time', label='PF Response Time (secs)', default=10.0)
info.param('crp.v_in_nom', label='Test V_in_nom', default='Enabled', values=['Disabled', 'Enabled'])
info.param('crp.v_in_min', label='Test V_in_min', default='Enabled', values=['Disabled', 'Enabled'])
info.param('crp.v_in_max', label='Test V_in_max', default='Enabled', values=['Disabled', 'Enabled'])
info.param('crp.imbalance_fix', label='Use minimum fix requirements from table 24 ?', \
           default='No', values=['Yes', 'No'])

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

# EUT CPF parameters
info.param_group('eut_crp', label='CPF - EUT Parameters', glob=True)
info.param('eut_crp.v_in_min', label='V_in_min: Nominal input voltage (Vdc)', default=300)
info.param('eut_crp.v_in_max', label='V_in_max: Nominal input voltage (Vdc)', default=500)
info.param('eut_crp.sink_power', label='Can the EUT sink power, e.g., is it a battery system', default='No',
           values=['No', 'Yes'])
info.param('eut_crp.p_rated_prime', label='P\'rated: Output power rating while sinking power (W) (negative)',
           default=-3000.0, active='eut_crp.sink_power', active_value=['Yes'])
info.param('eut_crp.p_min_prime', label='P\'min: minimum active power while sinking power(W) (negative)',
           default=-0.2 * 3000.0, active='eut_crp.sink_power', active_value=['Yes'])

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


