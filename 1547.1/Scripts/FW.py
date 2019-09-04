"""
Copyright (c) 2017, Sandia National Labs, SunSpec Alliance and CanmetENERGY
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
from svpelab import result as rslt
from svpelab import p1547
import script
import numpy as np
import collections

def test_run():

    result = script.RESULT_FAIL
    # Variables use in script
    daq = None
    data = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None
    dataset_filename = None
    fw_curves = []
    fw_response_time = [0, 0, 0]



    try:
        """
        Test Configuration
        """
        # Get all test script parameter
        mode = ts.param_value("fw.mode")
        eut_absorb = ts.param_value("eut_fw.absorb")
        if eut_absorb == "Yes":
            absorb_powers = [False, True]
        else:
            absorb_powers = [False]
        p_rated = ts.param_value('eut.p_rated')
        s_rated = ts.param_value('eut.s_rated')
        # DC voltages
        v_nom_in = ts.param_value('eut.v_in_nom')
        irr = ts.param_value('fw.power_lvl')
        if mode == 'Above':
            if irr == 'All':
                pwr_lvls = [1., 0.66, 0.2]
            elif irr == '100%':
                pwr_lvls = [1.]
            elif irr == '66%':
                pwr_lvls = [0.66]
            elif irr == '20%':
                pwr_lvls = [0.2]
        else:
            pwr_lvls = [1.]
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

        '''
        a) Connect the EUT according to the instructions and specifications provided by the manufacturer.
        '''
        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # DAS soft channels
        # TODO : add to library 1547
        #das_points = {'sc': ('P_TARGET', 'P_TARGET_MIN', 'P_TARGET_MAX', 'P_MEAS', 'F_TARGET', 'F_MEAS', 'event')}
        das_points = p1547.get_sc_points()
        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])
        if daq is not None:
            daq.sc['P_TARGET'] = 100
            daq.sc['P_TARGET_MIN'] = 100
            daq.sc['P_TARGET_MAX'] = 100
            daq.sc['P_MEAS'] = 100
            daq.sc['F_TARGET'] = f_nom
            daq.sc['P_TARGET'] = p_rated
            daq.sc['event'] = 'None'
            ts.log('DAS device: %s' % daq.info())

        # Configure the EUT communications
        eut = der.der_init(ts)
        '''
        b) Set all frequency trip parameters to the widest range of adjustability. 
            Disable all reactive/active power control functions.
        '''
        if eut is not None:
            eut.config()
            ts.log_debug(eut.measurements())
            ts.log_debug(
                'L/HFRT and trip parameters set to the widest range : f_min:{0} Hz, f_max:{1} Hz'.format(f_min,
                                                                                                         f_max))
            eut_response = eut.frt_stay_connected_high(
                params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000, 'Hz1': f_max, 'Tms2': 160, 'Hz2': f_max})
            ts.log_debug('HFRT and trip parameters from EUT : {}'.format(eut_response))
            eut_response = eut.frt_stay_connected_low(
                params={'Ena': True, 'ActCrv': 0, 'Tms1': 3000, 'Hz1': f_min, 'Tms2': 160, 'Hz2': f_min})
            ts.log_debug('LFRT and trip parameters from EUT : {}'.format(eut_response))

        else:
            ts.log_debug('Set L/HFRT and trip parameters to the widest range of adjustability possible.')

        '''
        c) Set all AC test source parameters to the nominal operating voltage and frequency 
        '''
        grid = gridsim.gridsim_init(ts)
        if grid is not None:
            grid.freq(f_nom)
            if mode == 'Below':
                # 1547.1 :  Frequency is ramped at the ROCOF for the category of the EUT.
                #           In this case the ROCOF is based on table 21 of 1547.2018
                #           (Category III is use because of table B.1 of 1547.2018)
                #           The ROCOF unit : Hz/s
                ts.log('Set Grid simulator ROCOF to 3 Hz/s')
                grid.rocof(3.0)

        """
        A separate module has been create for the 1547.1 Standard
        """
        lib_1547 = p1547.module_1547(ts=ts, aif='FW')
        ts.log_debug("1547.1 Library configured for %s" % lib_1547.get_test_name())

        # result params
        result_params = lib_1547.get_rslt_param_plot()

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write(lib_1547.get_rslt_sum_col_name())

        '''
        above_d) Adjust the EUT's available active power to Prated .
        below_d) ""         ""          "". Set the EUT's output power to 50% of P rated .
        '''
        pv = pvsim.pvsim_init(ts)
        if pv is not None:
            pv.iv_curve_config(pmp=p_rated, vmp=v_nom_in)
            pv.irradiance_set(1000.)
        if mode == 'Below':
            if eut is not None:
                ts.log_debug("In Below mode, EUT's output power is set to 50%% of %s (Prated)" % p_rated)
                eut.limit_max_power(params={
                    'MaxLimWEna': True,
                    'MaxLimW': round(p_rated / 2.0, 2)
                })
        """
        Test start
        """
        '''
        above_r) For EUT's that can absorb power, rerun Characteristic 1 allowing the unit to absorb power by
        programing a negative Pmin . 

        below_p) ""                 ""                  "". Set the unit to absorb power at -50% of P rated . 
        '''
        for absorb_power in absorb_powers:
            if absorb_power:
                if eut is not None:
                    if mode == 'Below':
                        ts.log_debug("Config EUT's absorb power at -50%% of P rated")
                        eut.limit_max_power(params={
                            'MaxLimWEna': True,
                            'MaxLimW': round(p_rated / 2.0, 2) * -1
                        })
                    else:
                        ts.log_debug("Config EUT's absorb power to %s (P\'min)" % p_min_prime)
                        eut.limit_max_power(params={
                            'MaxLimWEna': True,
                            'MaxLimW': p_min_prime
                        })

            '''
              above_q) Repeat steps b) through p) for Characteristic 2. 

              below_o) ""           ""              ""
            '''
            for fw_curve in fw_curves:
                ts.log('Starting test with characteristic curve %s' % (fw_curve))
                fw_param = lib_1547.get_params(fw_curve)
                a_f = lib_1547.MSA_F *1.5

                f_steps_dic = {}
                f_steps_dic[mode] = collections.OrderedDict()
                if mode == 'Above':  # 1547.1 (5.15.2.2):
                    f_steps_dic[mode]['Step H'] = (f_nom + fw_param['dbf']) - a_f
                    f_steps_dic[mode]['Step I'] = (f_nom + fw_param['dbf']) + a_f
                    f_steps_dic[mode]['Step J'] = fw_param['f_small'] + f_nom + fw_param['dbf']
                    # STD_CHANGE : step k) should consider the accuracy
                    f_steps_dic[mode]['Step K'] = f_max - a_f
                    f_steps_dic[mode]['Step L'] = f_max - fw_param['f_small']
                    f_steps_dic[mode]['Step M'] = (f_nom + fw_param['dbf']) + a_f
                    f_steps_dic[mode]['Step N'] = (f_nom + fw_param['dbf']) - a_f
                    f_steps_dic[mode]['Step O'] = f_nom

                    for step, frequency in f_steps_dic[mode].iteritems():
                        f_steps_dic[mode].update({step: np.around(frequency, 3)})
                        if frequency > f_max:
                            ts.log("{0} frequency step (value : {1}) changed to fH (f_max)".format(step, frequency))
                            f_steps_dic[mode].update({step: f_max})


                elif mode == 'Below':  # 1547.1 (5.15.3.2):
                    f_steps_dic[mode]['Step G'] = (f_nom + fw_param['dbf']) - a_f
                    f_steps_dic[mode]['Step H'] = (f_nom - fw_param['dbf']) - a_f
                    f_steps_dic[mode]['Step I'] = f_nom - fw_param['f_small'] - fw_param['dbf']
                    # STD_CHANGE : step j) should consider the accuracy
                    f_steps_dic[mode]['Step J'] = f_min + a_f
                    f_steps_dic[mode]['Step K'] = f_min + fw_param['f_small']
                    f_steps_dic[mode]['Step L'] = (f_nom - fw_param['dbf']) - a_f
                    f_steps_dic[mode]['Step M'] = (f_nom - fw_param['dbf']) + a_f
                    f_steps_dic[mode]['Step N'] = f_nom

                    for step, frequency in f_steps_dic[mode].iteritems():
                        f_steps_dic[mode].update({step: np.around(frequency, 3)})
                        if frequency < f_min:
                            ts.log("{0} frequency step (value : {1}) changed to fL (f_min)".format(step, frequency))
                            f_steps_dic[mode].update({step: f_min})
                '''
                p) Repeat test steps b) through o) with the EUT power set at 20% and 66% of rated power. 
                '''
                for power in pwr_lvls:
                    if pv is not None:
                        pv_power_setting = (p_rated * power)
                        pv.iv_curve_config(pmp=pv_power_setting, vmp=v_nom_in)
                        pv.irradiance_set(1000.)
                    '''
                    e) Set EUT freq-watt parameters to the values specified by Characteristic 1. 
                        All other functions should be turned off. 
                    '''

                    # STD_CHANGE : dbf and kf don't exist but dbof=dbuf and kof=kuf was the point of having two?
                    if eut is not None:
                        eut.freq_watt_param(params={
                            'Ena': True,
                            'curve': fw_curve,
                            'dbf': fw_param['dbf'],
                            'kf': fw_param['kof'],
                            'RspTms': fw_param['tr']
                        })
                        '''
                        f) Verify freq-watt mode is reported as active and that 
                            the correct characteristic is reported. 
                        '''
                        ts.log_debug('Initial EUT FW settings are %s' % eut.freq_watt())

                    ts.log_debug('Test parameters :  %s' % fw_param)
                    ts.log('Starting data capture for power = %s' % power)

                    dataset_filename = 'FW_{0}_PWR_{1}_{2}'.format(fw_curve, power, mode)
                    if absorb_power:
                        dataset_filename = 'FW_{0}_PWR_{1}_{2}_ABSORB'.format(fw_curve, power, mode)

                    ts.log('------------{}------------'.format(dataset_filename))
                    '''
                    g) Once steady state is reached, read and record the EUT's 
                    active power, reactive power, voltage,frequency, and current measurements. 
                    '''
                    # STD_CHANGE there should be a wait for steady state to be reached in both mode
                    step = 'Step F'
                    daq.sc['event'] = step
                    daq.data_sample()
                    ts.log('Wait for steady state to be reached')
                    ts.sleep(4 * fw_param['tr'])
                    daq.data_capture(True)

                    for step_label, f_step in f_steps_dic[mode].iteritems():
                        ts.log('Frequency step: setting Grid simulator frequency to %s (%s)' % (f_step, step_label))
                        p_initial = lib_1547.get_initial(daq=daq, step=step_label)
                        if grid is not None:
                            grid.freq(f_step)
                        f_p_analysis = lib_1547.criteria(daq=daq,
                                                         tr=fw_param['tr'],
                                                         step=step_label,
                                                         initial_value=p_initial,
                                                         target=f_step,
                                                         mode=mode,
                                                         curve =fw_curve,
                                                         pwr_lvl=power)
                        result_summary.write(lib_1547.write_rslt_sum(analysis=f_p_analysis, step=step_label,
                                                                     filename=dataset_filename))

                    dataset_filename = dataset_filename + ".csv"
                    daq.data_capture(False)
                    ds = daq.data_capture_dataset()
                    ts.log('Saving file: %s' % dataset_filename)
                    ds.to_csv(ts.result_file_path(dataset_filename))
                    result_params['plot.title'] = os.path.splitext(dataset_filename)[0]
                    ts.result_file(dataset_filename, params=result_params)

        result = script.RESULT_COMPLETE

        return result

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
            if p_rated is not None:
                pv.power_set(p_rated)
            pv.close()
        if grid is not None:
            if f_nom is not None:
                grid.voltage(f_nom)
            grid.close()
        if chil is not None:
            chil.close()
        if eut is not None:
            eut.volt_var(params={'Ena': False})
            eut.volt_watt(params={'Ena': False})
            eut.close()
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
        
        ts.svp_version(required='1.5.9')
        result = test_run()

        ts.result(result)
        if result == script.RESULT_FAIL:
            rc = 1

    except Exception, e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)

info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.2.0')

# FW test parameters
info.param_group('fw', label='Test Parameters')
info.param('fw.mode', label='Frequency Watt mode (Above or Below nominal frequency)', default='Both',\
           values=['Above', 'Below'])
info.param('fw.test_1', label='Characteristic 1 curve', default='Enabled', values=['Disabled', 'Enabled'])
info.param('fw.test_1_tr', label='Response time (s) for curve 1', default=10.0,active='fw.test_1',\
           active_value=['Enabled'])
info.param('fw.test_2', label='Characteristic 2 curve', default='Enabled', values=['Disabled', 'Enabled'])
info.param('fw.test_2_tr', label='Response time (s) for curve 2', default=10.0,active='fw.test_2',\
           active_value=['Enabled'])
info.param('fw.power_lvl', label='Power Levels', default='All', values=['100%', '66%', '20%', 'All'],\
           active='fw.mode', active_value=['Above'])

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


# EUT FW parameters
info.param_group('eut_fw', label='FW - EUT Parameters', glob=True)
info.param('eut_fw.p_small', label='Small-signal performance (%)', default=0.05)
info.param('eut_fw.absorb', label='Can DER absorb active power?', default='No',
           values=['No', 'Yes'])
info.param('eut_fw.p_rated_prime', label='P\'rated: Output power rating while absorbing power (W) (negative)',
           default=-3000.0, active='eut_vw.sink_power', active_value=['Yes'])
info.param('eut_fw.p_min_prime', label='P\'min: minimum active power while sinking power(W) (negative)',
           default=-0.2*3000.0, active='eut_vw.sink_power', active_value=['Yes'])


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


