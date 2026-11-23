#!/bin/sh
# Build the standalone receive adapter with Android SDK 35 and a local development key.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
sdk=${ANDROID_HOME:?Set ANDROID_HOME to the Android SDK}
tools="$sdk/build-tools/35.0.0"
platform="$sdk/platforms/android-35/android.jar"
out=${1:-"$here/build/Pocket-UVPRO.apk"}
mkdir -p "$(dirname "$out")"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir "$work/classes"
javac -source 8 -target 8 -classpath "$platform" -d "$work/classes" "$here"/src/org/pocketrevival/uvpro/*.java
jar cf "$work/classes.jar" -C "$work/classes" .
"$tools/d8" --min-api 30 --lib "$platform" --output "$work" "$work/classes.jar"
"$tools/aapt2" link -I "$platform" --manifest "$here/AndroidManifest.xml" -o "$work/raw.apk"
(cd "$work" && zip -q raw.apk classes.dex)
"$tools/zipalign" -f 4 "$work/raw.apk" "$work/aligned.apk"
key=${POCKET_ANDROID_DEBUG_KEY:-"$HOME/.android/pocket-uvpro-debug.p12"}
if [ ! -e "$key" ]; then
    mkdir -p "$(dirname "$key")"
    (umask 077 && keytool -genkeypair -storetype PKCS12 -keystore "$key" -storepass android -keypass android -alias pocket-debug -keyalg RSA -keysize 2048 -validity 3650 -dname CN=Pocket-Debug)
fi
"$tools/apksigner" sign --ks "$key" --ks-pass pass:android --ks-key-alias pocket-debug --out "$out" "$work/aligned.apk"
"$tools/apksigner" verify --verbose "$out"
