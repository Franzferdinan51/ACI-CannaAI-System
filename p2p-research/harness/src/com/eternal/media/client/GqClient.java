package com.eternal.media.client;

/* Minimal re-declaration of the app's GqClient JNI facade (decompiled from
   com.eternal.acinfinity v2.1.1, classes11.dex). Only the natives and the
   native->Java callback entry points needed for connect + live + snapshot
   are declared, with names/signatures/static-ness identical to the app so
   the genuine libgqipcsdk.so binds and calls back exactly as it does for
   the real app.

   Callback types (from the app): 0=CMD, 1=LIVE, 2=PLAYBACK, 3=DOWNLOAD,
   4=PHOTO, 5=SUB_PHOTO. Native calls back into:
     _onNativeData(int, GqProtocolHead, byte[])   (IL...;[B)V
     _onNativeCmdResult(Object, int, byte[])      (Ljava/lang/Object;I[B)V
     _onNativeReconnect(long, int, int)           (JII)V            */
public final class GqClient {

    public interface CmdSyncCallBack {
        void onResult(int i, byte[] bArr);
    }

    public interface Sink {
        void onData(int type, GqProtocolHead head, byte[] data);

        void onCmdResult(Object cb, int code, byte[] data);

        void onReconnect(long session, int a, int b);
    }

    public static volatile Sink sink;

    private final long handle;

    public GqClient() {
        long h = nativeCreate();
        if (h == 0) {
            throw new IllegalStateException("nativeCreate failed");
        }
        this.handle = h;
        // Mirror the app constructor: auto-reconnect on, cmd timeout 10 s.
        nativeSetAutoReconnect(h, true, -1);
        nativeSetCmdTimeout(h, 10000);
    }

    public long handle() {
        return handle;
    }

    public void enableCallbacks() {
        nativeSetCallbackEnabled(handle, 0, true);
        nativeSetCallbackEnabled(handle, 1, true);
        nativeSetCallbackEnabled(handle, 4, true);
        nativeSetCallbackEnabled(handle, 5, true);
    }

    public int connect(String did, String keyStr, int enableLanSearch, String byServerString) {
        return nativeConnect(handle, did, keyStr, enableLanSearch, byServerString);
    }

    public int checkConnection() {
        return nativeCheckConnection(handle);
    }

    public int heartbeat() {
        return nativeHeartbeat(handle);
    }

    public int liveStart() {
        return nativeLiveStart(handle);
    }

    public int liveStop() {
        return nativeLiveStop(handle);
    }

    public int snapshotImg(CmdSyncCallBack cb) {
        return nativeSnapshotImg(handle, cb);
    }

    public int subSnapshotImg(int i, CmdSyncCallBack cb) {
        return nativeSubSnapshotImg(handle, i, cb);
    }

    public int disconnect() {
        return nativeDisconnect(handle);
    }

    public void destroy() {
        nativeDestroy(handle);
    }

    // ---- native -> Java entry points (exact names/signatures) ----

    void _onNativeData(int i, GqProtocolHead head, byte[] bArr) {
        Sink s = sink;
        if (s != null) {
            s.onData(i, head, bArr);
        }
    }

    void _onNativeCmdResult(Object obj, int i, byte[] bArr) {
        if (obj instanceof CmdSyncCallBack) {
            ((CmdSyncCallBack) obj).onResult(i, bArr);
        }
        Sink s = sink;
        if (s != null) {
            s.onCmdResult(obj, i, bArr);
        }
    }

    void _onNativeReconnect(long j, int i, int i2) {
        Sink s = sink;
        if (s != null) {
            s.onReconnect(j, i, i2);
        }
    }

    // ---- JNI natives (signatures identical to the app) ----

    private native long nativeCreate();

    private static native int nativeCheckConnection(long j);

    private static native int nativeConnect(long j, String str, String str2, int i, String str3);

    private static native void nativeDestroy(long j);

    private static native int nativeDisconnect(long j);

    private static native int nativeHeartbeat(long j);

    private static native int nativeLiveStart(long j);

    private static native int nativeLiveStop(long j);

    private static native void nativeSetAutoReconnect(long j, boolean z, int i);

    private static native void nativeSetCallbackEnabled(long j, int i, boolean z);

    private static native void nativeSetCmdTimeout(long j, int i);

    private static native int nativeSnapshotImg(long j, CmdSyncCallBack cmdSyncCallBack);

    private static native int nativeSubSnapshotImg(long j, int i, CmdSyncCallBack cmdSyncCallBack);
}
