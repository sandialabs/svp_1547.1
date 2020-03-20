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
    fw_curves = []
    fw_response_time = [0, 0, 0]


    try:
        cat = ts.param_value('eut.cat')
        cat2 = ts.param_value('eut.cat2')
        sink_power = ts.param_value('eut.sink_power')
        p_rated = ts.param_value('eut.p_rated')
        p_rated_prime = ts.param_value('eut.p_rated_prime')
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
        absorb = {}
        absorb['ena'] = ts.param_value('eut_vw.sink_power')
        absorb['p_rated_prime'] = ts.param_value('eut_vw.p_rated_prime')
        absorb['p_min_prime'] = ts.param_value('eut_vw.p_min_prime')

        # AC voltages
        f_nom = ts.param_value('eut.f_nom')
        f_min = ts.param_value('eut.f_min')
        f_max = ts.param_value('eut.f_max')
        p_min = ts.param_value('eut.p_min')
        phases = ts.param_value('eut.phases')
        # EUI FW parameters
        absorb_enable = ts.param_value('eut_fw.sink_power')
        p_rated_prime = ts.param_value('eut_fw.p_rated_prime')
        p_min_prime = ts.param_value('eut_fw.p_min_prime')
        p_small = ts.param_value('eut_fw.p_small')

        if ts.param_value('fw.test_1') == 'Enabled':
            fw_curves.append(1)
            fw_response_time[1] = float(ts.param_value('fw.test_1_tr'))
        if ts.param_value('fw.test_2') == 'Enabled':
            fw_curves.append(2)
            fw_response_time[2] = float(ts.param_value('fw.test_2_tr'))

        # VW parameters
        absorb = {}
        absorb['ena'] = ts.param_value('eut_vw.sink_power')


        # Pass/fail accuracies
        pf_msa = ts.param_value('eut.pf_msa')

        """
        A separate module has been create for the 1547.1 Standard
        """
        lib_1547 = p1547.module_1547(ts=ts, aif='LAP', absorb=absorb)
        ts.log_debug("1547.1 Library configured for %s" % lib_1547.get_test_name())

        # result params
        result_params = lib_1547.get_rslt_param_plot()


        #  Set Test parameter
        act_pwrs = ts.param_value('lap.act_pwr')

        # List of power level for tests
        ts.log_debug('%s' %(act_pwrs))
        if act_pwrs == '0%':
            act_pwrs_limits = [0.0]
        elif act_pwrs == '33%':
            act_pwrs_limits = [0.33]
        elif act_pwrs == '66%':
            act_pwrs_limits = [0.66]
        else:
            act_pwrs_limits = [0.66, 0.33, 0.0]
        # 5.13.2 Procedure asks for three repetitions
        n_iters = list(range(1,int(ts.param_value('lap.iter'))+1))

        # Take the highest value for the steady state wait time
        tr_min = min(ts.param_value('fw.test_1_tr'),ts.param_value('vw.test_1_tr'))
        tr_vw = ts.param_value('vw.test_1_tr')


        """
        a) - Connect the EUT according to the instructions and specifications provided by the manufacturer.
           - Apply the default settings from IEEE std 1547 for voltage-active power mode 
             (Minimum setting of table 10 of IEEE 1547)
           
           - Apply the default settings from frequency droop response in IEE std 1547 for abnormal operating perfomance
             category of the DER
           - Enable voltage active power mode
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
        ts.log(das_points)
        # initialize data acquisition
        daq = das.das_init(ts, sc_points=das_points['sc'])

        if daq is not None:
            ts.log('DAS device: %s' % daq.info())

        eut = der.der_init(ts)

        if eut is not None:
            eut.config()
            # Enable volt/watt curve and configure default settings
            eut.volt_watt(params={'Ena': True,
                                  #'NCrv': 1,
                                  #'NPt': 3,
                                  #'WinTms': 0,
                                  #'RvrtTms': 0,
                                  'curve': {
                                      #'ActPt': 3,
                                      'v': [106, 110],
                                      'w': [100, 0],
                                      'DeptRef': 'W_MAX_PCT',
                                      #'RmpPt1Tms': 10,
                                      'RmpPtTms': 10,
                                      'RmpDecTmm': 0,
                                      'RmpIncTmm': 0}
                                  })
            eut.freq_watt(
                params={
                    'Ena': True,
                    'curve': 1,
                    'dbf': 0.036,
                    'kof': 0.05,
                    'RspTms': 5
                }
            )
            try:
                eut.vrt_stay_connected_high(params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000,
                                                    'V1': v_max, 'Tms2': 0.16, 'V2': v_max})
            except Exception as e:
                ts.log_error('Could not set VRT Stay Connected High curve. %s' % e)
            try:
                eut.frt_stay_connected_high(params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000,
                                                    'Hz1': f_max, 'Tms2': 160, 'Hz2': f_max})
            except Exception as e:
                ts.log_error('Could not set FRT Stay Connected High curve. %s' % e)
            try:
                eut.vrt_stay_connected_low(params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000,
                                                   'V1': v_min, 'Tms2': 0.16, 'V2': v_min})
            except Exception as e:
                ts.log_error('Could not set VRT Stay Connected Low curve. %s' % e)
            try:
                eut.frt_stay_connected_low(params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000,
                                                    'Hz1': f_min, 'Tms2': 160, 'Hz2': f_min})
            except Exception as e:
                ts.log_error('Could not set FRT Stay Connected Low curve. %s' % e)
            #eut.config()
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

        # Configure Grid simulator
        if grid is not None:
            grid.voltage(v_nom)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write(lib_1547.get_rslt_sum_col_name())



        """
        g) Repeat steps b) through f using active power limits of 33% and zero

        h) Repeat steps b) through g) twice for a total of three repetitions
        """


        for n_iter in n_iters :
            for act_pwrs_limit in act_pwrs_limits:
                """
                 b) - Establish nominal operating conditions as specified by the manufacturer at the terminals of the EUT.
                    - Make available sufficient input power for the EUT to reach its rated active power.
                    - Allow (or command) the EUT to reach steady-state output at its rated active power
                    - Begin recording EUT active power
                 """
                ts.log('Starting test no. %s with active power limit to %s ' % (n_iter, act_pwrs_limit))

                # For PV systems, this requires that Vmpp = Vin_nom and Pmpp = Prated.
                if pv is not None:
                    pv.iv_curve_config(pmp=p_rated, vmp=v_nom_in)
                    pv.irradiance_set(1000.)
                ts.log('EUT Config: setting Active Power Limit to 100%')
                if eut is not None:
                    # limit maximum power
                    eut.limit_max_power(params={'MaxLimWEna': True,
                                                'MaxLimW_PCT': 100,
                                                'WinTms': 0,
                                                'RmpTms': 0,
                                                'RvrtTms': 0.0})
                ts.sleep(2 * tr_min)
                daq.data_capture(True)
                filename = ('LAP_{0}_{1}'.format(act_pwrs_limit,n_iter))
                ts.log('------------{}------------'.format(filename))

                """
                c)  - Apply an active power limit to the EUT of 66% of its rated power.
                    - Wait until the EUT active power reaches a new steady state
                """
                # Setting up step label
                lib_1547.set_step_label(starting_label='C')
                step = lib_1547.get_step_label()
                daq.sc['event'] = step
                initial_values = lib_1547.get_initial_value(daq=daq, step=step)
                ts.log('EUT Config: setting Active Power Limit to %s (%s)' % (act_pwrs_limit, step))
                if eut is not None:
                    # limit maximum power
                    eut.limit_max_power(
                        params={
                            'MaxLimWEna': True,
                            'MaxLimW_PCT': act_pwrs_limit*100,
                            'WinTms': 0,
                            'RmpTms': 0,
                            'RvrtTms': 0.0
                        }
                    )
                step_dict = {'V': v_nom, 'F': f_nom}
                target_dict = {'P': act_pwrs_limit}
                lib_1547.process_data(
                    daq=daq,
                    tr=tr_min,
                    step=step,
                    initial_value=initial_values,
                    pwr_lvl=act_pwrs_limit,
                    x_target=step_dict,
                    y_target=target_dict,
                    result_summary=result_summary,
                    filename=filename
                )


                """
                d)  - Reduce the frequency of the AC test to 59 Hz and hold until EUT active power reaches a new steady 
                      state
                    - Return AC test frequency to nominal and Hold until new states reached
                """
                f_steps = [59, f_nom]
                step = lib_1547.get_step_label()
                if grid is not None:
                    for f_step in f_steps:
                        step_ = step + "_" + str(f_step)
                        ts.log('Frequency step: setting Grid simulator frequency to %s (%s)' % (f_step, step_))
                        initial_values = lib_1547.get_initial_value(daq=daq,step=step_)
                        grid.freq(f_step)
                        step_dict = {'V': v_nom, 'F': f_step}
                        #target_dict = {'P': None}
                        lib_1547.process_data(
                            daq=daq,
                            tr=tr_min,
                            step=step_,
                            initial_value=initial_values,
                            pwr_lvl=act_pwrs_limit,
                            x_target=step_dict,
                            #y_target=target_dict,
                            result_summary=result_summary,
                            filename=filename
                        )


                """
                e)  - Increase the frequency of the AC test to 61 Hz and hold until EUT active power reaches a new steady 
                      state
                    - Return AC test frequency to nominal and Hold until new states reached
                """
                f_steps = [61, f_nom]
                step = lib_1547.get_step_label()
                if grid is not None:
                    for f_step in f_steps:
                        step_ = step + "_" + str(f_step)
                        ts.log('Frequency step: setting Grid simulator frequency to %s (%s)' % (f_step, step_))
                        initial_values = lib_1547.get_initial_value(daq=daq,step=step_)
                        grid.freq(f_step)
                        step_dict = {'V': v_nom, 'F': f_step}
                        target_dict = {'P': None}
                        lib_1547.process_data(
                            daq=daq,
                            tr=tr_min,
                            step=step_,
                            initial_value=initial_values,
                            pwr_lvl=act_pwrs_limit,
                            x_target=step_dict,
                            y_target=None, #Calculated directly in P1547 lib
                            result_summary=result_summary,
                            filename=filename
                        )

                """
                f)  - Increase the voltage of the AC test to 1.08 times nominal and hold until EUT active power 
                      reaches a new steady state
                    - Return AC test voltage to nominal and Hold until new states reached
                """
                v_steps = [1.08*v_nom, v_nom]
                step = lib_1547.get_step_label()
                if grid is not None:
                    for v_step in v_steps:
                        step_ = step + "_" + str(v_step)
                        ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (v_step, step_))
                        initial_values = lib_1547.get_initial_value(daq=daq,step=step_)
                        grid.voltage(v_step)
                        lib_1547.process_data(
                            daq=daq,
                            tr=tr_vw,
                            step=step_,
                            initial_value=initial_values,
                            pwr_lvl=act_pwrs_limit,
                            x_target=v_step,
                            y_target=None, #Calculated directly in P1547 lib
                            result_summary=result_summary,
                            filename=filename
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

    except script.ScriptFail as e:
        reason = str(e)
        if reason:
            ts.log_error(reason)

    except Exception as e:
        if dataset_filename is not None:
            dataset_filename = filename + ".csv"
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

    except Exception as e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)

info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.3.0')

# CPF test parameters
info.param_group('lap', label='Test Parameters')
info.param('lap.act_pwr', label='Active Power limits iteration', default='All', values=['66%', '33%', '0%', 'All'])
# 5.13.2 Procedure asks for three repetitions
info.param('lap.iter', label='Number of repetitions', default=3)
# FW test parameters
info.param_group('fw', label='FW - Test Parameters', glob=True)
info.param('fw.test_1_tr', label='Response time (s) for default', default=5.0)
# VW test parameters
info.param_group('vw', label='VW - Test Parameters', glob=True)
info.param('vw.test_1_tr', label='Response time (s) for default', default=10.0)

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


