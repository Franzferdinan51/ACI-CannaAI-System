package com.eternal.media.client;

/* Minimal re-declaration of the app's GqSdk JNI facade (decompiled from
   com.eternal.acinfinity v2.1.1). Same package/class/method signatures so the
   genuine libgqipcsdk.so binds its Java_* JNI symbols to these methods. */
public final class GqSdk {
    static {
        System.loadLibrary("gqipcsdk");
    }

    private GqSdk() {
    }

    public static synchronized int init(int clientType, String appId, String intstr, boolean z) {
        return nativeInit(clientType, appId, intstr, z);
    }

    public static synchronized int cleanup() {
        return nativeCleanup();
    }

    public static void openLog(int i) {
        nativeOpenLog(i);
    }

    private static native int nativeCleanup();

    private static native int nativeInit(int i, String str, String str2, boolean z);

    private static native void nativeOpenLog(int i);
}
