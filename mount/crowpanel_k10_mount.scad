// =====================================================================
//  Support CrowPanel 1.28" Rotary (ESP32-S3) pour Keychron K10 Max
//  Pince sur le coin arrière droit, écran incliné à 70° vers l'utilisateur.
//
//  2 pièces : PINCE (pince + tour)  et  BERCEAU (coupe du CrowPanel),
//  assemblées par 2 vis M3x10 + 2 écrous M3.
//
//  Repère "bureau" (unités : mm) :
//    X = vers la droite, X=0 sur la face droite du clavier
//    Y = vers l'arrière, Y=0 sur la face arrière du clavier
//    Z = vers le haut,   Z=0 sur le bureau
//
//  part = "assembly" (aperçu), "clip", "cradle", "clip_print",
//         "cradle_print", "fit_test"
// =====================================================================

part = "assembly";
show_ghosts = true;          // clavier + CrowPanel fantômes dans l'aperçu

// ---------- Clavier K10 Max (valeurs CAO Keychron, À VÉRIFIER) ----------
rear_h     = 29.8;   // bureau -> dessus du rebord arrière (sans keycaps), pieds rabattus
typing_deg = 3.5;    // inclinaison du clavier (pieds rabattus)
rim_h      = 14.25;  // hauteur de la paroi du top case (dessus du rebord -> dessous de la marche)
ledge      = 2.7;    // largeur de la marche : le top case déborde du bottom case (2.7 à droite, ~4 derrière)
draft      = 0.9;    // dépouille des parois du top case (plus saillantes en bas qu'en haut)
rim_rear_w = 10.0;   // rebord libre entre la face arrière et les keycaps
rim_side_w = 9.0;    // rebord libre entre la face droite et les keycaps
corner_r   = 4.0;    // rayon du coin arrière droit (vue de dessus)
fit        = 0.25;   // jeu pince/clavier (réduire à 0.1 si ça flotte)

// ---------- Pince ----------
clip_len = 58;    // longueur le long du bord arrière (vers la gauche)
side_len = 32;    // longueur le long du bord droit (vers l'avant)
wall     = 3.5;   // épaisseur des parois
lip_t    = 2.4;   // épaisseur de la lèvre posée sur le rebord
lip_w    = 6.0;   // avancée de la lèvre sur le rebord (< rim_rear_w)
hook_t   = 3.0;   // épaisseur du crochet sous la marche
hook_d   = 1.9;   // avancée du crochet sous la marche (< ledge - 0.3)

// ---------- CrowPanel (STEP Elecrow) ----------
cp_base_d  = 46.0;  // socle acrylique fixe (c'est lui qu'on tient)
cp_base_h  = 12.2;  // hauteur du socle sous la molette
cp_knob_d  = 47.3;  // molette alu moletée (tourne, NE PAS toucher)
cp_knob_a0 = 12.4;  // début de la molette (depuis le fond du socle)
cp_knob_a1 = 32.1;  // fin de la molette (face écran)
cp_len     = 34.2;  // longueur totale

// ---------- Berceau ----------
tilt_deg   = 70;    // angle écran / bureau
cup_depth  = 6.0;   // hauteur de socle enserrée (le reste laisse passer la lumière des LEDs)
cup_wall   = 2.4;
cup_floor  = 2.4;   // épaisseur de l'anneau d'appui (reprend l'appui sur la molette)
floor_ring = 3.0;   // largeur de l'anneau d'appui (le centre reste ouvert : câble, BOOT/RESET)
cup_fit    = 0.2;   // jeu radial du socle
rib_h      = 0.45;  // nervures d'écrasement : dépassent de 0.45 mm (serrage ~0.25 mm)
pad_t      = 6.0;   // épaisseur de la semelle de fixation sous le berceau
pad_w      = 30;
pad_ext    = 10;    // la semelle se prolonge sous la molette (sans la toucher) pour des vis bien tenues

// Position de la molette : point le plus bas du bord avant de la molette
cp_x         = -24;  // centre de l'écran en X
screen_low_y = 0;    // 0 = à l'aplomb du bord arrière du clavier
screen_low_z = 42;   // juste au-dessus des keycaps arrière (40.1 mm)

// ---------- Vis : 2 x M3x10 + 2 écrous M3 ----------
m3_d     = 3.4;
m3_head  = 6.2;
nut_w    = 5.7;   // M3 : 5.5 sur plats + jeu
nut_t    = 2.6;
screw_dx = 8;     // ± en X

// ---------- Tour ----------
fin_x0 = -38;     // largeur de la tour (X) : de fin_x0 à la joue droite

$fn = 96;

// =====================================================================
// Calculs
// =====================================================================
s20 = sin(90 - tilt_deg);
c20 = cos(90 - tilt_deg);
n_axis = [0, -c20, s20];          // axe du bouton (socle -> écran)
down_r = [0, -s20, -c20];         // rayon "vers le bas" perpendiculaire à l'axe
rk = cp_knob_d / 2;
p_low = [cp_x, screen_low_y, screen_low_z];
cp_origin = p_low - cp_knob_a1 * n_axis - rk * down_r;   // centre du fond du socle
r_in  = cp_base_d / 2 + cup_fit;
pad_len = cup_floor + cup_depth + pad_ext;     // longueur de la semelle le long de l'axe
screw_z = -cup_floor + pad_len / 2;            // position axiale des vis
r_out = r_in + cup_wall;

// Repère du berceau : Z local = axe du bouton, -Y local = vers le bas/avant
module at_cradle() { translate(cp_origin) rotate([tilt_deg, 0, 0]) children(); }
// Repère du clavier (plaque) -> bureau
module at_keyboard() { translate([0, 0, rear_h]) rotate([typing_deg, 0, 0]) children(); }

// =====================================================================
// Clavier simplifié (repère plaque : Z=0 dessus du rebord, faces à X=0/Y=0)
// =====================================================================
// Boîte dont seul le coin (+X,+Y) est arrondi (vue de dessus)
module rounded_box(x0, x1, y0, y1, z0, z1, r) {
    translate([0, 0, z0]) linear_extrude(z1 - z0)
        hull() {
            translate([x1 - r, y1 - r]) circle(r);
            translate([x0, y0]) square([x1 - r - x0, y1 - y0]);
            translate([x0, y0]) square([x1 - x0, y1 - r - y0]);
        }
}
module kb_keepout() {
    // top case (parois en dépouille : la pince épouse le haut ET le bas)
    hull() {
        rounded_box(-400, fit - draft, -400, fit - draft, -0.01, fit, corner_r);
        rounded_box(-400, fit, -400, fit, -rim_h - fit, -rim_h - fit + 0.01, corner_r);
    }
    // bottom case, en retrait sous la marche (il rentre encore plus en descendant)
    rounded_box(-400, 0.3 - ledge, -400, 0.3 - ledge, -60, -rim_h - fit, corner_r);
    // keycaps et zone de frappe
    rounded_box(-400, -rim_side_w, -400, -rim_rear_w, -1, 40, 2);
}

// =====================================================================
// Pince (repère plaque)
// =====================================================================
zb = -rim_h - fit - hook_t;      // bas du crochet
zt = fit + lip_t;                // dessus de la lèvre
xr = fit + wall;                 // extérieur de la joue droite
yr = fit + wall;                 // extérieur de la paroi arrière
module clip_body() {
    difference() {
        union() {
            // paroi arrière (épouse la dépouille)
            translate([-clip_len, fit - draft, zb]) cube([clip_len + xr, wall + draft, zt - zb]);
            // joue droite
            translate([fit - draft, -side_len, zb]) cube([wall + draft, side_len + yr, zt - zb]);
            // lèvres sur le rebord (arrière + droite)
            translate([-clip_len, -lip_w, fit]) cube([clip_len + xr, lip_w + yr, lip_t]);
            translate([-lip_w, -side_len, fit]) cube([lip_w + xr, side_len + yr, lip_t]);
            // crochets sous la marche (arrière + droite)
            translate([-clip_len, -hook_d, zb]) cube([clip_len + xr, hook_d + yr, hook_t]);
            translate([-hook_d, -side_len, zb]) cube([hook_d + xr, side_len + yr, hook_t]);
        }
        kb_keepout();
        // chanfreins d'entrée : on pousse la pince vers l'avant sur le rebord
        zh = -rim_h - fit;
        rotate([90, 0, 90]) translate([0, 0, -clip_len - 1]) linear_extrude(clip_len + 10) {
            polygon([[-lip_w, fit], [-lip_w + 1.2, fit], [-lip_w, fit + 1.2]]);
            polygon([[-hook_d, zh], [-hook_d + 0.9, zh], [-hook_d, zh - 0.9]]);
        }
    }
}

// =====================================================================
// Berceau (repère local : socle posé à z=0, axe +Z)
// =====================================================================
module cradle_local() {
    difference() {
        union() {
            translate([0, 0, -cup_floor]) cylinder(r = r_out, h = cup_floor + cup_depth);
            // semelle de fixation (côté bas)
            hull() {
                translate([-pad_w / 2, -r_out - pad_t, -cup_floor]) cube([pad_w, 1, pad_len]);
                translate([-pad_w / 2 + 4, -r_out + 4, -cup_floor]) cube([pad_w - 8, 1, cup_floor + cup_depth]);
                translate([-pad_w / 2 + 2, -rk - 1.5 - 1, -cup_floor]) cube([pad_w - 4, 1, pad_len]);
            }
        }
        // logement du socle
        cylinder(r = r_in, h = 50);
        // ouverture du fond (connecteurs, câble, boutons BOOT/RESET)
        translate([0, 0, -10]) cylinder(r = cp_base_d / 2 - floor_ring, h = 20);
        // chanfrein d'entrée
        translate([0, 0, cup_depth - 1]) cylinder(r1 = r_in, r2 = r_in + 1.2, h = 1.01);
        // vis + écrous (écrous glissés par le haut)
        for (sx = [-1, 1]) translate([sx * screw_dx, 0, screw_z]) {
            // s'arrête avant la paroi intérieure : la vis ne touche jamais le socle
            translate([0, -r_in - 1.0, 0]) rotate([90, 0, 0]) cylinder(d = m3_d, h = pad_t + cup_wall + 2, $fn = 32);
            translate([-nut_w / 2, -r_out - pad_t / 2 - nut_t / 2 - 0.5, -2.75])
                cube([nut_w, nut_t, 20]);
        }
    }
    // nervures d'écrasement (3 x 120°)
    for (a = [90, 210, 330]) rotate([0, 0, a])
        translate([r_in, 0, 0.8]) cylinder(r = rib_h, h = cup_depth - 1.6, $fn = 16);
}

module cradle() { at_cradle() cradle_local(); }

// Volume interdit pour la tour : berceau + molette qui tourne
module cradle_keepout() {
    at_cradle() {
        translate([0, 0, -cup_floor - 0.01]) cylinder(r = r_out + 0.3, h = cp_len + 10);
        translate([0, 0, cp_knob_a0 - 1]) cylinder(r = rk + 2.5, h = 40);
        // dégagement du câble derrière le socle
        translate([0, 0, -30]) cylinder(r = cp_base_d / 2 - floor_ring, h = 30);
    }
    cradle();
}

// =====================================================================
// Tour : relie la paroi arrière de la pince à la semelle du berceau
// =====================================================================
// Dalle sous la semelle, sur toute la largeur de la tour : la tour garde une section
// constante en X, donc aucun porte-à-faux quand on l'imprime couchée sur la joue droite.
module pad_face_slab(th = 0.5) {
    at_cradle() translate([fin_x0 - cp_x, -r_out - pad_t - th, -cup_floor])
        cube([xr - fin_x0, th, pad_len]);
}
module fin() {
    difference() {
        intersection() {
            hull() {
                at_keyboard() translate([fin_x0, fit, zb]) cube([xr - fin_x0, wall, zt - zb]);
                pad_face_slab(8);
            }
            // largeur de la tour
            translate([fin_x0, -100, -50]) cube([xr - fin_x0, 300, 300]);
        }
        cradle_keepout();
        at_keyboard() kb_keepout();
        // vis M3 : passage + lamage par en dessous
        at_cradle() for (sx = [-1, 1]) translate([sx * screw_dx, -r_out - pad_t, screw_z]) {
            translate([0, 1, 0]) rotate([90, 0, 0]) cylinder(d = m3_d, h = 31, $fn = 32);
            translate([0, -5, 0]) rotate([90, 0, 0]) cylinder(d = m3_head, h = 60, $fn = 32);
        }
    }
}

module clip_part() {
    union() {
        at_keyboard() clip_body();
        fin();
    }
}

// =====================================================================
// Fantômes
// =====================================================================
module ghosts() {
    %import("ref/k10_ghost.stl");
    %at_cradle() import("ref/crowpanel_ghost.stl");
}

// =====================================================================
// Sorties
// =====================================================================
if (part == "assembly") {
    color("#2b2f36") clip_part();
    color("#e0e3e8") cradle();
    if (show_ghosts) ghosts();
}
else if (part == "clip") clip_part();
else if (part == "cradle") cradle();
// Pince à imprimer couchée sur la joue droite (aucun support)
else if (part == "clip_print") translate([0, 0, xr]) rotate([0, 90, 0]) clip_part();
// Berceau à imprimer anneau d'appui sur le plateau
else if (part == "cradle_print") translate([0, 0, cup_floor]) cradle_local();
// Tranche de 12 mm pour valider l'accroche avant la grande impression
else if (part == "fit_test") translate([0, 0, -18]) rotate([0, 90, 0]) intersection() {
    clip_body();
    translate([-30, -50, -50]) cube([12, 100, 100]);
}
