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
from svpelab import der1547
from svpelab import hil
from svpelab import p1547
import script
from svpelab import result as rslt
import collections
import random
import time

FW = 'FW'
CPF = 'CPF'
VW = 'VW'
VV = 'VV'
WV = 'WV'
CRP = 'CRP'
PRI = 'PRI'

LFRT = 'LFRT'
HFRT = 'HFRT'


def test_run():
    result = script.RESULT_FAIL
    grid = None
    pv = p_rated = None
    daq = None
    eut = None
    rs = None
    phil = None
    result_summary = None
    step = None
    q_initial = None
    dataset_filename = None

    try:
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
        p_min = ts.param_value('eut.p_min')
        p_min_prime = ts.param_value('eut.p_min_prime')
        phases = ts.param_value('eut.phases')

        # Pass/fail accuracies
        pf_msa = ts.param_value('eut.pf_msa')

        # EUI Absorb capabilities
        absorb = {}
        absorb['ena'] = ts.param_value('eut_cpf.sink_power')
        absorb['p_rated_prime'] = ts.param_value('eut_cpf.p_rated_prime')
        absorb['p_min_prime'] = ts.param_value('eut_cpf.p_min_prime')

        # initialize HIL environment, if necessary
        ts.log_debug(15 * "*" + "HIL initialization" + 15 * "*")

        phil = hil.hil_init(ts)
        if phil is not None:
            phil.open()  # must load model here
            # phil.load_model_on_hil()
            # phil.start_simulation()

        """
        Configure settings in 1547.1 Standard module for the Frequency Ride Through Tests
        """
        pwr = float(ts.param_value('frt.high_pwr_value'))
        repetitions = ts.param_value('frt.repetitions')
        if ts.param_value('frt.wav_ena') == "Yes":
            wav_ena = True
        else:
            wav_ena = False
        if ts.param_value('frt.data_ena') == "Yes":
            data_ena = True
        else:
            data_ena = False

        FreqRideThrough = p1547.FrequencyRideThrough(ts=ts, support_interfaces={"hil": phil})
        # result params
        # result_params = lib_1547.get_rslt_param_plot()
        # ts.log(result_params)

        # grid simulator is initialized with test parameters and enabled
        ts.log_debug(15 * "*" + "Gridsim initialization" + 15 * "*")
        grid = gridsim.gridsim_init(ts, support_interfaces={"hil": phil})  # Turn on AC so the EUT can be initialized

        # pv simulator is initialized with test parameters and enabled
        ts.log_debug(15 * "*" + "PVsim initialization" + 15 * "*")
        pv = pvsim.pvsim_init(ts)
        if pv is not None:
            pv.power_set(p_rated)
            pv.power_on()  # Turn on DC so the EUT can be initialized

        # initialize data acquisition
        ts.log_debug(15 * "*" + "DAS initialization" + 15 * "*")
        daq = das.das_init(ts, support_interfaces={"hil": phil, "pvsim": pv})
        daq.waveform_config({"mat_file_name": "WAV.mat",
                             "wfm_channels": FreqRideThrough.get_wfm_file_header()})

        if daq is not None:
            daq.sc['F_MEAS'] = 100

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write('Test Name, Waveform File, RMS File\n')

        """
        Set the frequency droop function and droop values to make the active power change with respect to
        frequency as small as possible.
        """
        # Wait to establish communications with the EUT after AC and DC power are provided
        eut = der1547.der1547_init(ts)
        if eut is not None:
            eut.config()

        # Default curve is characteristic curve 1
        fw_curve = 1
        ActiveFunction = p1547.ActiveFunction(ts=ts,
                                              script_name='Freq-Watt',
                                              functions=[FW],
                                              criteria_mode=[True, True, True])
        fw_param = ActiveFunction.get_params(function=FW, curve=fw_curve)
        ts.log_debug('fw_params: %s' % fw_param)

        if eut is not None:
            params = {'pf_mode_enable_as': False,
                      'pf_dbof_as': fw_param['dbf'],
                      'pf_dbuf_as': fw_param['dbf'],
                      'pf_kof_as': fw_param['kof'],
                      'pf_kuf_as': fw_param['kof']
                      }
            # set before running experiment
            # settings = eut.set_pf(params=params)
            # ts.log_debug('Initial EUT FW settings are %s' % settings)
            # ts.confirm('Set EUT FW settings to %s' % params)

        """
        Set or verify that all frequency trip settings are set to not influence the outcome of the test.
        """
        # ts.log_debug('HFRT and trip parameters from EUT : {}'.format(eut.frt_stay_connected_high()))
        # ts.log_debug('LFRT and trip parameters from EUT : {}'.format(eut.frt_stay_connected_low()))

        """
        Operate the ac test source at nominal frequency ± 0.1 Hz.
        """
        # Configured in PHIL on startup

        # Initial loop for all mode that will be executed
        modes = FreqRideThrough.get_modes()  # Options: LFRT, HFRT
        ts.log(f"FRT modes tested : '{modes}'")
        for current_mode in modes:
            for repetition in range(1, repetitions + 1):
                dataset_filename = f'{current_mode}_{round(pwr * 100)}PCT_{repetition}'
                ts.log_debug(15 * "*" + f"Starting {dataset_filename}" + 15 * "*")
                if data_ena:
                    daq.data_capture(True)

                """
                Setting up available power to appropriate power level 
                """
                if pv is not None:
                    ts.log_debug(f'Setting power level to {pwr}')
                    pv.power_set(p_rated * pwr)

                """
                Initiating voltage sequence for FRT
                """
                frt_test_sequences = FreqRideThrough.set_test_conditions(current_mode)
                ts.log_debug(frt_test_sequences)
                frt_stop_time = FreqRideThrough.get_frt_stop_time(frt_test_sequences)
                if phil is not None:
                    # This adds 5 seconds of nominal behavior for EUT normal shutdown. This 5 sec is not recorded.
                    frt_stop_time = frt_stop_time + 5
                    ts.log('Stop time set to %s' % phil.set_stop_time(frt_stop_time))

                    # The driver should take care of this by selecting "Yes" to "Load the model to target?"
                    phil.load_model_on_hil()

                    # Set the grid simulator rocof to 3Hz/s
                    grid.rocof(FreqRideThrough.get_rocof_dic())

                    # You need to first load the model, then configure the parameters
                    # Now that we have all the test_sequences its time to sent them to the model.
                    FreqRideThrough.set_frt_model_parameters(frt_test_sequences)

                    # The driver parameter "Execute the model on target?" should be set to "No"
                    phil.start_simulation()
                    ts.sleep(0.5)
                    sim_time = phil.get_time()
                    while (frt_stop_time - sim_time) > 1.0:  # final sleep will get to stop_time.
                        sim_time = phil.get_time()
                        ts.log('Sim Time: %0.3f.  Waiting another %0.3f sec before saving data.' % (
                            sim_time, frt_stop_time - sim_time))
                        ts.sleep(5)

                    rms_dataset_filename = "No File"
                    wave_start_filename = "No File"
                    if data_ena:
                        rms_dataset_filename = dataset_filename + "_RMS.csv"
                        daq.data_capture(False)

                        # complete data capture
                        ts.log('Waiting for Opal to save the waveform data: {}'.format(dataset_filename))
                        ts.sleep(10)
                    if wav_ena:
                        # Convert and save the .mat file 
                        ts.log('Processing waveform dataset(s)')
                        wave_start_filename = dataset_filename + "_WAV.csv"

                        ds = daq.waveform_capture_dataset()  # returns list of databases of waveforms (overloaded)
                        ts.log(f'Number of waveforms to save {len(ds)}')
                        if len(ds) > 0:
                            ds[0].to_csv(ts.result_file_path(wave_start_filename))
                            ts.result_file(wave_start_filename)

                    if data_ena:
                        ds = daq.data_capture_dataset()
                        ts.log('Saving file: %s' % rms_dataset_filename)
                        ds.to_csv(ts.result_file_path(rms_dataset_filename))
                        ds.remove_none_row(ts.result_file_path(rms_dataset_filename), "TIME")
                        result_params = {
                            'plot.title': rms_dataset_filename.split('.csv')[0],
                            'plot.x.title': 'Time (sec)',
                            'plot.x.points': 'TIME',
                            'plot.y.points': 'AC_VRMS_1, AC_VRMS_2, AC_VRMS_3',
                            'plot.y.title': 'Voltage (V)',
                            'plot.y2.points': 'AC_IRMS_1, AC_IRMS_2, AC_IRMS_3',
                            'plot.y2.title': 'Current (A)',
                        }
                        ts.result_file(rms_dataset_filename, params=result_params)
                    result_summary.write('%s, %s, %s,\n' % (dataset_filename, wave_start_filename,
                                                            rms_dataset_filename))

                    phil.stop_simulation()

        result = script.RESULT_COMPLETE

    except script.ScriptFail as e:
        reason = str(e)
        if reason:
            ts.log_error(reason)

    except Exception as e:
        ts.log_error(e)
        ts.log_error('Test script exception: %s' % traceback.format_exc())

    finally:
        if grid is not None:
            grid.close()
        if pv is not None:
            # if p_rated is not None:
            #     pv.power_set(p_rated)
            pv.close()
        if daq is not None:
            daq.close()
        if eut is not None:
            # eut.fixed_pf(params={'Ena': False, 'PF': 1.0})
            eut.close()
        if rs is not None:
            rs.close()
        if phil is not None:
            if phil.model_state() == 'Model Running':
                phil.stop_simulation()
            phil.close()

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


info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.4.2')

# PRI test parameters
info.param_group('frt', label='Test Parameters')
info.param('frt.lf_ena', label='Low frequency mode settings:', default='Enabled', values=['Disabled', 'Enabled'])
info.param('frt.lf_parameter', label='Low frequency parameter (Hz):', default=57.0, active='frt.lf_ena',
           active_value=['Enabled'])
info.param('frt.lf_period', label='Low frequency period (s):', default=299.0, active='frt.lf_ena',
           active_value=['Enabled'])

info.param('frt.hf_ena', label='High frequency mode settings:', default='Enabled', values=['Disabled', 'Enabled'])
info.param('frt.hf_parameter', label='High frequency parameter (Hz):', default=61.8, active='frt.hf_ena',
           active_value=['Enabled'])
info.param('frt.hf_period', label='High frequency period (s):', default=299.0, active='frt.hf_ena',
           active_value=['Enabled'])
info.param('frt.high_pwr_value', label='Power Output level (Over 90%):', default=0.9)
info.param('frt.repetitions', label='Number of repetitions', default=3)
info.param('frt.wav_ena', label='Waveform acquisition needed (.mat->.csv)?', default='Yes', values=['Yes', 'No'])
info.param('frt.data_ena', label='RMS acquisition needed (SVP creates .csv from block queries))?', default='No',
           values=['Yes', 'No'])

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
info.param('eut.startup_time', label='EUT Startup time', default=10)
info.param('eut.scale_current', label='EUT Current scale input string (e.g. 30.0,30.0,30.0)',
           default="33.3400,33.3133,33.2567")
info.param('eut.offset_current', label='EUT Current offset input string (e.g. 0,0,0)', default="0,0,0")
info.param('eut.scale_voltage', label='EUT Voltage scale input string (e.g. 30.0,30.0,30.0)', default="20.0,20.0,20.0")
info.param('eut.offset_voltage', label='EUT Voltage offset input string (e.g. 0,0,0)', default="0,0,0")

# Add the SIRFN logo
info.logo('sirfn.png')

# Other equipment parameters
der1547.params(info)
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
