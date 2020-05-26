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
import collections

FW = 'FW'
CPF = 'CPF'
VW = 'VW'
VV = 'VV'
WV = 'WV'
CRP = 'CRP'
PRI = 'PRI'


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
        v_nom_in_enabled = ts.param_value('cpf.v_in_nom')
        v_min_in_enabled = ts.param_value('cpf.v_in_min')
        v_max_in_enabled = ts.param_value('cpf.v_in_max')

        v_nom_in = ts.param_value('eut.v_in_nom')
        v_min_in = ts.param_value('eut_cpf.v_in_min')
        v_max_in = ts.param_value('eut_cpf.v_in_max')

        # AC voltages
        v_nom = ts.param_value('eut.v_nom')
        v_min = ts.param_value('eut.v_low')
        v_max = ts.param_value('eut.v_high')
        p_min = ts.param_value('eut.p_min')
        p_min_prime = ts.param_value('eut.p_min_prime')
        phases = ts.param_value('eut.phases')
        rt_response_time = ts.param_value('rt.rt_response_time')

        # Reactive power
        vv_status = ts.param_value('rt.vv_status')

        # Pass/fail accuracies
        pf_msa = ts.param_value('eut.pf_msa')

        # Imbalance configuration
        imbalance_fix = ts.param_value('cpf.imbalance_fix')

        # EUI Absorb capabilities
        absorb = {}
        absorb['ena'] = ts.param_value('eut_cpf.sink_power')
        absorb['p_rated_prime'] = ts.param_value('eut_cpf.p_rated_prime')
        absorb['p_min_prime'] = ts.param_value('eut_cpf.p_min_prime')

        # Functions to be enabled for test
        mode = []
        if vv_status == 'Enabled':
            mode.append(VV)

        """
        A separate module has been create for the 1547.1 Standard
        """
        lib_1547 = p1547.module_1547(ts=ts, aif='PRI', absorb=absorb)
        ts.log_debug("1547.1 Library configured for %s" % lib_1547.get_test_name())

        # result params
        result_params = lib_1547.get_rslt_param_plot()
        ts.log(result_params)

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

            eut.deactivate_all_fct()
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
        result_summary.write(lib_1547.get_rslt_sum_col_name())

        """
        d) Adjust the EUT's available active power to Prated. For an EUT with an input voltage range, set the input
        voltage to Vin_nom. The EUT may limit active power throughout the test to meet reactive power requirements.
        """

        if pv is not None:
            pv.iv_curve_config(pmp=p_rated, vmp=v_nom_in)
            pv.irradiance_set(1000.)

        """
        e) Set EUT frequency-watt and volt-watt parameters to the default values for the EUTs category, and
        enable frequency-watt and volt-watt parameters. For volt-watt, set P2 = 0.2Prated.
        """

        default_curve = 1

        if eut is not None:
            fw_settings = lib_1547.get_params(aif=FW)
            fw_curve_params = {
                'Ena': True,
                'curve': default_curve,
                'dbf': fw_settings[default_curve]['dbf'],
                'kof': fw_settings[default_curve]['kof'],
                'RspTms': fw_settings[default_curve]['tr']
            }
            ts.log_debug('Sending FW points: %s' % fw_curve_params)

            """
            h) Set the EUTs active power limit signal to 50% of Prated.
            """
            ts.sleep(4 * rt_response_time)

        for current_mode in mode:
            ts.log_debug('Starting mode = %s and %s' % (current_mode, current_mode == VV))

            if current_mode == VV:
                """
                f) Set EUT volt-var parameters to the default values for the EUTs category and enable volt-var
                mode
                """
                if eut is not None:
                    vv_settings = lib_1547.get_params(aif=VV)
                    # ts.log_debug('Sending VV points: %s' % vv_settings)
                    vv_curve_params = {'v': [vv_settings[default_curve]['V1'] * (100 / v_nom),
                                             vv_settings[default_curve]['V2'] * (100 / v_nom),
                                             vv_settings[default_curve]['V3'] * (100 / v_nom),
                                             vv_settings[default_curve]['V4'] * (100 / v_nom)],
                                       'q': [vv_settings[default_curve]['Q1'] * (100 / var_rated),
                                             vv_settings[default_curve]['Q2'] * (100 / var_rated),
                                             vv_settings[default_curve]['Q3'] * (100 / var_rated),
                                             vv_settings[default_curve]['Q4'] * (100 / var_rated)],
                                       'DeptRef': 'Q_MAX_PCT',
                                       'RmpPtTms': 10.0}
                    ts.log_debug('Sending VV points: %s' % vv_curve_params)
                    eut.volt_var(params={'Ena': True, 'curve': vv_curve_params})

            """
            g) Allow the EUT to reach steady state. Measure AC test source voltage and frequency and the EUTs
            active and reactive power production.
            """

            daq.data_capture(True)
            dataset_filename = 'RT_{}'.format(current_mode)
            ts.log('------------{}------------'.format(dataset_filename))

            # Todo : Start measuring Voltage and

            """
            i) Allow the EUT to reach steady state.
            """
            ts.sleep(2 * rt_response_time)
            """
            j) Measure AC test source voltage and frequency, and the EUTs active and reactive power
            production.
            """

            """
            k) Set the AC test source voltage and frequency to the values in step 1 of Table 38 or Table 39,
            depending on the EUTs normal operating performance category.

            l) Allow the EUT to reach steady state.

            m) Measure AC test source voltage and frequency, and the EUTs active and reactive power
            production.

            n) Repeat steps k) through m) for the rest of the steps in Table 38 or Table 39, depending on the
            EUTs normal operating performance category
            """

            steps_dict = [{'V': 1.00},
                          {'V': 1.09},
                          {'V': 1.09},
                          {'V': 1.09},
                          {'V': 1.09},
                          {'V': 1.00},
                          {'V': 1.00},
                          {'V': 1.00}]

            target_dict = lib_1547.get_params(aif=PRI)
            ts.log('Target_dict: %s' % (target_dict))
            target_dict_updated = {}
            i = 0

            for step in steps_dict:
                step_label = 'Step_%i_%s' % (i + 1, current_mode)
                step['V'] *= v_nom

                #target_dict_updated['Q'] = target_dict[i][current_mode]
                #target_dict_updated['P'] = target_dict[i]['P']
                ts.log('Voltage step: setting Grid simulator voltage to %s (%s)' % (step['V'], step_label))
                ts.log('Frequency step: setting Grid simulator frequency to %s (%s)' % (step['F'], step_label))
                ts.log('Ptarget: %s (%s)' % (target_dict_updated['P'], step_label))
                ts.log('Qtarget: %s (%s)' % (target_dict_updated['Q'], step_label))

                initial_values = lib_1547.get_initial_value(daq=daq, step=step_label)
                if grid is not None:
                    grid.freq(step['F'])
                    grid.voltage(step['V'])
                ts.log_debug('step: %s' % step)
                ts.log_debug('type: %s' % type(step))
                ts.log_debug('current mode %s' % current_mode)
                lib_1547.process_data(
                    daq=daq,
                    tr=rt_response_time,
                    step=step_label,
                    initial_value=initial_values,
                    x_target=step,
                    y_target=target_dict_updated,
                    # x_target=[v_step, f_step],
                    # y_target=[p_target, q_target],
                    result_summary=result_summary,
                    filename=dataset_filename,
                    aif=current_mode
                )
                ts.sleep(2 * rt_response_time)
                i += 1

            if current_mode == VV:
                eut.volt_var(params={'Ena': False})


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
        ts.log_error((e, traceback.format_exc()))
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
            # eut.fixed_pf(params={'Ena': False, 'PF': 1.0})
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

# PRI test parameters
info.param_group('rt', label='Test Parameters')
info.param('rt.vv_status', label='Volt-Var settings status', default='Enabled', values=['Disabled', 'Enabled'])
info.param('rt.rt_response_time', label='Test Response Time (secs)', default=10.0)

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


