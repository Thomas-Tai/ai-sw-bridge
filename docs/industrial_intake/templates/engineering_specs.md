# Engineering Specs

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

Numeric, testable engineering assumptions. Estimates are allowed — but **every
number carries a status**: `required`, `assumed`, `measured`, `vendor_provided`,
or `derived`.

## Throughput, speed, accuracy, repeatability

*(Numbers with units and status, e.g. "belt speed 0.1 m/s (derived)".)*

## Payload, force, torque, power, duty cycle

*(Worst-case moving mass, peak forces, continuous vs intermittent duty.)*

## Dimensional envelope and mass

*(Overall machine envelope; per-module mass budget if lifting matters.)*

## Materials and surface constraints

*(Food-safe? ESD? Corrosion? Contact-surface hardness?)*

## Control and signal requirements

*(Sensors in, actuators out, buses, voltages — enough to size the electrical interfaces.)*

## Tolerance policy

*(The default tolerance class and where tighter fits are actually needed.)*

## Applicable standards

*(Drawing standard and projection angle — ISO or ASME, stated explicitly;
thread standard, e.g. ISO metric coarse; fit conventions, e.g. ISO 286 H7/g6.)*

## Units and reference coordinate conventions

*(Length/mass/angle units; which way X/Y/Z point; where the machine origin sits.)*
