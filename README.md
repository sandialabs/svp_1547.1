## P1547.1 Compliance Python Test Scripts


---

This repository contains all of the open-source OpenSVP components written in Python 3.7. 
Hence, Python 3.7+ is required.

## Contribution

For the contribution list, please refer to [Contribution section](/1547.1/doc/CONTRIB.md)

### Installation

Please refer to the [Install section](/1547.1/doc/INSTALL.md) for detailed instruction

### SVP Scripts

Current compliance test scripts available:

#### Limit Active Power
   Limit Active Power (LAP):
   - [x] Limit active power mode 

#### Voltage regulation
   Constant power factor (CPF):
   - [x] Constant power factor mode 

   Volt-reactive power (VV):
   - [x] Volt-var mode
   - [ ] Volt-var mode(Vref Test)
   - [x] Volt-var mode with an imbalanced grid

   Active power-reactive power (VW):
   - [x] Active power-reactive mode
   - [x] Active power-reactive mode with an imbalanced grid
   - [x] Active power-reactive power (WV)
   
   Constant reactive power (CRP):
   - [x] Constant reactive power mode 

#### Frequency support
- [x] Frequency-watt or Frequency-droop - above nominal frequency (FW)
- [x] Frequency-watt or Frequency-droop - below nominal frequency (FW)

#### Ride-Through support
- [X] Phase-Change Ride-Through
- [ ] High/Low Frequency Ride-Through (Ongoing)
- [ ] Voltage Ride-Through

#### Prioritization of DER responses
- [x] Test for voltage and frequency regulation priority (PRI)

#### Limitation of overvoltage contribution
- [ ] Ground fault overvoltage (GFOV) test
- [ ] Load rejection overvoltage (LROV) test

#### Varia
- [ ] Interoperability test

### Support

For any bugs/issues, please refer to the [bug tracker][bug-tracker-url] section.

🐙 was here.

[bug-tracker-url]: https://github.com/BuiMCanmet/svp_1547.1/issues
[1547-1-url]: https://github.com/BuiMCanmet/svp_1547.1/tree/master_python37

