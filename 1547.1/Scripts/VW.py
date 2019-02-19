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
from svpelab import pvsim
from svpelab import das
from svpelab import der
from svpelab import hil
from svpelab import result as rslt
import script
import math
import numpy as np
import collections
import cmath

def sequence012_to_abc(params=None):
    """
    TODO: Switch vector 123 to abc when driver will be updated

    :param params={'zero':None, 'positive'=None, 'negative'=None}
    :return: magnitude dictionary containing phase and angles into degrees
    :        angles dictionary containing phase and angles into degrees
    """
    v_nom=ts.param_value('eut.v_nom')
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
        magnitudes[phase]=round(magnitudes[phase]*v_nom,2)
        #convert into degrees
        angles[phase]=str(round(angles[phase]*180/math.pi,3))+'DEGree'
    return magnitudes, angles

def imbalanced_grid_test(n_iter,power, daq,eut,grid,result_summary):
    """
    TODO: Function that execute test in mode imbalanced grid

    :param curve_number: VV characteristic curve desired
    :param v_nom: VV nominal voltage output
    :param s_rated: VV apparent power output
    :return: curve tests vector
    """

    seq012 =  ([0,   1.0,   0.10,   60],\
               [0,   1.0,   0.05,   300],\
               [0,   1.0,   0.03,   300],\
               [0,   1.0,   0,      30],\
               [0,   1.0,   -0.12,  60],\
               [0,   1.0,   -0.05,  300],\
               [0,   1.0,   -0.03,  300],\
               [0,   1.0,   0,      30])

    v_nom=ts.param_value('eut.v_nom')
    phases=ts.param_value('eut.phases')
    a_v=round(1.5*0.01*ts.param_value('eut.v_nom'),2)
    p_mra=round(1.5*0.05*ts.param_value('eut.s_rated'),1)
    mag={}
    angle={}
    
    dataset_filename = 'VW_Imbalanced_pwr_%0.2f_iter_%s.csv' % (int(power*100), n_iter + 1)

    daq.data_capture(True)
    #daq.data_sample()
    #data = daq.data_capture_read()
    v_pairs = curve_v_p(    curve_number=1,
                        power=power)

    for steps in seq012:
        daq.sc['event'] = 'zero_{}_pos_{}_neg_{}'.format(steps[0],steps[1],steps[2])
        mag,angle=sequence012_to_abc(params={'0':steps[0], '+':steps[1], '-':steps[2]})
        ts.log_debug('For sequence zero:%0.2f postive:%0.2f negative:%0.2f' % (steps[0],steps[1],steps[2]))
        ts.log('Setting magnitudes phA:%s phB:%s phC:%s' % (mag['1'],mag['2'],mag['3']))
        ts.log('Setting angles phA:%s phB:%s phC:%s' % (angle['1'],angle['2'],angle['3']))

        if grid is not None:
            grid.voltage(mag)
            grid.phases_angles(params=angle)    

        ts.sleep(steps[3])
        #ts.sleep(1)
        daq.data_sample()
        data = daq.data_capture_read()

        #Test result accuracy requirements per IEEE1547-4.2 for P(V)
        pv_passfail = p_v_passfail(    phases=phases,
                                       v_pairs=v_pairs,
                                       a_v=a_v,
                                       p_mra=p_mra,
                                       daq=daq,
                                       data=data)
        
        #Test result accuracy requirements per IEEE1547-4.2 for Q(tr)
        #Still needs to be implemented
        
        daq.sc['event'] = 'T_settling_done_{}'.format(steps[3])
        daq.data_sample()
        
        result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                 (pv_passfail,
                                  ts.config_name(),
                                  power*100.,
                                  n_iter+1,
                                  daq.sc['V_TARGET'],
                                  daq.sc['V_MEAS'],
                                  daq.sc['P_TARGET'],
                                  daq.sc['P_MEAS'],
                                  daq.sc['P_TARGET_MIN'],
                                  daq.sc['P_TARGET_MAX'],
                                  dataset_filename))

    result=script.RESULT_COMPLETE
    return result

def normal_curve_test(vw_curve,power,n_iter,t_settling,daq,eut,grid,result_summary):

    phases = ts.param_value('eut.phases')
    v_nom = ts.param_value('eut.v_nom')
    a_v=round(1.5*0.01*ts.param_value('eut.v_nom'),2)
    p_mra=round(1.5*0.05*ts.param_value('eut.s_rated'),1)
    v_min = ts.param_value('eut.v_low')
    v_max= ts.param_value('eut.v_high')

    dataset_filename = 'VW_curve_%s_pwr_%0.2f_iter_%s.csv' % (vw_curve, power, n_iter + 1)                        


    if eut is not None:
        vw_curve_params = {'v': [v_start, v_stop], 'w': [100., 0], 'DeptRef': 'W_MAX_PCT'}
        vw_params = {'Ena': True, 'ActCrv': 1, 'curve': vw_curve_params}
        eut.volt_watt(params=vw_params)
        ts.log_debug('Initial EUT VW settings are %s' % eut.volt_watt())        

    v_pairs = curve_v_p(    curve_number=vw_curve,
                            power=power)
    v_steps_dic=voltage_steps(  v=v_pairs,
                                a_v=a_v)

    ts.log('Testing VW function at the following voltage up points %s' % v_steps_dic['up'])
    ts.log('Testing VW function at the following voltage down points %s' % v_steps_dic['down'])
                         
    daq.data_capture(True)
    
    for direction ,v_steps in v_steps_dic.iteritems():
        for v_step in v_steps:                                

            ts.log('        Recording power at voltage %0.2f V for 4*t_settling = %0.1f sec.' %
                   (v_step, 4 * t_settling))
            daq.sc['V_TARGET'] = v_step
            daq.sc['event'] = 'v_step_{}'.format(direction)
               
            p_targ=interpolation_v_p(value=v_step,
                                     v_pairs=v_pairs)
            
            grid.voltage(v_step)
            for i in range(4):
                daq.sc['event'] = 'v_step_{}'.format(direction)
                ts.sleep(1 * t_settling)
                daq.sc['event'] = 'TR_{}_done'.format(i+1)
                daq.data_sample()
                data = daq.data_capture_read()

            daq.sc['P_TARGET'] = p_targ

            #Test result accuracy requirements per IEEE1547-4.2 for Q(V)
            pv_passfail = p_v_passfail(phases=phases,
                                           v_pairs=v_pairs,
                                           a_v=a_v,
                                           p_mra=p_mra,
                                           daq=daq,
                                           data=data)
            
            #Test result accuracy requirements per IEEE1547-4.2 for Q(tr)
            #Still needs to be implemented

            ts.log('        Powers targ, min, max: %s, %s, %s' % (daq.sc['P_TARGET'], daq.sc['P_TARGET_MIN'], daq.sc['P_TARGET_MAX']))

            daq.sc['event'] = 'T_settling_done_{}'.format(direction)
            daq.data_sample()

            result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                 (pv_passfail,
                                  ts.config_name(),
                                  power*100.,
                                  n_iter+1,
                                  direction,
                                  daq.sc['V_TARGET'],
                                  daq.sc['V_MEAS'],
                                  daq.sc['P_TARGET'],
                                  daq.sc['P_MEAS'],
                                  daq.sc['P_TARGET_MIN'],
                                  daq.sc['P_TARGET_MAX'],
                                  dataset_filename))
    """
    # Parameter for the plotting
    result_params = {
    'plot.title': 'title_name',
    'plot.x.title': 'Time (sec)',
    'plot.x.points': 'TIME',
    'plot.y.points': 'V_TARGET,V_ACT',
    'plot.y.title': 'Voltage (V)',
    'plot.V_TARGET.point': 'True',
    'plot.y2.points': 'P_TARGET,P_ACT',                    
    'plot.P_TARGET.point': 'True',
    'plot.P_TARGET.min_error': 'P_TARGET_MIN',
    'plot.P_TARGET.max_error': 'P_TARGET_MAX',
    }
    """
    daq.data_capture(False)
    ds = daq.data_capture_dataset()
    ts.log('Saving file: %s' % dataset_filename)
    ds.to_csv(ts.result_file_path(dataset_filename))
    #result_params['plot.title'] = os.path.splitext(dataset_filename)[0]
    ts.result_file(dataset_filename)

    result = script.RESULT_COMPLETE

    return result

def voltage_steps(v,a_v):
    """
    :param curve_number: VV characteristic curve desired
    :param v_nom: VV nominal voltage output
    :param s_rated: VV apparent power output
    :return: curve tests vector
    """
    v_steps_dict=collections.OrderedDict()
    v_min = ts.param_value('eut.v_low')
    v_max= ts.param_value('eut.v_high')
    v_nom= ts.param_value('eut.v_nom')

                                        # 1547.1 :
    v_steps_up=[    v_nom,              #init
                    (v['V1']+a_v),         #  step h
                    (v['V2']+v['V1'])/2,      #  step i
                    v['V2']-a_v,           #  step j
                    v['V2']+a_v,           #  step k
                    v_max-a_v]          #  step l

    v_steps_down=[  v['V2']+a_v,           #step m
                    v['V2']-a_v,           #step n
                    (v['V1']+v['V2'])/2,      #step o
                    v['V1']+a_v,           #step p
                    v['V1']-a_v,           #step q
                    v_min,              #step s
                    v_nom]              

    for i in range(len(v_steps_up)):
        if v_steps_up[i] > v_max:
            v_steps_up[i]=v_max
        elif v_steps_up[i] < v_min:
            v_steps_up[i]=v_min
    for i in range(len(v_steps_down)):
        if v_steps_down[i] > v_max:
            v_steps_down[i]=v_max
        elif v_steps_down[i] < v_min:
            v_steps_down[i]=v_min
        
    v_steps_dict['up'] = np.around(v_steps_up,  decimals=2)
    v_steps_dict['down'] = np.around(v_steps_down,  decimals=2)
    ts.log('Testing VW function at the following voltage(up) points %s' % v_steps_dict['up'])
    ts.log('Testing VW function at the following voltage(down) points %s' % v_steps_dict['down'])
    
    return v_steps_dict

def curve_v_p(curve_number,power):
    """
    TODO: make v and p vector for desired characteristic curve

    :param curve_number: VV characteristic curve desired
    :param v_nom: EUT nominal voltage output(V)
    :param s_rated: EUT apparent power output (VA)
    :param units: for value in PU or full scale value
    :return: curve tests vector
    """
    p_rated = power*ts.param_value('eut.p_rated')
    p_min = ts.param_value('eut.p_min') / p_rated
    v_nom = ts.param_value('eut.v_nom')
    abs_enable = ts.param_value('eut.abs_enabled')

    if abs_enable == 'No':
        p_min=p_rated
    elif (p_min*p_rated) > (0.2*p_rated):
        p_min=0.2*p_rated
    else:
        p_min=p_min*p_rated

    v_pairs={}

    v_pairs[1] = {'V1': round(1.06*v_nom,2),
                  'V2': round(1.10*v_nom,2),
                  'P1': round(p_rated,2),
                  'P2': round(p_min,2)}

    v_pairs[2] = {'V1': round(1.05 * v_nom, 2),
                  'V2': round(1.10 * v_nom, 2),
                  'P1': round(p_rated, 2),
                  'P2': round(p_min, 2)}

    v_pairs[3] = {'V1': round(1.09 * v_nom, 2),
                  'V2': round(1.10 * v_nom, 2),
                  'P1': round(p_rated, 2),
                  'P2': round(p_min, 2)}


    ts.log_debug('curve points:  %s' % v_pairs[curve_number])

    return v_pairs[curve_number]

def interpolation_v_p(value, v_pairs):
    """
    Interpolation function to find the target reactive power based on a 2 point VW curve

    :param value: voltage point for the interpolation
    :param v: VW voltage points
    :param p: VW active power points
    :return: target reactive power
    """
    ts.log(value, v_pairs)
    if value <= v_pairs['V1']:
        p_value = v_pairs['P1']
    elif value < v_pairs['V2']:
        p_value = v_pairs['P1'] + ((v_pairs['P2'] - v_pairs['P1'])/(v_pairs['V2'] - v_pairs['V1']) * (value-v_pairs['V1']))
    else:
        p_value = v_pairs['P2']

    return round(float(p_value),2)


def p_v_passfail(phases, v_pairs, a_v, p_mra, daq=None, data=None):
    """
    Determine reactive power target and the min/max q values for pass/fail acceptance based on manufacturer's specified
    accuracies (MSAs)

    :param phases: number of phases of systems
    :param v_value: measured voltage value
    :param a_v: manufacturer's mininum requirement accuracy of voltage
    :param p_mra: manufacturer's minimum requirement accuracy of reactive power
    :param v: VW voltage points (volts)
    :param p: VW reactive power points (W)
    :return: passfail for p(v)
    """

    #try:
    daq.sc['V_MEAS'] = measurement_total(data=data, phases=phases, type_meas='V')
    daq.sc['P_MEAS'] = measurement_total(data=data, phases=phases, type_meas='P')

    #To calculate the min/max, you need the measured value
    if daq.sc['V_MEAS'] != 'No Data':
        daq.sc['P_TARGET_MIN']= interpolation_v_p(daq.sc['V_MEAS'] + a_v, v_pairs)-p_mra  # reactive power target from the lower voltage limit
        daq.sc['P_TARGET_MAX']= interpolation_v_p(daq.sc['V_MEAS'] - a_v, v_pairs)+p_mra  # reactive power target from the upper voltage limit
        if daq.sc['P_TARGET_MIN'] <= daq.sc['P_MEAS'] <= daq.sc['P_TARGET_MAX']:
            passfail = 'Pass'
        else:
            passfail = 'Fail'
    else:
        daq.sc['P_TARGET_MIN'] = 'No Data'
        daq.sc['P_TARGET_MAX'] = 'No Data'
        passfail = 'Fail'

    ts.log('        P actual, min, max: %s, %s, %s' % (daq.sc['P_MEAS'], daq.sc['P_TARGET_MIN'], daq.sc['P_TARGET_MAX']))
    ts.log('        Passfail: %s' % (passfail))

    return passfail
    '''
    except:
        daq.sc['V_MEAS'] = 'No Data'
        passfail = 'Fail'
        daq.sc['P_TARGET_MIN']='No Data'
        daq.sc['P_TARGET_MAX']='No Data'

        return passfail
    '''

def measurement_total(data, phases, type_meas):
    """
    Sum the EUT reactive power from all phases
    :param data: dataset
    :param phases: number of phases in the EUT
    :param choice: Either V,P or Q
    :return: either total EUT reactive power, total EUT active power or average V
    """
    if type_meas == 'V':
        meas = 'VRMS'
        log_meas = 'Voltages'
    elif type_meas == 'P':
        meas = 'P'
        log_meas = 'Active powers'
    else:
        meas = 'Q'
        log_meas = 'Reactive powers'

    if phases == 'Single phase':
        ts.log_debug('        %s are: %s' % (log_meas, data.get('AC_{}_1'.format(meas))))
        try:
            value = data.get('AC_{}_1')
        except:
            value = 'No Data'
            return value
        phase = 1

    elif phases == 'Split phase':
        ts.log_debug('        %s are: %s, %s' % (log_meas, data.get('AC_{}_1'.format(meas)),
                                                 data.get('AC_{}_2'.format(meas))))
        try:
            value = data.get('AC_{}_1'.format(meas)) + data.get('AC_{}_2'.format(meas))
        except:
            value = 'No Data'
            return value
        phase = 2
    elif phases == 'Three phase':
        ts.log_debug('        %s are: %s, %s, %s' % (log_meas,
                                                     data.get('AC_{}_1'.format(meas)),
                                                     data.get('AC_{}_2'.format(meas)),
                                                     data.get('AC_{}_3'.format(meas))))
        try:
            value = data.get('AC_{}_1'.format(meas)) + data.get('AC_{}_2'.format(meas)) + data.get('AC_{}_3'.format(meas))
        except:
            value = 'No Data'
            return value
        phase = 3
    else:
        ts.log_error('Inverter phase parameter not set correctly.')
        raise

    if type_meas == 'V':
        # average value of V
        value = value / phase

    elif type_meas == 'P':
        return abs(value)

    return value

def test_run():

    result = script.RESULT_FAIL
    daq = None
    data = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None
    

    try:
        """
        Configuration
        """
        # Initiliaze VW EUT specified parameters variables
        mode = ts.param_value('vw.mode')
        irr = ts.param_value('vw.irr')
        n_iterations = ts.param_value('vw.n_iter')
        """
        Equipment Configuration
        """
        v_nom = ts.param_value('eut.v_nom')
        eff = {
            1.00 : ts.param_value('eut.efficiency_100')/100,
            0.66 : ts.param_value('eut.efficiency_66')/100,
            0.20 : ts.param_value('eut.efficiency_20')/100
        }

        # initialize hardware-in-the-loop environment (if applicable)
        ts.log('Configuring HIL system...')
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # initialize grid simulator
        grid = gridsim.gridsim_init(ts)

        # initialize pv simulator
        pv = pvsim.pvsim_init(ts)
        p_rated = ts.param_value('eut.p_rated')        
        pv.power_set(p_rated)
        pv.power_on()  # power on at p_rated

        # DAS soft channels
        das_points = {'sc': ('P_TARGET', 'P_TARGET_MIN', 'P_TARGET_MAX', 'P_MEAS', 'V_TARGET','V_MEAS','event')}

        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])
        daq.sc['P_TARGET'] = 100
        daq.sc['P_TARGET_MIN'] = 100
        daq.sc['P_TARGET_MAX'] = 100
        daq.sc['V_TARGET'] = v_nom
        daq.sc['event'] = 'None'
        """
        EUT Configuration
        """ 
        # Configure the EUT communications
        if eut is not None:
            eut.config()
            ts.log_debug(eut.measurements())
            ts.log_debug('L/HVRT and trip parameters set to the widest range : v_min:{0} V, v_max:{1} V'.format(v_min,v_max))
            
            # TODO : Need to update FRT parameters with SunSpec Model reference
            eut.vrt_stay_connected_high(params={'Ena' : True,'ActCrv':0, 'Tms1':3000,'V1' : f_max,'Tms2':0.16,'V2' : v_max})
            eut.vrt_stay_connected_low(params={'Ena' : True,'ActCrv':0, 'Tms1':3000,'V1' : f_min,'Tms2':0.16,'V2' : v_min})
        else:
            ts.log_debug('Set L/HVRT and trip parameters to the widest range of adjustability possible.')
        """
        Test Configuration
        """
        # list of active tests
        vw_curves = []
        t_r = [0,0,0,0]
        if mode == 'Imbalanced grid':
            vw_curves.append(1)
        else:
            irr = ts.param_value('vw.irr')
            if ts.param_value('vw.test_1') == 'Enabled':
                vw_curves.append(1)
                t_r[0]=ts.param_value('vw.test_1_t_r')
            if ts.param_value('vw.test_2') == 'Enabled':
                vw_curves.append(2)
                t_r[1]=ts.param_value('vw.test_2_t_r')
            if ts.param_value('vw.test_3') == 'Enabled':
                vw_curves.append(3)
                t_r[2]=ts.param_value('vw.test_3_t_r')

        #List of power level for tests
        if irr == '20%':
            pwr_lvls = [0.20]
        elif irr == '66%':
            pwr_lvls = [0.66]
        elif irr == '100%':
            pwr_lvls = [1.00]
        else:
            pwr_lvls = [1.00, 0.66, 0.20]

        #ts.log_debug('power_lvl_dictionary:%s' % (pwr_lvls))
	    #ts.log_debug('%s' % (vw_curves))
        
        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write('Result,Test Name,Power Level,Iteration,direction,V_target,V_actual,Power_target,Power_actual,P_min,P_max,Dataset File\n')
        """
        Test start
        """
        for vw_curve in vw_curves:
            
            for power in pwr_lvls:
                pv_power_setting = (p_rated * power) / eff[power]
                ts.log('Set PV simulator power to {} with efficiency at {} %'.format(p_rated * power, eff[power] * 100.))
                pv.power_set(pv_power_setting)

                for n_iter in range(n_iterations):
                    if mode == 'Imbalanced grid':
                        result=imbalanced_grid_test(n_iter=n_iter,
                                                    power=power,
                                                    daq=daq,
                                                    eut=eut,
                                                    grid=grid,
                                                    result_summary=result_summary)
                    else: 
                        result=normal_curve_test(   vw_curve=vw_curve,
                                                    power=power,
                                                    n_iter=n_iter,
                                                    t_settling=t_r[vw_curve-1],
                                                    daq=daq,
                                                    eut=eut,
                                                    grid=grid,
                                                    result_summary=result_summary)
        
        
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
            if v_nom is not None:
                grid.voltage(v_nom)
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

        result = test_run()

        ts.result(result)
        if result == script.RESULT_FAIL:
            rc = 1

    except Exception, e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)

info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.0.0')

# EUT VW parameters
info.param_group('eut', label='VW EUT specified parameters',glob=True)
info.param('eut.phases', label='Phases', default='Single Phase', values=['Single phase', 'Split phase', 'Three phase'])
info.param('eut.s_rated', label='Output Apparent power Rating (W)', default=10000.)
info.param('eut.p_rated', label='Output Power Rating (W)', default=10000.)
info.param('eut.p_min', label='Minimum Power Rating(W)', default=1000.)
info.param('eut.abs_enable', label='Can DER absorb active power?', default='No',values=['No', 'Yes'])
info.param('eut.v_low', label='Min AC voltage range with function enabled (V)', default=108.)
info.param('eut.v_high', label='Max AC voltage range with function enabled (V)', default=132.)
info.param('eut.v_nom', label='Nominal AC voltage (V)', default=120.)
info.param('eut.efficiency_20', label='CEC Efficiency list for power level = 20% at nominal VDC', default=97.0)
info.param('eut.efficiency_66', label='CEC Efficiency list for power level = 66% at nominal VDC', default=97.0)
info.param('eut.efficiency_100', label='CEC Efficiency list for power level = 100% at nominal VDC', default=96.9)

# VW test parameters
info.param_group('vw', label='Test Parameters')
info.param('vw.mode', label='Volt-Watt mode', default='Normal', values=['Normal', 'Imbalanced grid'])

info.param('vw.test_1', label='Characteristic 1 curve', default='Enabled', values=['Disabled', 'Enabled'],\
           active='vw.mode', active_value=['Normal'])
info.param('vw.test_1_t_r', label='Settling time (t) for curve 1', default=10.0,\
           active='vw.test_1', active_value=['Enabled'])

info.param('vw.test_2', label='Characteristic 2 curve', default='Enabled', values=['Disabled', 'Enabled'],\
           active='vw.mode', active_value=['Normal'])
info.param('vw.test_2_t_r', label='Settling time min (t) for curve 2', default=90.0,\
           active='vw.test_2', active_value=['Enabled'])

info.param('vw.test_3', label='Characteristic 3 curve', default='Enabled', values=['Disabled', 'Enabled'],\
           active='vw.mode', active_value=['Normal'])
info.param('vw.test_3_t_r', label='Settling time max (t) for curve 3', default=0.5,\
           active='vw.test_3', active_value=['Enabled'])

info.param('vw.power_lvl', label='Power Levels', default='All', values=['100%', '66%', '20%', 'All'])
info.param('vw.n_iter', label='Number of iteration for each test', default=1)


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
