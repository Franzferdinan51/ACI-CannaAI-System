package com.eternal.media.client;

import java.util.Arrays;

/* Faithful re-declaration of the app's GqProtocolHead (decompiled from
   com.eternal.acinfinity v2.1.1, classes11.dex). The vendor native library
   constructs this object from JNI with the exact constructor signature
   (BBBBBIIIJII)V and reads/writes these fields by name. */
public final class GqProtocolHead {
    public final byte channel;
    public final byte encodeType;
    public final byte fileType;
    public byte[] frame;
    public final int frameSize;
    public final byte frameType;
    public final int sessionId;
    public final byte streamType;
    public final int taskId;
    public final long timestamp;
    public final int videoHeight;
    public final int videoWidth;

    GqProtocolHead(byte b, byte b2, byte b3, byte b4, byte b5, int i, int i2, int i3, long j, int i4, int i5) {
        this.streamType = b;
        this.encodeType = b2;
        this.frameType = b3;
        this.fileType = b4;
        this.channel = b5;
        this.videoWidth = i;
        this.videoHeight = i2;
        this.frameSize = i3;
        this.timestamp = j;
        this.sessionId = i4;
        this.taskId = i5;
    }

    public String toString() {
        return "GqProtocolHead{streamType=" + ((int) this.streamType) + ", encodeType=" + ((int) this.encodeType) + ", frameType=" + ((int) this.frameType) + ", fileType=" + ((int) this.fileType) + ", channel=" + ((int) this.channel) + ", videoWidth=" + this.videoWidth + ", videoHeight=" + this.videoHeight + ", frameSize=" + this.frameSize + ", timestamp=" + this.timestamp + ", sessionId=" + this.sessionId + ", taskId=" + this.taskId + ", frame=" + Arrays.toString(this.frame) + '}';
    }
}
