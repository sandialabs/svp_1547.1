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
LF = 'Low-Frequency'
HF = 'High-Frequency'

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
        f_nom = ts.param_value('eut.f_nom')
        f_min = ts.param_value('eut.f_min')
        f_max = ts.param_value('eut.f_max')

        p_min = ts.param_value('eut.p_min')
        p_min_prime = ts.param_value('eut.p_min_prime')
        phases = ts.param_value('eut.phases')


        # RT test parameters
        lf_ena = ts.param_value('frt.lf_ena')
        hf_ena = ts.param_value('frt.hf_ena')
        freq_response_time = ts.param_value('frt.response_time')
        n_iter = ts.param_value('frt.n_iter')
        pwr_lvl = ts.param_value('frt.pwr_value')
        # Pass/fail accuracies
        pf_msa = ts.param_value('eut.pf_msa')

        # EUI Absorb capabilities
        absorb = {}
        absorb['ena'] = ts.param_value('eut_cpf.sink_power')
        absorb['p_rated_prime'] = ts.param_value('eut_cpf.p_rated_prime')
        absorb['p_min_prime'] = ts.param_value('eut_cpf.p_min_prime')

        # Functions to be enabled for test
        mode = []
        steps_dict = {}
        if lf_ena == 'Enabled':
            mode.append(LF)
            lf_value = ts.param_value('frt.lf_value')
            if not(isinstance(lf_value, float) or isinstance(lf_value, int)):
                #TODO if not numeric value inputed
                pass
            elif not (f_min <= lf_value <= 57.0):
                #TODO raise error if not between f_min and 57.0
                raise ValueError

            steps_dict[LF] = {'location': f'C:/', 'value': lf_value}

        if hf_ena == 'Enabled':
            mode.append(HF)
            hf_value = ts.param_value('frt.hf_value')
            if not(isinstance(hf_value, float) or isinstance(hf_value, int)):
                #TODO if not numeric value inputed
                pass
            elif not 61.7 <= hf_value <= f_max:
                #TODO raise error if not between 63.0 and f_max
                raise ValueError

            steps_dict[HF] = {'location': f'C:/', 'value': hf_value}

        if not (isinstance(freq_response_time, float) or isinstance(freq_response_time, int)):
            # TODO if not numeric value inputed
            pass
        elif 299 > freq_response_time:
            # TODO timedelay must be over 299 sec
            raise ValueError

        time_step = {'location': f'C:....', 'value': freq_response_time }
        """
        A separate module has been create for the 1547.1 Standard
        """

        lib_1547 = p1547.module_1547(ts=ts, aif='FW', absorb=absorb)
        ts.log_debug("1547.1 Library configured for %s" % lib_1547.get_test_name())

        # result params
        result_params = lib_1547.get_rslt_param_plot()
        ts.log(result_params)

        # initialize HIL environment, if necessary
        phil = hil.hil_init(ts)
        if phil is not None:
            phil.config()

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

        """
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

        """
        a) Connect the EUT according to the instructions and specifications provided by the manufacturer.
        """
        # it is assumed the EUT is on
        eut = der.der_init(ts)
        if eut is not None:
            eut.config()
            eut.deactivate_all_fct()

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write(lib_1547.get_rslt_sum_col_name())

        """
        c) Set the frequency droop function and droop values to make the active power change with respect to
        frequency as small as possible.
        """
        if eut is not None:
            default_curve = 1
            fw_settings = lib_1547.get_params(aif=FW)
            fw_curve_params = {
                'Ena': True,
                'curve': default_curve,
                'dbf': fw_settings[default_curve]['dbf'],
                'kof': fw_settings[default_curve]['kof'],
                'RspTms': fw_settings[default_curve]['tr']
            }
            eut.freq_watt(fw_curve_params)
            ts.log_debug('Sending FW points: %s' % fw_curve_params)


        """
        d) Set or verify that all frequency trip settings are set to not influence the outcome of the test.
        """
        ts.log_debug('If not done already, set L/HVRT and trip parameters to the widest range of adjustability.')
        ts.log_debug(f'{mode}')


        #TODO Isolated Source mode??
        for current_mode in mode:
            ts.log_debug(f'Initializing {current_mode}')

            # TODO FIND A WAY TO SET ROCOF

            """
            e) Operate the ac test source at nominal frequency ± 0.1 Hz.
            """

            if grid is not None:
                grid.voltage(v_nom)
                ts.log(f'Setting Grid simulator voltage to {v_nom}')
                grid.freq(f_nom)
                ts.log(f'Setting Grid simulator frequency to {f_nom}')

            for i in range(1, n_iter+1):
                ts.log_debug('Starting mode = %s and %s' % (current_mode, current_mode == VV))
                daq.data_capture(True)
                dataset_filename = f'FRT_{current_mode}_{i}'
                ts.log('------------{}------------'.format(dataset_filename))
                #step_label = lib_1547.set_step_label(starting_label='F')
                #step = lib_1547.get_step_label()

                """
                f) Operate EUT at any convenient power level between 90% and 100% of EUT rating and at any
                convenient power factor. Record the output current of the EUT at the nominal frequency condition.
                """
                if pv is not None:
                    pv.iv_curve_config(pmp=p_rated, vmp=v_nom_in)
                    pv.irradiance_set(1000.)
                    pv.power_set(round(pwr_lvl*p_rated))

                """
                ***For High Frequency RT test mode***
                g) Adjust the source frequency from PN to PU where fU is greater than or equal to 61.8 Hz. The source
                shall be held at this frequency for period th, which shall be not less than 299 s.
                """
                # Set values for steps
                freq_step_location = steps_dict[current_mode]['location']
                freq_step_value = steps_dict[current_mode]['value']
                ts.log(f'Frequency step: setting Grid simulator frequency to {freq_step_value}Hz')
                ts.log(f'At frequency step location: {freq_step_location}')

                # Set timestep
                time_step_location = time_step['location']
                time_step_value = time_step['value']
                ts.log(f'Time setting: setting Grid simulator time setting to {time_step_value}sec')
                ts.log(f'At time step location: {time_step_location}')

                if phil is not None:
                    #Send commands to HIL
                    phil.set_params((freq_step_location, freq_step_value))
                    phil.set_params((time_step_location, time_step_value))

                    #TODO HIL SECTION TO BE COMPLETED
                    ts.log('Stop time set to %s' % phil.set_stop_time(stop_time))

                    if compilation == 'Yes':
                        ts.log("    Model ID: {}".format(phil.compile_model().get("modelId")))
                    if stop_sim == 'Yes':
                        ts.log("    {}".format(phil.stop_simulation()))
                    if load == 'Yes':
                        ts.log("    {}".format(phil.load_model_on_hil()))
                    if execute == 'Yes':
                        ts.log("    {}".format(phil.start_simulation()))

                    sim_time = phil.get_time()
                    while (stop_time - sim_time) > 1.0:  # final sleep will get to stop_time.
                        sim_time = phil.get_time()
                        ts.log('Sim Time: %s.  Waiting another %s sec before saving data.' % (
                            sim_time, stop_time - sim_time))
                        ts.sleep(1)

                """
                h) Decrease the frequency of the ac test source to the nominal frequency ± 0.1 Hz.
                """
                if grid is not None:
                    grid.freq(f_nom)
                    ts.log(f'Frequency step: setting Grid simulator frequency to {f_nom}')

                """
                i) Repeat steps f) and g) twice for a total of three tests.
                """
                """
                j) During all frequency transitions in steps f) through h), the ROCOF shall be greater than or equal to
                the ROCOF limit in Table 21 of IEEE Std 1547-2018 and shall be within the demonstrated ROCOF
                capability of the EUT.
                """


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
            eut.freq_watt(params={'Ena': False})
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
info.param_group('frt', label='Test Parameters')
info.param('frt.isolated_der', label='Is DER capable of frequency operation while isolated from external sources?',
           default='No', values=['No', 'Yes'])
info.param('frt.pwr_value', label='Power Output level (between 0.9-1.0):', default=0.90)
info.param('frt.lf_ena', label='Low Frequency mode settings:', default='Enabled', values=['Disabled', 'Enabled'])
info.param('frt.lf_value', label='Low Frequency step (Hz):', default=57.0, active='frt.lf_ena',
           active_value='Enabled')
info.param('frt.hf_ena', label='High Frequency mode settings:', default='Enabled', values=['Disabled', 'Enabled'])
info.param('frt.hf_value', label='High Frequency step (Hz):', default=61.8, active='frt.hf_ena',
           active_value='Enabled')
info.param('frt.response_time', label='Test Response Time (secs)', default=299.0)
info.param('frt.n_iter', label='Number of iterations:', default=3)

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
info.param('eut.f_min', label='Nominal AC frequency (Hz)', default=56.0)
info.param('eut.f_max', label='Nominal AC frequency (Hz)', default=64.0)


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


