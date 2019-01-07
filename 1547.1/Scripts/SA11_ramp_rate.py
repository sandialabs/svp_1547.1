"""
Copyright (c) 2017, Sandia National Labs and SunSpec Alliance
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
from svpelab import loadsim
from svpelab import hil
import result as rslt
import script

TRIP_WAIT_DELAY = 5
POWER_WAIT_DELAY = 5

'''
def test_pass_fail(i_target=None, ds=None):

    i_10 = i_target * .1
    i_90 = i_target * .9

    passfail = 'Fail'

    point = None
    trigger_data = []
    try:
        point = 'AC_IRMS_1'
        idx = ds.points.index(point)
        i_data = ds.data[idx]
        point = 'TRIGGER'
        idx = ds.points.index(point)
        trigger_data = ds.data[idx]
    except ValueError, e:
        ts.fail('Data point %s not in dataset' % (point))
    if len(trigger_data) <= 0:
        ts.fail('No data in dataset')

    for t in range(len(trigger_data)):
        if t
        if v_target[i] != 0:
            act = var[i]
            target = var_target[i]
            min = target - var_msa
            max = target + var_msa
            var_act.append(var[i])
            var_target.append(target)
            var_min.append(min)
            var_max.append(max)
            if act < min or act > max:
                passfail = 'Fail'

    return (passfail)
'''

def test_run():

    result = script.RESULT_FAIL
    grid = None
    load = None
    pv = None
    daq = None
    eut = None
    chil = None

    # result params
    result_params = {
        'plot.title': 'title_name',
        'plot.x.title': 'Time (secs)',
        'plot.x.points': 'TIME',
        'plot.y.points': 'AC_IRMS_1',
        'plot.y.title': 'Current (A)'
    }

    try:
        v_nom = ts.param_value('eut.v_nom')
        i_rated = ts.param_value('eut.i_rated')
        i_low = ts.param_value('eut.i_low')
        rr_up_min = ts.param_value('eut.rr_up_min')
        rr_up_max = ts.param_value('eut.rr_up_max')
        rr_msa = ts.param_value('eut.rr_msa')
        t_dwell = ts.param_value('eut.t_dwell')

        ramp_rates = []
        if ts.param_value('rr.rr_max') == 'Enabled':
            ramp_rates.append(rr_up_max)
        if ts.param_value('rr.rr_mid') == 'Enabled':
            ramp_rates.append((rr_up_min + rr_up_max)/2)
        if ts.param_value('rr.rr_min') == 'Enabled':
            ramp_rates.append(rr_up_min)

        soft_start = ts.param_value('rr.soft_start') == 'Enabled'
        n_r = ts.param_value('rr.n_r')
        v_trip = ts.param_value('rr.v_trip')
        t_reconnect = ts.param_value('rr.t_reconnect')

        p_low = i_low * v_nom
        p_rated = i_rated * v_nom

        '''
        Test assumes the following steps have been performed:
            - Connect the EUT according to test requirements.
            - Set all AC source parameters to the nominal operating conditions for the EUT.
            - Turn on the EUT and allow to reach steady state.
        '''

        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # grid simulator is initialized with test parameters and enabled
        grid = gridsim.gridsim_init(ts)

        # load simulator initialization
        load = loadsim.loadsim_init(ts)
        if load is not None:
            ts.log('Load device: %s' % load.info())

        # pv simulator is initialized with test parameters and enabled
        pv = pvsim.pvsim_init(ts)
        pv.power_set(p_low)
        pv.power_on()

        # initialize rms data acquisition
        daq = das.das_init(ts, 'das_rms')
        if daq is not None:
            ts.log('DAS RMS device: %s' % (daq.info()))

        # it is assumed the EUT is on
        eut = der.der_init(ts)
        if eut is not None:
            eut.config()

        if soft_start:
            test_label = 'ss'
        else:
            test_label = 'rr'

        # For each ramp rate test level in Table SA11.1
        for rr in ramp_rates:
            duration = 100/rr + (t_dwell * 2)

            if soft_start:
                # set soft start ramp rate
                if eut is not None:
                    eut.ramp_rates(params={'soft_start': rr * 100})
                    # eut.soft_start_ramp_rate(rr)
                sample_duration = duration + TRIP_WAIT_DELAY + t_reconnect
            else:
                # set normal ramp rate
                if eut is not None:
                    eut.ramp_rates(params={'ramp_rate': rr * 100})
                    # eut.ramp_rate(rr)
                sample_duration = duration + POWER_WAIT_DELAY

            for count in range(1, n_r + 1):
                if daq is not None:
                    ts.log('Starting data capture %s' % rr)
                    daq.data_capture(True)
                    ts.log('Waiting for 3 seconds to start test')
                    ts.sleep(3)
                if soft_start:
                    # set to trip voltage
                    v1, v2, v3 = grid.voltage()
                    v_trip_grid = (v1 * v_trip/100)
                    ts.log('Nominal voltage = %s' % v1)
                    ts.log('Setting voltage to trip voltage (%s V)' % v_trip_grid)
                    grid.voltage((v_trip_grid, v2, v3))
                    ts.log('Waiting %s seconds' % TRIP_WAIT_DELAY)
                    ts.sleep(TRIP_WAIT_DELAY)
                    ts.log('Setting voltage to original nominal voltage (%s V)' % v1)
                    grid.voltage((v1, v2, v3))
                else:
                    ts.log('Setting to low power threshold (%s W)' % p_low)
                    pv.power_set(p_low)
                    ts.log('Waiting for %s seconds' % POWER_WAIT_DELAY)
                    ts.sleep(POWER_WAIT_DELAY)

                ts.log('Ramp rate: %s%%/sec - iteration %s' % (rr, count))
                ts.log('Setting to I_rated: %s' % i_rated)
                pv.power_set(p_rated)
                ts.log('Sampling for %s seconds' % sample_duration)
                ts.sleep(sample_duration)
                if daq is not None:
                    # Increase available input power to I_rated
                    ts.log('Sampling complete')
                    daq.data_capture(False)
                    ds = daq.data_capture_dataset()

                    test_name = '%s_%s_%s' % (test_label, str(int(rr)), str(count))
                    filename = '%s.csv' % test_name
                    ds.to_csv(ts.result_file_path(filename))
                    result_params['plot.title'] = test_name
                    ts.result_file(filename, params=result_params)
                    ts.log('Saving data capture %s' % filename)

        result = script.RESULT_COMPLETE

    except script.ScriptFail, e:
        reason = str(e)
        if reason:
            ts.log_error(reason)
    finally:
        if eut is not None:
            eut.close()
        if grid is not None:
            grid.close()
        if load is not None:
            load.close()
        if pv is not None:
            pv.close()
        if daq is not None:
            daq.close()
        if chil is not None:
            chil.close()

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

info.param_group('rr', label='Test Parameters')
info.param('rr.rr_max', label='Maximum Ramp Rate Test', default='Enabled', values=['Disabled', 'Enabled'])
info.param('rr.rr_mid', label='Medium Ramp Rate Test', default='Enabled', values=['Disabled', 'Enabled'])
info.param('rr.rr_min', label='Minimum Ramp Rate Test', default='Enabled', values=['Disabled', 'Enabled'])
info.param('rr.n_r', label='Number of test repetitions', default=3)
info.param('rr.soft_start', label='Perform Soft Start', default='Disabled', values=['Disabled', 'Enabled'])
info.param('rr.v_trip', label='Trip Threshold (% V_nom)', default=140.0,
           active='rr.soft_start', active_value=['Enabled'])
info.param('rr.t_reconnect', label='Reconnect Time (secs)', default=600.0,
           active='rr.soft_start', active_value=['Enabled'])

info.param_group('eut', label='EUT Parameters', glob=True)
info.param('eut.v_nom', label='V_nom', default=120.0)
info.param('eut.i_rated', label='I_rated', default=10.0)
info.param('eut.i_low', label='I_low', default=1.0)
info.param('eut.rr_up_min', label='RR_up_min', default=20.0)
info.param('eut.rr_up_max', label='RR_up_max', default=100.0)
info.param('eut.t_dwell', label='T_dwell', default=5.0)
info.param('eut.rr_msa', label='RR_msa', default=5)

der.params(info)
das.params(info, 'das_rms', 'Data Acquisition (RMS)')
das.params(info, 'das_wf', 'Data Acquisition (Waveform)')
gridsim.params(info)
loadsim.params(info)
pvsim.params(info)

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


