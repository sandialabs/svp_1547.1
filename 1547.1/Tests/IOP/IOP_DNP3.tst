<scriptConfig name="IOP_DNP3" script="IOP">
  <params>
    <param name="der1547.dnp3.oid" type="int">1</param>
    <param name="eut.f_min" type="float">56.0</param>
    <param name="eut.f_nom" type="float">60.0</param>
    <param name="eut.f_max" type="float">66.0</param>
    <param name="der1547.dnp3.outstation_addr" type="int">100</param>
    <param name="der1547.dnp3.master_addr" type="int">101</param>
    <param name="der1547.dnp3.ipaddr" type="string">127.0.0.1</param>
    <param name="der1547.dnp3.out_ipaddr" type="string">127.0.0.1</param>
    <param name="eut.v_in_nom" type="int">400</param>
    <param name="eut.p_min" type="float">1000.0</param>
    <param name="der1547.dnp3.rid" type="int">1234</param>
    <param name="eut.v_low" type="float">7000.0</param>
    <param name="eut.v_nom" type="float">7200.0</param>
    <param name="eut.v_high" type="float">7400.0</param>
    <param name="der1547.dnp3.ipport" type="int">10000</param>
    <param name="der1547.dnp3.out_ipport" type="int">20000</param>
    <param name="eut.s_rated" type="float">10000000.0</param>
    <param name="eut.p_rated" type="float">10000000.0</param>
    <param name="eut.var_rated" type="float">10000000.0</param>
    <param name="der1547.dnp3.path_to_py" type="string">C:\Users\jjohns2\Documents\Projects2020\InteroperabilityTesting\EPRI DER Setup\SimController.py</param>
    <param name="der1547.dnp3.path_to_exe" type="string">C:\Users\jjohns2\Documents\Projects2020\InteroperabilityTesting\EPRI DER Setup\epri-der-sim-0.1.0.6\epri-der-sim-0.1.0.6\DERSimulator.exe</param>
    <param name="der1547.mode" type="string">DNP3</param>
    <param name="hil.mode" type="string">Disabled</param>
    <param name="das.mode" type="string">Disabled</param>
    <param name="pvsim.mode" type="string">Disabled</param>
    <param name="gridsim.mode" type="string">Disabled</param>
    <param name="gridsim.auto_config" type="string">Disabled</param>
    <param name="der1547.dnp3.sim_type" type="string">EPRI DER Simulator</param>
    <param name="eut.imbalance_resp" type="string">EUT response to the average of the three-phase effective (RMS)</param>
    <param name="iop_params.monitoring_test" type="string">No</param>
    <param name="der1547.dnp3.auto_config" type="string">No</param>
    <param name="der1547.dnp3.dbus_ena" type="string">No</param>
    <param name="der1547.dnp3.irr_csv" type="string">None</param>
    <param name="eut.phases" type="string">Three phase</param>
    <param name="iop_params.settings_test" type="string">Yes</param>
    <param name="der1547.dnp3.simulated_outstation" type="string">Yes</param>
  </params>
</scriptConfig>
