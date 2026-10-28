import 'dart:async';
import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import 'api.dart';
import 'settings.dart';
import 'theme.dart';

const _minSeconds = 15;
const _maxSeconds = 90;

/// Optional: a family member reads a short paragraph so Dory can speak in their voice.
/// The first sentence they read is their consent. Dory still introduces itself as Dory.
class VoiceSetupScreen extends StatefulWidget {
  const VoiceSetupScreen({super.key});

  @override
  State<VoiceSetupScreen> createState() => _VoiceSetupScreenState();
}

class _VoiceSetupScreenState extends State<VoiceSetupScreen> {
  DorySettings? _s;
  late DoryApi _api;
  FamilyVoiceStatus? _status;
  String? _error;
  bool _rerecord = false;
  bool _busy = false;

  final _speaker = TextEditingController();
  bool _agreed = false;
  final _recorder = AudioRecorder();
  final _player = AudioPlayer();
  String? _path;
  bool _recording = false;
  int _seconds = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _speaker.addListener(() => setState(() {}));
    _load();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _recorder.dispose();
    _player.dispose();
    _speaker.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final s = await DorySettings.load();
    _api = DoryApi(s);
    try {
      final st = await _api.voiceStatus();
      if (!mounted) return;
      setState(() {
        _s = s;
        _status = st;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _s = s;
        _error = 'Can\'t reach the Dory server. Check the address in Settings.';
      });
    }
  }

  String get _person => (_s?.personName.isNotEmpty ?? false) ? _s!.personName : 'them';
  String get _speakerName => _speaker.text.trim();

  String get _paragraph => 'I\'m ${_speakerName.isEmpty ? '[your name]' : _speakerName}, and I agree to Dory '
      'using my voice to talk with $_person.\n\n'
      'Good morning! It\'s a bright, calm day today. Did you sleep well? There\'s no hurry, so let\'s take '
      'things slowly. Your family loves you very much, and we\'ll talk again this evening. If you\'re ever '
      'unsure about something, just ask, and someone will help you. The garden looks lovely after the rain, '
      'and the birds have been singing since six o\'clock. Have a cup of tea, and enjoy the sunshine.';

  Future<void> _toggleRecording() async {
    if (_recording) return _stop();
    if (!await _recorder.hasPermission()) {
      _snack('Please allow the microphone for Dory.');
      return;
    }
    await _player.stop();
    final dir = await getTemporaryDirectory();
    final path = '${dir.path}/family_voice.wav';
    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.wav, sampleRate: 22050, numChannels: 1),
      path: path,
    );
    setState(() {
      _recording = true;
      _seconds = 0;
      _path = null;
    });
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      setState(() => _seconds++);
      if (_seconds >= _maxSeconds) _stop();
    });
  }

  Future<void> _stop() async {
    _timer?.cancel();
    final path = await _recorder.stop();
    if (!mounted) return;
    setState(() {
      _recording = false;
      _path = path;
    });
  }

  Future<void> _upload() async {
    final path = _path;
    if (path == null) return;
    setState(() => _busy = true);
    try {
      final st = await _api.uploadVoice(await File(path).readAsBytes(), _speakerName);
      final s = _s!..useFamilyVoice = true;
      await s.save();
      if (!mounted) return;
      setState(() {
        _status = st;
        _rerecord = false;
        _path = null;
        _agreed = false;
      });
      _snack(st.serverOnline
          ? 'Saved. Dory will now speak in $_speakerName\'s voice.'
          : 'Saved. The voice server is off right now, so Dory uses the phone voice until it\'s started.');
    } catch (e) {
      _snack('Couldn\'t save the recording: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _test() async {
    setState(() => _busy = true);
    final audio = await _api.speakAsFamily('Hello $_person, it\'s Dory. I hope you\'re having a lovely day.');
    if (mounted) setState(() => _busy = false);
    if (audio == null) {
      _snack('The voice server isn\'t running right now. Dory will use the phone voice.');
      return;
    }
    await _player.play(BytesSource(audio, mimeType: 'audio/wav'));
  }

  Future<void> _delete() async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Delete this voice?'),
        content: Text('The recording of ${_status?.speakerName ?? 'the family member'} will be deleted from the '
            'Dory server and the voice server. Dory will use the phone voice.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('Delete')),
        ],
      ),
    );
    if (yes != true) return;
    await _api.deleteVoice();
    final s = _s!..useFamilyVoice = false;
    await s.save();
    await _load();
  }

  void _snack(String text) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final st = _status;
    return Scaffold(
      appBar: AppBar(title: Text('Family voice', style: display(28))),
      body: _s == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
              children: [
                Text(
                  'Optional. A family member reads a short paragraph, and Dory speaks to $_person in their voice. '
                  'Dory still introduces itself as Dory.',
                  style: t.bodyLarge?.copyWith(color: DoryColors.muted),
                ),
                const SizedBox(height: 16),
                if (_error != null)
                  _Card(child: Text(_error!, style: t.bodyLarge?.copyWith(color: DoryColors.warn)))
                else if (st != null && st.enabled && !_rerecord)
                  _currentVoice(st, t)
                else
                  ..._recordSteps(t),
              ],
            ),
    );
  }

  Widget _currentVoice(FamilyVoiceStatus st, TextTheme t) => _Card(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(color: DoryColors.primarySoft, borderRadius: BorderRadius.circular(13)),
              child: const Icon(Icons.record_voice_over_outlined, color: DoryColors.primary),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${st.speakerName}\'s voice', style: t.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
                Row(children: [
                  Icon(Icons.circle, size: 9, color: st.serverOnline ? DoryColors.ok : DoryColors.warn),
                  const SizedBox(width: 6),
                  Text(st.serverOnline ? 'Voice server on' : 'Voice server off (phone voice is used)',
                      style: t.bodyMedium?.copyWith(color: DoryColors.muted)),
                ]),
              ]),
            ),
          ]),
          const Divider(height: 28, color: DoryColors.border),
          Row(children: [
            Expanded(child: Text('Use in calls', style: t.titleMedium)),
            Switch(
              value: _s!.useFamilyVoice,
              onChanged: (v) async {
                setState(() => _s!.useFamilyVoice = v);
                await _s!.save();
              },
            ),
          ]),
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: _busy ? null : _test,
            icon: const Icon(Icons.play_arrow_rounded),
            label: Text(_busy ? 'Making the sample…' : 'Test voice'),
          ),
          const SizedBox(height: 8),
          OutlinedButton(onPressed: () => setState(() => _rerecord = true), child: const Text('Record again')),
          TextButton(
            onPressed: _delete,
            style: TextButton.styleFrom(foregroundColor: DoryColors.hangUp),
            child: const Text('Delete voice'),
          ),
        ]),
      );

  List<Widget> _recordSteps(TextTheme t) {
    final canRecord = _speakerName.isNotEmpty && _agreed;
    final mmss = '${_seconds ~/ 60}:${(_seconds % 60).toString().padLeft(2, '0')}';
    return [
      _Card(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('1. Who is recording?', style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 10),
          TextField(
            controller: _speaker,
            enabled: !_recording,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(hintText: 'Your name, e.g. Anu', border: OutlineInputBorder()),
          ),
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            value: _agreed,
            onChanged: _recording ? null : (v) => setState(() => _agreed = v ?? false),
            title: Text('This is my own voice, and I agree to Dory using it to talk with $_person. '
                'I can delete it at any time.'),
          ),
        ]),
      ),
      const SizedBox(height: 12),
      _Card(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('2. Read this aloud, slowly and naturally', style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text('Somewhere quiet, phone about a hand\'s width from your mouth.',
              style: t.bodyMedium?.copyWith(color: DoryColors.muted)),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(color: DoryColors.page, borderRadius: BorderRadius.circular(14)),
            child: Text(_paragraph, style: t.titleMedium?.copyWith(height: 1.5)),
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 58,
            child: FilledButton.icon(
              onPressed: canRecord ? _toggleRecording : null,
              style: FilledButton.styleFrom(backgroundColor: _recording ? DoryColors.hangUp : DoryColors.primary),
              icon: Icon(_recording ? Icons.stop_rounded : Icons.mic_rounded),
              label: Text(_recording ? 'Stop  ·  $mmss' : (_path == null ? 'Start recording' : 'Record again'),
                  style: t.titleMedium?.copyWith(color: Colors.white, fontWeight: FontWeight.w700)),
            ),
          ),
          if (!canRecord && !_recording)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text('Enter your name and tick the box first.',
                  style: t.bodyMedium?.copyWith(color: DoryColors.muted)),
            ),
        ]),
      ),
      if (_path != null && !_recording) ...[
        const SizedBox(height: 12),
        _Card(
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text('3. Check and save', style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Text('Recorded $mmss.', style: t.bodyMedium?.copyWith(color: DoryColors.muted)),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () => _player.play(DeviceFileSource(_path!)),
              icon: const Icon(Icons.play_arrow_rounded),
              label: const Text('Listen back'),
            ),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: _busy || _seconds < _minSeconds ? null : _upload,
              child: Text(_busy ? 'Saving…' : 'Use this recording'),
            ),
            if (_seconds < _minSeconds)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text('Please read for at least $_minSeconds seconds.',
                    style: t.bodyMedium?.copyWith(color: DoryColors.warn)),
              ),
          ]),
        ),
      ],
      if (_rerecord) TextButton(onPressed: () => setState(() => _rerecord = false), child: const Text('Cancel')),
    ];
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: DoryColors.card,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: DoryColors.border),
        ),
        child: child,
      );
}
