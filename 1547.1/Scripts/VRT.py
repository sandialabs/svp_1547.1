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
LV = 'Low-Voltage'
HV = 'High-Voltage'
CAT_2 = 'Categorie II'
CAT_3 = 'Categorie III'

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
        p_min = ts.param_value('eut.p_min')
        p_min_prime = ts.param_value('eut.p_min_prime')
        phases = ts.param_value('eut.phases')


        # RT test parameters
        lf_mode = ts.param_value('vrt.lv_mode')
        hf_mode = ts.param_value('vrt.hv_mode')
        low_pwr_ena = ts.param_value('vrt.low_pwr_ena')
        high_pwr_ena = ts.param_value('vrt.high_pwr_ena')
        low_pwr_lvl = ts.param_value('vrt.low_pwr_lvl')
        high_pwr_lvl = ts.param_value('vrt.low_pwr_lvl')
        vrt_response_time = ts.param_value('vrt.response_time')
        n_iter = ts.param_value('vrt.iteration')
        consecutive_ena = ts.param_value('vrt.consecutive_ena')
        categorie_ii_ena = ts.param_value('vrt.cat_2_ena')
        categorie_iii_ena = ts.param_value('vrt.cat_3_ena')

        # Pass/fail accuracies
        pf_msa = ts.param_value('eut.pf_msa')

        # EUI Absorb capabilities
        absorb = {}
        absorb['ena'] = ts.param_value('eut_cpf.sink_power')
        absorb['p_rated_prime'] = ts.param_value('eut_cpf.p_rated_prime')
        absorb['p_min_prime'] = ts.param_value('eut_cpf.p_min_prime')

        # Functions to be enabled for test
        mode = []
        pwr_lvl = []
        steps_dict = collections.OrderedDict()
        timestep_dict = {}
        sequence_dict = {}

        if lf_mode == 'Enabled':
            mode.append(LV)
            #TODO change sequence parameter for parameter to be chosen by users or average of both max & min values?

            if categorie_ii_ena == 'Enabled':

                steps_dict.update({LV:{CAT_2: {
                    'A': 0.94,
                    'B': 0.15,
                    'C': 0.25,
                    'D': 0.55,
                    'D_PRIME': 0.67,
                    'E': 0.65,
                    'F': 0.88
                }}})

                timestep_dict.update({LV: {CAT_2: {
                    'A': 10.0,
                    'B': 0.16,
                    'C': 0.32,
                    'D': 3.0,
                    'D_PRIME': 8.0,
                    'E': 5.0,
                    'F': 120
                }}})
            if categorie_iii_ena == 'Enabled':

                steps_dict.update({LV:{CAT_3: {
                    'A': 0.94,
                    'B': 0.15,
                    'C': 0.25,
                    'D': 0.55,
                    'D_PRIME': 0.67,
                    'E': 0.65,
                    'F': 0.88
                }}})

                timestep_dict.update({LV: {CAT_3: {
                    'A': 5.0,
                    'B': 1.0,
                    'C': 10.0,
                    'C_PRIME': 10.0,
                    'D': 20.0,
                    'E': 120.0
                }}})

        if hf_mode == 'Enabled':
            mode.append(HV)
            #TODO change sequence parameter for parameter to be chosen by users?

            if categorie_ii_ena == 'Enabled':

                steps_dict.update({HV: {CAT_2: {
                    'A': 1.05,
                    'B': 1.19,
                    'C': 1.165,
                    'D': 1.14,
                    'E': 1.05
                }}})

                timestep_dict.update({HV: {CAT_2: {
                    'A': 10.0,
                    'B': 0.20,
                    'C': 0.50,
                    'D': 1.0,
                    'E': 120.0
                }}})

            if categorie_iii_ena == 'Enabled':
                steps_dict.update({HV: {CAT_3: {
                    'A': 1.05,
                    'B': 1.19,
                    'B_PRIME': 1.16,
                    'C': 1.05
                }}})

                timestep_dict.update({HV: {CAT_3: {
                    'A': 5.0,
                    'B': 12.0,
                    'B_PRIME': 12.0,
                    'C': 120
                }}})

        if low_pwr_ena == 'Enabled':
            pwr_lvl.append(low_pwr_lvl)
        if high_pwr_ena == 'Enabled':
            pwr_lvl.append(high_pwr_lvl)

        if consecutive_ena == 'Enabled':

        else:
            sequence_dict.update()

        """
        A separate module has been create for the 1547.1 Standard
        """
        #TODO setup as VRT or FW
        lib_1547 = p1547.module_1547(ts=ts, aif='FW', absorb=absorb)
        ts.log_debug("1547.1 Library configured for %s" % lib_1547.get_test_name())

        # result params
        result_params = lib_1547.get_rslt_param_plot()
        ts.log(result_params)

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
            """
            daq.sc['P_MEAS'] = 100
            daq.sc['Q_MEAS'] = 100
            daq.sc['Q_TARGET_MIN'] = 100
            daq.sc['Q_TARGET_MAX'] = 100
            daq.sc['PF_TARGET'] = 1
            daq.sc['event'] = 'None'
            ts.log('DAS device: %s' % daq.info())
            """
        """
        This test doesn't have specific procedure steps. Keep in mind these steps has been 
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
        The voltage-reactive power control mode of the EUT shall be set to the default settings specified in Table 8
        of IEEE Std 1547-2018 for the applicable performance category, and enabled.
        """
        # Setting up v_pairs value corresponding to desired curve
        vv_curve = 1
        v_pairs = lib_1547.get_params(curve=vv_curve)
        ts.log_debug('v_pairs:%s' % v_pairs)

        # it is assumed the EUT is on
        eut = der.der_init(ts)
        if eut is not None:
            vv_curve_params = {'v': [v_pairs['V1'] * (100 / v_nom), v_pairs['V2'] * (100 / v_nom),
                                     v_pairs['V3'] * (100 / v_nom), v_pairs['V4'] * (100 / v_nom)],
                               'q': [v_pairs['Q1'] * (100 / var_rated), v_pairs['Q2'] * (100 / var_rated),
                                     v_pairs['Q3'] * (100 / var_rated), v_pairs['Q4'] * (100 / var_rated)],
                               'DeptRef': 'Q_MAX_PCT'}
            ts.log_debug('Sending VV points: %s' % vv_curve_params)
            eut.volt_var(params={'Ena': True, 'curve': vv_curve_params})

        """
        Set or verify that all frequency trip settings are set to not influence the outcome of the test.
        """
        ts.log_debug('If not done already, set L/HVRT and trip parameters to the widest range of adjustability.')
        #TODO DISABLE TRIP
        """
        Operate the ac test source at nominal frequency ± 0.1 Hz.
        """
        if grid is not None:
            grid.voltage(v_nom)
            ts.log(f'Setting Grid simulator voltage to {v_nom}')
            grid.freq(f_nom)
            ts.log(f'Setting Grid simulator frequency to {f_nom}')

        for current_mode in mode:
            ts.log_debug(f'Initializing {current_mode}')

            for pwr in pwr_lvl:
                #for i in range(n_iter+1):
                dataset_filename = f'VRT_{current_mode}_{pwr*100}PCT'
                ts.log(f'------------{dataset_filename}------------')
                daq.data_capture(True)

                #step_label = lib_1547.set_step_label(starting_label='F')
                #step = lib_1547.get_step_label()

                """
                Setting up available power to appropriate power level 
                """
                if pv is not None:
                    ts.log_debug(f'Setting power level to {pwr}')
                    pv.iv_curve_config(pmp=p_rated, vmp=v_nom_in)
                    pv.irradiance_set(1000.)
                    pv.power_set(p_rated*pwr)

                """
                ***For RT test mode***
                Initiating Voltage sequence for VRT
                """
                for step in sequence:

                    if grid is not None:

                        grid.voltage(steps_dict[HV])
                        ts.log(f'Voltage step: setting Grid simulator frequency to {steps_dict[current_mode]}')
                        ts.sleep(step)
                #initial_values = lib_1547.get_initial_value(daq=daq, step=step_label)
                #ts.sleep(freq_response_time)

                """
                h) Decrease the frequency of the ac test source to the nominal frequency ± 0.1 Hz.
                """
                if grid is not None:
                    grid.voltage(v_nom)
                    ts.log(f'Sequence completed: setting Grid voltage back at v_nom:{v_nom}')

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
info.param_group('vrt', label='Test Parameters')

info.param('vrt.lv_ena', label='Low Frequency mode settings:', default='Enabled', values=['Disabled', 'Enabled'])
info.param('vrt.hv_ena', label='High Frequency mode settings:', default='Enabled', values=['Disabled', 'Enabled'])

info.param('vrt.low_pwr_ena', label='Low Power Output Test:', default='Enabled', values=['Disabled', 'Enabled'])
info.param('vrt.low_pwr_value', label='Low Power Output level (Between 25-50%):', default=0.5, active='vrt.low_pwr_ena',
           active_value='Enabled')
info.param('vrt.high_pwr_ena', label='High Power Output Test :', default='Enabled', values=['Disabled', 'Enabled'])
info.param('vrt.high_pwr_value', label='High Power Output level (Over 90%):', default=0.91, active='vrt.high_pwr_ena',
           active_value='Enabled')
info.param('vrt.response_time', label='Test Response Time (secs)', default=299.0)
info.param('vrt.cat_2_ena', label='Categorie II:', default='Enabled', values=['Disabled', 'Enabled'])
info.param('vrt.cat_3_ena', label='Categorie III:', default='Disabled', values=['Disabled', 'Enabled'])
info.param('vrt.consecutive_ena', label='Consecutive Ride-Through test?', default='Enabled', values=['Disabled', 'Enabled'])

#info.param('vrt.n_iter', label='Number of iterations:', default=3)

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


