import struct
import numpy as np

ATH_FFT_SAMPLE_HT20      = 1
ATH_FFT_SAMPLE_HT20_40   = 2
SPECTRAL_HT20_NUM_BINS    = 56
SPECTRAL_HT20_40_NUM_BINS = 128
TLV_HDR = struct.Struct(">BH")

def parse_frames(raw: bytes):
    i = 0; n = len(raw)
    while i + TLV_HDR.size <= n:
        tlv_type, tlv_len = TLV_HDR.unpack_from(raw, i); i += TLV_HDR.size
        if tlv_len <= 0 or i + tlv_len > n: break
        payload = raw[i:i+tlv_len]; i += tlv_len

        if tlv_type == ATH_FFT_SAMPLE_HT20:
            if tlv_len < (1+2+1+1+2+1+1+8+SPECTRAL_HT20_NUM_BINS): continue
            off=0
            max_exp = payload[off]; off+=1
            (freq,) = struct.unpack_from(">H", payload, off); off+=2
            (rssi,) = struct.unpack_from("b", payload, off); off+=1
            (noise,) = struct.unpack_from("b", payload, off); off+=1
            (max_mag,) = struct.unpack_from(">H", payload, off); off+=2
            max_index = payload[off]; off+=1
            bitmap_weight = payload[off]; off+=1
            (tsf,) = struct.unpack_from(">Q", payload, off); off+=8
            bins = np.frombuffer(payload, dtype=np.uint8, count=SPECTRAL_HT20_NUM_BINS, offset=off).astype(np.float32)
            yield {"type":"HT20","freq":int(freq),"tsf":int(tsf),"rssi":int(rssi),"noise":int(noise),
                   "max_mag":int(max_mag),"max_index":int(max_index),"bitmap_weight":int(bitmap_weight),
                   "max_exp":int(max_exp),"bins":bins}

        elif tlv_type == ATH_FFT_SAMPLE_HT20_40:
            if tlv_len < (1+2+1+1+8+1+1+2+2+1+1+1+1+SPECTRAL_HT20_40_NUM_BINS): continue
            off=0
            chan_type = payload[off]; off+=1
            (freq,) = struct.unpack_from(">H", payload, off); off+=2
            (lower_rssi,) = struct.unpack_from("b", payload, off); off+=1
            (upper_rssi,) = struct.unpack_from("b", payload, off); off+=1
            (tsf,) = struct.unpack_from(">Q", payload, off); off+=8
            (lower_noise,) = struct.unpack_from("b", payload, off); off+=1
            (upper_noise,) = struct.unpack_from("b", payload, off); off+=1
            (lower_max_mag,) = struct.unpack_from(">H", payload, off); off+=2
            (upper_max_mag,) = struct.unpack_from(">H", payload, off); off+=2
            lower_max_index = payload[off]; off+=1
            upper_max_index = payload[off]; off+=1
            lower_bw = payload[off]; off+=1
            upper_bw = payload[off]; off+=1
            max_exp = payload[off]; off+=1
            bins = np.frombuffer(payload, dtype=np.uint8, count=SPECTRAL_HT20_40_NUM_BINS, offset=off).astype(np.float32)
            yield {"type":"HT40","freq":int(freq),"tsf":int(tsf),
                   "lower_rssi":int(lower_rssi),"upper_rssi":int(upper_rssi),
                   "lower_noise":int(lower_noise),"upper_noise":int(upper_noise),
                   "lower_max_mag":int(lower_max_mag),"upper_max_mag":int(upper_max_mag),
                   "lower_max_index":int(lower_max_index),"upper_max_index":int(upper_max_index),
                   "max_exp":int(max_exp),"bins":bins,"chan_type":int(chan_type)}
