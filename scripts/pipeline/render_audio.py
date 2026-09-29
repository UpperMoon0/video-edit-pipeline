"""Audio is always anchored to the video frame-grid duration."""


def add_audio(timeline, command, filters, index, measurement=None, normalization=True):
    total = timeline.duration
    audio = timeline.spec['audio']
    filters.append(f'[0:a:0]aresample=48000:async=1:first_pts=0,apad,atrim=duration={total:.9f},asetpts=N/SR/TB[bed]')
    background = ['bed']
    voice = None
    if audio.get('voiceover'):
        command += ['-ss', str(audio.get('voiceover_source_in', 0)), '-i', str(timeline.asset(audio['voiceover']))]
        start = audio.get('voiceover_start', 0)
        filters.append(f'[{index}:a:0]asetpts=PTS-STARTPTS,aresample=48000,'
            f'aformat=sample_fmts=fltp:channel_layouts=stereo,highpass=f=70,lowpass=f=10000,'
            f'volume={audio.get("voiceover_volume", 1)},adelay={round(start * 48000)}S:all=1,'
            f'apad,atrim=duration={total:.9f},asetpts=N/SR/TB[voice]')
        voice = 'voice'
        index += 1
    for kind in ('music', 'sfx'):
        for number, track in enumerate(audio.get(kind, [])):
            duration = track['end'] - track['start'] if kind == 'music' else track['duration']
            original_duration = track.get('_original_duration', duration)
            phase = track.get('_fade_phase', 0)
            fade_in = track.get('fade_in', min(1, original_duration / 2) if kind == 'music' else 0)
            fade_out = track.get('fade_out', min(1 if kind == 'music' else .05, original_duration / 2))
            volume = track.get('volume', .1 if kind == 'music' else .15)
            label = f'{kind}{number}'
            command += ['-ss', str(track.get('source_in', 0)), '-i', str(timeline.asset(track['source']))]
            chain = f'[{index}:a:0]atrim=duration={duration:.9f},asetpts=PTS-STARTPTS,aresample=48000,'
            chain += f'aformat=sample_fmts=fltp:channel_layouts=stereo,volume={volume},asetpts=PTS+{phase:.9f}/TB'
            if fade_in:
                chain += f',afade=t=in:st=0:d={fade_in:.9f}'
            if fade_out:
                chain += f',afade=t=out:st={original_duration - fade_out:.9f}:d={fade_out:.9f}'
            chain += f',asetpts=PTS-STARTPTS,adelay={round(track["start"] * 48000)}S:all=1[{label}]'
            filters.append(chain)
            background.append(label)
            index += 1
    filters.append(''.join(f'[{label}]' for label in background) +
        f'amix=inputs={len(background)}:duration=first:dropout_transition=0:normalize=0[background]')
    mixed = 'background'
    if voice:
        if audio.get('ducking', {}).get('enabled'):
            duck = audio['ducking']
            filters.append('[voice]asplit=2[dryvoice][sidechain]')
            filters.append(f'[background][sidechain]sidechaincompress=threshold={duck.get("threshold", .05)}:'
                f'ratio={duck.get("ratio", 8)}:attack=20:release=250[ducked]')
            mixed, voice = 'ducked', 'dryvoice'
        filters.append(f'[{mixed}][{voice}]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mixed]')
        mixed = 'mixed'
    finish = f'[{mixed}]apad,atrim=duration={total:.9f},asetpts=N/SR/TB'
    if normalization and audio.get('loudness'):
        target = audio['loudness']
        finish += f',loudnorm=I={target["integrated"]}:TP={target["true_peak"]}:LRA={target.get("range", 11)}'
        if measurement:
            finish += ''.join(':' + key + '=' + str(value) for key, value in measurement.items()) + ':linear=true'
        finish += ',aresample=48000'
    filters.append(finish + '[outa]')
    return index
