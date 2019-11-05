<scriptConfig name="VW_IMBALANCE_FIX" script="VW">
  <params>
    <param name="vw.test_1_tr" type="float">10.0</param>
    <param name="eut.v_low" type="float">108.0</param>
    <param name="eut.v_nom" type="float">120.0</param>
    <param name="eut.v_high" type="float">132.0</param>
    <param name="eut.v_in_nom" type="int">400</param>
    <param name="eut.p_min" type="float">1000.0</param>
    <param name="eut.var_rated" type="float">2000.0</param>
    <param name="eut.p_rated" type="float">10000.0</param>
    <param name="eut.s_rated" type="float">10000.0</param>
    <param name="pvsim.mode" type="string">Disabled</param>
    <param name="hil.mode" type="string">Disabled</param>
    <param name="gridsim.mode" type="string">Disabled</param>
    <param name="das.mode" type="string">Disabled</param>
    <param name="eut.imbalance_resp_3" type="string">Disabled</param>
    <param name="eut.imbalance_resp_1" type="string">Disabled</param>
    <param name="der.mode" type="string">Disabled</param>
    <param name="gridsim.auto_config" type="string">Disabled</param>
    <param name="vw.test_1" type="string">Enabled</param>
    <param name="eut.imbalance_resp_2" type="string">Enabled</param>
    <param name="vw.mode" type="string">Imbalanced grid</param>
    <param name="eut_vw.sink_power" type="string">No</param>
    <param name="eut.phases" type="string">Three phase</param>
    <param name="vw.imbalance_fix" type="string">Yes</param>
  </params>
</scriptConfig>
