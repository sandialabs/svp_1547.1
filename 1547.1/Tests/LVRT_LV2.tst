<scriptConfig name="LVRT_LV2" script="SA9_volt_ride_through">
  <params>
    <param name="eut.t_msa" type="float">1.0</param>
    <param name="eut.v_msa" type="float">2.0</param>
    <param name="eut.vrt_t_dwell" type="int">5</param>
    <param name="vrt.n_r" type="int">5</param>
    <param name="vrt.t_hold" type="float">10.0</param>
    <param name="vrt.v_test" type="float">50.0</param>
    <param name="vrt.v_grid_min" type="float">100.0</param>
    <param name="vrt.v_grid_max" type="float">100.0</param>
    <param name="eut.v_nom" type="float">240.0</param>
    <param name="eut.p_rated" type="int">3000</param>
    <param name="der.mode" type="string">Disabled</param>
    <param name="pvsim.mode" type="string">Disabled</param>
    <param name="das_das_wf.mode" type="string">Disabled</param>
    <param name="das_das_rms.mode" type="string">Disabled</param>
    <param name="gridsim.mode" type="string">Disabled</param>
    <param name="loadsim.mode" type="string">Disabled</param>
    <param name="gridsim.auto_config" type="string">Disabled</param>
    <param name="vrt.p_20" type="string">Enabled</param>
    <param name="vrt.p_100" type="string">Enabled</param>
    <param name="eut.phases" type="string">Single Phase</param>
    <param name="vrt.test_label" type="string">lvrt_lv2</param>
  </params>
</scriptConfig>
