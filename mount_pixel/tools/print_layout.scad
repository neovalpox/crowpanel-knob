// Disposition d'impression (aperçu uniquement)
color("#2b2f36") translate([0, 0, 0]) import("../stl/pixel_k10_P1_pince.stl");
color("#3a3f4a") translate([90, 0, 0]) import("../stl/pixel_k10_P2_socle.stl");
color("#e0e3e8") translate([300, 0, 0]) import("../stl/pixel_k10_P3_cadre.stl");
color("#ff9f43") for (i = [0, 1]) translate([0, -40 - i * 14, 0]) import("../stl/pixel_k10_P4_loquet_x2.stl");
color("#ff9f43") for (i = [0, 1]) translate([50 + i * 24, -50, 0]) import("../stl/pixel_k10_P5_molette_x2.stl");
color("#22d3ee") translate([110, -60, 0]) import("../stl/pixel_k10_test_accroche.stl");
