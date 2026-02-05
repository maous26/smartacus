"""
Niche-Specific Spec Mappings -- Car Phone Mounts
=================================================

Maps each defect_type to concrete OEM requirements, material specs,
and QC test procedures. Deterministic lookup tables.
"""

from typing import Dict

# Version of the mapping data. Bump when DEFECT_TO_SPEC or FEATURE_TO_SPEC change.
MAPPING_VERSION = "1.8.0"


# =====================================================================
# DEFECT -> OEM REQUIREMENTS + QC TESTS
# =====================================================================
# Key: defect_type (matches DefectType enum values)
# Value: dict with:
#   "requirements": list of (requirement, material_spec, tolerance)
#   "qc_tests": list of (category, test_name, method, pass_criterion)
#   "priority_base": CRITICAL / HIGH / MEDIUM / LOW

DEFECT_TO_SPEC: Dict[str, dict] = {
    "mechanical_failure": {
        "requirements": [
            (
                "Ball-joint / pivot mechanism rated for 50,000 cycles minimum",
                "Zinc alloy or stainless steel 304 pivot pins; PC+ABS housing, UL94-V0",
                "+/- 0.3mm on pivot bore diameter",
            ),
            (
                "Arm locking mechanism must hold 2kg static load without creep",
                "Spring-loaded steel lock with hardened teeth (HRC 40+)",
                "Lock engagement depth >= 2mm",
            ),
        ],
        "qc_tests": [
            ("cycles", "Arm open/close cycle test",
             "Open/close arm 50,000 times at 30 cycles/min",
             "No crack, no loosening, retention force within 80% of original"),
            ("load", "Static load hold test",
             "Mount 500g phone + 1.5kg weight, hold 24h horizontal",
             "Zero displacement beyond 1mm"),
        ],
        "priority_base": "CRITICAL",
    },
    "poor_grip": {
        "requirements": [
            (
                "Silicone grip pads on all phone-contact surfaces, Shore A 40-50",
                "Medical-grade silicone, non-yellowing, anti-slip texture (0.8mm relief)",
                "Pad thickness 1.5mm +/- 0.2mm",
            ),
            (
                "Grip retention force >= 3N per contact point (minimum 4 contact points)",
                "TPU over-mold on clamp arms",
                "Contact surface area >= 200mm2 per pad",
            ),
        ],
        "qc_tests": [
            ("vibration", "Vibration endurance test (vehicle simulation)",
             "Mount phone (200g), shaker table 5-200Hz, 2G acceleration, 2h",
             "Phone must not shift > 2mm; no pad detachment"),
            ("surface", "Grip force measurement",
             "Pull-test phone from mount at 90 degrees",
             "Release force >= 8N"),
        ],
        "priority_base": "CRITICAL",
    },
    "installation_issue": {
        "requirements": [
            (
                "Suction cup with pump-lock mechanism (not twist-only)",
                "PU gel suction disc, 72mm diameter minimum, pump-actuated vacuum",
                "Vacuum hold >= -0.6 bar after 72h on glass",
            ),
            (
                "Illustrated quick-start guide (max 4 steps), bilingual EN/ES",
                None,
                None,
            ),
        ],
        "qc_tests": [
            ("surface", "Suction hold test (multiple surfaces)",
             "Apply to glass, textured plastic, leather dash -- hold 1kg for 72h each",
             "No detachment on glass; warning label for textured surfaces"),
            ("thermal", "Suction thermal cycle",
             "10 cycles: 2h at 80C then 2h at -10C with 500g load",
             "No detachment during any cycle"),
        ],
        "priority_base": "HIGH",
    },
    "compatibility_issue": {
        "requirements": [
            (
                "Adjustable clamp range: 60mm to 95mm (covers 4.7\" to 7\" with case)",
                "Spring-loaded auto-grip arms with 35mm travel",
                "Clamp width +/- 1mm at each extreme",
            ),
            (
                "Camera and button cutout zones -- no obstruction within 15mm of edges",
                None,
                "Arm width <= 12mm at phone contact zone",
            ),
        ],
        "qc_tests": [
            ("compatibility", "Multi-phone compatibility test",
             "Test: iPhone 15 Pro Max + case, Samsung S24 Ultra + case, Pixel 8 Pro + case",
             "All phones fit, no camera/button obstruction, stable hold"),
        ],
        "priority_base": "HIGH",
    },
    "material_quality": {
        "requirements": [
            (
                "Main housing: PC+ABS blend (not pure ABS), matte finish, anti-UV additive",
                "PC+ABS GF10 or Bayblend T65 equivalent; 2% UV stabilizer",
                "Surface roughness Ra 0.8-1.6um (matte); no visible weld lines",
            ),
            (
                "All visible screws replaced with snap-fit or hidden fasteners",
                "Stainless steel internal fasteners where needed",
                None,
            ),
        ],
        "qc_tests": [
            ("surface", "Surface quality inspection",
             "Visual check 100%: weld lines, flash, color uniformity",
             "Zero visible defects at 30cm viewing distance"),
            ("thermal", "Material aging test (UV)",
             "120h UV-B exposure per ASTM G154",
             "No yellowing (delta-b < 2.0), no cracking"),
        ],
        "priority_base": "MEDIUM",
    },
    "vibration_noise": {
        "requirements": [
            (
                "Dampening pads at all metal-to-plastic contact points",
                "EPDM rubber gaskets, 1mm thickness, self-adhesive backing",
                "Gasket compression set < 25% after 1000h at 70C",
            ),
            (
                "All joints pre-loaded (zero free-play in neutral position)",
                "Spring washers on all adjustment joints",
                "Free play < 0.1mm in any direction when locked",
            ),
        ],
        "qc_tests": [
            ("vibration", "Road noise simulation test",
             "Shaker table: random vibration 10-500Hz, 1.5G RMS, 4h with 200g phone",
             "No audible rattle; phone screen readable throughout"),
            ("vibration", "Bump shock test",
             "50 half-sine shocks at 15G, 11ms pulse",
             "No loosening, no audible rattle post-test"),
        ],
        "priority_base": "HIGH",
    },
    "heat_issue": {
        "requirements": [
            (
                "Ventilated backplate design (min 40% open area behind phone)",
                "Perforated or skeletal cradle design; no solid plate behind phone",
                "Airflow opening total area >= 2000mm2",
            ),
            (
                "No wireless charging coil unless explicitly requested (heat source)",
                None,
                None,
            ),
        ],
        "qc_tests": [
            ("thermal", "Heat dissipation test",
             "Mount phone running GPS nav for 2h in 45C ambient",
             "Phone surface temperature delta vs unmounted < 5C"),
            ("thermal", "Dashboard thermal exposure",
             "Mount exposed to 90C for 8h (simulating parked car in sun)",
             "No deformation, no suction loss, no material degradation"),
        ],
        "priority_base": "HIGH",
    },
    "size_fit": {
        "requirements": [
            (
                "Compact footprint: mount head <= 80mm x 60mm when arms closed",
                "Low-profile design, arm fold-in mechanism",
                "Overall height from base <= 120mm at lowest position",
            ),
            (
                "Adjustable neck angle: 0-360 degrees rotation, 0-90 degrees tilt",
                "Ball-joint or dual-axis hinge",
                "Rotation lock with 15-degree detents",
            ),
        ],
        "qc_tests": [
            ("compatibility", "Windshield visibility test",
             "Mount installed on standard sedan windshield, driver seated",
             "Mount must not obstruct > 5% of driver forward view angle"),
        ],
        "priority_base": "MEDIUM",
    },
    "durability": {
        "requirements": [
            (
                "Suction cup adhesion rated for 12 months minimum (re-stick capable)",
                "PU gel disc with nano-texture; washable and reusable surface",
                "Re-stick test: wash with water, re-apply, must hold 1kg for 72h",
            ),
            (
                "All adhesive pads: 3M VHB 4910 or equivalent (not generic tape)",
                "3M VHB 4910 or tesa ACXplus 7078",
                "Peel strength >= 25 N/cm on ABS per ASTM D3330",
            ),
        ],
        "qc_tests": [
            ("cycles", "Long-term adhesion test",
             "Mount with 500g phone on glass, ambient cycle (40C/10C) for 30 days",
             "No detachment; suction vacuum loss < 20%"),
            ("cycles", "Arm wear endurance",
             "10,000 phone insert/remove cycles",
             "Retention force within 70% of original"),
        ],
        "priority_base": "HIGH",
    },
}


# =====================================================================
# FEATURE -> ENHANCEMENT SPEC
# =====================================================================
# Key: feature keyword(s) matched via substring search on wish text.

FEATURE_TO_SPEC: Dict[str, dict] = {
    "wireless charging": {
        "requirement": "Integrated Qi wireless charging coil, 10W, MagSafe-compatible alignment",
        "material": "Qi-certified charging module; N52 neodymium alignment magnets (ring array)",
        "tolerance": "Charging coil center alignment +/- 2mm from phone center",
        "accessory": "USB-C to 12V car adapter cable (1.2m, braided)",
        "qc_test": ("thermal", "Wireless charging thermal test",
                     "Charge phone at 10W for 1h in 35C ambient",
                     "Phone + mount surface < 45C; charging efficiency > 75%"),
    },
    "cable organizer": {
        "requirement": "Integrated cable management clip and routing channel on mount arm",
        "material": "TPU cable clip, snap-in design, fits cables 3-6mm diameter",
        "tolerance": None,
        "accessory": "2x adhesive cable clips (spare)",
        "qc_test": None,
    },
    "night mode": {
        "requirement": "Soft LED indicator (power/charging status), auto-dim in low light",
        "material": "0603 SMD LED, warm white 2700K, max 0.5cd brightness",
        "tolerance": "Light sensor threshold: auto-dim below 50 lux",
        "accessory": None,
        "qc_test": ("surface", "LED glare test",
                     "Mount in dark car, LED active",
                     "No visible reflection on windshield from driver position"),
    },
    "adhesive": {
        "requirement": "Premium adhesive disc alternative for textured dashboards",
        "material": "3M VHB 5952 disc, 70mm diameter, with alignment template",
        "tolerance": "Peel strength >= 30 N/cm on textured ABS",
        "accessory": "2x spare adhesive discs in package",
        "qc_test": ("surface", "Textured surface adhesion test",
                     "Apply to leather-grain and wood-grain dash samples, hold 1kg for 7 days",
                     "No detachment on any tested surface"),
    },
    "magsafe": {
        "requirement": "MagSafe-compatible magnetic alignment ring (Apple MFi spec)",
        "material": "18-magnet N52 ring array matching Apple MagSafe puck geometry",
        "tolerance": "Magnet ring center +/- 1mm; pull force >= 20N with MagSafe case",
        "accessory": "Metal ring sticker for non-MagSafe phones",
        "qc_test": ("load", "MagSafe hold strength test",
                     "Attach phone with MagSafe case, apply 15G shock",
                     "Phone must not detach"),
    },
    "one hand": {
        "requirement": "Auto-grip mechanism with trigger release (one-hand operation)",
        "material": "Spring-loaded gravity/sensor arms with push-release button",
        "tolerance": "Trigger force 3-5N; auto-grip close time < 0.5s",
        "accessory": None,
        "qc_test": ("cycles", "One-hand operation test",
                     "Insert and remove phone 1,000 times with one hand",
                     "Mechanism functions correctly with < 5N force throughout"),
    },
    "thicker case": {
        "requirement": "Extended clamp range to accommodate cases up to 15mm thick",
        "material": "Wider spring travel on grip arms (45mm total travel)",
        "tolerance": "Clamp max opening >= 100mm (for 6.7\" phone + 15mm case)",
        "accessory": None,
        "qc_test": None,
    },
}


# =====================================================================
# DEFAULTS (applied to every spec)
# =====================================================================

DEFAULT_GENERAL_MATERIALS = [
    "Main body: PC+ABS blend (UL94-V0 fire rating)",
    "Grip pads: Silicone Shore A 40-50, anti-slip texture",
    "Metal parts: Zinc alloy or stainless steel 304 (salt spray 48h min)",
    "Suction cup: PU gel, 72mm+ diameter",
    "Packaging: FSC-certified cardboard, soy ink printing",
]

DEFAULT_ACCESSORIES = [
    "1x Quick-start guide (EN/ES, illustrated, 4 steps max)",
    "1x Dashboard adhesive disc (3M VHB backup)",
    "1x Cable management clip",
]

DEFAULT_PACKAGING_NOTES = [
    "Retail-ready packaging with Amazon barcode window",
    "Inner tray: pulp molded (no foam/plastic)",
    "Product dimensions and weight on outer box",
    "Insert card with QR code to video installation guide",
]


def severity_to_priority(severity: float) -> str:
    """Map severity_score to OEM priority label."""
    if severity >= 0.8:
        return "CRITICAL"
    elif severity >= 0.6:
        return "HIGH"
    elif severity >= 0.4:
        return "MEDIUM"
    else:
        return "LOW"
