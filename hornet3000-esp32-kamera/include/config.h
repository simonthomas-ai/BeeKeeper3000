// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
// Hornet3000 ESP32-Kamera – Einstellungen zur Übersetzungszeit. KEINE Zugangsdaten hier eintragen:
// WLAN und Zugangsschlüssel werden im Einrichtungs-WLAN der Kamera gesetzt und im Flash (NVS) gespeichert.
#pragma once

#define FW_VERSION "1.0.0"

// Bild
#define CAM_FRAME_SIZE FRAMESIZE_VGA  // 640x480; SVGA (800x600) ist möglich, braucht mehr Bandbreite und WLAN-Güte
#define CAM_JPEG_QUALITY 12           // 4 (beste) … 63 (schlechteste); 10–14 ist ein guter Bereich
#define CAM_VFLIP 0
#define CAM_HMIRROR 0
#define STREAM_MAX_FPS 8              // Obergrenze der Übertragung; schont WLAN und Wärme
#define STREAM_PORT 81

// Einrichtungs-WLAN der Kamera (nur wenn noch nichts eingerichtet ist oder das WLAN dreimal in Folge nicht erreichbar war)
#define AP_PASSWORD ""                // leer = beim ersten Einrichten zufällig erzeugt, im Flash gespeichert, auf der seriellen Schnittstelle angezeigt
#define PORTAL_TIMEOUT_S 600          // danach Neustart und neuer Versuch mit den gespeicherten Daten
#define WIFI_CONNECT_TIMEOUT_S 25
#define WIFI_BOOTS_BEFORE_PORTAL 3

// Selbstheilung
#define WDT_TIMEOUT_S 30
#define WIFI_DOWN_REBOOT_S 300        // so lange ohne WLAN, dann Neustart
#define MIN_FREE_HEAP 20000           // darunter Neustart
#define AUTO_REBOOT_HOURS 168         // geplanter Neustart (7 Tage), nur wenn gerade nicht gestreamt wird; 0 = aus
#define CAM_ERRORS_BEFORE_REINIT 10

// Schutz des Zugangsschlüssels
#define AUTH_MAX_FAILS 5
#define AUTH_WINDOW_MS 60000
#define AUTH_LOCK_MS 60000

// Kamera-Anschlüsse AI-Thinker ESP32-CAM
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22
#define FLASH_LED_GPIO_NUM 4          // helle LED; bleibt immer aus (Strom, Wärme, Bienen)
