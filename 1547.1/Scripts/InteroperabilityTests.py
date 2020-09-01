'''
Copyright (c) 2016, Sandia National Labs and SunSpec Alliance
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

Written by Sandia National Laboratories and SunSpec Alliance
Questions can be directed to Jay Johnson (jjohns2@sandia.gov)
'''

#!C:\Python27\python.exe

import sys
import os
import traceback
from svpelab import der1547
from svpelab import das
from svpelab import pvsim
from svpelab import gridsim
from svpelab import hil
from svpelab import p1547
import script
import math

# todo
PARAM_MAP = {'np_p_max': 'Active power rating at unity power factor (nameplate active power rating',
             'np_p_max_over_pf': 'Active power rating at specified over-excited power factor',
             'np_over_pf': 'Specified over-excited power factor',
             'np_under_pf': 'Specified under-excited power factor',
             'np_va_max': 'Apparent power maximum rating',
             'np_normal_op_cat': 'Normal operating performance category', 
             'np_abnormal_op_cat': 'Abnormal operating performance category', 
             'np_q_max_inj': 'Reactive power injected maximum rating',
             'np_q_max_abs': 'Reactive power absorbed maximum rating',
             'np_apparent_power_charge_max': 'Apparent power charge maximum rating',
             'np_ac_v_nom': 'AC voltage nominal rating',
             'np_ac_v_max_er_max': 'AC voltage maximum rating',
             'np_ac_v_min_er_min': 'AC voltage minimum rating',
             'np_supported_modes': 'Supported control mode functions',
             'UV': 'Supports Low Voltage Ride-Through Mode',
             'OV': 'Supports High Voltage Ride-Through Mode',
             'UF': 'Supports Low Freq Ride-Through Mode',
             'OF': 'Supports High Freq Ride-Through Mode',
             'P_LIM': 'Supports Active Power Limit Mode',
             'PV': 'Supports Volt-Watt Mode',
             'PF': 'Supports Frequency-Watt Curve Mode',
             'CONST_Q': 'Supports Constant VArs Mode',
             'CONST_PF': 'Supports Fixed Power Factor Mode',
             'QV': 'Supports Volt-VAr Control Mode',
             'QP': 'Supports Watt-VAr Mode',
             'np_reactive_susceptance': 'Reactive susceptance that remains connected to the Area EPS in the cease to ' \
                                        'energize and trip state',
             'np_manufacturer': 'Manufacturer',
             'np_model': 'Model',
             'np_serial_num': 'Serial Number',
             'np_fw_ver': 'Version',
             'mn_w': 'Active Power (kW)',
             'mn_var': 'Reactive Power (kVAr)',
             'mn_v': 'Voltage (list) (V)',
             'mn_hz': 'Frequency (Hz)',
             'mn_st': 'Operational State (dict of bools)',
             'mn_conn': 'Connection State (bool)',
             'mn_alrm': 'Alarm Status (str)',
             'mn_soc_pct': 'Operational State of Charge (%)',
             }


def print_params(param_dict, indent=1):
    """
    Pretty print of parameters from dictionary of parameters returned from der1547

    :param param_dict: dict from a getter function, e.g., der1547.get_nameplate()
    :param indent: number of spaces in the print
    :return: None
    """
    # ts.log('DER Parameter Dictionary: %s' % param_dict)
    for key, value in param_dict.items():
        if not isinstance(value, dict):
            if key in PARAM_MAP:
                ts.log('\t' * indent + PARAM_MAP[key] + ' [' + key + '] : ' + str(value))
            else:
                ts.log('\t' * indent + str(key) + ': ' + str(value))
        else:
            if key in PARAM_MAP:
                ts.log('\t' * indent + PARAM_MAP[key] + ' [' + key + '] : ')
            else:
                ts.log('\t' * indent + str(key) + ': ')
            print_params(value, indent+1)


def test_run():

    result = script.RESULT_FAIL
    daq = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None
    dataset_filename = None
    v_nom = None

    try:

        settings_test = ts.param_value('iop_params.settings_test') == 'Yes'
        monitoring_test = ts.param_value('iop_params.monitoring_test') == 'Yes'

        v_nom = float(ts.param_value('eut.v_nom'))
        # va_max = float(ts.param_value('eut.s_rated'))
        # va_crg_max = va_max
        # f_nom = float(ts.param_value('eut.f_nom'))
        phases = ts.param_value('eut.phases')
        p_rated = float(ts.param_value('eut.p_rated'))
        w_max = p_rated
        va_max = p_rated
        p_min = p_rated
        w_crg_max = p_rated
        var_rated = float(ts.param_value('eut.var_rated'))
        var_max = var_rated

        # initialize DER configuration
        eut = der1547.der1547_init(ts)
        eut.config()

        das_points = {'sc': ('event')}
        daq = das.das_init(ts, sc_points=das_points['sc'])

        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts)
        if pv is not None:
            pv.power_set(p_rated)
            pv.power_on()  # Turn on DC so the EUT can be initialized

        # grid simulator is initialized with test parameters and enabled
        grid = gridsim.gridsim_init(ts)  # Turn on AC so the EUT can be initialized
        if grid is not None:
            grid.voltage(v_nom)

        iop = p1547.ActiveFunction(ts=ts, functions=['IOP'], script_name='Interoperability',
                                   criteria_mode=[False, False, False])
        ts.log_debug("1547.1 Library configured for %s" % iop.get_script_name())
        iop.set_params()

        '''
        6.4 Nameplate data test
        a) Read from the DER each nameplate data item listed in Table 28 in IEEE Std 1547-2018.
        b) Compare each value received to the expected values from the manufacturer-provided expected values.
        '''

        ts.log('---')
        nameplate = eut.get_nameplate()
        if nameplate is not None:
            ts.log('DER Nameplate Information:')
            print_params(nameplate)
            ts.log('---')
        else:
            ts.log_warning('DER Nameplate Information not supported')

        if settings_test:  # Not supported by DNP3 App Note
            '''
            6.5 Basic settings information test

            a) Read from the DER each parameter identified in Table 42.
            b) For each, verify that the value reported matches the behavior of the DER measured though independent test
               equipment separate from the DER interface.
            c) Adjust values as identified in Table 42.
            d) Repeat steps a) and b) for the new values.
            e) Adjust parameters back to the initial values and verify that the value reported matches the initial
               values.

            Table 42 - Basic settings test levels
            ____________________________________________________________________________________________________________
            Parameter                           Adjustment required            Additional test instructions
            ____________________________________________________________________________________________________________
            Active Power Maximum                Set to 80% of Initial Value
            Apparent Power Maximum              Set to 80% of Initial Value
            Reactive Power Injected Maximum     Set to 80% of Initial Value
            Reactive Power Absorbed Maximum     Set to 80% of Initial Value
            Active Power Charge Maximum         Set to 80% of Initial Value     This test applies only to DER that
                                                                                include energy storage.
            Apparent Power Charge Maximum       Set to 80% of Initial Value     This test applies only to DER that
                                                                                include energy storage.
            AC Current Maximum                  Set to 80% of Initial Value
            Control Mode Functions              Not applicable
            Stated Energy Storage Capacity      Set to 80% of Initial Value     This test applies only to DER that
                                                                                include energy storage.
            Mode Enable Interval                Set to 5 s, set to 300 s
            '''
            ts.log('---')
            settings = eut.get_settings()
            if settings is not None:
                ts.log('DER Settings Information:')
                print_params(settings)
                ts.log('---')
                basic_settings = []
                if settings.get('np_p_max') is not None:
                    basic_settings.append(('np_p_max', 0.8 * settings['np_p_max'], 'P', settings['np_p_max']))
                else:
                    ts.log_warning('DER Settings does not include np_p_max')
                if settings.get('np_va_max') is not None:
                    basic_settings.append(('np_va_max', 0.8 * settings['np_va_max'], 'VA', settings['np_va_max']))
                else:
                    ts.log_warning('DER Settings does not include np_va_max')
                if settings.get('np_q_max_inj') is not None:
                    basic_settings.append(('np_q_max_inj', 0.8 * settings['np_q_max_inj'], 'Q',
                                           settings['np_q_max_inj']))
                else:
                    ts.log_warning('DER Settings does not include np_q_max_inj')
                if settings.get('np_q_max_abs') is not None:
                    basic_settings.append(('np_q_max_abs', 0.8 * settings['np_q_max_abs'], 'Q',
                                           settings['np_q_max_abs']))
                else:
                    ts.log_warning('DER Settings does not include np_q_max_abs')
                if settings.get('np_ac_v_max_er_max') is not None:
                    basic_settings.append(('np_ac_v_max_er_max', 0.8 * settings['np_ac_v_max_er_max'], 'V',
                                           settings['np_ac_v_max_er_max']))  # assume this is a typo for AC Current
                else:
                    ts.log_warning('DER Settings does not include np_ac_v_max_er_max')
                if settings.get('np_p_max_charge') is not None:
                    basic_settings.append(('np_p_max_charge', 0.8 * settings['np_p_max_charge'], 'P',
                                           settings['np_p_max_charge']))
                else:
                    ts.log_warning('DER Settings does not include np_p_max_charge')
                basic_settings.append(('set_t_mod_ena', 5.0, 'P', 300.0))

                for s in range(len(basic_settings)):
                    param = basic_settings[s][0]
                    val = basic_settings[s][1]
                    meas = basic_settings[s][2]
                    final_val = basic_settings[s][3]
                    ts.log('  Currently %s = %s' % (param, eut.get_settings()[param]))
                    ts.log('  Setting %s to %0.1f.' % (param, val))
                    eut.set_settings(params={param: val})
                    ts.sleep(2)
                    verify_val = iop.util.get_measurement_total(data=daq.data_capture_read(), type_meas=meas, log=True)
                    ts.log('  Verification value is: %f.' % verify_val)
                    ts.log('  Returning %s to %f.' % (param, final_val))
                    eut.set_settings(params={param: val})
                    ts.sleep(2)
            else:
                ts.log_warning('DER settings not supported')
        else:
            ts.log('Skipping DER settings test')

        if monitoring_test:
            '''
            6.6 Monitoring information test

            a) Set the operating conditions of the DER to the values specified in the "Operating Point A" column in
               Table 43.
            b) Wait not less than 30 s, then read from the DER each monitoring information, and verify that the
               reported values match the operating conditions as identified.
            c) Change the operating conditions of the DER as specified in the "Operating Point B" column 16 in Table 43.
            d) Repeat step b).
            
            Table 43 — Monitoring information test levels
            ____________________________________________________________________________________________________________
            Monitoring          Operating               Operating               Criteria
            information         Point A                 Point B
            parameter                                
            ____________________________________________________________________________________________________________
            Active Power        20% to 30% of           90% to 100% of          Reported values match test operating
                                DER “active power       DER “active power       conditions within the accuracy 
                                rating at unity power   rating at unity power   requirements specified in Table 3 in 
                                factor.”                factor.”                IEEE Std 1547-2018.

            Reactive Power      20% to 30% of           90% to 100% of          Reported values match test operating
            (Injected)          DER “reactive power     DER “reactive power     conditions within the accuracy 
                                injected maximum        injected maximum        requirements specified in Table 3 in
                                rating.”                rating.”                IEEE Std 1547-2018.

            Reactive Power      20% to 30% of           90% to 100% of          Reported values match test operating
            (Absorbed)          DER “reactive power     DER “reactive power     conditions within the accuracy 
                                injected maximum        injected maximum        requirements specified in Table 3 in
                                rating.”                rating.”                IEEE Std 1547-2018.

            Voltage(s)          At or below             At or above 1.08 × (ac  Reported values match test operating
                                0.90 × (ac voltage      voltage nominal         conditions within the accuracy 
                                nominal rating).        rating).                requirements specified in Table 3 in
                                                                                IEEE Std 1547-2018.
                                                                                
            Frequency           At or below 57.2 Hz.    At or above 61.6 Hz.    Reported values match test operating
                                                                                conditions within the accuracy 
                                                                                requirements specified in Table 3 in 
                                                                                IEEE Std 1547-2018.
            
            Operational State   On: Conduct this test   Off: If supported by    Reported Operational State matches the
                                while the DER is        the DER, conduct this   device present condition for on and off 
                                generating.             test while capable of   states.
                                                        communicating but not
                                                        capable of generating.
            
            Connection Status   Connected: Conduct      Disconnected:           Reported Connection Status matches the
                                this test while the     Conduct this test while device present connection condition.
                                DER is generating.      permit service is
                                                        disabled.

            Alarm Status        Has alarms set.         No alarms set.          Reported Alarm Status matches the device
                                                                                present alarm condition for alarm and no
                                                                                alarm conditions. For test purposes 
                                                                                only, the DER manufacturer shall specify 
                                                                                at least one way an alarm condition that
                                                                                is supported in the protocol being 
                                                                                tested can be set and cleared.
            '''

            # for p in [0.25, 0.59, 0.87, 0.45]:
            #     ts.log_debug('Test Read: %s' % eut.get_p_lim())
            #     ts.log_debug('Test Write: %s' % eut.set_p_lim(params={"p_lim_mode_enable_as": True, "p_lim_w_as": p}))
            #     ts.sleep(10)
            #     mn_w = eut.get_monitoring().get("mn_w")
            #     ts.log_debug('mn_w: %s' % mn_w)
            #     ts.log_debug('w_max: %s' % w_max)
            #     ts.log_debug('eval: %s' % (1e5 * (mn_w / w_max)))
            # eut.set_p_lim(params={"p_lim_mode_enable_as": False, "p_lim_w_as": 1.})

            m = eut.get_monitoring()
            if m is not None:
                print_params(m)
                '''
                ________________________________________________________________________________________________________
                Monitoring          Operating               Operating               Criteria
                information         Point A                 Point B
                parameter                                
                ________________________________________________________________________________________________________
                Active Power        20% to 30% of           90% to 100% of          Reported values match test operating
                                    DER “active power       DER “active power       conditions within the accuracy 
                                    rating at unity power   rating at unity power   requirements specified in Table 3 in 
                                    factor.”                factor.”                IEEE Std 1547-2018.
                '''

                accuracy = 5.
                ts.log('Starting Monitoring Assessment. Active Power reported from the EUT is: %s' % m.get('mn_w'))
                for setpoint in [0.25, 0.95]:  # test_pts (pu)
                    setpoint_pct = setpoint * 100.
                    ts.log_debug('    ****Configuring Experiment. Executing: p_lim = %s' % setpoint)
                    eut.set_p_lim(params={"p_lim_mode_enable_as": True, "p_lim_w_as": setpoint})
                    ts.sleep(2)
                    inaccurate_measurement = True
                    timeout = 5
                    test_pass_fail = 'FAIL'
                    while inaccurate_measurement and timeout > 0:
                        timeout -= 1
                        value = 1e5*(eut.get_monitoring().get("mn_w")/var_max)
                        # ts.log_debug('    ****Returned Value: %s' % value)
                        ts.log('    EUT Active Power is currently %0.1f%% Prated, waiting another %0.1f sec' %
                               (value, timeout))
                        if setpoint_pct - accuracy <= value <= setpoint_pct + accuracy:  # +/- accuracy in pct
                            ts.log('    EUT has recorded power +/- %s%% as required by IEEE 1547-2018.' % accuracy)
                            ts.log('    Returning EUT to rated power.')
                            test_pass_fail = 'PASS'
                            inaccurate_measurement = False
                        else:
                            ts.log('    EUT outside the IEEE 1547-2018 requirements. Bounds = [%0.1f, %0.1f], '
                                   'Value = %0.1f' % (setpoint_pct - accuracy, setpoint_pct + accuracy, value))
                            ts.sleep(1)
                    ts.log('RESULT = %s' % test_pass_fail)

                ts.log_debug('    ****Resetting Function p_lim')
                eut.set_p_lim(params={"p_lim_mode_enable_as": False, "p_lim_w_as": 1.})

                # for q in [0.25, 0.59, 0.87, 0.45]:
                #     ts.log_debug('Test Read: %s' % eut.get_const_q())
                #     ts.log_debug('Test Write: %s' % eut.set_const_q(params={"const_q_mode_enable_as": True,
                #                                                             "const_q_as": q}))
                #     ts.sleep(10)
                #     mn_var = eut.get_monitoring().get("mn_var")
                #     ts.log_debug('mn_var: %s' % mn_var)
                #     ts.log_debug('var_max: %s' % var_max)
                #     ts.log_debug('eval: %s' % (1e5 * (mn_var / var_max)))
                # eut.set_const_q(params={"const_q_mode_enable_as": False})

                # for pf in [(0.10, 'inj'), (-0.10, 'abs'), (0.85, 'inj')]:
                #     ts.log_debug('Test Read: %s' % eut.get_const_pf())
                #     ts.log_debug('Test Write: %s' % eut.set_const_pf(params={"const_pf_mode_enable_as": True,
                #                                                              "const_pf_abs_as": pf[0],
                #                                                              "const_pf_excitation_as": pf[1]}))
                #     ts.sleep(20)
                #     mn_var = eut.get_monitoring().get("mn_var")
                #     ts.log_debug('mn_var: %s' % mn_var)
                #     # ts.log_debug('var_max: %s' % var_max)
                #     ts.log_debug('eval: %s' % (1e5 * (mn_var / var_max)))
                # eut.set_const_q(params={"const_q_mode_enable_as": False})

                '''
                ________________________________________________________________________________________________________
                Monitoring          Operating               Operating               Criteria
                information         Point A                 Point B
                parameter                                
                ________________________________________________________________________________________________________
                Reactive Power      20% to 30% of           90% to 100% of          Reported values match test operating
                (Injected)          DER “reactive power     DER “reactive power     conditions within the accuracy 
                                    injected maximum        injected maximum        requirements specified in Table 3 in
                                    rating.”                rating.”                IEEE Std 1547-2018.
    
                Reactive Power      20% to 30% of           90% to 100% of          Reported values match test operating
                (Absorbed)          DER “reactive power     DER “reactive power     conditions within the accuracy 
                                    injected maximum        injected maximum        requirements specified in Table 3 in
                                    rating.”                rating.”                IEEE Std 1547-2018.
                '''

                accuracy = 5.
                ts.log('Starting Monitoring Assessment. Reactive Power reported from the EUT is: %s' %
                       eut.get_monitoring().get('mn_var'))
                for setpoint in [0.25, 0.95]:
                    setpoint_pct = setpoint * 100.
                    pf = math.sqrt(1. - (setpoint ** 2))
                    ts.log_debug('     ****Configuring Experiment. Executing: Const PF = %s' % setpoint)
                    eut.set_const_pf(params={"const_pf_mode_enable_as": True, "const_pf_abs_as": pf,
                                             "const_pf_excitation_as": "inj"})
                    ts.sleep(2)
                    inaccurate_measurement = True
                    timeout = 5
                    test_pass_fail = 'FAIL'
                    while inaccurate_measurement and timeout > 0:
                        timeout -= 1
                        value = 1e5*(eut.get_monitoring().get("mn_var")/var_max)
                        # ts.log_debug('    ****Returned Value: %s' % value)
                        ts.log('    EUT Reactive Power is currently %0.1f%%, waiting another %0.1f sec' %
                               (value, timeout))
                        if setpoint_pct - accuracy <= value <= setpoint_pct + accuracy:  # +/- accuracy in pct
                            ts.log('    EUT has recorded value of +/- %s%% as required by IEEE 1547-2018.' % accuracy)
                            test_pass_fail = 'PASS'
                            inaccurate_measurement = False
                        else:
                            ts.log('    EUT outside the IEEE 1547-2018 requirements. Bounds = [%0.1f, %0.1f], '
                                   'Value = %0.1f' % (setpoint_pct - accuracy, setpoint_pct + accuracy, value))
                            ts.sleep(1)
                    ts.log('RESULT = %s' % test_pass_fail)

                ts.log_debug('    ****Resetting Function Executing: Const PF')
                eut.set_const_pf(params={"const_pf_mode_enable_as": False})

                # Absorbed Reactive Power
                for setpoint in [-0.25, -0.95]:
                    setpoint_pct = setpoint * 100.
                    pf = math.sqrt(1. - (setpoint ** 2))
                    ts.log_debug('****Configuring Experiment. Executing: Const PF')
                    eut.set_const_pf(params={"const_pf_mode_enable_as": True, "const_pf_abs_as": pf,
                                             "const_pf_excitation_as": "abs"})
                    ts.sleep(2)
                    inaccurate_measurement = True
                    timeout = 5
                    test_pass_fail = 'FAIL'
                    while inaccurate_measurement and timeout > 0:
                        timeout -= 1
                        value = 1e5*(eut.get_monitoring().get("mn_var")/var_max)
                        # ts.log_debug('    ****Returned Value: %s' % value)
                        ts.log('    EUT Reactive Power is currently %0.1f%%, waiting another %0.1f sec' %
                               (value, timeout))
                        if setpoint_pct - accuracy <= value <= setpoint_pct + accuracy:  # +/- accuracy in pct
                            ts.log('    EUT has recorded value of +/- %s%% as required by IEEE 1547-2018.' % accuracy)
                            test_pass_fail = 'PASS'
                            inaccurate_measurement = False
                        else:
                            ts.log('    EUT outside the IEEE 1547-2018 requirements. Bounds = [%0.1f, %0.1f], '
                                   'Value = %0.1f' % (setpoint_pct - accuracy, setpoint_pct + accuracy, value))
                            ts.sleep(1)
                    ts.log('RESULT = %s' % test_pass_fail)

                ts.log_debug('    ****Resetting Function Executing: Const PF')
                eut.set_const_pf(params={"const_pf_mode_enable_as": False})

                '''
                ________________________________________________________________________________________________________
                Monitoring          Operating               Operating               Criteria
                information         Point A                 Point B
                parameter                                
                ________________________________________________________________________________________________________
                Voltage(s)          At or below             At or above 1.08 × (ac  Reported values match test operating
                                    0.90 × (ac voltage      voltage nominal         conditions within the accuracy 
                                    nominal rating).        rating).                requirements specified in Table 3 in
                                                                                    IEEE Std 1547-2018. (+/-1% Vnom)
                '''

                accuracy = 1.
                ts.log('Starting Monitoring Assessment. Voltage reported from the EUT is: %s' %
                       eut.get_monitoring().get('mn_v'))
                for setpoint in [89, 109]:
                    v_grid = setpoint * 0.01 * v_nom
                    if grid is not None:
                        grid.voltage(v_grid)
                    ts.log_debug('****Configuring Experiment. Setting grid voltage to %s V' % v_grid)
                    ts.sleep(2)
                    inaccurate_measurement = True
                    timeout = 5
                    test_pass_fail = 'FAIL'
                    while inaccurate_measurement and timeout > 0:
                        timeout -= 1
                        # voltages = grid.meas_voltage()
                        voltages = [v_grid, v_grid, v_grid]
                        meas_volt_mean_pct = (sum(voltages)/len(voltages)/v_nom)*100.
                        eut_volt = [eut.get_monitoring().get("mn_v")]
                        eut_volt_mean_pct = (sum(eut_volt)/len(eut_volt)/v_nom)*100.
                        ts.log('    EUT-reported voltage is currently %0.1f%%, real voltage = %s%%, '
                               'waiting another %0.1f sec' % (eut_volt_mean_pct, meas_volt_mean_pct, timeout))
                        if meas_volt_mean_pct - accuracy <= eut_volt_mean_pct <= meas_volt_mean_pct + accuracy:
                            ts.log('    EUT has recorded value of +/- %s%% as required by IEEE 1547-2018.' % accuracy)
                            test_pass_fail = 'PASS'
                            inaccurate_measurement = False
                        else:
                            ts.log('    EUT outside the IEEE 1547-2018 requirements. Bounds = [%0.1f, %0.1f], '
                                   'Value = %0.1f' % (meas_volt_mean_pct - accuracy, meas_volt_mean_pct + accuracy,
                                                      eut_volt_mean_pct))
                            ts.sleep(1)
                    ts.log('RESULT = %s' % test_pass_fail)
                if grid is not None:
                    grid.voltage(v_nom)

                '''
                ________________________________________________________________________________________________________
                Monitoring          Operating               Operating               Criteria
                information         Point A                 Point B
                parameter                                
                ________________________________________________________________________________________________________
                Frequency           At or below 57.2 Hz.    At or above 61.6 Hz.    Reported values match test operating
                                                                                    conditions within the accuracy 
                                                                                    requirements specified in Table 3 in 
                                                                                    IEEE Std 1547-2018. (10 mHz)
                '''

                accuracy = (0.010/60.)*100.  # 10 mHz
                ts.log('Starting Monitoring Assessment. Frequency reported from the EUT is: %s' %
                       eut.get_monitoring().get('mn_hz'))
                for setpoint in [57., 61.8]:
                    if grid is not None:
                        grid.freq(setpoint)
                    ts.log_debug('****Configuring Experiment. Setting grid frequency to %s Hz' % setpoint)
                    ts.sleep(2)
                    inaccurate_measurement = True
                    timeout = 5
                    test_pass_fail = 'FAIL'
                    while inaccurate_measurement and timeout > 0:
                        timeout -= 1
                        eut_freq = eut.get_monitoring().get("mn_hz")
                        ts.log('    EUT-reported freq is currently %0.1f, real freq = %s%%, '
                               'waiting another %0.1f sec' % (eut_freq, setpoint, timeout))
                        if eut_freq - accuracy <= setpoint <= eut_freq + accuracy:
                            ts.log('    EUT has recorded value of +/- %s%% as required by IEEE 1547-2018.' % accuracy)
                            test_pass_fail = 'PASS'
                            inaccurate_measurement = False
                        else:
                            ts.log('    EUT outside the IEEE 1547-2018 requirements. Bounds = [%0.1f, %0.1f], '
                                   'Value = %0.1f' % (eut_freq - accuracy, setpoint + accuracy, eut_freq))
                            ts.sleep(1)
                    ts.log('RESULT = %s' % test_pass_fail)
                if grid is not None:
                    grid.freq(60.)

                '''
                ________________________________________________________________________________________________________
                Monitoring          Operating               Operating               Criteria
                information         Point A                 Point B
                parameter                                
                ________________________________________________________________________________________________________
            
                Operational State   On: Conduct this test   Off: If supported by    Reported Operational State matches 
                                    while the DER is        the DER, conduct this   the device present condition for on 
                                    generating.             test while capable of   and off states.
                                                            communicating but not
                                                            capable of generating.
                '''
                ts.log('Starting Monitoring Assessment. State reported from the EUT is: %s' %
                       eut.get_monitoring().get('mn_st'))
                for state in [True, False]:
                    eut.set_conn(params={'conn_as': state})
                    ts.log_debug('****Configuring Experiment. Setting EUT Operational State to %s' % setpoint)
                    ts.sleep(2)
                    inaccurate_measurement = True
                    timeout = 5
                    test_pass_fail = 'FAIL'
                    while inaccurate_measurement and timeout > 0:
                        timeout -= 1
                        eut_conn = eut.get_monitoring().get('mn_conn').get('mn_op_started')
                        ts.log('    EUT-reported connection = %s, State setting = %s, waiting another %0.1f sec' %
                               (eut_conn, state, timeout))
                        if eut_conn == state:
                            test_pass_fail = 'PASS'
                            inaccurate_measurement = False
                        else:
                            ts.log('    EUT outside IEEE 1547-2018 requirements.')
                            ts.sleep(1)
                    ts.log('RESULT = %s' % test_pass_fail)
                eut.set_conn(params={'conn_as': True})

                '''
                ________________________________________________________________________________________________________
                Monitoring          Operating               Operating               Criteria
                information         Point A                 Point B
                parameter                                
                ________________________________________________________________________________________________________
                Connection Status   Connected: Conduct      Disconnected:           Reported Connection Status matches 
                                    this test while the     Conduct this test while the device present connection 
                                    DER is generating.      permit service is       condition.
                                                            disabled.
                '''
                ts.log('Starting Monitoring Assessment. Connection Status reported from the EUT is: %s' %
                       eut.get_monitoring().get('mn_conn'))
                for conn in [True, False]:
                    eut.set_conn(params={'conn_as': conn})
                    ts.log_debug('****Configuring Experiment. Setting EUT connection status to %s' % setpoint)
                    ts.sleep(2)
                    inaccurate_measurement = True
                    timeout = 5
                    test_pass_fail = 'FAIL'
                    while inaccurate_measurement and timeout > 0:
                        timeout -= 1
                        eut_conn = eut.get_monitoring().get('mn_st').get('mn_conn_connected_generating')
                        ts.log('    EUT-reported Status = %s, Connection Status = %s, waiting another %0.1f sec' %
                               (eut_conn, conn, timeout))
                        if eut_conn == conn:
                            test_pass_fail = 'PASS'
                            inaccurate_measurement = False
                        else:
                            ts.log('    EUT outside IEEE 1547-2018 requirements.')
                            ts.sleep(1)
                    ts.log('RESULT = %s' % test_pass_fail)
                eut.set_conn(params={'conn_as': True})

                '''
                ________________________________________________________________________________________________________
                Monitoring          Operating               Operating               Criteria
                information         Point A                 Point B
                parameter                                
                ________________________________________________________________________________________________________
                Alarm Status        Has alarms set.         No alarms set.          Reported Alarm Status matches the 
                                                                                    device present alarm condition for 
                                                                                    alarm and no alarm conditions. For 
                                                                                    test purposes only, the DER 
                                                                                    manufacturer shall specify at least 
                                                                                    one way an alarm condition that
                                                                                    is supported in the protocol being 
                                                                                    tested can be set and cleared.
                '''

                for error in [True, False]:
                    eut.set_error(params={'error_as': error})  # configure and error state
                    ts.log_debug('****Configuring Experiment. Setting EUT error to %s' % setpoint)
                    ts.sleep(2)
                    inaccurate_measurement = True
                    timeout = 5.
                    test_pass_fail = 'FAIL'
                    while inaccurate_measurement and timeout > 0:
                        timeout -= 1
                        eut_error = eut.get_monitoring().get('mn_alrm').get('mn_alm_priority_1')
                        ts.log('    EUT-reported Status = %s, Error Status = %s, waiting another %0.1f sec' %
                               (eut_error, error, timeout))
                        if eut_error == error:
                            test_pass_fail = 'PASS'
                            inaccurate_measurement = False
                        else:
                            ts.log('    EUT outside non-compliant to IEEE 1547-2018 requirements.')
                            ts.sleep(1)
                    ts.log('RESULT = %s' % test_pass_fail)
                eut.set_error(params={'error_as': False})  # configure and error state

            else:
                ts.log_warning('DER measurements testing not supported')
        else:
            ts.log('Skipping DER monitoring test')

        return script.RESULT_COMPLETE

    except script.ScriptFail as e:
        reason = str(e)
        if reason:
            ts.log_error(reason)

    finally:
        if daq is not None:
            daq.close()
        if pv is not None:
            pv.close()
        if grid is not None:
            if v_nom is not None:
                grid.voltage(v_nom)
            grid.close()
        if chil is not None:
            chil.close()
        if eut is not None:
            eut.close()
            if eut.close() != 'No Agent':
                eut.stop_agent()
        if result_summary is not None:
            result_summary.close()

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

info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.0.0')

info.param_group('iop_params', label='Test Parameters')
info.param('iop_params.settings_test', label='Run Settings Test', default='No', values=['Yes', 'No'])
info.param('iop_params.monitoring_test', label='Run Monitoring Test', default='Yes', values=['Yes', 'No'])

# EUT general parameters
info.param_group('eut', label='EUT Parameters', glob=True)
info.param('eut.phases', label='Phases', default='Three phase', values=['Single phase', 'Split phase', 'Three phase'])
info.param('eut.s_rated', label='Apparent power rating (VA)', default=10000.0)
info.param('eut.p_rated', label='Output power rating (W)', default=8000.0)
info.param('eut.p_min', label='Minimum Power Rating (W)', default=1000.)
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

der1547.params(info)
hil.params(info)
das.params(info)
pvsim.params(info)
gridsim.params(info)


def script_info():

    return info


if __name__ == "__main__":

    # stand alone invocation
    config_file = None
    if len(sys.argv) > 1:
        config_file = sys.argv[1]

    params = None

    test_script = script.Script(info=script_info(), config_file=config_file, params=params)

    run(test_script)


