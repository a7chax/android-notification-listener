"""Build the tiny companion with Android SDK tools; no Gradle downloads required."""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"


def run(*args):
    print("Running " + Path(str(args[0])).name, file=sys.stderr, flush=True)
    subprocess.run([str(a) for a in args], check=True, stdout=sys.stderr)


def version(path):
    return tuple(int(n) for n in path.name.replace("android-", "").split(".") if n.isdigit())


def main():
    sdk = Path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
               or Path.home() / "Android" / "Sdk")
    tools = sorted((sdk / "build-tools").glob("*"), key=version)
    platforms = sorted((sdk / "platforms").glob("android-*"), key=version)
    if not tools or not platforms:
        raise RuntimeError("Install Android SDK build-tools and platform 35+; set ANDROID_HOME.")
    tools = tools[-1]
    android = platforms[-1] / "android.jar"
    BUILD.mkdir(exist_ok=True)
    classes, dex, generated = BUILD / "classes", BUILD / "dex", BUILD / "generated"
    for folder in (classes, dex, generated):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir()
    unsigned, aligned = BUILD / "unsigned.apk", BUILD / "aligned.apk"
    resources = BUILD / "resources.zip"
    run(tools / "aapt2", "compile", "--dir", ROOT / "android" / "res", "-o", resources)
    run(tools / "aapt2", "link", "-o", unsigned, "-I", android,
        "--manifest", ROOT / "android" / "AndroidManifest.xml", "--java", generated, resources)
    sources = sorted((ROOT / "android" / "src").rglob("*.java")) + sorted(generated.rglob("*.java"))
    run("javac", "-encoding", "UTF-8", "-source", "8", "-target", "8", "-Xlint:-options",
        "-classpath", android, "-d", classes, *sources)
    run(tools / "d8", "--lib", android, "--min-api", "26", "--output", dex,
        *sorted(classes.rglob("*.class")))
    with zipfile.ZipFile(unsigned, "a", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dex.glob("*.dex")):
            archive.write(path, path.name)
    run(tools / "zipalign", "-f", "4", unsigned, aligned)
    key = BUILD / "debug.keystore"
    if not key.exists():
        run("keytool", "-genkeypair", "-noprompt", "-keystore", key,
            "-storepass", "android", "-keypass", "android", "-alias", "androiddebugkey",
            "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
            "-dname", "CN=Local Notification Bridge,O=Development,C=ID")
    apk = BUILD / "notification-bridge.apk"
    run(tools / "apksigner", "sign", "--ks", key, "--ks-pass", "pass:android",
        "--key-pass", "pass:android", "--out", apk, aligned)
    run(tools / "apksigner", "verify", "--verbose", apk)
    print(f"Built {apk}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Build error: {exc}", file=sys.stderr)
        sys.exit(1)
