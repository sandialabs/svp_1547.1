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
import script
from svpelab import result as rslt
import numpy as np
import collections
import cmath
import math

def sequence012_to_abc(params=None):
    """
    TODO: Convert desired sequence 012 into phase a,b,c magnitudes and angles

    :param params={'zero':None, 'positive'=None, 'negative'=None}
    :return: magnitude dictionary containing phase and angles into degrees
    :        angles dictionary containing phase and angles into degrees
    """
    a=cmath.exp(2*cmath.pi*1j/3)
    a2=cmath.exp(4*cmath.pi*1j/3)
    magnitudes={}
    angles={}
    vector={}
    #Fortescue equation to convert into ABC
    #Current driver takes channel 1,2,3 instead of a,b,c
    """
    vector['a']=(params['0']+params['+']+params['-'])
    vector['b']=(params['0']+a2*params['+']+a*params['-'])
    vector['c']=(params['0']+a*params['+']+a2*params['-'])
    """
    vector['1']=(params['0']+params['+']+params['-'])
    vector['2']=(params['0']+a2*params['+']+a*params['-'])
    vector['3']=(params['0']+a*params['+']+a2*params['-'])
    for phase,value in vector.iteritems():        
        magnitudes[phase],angles[phase]=cmath.polar(value)
        #Rounding up values
        magnitudes[phase]=round(magnitudes[phase],2)
        #convert into degrees
        angles[phase]=str(round(angles[phase]*180/math.pi,3))+'DEGree'
    return magnitudes, angles

def constant_pf_test(pf, MSA_P, MSA_Q,v_nom,grid, daq, result_summary,dataset_filename):

    pf_settling_time = ts.param_value('eut.pf_settling_time')
    v_low=ts.param_value('eut.v_low')
    v_high=ts.param_value('eut.v_high')
    
    steps =  ([v_low,   pf_settling_time],\
              [v_high,  pf_settling_time],\
              [v_low,   pf_settling_time],\
               [0,   1.0,   0.10,   60],\
               [0,   1.0,   0.05,   300],\
               [0,   1.0,   0.03,   300],\
               [0,   1.0,   0,      30],\
               [0,   1.0,   -0.12,  60],\
               [0,   1.0,   -0.05,  300],\
               [0,   1.0,   -0.03,  300],\
               [0,   1.0,   0,      30])

    mag={}
    angle={}
    mode = ts.param_value('vv.mode')
    daq.data_capture(True)
    #daq.data_sample()
    data = daq.data_capture_read()
    
    for step in steps:
        if len(step)> 2:
            #ts.log('steps count: %s' % (len(step)))
            daq.sc['event'] = 'zero_{}_pos_{}_neg_{}'.format(step[0],step[1],step[2])
            mag,angle=sequence012_to_abc(params={'0':step[0], '+':step[1], '-':step[2]})
            ts.log_debug('For sequence zero:%0.2f postive:%0.2f negative:%0.2f' % (step[0],step[1],step[2]))
            ts.log('Setting magnitudes phA:%s phB:%s phC:%s' % (mag['1'],mag['2'],mag['3']))
            ts.log('Setting angles phA:%s phB:%s phC:%s' % (angle['1'],angle['2'],angle['3']))

            if grid is not None:
                grid.voltage(mag)
                grid.phases_angles(params=angle)
            ts.sleep(step[3])
            #ts.sleep(1)
            daq.sc['event'] = 'T_settling_done_{}'.format(step[3])
        else:
            daq.sc['event'] = 'vstep_{}'.format(step[0])
            if grid is not None:
                grid.voltage(step[0])
            ts.log('Setting voltage at %d for %d' % (step[0], step[1]))
            ts.sleep(step[1])
            #ts.sleep(1)
            daq.sc['event'] = 'T_settling_done_{}'.format(step[1])

        #Test result accuracy requirements per IEEE1547-4.2 for Q(P)
        Q_P_passfail=q_p_criteria(data=data,
                                  pf=pf,
                                  MSA_P=MSA_P,
                                  MSA_Q=MSA_Q,
                                  daq=daq)

        daq.data_sample()
        data = daq.data_capture_read()
        result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                     (Q_P_passfail,
                      ts.config_name(),
                      mode,
                      daq.sc['V_MEAS'],
                      daq.sc['P_MEAS'],
                      daq.sc['Q_MEAS'],
                      daq.sc['Q_TARGET_MIN'],
                      daq.sc['Q_TARGET_MAX'],
                      dataset_filename))
    return 1

def q_p_criteria(data, pf, MSA_P, MSA_Q, daq):
    """
    Determine Q(P) passfail criteria with PF and accuracies (MSAs)

    :param pf: power factor
    :param v_msa: manufacturer's specified accuracy of voltage
    :param q_msa: manufacturer's specified accuracy of reactive power
    :return: passfail value
    """

    try:
        daq.sc['V_MEAS'] = measurement_total(data=data, type_meas='V')
        daq.sc['Q_MEAS'] = measurement_total(data=data, type_meas='Q')
        daq.sc['P_MEAS'] = measurement_total(data=data, type_meas='P')
        
        #To calculate the min/max, you need the measured value
        p_min=daq.sc['P_MEAS']+1.5*MSA_P
        p_max=daq.sc['P_MEAS']-1.5*MSA_P
        daq.sc['Q_TARGET_MIN']= math.sqrt(pow(p_min,2)*((1/pf)-1))-1.5*MSA_Q  # reactive power target from the lower voltage limit
        daq.sc['Q_TARGET_MAX']= math.sqrt(pow(p_max,2)*((1/pf)-1))+1.5*MSA_Q  # reactive power target from the upper voltage limit

        ts.log('        Q actual, min, max: %s, %s, %s' % (daq.sc['Q_MEAS'], daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX']))
        
        if daq.sc['Q_TARGET_MIN'] <= AC_Q <= daq.sc['Q_TARGET_MAX']:
            passfail = 'Pass'
        else:
            passfail = 'Fail'

        ts.log('        Q(P) Passfail: %s' % (passfail))

        return passfail
    
    except:
        daq.sc['V_MEAS'] = 'No Data'
        daq.sc['P_MEAS'] = 'No Data'
        daq.sc['Q_MEAS'] = 'No Data'
        passfail = 'Fail'
        daq.sc['Q_TARGET_MIN']='No Data'
        daq.sc['Q_TARGET_MAX']='No Data'

        return passfail

def measurement_total(data, type_meas):
    """
    Sum the EUT reactive power from all phases
    :param data: dataset
    :param phases: number of phases in the EUT
    :param choice: Either V,P or Q 
    :return: either total EUT reactive power, total EUT active power or average V
    """
    phases=ts.param_value('eut.phases')
    if type_meas == 'V':
        meas='VRMS'
        log_meas='Voltages'
    elif type_meas == 'P':
        meas='P'
        log_meas='Active powers'
    else:
        meas='Q'
        log_meas='Reactive powers'
    ts.log_debug('%s' % type_meas)
    ts.log_debug('%s' % log_meas)
    if phases == 'Single phase':
        ts.log_debug('        %s are: %s' % (log_meas, data.get('AC_{}_1'.format(meas))))
        value = data.get('AC_{}_1')

    elif phases == 'Split phase':
        ts.log_debug('        %s are: %s, %s' % (log_meas,data.get('AC_{}_1'.format(meas)),
                                                    data.get('AC_{}_2'.format(meas))))
        value = data.get('AC_{}_1'.format(meas)) + data.get('AC_{}_2'.format(meas))

    elif phases == 'Three phase':
        ts.log_debug('        %s are: %s, %s, %s' % (log_meas,
                                                        data.get('AC_{}_1'.format(meas)),
                                                        data.get('AC_{}_2'.format(meas)),
                                                        data.get('AC_{}_3'.format(meas))))
        value = data.get('AC_{}_1'.format(meas)) + data.get('AC_{}_2'.format(meas)) + data.get('AC_{}_3'.format(meas))
    else:
        ts.log_error('Inverter phase parameter not set correctly.')
        ts.log_error('phases=%s' % phases)
        raise

    if type_meas == 'V':
        #average value of V
        value=value/3
        
    elif type_meas == 'P':
        return abs(value)

    return value

def test_run():

    result = script.RESULT_FAIL
    grid = None
    pv = p_rated = None
    daq = None
    eut = None
    rs = None
    chil = None
    result_summary = None

    #sc_points = ['PF_TARGET', 'PF_MAX', 'PF_MIN']

    # result params
    result_params = {
        'plot.title': ts.name,
        'plot.x.title': 'Time (sec)',
        'plot.x.points': 'TIME',
        'plot.y.points': 'AC_PF_1, PF_TARGET',
        'plot.y.title': 'Power Factor',
        'plot.y2.points': 'AC_IRMS_1',
        'plot.y2.title': 'Current (A)'
    }

    try:
        p_rated = ts.param_value('eut.p_rated')
        p_min = ts.param_value('eut.p_min')
        pf_min_ind = ts.param_value('eut.pf_min_ind')
        pf_min_cap = ts.param_value('eut.pf_min_cap')
        pf_settling_time = ts.param_value('eut.pf_settling_time')
        pf_msa = ts.param_value('eut.pf_msa')
        phases = ts.param_value('eut.phases')
        MSA_Q=ts.param_value('eut.q_msa')
        MSA_P=ts.param_value('eut.p_msa')
        v_nom_in=ts.param_value('eut.v_in_nom')
        #pf_mid_ind = (1. + pf_min_ind)/2.
        #pf_mid_cap = -(1. - pf_min_cap)/2.

        '''
        2) Set all AC source parameters to the normal operating conditions for the EUT. 
        '''

        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # grid simulator is initialized with test parameters and enabled
        grid = gridsim.gridsim_init(ts)
        if grid is not None:
            grid.voltage(v_nom_in)
                    
        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts)
        pv.power_set(p_rated)
        pv.power_on()

        # DAS soft channels
        das_points = {'sc': ('V_MEAS', 'P_MEAS', 'Q_MEAS', 'Q_TARGET_MIN', 'Q_TARGET_MAX','PF_TARGET', 'event')}

        # initialize data acquisition
        daq = das.das_init(ts, sc_points=das_points['sc'])

        if daq :
            daq.sc['V_MEAS'] = 100
            daq.sc['P_MEAS'] = 100
            daq.sc['Q_MEAS'] = 100
            daq.sc['Q_TARGET_MIN'] = 100
            daq.sc['Q_TARGET_MAX'] = 100
            daq.sc['PF_TARGET'] = 1
            daq.sc['event'] = 'None'
            
        ts.log('DAS device: %s' % daq.info())

        '''
        3) Turn on the EUT. It is permitted to set all L/HVRT limits and abnormal voltage trip parameters to the
        widest range of adjustability possible with the CPF enabled in order not to cross the must trip
        magnitude threshold during the test.
        '''
        # it is assumed the EUT is on
        eut = der.der_init(ts)
        if eut is not None:
            eut.config()
            # disable volt/var curve
            eut.volt_var(params={'Ena': False})
            ts.log_debug('If not done already, set L/HVRT and trip parameters to the widest range of adjustability.')

        # set target power factors
        pf_targets = {}
        if ts.param_value('cpf.pf_min_ind') == 'Enabled':
            pf_targets['cpf_min_ind']=ts.param_value('cpf.pf_min_ind_value')
        if ts.param_value('cpf.pf_mid_ind') == 'Enabled':
            pf_targets['cpf_mid_ind']=ts.param_value('cpf.pf_mid_ind_value')
        if ts.param_value('cpf.pf_min_cap') == 'Enabled':
            pf_targets['cpf_min_cap']=ts.param_value('cpf.pf_min_cap_value')
        if ts.param_value('cpf.pf_mid_cap') == 'Enabled':
            pf_targets['cpf_mid_cap']=ts.param_value('cpf.pf_mid_cap_value')

        n_iter = ts.param_value('cpf.n_iter')
        power_levels = ts.param_value('cpf.irr')

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)

        result_summary.write('Result,Test Name,Power Level,Iteration,PF_ACT,PF Target,'
                             'PF MSA,PF Min Allowed,PF Max Allowed,Dataset File,'
                             'AC_P, AC_Q, P_TARGET,Q_TARGET\n')

        for test, pf in pf_targets.iteritems():
            ts.log('Starting test %s at %s' % (test,pf))

            '''
            5) Set the input source to produce Prated for the EUT.
            '''
            if eut is not None:
                if chil is not None:
                    eut.fixed_pf(params={'Ena': True, 'PF': round(pf*100,0)})  # HACK for ASGC - To be fixed in firmware
                else:
                    eut.fixed_pf(params={'Ena': True, 'PF': pf})

            if grid is not None:
                grid.voltage(v_nom_in)
            ts.log('Setting grid at %s%% of p_rated' % (p_min*100))
            pv.power_set(p_rated * p_min)
            ts.sleep(4*pf_settling_time)
            ts.log('Setting grid at 100%% of p_rated: %s' % (p_rated))
            pv.power_set(p_rated)
            ts.sleep(4*pf_settling_time)

            for count in range(1, n_iter + 1):
                ts.log('Starting pass %s' % (count))
                '''
                6) Set the EUT power factor to unity. Measure the AC source voltage and EUT current to measure the
                displacement
                '''

                dataset_filename='%s_%d_iter_%d' % (test,pf*100,count)
                daq.sc['PF_TARGET'] = pf


                if eut is not None:
                    if chil is not None:
                        parameters = {'Ena': True, 'PF': pf*100}  # HACK for ASGC - To be fixed in their firmware
                    else:
                        parameters = {'Ena': True, 'PF': pf}
                    ts.log('PF set: %s' % (parameters))
                    eut.fixed_pf(params=parameters)
                    pf_setting = eut.fixed_pf()
                    ts.log('PF setting read: %s' % (pf_setting))
                ts.log('Starting data capture for pf = %s' % (pf))

                constant_pf_test(pf=pf,
                                 MSA_P=MSA_P,
                                 MSA_Q=MSA_Q,
                                 v_nom=v_nom_in,
                                 grid=grid,
                                 daq=daq,
                                 result_summary=result_summary,
                                 dataset_filename=dataset_filename)
                """
                # create result summary entry
                pf_points = ['AC_PF']
                va_points = ['AC_S']
                p_points = ['AC_P']
                q_points = ['AC_Q']

                pf_act = []
                va_act = []
                p_act = []  # Used for plotting results on P-Q plane
                q_act = []  # Used for plotting results on P-Q plane
                """

                ts.log('Sampling complete')
                daq.data_capture(False)
                ds = daq.data_capture_dataset()
                data = daq.data_capture_read()
                ts.log('Saving file: %s' % dataset_filename)
                ds.to_csv(ts.result_file_path(dataset_filename))
                result_params['plot.title'] = os.path.splitext(dataset_filename)[0]
                ts.result_file(dataset_filename, params=result_params)
                
                """
                # create result summary entry
                pf_act = []
                va_act = []
                p_act = []  # Used for plotting results on P-Q plane
                q_act = []  # Used for plotting results on P-Q plane
                va_nameplate_per_phase = p_rated/len(pf_points)  # assume VA_nameplate and P_rated are the same

                p_target_at_rated = np.fabs(pf) * power
                if pf < 0:
                    q_target_at_rated = np.sin(np.arccos(pf)) * power  # PF < 0, +Q
                else:
                    q_target_at_rated = -np.sin(np.arccos(pf)) * power  # PF > 0, -Q
                
                result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                     (passfail,
                                      ts.config_name(),
                                      power * 100,
                                      count,
                                      pf_act,
                                      pf,
                                      pf_msa,
                                      pf_lower,
                                      pf_upper,
                                      filename,
                                      p_act,
                                      q_act,
                                      p_target_at_rated,
                                      q_target_at_rated))
                """
                '''
                8) Repeat steps (6) - (8) for two additional times for a total of three repetitions.
                '''
            '''
            9) Repeat steps (5) - (7) at two additional power levels. One power level shall be a Pmin or 20% of
            Prated and the second at any power level between 33% and 66% of Prated.
            '''
        '''
        10) Repeat Steps (6) - (9) for Tests 2 - 5 in Table SA12.1
        '''

        result = script.RESULT_COMPLETE

    except script.ScriptFail, e:
        reason = str(e)
        if reason:
            ts.log_error(reason)
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

    except Exception, e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)

info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.1.0')

info.param_group('cpf', label='Test Parameters')
info.param('cpf.irr', label='Power Level for Test (%)', default=100)
info.param('cpf.n_iter', label='Number of test repetitions', default=3)

info.param('cpf.pf_min_ind', label='Minimum inductive', default='Enabled', values=['Disabled', 'Enabled'])
info.param('cpf.pf_min_ind_value', label='PF_min_ind (Underexcited)', default=0.90,\
           active='cpf.pf_min_ind', active_value=['Enabled'])
info.param('cpf.pf_mid_ind', label='Mid-range inductive', default='Enabled', values=['Disabled', 'Enabled'])
info.param('cpf.pf_mid_ind_value', label='Mid-range inductive PF value (PFmin_ind < PFmid < 1.00):', default=0.99,\
           active='cpf.pf_mid_ind', active_value=['Enabled'])
info.param('cpf.pf_min_cap', label='Minimum capacitive', default='Enabled', values=['Disabled', 'Enabled'])
info.param('cpf.pf_min_cap_value', label='PF_min_cap (Overexcited) (negative value)', default=0.90,\
           active='cpf.pf_min_cap', active_value=['Enabled'])
info.param('cpf.pf_mid_cap', label='Mid-range capacitive', default='Enabled', values=['Disabled', 'Enabled'])
info.param('cpf.pf_mid_cap_value', label='Mid-range capacitive value (PFmin_cap < PFmid < 1.00):', default=0.99,\
           active='cpf.pf_mid_cap', active_value=['Enabled'])

info.param_group('eut', label='EUT Parameters', glob=True)
info.param('eut.p_rated', label='P_rated: Output power rating (W)', default=3000.0)
info.param('eut.p_min', label='P_min: Minimum active power (PU)', default=0.2)
info.param('eut.p_msa', label='Active power manufacturers stated accuracy (Var)', default=0.0)
info.param('eut.q_msa', label='Reactive power manufacturers stated accuracy (Var)', default=0.0)
info.param('eut.v_in_nom', label='V_in_nom: Nominal voltage output (V)', default=120.0)
info.param('eut.v_in_min', label='V_in_min: Nominal voltage output (V)', default=0.0)
info.param('eut.v_in_max', label='V_in_max: Nominal voltage output (V)', default=0.0)
info.param('eut.v_nom', label='V_nom: Nominal voltage output (V)', default=120.0)
info.param('eut.v_low', label='Minimum AC voltage (V)', default=0.0)
info.param('eut.v_high', label='Maximum AC voltage (V)', default=0.0)
info.param('eut.phases', label='Phases', values=['Single phase', 'Split phase', 'Three phase'], default='Three phase')

info.param('eut.pf_settling_time', label='PF Settling Time (secs)', default=1.0)
info.param('eut.pf_msa', label='PF Manufacturer Stated Accuracy (PF units)', default=5.0)

der.params(info)
das.params(info)
gridsim.params(info)
loadsim.params(info)
pvsim.params(info)
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


