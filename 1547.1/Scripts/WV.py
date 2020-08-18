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

WV = 'WV'  # Watt-Var

def watt_var_mode(wv_curves, wv_response_time, pwr_lvls):

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

        # EUI Absorb capabilities
        absorb = {}
        absorb['ena'] = ts.param_value('eut_cpf.sink_power')

        """
        A separate module has been create for the 1547.1 Standard
        """
        #lib_1547 = p1547.module_1547(ts=ts, aif='WV', criteria)
        ActiveFunction = p1547.ActiveFunction(ts=ts,
                                              functions=[WV],
                                              script_name='Watt-Var',
                                              criteria_mode=[True, True, True])
        ts.log_debug("1547.1 Library configured for %s" % ActiveFunction.get_script_name())

        # result params
        result_params = ActiveFunction.get_rslt_param_plot()

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
        das_points = ActiveFunction.get_sc_points()

        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])

        ts.log_debug(0.05 * ts.param_value('eut.s_rated'))
        daq.sc['P_TARGET'] = v_nom
        daq.sc['Q_TARGET'] = 100
        daq.sc['Q_TARGET_MIN'] = 100
        daq.sc['Q_TARGET_MAX'] = 100
        daq.sc['event'] = 'None'

        ts.log('DAS device: %s' % daq.info())

        '''
        b) Set all voltage trip parameters to the widest range of adjustability.  Disable all reactive/active power
        control functions.
        '''

        eut = der.der_init(ts)
        if eut is not None:
            eut.config()
            ts.log_debug(eut.measurements())

            #Disable all functions on EUT
            eut.deactivate_all_fct()

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
        grid = gridsim.gridsim_init(ts, support_interfaces={'hil': chil})  # Turn on AC so the EUT can be initialized
        if grid is not None:
            grid.voltage(v_nom)

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
        dd) Repeat steps e) through dd) for characteristics 2 and 3.
        '''

        #TODO 1.Add absorb option possibility for EUT
        #TODO 2.Add communication with EUT

        for wv_curve in wv_curves:
            ts.log('Starting test with characteristic curve %s' % (wv_curve))
            ActiveFunction.reset_curve(wv_curve)
            ActiveFunction.reset_time_settings(tr=wv_response_time[wv_curve], number_tr=2)
            p_pairs = ActiveFunction.get_params(function=WV, curve=wv_curve)
            '''
            d2) Set EUT volt-var parameters to the values specified by Characteristic 1.
            All other function should be turned off. Turn off the autonomously adjusting reference voltage.
            '''
            if eut is not None:
                # Activate watt-var function with following parameters
                # SunSpec convention is to use percentages for P and Q points.
                wv_curve_params = {'w': [p_pairs['P0']*(100/p_rated),
                                         p_pairs['P1']*(100/p_rated),
                                         p_pairs['P2']*(100/p_rated),
                                         p_pairs['P3']*(100/p_rated)],
                                   'var': [p_pairs['Q0']*(100/var_rated),
                                           p_pairs['Q1']*(100/var_rated),
                                           p_pairs['Q2']*(100/var_rated),
                                           p_pairs['Q3']*(100/var_rated)]}
                ts.log_debug('Sending WV points: %s' % wv_curve_params)
                eut.watt_var(params={'Ena': True, 'curve': wv_curve_params})


                '''
                e) Verify volt-var mode is reported as active and that the correct characteristic is reported.
                '''
                ts.log_debug('Initial EUT VV settings are %s' % eut.watt_var())

            '''
            cc) Repeat test steps d) through cc) at EUT power set at 20% and 66% of rated power.
            '''
            for power in pwr_lvls:
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

                #Create Watt-Var Dictionary
                p_steps_dict = ActiveFunction.create_wv_dict_steps()

                filename = 'WV_%s_PWR_%d' % (wv_curve, power * 100)
                ActiveFunction.reset_filename(filename=filename)
                ts.log('------------{}------------'.format(dataset_filename))

                # Start the data acquisition systems
                daq.data_capture(True)

                for step_label, p_step in p_steps_dict.items():
                    ts.log('Power step: setting Grid power to %s (W)(%s)' % (p_step, step_label))
                    ActiveFunction.start(daq=daq, step_label=step_label)
                    step_dict = {'V': v_nom, 'P': p_step}
                    if pv is not None:
                        pv.power_set(step_dict['P'])

                    ActiveFunction.record_timeresponse(daq=daq, step_dict=step_dict)
                    ActiveFunction.evaluate_criterias()
                    result_summary.write(ActiveFunction.write_rslt_sum())

                ts.log('Sampling complete')
                dataset_filename = filename + ".csv"
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
            pv.power_set(p_rated)
            pv.close()
        if grid is not None:
            if v_nom is not None:
                grid.voltage(v_nom)
            grid.close()
        if chil is not None:
            chil.close()
        if eut is not None:
            eut.deactivate_all_fct()
            eut.close()
        if result_summary is not None:
            result_summary.close()

    return result


def test_run():

    result = script.RESULT_FAIL

    try:
        """
        Test Configuration
        """
        # list of active tests
        wv_curves = []
        wv_response_time = [0, 0, 0, 0]

        irr = ts.param_value('eut_wv.irr')

        if ts.param_value('eut_wv.test_1') == 'Enabled':
            wv_curves.append(1)
            wv_response_time[1] = ts.param_value('eut_wv.test_1_t_r')
        if ts.param_value('eut_wv.test_2') == 'Enabled':
            wv_curves.append(2)
            wv_response_time[2] = ts.param_value('eut_wv.test_2_t_r')
        if ts.param_value('eut_wv.test_3') == 'Enabled':
            wv_curves.append(3)
            wv_response_time[3] = ts.param_value('eut_wv.test_3_t_r')

        # List of power level for tests
        if irr == '20%':
            pwr_lvls = [0.20]
        elif irr == '66%':
            pwr_lvls = [0.66]
        elif irr == '100%':
            pwr_lvls = [1.]
        else:
            pwr_lvls = [1., 0.66, 0.20]

        result = watt_var_mode(wv_curves=wv_curves, wv_response_time=wv_response_time,
                                pwr_lvls=pwr_lvls)

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


info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.3.0')

# VV test parameters
info.param_group('eut_wv', label='Test Parameters')
info.param('eut_wv.mode', label='Watt-Vat mode', default='Normal', values=['Normal'])
info.param('eut_wv.test_1', label='Characteristic 1 curve', default='Enabled', values=['Disabled', 'Enabled'],
           active='eut_wv.mode', active_value=['Normal'])
info.param('eut_wv.test_1_t_r', label='Response time (s) for curve 1', default=10.0,
           active='eut_wv.test_1', active_value=['Enabled'])
info.param('eut_wv.test_2', label='Characteristic 2 curve', default='Enabled', values=['Disabled', 'Enabled'],
           active='eut_wv.mode', active_value=['Normal'])
info.param('eut_wv.test_2_t_r', label='Settling time min (t) for curve 2', default=1.0,
           active='eut_wv.test_2', active_value=['Enabled'])
info.param('eut_wv.test_3', label='Characteristic 3 curve', default='Enabled', values=['Disabled', 'Enabled'],
           active='eut_wv.mode', active_value=['Normal'])
info.param('eut_wv.test_3_t_r', label='Settling time max (t) for curve 3', default=90.0,
           active='eut_wv.test_3', active_value=['Enabled'])
info.param('eut_wv.irr', label='Power Levels iteration', default='All', values=['100%', '66%', '20%', 'All'],
           active='eut_wv.mode', active_value=['Normal'])
info.param('eut_wv.p_prime_mode', label='Repeat Test with P(prime) value if EUT able to absorb', default='No',
           values=['Yes', 'No'], active='eut.abs_enable', active_value=['Yes'])

# EUT general parameters
info.param_group('eut', label='EUT Parameters', glob=True)
info.param('eut.phases', label='Phases', default='Three phase', values=['Single phase', 'Split phase', 'Three phase'])
info.param('eut.s_rated', label='Apparent power rating (VA)', default=10000.0)
info.param('eut.p_rated', label='Output power rating (W)', default=8000.0)
info.param('eut.p_min', label='Minimum Power Rating(W)', default=1000.)
info.param('eut.abs_enable', label='EUT able to absorb power?', default='No', values=['Yes', 'No'])
info.param('eut.var_rated', label='Output var rating (vars)', default=2000.0)
info.param('eut.v_nom', label='Nominal AC voltage (V)', default=120.0, desc='Nominal voltage for the AC simulator.')
info.param('eut.v_low', label='Minimum AC voltage (V)', default=116.0)
info.param('eut.v_high', label='Maximum AC voltage (V)', default=132.0)
info.param('eut.v_in_nom', label='V_in_nom: Nominal input voltage (Vdc)', default=400)


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
