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


def watt_var_mode(wv_curves, wv_response_time):

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
        lib_1547 = p1547.module_1547(ts=ts, aif='WV', absorb=absorb)
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

        # DAS soft channels
        das_points = lib_1547.get_sc_points()
        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])
        daq.sc['P_TARGET'] = p_min
        daq.sc['Q_TARGET'] = 100
        daq.sc['Q_TARGET_MIN'] = 100
        daq.sc['Q_TARGET_MAX'] = 100
        daq.sc['event'] = 'None'
        ts.log('DAS device: %s' % daq.info())

        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts)
        if pv is not None:
            pv.power_set(p_rated)
            pv.power_on()  # Turn on DC so the EUT can be initialized
            if callable(getattr(daq, "set_dc_measurement", None)):  # for DAQs that don't natively have dc measurements
                daq.set_dc_measurement(pv)  # send pv obj to daq to get dc measurements
                ts.sleep(0.5)

        eut = der.der_init(ts)
        if eut is not None:
            eut.config()
            ts.log_debug(eut.measurements())

        # Special considerations for CHIL ASGC/Typhoon startup
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
                ts.log_debug('DAS data_read(): %s' % daq.data_read())

        '''
        b) Set all AC test source parameters to the nominal operating voltage and frequency.
        '''
        grid = gridsim.gridsim_init(ts)  # Turn on AC so the EUT can be initialized
        if grid is not None:
            # for HIL-based gridsim objects, link the chil parameters to voltage/frequency simulink parameters
            if callable(getattr(grid, "gridsim_info", None)):
                if grid.gridsim_info()['mode'] == 'Opal':
                    grid.config(hil_object=chil)
            grid.voltage(v_nom)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write(lib_1547.get_rslt_sum_col_name())

        '''
        c) Set all EUT parameters to the rated active power conditions for the EUT.
        '''
        if pv is not None:
            pv.iv_curve_config(pmp=p_rated, vmp=v_in_nom)
            pv.irradiance_set(1000.)
            ts.log('Waiting for EUT to power up. Sleeping 30 sec.')
            ts.sleep(30)

        '''
        d) Set all voltage trip parameters to default settings.
        '''
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

        '''
        aa) Repeat test steps f) through z) at EUT power set at 20% and 66% of rated power
        
        STD CHANGE - This doesn't make sense because the power is changed in the test procedure
        It's likely a copy/paste error from VV and VW tests
        '''

        '''
        e) Set EUT watt-var parameters to the values specified by Characteristic 1. All other functions should 
        be turned off.
        
        Repeat steps f) through aa) for characteristics 2 and 3.
        '''
        # Disable all functions on EUT
        eut.deactivate_all_fct()

        for wv_curve in wv_curves:
            ts.log('Starting test with characteristic curve %s' % wv_curve)
            p_pairs = lib_1547.get_params(curve=wv_curve)

            if eut is not None:
                # Activate watt-var function with following parameters
                # SunSpec convention is to use percentages for P and Q points.
                wv_curve_params = {'w': [p_pairs['P1']*(100./p_rated),
                                         p_pairs['P2']*(100./p_rated),
                                         p_pairs['P3']*(100./p_rated)],
                                   'var': [p_pairs['Q1']*(100./var_rated),
                                           p_pairs['Q2']*(100./var_rated),
                                           p_pairs['Q3']*(100./var_rated)]}
                ts.log_debug('Sending WV points: %s' % wv_curve_params)
                ts.log_debug('Time Constant Set to: %s' % wv_response_time[wv_curve])
                eut.watt_var(params={'Ena': True, 'NPt': 3, 'RmpTms': wv_response_time[wv_curve],
                                     'curve': wv_curve_params})

                '''
                f) Record applicable settings.
                '''
                t_wait = 15
                ts.log('Waiting %s sec before verifying the parameters were set.' % t_wait)
                ts.sleep(t_wait)
                ts.log_debug('Initial EUT WV settings are %s' % eut.watt_var())

            '''
            z) If this EUT can absorb active power, repeat steps g) through y) using PN' values instead of PN.
            '''
            # todo - add this case

            '''
            g) Set the EUT's available active power to Pmin
            h) Begin the adjustment to Prated. Step the EUT's available active power to aP below P1.
            i) Step the EUT's available active power to aP above P1.
            j) Step the EUT's available active power to (P1 + P2)/2.
            k) Step the EUT's available active power to aP below P2.
            l) Step the EUT's available active power to aP above P2.
            m) Step the EUT's available active power to (P2 + P3)/2.
            n) Step the EUT's available active power to aP below P3.
            o) Step the EUT's available active power to aP above P3.
            p) Step the EUT's available active power to Prated.
            q) Begin the return to Pmin. Step the EUT power to aP above P3.
            r) Step the EUT's available active power to aP below P3.
            s) Step the EUT's available active power to (P2 + P3)/2.
            t) Step the EUT's available active power to aP above P2.
            u) Step the EUT's available active power to aP below P2.
            v) Step the EUT's available active power to (P1 + P2)/2. 
            w) Step the EUT's available active power to aP above P1. 
            x) Step the EUT's available active power to aP below P1. 
            y) Step the EUT's available active power to Pmin.
            '''

            p_steps_dict = collections.OrderedDict()
            a_p = lib_1547.MRA_P * 1.5

            lib_1547.set_step_label(starting_label='G')
            p_steps_dict[lib_1547.get_step_label()] = p_min  # G
            p_steps_dict[lib_1547.get_step_label()] = p_pairs['P1'] - a_p  # H
            p_steps_dict[lib_1547.get_step_label()] = p_pairs['P1'] + a_p  # I
            p_steps_dict[lib_1547.get_step_label()] = (p_pairs['P1'] + p_pairs['P2']) / 2  # J
            p_steps_dict[lib_1547.get_step_label()] = p_pairs['P2'] - a_p  # K
            p_steps_dict[lib_1547.get_step_label()] = p_pairs['P2'] + a_p  # L
            p_steps_dict[lib_1547.get_step_label()] = (p_pairs['P2'] + p_pairs['P3']) / 2  # M
            p_steps_dict[lib_1547.get_step_label()] = p_pairs['P3'] - a_p  # N
            p_steps_dict[lib_1547.get_step_label()] = p_pairs['P3'] + a_p  # O
            p_steps_dict[lib_1547.get_step_label()] = p_rated  # P

            # Begin the return to Pmin
            p_steps_dict[lib_1547.get_step_label()] = p_pairs['P3'] + a_p  # Q
            p_steps_dict[lib_1547.get_step_label()] = p_pairs['P3'] - a_p  # R
            p_steps_dict[lib_1547.get_step_label()] = (p_pairs['P2'] + p_pairs['P3']) / 2  # S
            p_steps_dict[lib_1547.get_step_label()] = p_pairs['P2'] + a_p  # T
            p_steps_dict[lib_1547.get_step_label()] = p_pairs['P2'] - a_p  # U
            p_steps_dict[lib_1547.get_step_label()] = (p_pairs['P1'] + p_pairs['P2']) / 2  # V
            p_steps_dict[lib_1547.get_step_label()] = p_pairs['P1'] + a_p  # V
            p_steps_dict[lib_1547.get_step_label()] = p_pairs['P1'] - a_p  # X
            p_steps_dict[lib_1547.get_step_label()] = p_min  # Y

            filename = 'WV_%s' % wv_curve
            ts.log('------------{}------------'.format(filename))

            # Start the data acquisition systems
            daq.data_capture(True)

            for step_label, p_step in p_steps_dict.iteritems():
                ts.log('Power step: setting available power to %s W (%s)' % (p_step, step_label))
                p_initial = lib_1547.get_initial_value(daq=daq, step=step_label)

                step_dict = {'V': v_nom, 'P': p_step}
                if pv is not None:
                    pv.power_set(step_dict['P'])

                # WV requires 2 things to pass the test:
                # 1) After 1*Tr, the Q must be 90% * (Q_final - Q_initial) + Q_initial.
                #    Accuracy requirements are from 1547.1 4.2 with X = Tr, Y = Q(Tr)
                # 2) After 2*Tr, the Q must be within the MRA of the VW curve
                #    Accuracy requirements are from 1547.1 4.2 with X = P_final, Y = Q_final

                lib_1547.process_data(
                    daq=daq,
                    tr=wv_response_time[wv_curve],
                    step=step_label,
                    initial_value=p_initial,
                    curve=wv_curve,
                    pwr_lvl=1.0,
                    x_target=step_dict,
                    result_summary=result_summary,
                    filename=filename,
                    number_of_tr=2
                )

            ts.log('Sampling complete')
            dataset_filename = filename + ".csv"
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

        result = watt_var_mode(wv_curves=wv_curves, wv_response_time=wv_response_time)

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
        ts.result(result)
        if result == script.RESULT_FAIL:
            rc = 1

    except Exception, e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)


info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.3.0')

# VV test parameters
info.param_group('eut_wv', label='Test Parameters')
info.param('eut_wv.mode', label='Watt-Var mode', default='Normal', values=['Normal'])
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
