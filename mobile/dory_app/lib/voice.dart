import 'dart:async';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

/// Dory speaks and listens in US English only.
const doryLocale = 'en-US';

/// Listening and speaking, using Android's built-in engines (free, on the phone).
class Voice {
  final SpeechToText _stt = SpeechToText();
  final FlutterTts _tts = FlutterTts();
  bool _ready = false;
  String? _localeId;
  Completer<String>? _pending;
  String _lastWords = '';
  // Bumped by every speak() and stop(), so an older line can never play over a newer one.
  int _speech = 0;

  /// Called with each partial transcript while the person is speaking.
  void Function(String words)? onPartial;

  /// Set when the family voice is switched on: returns the line as WAV audio, or null
  /// (voice server off...), in which case the phone voice speaks it.
  Future<Uint8List?> Function(String text)? familyVoice;
  final AudioPlayer _player = AudioPlayer();

  Future<bool> init() async {
    if (_ready) return true;
    _ready = await _stt.initialize(onStatus: _onStatus, onError: _onError);
    if (_ready) _localeId = await _matchLocale(doryLocale);

    await _tts.awaitSpeakCompletion(true);
    await _tts.setLanguage(doryLocale);
    await _pickNaturalVoice();
    await _tts.setSpeechRate(0.48); // close to a normal talking pace; slower sounds robotic
    await _tts.setPitch(1.0);
    return _ready;
  }

  /// The best-sounding US English voice on the phone, preferring ones that work offline
  /// (no wait for the network before Dory starts talking).
  Future<void> _pickNaturalVoice() async {
    try {
      const rank = {'very high': 4, 'high': 3, 'normal': 2, 'low': 1};
      final voices = [
        for (final v in (await _tts.getVoices) as List)
          if (v is Map && '${v['locale']}'.toLowerCase().replaceAll('_', '-') == 'en-us') v
      ];
      int score(Map v) => (rank[v['quality']] ?? 0) * 2 + (v['network_required'] == '1' ? 0 : 1);
      voices.sort((a, b) => score(b).compareTo(score(a)));
      if (voices.isNotEmpty) {
        await _tts.setVoice({'name': '${voices.first['name']}', 'locale': '${voices.first['locale']}'});
      }
    } catch (_) {
      // Keep the phone's default voice for the language.
    }
  }

  Future<String?> _matchLocale(String wanted) async {
    final norm = wanted.replaceAll('-', '_').toLowerCase();
    final locales = await _stt.locales();
    for (final l in locales) {
      if (l.localeId.replaceAll('-', '_').toLowerCase() == norm) return l.localeId;
    }
    for (final l in locales) {
      if (l.localeId.toLowerCase().startsWith('en')) return l.localeId;
    }
    return (await _stt.systemLocale())?.localeId;
  }

  /// Speaks [text] to the end. [onStart] runs the moment the voice starts, so the words
  /// appear on screen together with the sound.
  Future<void> speak(String text, {void Function()? onStart}) async {
    final id = ++_speech;
    await _tts.stop();
    await _player.stop();
    if (text.trim().isEmpty) return;
    if (familyVoice != null && await _speakAsFamily(text, id, onStart)) return;
    if (id != _speech) return;
    onStart?.call();
    await _tts.speak(text);
  }

  /// The first sentence is made on its own so the family voice starts quickly; the rest is made
  /// in one piece while that plays, so it flows on without a break between sentences.
  Future<bool> _speakAsFamily(String text, int id, void Function()? onStart) async {
    final parts = _firstSentenceAndRest(text);
    final first = await familyVoice!(parts.$1);
    if (first == null || id != _speech) return false;
    final rest = parts.$2.isEmpty ? null : familyVoice!(parts.$2);
    onStart?.call();
    if (!await play(first) || id != _speech) return id != _speech;
    final restAudio = await rest;
    if (id != _speech) return true;
    if (parts.$2.isNotEmpty) {
      if (restAudio == null || !await play(restAudio)) {
        if (id == _speech) await _tts.speak(parts.$2);
      }
    }
    return true;
  }

  static (String, String) _firstSentenceAndRest(String text) {
    final t = text.trim();
    final m = RegExp(r'^.{12,}?[.!?](\s+|$)').firstMatch(t);
    if (m == null) return (t, '');
    return (t.substring(0, m.end).trim(), t.substring(m.end).trim());
  }

  /// Plays WAV bytes to the end. False if playback failed.
  Future<bool> play(Uint8List wav) async {
    try {
      final done = _player.onPlayerComplete.first;
      await _player.play(BytesSource(wav, mimeType: 'audio/wav'));
      await done.timeout(const Duration(minutes: 2));
      return true;
    } catch (_) {
      await _player.stop();
      return false;
    }
  }

  /// Listens once. Returns what the person said, or '' if they said nothing.
  Future<String> listen(
      {Duration listenFor = const Duration(seconds: 20), Duration pauseFor = const Duration(seconds: 3)}) async {
    if (!_ready) return '';
    await _stt.cancel();
    // Let the end of Dory's own voice fade, so the microphone doesn't pick it up.
    await Future.delayed(const Duration(milliseconds: 350));
    _lastWords = '';
    final completer = Completer<String>();
    _pending = completer;
    try {
      await _stt.listen(
        onResult: _onResult,
        // ignore: deprecated_member_use
        listenFor: listenFor,
        // ignore: deprecated_member_use
        pauseFor: pauseFor,
        // ignore: deprecated_member_use
        localeId: _localeId,
      );
    } catch (_) {
      _finish();
    }
    // Safety net in case the engine never reports that it stopped.
    return completer.future.timeout(listenFor + const Duration(seconds: 5), onTimeout: () {
      _stt.stop();
      return _lastWords;
    });
  }

  void _onResult(SpeechRecognitionResult r) {
    if (_pending == null) return; // a late result from an earlier turn
    _lastWords = r.recognizedWords;
    onPartial?.call(_lastWords);
    if (r.finalResult) _finish();
  }

  void _onStatus(String status) {
    if (status == SpeechToText.doneStatus || status == SpeechToText.notListeningStatus) {
      // Give a final result a moment to arrive before giving up.
      Future.delayed(const Duration(milliseconds: 400), _finish);
    }
  }

  void _onError(SpeechRecognitionError e) => _finish();

  void _finish() {
    final c = _pending;
    if (c != null && !c.isCompleted) {
      _pending = null;
      c.complete(_lastWords.trim());
    }
  }

  Future<void> stop() async {
    _speech++;
    await _stt.cancel();
    await _tts.stop();
    await _player.stop();
    _finish();
  }
}
