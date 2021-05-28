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
import time

FW = 'FW'
CPF = 'CPF'
VW = 'VW'
VV = 'VV'
WV = 'WV'
CRP = 'CRP'
PRI = 'PRI'
LV = 'LV'
HV = 'HV'
CAT_2 = 'CAT_2'
CAT_3 = 'CAT_3'


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

        low_pwr_ena = ts.param_value('vrt.low_pwr_ena')
        high_pwr_ena = ts.param_value('vrt.high_pwr_ena')
        low_pwr_value = ts.param_value('vrt.low_pwr_value')
        high_pwr_value = ts.param_value('vrt.high_pwr_value')

        # Pass/fail accuracies
        pf_msa = ts.param_value('eut.pf_msa')

        # EUI Absorb capabilities
        absorb = {}
        absorb['ena'] = ts.param_value('eut_cpf.sink_power')
        absorb['p_rated_prime'] = ts.param_value('eut_cpf.p_rated_prime')
        absorb['p_min_prime'] = ts.param_value('eut_cpf.p_min_prime')

        # Following parameters are collected in p1547.VoltageRideThrough.set_vrt_params in init:
        # vrt.lv_ena, vrt.hv_ena, vrt.consecutive_ena, vrt.cat, vrt.range_steps
        consecutive_ena = ts.param_value('vrt.consecutive_ena')
        if consecutive_ena == "Enabled":
            consecutive_label = "CE"
        else:
            consecutive_label = "CD"

        phase_comb_list = []

        if ts.param_value('vrt.one_phase_mode') == "Enabled":
            phase_comb_list.append([ts.param_value('vrt.one_phase_value')])
        
        if ts.param_value('vrt.two_phase_mode') == "Enabled":
            phase_comb_list.append([ts.param_value('vrt.two_phase_value_1'),ts.param_value('vrt.two_phase_value_2')])

        if ts.param_value('vrt.three_phase_mode') == "Enabled":
            phase_comb_list.append(['A', 'B', 'C'])

        # Functions to be enabled for test
        mode = []
        pwr_lvl = []
        steps_dict = {}
        timestep_dict = {}
        sequence_dict = {}
        parameters = []

        # initialize HIL environment, if necessary
        ts.log_debug(15 * "*" + "HIL initialization" + 15 * "*")

        phil = hil.hil_init(ts)
        if phil is not None:
            # return self.ts.param_value(self.group_name + '.' + GROUP_NAME + '.' + name)
            open_proj = phil._param_value('hil_config_open')
            compilation = phil._param_value('hil_config_compile')
            stop_sim = phil._param_value('hil_config_stop_sim')
            load = phil._param_value('hil_config_load')
            execute = phil._param_value('hil_config_execute')
            model_name = phil._param_value('hil_config_model_name')
            phil.config()

        ''' RTLab OpWriteFile Math using worst case scenario of 160 seconds, 14 signals and Ts = 40e-6
        Duration of acquisition in number of points: Npoints = (Tend-Tstart)/(Ts*dec) = (350)/(0.000040*25) = 1350e3
        
        Acquisition frame duration: Tframe = Nbss * Ts * dec = 1000*0.000040*250 = 10 sec
        
        Number of buffers to be acquired: Nbuffers = Npoints / Nbss = (Tend - Tstart) / Tframe = 16
        
        Minimum file size: MinSize= Nbuffers x SizeBuf = [(Tend - Tstart) / Ts ] * (Nsig+1) * 8 * Nbss 
            = (160/40e-6)*(14+1)*8*1000 = 4.8e11
        
        SizeBuf = 1/Nbuffers * {[(Tend - Tstart) / Ts ]*(Nsig+1)*8*Nbss} = [(160/0.000040)*(14+1)*8*1e3]/16 = 30e9
        Size of one buffer in bytes (SizeBuf) = (Nsig+1) * 8 * Nbss (Minimum) = (14+1)*8*1000 = 120e3
        '''

        if low_pwr_ena == 'Enabled':
            pwr_lvl.append(low_pwr_value)
        else:
            ts.log_debug('No low power chosen')
        if high_pwr_ena == 'Enabled':
            pwr_lvl.append(high_pwr_value)
        else:
            ts.log_debug('No high power chosen')
        if high_pwr_ena == 'Disabled' and low_pwr_ena == 'Disabled':
            ts.log_error('No power tests included in VRT test!')

        if ts.param_value('vrt.wav_ena') == "Yes" :
            wav_ena = True
        else :
            wav_ena = False
        if ts.param_value('vrt.data_ena') == "Yes" :
            data_ena = True
        else :
            data_ena = False
        """
        Configure settings in 1547.1 Standard module for the Voltage Ride Through Tests
        """
        VoltRideThrough = p1547.VoltageRideThrough(ts=ts, support_interfaces={"hil": phil})
        # result params
        # result_params = lib_1547.get_rslt_param_plot()
        # ts.log(result_params

        # grid simulator is initialized with test parameters and enabled
        ts.log_debug(15 * "*" + "Gridsim initialization" + 15 * "*")
        grid = gridsim.gridsim_init(ts, support_interfaces={"hil": phil})  # Turn on AC so the EUT can be initialized
        if grid is not None:
            grid.voltage(v_nom)  

        # pv simulator is initialized with test parameters and enabled
        ts.log_debug(15 * "*" + "PVsim initialization" + 15 * "*")
        pv = pvsim.pvsim_init(ts)
        if pv is not None:
            pv.power_set(p_rated)
            pv.power_on()  # Turn on DC so the EUT can be initialized

        # initialize data acquisition
        ts.log_debug(15 * "*" + "DAS initialization" + 15 * "*")
        daq = das.das_init(ts, support_interfaces={"hil": phil, "pvsim": pv})
        daq.waveform_config({"mat_file_name":"Data.mat",
                            "wfm_channels": VoltRideThrough.get_wfm_file_header()})

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
        This test doesn't have specific procedure steps. 
        """

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write('Test Name, Waveform File, RMS File\n')

        """
        During the LVRT test, the settings for magnitude and duration of undervoltage tripping functions shall be
        disabled or set so as not to influence the outcome of the test. 
        
        If the EUT provides a voltage-active power control mode, that mode shall be disabled. 
        
        Connect the EUT according to the instructions and specifications provided by the manufacturer.
        """
        # Wait to establish communications with the EUT after AC and DC power are provided
        eut = der.der_init(ts, support_interfaces={'hil': phil}) 

        # start = time.time()
        # comm_wait_time = max(0.0, startup_time - 60.)
        # while time.time()-start < comm_wait_time - 1:
        #     ts.sleep(1)
        #     ts.log('Waiting another %0.2f seconds until communicating with EUT' %
        #            (comm_wait_time - (time.time()-start)))

        if eut is not None:
            eut.config()
            
        # if eut is not None:
        #     eut.deactivate_all_fct()

    

        # Initial loop for all mode that will be executed
        modes = VoltRideThrough.get_modes()  # Options: LV_CAT_2, HV_CAT_2, LV_CAT_3, HV_CAT_3
        ts.log(f"VRT modes tested : '{modes}'")
        ts.log(f"VRT power level tested : '{pwr_lvl}'")
        ts.log(f"VRT phase combination tested : '{phase_comb_list}'")
        for current_mode in modes:
            # Configuring waveform timing blocks with offset in seconds
            # daq.waveform_config(vrt_lib_1547.get_waveform_config(current_mode,offset=5))
            """
            The ride-through tests shall be performed at two output power levels, high and low, and at any convenient
            power factor greater than 0.90. The output power levels shall be measured prior to the disturbance, i.e., in
            test condition A. High-power tests shall be performed at any active power level greater than 90% of the
            EUT nameplate active power rating at nominal voltage. ... Low-power tests shall be performed at any 
            convenient power level between 25% to 50% of EUT nameplate  apparent power rating at nominal voltage.
            """
            for pwr in pwr_lvl:  
                for phase in phase_comb_list :  
             
                    phase_combination_label = "PH" + ''.join(phase)

                    dataset_filename = f'{current_mode}_{round(pwr*100)}PCT_{phase_combination_label}_{consecutive_label}'
                    ts.log_debug(15 * "*" + f"Starting {dataset_filename}" + 15 * "*")
                    if data_ena:
                        daq.data_capture(True)

                    """
                    Setting up available power to appropriate power level 
                    """
                    if pv is not None:
                        ts.log_debug(f'Setting power level to {pwr}')
                        pv.iv_curve_config(pmp=p_rated, vmp=v_nom_in)
                        pv.irradiance_set(1000.)
                        pv.power_set(p_rated * pwr)
                        
                    """
                    Initiating voltage sequence for VRT
                    """
                    vrt_test_sequences = VoltRideThrough.set_test_conditions(current_mode)
                    VoltRideThrough.set_phase_combination(phase)
                    vrt_stop_time = VoltRideThrough.get_vrt_stop_time(vrt_test_sequences)
                    if phil is not None:
                        # Set model parameters
                        #phil.set_parameters(vrt_parameters)
                        # This adds 5 seconds of nominal behavior for EUT normal shutdown. This 5 sec is not recorded.
                        vrt_stop_time = vrt_stop_time + 5
                        ts.log('Stop time set to %s' % phil.set_stop_time(vrt_stop_time))
                        # The driver should take care of this by selecting "Yes" to "Load the model to target?"
                        ts.sleep(2.0)
                        phil.load_model_on_hil()
                        # You need to first load the model, then configure the parameters
                        # Now that we have all the test_sequences its time to sent them to the model.
                        VoltRideThrough.set_vrt_model_parameters(vrt_test_sequences)
                                        
                        """
                        The voltage-reactive power control mode of the EUT shall be set to the default settings specified in Table 8
                        of IEEE Std 1547-2018 for the applicable performance category, and enabled.
                        """
                        # Default curve is characteristic curve 1
                        vv_curve = 1
                        ActiveFunction = p1547.ActiveFunction(ts=ts,
                                                            script_name='Volt-Var',
                                                            functions=[VV],
                                                            criteria_mode=[True, True, True])
                        # Don't need to be set to imbalance mode
                        #ActiveFunction.set_imbalance_config(imbalance_angle_fix="std")
                        #ActiveFunction.reset_curve(vv_curve)
                        #ActiveFunction.reset_time_settings(tr=10, number_tr=2)
                        v_pairs = ActiveFunction.get_params(function=VV, curve=vv_curve)
                        ts.log_debug('v_pairs:%s' % v_pairs)
                        if eut is not None:
                            # Set to: V = {92, 98, 102, 108}, Var = {44, 0 , 0 , -44}
                            vv_curve_params = {'v': [round(v_pairs['V1']/v_nom,2),
                                                    round(v_pairs['V2']/v_nom,2),
                                                    round(v_pairs['V3']/v_nom,2),
                                                    round(v_pairs['V4']/v_nom,2)],
                                            'var': [round(v_pairs['Q1']/p_rated,2),
                                                    round(v_pairs['Q2']/p_rated,2),
                                                    round(v_pairs['Q3']/p_rated,2),
                                                    round(v_pairs['Q4']/p_rated,2)],
                                            'vref': 1.0,
                                            'RmpPtTms': 1.0}
                            ts.log_debug('Setting VV points: %s' % vv_curve_params)
                            eut.volt_var(params={'Ena': True, 'ACTCRV': vv_curve, 'curve': vv_curve_params})
                            ts.log_debug('Initial EUT VV settings are %s' % eut.volt_var())

                        # The driver parameter "Execute the model on target?" should be set to "No"
                        phil.start_simulation() 
                        ts.sleep(0.5)
                        sim_time = phil.get_time()
                        while (vrt_stop_time - sim_time) > 1.0:  # final sleep will get to stop_time.
                            sim_time = phil.get_time()
                            ts.log('Sim Time: %0.3f.  Waiting another %0.3f sec before saving data.' % (
                                sim_time, vrt_stop_time - sim_time))
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
        ts.log_error((e, traceback.format_exc()))

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


info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.4.3')

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
info.param('vrt.cat', label='Category II and/or III:', default=CAT_2, values=[CAT_2, CAT_3, "Both"])
# TODO: The consecutive option needs a way to verify the first test to apply a different perturbation accordingly.
info.param('vrt.consecutive_ena', label='Consecutive Ride-Through test?', default='Enabled',
           values=['Disabled', 'Enabled'])

info.param('vrt.one_phase_mode', label="Apply disturbance to one phase" , default='Enabled', values=['Disabled', 'Enabled'])
info.param('vrt.one_phase_value', label="Which phase ?" , active='vrt.one_phase_mode', active_value=['Enabled'], default='A', values=['A', 'B', 'C'])

info.param('vrt.two_phase_mode', label="Apply disturbance to two phases" , default='Enabled', values=['Disabled', 'Enabled'])
info.param('vrt.two_phase_value_1', label="Which phase ?" , active='vrt.two_phase_mode', active_value=['Enabled'], default='A', values=['A', 'B', 'C'])
info.param('vrt.two_phase_value_2', label="Which phase ?" , active='vrt.two_phase_mode', active_value=['Enabled'], default='B', values=['A', 'B', 'C'])
info.param('vrt.three_phase_mode', label="Apply disturbance to all phases" , default='Enabled', values=['Disabled', 'Enabled'])
info.param('vrt.range_steps', label='Ride-Through Profile ("Figure" is following the RT images from standard)',
           default='Figure', values=['Figure', 'Random'])
info.param('vrt.wav_ena', label='Waveform acquisition needed (.mat->.csv) ?', default='Yes', values=['Yes', 'No'])
info.param('vrt.data_ena', label='RMS acquisition needed (SVP creates .csv from block queries)?', default='No', values=['Yes', 'No'])

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
info.param('eut.scale_current', label='EUT Current scale input string (e.g. 30.0,30.0,30.0)', default="33.3400,33.3133,33.2567")
info.param('eut.offset_current', label='EUT Current offset input string (e.g. 0,0,0)', default="0,0,0")
info.param('eut.scale_voltage', label='EUT Voltage scale input string (e.g. 30.0,30.0,30.0)', default="20.0,20.0,20.0")
info.param('eut.offset_voltage', label='EUT Voltage offset input string (e.g. 0,0,0)', default="0,0,0")

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



