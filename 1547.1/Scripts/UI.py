"""
IEEE 1547.1-2020 Section 5.10 Unintentional islanding

The unintentional islanding test given in 5.10.2 may be used for any EUT. EUT that use conducted
permissive signals for unintentional islanding shall follow the procedure 5.10.3. EUT that have a
permissive hardware input shall follow the procedure in 5.10.4. Reverse-power or minimum import power
flow protection shall be tested in accordance with 5.10.5. EUT may support multiple methods and shall be
tested for each of the methods supported.

Full compliance is achieved by meeting the criteria of 5.10.2 or 5.10.5. Partial compliance is achieved by
meeting the criteria of 5.10.3 or 5.10.4, because those methods either require additional equipment beyond
what is tested in the type test or installed on the EPS. More information can be found in 8.1.2 on treatment
of full and partial compliance during DER evaluation and commissioning.

In order to facilitate faster test times, default time settings longer than 2.5 seconds may be reduced to as
low as 2.5 seconds for the purposes of these tests, and enter service delay settings may be adjusted to any
convenient value.

Initial Script: 8-27-20, jjohns2@sandia.gov

"""

import sys
import os
import traceback
from svpelab import hil
from svpelab import das
from svpelab import pvsim
from svpelab import der
from svpelab import der1547
from svpelab import p1547
import script


def find_rlc():
    res = 1
    ind = 1
    cap = 1
    return res, ind, cap


def run_ui_test(phil, model_name, daq, test_num, t_trips, q_inc, high_freq_count, low_freq_count, result_summary, c):
    """
    Run single UI test

    :param phil: Power hardware-in-the-loop object
    :param model_name: name of the PHIL model
    :param daq: DAQ object
    :param test_num: number of the test
    :param t_trips: trip time dict with {q_inc, t_trip}
    :param q_inc: reactive power increment
    :param high_freq_count: number of over frequency islanding events
    :param low_freq_count: number of under frequency islanding events
    :param result_summary: summary file
    :return: t_trips, t_trip, high_freq_count, low_freq_count
    """

    # adjust reactive load
    phil.set_params(model_name + '/SM_Source/Phase Angle Phase A0/Value', c * q_inc)

    '''
    2) With the EUT and load operating at stable conditions, record the voltage and current at switch
    S3. Record the active and reactive power at switch S3 on a net and per phase basis. Record
    the active and reactive power of the EUT, the resistive load, the capacitive load and the
    inductive loads on a net and per phase basis as well. These measurements may be done
    individually for the EUT, resistive load, capacitive load and inductive loads prior to operating
    the entire combined circuit.
    '''
    ts.sleep(2.)
    daq.data_sample()
    meas = daq.data_read()
    ts.log('Voltages = [%0.1f, %0.1f, %0.1f] and currents = [%0.1f, %0.1f, %0.1f] at switch S3' %
           (meas['v1_s3'], meas['v2_s3'], meas['v3_s3'], meas['i1_s3'], meas['i2_s3'], meas['i3_s3']))
    ts.log('Active powers = [%0.1f, %0.1f, %0.1f] and reactive powers = [%0.1f, %0.1f, %0.1f] at '
           'switch S3' % (meas['p1_s3'], meas['p2_s3'], meas['p3_s3'],
                          meas['q1_s3'], meas['q2_s3'], meas['q3_s3']))
    ts.log('Active powers = [%0.1f, %0.1f, %0.1f] and reactive powers = [%0.1f, %0.1f, %0.1f] at '
           'switch S2' % (meas['p1_s2'], meas['p2_s2'], meas['p3_s2'],
                          meas['q1_s2'], meas['q2_s2'], meas['q3_s2']))
    ts.log('Active powers = [%0.1f, %0.1f, %0.1f] and reactive powers = [%0.1f, %0.1f, %0.1f] at '
           'resistive load' % (meas['p1_r'], meas['p2_r'], meas['p3_r'],
                               meas['q1_r'], meas['q2_r'], meas['q3_r']))
    ts.log('Active powers = [%0.1f, %0.1f, %0.1f] and reactive powers = [%0.1f, %0.1f, %0.1f] at '
           'capacitive load' % (meas['p1_c'], meas['p2_c'], meas['p3_c'],
                                meas['q1_c'], meas['q2_c'], meas['q3_c']))
    ts.log('Active powers = [%0.1f, %0.1f, %0.1f] and reactive powers = [%0.1f, %0.1f, %0.1f] at '
           'inductive load' % (meas['p1_l'], meas['p2_l'], meas['p3_l'],
                               meas['q1_l'], meas['q2_l'], meas['q3_l']))

    '''
    3) Open switch S3 and measure the time it takes for the EUT to cease to energize the island.
    This is the time from when S3 opens to when instantaneous voltage and EUT current in the
    island drops and remains below 0.05 p.u. Record this as the clearing time.
    '''
    # waveform OpWrite configured to capture when S3 is opened
    phil.set_params(model_name + '/SM_Source/Phase Angle Phase A0/Value', 0)  # open S3

    # Complete data capture
    ts.log('Waiting 10 seconds for Opal to save the waveform data.')
    ts.sleep(10)

    test_filename = 'PhaseJump_Test%s' % test_num
    ts.log('------------{}------------'.format(test_filename))

    # Convert and save the .mat file that contains the phase jump start
    ts.log('Processing waveform dataset(s)')
    ds = daq.waveform_capture_dataset()  # returns list of databases of waveforms (overloaded)
    ui_wave = '%s.csv' % test_filename
    ts.log('Saving file: %s' % ui_wave)
    ds[0].to_csv(ts.result_file_path(ui_wave))
    ts.result_file(ui_wave)

    # Values returned from RT-Lab analysis
    t_trip = 0.0
    freq = 60.  # todo: calculate fundamental frequency after S3 is open
    t_trips[q_inc] = t_trip  # append trip time in dict with reactive power increment value key

    '''
    If at any point at least three test instances show island frequency increasing above the
    fundamental frequency of the ac test source after S3 was opened and at least three instances
    show island frequency decreasing below the fundamental frequency of the ac test source after
    S3 was opened S3 was opened, the remaining 1% steps and step e)5) may be omitted.
    '''
    f_nom = ts.param_value('eut.f_nom')
    if freq > f_nom:
        high_freq_count += 1
    else:
        low_freq_count += 1

    # 'Test, Start Waveform, Reactive Power, Trip Time'
    result_summary.write('%s, %s, %s, %s\n' % (test_filename, ui_wave, q_inc, t_trip))

    return t_trips, t_trip, high_freq_count, low_freq_count

def test_run():

    result = script.RESULT_PASS
    phil = None
    daq = None
    pv = None
    eut = None
    result_summary = None
    dataset_filename = None
    ds = None
    result_params = None

    try:
        open_proj = ts.param_value('hil_config.open')
        compilation = ts.param_value('hil_config.compile')
        stop_sim = ts.param_value('hil_config.stop_sim')
        load = ts.param_value('hil_config.load')
        execute = ts.param_value('hil_config.execute')
        model_name = ts.param_value('hil_config.model_name')

        test_num = ts.param_value('phase_jump.test_num')
        n_iter = ts.param_value('phase_jump.n_iter')
        eut_startup_time = ts.param_value('phase_jump_startup.eut_startup_time')

        cat = ts.param_value('eut.cat')
        cat2 = ts.param_value('eut.cat2')
        p_rated = ts.param_value('eut.p_rated')
        var_rated = ts.param_value('eut.var_rated')
        s_rated = ts.param_value('eut.s_rated')
        phases = ts.param_value('eut.phases')

        '''
        a) Test circuit configuration:
        
            1) The test circuit shall be configured as shown in Figure 7 using only the number of phases
            required for EUT operation. The connection of the neutral conductor to the EUT is only
            required when the EUT has a neutral connection. If the EUT does not have an equipment
            ground connection, then GND is not required to be connected to the EUT. The neutral
            connection shall be unaffected by the operation of switch S3 or S2. Switches S2 and S3 shall
            be gang-operated and multi-pole. The grounding of the load and ac test source shall be
            unaffected by the position of switch S3. Switch S2 is not required but is permitted.
            
            2) Connect the EUT according to the instructions and specifications provided by the
            manufacturer. If the EUT manufacturer requires an external or separate transformer, the
            transformer is to be included in the test configuration between the EUT and RLC load
            components.
            
            3) The ac test source voltage is set to EUT nominal voltage ± 5% and nominal frequency.
        '''

        # initialize the hardware in the loop
        phil = hil.hil_init(ts)

        """
        A separate module has been create for the 1547.1 Standard
        """
        active_function = p1547.active_function(ts=ts, functions=['UI'], script_name='UI',
                                                criteria_mode=[False, False, False])
        ts.log_debug("1547.1 Library configured for %s" % active_function.get_script_name())

        # initialize the pv
        pv = pvsim.pvsim_init(ts)
        pv.power_on()
        ts.sleep(0.5)

        if phil is not None:
            ts.log("{}".format(phil.info()))
            if open_proj == 'Yes':
                phil.open()

        # initialize the das
        das_points = active_function.get_sc_points()
        daq = das.das_init(ts, sc_points=das_points['sc'], support_interfaces={'hil': phil, 'pvsim': pv})
        ts.sleep(0.5)

        # initialize the der
        if ts.param_value('der_iop.phases') == '1547-2018 Compliant':
            eut = der1547.der1547_init(ts)
        else:
            eut = der.der_init(ts)
        eut.config()
        ts.sleep(0.5)

        # result params
        result_params = active_function.get_rslt_param_plot()
        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write('Test, Start Waveform, Reactive Power, Trip Time\n')

        '''
        b) EUT settings:
            1) Commanded active power operating mode, as described in Table 12, shall be used for UI
            testing.
            
                                                 Table 12 - EUT active power modes
        |----------------------------------------------------------------------------------------------------------
        | EUT active-power mode     | Description
        |----------------------------------------------------------------------------------------------------------
        | Tracking                  | For EUT operating with an input power tracking capability, the input source
        |                           | power is adjusted so that the EUT operates at the desired EUT output power
        |                           | level.
        |----------------------------------------------------------------------------------------------------------
        | Commanded                 | In this case, the EUT is set to a commanded active output power level. The
        |                           | input source power shall be set capable of delivering at least 125% active
        |                           | power in case the EUT needs to increase output active power that may occur
        |                           | during these tests. If the EUT is not capable of operating at a specified power
        |                           | level, then it shall be operated at its closest nonzero power level capability.
        -----------------------------------------------------------------------------------------------------------
        '''
        pv.power(p_rated*1.25)

        '''
        
            2) These tests shall be run for each of the test cases shown in Table 13 or Table 14, depending
            upon EUT category. The power levels in the tables are listed on a per unit basis with a
            tolerance of ± 0.05 p.u. and are listed in the generator frame of reference. The PEUT, QEUT
            operating points of the EUT are chosen to be spread out over a range of the active and
            reactive power capabilities defined in 5.2 of IEEE Std 1547-2018.
            
            Test cases 7A and 8A as well as voltage-active power (VW) functions are not required for
            Category A equipment shown in Table 13. However, if the EUT does support those functions
            then they shall be included in the unintentional islanding testing.


                    Table 13 — Balanced load unintentional islanding test matrix for Category A
    |-------------------------------------------------------------------------------------------------------------------
    | Test | EUT power level (p.u.) | Reactive power mode    | Active power mode | Initial RLC load (p.u.) | Effective
    | case |                        |                        | settings          |                         | quality 
    |      |                        |                        |                   |                         | factor 
    |      | -----------------------------------------------------------------------------------------------------------
    |      | PEUT       | QEUT      | Mode/setting | Resp    | VW      | FW      | PR+PL+PC | QC   | QL    | QF
    |      |            |           |              | time    |         |         |          |      |       |
    |-------------------------------------------------------------------------------------------------------------------
    | 1A   | 1.00       | 0.00      | Constant PF  | n/a     | Default | Default |  –1.00   | 1.00 | –1.00 | 1.00
    |-------------------------------| p.f. = 1.00  |--------------------------------------------------------------------
    | 2A   | 0.50       | 0.00      |              | n/a     | Default | Default |  –0.50   | 0.50 | –0.50 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 3A   | 0.90       | –0.25     | p.f. = –0.96 | n/a     | Off     | LA      |  –0.90   | 0.90 | –0.65 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 4A   | 0.90       | 0.44      | p.f. = 0.90  | n/a     | Off     | LA      |  –0.90   | 0.46 | –0.90 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 5A   | 1.00       | 0.00      | VV MA        | 1       | MA      | MA      |  –1.00   | 1.00 | –1.00 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 6A   | 0.50       | 0.00      | VV Default   | 10      | MA      | MA      |  –0.50   | 0.50 | –0.50 | 1.00    
    |-------------------------------------------------------------------------------------------------------------------
    | 7A   | 0.50       | 0.00      | WV Default   | n/a     | MA      | MA      |  –0.50   | 0.50 | –0.50 | 1.00    
    |-------------------------------------------------------------------------------------------------------------------
    | 8A   | 1.00       | 0.00      | WV MA        | n/a     | MA      | MA      |  –1.00   | 1.00 | –1.00 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 9A   | 0.90       | –0.25     | Const Q=-0.25| n/a     | MA      | MA      |  –0.90   | 0.90 | –0.65 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 10A   | 0.50      | 0.44      | Const Q=0.44 | n/a     | MA      | MA      |  –0.50   | 0.06 | –0.50 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | NOTE—LA = least aggressive; MA = most aggressive. As indicated in Table 16 through Table 19.
    |-------------------------------------------------------------------------------------------------------------------
    | a (p.u.) is per unit of the EUT kVA rating.
    | b Effective quality factor is provided for information only to help readers compare these test requirements with 
    | earlier versions of this standard. See Annex D for details.
    |-------------------------------------------------------------------------------------------------------------------

        '''
        cat_a_tests = {'1A': {'p_eut': 1., 'q_eut': 0., 'pf': 1., 'vv': None, 'wv': None, 'q_fixed': None,
                              't_resp': None, 'vw': 'default', 'fw': 'default',
                              'pr_pl_pc': -1., 'qc': 1., 'ql': -1., 'qf': 1.},
                       '2A': {'p_eut': 0.5, 'q_eut': 0., 'pf': 1., 'vv': None, 'wv': None, 'q_fixed': None,
                              't_resp': None, 'vw': 'default', 'fw': 'default',
                              'pr_pl_pc': -0.5, 'qc': 0.5, 'ql': -0.5, 'qf': 1.},
                       }  # todo: complete other tests

        '''

                    Table 13 — Balanced load unintentional islanding test matrix for Category B
    |-------------------------------------------------------------------------------------------------------------------
    | Test | EUT power level (p.u.) | Reactive power mode    | Active power mode | Initial RLC load (p.u.) | Effective
    | case |                        |                        | settings          |                         | quality 
    |      |                        |                        |                   |                         | factor 
    |      | -----------------------------------------------------------------------------------------------------------
    |      | PEUT       | QEUT      | Mode/setting | Resp    | VW      | FW      | PR+PL+PC | QC   | QL    | QF
    |      |            |           |              | time    |         |         |          |      |       |
    |-------------------------------------------------------------------------------------------------------------------
    | 1B   | 1.00       | 0.00      | p.f. = 1.00  | n/a     | Default | Default |  –1.00   | 1.00 | –1.00 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 2B   | 0.50       | 0.00      | p.f. = 1.00  | n/a     | Default | Default |  –0.50   | 0.50 | –0.50 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 3B   | 0.90       | –0.25     | p.f. = –0.90 | n/a     | Off     | LA      |  –0.90   | 0.90 | –0.46 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 4B   | 0.90       | 0.44      | p.f. = 0.90  | n/a     | Off     | LA      |  –0.90   | 0.46 | –0.90 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 5B   | 1.00       | 0.00      | VV MA        | 1       | MA      | MA      |  –1.00   | 1.00 | –1.00 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 6B   | 0.50       | 0.00      | VV Default   | 10      | MA      | MA      |  –0.50   | 0.50 | –0.50 | 1.00    
    |-------------------------------------------------------------------------------------------------------------------
    | 7B   | 0.50       | 0.00      | WV Default   | n/a     | MA      | MA      |  –0.50   | 0.50 | –0.50 | 1.00    
    |-------------------------------------------------------------------------------------------------------------------
    | 8B   | 1.00       | 0.00      | WV MA        | n/a     | MA      | MA      |  –1.00   | 1.00 | –1.00 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 9B   | 0.50       | –0.44     | Const Q=-0.44| n/a     | MA      | MA      |  –0.90   | 0.50 | –0.06 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | 10B   | 0.50      | 0.44      | Const Q=0.44 | n/a     | MA      | MA      |  –0.50   | 0.06 | –0.50 | 1.00
    |-------------------------------------------------------------------------------------------------------------------
    | NOTE—LA = least aggressive; MA = most aggressive. As indicated in Table 16 through Table 19.
    |-------------------------------------------------------------------------------------------------------------------
    | a (p.u.) is per unit of the EUT kVA rating.
    | b Effective quality factor is provided for information only to help readers compare these test requirements with 
    | earlier versions of this standard. See Annex D for details.
    |-------------------------------------------------------------------------------------------------------------------
        '''

        cat_b_tests = {'1B': {'p_eut': 1., 'q_eut': 0., 'pf': 1., 'vv': None, 'wv': None, 'q_fixed': None,
                              't_resp': None, 'vw': 'default', 'fw': 'default',
                              'pr_pl_pc': -1., 'qc': 1., 'ql': -1., 'qf': 1.},
                       '2B': {'p_eut': 0.5, 'q_eut': 0., 'pf': 1., 'vv': None, 'wv': None, 'q_fixed': None,
                              't_resp': None, 'vw': 'default', 'fw': 'default',
                              'pr_pl_pc': -0.5, 'qc': 0.5, 'ql': -0.5, 'qf': 1.},
                       }  # todo: complete other tests

        '''
        c) Establish a balanced load condition for each test case.
        
        Operate the EUT and adjust the RLC load components so that active, PS3, and reactive, QS3, power
        flow through each phase measured at switch S3 is less than 2% of the EUT rated power on a
        steady-state basis. Initial settings of the EUT and RLC load components for each test case are
        shown in Table 13 and Table 14. These settings are sufficient to get close to the balanced power
        requirement, and the EUT settings are not further adjusted. The RLC load components are then
        adjusted to achieve a balance between generation and load active and reactive powers such that the
        following two conditions are met:
                    ǀPS3ǀ = ǀPEUT + PR + PC + PLǀ <= 0.02 p.u.
                    ǀQS3ǀ = ǀQEUT + QR + QC + QLǀ <= 0.02 p.u.
        
        Multiphase voltages shall be balanced to within 5% of each other.
        
        AC test source voltage and/or frequency and EUT power may be adjusted to meet the power
        balance requirements so long as the resulting EUT power levels remain within 0.05 p.u. of the
        values in Table 13 or Table 14. The order in which adjustments are made is not specified in this
        procedure.
        
        '''

        if compilation == 'Yes':
            ts.sleep(1)
            ts.log("    Model ID: {}".format(phil.compile_model().get("modelId")))
        if stop_sim == 'Yes':
            ts.sleep(1)
            ts.log("    {}".format(phil.stop_simulation()))

        ts.log('Stop time set to %s' % phil.set_stop_time(1000.))

        if load == 'Yes':
            ts.sleep(1)
            ts.log("    {}".format(phil.load_model_on_hil()))
        if execute == 'Yes':
            ts.log("    {}".format(phil.start_simulation()))
            daq.data_capture(True)  # Start RMS data capture

        # get PS3 and QS3
        daq.data_sample()
        meas = daq.data_read()
        ps3_pu = meas['PS3']/p_rated
        qs3_pu = meas['QS3']/s_rated

        while -0.02 < ps3_pu > 0.02 or -0.02 < qs3_pu > 0.02:  # tune RLC to get target P/Q levels through switch 3
            # calculations to determine RLC adjustments
            r, l, c = find_rlc()
            ts.log('Setting R = %0.3f Ohms, L = %0.3f Ohms, C = %0.3f Ohms...' % (r, l, c))

            parameters = []
            # Phase A RLC
            parameters.append((model_name + '/SM_Source/Switch1/Threshold', r))
            parameters.append((model_name + '/SM_Source/Switch2/Threshold', l))
            parameters.append((model_name + '/SM_Source/Phase Angle Phase A0/Value', c))
            # Phase B RLC
            parameters.append((model_name + '/SM_Source/Switch1/Threshold', r))
            parameters.append((model_name + '/SM_Source/Switch2/Threshold', l))
            parameters.append((model_name + '/SM_Source/Phase Angle Phase A0/Value', c))
            # Phase C RLC
            parameters.append((model_name + '/SM_Source/Switch1/Threshold', r))
            parameters.append((model_name + '/SM_Source/Switch2/Threshold', l))
            parameters.append((model_name + '/SM_Source/Phase Angle Phase A0/Value', c))

            for p, v in parameters:
                ts.log_debug('Setting %s = %s' % (p, v))
                phil.set_params(p, v)

            ts.sleep(2)  # wait to see how changes affect P/Q

            # get PS3 and QS3
            daq.data_sample()
            meas = daq.data_read()
            ps3_pu = meas['PS3'] / p_rated
            qs3_pu = meas['QS3'] / s_rated

            # todo: verify the voltage are within 5% of each other

        '''
        d) Verify the test setup can sustain an island.
        
        1) Disable the unintentional islanding protection in the EUT.
        '''
        ts.log('This EUT supports the following Unintentional Islanding modes: %s' %
               eut.get_ui()['ui_capability_er'])
        ts.log('Disabling the UI on EUT for Step D.1.')
        eut.set_ui(params={'ui_mode_enable_as': False})

        '''
        2) Operate the EUT and RLC load under the conditions established in step c) for any one of the
        test cases in Table 13 or Table 14 as appropriate for the EUT Category.
        3) With the EUT and load operating at stable conditions, record the voltage and current at switch
        S3. Record the active and reactive power at switch S3, switch S2, the resistive load, the
        capacitive load and the inductive load on a net and per phase basis.
        '''
        ts.sleep(2.)
        daq.data_sample()
        meas = daq.data_read()
        ts.log('Voltages = [%0.1f, %0.1f, %0.1f] and currents = [%0.1f, %0.1f, %0.1f] at switch S3' %
               (meas['v1_s3'], meas['v2_s3'], meas['v3_s3'], meas['i1_s3'], meas['i2_s3'], meas['i3_s3']))
        ts.log('Active powers = [%0.1f, %0.1f, %0.1f] and reactive powers = [%0.1f, %0.1f, %0.1f] at switch S3' %
               (meas['p1_s3'], meas['p2_s3'], meas['p3_s3'], meas['q1_s3'], meas['q2_s3'], meas['q3_s3']))
        ts.log('Active powers = [%0.1f, %0.1f, %0.1f] and reactive powers = [%0.1f, %0.1f, %0.1f] at switch S2' %
               (meas['p1_s2'], meas['p2_s2'], meas['p3_s2'], meas['q1_s2'], meas['q2_s2'], meas['q3_s2']))
        ts.log('Active powers = [%0.1f, %0.1f, %0.1f] and reactive powers = [%0.1f, %0.1f, %0.1f] at resistive load'
               % (meas['p1_r'], meas['p2_r'], meas['p3_r'], meas['q1_r'], meas['q2_r'], meas['q3_r']))
        ts.log('Active powers = [%0.1f, %0.1f, %0.1f] and reactive powers = [%0.1f, %0.1f, %0.1f] at capacitive '
               'load' % (meas['p1_c'], meas['p2_c'], meas['p3_c'], meas['q1_c'], meas['q2_c'], meas['q3_c']))
        ts.log('Active powers = [%0.1f, %0.1f, %0.1f] and reactive powers = [%0.1f, %0.1f, %0.1f] at inductive '
               'load' % (meas['p1_l'], meas['p2_l'], meas['p3_l'], meas['q1_l'], meas['q2_l'], meas['q3_l']))

        '''
        4) Open switch S3. If, after 10 s, the island circuit remains energized, the test setup is considered
        verified. Measure and record the voltage and frequency of the islanding operation.
        '''
        phil.set_params(model_name + '/SM_Source/Phase Angle Phase A0/Value', c)  # open S3
        ts.sleep(10.)
        daq.data_sample()
        meas = daq.data_read()
        ts.log('Voltage = [%0.1f, %0.1f, %0.1f] and frequency = [%0.1f, %0.1f, %0.1f] of island.'
               'load' % (meas['AC_V1'], meas['AC_V2'], meas['AC_V3'], meas['AC_V1'], meas['q2_l'], meas['q3_l']))
        '''
        5) De-energize the island.
        '''
        # phil.stop_simulation()
        eut.set_p_lim(params={'p_lim_mode_enable_as': True, 'p_lim_dbof_as': 0.0})

        '''
        6) Enable the unintentional islanding protection in the EUT.
        '''
        eut.set_ui(params={'ui_mode_enable_as': True})
        ts.log('EUT settings: %s' % eut.get_ui())
        eut.set_p_lim(params={'p_lim_mode_enable_as': True, 'p_lim_dbof_as': 100.})

        '''
        e) Clearing time tests.
        
        1) Operate the EUT and load under the conditions established in step c) for each one of the test
        cases in Table 13 or Table 14 as appropriate for the EUT Category.
        '''

        for test_number in test_num:
            if cat == 'CAT_A':
                test = test_number + 'A'
                test_params = cat_a_tests[test]
            else:
                test = test_number + 'B'
                test_params = cat_b_tests[test]

            '''
            Table 15 shows the voltage and frequency trip levels and clearing time settings to be used for the
            unintentional islanding tests. If the EUT is capable of operating at wider voltage and frequency trip
            settings, then such settings shall be used. The EUT may have additional voltage and frequency trip
            settings for self-protection, and such settings may remain enabled in the EUT.
        
                    Table 15 —Voltage and frequency trip settings for unintentional islanding testing
        |--------------------------------------------------------------------------------------------------------
        | Trip           |             Category I and Category II       |            Category III               |
        | Function       | Voltage (p.u.)       | Clearing time (s)     | Voltage (p.u.) | Clearing time (s)    |
        ---------------------------------------------------------------------------------------------------------
            OV2                 1.2                     0.16                    1.2                 0.16
            OV1                 1.2                     13                      1.2                 13
            UV1                 0                       21                      0                   50
            UV2                 0                       2                       0                   21
        ---------------------------------------------------------------------------------------------------------
                           Frequency (Hz)      Clearing time (s)       Frequency (Hz)          Clearing time (s)
            OF2                 66                      1000                    66                  1000
            OF1                 66                      1000                    66                  1000
            UF1                 50                      1000                    50                  1000
            UF2                 50                      1000                    50                  1000
        ---------------------------------------------------------------------------------------------------------
            '''
            if cat2 == 'CAT_I' or cat2 == 'CAT_II':
                eut.set_ov(params={'ov_trip_v_pts_as': [1.2, 1.2], 'ov_trip_t_pts_as': [0.16, 13]})
                eut.set_uv(params={'uv_trip_v_pts_as': [0., 0.], 'uv_trip_t_pts_as': [21, 2]})
                eut.set_of(params={'of_trip_f_pts_as': [66., 66.], 'of_trip_t_pts_as': [1000, 1000]})
                eut.set_uf(params={'uf_trip_f_pts_as': [50., 50.], 'uf_trip_t_pts_as': [1000, 1000]})
            else:
                eut.set_ov(params={'ov_trip_v_pts_as': [1.2, 1.2], 'ov_trip_t_pts_as': [0.16, 13]})
                eut.set_uv(params={'uv_trip_v_pts_as': [0., 0.], 'uv_trip_t_pts_as': [50, 21]})
                eut.set_of(params={'of_trip_f_pts_as': [66., 66.], 'of_trip_t_pts_as': [1000, 1000]})
                eut.set_uf(params={'uf_trip_f_pts_as': [50., 50.], 'uf_trip_t_pts_as': [1000, 1000]})

            '''
            Table 16 shows the most aggressive settings for the voltage–active power function to be used in
            these tests. The P2 setting is intentionally set to a low but nonzero value so that the tester can
            differentiate between when the unit stops operating due to unintentional islanding operation versus
            power being reduced to zero due to this function response. Testing of a storage system configured
            with these settings is applicable to this type test.
            
            Table 16 — Voltage–active power (VW) settings for unintentional islanding testing
            |-------------------------------------------------------------------------------
            | Setting        |             Most aggressive       |            Default      |
            --------------------------------------------------------------------------------
                                                         Voltage (p.u.)                    
                 V1                             1.05                            1.06
                 V2                             1.06                            1.10
            --------------------------------------------------------------------------------
                                                         Active power (p.u.)
                 P1                             1.0                             1.0
                 P2                             0.2                             0.2
            --------------------------------------------------------------------------------
                                                         Response time (s)
            Open Loop Response Time             0.5                             10
            --------------------------------------------------------------------------------
            '''
            if test_params['vw'] == 'default':
                eut.set_pv(params={'pv_mode_enable_as': True, 'pv_curve_v_pts_as': [1.06, 1.10],
                                   'pv_curve_p_pts_as': [1., 0.2], 'pv_olrt_as': 10.})
            elif test_params['vw'] == 'ma':
                eut.set_pv(params={'pv_mode_enable_as': True, 'pv_curve_v_pts_as': [1.05, 1.06],
                                   'pv_curve_p_pts_as': [1., 0.2], 'pv_olrt_as': 0.5})
            else:
                eut.set_pv(params={'pv_mode_enable_as': False})

            '''
            Table 17 shows the settings for the voltage-reactive power function to be used in these tests. The
            autonomously adjusted reference voltage (VRef) capability of the DER is not enabled for this testing
            since the fastest time constant is 300 s, far longer than any response that would affect unintentional
            islanding operation. The values in this table are for VRef = 1.00 p.u. VRef may be adjusted during the
            power balance setup of the test, as needed, so that the testing is started in the center of the VV
            curve. If the EUT has a wider range of capability than the settings in Table 17, such wider settings
            may be used.
            
            Table 17 — Voltage–reactive power (VV) settings for unintentional islanding testing Setting Category A
            |-------------------------------------------------------------------------------------------------
            | Setting           |                  Category A          |                 Category B             |
            |                   | Most aggressive      | Default       | Most aggressive      | Default         |
            --------------------------------------------------------------------------------------------------
                                                         Voltage (p.u.)                    
            | V1                | 0.98                 | 0.9           | 0.98                  | 0.92           
            | V2                | 1.00                 | 1.0           | 1.00                  | 0.98           
            | V3                | 1.00                 | 1.0           | 1.00                  | 1.02          
            | V4                | 1.02                 | 1.1           | 1.02                  | 1.08           
            --------------------------------------------------------------------------------------------------
                                                         Reactive power (p.u.)
            | Q1                | 0.25                 | 0.25           | 0.44                  | 0.44           
            | Q2                | 0.00                 | 0              | 0                     | 0   
            | Q3                | 0.00                 | 0              | 0                     | 0   
            | Q4                | -0.25                | -0.25          | -0.44                 | -0.44     
            --------------------------------------------------------------------------------------------------
                                                         Response time (s)
            Open Loop Rsp Time  | 1.00                 | 10            | 1                     | 5        
            --------------------------------------------------------------------------------
            '''
            if cat == 'CAT_A':
                if test_params['vv'] == 'default':
                    eut.set_qv(params={'qv_mode_enable_as': True, 'qv_vref_as': 1., 'qv_vref_auto_mode_as': 'Off',
                                       'qv_curve_v_pts': [0.9, 1., 1., 1.1],
                                       'qv_curve_q_pts': [0.25, 0., 0., -0.25], 'qv_olrt_as': 10.})
                elif test_params['vv'] == 'ma':
                    eut.set_qv(params={'qv_mode_enable_as': True, 'qv_vref_as': 1., 'qv_vref_auto_mode_as': 'Off',
                                       'qv_curve_v_pts': [0.98, 1., 1., 1.02],
                                       'qv_curve_q_pts': [0.25, 0., 0., -0.25], 'qv_olrt_as': 1.})
                else:
                    eut.set_qv(params={'qv_mode_enable_as': False})
            else:
                if test_params['vv'] == 'default':
                    eut.set_qv(params={'qv_mode_enable_as': True, 'qv_vref_as': 1., 'qv_vref_auto_mode_as': 'Off',
                                       'qv_curve_v_pts': [0.92, 0.98, 1.02, 1.08],
                                       'qv_curve_q_pts': [0.44, 0., 0., -0.44], 'qv_olrt_as': 5.})
                elif test_params['vv'] == 'ma':
                    eut.set_qv(params={'qv_mode_enable_as': True, 'qv_vref_as': 1., 'qv_vref_auto_mode_as': 'Off',
                                       'qv_curve_v_pts': [0.98, 1., 1., 1.02],
                                       'qv_curve_q_pts': [0.44, 0., 0., -0.44], 'qv_olrt_as': 1.})
                else:
                    eut.set_qv(params={'qv_mode_enable_as': False})

            '''
        
            Table 18 shows the settings for the active power-reactive power function to be used in these tests.
            
                                    Table 18 — Active power–reactive power settings
            |-------------------------------------------------------------------------------------------------
            | Setting           |                  Category A          |                 Category B             |
            |                   | Most aggressive      | Default       | Most aggressive      | Default         |
            --------------------------------------------------------------------------------------------------
                                                         Active power (p.u.)                    
            | P1                | 0.2                  | 0.2           | 0.2                  | 0.2          
            | P2                | 0.8                  | 0.5           | 0.9                  | 0.5          
            | P3                | 0.9                  | 1.0           | 1.0                  | 1.0    
            |-------------------------------------------------------------------------------------------------
                                                         Reactive power (p.u.)
            | Q1                | 0.44                 | 0.0           | 0.44                 | 0.0           
            | Q1                | 0.44                 | 0.0           | 0.44                 | 0.0           
            | Q1                | -0.25                | -0.25         | -0.44                | -0.44           
            |-------------------------------------------------------------------------------------------------
            
            '''
            if cat == 'CAT_A':
                if test_params['wv'] == 'default':
                    eut.set_qp(params={'qp_mode_enable_as': True, 'qp_curve_p_gen_pts_as': [0.2, 0.5, 1.0],
                                       'qp_curve_q_gen_pts_as': [0., 0., -0.25]})
                elif test_params['wv'] == 'ma':
                    eut.set_qp(params={'qp_mode_enable_as': True, 'qp_curve_p_gen_pts_as': [0.2, 0.8, 0.9],
                                       'qp_curve_q_gen_pts_as': [0.44, 0.44, -0.25]})
                else:
                    eut.set_pv(params={'qp_mode_enable_as': False})
            else:
                if test_params['wv'] == 'default':
                    eut.set_qp(params={'qp_mode_enable_as': True, 'qp_curve_p_gen_pts_as': [0.2, 0.5, 1.0],
                                       'qp_curve_q_gen_pts_as': [0., 0., -0.44]})
                elif test_params['wv'] == 'ma':
                    eut.set_qp(params={'qp_mode_enable_as': True, 'qp_curve_p_gen_pts_as': [0.2, 0.9, 1.0],
                                       'qp_curve_q_gen_pts_as': [0.44, 0.44, -0.44]})
                else:
                    eut.set_qp(params={'qp_mode_enable_as': False})

            '''
            Table 19 shows the settings for the frequency-droop function to be used in these tests. Least
            aggressive, default, and most aggressive settings are used in the test matrix in Table 13 and Table
            14.
            
                            Table 19 —Frequency-droop (FW) settings for unintentional islanding testing
        |---------------------------------------------------------------------------------------------------------------
        | Setting        |             Category I and Category II       |            Category III               
        |                | Least aggressive | Default | Most aggressive | Least aggressive | Default | Most aggressive 
        ----------------------------------------------------------------------------------------------------------------
            dbOF, dbUF          1.0            0.036        0.017               1.0         0.036       0.017
            kOF, kUF            0.05            0.05        0.03                0.05        0.05        0.02
            T_response (s)      0               5             1                 10          5           0.2
        ----------------------------------------------------------------------------------------------------------------
            '''
            if cat2 == 'CAT_I' or cat2 == 'CAT_II':
                if test_params['fw'] == 'la':
                    eut.set_pf(params={'pf_mode_enable_as': True, 'pf_dbof_as': 1.0, 'pf_dbuf_as': 1.0,
                                       'pf_kof_as': 0.05, 'pf_kuf_as': 0.05, 'pf_olrt_as': 0.})
                elif test_params['fw'] == 'default':
                    eut.set_pf(params={'pf_mode_enable_as': True, 'pf_dbof_as': 0.036, 'pf_dbuf_as': 0.036,
                                       'pf_kof_as': 0.05, 'pf_kuf_as': 0.05, 'pf_olrt_as': 5.})
                else:  # ma
                    eut.set_pf(params={'pf_mode_enable_as': True, 'pf_dbof_as': 0.017, 'pf_dbuf_as': 0.017,
                                       'pf_kof_as': 0.03, 'pf_kuf_as': 0.03, 'pf_olrt_as': 1.})
            else:
                if test_params['fw'] == 'la':
                    eut.set_pf(params={'pf_mode_enable_as': True, 'pf_dbof_as': 1.0, 'pf_dbuf_as': 1.0,
                                       'pf_kof_as': 0.05, 'pf_kuf_as': 0.05, 'pf_olrt_as': 10.})
                elif test_params['fw'] == 'default':
                    eut.set_pf(params={'pf_mode_enable_as': True, 'pf_dbof_as': 0.036, 'pf_dbuf_as': 0.036,
                                       'pf_kof_as': 0.05, 'pf_kuf_as': 0.05, 'pf_olrt_as': 5.})
                else:  # ma
                    eut.set_pf(params={'pf_mode_enable_as': True, 'pf_dbof_as': 0.017, 'pf_dbuf_as': 0.017,
                                       'pf_kof_as': 0.02, 'pf_kuf_as': 0.02, 'pf_olrt_as': 0.2})

            '''
            d)4) The test is to be repeated with the reactive load (either capacitive or inductive) adjusted in 1%
            increments from 95% to 105% of the initial balanced load value determined in step c). 
            '''
            # This requires clearing times be calculated while the script is running.  It is suggested that this
            # be completed with logic in the RT-Lab simulation

            eut.set_p_lim(params={'p_lim_mode_enable_as': True, 'p_lim_dbof_as': 0.})  # de-energize island
            ts.log_sleep(2.)  # wait
            phil.set_params(model_name + '/SM_Source/Phase Angle Phase A0/Value', c)  # close S3

            counter = 0
            high_freq_count = 0
            low_freq_count = 0
            t_trips = {}
            for q_inc in [1.0, 0.99, 0.98, 0.97, 0.96, 0.95, 1.01, 1.02, 1.03, 1.04, 1.05]:
                counter += 1
                t_trips, t_trip, high_freq_count, low_freq_count = \
                    run_ui_test(phil, model_name, daq, test_num, t_trips, q_inc, high_freq_count,
                                low_freq_count, result_summary, c)

                ''' 
                d)4) If clearing times are still increasing at the 95% or 105% points, additional 1% increments 
                shall be taken until clearing times begin decreasing.
                '''
                min_unreached = True
                q_min = 0.95
                while min_unreached:
                    if q_inc == q_min:
                        if t_trip > t_trips[round(q_min+0.01, 2)]:  # must run a lower q_inc test
                            counter += 1
                            t_trips, t_trip, high_freq_count, low_freq_count = \
                                run_ui_test(phil, model_name, daq, test_num, t_trips, q_min, high_freq_count,
                                            low_freq_count, result_summary, c)
                            if t_trip < t_trips[round(q_min, 2)]:
                                min_unreached = False
                            else:
                                q_min -= 0.01
                    else:
                        break

                max_unreached = True
                q_max = 1.05
                while max_unreached:
                    if q_inc == q_max:
                        if t_trip > t_trips[round(q_min+0.01, 2)]:  # must run a lower q_inc test
                            counter += 1
                            t_trips, t_trip, high_freq_count, low_freq_count = \
                                run_ui_test(phil, model_name, daq, test_num, t_trips, q_max, high_freq_count,
                                            low_freq_count, result_summary, c)
                            if t_trip < t_trips[round(q_min, 2)]:
                                max_unreached = False
                            else:
                                q_min -= 0.01
                    else:
                        break

            '''
            5) After reviewing the results of the previous step, the 1% setting increments that yielded the
            three longest clearing times shall be subjected to two additional test iterations. If the three
            longest clearing times occur at nonconsecutive 1% load setting increments, the additional two
            iterations shall be run for all load settings in between.
            '''
            t_trips_sorted = [(q, t) for q, t in sorted(t_trips.items(), key=lambda item: item[1])]
            q_repeats = t_trips_sorted[0:2][0]

            for q_inc in q_repeats:
                counter += 1
                t_trips, t_trip, high_freq_count, low_freq_count = \
                    run_ui_test(phil, model_name, daq, test_num, t_trips, q_inc, high_freq_count,
                                low_freq_count, result_summary, c)

            daq.data_capture(False)

            ts.log('Sampling RMS complete')
            rms_dataset_filename = test_num + "_RMS.csv"
            ds = daq.data_capture_dataset()
            ts.log('Saving file: %s' % rms_dataset_filename)
            ds.to_csv(ts.result_file_path(rms_dataset_filename))
            # lib_1547 = p1547.module_1547(ts=ts, aif='VV', imbalance_angle_fix=imbalance_fix)
            # ts.log_debug('1547.1 Library configured for %s' % lib_1547.get_test_name())
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
    finally:
        if phil is not None:
            if phil.model_state() == 'Model Running':
                phil.stop_simulation()
            phil.close()
        if daq is not None:
            daq.close()
        if pv is not None:
            pv.close()
        if eut is not None:
            eut.close()
        # if dataset_filename is not None and ds is not None and result_params is not None:
        #     ts.log('Saving file: %s' % dataset_filename)
        #     ds.to_csv(ts.result_file_path(dataset_filename))
        #     ts.result_file(dataset_filename, params=result_params)
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

        ts.svp_version(required='1.5.9')

        result = test_run()

        ts.result(result)
        if result == script.RESULT_FAIL:
            rc = 1

    except Exception as e:
        ts.log_error('Test script exception: %s' % traceback.format_exc())
        rc = 1

    sys.exit(rc)


info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.0.0')
# Data acquisition
info.param_group('hil_config', label='HIL Configuration')
info.param('hil_config.open', label='Open Project?', default="Yes", values=["Yes", "No"])
info.param('hil_config.compile', label='Compilation needed?', default="Yes", values=["Yes", "No"])
info.param('hil_config.stop_sim', label='Stop the simulation before loading/execution?',
           default="Yes", values=["Yes", "No"])
info.param('hil_config.load', label='Load the model to target?', default="Yes", values=["Yes", "No"])
info.param('hil_config.execute', label='Execute the model on target?', default="Yes", values=["Yes", "No"])
info.param('hil_config.model_name', label='Model Name', default="Phase_Jump_A_B_A")

info.param_group('phase_jump', label='IEEE 1547.1 Phase Jump Configuration')
info.param('phase_jump.test_num', label='Test Number (1-5)', default=1)
info.param('phase_jump.n_iter', label='Number of Iterations', default=5)
info.param_group('phase_jump_startup', label='IEEE 1547.1 Phase Jump Startup Time', glob=True)
info.param('phase_jump_startup.eut_startup_time', label='EUT Startup Time (s)', default=85, glob=True)

info.param_group('eut', label='EUT Parameters', glob=True)
info.param('eut.phases', label='Phases', default='Single Phase', values=['Single phase', 'Split phase', 'Three phase'])
info.param('eut.cat', label='Alphabetic Category', default='CAT_A', values=['CAT_A', 'CAT_B'])
info.param('eut.cat2', label='Numeric Category', default='CAT_I', values=['CAT_I', 'CAT_II', 'CAT_III'])
info.param('eut.f_nom', label='Nominal frequency (Hz)', default=60.0)
# info.param('eut.s_rated', label='Apparent power rating (VA)', default=10000.0)
# info.param('eut.p_rated', label='Output power rating (W)', default=8000.0)
# info.param('eut.p_min', label='Minimum Power Rating(W)', default=1000.)
# info.param('eut.var_rated', label='Output var rating (vars)', default=2000.0)


hil.params(info)
das.params(info)
pvsim.params(info)
info.param_group('der_iop', label='Communication Interface', glob=True)
info.param('der_iop.phases', label='1547-Compliance', default='Nonclompliant',
           values=['Nonclompliant', '1547-2018 Compliant'])
der.params(info)
der1547.params(info)


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



