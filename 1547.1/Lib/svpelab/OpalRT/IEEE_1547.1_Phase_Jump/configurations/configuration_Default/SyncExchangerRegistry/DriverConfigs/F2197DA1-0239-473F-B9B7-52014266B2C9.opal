OPAL-1.0 Object
DataLogger::Configuration {
  m01_recordMode=Automatic
  m05_useRTCore=0
  m06_verbose=0
  m09_noDataLoss=0
  m13_usageMode=Basic
  m14_logLevel=Minimal
  m15_toolPriority=NORMAL
  m17_showDLTConsole=0
  name=F2197DA1-0239-473F-B9B7-52014266B2C9_ConfigA7CC5679-0F2A-4387-9C9A-56EDF0B454F7
  m10_signalGroupConfigList=F2197DA1-0239-473F-B9B7-52014266B2C9_ConfigA7CC5679-0F2A-4387-9C9A-56EDF0B454F7/SignalGroupConfigList
  parent=/
}
IOConfigListMap<DataLogger::SignalGroupConfig> {
  resizable=1
  uiName=SIGNAL_GROUP_
  name=F2197DA1-0239-473F-B9B7-52014266B2C9_ConfigA7CC5679-0F2A-4387-9C9A-56EDF0B454F7/SignalGroupConfigList
  items {
    item {
      IOConfigItem_id=SIGNAL_GROUP_1
      listParent=100ADBCF-6EEC-4AFD-A7AC-4EF1AAFEAE8C-default/SyncExchangerRegistry/292763D1-9E77-4EF3-8AF0-4CAE02F08227/F2197DA1-0239-473F-B9B7-52014266B2C9_ConfigA7CC5679-0F2A-4387-9C9A-56EDF0B454F7/SignalGroupConfigList
      instance {
        guid=F33EB391-7008-4153-B574-DAC1EF5CFBEA
        m003_recordMode=Inherit
        m006_exportFormat=OPREC
        m007_fileAutoNaming=1
        m010_fileName=data
        m011_decimationFactor=1
        m015_frameLength=1000
        m016_frameLengthUnits=Steps
        m020_nbRecordedFrames=10
        m021_fileLength=10
        m022_fileLengthUnits=Seconds
        m11_showTriggerConfiguration=0
        m12_triggerReferenceValue=0
        m13_triggerMode=Normal
        m14_triggerFunction=Edge
        m15_triggerPolarity=Positive
        m18_preTriggerPercent=0
        m19_triggerHoldoff=0
        m35_enableSubFraming=1
        m36_subFrameSizeMillis=10
      }
    }
  }
  parent=F2197DA1-0239-473F-B9B7-52014266B2C9_ConfigA7CC5679-0F2A-4387-9C9A-56EDF0B454F7
}