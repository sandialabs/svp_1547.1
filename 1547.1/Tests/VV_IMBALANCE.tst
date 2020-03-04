<scriptConfig name="VV_IMBALANCE" script="VV">
  <params>
    <param name="vv.test_1_t_r" type="float">10.0</param>
    <param name="eut.f_min" type="float">56.0</param>
    <param name="eut.f_nom" type="float">60.0</param>
    <param name="eut.f_max" type="float">66.0</param>
    <param name="eut.v_low" type="float">105.6</param>
    <param name="eut.v_nom" type="float">120.0</param>
    <param name="eut.v_high" type="float">130.2</param>
    <param name="eut.v_in_nom" type="int">400</param>
    <param name="eut.p_min" type="float">1000.0</param>
    <param name="eut.var_rated" type="float">4400.0</param>
    <param name="eut.p_rated" type="float">10000.0</param>
    <param name="eut.s_rated" type="float">10000.0</param>
    <param name="der.mode" type="string">Disabled</param>
    <param name="pvsim.mode" type="string">Disabled</param>
    <param name="hil.mode" type="string">Disabled</param>
    <param name="gridsim.mode" type="string">Disabled</param>
    <param name="gridsim.auto_config" type="string">Disabled</param>
    <param name="das.mode" type="string">Disabled</param>
    <param name="eut.imbalance_resp" type="string">EUT response to the average of the three-phase effective (RMS)</param>
    <param name="vv.test_1" type="string">Enabled</param>
    <param name="vv.mode" type="string">Imbalanced grid</param>
    <param name="eut.phases" type="string">Three phase</param>
    <param name="vv.imbalance_fix" type="string">std</param>
  </params>
</scriptConfig>
