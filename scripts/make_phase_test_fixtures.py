"""Create controlled fixtures for docs/testing/phase_test_template.md.
Run with the project's dependencies installed: python scripts/make_phase_test_fixtures.py
Existing samples and keys are never overwritten. Only samples/phase_tests is managed.
"""
from pathlib import Path
import hashlib
import io
import json
import math
import struct
import sys
import wave

import numpy as np
from PIL import Image
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'samples' / 'phase_tests'


def wav(path, frames=44100, rate=44100, channels=1, silent=False):
    values = np.zeros(frames, dtype='<i2') if silent else (np.sin(np.arange(frames)*2*math.pi*440/rate)*12000).astype('<i2')
    if channels > 1:
        values = np.repeat(values[:, None], channels, axis=1)
    with wave.open(str(path), 'wb') as f:
        f.setparams((channels, 2, rate, frames, 'NONE', 'not compressed'))
        f.writeframes(values.tobytes())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    y,x=np.indices((256,256))
    rgb=np.stack([(x*3+y)%256,(x+y*5)%256,(x*7+y*11)%256],axis=-1).astype('uint8')
    Image.fromarray(rgb).save(OUT/'cover_rgb.png')
    Image.fromarray(np.concatenate([rgb,np.full((256,256,1),255,dtype='uint8')],axis=2)).save(OUT/'cover_rgba.png')
    Image.fromarray(rgb[:,:,0]).save(OUT/'cover_gray.png')
    Image.fromarray(rgb).save(OUT/'cover_rgb.jpg',quality=90)
    Image.fromarray(rgb[:128]).save(OUT/'mismatch_dimensions.png')
    Image.fromarray(np.bitwise_xor(rgb, np.uint8(128))).save(OUT/'unrelated_same_dimensions.png')
    Image.fromarray(np.zeros((8,8,3),dtype='uint8')).save(OUT/'tiny_cover.png')
    Image.fromarray(rgb[:16,:16]).save(OUT/'small_payload.png')
    wav(OUT/'cover_pcm16.wav')
    wav(OUT/'cover_silent.wav',silent=True)
    wav(OUT/'mismatch_duration.wav',frames=22050)
    wav(OUT/'mismatch_rate.wav',rate=22050)
    wav(OUT/'mismatch_channels.wav',channels=2)
    wav(OUT/'zero_frames.wav',frames=0)
    wav(OUT/'small_payload.wav',frames=256)
    for name in ['empty.txt','empty.png','empty.wav','empty.mp4']:
        (OUT/name).write_bytes(b'')
    for name in ['fake.png','fake.wav','fake.mp4','unsupported.bin','unsupported.pdf']:
        (OUT/name).write_bytes(b'This is plain text, not the media named by the extension.\n')
    (OUT/'unicode.txt').write_text('Hello Bob. Unicode: 中文 • café • 😀\nLine two.\n',encoding='utf-8')
    (OUT/'one_byte.txt').write_bytes(b'X')
    (OUT/'whitespace.txt').write_bytes(b' \n\t')
    (OUT/'sample.md').write_text('# Test payload\nMarkdown is carried as original bytes.\n')
    (OUT/'sample.csv').write_text('id,value\n1,alpha\n2,beta\n')
    (OUT/'sample.json').write_text('{"test": true, "value": 42}\n')
    (OUT/'invalid_json_payload.json').write_text('{not valid JSON; this is still a supported byte payload}\n')
    (OUT/'oversized_payload.txt').write_bytes(b'X'*(1024*1024))
    (OUT/'truncated_partial_sample.wav').write_bytes((OUT/'cover_pcm16.wav').read_bytes()[:-1])
    (OUT/'truncated_whole_frame.wav').write_bytes((OUT/'cover_pcm16.wav').read_bytes()[:-2])
    (OUT/'invalid_public.pem').write_text('not an RSA public key\n')
    public=rsa.generate_private_key(public_exponent=65537,key_size=2048).public_key()
    (OUT/'wrong_alice_public.pem').write_bytes(public.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    wrong_bob=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    (OUT/'wrong_bob_private.pem').write_bytes(wrong_bob.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    video_units=None
    try:
        sys.path.insert(0,str(ROOT/'backend'))
        from stego import video_lsb
        video_lsb._run_ffmpeg(['-f','lavfi','-i','color=c=blue:s=160x120:r=10:d=1','-f','lavfi','-i','sine=frequency=440:sample_rate=44100:duration=1','-map','0:v:0','-map','1:a:0','-c:v','mpeg4','-c:a','aac',str(OUT/'cover_with_audio.mp4')])
        video_lsb._run_ffmpeg(['-i',str(OUT/'cover_with_audio.mp4'),'-map','0:v:0','-c:v','copy','-an',str(OUT/'no_audio.mp4')])
        video_lsb._run_ffmpeg(['-f','lavfi','-i','sine=frequency=440:sample_rate=44100:duration=0.05','-c:a','libmp3lame','-b:a','32k',str(OUT/'small_payload.mp3')])
        video_lsb._run_ffmpeg(['-f','lavfi','-i','color=c=red:s=32x32:r=5:d=0.2','-c:v','mpeg4','-an',str(OUT/'small_payload.mp4')])
        audio,_=video_lsb.extract_audio_track((OUT/'cover_with_audio.mp4').read_bytes())
        with wave.open(io.BytesIO(audio),'rb') as f:
            video_units=f.getnframes()*f.getnchannels()
        (OUT/'video_audio_baseline.wav').write_bytes(audio)
    except Exception as exc:
        print('Video fixtures unavailable:',exc)
    units={'png':256*256*3,'wav':44100}
    if video_units is not None:units['video']=video_units
    for kind,n in units.items():
        for depth in [6,7,8]:
            size=((n-100)*(depth-1))//8+256
            (OUT/f'large_{kind}_needs_{depth}lsb.txt').write_bytes(b'L'*size)
    manifest={
        'manual_start_index':100,'cover_units':units,
        'notes':['Video cover capacity uses the decoded 44.1 kHz PCM16 audio track.','Large fixtures exceed the preceding depth even before overhead; verify actual fits in Review capacity.','wrong_alice_public.pem is unrelated to the app signing key.','Do not use fake media as decoder-negative evidence: supported file payloads are not validated as playable media.'],
        'files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='manifest.json'}}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Created fixtures:',OUT)
    print('Carrier units:',units)

if __name__=='__main__':main()
