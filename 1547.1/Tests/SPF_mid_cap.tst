<scriptConfig name="SPF_mid_cap" script="SA12_power_factor">
  <params>
    <param name="eut.pf_min_ind" type="float">-0.85</param>
    <param name="eut.pf_min_cap" type="float">0.85</param>
    <param name="eut.pf_settling_time" type="int">1</param>
    <param name="spf.n_r" type="int">3</param>
    <param name="eut.pf_msa" type="float">5.0</param>
    <param name="eut.p_rated" type="int">5000</param>
    <param name="spf.pf_min_cap" type="string">Disabled</param>
    <param name="pvsim.mode" type="string">Disabled</param>
    <param name="spf.pf_min_ind" type="string">Disabled</param>
    <param name="gridsim.mode" type="string">Disabled</param>
    <param name="der.mode" type="string">Disabled</param>
    <param name="spf.pf_mid_ind" type="string">Disabled</param>
    <param name="loadsim.mode" type="string">Disabled</param>
    <param name="gridsim.auto_config" type="string">Disabled</param>
    <param name="das.mode" type="string">Disabled</param>
    <param name="spf.p_100" type="string">Enabled</param>
    <param name="spf.p_50" type="string">Enabled</param>
    <param name="spf.p_20" type="string">Enabled</param>
    <param name="spf.pf_mid_cap" type="string">Enabled</param>
    <param name="eut.phases" type="string">Single Phase</param>
  </params>
</scriptConfig>
