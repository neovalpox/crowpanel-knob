// =====================================================================
//  Support rotatif Google Pixel 10 Pro Fold (DÉPLIÉ) pour Keychron K10 Max
//  Coin arrière GAUCHE du clavier, écran incliné vers l'utilisateur.
//
//  Pièces :
//    P1 "pince"   : pince en C sur le coin (lèvres + crochets + 2 vis de serrage)
//                   + patte arrière boulonnée sur le socle. Imprimée couchée sur la joue gauche.
//    P2 "socle"   : semelle posée sur le bureau + colonne + tête de pivot. Imprimé debout.
//    P3 "cadre"   : cadre dans lequel le téléphone ouvert se glisse (par le haut),
//                   avec disque de pivot au dos. Imprimé dos sur le plateau.
//    P4 "loquet"  x2 : loquets pivotants qui ferment le haut du cadre.
//    P5 "molette" x2 : têtes moletées des vis de serrage M4.
//
//  Repère bureau (mm) : X vers la droite (X=0 = face gauche du clavier, clavier en X>0),
//                       Y vers l'arrière (Y=0 = face arrière, clavier en Y<0),
//                       Z vers le haut (Z=0 = bureau).
//
//  part = "assembly" | "sweep_check" | "clip" | "base" | "frame" | "latch" | "knob"
//         | "clip_print" | "base_print" | "frame_print" | "latch_print" | "knob_print" | "fit_test"
// =====================================================================
part = "assembly";
show_ghosts = true;
frame_angle = 0;        // rotation du cadre dans l'aperçu (0 = portrait, 90 = paysage)

// ---------- Clavier (CAO Keychron, à vérifier au pied à coulisse) ----------
rear_h     = 29.8;   // bureau -> dessus du rebord arrière (sans keycaps), pieds rabattus
typing_deg = 3.5;    // inclinaison du clavier (pieds rabattus)
rim_h      = 14.25;  // hauteur de la paroi du top case (dessus du rebord -> dessous de la marche)
ledge      = 2.7;    // largeur de la marche (le top case déborde du bottom case)
draft      = 0.9;    // dépouille des parois du top case
rim_rear_w = 10.6;   // rebord libre derrière les keycaps (mesuré CAO, côté gauche)
rim_side_w = 9.7;    // rebord libre à gauche des keycaps (Échap à 9.7 mm du bord)
corner_r   = 2.5;    // rayon du coin arrière gauche (réel ≈ 3 mm, CAO) : doit rester ≤ au réel
fit        = 0.25;   // jeu pince/clavier (réduire à 0.1 si ça flotte)
rim_dz     = 0.45;   // le dessus réel du rebord est ~0.4 mm au-dessus de l'origine (CAO)
ports_x0   = 35;     // début du panneau USB-C + interrupteurs (bord arrière, depuis la face gauche)

// ---------- Pince (P1) ----------
clip_len = 31;    // longueur le long du bord arrière (s'arrête avant les ports !)
side_len = 78;    // longueur le long du bord gauche (vers l'avant)
wall     = 5.0;   // épaisseur des parois
lip_t    = 4.0;   // épaisseur des lèvres posées sur le rebord
lip_w    = 6.5;   // avancée des lèvres sur le rebord (< rim_*_w)
hook_t   = 4.0;   // épaisseur des crochets sous la marche
hook_d   = 1.9;   // avancée des crochets sous la marche (< ledge - 0.3)
boss_d   = 12;    // bossages des vis de serrage
boss_h   = 11;    // hauteur des bossages au-dessus du rebord
screw_rear_x = 15;   // vis de serrage arrière (X bureau)
screw_side_y = -48;  // vis de serrage latérale (Y bureau)
tab_y1   = 38;    // la patte arrière va jusqu'ici (Y)
tab_z0   = 9;     // dessous de la patte = dessus de la semelle du socle
tab_x1   = 34;    // largeur de la patte et de la semelle avant (reste à gauche des ports)

// ---------- Socle (P2) ----------
base_z0  = 1.0;   // dessous de la semelle (patins adhésifs de 3 mm, enfoncés de 2 mm)
base_y1  = 102;   // arrière de la semelle
foot_x0  = -60;   // la semelle s'élargit vers la gauche à l'arrière (anti-basculement)
foot_y0  = 64;
col_w    = 38;    // colonne : largeur X
col_d    = 24;    // colonne : profondeur Y
col_gap  = 3.0;   // jeu entre l'avant de la colonne et l'arrière du cadre

// ---------- Téléphone : Pixel 10 Pro Fold ouvert (Google : 155.2 x 150.4 x 5.2 mm) ----------
ph_w   = 150.4;   // largeur dépliée (charnière verticale au milieu)
ph_h   = 155.2;   // hauteur
ph_t   = 5.2;     // épaisseur dépliée (hors îlot photo, qui ne touche rien)
ph_r   = 9.0;     // rayon des coins (estimé)
gap    = 0.5;     // jeu latéral (par côté) ; +0.6 avec une coque fine
t_gap  = 0.5;     // jeu en épaisseur

// ---------- Cadre (P3) ----------
f_wall   = 3.2;   // parois latérales
lip_over = 2.2;   // recouvrement de l'écran par les lèvres avant (ne masque que la bordure)
f_lip_t  = 1.8;
leg      = 24;    // longueur des coins (laisse libres le port USB-C et les boutons)
ledge_in = 4.0;   // appui du dos du téléphone dans les coins
back_t   = 8.5;   // épaisseur du dos du cadre (le dos du téléphone est à w=0)
spoke_w  = 14;    // croix d'appui (charnière + milieu des deux moitiés)
disc_d   = 56;    // disque de pivot (frotte sur la tête de colonne)
latch_h  = 7.0;   // bloc des loquets au-dessus du téléphone

// ---------- Pivot ----------
tilt_deg = 70;    // angle écran / bureau
hub      = [18, 62, 154];   // centre du pivot (dos du téléphone) : X, Y, Z
head_t   = 12;    // épaisseur de la tête de colonne
m6_d     = 6.5;
m6_hex   = 10.4;  // tête H M6 (10 sur plats) + jeu
m6_head_h = 4.6;
wrench_d = 25;    // accès clé de 10 / douille à l'écrou nylstop

// ---------- Visserie ----------
m5_d = 5.4; m5_nut = 8.4; m5_nut_t = 4.4;
m4_d = 4.4; m4_nut = 7.4; m4_nut_t = 3.4;
m3_d = 3.3; m3_nut = 5.8; m3_nut_t = 2.6;

$fn = 64;

// =====================================================================
// Calculs du plan du téléphone
// =====================================================================
s_t = sin(tilt_deg); c_t = cos(tilt_deg);
U = [1, 0, 0];
V = [0, c_t, s_t];          // "haut" de l'écran
N = [0, -s_t, c_t];         // normale vers l'utilisateur
// Repère cadre : u = X, v = haut de l'écran, w = vers l'utilisateur, origine = dos du téléphone au centre
module at_phone(a = 0) {
    multmatrix([[U[0], V[0], N[0], hub[0]],
                [U[1], V[1], N[1], hub[1]],
                [U[2], V[2], N[2], hub[2]],
                [0, 0, 0, 1]]) rotate([0, 0, a]) children();
}
hw = ph_w / 2 + gap;   // demi-largeur intérieure
hh = ph_h / 2 + gap;   // demi-hauteur intérieure
ow = hw + f_wall;      // demi-largeur extérieure
oh = hh + f_wall;
front_w = ph_t + t_gap + f_lip_t;            // face avant des lèvres
sweep_r = sqrt(ow * ow + (hh + latch_h) * (hh + latch_h)) + 3;   // rayon balayé (+ marge)

// Repère clavier (plaque) -> bureau
module at_keyboard() { translate([0, 0, rear_h]) rotate([typing_deg, 0, 0]) children(); }

// =====================================================================
// P1 — Pince (écrite pour un coin "droit" puis mise en miroir)
//   repère plaque miroir : clavier en X<0, Y<0, Z=0 dessus du rebord
// =====================================================================
module rounded_box(x0, x1, y0, y1, z0, z1, r) {
    translate([0, 0, z0]) linear_extrude(z1 - z0)
        hull() {
            translate([x1 - r, y1 - r]) circle(r);
            translate([x0, y0]) square([x1 - r - x0, y1 - y0]);
            translate([x0, y0]) square([x1 - x0, y1 - r - y0]);
        }
}
module kb_keepout_r() {
    hull() {
        rounded_box(-400, fit - draft, -400, fit - draft, -0.01, fit + rim_dz, corner_r);
        rounded_box(-400, fit, -400, fit, -rim_h - fit, -rim_h - fit + 0.01, corner_r);
    }
    rounded_box(-400, 0.3 - ledge, -400, 0.3 - ledge, -60, -rim_h - fit, corner_r);
    rounded_box(-400, -rim_side_w, -400, -rim_rear_w, -1, 40, 2);
}
zb = -rim_h - fit - hook_t;   // bas des crochets (plaque)
zt = fit + rim_dz + lip_t;    // dessus des lèvres
xr = fit + wall;              // extérieur de la joue
yr = fit + wall;              // extérieur de la paroi arrière

module clip_c_r() {
    difference() {
        union() {
            translate([-clip_len, fit - draft, zb]) cube([clip_len + xr, wall + draft, zt - zb]);
            translate([fit - draft, -side_len, zb]) cube([wall + draft, side_len + yr, zt - zb]);
            translate([-clip_len, -lip_w, fit + rim_dz]) cube([clip_len + xr, lip_w + yr, lip_t]);
            translate([-lip_w, -side_len, fit + rim_dz]) cube([lip_w + xr, side_len + yr, lip_t]);
            translate([-clip_len, -hook_d, zb]) cube([clip_len + xr, hook_d + yr, hook_t]);
            translate([-hook_d, -side_len, zb]) cube([hook_d + xr, side_len + yr, hook_t]);
            // bossages des vis de serrage (au-dessus du rebord libre)
            // prolongés jusqu'à la joue : imprimés couchés, ils reposent ainsi sur le plateau
            for (p = screw_pts_r()) hull() {
                translate([p[0], p[1], fit + rim_dz]) cylinder(d = boss_d, h = boss_h);
                translate([xr - 1, p[1] - boss_d / 2, fit + rim_dz]) cube([1, boss_d, boss_h]);
            }
        }
        kb_keepout_r();
        zh = -rim_h - fit;
        rotate([90, 0, 90]) translate([0, 0, -clip_len - 1]) linear_extrude(clip_len + 10) {
            polygon([[-lip_w, fit + rim_dz], [-lip_w + 1.2, fit + rim_dz], [-lip_w, fit + rim_dz + 1.2]]);
            polygon([[-hook_d, zh], [-hook_d + 0.9, zh], [-hook_d, zh - 0.9]]);
        }
        rotate([90, 0, 0]) translate([0, 0, -side_len - 1]) linear_extrude(side_len + 10) {
            polygon([[-lip_w, fit + rim_dz], [-lip_w + 1.2, fit + rim_dz], [-lip_w, fit + rim_dz + 1.2]]);
            polygon([[-hook_d, zh], [-hook_d + 0.9, zh], [-hook_d, zh - 0.9]]);
        }
        // vis M4 de serrage : traversent le bossage et appuient sur le rebord
        for (p = screw_pts_r()) translate([p[0], p[1], 0]) {
            cylinder(d = m4_d, h = 40);
            // écrou M4 glissé par le côté extérieur, à mi-hauteur du bossage
            translate([0, 0, fit + rim_dz + boss_h / 2 - m4_nut_t / 2]) hull() {
                cylinder(d = m4_nut / cos(30), h = m4_nut_t, $fn = 6);
                translate(p[2] * 20) cylinder(d = m4_nut / cos(30), h = m4_nut_t, $fn = 6);
            }
        }
    }
}
// [x, y, direction d'insertion de l'écrou] en repère plaque miroir
function screw_pts_r() = [[-screw_rear_x, -lip_w / 2 + 0.2, [0, 1, 0]],
                          [-lip_w / 2 + 0.2, screw_side_y, [1, 0, 0]]];

// =====================================================================
// P1 complète, repère bureau
// =====================================================================
cheek_x0 = -(fit + wall);           // face extérieure de la joue gauche (bureau)
rear_y1 = fit + wall;               // face arrière de la paroi arrière (bureau)
zb_desk = rear_h + zb;              // bas des crochets au droit de la face arrière (≈ bureau)
// Prolongements vers le bureau, construits dans le repère incliné du clavier (repère plaque miroir)
module clip_ext_r() {
    // joue prolongée jusqu'au bureau (le bottom case est en retrait sous la marche)
    translate([fit, -side_len, -80]) cube([wall, side_len + yr, 80 + zb + 0.5]);
    // paroi arrière prolongée vers la patte
    translate([-clip_len, fit, -80]) cube([clip_len + xr, wall, 80 + zb + 0.5]);
}
module clip_part() {
    union() {
        mirror([1, 0, 0]) at_keyboard() clip_c_r();
        intersection() {
            mirror([1, 0, 0]) at_keyboard() clip_ext_r();
            translate([-500, -500, base_z0]) cube(1000);
        }
        // patte arrière (posée sur la semelle du socle, 2 vis M5)
        difference() {
            union() {
                translate([cheek_x0, tab_y0, tab_z0]) cube([tab_x1 - cheek_x0, tab_y1 - tab_y0, 9]);
                // goussets entre paroi arrière et patte
                for (x = [cheek_x0, tab_x1 - 5]) hull() {
                    translate([x, tab_y0, tab_z0]) cube([5, 3, zb_desk - tab_z0 + 14]);
                    translate([x, tab_y1 - 0.1, tab_z0]) cube([5, 0.1, 9]);
                }
            }
            for (p = tab_bolts()) translate([p[0], p[1], 0]) {
                cylinder(d = m5_d, h = 60);
                translate([0, 0, tab_z0 + 9]) cylinder(d = 10, h = 60);   // têtes de vis
            }
        }
    }
}
tab_y0 = 2.2;   // la patte reste derrière la paroi du clavier (qui recule de 0.85 mm en bas)
function tab_bolts() = [[8, 24], [24, 24]];

// =====================================================================
// P2 — Socle : semelle + colonne + tête de pivot
// =====================================================================
col_y0 = hub[1] + (back_t + col_gap) / s_t;   // avant de la colonne (derrière le plan du cadre)
col_x0 = hub[0] - col_w / 2;
head_c = hub - N * (back_t + head_t / 2);      // centre de la tête

module head_disc(extra = 0, recess = 0) {
    at_phone() translate([0, 0, -back_t - head_t - extra]) cylinder(d = disc_d, h = head_t + extra - recess);
}
module base_part() {
    difference() {
        union() {
            // semelle avant (sous la patte de la pince) + arrière élargie vers la gauche
            hull() {
                translate([cheek_x0 + wall + fit - 0.6, tab_y0, base_z0]) cube([tab_x1 - cheek_x0 - wall, 1, tab_z0 - base_z0]);
                translate([cheek_x0 + wall + fit - 0.6, foot_y0, base_z0]) cube([tab_x1 - cheek_x0 - wall, 1, tab_z0 - base_z0]);
            }
            hull() {
                translate([foot_x0, foot_y0, base_z0]) cube([tab_x1 - foot_x0, base_y1 - foot_y0, tab_z0 - base_z0]);
                translate([cheek_x0 + wall, foot_y0 - 25, base_z0]) cube([tab_x1 - cheek_x0 - wall, 1, tab_z0 - base_z0]);
            }
            // colonne + tête
            hull() {
                translate([col_x0, col_y0, base_z0]) cube([col_w, col_d, 1]);
                translate([col_x0, col_y0, hub[2] - 10]) cube([col_w, col_d, 10]);
                head_disc(0, 1.5);
            }
            // bossage frottant : seul contact avec le dos du cadre (le reste est 1.5 mm en retrait)
            head_disc();
            // goussets : avant (vers la pince) et gauche (vers la semelle élargie)
            hull() {
                translate([col_x0 + 4, tab_y1 + 2, base_z0]) cube([col_w - 8, 1, tab_z0 - base_z0]);
                translate([col_x0 + 4, col_y0, base_z0]) cube([col_w - 8, 1, 75]);
            }
            hull() {
                translate([foot_x0 + 8, col_y0 + 4, base_z0]) cube([1, col_d - 8, tab_z0 - base_z0]);
                translate([col_x0, col_y0 + 4, base_z0]) cube([1, col_d - 8, 85]);
            }
            hull() {
                translate([col_x0 + 4, base_y1 - 1, base_z0]) cube([col_w - 8, 1, tab_z0 - base_z0]);
                translate([col_x0 + 4, col_y0 + col_d - 1, base_z0]) cube([col_w - 8, 1, 60]);
            }
        }
        // passage du boulon M6 et accès clé à l'écrou (en losange : imprimable sans support)
        at_phone() {
            translate([0, 0, -back_t - head_t - 1]) cylinder(d = m6_d, h = head_t + 2);
            translate([0, 0, -back_t - head_t - 200]) rotate([0, 0, 45])
                cylinder(d = wrench_d, h = 200, $fn = 4);
        }
        // écrous M5 de la patte (sous la semelle)
        for (p = tab_bolts()) translate([p[0], p[1], 0]) {
            cylinder(d = m5_d, h = 30);
            translate([0, 0, base_z0 - 0.01]) cylinder(d = m5_nut / cos(30), h = m5_nut_t + 0.01, $fn = 6);
        }
        // logements des patins adhésifs (Ø12 x 2 mm)
        for (p = [[2, 10], [28, 10], [-52, 96], [28, 96], [-52, 70]])
            translate([p[0], p[1], base_z0 - 0.01]) cylinder(d = 12.6, h = 2);
    }
}

// =====================================================================
// P3 — Cadre (repère cadre : u, v, w ; dos du téléphone à w=0)
// =====================================================================
module rrect(w, h, r) { offset(r) offset(-r) square([2 * w, 2 * h], center = true); }
module phone_outline(g = 0) { rrect(ph_w / 2 + g, ph_h / 2 + g, ph_r + g); }
module frame_local() {
    difference() {
        union() {
            // anneau arrière (sous le bord du téléphone, ne le touche pas)
            translate([0, 0, -back_t]) linear_extrude(back_t - 1.5) difference() {
                rrect(ow, oh, ph_r + gap + f_wall);
                rrect(hw - 4, hh - 4, ph_r);
            }
            // croix d'appui (charnière + milieu des moitiés) et disque de pivot
            translate([0, 0, -back_t]) linear_extrude(back_t) {
                square([spoke_w, 2 * hh - 8], center = true);
                square([2 * hw - 8, spoke_w], center = true);
                circle(d = disc_d);
            }
            // coins : parois + lèvres avant + appuis du dos
            for (sx = [-1, 1], sy = [-1, 1]) corner(sx, sy);
            // blocs des loquets en haut
            for (sx = [-1, 1]) latch_block(sx);
        }
        // tête du boulon M6 noyée (hexagonale, il tourne avec le cadre)
        translate([0, 0, -m6_head_h]) cylinder(d = m6_hex / cos(30), h = m6_head_h + 1, $fn = 6);
        translate([0, 0, -back_t - 1]) cylinder(d = m6_d, h = back_t + 2);
        // le téléphone (jeux compris)
        translate([0, 0, 0]) linear_extrude(ph_t + t_gap) phone_outline(gap);
        // le haut reste ouvert pour glisser le téléphone
        translate([-hw, 0, 0]) cube([2 * hw, hh + 50, ph_t + t_gap]);
        // fenêtre avant : tout l'écran sauf lip_over sur le pourtour
        translate([0, 0, ph_t + t_gap - 0.01]) linear_extrude(20) phone_outline(gap - lip_over);
    }
}
// Coin (sx, sy) : parois sur `leg` mm dans les deux directions (en haut : seulement côté)
module corner(sx, sy) {
    top = sy > 0;
    intersection() {
        translate([0, 0, -back_t]) linear_extrude(back_t + front_w) difference() {
            rrect(ow, oh, ph_r + gap + f_wall);
            // appui du dos : ledge_in mm à l'intérieur du contour
        }
        union() {
            // bande verticale (le long du côté)
            translate([sx > 0 ? hw - ledge_in : -ow, sy > 0 ? hh - leg : -oh, -back_t]) cube([ow - hw + ledge_in, leg + (oh - hh), 50]);
            // bande horizontale (le long du bas) seulement pour les coins du bas
            if (!top) translate([sx > 0 ? hw - leg : -ow, -oh, -back_t]) cube([leg + (ow - hw), oh - hh + ledge_in, 50]);
        }
    }
}
// Bloc au-dessus du téléphone pour le pivot du loquet (chape)
latch_piv = [hw - 1.5, hh + latch_h / 2 + 0.3];   // axe dans la chape, extérieur fermé
module latch_block(sx) {
    difference() {
        translate([sx > 0 ? hw - 4 : -ow, hh - leg, -back_t]) cube([ow - hw + 4, leg + latch_h + 0.3, back_t + front_w + 1.6]);
        // fente du loquet (dans l'épaisseur du téléphone), ouverte vers l'intérieur
        translate([sx > 0 ? hw - 4.1 : -ow + 1.2, hh + 0.01, -0.01]) cube([ow - hw + 2.9, latch_h + 1, ph_t + t_gap + 0.4]);
        // axe M3 du loquet (traverse la chape)
        translate([sx * latch_piv[0], latch_piv[1], -back_t - 1]) cylinder(d = m3_d, h = 30);
        translate([sx * latch_piv[0], latch_piv[1], -back_t - 0.01]) cylinder(d = m3_nut / cos(30), h = m3_nut_t + 0.5, $fn = 6);
    }
}

// =====================================================================
// P4 — Loquet (pivote dans la chape, bloque le bord haut du téléphone)
// =====================================================================
latch_len = 22;
module latch_local() {
    difference() {
        hull() {
            cylinder(d = latch_h - 0.4, h = ph_t + t_gap);
            translate([-latch_len, -(latch_h - 0.4) / 2, 0]) cube([1, latch_h - 0.4, ph_t + t_gap]);
        }
        translate([0, 0, -1]) cylinder(d = m3_d, h = 20);
    }
}
module latches_in_frame() {
    for (sx = [-1, 1]) translate([sx * latch_piv[0], latch_piv[1], 0.1])
        mirror([sx > 0 ? 0 : 1, 0, 0]) latch_local();
}

// =====================================================================
// P5 — Molette de serrage (tête de vis M4 H noyée)
// =====================================================================
module knob() {
    difference() {
        union() {
            cylinder(d = 16, h = 8);
            for (a = [0:30:330]) rotate([0, 0, a]) translate([8, 0, 0]) cylinder(d = 2.4, h = 8);
        }
        translate([0, 0, -1]) cylinder(d = m4_d, h = 20);
        translate([0, 0, 4]) cylinder(d = 7.3 / cos(30), h = 10, $fn = 6);   // tête H M4 (7 sur plats)
    }
}

// =====================================================================
// Fantômes et contrôle du balayage
// =====================================================================
module phone_ghost() { linear_extrude(ph_t) phone_outline(0); }
module sweep_volume() {
    at_phone() translate([0, 0, -back_t]) cylinder(r = sweep_r, h = back_t + front_w, $fn = 180);
}

module frame_assembly(a) {
    at_phone(a) {
        frame_local();
        latches_in_frame();
    }
}

// =====================================================================
// Sorties
// =====================================================================
if (part == "assembly") {
    color("#2b2f36") clip_part();
    color("#3a3f4a") base_part();
    color("#e0e3e8") frame_assembly(frame_angle);
    if (show_ghosts) {
        %import("ref/k10_left_ghost.stl");
        %at_phone(frame_angle) translate([0, 0, 0.25]) phone_ghost();
    }
}
else if (part == "sweep_check") sweep_volume();
else if (part == "clip") clip_part();
else if (part == "base") base_part();
else if (part == "frame") at_phone() frame_local();
else if (part == "latch") latch_local();
else if (part == "knob") knob();
// Impression
else if (part == "clip_print") translate([0, 0, -cheek_x0]) rotate([0, -90, 0]) clip_part();
else if (part == "base_print") translate([0, 0, -base_z0]) base_part();
else if (part == "frame_print") translate([0, 0, back_t]) frame_local();
else if (part == "latch_print") latch_local();
else if (part == "knob_print") knob();
// Tranche de 9 mm de la pince (profil arrière) : à clipser sur le bord arrière avant la grande impression
else if (part == "fit_test") translate([0, 0, -22]) rotate([0, 90, 0]) intersection() {
    clip_c_r();
    translate([-31, -50, -50]) cube([9, 100, 100]);
}
