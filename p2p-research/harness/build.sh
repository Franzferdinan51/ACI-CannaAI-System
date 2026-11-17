#!/bin/zsh
# Build the GQ harness APK on the Mac (manual javac/d8/aapt2 pipeline --
# no Gradle/Android Studio on this machine). Run from the harness dir.
set -e
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
export PATH=$JAVA_HOME/bin:/opt/homebrew/bin:$PATH
BT=~/Library/Android/sdk/build-tools/35.0.0
AJ=~/Library/Android/sdk/platforms/android-34/android.jar
SO=~/pppp-dig/libgqipcsdk.so

rm -rf build && mkdir -p build/classes build/apk/lib/arm64-v8a
cp $SO build/apk/lib/arm64-v8a/libgqipcsdk.so

javac -source 8 -target 8 -cp $AJ -d build/classes $(find src -name '*.java')
$BT/d8 --lib $AJ --output build $(find build/classes -name '*.class')

$BT/aapt2 link -o build/base.apk -I $AJ --manifest AndroidManifest.xml
cd build/apk
cp ../base.apk app.apk
zip -q app.apk -j ../classes.dex
# classes.dex must sit at zip root; the -j above flattens it in. Add lib tree:
mkdir -p lib/arm64-v8a && cp $SO lib/arm64-v8a/libgqipcsdk.so
zip -q -r app.apk lib
cd ../..
$BT/zipalign -f 4 build/apk/app.apk build/app-aligned.apk

if [ ! -f build/debug.keystore ]; then
  keytool -genkeypair -keystore build/debug.keystore -alias androiddebugkey \
    -keyalg RSA -keysize 2048 -validity 10000 -storepass android -keypass android \
    -dname "CN=Android Debug,O=Android,C=US" 2>/dev/null
fi
$BT/apksigner sign --ks build/debug.keystore --ks-pass pass:android \
  --key-pass pass:android --out build/gqharness.apk build/app-aligned.apk
$BT/apksigner verify build/gqharness.apk
echo "BUILT build/gqharness.apk"
