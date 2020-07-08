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
import random

FW = 'FW'
CPF = 'CPF'
VW = 'VW'
VV = 'VV'
WV = 'WV'
CRP = 'CRP'
PRI = 'PRI'
LV = 'Low-Voltage'
HV = 'High-Voltage'
CAT_2 = 'Category II'
CAT_3 = 'Category III'

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
        eut_startup_time = ts.param_value('eut.startup_time')


        # RT test parameters
        lf_mode = ts.param_value('vrt.lv_ena')
        hf_mode = ts.param_value('vrt.hv_ena')
        low_pwr_ena = ts.param_value('vrt.low_pwr_ena')
        high_pwr_ena = ts.param_value('vrt.high_pwr_ena')
        low_pwr_value = ts.param_value('vrt.low_pwr_value')
        high_pwr_value = ts.param_value('vrt.high_pwr_value')

        #vrt_response_time = ts.param_value('vrt.response_time')
        #n_iter = ts.param_value('vrt.iteration')
        consecutive_ena = ts.param_value('vrt.consecutive_ena')

        categories = ts.param_value('vrt.cat')
        range_steps = ts.param_value('vrt.range_steps')


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
        steps_dict = {}
        timestep_dict = {}
        sequence_dict = {}
        parameters = []

        # initialize HIL environment, if necessary
        ts.log_debug(15*"*"+"HIL initialization"+15*"*")

        phil = hil.hil_init(ts)
        if phil is not None:
            #return self.ts.param_value(self.group_name + '.' + GROUP_NAME + '.' + name)
            open_proj = phil._param_value('hil_config_open')
            compilation = phil._param_value('hil_config_compile')
            stop_sim = phil._param_value('hil_config_stop_sim')
            load = phil._param_value('hil_config_load')
            execute = phil._param_value('hil_config_execute')
            model_name = phil._param_value('hil_config_model_name')
            phil.config()

       
        # TODO : Handle when both disabled add error or 
        if low_pwr_ena == 'Enabled':
            pwr_lvl.append(low_pwr_value)
        else:
            ts.log_debug('No low power chosen')
        if high_pwr_ena == 'Enabled':
            pwr_lvl.append(high_pwr_value)
        else:
            ts.log_debug('No high power chosen')

        """
        A separate module has been create for the 1547.1 Standard
        """
        #TODO setup as VRT or VV
        lib_1547 = p1547.module_1547(ts=ts, aif='VV', absorb=absorb)
        vrt_lib_1547 = p1547.vrt_1547(ts=ts,support_interfaces = {"hil" : phil})

        ts.log_debug("1547.1 Library configured for %s" % lib_1547.get_test_name())

        ''' RTLab OpWriteFile Math using worst case scenario of 160 seconds, 10 signals and Ts = 50e-6
        Duration of acquisition in number of points: Npoints = (Tend - Tstart) / (Ts * dec) = 4/(0.000050*1) = 80000
        Acquisition frame duration: Tframe = Nbss * Ts * dec = 1000*0.000050*1 = 0.05 sec
        Number of buffers to be acquired: Nbuffers = Npoints / Nbss = (Tend - Tstart) / Tframe = 3200
        Minimum file size: MinSize= Nbuffers x SizeBuf = [(Tend - Tstart) / Ts ] * (Nsig+1) * 8 * Nbss 
            = (160/50e-6)*(10+1)*8*1000 = 2.8160e+11
        SizeBuf = 1/Nbuffers * {[(Tend - Tstart) / Ts ]*(Nsig+1)*8*Nbss} = [(160/0.000050)*(10+1)*8*1e3]/3200 = 88000000
        Size of one buffer in bytes (SizeBuf) = (Nsig+1) * 8 * Nbss (Minimum) = 8*8*20 = 1280
        '''

        # result params
        #result_params = lib_1547.get_rslt_param_plot()
        #ts.log(result_params)

       

        # grid simulator is initialized with test parameters and enabled
        ts.log_debug(15*"*"+"Gridsim initialization"+15*"*")

        grid = gridsim.gridsim_init(ts,support_interfaces = {"hil" : phil} )  # Turn on AC so the EUT can be initialized
        if grid is not None:
            grid.voltage(v_nom)

        # pv simulator is initialized with test parameters and enabled
        ts.log_debug(15*"*"+"PVsim initialization"+15*"*")

        pv = pvsim.pvsim_init(ts)
        if pv is not None:
            pv.power_set(p_rated)
            pv.power_on()  # Turn on DC so the EUT can be initialized

        # DAS soft channels
        das_points = lib_1547.get_sc_points()

        # initialize data acquisition
        ts.log_debug(15*"*"+"DAS initialization"+15*"*")

        daq = das.das_init(ts, sc_points=das_points['sc'],support_interfaces = {"hil" : phil,"pvsim":pv})
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
        result_summary.write('Test, Waveform, RMS Data\n')

        """
        The voltage-reactive power control mode of the EUT shall be set to the default settings specified in Table 8
        of IEEE Std 1547-2018 for the applicable performance category, and enabled.
        """
        # Default curve is characteristic curve 1
        vv_curve = 1
        v_pairs = lib_1547.get_params(curve=vv_curve)
        ts.log_debug('v_pairs:%s' % v_pairs)

        """
        Set or verify that all frequency trip settings are set to not influence the outcome of the test.
        """
        # Sending VV parameters
        # TODO DISABLE TRIP
        eut = der.der_init(ts)
        if eut is not None:
            vv_curve_params = {'v': [v_pairs['V1'] * (100 / v_nom), v_pairs['V2'] * (100 / v_nom),
                                     v_pairs['V3'] * (100 / v_nom), v_pairs['V4'] * (100 / v_nom)],
                               'q': [v_pairs['Q1'] * (100 / var_rated), v_pairs['Q2'] * (100 / var_rated),
                                     v_pairs['Q3'] * (100 / var_rated), v_pairs['Q4'] * (100 / var_rated)],
                               'DeptRef': 'Q_MAX_PCT'}
            ts.log_debug('Setting VV points: %s' % vv_curve_params)
            eut.volt_var(params={'Ena': True, 'curve': vv_curve_params})
            ts.log_debug('Setting L/HVRT and trip parameters to the widest range of adjustability.')
        """
        Operate the ac test source at nominal frequency ± 0.1 Hz.
        """
        mode = vrt_lib_1547.get_modes()
        if grid is not None:
            grid.voltage(v_nom)
            ts.log(f'Setting Grid simulator voltage to {v_nom}')
            grid.freq(f_nom)
            ts.log(f'Setting Grid simulator frequency to {f_nom}')
            ts.log(f'Mode: {mode}')

        #Initial loop for all mode that will be executed
        for current_mode in mode:
            #Configuring waveform timing blocks with offset in seconds
            #daq.waveform_config(vrt_lib_1547.get_waveform_config(current_mode,offset=5))

            ts.log_debug(f'Clearing old parameters if any')
            #parameters.clear()

            # Only for Category II, a rate limiter needs to be added
            if CAT_2 in current_mode:
                # For t4 < t ≤ t5: V = 0.65 p.u. + [(1 p.u.) × (t – t4)]/(8.7 s) 
                grid.rocom(rocom=0.115,init_value=v_nom)

            ts.log_debug(f'Initializing {current_mode}')
            #Loop for all power level
            for pwr in pwr_lvl:
                dataset_filename = f'VRT_{current_mode}_{round(pwr*100)}PCT'
                ts.log(f'------------{dataset_filename}------------')
                daq.data_capture(True)

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
                vrt_parameters, vrt_start_time, vrt_stop_time = vrt_lib_1547.get_model_parameters(current_mode)

                if phil is not None:
                    #Set model parameters
                    phil.set_parameters(vrt_parameters)
                    vrt_stop_time = vrt_stop_time+5 +5
                    ts.sleep(0.5)
                    ts.log('Stop time set to %s' % phil.set_stop_time(vrt_stop_time))
                    phil.start_simulation()


                    sim_time = phil.get_time()
                    while (vrt_stop_time - sim_time) > 1.0:  # final sleep will get to stop_time.
                        sim_time = phil.get_time()
                        ts.log('Sim Time: %s.  Waiting another %s sec before saving data.' % (
                        sim_time, vrt_stop_time - sim_time))
                        ts.sleep(1)
                """
                h) Decrease the frequency of the ac test source to the nominal frequency ± 0.1 Hz.
                """
                ts.log('Sampling RMS complete')
                rms_dataset_filename = dataset_filename + "_RMS.csv"
                daq.data_capture(False)
                
                # complete data capture
                ts.log('Waiting 10 seconds for Opal to save the waveform data.')
                ts.sleep(10)

                ts.log('------------{}------------'.format(dataset_filename))

                # Convert and save the .mat file that contains the phase jump start
                ts.log('Processing waveform dataset(s)')
                ds = daq.waveform_capture_dataset()  # returns list of databases of waveforms (overloaded)

                wave_start_filename = '%s_startwave.csv' % dataset_filename
                ts.log('Saving file: %s' % wave_start_filename)
                ts.log_debug(f"{ds}")

                ds[0].to_csv(ts.result_file_path(wave_start_filename))
                ts.result_file(wave_start_filename)
                
                ds = daq.data_capture_dataset()
                ts.log('Saving file: %s' % rms_dataset_filename)
                ds.to_csv(ts.result_file_path(rms_dataset_filename))
                result_params = {
                'plot.title': rms_dataset_filename.split('.csv')[0],
                'plot.x.title': 'Time (sec)',
                'plot.x.points': 'TIME',
                'plot.y.points': 'AC_V_1',  # 'AC_V_2', 'AC_V_3',
                'plot.y.title': 'Voltage (V)',
                'plot.y2.points': 'AC_I_1',  # 'AC_I_2', 'AC_I_3',
                'plot.y2.title': 'Current (A)',
                # 'plot.%s_TARGET.min_error' % y: '%s_TARGET_MIN' % y,
                # 'plot.%s_TARGET.max_error' % y: '%s_TARGET_MAX' % y,
                }
                ts.result_file(rms_dataset_filename, params=result_params)
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
info.param('vrt.lv_ena', label='Low Voltage mode settings:', default='Enabled', values=['Disabled', 'Enabled'])
info.param('vrt.hv_ena', label='High Voltage mode settings:', default='Enabled', values=['Disabled', 'Enabled'])

info.param('vrt.low_pwr_ena', label='Low Power Output Test:', default='Enabled', values=['Disabled', 'Enabled'])
info.param('vrt.low_pwr_value', label='Low Power Output level (Between 25-50%):', default=0.5, active='vrt.low_pwr_ena',
           active_value='Enabled')
info.param('vrt.high_pwr_ena', label='High Power Output Test :', default='Enabled', values=['Disabled', 'Enabled'])
info.param('vrt.high_pwr_value', label='High Power Output level (Over 90%):', default=0.91, active='vrt.high_pwr_ena',
           active_value='Enabled')
#info.param('vrt.response_time', label='Test Response Time (secs)', default=299.0)
info.param('vrt.cat', label='Category II and/or III:', default=CAT_2, values=[CAT_2, CAT_3, "Both"])
#info.param('vrt.consecutive_ena', label='Consecutive Ride-Through test?', default='Enabled', values=['Disabled', 'Enabled'])
# TODO : This should be change for following the "figure" or "Random"
info.param('vrt.range_steps', label='Ride-Through Profile ("Figure" is following the RT images from standard)', default='Figure', values=['Figure', 'Random'])


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

