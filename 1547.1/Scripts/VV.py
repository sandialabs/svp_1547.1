
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

test_labels = {
    1: 'Characteristic Curve 1',
    2: 'Characteristic Curve 2',
    3: 'Characteristic Curve 3',
    4: 'Specified Curve',
    5: 'Vref test',
    6: 'Imbalanced grid',
    'Characteristic Curve 1': [1],
    'Characteristic Curve 2': [2],
    'Characteristic Curve 3': [3],
    'Specified Curve': [4],
    'Vref test':[5],
    'Imbalanced grid':[6]
}
"""

"""
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

def imbalanced_grid_test(a_v, MSA_Q,v_nom, v, q, grid, daq, result_summary,dataset_filename):
    seq012 =  ([0,   1.0,   0.10,   60],\
               [0,   1.0,   0.05,   300],\
               [0,   1.0,   0.03,   300],\
               [0,   1.0,   0,      30],\
               [0,   1.0,   -0.12,  60],\
               [0,   1.0,   -0.05,  300],\
               [0,   1.0,   -0.03,  300],\
               [0,   1.0,   0,      30])

    mag={}
    angle={}
    phases=ts.param_value('eut_vv.phases')
    mode = ts.param_value('vv.mode')
    daq.data_capture(True)
    daq.data_sample()
    data = daq.data_capture_read()

    for steps in seq012:
        daq.sc['event'] = 'zero_{}_pos_{}_neg_{}'.format(steps[0],steps[1],steps[2])
        mag,angle=sequence012_to_abc(params={'0':steps[0], '+':steps[1], '-':steps[2]})
        ts.log_debug('For sequence zero:%0.2f postive:%0.2f negative:%0.2f' % (steps[0],steps[1],steps[2]))
        ts.log('Setting magnitudes phA:%s phB:%s phC:%s' % (mag['1'],mag['2'],mag['3']))
        ts.log('Setting angles phA:%s phB:%s phC:%s' % (angle['1'],angle['2'],angle['3']))

        if grid is not None:
            grid.voltage(mag)
            grid.phases_angles(params=angle)    

        Q_V_passfail=q_msa_range(data=data, phases=phases,a_v=a_v, msa_q=MSA_Q, v=v, q=q,daq=daq)

        ts.sleep(steps[3])
        #ts.sleep(1)
        daq.sc['event'] = 'T_settling_done_{}'.format(steps[3])
        
        #Test result accuracy requirements per IEEE1547-4.2 for Q(tr)
        #Still needs to be implemented
        
        #Test result accuracy requirements per IEEE1547-4.2 for Q(V)
        #Q_V_passfail=q_msa_range(data=data, phases=phases,a_v=a_v, msa_q=MSA_Q, v=v, q=q,daq=daq)

        daq.data_sample()
        data = daq.data_capture_read()
        result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                     (Q_V_passfail, ts.config_name(), mode,
                     daq.sc['V_MEAS'],daq.sc['Q_MEAS'], daq.sc['Q_TARGET'], daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX'],
                      dataset_filename))
    return None

def voltage_steps(v,v_low,v_high,v_ref,a_v, mode):
    """
    TODO: make v steps vector for desired test (Normal or Vref test)

    :param curve_number: VV characteristic curve desired
    :param v_nom: VV nominal voltage output
    :param s_rated: VV apparent power output
    :return: curve tests vector
    """
    v_steps_dict=dict()
    
    #Establishing V step depending on mode Normal or Vref 
    if mode == 'Vref-test':
        v_steps_vref=[  v_ref,
                        (v[2]+v[3])/2,  
                        (v[0]+v[1])/2]
        v_steps_dict['Vref-test'] = np.around(v_steps_vref,  decimals=2)
        ts.log('Testing VV function at the following voltage(vref test) points %s' % v_steps_dict['Vref-test'])

    else:
                                        #Per standard 1547.1 december 2018 version
        v_steps_cap=[v_high,            #step f1
                    (v[2]-a_v),         #step f2
                    (v[2]+a_v),         #step g
                    (v[2]+v[3])/2,      #step h
                    v[3]-a_v,           #step i only if V4<V_h
                    v[3]+a_v,           #step j only if V4<V_h
                    v_high-a_v,         #step k only if V4<V_h
                    v[3]+a_v,           #step l only if V4<V_h
                    (v[2]+v[3])/2,      #step m only if V4<V_h
                    v[2]+a_v,           #step n
                    v[2]-a_v,           #step o
                    v_ref]              #step p
        
        if v[3] >= v_high: #if V4 > V_h, remove step i,j,k,l,m
            del v_steps_cap[8]
            del v_steps_cap[7]
            del v_steps_cap[6]
            del v_steps_cap[5]
            del v_steps_cap[4]
            
        v_steps_dict['capacitive'] = np.around(v_steps_cap,  decimals=2)

        """
        This section will need to be reviewed. As it is, it seems there are a few typos with this draft
        """
        v_steps_ind=[v_low,             #step q1
                    (v[1]+a_v),         #step q2
                    (v[1]-a_v),         #step r
                    (v[0]+v[1])/2,      #step s
                    v[0]+a_v,           #step t only if V1>V_low
                    v[0]-a_v,           #step u only if V1>V_low
                    v_low+a_v,          #step v only if V1>V_low
                    v[0]+a_v,           #step w only if V1>V_low
                    (v[0]+v[1])/2,      #step x only if V1>V_low
                    v[1]-a_v,           #step y 
                    v[1]+a_v,           #step z
                    v_ref]              #step aa

        if v[0] <= v_low: #if V1 < V_low, remove step t,u,v,w,x
            del v_steps_ind[8]
            del v_steps_ind[7]
            del v_steps_ind[6]
            del v_steps_ind[5]
            del v_steps_ind[4]
        v_steps_dict['inductive'] = np.around(v_steps_ind,  decimals=2)

        ts.log('Testing VV function at the following voltage(capacitive) points %s' % v_steps_dict['capacitive'])
        ts.log('Testing VV function at the following voltage(inductive) points %s' % v_steps_dict['inductive'])
        
    return v_steps_dict

def curve_v_q(curve_number,param_value,spec_curve_q=None,spec_curve_v=None):
    """
    TODO: make v and q vector for desired characteristic curve

    :param curve_number: VV characteristic curve desired
    :param v_nom: VV nominal voltage output
    :param s_rated: VV apparent power output
    :param spec_curve_q: for desired q points 
    :param spec_curve_v: for desired v points
    :param units: for value in PU or full scale value
    :return: curve tests vector
    """
    q = [0] * 4
    v = [0] * 4

    #For specified curve
    if curve_number == 3:
        for i in range(0,4):
            q[i] = spec_curve_q[i]
            v[i] = spec_curve_v[i]

    #For characteristic curves 1,2,3
    else:
                    #Curve
                    #1        2        3
        q_curve = ( [1.0,   1.0,    1.0],\
                    [0,     0.5,    -0.5],\
                    [0,     0.5,    -0.5],\
                    [-1.0,  -1.0,   -1.0])
                    #Curve
                    #1        2        3
        v_curve = ([0.92,   0.88,   0.9],\
                   [0.98,   1.04,   0.93],\
                   [1.02,   1.07,   0.96],\
                   [1.08,   1.1,    1.1])
        

        for i in range(0,4):
            q[i] = q_curve[i][curve_number]
            v[i] = v_curve[i][curve_number]
        ts.log_debug('v:  %s' % v)
        ts.log_debug('q:  %s' % q)
        
    q[:] = [ round(x * param_value[3],2) for x in q]
    v[:] = [ round(x * param_value[2],2) for x in v]

    ts.log('v points= %s' % (v))
    ts.log('q points= %s' % (q))
    return v,q
    
def v_q(value, v, q):
    """
    Interpolation function to find the target reactive power based on a 4 point VV curve

    TODO: make generic for n-point curves

    :param value: voltage point for the interpolation
    :param v: VV voltage points
    :param q: VV reactive power points
    :return: target reactive power
    """
    if value <= v[0]:
        q_value = q[0]
    elif value < v[1]:
        q_value = q[0] + ((q[1] - q[0])/(v[1] - v[0]) * (value - v[0]))
    elif value == v[1]:
        q_value = q[1]
    elif value <= v[2]:
        q_value = q[2]
    elif value < v[3]:
        q_value = q[2] + ((q[3] - q[2])/(v[3] - v[2]) * (value - v[2]))
    else:
        q_value = q[3]
    return round(q_value, 1)


def q_msa_range(data, phases, a_v, msa_q, v, q,daq=None):
    """
    Determine reactive power target and the min/max q values for pass/fail acceptance based on manufacturer's specified
    accuracies (MSAs)

    :param v_value: measured voltage value
    :param v_msa: manufacturer's specified accuracy of voltage
    :param q_msa: manufacturer's specified accuracy of reactive power
    :param v: VV voltage points
    :param q: VV reactive power points
    :return: points for q_target, q_target_min, q_target_max
    """
    
    #q_lower = v_q(v_measured + a_v, v, q)-1.5*q_msa  # reactive power target from the lower voltage limit
    #q_upper = v_q(v_measured - a_v, v, q)+1.5*q_msa  # reactive power target from the upper voltage limit

    try:
        daq.sc['V_MEAS'] = measurement_total(data=data, phases=phases, type_meas='V')
        daq.sc['Q_MEAS'] = measurement_total(data=data, phases=phases, type_meas='Q')

        #To calculate the min/max, you need the measured value

        daq.sc['Q_TARGET_MIN']= v_q(daq.sc['V_MEAS'] + a_v, v, q)-1.5*q_msa  # reactive power target from the lower voltage limit
        daq.sc['Q_TARGET_MAX']= v_q(daq.sc['V_MEAS'] - a_v, v, q)+1.5*q_msa  # reactive power target from the upper voltage limit

        ts.log('        Q actual, min, max: %s, %s, %s' % (q_final, daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX']))
        
        if daq.sc['Q_TARGET_MIN'] <= AC_Q <= daq.sc['Q_TARGET_MAX']:
            passfail = 'Pass'
        else:
            passfail = 'Fail'

        ts.log('        Passfail: %s' % (passfail))

        return passfail
    
    except:
        daq.sc['V_MEAS'] = 'No Data'
        daq.sc['V_MEAS'] = 'No Data'
        passfail = 'Fail'
        daq.sc['Q_TARGET_MIN']='No Data'
        daq.sc['Q_TARGET_MAX']='No Data'

        return passfail

def measurement_total(data, phases, type_meas):
    """
    Sum the EUT reactive power from all phases
    :param data: dataset
    :param phases: number of phases in the EUT
    :param choice: Either V,P or Q 
    :return: either total EUT reactive power, total EUT active power or average V
    """
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
        raise

    if type_meas == 'V':
        #average value of V
        value=value/3
        
    elif type_meas == 'P':
        return abs(value)

    return value


def test_run():

    result = script.RESULT_PASS
    daq = None
    pv = None
    grid = None
    chil = None
    result_summary = None
    p_max = None
    eut = None
    v_steps_dic = collections.OrderedDict()

    """
    Plotting still in work
    """
    result_params = {
        'plot.title': 'title_name',
        'plot.x.title': 'Time (secs)',
        'plot.x.points': 'TIME',
        'plot.y.points': 'AC_Q_1, Q_TARGET',
        'plot.Q_ACT.point': 'True',
        'plot.Q_TARGET.point': 'True',
        'plot.Q_TARGET.min_error': 'Q_MIN_ERROR',
        'plot.Q_TARGET.max_error': 'Q_MAX_ERROR',
        'plot.Q_MIN.point': 'True',
        'plot.Q_MAX.point': 'True',
        'plot.V_TARGET.point': 'True',
        'plot.y.title': 'Reactive Power (var)',
        'plot.y2.points': 'AC_VRMS_1, V_TARGET',
        'plot.y2.title': 'Voltage (V)'
    }

    try:
	"""
	a) Connect the EUT according to the instructions and specifications provided by the manufacturer.
	"""
        # Initiliaze VV EUT specified parameters variables
        tests_param = ts.param_value('eut_vv.tests')

        s_rated = ts.param_value('eut_vv.s_rated')
        p_rated = ts.param_value('eut_vv.p_rated')
        var_rated = ts.param_value('eut_vv.var_rated')
		
        v_nom = ts.param_value('eut_vv.v_nom')
        v_low = ts.param_value('eut_vv.v_low')
        v_high= ts.param_value('eut_vv.v_high')

	MSA_V= ts.param_value('eut_vv.v_msa')
	a_v=round(1.5*MSA_V,2)
        MSA_Q= ts.param_value('eut_vv.q_msa')
		
	q_max_over = ts.param_value('eut_vv.q_max_over')
        q_max_under = ts.param_value('eut_vv.q_max_under')

        """	
	t_r = [ ts.param_value('eut_vv.vv_t_r'),
                ts.param_value('eut_vv.vv_t_r_min'),
                ts.param_value('eut_vv.vv_t_r_max') ]
	"""
        mode = ts.param_value('vv.mode')
        phases = ts.param_value('eut_vv.phases')
        

	# default power range
        p_min = p_rated * .2
        p_max = p_rated

	# initialize hardware-in-the-loop environment (if applicable)
        ts.log('Configuring HIL system...')
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()
	
	# initialize grid simulator
        grid = gridsim.gridsim_init(ts)

        if grid is not None:
            grid.voltage(v_nom)
	"""
	b) Set all voltage trip parameters to the widest range of adjustability. 
	Disable all reactive/active power control functions.
	"""
	# Configure the EUT communications
        
        eut = der.der_init(ts)
        if eut is not None:
            eut.config()
            #ts.log_debug(eut.measurements())
            ts.log_debug('If not done already, set L/HVRT and trip parameters to the widest range of adjustability.')
    
        else:
            ts.log_debug('Set L/HFRT and trip parameters to the widest range of adjustability possible.')

	"""
	c) Set all EPS source parameters to the nominal operating voltage and frequency. 
	"""
	"""
	d) Adjust the EUT active power to Prated. Where applicable, set the input voltage to Vin_nom.
	"""
	# initialize pv simulator
        if pv is not None:
            pv = pvsim.pvsim_init(ts)
            pv.power_set(p_rated)
            pv.power_on()  # power on at p_rated

	# DAS soft channels
        das_points = {'sc': ('V_MEAS', 'V_TARGET','Q_MEAS', 'Q_TARGET', 'Q_TARGET_MIN', 'Q_TARGET_MAX', 'event')}

        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])
        if daq :
            daq.sc['V_MEAS'] = 100
            daq.sc['Q_MEAS'] = 100
            daq.sc['Q_TARGET'] = 100
            daq.sc['Q_TARGET_MIN'] = 100
            daq.sc['Q_TARGET_MAX'] = 100
            daq.sc['event'] = 'None'

	"""
	e) Set EUT volt-var parameters to the values specified by Characteristic 1. 
	All other function should 1 be turned off. Turn off the autonomously adjusting reference voltage.
	"""
		
	"""
	Test Configuration
	"""
	# list of active tests
        vv_curves = []
        t_r = [0,0,0,0]
        if mode == 'Vref-test':
            vv_curves.append(1)
            t_r[0]=ts.param_value('vv.vref_t_r_1')
            irr = '100%'
            vref = '100%'
        elif mode == 'Imbalanced grid':
            irr = '100%'
            vref = '100%'
            vv_curves.append(1)
        else:
            irr = ts.param_value('vv.irr')
            vref = ts.param_value('vv.vref')
            if ts.param_value('vv.test_1') == 'Enabled':
                vv_curves.append(1)
                t_r[0]=ts.param_value('vv.test_1_t_r')
            if ts.param_value('vv.test_2') == 'Enabled':
                vv_curves.append(2)
                t_r[1]=ts.param_value('vv.test_2_t_r')
            if ts.param_value('vv.test_3') == 'Enabled':
                vv_curves.append(3)
                t_r[2]=ts.param_value('vv.test_3_t_r')
            if ts.param_value('vv.spec_curve') == 'Enabled':
                vv_curves.append(4)
                t_r[3]=ts.param_value('vv.test_4_t_r')
                spec_curve_unit=ts.param_value('vv.spec_curve_unit')
                spec_curve_v_str = ts.param_value('vv.spec_curve_v').split(',')
                if len(spec_curve_v_str) != 4:
                    ts.fail('Invalid specified curve V point count (must be 4): %s' % len(spec_curve_v))
                spec_curve_v = [float(i) for i in spec_curve_v_str]
                spec_curve_q_str = ts.param_value('vv.spec_curve_q').split(',')
                if len(spec_curve_q_str) != 4:
                    ts.fail('Invalid specified curve Q point count (must be 4): %s' % len(spec_curve_q))
                spec_curve_q = [float(i) for i in spec_curve_q_str]

        #List of power level for tests
        if irr == '20%':
            pwr_lvls = [0.20]
        elif irr == '66%':
            pwr_lvls = [0.66]
        elif irr == '100%':
            pwr_lvls = [1.]
        else:
            pwr_lvls = [1., 0.66, 0.20]


        if vref == '95%':
            v_ref_value = [0.95]
        elif vref == '105%':
            v_ref_value = [1.05]
        elif vref == '100%':
            v_ref_value = [1.]
        else:
            v_ref_value=[1,0.95,1.05]
    
        v_ref_value[:]=[v_nom * i for i in v_ref_value]
        ts.log_debug('v_reference_dictionary:%s' % (v_ref_value))

	param_value=[v_low,v_high,v_nom,var_rated]
	
	ts.log_debug('power_lvl_dictionary:%s' % (pwr_lvls))
	ts.log_debug('%s' % (vv_curves))

	# open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write('Result, Curve Characteristic, Power Level, Vref, Test, '
                             'Vstep, V_measured, Q_measured, Q_target, Q_min, Q_max, Dataset File\n')

	"""
        Test start
        """
	if eut is not None:	
            ts.log_debug('Initial EUT VV settings are %s' % eut.volt_var())

        ts.log('Starting test - %s' % (mode))
        for vv_curve in vv_curves:
            ts.log('With - %s' % (test_labels[vv_curve]))

            if vv_curve is not 4 :
                v,q=curve_v_q(  vv_curve-1,
                                param_value,
                                spec_curve_q=None,
                                spec_curve_v=None)
            else:
                # Specified curve
                v,q=curve_v_q(  vv_curve-1,
                                param_value,
                                spec_curve_q=spec_curve_q,
                                spec_curve_v=spec_curve_v)

            for pwr_lvl in pwr_lvls:
                ts.log('With power at - %s%%' % (pwr_lvl*100))
                if pv is not None:
                    pv.power_set(p_rated*pwr_lvl)

                for v_ref in v_ref_value:
                    if mode == 'Vref-test':
                        dataset_filename = 'VV_%s_tr_%d.csv' % (mode,t_r[vv_curve-1])
                    if mode == 'Imbalanced grid':
                        dataset_filename = 'VV_IG_Vnom_%d.csv' % (v_nom)
                    else:
                        dataset_filename = 'VV_%s_pwr_%d_Vref_%d.csv' % (vv_curve,int(pwr_lvl*100),(100*round(v_ref/v_nom,2)))

                    # create voltage settings along all segments of the curve
                    if not(mode == 'Imbalanced grid'):
                        v_steps_dic=voltage_steps(  v=v,
                                                    v_low=v_low,
                                                    v_high=v_high,
                                                    v_ref=v_ref,
                                                    a_v=a_v,
                                                    mode=mode)
                    
                        daq.data_capture(True)
                       
                        for test,v_steps in v_steps_dic.iteritems():
                            ts.log('With v_steps_dict at - %s' % (v_steps))
                            daq.data_sample()
                            data = daq.data_capture_read()
                            for v_step in v_steps:
                                ts.log('        Recording Q(vars) at voltage %0.2f V for 4*t_settling = %0.1f sec. %s' %
                                   (v_step, 4*t_r[vv_curve-1], test))

                                q_targ = v_q(value=v_step, v=v, q=q)    # target reactive power for the voltage measurement
                                ts.log('        Q target: %s' % (q_targ))
                              
                                daq.sc['V_TARGET'] = v_step
                                daq.sc['Q_TARGET'] = q_targ
                                daq.sc['event'] = 'v_Step_{}'.format(test)
 
                                if grid is not None:
                                    grid.voltage(v_step)

                                ts.sleep(4 * t_r[vv_curve-1])
                                #ts.sleep(1)
                                daq.sc['event'] = 'T_settling_done_{}'.format(test)
                                
                                #Test result accuracy requirements per IEEE1547-4.2 for Q(t)
                                #Still needs to be implemented

                                #Test result accuracy requirements per IEEE1547-4.2 for Q(V)

                                Q_V_passfail=q_msa_range(data=data, phases=phases,a_v=a_v, msa_q=MSA_Q, v=v, q=q,daq=daq)
                                daq.data_sample()
                                data = daq.data_capture_read()
                                result_summary.write('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s \n' %
                                             (Q_V_passfail, ts.config_name(), pwr_lvl*100., v_ref, '%s-%s' % (mode,test),
                                              v_step, daq.sc['V_MEAS'],daq.sc['Q_MEAS'], daq.sc['Q_TARGET'], daq.sc['Q_TARGET_MIN'], daq.sc['Q_TARGET_MAX'],
                                              dataset_filename))
                                
                    else:
                        Q_V_passfail=imbalanced_grid_test(a_v=a_v, MSA_Q=MSA_Q, v_nom=v_nom,
                                                          v=v, q=q,grid=grid,
                                                          daq=daq,
                                                          result_summary=result_summary,
                                                          dataset_filename=dataset_filename)
                        
        daq.data_capture(False)
        ds = daq.data_capture_dataset()
        data = daq.data_capture_read()
        ts.log('Saving file: %s' % dataset_filename)
        ds.to_csv(ts.result_file_path(dataset_filename))
        result_params['plot.title'] = os.path.splitext(dataset_filename)[0]
        ts.result_file(dataset_filename, params=result_params)
			
        result = script.RESULT_COMPLETE

    except script.ScriptFail, e:
        reason = str(e)
        if reason:
            ts.log_error(reason)
            daq.data_capture(False)
            ds = daq.data_capture_dataset()
            ds.to_csv(ts.result_file_path(dataset_filename))
            ts.result_file(dataset_filename)

    finally:

        if daq is not None:
            daq.close()
        if pv is not None:
            if p_max is not None:
                pv.power_set(p_max)
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

        #ts.svp_version(required='1.5.3')
        ts.svp_version(required='1.5.8')
        
        result = test_run()
        ts.log_debug('after test_run')
        ts.result(result)
        if result == script.RESULT_FAIL:
            rc = 1

    except Exception, e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)

info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.0.0')

info.param_group('vv', label='Test Parameters')
info.param('vv.mode', label='Volt-Var mode', default='Normal', values=['Normal', 'Vref-test', 'Imbalanced grid'])
info.param('vv.vref_t_r_1', label='T ref value (t)', default=300,\
           active='vv.mode', active_value=['Vref-test'])
"""
info.param('vv.vref_t_r_2', label='T ref value (t) for iteration 2', default=5000,\
           active='vv.mode', active_value=['Vref-test'])
"""
info.param('vv.test_1', label='Characteristic 1 curve', default='Enabled', values=['Disabled', 'Enabled'],\
           active='vv.mode', active_value=['Normal'])
info.param('vv.test_1_t_r', label='Settling time (t) for curve 1', default=5.0,\
           active='vv.test_1', active_value=['Enabled'])


info.param('vv.test_2', label='Characteristic 2 curve', default='Enabled', values=['Disabled', 'Enabled'],\
           active='vv.mode', active_value=['Normal'])
info.param('vv.test_2_t_r', label='Settling time min (t) for curve 2', default=1.0,\
           active='vv.test_2', active_value=['Enabled'])

info.param('vv.test_3', label='Characteristic 3 curve', default='Enabled', values=['Disabled', 'Enabled'],\
           active='vv.mode', active_value=['Normal'])
info.param('vv.test_3_t_r', label='Settling time max (t) for curve 3', default=90.0,\
           active='vv.test_3', active_value=['Enabled'])

info.param('vv.spec_curve', label='Specified curve', default='Disabled', values=['Disabled', 'Enabled'],\
           active='vv.mode', active_value=['Normal'])
info.param('vv.spec_curve_v', label='Specified curve V points in PU(v1,...,v4)', default='',\
           active='vv.spec_curve', active_value=['Enabled'])
info.param('vv.spec_curve_q', label='Specified curve Q points in PU(q1,...,q4)', default='',\
           active='vv.spec_curve', active_value=['Enabled'])
#info.param('vv.spec_curve_unit', label='Units in', default='pu',values=['pu', 'Volt-Vars'],\
#           active='vv.spec_curve', active_value=['Enabled'])
info.param('vv.test_4_t_r', label='Settling time (t) for specified curve', default=5.0,\
           active='vv.spec_curve', active_value=['Enabled'])

info.param('vv.irr', label='Power Levels iteration', default='All',values=['100%', '66%', '20%', 'All'],
           active='vv.mode', active_value=['Normal'])
info.param('vv.vref', label='Voltage reference iteration', default='All',values=['100%', '95%', '105%', 'All'],
           active='vv.mode', active_value=['Normal'])

info.param_group('eut_vv', label='EUT VV Parameters', glob=True)
info.param('eut_vv.s_rated', label='Apparent power rating (VA)', default=0.0)
info.param('eut_vv.p_rated', label='Output power rating (W)', default=0.0)
info.param('eut_vv.var_rated', label='Output var rating (vars)', default=0.0)
info.param('eut_vv.v_nom', label='Nominal AC voltage (V)', default=120.0, desc='Nominal voltage for the AC simulator.')
info.param('eut_vv.v_low', label='Minimum AC voltage (V)', default=0.0)
info.param('eut_vv.v_high', label='Maximum AC voltage (V)', default=0.0)
info.param('eut_vv.v_msa', label='AC voltage manufacturers stated accuracy (V)', default=0.0)
info.param('eut_vv.q_msa', label='Reactive power manufacturers stated accuracy (Var)', default=0.0)

info.param('eut_vv.q_max_over', label='Maximum reactive power production (over-excited) (VAr)', default=0.0)
info.param('eut_vv.q_max_under', label='Maximum reactive power absorbtion (under-excited) (VAr)(-)', default=0.0)
#info.param('eut_vv.vv_t_r', label='Settling time (t) for curve 1', default=5.0)
#info.param('eut_vv.vv_t_r_min', label='Settling time min (t) for curve 2', default=1.0)
#info.param('eut_vv.vv_t_r_max', label='Settling time max (t) for curve 3', default=90.0)
info.param('eut_vv.phases', label='Phases', default='Single phase', values=['Single phase', 'Split phase', 'Three phase'])


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



