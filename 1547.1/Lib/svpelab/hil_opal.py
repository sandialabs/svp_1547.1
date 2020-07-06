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
import os

from . import hil
import sys
try:
    import RtlabApi
except ImportError as e:
    print(e)

from time import sleep
import glob
import numpy as np

opalrt_info = {
    'name': os.path.splitext(os.path.basename(__file__))[0],
    'mode': 'Opal-RT'
}

def params(info,group_name=None):
    gname = lambda name: group_name + '.' + name
    pname = lambda name: group_name + '.' + GROUP_NAME + '.' + name
    mode = opalrt_info['mode']
    info.param_add_value('hil.mode', opalrt_info['mode'])
    info.param_group(gname(GROUP_NAME), label='%s Parameters' % mode, active=gname('mode'), active_value=mode,glob=True)
    info.param(pname('project_name'), label='"Active" RT-LAB project name', default = "Open loop")
    info.param(pname('target_name'), label='Target name in RT-LAB', default="RTserver")
GROUP_NAME = 'opal'


def hil_info():
    return opalrt_info

class HIL(hil.HIL):
    """
    Opal_RT HIL implementation - The default.
    """
    def __init__(self, ts, group_name):
        hil.HIL.__init__(self, ts,group_name)
        self.project_name = self._param_value('project_name')
        self.target_name = self._param_value('target_name')
        self.ts = ts
        self.open()
    def _param_value(self, name):
        return self.ts.param_value(self.group_name + '.' + GROUP_NAME + '.' + name)

    def config(self):
        """
        Perform any configuration for the simulation based on the previously
        provided parameters.
        """
        pass

    def open(self):
        """
        Open the communications resources associated with the HIL.
        """
        RtlabApi.OpenProject(self.project_name)

        pass

    def close(self):
        """
        Close any open communications resources associated with the HIL.
        """
        RtlabApi.CloseProject()

    def info(self):
        sytem_info = RtlabApi.GetTargetNodeSystemInfo(self.target_name)
        opal_rt_info = "OPAL-RT - Platform version {0} (IP address : {1})".format(sytem_info[1],sytem_info[6])
        return opal_rt_info

    def control_panel_info(self):
        pass

    def load_schematic(self):
        pass

    def model_state(self):
        pass

    def compile_model(self):
        model_info = {}
        ## Get path to model
        model_info["mdlFolder"],model_info["mdlName"] = RtlabApi.GetCurrentModel()
        model_info["mdlPath"] = os.path.join(model_info["mdlFolder"], model_info["mdlName"] )

        RtlabApi.RegisterDisplay(RtlabApi.DISPLAY_REGISTER_ALL)

        ## Set attribute on project to force to recompile (optional)
        model_info["modelId"] = RtlabApi.FindObjectId(RtlabApi.OP_TYPE_MODEL, model_info["mdlPath"] )

        RtlabApi.SetAttribute(model_info["modelId"], RtlabApi.ATT_FORCE_RECOMPILE, True)

        ## Launch compilation
        compilationSteps = RtlabApi.OP_COMPIL_ALL_NT | RtlabApi.OP_COMPIL_ALL_LINUX
        RtlabApi.StartCompile2((("", compilationSteps),), )
        self.ts.log('Compilation started.')

        ## Wait until the end of the compilation
        status = RtlabApi.MODEL_COMPILING
        while status == RtlabApi.MODEL_COMPILING:
            try:
                ## Check status every 0.5 second
                sleep(0.5)

                ## Get new status
                ## To be done before DisplayInformation because
                ## DisplayInformation may generate an Exception when there is
                ## nothing to read
                status, _ = RtlabApi.GetModelState()

                ## Display compilation log into Python console
                _, _, msg = RtlabApi.DisplayInformation(100)
                while len(msg) > 0:
                    print(msg, end=' ')
                    _, _, msg = RtlabApi.DisplayInformation(100)

            except Exception as exc:
                ## Ignore error 11 which is raised when
                ## RtlabApi.DisplayInformation is called whereas there is no
                ## pending message
                info = sys.exc_info()
                if info[1][0] != 11:  # 'There is currently no data waiting.'
                    ## If a exception occur: stop waiting
                    self.ts.debug("An error occured during compilation.")
                    raise

        ## Because we use a comma after print when forward compilation log into
        ## python log we have to ensure to write a carriage return when
        ## finished.
        print('')

        ## Get project status to check is compilation succed
        status, _ = RtlabApi.GetModelState()
        if status == RtlabApi.MODEL_LOADABLE:
            self.ts.log('Compilation success.')
        else:
            self.ts.log('Compilation failed.')


        return model_info

        pass

    def load_model_on_hil(self):
        status, _ = RtlabApi.GetModelState()
        if status == RtlabApi.MODEL_LOADABLE:
            realTimeMode = RtlabApi.HARD_SYNC_MODE  # Also possible to use SIM_MODE, SOFT_SIM_MODE, SIM_W_NO_DATA_LOSS_MODE or SIM_W_LOW_PRIO_MODE
            timeFactor = 1
            RtlabApi.Load(realTimeMode, timeFactor)
            return "The model is loaded."
        else:
            return "The model is not loadable."

        pass

    def init_sim_settings(self):
        pass

    def init_control_panel(self):
        pass

    def voltage(self, voltage=None):
        pass

    def stop_simulation(self):
        pass

    def start_simulation(self):
        status, _ = RtlabApi.GetModelState()
        if status == RtlabApi.MODEL_PAUSED:
            RtlabApi.Execute(1)
            modelState, realTimeMode = RtlabApi.GetModelState()

            ## Print the model state

        return "The model state is now %s." % RtlabApi.OP_MODEL_STATE(modelState)

if __name__ == "__main__":
    projectName = "Open loop"

    mag = {}
    ang = {}
    for chan in range(1, 4):
        mag[chan] = "PF818072_test_model/sm_computation/Magnitude/Value({})".format(chan)
        ang[chan] = "PF818072_test_model/sm_computation/Phases/Value({})".format(chan)
    RtlabApi.OpenProject(projectName)
    parameterControl = 1
    RtlabApi.GetParameterControl(parameterControl)
    RtlabApi.SetParametersByName((mag[1],mag[2],mag[3],ang[1],ang[2],ang[3]),(2,2,2,0,60,120))

    RtlabApi.CloseProject()



