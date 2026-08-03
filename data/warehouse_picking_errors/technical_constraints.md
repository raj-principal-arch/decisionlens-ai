# Systems and Facility Constraints — RDC-7

> **Synthetic document.** Fictional systems and fictional limits. No real Walmart data.
> Owner: warehouse-systems. Last updated: 2026-06-30.

## RF terminals

The RF pick screen displays the item description truncated to 18 characters. The field width is fixed in the Corvus WMS 7.2 client and cannot be widened before the WMS core upgrade, which is scheduled for FY28.

The screen also shows a three-digit slot check digit. Keying the check digit is optional for ambient full-case picks under the current configuration.

## Slotting

Slot reassignment is available to site users through the Corvus slotting workbench. Bulk moves are supported and need no vendor involvement. Physically relocating a pick face takes an average of 11 minutes including relabelling.

Item similarity is not available as an input to the slotting rules in Corvus WMS 7.2. Adding it would be a configuration change to the slotting profile. The vendor has confirmed it is possible but has not scoped it.

## Pack-out area

There are no spare network drops at the pack stations. Any camera or scanner hardware would need new cabling run across the pick module.

The mezzanine above the pack-out area is covered by a fire-suppression drawing. Adding a fixture above the pack line requires that drawing to be re-approved before installation.

## Pick-to-light

Pick-to-light is installed in aisles 45 to 52 only. The controller reaches end of support in June 2027, so extending the system to further aisles would mean replacing it first.

## How a mispick is recorded

A mispick is recorded only when the receiving store files a discrepancy claim within 72 hours of receipt. Claims filed later are logged as store adjustments and never enter the mispick series.

Mispick records reach the reporting warehouse with a lag of up to 48 hours.

## Voice picking

Voice picking is not installed at RDC-7. It would need headsets and a voice server for 340 associates and has not been scoped.
