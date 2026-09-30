"""Check template baselines through Flask API with isolated temporary keys.
Run from the repository root with project dependencies installed.
Does not modify application keys or fill manual observations.
"""
from pathlib import Path
import base64
import io
import json
import re
import sys
import tempfile
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app import app
from stego import crypto_utils, pipeline, image_lsb
from stego.bitstream import StegoStream

F=ROOT/'samples/phase_tests'
rows=[]
failures=[]


def check(id, fn):
    try:
        details=fn()
        rows.append({'id':id,'status':'passed','details':details})
    except Exception as exc:
        rows.append({'id':id,'status':'failed','error':str(exc),'traceback':traceback.format_exc()})
        failures.append(id)
        print('FAIL',id,str(exc),flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='stego_reference_keys_') as folder:
        old=(crypto_utils.KEY_DIR,crypto_utils.PRIVATE_KEY_PATH,crypto_utils.PUBLIC_KEY_PATH)
        crypto_utils.KEY_DIR=Path(folder)
        crypto_utils.PRIVATE_KEY_PATH=Path(folder)/'private_key.pem'
        crypto_utils.PUBLIC_KEY_PATH=Path(folder)/'public_key.pem'
        try:
            run()
        finally:
            crypto_utils.KEY_DIR,crypto_utils.PRIVATE_KEY_PATH,crypto_utils.PUBLIC_KEY_PATH=old
    output={'scope':'Backend API checks with isolated ephemeral keys; not GUI/manual execution results.','passed':len(rows)-len(failures),'failed':len(failures),'checks':rows}
    (ROOT/'docs/testing/reference_checks.json').write_text(json.dumps(output,indent=2)+'\n')
    print('Reference checks:',output['passed'],'passed;',output['failed'],'failed',flush=True)
    if failures:raise SystemExit(1)


def run():
    c=app.test_client();public=c.get('/api/keys/public').get_json()['public_key_pem']
    c.get('/api/keys') # create only isolated Bob key
    js=(ROOT/'frontend/app.js').read_text()
    short=re.search(r'\$\("short-text"\).*?value="([^"]+)"',js)[1]
    long=re.search(r'\$\("long-text"\).*?value="([^"]+)"',js)[1]
    covers={'PNG':('image',F/'cover_rgb.png'),'WAV':('audio',F/'cover_pcm16.wav'),'MP4':('video',F/'cover_with_audio.mp4')}
    payloads=[('text',short.encode(),None),('text',long.encode(),None),('text',(F/'unicode.txt').read_bytes(),None),('file',(ROOT/'samples/text/sample-001.txt').read_bytes(),'sample-001.txt'),('file',(F/'sample.md').read_bytes(),'sample.md'),('file',(F/'sample.csv').read_bytes(),'sample.csv'),('file',(F/'sample.json').read_bytes(),'sample.json'),('image',(F/'small_payload.png').read_bytes(),'small_payload.png'),('audio',(F/'small_payload.wav').read_bytes(),'small_payload.wav'),('audio',(F/'small_payload.mp3').read_bytes(),'small_payload.mp3'),('video',(F/'small_payload.mp4').read_bytes(),'small_payload.mp4')]
    baseline={}

    def inputs(kind,cover,p,depth,offset=100,**extras):
        payload_type,data,name=p
        form={'cover_type':kind,'num_lsb':str(depth),'start_mode':'manual','manual_offset':str(offset),'hash_algorithm':'SHA-256','media_id':'phase-reference','cover_file':(io.BytesIO(cover.read_bytes()),cover.name),'payload_type':payload_type}
        if name is None:form['payload_text']=data.decode()
        else:form['payload_file']=(io.BytesIO(data),name)
        form.update(extras);return form

    def decode(kind,blob,depth=1,offset=100,key=public,**extras):
        form={'cover_type':kind,'num_lsb':str(depth),'start_mode':'manual','manual_offset':str(offset),'public_key_pem':key,'stego_file':(io.BytesIO(blob),{'image':'stego.png','audio':'stego.wav','video':'stego.mkv'}[kind])}
        form.update(extras)
        return c.post('/api/decode',data=form).get_json()

    def roundtrip(cover_name,p,depth=1,save=False,hash_algorithm='SHA-256'):
        kind,cover=covers[cover_name]
        prep=c.post('/api/prepare',data=inputs(kind,cover,p,depth,hash_algorithm=hash_algorithm)).get_json()
        assert prep.get('fits'),prep
        enc=c.post('/api/encode',data=inputs(kind,cover,p,depth,hash_algorithm=hash_algorithm)).get_json()
        assert 'error' not in enc,enc
        blob=base64.b64decode(enc['stego_base64'])
        dec=decode(kind,blob,depth)
        assert dec.get('verdict')=='Authentic',dec
        assert all(value=='Passed' for value in dec['evidence']['checks'].values()),dec
        assert base64.b64decode(dec['data_base64'])==p[1]
        comp=c.post('/api/compare',data={'cover_type':kind,'original_file':(io.BytesIO(cover.read_bytes()),cover.name),'stego_file':(io.BytesIO(blob),enc['stego_filename'])}).get_json()
        assert 'error' not in comp,comp
        assert comp['max_absolute_difference']<=2**depth-1,comp
        if save:baseline[cover_name]=(blob,p,enc)
        return {'fits':True,'content_bytes':prep['content_size_bytes'],'package_bytes':prep['container_size_bytes'],'capacity_bytes':prep['capacity_bytes'],'required_units':prep['required_units'],'padding_bits':prep['padding_bits'],'verdict':dec['verdict'],'checks':dec['evidence']['checks'],'exact_payload':True,'comparison_max':comp['max_absolute_difference'],'comparison_mse':comp['mse'],'hash_algorithm':hash_algorithm}

    for name in covers:
        for i,p in enumerate(payloads,1):check(f'POS-{name}-{i:02}',lambda n=name,p=p,i=i:roundtrip(n,p,save=i==1))
        for depth in range(1,9):check(f'LSB-{name}-{depth}',lambda n=name,d=depth:roundtrip(n,payloads[0],d))
        for depth in [6,7,8]:
            tag='video' if name=='MP4' else name.lower();path=F/f'large_{tag}_needs_{depth}lsb.txt';p=('file',path.read_bytes(),path.name)
            def high(n=name,d=depth,p=p):
                kind,cover=covers[n]
                low=c.post('/api/prepare',data=inputs(kind,cover,p,d-1)).get_json()
                assert low.get('fits') is False,low
                out=roundtrip(n,p,d);out['preceding_depth_fits']=False;return out
            check(f'LARGE-{name}-{depth}',high)
        print('Checked positive matrix/depth/capacity:',name,flush=True)

    for name,(kind,cover) in covers.items():
        blob,p,enc=baseline[name]
        def neg_depth(kind=kind,blob=blob):
            out=decode(kind,blob,2);assert out['verdict']!='Authentic';return {'verdict':out['verdict'],'reason':out['evidence']['reason_code']}
        check(f'VER-{name}-01',neg_depth)
        for offset in [101,1000]:
            def neg_offset(kind=kind,blob=blob,offset=offset):
                out=decode(kind,blob,offset=offset);assert out['verdict']=='Payload Missing',out;return {'verdict':out['verdict'],'reason':out['evidence']['reason_code']}
            check(f'VER-{name}-02-offset-{offset}',neg_offset)
        def wrong_key(kind=kind,blob=blob):
            out=decode(kind,blob,key=(F/'wrong_alice_public.pem').read_text());assert out['verdict']=='Signature Invalid',out;return {'verdict':out['verdict'],'reason':out['evidence']['reason_code'],'payload_returned':bool(out['data_base64'])}
        check(f'VER-{name}-03',wrong_key)
        for mode,expected,reason in [('payload','Cannot Verify','DECRYPTION_FAILED'),('cover','Tampered','COVER_HASH_MISMATCH')]:
            def mutate(kind=kind,blob=blob,mode=mode,expected=expected,reason=reason):
                mod=c.post('/api/demo/tamper',data={'cover_type':kind,'num_lsb':'1','start_mode':'manual','manual_offset':'100','tamper_mode':mode,'stego_file':(io.BytesIO(blob),'stego.'+('mkv' if kind=='video' else 'png' if kind=='image' else 'wav'))}).get_json()
                assert 'error' not in mod,mod
                out=decode(kind,base64.b64decode(mod['stego_base64']));assert out['verdict']==expected and out['evidence']['reason_code']==reason,out
                return {'verdict':out['verdict'],'reason':out['evidence']['reason_code'],'payload_returned':bool(out['data_base64'])}
            check(f'VER-{name}-'+('04' if mode=='payload' else '05'),mutate)
        def original(kind=kind,cover=cover):
            out=decode(kind,cover.read_bytes());assert out['verdict']=='Payload Missing',out;return {'verdict':out['verdict'],'reason':out['evidence']['reason_code']}
        check(f'VER-{name}-06',original)

    def blind_spot():
        blob=baseline['PNG'][0];carrier=image_lsb.load_image_carrier(blob);carrier.array[0]^=1
        out=decode('image',image_lsb.carrier_to_png_bytes(carrier));assert out['verdict']=='Authentic',out
        return {'verdict':out['verdict'],'mutation':'low bit of value 0 outside package'}
    check('VER-EDGE-12',blind_spot)
    def header_corruption():
        carrier=image_lsb.load_image_carrier(baseline['PNG'][0]);carrier.array[100]^=1
        out=decode('image',image_lsb.carrier_to_png_bytes(carrier));assert out['verdict']=='Payload Missing',out
        return {'verdict':out['verdict'],'reason':out['evidence']['reason_code']}
    check('VER-EDGE-10',header_corruption)
    def wrong_bob():
        out=decode('image',baseline['PNG'][0],use_saved_bob='off',decryption_private_file=(io.BytesIO((F/'wrong_bob_private.pem').read_bytes()),'wrong_bob_private.pem'))
        assert out['verdict']=='Cannot Verify' and out['evidence']['reason_code']=='DECRYPTION_FAILED',out
        return {'verdict':out['verdict'],'reason':out['evidence']['reason_code']}
    check('API-04',wrong_bob)
    for name in covers:check('SHA512-'+name,lambda n=name:roundtrip(n,payloads[0],2,hash_algorithm='SHA-512'))
    for path in [F/'no_audio.mp4',ROOT/'samples/video/sample-001.avi']:
        def noaudio(path=path):
            result=c.post('/api/prepare',data=inputs('video',path,payloads[0],1))
            assert result.status_code==400 and 'no audio track' in result.get_json()['error'],result.get_json()
            return result.get_json()
        check('NO-AUDIO-'+path.name,noaudio)
    for first,second in [(F/'cover_rgb.png',F/'mismatch_dimensions.png'),(F/'cover_pcm16.wav',F/'mismatch_duration.wav'),(F/'cover_pcm16.wav',F/'mismatch_rate.wav'),(F/'cover_pcm16.wav',F/'mismatch_channels.wav')]:
        def mismatch(first=first,second=second):
            kind='image' if first.suffix=='.png' else 'audio'
            result=c.post('/api/compare',data={'cover_type':kind,'original_file':(io.BytesIO(first.read_bytes()),first.name),'stego_file':(io.BytesIO(second.read_bytes()),second.name)})
            assert result.status_code==400 and 'matching dimensions' in result.get_json()['error'];return result.get_json()
        check('CMP-MISMATCH-'+second.name,mismatch)
    for name in covers:
        def same(name=name):
            kind,path=covers[name]
            out=c.post('/api/compare',data={'cover_type':kind,'original_file':(io.BytesIO(path.read_bytes()),path.name),'stego_file':(io.BytesIO(path.read_bytes()),path.name)}).get_json()
            assert out['mse']==0 and out['changed_values']==0 and out['psnr_db'] is None,out
            return {'mse':out['mse'],'changed_values':out['changed_values'],'psnr_db':out['psnr_db'],'snr':out.get('audio_metrics',{}).get('snr_display')}
        check('CMP-IDENTICAL-'+name,same)

if __name__=='__main__':main()
