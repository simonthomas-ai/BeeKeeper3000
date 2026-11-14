#!/bin/bash
# Baut die Android-App „Hornet3000 Station“ OHNE Gradle/Android Studio – nur mit den Debian/Ubuntu-Paketen
#   sudo apt install default-jdk-headless aapt apksigner zipalign dalvik-exchange android-sdk-platform-23
# Aufruf (im Ordner android/):   ./build.sh [Schlüsselspeicher.keystore Passwortdatei]
#
# Umgebungsvariablen:
#   ANDROID_JAR   android.jar für aapt (Vorgabe: /usr/lib/android-sdk/platforms/android-23/android.jar)
#   LINT_JAR      OPTIONAL die android.jar einer ALTEN Android-Version (z. B. API 8, Android 2.2). Mit ihr wird der Quelltext
#                 übersetzt: Jede Funktion, die es dort nicht gibt, ist ein Übersetzungsfehler – das ist die Prüfung,
#                 dass die App wirklich auf alten Geräten läuft. Ohne LINT_JAR wird gegen ANDROID_JAR übersetzt (keine
#                 Alters-Prüfung, das Skript sagt es laut).
#   MIN_SDK       Vorgabe 8
# Ergebnis: build/Hornet3000-Station-<Version>.apk  (signiert mit v1 + v2) und die Prüfausgaben.
set -euo pipefail
cd "$(dirname "$0")"

ANDROID_JAR="${ANDROID_JAR:-/usr/lib/android-sdk/platforms/android-23/android.jar}"
LINT_JAR="${LINT_JAR:-}"
MIN_SDK="${MIN_SDK:-8}"
TARGET_SDK=28
VERSION="$(sed -n 's/^__version__ *= *"\(.*\)"/\1/p' ../hornet/__init__.py)"
[ -n "$VERSION" ] || { echo "Version nicht gefunden"; exit 1; }
IFS=. read -r MA MI PA <<< "$VERSION"
VERSIONCODE=$(( MA * 10000 + MI * 100 + ${PA:-0} ))
OUT="build"
APK="$OUT/Hornet3000-Station-$VERSION.apk"

for t in javac aapt zipalign apksigner dalvik-exchange keytool; do
  command -v "$t" >/dev/null || { echo "Werkzeug fehlt: $t (siehe Kopf dieser Datei)"; exit 1; }
done
[ -f "$ANDROID_JAR" ] || { echo "android.jar nicht gefunden: $ANDROID_JAR"; exit 1; }

rm -rf "$OUT"; mkdir -p "$OUT/classes" "$OUT/assets"
sed -e "s/@VERSIONCODE@/$VERSIONCODE/" -e "s/@VERSION@/$VERSION/" AndroidManifest.xml > "$OUT/AndroidManifest.xml"
cp ../web/assets/alarm.wav "$OUT/assets/alarm.wav"

# 1) Quelltext übersetzen (Java 8-Sprachstand, ohne Lambdas – der Dex-Umsetzer kennt keine; Klassenbibliothek = Android)
COMPILE_JAR="${LINT_JAR:-$ANDROID_JAR}"
if [ -z "$LINT_JAR" ]; then echo "HINWEIS: ohne LINT_JAR keine Prüfung auf alte Android-Versionen"; fi
javac -source 8 -target 8 -Xlint:all -Xlint:-options -Xlint:-deprecation -Werror -encoding UTF-8 \
      -bootclasspath "$COMPILE_JAR" -d "$OUT/classes" $(find src -name '*.java')

# 2) Dex-Datei
dalvik-exchange --dex --min-sdk-version="$MIN_SDK" --output="$OUT/classes.dex" "$OUT/classes"

# 3) Ressourcen + Manifest + Assets zu einer APK ohne Code
aapt package -f -M "$OUT/AndroidManifest.xml" -S res -A "$OUT/assets" -I "$ANDROID_JAR" \
     --min-sdk-version "$MIN_SDK" --target-sdk-version "$TARGET_SDK" -F "$OUT/unsigned.apk"
( cd "$OUT" && aapt add -f unsigned.apk classes.dex >/dev/null )

# 4) ausrichten und signieren
zipalign -f 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
KS="${1:-}"; PW="${2:-}"
if [ -z "$KS" ]; then
  KS="$OUT/test-only.keystore"; PW="$OUT/test-only.pass"
  echo "HINWEIS: kein Schlüsselspeicher angegeben – Wegwerf-Schlüssel nur zum Ausprobieren (Updates über einen anderen Schlüssel sind später nicht möglich)"
  head -c 18 /dev/urandom | base64 | tr -d '/+=' > "$PW"
  keytool -genkeypair -keystore "$KS" -storepass:file "$PW" -keypass:file "$PW" -alias hornet3000 -keyalg RSA -keysize 2048 \
          -validity 10000 -dname "CN=Hornet3000 Station (Test), O=Hornet3000" >/dev/null 2>&1
fi
HN_KS_PASS="$(head -n1 "$PW")"; export HN_KS_PASS          # über die Umgebung statt Befehlszeile: nicht in der Prozessliste sichtbar
apksigner sign --ks "$KS" --ks-key-alias hornet3000 --ks-pass env:HN_KS_PASS --key-pass env:HN_KS_PASS \
         --min-sdk-version "$MIN_SDK" --v1-signing-enabled true --v2-signing-enabled true --out "$APK" "$OUT/aligned.apk"

# 5) prüfen
apksigner verify --verbose --min-sdk-version "$MIN_SDK" "$APK"
aapt dump badging "$APK" | grep -E "^(package|sdkVersion|targetSdkVersion|uses-permission|application-label:|launchable)" || true
echo "FERTIG: $APK ($(stat -c %s "$APK") Bytes)"
