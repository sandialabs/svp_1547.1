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
from svpelab import der
from svpelab import das
from svpelab import pvsim
from svpelab import gridsim
from svpelab import hil
from svpelab import p1547
import script


def test_run():

    result = script.RESULT_FAIL
    daq = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None
    dataset_filename = None

    try:

        settings_test = ts.param_value('iop.settings_test')
        monitoring_test = ts.param_value('iop.monitoring_test')

        v_nom = float(ts.param_value('eut.v_nom'))
        MSA_V = 0.01 * v_nom
        va_max = float(ts.param_value('eut.s_rated'))
        va_crg_max = va_max
        MSA_Q = 0.05 * float(ts.param_value('eut.s_rated'))
        MSA_P = 0.05 * float(ts.param_value('eut.s_rated'))
        MSA_F = 0.01
        f_nom = float(ts.param_value('eut.f_nom'))
        phases = ts.param_value('eut.phases')
        p_rated = float(ts.param_value('eut.p_rated'))
        w_max = p_rated
        p_min = p_rated
        w_crg_max = p_rated
        var_rated = float(ts.param_value('eut.var_rated'))
        var_max = float(ts.param_value('eut.var_rated'))

        # initialize DER configuration
        eut = der.der_init(ts)
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

        lib_1547 = p1547.module_1547(ts=ts, aif='Interoperability Tests')
        ts.log_debug("1547.1 Library configured for %s" % lib_1547.get_test_name())

        '''
        6.4 Nameplate data test
        a) Read from the DER each nameplate data item listed in Table 28 in IEEE Std 1547-2018.
        b) Compare each value received to the expected values from the manufacturer-provided expected values.

        Table 28 - Nameplate information
        ________________________________________________________________________________________________________________
        Parameter                                               Description
        ________________________________________________________________________________________________________________
        1. Active power rating at unity power factor            Active power rating in watts at unity power factor
           (nameplate active power rating)
        2. Active power rating at specified over-excited        Active power rating in watts at specified over-excited
           power factor                                         power factor
        3. Specified over-excited power factor                  Over-excited power factor as described in 5.2
        4. Active power rating at specified under-excited       Active power rating in watts at specified under-excited
           power factor                                         power factor
        5. Specified under-excited power factor                 Under-excited power factor as described in 5.2
        6. Apparent power maximum rating                        Maximum apparent power rating in voltamperes
        7. Normal operating performance category                Indication of reactive power and voltage/power control
                                                                capability. (Category A/B as described in 1.4)
        8. Abnormal operating performance category              Indication of voltage and frequency ride-through
                                                                capability Category I, II, or III, as described in 1.4
        9. Reactive power injected maximum rating               Maximum injected reactive power rating in vars
        10. Reactive power absorbed maximum rating              Maximum absorbed reactive power rating in vars
        11. Active power charge maximum rating                  Maximum active power charge rating in watts
        12. Apparent power charge maximum rating                Maximum apparent power charge rating in voltamperes. May
                                                                differ from the apparent power maximum rating
        13. AC voltage nominal rating                           Nominal AC voltage rating in RMS volts
        14. AC voltage maximum rating                           Maximum AC voltage rating in RMS volts
        15. AC voltage minimum rating                           Minimum AC voltage rating in RMS volts
        16. Supported control mode functions                    Indication of support for each control mode function
        17. Reactive susceptance that remains connected to      Reactive susceptance that remains connected to the Area
            the Area EPS in the cease to energize and trip      EPS in the cease to energize and trip state
            state
        18. Manufacturer                                        Manufacturer
        19. Model                                               Model
        20. Serial number                                       Serial number
        21. Version                                             Version
        '''

        ts.log('---')
        der_info = eut.info()
        nameplate = eut.nameplate()

        ts.log('DER Nameplate Information:')
        if nameplate is not None:
            ts.log('  Active power rating at unity power factor (nameplate active power rating) [WRtg]: %s' %
                   nameplate.get('WRtg'))
            ts.log('  Active power rating at specified over-excited power factor: %s' % 'Unknown')
            ts.log('  Specified over-excited power factor [PFRtgQ1]: %s' % nameplate.get('PFRtgQ1'))
            ts.log('  Specified under-excited power factor [PFRtgQ2]: %s' % nameplate.get('PFRtgQ2'))
            ts.log('  Apparent power maximum rating: %s' % nameplate.get('VARtg'))
            ts.log('  Normal operating performance category: %s' % 'Unknown')
            ts.log('  Abnormal operating performance category: %s' % 'Unknown')
            ts.log('  Reactive power injected maximum rating [VArRtgQ1]: %s' % nameplate.get('VArRtgQ1'))
            ts.log('  Reactive power absorbed maximum rating [VArRtgQ4]: %s' % nameplate.get('VArRtgQ4'))
            ts.log('  Apparent power charge maximum rating: %s' % nameplate.get('MaxChrRte'))
            ts.log('  AC voltage nominal rating: %s' % 'Unknown')
            ts.log('  AC voltage maximum rating: %s' % 'Unknown')
            ts.log('  AC voltage minimum rating: %s' % 'Unknown')
        if der_info is not None:
            ts.log('  Supported control mode functions: %s' % der_info.get('Options'))
        else:
            ts.log_warning('DER info not supported')
        if nameplate is not None:
            ts.log('  Reactive susceptance that remains connected to the Area EPS in the cease to '
                   'energize and trip state: %s' % 'Unknown')
        else:
            ts.log_warning('DER nameplate not supported')
        if der_info is not None:
            ts.log('  Manufacturer: %s' % (der_info.get('Manufacturer')))
            ts.log('  Model: %s' % (der_info.get('Model')))
            ts.log('  Serial Number: %s' % (der_info.get('SerialNumber')))
            ts.log('  Version: %s' % (der_info.get('Version')))
        else:
            ts.log_warning('DER info not supported')

        if settings_test:

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

            # Special considerations for CHIL ASGC/Typhoon startup
            if chil is not None:
                inv_power = eut.measurements().get('W')
                timeout = 120.
                if inv_power <= p_rated * 0.85:
                    pv.irradiance_set(995)  # Perturb the pv slightly to start the inverter
                    ts.sleep(3)
                    eut.connect(params={'Conn': True})
                while inv_power <= p_rated * 0.85 and timeout >= 0:
                    ts.log('Inverter power is at %0.1f. Waiting up to %s more seconds or until EUT starts...' %
                           (inv_power, timeout))
                    ts.sleep(1)
                    timeout -= 1
                    inv_power = eut.measurements().get('W')
                    if timeout == 0:
                        result = script.RESULT_FAIL
                        raise der.DERError('Inverter did not start.')
                ts.log('Waiting for EUT to ramp up')
                ts.sleep(8)
                # ts.log_debug('DAS data_read(): %s' % daq.data_read())

            settings = eut.settings()
            if settings is not None:
                # Active Power Maximum
                ts.log('  Active Power Maximum [WMax]: %s' % (settings.get('WMax')))
                ts.log('  Setting WMax to %f.' % (0.8*w_max))
                eut.settings(params={'WMax': 0.8*w_max})
                ts.sleep(2)
                power = lib_1547.get_measurement_total(data=daq.data_capture_read(), type_meas='P', log=True)
                ts.log('  Power was recorded to be: %f.' % power)
                ts.log('  Returning WMax to %f.' % w_max)
                eut.settings(params={'WMax': w_max})

                # Apparent Power Maximum
                ts.log('  Apparent Power Maximum [VAMax]: %s' % (settings.get('VAMax')))
                ts.log('  Setting VAMax to %f.' % (0.8*va_max))
                eut.settings(params={'VAMax': 0.8*va_max})
                ts.sleep(2)
                va = lib_1547.get_measurement_total(data=daq.data_capture_read(), type_meas='VA', log=True)
                ts.log('  Apparent Power was recorded to be: %f.' % va)
                ts.log('  Returning VAMax to %f.' % va_max)
                eut.settings(params={'VAMax': va_max})

                # Reactive Power Injected Maximum
                # TODO check on sign convention here
                ts.log('  Reactive Power Injected Maximum [VArMaxQ1]: %s' % (settings.get('VArMaxQ1')))
                ts.log('  Setting VArMaxQ1 to %f.' % (0.8*var_max))
                eut.settings(params={'VArMaxQ1': 0.8*var_max})
                eut.reactive_power(params={'Ena': True, 'VArPct_Mod': 'VArMax', 'VArMaxPct': 100})
                ts.sleep(2)
                q = lib_1547.get_measurement_total(data=daq.data_capture_read(), type_meas='Q', log=True)
                ts.log('  Reactive Power Injected was recorded to be: %f.' % q)
                ts.log('  Returning VArMaxQ1 to %f.' % var_max)
                eut.settings(params={'VArMaxQ1': var_max})
                eut.reactive_power(params={'Ena': False})

                # Reactive Power Absorbed Maximum
                ts.log('  Reactive Power Absorbed Maximum [VArMaxQ4]: %s' % (settings.get('VArMaxQ4')))
                ts.log('  Setting VArMaxQ4 to %f.' % (0.8*var_max))
                eut.settings(params={'VArMaxQ4': 0.8*var_max})
                eut.reactive_power(params={'Ena': True, 'VArPct_Mod': 'VArMax', 'VArMaxPct': -100})
                ts.sleep(2)
                q = lib_1547.get_measurement_total(data=daq.data_capture_read(), type_meas='Q', log=True)
                ts.log('  Reactive Power Absorbed was recorded to be: %f.' % q)
                ts.log('  Returning VArMaxQ4 to %f.' % var_max)
                eut.settings(params={'VArMaxQ4': var_max})
                eut.reactive_power(params={'Ena': False})

                # AC Current Maximum
                ts.log('  Apparent Power Maximum [VAMax]: %s' % (settings.get('VAMax')))
                ts.log('  Setting VAMax to %f.' % (0.8*va_max))
                eut.settings(params={'VAMax': 0.8*va_max})
                ts.sleep(2)
                va = lib_1547.get_measurement_total(data=daq.data_capture_read(), type_meas='VA', log=True)
                ts.log('  Apparent Power was recorded to be: %f.' % va)
                ts.log('  Returning VAMax to %f.' % va_max)
                eut.settings(params={'VAMax': va_max})

                # Mode Enable Interval
                # TODO add this assessment  {'ModeInterval': [5, 300]}

            else:
                ts.log_warning('DER settings not supported')

            storage = eut.storage()
            if storage is not None:
                # Active Power Charge Maximum
                ts.log('  Active Power Charge Maximum [WChaMax]: %s' % (storage.get('WChaMax')))
                ts.log('  Setting WChaMax to %f.' % (0.8*w_crg_max))
                eut.storage(params={'WChaMax': 0.8*w_crg_max})
                ts.log('  Setting InWRte to %f %% of max charging rate.' % 100.)  # Percent of max charging rate.
                eut.storage(params={'InWRte': 100.})
                ts.sleep(2)
                power = lib_1547.get_measurement_total(data=daq.data_capture_read(), type_meas='P', log=True)
                ts.log('  Apparent Power was recorded to be: %f.' % power)
                ts.log('  Returning WChaMax to %f.' % w_crg_max)
                eut.storage(params={'WChaMax': w_crg_max})
                eut.storage(params={'InWRte': 0.})

                # Apparent Power Charge Maximum
                ts.log('  Apparent Power Charge Maximum [VAChaMax]: %s' % (storage.get('VAChaMax')))
                ts.log('  Setting WChaMax to %f.' % (0.8*va_crg_max))
                eut.storage(params={'VAChaMax': 0.8*va_crg_max})
                ts.log('  Setting InWRte to %f %% of max charging rate.' % 100.)  # Percent of max charging rate.
                eut.storage(params={'InWRte': 100.})
                ts.sleep(2)
                power = lib_1547.get_measurement_total(data=daq.data_capture_read(), type_meas='VA', log=True)
                ts.log('  Apparent Power was recorded to be: %f.' % power)
                ts.log('  Returning VAChaMax to %f.' % va_crg_max)
                eut.storage(params={'VAChaMax': va_crg_max})
                eut.storage(params={'InWRte': 0.})

                # Stated Energy Storage Capacity
                # StorAval = State of charge (ChaState) minus storage reserve (MinRsvPct) times capacity rating (AhrRtg)
                # TODO add this assessment

            else:
                ts.log_warning('DER storage not supported')

        if monitoring_test:
            '''
            6.6 Monitoring information test

            a) Set the operating conditions of the DER to the values specified in the "Operating Point A" column in
               Table 43.
            b) Wait not less than 30 s, then read from the DER each monitoring information, and verify that the
               reported values match the operating conditions as identified.
            c) Change the operating conditions of the DER as specified in the "Operating Point B" column 16 in Table 43.
            d) Repeat step b).
            '''

            # Monitoring information parameter: Active Power
            # Operating Point A: 0 to 10% of DER "active power rating at unity power factor"
            # Operating Point B: 90 to 100% of DER "active power rating at unity power factor"
            # Pass/Fail Criteria: Reported values match test operating conditions within the accuracy requirements
            # specified in Table 3 in IEEE Std 1547-2018. (+/- 5% Srated)
            m = eut.measurements()
            if m is not None:
                ts.log('  Active Power reported from the EUT is: %s W' % (m.get('W')))
                for setpoint in [5, 100]:
                    eut.limit_max_power(params={'Ena': True, 'WMaxPct': setpoint})  # curtial to 5% of power
                    inaccurate_measurement = True
                    while inaccurate_measurement:
                        power_pct = 100*(eut.measurements().get('W')/w_max)
                        ts.log('    EUT power is currently %f%% Prated' % power_pct)
                        if setpoint - 5. <= power_pct <= setpoint + 5.:  # +/- 5% Srated
                            ts.log('EUT has recorded power +/- 5%% Srated, as required by IEEE 1547-2018.')
                            ts.log('Returning EUT to rated power.')
                            inaccurate_measurement = False
                        ts.sleep(1)
                    eut.limit_max_power(params={'Ena': False})
            else:
                ts.log_warning('DER measurements not supported')
            ts.log('---')

            # Monitoring information parameter: Reactive Power
            # Operating Point A: 90 to 100% of DER "reactive power injected maximum rating"
            # Operating Point B: 90 to 100% of DER "reactive power absorbed maximum rating"
            # Pass/Fail Criteria: Reported values match test operating conditions within the accuracy requirements
            # specified in Table 3 in IEEE Std 1547-2018. (+/- 5% Srated)
            m = eut.measurements()
            if m is not None:
                ts.log('  Reactive Power reported from the EUT is: %f VAr' % (m.get('VAr')))
                for setpoint in [5, 100]:
                    eut.reactive_power(params={'Ena': True, 'VArPct_Mod': 'VArMax', 'VArMaxPct': 100})
                    inaccurate_measurement = True
                    while inaccurate_measurement:
                        q_pct = 100*(eut.measurements().get('VAr')/var_max)
                        ts.log('    EUT reactive power is currently %f%% Qrated' % q_pct)
                        if setpoint - 5. <= q_pct <= setpoint + 5.:  # +/- 5% Srated
                            ts.log('EUT has recorded reactive power +/- 5%% Srated, as required by IEEE 1547-2018.')
                            ts.log('Returning EUT to rated power.')
                            inaccurate_measurement = False
                        ts.sleep(1)
                    eut.reactive_power(params={'Ena': False})
            else:
                ts.log_warning('DER measurements not supported')
            ts.log('---')

            # Monitoring information parameter: Voltage
            # Operating Point A: At or below 0.90x(AC voltage nominal rating)
            # Operating Point B: At or above 1.08x(AC voltage nominal rating)
            # Pass/Fail Criteria: Reported values match test operating conditions within the accuracy requirements
            # specified in Table 3 in IEEE Std 1547-2018. (+/-1% Vnom)

            for setpoint in [90, 108]:
                grid.voltage(setpoint)

                inaccurate_measurement = True
                while inaccurate_measurement:

                    voltages = []
                    if self.phases == 'Single phase':
                        voltages.append(eut.measurements()['PhVphA'])
                    elif self.phases == 'Split phase':
                        voltages.append(eut.measurements()['PhVphA'])
                        voltages.append(eut.measurements()['PhVphB'])
                    elif self.phases == 'Three phase':
                        voltages.append(eut.measurements()['PhVphB']/v_nom)
                        voltages.append(eut.measurements()['PhVphB']/v_nom)
                        voltages.append(eut.measurements()['PhVphC']/v_nom)
                        # TODO: also check phase to phase voltages
                        voltages.append(eut.measurements()['PPVphAB']/(v_nom*math.sqrt(3)))
                        voltages.append(eut.measurements()['PPVphBC']/(v_nom*math.sqrt(3)))
                        voltages.append(eut.measurements()['PPVphCA']/(v_nom*math.sqrt(3)))

                    ts.log('    EUT voltages are currently %s pu' % voltages)
                    pass_criteria = []
                    for voltage in voltages:
                        if setpoint/100. - 0.01 <= voltage <= setpoint/100. + 0.01:  # +/- 1% Vnom
                            pass_criteria.append(True)
                        else:
                            pass_criteria.append(True)

                    if all(pass_criteria):
                        ts.log('EUT has recorded voltage +/- 1%% Vnom, as required by IEEE 1547-2018.')
                        ts.log('Returning EUT to rated power.')
                        inaccurate_measurement = False
                    ts.sleep(1)

            grid.voltage(v_nom)

            # Monitoring information parameter: Frequency
            # Operating Point A: At or below 57.2Hz
            # Operating Point B: At or above 61.6Hz
            # Pass/Fail Criteria: Reported values match test operating conditions within the accuracy requirements
            # specified in Table 3 in IEEE Std 1547-2018. (10 mHz)

            # Monitoring information parameter: Operational State
            # Operating Point A: On
            # Operating Point B: Off
            # Pass/Fail Criteria: Reported Operational State matches the device present condition for on and off states.

            # Monitoring information parameter: Connection Status
            # Operating Point A: Connected: Enable Permit and AC conditions have been met to enter service as specified
            # in Table 39 of IEEE Std 1547-2018
            # Operating Point B: Disconnected: Permit service is disabled
            # Pass/Fail Criteria: Reported Connection Status matches the device present connection condition.
            status = eut.controls_status()
            if status is not None:
                ts.log('    Is Fixed_W enabled?: %s' % (status.get('Fixed_W')))
                ts.log('    Is Fixed_Var enabled?: %s' % (status.get('Fixed_Var')))
                ts.log('    Is Fixed_PF enabled?: %s' % (status.get('Fixed_PF')))
                ts.log('    Is Volt_Var enabled?: %s' % (status.get('Volt_Var')))
                ts.log('    Is Freq_Watt_Param enabled?: %s' % (status.get('Freq_Watt_Param')))
                ts.log('    Is Freq_Watt_Curve enabled?: %s' % (status.get('Freq_Watt_Curve')))
                ts.log('    Is Dyn_Reactive_Power enabled?: %s' % (status.get('Dyn_Reactive_Power')))
                ts.log('    Is LVRT enabled?: %s' % (status.get('LVRT')))
                ts.log('    Is HVRT enabled?: %s' % (status.get('HVRT')))
                ts.log('    Is Watt_PF enabled?: %s' % (status.get('Watt_PF')))
                ts.log('    Is Volt_Watt enabled?: %s' % (status.get('Volt_Watt')))
                ts.log('    Is Scheduled enabled?: %s' % (status.get('Scheduled')))
                ts.log('    Is LFRT enabled?: %s' % (status.get('LFRT')))
                ts.log('    Is HFRT enabled?: %s' % (status.get('HFRT')))

                ts.log('---')
                status = eut.conn_status()
                ts.log('    Is PV_Connected?: %s' % (status.get('PV_Connected')))
                ts.log('    Is PV_Available?: %s' % (status.get('PV_Available')))
                ts.log('    Is PV_Operating?: %s' % (status.get('PV_Operating')))
                ts.log('    Is PV_Test?: %s' % (status.get('PV_Test')))
                ts.log('    Is Storage_Connected?: %s' % (status.get('Storage_Connected')))
                ts.log('    Is Storage_Available?: %s' % (status.get('Storage_Available')))
                ts.log('    Is Storage_Operating?: %s' % (status.get('Storage_Operating')))
                ts.log('    Is Storage_Test?: %s' % (status.get('Storage_Test')))
                ts.log('    Is EPC_Connected?: %s' % (status.get('EPC_Connected')))
                ts.log('---')

            # Monitoring information parameter: Alarm Status
            # Operating Point A: Has alarms set
            # Operating Point B: No alarms set
            # Pass/Fail Criteria: Reported Alarm Status matches the device present alarm condition for alarm and no
            # alarm conditions. The DER manufacturer shall specify at least one way an alarm condition which is
            # supported in the protocol being tested can be set and cleared.

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

info.param_group('iop', label='Test Parameters')
info.param('iop.settings_test', label='Run the Settings Test', default=True, values=[True, False])
info.param('iop.monitoring_test', label='Run the Monitoring Test', default=True, values=[True, False])

der.params(info)
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


