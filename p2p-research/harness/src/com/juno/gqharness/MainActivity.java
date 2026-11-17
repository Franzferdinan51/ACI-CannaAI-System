package com.juno.gqharness;

import android.app.Activity;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Log;
import android.widget.TextView;

import com.eternal.media.client.GqClient;
import com.eternal.media.client.GqProtocolHead;
import com.eternal.media.client.GqSdk;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/* GQ harness: replays the AC Infinity app's exact vendor-SDK call sequence
   against the genuine libgqipcsdk.so, with no phone involved:
     GqSdk.openLog(5)
     GqSdk.init(0 /*SY*, "Android_"+android_id, <account intstr>, false)
     new GqClient()                       (nativeCreate + auto-reconnect + cmd timeout)
     enable callbacks 0/1/4/5
     nativeConnect(handle, did, intstr + ":" + key, 122, null)
     nativeLiveStart(handle)              -> frames via _onNativeData type 1
     nativeSnapshotImg(handle, cb)        -> still via cmd result / type 4
   Credentials arrive over a loopback socket from the host feeder and are
   kept in memory only. Status output contains return codes and metadata
   only -- never credential values. */
public final class MainActivity extends Activity {
    private static final String TAG = "GQH";
    private static final int PORT = 18777;

    private File dir;
    private final AtomicLong liveBytes = new AtomicLong();
    private final AtomicInteger liveFrames = new AtomicInteger();
    private final AtomicInteger photoCount = new AtomicInteger();
    private final AtomicInteger subPhotoCount = new AtomicInteger();
    private volatile int snapCode = Integer.MIN_VALUE;
    private volatile byte[] snapBytes;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        TextView tv = new TextView(this);
        tv.setText("gq harness running");
        setContentView(tv);
        dir = getFilesDir();
        Thread t = new Thread(this::run, "gq-worker");
        t.setDaemon(true);
        t.start();
    }

    private synchronized void status(String line) {
        Log.i(TAG, line);
        try (BufferedWriter w = new BufferedWriter(new FileWriter(new File(dir, "status.txt"), true))) {
            w.write(System.currentTimeMillis() + " " + line);
            w.newLine();
        } catch (Exception ignored) {
        }
    }

    private void appendBytes(String name, byte[] data) {
        try (FileOutputStream fos = new FileOutputStream(new File(dir, name), true)) {
            fos.write(data);
        } catch (Exception e) {
            status("WRITE_FAIL " + name + " " + e);
        }
    }

    private void meta(String name, String line) {
        try (BufferedWriter w = new BufferedWriter(new FileWriter(new File(dir, name), true))) {
            w.write(line);
            w.newLine();
        } catch (Exception ignored) {
        }
    }

    private void run() {
        try {
            runInner();
        } catch (Throwable th) {
            status("FATAL " + th);
        }
        status("DONE");
    }

    private void runInner() throws Exception {
        // 1. Wait for credentials from the host feeder (loopback only).
        String did, intstr, key;
        try (ServerSocket ss = new ServerSocket(PORT, 1, InetAddress.getByName("127.0.0.1"))) {
            ss.setSoTimeout(300000);
            status("LISTENING port=" + PORT);
            try (Socket s = ss.accept();
                 BufferedReader r = new BufferedReader(new InputStreamReader(s.getInputStream()))) {
                String line = r.readLine();
                JSONObject j = new JSONObject(line);
                did = j.getString("did");
                intstr = j.getString("intstr");
                key = j.getString("key");
            }
        }
        status("CREDS received didLen=" + did.length() + " intstrLen=" + intstr.length() + " keyLen=" + key.length());

        // 2. SDK init, exactly as MainApplicationLifecycle does.
        String appId = "Android_" + Settings.Secure.getString(getContentResolver(), Settings.Secure.ANDROID_ID);
        GqSdk.openLog(5);
        int initRet = GqSdk.init(0, appId, intstr, false);
        status("INIT ret=" + initRet);
        if (initRet != 0) {
            return;
        }

        // 3. Client + callbacks.
        GqClient client = new GqClient();
        status("CREATE ok handleNonZero=" + (client.handle() != 0));
        GqClient.sink = new GqClient.Sink() {
            @Override
            public void onData(int type, GqProtocolHead head, byte[] data) {
                int len = data == null ? 0 : data.length;
                String hm = head == null ? "null" :
                        "st=" + (int) head.streamType + " enc=" + (int) head.encodeType
                                + " ft=" + (int) head.frameType + " file=" + (int) head.fileType
                                + " ch=" + (int) head.channel + " " + head.videoWidth + "x" + head.videoHeight
                                + " fs=" + head.frameSize + " ts=" + head.timestamp
                                + " sid=" + head.sessionId + " task=" + head.taskId;
                if (type == 1) {
                    int n = liveFrames.incrementAndGet();
                    liveBytes.addAndGet(len);
                    meta("frames_live.txt", n + " len=" + len + " " + hm);
                    if (data != null) {
                        appendBytes("stream_live.bin", data);
                    }
                } else if (type == 4 || type == 5) {
                    int n = photoCount.incrementAndGet();
                    if (type == 5) {
                        subPhotoCount.incrementAndGet();
                    }
                    meta("frames_photo.txt", "type=" + type + " n=" + n + " len=" + len + " " + hm);
                    status("PHOTO_DATA type=" + type + " n=" + n + " len=" + len);
                    if (data != null) {
                        appendBytes("photo_type" + type + "_" + n + ".jpg", data);
                    }
                } else {
                    meta("frames_misc.txt", "type=" + type + " len=" + len + " " + hm);
                    if (data != null) {
                        appendBytes("misc_type" + type + ".bin", data);
                    }
                }
            }

            @Override
            public void onCmdResult(Object cb, int code, byte[] data) {
                int len = data == null ? 0 : data.length;
                meta("cmd_results.txt", "code=" + code + " len=" + len + " cb=" + (cb == null ? "null" : cb.getClass().getName()));
                if (data != null && len > 0) {
                    appendBytes("cmd_result_" + code + "_" + len + ".bin", data);
                }
            }

            @Override
            public void onReconnect(long session, int a, int b) {
                status("RECONNECT cb session=" + session + " a=" + a + " b=" + b);
            }
        };
        client.enableCallbacks();
        status("CALLBACKS enabled 0,1,4,5");

        // 4. Connect, exactly as the app configures it:
        //    keyStr = intstr + ":" + key, enableLanSearch = 122, byServer = null.
        long t0 = System.currentTimeMillis();
        int connRet = client.connect(did, intstr + ":" + key, 122, null);
        long connMs = System.currentTimeMillis() - t0;
        status("CONNECT ret=" + connRet + " elapsedMs=" + connMs);
        if (connRet != 0) {
            status("CONNECT_FAILED code=" + connRet);
            client.destroy();
            GqSdk.cleanup();
            return;
        }
        status("CHECK ret=" + client.checkConnection());
        status("HEARTBEAT ret=" + client.heartbeat());

        // 5a. Snapshot BEFORE live (HD-photo lane order), wait for the
        //     type-4 photo data callback up to 45 s.
        CountDownLatch snapLatch = new CountDownLatch(1);
        GqClient.CmdSyncCallBack snapCb = (code, data) -> {
            snapCode = code;
            snapBytes = data;
            status("SNAP_CB code=" + code + " len=" + (data == null ? 0 : data.length));
            if (data != null && data.length > 0) {
                appendBytes("snapshot_cb.jpg", data);
            }
            snapLatch.countDown();
        };
        int snapRet = client.snapshotImg(snapCb);
        status("SNAPSHOT ret=" + snapRet);
        boolean snapArrived = snapLatch.await(10, TimeUnit.SECONDS);
        status("SNAPSHOT ack arrived=" + snapArrived + " code=" + snapCode);
        long photoDeadline = System.currentTimeMillis() + 45000;
        while (System.currentTimeMillis() < photoDeadline && photoCount.get() == 0) {
            Thread.sleep(500);
        }
        status("SNAPSHOT photoData count=" + photoCount.get());

        // Snapshot-only mode (MCP spectron_snapshot): skip the live
        // collect and the while-live second snapshot; go straight
        // main still -> sub still -> teardown.
        boolean snapshotOnly = "snapshot".equals(getIntent().getStringExtra("mode"));
        status("MODE snapshotOnly=" + snapshotOnly);

        // 5b. Live start; collect frames for up to 30 s.
        if (!snapshotOnly) {
        int liveRet = client.liveStart();
        status("LIVE_START ret=" + liveRet);
        long deadline = System.currentTimeMillis() + 30000;
        while (System.currentTimeMillis() < deadline) {
            if (liveFrames.get() >= 40 && liveBytes.get() > 200000) {
                break;
            }
            Thread.sleep(250);
        }
        status("LIVE_COLLECT frames=" + liveFrames.get() + " bytes=" + liveBytes.get());

        // 6. Snapshot again while live is running; wait for photo data.
        snapCode = Integer.MIN_VALUE;
        snapBytes = null;
        int photosBefore = photoCount.get();
        CountDownLatch snap2Latch = new CountDownLatch(1);
        GqClient.CmdSyncCallBack snap2Cb = (code, data) -> {
            snapCode = code;
            snapBytes = data;
            status("SNAP2_CB code=" + code + " len=" + (data == null ? 0 : data.length));
            if (data != null && data.length > 0) {
                appendBytes("snapshot2_cb.jpg", data);
            }
            snap2Latch.countDown();
        };
        int snapRet2 = client.snapshotImg(snap2Cb);
        status("SNAPSHOT2 ret=" + snapRet2);
        boolean snap2Arrived = snap2Latch.await(10, TimeUnit.SECONDS);
        status("SNAPSHOT2 ack arrived=" + snap2Arrived + " code=" + snapCode);
        long photo2Deadline = System.currentTimeMillis() + 45000;
        while (System.currentTimeMillis() < photo2Deadline && photoCount.get() <= photosBefore) {
            Thread.sleep(500);
        }
        status("SNAPSHOT2 photoData count=" + photoCount.get());
        }

        CountDownLatch subLatch = new CountDownLatch(1);
        GqClient.CmdSyncCallBack subCb = (code, data) -> {
            status("SUBSNAP_CB code=" + code + " len=" + (data == null ? 0 : data.length));
            if (data != null && data.length > 0) {
                appendBytes("sub_snapshot_cb.jpg", data);
            }
            subLatch.countDown();
        };
        int subRet = client.subSnapshotImg(0, subCb);
        status("SUBSNAPSHOT ret=" + subRet);
        boolean subArrived = subLatch.await(20, TimeUnit.SECONDS);
        status("SUBSNAPSHOT ack arrived=" + subArrived);
        long subDeadline = System.currentTimeMillis() + 45000;
        while (System.currentTimeMillis() < subDeadline && subPhotoCount.get() == 0) {
            Thread.sleep(500);
        }
        status("SUBSNAPSHOT photoData type5count=" + subPhotoCount.get() + " totalPhotos=" + photoCount.get());

        // 7. Teardown.
        if (!snapshotOnly) {
            status("LIVE_STOP ret=" + client.liveStop());
        }
        status("DISCONNECT ret=" + client.disconnect());
        client.destroy();
        status("CLEANUP ret=" + GqSdk.cleanup());
    }
}
