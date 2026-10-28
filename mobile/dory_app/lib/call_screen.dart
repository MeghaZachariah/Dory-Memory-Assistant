import 'package:flutter/material.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';

import 'api.dart';
import 'calls.dart';
import 'settings.dart';
import 'theme.dart';
import 'voice.dart';

enum _Phase { connecting, speaking, listening, thinking, ended }

/// The screen during a call with Dory. Everything is spoken; text is shown large as a backup.
class CallScreen extends StatefulWidget {
  const CallScreen({super.key, required this.mode, this.callId});
  final CallMode mode;
  final String? callId;

  @override
  State<CallScreen> createState() => _CallScreenState();
}

class _CallScreenState extends State<CallScreen> {
  final Voice _voice = Voice();
  late DoryApi _api;
  _Phase _phase = _Phase.connecting;
  String _doryLine = '';
  String _heard = '';
  bool _hungUp = false;
  bool _closing = false;
  // The evening call so far, kept so it can still be saved if the call ends early.
  final List<Map<String, String>> _eveningTurns = [];
  bool _eveningSaved = false;

  static final _goodbye = RegExp(
      r"\b(bye|goodbye|good night|that's all|that is all|no thanks|no thank you|nothing else|stop)\b",
      caseSensitive: false);

  @override
  void initState() {
    super.initState();
    _voice.onPartial = (w) => _set(heard: w);
    _run();
  }

  bool get _active => mounted && !_hungUp;

  void _set({_Phase? phase, String? dory, String? heard}) {
    if (!mounted) return;
    setState(() {
      if (phase != null) _phase = phase;
      if (dory != null) _doryLine = dory;
      if (heard != null) _heard = heard;
    });
  }

  Future<void> _say(String text) async {
    if (!_active) return;
    _set(phase: _Phase.speaking, dory: text, heard: '');
    await _voice.speak(text);
  }

  Future<String> _listen() async {
    if (!_active) return '';
    _set(phase: _Phase.listening, heard: '');
    final words = await _voice.listen();
    return _active ? words : '';
  }

  Future<void> _run() async {
    final settings = await DorySettings.load();
    _api = DoryApi(settings);
    await _voice.init(settings.locale);
    if (settings.useFamilyVoice) _voice.familyVoice = _api.speakAsFamily;
    if (widget.callId != null) await FlutterCallkitIncoming.setCallConnected(widget.callId!);
    try {
      switch (widget.mode) {
        case CallMode.briefing:
          await _briefing();
        case CallMode.evening:
          await _evening(settings);
        case CallMode.ask:
          await _ask(settings);
      }
    } on DoryApiException {
      await _say("Sorry, I can't reach my notes right now. Please try again in a little while.");
    }
    await _end();
  }

  Future<void> _briefing() async {
    _set(phase: _Phase.thinking);
    await _say(await _api.briefing());
  }

  Future<void> _evening(DorySettings settings) async {
    final turns = _eveningTurns;
    while (_active) {
      _set(phase: _Phase.thinking);
      final next = await _api.eveningTurn(turns);
      turns.add({'speaker': 'Dory', 'text': next.say});
      if (next.done) _eveningSaved = true; // the server saved the memories with its closing line
      await _say(next.say);
      if (next.done) return;
      var heard = await _listen();
      if (heard.isEmpty && _active) {
        await _say('Sorry, I didn\'t hear you. Take your time.');
        heard = await _listen();
      }
      if (heard.isNotEmpty) {
        turns.add({'speaker': settings.personName.isEmpty ? 'Person' : settings.personName, 'text': heard});
      }
    }
  }

  Future<void> _ask(DorySettings settings) async {
    final name = settings.personName.isEmpty ? '' : ', ${settings.personName}';
    await _say('Hello$name. I’m right here. What would you like to know?');
    var silences = 0;
    final history = <Map<String, String>>[];
    final me = settings.personName.isEmpty ? 'Person' : settings.personName;
    while (_active) {
      final heard = await _listen();
      if (heard.isEmpty) {
        silences++;
        if (silences >= 2) {
          await _say("I'm here whenever you need me. Goodbye.");
          return;
        }
        await _say("I'm listening.");
        continue;
      }
      silences = 0;
      if (_goodbye.hasMatch(heard)) {
        await _say('All right. Goodbye for now.');
        return;
      }
      _set(phase: _Phase.thinking);
      final reply = await _api.chat(heard, history: history);
      history
        ..add({'speaker': me, 'text': heard})
        ..add({'speaker': 'Dory', 'text': reply.reply});
      await _say(reply.reply);
    }
  }

  Future<void> _end() async {
    if (_closing) return;
    _closing = true;
    _hungUp = true;
    await _voice.stop();
    await _saveEveningIfCutShort();
    await FlutterCallkitIncoming.endAllCalls();
    if (mounted) {
      _set(phase: _Phase.ended);
      await Future.delayed(const Duration(milliseconds: 900));
      if (mounted && Navigator.of(context).canPop()) Navigator.of(context).pop();
    }
  }

  /// Hung up before Dory's goodbye: what the person said still becomes memories.
  Future<void> _saveEveningIfCutShort() async {
    if (widget.mode != CallMode.evening || _eveningSaved) return;
    if (!_eveningTurns.any((t) => t['speaker'] != 'Dory')) return;
    _eveningSaved = true;
    try {
      await _api.finishEvening(_eveningTurns).timeout(const Duration(seconds: 20));
    } catch (_) {
      // Nothing more to do: the call has ended either way.
    }
  }

  String get _phaseLabel => switch (_phase) {
        _Phase.connecting => 'Dory is coming',
        _Phase.speaking => 'Dory is speaking',
        _Phase.listening => 'I’m listening',
        _Phase.thinking => 'Let me think',
        _Phase.ended => 'Call ended',
      };

  @override
  void dispose() {
    _hungUp = true;
    _voice.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return PopScope(
      canPop: false,
      child: Scaffold(
        backgroundColor: DoryColors.page,
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 32, 24, 32),
            child: Column(
              children: [
                const DoryLogo(onDark: false),
                const SizedBox(height: 20),
                _PhaseChip(label: _phaseLabel, listening: _phase == _Phase.listening),
                const SizedBox(height: 32),
                Expanded(
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(_doryLine, style: display(32).copyWith(height: 1.25, letterSpacing: -0.6)),
                        if (_heard.isNotEmpty) ...[
                          const SizedBox(height: 28),
                          Text('YOU SAID', style: eyebrow()),
                          const SizedBox(height: 6),
                          Text(_heard, style: t.headlineSmall?.copyWith(color: DoryColors.primary, height: 1.35)),
                        ],
                      ],
                    ),
                  ),
                ),
                SizedBox(
                  width: double.infinity,
                  height: 84,
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: DoryColors.hangUp,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(42)),
                    ),
                    onPressed: _phase == _Phase.ended ? null : _end,
                    icon: const Icon(Icons.call_end, size: 36),
                    label: Text('End call', style: t.headlineSmall?.copyWith(color: Colors.white)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _PhaseChip extends StatelessWidget {
  const _PhaseChip({required this.label, required this.listening});
  final String label;
  final bool listening;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
      decoration: BoxDecoration(
        color: listening ? DoryColors.primary : DoryColors.primarySoft,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(listening ? Icons.mic : Icons.graphic_eq, color: listening ? Colors.white : DoryColors.primary),
        const SizedBox(width: 8),
        Text(label,
            style:
                Theme.of(context).textTheme.titleLarge?.copyWith(color: listening ? Colors.white : DoryColors.primary)),
      ]),
    );
  }
}
