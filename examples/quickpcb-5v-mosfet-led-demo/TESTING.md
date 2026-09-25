# Bench test procedure

## Scope

This procedure verifies the assembled acceptance board at 5 V with its onboard LED load. It does not qualify external loads, operation above 5 V, EMC, environmental limits or production yield.

## Equipment

- current-limited regulated 5.0 V supply;
- 3.3 V or 5.0 V logic source, or a second current-limited supply;
- digital multimeter;
- assembled board matching the supplied Gerber, BOM and CPL.

Set the 5 V supply current limit to 20 mA for first power-up. Keep all supplies off while wiring.

## Pre-power checks

1. Inspect polarity and orientation: LED1 cathode is pad 1, Q1 pin 1 is gate, pin 2 is source and pin 3 is drain.
2. Confirm there is no solder bridge between J1 pin 1 and pin 2.
3. Measure R1 and R2 near 2.2 kΩ and R3 near 100 kΩ without power.
4. Check continuity from J1 pin 2 to J2 pin 2, J3 pin 2 and Q1 pin 2.
5. Check continuity from J1 pin 1 to R1 pin 1 and C1 pin 1.

Any hard short or incorrect orientation is a failure. Correct it before applying power.

## Functional test

1. Connect J1 pin 1 to +5.0 V and J1 pin 2 to GND. Leave J2 pin 1 open. Turn on the supply.
2. Verify the LED is off and supply current is below 0.5 mA. J3 pin 1 should be near 5 V.
3. Drive J2 pin 1 to 0 V. Verify the LED remains off. Q1 gate should measure below 0.1 V.
4. Drive J2 pin 1 to 3.3 V. Verify the LED turns on. J3 pin 1 should fall below 0.3 V and total supply current should be approximately 1–2 mA.
5. Repeat with J2 pin 1 at 5.0 V. The LED must remain on and supply current must stay below 3 mA.
6. Remove the J2 drive. The 100 kΩ pull-down must return the LED to off within one second.

## Pass record

Record board serial, date, supply voltage, supply current, J3 pin 1 voltage and visual LED state for open, 0 V, 3.3 V and 5 V control conditions. The board passes only when every pre-power and functional criterion above passes on the physical unit.
