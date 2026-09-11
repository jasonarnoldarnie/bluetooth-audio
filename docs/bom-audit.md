# BOM Audit & Cost — bluetooth-audio

**Date:** 2026-09-11 · **Scope:** power, audio, micro sheets · **Sourcing target:** JLCPCB / LCSC

This document records a full footprint + part-number sanity check of the schematic BOM, the
corrections applied, the resulting priced BOM, and the open decisions. Every LCSC code was
validated against the local jlcparts snapshot (and the CH340K against jlcpcb.com).

## 1. Result summary

- **137 components** audited. Every non-testpoint / non-antenna part now carries a
  **Manufacturer + MPN + LCSC** field, in one consistent field set.
- Verification (post-edit): missing LCSC — **none**; missing Manufacturer/MPN — **none**;
  stale/duplicate `Supplier Part Number` fields — **none**.

## 2. Corrections applied

### 2.1 Critical — `C1849` mis-assignment (14 caps)
`C1849` (a 10 µF 16 V 1206 MLCC) had been pasted as a placeholder supplier code onto 14
capacitors of unrelated values (1 µF, 4.7 µF, 47 µF, 4.7 nF, 100 nF, **18 pF crystal load**),
several in the wrong package. All were reassigned to the correct part for their value/footprint;
the stale `Supplier Part Number` field was cleared so a BOM export cannot pick it up.

### 2.2 D1 LED colour
Was `C34499` (KT-0805**W**, white) on a part labelled `LED_BLUE`. Reassigned to **`C2293`
(KT-0805B, blue)**.

### 2.3 Missing passive PNs populated
All resistors, capacitors and L1 were given JLCPCB parts — **Basic** parts wherever a Basic
option exists (free assembly); Extended only where no Basic part is stocked (1k2/3k/56k, the
C0G/NP0 caps, RF 3.3 pF, 2.2 nH). Dielectric was chosen deliberately: **C0G** for the 18 pF
crystal load caps and 3.3 pF RF caps, **C0G preserved** on the audio 100 nF (C41/C42, Murata
`C97946`), X7R/X5R for decoupling.

### 2.4 Part / footprint changes (this review)
| Ref | Change | Part |
|-----|--------|------|
| C48 | 47 µF SYS bulk: MLCC → **polymer/tantalum** (footprint → `CP_EIA-3528-21_Kemet-B`) | `C22036` Kyocera AVX TAJB476K010RNJ |
| C27 | 10 µF footprint **0402 → 0603** (matches its siblings) | `C19702` |
| U3  | footprint **TSSOP-10 → MSOP-10** (DGS = VSSOP/MSOP, no thermal pad) | `C42751` TI TS5A23159DGSR |
| Q2  | PN added | `C15127` AO3401A (Basic) |
| J2  | PN added | `C5143397` GCT USB4110-GF-A |
| J5  | Molex → **JST-PH 3-pin** side-entry (battery connector), footprint changed | `C157929` JST S3B-PH-K-S |
| D6  | LED_CHG → **amber** | `C2296` KT-0805Y |
| U9  | **marked DNP** (per instruction) — BQ24074 charger not populated | `C54313` (kept for reference) |

### 2.5 Field normalisation
Every IC/LED/transistor/crystal/connector was migrated from the old `Supplier Part Number`
field to the unified `LCSC` + `Manufacturer` + `MPN` set used by the passives; stale
`Supplier Part Number` values (including secondary units of multi-unit symbols D7/D8/Q1) cleared.

## 3. MLCC review (power rail)

Roles confirmed from the PCB netlist: C47 = VBUS input; C2/C3/C5 = SYS & LDO inputs;
**C48 = +V_SYS bulk, C49 = +BATT bulk**; C4/C20/C50 = 3V3 rails; C51 = USB-shield Y-cap;
C52/C53 = ADC / VBUS-sense.

- **Decoupling and all three regulators (BQ24074, AP7361C, LP5907) → MLCC is correct** — they
  are designed for low-ESR ceramic. Using **1206** for the rail caps already limits DC-bias loss
  and gives voltage headroom (1 µF/4.7 µF/100 nF 1206 selected at 50 V; 10 µF 1206 at 50 V).
- **C48 (SYS bulk) swapped to a 47 µF/10 V tantalum** (`C22036`): a 10 V X5R 47 µF 1206 on a
  3.0–4.4 V rail delivers only ~50–65 % of nameplate under DC bias; the tantalum holds its value.
- **C49 (+BATT bulk) left as MLCC** for now — revisit if bulk hold-up on the battery node
  matters (see open items).

## 4. Priced BOM (assembled parts; DNP excluded)

Unit price shown at the 100-board quantity tier. Lib = JLCPCB Basic (free feeder) vs Extended
($3 one-time setup each).

| Qty | Value | Refs | Footprint | Manufacturer | MPN | LCSC | Lib | Unit(100) |
|----:|-------|------|-----------|--------------|-----|------|-----|----------:|
| 14 | 100nF | C9,C10,C11,C12,C13,C16,C18,C19,C28,C30,C32,C33,C43,C46 | C_0402_1005Metric | Samsung Electro Mechanics | CL05B104KO5NNNC | C1525 | Basic | $0.0051 |
| 10 | 100k | R17,R22,R23,R30,R31,R34,R35,R38,R39,R40 | R_0402_1005Metric | UNI ROYAL Uniroyal Elec | 0402WGF1003TCE | C25741 | Basic | $0.0033 |
| 8 | 10u | C8,C14,C15,C17,C27,C29,C31,C44 | C_0603_1608Metric | Samsung Electro Mechanics | CL10A106KP8NNNC | C19702 | Basic | $0.0723 |
| 6 | 1k | R19,R20,R32,R33,R36,R37 | R_0402_1005Metric | UNI ROYAL Uniroyal Elec | 0402WGF1001TCE | C11702 | Basic | $0.0011 |
| 6 | 10R | R7,R8,R9,R10,R16,R21 | R_0402_1005Metric | UNI ROYAL Uniroyal Elec | 0402WGF100JTCE | C25077 | Basic | $0.0009 |
| 6 | 330R | R6,R12,R15,R18,R28,R29 | R_0402_1005Metric | UNI ROYAL Uniroyal Elec | 0402WGF3300TCE | C25104 | Basic | $0.0012 |
| 5 | 1uF | C6,C7,C24,C26,C34 | C_0402_1005Metric | Samsung Electro Mechanics | CL05A105KA5NQNC | C52923 | Basic | $0.0122 |
| 4 | LED_PGOOD | D2,D3,D4,D5 | LED_0805_2012Metric | Hubei KENTO Elec | KT-0805G | C2297 | Basic | $0.0163 |
| 4 | 10k | R1,R2,R11,R27 | R_0402_1005Metric | UNI ROYAL Uniroyal Elec | 0402WGF1002TCE | C25744 | Basic | $0.0029 |
| 3 | 10uF | C5,C47,C50 | C_1206_3216Metric | Samsung Electro Mechanics | CL31A106KBHNNNE | C13585 | Basic | $0.1622 |
| 2 | 18pF | C35,C36 | C_0402_1005Metric | FH Guangdong Fenghua Advanced Tech | 0402CG180J500NT | C1549 | Basic | $0.0023 |
| 2 | 4.7uF | C4,C22 | C_0603_1608Metric | Samsung Electro Mechanics | CL10A475KO8NNNC | C19666 | Basic | $0.0209 |
| 2 | 100nF | C52,C53 | C_1206_3216Metric | Samsung Electro Mechanics | CL31B104KBCNNNC | C24497 | Basic | $0.0188 |
| 2 | 4k7 | R24,R25 | R_0402_1005Metric | UNI ROYAL Uniroyal Elec | 0402WGF4701TCE | C25900 | Basic | $0.0011 |
| 2 | 5k1 | R4,R5 | R_0402_1005Metric | UNI ROYAL Uniroyal Elec | 0402WGF5101TCE | C25905 | Basic | $0.0009 |
| 2 | 47uF | C1,C21 | CP_Elec_5x5.8 | PANASONIC | EEEFT1E470AR | C336270 | Ext | $0.3106 |
| 2 | D_Schottky_Dual_Series_AKC_Split | D7,D8 | SOT-23 | MDD Microdiode Semiconductor | BAT54S | C408389 | Ext | $0.0137 |
| 2 | 3.3pF | C37,C38 | C_0402_1005Metric | Murata Electronics | GJM1555C1H3R3BB01D | C76906 | Ext | $0.0318 |
| 2 | 100nF | C41,C42 | C_1206_3216Metric_Pad1.33x1.80mm_HandSolder | Murata Electronics | GRM31C5C1H104JA01L | C97946 | Ext | $0.1513 |
| 1 | 4.7nF | C51 | C_1206_3216Metric | YAGEO | CC1206JRNPO9BN472 | C113886 | Ext | $0.0544 |
| 1 | AO3401A | Q2 | SOT-23 | Alpha Omega Semicon | AO3401A | C15127 | Basic | $0.0596 |
| 1 | 10nF | C45 | C_0402_1005Metric | Samsung Electro Mechanics | CL05B103KB5NNNC | C15195 | Basic | $0.0035 |
| 1 | Conn_01x03 | J5 | JST_PH_S3B-PH-K_1x03_P2.00mm_Horizontal | JST | S3B-PH-K-S(LF)(SN) | C157929 | Ext | $0.0402 |
| 1 | 1uF | C20 | C_0603_1608Metric | Samsung Electro Mechanics | CL10A105KB8NNNC | C15849 | Basic | $0.0297 |
| 1 | 0R | R13 | R_0402_1005Metric | UNI ROYAL Uniroyal Elec | 0402WGF0000TCE | C17168 | Basic | $0.0011 |
| 1 | 1uF | C2 | C_1206_3216Metric | Samsung Electro Mechanics | CL31B105KBHNNNE | C1848 | Basic | $0.0414 |
| 1 | 47uF | C48 | CP_EIA-3528-21_Kemet-B | Kyocera AVX | TAJB476K010RNJ | C22036 | Ext | $0.1847 |
| 1 | LED_BLUE | D1 | LED_0805_2012Metric | Hubei KENTO Elec | KT-0805B | C2293 | Ext | $0.0123 |
| 1 | LED_CHG | D6 | LED_0805_2012Metric | Hubei KENTO Elec | KT-0805Y | C2296 | Basic | $0.0153 |
| 1 | Crystal 40 MHz 10pF | Y1 | Crystal_SMD_SeikoEpson_FA128-4Pin_2.0x1.6mm | Seiko Epson | Q22FA12800101 | C255898 | Ext | $0.2268 |
| 1 | 1k5 | R_ILIM1 | R_0402_1005Metric | UNI ROYAL Uniroyal Elec | 0402WGF1501TCE | C25867 | Basic | $0.0011 |
| 1 | PJ-3537S-SMT | J1 | PJ-3537S-SMT | XKB Connection | PJ-3537S-SMT | C2689709 | Ext | $0.2473 |
| 1 | 56k | R_TMR1 | R_0402_1005Metric | FOJAN | FRC0402F5602TS | C2906875 | Ext | $0.0018 |
| 1 | 1k2 | R_ISET1 | R_0402_1005Metric | FOJAN | FRC0402F1201TS | C2909307 | Ext | $0.0022 |
| 1 | 3k | R_ITERM1 | R_0402_1005Metric | FOJAN | FRC0402F3001TS | C2909355 | Ext | $0.0017 |
| 1 | 4.7uF | C3 | C_1206_3216Metric | FH Guangdong Fenghua Advanced Tech | 1206B475K500NT | C29823 | Basic | $0.0998 |
| 1 | ES8388 | U4 | QFN-28-1EP_4x4mm_P0.4mm_EP2.3x2.3mm | Everest Semiconductor | ES8388 | C365736 | Ext | $0.7110 |
| 1 | TS5A23159DGS | U3 | MSOP-10_3x3mm_P0.5mm | Texas Instruments | TS5A23159DGSR | C42751 | Ext | $0.3531 |
| 1 | AP7361C-33Y5 | U7 | SOT-89-5 | Diodes Incorporated | AP7361C-33Y5-13 | C460397 | Ext | $0.2460 |
| 1 | ZTS6216 | MK1 | ZTS6216 | ZILLTEK | ZTS6216 | C481302 | Ext | $0.4572 |
| 1 | USB_C_Receptacle_USB2.0 | J2 | USB_C_Receptacle_GCT_USB4110 | Global Connector Technology | USB4110-GF-A | C5143397 | Ext | $0.8737 |
| 1 | W25Q32JVZP | U6 | WSON-8-1EP_6x5mm_P1.27mm_EP3.4x4.3mm | Winbond Elec | W25Q32JVZPIQ | C571260 | Ext | $1.3211 |
| 1 | UMH3N | Q1 | SOT-363_SC-70-6 | Jiangsu Changjing Electronics | UMH3N | C62892 | Ext | $0.0438 |
| 1 | USBLC6-2SC6 | U5 | SOT-23-6 | STMicroelectronics | USBLC6-2SC6 | C7519 | Ext | $0.1287 |
| 1 | LP5907MFX-3.3 | U11 | SOT-23-5 | Texas Instruments | LP5907MFX-3.3/NOPB | C80670 | Ext | $0.1102 |
| 1 | 2.2nH | L1 | L_0402_1005Metric | Murata Electronics | LQG15HS2N2S02D | C86061 | Ext | $0.0191 |
| 1 | ESP32D0WD-V3 | U1 | QFN-48-1EP_5x5mm_P0.35mm_EP3.7x3.7mm_ThermalVias | Espressif Systems | ESP32-D0WD-V3 | C967021 | Ext | $2.0515 |
| 1 | CH340K | U2 | SSOP-10-1EP_3.9x4.9mm_P1mm_EP2.1x3.3mm | WCH(Jiangsu Qin Heng) | CH340K | C968586 | Ext | $0.3200 |
*Also on the board but **DNP** (not assembled): U9 (BQ24074 charger), C54, R3/R14/R41 (0 Ω options), R26, R_NTC_LIN1, J3 (prog header), J4 (JTAG pads). ANT1 is a PCB trace antenna. Test points TPx carry no part.*

## 5. Cost

**Component (parts) cost** — from live LCSC tier pricing, DNP parts excluded, 113 SMT placements/board:

| Boards | Parts cost (order) | Per board | Extended-part setup (one-time) |
|-------:|-------------------:|----------:|-------------------------------:|
| 5   | \$66.75    | **\$13.35** | 25 × \$3 = \$75 |
| 30  | \$338.76   | **\$11.29** | \$75 |
| 100 | \$1,008.75 | **\$10.09** | \$75 |

**Main cost drivers / board:** U1 ESP32 \$2.05 · U6 W25Q32 \$1.32 · J2 USB-C (GCT) \$0.87 ·
U4 ES8388 \$0.71 · MK1 mic \$0.46 · 3× 10 µF 1206 \$0.49 · 2× 47 µF elec \$0.62.

**Not included:** BQ24074 charger (DNP — adds ~\$1.6–2.0/board if populated); the battery
(off-board, ~\$8–12); PCB fabrication and SMT assembly labour (needs final board dimensions —
the `.kicad_pcb` is stale vs the current schematic).

**Cost-reduction options (optional):**
- **U6** `W25Q32JVZPIQ` (WSON, \$1.32) → `W25Q32JVSSIQ` SOIC-8 or a plain W25Q32 (~\$0.30) saves ~\$1/board.
- **J2** GCT USB4110 (\$0.87) → a JLCPCB-Basic USB-C (e.g. TYPE-C-31-M-12, ~\$0.15) saves ~\$0.7/board — GCT is the more robust part, so this is a trade-off.

## 6. Open items / decisions

1. **Battery (off-board, source separately — not on the JLCPCB BOM).** Design calls for a
   removable Li-ion cell **≥1000 mAh** with a **3-wire JST-PH** lead (BAT+/NTC/BAT−) and an
   integrated **10 kΩ NTC** for the BQ24074 TS pin. J5 (`S3B-PH-K-S`) mates the standard JST-PH
   battery connector. Recommended: a **1200 mAh 3.7 V Li-Po with PCM + 10 kΩ NTC + 3-wire
   JST-PH** (e.g. LP504050-class, or a 603450 3-wire pack). Confirm the NTC β/value matches the
   R_NTC network.
2. **U9 = DNP** disables on-board charging. Confirm this is intended (e.g. hand-populate later /
   charge externally), since it removes the power-path charger from the assembled board.
3. **C49 (+BATT bulk)** still MLCC — decide whether to match C48 (polymer) if battery-node
   hold-up matters.
4. **J5 is through-hole** — JLCPCB assembles THT for an added fee, or hand-solder.
5. **PCB is stale** vs the revised schematic (duplicate refs / a `+1V8` net not in the current
   design). Re-sync schematic → PCB before fab; board dimensions are needed to complete a full
   fab+assembly quote.

*Generated during BOM sanity-check pass. Component pricing from the local jlcparts snapshot; verify live stock/price at order time.*
