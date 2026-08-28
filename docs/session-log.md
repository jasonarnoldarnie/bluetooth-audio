# Session Log — Bluetooth Audio Adaptor

> Newest entry at the top. Written in the last five minutes of each session so the next morning's
> triage takes five minutes instead of twenty.

---

## Clocks currently running

| What | Started | Expected back | Notes |
|---|---|---|---|
| *(nothing on order)* | — | — | No fab or parts clock running. VNA will be **borrowed**, not bought (decided 2026-08-25). |

## ✅ Decisions RESOLVED 2026-08-23

| Decision | Answer |
|---|---|
| Battery in scope? | **Yes.** Note: pairing already survives power-off via NVS flash — battery is justified by ground-loop breaking and portable use, not state retention |
| Lives permanently in a hot car? | **No** — removable. Li-ion stays (LFP rejected: 3.2 V nominal forces a boost converter onto an audio board) |
| HFP happening? | **Yes** — mic stays, ES8388 stays, record path must actually work |
| TX mode in scope? | **Yes** — REQ-AUD-07, second jack into LIN2/RIN2 |
| Quantity / cost | **5 PCBA + 5 bare, $20 USD landed target**, both flexible |

## Open decisions — blocking work

| Decision | Blocks | Leaning |
|---|---|---|
| **Battery: in scope? And which use case** — retain-state / break-ground-loop / portable | Whole power section: regulator choice, charger, whether REQ-AUD-05 is solved by battery or transformers, CAP2 network | Use case B (ground-loop break) is the strongest argument |
| **Will the device live permanently in a hot car?** | Safety gate on lithium — may rule it out entirely | — |
| **Is handsfree (HFP) ever happening?** | Whether the mic stays (it's discontinued), and whether ES8388 stays vs a simpler DAC-only part | — |
| **Is TX mode in scope?** | Whether a jack input path + switching must be designed. v1 hardware cannot do it | — |
| **Build quantity / cost target** | The whole cost model in requirements §2.1a | Placeholder: 5–10 boards, ≤$25–30/unit |

## Open defects (from `design-review-v1.md`)

**S1 — must fix before ordering:**
1. Codec digital rail at 1.8 V — must become 3.3 V (delete the 1.8 V rail; refit U3 as a 3.3 V codec LDO)
2. ES8388 `CE` pin floating — needs a pull-down to DGND
3. ESP32 `CAP1` missing its required 10 nF cap

**S2:** flash IO2/IO3 swapped · no ground-loop provision · crystal load caps likely mis-derived ·
codec shares the noisy ESP32 rail · mic bias network wrong for a self-biased part

**Instruments not yet owned:** NanoVNA (required to tune the antenna match — the project's stated
learning objective), and a way to measure crystal frequency offset (RTL-SDR).

---

## 2026-08-25 — library infrastructure

**Worked on:** Extracted custom KiCad libraries into a standalone shared repo. No schematic work.

**State now:** Custom symbols, footprints and 3D models live in
`C:\Users\jason\code\kicad-library` (private GitHub repo `jasonarnoldarnie/kicad-library`).
Registered **globally** in KiCad 10 via the `KICAD_USER_LIB` environment variable, so every project
sees them with no per-project setup. Nicknames kept as `custom_symbols` / `custom_footprints`, so
all existing `lib_id` references resolve with zero schematic or PCB edits — verified.

**Next session should:** Swap the regulator parts. The **rail split is already done** — corrected
2026-08-28: [`power.kicad_sch`](../hw/bluetooth-audio/power.kicad_sch) has two regulators (U7, U8)
feeding `+3V3_SYS` and `+3V3_AUDIO`, each with its own test point. What remains is that both are
`NCP1117-3.3_SOT223`, not the specified parts: Rail A → **AP7361C-33Y5** (SOT-89-5, ultra-low
dropout, needed to survive on battery), Rail B → **LP5907MFX-3.3** (6.5 µV<sub>RMS</sub>, the whole
point of a separate analog rail). Two SOT-223 parts also spend the board area the review asked to
reclaim.

**Discovered / decided:**
- **Both project lib tables were broken** — pointed at `${KIPRJMOD}/symbols/` and
  `${KIPRJMOD}/footprints/`, neither of which existed. Hidden because KiCad caches symbols in
  `lib_symbols` and footprints in the `.kicad_pcb`; it only bites when *placing a new part*. Would
  have derailed the power session.
- **No custom footprints needed for either LDO.** `Package_TO_SOT_SMD:SOT-89-5` and `SOT-23-5` both
  ship with KiCad 10. `Regulator_Linear:LP5907MFX-3.3` exists as a stock symbol — Rail B is zero
  library work.
- **AP7361C-33Y5 does need a custom symbol.** Stock only has `AP7361C-33E`, which is the SOT-223
  **3-pin** variant; the Y5 is SOT-89-5 with 5 pins including `EN`. Not a substitute.
- **Open question raised, not closed:** what drives Rail A's `EN` pin? Battery proposal §4.5 raised
  power switching/standby but never resolved it. Decide when drawing the symbol, or the schematic
  gets reopened later.
- **No LCSC part numbers anywhere in the design** — zero `LCSC`/`MPN` fields across all four sheets,
  so the JLCPCB BOM mapping is being done by hand outside KiCad. Highest-value remaining library
  improvement; also makes the requirements §2.3 "verify stock" rule mechanically checkable.
- Dropped KiCad 5 legacy cruft (`.dcm`/`.lib`/`.mod`) and the duplicate ICS-40720 footprint.
- `ICS-40720.stp` was referenced by its footprint but **never existed in the tree**. Reference now
  points at the library's 3D dir; drop the STEP in and it resolves.
- **Fab package is stale.** The gerbers, drill, BOM and position files under
  `production/jlc_pcba/` are byte-identical to the April 2025 commit — they describe the pre-split
  board. **Do not order from them.** They only *appeared* modified in `git status` because
  `core.autocrlf=true` plus a stale index stat-cache; `git add` refreshed the index and found no
  change. The schematics, by contrast, had genuinely changed.
- Project moved off Google Drive to `C:\Users\jason\electronics\bluetooth-audio` on 2026-08-28.
  16 months of uncommitted work committed in five chunks and pushed; `main` had been stale since
  April 2025. The library repo was placed on local disk for the same reason.

---

## 2026-08-23 — review round trip closed

**Worked on:** Folded the artifact annotations back into the docs. All five scope decisions
resolved; three S1 fixes confirmed in plan.

**State now:** Requirements at v1.5. Battery accepted and its follow-ups answered
([`battery-power-proposal.md`](battery-power-proposal.md) §0). New
[`mems-microphone-primer.md`](mems-microphone-primer.md) covers the biasing question and picks a
replacement mic. No schematic edits yet — all of this is still paper.

**Next session should:** Start the schematic pass. The three S1 fixes are unconditional and no
longer blocked by any decision: separate codec LDO at 3.3 V, `CE` pull-down, `CAP1` 10 nF. Roughly
one session's work and it clears the correctness backlog.

**Discovered / decided:**
- ESP32 stores BT bonding in NVS flash automatically — battery was never needed for state retention
- Nordic checked and closed: entire nRF portfolio is BLE-only, no Classic/A2DP anywhere
- ICS-40720 replacement found: Knowles SPH8878LR5H-1 (C3171733), Economic-tier, does both
  differential and single-ended
- Splitting into two 3.3 V rails plus the charger's 4.4 V clamp cuts main-LDO dissipation ~40 %,
  so the oversized SOT-223 can shrink to SOT-89 — but not to SOT-23-5
- Power path does **not** break the ground loop while USB is connected; audio transformers do

---

## 2026-08-21 — planning session (no bench work)

**Worked on:** Full requirements extraction from `calculations.xlsx`, netlist-level design review,
battery proposal, and skill creation.

**State now:** Design is schematic-complete as of commit `369c5f9` (April 2025) but has 3 open S1
defects. No layout changes made. Nothing ordered. Direction settled: keep the bare ESP32 (RF design
is a stated learning objective), self-populate it to put the rest of the board on Economic PCBA.

**Next session should:** Settle the scope decisions above — they gate the power redesign and the
part-retention questions, and they're cheap. Then order the NanoVNA.

**Discovered / decided:**
- Economic PCBA *is* reachable by hand-populating the ESP32 — it is the only Standard-Only part
- Nothing is actually assembled on the back side (J3/J4 are DNP, TP5-9 are bare pads), so the
  single-sided constraint is already met — no re-layout needed
- Module recommendation withdrawn and closed: RF design is the point of the project
- Project has been dormant ~16 months — expect cold context on re-entry
