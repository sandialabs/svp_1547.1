OPAL-1.0 Object
DataLogger::Configuration {
  m00_usageMode=Basic
  m01_recordMode=Automatic
  m05_useRTCore=0
  m06_verbose=0
  m07_showDLTConsole=0
  m09_noDataLoss=0
  name=82A432A5-7359-4135-9D1B-3123DE2B17B5_ConfigF3752212-4BBC-46F1-81D5-864CAF22EE6F
  m10_signalGroupConfigList=82A432A5-7359-4135-9D1B-3123DE2B17B5_ConfigF3752212-4BBC-46F1-81D5-864CAF22EE6F/SignalGroupConfigList
  parent=/
}
IOConfigListMap<DataLogger::SignalGroupConfig> {
  resizable=1
  uiName=SIGNAL_GROUP_
  name=82A432A5-7359-4135-9D1B-3123DE2B17B5_ConfigF3752212-4BBC-46F1-81D5-864CAF22EE6F/SignalGroupConfigList
  items {
    item {
      IOConfigItem_id=SIGNAL_GROUP_1
      listParent=100ADBCF-6EEC-4AFD-A7AC-4EF1AAFEAE8C-default/SyncExchangerRegistry/D200796A-5D1C-4DB1-8F34-A3E3A4EB30AC/82A432A5-7359-4135-9D1B-3123DE2B17B5_ConfigF3752212-4BBC-46F1-81D5-864CAF22EE6F/SignalGroupConfigList
      instance {
        guid=BEAEE3B4-0426-47D5-827B-5ADCBA421176
        m003_recordMode=Inherit
        m006_exportFormat=OPREC
        m007_fileAutoNaming=1
        m010_fileName=data
        m011_decimationRatio=1
        m021_fileLength=10
        m022_fileLengthUnits=Seconds
        m031_recordLength=1000
        m032_recordLengthUnits=Steps
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
  parent=82A432A5-7359-4135-9D1B-3123DE2B17B5_ConfigF3752212-4BBC-46F1-81D5-864CAF22EE6F
}