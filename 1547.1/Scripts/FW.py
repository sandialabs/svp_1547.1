# -*- coding: utf-8 -*-
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
from svpelab import pvsim
from svpelab import das
from svpelab import der
from svpelab import hil
from svpelab import result as rslt
import script
import numpy as np
import collections


def interpolation_f_p(f, f_nom, fw_pairs):
    """
    Interpolation function to find the target power (using the FW parameter definition)
    :param f: FW freq target point (Hz)
    :param f_nom: Nominal Frequency (Hz)
    :param fw_pairs: Dictionnary with FW (Hz and %) pairs of characterstic curve
    :param pwr: Power level (p.u.)

    :return: Power test target point (%)
    """
    f_pct = 100.*(f/f_nom)
    f1_pct = 100.*(fw_pairs['F1']/f_nom)
    f2_pct = 100.*(fw_pairs['F2']/f_nom)

    if f_pct < f1_pct:
        p_targ = fw_pairs['P1']
    elif f2_pct <= f_pct:
        p_targ = fw_pairs['P2']
    else:
        #p_targ = fw_pairs['P1']+f_pct*((fw_pairs['P2']-fw_pairs['P1'])/(f2_pct-f1_pct))
        p_targ = (fw_pairs['P1'] - fw_pairs['P1']*((f_pct-f1_pct)/(f2_pct-f1_pct)))


    return float(p_targ)


def fw_passfail(phases, f_nom, fw_pairs, a_f, a_p, daq=None, data=None):
    """
    Determine reactive power target and the min/max q values for pass/fail acceptance based on manufacturer's specified
    accuracies (MSAs)

    :param phases: number of phases of systems
    :param v_value: measured voltage value
    :param a_f: (Hz)
    :param a_p: (%)
    :param v: VW voltage points (volts)
    :param p: VW reactive power points (W)
    :return: passfail for p(v)
    """
    p_rated = ts.param_value('eut_fw.p_rated')

    try:
        daq.sc['F_MEAS'] = measurement_total(data=data, phases=phases, type_meas='F')
        daq.sc['P_MEAS'] = round((measurement_total(data=data, phases=phases, type_meas='P')/p_rated)*100.0,2)

        # To calculate the min/max, you need the measured value
        # Active power target from the lower frequency limit
        daq.sc['P_TARGET_MIN'] = interpolation_f_p(f=daq.sc['F_MEAS'] + a_f, f_nom=f_nom, fw_pairs=fw_pairs) - a_p
        # Active power target from the upper frequency limit
        daq.sc['P_TARGET_MAX'] = interpolation_f_p(f=daq.sc['F_MEAS'] - a_f, f_nom=f_nom, fw_pairs=fw_pairs) + a_p

        ts.log('        P actual, min, max: %s, %s, %s' % (
        daq.sc['P_MEAS'], daq.sc['P_TARGET_MIN'], daq.sc['P_TARGET_MAX']))

        if daq.sc['P_TARGET_MIN'] <= daq.sc['P_MEAS'] <= daq.sc['P_TARGET_MAX']:
            passfail = 'Pass'
        else:
            passfail = 'Fail'

        ts.log('        Passfail: %s' % (passfail))

        return passfail

    except:
        daq.sc['F_MEAS'] = 'No Data'
        daq.sc['P_MEAS'] = 'No Data'
        passfail = 'Fail'
        daq.sc['P_TARGET_MIN'] = 'No Data'
        daq.sc['P_TARGET_MAX'] = 'No Data'

        return passfail


def measurement_total(data, phases, type_meas):
    """
    Sum the EUT reactive power from all phases
    :param data: dataset
    :param phases: number of phases in the EUT
    :param choice: Either V,P or Q
    :return: either total EUT reactive power, total EUT active power or average V
    """
    if type_meas == 'F':
        meas = 'FREQ'
        log_meas = 'Frequency'
    elif type_meas == 'P':
        meas = 'P'
        log_meas = 'Active powers'
    else:
        meas = 'Q'
        log_meas = 'Reactive powers'

    # ts.log_debug('%s' % type_meas)
    # ts.log_debug('%s' % log_meas)

    if phases == 'Single phase':
        ts.log_debug('        %s are: %s' % (log_meas, data.get('AC_{}_1'.format(meas))))
        value = data.get('AC_{}_1')
        phase = 1

    elif phases == 'Split phase':
        ts.log_debug('        %s are: %s, %s' % (log_meas, data.get('AC_{}_1'.format(meas)),
                                                 data.get('AC_{}_2'.format(meas))))
        value = data.get('AC_{}_1'.format(meas)) + data.get('AC_{}_2'.format(meas))
        phase = 2
    elif phases == 'Three phase':
        ts.log_debug('        %s are: %s, %s, %s' % (log_meas,
                                                     data.get('AC_{}_1'.format(meas)),
                                                     data.get('AC_{}_2'.format(meas)),
                                                     data.get('AC_{}_3'.format(meas))))
        value = data.get('AC_{}_1'.format(meas)) + data.get('AC_{}_2'.format(meas)) + data.get('AC_{}_3'.format(meas))
        phase = 3
    else:
        ts.log_error('Inverter phase parameter not set correctly.')
        raise

    if type_meas == 'F':
        # average value of V
        value /= phase

    elif type_meas == 'P':
        return abs(value)

    return value


def f_mean(data, phases):
    """
    Average the EUT frequency from all phases
    :param data: dataset
    :param phases: number of phases in the EUT
    :return: mean EUT frequency
    """
    if phases == 'Single phase':
        freq = data.get('AC_FREQ_1')
    elif phases == 'Split phase':
        freq = (data.get('AC_FREQ_1') + data.get('AC_FREQ_2'))/2
    elif phases == 'Three phase':
        freq = (data.get('AC_FREQ_1') + data.get('AC_FREQ_2') + data.get('AC_FREQ_3'))/3
    else:
        ts.log_error('Inverter phase parameter not set correctly.')


    return freq
def fw_pairs(curve_number,f_nom,fw_params,power):
    """
    TODO: make f and p vector for specified curve
    :param curve_number: VV characteristic curve desired
    :param f_nom: nominal frequency
    :param fw_params: FW parameters
    :return: FW curve point as F1 is frequency start and F2 is frequency stop
    """
    fw_pairs={}
    f1 = round((f_nom + fw_params['dbf']),3)
    f2 = round((f_nom + fw_params['dbf']+(f_nom*fw_params['kf'])),3)
    p1 = 100.0
    p2 = 0
    slope = round(abs((p2-p1)/(f2-f1)),3)
    fw_pairs[curve_number] = {  'F1' : f1,
                                'F2' : round(f1 + (power*100.)/slope,3),
                                'P1' : power*100.0,
                                'P2' : 0.0,
                                'slope' : slope
                                }
    return fw_pairs


def frequency_steps(f_nom, f_small, dbf, a_f, mode):
    """
    :param f_nom: Nominal frequency (Hz)
    :param f_small: Small-signal performance (Hz)
    :param dbof: Deadband frequency (Hz)
    :param a_f: minimum required measurement accuracy (MRA) for frequency (Hz)
    :param mode: Test for frequency can be above or below nominal frequency
    """
    f_steps_dic = collections.OrderedDict()

    f_max = ts.param_value('eut_fw.f_max')
    f_min = ts.param_value('eut_fw.f_min')

    if mode == 'Above':                                 # 1547.1 (5.15.2.2) :
        f_steps_above = [f_nom, (f_nom + dbf) - a_f,    #  h) Begin the adjustment to fH . Ramp the frequency to af below (fN + dbOF )
                        (f_nom + dbf) + a_f,            #  i) Ramp the frequency to af above (fn + dbOF )
                        f_small + f_nom + dbf,          #  j) Ramp the frequency to fsmall + f N + dbOF
                        f_max,                          #  k) Ramp the frequency to fH
                        f_max - f_small,                #  l) Ramp the frequency to fH – fsmall
                        (f_nom + dbf) + a_f,            #  m) Ramp the frequency to af above(fN + dbOF)
                        (f_nom + dbf) - a_f,            #  n) Ramp the frequency to af below(fN + dbOF)
                        f_nom ]                         #  o) Ramp the frequency to fN.
        f_steps_dic[mode] = np.around(f_steps_above, decimals=3)
        ts.log('Testing FW function at the following frequency ({0}) points:\n {1}'.format(mode,f_steps_dic[mode]))

    elif mode == 'Below':                               # 1547.1 (5.15.3.2) :
        f_steps_below = [f_nom, (f_nom + dbf) - a_f,    #  g) Begin the adjustment to fL . Ramp the frequency to af below (fN + dbuf)
                        (f_nom - dbf) - a_f,            #  h) Ramp the frequency to af below (fN – dbUF).
                        f_nom - f_small - dbf,          #  i) Ramp the frequency to fN - fsmall – dbUF.
                        f_min,                          #  j) Ramp the frequency to fL.
                        f_min + f_small,                #  k) Ramp the frequency to fL + fsmall.
                        (f_nom - dbf) - a_f,            #  l) Ramp the frequency to af below (fN – dbUF).
                        (f_nom - dbf) + a_f,            #  m) Ramp the frequency to af above (fN – dbUF).
                        f_nom ]                         #  n) Ramp the frequency to fN.
        f_steps_dic[mode] = np.around(f_steps_below, decimals=3)
        ts.log('Testing FW function at the following frequency ({0}) points:\n {1}'.format(mode,f_steps_dic[mode]))


    return f_steps_dic

def normal_curve_test(mode,fw_curve,fw_params,power,daq,eut,grid,result_summary):
    phases = ts.param_value('eut_fw.phases')
    f_nom = ts.param_value('eut_fw.f_nom')
    # 1547.1: 'af' The term af, is 150% of the minimum
    #  required measurement accuracy for frequency, as specified in
    #  Table 3 of IEEE Std 1547-2018 for steady-state conditions.
    a_f = round(1.5 * 0.01 * f_nom, 3)
    a_p = round(1.5 * 0.05 * 100, 2)
    dataset_filename = 'FW_curve_{0}_pwr_{1}_{2}.csv'.format(fw_curve, power ,mode)

    # 1547.1 : Parameters name from Table 51 - SunSpec Frequency Droop
    # Notes : dbf and kf don't exist but dbof=dbuf and kof=kuf was the point of having two?
    if eut is not None:
        eut.freq_watt_param(params={
            'Ena': True,
            'curve' : curve,
            'dbf': fw_params['dbf'],
            'kf': fw_params['dbf'],
            'RspTms': fw_params['tr']
            })
        ts.log_debug('Initial EUT FW settings are %s' % eut.freq_watt())
    fw_pairs_dic = fw_pairs(fw_curve, f_nom, fw_params,power)
    ts.log_debug('FW pairs are : %s' % fw_pairs_dic)

    f_steps_dic = frequency_steps(f_nom, fw_params['f_small'], fw_params['dbf'], a_f, mode)
    # Start acquisition
    daq.data_capture(True)
    for f_step in f_steps_dic[mode]:
        ts.log('        Recording power at frequnecy %0.3f Hz for 4*t_settling = %0.1f sec.' %
               (f_step, 4 * fw_params['tr']))
        daq.sc['F_TARGET'] = f_step
        daq.sc['event'] = 'f_step_{}'.format(mode)
        p_targ = interpolation_f_p(f=f_step,
                                   f_nom=f_nom,
                                   fw_pairs=fw_pairs_dic[fw_curve])

        grid.freq(f_step)
        daq.sc['P_TARGET'] = p_targ
        for i in range(4):
            ts.sleep(1 * fw_params['tr'])
            daq.sc['event'] = 'TR_{}_done'.format(i+1)
            daq.data_sample()
            data = daq.data_capture_read()

        # Test result accuracy requirements per IEEE1547-4.2 for Q(V)

        fw_passfail_res = fw_passfail(phases=phases,
                                   f_nom=f_nom,
                                   fw_pairs=fw_pairs_dic[fw_curve],
                                   a_f=a_f,
                                   a_p=a_p,
                                   daq=daq,
                                   data=data)

        # Test result accuracy requirements per IEEE1547-4.2 for Q(tr)
        # Still needs to be implemented

        ts.log('        Powers targ, min, max: %s, %s, %s' % (
        daq.sc['P_TARGET'], daq.sc['P_TARGET_MIN'], daq.sc['P_TARGET_MAX']))

        daq.sc['event'] = 'TR_F_TARGET_{}_done'.format(f_step)
        daq.data_sample()

        result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                             (fw_passfail_res,
                              ts.config_name(),
                              power * 100.,
                              mode,
                              daq.sc['F_TARGET'],
                              daq.sc['F_MEAS'],
                              daq.sc['P_TARGET'],
                              daq.sc['P_MEAS'],
                              daq.sc['P_TARGET_MIN'],
                              daq.sc['P_TARGET_MAX'],
                              dataset_filename))

    result_params = {
    'plot.title': 'title_name',
    'plot.x.title': 'Time (sec)',
    'plot.x.points': 'TIME',
    'plot.y.points': 'F_TARGET,F_MEAS',
    'plot.y.title': 'Frequency (Hz)',
    'plot.F_TARGET.point': 'True',
    'plot.y2.points': 'P_TARGET,P_MEAS',                    
    'plot.P_TARGET.point': 'True',
    'plot.P_TARGET.min_error': 'P_TARGET_MIN',
    'plot.P_TARGET.max_error': 'P_TARGET_MAX',
    }

    daq.data_capture(False)
    ds = daq.data_capture_dataset()
    ts.log('Saving file: %s' % dataset_filename)
    ds.to_csv(ts.result_file_path(dataset_filename))
    result_params['plot.title'] = os.path.splitext(dataset_filename)[0]
    ts.result_file(dataset_filename,params=result_params)

    result = script.RESULT_COMPLETE

    return result


def test_run():

    result = script.RESULT_FAIL
    daq = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None
    fw_curves = collections.OrderedDict()

    try:
        """
        Configuration
        """
        # EUT FW parameters
        p_rated = ts.param_value('eut_fw.p_rated')
        f_nom = ts.param_value('eut_fw.f_nom')
        f_min = ts.param_value('eut_fw.f_max')
        f_max = ts.param_value('eut_fw.f_min')
        p_small = ts.param_value('eut_fw.p_small')
        p_large = ts.param_value('eut_fw.p_large')
        phases = ts.param_value('eut_fw.phases')

        # TODO: Check the effiency at 20% for fronius

        eff = {
                1.0 : ts.param_value('eut_fw.efficiency_100')/100,
                0.66:ts.param_value('eut_fw.efficiency_66')/100,
                0.2:ts.param_value('eut_fw.efficiency_20')/100,
        }
        # Test Parameters
        mode = ts.param_value('fw.mode')
        curves = ts.param_value('fw.curves')
        irr = ts.param_value('fw.irr')

        """
        Equipment Configuration
        """         
        # initialize hardware-in-the-loop environment (if applicable)
        ts.log('Configuring HIL system...')
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()
            


        # DAS soft channels
        das_points = {'sc': ('P_TARGET', 'P_TARGET_MIN', 'P_TARGET_MAX','P_ACT','F_TARGET','F_ACT','event')}
        
        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])
        daq.sc['P_TARGET'] = 100
        daq.sc['P_TARGET_MIN'] = 100
        daq.sc['P_TARGET_MAX'] = 100
        daq.sc['F_TARGET'] = f_nom
        daq.sc['event'] = 'None'
        """
        EUT Configuration
        """        
        # Configure the EUT communications
        eut = der.der_init(ts)
        # 1547.1: b) Set all frequency trip parameters to the widest range of adjustability.
        if eut is not None:
            eut.config()
            ts.log_debug(eut.measurements())
            ts.log_debug('L/HFRT and trip parameters set to the widest range : f_min:{0} Hz, f_max:{1} Hz'.format(f_min,f_max))
            eut_response = eut.frt_stay_connected_high(params={'Ena' : True,'ActCrv':0, 'Tms1':3000,'Hz1' : f_max,'Tms2':160,'Hz2' : f_max})
            ts.log_debug('HFRT and trip parameters from EUT : {}'.format(eut_response))
            eut_response = eut.frt_stay_connected_low(params={'Ena' : True,'ActCrv':0, 'Tms1':3000,'Hz1' : f_min,'Tms2':160,'Hz2' : f_min})
            ts.log_debug('LFRT and trip parameters from EUT : {}'.format(eut_response))

        else:
            ts.log_debug('Set L/HFRT and trip parameters to the widest range of adjustability possible.')

        # 1547.1: c)    Set all AC test source source parameters to the nominal operating voltage and frequency
        grid = gridsim.gridsim_init(ts)

        # 1547.1: d)    Adjust the EUT's active power to P_rated
        pv = pvsim.pvsim_init(ts)
        pv.power_set(p_rated)
        pv.power_on()

        """
        Test Configuration
        """
        if mode == 'Both':
            modes = ['Above','Below']
        elif mode == 'Above' :
            modes = ['Above']
        elif mode == 'Below' :
            modes = ['Below']

        # 1547.1 : Using Category III as specified in Table B.1
        if curves == 'Characteristic Curve 1' or curves == 'Both':
            fw_curves[1] = {
                            'dbf' : 0.036 ,
                            'kf' : 0.05,
                            'tr' : 5,
                            'f_small' : p_small * f_nom * 0.05
                            }
        if curves == 'Characteristic Curve 2' or curves == 'Both':
            fw_curves[2] = {
                            'dbf': 0.017,
                            'kf': 0.02,
                            'tr' : 0.2,
                            'f_small' : p_small * f_nom * 0.02
                            }

        if irr == 'All':
            pv_powers = [1., 0.66, 0.2]
        elif irr == '100%':
            pv_powers = [1.]
        elif irr == '66%':
            pv_powers = [0.66]
        elif irr == '20%':
            pv_powers = [0.2]
        ts.log_debug("Power level tested : {}".format(pv_powers))


        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write('Result,'
                             'Test Name,'
                             'Power Level,'
                             'Mode,'
                             'Freq_target,'
                             'Freq_actual,'
                             'Power_target,'
                             'Power_actual,'
                             'P_min,'
                             'P_max,'
                             'Dataset File\n')
        """
        Test start
        """
        for mode in modes:
            for fw_curve ,fw_params in fw_curves.iteritems():
                for power in pv_powers:
                    # Notes: Efficiency is consider... still ok ?
                    pv_power_setting = (p_rated * power) / eff[power]
                    ts.log('Set PV simulator power to {} with efficiency at {} %'.format(p_rated * power, eff[power] * 100.))
                    pv.power_set(pv_power_setting)

                    result = normal_curve_test(mode=mode,
                                               fw_curve=fw_curve,
                                               fw_params=fw_params,
                                               power=power,
                                               daq=daq,
                                               eut=eut,
                                               grid=grid,
                                               result_summary=result_summary)




        result = script.RESULT_COMPLETE
    except script.ScriptFail, e:
        reason = str(e)
        if reason:
            ts.log_error(reason)
    finally:
        if daq is not None:
            daq.close()
        if pv is not None:
            if p_rated is not None:
                pv.power_set(p_rated)
            pv.close()
        if grid is not None:
            if f_nom is not None:
                grid.freq(f_nom)
            grid.close()
        if chil is not None:
            chil.close()
        if eut is not None:
            eut.close()
        if result_summary is not None:
            result_summary.close()

        # create result workbook
        xlsxfile = ts.config_name() + '.xlsx'
        rslt.result_workbook(xlsxfile, ts.results_dir(), ts.result_dir())
        ts.result_file(xlsxfile)

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

info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.0.0')

der.params(info)
# EUT FW parameters
info.param_group('eut_fw', label='EUT FW Configuration',glob=True)
info.param('eut_fw.p_rated', label='Output Power Rating (W)', default=10000.)
info.param('eut_fw.f_nom', label='Nominal AC frequency (Hz)', default=60.)
info.param('eut_fw.f_max', label='Maximum frequency in the continuous operating region (Hz)', default=66.)
info.param('eut_fw.f_min', label='Minimum frequency in the continuous operating region (Hz)', default=56.)
# TODO: Check about this two parameters p_small and p_large since it is normally provided by the inverter model
info.param('eut_fw.p_small', label='Small-signal performance (%)', default=0.05)
# Notes:eut_fw.p_large is not use the standard
#info.param('eut_fw.p_large', label='Large-signal performance in % of rated power per minute', default=10.)
info.param('eut_fw.phases', label='Phases', default='Single Phase', values=['Single phase', 'Split phase', 'Three phase'])
# TODO: Do we keep the same approach with effiency ?
info.param('eut_fw.efficiency_20', label='CEC Efficiency list for power level = 20% at nominal VDC', default=97.0)
info.param('eut_fw.efficiency_66', label='CEC Efficiency list for power level = 66% at nominal VDC', default=97.1)
info.param('eut_fw.efficiency_100', label='CEC Efficiency list for power level = 100% at nominal VDC', default=96.9)
info.param_group('fw', label='Test Parameters')
info.param('fw.mode', label='Frequency Watt test mode', default='Both',values=['Above', 'Below', 'Both'])
info.param('fw.curves', label='Curves to Evaluate', default='Both',values=['Characteristic Curve 1', 'Characteristic Curve 2', 'Both'])
info.param('fw.irr', label='Power Levels', default='All',values=['100%', '66%', '20%', 'All'])

gridsim.params(info)
pvsim.params(info)
das.params(info)
hil.params(info)

# info.logo('sunspec.gif')

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


