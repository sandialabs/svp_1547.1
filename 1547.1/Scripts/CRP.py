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
    result_params = None

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
        response_time = ts.param_value('crp.response_time')

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

        # get target q relative value
        q_targets = {}
        if ts.param_value('crp.q_max_abs_enable') == 'Enabled':
            q_targets['crp_q_max_abs'] = float(ts.param_value('crp.q_max_abs_value'))
        if ts.param_value('crp.q_max_inj_enable') == 'Enabled':
            q_targets['crp_q_max_inj'] = float(ts.param_value('crp.q_max_inj_value'))
        if ts.param_value('crp.half_q_max_abs_enable') == 'Enabled':
            q_targets['crp_half_q_max_abs'] = 0.5*float(ts.param_value('crp.q_max_abs_value'))
        if ts.param_value('crp.half_q_max_inj_enable') == 'Enabled':
            q_targets['crp_half_q_max_inj'] = 0.5*float(ts.param_value('crp.q_max_inj_value'))
        ts.log('Evaluating the following Reactive Power Targets: %s' % q_targets)

        v_in_targets = {}
        if v_nom_in_enabled == 'Enabled':
            v_in_targets['v_nom_in'] = v_nom_in
        if v_min_in != v_nom_in and v_min_in_enabled == 'Enabled':
            v_in_targets['v_min_in'] = v_min_in
        if v_max_in != v_nom_in and v_max_in_enabled == 'Enabled':
            v_in_targets['v_max_in'] = v_max_in
        if not v_in_targets:
            raise ts.log_error('No V_in target specify. Please select a V_IN test')

        """
        a) Connect the EUT according to the instructions and specifications provided by the manufacturer.
        """
        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # grid simulator is initialized with test parameters and enabled
        grid = gridsim.gridsim_init(ts, support_interfaces={'hil': chil})  # Turn on AC so the EUT can be initialized
        if grid is not None:
            grid.voltage(v_nom)

        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts)
        if pv is not None:
            pv.power_set(p_rated)
            pv.power_on()  # Turn on DC so the EUT can be initialized
            start_up = 60
            ts.log('Waiting for EUT to power up. Sleeping %s sec.' % start_up)
            ts.sleep(start_up)

        das_points = lib_1547.get_sc_points()  # DAS soft channels
        # initialize data acquisition
        daq = das.das_init(ts, sc_points=das_points['sc'], support_interfaces={'pvsim': pv, 'hil': chil})
        if daq is not None:
            daq.sc['V_MEAS'] = None
            daq.sc['P_MEAS'] = None
            daq.sc['Q_MEAS'] = None
            daq.sc['Q_TARGET_MIN'] = None
            daq.sc['Q_TARGET_MAX'] = None
            daq.sc['PF_TARGET'] = None
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
            eut.volt_var(params={'Ena': False})  # disable volt/var curve
            eut.watt_var(params={'Ena': False})
            eut.volt_watt(params={'Ena': False})
            ts.log_debug('If not done already, set L/HVRT and trip parameters to the widest range of adjustability.')

        # Special considerations for CHIL ASGC/Typhoon startup #
        if chil is not None:
            if chil.hil_info()['mode'] == 'Typhoon':
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
        v) Steps d) through s) may be repeated to test additional protocols methods. (Rerun script in those cases)
        
        u) For an EUT with an input voltage range, repeat steps d) through t) for Vin_min and Vin_max
        """
        # For PV systems, this requires that Vmpp = Vin_nom and Pmpp = Prated.
        for v_in_label, v_in in v_in_targets.items():
            ts.log('Starting test %s at v_in = %s' % (v_in_label, v_in))
            a_v = lib_1547.MRA_V * 1.5
            if pv is not None:
                pv.iv_curve_config(pmp=p_rated, vmp=v_in)
                pv.irradiance_set(1000.)
                ts.sleep(60.)  # Give EUT time to track new I-V Curve

            """
            t) Repeat steps d) through s) for additional reactive power settings: Qmax,ab, 0.5Qmax,inj, 0.5Qmax,ab.
            
            d) Adjust the EUT's active power to Prated. For an EUT with an input voltage range, set the input 
               voltage to Vin_nom.  (previously completed)
                
            e) Enable constant power factor mode and set the EUT power factor to PFmin,inj.
            """
            for q_test_name, q_target in q_targets.items():
                dataset_filename = '%s_v=%0.1f' % (q_test_name, v_in)
                ts.log('------------{}------------'.format(dataset_filename))

                q_target *= var_rated
                ts.log('Starting data capture for fixed Q relative = %s' % q_target)
                daq.data_capture(True)  # Start the data acquisition systems
                daq.sc['Q_TARGET'] = q_target

                if eut is not None:
                    parameters = {'Ena': True,
                                  'VArPct_Mod': 1,  # 1 = WMax percentage
                                  'VArWMaxPct': (100.*q_target)/var_rated}
                    ts.log('Parameters set: %s' % parameters)
                    eut.reactive_power(params=parameters)

                """
                f) Verify Constant Var mode is reported as active and that the reactive power setting is reported as 
                Qmax,inj.
                """
                ts.log('Waiting 15 seconds before reading back parameters')
                ts.sleep(15)
                vars_setting = eut.reactive_power()
                ts.log('fixed vars setting read: %s' % vars_setting)

                """
                g) Step the EUT's active power to 20% of Prated or Pmin, whichever is less.
                h) Step the EUT's active power to 5% of Prated or Pmin, whichever is less.
                i) Step the EUT's available active power to Prated.
                j) Step the AC test source voltage to (VL + av).
                k) Step the AC test source voltage to (VH - av).
                l) Step the AC test source voltage to (VL + av).
                m) For multiphase units, step the AC test source voltage to VN.
                n) For multiphase units, step the AC test source voltage to Case A from Table 24.
                o) For multiphase units, step the AC test source voltage to VN.
                p) For multiphase units, step the AC test source voltage to Case B from Table 24.
                q) For multiphase units, step the AC test source voltage to VN.
                """

                lib_1547.set_step_label(starting_label='G')
                crp_dict = collections.OrderedDict()
                crp_dict[lib_1547.get_step_label()] = {'p_pv': min(0.2*p_rated, p_min)}  # G
                crp_dict[lib_1547.get_step_label()] = {'p_pv': min(0.05*p_rated, p_min)}  # H
                crp_dict[lib_1547.get_step_label()] = {'p_pv': p_rated}  # I
                crp_dict[lib_1547.get_step_label()] = {'V': v_min + a_v}  # J
                crp_dict[lib_1547.get_step_label()] = {'V': v_max - a_v}  # K
                crp_dict[lib_1547.get_step_label()] = {'V': v_min + a_v}  # L
                crp_dict[lib_1547.get_step_label()] = {'V': v_nom}  # M
                if imbalance_fix == "Yes":
                    crp_dict[lib_1547.get_step_label()] = {'V': [v_nom*1.07, v_nom*0.91, v_nom*0.91]}  # N
                    crp_dict[lib_1547.get_step_label()] = {'V': v_nom}  # O
                    crp_dict[lib_1547.get_step_label()] = {'V': [v_nom * 0.91, v_nom * 1.07, v_nom * 1.07]}  # P
                    crp_dict[lib_1547.get_step_label()] = {'V': v_nom}  # Q

                for step_label, step_change in crp_dict.items():

                    daq.data_sample()
                    initial_values = lib_1547.get_initial_value(daq=daq, step=step_label)
                    if pv is not None and step_change.get('p_pv') is not None:
                        pwr_lvl = step_change.get('p_pv')
                        ts.log('Power step: setting PV simulator power to %s (%s)' % (pwr_lvl, step))
                        pv.power_set(pwr_lvl)

                    if grid is not None and step_change.get('V') is not None:
                        volt = step_change.get('V')
                        ts.log('Voltage step: setting grid simulator voltage to %s (%s)' % (volt, step))
                        grid.voltage(volt)

                    lib_1547.process_data(
                        daq=daq,
                        tr=response_time,
                        step=step_label,
                        pwr_lvl=1.0,
                        y_target=q_target,
                        initial_value=initial_values,
                        result_summary=result_summary,
                        filename=dataset_filename,
                        number_of_tr=1
                    )

                """
                r) Disable constant reactive power mode. Reactive power should return to zero.
                s) Verify all reactive/active power control functions are disabled.
                """
                if eut is not None:
                    ts.log('Reactive Power disabled. Readback: %s' % eut.reactive_power(params={'Ena': False}))

                step_label = lib_1547.get_step_label()
                ts.log('Waiting %s seconds to get the next Tr data for analysis...' % response_time)
                ts.sleep(response_time)
                daq.data_sample()  # sample new data
                data = daq.data_capture_read()  # Return dataset created from last data capture
                q_meas = lib_1547.get_measurement_total(data=data, type_meas='Q', log=False)
                daq.sc['Q_MEAS'] = q_meas
                daq.sc['Q_TARGET'] = 0.0
                daq.sc['EVENT'] = "{0}_TR_1".format(step_label)
                daq.sc['Q_TARGET_MIN'] = daq.sc['Q_TARGET'] - 1.5 * lib_1547.MRA_Q
                daq.sc['Q_TARGET_MAX'] = daq.sc['Q_TARGET'] + 1.5 * lib_1547.MRA_Q
                if daq.sc['Q_TARGET_MIN'] <= daq.sc['Q_MEAS'] <= daq.sc['Q_TARGET_MAX']:
                    daq.sc['90%_BY_TR=1'] = 'Pass'
                else:
                    daq.sc['90%_BY_TR=1'] = 'Fail'
                ts.log_debug('Disabled CRP: q_min [%s] <= q_meas [%s] <= q_max [%s] = %s' %
                             (daq.sc['Q_TARGET_MIN'], daq.sc['Q_MEAS'], daq.sc['Q_TARGET_MAX'], daq.sc['90%_BY_TR=1']))
                daq.data_sample()

                # 90%_BY_TR=1, V_MEAS, V_TARGET, P_MEAS, P_TARGET, Q_MEAS, Q_TARGET, Q_TARGET_MIN,
                # Q_TARGET_MAX, PF_MEAS, STEP, FILENAME
                row_data = []
                row_data.append(str(daq.sc['90%_BY_TR=1']))
                row_data.append(str(lib_1547.get_measurement_total(data=data, type_meas='V', log=False)))
                row_data.append('None')
                row_data.append(str(lib_1547.get_measurement_total(data=data, type_meas='P', log=False)))
                row_data.append('None')
                row_data.append(str(daq.sc['Q_MEAS']))
                row_data.append(str(daq.sc['Q_TARGET']))
                row_data.append(str(daq.sc['Q_TARGET_MIN']))
                row_data.append(str(daq.sc['Q_TARGET_MAX']))
                row_data.append(str(lib_1547.get_measurement_total(data=data, type_meas='PF', log=False)))
                row_data.append(str(step_label))
                row_data.append(str(dataset_filename))
                row_data_str = ','.join(row_data) + '\n'
                result_summary.write(row_data_str)

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
        rslt.result_workbook(excelfile, ts.results_dir(), ts.result_dir(), ts=ts)
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
info.param('crp.q_max_abs_value', label='Qmax,inj value (pu)', default=-0.44)
info.param('crp.q_max_inj_value', label='Qmax,abs value (pu)', default=0.44)
#info.param('crp.q_max_value', label='Qmax value (vars)', default=4400)
info.param('crp.q_max_abs_enable', label='Qmax,abs activation', default='Enabled', values=['Disabled', 'Enabled'])
info.param('crp.q_max_inj_enable', label='Qmax,inj activation', default='Enabled', values=['Disabled', 'Enabled'])
info.param('crp.half_q_max_abs_enable', label='0.5*Qmax,abs activation', default='Enabled',
           values=['Disabled', 'Enabled'])
info.param('crp.half_q_max_inj_enable', label='0.5*Qmax,inj activation', default='Enabled',
           values=['Disabled', 'Enabled'])

info.param('crp.response_time', label='Response Time (secs)', default=10.0)
info.param('crp.v_in_nom', label='Test V_in_nom', default='Enabled', values=['Disabled', 'Enabled'])
info.param('crp.v_in_min', label='Test V_in_min', default='Enabled', values=['Disabled', 'Enabled'])
info.param('crp.v_in_max', label='Test V_in_max', default='Enabled', values=['Disabled', 'Enabled'])
info.param('crp.imbalance_fix', label='Use minimum fix requirements from table 24?',
           default='Yes', values=['Yes', 'No'])

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
info.param_group('eut_crp', label='CRP - EUT Parameters', glob=True)
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


